"""Music Card Widget v0.2 - 音乐卡片(带播放控制)

显示:
- 播放器名称 + 图标
- 歌曲名(如有)
- 歌手名(如有)
- 播放控制按钮(上一首 / 播放暂停 / 下一首)
- 播放中动画(粒子跳动)
- 未播放状态

设计:
- 280x180 卡片(比 v0.1 高 20px 给按钮留空间)
- 冷蓝主题(与月历卡统一)
- 粒子动画表示播放状态
- 按钮用 emoji 绘制,点击模拟系统媒体键
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from random import uniform

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush,
    QLinearGradient, QPainterPath, QFontMetrics,
)

_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.card_base import CardBase
from core.theme import ThemeManager
from .service import (
    detect_music_simple, MusicInfo,
    media_play_pause,
    media_next,
    media_prev,
)
from .audio_viz import get_peak, get_levels, start as start_audio
from .media_ctrl import get_media_progress, MediaProgress


# ── 粒子 ──────────────────────────────────────────────
class _Particle:
    __slots__ = ("x", "y", "r", "speed", "phase", "color")

    def __init__(self, w: int, h: int, color: QColor):
        self.x = uniform(20, w - 20)
        self.y = uniform(h * 0.4, h - 40)
        self.r = uniform(2, 5)
        self.speed = uniform(0.3, 1.2)
        self.phase = uniform(0, math.pi * 2)
        self.color = color


# ── 按钮区域定义 ──────────────────────────────────────
class _Btn:
    """播放控制按钮"""
    __slots__ = ("x", "y", "w", "h", "emoji", "action")

    def __init__(self, x: float, y: float, w: float, h: float, emoji: str, action):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.emoji = emoji
        self.action = action

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


# ── 主卡片 ────────────────────────────────────────────
class MusicCardWidget(CardBase):
    """音乐卡片 v0.2"""

    card_id = "music_card"
    card_name = "🎵 音乐"
    card_icon = "🎵"
    default_size = (280, 240)
    update_interval_ms = 3000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 160)

    def init_ui(self) -> None:
        """纯自绘,无子控件"""
        self._info: MusicInfo | None = None
        self._particles: list[_Particle] = []
        self._tick = 0.0
        self._hover_btn: int = -1
        self._buttons: list[_Btn] = []
        self._num_bars = 27
        self._audio_levels: list[float] = [0.0] * self._num_bars
        self._smooth_levels: list[float] = [0.0] * self._num_bars
        self._progress: MediaProgress = MediaProgress()
        # 歌词
        self._lyrics: list = []  # List[LyricLine]
        self._lyric_idx: int = -1
        self._lyric_offset: float = 0.0  # 当前行滚动偏移

        # 启动后台音频采样线程
        start_audio()

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(100)  # 10 FPS 足够,省 CPU
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start()

        self.setMouseTracking(True)

    def update_data(self) -> None:
        """检测音乐播放器+进度"""
        old_title = self._info.song_title if self._info else None
        old_artist = self._info.song_artist if self._info else None
        self._info = detect_music_simple()
        p = get_media_progress()
        if p:
            self._progress = p
        # 歌曲变化时加载歌词
        if self._info and self._info.song_title:
            if (self._info.song_title != old_title or
                    self._info.song_artist != old_artist):
                self._load_lyrics()
        self.update()

    def _load_lyrics(self) -> None:
        """加载当前歌曲歌词"""
        from .lyrics_loader import get_lyrics
        title = self._info.song_title if self._info else ""
        artist = self._info.song_artist if self._info else ""
        if title:
            self._lyrics = get_lyrics(title, artist)
            self._lyric_idx = -1
        else:
            self._lyrics = []

    def _animate(self) -> None:
        # 读取音频电平
        if self._info and self._info.is_playing:
            self._tick += 0.1
            raw = get_levels(self._num_bars)
            # 平滑(轻度平滑,保持响应速度)
            for i in range(self._num_bars):
                self._smooth_levels[i] = self._smooth_levels[i] * 0.3 + raw[i] * 0.7
            self._audio_levels = raw

            if len(self._particles) < 12:
                c = QColor(95, 229, 224, 180)
                self._particles.append(_Particle(self.width(), self.height(), c))
            alive = []
            for pt in self._particles:
                pt.y -= pt.speed * (1.0 + raw[0] * 2)  # 低频越强粒子越快
                pt.x += math.sin(self._tick + pt.phase) * (0.5 + raw[1] * 2)
                if pt.y > -10:
                    alive.append(pt)
            self._particles = alive
        else:
            self._particles.clear()
            self._smooth_levels = [0.0] * 5
        self.update()

    # ── 鼠标事件 ──────────────────────────────────────
    def mouseMoveEvent(self, ev) -> None:
        x, y = ev.position().x(), ev.position().y()
        old = self._hover_btn
        self._hover_btn = -1
        for i, btn in enumerate(self._buttons):
            if btn.contains(x, y):
                self._hover_btn = i
                break
        if self._hover_btn != old:
            self.update()

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            x, y = ev.position().x(), ev.position().y()
            for btn in self._buttons:
                if btn.contains(x, y):
                    btn.action()
                    return

    def leaveEvent(self, ev) -> None:
        self._hover_btn = -1
        self.update()

    # ── 绘制 ──────────────────────────────────────────
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        tm = ThemeManager.instance()
        d = tm.current()
        w, h = self.width(), self.height()

        bg = self._to_color(d.get("background", "#1a1a2e"))
        bg_end = self._to_color(d.get("background_gradient_end", bg))
        border = self._to_color(d.get("border", "#4a7c9e"))
        text_p = self._to_color(d.get("text_primary", "#e0e0ff"))
        text_s = self._to_color(d.get("text_secondary", "#a0aec0"))
        accent = self._to_color(d.get("accent", "#5fe5e0"))
        radius = int(d.get("corner_radius", 16))

        # ── 背景 ──
        grad = QLinearGradient(0, 0, 0, h)
        c1 = QColor(bg); c1.setAlpha(170)
        c2 = QColor(bg_end if bg_end != bg else bg); c2.setAlpha(210)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        p.fillPath(path, QBrush(grad))

        # ── 顶部高光 ──
        hl = QLinearGradient(0, 0, 0, 50)
        hl.setColorAt(0.0, QColor(255, 255, 255, 25))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(hl))

        # ── 边框 ──
        pen_outer = QPen(QColor(border.red(), border.green(), border.blue(), 70))
        pen_outer.setWidthF(1.0)
        p.setPen(pen_outer)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)
        pen_inner = QPen(QColor(255, 255, 255, 40))
        pen_inner.setWidthF(0.5)
        p.setPen(pen_inner)
        p.drawRoundedRect(QRectF(1.5, 1.5, w - 3, h - 3), radius - 1, radius - 1)

        # ── 粒子 ──
        for pt in self._particles:
            alpha = max(0, min(255, int(180 * (pt.y / h))))
            c = QColor(pt.color); c.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(pt.x, pt.y), pt.r, pt.r)

        # ── 读取字体 ──
        family = d.get("fonts", {}).get("family", "Microsoft YaHei UI") if isinstance(d.get("fonts"), dict) else "Microsoft YaHei UI"

        # ── 内容 ──
        margin = 16
        top_y = 14

        if self._info and self._info.player_name:
            # 播放器图标+名称
            font = QFont(family, 16)
            p.setFont(font)
            p.setPen(QPen(text_p))
            p.drawText(QPointF(margin, top_y + 18), self._info.player_icon)

            font_name = QFont(family, 11)
            font_name.setBold(True)
            p.setFont(font_name)
            p.setPen(QPen(text_p))
            p.drawText(QPointF(margin + 26, top_y + 18), self._info.player_name)

            # 歌曲名
            if self._info.song_title:
                top_y += 28
                font_song = QFont(family, 13)
                font_song.setBold(True)
                p.setFont(font_song)
                p.setPen(QPen(accent))
                song = self._info.song_title
                fm = QFontMetrics(font_song)
                max_w = w - margin * 2
                if fm.horizontalAdvance(song) > max_w:
                    song = fm.elidedText(song, Qt.TextElideMode.ElideRight, max_w)
                p.drawText(QPointF(margin, top_y + 16), song)

            # 歌手名
            if self._info.song_artist:
                top_y += 20
                font_art = QFont(family, 10)
                p.setFont(font_art)
                p.setPen(QPen(text_s))
                artist = self._info.song_artist
                fm = QFontMetrics(font_art)
                max_w = w - margin * 2
                if fm.horizontalAdvance(artist) > max_w:
                    artist = fm.elidedText(artist, Qt.TextElideMode.ElideRight, max_w)
                p.drawText(QPointF(margin, top_y + 14), artist)

            # ── 播放进度条(歌手名下方) ──
            if self._progress.duration_ms > 0:
                prog_y = top_y + 22
                prog_h = 3
                prog_w = w - margin * 2
                # 背景
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 255, 255, 25)))
                p.drawRoundedRect(QRectF(margin, prog_y, prog_w, prog_h), 1.5, 1.5)
                # 进度
                fill_w = prog_w * self._progress.progress_pct
                prog_grad = QLinearGradient(margin, 0, margin + prog_w, 0)
                prog_grad.setColorAt(0.0, QColor(95, 229, 224, 200))
                prog_grad.setColorAt(1.0, QColor(74, 124, 158, 200))
                p.setBrush(QBrush(prog_grad))
                p.drawRoundedRect(QRectF(margin, prog_y, max(fill_w, 3), prog_h), 1.5, 1.5)
                # 时间文字
                font_time = QFont(family, 8)
                p.setFont(font_time)
                p.setPen(QPen(text_s))
                time_text = f"{self._progress.position_str} / {self._progress.duration_str}"
                p.drawText(QPointF(margin, prog_y + 12), time_text)

            # ── 歌词显示(滚动,当前行高亮) ──
            lyric_y = top_y + 34 if self._progress.duration_ms > 0 else top_y + 24
            if self._lyrics and self._info and self._info.is_playing:
                # 根据播放进度找到当前歌词行
                pos_sec = self._progress.position_ms / 1000.0
                new_idx = -1
                for i, line in enumerate(self._lyrics):
                    if line.time_sec <= pos_sec:
                        new_idx = i
                    else:
                        break
                self._lyric_idx = new_idx

                font_lyric = QFont(family, 9)
                font_lyric_cur = QFont(family, 10)
                font_lyric_cur.setBold(True)
                fm_cur = QFontMetrics(font_lyric_cur)
                fm_norm = QFontMetrics(font_lyric)
                max_w = w - margin * 2

                # 显示当前行 + 上下各 1 行
                for di in range(-1, 2):
                    idx = self._lyric_idx + di
                    if idx < 0 or idx >= len(self._lyrics):
                        continue
                    text = self._lyrics[idx].text
                    is_current = (di == 0)
                    f = font_lyric_cur if is_current else font_lyric
                    fm = fm_cur if is_current else fm_norm
                    if fm.horizontalAdvance(text) > max_w:
                        text = fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w)
                    alpha = 255 if is_current else 80
                    color = QColor(accent) if is_current else QColor(text_s)
                    color.setAlpha(alpha)
                    p.setFont(f)
                    p.setPen(QPen(color))
                    y_off = lyric_y + (di * 16) if di != 0 else lyric_y
                    # 当前行居中,其他行偏移
                    tw = fm.horizontalAdvance(text)
                    x = (w - tw) / 2 if is_current else margin
                    p.drawText(QPointF(x, y_off + 12), text)
            elif self._lyrics:
                # 有歌词但未播放,显示第一行
                font_lyric = QFont(family, 9)
                p.setFont(font_lyric)
                p.setPen(QPen(QColor(text_s)))
                if self._lyrics:
                    text = self._lyrics[0].text
                    fm = QFontMetrics(font_lyric)
                    if fm.horizontalAdvance(text) > w - margin * 2:
                        text = fm.elidedText(text, Qt.TextElideMode.ElideRight, w - margin * 2)
                    p.drawText(QPointF(margin, lyric_y + 12), text)

            # ── 音频律动条(水平+垂直居中,避开文字和按钮) ──
            bar_w = 4
            bar_gap = 3
            bar_max_h = 50
            total_bars_w = self._num_bars * (bar_w + bar_gap) - bar_gap
            bar_start_x = (w - total_bars_w) / 2
            # 垂直区域:文字底部到按钮顶部之间
            content_top = 88
            content_bottom = h - 56  # 按钮区上方(上移12px)
            bar_area_h = content_bottom - content_top
            bar_y_center = content_top + bar_area_h / 2
            for i, level in enumerate(self._smooth_levels):
                bh = max(2, bar_max_h * level)
                by = bar_y_center - bh / 2  # 以中心线为基准上下扩展
                bx = bar_start_x + i * (bar_w + bar_gap)
                ratio = i / max(1, self._num_bars - 1)
                center_dist = abs(ratio - 0.5) * 2
                bright = 1.0 - center_dist * 0.4
                r_c = int((95 + (74 - 95) * ratio) * bright)
                g_c = int((229 + (124 - 229) * ratio) * bright)
                b_c = int((224 + (158 - 224) * ratio) * bright)
                bar_c = QColor(r_c, g_c, b_c, int((120 + 135 * level) * bright))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(bar_c))
                p.drawRoundedRect(QRectF(bx, by, bar_w, bh), 2, 2)

            # ── 控制按钮(科技风) ──
            btn_y = h - 52  # 上移12px
            btn_h = 32
            btn_w = 40
            center_x = w / 2
            gap = 12

            self._buttons = [
                _Btn(center_x - btn_w * 1.5 - gap, btn_y, btn_w, btn_h, "prev", media_prev),
                _Btn(center_x - btn_w / 2, btn_y - 2, btn_w, btn_h + 4,
                     "pause" if self._info.is_playing else "play", media_play_pause),
                _Btn(center_x + btn_w / 2 + gap, btn_y, btn_w, btn_h, "next", media_next),
            ]

            # ── 装饰线(控制区两侧) ──
            dec_y = btn_y + btn_h / 2
            dec_w = 20
            pen_dec = QPen(QColor(border.red(), border.green(), border.blue(), 50))
            pen_dec.setWidthF(0.5)
            p.setPen(pen_dec)
            p.drawLine(QPointF(center_x - btn_w * 1.5 - gap - dec_w - 4, dec_y),
                       QPointF(center_x - btn_w * 1.5 - gap - 4, dec_y))
            p.drawLine(QPointF(center_x + btn_w * 1.5 + gap + 4, dec_y),
                       QPointF(center_x + btn_w * 1.5 + gap + dec_w + 4, dec_y))

            for i, btn in enumerate(self._buttons):
                cx = btn.x + btn.w / 2
                cy = btn.y + btn.h / 2
                is_main = (i == 1)  # 播放/暂停是主按钮
                is_hover = (self._hover_btn == i)

                # ── 按钮背景(主按钮渐变,普通按钮半透明) ──
                btn_path = QPainterPath()
                btn_path.addRoundedRect(QRectF(btn.x, btn.y, btn.w, btn.h),
                                        btn.h / 2, btn.h / 2)  # 全圆角胶囊

                if is_main:
                    # 主按钮:冷青渐变
                    play_grad = QLinearGradient(btn.x, btn.y, btn.x + btn.w, btn.y + btn.h)
                    if self._info.is_playing:
                        play_grad.setColorAt(0.0, QColor(95, 229, 224, 180))
                        play_grad.setColorAt(1.0, QColor(74, 124, 158, 180))
                    else:
                        play_grad.setColorAt(0.0, QColor(95, 229, 224, 120))
                        play_grad.setColorAt(1.0, QColor(74, 124, 158, 120))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(play_grad))
                    p.drawRoundedRect(QRectF(btn.x, btn.y, btn.w, btn.h),
                                      btn.h / 2, btn.h / 2)
                    # 播放中:呼吸光环
                    if self._info.is_playing:
                        pulse = abs(math.sin(self._tick * 2)) * 0.5 + 0.5
                        glow_c = QColor(95, 229, 224, int(60 * pulse))
                        p.setPen(QPen(glow_c, 2))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(QRectF(btn.x - 2, btn.y - 2, btn.w + 4, btn.h + 4),
                                          btn.h / 2 + 2, btn.h / 2 + 2)
                else:
                    # 普通按钮
                    bg_alpha = 45 if is_hover else 20
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(QColor(255, 255, 255, bg_alpha)))
                    p.drawRoundedRect(QRectF(btn.x, btn.y, btn.w, btn.h),
                                      btn.h / 2, btn.h / 2)
                    # 悬停发光边框
                    if is_hover:
                        p.setPen(QPen(QColor(95, 229, 224, 100), 1))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(QRectF(btn.x, btn.y, btn.w, btn.h),
                                          btn.h / 2, btn.h / 2)

                # ── 图标(矢量绘制) ──
                icon_color = QColor(255, 255, 255) if is_main else QColor(text_p)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(icon_color))

                if btn.emoji == "prev":
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
                elif btn.emoji == "pause":
                    p.drawRoundedRect(QRectF(cx - 5, cy - 5, 3.5, 10), 1.5, 1.5)
                    p.drawRoundedRect(QRectF(cx + 1.5, cy - 5, 3.5, 10), 1.5, 1.5)
                elif btn.emoji == "play":
                    tri = QPainterPath()
                    tri.moveTo(cx - 3, cy - 7)
                    tri.lineTo(cx - 3, cy + 7)
                    tri.lineTo(cx + 7, cy)
                    tri.closeSubpath()
                    p.drawPath(tri)
                elif btn.emoji == "next":
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
            # 无播放器
            font_empty = QFont(family, 12)
            p.setFont(font_empty)
            p.setPen(QPen(text_s))
            fm = QFontMetrics(font_empty)
            text = "🎵 未在播放"
            tw = fm.horizontalAdvance(text)
            p.drawText(QPointF((w - tw) / 2, h / 2 + 5), text)
            self._buttons.clear()

        p.end()

    # ── 鼠标事件 ──
    def mousePressEvent(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = ev.position().x(), ev.position().y()
        for btn in self._buttons:
            if btn.contains(x, y):
                btn.action()
                # 点击后刷新状态
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(200, self.update_data)
                break

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

    @staticmethod
    def _to_color(v) -> QColor:
        if isinstance(v, QColor):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("rgba"):
                inner = v[v.index("(") + 1:v.rindex(")")]
                parts = [x.strip() for x in inner.split(",")]
                if len(parts) == 4:
                    return QColor(int(parts[0]), int(parts[1]), int(parts[2]), int(float(parts[3]) * 255))
            if v.startswith("#") and len(v) == 9:
                try:
                    r, g, b, a = int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16), int(v[7:9], 16)
                    return QColor(r, g, b, a)
                except ValueError:
                    pass
            try:
                return QColor(v)
            except Exception:
                pass
        return QColor("#888888")
