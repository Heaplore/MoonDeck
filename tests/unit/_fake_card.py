"""测试用假卡片(不依赖真实 token_card)"""
import sys
from pathlib import Path

# 让 core 可导入
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.card_base import CardBase


class FakeCard(CardBase):
    """最小可用 CardBase 实现,供测试用"""

    card_id = "fake_card"
    card_name = "Fake Test Card"
    card_icon = "🧪"
    default_size = (200, 100)
    update_interval_ms = 1000

    def __init__(self, config=None, parent=None):
        self.update_data_called = 0
        self.apply_theme_called = 0
        self.on_drag_end_called = []
        super().__init__(config, parent)

    def init_ui(self) -> None:
        # 不创建子控件,默认 paintEvent 兜底
        pass

    def update_data(self) -> None:
        self.update_data_called += 1

    def apply_theme(self) -> None:
        self.apply_theme_called += 1
        super().apply_theme()

    def on_drag_end(self, final_pos) -> None:
        self.on_drag_end_called.append(final_pos)
        super().on_drag_end(final_pos)
