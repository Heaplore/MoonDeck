"""
CalendarCardWidget - 月历卡片(集成天气顶部)

v0.5 (2026-06-14 天气集成到月历):
- 砍掉独立天气卡, 天气信息整合到月历卡片顶部
- 顶部: 城市 + 天气图标 + 温度 + 天气描述 + 日期
- 中间: 月历视图(保持不变)

布局(自上而下):
  ┌─────────────────────────────────┐
  │ [天气条 50px]                    │  50
  │ [分割线 1px]                     │  1
  │ [月历头 35px]                    │  35
  │ [月历]                           │  variable
  │ (16px bottom padding)            │
  └─────────────────────────────────┘
"""
from __future__ import annotations
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRect, QRectF, QTimer, QThread
from PyQt6.QtGui import (QPainter, QColor, QFont, QPen, QBrush,
                          QLinearGradient, QRadialGradient, QPainterPath)
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QLineEdit, QSizePolicy, QFrame, QScrollArea,
                              QGraphicsDropShadowEffect)

import os
_HERE = Path(__file__).resolve().parent
parent = _HERE.parent
_ROOT = parent.parent if parent.name == 'cards' else parent
sys.path.insert(0, str(_ROOT))

from core.card_base import CardBase
from core.theme import ThemeManager

from .lunar import (get_today_info, get_lunar_text, get_ganzhi_year, get_shengxiao,
                       get_festivals, get_upcoming_holidays, _LUNAR_MONTHS)
from .month_view import MonthView
from .events import CalendarEventStore
from cards.weather_card.service import WeatherService, WeatherData
from cards.token_card.service import TokenService, TokenUsage

import logging
_LOG = logging.getLogger(__name__)


# =============================================================================
# Helper
# =============================================================================

def _to_color(c) -> QColor:
    """主题配置颜色值 -> QColor。容错: 字符串/None/已是 QColor。"""
    if isinstance(c, QColor):
        return c
    if c is None:
        return QColor()
    if isinstance(c, str):
        s = c.strip()
        if s.startswith('#') and len(s) in (7, 9):
            return QColor(s)
        # rgba(...) / rgb(...) 形式
        m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)', s)
        if m:
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            a = int(float(m.group(4) or 1) * 255)
            return QColor(r, g, b, a)
        return QColor(s)
    return QColor()


# =============================================================================

# =============================================================================
# TokenAreaWidget — 银月额度区域
# =============================================================================

class TokenAreaWidget(QWidget):
    """银月额度区域: 分割线 + 标题 + 进度条"""

    def __init__(self, card, parent=None):
        super().__init__(parent)
        self._card = card
        self.setFixedHeight(80)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = ThemeManager.instance().current()

        text_p = _to_color(d.get('text_primary', '#e0e0ff'))
        text_s = _to_color(d.get('text_secondary', '#a0aec0'))
        border = _to_color(d.get('border', '#4a7c9e'))

        if isinstance(d.get('fonts'), dict):
            family = d.get('fonts', {}).get('family', 'Microsoft YaHei UI')
        else:
            family = 'Microsoft YaHei UI'
        if isinstance(d.get('fonts'), dict):
            body_size = d.get('fonts', {}).get('sizes', {}).get('body', 12)
        else:
            body_size = 12
        if isinstance(d.get('fonts'), dict):
            cap_size = d.get('fonts', {}).get('sizes', {}).get('caption', 9)
        else:
            cap_size = 9

        y = 17

        # 上方分割线
        p.setPen(QPen(QColor(border.red(), border.green(), border.blue(), 70)))
        p.drawLine(14, y, self.width() - 14, y)
        y += 17

        # Token 标题
        f_title = QFont(family, body_size + 1)
        f_title.setBold(True)
        p.setFont(f_title)
        p.setPen(QPen(text_p))
        p.drawText(14, y + 12, '🌙 MiniMax Token Plan额度')
        y += 26

        # Token 副标题 + 进度条
        f_cap = QFont(family, cap_size + 1)
        p.setFont(f_cap)
        u = self._card._token

        if not u.error:
            rem5 = u.interval_remaining_pct
            rem_week = u.weekly_remaining_pct

            p.setPen(QPen(text_s))
            p.drawText(14, y + 10, f'5h 剩余  {rem5:.0f}%')
            y += 16
            self._draw_bar(p, 14, y, self.width() - 28, 8, rem5, d)
            y += 18

            p.drawText(14, y + 10, f'本周剩余  {rem_week:.0f}%')
            y += 16
            self._draw_bar(p, 14, y, self.width() - 28, 8, rem_week, d)
            y += 18
        else:
            p.setPen(QPen(text_s))
            p.drawText(14, y + 10, '5h 剩余  --%')
            y += 16
            self._draw_bar(p, 14, y, self.width() - 28, 8, 0, d)
            y += 18
            p.drawText(14, y + 10, '本周剩余  --%')
            y += 16
            self._draw_bar(p, 14, y, self.width() - 28, 8, 0, d)
            y += 18

        p.end()

    def _draw_bar(self, p, x, y, w, h, pct, d) -> None:
        pct = max(0.0, min(100.0, pct))
        bg_c = _to_color(d.get('token_bar_bg', 'rgba(0,0,0,0.35)'))
        if pct < 20:
            fill_c = _to_color(d.get('token_bar_low', '#f6ad55'))
        elif pct < 50:
            fill_c = _to_color(d.get('token_bar_mid', '#B4C8DC'))
        else:
            fill_c = _to_color(d.get('token_bar_high', '#4a7c9e'))
        r = h / 2
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(x, y, w, h), r, r)
        p.fillPath(bg_path, QBrush(bg_c))
        if pct > 0:
            fw = (w - 2) * pct / 100.0
            fill_path = QPainterPath()
            fill_path.addRoundedRect(
                QRectF(x + 1, y + 1, max(fw, r * 2 - 2), h - 2),
                r - 1, r - 1
            )
            grad = QLinearGradient(x, 0, x + fw, 0)
            c1 = QColor(fill_c)
            c1.setAlpha(220)
            c2 = QColor(fill_c)
            c2.setAlpha(255)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            p.fillPath(fill_path, QBrush(grad))


# =============================================================================
# CalendarCardWidget
# =============================================================================

class CalendarCardWidget(CardBase):
    """月历卡片 v0.4: 集成精简天气 + token 余量"""
    card_id = 'calendar_card'
    card_name = '📅 月历'
    card_icon = '📅'
    default_size = (380, 840)  # 20+45+31+35+263+115+320+20=840 (含音乐区域)
    update_interval_ms = 60000

    def __init__(self, config: Optional[Dict] = None,
                 parent: Optional[QWidget] = None) -> None:
        # 路径 & 事件存储
        events_path = Path(_ROOT) / 'cache' / 'calendar_events.json'
        self.store = CalendarEventStore(events_path)

        self._upcoming = []
        self._selected_info = {}

        # 数据源 dataclass 实例
        self._weather = WeatherData()
        self._token = TokenUsage()

        # 服务实例
        self._weather_svc = WeatherService(widget=None, interval_ms=1800000)
        self._token_svc = TokenService(mmx_path='mmx.cmd', timeout=10)
        self._weather_svc.data_ready.connect(self._on_weather_ready)

        super().__init__(config=config, parent=parent)

    def init_ui(self) -> None:
        self.setMinimumSize(380, 300)
        self.setMaximumHeight(900)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 20)  # 上下20px边距
        root.setSpacing(0)

        # === 天气条 30px 双行 ===
        self._weather_strip = QWidget()
        self._weather_strip.setFixedHeight(45)

        ws_main = QHBoxLayout(self._weather_strip)
        ws_main.setContentsMargins(10, 0, 10, 0)
        ws_main.setSpacing(0)

        # 左: 城市 + 天气(双行)
        ws_left = QVBoxLayout()
        ws_left.setSpacing(4)
        ws_left.setContentsMargins(0, 2, 0, 2)

        self.weather_city_lbl = QLabel('📍--')
        self.weather_city_lbl.setObjectName('cal_w_city')
        ws_left.addWidget(self.weather_city_lbl)

        self.weather_text_lbl = QLabel('--')
        self.weather_text_lbl.setObjectName('cal_w_text')
        ws_left.addWidget(self.weather_text_lbl)

        ws_main.addLayout(ws_left)

        ws_main.addStretch()

        # 中: 图标 + 温度(居中)
        ws_center = QHBoxLayout()
        ws_center.setSpacing(6)
        ws_center.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.weather_icon_lbl = QLabel('🌤️')
        self.weather_icon_lbl.setObjectName('cal_w_icon')
        self.weather_icon_lbl.setFixedWidth(40)
        ws_center.addWidget(self.weather_icon_lbl)

        self.weather_temp_lbl = QLabel('--°')
        self.weather_temp_lbl.setObjectName('cal_w_temp')
        ws_center.addWidget(self.weather_temp_lbl)

        ws_main.addLayout(ws_center)

        ws_main.addStretch()

        # 右: 日期 + 农历(双行)
        ws_right = QVBoxLayout()
        ws_right.setSpacing(4)
        ws_right.setContentsMargins(0, 2, 0, 2)
        ws_right.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.weather_date_lbl = QLabel('--')
        self.weather_date_lbl.setObjectName('cal_w_date')
        self.weather_date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        ws_right.addWidget(self.weather_date_lbl)

        self.weather_lunar_lbl = QLabel('--')
        self.weather_lunar_lbl.setObjectName('cal_w_lunar')
        self.weather_lunar_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        ws_right.addWidget(self.weather_lunar_lbl)

        ws_main.addLayout(ws_right)

        root.addWidget(self._weather_strip)

        root.addWidget(self._hline(top=20, bottom=10))  # 月历上方: 上20下10

        # === 月历头 35px ===
        self._header = QWidget()
        self._header.setFixedHeight(35)
        header_lay = QHBoxLayout(self._header)
        header_lay.setContentsMargins(14, 4, 10, 4)
        header_lay.setSpacing(6)

        self.title_label = QLabel('📅 月历')
        self.title_label.setObjectName('cal_title')
        header_lay.addWidget(self.title_label)
        header_lay.addStretch()

        self.prev_btn = QPushButton('‹')
        self.prev_btn.setObjectName('cal_prev')
        self.prev_btn.setFixedSize(20, 18)

        self.next_btn = QPushButton('›')
        self.next_btn.setObjectName('cal_next')
        self.next_btn.setFixedSize(20, 18)

        self.today_btn = QPushButton('今')
        self.today_btn.setObjectName('cal_today')
        self.today_btn.setFixedSize(20, 18)

        header_lay.addWidget(self.prev_btn)
        header_lay.addWidget(self.today_btn)
        header_lay.addWidget(self.next_btn)

        root.addWidget(self._header)

        # === 月历 ===
        self.month_view = MonthView(self)
        root.addWidget(self.month_view)

        # === Token 区域 ===
        self._token_area = TokenAreaWidget(card=self)
        self._token_area.setFixedHeight(115)  # 分割线17+标题26+5h进度34+本周进度34+余量
        root.addWidget(self._token_area)

        # === 音乐区域 (嵌入月历底部) ===
        from .music_area import MusicAreaWidget
        self._music_area = MusicAreaWidget()
        self._music_area.setFixedHeight(320)
        root.addWidget(self._music_area)

        # 信号
        self.prev_btn.clicked.connect(self.month_view.go_prev_month)
        self.next_btn.clicked.connect(self.month_view.go_next_month)
        self.today_btn.clicked.connect(self._on_today_clicked)
        self.month_view.month_changed.connect(self._on_month_changed)
        self.month_view.day_clicked.connect(self._on_day_clicked)

        # 主题
        ThemeManager.instance().subscribe(lambda name: self._on_theme_changed(name))
        self._apply_theme()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def _hline(self, top=20, bottom=20) -> QWidget:
        """分割线: 1px 线 + 上下留白"""
        h = top + 1 + bottom
        wrapper = QWidget()
        wrapper.setFixedHeight(h)
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addSpacing(top)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName('cal_hline')
        line.setFixedHeight(1)
        lay.addWidget(line)
        lay.addSpacing(bottom)
        return wrapper

    def update_data(self) -> None:
        self._upcoming = get_upcoming_holidays(3)

    def start_data_sources(self) -> None:
        try:
            self._weather_svc.start()
        except Exception as e:
            _LOG.warning(f'启动天气服务失败: {e}')

        # Token 1 分钟刷新
        self._token_timer = QTimer(self)
        self._token_timer.setInterval(60000)
        self._token_timer.timeout.connect(self._refresh_token)
        self._token_timer.start()
        self._refresh_token()

    def _on_weather_ready(self, data: WeatherData) -> None:
        self._weather = data
        self._refresh_weather_strip()

    def _refresh_token(self) -> None:
        try:
            self._token = self._token_svc.fetch()
        except Exception as e:
            _LOG.debug(f'token 采集失败: {e}')
            self._token = self._token_svc.fetch_mock()
        self._token_area.update()

    def _refresh_weather_strip(self) -> None:
        d = self._weather
        sel = self.month_view.selected_date() or date.today()
        weekday_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][sel.weekday()]
        lunar_text = get_lunar_text(sel)
        ganzhi = get_ganzhi_year(sel)
        shengxiao = get_shengxiao(sel)

        if d and d.success:
            self.weather_city_lbl.setText(f'📍{d.city}')
            self.weather_icon_lbl.setText(d.now_icon or '🌤️')
            self.weather_temp_lbl.setText(f'{d.now_temp}°')
            self.weather_text_lbl.setText(d.now_text or '--')
        else:
            self.weather_city_lbl.setText('📍--')
            self.weather_icon_lbl.setText('🌤️')
            self.weather_temp_lbl.setText('--°')
            self.weather_text_lbl.setText('--')

        self.weather_date_lbl.setText(f'{sel.month}月{sel.day}日 {weekday_cn}')
        self.weather_lunar_lbl.setText(lunar_text)

    def _on_today_clicked(self) -> None:
        self.month_view.go_today()

    def _on_month_changed(self, year: int, month: int) -> None:
        self.title_label.setText(f'📅 {year}年{month}月')

    def _on_day_clicked(self, d: date) -> None:
        pass

    def _on_theme_changed(self, _name: str) -> None:
        self._apply_theme()
        self.update()

    def _apply_theme(self) -> None:
        tm = ThemeManager.instance()
        d = tm.current()

        bg = _to_color(d.get('background', '#1a1a2e'))
        bg_end = _to_color(d.get('background_gradient_end', bg))
        border = _to_color(d.get('border', '#4a7c9e'))
        text_p = _to_color(d.get('text_primary', '#e0e0ff'))
        text_s = _to_color(d.get('text_secondary', '#a0aec0'))
        accent = _to_color(d.get('accent', '#f6ad55'))
        accent_text = _to_color(d.get('accent_text', accent.name()))
        radius = int(d.get('corner_radius', 16))

        if isinstance(d.get('fonts'), dict):
            family = d.get('fonts', {}).get('family', 'Microsoft YaHei UI')
        else:
            family = 'Microsoft YaHei UI'
        if isinstance(d.get('fonts'), dict):
            title_size = d.get('fonts', {}).get('sizes', {}).get('title', 16)
        else:
            title_size = 16
        if isinstance(d.get('fonts'), dict):
            body_size = d.get('fonts', {}).get('sizes', {}).get('body', 12)
        else:
            body_size = 12
        if isinstance(d.get('fonts'), dict):
            cap_size = d.get('fonts', {}).get('sizes', {}).get('caption', 9)
        else:
            cap_size = 9

        css = '\n'.join([
            f'            QWidget {{',
            f'                color: {text_p.name()};',
            f'                font-family: "{family}";',
            f'            }}',
            f'            QLabel#cal_title {{',
            f'                color: {text_p.name()};',
            f'                font-size: {title_size}px;',
            f'                font-weight: bold;',
            f'            }}',
            f'            QLabel#cal_w_icon {{',
            f'                font-size: 28px;',
            f'            }}',
            f'            QLabel#cal_w_temp {{',
            f'                color: {text_p.name()};',
            f'                font-size: 24px;',
            f'                font-weight: bold;',
            f'            }}',
            f'            QLabel#cal_w_city {{',
            f'                color: {text_s.name()};',
            f'                font-size: 13px;',
            f'            }}',
            f'            QLabel#cal_w_text {{',
            f'                color: {accent_text.name()};',
            f'                font-size: 13px;',
            f'            }}',
            f'            QLabel#cal_w_date {{',
            f'                color: {text_s.name()};',
            f'                font-size: 13px;',
            f'            }}',
            f'            QLabel#cal_w_lunar {{',
            f'                color: {text_s.name()};',
            f'                font-size: 13px;',
            f'            }}',
            f'            QLabel#cal_detail_date {{',
            f'                color: {text_p.name()};',
            f'                font-size: {title_size - 2}px;',
            f'                font-weight: bold;',
            f'            }}',
            f'            QLabel#cal_detail_lunar {{',
            f'                color: {text_s.name()};',
            f'                font-size: {body_size - 1}px;',
            f'            }}',
            f'            QLabel#cal_detail_fest {{',
            f'                color: {accent_text.name()};',
            f'                font-size: {body_size - 1}px;',
            f'            }}',
            f'            QLabel#cal_detail_events {{',
            f'                color: {text_p.name()};',
            f'                font-size: {body_size - 1}px;',
            f'                padding: 4px 0 2px 0;',
            f'                background: transparent;',
            f'            }}',
            f'            QLabel#cal_token_title {{',
            f'                color: {text_p.name()};',
            f'                font-size: {body_size + 1}px;',
            f'                font-weight: bold;',
            f'            }}',
            f'            QLabel#cal_token_5h_title, QLabel#cal_token_week_title {{',
            f'                color: {text_s.name()};',
            f'                font-size: {cap_size + 1}px;',
            f'            }}',
            f'            QFrame#cal_hline {{',
            f'                background: {border.name()};',
            f'                border: none;',
            f'            }}',
            f'            QPushButton#cal_prev, QPushButton#cal_next, QPushButton#cal_today {{',
            f'                background: {border.name()};',
            f'                color: {bg.name()};',
            f'                border: none;',
            f'                border-radius: 6px;',
            f'                font-weight: bold;',
            f'                font-size: 14px;',
            f'            }}',
            f'            QPushButton#cal_prev:hover, QPushButton#cal_next:hover, QPushButton#cal_today:hover {{',
            f'                background: {accent.name()};',
            f'                color: {bg.name()};',
            f'            }}',
            f'            QPushButton#cal_event_add {{',
            f'                background: {accent.name()};  # 按钮仍用 accent 紫',
            f'                color: {bg.name()};',
            f'                border: none;',
            f'                border-radius: 6px;',
            f'                font-weight: bold;',
            f'                font-size: 16px;',
            f'            }}',
            f'            QLineEdit#cal_event_input {{',
            f'                background: rgba(0, 0, 0, 0.25);',
            f'                color: {text_p.name()};',
            f'                border: 1px solid {border.name()};',
            f'                border-radius: 6px;',
            f'                padding: 4px 8px;',
            f'                font-size: {body_size - 1}px;',
            f'            }}',
            f'            QLineEdit#cal_event_input:focus {{',
            f'                border: 1px solid {accent.name()};',
            f'            }}',
        ])

        self.setStyleSheet(css)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = ThemeManager.instance().current()

        bg = _to_color(d.get('background', '#1a1a2e'))
        bg_end_src = d.get('background_gradient_end', '#0F1632')
        if isinstance(bg_end_src, QColor):
            bg_end = QColor(bg_end_src)
        else:
            bg_end = _to_color(bg_end_src)
        border = _to_color(d.get('border', '#4a7c9e'))
        radius = int(d.get('corner_radius', 16))

        # frosted glass: c1 (top) alpha 170, c2 (bottom) alpha 210
        c1 = QColor(bg)
        c1.setAlpha(170)
        c2 = QColor(bg_end)
        c2.setAlpha(210)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)

        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1),
                              radius, radius)
        painter.fillPath(path, QBrush(grad))

        # 顶部高光
        highlight = QLinearGradient(0, 0, 0, 60)
        h_c1 = QColor(255, 255, 255, 28)
        h_c2 = QColor(255, 255, 255, 0)
        highlight.setColorAt(0.0, h_c1)
        highlight.setColorAt(1.0, h_c2)
        painter.fillPath(path, QBrush(highlight))

        # 双层边框
        painter.setPen(QPen(QColor(border.red(), border.green(), border.blue(), 70), 1))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        inner = QPainterPath()
        inner.addRoundedRect(QRectF(1.5, 1.5, self.width() - 3, self.height() - 3),
                              radius - 1, radius - 1)
        painter.drawPath(inner)

        painter.end()
