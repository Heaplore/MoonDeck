"""交互层集成测试

模拟真实画布 + 卡片场景,验证 4 个管理器:
- HotkeyManager + DragManager + ClickManager + LayoutManager
- 协同工作(一个 emit,另一个响应)
- 事件流(card:moved → storage 持久化)
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TEST_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402

from core.click_manager import ClickManager  # noqa: E402
from core.drag_manager import DragManager  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from core.hotkey_manager import HotkeyManager  # noqa: E402
from core.layout_manager import LayoutManager  # noqa: E402
from core.storage import StorageManager  # noqa: E402
from tests.unit._test_helpers import FakeCanvas, FakeCard, get_qapp  # noqa: E402


def _to_f(p):
    return QPointF(float(p.x()), float(p.y()))


def make_press(canvas, global_pos, button=Qt.MouseButton.LeftButton):
    local = canvas.mapFromGlobal(global_pos)
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        _to_f(local),
        _to_f(global_pos),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def make_move(canvas, global_pos, buttons=Qt.MouseButton.LeftButton):
    local = canvas.mapFromGlobal(global_pos)
    return QMouseEvent(
        QEvent.Type.MouseMove,
        _to_f(local),
        _to_f(global_pos),
        Qt.MouseButton.NoButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def make_release(canvas, global_pos, button=Qt.MouseButton.LeftButton):
    local = canvas.mapFromGlobal(global_pos)
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        _to_f(local),
        _to_f(global_pos),
        button,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


class TestInteractionLayerIntegration(unittest.TestCase):
    """4 个管理器协同工作场景"""

    def setUp(self):
        EventBus._instance = None
        self.app = get_qapp()
        self.bus = EventBus.instance()
        # 临时 SQLite
        tmpdir = tempfile.mkdtemp(prefix="moondeck_int_")
        self.db_path = Path(tmpdir) / "test.db"
        StorageManager.reset_instance()
        self.storage = StorageManager.init_instance(self.db_path)
        # 画布
        self.canvas = FakeCanvas()
        self.canvas.show()
        # 卡片
        self.card1 = FakeCard("c1", "Card1")
        self.card1.setGeometry(100, 100, 200, 100)
        self.canvas.add_widget_card("c1", self.card1)
        self.card1.show()
        # 4 个管理器
        self.hkm = HotkeyManager(bus=self.bus)
        self.dm = DragManager(self.canvas, bus=self.bus)
        self.cm = ClickManager(self.canvas, bus=self.bus)
        self.lm = LayoutManager(
            self.canvas, self.storage, bus=self.bus,
            default_positions={"c1": {"x": 0, "y": 0, "width": 200, "height": 100}},
        )

    def tearDown(self):
        StorageManager.reset_instance()
        EventBus._instance = None
        import shutil
        try:
            shutil.rmtree(self.db_path.parent, ignore_errors=True)
        except Exception:
            pass

    def test_drag_emits_event_others_can_subscribe(self):
        """拖动 → card:moved → storage 持久化"""
        # 订阅 card:moved → 写 storage
        def on_moved(p):
            cid = p.get("card_id")
            if cid:
                self.storage.save_layout(
                    cid, int(p["x"]), int(p["y"]), int(p["w"]), int(p["h"]), True
                )
        self.bus.subscribe("card:moved", on_moved)

        # 模拟拖动 c1 从 (100,100) 到 (100+50, 100+30)
        self.dm._handle_press(make_press(self.canvas, QPoint(150, 150)))
        self.dm._handle_move(make_move(self.canvas, QPoint(200, 180)))
        self.dm._handle_release(make_release(self.canvas, QPoint(200, 180)))

        # 验证 storage 里 c1 位置已更新
        saved = self.storage.load_layout("c1")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["x"], 150)  # 100+50
        self.assertEqual(saved["y"], 130)  # 100+30

    def test_layout_apply_uses_storage(self):
        """应用布局预设 → 卡片位置更新"""
        # 准备预设
        self.card1.setGeometry(50, 50, 200, 100)
        self.lm.save_current_as("test_preset")
        # 移动卡
        self.card1.setGeometry(0, 0, 1, 1)
        # 应用
        self.lm.apply("test_preset")
        # 卡片回到预设
        self.assertEqual(self.card1.x(), 50)
        self.assertEqual(self.card1.y(), 50)

    def test_hotkey_can_trigger_callback(self):
        """Hotkey 触发 → 调用 callback"""
        from pynput.keyboard import Key
        called = []
        self.hkm.register("<ctrl>+t", lambda: called.append("fire"))
        # 按 ctrl 再按 t
        self.hkm._on_press(Key.ctrl)
        self.hkm._on_press(_key_char("t"))
        self.assertEqual(called, ["fire"])

    def test_right_click_emits_close_event(self):
        """右键 → 关闭动作 → card:close 事件"""
        close_events = []
        self.bus.subscribe("card:close", lambda p: close_events.append(p))
        # 模拟用户右键 c1
        evt = make_press(self.canvas, QPoint(150, 150), Qt.MouseButton.RightButton)
        # ClickManager 弹菜单(在测试里 menu.exec() 会真弹 → 我们直接走 _close_card)
        self.cm._close_card("c1")
        self.assertEqual(len(close_events), 1)
        self.assertEqual(close_events[0]["card_id"], "c1")

    def test_all_managers_share_same_eventbus(self):
        """4 个管理器用同一个 EventBus,emit 互通"""
        from pynput.keyboard import Key, KeyCode
        # 在 HotkeyManager 注册,期望它在 Bus 上发事件
        # 其它管理器通过 Bus 收
        received = []
        self.bus.subscribe("hotkey:pressed", lambda p: received.append(p["hotkey"]))
        self.hkm.register("<f5>", lambda: None)
        self.hkm._on_press(Key.f5)
        self.assertIn("<f5>", received)

    def test_drag_disabled_no_events(self):
        """禁用 DragManager → 拖动不触发事件"""
        self.dm.set_enabled(False)
        before = self.storage.load_layout("c1")
        # 走 eventFilter(disabled 拦截)
        self.dm.eventFilter(self.canvas, make_press(self.canvas, QPoint(150, 150)))
        # 没创建 state
        self.assertIsNone(self.dm._state)

    def test_presets_persist_across_storage_restart(self):
        """保存预设后,重新开 storage 能读出来"""
        self.card1.setGeometry(333, 444, 200, 100)
        self.lm.save_current_as("persist_test")
        # 模拟重启:重开 storage
        StorageManager.reset_instance()
        new_storage = StorageManager.init_instance(self.db_path)
        lm2 = LayoutManager(self.canvas, new_storage, default_positions={})
        # 旧预设还在
        self.assertTrue(lm2.has_preset("persist_test"))
        preset = lm2.load_preset("persist_test")
        self.assertEqual(preset["c1"]["x"], 333)
        self.assertEqual(preset["c1"]["y"], 444)


def _key_char(c):
    from pynput.keyboard import KeyCode
    return KeyCode.from_char(c)


if __name__ == "__main__":
    unittest.main()
