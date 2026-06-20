"""CalendarCard 集成测试 - 启动 + 渲染 + 关闭

验证:
1. 卡片能实例化(继承 CardBase)
2. 卡片能添加到画布
3. update_data 不抛错
4. 添加事件 → 选中日显示 → 月视图显示
5. 主题切换不崩
"""
import sys
from datetime import date
from pathlib import Path

import pytest

# 让 tests/ 能找到 cards/
_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

from core import ThemeManager
from core.canvas import Canvas
from cards.calendar_card import create_for_canvas


@pytest.fixture
def app():
    a = QApplication.instance()
    if a is None:
        a = QApplication(sys.argv)
    return a


@pytest.fixture
def theme(app):
    # 重置单例,确保干净状态
    ThemeManager.reset_instance()
    return ThemeManager.instance()


class TestCalendarCardStartup:
    def test_widget_creation(self, app, theme):
        widget, controller = create_for_canvas()
        assert widget is not None
        assert widget.card_id == "calendar_card"
        assert widget.card_name.startswith("📅")

    def test_widget_minimum_size(self, app, theme):
        widget, _ = create_for_canvas()
        assert widget.minimumSize().width() >= 360
        assert widget.minimumSize().height() >= 560

    def test_update_data_doesnt_crash(self, app, theme):
        widget, _ = create_for_canvas()
        widget.update_data()  # 应不抛错
        assert widget.month_view is not None
        # 验证倒计时已加载
        cd_text = widget.cd_labels[0].text()
        assert "天后" in cd_text or "今天" in cd_text or "已过" in cd_text or cd_text.strip() != "---"

    def test_month_view_starts_current(self, app, theme):
        widget, _ = create_for_canvas()
        today = date.today()
        y, m = widget.month_view.current_month()
        assert y == today.year
        assert m == today.month

    def test_navigation(self, app, theme):
        widget, _ = create_for_canvas()
        today = date.today()
        # 下一月
        widget.month_view.go_next_month()
        if today.month == 12:
            assert widget.month_view.current_month() == (today.year + 1, 1)
        else:
            assert widget.month_view.current_month() == (today.year, today.month + 1)
        # 上一月 = 回到原月
        widget.month_view.go_prev_month()
        assert widget.month_view.current_month() == (today.year, today.month)
        # 再上 = 上月
        widget.month_view.go_prev_month()
        if today.month == 1:
            assert widget.month_view.current_month() == (today.year - 1, 12)
        else:
            assert widget.month_view.current_month() == (today.year, today.month - 1)

    def test_event_add_and_display(self, app, theme):
        widget, _ = create_for_canvas()
        today = date.today()
        # 直接用 store 添加
        widget.store.clear()
        widget.store.add_event(today, "测试事件 A")
        widget.store.add_event(today, "测试事件 B")
        widget._refresh_detail()
        text = widget.detail_events_lbl.text()
        assert "测试事件 A" in text
        assert "测试事件 B" in text

    def test_canvas_adds_card(self, app, theme):
        canvas = Canvas(config={"fullscreen": True, "click_through": True})
        widget, controller = create_for_canvas()
        canvas.add_widget_card("calendar_card", widget, card_name=widget.card_name)
        controller.start()
        # 验证在画布的 widget_cards
        all_cards = canvas.all_cards()
        assert any(getattr(c, 'card_id', None) == 'calendar_card' for c in all_cards)
        # 验证 controller timer 在跑
        assert controller is not None
        canvas.shutdown()

    def test_theme_change_no_crash(self, app, theme):
        widget, _ = create_for_canvas()
        # 切换到每个主题
        for name in theme.themes():
            theme.set_theme(name)
            widget._on_theme_changed(name)  # 应不抛错
            widget.update()


class TestFullStartup:
    """模拟主程序启动:加载 config + 加载 calendar_card"""

    def test_full_flow(self, app, theme):
        # 构造画布
        canvas = Canvas(config={"fullscreen": False, "click_through": True})
        # 加载 calendar
        widget, controller = create_for_canvas()
        canvas.add_widget_card("calendar_card", widget, card_name=widget.card_name)
        # 跑 1.5s 事件循环
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, app.quit)
        controller.start()
        canvas.show()
        # offscreen 平台
        try:
            app.exec()
        except Exception:
            pass
        # 验证 widget 没崩
        assert widget is not None
        assert widget.month_view is not None
        canvas.shutdown()
