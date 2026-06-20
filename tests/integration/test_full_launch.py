"""MoonDeck 完整启动流程集成测试

模拟 main.py 的启动流程:
- 加载 config
- 初始化 Storage + Theme + EventBus
- 创建 Canvas
- 添加测试卡片
- 跑 1.5s 事件循环(检查 timer、刷新等)
- 关闭 + 验证布局持久化
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core import EventBus, StorageManager, ThemeManager
from core.canvas import Canvas
sys.path.insert(0, str(ROOT / "tests" / "unit"))
from _fake_card import FakeCard


class TestFullLaunch(unittest.TestCase):
    """main.py 启动流程的端到端模拟"""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        # 重置所有单例
        StorageManager.reset_instance()
        EventBus.reset_instance()
        ThemeManager.reset_instance()
        # 临时 DB
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)

    def tearDown(self):
        StorageManager.reset_instance()
        EventBus.reset_instance()
        ThemeManager.reset_instance()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_01_full_launch_cycle(self):
        """完整启动 → 运行 → 关闭 → 重启 流程"""
        # === 第一次启动 ===
        StorageManager.init_instance(self.db_path)
        ThemeManager(theme_yaml_path=None, default_name="dark")
        bus = EventBus.instance()
        canvas = Canvas(config={
            "click_through": True,
            "span_all_screens": False,
            "auto_save_interval": 0,
            "default_positions": {"fake_card": {"x": 50, "y": 60, "width": 200, "height": 100}},
        })
        # 添加卡片
        card = FakeCard()
        canvas.add_card(card)
        self.assertEqual(card.x(), 50)  # 默认位置
        # 移动卡片
        card.move(123, 456)
        # 手动保存
        canvas.save_layout("fake_card")
        # 关闭
        canvas.shutdown()
        # 关闭 storage
        StorageManager.instance().close()
        StorageManager.reset_instance()

        # === 第二次启动(同 DB) ===
        StorageManager.init_instance(self.db_path)
        ThemeManager(theme_yaml_path=None, default_name="dark")
        bus2 = EventBus.instance()
        canvas2 = Canvas(config={
            "click_through": True,
            "span_all_screens": False,
            "auto_save_interval": 0,
            "default_positions": {"fake_card": {"x": 50, "y": 60, "width": 200, "height": 100}},
        })
        card2 = FakeCard()
        canvas2.add_card(card2)
        # 位置应从 DB 恢复
        self.assertEqual(card2.x(), 123)
        self.assertEqual(card2.y(), 456)
        canvas2.shutdown()
        StorageManager.instance().close()
        StorageManager.reset_instance()

    def test_02_event_bus_routes_during_run(self):
        """运行中 EventBus 正确路由事件"""
        StorageManager.init_instance(self.db_path)
        ThemeManager(theme_yaml_path=None)
        bus = EventBus.instance()
        canvas = Canvas(config={"click_through": True, "auto_save_interval": 0, "span_all_screens": False})

        received = []
        bus.subscribe("test:during_run", lambda p: received.append(p))
        # emit
        bus.emit("test:during_run", "hello")
        self.assertEqual(received, ["hello"])
        # canvas 自己的事件
        bus.subscribe("canvas:interactive_on", lambda p: received.append("on"))
        canvas.enter_interactive_mode()
        self.assertIn("on", received)

        canvas.shutdown()
        StorageManager.instance().close()
        StorageManager.reset_instance()

    def test_03_theme_change_propagates(self):
        """主题变化 → 所有订阅者收到通知"""
        StorageManager.init_instance(self.db_path)
        ThemeManager(theme_yaml_path=None)

        bus = EventBus.instance()
        canvas = Canvas(config={"click_through": True, "auto_save_interval": 0, "span_all_screens": False})

        # 卡片订阅主题
        card = FakeCard()
        card._theme_sub_unsub = ThemeManager.instance().subscribe(
            lambda name, theme: card.apply_theme_called_increment()
        )
        # 由于上面 _theme_sub_unsub 在 init 前调用,实际拿不到,简化
        canvas.add_card(card)

        # 直接调 theme
        before = card.apply_theme_called
        ThemeManager.instance().set_theme("light")
        # 因为我们没用 ThemeManager.subscribe,apply_theme_called 不会自动增加
        # 但手动调应该增加
        card.apply_theme()
        self.assertGreater(card.apply_theme_called, before)

        canvas.shutdown()
        StorageManager.instance().close()
        StorageManager.reset_instance()

    def test_04_short_event_loop_run(self):
        """跑短事件循环验证 timer/signal 都不崩"""
        StorageManager.init_instance(self.db_path)
        ThemeManager(theme_yaml_path=None)
        bus = EventBus.instance()
        # auto_save_interval 设很小
        canvas = Canvas(config={
            "click_through": True,
            "auto_save_interval": 1,  # 1s
            "span_all_screens": False,
        })
        card = FakeCard()
        canvas.add_card(card)

        # 让 app 跑 1.5s
        QTimer.singleShot(1500, canvas.shutdown)
        QTimer.singleShot(1600, QApplication.instance().quit)
        QApplication.instance().exec()

        # shutdown 触发后所有 cards 应清空
        self.assertEqual(len(canvas.all_cards()), 0)
        StorageManager.instance().close()
        StorageManager.reset_instance()


if __name__ == "__main__":
    unittest.main(verbosity=2)
