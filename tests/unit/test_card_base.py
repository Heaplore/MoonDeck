"""CardBase 单元测试"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "unit"))

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from _fake_card import FakeCard


class TestCardBase(unittest.TestCase):
    """CardBase 抽象基类行为"""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.card = FakeCard(config={"foo": "bar", "nested": {"a": 1}})

    def tearDown(self):
        self.card.deleteLater()

    def test_01_metadata(self):
        """元信息子类可读"""
        self.assertEqual(self.card.card_id, "fake_card")
        self.assertEqual(self.card.card_name, "Fake Test Card")
        self.assertEqual(self.card.default_size, (200, 100))

    def test_02_default_size_applied(self):
        """默认尺寸生效"""
        self.assertEqual(self.card.width(), 200)
        self.assertEqual(self.card.height(), 100)

    def test_03_update_data_called_once(self):
        """构造时调用 update_data 一次"""
        self.assertEqual(self.card.update_data_called, 1)

    def test_04_config_simple(self):
        """config 简单 key"""
        self.assertEqual(self.card.config("foo"), "bar")
        self.assertIsNone(self.card.config("missing"))
        self.assertEqual(self.card.config("missing", "default"), "default")

    def test_05_config_dotted(self):
        """config 点号路径"""
        self.assertEqual(self.card.config("nested.a"), 1)
        self.assertIsNone(self.card.config("nested.missing"))

    def test_06_serialize(self):
        """序列化包含 card_id + 几何"""
        data = self.card.serialize()
        self.assertEqual(data["card_id"], "fake_card")
        self.assertIn("x", data)
        self.assertIn("y", data)
        self.assertIn("w", data)
        self.assertIn("h", data)

    def test_07_deserialize(self):
        """反序列化恢复几何"""
        self.card.deserialize({"x": 500, "y": 600, "w": 250, "h": 150, "visible": True})
        self.assertEqual(self.card.x(), 500)
        self.assertEqual(self.card.y(), 600)
        self.assertEqual(self.card.width(), 250)
        self.assertEqual(self.card.height(), 150)

    def test_08_on_drag_end(self):
        """拖拽结束回调"""
        self.card.on_drag_end(QPoint(100, 200))
        self.assertEqual(len(self.card.on_drag_end_called), 1)

    def test_09_window_flags(self):
        """窗口标志:无边框 + 工具窗口"""
        flags = self.card.windowFlags()
        from PyQt6.QtCore import Qt
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.Tool)

    def test_10_translucent(self):
        """透明背景属性"""
        from PyQt6.QtCore import Qt
        self.assertTrue(self.card.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))


if __name__ == "__main__":
    unittest.main(verbosity=2)
