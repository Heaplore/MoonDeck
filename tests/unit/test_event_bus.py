"""EventBus 单元测试"""
import sys
import unittest
from pathlib import Path

# 让 core 可以 import
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QCoreApplication
from core.event_bus import EventBus


class TestEventBus(unittest.TestCase):
    """EventBus 单例 + 订阅/发布"""

    @classmethod
    def setUpClass(cls):
        # QApplication 必须存在(Qt Signal 需要)
        cls._app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        EventBus.reset_instance()

    def setUp(self):
        EventBus.reset_instance()
        self.bus = EventBus.instance()

    def tearDown(self):
        EventBus.reset_instance()

    def test_01_singleton(self):
        """单例:两次 .instance() 返回同一对象"""
        a = EventBus.instance()
        b = EventBus.instance()
        self.assertIs(a, b)

    def test_02_emit_subscribe(self):
        """基本 emit + subscribe"""
        received = []
        self.bus.subscribe("test:event", lambda p: received.append(p))
        self.bus.emit("test:event", {"value": 42})
        # Qt Signal 是同步直连 → 直接触发
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["value"], 42)

    def test_03_multiple_subscribers(self):
        """多订阅者"""
        a, b, c = [], [], []
        self.bus.subscribe("evt", lambda p: a.append(p))
        self.bus.subscribe("evt", lambda p: b.append(p))
        self.bus.subscribe("other", lambda p: c.append(p))  # 不同事件
        self.bus.emit("evt", "hello")
        self.assertEqual(a, ["hello"])
        self.assertEqual(b, ["hello"])
        self.assertEqual(c, [])  # 不应收到

    def test_04_unsubscribe(self):
        """取消订阅"""
        received = []
        unsub = self.bus.subscribe("evt", lambda p: received.append(p))
        self.bus.emit("evt", 1)
        self.assertEqual(received, [1])
        # 取消订阅
        unsub()
        self.bus.emit("evt", 2)
        self.assertEqual(received, [1])  # 没收到第二条

    def test_05_subscriber_exception_isolated(self):
        """一个订阅者异常不影响其他订阅者"""
        results = []
        self.bus.subscribe("evt", lambda p: results.append("A"))
        self.bus.subscribe("evt", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
        self.bus.subscribe("evt", lambda p: results.append("C"))
        # 不应抛异常
        try:
            self.bus.emit("evt", None)
        except Exception as e:
            self.fail(f"emit 不应传播异常,但抛了: {e}")
        self.assertIn("A", results)
        self.assertIn("C", results)

    def test_06_subscriber_count(self):
        """订阅者计数"""
        self.assertEqual(self.bus.subscriber_count("evt"), 0)
        self.bus.subscribe("evt", lambda p: None)
        self.bus.subscribe("evt", lambda p: None)
        self.assertEqual(self.bus.subscriber_count("evt"), 2)

    def test_07_history(self):
        """事件历史"""
        self.bus.emit("e1", 1)
        self.bus.emit("e2", 2)
        hist = self.bus.history()
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0][0], "e1")
        self.assertEqual(hist[1][0], "e2")
        self.bus.clear_history()
        self.assertEqual(len(self.bus.history()), 0)

    def test_08_payload_none(self):
        """payload 默认 None"""
        received = []
        self.bus.subscribe("p", lambda p: received.append(p))
        self.bus.emit("p")
        self.assertEqual(received, [None])


if __name__ == "__main__":
    unittest.main(verbosity=2)
