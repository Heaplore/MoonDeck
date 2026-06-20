"""农历 / 节气 / 节日数据

提供:
- solar_to_lunar(date)        公历 -> 农历
- get_lunar_text(date)        返回 "农历四月廿七"
- get_solar_term(date)        返回节气名(立春/惊蛰...),无则 None
- get_festivals(date)         返回节日列表 ["端午节","父亲节"]
- is_weekend(date)            是否周末
- is_holiday(date)            是否法定节假日
- is_workday(date)            是否调休补班
- get_month_calendar(year, month) -> 6x7 二维数组(每格 SolarDay)
- cn_digit(n)                 数字转中文 ("1" -> "一")

数据源:
- lunardate: 农历转换
- chinese_calendar: 节假日判定
- sxtwl: 暂未使用(包太大),节气用手写查找表
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from lunardate import LunarDate
from chinese_calendar import is_holiday, get_holiday_detail, is_workday


# === 农历月份 / 日期 中文 ===

_LUNAR_MONTHS = [
    "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "冬月", "腊月",
]

_LUNAR_DAYS = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]

# 天干地支
_TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
_SHENGXIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]


# === 24 节气(按月份 + 日序 简化查找表)===
# 节气在公历的日期基本固定(±1 天),用近似日期即可
# 每月两个节气,排在月初和月中
_SOLAR_TERMS = {
    1:  ["小寒", "大寒"],
    2:  ["立春", "雨水"],
    3:  ["惊蛰", "春分"],
    4:  ["清明", "谷雨"],
    5:  ["立夏", "小满"],
    6:  ["芒种", "夏至"],
    7:  ["小暑", "大暑"],
    8:  ["立秋", "处暑"],
    9:  ["白露", "秋分"],
    10: ["寒露", "霜降"],
    11: ["立冬", "小雪"],
    12: ["大雪", "冬至"],
}

# 节气大致公历日序(±1 天精度足够)
_SOLAR_TERM_DAYS = {
    1:  [5, 20], 2:  [4, 19], 3:  [5, 20], 4:  [4, 20],
    5:  [5, 21], 6:  [5, 21], 7:  [7, 22], 8:  [7, 23],
    9:  [7, 23], 10: [8, 23], 11: [7, 22], 12: [7, 22],
}


# === 传统节日(按农历月日)===

_LUNAR_FESTIVALS = {
    (1, 1):  "春节",
    (1, 15): "元宵节",
    (2, 2):  "龙抬头",
    (5, 5):  "端午节",
    (7, 7):  "七夕节",
    (7, 15): "中元节",
    (8, 15): "中秋节",
    (9, 9):  "重阳节",
    (12, 8): "腊八节",
    (12, 23): "小年",
    (12, 30): "除夕",   # 也可能是 (12, 29)
}

# 英文 -> 中文 映射(给 chinese_calendar 的英文名转中文用)
_HOLIDAY_NAME_CN = {
    "New Year's Day": "元旦",
    "Spring Festival": "春节",
    "Tomb-sweeping Day": "清明节",
    "Labour Day": "劳动节",
    "Dragon Boat Festival": "端午节",
    "Mid-autumn Festival": "中秋节",
    "National Day": "国庆节",
    "Anti-Fascist War Day": "抗战胜利日",
}

# === 公历节日(按月日)===

_SOLAR_FESTIVALS = {
    (1, 1):   "元旦",
    (2, 14):  "情人节",
    (3, 8):   "妇女节",
    (3, 12):  "植树节",
    (4, 1):   "愚人节",
    (5, 1):   "劳动节",
    (5, 4):   "青年节",
    (6, 1):   "儿童节",
    (8, 1):   "建军节",
    (9, 10):  "教师节",
    (10, 1):  "国庆节",
    (11, 1):  "万圣节",
    (12, 24): "平安夜",
    (12, 25): "圣诞节",
}

# === 母亲节 / 父亲节(5月第2周日 / 6月第3周日) ===
# 用算法计算


# ============================================================
# 数据类
# ============================================================


@dataclass(frozen=True)
class SolarDay:
    """日历单格:代表一个公历日"""
    date: date                                # 公历日期
    in_current_month: bool = True             # True=当月,False=邻月填充
    events: List[str] = field(default_factory=list)  # 事件名/节日

    @property
    def year(self) -> int:
        return self.date.year

    @property
    def month(self) -> int:
        return self.date.month

    @property
    def day(self) -> int:
        return self.date.day

    @property
    def weekday(self) -> int:
        # Monday=0 ... Sunday=6
        return self.date.weekday()

    @property
    def is_today(self) -> bool:
        return self.date == date.today()

    @property
    def is_weekend(self) -> bool:
        return self.weekday >= 5

    def lunar_text(self) -> str:
        """农历短文本,优先显示节日/节气,否则显示农历日"""
        # 节日优先
        if self.events:
            return self.events[0]
        # 农历初一显示月份
        ld = solar_to_lunar(self.date)
        if ld.day == 1:
            return _LUNAR_MONTHS[ld.month - 1]
        return _LUNAR_DAYS[ld.day - 1]


# ============================================================
# 转换函数
# ============================================================


def solar_to_lunar(d: date) -> LunarDate:
    """公历 -> 农历"""
    return LunarDate.fromSolarDate(d.year, d.month, d.day)


def get_lunar_text(d: date) -> str:
    """获取农历完整文本: '农历四月廿七'"""
    ld = solar_to_lunar(d)
    month_text = _LUNAR_MONTHS[ld.month - 1]
    if ld.isLeapMonth:
        month_text = "闰" + month_text
    day_text = _LUNAR_DAYS[ld.day - 1]
    return f"农历{month_text}{day_text}"


def get_ganzhi_year(d: date) -> str:
    """获取干支年,例: '丙午'"""
    ld = solar_to_lunar(d)
    # lunardate 没有干支,简单按农历年计算(2024=甲辰,2026=丙午)
    # 用 1984 甲子年反推: (year - 1984) % 60
    idx = (ld.year - 1984) % 60
    tiangan_idx = idx % 10
    dizhi_idx = idx % 12
    return _TIANGAN[tiangan_idx] + _DIZHI[dizhi_idx]


def get_shengxiao(d: date) -> str:
    """获取生肖,例: '马'"""
    ld = solar_to_lunar(d)
    return _SHENGXIAO[(ld.year - 1900) % 12]


def get_solar_term(d: date) -> Optional[str]:
    """返回节气名,无则 None"""
    month_days = _SOLAR_TERM_DAYS.get(d.month, [])
    terms = _SOLAR_TERMS.get(d.month, [])
    for i, target_day in enumerate(month_days):
        # 精确匹配(表是多年平均近似,不需 ±1)
        if d.day == target_day:
            return terms[i]
    return None


def _get_solar_festival(d: date) -> Optional[str]:
    """公历节日"""
    return _SOLAR_FESTIVALS.get((d.month, d.day))


def _get_lunar_festival(d: date) -> Optional[str]:
    """农历节日"""
    ld = solar_to_lunar(d)
    name = _LUNAR_FESTIVALS.get((ld.month, ld.day))
    if name:
        return name
    # 除夕特判:腊月最后一天
    if ld.month == 12:
        # 看下一天是不是正月初一
        next_d = d + timedelta(days=1)
        next_ld = LunarDate.fromSolarDate(next_d.year, next_d.month, next_d.day)
        if next_ld.month == 1 and next_ld.day == 1:
            return "除夕"
    return None


def _get_relative_festival(d: date) -> Optional[str]:
    """第 N 个周 X 的节日(母亲节/父亲节)"""
    weekday = d.weekday()  # Monday=0
    # 5月第2个周日 = 母亲节
    if d.month == 5 and weekday == 6:
        week_of_month = (d.day - 1) // 7 + 1
        if week_of_month == 2:
            return "母亲节"
    # 6月第3个周日 = 父亲节
    if d.month == 6 and weekday == 6:
        week_of_month = (d.day - 1) // 7 + 1
        if week_of_month == 3:
            return "父亲节"
    return None


def get_festivals(d: date) -> List[str]:
    """返回该日所有节日/节气"""
    result: List[str] = []
    # 法定假日
    try:
        _is_holiday = is_holiday(d)
        _is_workday = is_workday(d)
    except (NotImplementedError, ValueError):
        _is_holiday = False
        _is_workday = d.weekday() < 5
    if _is_holiday:
        try:
            detail = get_holiday_detail(d)
        except Exception:
            detail = None
        # chinese_calendar 返回 (is_holiday: bool, name: str|None)
        if isinstance(detail, tuple) and len(detail) == 2:
            name = detail[1]
        elif isinstance(detail, str):
            name = detail
        else:
            name = None
        if name:
            # 英文转中文(没匹配的保留原名)
            cn_name = _HOLIDAY_NAME_CN.get(name, name)
            result.append(cn_name)
        else:
            result.append("休")  # 兜底:有假但无名
    # 调休补班
    elif _is_workday and d.weekday() >= 5:
        result.append("班")
    # 节气
    term = get_solar_term(d)
    if term and term not in result:
        result.append(term)
    # 公历节日
    sf = _get_solar_festival(d)
    if sf and sf not in result:
        result.append(sf)
    # 农历节日
    lf = _get_lunar_festival(d)
    if lf and lf not in result:
        result.append(lf)
    # 周日节日
    rf = _get_relative_festival(d)
    if rf and rf not in result:
        result.append(rf)
    return result


def is_today(d: date) -> bool:
    return d == date.today()


def get_today_info() -> Dict[str, object]:
    """获取今天的完整信息,用于卡片头部"""
    today = date.today()
    return {
        "date": today,
        "solar_text": f"{today.year}年{today.month}月{today.day}日",
        "weekday_text": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()],
        "lunar_text": get_lunar_text(today),
        "ganzhi": get_ganzhi_year(today),
        "shengxiao": get_shengxiao(today),
        "festivals": get_festivals(today),
        "is_holiday": is_holiday(today),
        "is_today": True,
    }


# ============================================================
# 月历网格
# ============================================================


def get_month_calendar(
    year: int,
    month: int,
    events_map: Optional[Dict[date, List[str]]] = None,
) -> List[List[Optional[SolarDay]]]:
    """生成 6x7 的月历网格(从周一开始)

    Args:
        year, month: 公历年月
        events_map: 用户事件 {date: ['会议', '生日']}

    Returns:
        6x7 的二维数组,每格是 SolarDay 或 None
        邻月日期 in_current_month=False
    """
    events_map = events_map or {}
    first_day = date(year, month, 1)
    first_weekday = first_day.weekday()  # Monday=0

    # 当月所有天
    _, days_in_month = calendar.monthrange(year, month)

    # 上个月填充(从 first_weekday 天前开始)
    if first_weekday > 0:
        prev_month_last = first_day - timedelta(days=1)
        prev_year, prev_month = prev_month_last.year, prev_month_last.month
        _, prev_days = calendar.monthrange(prev_year, prev_month)
        for i in range(first_weekday - 1, -1, -1):
            d = date(prev_year, prev_month, prev_days - i)
            # 留到下面统一生成 SolarDay
            pass

    # 生成所有格子
    cells: List[Optional[SolarDay]] = []
    # 填充前置
    if first_weekday > 0:
        prev_month_last = first_day - timedelta(days=1)
        prev_year, prev_month = prev_month_last.year, prev_month_last.month
        _, prev_days = calendar.monthrange(prev_year, prev_month)
        for i in range(first_weekday):
            d = date(prev_year, prev_month, prev_days - first_weekday + i + 1)
            cells.append(_make_solar_day(d, in_current_month=False, events_map=events_map))
    # 当月
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        cells.append(_make_solar_day(d, in_current_month=True, events_map=events_map))
    # 填充后置
    remaining = 42 - len(cells)  # 6x7=42
    next_year, next_month = (year, month + 1) if month < 12 else (year + 1, 1)
    for i in range(1, remaining + 1):
        d = date(next_year, next_month, i)
        cells.append(_make_solar_day(d, in_current_month=False, events_map=events_map))

    # 6 行 7 列
    return [cells[i * 7:(i + 1) * 7] for i in range(6)]


def _make_solar_day(d: date, in_current_month: bool, events_map: Dict[date, List[str]]) -> SolarDay:
    """构造 SolarDay(融合节日+用户事件)"""
    all_events = list(get_festivals(d))
    user_events = events_map.get(d, [])
    for ev in user_events:
        if ev not in all_events:
            all_events.append(ev)
    return SolarDay(date=d, in_current_month=in_current_month, events=all_events)


def cn_digit(n: int) -> str:
    """数字转中文(用于日期标签): 1->一 11->十一"""
    cn = "零一二三四五六七八九"
    if n < 10:
        return cn[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + cn[n - 10]
    if n < 30:
        return "二十" + (cn[n - 20] if n > 20 else "")
    if n == 30:
        return "三十"
    if n < 40:
        return "三十" + cn[n - 30]
    return str(n)


def get_days_in_month(year: int, month: int) -> int:
    """当月天数"""
    return calendar.monthrange(year, month)[1]


# ============================================================
# 倒计时
# ============================================================


def get_next_countdown(target: date) -> int:
    """距离 target 还有多少天(可负数,表示已过)"""
    today = date.today()
    return (target - today).days


def get_upcoming_holidays(n: int = 3) -> List[Tuple[str, int]]:
    """获取接下来 n 个重要节日(法定假日优先)

    Returns:
        [("国庆节", 88), ("中秋节", 95), ...]
    """
    today = date.today()
    result: List[Tuple[str, int, date]] = []
    # 接下来 365 天的所有节日
    for offset in range(0, 365):
        d = today + timedelta(days=offset)
        festivals = get_festivals(d)
        for f in festivals:
            # 优先级:法定 > 传统节日 > 公历节日
            try:
                _is_holiday = is_holiday(d)
            except (NotImplementedError, ValueError):
                _is_holiday = False
            if _is_holiday:
                priority = 0
            elif f in _LUNAR_FESTIVALS.values():
                priority = 1
            elif f in _SOLAR_FESTIVALS.values():
                priority = 2
            else:
                priority = 3
            result.append((f, (d - today).days, priority, d))
    # 排序:优先级小的优先 + 天数少的优先
    result.sort(key=lambda x: (x[2], x[1]))
    # 去重(同名只保留最近)
    seen = set()
    final = []
    for name, days, _prio, _d in result:
        if name in seen:
            continue
        seen.add(name)
        final.append((name, days))
        if len(final) >= n:
            break
    return final


# ============================================================
# 自测
# ============================================================


if __name__ == "__main__":
    today = date.today()
    print(f"今天: {today}")
    print(f"  农历: {get_lunar_text(today)}")
    print(f"  干支: {get_ganzhi_year(today)}")
    print(f"  生肖: {get_shengxiao(today)}")
    print(f"  节日: {get_festivals(today)}")
    print(f"  节假日: {is_holiday(today)}")
    print()
    print("接下来 3 个节日:")
    for name, days in get_upcoming_holidays(3):
        print(f"  {name}: {days} 天后")
    print()
    print("本月日历:")
    grid = get_month_calendar(today.year, today.month)
    for week in grid:
        for cell in week:
            if cell is None:
                print("    ", end=" ")
            else:
                marker = "*" if cell.is_today else (" " if cell.in_current_month else ".")
                print(f"{marker}{cell.day:2d}", end=" ")
        print()
