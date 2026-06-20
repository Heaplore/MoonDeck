"""DragManager 单元测试

覆盖:
- 启用/禁用
- 事件过滤器只对画布生效
- 阈值判断
- widget.move 实际被调用
- EventBus 事件(card:moved)
- 释放时未拖动 → 不发事件
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

# offscreen
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# path
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TEST_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from core.drag_manager import DragManager  # noqa: E402
from core.event_bus import EventBus  # noqa: E402
from tests.unit._test_helpers import FakeCanvas, FakeCard, get_qapp  # noqa: E402


def _to_f(p):
    """QPoint -> QPointF(PyQt6 6.11 QMouseEvent 要求 QPointF)"""
    return QPointF(float(p.x()), float(p.y()))


def make_press(canvas, global_pos, button=Qt.MouseButton.LeftButton):
    """造一个 QMouseEvent 鼠标按下事件"""
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


class TestDragManager(unittest.TestCase):
    def setUp(self):
        EventBus._instance = None
        self.app = get_qapp()
        self.bus = EventBus.instance()
        self.canvas = FakeCanvas()
        self.canvas.show()
        # 加 2 张卡
        self.card1 = FakeCard("card1", "Card1")
        self.card1.setGeometry(100, 100, 200, 100)
        self.canvas.add_widget_card("card1", self.card1)
        self.card1.show()
        self.card2 = FakeCard("card2", "Card2")
        self.card2.setGeometry(500, 500, 200, 100)
        self.canvas.add_widget_card("card2", self.card2)
        self.card2.show()
        self.dm = DragManager(self.canvas, bus=self.bus, threshold=5)
        # 收到的 move 事件列表
        self.moved_events = []
        self.bus.subscribe("card:moved", lambda p: self.moved_events.append(p))

    def tearDown(self):
        EventBus._instance = None

    def test_disabled_does_nothing(self):
        self.dm.set_enabled(False)
        # 走 eventFilter(disabled 在 eventFilter 入口拦截)
        self.dm.eventFilter(self.canvas, make_press(self.canvas, QPoint(150, 150)))
        self.assertIsNone(self.dm._state)

    def test_press_outside_cards(self):
        self.dm._handle_press(make_press(self.canvas, QPoint(9999, 9999)))
        self.assertIsNone(self.dm._state)

    def test_press_on_card_starts_session(self):
        # card1 在 (100,100,200,100)
        self.dm._handle_press(make_press(self.canvas, QPoint(150, 150)))
        self.assertIsNotNone(self.dm._state)
        self.assertEqual(self.dm._state.card_id, "card1")

    def test_move_below_threshold_no_drag(self):
        self.dm._handle_press(make_press(self.canvas, QPoint(150, 150)))
        # 移动 3px(阈值 5)
        self.dm._handle_move(make_move(self.canvas, QPoint(152, 152)))
        self.assertFalse(self.dm._state.is_dragging)
        # card 位置未变
        self.assertEqual(self.card1.x(), 100)
        self.assertEqual(self.card1.y(), 100)

    def test_move_above_threshold_drags(self):
        self.dm._handle_press(make_press(self.canvas, QPoint(150, 150)))
        # 移动 20px
        self.dm._handle_move(make_move(self.canvas, QPoint(170, 165)))
        self.assertTrue(self.dm._state.is_dragging)
        # card 位置已更新
        self.assertEqual(self.card1.x(), 100 + 20)
        self.assertEqual(self.card1.y(), 100 + 15)

    def test_release_without_drag_no_event(self):
        self.dm._handle_press(make_press(self.canvas, QPoint(150, 150)))
        self.dm._handle_release(make_release(self.canvas, QPoint(150, 150)))
        # 没拖动 → 不发事件
        self.assertEqual(self.moved_events, [])

    def test_release_after_drag_emits_event(self):
        self.dm._handle_press(make_press(self.canvas, QPoint(150, 150)))
        self.dm._handle_move(make_move(self.canvas, QPoint(170, 170)))
        self.dm._handle_release(make_release(self.canvas, QPoint(170, 170)))
        # 发了 1 个 card:moved
        self.assertEqual(len(self.moved_events), 1)
        evt = self.moved_events[0]
        self.assertEqual(evt["card_id"], "card1")
        self.assertEqual(evt["x"], 120)
        self.assertEqual(evt["y"], 120)

    def test_eventfilter_routes_correctly(self):
        """eventFilter 收到画布事件应该 dispatch 给 _handle_*"""
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QWidget
        # 模拟一个非画布对象
        other = QWidget()
        other.show()
        try:
            result = self.dm.eventFilter(other, make_press(self.canvas, QPoint(150, 150)))
            self.assertFalse(result)  # 不吞
        finally:
            other.deleteLater()

    def test_right_click_ignored(self):
        self.dm._handle_press(make_press(self.canvas, QPoint(150, 150), button=Qt.MouseButton.RightButton))
        self.assertIsNone(self.dm._state)


if __name__ == "__main__":
    unittest.main()
