"""Canvas 单元测试

注意:需要在调用前设置 QT_QPA_PLATFORM=offscreen 避免弹窗
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 必须在 import Qt 前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core import EventBus, StorageManager
from core.canvas import Canvas
from _fake_card import FakeCard


class TestCanvas(unittest.TestCase):
    """Canvas 透明全屏 + 卡片管理 + 交互态"""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(sys.argv)
        # 临时 DB
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp.close()
        StorageManager.reset_instance()
        StorageManager.init_instance(Path(cls._tmp.name))
        EventBus.reset_instance()

    @classmethod
    def tearDownClass(cls):
        StorageManager.reset_instance()
        Path(cls._tmp.name).unlink(missing_ok=True)

    def setUp(self):
        EventBus.reset_instance()
        self.canvas = Canvas(config={
            "click_through": True,
            "span_all_screens": False,
            "auto_save_interval": 0,  # 测试中关掉
        })

    def tearDown(self):
        self.canvas.shutdown()
        self.canvas.deleteLater()

    def test_01_window_flags(self):
        """画布窗口标志:无边框 + 工具窗口 + 顶部(z-order 修复 2026-06-12)"""
        flags = self.canvas.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.Tool)
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)

    def test_02_translucent(self):
        """画布透明背景"""
        self.assertTrue(self.canvas.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(self.canvas.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))

    def test_03_add_card(self):
        """添加卡片"""
        card = FakeCard()
        self.canvas.add_card(card)
        self.assertIn("fake_card", self.canvas.all_cards().__class__._dummy if False else {c.card_id for c in self.canvas.all_cards()})

    def test_04_get_card(self):
        """按 ID 查卡片"""
        card = FakeCard()
        self.canvas.add_card(card)
        found = self.canvas.get_card("fake_card")
        self.assertIs(found, card)
        self.assertIsNone(self.canvas.get_card("nonexistent"))

    def test_05_remove_card(self):
        """移除卡片"""
        card = FakeCard()
        self.canvas.add_card(card)
        self.canvas.remove_card("fake_card")
        self.assertIsNone(self.canvas.get_card("fake_card"))
        self.assertEqual(len(self.canvas.all_cards()), 0)

    def test_06_add_card_duplicate_replaces(self):
        """同 ID 卡片会替换"""
        card1 = FakeCard()
        card2 = FakeCard()
        self.canvas.add_card(card1)
        self.canvas.add_card(card2)
        self.assertEqual(len(self.canvas.all_cards()), 1)
        self.assertIs(self.canvas.get_card("fake_card"), card2)

    def test_07_add_non_card_raises(self):
        """非 CardBase 抛 TypeError"""
        from PyQt6.QtWidgets import QWidget
        with self.assertRaises(TypeError):
            self.canvas.add_card(QWidget())

    def test_08_add_card_no_id_raises(self):
        """无 card_id 抛 ValueError"""
        from core.card_base import CardBase
        class NoIdCard(CardBase):
            card_id = ""
            def init_ui(self): pass
            def update_data(self): pass
        with self.assertRaises(ValueError):
            self.canvas.add_card(NoIdCard())

    def test_09_layout_persistence(self):
        """添加卡片后位置被保存到 SQLite"""
        # 先清掉上轮残留
        StorageManager.instance().delete_layout("fake_card")
        card = FakeCard()
        # 强制一个非默认位置
        card.setGeometry(111, 222, 333, 444)
        self.canvas.add_card(card)
        self.canvas.save_layout("fake_card")
        # 重新从 DB 读
        storage = StorageManager.instance()
        data = storage.load_layout("fake_card")
        self.assertIsNotNone(data)
        self.assertEqual(data["x"], 111)
        self.assertEqual(data["y"], 222)
        self.assertEqual(data["w"], 333)
        self.assertEqual(data["h"], 444)

    def test_10_restore_layout_on_add(self):
        """已有 layout 时,新卡片位置从 DB 恢复"""
        # 先存一个 layout
        storage = StorageManager.instance()
        storage.save_layout("fake_card", 555, 666, 777, 888, visible=True)
        # 加卡片
        card = FakeCard()
        # 卡片本身是 200x100,加了之后应该被恢复成 777x888
        self.canvas.add_card(card)
        self.assertEqual(card.x(), 555)
        self.assertEqual(card.y(), 666)
        self.assertEqual(card.width(), 777)
        self.assertEqual(card.height(), 888)

    def test_11_interactive_toggle(self):
        """交互态切换"""
        self.assertFalse(self.canvas.is_interactive())
        self.canvas.enter_interactive_mode()
        self.assertTrue(self.canvas.is_interactive())
        self.canvas.exit_interactive_mode()
        self.assertFalse(self.canvas.is_interactive())

    def test_12_interactive_signal(self):
        """交互态 signal 触发"""
        signals = []
        self.canvas.interactive_changed.connect(lambda b: signals.append(b))
        self.canvas.enter_interactive_mode()
        self.canvas.exit_interactive_mode()
        self.assertEqual(signals, [True, False])

    def test_13_event_bus_canvas_events(self):
        """EventBus 收到 canvas:interactive_on/off"""
        bus = EventBus.instance()
        events = []
        bus.subscribe("canvas:interactive_on", lambda p: events.append("on"))
        bus.subscribe("canvas:interactive_off", lambda p: events.append("off"))
        self.canvas.enter_interactive_mode()
        self.canvas.exit_interactive_mode()
        self.assertEqual(events, ["on", "off"])

    def test_14_default_position_from_config(self):
        """无 storage 时,使用 config 默认位置"""
        # 删 storage 里 fake_card 的记录
        storage = StorageManager.instance()
        storage.delete_layout("fake_card")
        # canvas 给一个 default position
        canvas2 = Canvas(config={
            "click_through": True,
            "span_all_screens": False,
            "auto_save_interval": 0,
            "default_positions": {"fake_card": {"x": 99, "y": 88, "width": 150, "height": 120}},
        })
        try:
            card = FakeCard()
            canvas2.add_card(card)
            self.assertEqual(card.x(), 99)
            self.assertEqual(card.y(), 88)
            self.assertEqual(card.width(), 150)
            self.assertEqual(card.height(), 120)
        finally:
            canvas2.shutdown()
            canvas2.deleteLater()

    def test_15_shutdown_clears_cards(self):
        """shutdown 清理所有卡片"""
        # 用不同 card_id 才能同时存在 3 个
        from core.card_base import CardBase
        class FakeCardA(CardBase):
            card_id = "fake_a"
            default_size = (50, 50)
            def init_ui(self): pass
            def update_data(self): pass
        class FakeCardB(CardBase):
            card_id = "fake_b"
            default_size = (50, 50)
            def init_ui(self): pass
            def update_data(self): pass
        class FakeCardC(CardBase):
            card_id = "fake_c"
            default_size = (50, 50)
            def init_ui(self): pass
            def update_data(self): pass
        for c in (FakeCardA(), FakeCardB(), FakeCardC()):
            self.canvas.add_card(c)
        self.assertEqual(len(self.canvas.all_cards()), 3)
        self.canvas.shutdown()
        self.assertEqual(len(self.canvas.all_cards()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
