"""MoonDeck 布局管理器

职责:
- 维护多套布局(工作/摸鱼/极简/自定义)
- 一键切换:加载对应布局的位置数据 + 应用到所有卡片
- 保存当前布局为新预设

设计:
- 布局存到 storage 的 kv 表(layouts/<name> = JSON 字典 {card_id: {x,y,w,h,visible}})
- 内置 3 套 default 布局,首次启动用
- 切换布局时:遍历画布上的卡片 → 找到对应预设 → widget.setGeometry
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .event_bus import EventBus
from .storage import StorageManager


_KV_KEY_PREFIX = "layout_preset:"


def _preset_key(name: str) -> str:
    return f"{_KV_KEY_PREFIX}{name}"


class LayoutManager:
    """布局管理器(多预设切换)

    用法:
        lm = LayoutManager(canvas, storage, bus=bus)
        lm.list_presets()          # ["default", "work", "fun", ...]
        lm.save_current_as("work") # 把当前所有卡片位置存为 "work" 预设
        lm.apply("work")           # 应用 "work" 预设
        lm.apply("default")        # 应用默认布局
    """

    BUILTIN_PRESETS = ("default", "work", "fun", "minimal")

    def __init__(
        self,
        canvas: Any,
        storage: StorageManager,
        bus: Optional[EventBus] = None,
        default_positions: Optional[Dict[str, Dict[str, int]]] = None,
    ):
        self._canvas = canvas
        self._storage = storage
        self._bus = bus or EventBus.instance()
        self._default_positions = default_positions or {}
        self._active_preset: str = "default"

    # === 预设列表 ===

    def list_presets(self) -> List[str]:
        """列出所有预设(内置 + 用户)"""
        all_keys = self._storage.get_kv("layout_presets", [])
        combined = list(self.BUILTIN_PRESETS) + [
            k for k in all_keys if k not in self.BUILTIN_PRESETS
        ]
        return combined

    def has_preset(self, name: str) -> bool:
        return name in self.list_presets()

    def active_preset(self) -> str:
        return self._active_preset

    # === 保存/读取预设 ===

    def save_current_as(self, name: str) -> bool:
        """把当前画布上所有卡片位置保存为预设"""
        name = name.strip()
        if not name:
            return False
        cards = self._canvas.all_cards() if hasattr(self._canvas, "all_cards") else []
        snapshot: Dict[str, Dict[str, Any]] = {}
        for card in cards:
            card_id = getattr(card, "card_id", None)
            if not card_id:
                continue
            snapshot[card_id] = {
                "x": int(card.x()),
                "y": int(card.y()),
                "w": int(card.width()),
                "h": int(card.height()),
                "visible": bool(card.isVisible()),
            }
        # 存到 kv
        self._storage.set_kv(
            _preset_key(name),
            {"name": name, "created_at": datetime.now().isoformat(), "cards": snapshot},
        )
        # 更新预设列表
        presets = self._storage.get_kv("layout_presets", [])
        if name not in presets and name not in self.BUILTIN_PRESETS:
            presets.append(name)
            self._storage.set_kv("layout_presets", presets)
        try:
            self._bus.emit("layout:preset_saved", {"name": name, "count": len(snapshot)})
        except Exception:
            pass
        return True

    def load_preset(self, name: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """读取预设;不存在返回 None"""
        if name == "default":
            return self._build_default_preset()
        raw = self._storage.get_kv(_preset_key(name), None)
        if raw is None:
            return None
        if isinstance(raw, dict) and "cards" in raw:
            return raw["cards"]
        return None

    def delete_preset(self, name: str) -> bool:
        if name in self.BUILTIN_PRESETS:
            return False  # 内置预设不能删
        # 从 kv 删 + 从列表删
        conn = self._storage._connect()  # noqa: SLF001
        with self._storage._write_lock:  # noqa: SLF001
            conn.execute("DELETE FROM kv WHERE key = ?", (_preset_key(name),))
            self._storage._conn.commit()  # noqa: SLF001
        presets = self._storage.get_kv("layout_presets", [])
        if name in presets:
            presets.remove(name)
            self._storage.set_kv("layout_presets", presets)
        return True

    def _build_default_preset(self) -> Dict[str, Dict[str, Any]]:
        """从 default.yaml 构造 default 预设"""
        result: Dict[str, Dict[str, Any]] = {}
        for card_id, pos in self._default_positions.items():
            try:
                result[card_id] = {
                    "x": int(pos.get("x", 100)),
                    "y": int(pos.get("y", 100)),
                    "w": int(pos.get("width", 200)),
                    "h": int(pos.get("height", 200)),
                    "visible": True,
                }
            except Exception:
                continue
        return result

    # === 应用预设 ===

    def apply(self, name: str) -> bool:
        """应用预设到画布

        Returns:
            True=应用成功,False=预设不存在
        """
        preset = self.load_preset(name)
        if preset is None:
            return False
        cards = self._canvas.all_cards() if hasattr(self._canvas, "all_cards") else []
        for card in cards:
            card_id = getattr(card, "card_id", None)
            if not card_id or card_id not in preset:
                continue
            pos = preset[card_id]
            try:
                card.setGeometry(
                    int(pos["x"]), int(pos["y"]),
                    int(pos["w"]), int(pos["h"]),
                )
                if "visible" in pos:
                    card.setVisible(bool(pos["visible"]))
            except Exception:
                continue
        self._active_preset = name
        # 保存到 storage 作为 active 标记
        self._storage.set_kv("active_layout", name)
        try:
            self._bus.emit("layout:applied", {"name": name, "card_count": len(preset)})
        except Exception:
            pass
        return True
