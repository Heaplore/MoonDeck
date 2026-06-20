"""MusicAreaWidget - 嵌入月历底部的音乐区域

独立自绘 QWidget, 从 cards.music_card.service / audio_viz 拉数据。
复用 music_card widget.py 的绘制逻辑, 但去掉背景/边框 (继承父级)。
"""
from __future__ import annotations

import logging
import math
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush,
    QLinearGradient, QRadialGradient, QPainterPath, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget, QSizePolicy

_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.theme import ThemeManager
from cards.music_card import audio_viz, service
from cards.music_card.lyrics_loader import LyricLine, get_lyrics
from cards.music_card.audio_viz import set_now_playing

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 歌词元数据行过滤 (同 music_card)
# ---------------------------------------------------------------------------
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


def _fmt_time(sec: float) -> str:
    if not sec or sec <= 0:
        return "--:--"
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}"


def _to_color(v) -> QColor:
    if isinstance(v, QColor):
        return v
    if v is None:
        return QColor()
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("#") and len(s) in (7, 9):
            try:
                return QColor(s)
            except Exception:
                return QColor()
        m = re.match(
            r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", s
        )
        if m:
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            a = int(float(m.group(4) or 1) * 255)
            return QColor(r, g, b, a)
        try:
            return QColor(s)
        except Exception:
            return QColor()
    return QColor()


# ---------------------------------------------------------------------------
# 控制按钮
# ---------------------------------------------------------------------------
@dataclass
class _Btn:
    x: float
    y: float
    w: float
    h: float
    kind: str
    action: callable

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


# ---------------------------------------------------------------------------
# MusicAreaWidget
# ---------------------------------------------------------------------------
class MusicAreaWidget(QWidget):
    """月历底部音乐区域 - 自绘, 无背景 (继承月历风格)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setMaximumHeight(340)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(320)

        self._info = None
        self._lyrics: List[LyricLine] = []
        self._lyric_idx: int = -1
        self._num_bars = 27
        self._smooth_levels: List[float] = [0.0] * self._num_bars
        self._tick = 0.0
        self._hover_btn: int = -1
        self._buttons: List[_Btn] = []
        self._last_song_key: str = ""
        self._lyrics_fetch_started: bool = False
        # 插值 position
        self._current_position: float = 0.0
        self._last_smtc_position: float = 0.0
        self._last_smtc_playing: bool = False
        self._last_frame_time: float = 0.0

        # 拖动进度条状态
        self._dragging: bool = False
        self._drag_position: float = 0.0
        self._progress_rect_y: float = 0.0
        self._progress_rect_h: float = 2.0
        self._seek_cooldown: float = 0.0  # seek 后冷却期 (防止 SMTC 覆盖)

        # 启动数据源
        audio_viz.start()

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start()

        self.setMouseTracking(True)

    def _animate(self) -> None:
        import time as _time
        self._tick += 0.1
        now = _time.time()
        if self._last_frame_time > 0:
            dt = min(now - self._last_frame_time, 0.5)
        else:
            dt = 0.033
        self._last_frame_time = now

        new_info = service.detect_music_simple()
        if new_info:
            self._info = new_info

        if self._info:
            smtc_pos = self._info.position_sec
            self._last_smtc_playing = self._info.is_playing

            # seek 冷却期: 不让 SMTC 覆盖 seek 结果
            if self._seek_cooldown > 0:
                self._seek_cooldown -= dt
                if smtc_pos != self._last_smtc_position:
                    self._last_smtc_position = smtc_pos
            elif self._info.is_playing:
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

        # 频谱
        if self._info and self._info.is_playing:
            raw = audio_viz.get_levels(self._num_bars)
            for i in range(self._num_bars):
                self._smooth_levels[i] = self._smooth_levels[i] * 0.3 + raw[i] * 0.7
        else:
            for i in range(self._num_bars):
                self._smooth_levels[i] *= 0.85

        # 歌词
        if self._lyrics and self._info and self._current_position > 0:
            self._lyric_idx = self._find_lyric_idx(self._current_position)

        # 歌曲切换时加载歌词
        if self._info and self._info.song_title:
            key = f"{self._info.song_title}|{self._info.song_artist}"
            if key != self._last_song_key:
                self._last_song_key = key
                self._lyrics = []
                self._lyric_idx = -1
                self._lyrics_fetch_started = False
                self._load_lyrics_async()

        # 共享当前播放状态给桌面动效
        try:
            set_now_playing(
                lyrics=self._lyrics,
                lyric_idx=self._lyric_idx,
                position_sec=self._current_position,
                duration_sec=self._info.duration_sec if self._info else 0.0,
                is_playing=self._info.is_playing if self._info else False,
                song_title=self._info.song_title if self._info else "",
                song_artist=self._info.song_artist if self._info else "",
            )
        except Exception:
            pass

        self.update()

    def _find_lyric_idx(self, pos_sec: float) -> int:
        idx = -1
        for i, ln in enumerate(self._lyrics):
            if ln.time_sec <= pos_sec:
                idx = i
            else:
                break
        return idx

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
            except Exception:
                self._lyrics = []
            finally:
                self._lyrics_fetch_started = False
                self.update()

        QTimer.singleShot(50, _fetch)

    # ── 进度条区域计算 ──
    def _progress_rect(self) -> tuple:
        """返回进度条的 (x, y, w, h)"""
        margin = 14
        w = self.width()
        h = self.height()
        viz_bottom = h - 56
        prog_y = viz_bottom + 4
        prog_w = w - margin * 2
        return (margin, prog_y, prog_w, 3)

    def _is_on_progress(self, x: float, y: float) -> bool:
        """判断是否在进度条区域 (扩展点击范围)"""
        px, py, pw, ph = self._progress_rect()
        return px <= x <= px + pw and py - 10 <= y <= py + ph + 10

    def _x_to_position(self, x: float) -> float:
        """把 x 坐标转为 position (秒)"""
        px, py, pw, ph = self._progress_rect()
        pct = max(0.0, min(1.0, (x - px) / pw))
        if self._info and self._info.duration_sec > 0:
            return pct * self._info.duration_sec
        return 0.0

    # ── 鼠标事件 ──
    def mouseMoveEvent(self, ev) -> None:
        x, y = ev.position().x(), ev.position().y()

        # 拖动中
        if self._dragging:
            self._drag_position = self._x_to_position(x)
            self.update()
            return

        # hover 按钮
        new_hover = -1
        for i, btn in enumerate(self._buttons):
            if btn.contains(x, y):
                new_hover = i
                break
        if new_hover != self._hover_btn:
            self._hover_btn = new_hover
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if new_hover >= 0
                else Qt.CursorShape.ArrowCursor
            )
            self.update()

        # hover 进度条
        if not self._dragging and self._is_on_progress(x, y):
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = ev.position().x(), ev.position().y()

        # 点击进度条 → 开始拖动
        if self._is_on_progress(x, y) and self._info and self._info.duration_sec > 0:
            self._dragging = True
            self._drag_position = self._x_to_position(x)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            return

        # 点击按钮
        for btn in self._buttons:
            if btn.contains(x, y):
                btn.action()
                break

    def mouseReleaseEvent(self, ev) -> None:
        if self._dragging:
            # seek 到拖动位置
            service.media_seek(self._drag_position)
            self._current_position = self._drag_position
            self._last_smtc_position = self._drag_position
            self._seek_cooldown = 2.0  # 2s 冷却期: 不让 SMTC 覆盖
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, ev) -> None:
        self._hover_btn = -1
        if not self._dragging:
            self.update()

    # ── 绘制 (v2: 无封面, 装饰线+渐变歌词+频谱倒影) ──
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        tm = ThemeManager.instance()
        d = tm.current()
        w, h = self.width(), self.height()

        text_p = _to_color(d.get("text_primary", "#E8F4F8"))
        text_s = _to_color(d.get("text_secondary", "#8FA8C0"))
        text_c = _to_color(d.get("text_caption", "#5A6A85"))
        accent_text = _to_color(d.get("accent_text", "#B4C8DC"))
        border = _to_color(d.get("border", "rgba(180, 200, 220, 0.20)"))

        fonts = d.get("fonts", {})
        family = fonts.get("family", "Microsoft YaHei UI") if isinstance(fonts, dict) else "Microsoft YaHei UI"
        margin = 14
        is_playing = self._info and self._info.is_playing

        # ── 1. 冷青分割线 ──
        p.setPen(QPen(QColor(0xB4, 0xC8, 0xDC, 60)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(margin, 4, w - margin, 4)

        # ── 2. 歌名(左) + via(右) ──
        top_y = 16
        full_w = w - margin * 2
        if self._info and self._info.player_name:
            # 歌名 (左)
            font_song = QFont(family, 13)
            font_song.setBold(True)
            p.setFont(font_song)
            p.setPen(QPen(text_p))
            song = self._info.song_title or ""
            fm_song = QFontMetrics(font_song)
            # 给 via 留 80px
            song_w = full_w - 80
            if fm_song.horizontalAdvance(song) > song_w:
                song = fm_song.elidedText(song, Qt.TextElideMode.ElideRight, song_w)
            p.drawText(QPointF(margin, top_y + 15), song)

            # via (右)
            if self._info.player_name:
                font_via = QFont(family, 8)
                p.setFont(font_via)
                p.setPen(QPen(text_c))
                via = self._info.player_name
                fm_via = QFontMetrics(font_via)
                via_tw = fm_via.horizontalAdvance(via)
                p.drawText(QPointF(w - margin - via_tw, top_y + 15), via)

            # 歌手 (歌名下方)
            if self._info.song_artist:
                font_art = QFont(family, 9)
                p.setFont(font_art)
                p.setPen(QPen(text_s))
                artist = self._info.song_artist
                fm_a = QFontMetrics(font_art)
                if fm_a.horizontalAdvance(artist) > full_w:
                    artist = fm_a.elidedText(artist, Qt.TextElideMode.ElideRight, full_w)
                p.drawText(QPointF(margin, top_y + 32), artist)

        # ── 3. 装饰分割点 ──
        dot_y = top_y + 44
        dot_color = QColor(0xB4, 0xC8, 0xDC, 50)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(dot_color))
        for i in range(7):
            dx = margin + 20 + i * ((full_w - 40) / 6)
            p.drawEllipse(QPointF(dx, dot_y), 1.5, 1.5)

        # ── 4. 歌词区 (全宽居中, 上下渐变褪色) ──
        lyric_y = dot_y + 12
        if self._lyrics and self._info and self._info.is_playing:
            font_lyric_cur = QFont(family, 12)
            font_lyric_cur.setBold(True)
            font_lyric = QFont(family, 10)
            fm_cur = QFontMetrics(font_lyric_cur)
            fm_norm = QFontMetrics(font_lyric)

            for di in range(-1, 2):
                idx = self._lyric_idx + di
                if idx < 0 or idx >= len(self._lyrics):
                    continue
                ln = self._lyrics[idx]
                text = ln.text
                is_cur = (di == 0)
                f = font_lyric_cur if is_cur else font_lyric
                fm = fm_cur if is_cur else fm_norm
                if fm.horizontalAdvance(text) > full_w:
                    text = fm.elidedText(text, Qt.TextElideMode.ElideRight, full_w)
                tw = fm.horizontalAdvance(text)
                x = (w - tw) / 2
                y_off = lyric_y + (di * 20) if di != 0 else lyric_y

                if is_cur:
                    # 当前行: 冷青 + 两侧装饰短线
                    color = QColor(accent_text)
                    color.setAlpha(255)
                    p.setFont(f)
                    p.setPen(QPen(color))
                    p.drawText(QPointF(x, y_off + 14), text)
                    # 左装饰线
                    line_y = y_off + 10
                    line_w = 16
                    p.setPen(QPen(QColor(0xB4, 0xC8, 0xDC, 120), 1.5))
                    p.drawLine(QPointF(x - line_w - 4, line_y), QPointF(x - 4, line_y))
                    # 右装饰线
                    p.drawLine(QPointF(x + tw + 4, line_y), QPointF(x + tw + line_w + 4, line_y))
                else:
                    # 上下行: 灰色渐变褪色
                    alpha = 80 if di == -1 else 60
                    color = QColor(text_s)
                    color.setAlpha(alpha)
                    p.setFont(f)
                    p.setPen(QPen(color))
                    p.drawText(QPointF(x, y_off + 14), text)
        else:
            font_lyric = QFont(family, 10)
            p.setFont(font_lyric)
            p.setPen(QPen(text_c))
            if self._info and self._info.player_name:
                text = "♪ 暂无歌词"
                fm = QFontMetrics(font_lyric)
                tw = fm.horizontalAdvance(text)
                p.drawText(QPointF((w - tw) / 2, lyric_y + 14), text)

        # ── 5. 频谱律动 (全宽, 冷青渐变 + 倒影) ──
        viz_top = lyric_y + 64
        viz_bottom = h - 56
        viz_h = viz_bottom - viz_top
        if viz_h > 10:
            bar_w = 4
            bar_gap = max(2, int((w - margin * 2 - self._num_bars * bar_w) / max(1, self._num_bars - 1)))
            total_w = self._num_bars * bar_w + (self._num_bars - 1) * bar_gap
            start_x = (w - total_w) / 2

            for i in range(self._num_bars):
                level = float(self._smooth_levels[i]) if i < len(self._smooth_levels) else 0.0
                bh = max(2, viz_h * 0.9 * level)
                bx = start_x + i * (bar_w + bar_gap)
                by = viz_bottom - bh

                # bar: vertical gradient 冷青 → 灰蓝
                if bh > 4:
                    bar_grad = QLinearGradient(0, by, 0, viz_bottom)
                    bar_grad.setColorAt(0.0, QColor(0xE8, 0xF4, 0xF8, int(120 + 135 * level)))
                    bar_grad.setColorAt(0.5, QColor(0xB4, 0xC8, 0xDC, int(120 + 135 * level)))
                    bar_grad.setColorAt(1.0, QColor(0x8F, 0xA8, 0xC0, int(120 + 135 * level)))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(bar_grad))
                    p.drawRect(int(bx), int(by), bar_w, int(bh))
                else:
                    bar_c = QColor(0xB4, 0xC8, 0xDC, int(100 + 155 * level))
                    p.fillRect(int(bx), int(by), bar_w, int(bh), bar_c)

                # 倒影 (alpha 减半, 镜像在下, 渐变透明)
                if bh > 3:
                    # 倒影高度减半 (从 0.35/0.15 -> 0.175/0.075)
                    refl_h = min(bh * 0.175, viz_h * 0.075)
                    refl_grad = QLinearGradient(0, viz_bottom, 0, viz_bottom + refl_h)
                    refl_grad.setColorAt(0.0, QColor(0xB4, 0xC8, 0xDC, int(50 * level)))
                    refl_grad.setColorAt(1.0, QColor(0xB4, 0xC8, 0xDC, 0))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(refl_grad))
                    p.drawRect(int(bx), int(viz_bottom), bar_w, int(refl_h))

        # ── 6. 进度条 ──
        prog_y = h - 50  # 倒影减半 + viz_bottom 上移后, 进度条也上移 12px
        prog_h = 3
        prog_w = w - margin * 2
        # 背景
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 30)))
        p.drawRoundedRect(QRectF(margin, prog_y, prog_w, prog_h), 1.5, 1.5)

        if self._info and self._info.duration_sec > 0:
            pct = max(0.0, min(1.0, self._current_position / self._info.duration_sec))
            fill_w = prog_w * pct
            prog_grad = QLinearGradient(margin, 0, margin + prog_w, 0)
            prog_grad.setColorAt(0.0, QColor(0xE8, 0xF4, 0xF8, 230))
            prog_grad.setColorAt(0.5, QColor(0xB4, 0xC8, 0xDC, 230))
            prog_grad.setColorAt(1.0, QColor(0x8F, 0xA8, 0xC0, 230))
            p.setBrush(QBrush(prog_grad))
            p.drawRoundedRect(QRectF(margin, prog_y, max(fill_w, 3), prog_h), 1.5, 1.5)

            # 拖动时: 竖线 + 小圆点 + 时间
            if self._dragging:
                drag_pct = max(0.0, min(1.0, self._drag_position / self._info.duration_sec))
                drag_x = margin + prog_w * drag_pct
                p.setPen(QPen(QColor(0xB4, 0xC8, 0xDC, 200), 1))
                p.drawLine(QPointF(drag_x, prog_y - 5), QPointF(drag_x, prog_y + prog_h + 5))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(0xE8, 0xF4, 0xF8, 255)))
                p.drawEllipse(QPointF(drag_x, prog_y + prog_h / 2), 4, 4)
                font_td = QFont(family, 8)
                font_td.setBold(True)
                p.setFont(font_td)
                p.setPen(QPen(accent_text))
                drag_text = _fmt_time(self._drag_position)
                fm = QFontMetrics(font_td)
                tw = fm.horizontalAdvance(drag_text)
                tx = max(margin, min(w - margin - tw, drag_x - tw / 2))
                p.drawText(QPointF(tx, prog_y - 12), drag_text)

        # 时间文字 (进度条左下)
        font_time = QFont(family, 7)
        p.setFont(font_time)
        p.setPen(QPen(text_c))
        if self._info:
            pos = self._drag_position if self._dragging else self._current_position
            time_text = f"{_fmt_time(pos)} / {_fmt_time(self._info.duration_sec)}"
            fm = QFontMetrics(font_time)
            tw = fm.horizontalAdvance(time_text)
            p.drawText(QPointF(margin, prog_y + 12), time_text)

        # ── 7. 控制按钮 ──
        if self._info and self._info.player_name:
            btn_y = h - 28
            btn_h = 24
            btn_w = 32
            center_x = w / 2
            gap = 12

            self._buttons = [
                _Btn(center_x - btn_w * 1.5 - gap, btn_y, btn_w, btn_h, "prev", service.media_prev),
                _Btn(center_x - btn_w / 2, btn_y - 1, btn_w, btn_h + 2,
                     "pause" if is_playing else "play", service.media_play_pause),
                _Btn(center_x + btn_w / 2 + gap, btn_y, btn_w, btn_h, "next", service.media_next),
            ]

            for i, btn in enumerate(self._buttons):
                cx = btn.x + btn.w / 2
                cy = btn.y + btn.h / 2
                is_main = (i == 1)
                is_hover = (self._hover_btn == i)

                if is_main:
                    if is_playing:
                        pulse = abs(math.sin(self._tick * 0.5)) * 0.5 + 0.5
                        ca = int(200 + 55 * pulse)
                    else:
                        ca = 180
                    pg = QRadialGradient(QPointF(cx, cy), btn.w / 2)
                    pg.setColorAt(0.0, QColor(0xE8, 0xF4, 0xF8, ca))
                    pg.setColorAt(1.0, QColor(0xB4, 0xC8, 0xDC, ca))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(pg))
                    p.drawEllipse(QPointF(cx, cy), btn.w / 2 - 1, btn.h / 2 - 1)
                    if is_playing:
                        pulse = abs(math.sin(self._tick * 0.5)) * 0.5 + 0.5
                        gc = QColor(0xB4, 0xC8, 0xDC, int(60 * pulse))
                        p.setPen(QPen(gc, 2))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawEllipse(QPointF(cx, cy), btn.w / 2 + 1, btn.h / 2 + 1)
                else:
                    ba = 60 if is_hover else 30
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(255, 255, 255, ba)))
                    p.drawEllipse(QPointF(cx, cy), btn.w / 2, btn.h / 2)
                    if is_hover:
                        p.setPen(QPen(QColor(0xB4, 0xC8, 0xDC, 140), 1.5))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawEllipse(QPointF(cx, cy), btn.w / 2, btn.h / 2)

                ic = QColor(0x1A, 0x23, 0x48) if is_main else QColor(text_p)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(ic))
                if btn.kind == "prev":
                    tri = QPainterPath()
                    tri.moveTo(cx+5, cy-5); tri.lineTo(cx-1, cy); tri.lineTo(cx+5, cy+5); tri.closeSubpath()
                    p.drawPath(tri)
                    tri2 = QPainterPath()
                    tri2.moveTo(cx+11, cy-5); tri2.lineTo(cx+5, cy); tri2.lineTo(cx+11, cy+5); tri2.closeSubpath()
                    p.drawPath(tri2)
                elif btn.kind == "pause":
                    p.drawRoundedRect(QRectF(cx-5, cy-5, 3.5, 10), 1.5, 1.5)
                    p.drawRoundedRect(QRectF(cx+1.5, cy-5, 3.5, 10), 1.5, 1.5)
                elif btn.kind == "play":
                    tri = QPainterPath()
                    tri.moveTo(cx-3, cy-7); tri.lineTo(cx-3, cy+7); tri.lineTo(cx+7, cy); tri.closeSubpath()
                    p.drawPath(tri)
                elif btn.kind == "next":
                    tri = QPainterPath()
                    tri.moveTo(cx-11, cy-5); tri.lineTo(cx-5, cy); tri.lineTo(cx-11, cy+5); tri.closeSubpath()
                    p.drawPath(tri)
                    tri2 = QPainterPath()
                    tri2.moveTo(cx-5, cy-5); tri2.lineTo(cx+1, cy); tri2.lineTo(cx-5, cy+5); tri2.closeSubpath()
                    p.drawPath(tri2)
        else:
            self._buttons.clear()

        p.end()

