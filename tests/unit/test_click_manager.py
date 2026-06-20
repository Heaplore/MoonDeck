"""ClickManager 单元测试

覆盖:
- 右键识别
- 非画布对象不响应
- 菜单动作 emit 对应 EventBus 事件
- 显示/隐藏切换
- 置顶/刷新/关闭
"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TEST_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402

from core.click_manager import ClickManager  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from tests.unit._test_helpers import FakeCanvas, FakeCard, get_qapp  # noqa: E402


def _to_f(p):
    return QPointF(float(p.x()), float(p.y()))


def make_press(canvas, global_pos, button):
    local = canvas.mapFromGlobal(global_pos)
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        _to_f(local),
        _to_f(global_pos),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


class TestClickManager(unittest.TestCase):
    def setUp(self):
        EventBus._instance = None
        self.app = get_qapp()
        self.bus = EventBus.instance()
        self.canvas = FakeCanvas()
        self.canvas.show()
        self.card = FakeCard("c1", "Card1")
        self.card.setGeometry(100, 100, 200, 100)
        self.canvas.add_widget_card("c1", self.card)
        self.card.show()
        self.cm = ClickManager(self.canvas, bus=self.bus)
        # 收集事件
        self.events: list = []
        for ev in ("card:refresh", "card:raised", "card:close", "card:visibility_changed"):
            self.bus.subscribe(ev, lambda p, e=ev: self.events.append((e, p)))

    def tearDown(self):
        EventBus._instance = None

    def test_right_click_emits_close_on_close_action(self):
        """右键弹出菜单 → 直接测 _close_card 内部函数"""
        self.cm._close_card("c1")
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0][0], "card:close")
        self.assertEqual(self.events[0][1]["card_id"], "c1")

    def test_refresh_emits_event(self):
        self.cm._fire("card:refresh", {"card_id": "c1"})
        self.assertEqual(self.events[-1][0], "card:refresh")

    def test_toggle_visible_emits_event(self):
        # 初始可见
        self.assertTrue(self.card.isVisible())
        self.cm._toggle_visible("c1")
        self.assertFalse(self.card.isVisible())
        self.assertEqual(self.events[-1][0], "card:visibility_changed")
        # 再切回
        self.cm._toggle_visible("c1")
        self.assertTrue(self.card.isVisible())

    def test_raise_card_emits_event(self):
        self.cm._raise_card("c1")
        self.assertEqual(self.events[-1][0], "card:raised")

    def test_left_click_does_not_open_menu(self):
        """左键不应触发右键菜单路径"""
        # eventFilter 接收左键 → 返回 False
        result = self.cm.eventFilter(
            self.canvas,
            make_press(self.canvas, QPoint(150, 150), Qt.MouseButton.LeftButton),
        )
        self.assertFalse(result)

    def test_right_click_outside_card(self):
        """空白处右键不弹菜单"""
        result = self.cm.eventFilter(
            self.canvas,
            make_press(self.canvas, QPoint(9999, 9999), Qt.MouseButton.RightButton),
        )
        self.assertFalse(result)
        # 没事件
        self.assertEqual(self.events, [])

    def test_eventfilter_ignores_other_widgets(self):
        from PyQt6.QtWidgets import QWidget
        other = QWidget()
        other.show()
        try:
            result = self.cm.eventFilter(
                other,
                make_press(self.canvas, QPoint(150, 150), Qt.MouseButton.RightButton),
            )
            self.assertFalse(result)
        finally:
            other.deleteLater()

    def test_disabled_blocks(self):
        self.cm.set_enabled(False)
        result = self.cm.eventFilter(
            self.canvas,
            make_press(self.canvas, QPoint(150, 150), Qt.MouseButton.RightButton),
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
