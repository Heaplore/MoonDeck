"""MonthView - 月历自绘控件

负责绘制 6x7 网格的月视图,处理点击事件,emit 信号给主 widget。

布局:
   一 二 三 四 五 六 日
 ┌──┬──┬──┬──┬──┬──┬──┐
 │ 1│ 2│ 3│ 4│ 5│ 6│ 7│
 │初│  │  │  │  │  │  │  <- 农历日 / 节日
 ├──┼──┼──┼──┼──┼──┼──┤
 ...

设计原则:
- 自绘(不用 QCalendarWidget):完全控制样式 + 主题
- 节日农历文本:每个格最多显示 1 个,优先级: 节日 > 节气 > 农历日
- 今日:圆角背景 + 文字反白
- 选中:边框高亮
- 周末:周末色
- 邻月:淡色
- 切换月份:emit month_changed
- 点击日期:emit day_clicked(date)
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics
)
from PyQt6.QtWidgets import QWidget

from .lunar import (
    SolarDay, get_month_calendar, get_festivals, get_today_info,
    _LUNAR_MONTHS, _LUNAR_DAYS
)
# ThemeManager 路径
import sys
from pathlib import Path
_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
try:
    from core.theme import ThemeManager
except ImportError:
    # 兑底: 简易占位(在独立测试场景)
    class ThemeManager:
        _instance = None
        def __init__(self, *a, **k): pass
        @classmethod
        def instance(cls): return cls._instance or cls()


# 星期标签
_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


class MonthView(QWidget):
    """月历自绘控件"""

    day_clicked = pyqtSignal(object)        # 点击的 date
    month_changed = pyqtSignal(int, int)    # (year, month)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._today = date.today()
        self._year = self._today.year
        self._month = self._today.month
        self._selected: Optional[date] = self._today
        self._events_map: Dict[date, List[str]] = {}

        # 颜色缓存(避免每帧重查 ThemeManager)
        self._recompute_colors()
        ThemeManager.instance().subscribe(lambda name, theme: self._on_theme_changed(name))

        self.setMouseTracking(True)
        # 固定高度:每个 cell 42px,加 14px 头 + 3px 底
        self.setFixedHeight(35 + 45 * 5 + 3)  # = 263, v0.5.1 头35+行45
        self.setMinimumWidth(280)

    def _on_theme_changed(self, _name: str) -> None:
        self._recompute_colors()
        self.update()

    def _recompute_colors(self) -> None:
        tm = ThemeManager.instance()
        self.c_bg_card = self._to_color(tm.get("background", "#1a1a2e"))
        self.c_text_primary = self._to_color(tm.get("text_primary", "#e0e0ff"))
        self.c_text_secondary = self._to_color(tm.get("text_secondary", "#a0aec0"))
        self.c_accent = self._to_color(tm.get("accent", "#f6ad55"))
        self.c_accent_text = self._to_color(tm.get("accent_text", tm.get("accent", "#f6ad55")))
        self.c_border = self._to_color(tm.get("border", "#b794f4"))
        self.c_success = self._to_color(tm.get("success", "#48bb78"))
        self.c_warning = self._to_color(tm.get("warning", "#ed8936"))
        self.c_danger = self._to_color(tm.get("danger", "#f56565"))
        self.font_family = tm.get("fonts", {}).get("family", "Microsoft YaHei UI, sans-serif") if isinstance(tm.get("fonts"), dict) else "Microsoft YaHei UI, sans-serif"

    def _to_color(self, v) -> QColor:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("rgba"):
                # 简化的 rgba 解析
                inside = v[5:-1]
                parts = [p.strip() for p in inside.split(",")]
                if len(parts) >= 3:
                    r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                    a = float(parts[3]) if len(parts) > 3 else 1.0
                    return QColor(r, g, b, int(a * 255))
            if v.startswith("#"):
                return QColor(v)
        return QColor("#888888")

    # === 公共 API ===

    def set_month(self, year: int, month: int) -> None:
        if year != self._year or month != self._month:
            self._year, self._month = year, month
            self.month_changed.emit(year, month)
            self.update()

    def current_month(self) -> tuple:
        return (self._year, self._month)

    def go_prev_month(self) -> None:
        y, m = self._year, self._month - 1
        if m == 0:
            y, m = y - 1, 12
        self.set_month(y, m)

    def go_next_month(self) -> None:
        y, m = self._year, self._month + 1
        if m == 13:
            y, m = y + 1, 1
        self.set_month(y, m)

    def go_today(self) -> None:
        t = date.today()
        self._selected = t
        self.set_month(t.year, t.month)

    def set_events(self, events_map: Dict[date, List[str]]) -> None:
        self._events_map = events_map
        self.update()

    def selected_date(self) -> Optional[date]:
        return self._selected

    # === 绘制 ===

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        if w < 280 or h < 70:
            return

        # 计算布局
        header_h = 14
        grid_top = header_h + 1
        grid_h = h - grid_top
        col_w = w / 7.0
        row_h = grid_h / 5.0

        # 绘制星期标签
        font = QFont(self.font_family, 10, QFont.Weight.Bold)
        painter.setFont(font)
        for i, wd in enumerate(_WEEKDAYS):
            rect = QRect(int(i * col_w), 0, int(col_w), header_h)
            text_color = self.c_text_secondary
            if i >= 5:  # 周末
                text_color = self.c_warning if i == 5 else self.c_danger
            painter.setPen(text_color)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, wd)

        # 绘制月份网格
        grid = get_month_calendar(self._year, self._month, self._events_map)
        for row in range(5):
            for col in range(7):
                cell = grid[row][col]
                if cell is None:
                    continue
                self._draw_cell(painter, cell, col, row, col_w, row_h, grid_top)

        painter.end()

    def _draw_cell(
        self, painter: QPainter, cell: SolarDay,
        col: int, row: int, col_w: float, row_h: float, grid_top: float,
    ) -> None:
        x = int(col * col_w)
        y = int(grid_top + row * row_h)
        cw = int(col_w)
        ch = int(row_h)
        # 留 2px 间距
        margin = 2
        rect = QRect(x + margin, y + margin, cw - 2 * margin, ch - 2 * margin)

        # 背景:今日画圆角背景
        is_today = cell.is_today
        is_selected = (self._selected == cell.date)
        is_in_month = cell.in_current_month
        is_weekend = cell.is_weekend

        # 文本颜色
        if not is_in_month:
            text_color = QColor(self.c_text_secondary)
            text_color.setAlpha(90)
            sub_color = text_color
        elif is_today:
            text_color = QColor(self.c_bg_card)  # 今日数字用背景色(反白)
            sub_color = QColor(self.c_bg_card)  # 农历/节日也用深色,在冷青底上可读
            sub_color.setAlpha(220)
        elif is_weekend:
            text_color = QColor(self.c_warning if cell.weekday == 5 else self.c_danger)
            sub_color = QColor(self.c_text_secondary)
        else:
            text_color = QColor(self.c_text_primary)
            sub_color = QColor(self.c_text_secondary)

        # 今日背景(圆角矩形,冷青)
        if is_today:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.c_accent_text))
            painter.drawRoundedRect(rect, 10, 10)

        # 选中边框
        if is_selected and not is_today:
            pen = QPen(self.c_border, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 10, 10)

        # 数字大字
        font_day = QFont(self.font_family, 14, QFont.Weight.Bold)
        painter.setFont(font_day)
        painter.setPen(text_color)
        # 阳历: 顶部留 2px, 占 50% 高度(避免与农历重叠)
        day_rect = QRect(rect.x(), rect.y() + 2, rect.width(), int(rect.height() * 0.5))
        painter.drawText(day_rect, Qt.AlignmentFlag.AlignCenter, str(cell.day))

        # 农历/节日小字
        sub_text = cell.lunar_text()
        # 节日高亮
        is_festival = bool(cell.events) and any(
            e in {"休", "班"} or any(c in e for c in ["节", "气", "旦", "宵", "夕", "至"])
            for e in cell.events
        )
        if sub_text:
            # 今日:保持深色(在冷青底上可读),跳过节日高亮
            if is_today:
                sub_color_final = QColor(sub_color)
            elif is_festival and is_in_month:
                sub_color_final = QColor(self.c_accent_text)  # 节日:冷青
            elif is_festival and not is_in_month:
                sc = QColor(self.c_accent_text)
                sc.setAlpha(120)
                sub_color_final = sc
            else:
                sub_color_final = QColor(sub_color)
            font_sub = QFont(self.font_family, 8)
            painter.setFont(font_sub)
            painter.setPen(sub_color_final)
            # 农历: 从 50% 处开始, 占 45% 高度(留 5% 底部), 严格不重叠
            sub_rect = QRect(rect.x(), rect.y() + int(rect.height() * 0.5),
                             rect.width(), int(rect.height() * 0.45))
            # 截断
            metrics = QFontMetrics(font_sub)
            elided = metrics.elidedText(sub_text, Qt.TextElideMode.ElideRight, sub_rect.width() - 4)
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, elided)

        # 事件圆点(用户事件)
        user_events = [e for e in cell.events if e not in get_festivals(cell.date)]
        if user_events:
            dot_color = self.c_success
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(dot_color))
            dot_r = 3
            dot_x = rect.x() + rect.width() - dot_r - 4
            dot_y = rect.y() + 4
            painter.drawEllipse(QPoint(dot_x, dot_y), dot_r, dot_r)

    # === 鼠标 ===

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        x = pos.x()
        y = pos.y()
        w = self.width()
        h = self.height()
        header_h = 14
        grid_top = header_h + 1
        if y < grid_top:
            return
        col_w = w / 7.0
        row_h = (h - grid_top) / 5.0
        col = int(x / col_w)
        row = int((y - grid_top) / row_h)
        if 0 <= col < 7 and 0 <= row < 5:
            grid = get_month_calendar(self._year, self._month, self._events_map)
            cell = grid[row][col]
            if cell:
                self._selected = cell.date
                self.day_clicked.emit(cell.date)
                self.update()
