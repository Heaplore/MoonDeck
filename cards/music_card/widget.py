"""Music Card Widget v0.6 (Phase 4+) - 音乐卡片(对齐月历 theme, 380 宽)

布局(380 x 300, 自上而下):
  ┌────────────────────────────────────┐
  │ [🥤 汽水音乐 (左上 caption 8px)]      │  0-22
  │ [       🎵 歌名居中 (16px 加粗)  ]    │  22-44
  │ [                歌手右对齐 (10px) ] │  44-58
  │                                     │
  │ [歌词 3 行 (当前行紫色高亮)]         │  60-110
  │                                     │
  │ [频谱律动 27 根 - 紫青渐变]          │  120-220
  │                                     │
  │ [进度条 3px (紫青) + 时间文字]       │  226-240
  │                                     │
  │ [控制 ⏮ ⏯ ⏭ (主按钮紫色)]          │  260-292
  └────────────────────────────────────┘
  总 300px

v0.6 改动:
  - 宽度对齐月历 (380)
  - 歌名居中 + 歌手右对齐
  - 进度条挪到律动条和按钮中间
  - _animate 实时同步 SMTC 元数据 (进度条动)
  - 卡片高度从 260 提到 300 (容纳新布局)
"""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush,
    QLinearGradient, QPainterPath, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget

_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.card_base import CardBase
from core.theme import ThemeManager

from . import audio_viz
from . import service
from .lyrics_loader import LyricLine, get_lyrics
from .audio_viz import set_now_playing

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 歌词元数据行过滤
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
# 颜色 helper
# ---------------------------------------------------------------------------
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
# 主卡片
# ---------------------------------------------------------------------------
class MusicCardWidget(CardBase):
    """音乐卡片 v0.6 - 对齐月历宽度 (380), 进度条在中间"""

    card_id = "music_card"
    card_name = "🎵 音乐"
    card_icon = "🎵"
    default_size = (380, 360)  # v0.7 改: 高度增加, 进度条和按钮间距 80px
    update_interval_ms = 1000

    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def init_ui(self) -> None:
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
        # v0.7 插值 position: 每帧 +dt, 不等 SMTC 0.3s 刷新
        self._current_position: float = 0.0
        self._last_smtc_position: float = 0.0
        self._last_smtc_playing: bool = False
        self._last_frame_time: float = 0.0

        audio_viz.start()

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)  # 30fps
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start()

        self.setMouseTracking(True)

    def update_data(self) -> None:
        """1s 一次拉数据 (含歌词触发)"""
        self._info = service.detect_music_simple()
        if not self._info:
            return
        key = f"{self._info.song_title}|{self._info.song_artist}"
        if key != self._last_song_key and self._info.song_title:
            self._last_song_key = key
            self._lyrics = []
            self._lyric_idx = -1
            self._lyrics_fetch_started = False
            self._current_position = self._info.position_sec  # 切歌时同步到 SMTC
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
                log.info(f"歌词加载: {title} - {artist} → {len(lines)} 行 (过滤后)")
            except Exception as e:
                log.warning(f"歌词加载失败: {e}")
                self._lyrics = []
            finally:
                self._lyrics_fetch_started = False
                self.update()

        QTimer.singleShot(50, _fetch)

    def _animate(self) -> None:
        """30fps: 插值 position + 频谱 + 歌词行号"""
        import time as _time
        self._tick += 0.1

        # v0.8: 测量真实帧间隔 (不用硬编码 0.033)
        now = _time.time()
        if self._last_frame_time > 0:
            dt = min(now - self._last_frame_time, 0.5)  # cap 0.5s 防切 tab 时爆
        else:
            dt = 0.033
        self._last_frame_time = now

        # 同步 SMTC 元数据
        new_info = service.detect_music_simple()
        if new_info:
            self._info = new_info

        # v0.8: 插值 position (用真实 dt)
        if self._info:
            smtc_pos = self._info.position_sec
            self._last_smtc_playing = self._info.is_playing

            if self._info.is_playing:
                self._current_position += dt
                # SMTC 更新时: 只在 seek (前后跳 >2s) 才重置
                if smtc_pos != self._last_smtc_position:
                    diff = smtc_pos - self._current_position
                    if abs(diff) > 2.0:
                        self._current_position = smtc_pos
                    self._last_smtc_position = smtc_pos
                if self._info.duration_sec > 0:
                    self._current_position = min(self._current_position, self._info.duration_sec)
            else:
                # 暂停: 同步到 SMTC
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

        # 歌词行号: 用插值 position 计算
        if self._lyrics and self._info and self._current_position > 0:
            self._lyric_idx = self._find_lyric_idx(self._current_position)

        # 共享歌词状态给桌面动效层 (LyricsFX)
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

    # ── 鼠标事件 ──
    def mouseMoveEvent(self, ev) -> None:
        x, y = ev.position().x(), ev.position().y()
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

    def mousePressEvent(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = ev.position().x(), ev.position().y()
        for btn in self._buttons:
            if btn.contains(x, y):
                btn.action()
                QTimer.singleShot(300, self.update_data)
                break

    def leaveEvent(self, ev) -> None:
        self._hover_btn = -1
        self.update()

    # ── 绘制 ──
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        tm = ThemeManager.instance()
        d = tm.current()
        w, h = self.width(), self.height()

        # 主题色
        bg = _to_color(d.get("background", "#1A2348"))
        bg_end = _to_color(d.get("background_gradient_end", "#0F1632"))
        border = _to_color(d.get("border", "rgba(180, 200, 220, 0.20)"))
        text_p = _to_color(d.get("text_primary", "#E8F4F8"))
        text_s = _to_color(d.get("text_secondary", "#8FA8C0"))
        text_c = _to_color(d.get("text_caption", "#5A6A85"))
        accent = _to_color(d.get("accent", "#9F7CFF"))
        accent_text = _to_color(d.get("accent_text", "#B4C8DC"))
        radius = int(d.get("corner_radius", 24))

        fonts = d.get("fonts", {})
        family = fonts.get("family", "Microsoft YaHei UI") if isinstance(fonts, dict) else "Microsoft YaHei UI"
        sizes = fonts.get("sizes", {}) if isinstance(fonts, dict) else {}

        # ── 1. 背景 ──
        grad = QLinearGradient(0, 0, 0, h)
        c1 = QColor(bg); c1.setAlpha(180)
        c2 = QColor(bg_end); c2.setAlpha(220)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        p.fillPath(path, QBrush(grad))

        # 顶部高光
        hl = QLinearGradient(0, 0, 0, 40)
        hl.setColorAt(0.0, QColor(255, 255, 255, 20))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(hl))

        # 边框
        pen_outer = QPen(QColor(border.red(), border.green(), border.blue(), 90))
        pen_outer.setWidthF(1.0)
        p.setPen(pen_outer)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)
        pen_inner = QPen(QColor(255, 255, 255, 30))
        pen_inner.setWidthF(0.5)
        p.setPen(pen_inner)
        p.drawRoundedRect(QRectF(1.5, 1.5, w - 3, h - 3), radius - 1, radius - 1)

        # ── 2. 顶部信息 (播放器左上 + 歌名居中 + 歌手右对齐) ──
        margin = 16
        top_y = 14

        if self._info and self._info.player_name:
            # 播放器图标 + 名 (左上, caption 8px)
            font_cap = QFont(family, 8)
            p.setFont(font_cap)
            p.setPen(QPen(text_c))
            cap_text = f"{self._info.player_icon}  {self._info.player_name}"
            p.drawText(QPointF(margin, top_y + 12), cap_text)

            # 歌名 (居中, 加粗 13px)
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
                p.drawText(QPointF((w - tw) / 2, top_y + 32), song)

            # 歌手 (右对齐, 9px)
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
                p.drawText(QPointF(w - margin - tw_a, top_y + 50), artist)
        else:
            font_empty = QFont(family, 12)
            p.setFont(font_empty)
            p.setPen(QPen(text_s))
            p.drawText(QPointF(margin, top_y + 32), "🎵 未在播放")

        # ── 3. 歌词区 (60-110) ──
        lyric_y = 72
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
                y_off = lyric_y + (di * 16) if di != 0 else lyric_y
                tw = fm.horizontalAdvance(text)
                x = (w - tw) / 2 if is_cur else margin
                p.drawText(QPointF(x, y_off + 12), text)
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
                p.drawText(QPointF((w - tw) / 2, lyric_y + 12), text)
        else:
            # 无歌词: 提示加载中 / 暂无
            font_lyric = QFont(family, 9)
            p.setFont(font_lyric)
            p.setPen(QPen(text_c))
            if self._info and self._info.player_name:
                if self._lyrics_fetch_started:
                    p.drawText(QPointF(margin, lyric_y + 12), "♪ 加载歌词中...")
                else:
                    p.drawText(QPointF(margin, lyric_y + 12), "♪ 暂无歌词")

        # ── 4. 律动条 (彩虹色: 红→橙→黄→绿→青→蓝→紫) ──
        viz_top = 120
        viz_bottom = 220
        viz_h = viz_bottom - viz_top  # 100

        bar_w = 4
        bar_gap = max(2, int((w - margin * 2 - self._num_bars * bar_w) / max(1, self._num_bars - 1)))
        total_w = self._num_bars * bar_w + (self._num_bars - 1) * bar_gap
        start_x = (w - total_w) / 2

        RAINBOW = [
            (128, 0, 255),  # 紫 - level=0
            (0, 0, 255),    # 蓝
            (0, 255, 255),  # 青
            (0, 200, 0),    # 绿
            (255, 255, 0),  # 黄
            (255, 127, 0),  # 橙
            (255, 0, 0),    # 红 - level=1
        ]

        for i in range(self._num_bars):
            level = float(self._smooth_levels[i]) if i < len(self._smooth_levels) else 0.0
            bh = max(2, viz_h * 0.85 * level)
            bx = start_x + i * (bar_w + bar_gap)
            by = viz_bottom - bh

            color_idx = min(len(RAINBOW) - 1, int(level * (len(RAINBOW) - 1)))
            r, g, b = RAINBOW[color_idx]

            bar_c = QColor(r, g, b, int(80 + 175 * level))
            p.fillRect(int(bx), int(by), bar_w, int(bh), bar_c)

        # ── 5. 进度条 (226-244, 律动和按钮中间) ──
        prog_y = viz_bottom + 6  # 226
        prog_h = 3
        prog_w = w - margin * 2
        # 背景
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 30)))
        p.drawRoundedRect(QRectF(margin, prog_y, prog_w, prog_h), 1.5, 1.5)
        # 进度
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

        # ── 6. 控制按钮 (260-292) ──
        if self._info and self._info.player_name:
            btn_y = viz_bottom + 80  # 300 (律动条下方 80px, 进度条和按钮间距 ≈ 80)
            btn_h = 30
            btn_w = 36
            center_x = w / 2
            gap = 12

            self._buttons = [
                _Btn(center_x - btn_w * 1.5 - gap, btn_y, btn_w, btn_h,
                     "prev", service.media_prev),
                _Btn(center_x - btn_w / 2, btn_y - 1, btn_w, btn_h + 2,
                     "pause" if self._info.is_playing else "play",
                     service.media_play_pause),
                _Btn(center_x + btn_w / 2 + gap, btn_y, btn_w, btn_h,
                     "next", service.media_next),
            ]

            for i, btn in enumerate(self._buttons):
                cx = btn.x + btn.w / 2
                cy = btn.y + btn.h / 2
                is_main = (i == 1)
                is_hover = (self._hover_btn == i)

                if is_main:
                    play_grad = QLinearGradient(btn.x, btn.y, btn.x + btn.w, btn.y + btn.h)
                    if self._info.is_playing:
                        play_grad.setColorAt(0.0, QColor(0x9F, 0x7C, 0xFF, 200))
                        play_grad.setColorAt(1.0, QColor(0xB8, 0x9F, 0xFF, 200))
                    else:
                        play_grad.setColorAt(0.0, QColor(0x9F, 0x7C, 0xFF, 130))
                        play_grad.setColorAt(1.0, QColor(0xB8, 0x9F, 0xFF, 130))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(play_grad))
                    p.drawRoundedRect(QRectF(btn.x, btn.y, btn.w, btn.h),
                                      btn.h / 2, btn.h / 2)
                    if self._info.is_playing:
                        import math
                        pulse = abs(math.sin(self._tick)) * 0.5 + 0.5
                        glow_c = QColor(0x9F, 0x7C, 0xFF, int(60 * pulse))
                        p.setPen(QPen(glow_c, 2))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(QRectF(btn.x - 2, btn.y - 2, btn.w + 4, btn.h + 4),
                                          btn.h / 2 + 2, btn.h / 2 + 2)
                else:
                    bg_alpha = 50 if is_hover else 25
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(255, 255, 255, bg_alpha)))
                    p.drawRoundedRect(QRectF(btn.x, btn.y, btn.w, btn.h),
                                      btn.h / 2, btn.h / 2)
                    if is_hover:
                        p.setPen(QPen(QColor(0xB4, 0xC8, 0xDC, 120), 1))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(QRectF(btn.x, btn.y, btn.w, btn.h),
                                          btn.h / 2, btn.h / 2)

                # 图标
                icon_color = QColor(255, 255, 255) if is_main else QColor(text_p)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(icon_color))

                if btn.kind == "prev":
                    tri = QPainterPath()
                    tri.moveTo(cx + 5, cy - 5)
                    tri.lineTo(cx - 1, cy)
                    tri.lineTo(cx + 5, cy + 5)
                    tri.closeSubpath()
                    p.drawPath(tri)
                    tri2 = QPainterPath()
                    tri2.moveTo(cx + 11, cy - 5)
                    tri2.lineTo(cx + 5, cy)
                    tri2.lineTo(cx + 11, cy + 5)
                    tri2.closeSubpath()
                    p.drawPath(tri2)
                elif btn.kind == "pause":
                    p.drawRoundedRect(QRectF(cx - 5, cy - 5, 3.5, 10), 1.5, 1.5)
                    p.drawRoundedRect(QRectF(cx + 1.5, cy - 5, 3.5, 10), 1.5, 1.5)
                elif btn.kind == "play":
                    tri = QPainterPath()
                    tri.moveTo(cx - 3, cy - 7)
                    tri.lineTo(cx - 3, cy + 7)
                    tri.lineTo(cx + 7, cy)
                    tri.closeSubpath()
                    p.drawPath(tri)
                elif btn.kind == "next":
                    tri = QPainterPath()
                    tri.moveTo(cx - 11, cy - 5)
                    tri.lineTo(cx - 5, cy)
                    tri.lineTo(cx - 11, cy + 5)
                    tri.closeSubpath()
                    p.drawPath(tri)
                    tri2 = QPainterPath()
                    tri2.moveTo(cx - 5, cy - 5)
                    tri2.lineTo(cx + 1, cy)
                    tri2.lineTo(cx - 5, cy + 5)
                    tri2.closeSubpath()
                    p.drawPath(tri2)
        else:
            self._buttons.clear()

        p.end()
