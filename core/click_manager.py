"""MoonDeck 卡片右键菜单管理器

职责:
- 拦截鼠标右键事件
- 弹出上下文菜单(显隐/刷新/置顶/关闭)
- 触发对应动作

设计:
- 同样走事件过滤器(挂在画布上)
- 菜单用 QMenu(系统原生外观)
- 每个动作 emit EventBus 事件,业务侧订阅处理
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtGui import QAction, QMouseEvent
from PyQt6.QtWidgets import QMenu, QWidget

from .event_bus import EventBus


class ClickManager(QObject):
    """卡片右键菜单管理器

    菜单项:
    - 显示/隐藏(根据当前 visible 状态切换)
    - 刷新(emit "card:refresh")
    - 置顶(emit "card:raise")
    - 保存布局(emit "card:save_layout")
    - 关闭卡片(emit "card:close",画布侧订阅并 remove)
    """

    def __init__(
        self,
        canvas: QWidget,
        bus: Optional[EventBus] = None,
        enabled: bool = True,
    ):
        # 兼容 dispatcher 容器模式(独立顶层 widget 架构)
        self._is_dispatcher = hasattr(canvas, "install_event_filter_to_all")
        if self._is_dispatcher:
            super().__init__()
        else:
            super().__init__(canvas)
        self._canvas = canvas
        self._bus = bus or EventBus.instance()
        self._enabled = bool(enabled)
        if self._is_dispatcher:
            canvas.install_event_filter_to_all(self)
        else:
            self._canvas.installEventFilter(self)

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)

    def is_enabled(self) -> bool:
        return self._enabled

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if not self._enabled:
            return False
        # 关键修复:dispatcher 模式下,obj 是 widget,不是 dispatcher 本身
        if self._is_dispatcher:
            try:
                known = list(self._canvas.all_cards())
            except Exception:
                known = []
            if obj not in known:
                return False
        else:
            if obj is not self._canvas:
                return False
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if event.button() != Qt.MouseButton.RightButton:
            return False
        # 找卡片:dispatcher 模式直接用 obj,否则走 _card_at 推断
        if self._is_dispatcher and obj in known:
            widget = obj
        else:
            global_pos = event.globalPosition().toPoint()
            widget = self._card_at(global_pos)
        if widget is None:
            return False
        card_id = getattr(widget, "card_id", None)
        if not card_id:
            return False
        # 弹菜单(全局坐标,菜单应该弹在屏幕坐标)
        try:
            global_pos = widget.mapToGlobal(event.position().toPoint())
        except Exception:
            global_pos = event.globalPosition().toPoint()
        self._show_menu(widget, card_id, global_pos)
        # 吞掉事件,避免穿透到画布
        return True

    def _card_at(self, global_pos: QPoint) -> Optional[QWidget]:
        local = self._canvas.mapFromGlobal(global_pos)
        cards = self._canvas.all_cards() if hasattr(self._canvas, "all_cards") else []
        for card in reversed(cards):
            if not card.isVisible():
                continue
            if card.geometry().contains(local):
                return card
        return None

    def _show_menu(self, widget: QWidget, card_id: str, global_pos: QPoint) -> None:
        # 2026-06-14 12:31 修复:_canvas 在某些路径下是 weakref._Dispatcher,需要拆包
        canvas = self._canvas
        if canvas is not None and not isinstance(canvas, QWidget):
            try:
                canvas = canvas()
            except Exception:
                canvas = None
        if canvas is None:
            canvas = widget  # 兜底用 widget 当 parent
        menu = QMenu(canvas)
        menu.setObjectName(f"context_menu_{card_id}")
        # 标题(不可点)
        title = menu.addAction(f"📌 {card_id}")
        title.setEnabled(False)
        menu.addSeparator()

        # 显示/隐藏
        is_visible = widget.isVisible()
        toggle = menu.addAction("👁 隐藏" if is_visible else "👁 显示")
        toggle.triggered.connect(lambda: self._toggle_visible(card_id))

        # 刷新
        refresh = menu.addAction("🔄 刷新")
        refresh.triggered.connect(lambda: self._fire("card:refresh", {"card_id": card_id}))

        # 置顶
        raise_act = menu.addAction("⬆ 置顶")
        raise_act.triggered.connect(lambda: self._raise_card(card_id))

        # 保存布局
        save_act = menu.addAction("💾 保存布局")
        save_act.triggered.connect(lambda: self._fire("card:save_layout", {"card_id": card_id}))

        menu.addSeparator()

        # 关闭
        close_act = menu.addAction("❌ 关闭卡片")
        close_act.triggered.connect(lambda: self._close_card(card_id))

        # 显示(系统原生,会在画布上层弹)
        try:
            menu.exec(global_pos)
        except Exception as e:
            print(f"[ClickManager] 弹菜单失败: {e}")

    # === 动作 ===

    def _toggle_visible(self, card_id: str) -> None:
        card = self._canvas.get_card(card_id) if hasattr(self._canvas, "get_card") else None
        if card is None:
            return
        new_state = not card.isVisible()
        card.setVisible(new_state)
        self._fire("card:visibility_changed", {"card_id": card_id, "visible": new_state})

    def _raise_card(self, card_id: str) -> None:
        card = self._canvas.get_card(card_id) if hasattr(self._canvas, "get_card") else None
        if card is None:
            return
        card.raise_()
        self._fire("card:raised", {"card_id": card_id})

    def _close_card(self, card_id: str) -> None:
        self._fire("card:close", {"card_id": card_id})

    def _fire(self, event_name: str, payload: Dict[str, Any]) -> None:
        try:
            self._bus.emit(event_name, payload)
        except Exception:
            pass
