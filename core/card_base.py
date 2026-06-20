"""MoonDeck 卡片抽象基类

所有卡片必须继承 CardBase 并实现以下方法:
- init_ui()        构建 widget 树
- update_data()    拉取/处理数据
- card_id (类属性) 唯一标识

可选重写:
- apply_theme()    主题变化时重新绘制
- on_drag_start()  拖拽开始
- on_drag_end()    拖拽结束
- on_dock()        被吸附到其他卡片

老大原则:卡片可独立跑、可独立测、不依赖画布也能实例化。
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget


class CardBase(QWidget):
    """卡片抽象基类(QWidget 子类)

    为什么不继承 ABC:PyQt6 的 QWidget 有自己的 metaclass(Shiboken),
    与 ABC 冲突导致 metaclass 错误。改用 raise NotImplementedError
    的方式强制子类实现。
    """

    # === 子类必须设置的元信息 ===
    card_id: str = ""              # 唯一 ID,如 "token_card"
    card_name: str = ""            # 显示名,如 "Token 监控"
    card_icon: str = ""            # emoji 或图标路径
    default_size: Tuple[int, int] = (300, 200)
    update_interval_ms: int = 5000  # 默认 5s 刷新一次

    def __init__(self, config: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._config: Dict[str, Any] = config or {}
        self._last_update_ts: float = 0.0
        # 窗口标志:无边框 + 工具窗口(不在任务栏)
        # 注意:WS_EX_LAYERED + WS_EX_TRANSPARENT 由 Canvas 在 addCard 时设
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        # 透明背景支持
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        # 默认尺寸
        self.resize(*self.default_size)
        # 调用子类实现
        self.init_ui()
        # 首次拉数据
        self.update_data()

    # === 子类必须实现 ===

    def init_ui(self) -> None:
        """初始化 widget 树(创建子控件、布局)"""
        raise NotImplementedError(f"{type(self).__name__} 必须实现 init_ui()")

    def update_data(self) -> None:
        """更新数据(可同步/异步)

        完成后应调用 self._mark_updated() 或自行触发重绘。
        """
        raise NotImplementedError(f"{type(self).__name__} 必须实现 update_data()")

    # === 公开辅助方法 ===

    def config(self, key: str, default: Any = None) -> Any:
        """取卡片专属配置"""
        keys = key.split(".")
        cur: Any = self._config
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return default
        return cur

    def theme_value(self, key: str, default: Any = None) -> Any:
        """从当前主题取色值(避免硬编码颜色)"""
        from .theme import ThemeManager
        return ThemeManager.instance().get(key, default)

    def font_value(self, key: str, default: Any = None) -> Any:
        """从字体配置取字体属性"""
        from .theme import ThemeManager
        return ThemeManager.instance().font(key, default)

    # === 生命周期回调(可选重写) ===

    def apply_theme(self) -> None:
        """主题变化时调用(默认触发重绘)"""
        self.update()

    def on_drag_start(self) -> None:
        """开始拖拽"""

    def on_drag_end(self, final_pos: QPoint) -> None:
        """拖拽结束

        默认:不做事。子类可保存到 StorageManager。
        """

    def on_dock(self, target_card_id: str) -> None:
        """被吸附到其他卡片"""

    def on_resize(self) -> None:
        """窗口大小变化"""

    # === 序列化(给 StorageManager 用) ===

    def serialize(self) -> Dict[str, Any]:
        """序列化为 dict(存 SQLite)"""
        return {
            "card_id": self.card_id,
            "x": self.x(),
            "y": self.y(),
            "w": self.width(),
            "h": self.height(),
            "visible": self.isVisible(),
        }

    def deserialize(self, data: Dict[str, Any]) -> None:
        """从 dict 恢复(从 SQLite 读)"""
        try:
            x = int(data.get("x", self.x()))
            y = int(data.get("y", self.y()))
            w = int(data.get("w", self.width()))
            h = int(data.get("h", self.height()))
            self.setGeometry(x, y, w, h)
            if not data.get("visible", True):
                self.hide()
            else:
                self.show()
        except (TypeError, ValueError):
            # 静默失败,使用当前几何
            pass

    def resizeEvent(self, event) -> None:
        """重写以通知子类"""
        super().resizeEvent(event)
        self.on_resize()

    def paintEvent(self, event) -> None:
        """默认空绘制(子类应重写)"""
        # 提供一个最简单的 paint 兜底,避免 PyQt 警告
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())
        painter.end()
        super().paintEvent(event)
