"""MoonDeck 系统托盘 - QSystemTrayIcon 封装

职责:
- 启动时在 Windows 任务栏右下角放一个月亮图标
- 菜单项:
  * 显示/隐藏全部卡片
  * 单独显示/隐藏每张卡
  * 重置布局
  * 退出
- 双击托盘图标 = 显示/隐藏全部
- 托盘通知(比如下次刷新时间)

依赖:PyQt6
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QMenu, QSystemTrayIcon, QWidget
)

_LOG = logging.getLogger("moondeck.tray")

_HERE = Path(__file__).parent


# ============== 图标生成(emoji 画成 PNG,免去依赖资源) ==============

def _make_moon_icon(size: int = 64) -> QIcon:
    """加载 AI 生成的图标,失败时 fallback 到绘制"""
    # 尝试加载 AI 生成的图标
    icon_paths = [
        Path(__file__).parent.parent / 'assets' / 'moondeck_agnes_001.jpg',
        Path(__file__).parent.parent / 'assets' / 'moondeck.png',
    ]
    
    for icon_path in icon_paths:
        if icon_path.exists():
            pm = QPixmap(str(icon_path))
            if not pm.isNull():
                pm = pm.scaled(QSize(size, size),
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                return QIcon(pm)
    
    # fallback: 动态绘制
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    p.setBrush(QColor("#1a3a5c"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, size - 4, size - 4)

    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.setBrush(QColor("#FFE082"))
    p.drawEllipse(int(size * 0.22), int(size * 0.18), int(size * 0.55), int(size * 0.55))
    p.setBrush(QColor("#1a3a5c"))
    p.drawEllipse(int(size * 0.32), int(size * 0.12), int(size * 0.55), int(size * 0.55))

    p.setBrush(QColor("#FFFFFF"))
    p.setPen(Qt.PenStyle.NoPen)
    star_x = int(size * 0.78)
    star_y = int(size * 0.25)
    star_r = max(2, size // 16)
    p.drawEllipse(star_x - star_r, star_y - star_r, star_r * 2, star_r * 2)

    p.end()
    return QIcon(pm)


# ============== 托盘管理 ==============


class MoonDeckTray:
    """系统托盘封装

    用法:
        tray = MoonDeckTray(
            live_widgets={card_id: (widget, controller), ...},
            on_reset_layout=callback,
        )
        tray.show()
    """

    def __init__(
        self,
        live_widgets: Dict[str, Any],
        on_reset_layout: Optional[Callable[[], None]] = None,
        on_show_all: Optional[Callable[[], None]] = None,
        on_hide_all: Optional[Callable[[], None]] = None,
        on_visualizer_change: Optional[Callable[[str], None]] = None,
        available_visualizers: Optional[Dict[str, str]] = None,
        current_visualizer: str = "",
        on_lyrics_fx_change: Optional[Callable[[str], None]] = None,
        available_lyrics_fx: Optional[Dict[str, str]] = None,
        current_lyrics_fx: str = "",
        on_pet_character_change: Optional[Callable[[str], None]] = None,
        available_pet_characters: Optional[Dict[str, str]] = None,
        current_pet_character: str = "",
        on_pet_always_on_top: Optional[Callable[[bool], None]] = None,
        pet_always_on_top: bool = False,
    ):
        self._live_widgets = live_widgets  # 引用 main 的 _live_widgets 防 GC
        self._on_reset_layout = on_reset_layout or (lambda: None)
        self._on_show_all = on_show_all or (lambda: self._show_all_widgets())
        self._on_hide_all = on_hide_all or (lambda: self._hide_all_widgets())
        self._on_visualizer_change = on_visualizer_change or (lambda name: None)
        self._available_visualizers = available_visualizers or {}
        self._current_visualizer = current_visualizer
        self._viz_actions: Dict[str, QAction] = {}  # internal_name -> QAction
        # 歌词动效
        self._on_lyrics_fx_change = on_lyrics_fx_change or (lambda name: None)
        self._available_lyrics_fx = available_lyrics_fx or {}
        self._current_lyrics_fx = current_lyrics_fx
        self._lyrics_actions: Dict[str, QAction] = {}
        # 桌宠角色
        self._on_pet_character_change = on_pet_character_change or (lambda name: None)
        self._available_pet_characters = available_pet_characters or {}
        self._current_pet_character = current_pet_character
        self._pet_actions: Dict[str, QAction] = {}
        self._pet_always_on_top = pet_always_on_top
        self._on_pet_always_on_top = on_pet_always_on_top or (lambda on: None)
        self._visible_state: Dict[str, bool] = {}  # card_id → bool

        # 系统托盘
        if not QSystemTrayIcon.isSystemTrayAvailable():
            _LOG.warning("系统托盘不可用,跳过")
            self._tray = None
            return

        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_make_moon_icon(64))
        self._tray.setToolTip("MoonDeck 月坞 - 桌面浮窗卡片")
        self._tray.activated.connect(self._on_activated)
        self._tray.setContextMenu(self._build_menu())
        # 重要:必须 show() 才能用
        self._tray.show()
        self._tray.showMessage(
            "MoonDeck 已启动",
            "🌙 月坞在跑!右键托盘图标 → 设置 / 退出",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        _LOG.info("✅ 系统托盘已显示")

    # ============== 菜单 ==============

    def _build_menu(self) -> QMenu:
        """构建右键菜单(每次动态生成,卡列表会变)"""
        menu = QMenu()

        # === 显示/隐藏全部 ===
        act_show_all = QAction("👁️ 显示全部", menu)
        act_show_all.triggered.connect(self._on_show_all)
        menu.addAction(act_show_all)

        act_hide_all = QAction("🙈 隐藏全部", menu)
        act_hide_all.triggered.connect(self._on_hide_all)
        menu.addAction(act_hide_all)

        menu.addSeparator()

        # === 单独显示/隐藏每张卡 ===
        sub = menu.addMenu("🎴 单卡显隐")
        if self._live_widgets:
            for card_id, (widget, _ctrl) in self._live_widgets.items():
                # 卡片名优先用 widget.card_name,否则用 card_id
                name = getattr(widget, "card_name", None) or card_id
                act = QAction(name, sub)
                act.setCheckable(True)
                act.setChecked(widget.isVisible())
                # 用 default arg 绑定避免闭包坑
                act.toggled.connect(
                    lambda checked, w=widget, cid=card_id: self._toggle_one(w, cid, checked)
                )
                sub.addAction(act)
        else:
            empty = QAction("(暂无卡片)", sub)
            empty.setEnabled(False)
            sub.addAction(empty)

        menu.addSeparator()

        # === 桌面动效 (互斥单选) ===
        if self._available_visualizers:
            viz_sub = menu.addMenu("🎨 桌面动效")
            viz_group = QActionGroup(viz_sub)
            viz_group.setExclusive(True)
            for internal_name, display_name in self._available_visualizers.items():
                act = QAction(display_name, viz_sub)
                act.setCheckable(True)
                act.setChecked(internal_name == self._current_visualizer)
                act.triggered.connect(
                    lambda checked, n=internal_name: self._on_viz_selected(n, checked)
                )
                viz_group.addAction(act)
                viz_sub.addAction(act)
                self._viz_actions[internal_name] = act
            menu.addSeparator()

        # === 歌词动效 (互斥单选) ===
        if self._available_lyrics_fx:
            lyrics_sub = menu.addMenu("🎤 歌词动效")
            lyrics_group = QActionGroup(lyrics_sub)
            lyrics_group.setExclusive(True)
            for internal_name, display_name in self._available_lyrics_fx.items():
                act = QAction(display_name, lyrics_sub)
                act.setCheckable(True)
                act.setChecked(internal_name == self._current_lyrics_fx)
                act.triggered.connect(
                    lambda checked, n=internal_name: self._on_lyrics_selected(n, checked)
                )
                lyrics_group.addAction(act)
                lyrics_sub.addAction(act)
                self._lyrics_actions[internal_name] = act
            menu.addSeparator()

        # === 桌宠角色 (互斥单选) ===
        if self._available_pet_characters:
            pet_sub = menu.addMenu("🎀 桌宠角色")
            pet_group = QActionGroup(pet_sub)
            pet_group.setExclusive(True)
            for internal_name, display_name in self._available_pet_characters.items():
                act = QAction(display_name, pet_sub)
                act.setCheckable(True)
                act.setChecked(internal_name == self._current_pet_character)
                act.triggered.connect(
                    lambda checked, n=internal_name: self._on_pet_selected(n, checked)
                )
                pet_group.addAction(act)
                pet_sub.addAction(act)
                self._pet_actions[internal_name] = act
            menu.addSeparator()

        # === 桌宠置顶 (复选) ===
        if self._on_pet_always_on_top is not None:
            act_pet_top = QAction("📌 桌宠始终置顶", menu)
            act_pet_top.setCheckable(True)
            act_pet_top.setChecked(self._pet_always_on_top)
            act_pet_top.toggled.connect(
                lambda checked, n="pet_top": self._on_pet_always_on_top(checked)
            )
            menu.addAction(act_pet_top)
            menu.addSeparator()

        # === 设置 / 重置 ===
        act_reset = QAction("🔄 重置布局", menu)
        act_reset.triggered.connect(self._on_reset_layout)
        menu.addAction(act_reset)

        menu.addSeparator()

        # === 退出 ===
        act_quit = QAction("❌ 退出 MoonDeck", menu)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)

        return menu

    def _refresh_menu(self):
        """重新生成菜单(卡列表变化后)"""
        if self._tray is None:
            return
        self._tray.setContextMenu(self._build_menu())

    # ============== 动效切换 ==============

    def _on_viz_selected(self, internal_name: str, checked: bool):
        """用户选了某个动效"""
        if checked and internal_name != self._current_visualizer:
            self._current_visualizer = internal_name
            self._on_visualizer_change(internal_name)

    def set_current_visualizer(self, internal_name: str):
        """外部同步当前动效 (例如 hotkey 切换)"""
        if internal_name not in self._viz_actions:
            return
        self._current_visualizer = internal_name
        for name, act in self._viz_actions.items():
            act.setChecked(name == internal_name)

    # ============== 歌词动效切换 ==============

    def _on_lyrics_selected(self, internal_name: str, checked: bool):
        """用户选了某个歌词动效"""
        if checked and internal_name != self._current_lyrics_fx:
            self._current_lyrics_fx = internal_name
            self._on_lyrics_fx_change(internal_name)

    def set_current_lyrics_fx(self, internal_name: str):
        """外部同步当前歌词动效"""
        if internal_name not in self._lyrics_actions:
            return
        self._current_lyrics_fx = internal_name
        for name, act in self._lyrics_actions.items():
            act.setChecked(name == internal_name)

    # ============== 桌宠角色切换 ==============

    def _on_pet_selected(self, internal_name: str, checked: bool):
        """用户选了某个桌宠角色"""
        if checked and internal_name != self._current_pet_character:
            self._current_pet_character = internal_name
            self._on_pet_character_change(internal_name)

    def set_current_pet_character(self, internal_name: str):
        """外部同步当前桌宠角色"""
        if internal_name not in self._pet_actions:
            return
        self._current_pet_character = internal_name
        for name, act in self._pet_actions.items():
            act.setChecked(name == internal_name)

    # ============== 显隐控制 ==============

    def _toggle_one(self, widget: QWidget, card_id: str, checked: bool):
        if checked:
            widget.show()
            widget.raise_()
        else:
            widget.hide()
        self._visible_state[card_id] = checked

    def _show_all_widgets(self):
        for card_id, (widget, _ctrl) in self._live_widgets.items():
            widget.show()
            widget.raise_()
            self._visible_state[card_id] = True
        self._refresh_menu()

    def _hide_all_widgets(self):
        for card_id, (widget, _ctrl) in self._live_widgets.items():
            widget.hide()
            self._visible_state[card_id] = False
        self._refresh_menu()

    # ============== 托盘图标双击 ==============

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        # 双击 = 切显隐
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            any_visible = any(
                w.isVisible() for w, _ in self._live_widgets.values()
            )
            if any_visible:
                self._on_hide_all()
            else:
                self._on_show_all()
            self._refresh_menu()

    # ============== 退出 ==============

    def _quit(self):
        """优雅退出:走 app.quit() 让 aboutToQuit hook 跑"""
        if self._tray is not None:
            self._tray.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    # ============== 通知 API(后续其他模块用) ==============

    def notify(self, title: str, body: str, duration_ms: int = 3000):
        """发系统通知(Windows Action Center)"""
        if self._tray is None:
            return
        self._tray.showMessage(
            title, body,
            QSystemTrayIcon.MessageIcon.Information,
            duration_ms,
        )
