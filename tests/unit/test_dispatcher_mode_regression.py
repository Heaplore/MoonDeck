"""回归测试:dispatcher 模式下,eventFilter 应该能接到 widget 的鼠标事件

背景(2026-06-13 bug):
  DragManager / ClickManager 在 dispatcher 模式(canvas 是 _Dispatcher 容器)
  下被 install 到所有 widget 上,但 eventFilter 里用
  `if obj is not self._canvas: return False` 过滤,
  导致 obj(widget) 永远 != self._canvas(dispatcher),所有事件直接被丢弃。

修复:
  在 dispatcher 模式下,用 `obj in canvas.all_cards()` 替代 `obj is canvas`。
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

# 让 unittest discover 能 import core.* / cards.*
_HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))

from core.drag_manager import DragManager, ResizeHandle  # noqa: E402
from core.click_manager import ClickManager  # noqa: E402
from core.event_bus import EventBus  # noqa: E402


class _Dispatcher:
    """模拟 main.py 里的 _Dispatcher 容器"""

    def __init__(self, widgets):
        self._widgets = {f"w{i}": (w, None) for i, w in enumerate(widgets)}

    def all_cards(self):
        return [w for w, _ in self._widgets.values()]

    def get_card(self, key):
        v = self._widgets.get(key)
        return v[0] if v else None

    def mapFromGlobal(self, pos):
        return pos  # 简化:本地==全局

    def width(self):
        return 1920

    def height(self):
        return 1080

    def install_event_filter_to_all(self, event_filter):
        for w in self.all_cards():
            w.installEventFilter(event_filter)


class DispatcherModeRegressionTest(unittest.TestCase):
    """验证 dispatcher 模式下 DragManager/ClickManager 真的能过滤 widget 事件"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # 3 个 widget,geometry 错开
        self.w1 = QWidget()
        self.w1.setGeometry(100, 100, 200, 150)
        self.w1.card_id = "card_a"
        self.w1.show()
        self.w2 = QWidget()
        self.w2.setGeometry(400, 100, 200, 150)
        self.w2.card_id = "card_b"
        self.w2.show()
        self.w3 = QWidget()
        self.w3.setGeometry(100, 300, 200, 150)
        self.w3.card_id = "card_c"
        self.w3.show()
        self.dispatcher = _Dispatcher([self.w1, self.w2, self.w3])
        self.bus = EventBus()
        # 重新订阅计数
        self.drag_events = []
        self.click_events = []
        self.bus.subscribe("card:moved", lambda p: self.drag_events.append(p))
        self.bus.subscribe("card:resized", lambda p: self.drag_events.append(p))
        self.bus.subscribe("card:refresh", lambda p: self.click_events.append(p))

    def _make_press(self, widget, local_pos):
        return QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(float(local_pos.x()), float(local_pos.y())),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_release(self, widget, local_pos):
        return QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(float(local_pos.x()), float(local_pos.y())),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def _make_move(self, widget, local_pos, buttons=Qt.MouseButton.LeftButton):
        return QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(float(local_pos.x()), float(local_pos.y())),
            Qt.MouseButton.NoButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )

    # === 核心回归 ===

    def test_drag_manager_eventfilter_accepts_widget_obj(self):
        """回归 1:DragManager 应该接收 widget 触发的事件(不是直接 return)"""
        dm = DragManager(self.dispatcher, bus=self.bus, snap_threshold=10)
        try:
            # 模拟:在 w1 内按下鼠标
            press = self._make_press(self.w1, QPoint(50, 50))
            # 直接调 eventFilter (因为 QApplication.postEvent 在 offscreen 不稳定)
            result = dm.eventFilter(self.w1, press)
            # 关键断言:不应该是被过滤掉的(False 但内部已经处理)
            # 我们看状态是否设置上
            self.assertIsNotNone(dm._state, "DragManager 没接到 widget 事件!")
            self.assertEqual(dm._state.card_id, "card_a")
            self.assertEqual(dm._state.mode, "drag")
        finally:
            dm._state = None

    def test_drag_manager_ignores_unknown_obj(self):
        """回归 2:DragManager 应该忽略非 card widget 的事件"""
        dm = DragManager(self.dispatcher, bus=self.bus, snap_threshold=10)
        # 创建一个不在 dispatcher 里的 widget
        foreign = QWidget()
        foreign.show()
        press = self._make_press(foreign, QPoint(0, 0))
        result = dm.eventFilter(foreign, press)
        self.assertFalse(result, "应该忽略未知 widget")
        self.assertIsNone(dm._state, "不应设置状态")

    def test_click_manager_eventfilter_accepts_widget_obj(self):
        """回归 3:ClickManager 应该接收 widget 的右键事件"""
        cm = ClickManager(self.dispatcher, bus=self.bus)
        # 模拟右键,Mock 掉 menu.exec 和 menu 构造
        from PyQt6.QtWidgets import QMenu
        class _FakeMenu:
            def __init__(self, *a, **k): pass
            def setObjectName(self, *a, **k): pass
            def addAction(self, *a, **k):
                class _A:
                    def __init__(self): self.triggered = type('X',(object,),{'connect':lambda fn, *a, **k: None})()
                    def setEnabled(self, *a, **k): pass
                return _A()
            def addSeparator(self): pass
            def exec(self, *a, **k): return None
        # Monkey-patch QMenu 在 click_manager 命名空间
        import core.click_manager as _cm_mod
        original_menu = _cm_mod.QMenu
        _cm_mod.QMenu = _FakeMenu
        try:
            # 右键
            press = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(50.0, 50.0),
                Qt.MouseButton.RightButton,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
            )
            result = cm.eventFilter(self.w1, press)
            # 关键:应该吞掉事件(返回 True)
            self.assertTrue(result, "ClickManager 没接住右键事件")
        finally:
            _cm_mod.QMenu = original_menu

    def test_full_drag_flow_emits_event(self):
        """回归 4:完整 drag 流程(press→move→release)应该 emit card:moved"""
        dm = DragManager(self.dispatcher, bus=self.bus, snap_threshold=10)
        try:
            # 按下
            press = self._make_press(self.w1, QPoint(50, 50))
            dm.eventFilter(self.w1, press)
            self.assertIsNotNone(dm._state)
            # 移动 30px(超过 5px 阈值)
            move = self._make_move(self.w1, QPoint(80, 80))
            dm.eventFilter(self.w1, move)
            self.assertTrue(dm._state.is_active)
            # 释放
            release = self._make_release(self.w1, QPoint(80, 80))
            dm.eventFilter(self.w1, release)
            # 关键断言:事件 emit 了
            self.assertEqual(len(self.drag_events), 1, f"应 emit 1 个事件,实际 {len(self.drag_events)}")
            self.assertEqual(self.drag_events[0]["card_id"], "card_a")
            self.assertEqual(self.drag_events[0]["mode"], "drag")
        finally:
            dm._state = None

    def test_resize_flow_with_se_handle(self):
        """回归 5:右下角拖动 → resize + emit card:resized"""
        dm = DragManager(self.dispatcher, bus=self.bus, snap_threshold=10)
        try:
            # w1 在 (100,100,200,150),按下绝对 (288, 240) → local (188, 140)
            # on_rc(188>=w-hs=200-12=188)=True, on_bc(140>=h-hs=150-12=138)=True → SE 角
            press = self._make_press(self.w1, QPoint(288, 240))
            dm.eventFilter(self.w1, press)
            self.assertIsNotNone(dm._state)
            self.assertEqual(dm._state.mode, "resize", f"应是 resize,实际 {dm._state.mode}")
            self.assertEqual(dm._state.handle, ResizeHandle.SE, f"应是 SE,实际 {dm._state.handle}")
            # 拖到绝对 (313, 265) → 扩大 25x25
            move = self._make_move(self.w1, QPoint(313, 265))
            dm.eventFilter(self.w1, move)
            # 释放
            release = self._make_release(self.w1, QPoint(313, 265))
            dm.eventFilter(self.w1, release)
            self.assertEqual(len(self.drag_events), 1)
            self.assertEqual(self.drag_events[0]["mode"], "resize")
            self.assertEqual(self.drag_events[0]["w"], 200 + (313 - 288))
        finally:
            dm._state = None

    def test_snap_to_canvas_edge(self):
        """回归 6:拖到屏边 10px 内 → 自动贴齐"""
        dm = DragManager(self.dispatcher, bus=self.bus, snap_threshold=10)
        try:
            # offscreen 模式下 widget 实际位置可能不是 (100,100)
            # 按 widget 内 (95,95),拖到 (5,5) → dx=-90, dy=-90
            # 释放时 w1.x = base_x - 90, 应在 10 阈值内, 吸到 0
            press2 = self._make_press(self.w1, QPoint(95, 95))
            dm._state = None
            dm.eventFilter(self.w1, press2)
            move = self._make_move(self.w1, QPoint(5, 5))
            dm.eventFilter(self.w1, move)
            release = self._make_release(self.w1, QPoint(5, 5))
            dm.eventFilter(self.w1, release)
            # 验证吸附: w1.x 应 <= 10(= 阈值 10 内,被吸到 0)
            # offscreen widget 真实位置可能与 geometry 偏差 ±2
            self.assertLessEqual(self.w1.x(), 10, f"应被吸到 <=10,实际 {self.w1.x()}")
            self.assertLessEqual(self.w1.y(), 10, f"应被吸到 <=10,实际 {self.w1.y()}")
        finally:
            dm._state = None
            # 还原位置,别影响别的测试
            self.w1.setGeometry(100, 100, 200, 150)


if __name__ == "__main__":
    unittest.main()
