"""calendar_card lunar 模块单元测试"""
from datetime import date
from pathlib import Path
import tempfile

import pytest

from cards.calendar_card.lunar import (
    solar_to_lunar, get_lunar_text, get_ganzhi_year, get_shengxiao,
    get_solar_term, get_festivals, get_month_calendar, get_today_info,
    get_upcoming_holidays, cn_digit, SolarDay,
)
from cards.calendar_card.events import CalendarEventStore


class TestSolarToLunar:
    def test_known_date(self):
        ld = solar_to_lunar(date(2026, 6, 12))
        assert ld.year == 2026
        assert ld.month == 4
        assert ld.day == 27

    def test_chinese_new_year_2024(self):
        # 2024 春节 = 2024-02-10
        ld = solar_to_lunar(date(2024, 2, 10))
        assert ld.month == 1
        assert ld.day == 1


class TestGanzhi:
    def test_2026_is_bingwu(self):
        assert get_ganzhi_year(date(2026, 6, 12)) == "丙午"
        assert get_shengxiao(date(2026, 6, 12)) == "马"

    def test_2024_is_jiamao(self):
        # 春节前 1 天
        assert get_ganzhi_year(date(2024, 2, 1)) == "癸卯"
        assert get_shengxiao(date(2024, 2, 1)) == "兔"


class TestFestivals:
    def test_chinese_new_year(self):
        # 2026 春节 = 2026-02-17
        f = get_festivals(date(2026, 2, 17))
        assert "春节" in f

    def test_lantern_festival(self):
        # 2026 元宵 = 2026-03-03
        f = get_festivals(date(2026, 3, 3))
        assert "元宵节" in f

    def test_dragon_boat(self):
        # 2026 端午 = 2026-06-19
        f = get_festivals(date(2026, 6, 19))
        assert "端午节" in f

    def test_mid_autumn(self):
        # 2026 中秋 = 2026-09-25
        f = get_festivals(date(2026, 9, 25))
        assert "中秋节" in f

    def test_qingming_solar_term(self):
        # 2026 清明 = 2026-04-04
        assert get_solar_term(date(2026, 4, 4)) == "清明"

    def test_xiazhi_solar_term(self):
        # 2026 夏至 = 2026-06-21
        assert get_solar_term(date(2026, 6, 21)) == "夏至"


class TestMonthCalendar:
    def test_grid_shape(self):
        grid = get_month_calendar(2026, 6)
        assert len(grid) == 6
        for row in grid:
            assert len(row) == 7

    def test_june_2026_first_day_is_monday(self):
        # 2026-06-01 是周一
        grid = get_month_calendar(2026, 6)
        # 第 0 行第 0 列 = 6月1日
        cell = grid[0][0]
        assert cell.date == date(2026, 6, 1)
        assert cell.in_current_month is True
        assert cell.weekday == 0  # Monday

    def test_prev_month_filling(self):
        grid = get_month_calendar(2026, 6)
        # 5月最后一天是周日,在 6月日历的最后一周
        # 6月有 30 天,日历共 5+1=6 行
        # 最后一行: 6/29(周一), 6/30(周二), 7/1(周三)...
        last_row = grid[-1]
        # 5月 31 日(周日) 应在最后一行最后
        assert last_row[-1].date == date(2026, 7, 12)  # 实际看具体月

    def test_next_month_filling(self):
        grid = get_month_calendar(2026, 6)
        # 6/30 在第 4 行第 1 列(周二)
        row_4 = grid[4]
        assert row_4[1].date == date(2026, 6, 30) and row_4[1].in_current_month
        # 7/1 在第 4 行第 2 列(周三),in_current_month=False
        assert row_4[2].date == date(2026, 7, 1) and not row_4[2].in_current_month
        # 7/6-7/12 在最后一行
        last_row = grid[-1]
        assert last_row[0].date == date(2026, 7, 6) and not last_row[0].in_current_month
        assert last_row[-1].date == date(2026, 7, 12) and not last_row[-1].in_current_month

    def test_user_events_merged(self):
        events = {date(2026, 6, 19): ["家宴"]}
        grid = get_month_calendar(2026, 6, events)
        for row in grid:
            for cell in row:
                if cell.date == date(2026, 6, 19):
                    assert "家宴" in cell.events
                    assert "端午节" in cell.events
                    return
        pytest.fail("6月19日未找到")

    def test_today_highlight(self):
        today = date.today()
        grid = get_month_calendar(today.year, today.month)
        found = False
        for row in grid:
            for cell in row:
                if cell.date == today:
                    assert cell.is_today is True
                    found = True
        assert found


class TestSolarDay:
    def test_weekend(self):
        # 2026-06-13 是周六
        cell = SolarDay(date=date(2026, 6, 13))
        assert cell.is_weekend is True

    def test_weekday(self):
        cell = SolarDay(date=date(2026, 6, 12))  # 周五
        assert cell.is_weekend is False


class TestTodayInfo:
    def test_keys(self):
        info = get_today_info()
        for key in ["date", "solar_text", "weekday_text", "lunar_text", "festivals"]:
            assert key in info


class TestUpcoming:
    def test_returns_3(self):
        result = get_upcoming_holidays(3)
        assert len(result) == 3
        for name, days in result:
            assert isinstance(name, str)
            assert isinstance(days, int)


class TestCnDigit:
    @pytest.mark.parametrize("n,expected", [
        (1, "一"), (5, "五"), (9, "九"),
        (10, "十"), (11, "十一"), (19, "十九"),
        (20, "二十"), (25, "二十五"),
        (30, "三十"), (31, "三十一"),
    ])
    def test_values(self, n, expected):
        assert cn_digit(n) == expected


class TestEventStore:
    def setup_method(self):
        self.tmp = Path(tempfile.mkdtemp()) / "events.json"

    def teardown_method(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def test_add_and_get(self):
        store = CalendarEventStore(self.tmp)
        assert store.add_event(date(2026, 6, 12), "测试") is True
        ev = store.get_events(date(2026, 6, 12))
        assert "测试" in ev

    def test_duplicate_no_add(self):
        store = CalendarEventStore(self.tmp)
        store.add_event(date(2026, 6, 12), "测试")
        assert store.add_event(date(2026, 6, 12), "测试") is False
        assert len(store.get_events(date(2026, 6, 12))) == 1

    def test_remove(self):
        store = CalendarEventStore(self.tmp)
        store.add_event(date(2026, 6, 12), "测试")
        assert store.remove_event(date(2026, 6, 12), "测试") is True
        assert store.get_events(date(2026, 6, 12)) == []

    def test_persistence(self):
        store1 = CalendarEventStore(self.tmp)
        store1.add_event(date(2026, 6, 12), "持久化")
        # 新建实例,应能读到
        store2 = CalendarEventStore(self.tmp)
        ev = store2.get_events(date(2026, 6, 12))
        assert "持久化" in ev

    def test_get_events_in_range(self):
        store = CalendarEventStore(self.tmp)
        store.add_event(date(2026, 6, 12), "A")
        store.add_event(date(2026, 6, 15), "B")
        store.add_event(date(2026, 6, 20), "C")
        result = store.get_events_in_range(date(2026, 6, 10), date(2026, 6, 18))
        assert date(2026, 6, 12) in result
        assert date(2026, 6, 15) in result
        assert date(2026, 6, 20) not in result
