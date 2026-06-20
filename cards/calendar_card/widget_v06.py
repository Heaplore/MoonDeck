"""
CalendarCardWidget - 月历卡片 v0.6 (集成天气+Token+音乐)

v0.6 (2026-06-17 音乐集成到月历):
- 音乐卡片集成到月历底部
- 月历卡片整体高度自适应
- 天气、月历、Token 布局样式严格不变

布局(自上而下):
  ┌─────────────────────────────────────┐
  │ [天气条 45px]                        │  45
  │ [分割线 1px]                         │  1
  │ [月历头 35px]                        │  35
  │ [月历视图]                           │  variable
  │ [分割线 1px]                         │  1
  │ [Token 区域 115px]                   │  115
  │ [分割线 1px]                         │  1
  │ [音乐区域 ~180px]                    │  180
  └─────────────────────────────────────┘
  总高度: 自适应 (weather + calendar + token + music)
"""
from __future__ import annotations
import re
import sys
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRect, QRectF, QSize, QTimer, QThread
from PyQt6.QtGui import (QPainter, QColor, QFont, QPen, QBrush,
                          QLinearGradient, QRadialGradient, QPainterPath, QFontMetrics)
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

# 音乐相关导入
from cards.music_card import audio_viz, service as music_service
from cards.music_card.lyrics_loader import LyricLine, get_lyrics

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


def _fmt_time(sec: float) -> str:
    """格式化时间"""
    if not sec or sec <= 0:
        return "--:--"
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}"


# 歌词元数据行过滤
_META_RE = re.compile(
    r"^\s*("
    r"作\s?词|作\s?曲|编\s?曲|制\s?作|出\s?品|统\s?筹|监\s?制|"
    r"混\s?音|母\s?带|吉\s?他|贝\s?斯|鼓\s?手|录\s?音|封\s?面|"
    r"和\s?声|合\s?唱|弦\s?乐|配\s?乐|策\s?划|发\s?行|版\s?权|"
    r"OP|SP|Music|Lyrics|Producer|Composed|Arranged|Lyric|Composer"
    r")\s*[:：]",
    re.IGNORECASE,
)


def _is_meta_line(text: str) -> bool:
    if not text:
        return True
    return bool(_META_RE.match(text.strip()))


def _filter_meta_lines(lines: List[LyricLine]) -> List[LyricLine]:
    return [ln for ln in lines if not _is_meta_line(ln.text)]


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
# MusicAreaWidget — 音乐区域
# =============================================================================

class MusicAreaWidget(QWidget):
    """音乐区域: 集成音乐卡片功能到月历底部"""

    def __init__(self, card, parent=None):
        super().__init__(parent)
        self._card = card
        self._info = None
        self._lyrics: List[LyricLine] = []
        self._lyric_idx: int = -1
        self._num_bars = 27
        self._smooth_levels: List[float] = [0.0] * self._num_bars
        self._tick = 0.0
        self._current_position: float = 0.0
        self._last_smtc_position: float = 0.0
        self._last_smtc_playing: bool = False
        self._last_frame_time: float = 0.0
        self._lyrics_fetch_started: bool = False
        self._last_song_key: str = ""

        # 按钮区域
        self._btn_prev = QRectF()
        self._btn_play = QRectF()
        self._btn_next = QRectF()
        self._hover_btn: str = ""

        # 设置固定宽度，与月历卡对齐
        self.setFixedWidth(380)

        # 启动音频可视化
        audio_viz.start()

        # 动画定时器 (30fps)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start()

        # 数据刷新定时器 (1s)
        self._data_timer = QTimer(self)
        self._data_timer.setInterval(1000)
        self._data_timer.timeout.connect(self._update_data)
        self._data_timer.start()

        self.setMouseTracking(True)

    def _update_data(self) -> None:
        """1s 一次拉数据"""
        self._info = music_service.detect_music_simple()
        if not self._info:
            return
        key = f"{self._info.song_title}|{self._info.song_artist}"
        if key != self._last_song_key and self._info.song_title:
            self._last_song_key = key
            self._lyrics = []
            self._lyric_idx = -1
            self._lyrics_fetch_started = False
            self._current_position = self._info.position_sec
            self._last_smtc_position = self._info.position_sec
            self._load_lyrics_async()
        self.update()

    def _load_lyrics_async(self) -> None:
        if not self._info or not self._info.song_title:
            return
        if self._lyrics_fetch_started:
            return
        self._lyrics_fetch_started = True
        title = self._info.song_title
        artist = self._info.song_artist or ""

        def _fetch():
            try:
                lines = get_lyrics(title, artist)
                lines = _filter_meta_lines(lines)
                self._lyrics = lines
                self._lyric_idx = -1
                _LOG.info(f"歌词加载: {title} - {artist} → {len(lines)} 行")
            except Exception as e:
                _LOG.warning(f"歌词加载失败: {e}")
                self._lyrics = []
            finally:
                self._lyrics_fetch_started = False
                self.update()

        QTimer.singleShot(50, _fetch)

    def _animate(self) -> None:
        """30fps: 插值 position + 频谱 + 歌词行号"""
        self._tick += 0.1

        now = _time.time()
        if self._last_frame_time > 0:
            dt = min(now - self._last_frame_time, 0.5)
        else:
            dt = 0.033
        self._last_frame_time = now

        # 同步 SMTC 元数据
        new_info = music_service.detect_music_simple()
        if new_info:
            self._info = new_info

        # 插值 position
        if self._info:
            smtc_pos = self._info.position_sec
            self._last_smtc_playing = self._info.is_playing

            if self._info.is_playing:
                self._current_position += dt
                if smtc_pos != self._last_smtc_position:
                    diff = smtc_pos - self._current_position
                    if abs(diff) > 2.0:
                        self._current_position = smtc_pos
                    self._last_smtc_position = smtc_pos
                if self._info.duration_sec > 0:
                    self._current_position = min(self._current_position, self._info.duration_sec)
            else:
                if smtc_pos != self._last_smtc_position:
                    self._current_position = smtc_pos
                    self._last_smtc_position = smtc_pos

        # 频谱律动
        if self._info and self._info.is_playing:
            raw = audio_viz.get_levels(self._num_bars)
            for i in range(self._num_bars):
                self._smooth_levels[i] = self._smooth_levels[i] * 0.3 + raw[i] * 0.7
        else:
            for i in range(self._num_bars):
                self._smooth_levels[i] *= 0.85

        # 歌词行号
        if self._lyrics and self._info and self._current_position > 0:
            self._lyric_idx = self._find_lyric_idx(self._current_position)
        self.update()

    def _find_lyric_idx(self, pos_sec: float) -> int:
        idx = -1
        for i, ln in enumerate(self._lyrics):
            if ln.time_sec <= pos_sec:
                idx = i
            else:
                break
        return idx

    def mouseMoveEvent(self, ev) -> None:
        x, y = ev.position().x(), ev.position().y()
        new_hover = ""
        if self._btn_prev.contains(x, y):
            new_hover = "prev"
        elif self._btn_play.contains(x, y):
            new_hover = "play"
        elif self._btn_next.contains(x, y):
            new_hover = "next"
        if new_hover != self._hover_btn:
            self._hover_btn = new_hover
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if new_hover
                else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def mousePressEvent(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = ev.position().x(), ev.position().y()
        if self._btn_prev.contains(x, y):
            music_service.media_prev()
            QTimer.singleShot(300, self._update_data)
        elif self._btn_play.contains(x, y):
            music_service.media_play_pause()
            QTimer.singleShot(300, self._update_data)
        elif self._btn_next.contains(x, y):
            music_service.media_next()
            QTimer.singleShot(300, self._update_data)

    def leaveEvent(self, ev) -> None:
        self._hover_btn = ""
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        d = ThemeManager.instance().current()
        w, h = self.width(), self.height()

        # 主题色
        text_p = _to_color(d.get('text_primary', '#e0e0ff'))
        text_s = _to_color(d.get('text_secondary', '#a0aec0'))
        text_c = _to_color(d.get('text_caption', '#5A6A85'))
        accent = _to_color(d.get('accent', '#9F7CFF'))
        accent_text = _to_color(d.get('accent_text', '#B4C8DC'))
        border = _to_color(d.get('border', '#4a7c9e'))

        if isinstance(d.get('fonts'), dict):
            family = d.get('fonts', {}).get('family', 'Microsoft YaHei UI')
        else:
            family = 'Microsoft YaHei UI'
        if isinstance(d.get('fonts'), dict):
            sizes = d.get('fonts', {}).get('sizes', {})
        else:
            sizes = {}

        margin = 14

        # ── 1. 顶部信息 (播放器 + 歌名 + 歌手) ──
        top_y = 8
        if self._info and self._info.player_name:
            # 播放器名 (左上)
            font_cap = QFont(family, 8)
            p.setFont(font_cap)
            p.setPen(QPen(text_c))
            cap_text = f"{self._info.player_icon}  {self._info.player_name}"
            p.drawText(QPointF(margin, top_y + 10), cap_text)

            # 歌名 (居中)
            if self._info.song_title:
                font_song = QFont(family, sizes.get("title", 13))
                font_song.setBold(True)
                p.setFont(font_song)
                p.setPen(QPen(accent_text))
                song = self._info.song_title
                fm = QFontMetrics(font_song)
                max_w = w - margin * 2
                if fm.horizontalAdvance(song) > max_w:
                    song = fm.elidedText(song, Qt.TextElideMode.ElideRight, max_w)
                tw = fm.horizontalAdvance(song)
                p.drawText(QPointF((w - tw) / 2, top_y + 28), song)

            # 歌手 (右对齐)
            if self._info.song_artist:
                font_art = QFont(family, 9)
                p.setFont(font_art)
                p.setPen(QPen(text_s))
                artist = self._info.song_artist
                fm_a = QFontMetrics(font_art)
                max_w = w - margin * 2
                if fm_a.horizontalAdvance(artist) > max_w:
                    artist = fm_a.elidedText(artist, Qt.TextElideMode.ElideRight, max_w)
                tw_a = fm_a.horizontalAdvance(artist)
                p.drawText(QPointF(w - margin - tw_a, top_y + 44), artist)
        else:
            font_empty = QFont(family, 12)
            p.setFont(font_empty)
            p.setPen(QPen(text_s))
            p.drawText(QPointF(margin, top_y + 28), "🎵 未在播放")

        # ── 2. 歌词区 ──
        lyric_y = 58
        if self._lyrics and self._info and self._info.is_playing:
            font_lyric = QFont(family, 9)
            font_lyric_cur = QFont(family, 10)
            font_lyric_cur.setBold(True)
            fm_cur = QFontMetrics(font_lyric_cur)
            fm_norm = QFontMetrics(font_lyric)
            max_w = w - margin * 2

            for di in range(-1, 2):
                idx = self._lyric_idx + di
                if idx < 0 or idx >= len(self._lyrics):
                    continue
                ln = self._lyrics[idx]
                text = ln.text
                is_cur = (di == 0)
                f = font_lyric_cur if is_cur else font_lyric
                fm = fm_cur if is_cur else fm_norm
                if fm.horizontalAdvance(text) > max_w:
                    text = fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w)
                alpha = 255 if is_cur else 80
                color = QColor(accent if is_cur else text_s)
                color.setAlpha(alpha)
                p.setFont(f)
                p.setPen(QPen(color))
                y_off = lyric_y + (di * 14) if di != 0 else lyric_y
                tw = fm.horizontalAdvance(text)
                x = (w - tw) / 2 if is_cur else margin
                p.drawText(QPointF(x, y_off + 10), text)
        elif self._lyrics:
            font_lyric = QFont(family, 10)
            p.setFont(font_lyric)
            p.setPen(QPen(text_s))
            text = self._lyrics[0].text if self._lyrics else ""
            if text:
                fm = QFontMetrics(font_lyric)
                max_w = w - margin * 2
                if fm.horizontalAdvance(text) > max_w:
                    text = fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w)
                tw = fm.horizontalAdvance(text)
                p.drawText(QPointF((w - tw) / 2, lyric_y + 10), text)
        else:
            font_lyric = QFont(family, 9)
            p.setFont(font_lyric)
            p.setPen(QPen(text_c))
            if self._info and self._info.player_name:
                if self._lyrics_fetch_started:
                    p.drawText(QPointF(margin, lyric_y + 10), "♪ 加载歌词中...")
                else:
                    p.drawText(QPointF(margin, lyric_y + 10), "♪ 暂无歌词")

        # ── 3. 律动条 ──
        viz_top = 95
        viz_bottom = 165
        viz_h = viz_bottom - viz_top

        bar_w = 4
        bar_gap = max(2, int((w - margin * 2 - self._num_bars * bar_w) / max(1, self._num_bars - 1)))
        total_w = self._num_bars * bar_w + (self._num_bars - 1) * bar_gap
        start_x = (w - total_w) / 2
        peaks = audio_viz.get_peaks()

        for i in range(self._num_bars):
            ratio = i / max(1, self._num_bars - 1)
            if ratio < 0.5:
                t = ratio / 0.5
                r = int(0x9F + (0xB8 - 0x9F) * t)
                g = int(0x7C + (0x9F - 0x7C) * t)
                b = 0xFF
            else:
                t = (ratio - 0.5) / 0.5
                r = int(0xB8 + (0xB4 - 0xB8) * t)
                g = int(0x9F + (0xC8 - 0x9F) * t)
                b = int(0xFF + (0xDC - 0xFF) * t)

            level = float(self._smooth_levels[i]) if i < len(self._smooth_levels) else 0.0
            bh = max(2, viz_h * 0.85 * level)
            bx = start_x + i * (bar_w + bar_gap)
            by = viz_bottom - bh

            bar_c = QColor(r, g, b, int(80 + 175 * level))
            p.fillRect(int(bx), int(by), bar_w, int(bh), bar_c)

            pk = float(peaks[i]) if i < len(peaks) else 0.0
            if pk > 0.02:
                ph = max(2, viz_h * 0.85 * pk)
                py = viz_bottom - ph
                p.fillRect(int(bx), int(py), bar_w, 2, QColor(0xE8, 0xF4, 0xF8, 200))

        # ── 4. 进度条 ──
        prog_y = viz_bottom + 4
        prog_h = 3
        prog_w = w - margin * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 30)))
        p.drawRoundedRect(QRectF(margin, prog_y, prog_w, prog_h), 1.5, 1.5)
        if self._info and self._info.duration_sec > 0:
            pct = max(0.0, min(1.0, self._current_position / self._info.duration_sec))
            fill_w = prog_w * pct
            prog_grad = QLinearGradient(margin, 0, margin + prog_w, 0)
            prog_grad.setColorAt(0.0, QColor(0x9F, 0x7C, 0xFF, 220))
            prog_grad.setColorAt(1.0, QColor(0xB4, 0xC8, 0xDC, 220))
            p.setBrush(QBrush(prog_grad))
            p.drawRoundedRect(QRectF(margin, prog_y, max(fill_w, 3), prog_h), 1.5, 1.5)
        # 时间文字
        font_time = QFont(family, 8)
        p.setFont(font_time)
        p.setPen(QPen(text_c))
        if self._info:
            time_text = f"{_fmt_time(self._current_position)} / {_fmt_time(self._info.duration_sec)}"
            p.drawText(QPointF(margin, prog_y + 12), time_text)

        # ── 5. 控制按钮 ──
        if self._info and self._info.player_name:
            btn_y = h - 32
            btn_h = 26
            btn_w = 30
            center_x = w / 2
            gap = 10

            self._btn_prev = QRectF(center_x - btn_w * 1.5 - gap, btn_y, btn_w, btn_h)
            self._btn_play = QRectF(center_x - btn_w / 2, btn_y - 1, btn_w, btn_h + 2)
            self._btn_next = QRectF(center_x + btn_w / 2 + gap, btn_y, btn_w, btn_h)

            buttons = [
                (self._btn_prev, "prev"),
                (self._btn_play, "pause" if self._info.is_playing else "play"),
                (self._btn_next, "next"),
            ]

            for btn_rect, kind in buttons:
                cx = btn_rect.x() + btn_rect.width() / 2
                cy = btn_rect.y() + btn_rect.height() / 2
                is_main = (kind == "pause" or kind == "play")
                is_hover = (self._hover_btn == kind)

                if is_main:
                    play_grad = QLinearGradient(btn_rect.x(), btn_rect.y(),
                                                btn_rect.x() + btn_rect.width(),
                                                btn_rect.y() + btn_rect.height())
                    if self._info.is_playing:
                        play_grad.setColorAt(0.0, QColor(0x9F, 0x7C, 0xFF, 200))
                        play_grad.setColorAt(1.0, QColor(0xB8, 0x9F, 0xFF, 200))
                    else:
                        play_grad.setColorAt(0.0, QColor(0x9F, 0x7C, 0xFF, 130))
                        play_grad.setColorAt(1.0, QColor(0xB8, 0x9F, 0xFF, 130))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(play_grad))
                    p.drawRoundedRect(btn_rect, btn_rect.height() / 2, btn_rect.height() / 2)
                    if self._info.is_playing:
                        import math
                        pulse = abs(math.sin(self._tick)) * 0.5 + 0.5
                        glow_c = QColor(0x9F, 0x7C, 0xFF, int(60 * pulse))
                        p.setPen(QPen(glow_c, 2))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(QRectF(btn_rect.x() - 2, btn_rect.y() - 2,
                                                 btn_rect.width() + 4, btn_rect.height() + 4),
                                          btn_rect.height() / 2 + 2, btn_rect.height() / 2 + 2)
                else:
                    bg_alpha = 50 if is_hover else 25
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(255, 255, 255, bg_alpha)))
                    p.drawRoundedRect(btn_rect, btn_rect.height() / 2, btn_rect.height() / 2)
                    if is_hover:
                        p.setPen(QPen(QColor(0xB4, 0xC8, 0xDC, 120), 1))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(btn_rect, btn_rect.height() / 2, btn_rect.height() / 2)

                # 图标
                icon_color = QColor(255, 255, 255) if is_main else QColor(text_p)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(icon_color))

                if kind == "prev":
                    tri = QPainterPath()
                    tri.moveTo(cx + 4, cy - 4)
                    tri.lineTo(cx - 1, cy)
                    tri.lineTo(cx + 4, cy + 4)
                    tri.closeSubpath()
                    p.drawPath(tri)
                    tri2 = QPainterPath()
                    tri2.moveTo(cx + 9, cy - 4)
                    tri2.lineTo(cx + 4, cy)
                    tri2.lineTo(cx + 9, cy + 4)
                    tri2.closeSubpath()
                    p.drawPath(tri2)
                elif kind == "pause":
                    p.drawRoundedRect(QRectF(cx - 4, cy - 4, 3, 8), 1.5, 1.5)
                    p.drawRoundedRect(QRectF(cx + 1, cy - 4, 3, 8), 1.5, 1.5)
                elif kind == "play":
                    tri = QPainterPath()
                    tri.moveTo(cx - 3, cy - 5)
                    tri.lineTo(cx - 3, cy + 5)
                    tri.lineTo(cx + 6, cy)
                    tri.closeSubpath()
                    p.drawPath(tri)
                elif kind == "next":
                    tri = QPainterPath()
                    tri.moveTo(cx - 9, cy - 4)
                    tri.lineTo(cx - 4, cy)
                    tri.lineTo(cx - 9, cy + 4)
                    tri.closeSubpath()
                    p.drawPath(tri)
                    tri2 = QPainterPath()
                    tri2.moveTo(cx - 4, cy - 4)
                    tri2.lineTo(cx + 1, cy)
                    tri2.lineTo(cx - 4, cy + 4)
                    tri2.closeSubpath()
                    p.drawPath(tri2)

        p.end()


# =============================================================================
# CalendarCardWidget
# =============================================================================

class CalendarCardWidget(CardBase):
    """月历卡片 v0.6: 集成天气 + Token + 音乐"""

    card_id = 'calendar_card'
    card_name = '📅 月历'
    card_icon = '📅'
    default_size = (380, 820)  # 自适应高度
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

    def sizeHint(self):
        """返回建议尺寸: 宽度 380, 高度自适应"""
        return QSize(380, 820)

    def init_ui(self) -> None:
        self.setMinimumSize(380, 820)
        self.setMaximumHeight(1200)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 20)  # 上下20px边距
        root.setSpacing(0)

        # === 天气条 45px ===
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
        self._token_area.setFixedHeight(115)
        root.addWidget(self._token_area)

        # === 音乐区域 ===
        self._music_area = MusicAreaWidget(card=self)
        self._music_area.setFixedHeight(180)
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
