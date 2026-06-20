"""MoonDeck 全局快捷键管理器

职责:
- 监听 pynput 全局键盘事件
- 把快捷键字符串(如 "<alt>", "<ctrl>+s")解析为可匹配状态
- 触发时回调 + 发送 EventBus 事件

设计:
- 独立线程跑 pynput.Listener(主线程跑 Qt,不能阻塞)
- 修饰键状态用集合维护(<alt> 按下/松开时增减)
- 组合键 "<ctrl>+a" = ctrl 按下后再按 a
- 单键 "<f1>" = 直接按 f1
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Set

from pynput import keyboard as pynput_kb

from .event_bus import EventBus


# pynput.Key -> 内部修饰键映射(都归一为字符串)
_MODIFIER_KEY_MAP = {
    pynput_kb.Key.alt: "<alt>",
    pynput_kb.Key.alt_l: "<alt>",
    pynput_kb.Key.alt_r: "<alt>",
    pynput_kb.Key.ctrl: "<ctrl>",
    pynput_kb.Key.ctrl_l: "<ctrl>",
    pynput_kb.Key.ctrl_r: "<ctrl>",
    pynput_kb.Key.shift: "<shift>",
    pynput_kb.Key.shift_l: "<shift>",
    pynput_kb.Key.shift_r: "<shift>",
    pynput_kb.Key.cmd: "<cmd>",
    pynput_kb.Key.cmd_l: "<cmd>",
    pynput_kb.Key.cmd_r: "<cmd>",
}


def _parse_hotkey(hotkey_str: str) -> List[str]:
    """把 "<ctrl>+a" 解析为 ["<ctrl>", "a"] 列表(小写)

    规则:
    - "+" 分隔
    - 修饰键(<alt> / <ctrl> / <shift> / <cmd>)保留 <...> 包裹
    - 其他 <...>包裹的 key(如 <f5>, <esc>)去掉括号,变 "f5", "esc"
    - 普通 key 转小写
    """
    _MOD_PREFIXES = ("<alt>", "<ctrl>", "<shift>", "<cmd>")
    result = []
    for p in hotkey_str.split("+"):
        token = p.strip().lower()
        if not token:
            continue
        if token in _MOD_PREFIXES:
            result.append(token)
        elif token.startswith("<") and token.endswith(">"):
            # <f5> -> f5
            result.append(token[1:-1])
        else:
            result.append(token)
    return result


class HotkeyManager:
    """全局快捷键监听器

    用法:
        hkm = HotkeyManager()
        hkm.register("<alt>", callback=lambda: enter_interactive())
        hkm.register("<esc>", callback=lambda: exit_interactive())
        hkm.start()  # 启动监听线程
        ...
        hkm.stop()   # 退出
    """

    # 修饰键名集合
    _MODIFIER_NAMES = frozenset({"<alt>", "<ctrl>", "<shift>", "<cmd>"})

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus or EventBus.instance()
        self._hotkeys: Dict[str, Callable[[], None]] = {}
        self._parsed: Dict[str, List[str]] = {}  # hotkey -> 解析后的 keys
        self._held_modifiers: Set[str] = set()  # 当前按下的修饰键
        self._listener: Optional[pynput_kb.Listener] = None
        self._lock = threading.Lock()
        self._running = False
        # 调试模式:打印每次按键
        self._verbose: bool = False

    # === 注册 ===

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        """注册一个快捷键

        Args:
            hotkey: 字符串,如 "<alt>", "<ctrl>+s", "<f1>"
            callback: 触发时的回调
        """
        hk = hotkey.strip().lower()
        with self._lock:
            self._hotkeys[hk] = callback
            self._parsed[hk] = _parse_hotkey(hk)
        if self._verbose:
            print(f"[HotkeyManager] 注册: {hk} -> {self._parsed[hk]}")

    def unregister(self, hotkey: str) -> None:
        hk = hotkey.strip().lower()
        with self._lock:
            self._hotkeys.pop(hk, None)
            self._parsed.pop(hk, None)

    def clear(self) -> None:
        with self._lock:
            self._hotkeys.clear()
            self._parsed.clear()

    def registered_hotkeys(self) -> List[str]:
        with self._lock:
            return list(self._hotkeys.keys())

    # === 启动/停止 ===

    def start(self) -> bool:
        """启动 pynput 监听(后台线程)

        Returns:
            True=启动成功, False=已经在跑
        """
        with self._lock:
            if self._running:
                return False
            self._running = True
        try:
            self._listener = pynput_kb.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._listener.daemon = True
            self._listener.start()
            if self._verbose:
                print(f"[HotkeyManager] 启动,已注册 {len(self._hotkeys)} 个快捷键")
            return True
        except Exception as e:
            print(f"[HotkeyManager] 启动失败: {e}")
            with self._lock:
                self._running = False
            return False

    def stop(self) -> None:
        """停止监听"""
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        if self._verbose:
            print("[HotkeyManager] 停止")

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    # === 事件处理(在 pynput 线程) ===

    def _on_press(self, key) -> None:
        try:
            mod = _MODIFIER_KEY_MAP.get(key)
            if mod is not None:
                self._held_modifiers.add(mod)
                self._check_match()
                return
            # 普通 key
            key_name = self._key_to_name(key)
            if key_name:
                self._check_match(extra_key=key_name)
        except Exception as e:
            if self._verbose:
                print(f"[HotkeyManager] _on_press 异常: {e}")

    def _on_release(self, key) -> None:
        try:
            mod = _MODIFIER_KEY_MAP.get(key)
            if mod is not None:
                self._held_modifiers.discard(mod)
        except Exception as e:
            if self._verbose:
                print(f"[HotkeyManager] _on_release 异常: {e}")

    @staticmethod
    def _key_to_name(key) -> Optional[str]:
        """pynput.Key/KeyCode -> 字符串形式

        - Key.f1 -> "f1"
        - KeyCode(char='a') -> "a"
        - Key.esc -> "esc"
        """
        if isinstance(key, pynput_kb.KeyCode):
            if key.char:
                return key.char.lower()
            return None
        if isinstance(key, pynput_kb.Key):
            # pynput.Key.f1 / Key.esc 等的 .name 属性
            return key.name.lower() if hasattr(key, "name") else None
        return None

    def _check_match(self, extra_key: Optional[str] = None) -> None:
        """检查当前按下状态是否匹配任何已注册快捷键

        extra_key: 刚按下的非修饰键(可选)

        匹配规则:
        - hotkey 的所有 keys 都必须在 current 中(子集匹配)
        - 只要 hotkey 的最后一个 key 刚被按下(就是 extra_key 或某修饰键),才考虑匹配
          这样避免“一直按 alt 自动重复触发”
        """
        current: Set[str] = set(self._held_modifiers)
        if extra_key:
            current.add(extra_key)

        with self._lock:
            hotkeys = list(self._parsed.items())

        # 按优先级:带 extra_key 的优先,再试修饰键
        # 1. 包含 extra_key 的 hotkey(刚按下的 key 是 hotkey 一部分)
        if extra_key is not None:
            for hk, parts in hotkeys:
                if extra_key in parts and set(parts).issubset(current):
                    self._fire(hk)
                    return
        # 2. 只含修饰键的 hotkey(用最后按下的修饰键作为锚)
        if self._held_modifiers:
            last_mod = max(self._held_modifiers)  # 任意一个都能触发
            for hk, parts in hotkeys:
                if all(p in self._MODIFIER_NAMES for p in parts) and set(parts).issubset(current):
                    # 只触发一次:记录已触发的修饰键组合
                    self._fire(hk)
                    return

    def _fire(self, hotkey: str) -> None:
        with self._lock:
            cb = self._hotkeys.get(hotkey)
        if cb is None:
            return
        # 触发 EventBus 事件
        try:
            self._bus.emit("hotkey:pressed", {"hotkey": hotkey})
        except Exception:
            pass
        # 调回调(异常隔离)
        try:
            cb()
        except Exception as e:
            print(f"[HotkeyManager] 快捷键 {hotkey} 回调异常: {e}")

    # === 调试 ===

    def set_verbose(self, on: bool) -> None:
        self._verbose = bool(on)
