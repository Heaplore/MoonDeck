"""交互层共享测试 helper

提供:
- offscreen QApplication fixture
- 模拟 Canvas(有 all_cards / get_card / mapFromGlobal 等)
- 假 QWidget 卡片
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

# 测试环境:必须 offscreen
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

# 让 tests 能 import 顶层模块
_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TEST_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def get_qapp() -> QApplication:
    """获取(或创建)QApplication 实例"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class FakeCard(QWidget):
    """测试用假卡片

    - 模拟 canvas.add_widget_card 行为
    - 设置 card_id / card_name 属性
    - 默认位置 100,100 200x100
    """

    def __init__(self, card_id: str = "fake", name: str = "FakeCard", parent=None):
        super().__init__(parent)
        self.card_id = card_id
        self.card_name = name
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | self.windowFlags())
        self.setGeometry(100, 100, 200, 100)


class FakeCanvas(QWidget):
    """测试用假画布

    暴露接口:
    - add_widget_card / all_cards / get_card
    - mapFromGlobal
    - installEventFilter
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: Dict[str, QWidget] = {}
        # 屏幕区域 1920x1080(模拟多屏)
        self.setGeometry(0, 0, 1920, 1080)
        # 去掉 frame(测试时不要 window decoration 干扰坐标)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | self.windowFlags())

    def add_widget_card(self, card_id: str, widget: QWidget, card_name: str = "") -> None:
        widget.card_id = card_id
        widget.card_name = card_name or type(widget).__name__
        self._cards[card_id] = widget

    def all_cards(self) -> List[QWidget]:
        return list(self._cards.values())

    def get_card(self, card_id: str) -> Optional[QWidget]:
        return self._cards.get(card_id)

    def remove_card(self, card_id: str) -> None:
        self._cards.pop(card_id, None)

    def mapFromGlobal(self, pos: QPoint) -> QPoint:
        """画布自身覆盖整个屏幕,本地 = 全局"""
        return pos
