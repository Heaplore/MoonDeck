"""HotkeyManager 单元测试

覆盖:
- 解析("<ctrl>+a" -> ["<ctrl>", "a"])
- 注册/注销
- 触发回调
- 启动/停止
- 事件触发
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

# offscreen
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# path hack
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TEST_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.event_bus import EventBus  # noqa: E402
from core.hotkey_manager import HotkeyManager, _parse_hotkey  # noqa: E402


class TestParseHotkey(unittest.TestCase):
    def test_single_modifier(self):
        self.assertEqual(_parse_hotkey("<alt>"), ["<alt>"])

    def test_single_key(self):
        self.assertEqual(_parse_hotkey("f1"), ["f1"])

    def test_combo(self):
        self.assertEqual(_parse_hotkey("<ctrl>+a"), ["<ctrl>", "a"])

    def test_with_spaces(self):
        self.assertEqual(_parse_hotkey(" <ctrl> + a "), ["<ctrl>", "a"])

    def test_case_insensitive(self):
        self.assertEqual(_parse_hotkey("<CTRL>+A"), ["<ctrl>", "a"])


class TestHotkeyManager(unittest.TestCase):
    def setUp(self):
        # 重置 EventBus 单例
        EventBus._instance = None
        self.bus = EventBus.instance()
        self.hkm = HotkeyManager(bus=self.bus)
        self.hkm.set_verbose(False)

    def tearDown(self):
        self.hkm.stop()
        EventBus._instance = None

    def test_register_and_list(self):
        self.hkm.register("<alt>", lambda: None)
        self.hkm.register("<ctrl>+s", lambda: None)
        keys = self.hkm.registered_hotkeys()
        self.assertIn("<alt>", keys)
        self.assertIn("<ctrl>+s", keys)
        self.assertEqual(len(keys), 2)

    def test_unregister(self):
        self.hkm.register("<alt>", lambda: None)
        self.hkm.unregister("<alt>")
        self.assertNotIn("<alt>", self.hkm.registered_hotkeys())

    def test_clear(self):
        self.hkm.register("<alt>", lambda: None)
        self.hkm.register("<esc>", lambda: None)
        self.hkm.clear()
        self.assertEqual(self.hkm.registered_hotkeys(), [])

    def test_key_to_name(self):
        from pynput.keyboard import Key, KeyCode
        # 修饰键
        self.assertEqual(HotkeyManager._key_to_name(Key.alt), "alt")
        # ctrl_l 在 pynput 里的 name 是 "ctrl_l" 不是 "ctrl"
        self.assertEqual(HotkeyManager._key_to_name(Key.ctrl_l), "ctrl_l")
        # 普通 key
        self.assertEqual(HotkeyManager._key_to_name(KeyCode.from_char("a")), "a")
        self.assertEqual(HotkeyManager._key_to_name(KeyCode.from_char("A")), "a")
        # 函数键
        self.assertEqual(HotkeyManager._key_to_name(Key.f1), "f1")
        self.assertEqual(HotkeyManager._key_to_name(Key.esc), "esc")

    def test_modifier_held_tracking(self):
        from pynput.keyboard import Key
        # alt 按下
        self.hkm._on_press(Key.alt)
        self.assertIn("<alt>", self.hkm._held_modifiers)
        # alt 松开
        self.hkm._on_release(Key.alt)
        self.assertNotIn("<alt>", self.hkm._held_modifiers)

    def test_callback_fires_on_match(self):
        from pynput.keyboard import Key
        cb = MagicMock()
        self.hkm.register("<alt>", cb)
        # 模拟 alt 按下
        self.hkm._on_press(Key.alt)
        cb.assert_called_once()

    def test_callback_fires_for_combo(self):
        from pynput.keyboard import Key, KeyCode
        cb = MagicMock()
        self.hkm.register("<ctrl>+s", cb)
        # 先按 ctrl
        self.hkm._on_press(Key.ctrl)
        # 再按 s
        self.hkm._on_press(KeyCode.from_char("s"))
        cb.assert_called_once()

    def test_callback_not_fires_for_partial(self):
        from pynput.keyboard import Key
        cb = MagicMock()
        self.hkm.register("<ctrl>+s", cb)
        # 只按 ctrl(不按 s)→ 不应触发
        self.hkm._on_press(Key.ctrl)
        cb.assert_not_called()

    def test_eventbus_emit_on_fire(self):
        from pynput.keyboard import Key
        received = []
        self.bus.subscribe("hotkey:pressed", lambda p: received.append(p))
        self.hkm.register("<alt>", lambda: None)
        self.hkm._on_press(Key.alt)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["hotkey"], "<alt>")

    def test_callback_exception_isolated(self):
        """回调抛错不能影响其他注册"""
        from pynput.keyboard import Key
        # 先注册一个会抛错的 cb 在 alt
        cb1 = MagicMock(side_effect=RuntimeError("boom"))
        self.hkm.register("<alt>", cb1)
        # 再注册 ctrl+s 不应被影响
        cb2 = MagicMock()
        self.hkm.register("<ctrl>+s", cb2)
        # 按 alt → cb1 抛错
        self.hkm._on_press(Key.alt)
        # 按 ctrl 再按 s → cb2 仍应触发
        from pynput.keyboard import KeyCode
        self.hkm._on_press(Key.ctrl)
        self.hkm._on_press(KeyCode.from_char("s"))
        cb2.assert_called_once()

    def test_start_stop(self):
        # 不真正起监听(避免后台线程)
        # 只验证 start 标志位
        result = self.hkm.start()
        # 第一次启动应成功
        # 注意:start 会启动后台 listener,可能受环境限制
        # 如果失败也不应抛
        if result:
            self.assertTrue(self.hkm.is_running())
            self.hkm.stop()
        self.assertFalse(self.hkm.is_running())


if __name__ == "__main__":
    unittest.main()
