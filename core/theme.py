"""MoonDeck 主题管理器

职责:
- 加载/切换/保存主题
- 主题变更时通知所有订阅者(用 EventBus 派发)
- 提供 QSS 字符串给 widget 使用

主题可以是:
- 内置 4 种(dark/light/glass/neon)
- 用户自定义(在 config/theme.yaml 添加)

老大原则:主题独立可测,任何 widget 都不应硬编码颜色,统一从 theme 取。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml


class ThemeManager:
    """主题管理器(单例)"""

    _instance: "ThemeManager | None" = None
    _lock = threading.Lock()

    # 内置主题(永远存在,即便 yaml 加载失败)
    BUILTIN_THEMES: Dict[str, Dict[str, Any]] = {
        "dark": {
            "background": "#1a1a2e",
            "background_gradient_end": "#2d1b4e",
            "border": "#b794f4",
            "accent": "#f6ad55",
            "text_primary": "#e0e0ff",
            "text_secondary": "#a0aec0",
            "success": "#48bb78",
            "warning": "#ed8936",
            "danger": "#f56565",
            "corner_radius": 16,
            "border_width": 2,
        },
        "light": {
            "background": "#ffffff",
            "background_gradient_end": "#f7fafc",
            "border": "#3182ce",
            "accent": "#dd6b20",
            "text_primary": "#1a202c",
            "text_secondary": "#4a5568",
            "success": "#38a169",
            "warning": "#dd6b20",
            "danger": "#e53e3e",
            "corner_radius": 12,
            "border_width": 1,
        },
        "glass": {
            "background": "rgba(255, 255, 255, 0.1)",
            "background_gradient_end": "rgba(255, 255, 255, 0.05)",
            "border": "rgba(255, 255, 255, 0.3)",
            "accent": "#f6ad55",
            "text_primary": "#ffffff",
            "text_secondary": "rgba(255, 255, 255, 0.7)",
            "success": "#48bb78",
            "warning": "#ed8936",
            "danger": "#f56565",
            "corner_radius": 16,
            "border_width": 1,
        },
        "neon": {
            "background": "#0a0a1a",
            "background_gradient_end": "#1a0a2e",
            "border": "#00ff88",
            "accent": "#ff00ff",
            "text_primary": "#00ff88",
            "text_secondary": "rgba(0, 255, 136, 0.6)",
            "success": "#00ff88",
            "warning": "#ffaa00",
            "danger": "#ff0066",
            "corner_radius": 8,
            "border_width": 2,
        },
    }

    def __init__(self, theme_yaml_path: Optional[Path] = None, default_name: str = "dark"):
        # 从 yaml 加载(覆盖内置)
        self._themes: Dict[str, Dict[str, Any]] = dict(self.BUILTIN_THEMES)
        if theme_yaml_path and theme_yaml_path.exists():
            try:
                with open(theme_yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                user_themes = data.get("themes", {})
                if isinstance(user_themes, dict):
                    for name, theme_dict in user_themes.items():
                        if isinstance(theme_dict, dict):
                            # 合并:用户值覆盖内置
                            merged = dict(self._themes.get(name, {}))
                            merged.update(theme_dict)
                            self._themes[name] = merged
            except Exception as e:
                print(f"[ThemeManager] 加载 {theme_yaml_path} 失败,使用内置: {e}")

        # 字体配置(可选)
        self._fonts: Dict[str, Any] = {}
        if theme_yaml_path and theme_yaml_path.exists():
            try:
                with open(theme_yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._fonts = data.get("fonts", {})
            except Exception:
                pass

        # 当前主题
        self._current_name: str = default_name if default_name in self._themes else "dark"
        # 观察者
        self._observers: List[Callable[[str, Dict[str, Any]], None]] = []

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    # ---- 主题访问 ----

    def current_name(self) -> str:
        return self._current_name

    def current(self) -> Dict[str, Any]:
        """获取当前主题的色值字典"""
        return dict(self._themes[self._current_name])

    def get(self, key: str, default: Any = None) -> Any:
        """取当前主题的某个色值"""
        return self._themes[self._current_name].get(key, default)

    def themes(self) -> List[str]:
        """所有可用主题名"""
        return list(self._themes.keys())

    def font(self, key: str, default: Any = None) -> Any:
        """取字体配置"""
        return self._fonts.get(key, default)

    # ---- 主题切换 ----

    def set_theme(self, name: str) -> bool:
        """切换主题

        Returns:
            True=切换成功,False=主题名不存在
        """
        if name not in self._themes:
            return False
        if name == self._current_name:
            return True  # no-op
        self._current_name = name
        self._notify()
        return True

    def cycle_theme(self) -> str:
        """循环切换到下一个主题,返回新主题名"""
        names = self.themes()
        if not names:
            return self._current_name
        idx = names.index(self._current_name) if self._current_name in names else -1
        next_name = names[(idx + 1) % len(names)]
        self.set_theme(next_name)
        return next_name

    # ---- 观察者 ----

    def subscribe(self, callback: Callable[[str, Dict[str, Any]], None]) -> Callable[[], None]:
        """订阅主题变化

        callback 签名: callback(theme_name: str, theme_dict: dict)
        """
        self._observers.append(callback)

        def _unsub():
            try:
                self._observers.remove(callback)
            except ValueError:
                pass
        return _unsub

    def _notify(self) -> None:
        for obs in self._observers:
            try:
                obs(self._current_name, self.current())
            except Exception as e:
                print(f"[ThemeManager] 观察者 {obs.__name__} 失败: {e}")

    # ---- QSS 生成 ----

    def qss(self) -> str:
        """生成全局 QSS 样式(可选,大部分 widget 自己 paint)"""
        t = self.current()
        return (
            f"QWidget {{ background: {t['background']}; color: {t['text_primary']}; }}"
            f"QPushButton {{ color: {t['accent']}; }}"
        )
