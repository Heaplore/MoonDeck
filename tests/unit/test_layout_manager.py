"""LayoutManager 单元测试

覆盖:
- 内置预设
- 保存/读取自定义预设
- 应用预设到画布
- 删除预设(内置不能删)
- list_presets
- active_preset
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TEST_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.event_bus import EventBus  # noqa: E402
from core.layout_manager import LayoutManager  # noqa: E402
from core.storage import StorageManager  # noqa: E402
from tests.unit._test_helpers import FakeCanvas, FakeCard, get_qapp  # noqa: E402


class TestLayoutManager(unittest.TestCase):
    def setUp(self):
        EventBus._instance = None
        self.bus = EventBus.instance()
        self.app = get_qapp()
        # 临时 SQLite
        tmpdir = tempfile.mkdtemp(prefix="moondeck_lm_")
        self.db_path = Path(tmpdir) / "test.db"
        StorageManager.reset_instance()
        self.storage = StorageManager.init_instance(self.db_path)
        self.canvas = FakeCanvas()
        self.canvas.show()
        # 2 张卡
        self.card1 = FakeCard("c1", "Card1")
        self.card1.setGeometry(100, 100, 200, 100)
        self.canvas.add_widget_card("c1", self.card1)
        self.card2 = FakeCard("c2", "Card2")
        self.card2.setGeometry(500, 500, 200, 100)
        self.canvas.add_widget_card("c2", self.card2)
        # 默认位置
        self.defaults = {
            "c1": {"x": 0, "y": 0, "width": 200, "height": 100},
            "c2": {"x": 800, "y": 600, "width": 100, "height": 100},
        }
        self.lm = LayoutManager(
            self.canvas, self.storage, bus=self.bus, default_positions=self.defaults
        )

    def tearDown(self):
        StorageManager.reset_instance()
        EventBus._instance = None
        import shutil
        try:
            shutil.rmtree(self.db_path.parent, ignore_errors=True)
        except Exception:
            pass

    def test_builtin_presets(self):
        presets = self.lm.list_presets()
        for p in ("default", "work", "fun", "minimal"):
            self.assertIn(p, presets)

    def test_load_default_preset(self):
        preset = self.lm.load_preset("default")
        self.assertIsNotNone(preset)
        self.assertIn("c1", preset)
        self.assertEqual(preset["c1"]["x"], 0)
        self.assertEqual(preset["c1"]["y"], 0)

    def test_load_nonexistent_preset(self):
        self.assertIsNone(self.lm.load_preset("nope"))

    def test_save_current_as(self):
        # 把 c1 拖到 (300, 400)
        self.card1.setGeometry(300, 400, 200, 100)
        ok = self.lm.save_current_as("custom1")
        self.assertTrue(ok)
        # 读出来
        preset = self.lm.load_preset("custom1")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["c1"]["x"], 300)
        self.assertEqual(preset["c1"]["y"], 400)
        # 列表中应包含
        self.assertIn("custom1", self.lm.list_presets())

    def test_apply_preset(self):
        # 保存一个
        self.card1.setGeometry(111, 222, 333, 444)
        self.lm.save_current_as("mypreset")
        # 移动 c1 到别处
        self.card1.setGeometry(0, 0, 1, 1)
        # 应用
        ok = self.lm.apply("mypreset")
        self.assertTrue(ok)
        # 位置应恢复
        self.assertEqual(self.card1.x(), 111)
        self.assertEqual(self.card1.y(), 222)
        # active_preset 更新
        self.assertEqual(self.lm.active_preset(), "mypreset")

    def test_apply_nonexistent(self):
        ok = self.lm.apply("not_exist")
        self.assertFalse(ok)

    def test_apply_default_uses_default_positions(self):
        # 把卡移到 (0,0)
        self.card1.setGeometry(0, 0, 1, 1)
        self.card2.setGeometry(0, 0, 1, 1)
        ok = self.lm.apply("default")
        self.assertTrue(ok)
        # c1 应回到 (0,0,200,100)
        self.assertEqual(self.card1.x(), 0)
        self.assertEqual(self.card1.y(), 0)
        # c2 应回到 (800,600,200,100)(画布右边界 1920,800+200=1000 没问题)
        self.assertEqual(self.card2.x(), 800)
        self.assertEqual(self.card2.y(), 600)

    def test_delete_preset(self):
        self.lm.save_current_as("todelete")
        self.assertTrue(self.lm.has_preset("todelete"))
        ok = self.lm.delete_preset("todelete")
        self.assertTrue(ok)
        self.assertFalse(self.lm.has_preset("todelete"))

    def test_cannot_delete_builtin(self):
        ok = self.lm.delete_preset("default")
        self.assertFalse(ok)
        ok2 = self.lm.delete_preset("work")
        self.assertFalse(ok2)

    def test_emit_event_on_apply(self):
        events = []
        self.bus.subscribe("layout:applied", lambda p: events.append(p))
        self.lm.apply("default")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "default")

    def test_emit_event_on_save(self):
        events = []
        self.bus.subscribe("layout:preset_saved", lambda p: events.append(p))
        self.lm.save_current_as("saved_one")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "saved_one")
        self.assertEqual(events[0]["count"], 2)  # c1 + c2


if __name__ == "__main__":
    unittest.main()
