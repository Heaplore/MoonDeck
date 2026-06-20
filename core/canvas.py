"""MoonDeck 画布主类

透明全屏窗口,承载所有卡片。

关键能力:
- 跨屏覆盖(所有显示器虚拟区域)
- 鼠标穿透(默认 click_through=True,Alt 唤起时关闭)
- Windows 扩展样式(WS_EX_LAYERED + WS_EX_TRANSPARENT + WS_EX_TOOLWINDOW)
- 卡片注册表(可挂载任意 CardBase 子类 或 独立 QWidget)
- 交互态切换(Alt 按住 / 松开)

两种卡片接入方式:
1. add_card(card: CardBase)     - 严格接口(虚函数/serialize 完整支持)
2. add_widget_card(card_id, w)  - 适配器(任何 QWidget 都能挂,模块独立原则)

注意:
- Canvas 不直接渲染任何内容,只承载 CardBase 子 widget
- 卡片自己 paint,自己响应事件(在自己的 QWidget 内部)
- Canvas 主要是"不抢焦点 + 鼠标穿透 + 容器" 三个职责
"""
from __future__ import annotations

import ctypes
import sys
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QGuiApplication, QPainter, QColor, QRadialGradient, QBrush, QLinearGradient
from PyQt6.QtWidgets import QWidget

from .card_base import CardBase
from .event_bus import EventBus
from .storage import StorageManager

# Windows 常量
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


class Canvas(QWidget):
    """透明全屏画布主窗口"""

    # 交互态切换 signal(给 CardBase 订阅)
    interactive_changed = pyqtSignal(bool)

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._config = config or {}
        self._cards: Dict[str, Any] = {}  # card_id -> widget(CardBase 或 QWidget)
        self._click_through: bool = bool(self._config.get("click_through", True))
        self._interactive: bool = False  # 是否处于交互态(Alt 按住)
        self._auto_save_timer: Optional[QTimer] = None

        # 窗口标志
        self._apply_window_flags()
        # 透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # 永远不抢焦点
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # 全屏覆盖所有屏
        self._span_all_screens()
        # 应用 Windows 扩展样式
        self._apply_win32_exstyle()

        # 监听 EventBus 事件
        self._bus = EventBus.instance()
        self._bus.subscribe("card:moved", self._on_card_moved)
        self._bus.subscribe("card:resized", self._on_card_resized)

        # 自动保存布局
        save_interval = int(self._config.get("auto_save_interval", 30)) * 1000
        if save_interval > 0:
            self._auto_save_timer = QTimer(self)
            self._auto_save_timer.timeout.connect(self._auto_save_all_layouts)
            self._auto_save_timer.start(save_interval)

    # === 窗口/样式 ===

    def _apply_window_flags(self) -> None:
        # 修复 2026-06-12: 从 WindowStaysOnBottomHint 改为 WindowStaysOnTopHint
        # 根因: 底部 z-order + WA_TranslucentBackground + WS_EX_LAYERED 三件套导致
        # DWM 不把 GDI SaveBits backbuffer 合成到屏幕 (EnumWindows 诊断证据)
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint  # 永远在顶部(修复 z-order)
            | Qt.WindowType.Tool  # 工具窗口(不在任务栏)
        )
        self.setWindowFlags(flags)

    def _span_all_screens(self) -> None:
        """全屏覆盖所有显示器"""
        if not self._config.get("span_all_screens", True):
            # 只主屏
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                self.setGeometry(screen.geometry())
            return
        # 虚拟几何(所有屏合并)
        screens = QGuiApplication.screens()
        if not screens:
            return
        geo = screens[0].geometry()
        for s in screens[1:]:
            geo = geo.united(s.geometry())
        self.setGeometry(geo)

    def _apply_win32_exstyle(self) -> None:
        """Windows 专属:设置画布扩展样式(分层 + 工具窗口)"""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_LAYERED
            ex_style |= WS_EX_TOOLWINDOW
            ex_style |= WS_EX_NOACTIVATE
            if self._click_through:
                ex_style |= WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception as e:
            print(f"[Canvas] 设置 Windows 扩展样式失败(非 Windows 或权限不足): {e}")

    def _set_click_through(self, transparent: bool) -> None:
        """动态切换鼠标穿透"""
        if sys.platform != "win32":
            self._click_through = transparent
            return
        try:
            hwnd = int(self.winId())
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if transparent:
                ex_style |= WS_EX_TRANSPARENT
            else:
                ex_style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            self._click_through = transparent
        except Exception as e:
            print(f"[Canvas] 切换 click_through 失败: {e}")

    # === 交互态 ===

    def enter_interactive_mode(self) -> None:
        """进入交互态(关闭鼠标穿透 + 抬高 z-order)"""
        if self._interactive:
            return
        self._interactive = True
        self._set_click_through(False)
        # 把所有卡片置顶
        self.raise_all_cards()
        # signal 通知
        self.interactive_changed.emit(True)
        self._bus.emit("canvas:interactive_on", {"ts": self._get_timestamp()})

    def exit_interactive_mode(self) -> None:
        """退出交互态(开启鼠标穿透 + 恢复底层)"""
        if not self._interactive:
            return
        self._interactive = False
        self._set_click_through(True)
        self.lower()  # 画布回到底层
        self.interactive_changed.emit(False)
        self._bus.emit("canvas:interactive_off", {"ts": self._get_timestamp()})

    def toggle_interactive(self) -> bool:
        if self._interactive:
            self.exit_interactive_mode()
        else:
            self.enter_interactive_mode()
        return self._interactive

    def is_interactive(self) -> bool:
        return self._interactive

    # === 卡片管理 ===

    def add_card(self, card: CardBase) -> None:
        """注册并显示一张 CardBase 卡片(严格接口)

        Args:
            card: CardBase 实例
        """
        if not isinstance(card, CardBase):
            raise TypeError(f"add_card 要求 CardBase 子类,收到 {type(card).__name__}")
        if not card.card_id:
            raise ValueError(f"卡片 {type(card).__name__} 没有设置 card_id")
        if card.card_id in self._cards:
            print(f"[Canvas] 警告: 卡片 {card.card_id} 已存在,替换")
            self.remove_card(card.card_id)

        self._cards[card.card_id] = card
        self._attach_window_props(card)
        self._restore_or_default_position(card)
        card.show()
        card.raise_()
        # 修复 2026-06-12: 显式触发 update 强制 paintEvent 跑
        card.update()
        print(f"[Canvas] 添加卡片: {card.card_id} ({card.card_name}) at ({card.x()},{card.y()})")

    def add_widget_card(
        self,
        card_id: str,
        widget: QWidget,
        card_name: str = "",
        visible: bool = True,
    ) -> None:
        """适配器:为"未继承 CardBase 但仍是 QWidget"的独立卡片提供接入

        用例:cards/token_card 严格遵守"独立模块"原则,不依赖画布核心。
        画布同样能包装它——只是失去 CardBase 的虚函数特性。

        Args:
            card_id: 唯一 ID
            widget: 任意 QWidget(自己设过 setWindowFlags、WA_TranslucentBackground)
            card_name: 可选显示名(只用于日志)
            visible: True=show,False=hide
        """
        if card_id in self._cards:
            print(f"[Canvas] 警告: 卡片 {card_id} 已存在,替换")
            self.remove_card(card_id)
        # 给 widget 打补丁属性(画布内部识别用)
        try:
            widget.card_id = card_id  # type: ignore[attr-defined]
            widget.card_name = card_name or type(widget).__name__  # type: ignore[attr-defined]
        except Exception:
            pass
        self._cards[card_id] = widget
        self._attach_window_props(widget)
        # 修复 2026-06-12: 卡片之前设了 WindowStaysOnTopHint, setParent 后 Qt 会创建
        # 新窗口, setWindowFlags 才会重设 (setParent 不会自动重设 flags)
        # 先 setParent, 再确保子 widget 是真正的 child (不是独立顶级窗口)
        widget.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        widget.setParent(self)
        self._restore_or_default_position(widget)
        if visible:
            widget.show()
            widget.raise_()
        print(f"[Canvas] 添加卡片(widget): {card_id} ({card_name or type(widget).__name__}) at ({widget.x()},{widget.y()})")

    def _attach_window_props(self, widget: QWidget) -> None:
        """子窗口:设 parent(挂画布)+ Windows 扩展样式

        修复 2026-06-12: 保留 setParent + WS_EX_LAYERED (画布本身有, 子 widget 跟画布风格统一)
        """
        # 先确保子 widget 是 child (setWindowFlags 必须在 setParent 之前调, 才能去掉顶级 window 标志)
        widget.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        widget.setParent(self)
        if sys.platform == "win32":
            try:
                hwnd = int(widget.winId())
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ex_style |= WS_EX_LAYERED
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            except Exception:
                pass

    def _restore_or_default_position(self, widget: QWidget) -> None:
        """从 storage 恢复布局,失败用 config 默认位置"""
        card_id = getattr(widget, "card_id", None)
        if not card_id:
            return
        storage = self._get_storage()
        saved = None
        if storage is not None:
            try:
                saved = storage.load_layout(card_id)
            except Exception:
                saved = None
        if saved is not None:
            # CardBase 走 serialize/deserialize 接口
            if isinstance(widget, CardBase):
                widget.deserialize(saved)
            else:
                # 普通 QWidget:手动 setGeometry
                try:
                    widget.setGeometry(
                        int(saved["x"]), int(saved["y"]),
                        int(saved["w"]), int(saved["h"]),
                    )
                except Exception:
                    pass
            return
        # 用 config 里 default_positions
        default_pos = self._config.get("default_positions", {}).get(card_id, {})
        if default_pos:
            try:
                x = int(default_pos.get("x", 100))
                y = int(default_pos.get("y", 100))
                w = int(default_pos.get("width", 200))
                h = int(default_pos.get("height", 200))
                widget.setGeometry(x, y, w, h)
            except Exception:
                pass

    def remove_card(self, card_id: str) -> None:
        """移除一张卡片"""
        if card_id not in self._cards:
            return
        card = self._cards.pop(card_id)
        card.hide()
        card.setParent(None)
        card.deleteLater()
        print(f"[Canvas] 移除卡片: {card_id}")

    def get_card(self, card_id: str) -> Optional[QWidget]:
        return self._cards.get(card_id)

    def all_cards(self) -> List[QWidget]:
        return list(self._cards.values())

    def raise_all_cards(self) -> None:
        """把所有卡片置顶"""
        for card in self._cards.values():
            try:
                card.raise_()
            except RuntimeError:
                pass  # widget 可能已被 GC

    def save_layout(self, card_id: str) -> None:
        """保存单卡片布局到 storage"""
        card = self._cards.get(card_id)
        if card is None:
            return
        storage = self._get_storage()
        if storage is None:
            return
        storage.save_layout(
            card_id,
            card.x(), card.y(),
            card.width(), card.height(),
            card.isVisible(),
        )

    def _auto_save_all_layouts(self) -> None:
        """定时器:批量保存所有布局"""
        for cid in self._cards:
            self.save_layout(cid)

    def _on_card_moved(self, payload: Any) -> None:
        """EventBus 回调:卡片移动"""
        if not isinstance(payload, dict):
            return
        cid = payload.get("card_id")
        if cid:
            self.save_layout(cid)

    def _on_card_resized(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        cid = payload.get("card_id")
        if cid:
            self.save_layout(cid)

    # === 内部辅助 ===

    def _get_storage(self) -> Optional[StorageManager]:
        try:
            return StorageManager.instance()
        except RuntimeError:
            return None

    @staticmethod
    def _get_timestamp() -> str:
        from datetime import datetime
        return datetime.now().isoformat(timespec="seconds")

    # === 绘制(深紫蓝径向渐变 + 左上角发光点) ===
    # v0.3 (2026-06-13): 参考 16:9 横向布局图,加科技感青蓝紫渐变

    def paintEvent(self, event) -> None:
        """画布背景:深紫蓝径向渐变 + 左上角冷青发光点"""
        from .theme import ThemeManager
        tm = ThemeManager.instance()
        d = tm.current() or {}
        if not d:
            return
        # 画布专用色(没配置回退到深色)
        start_hex = d.get("background_canvas_start") or d.get("background", "#0E1230")
        end_hex = d.get("background_canvas_end") or d.get("background_gradient_end", "#070918")
        glow_hex = d.get("background_glow") or d.get("accent", "#B4C8DC")
        try:
            start = QColor(start_hex)
            end = QColor(end_hex)
            glow = QColor(glow_hex)
        except Exception:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 1. 底色径向渐变(中心深紫蓝,边缘更黑)
        cx, cy = self.width() / 2, self.height() / 2
        max_r = (self.width() ** 2 + self.height() ** 2) ** 0.5 / 2
        grad = QRadialGradient(QPointF(cx, cy), max_r)
        grad.setColorAt(0.0, start)
        grad.setColorAt(1.0, end)
        painter.fillRect(self.rect(), QBrush(grad))
        # 2. 左上角冷青发光点(径向透明)
        glow_cx = self.width() * 0.12
        glow_cy = self.height() * 0.10
        glow_r = max(self.width(), self.height()) * 0.55
        glow_grad = QRadialGradient(QPointF(glow_cx, glow_cy), glow_r)
        glow.setAlpha(70)  # 透明
        glow_grad.setColorAt(0.0, glow)
        glow_grad.setColorAt(0.4, QColor(glow.red(), glow.green(), glow.blue(), 25))
        glow_grad.setColorAt(1.0, QColor(glow.red(), glow.green(), glow.blue(), 0))
        painter.fillRect(self.rect(), QBrush(glow_grad))
        painter.end()

    # === 关闭 ===

    def shutdown(self) -> None:
        """关闭前清理"""
        # 保存所有布局
        self._auto_save_all_layouts()
        # 停 timer
        if self._auto_save_timer is not None:
            self._auto_save_timer.stop()
        # 移除所有卡片
        for cid in list(self._cards.keys()):
            self.remove_card(cid)
        print(f"[Canvas] 关闭,共清理 {len(self._cards)} 张卡片")
