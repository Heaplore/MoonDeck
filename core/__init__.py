"""MoonDeck 核心模块

提供画布运行所需的基础设施:
- event_bus: 全局事件总线
- theme: 主题管理器
- card_base: 卡片抽象基类
- canvas: 透明全屏主窗口
- storage: SQLite 布局/数据持久化

老大原则:核心模块不依赖具体卡片,卡片可独立引用核心。
"""
from .event_bus import EventBus
from .theme import ThemeManager
from .card_base import CardBase
from .storage import StorageManager

__all__ = ["EventBus", "ThemeManager", "CardBase", "StorageManager"]
