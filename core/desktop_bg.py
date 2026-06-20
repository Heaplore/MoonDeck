"""Audio-Reactive Desktop Background v0.9

双层架构:
  1. 桌面背景层 (DesktopBackground) - z_order 最底
     3 种可切换动效: nebula / starfield / mandala
  2. 歌词动效层 (LyricsFX) - 叠加在背景层之上
     2 种可切换动效: lyrics_stream (飘字流) / lyrics_particle (粒子字)

两层独立可叠加，互不影响。
- z-order: LyricsFX 在 DesktopBackground 之上
- 不拦截鼠标 (WA_TransparentForMouseEvents + WS_EX_TRANSPARENT)

数据源: cards.music_card.audio_viz
"""
from __future__ import annotations

import math
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (QPainter, QColor, QRadialGradient, QLinearGradient,
                         QBrush, QPen, QGuiApplication, QPixmap,
                         QPainterPath, QPolygonF, QFont, QFontMetrics)
from PyQt6.QtWidgets import QWidget


# ---------------------------------------------------------------------------
# 音频数据 (每帧从 audio_viz 取)
# ---------------------------------------------------------------------------
@dataclass
class _Audio:
    bass: float = 0.0       # 低频能量 0-1
    mid: float = 0.0        # 中频能量 0-1
    treble: float = 0.0     # 高频能量 0-1
    peak: float = 0.0       # 峰值 0-1
    is_playing: bool = False
    beat_hit: bool = False  # 本帧是否触发 beat
    # 歌词同步 (从 NowPlayingState 填充)
    lyrics: List = field(default_factory=list)
    lyric_idx: int = -1
    position_sec: float = 0.0
    duration_sec: float = 0.0
    song_title: str = ""
    song_artist: str = ""


def _read_audio(audio_viz) -> _Audio:
    """从 audio_viz 读取数据, 并从 NowPlayingState 拉歌词"""
    try:
        spectrum = audio_viz.get_spectrum()
    except Exception:
        spectrum = None
    n = len(spectrum) if spectrum is not None else 0
    if n == 0:
        a = _Audio()
    else:
        bass = float(spectrum[: max(n // 6, 1)].mean())
        mid = float(spectrum[n // 6: max(n // 2, n // 6 + 1)].mean())
        treble = float(spectrum[n // 2:].mean()) if n // 2 < n else 0.0
        peak = float(spectrum.max())
        is_playing = peak > 0.04
        a = _Audio(bass=bass, mid=mid, treble=treble, peak=peak,
                   is_playing=is_playing)
    # 从 NowPlayingState 拉歌词 (从 audio_viz 直接读，避免 PyInstaller 遗漏 now_playing.py)
    try:
        from cards.music_card import audio_viz
        np_ = audio_viz.get_now_playing()
        a.lyrics = np_.lyrics
        a.lyric_idx = np_.lyric_idx
        a.position_sec = np_.position_sec
        a.duration_sec = np_.duration_sec
        a.song_title = np_.song_title
        a.song_artist = np_.song_artist
    except Exception:
        pass
    return a


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------
class _BaseVisualizer:
    """所有动效的基类"""
    NAME = "base"
    DISPLAY_NAME = "Base"

    def __init__(self, w: int, h: int):
        self._w = w
        self._h = h
        self._t = 0.0
        # 背景渐变缓存 (10Hz 重渲)
        self._grad_frame = -1
        self._grad_pixmap: Optional[QPixmap] = None

    def resize(self, w: int, h: int) -> None:
        self._w = w
        self._h = h
        self._grad_pixmap = None
        self._grad_frame = -1
        self.on_resize()

    def on_resize(self) -> None:
        """子类可重写"""
        pass

    def update(self, dt: float, audio: _Audio) -> None:
        self._t += dt

    def paint(self, p: QPainter, audio: _Audio) -> None:
        """子类实现"""
        pass

    def _bg_gradient(self, p: QPainter) -> None:
        """默认背景: 3 个大径向渐变 (子类可重写)"""
        new_frame = int(self._t * 10)
        if new_frame == self._grad_frame and self._grad_pixmap is not None:
            p.drawPixmap(0, 0, self._grad_pixmap)
            return
        self._grad_frame = new_frame
        pm = QPixmap(self._w, self._h)
        pm.fill(Qt.GlobalColor.transparent)
        gp = QPainter(pm)
        gp.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._t * 0.08
        h1 = int(220 + math.sin(t) * 14) % 360
        h2 = int(275 + math.cos(t * 0.7) * 16) % 360
        h3 = int(205 + math.sin(t * 0.5) * 12) % 360
        for cx, cy, color in [
            (self._w * 0.15, self._h * 0.25,
             QColor.fromHsv(h1, 80, 35, 30)),
            (self._w * 0.85, self._h * 0.75,
             QColor.fromHsv(h2, 95, 45, 25)),
            (self._w * 0.5, self._h * 0.5,
             QColor.fromHsv(h3, 60, 18, 40)),
        ]:
            radius = max(self._w, self._h) * 0.75
            grad = QRadialGradient(cx, cy, radius)
            grad.setColorAt(0.0, color)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            gp.fillRect(0, 0, self._w, self._h, QBrush(grad))
        gp.end()
        self._grad_pixmap = pm
        p.drawPixmap(0, 0, pm)


# ---------------------------------------------------------------------------
# 1. 粒子星云 + 中心球 + 涟漪环 (Nebula Orb)
# ---------------------------------------------------------------------------
class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "size", "life", "max_life", "hue", "alpha")

    def __init__(self, w: int, h: int):
        self.reset(w, h, fresh=True)

    def reset(self, w: int, h: int, fresh: bool) -> None:
        if fresh:
            self.x = random.uniform(0, w)
            self.y = random.uniform(0, h)
        else:
            self.x = random.uniform(0, w)
            self.y = h + random.uniform(0, 30)
        angle = random.uniform(-math.pi * 0.18, math.pi * 0.18)
        speed = random.uniform(0.25, 0.7)
        self.vx = math.sin(angle) * speed
        self.vy = -math.cos(angle) * speed
        self.size = random.uniform(1.5, 4.5)
        self.max_life = random.uniform(0.6, 1.0)
        self.life = self.max_life
        self.hue = random.uniform(215, 295)
        self.alpha = random.uniform(0.45, 0.85)

    def update(self, dt: float, w: int, h: int,
               bass: float, mid: float, treble: float,
               cx: float, cy: float) -> None:
        # 中心吸引 (bass 强时聚拢)
        attract = bass * 0.6
        dx = cx - self.x
        dy = cy - self.y
        dist = max(math.hypot(dx, dy), 1)
        self.vx += (dx / dist) * attract
        self.vy += (dy / dist) * attract
        # 横向漂移
        sway = math.sin(time.time() * 0.8 + self.y * 0.005) * 0.18
        self.x += self.vx + sway
        self.y += self.vy - bass * 0.4
        self.vx += treble * 0.04 * random.uniform(-1, 1)
        self.vx *= 0.985
        self.life -= dt * 0.12
        if self.life <= 0 or self.y < -20 or self.x < -20 or self.x > w + 20:
            self.reset(w, h, fresh=False)


class _EnergyRing:
    __slots__ = ("x", "y", "radius", "max_radius", "life", "alpha")

    def __init__(self, x: float, y: float, max_r: float = 220.0):
        self.x = x
        self.y = y
        self.radius = 6.0
        self.max_radius = max_r
        self.life = 1.0
        self.alpha = 0.7

    def update(self, dt: float) -> bool:
        self.radius += (self.max_radius - self.radius) * 0.05
        self.life -= dt * 0.45
        self.alpha = max(0.0, self.life * 0.65)
        return self.life > 0


class _NebulaOrbVisualizer(_BaseVisualizer):
    NAME = "nebula"
    DISPLAY_NAME = "粒子星云"

    NUM_PARTICLES = 70

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        random.seed()
        self._particles: List[_Particle] = [
            _Particle(w, h) for _ in range(self.NUM_PARTICLES)
        ]
        self._rings: List[_EnergyRing] = []
        self._beat_cooldown = 0.0
        self._last_peak = 0.0

    def update(self, dt: float, audio: _Audio) -> None:
        super().update(dt, audio)
        cx, cy = self._w / 2, self._h / 2
        for p in self._particles:
            p.update(dt, self._w, self._h, audio.bass, audio.mid,
                     audio.treble, cx, cy)
        # beat 触发环
        self._beat_cooldown -= dt
        if (audio.peak > 0.45 and audio.peak > self._last_peak * 1.25
                and self._beat_cooldown <= 0 and audio.is_playing):
            rx = random.uniform(self._w * 0.1, self._w * 0.9)
            ry = random.uniform(self._h * 0.3, self._h * 0.8)
            self._rings.append(_EnergyRing(rx, ry, max_r=random.uniform(160, 300)))
            self._beat_cooldown = 0.28
        self._last_peak = audio.peak * 0.7 + self._last_peak * 0.3
        self._rings = [r for r in self._rings if r.update(dt)]
        if len(self._rings) > 6:
            self._rings = self._rings[-6:]

    def paint(self, p: QPainter, audio: _Audio) -> None:
        # 1. 渐变背景
        self._bg_gradient(p)
        # 2. 中心球 (脉动)
        cx, cy = self._w / 2, self._h / 2
        orb_r = 80 + audio.bass * 100
        orb_alpha = int(60 + audio.bass * 120)
        orb_grad = QRadialGradient(cx, cy, orb_r)
        orb_grad.setColorAt(0.0, QColor(220, 235, 255, orb_alpha))
        orb_grad.setColorAt(0.5, QColor(180, 200, 240, orb_alpha // 2))
        orb_grad.setColorAt(1.0, QColor(120, 150, 220, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(orb_grad))
        p.drawEllipse(QPointF(cx, cy), orb_r, orb_r)
        # 3. 能量环
        for ring in self._rings:
            alpha = int(ring.alpha * 255)
            color = QColor(180, 210, 255, alpha)
            pen = QPen(color)
            pen.setWidthF(1.8)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(ring.x, ring.y), ring.radius, ring.radius)
        # 4. 粒子
        for particle in self._particles:
            self._draw_particle(p, particle)

    def _draw_particle(self, p: QPainter, particle: _Particle) -> None:
        life_ratio = max(0.0, particle.life / particle.max_life)
        alpha = int(particle.alpha * 255 * life_ratio)
        size = particle.size * (1.0 + 0.4 * life_ratio)
        color = QColor.fromHsv(int(particle.hue) % 360, 180, 255, alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawEllipse(QPointF(particle.x, particle.y), size, size)
        halo_alpha = alpha // 4
        if halo_alpha > 3:
            halo = QColor.fromHsv(int(particle.hue) % 360, 150, 255, halo_alpha)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(particle.x, particle.y), size * 2.8, size * 2.8)


# ---------------------------------------------------------------------------
# 3. 星空 (Starfield) - 辅助类
# ---------------------------------------------------------------------------


class _Star:
    __slots__ = ("x", "y", "size", "layer", "color", "twinkle_speed",
                 "twinkle_phase", "is_giant")

    def __init__(self, w: int, h: int, layer: int):
        self.x = random.uniform(0, w)
        self.y = random.uniform(0, h)
        self.layer = layer
        self.size = {0: random.uniform(0.3, 0.6),
                     1: random.uniform(0.5, 1.0),
                     2: random.uniform(0.8, 1.6)}[layer]
        self.is_giant = (layer == 2 and random.random() < 0.02)
        if self.is_giant:
            self.size = random.uniform(1.8, 2.8)
        if self.is_giant:
            self.color = random.choice([(200, 220, 255), (220, 230, 255)])
        else:
            self.color = random.choice([(255, 240, 220), (200, 220, 255),
                                        (255, 220, 200)])
        self.twinkle_speed = random.uniform(0.5, 2.5)
        self.twinkle_phase = random.uniform(0, math.pi * 2)


class _ShootingStar:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "length",
                 "head_color", "trail_color")

    def __init__(self, w: int, h: int):
        edge = random.choice([0, 1, 2])
        if edge == 0:
            self.x = random.uniform(0, w * 0.7)
            self.y = -20
        elif edge == 1:
            self.x = -20
            self.y = random.uniform(0, h * 0.5)
        else:
            self.x = w + 20
            self.y = random.uniform(0, h * 0.4)
        cx, cy = w * 0.5, h * 0.55
        dx, dy = cx - self.x, cy - self.y
        d = math.hypot(dx, dy) or 1
        speed = random.uniform(180, 320)
        self.vx = dx / d * speed
        self.vy = dy / d * speed
        self.max_life = random.uniform(1.2, 2.0)
        self.life = self.max_life
        self.length = random.uniform(80, 160)
        self.head_color = random.choice([(255, 255, 240), (220, 235, 255)])
        self.trail_color = random.choice([(150, 200, 255), (180, 180, 220)])

    def update(self, dt: float) -> bool:
        """推进位置和生命, 返回 False 时应被回收"""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0


class _StarfieldVisualizer(_BaseVisualizer):
    """真实风格星空: 颜色温度/银道带/巨星十字光芒/渐变尾巴流星/强度自适应"""
    NAME = "starfield"
    DISPLAY_NAME = "星空"

    NUM_STARS = 240

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        random.seed()
        self._stars: List[_Star] = []
        for _ in range(self.NUM_STARS):
            layer = random.choices([0, 1, 2], weights=[5, 3, 1])[0]
            self._stars.append(_Star(w, h, layer))
        self._shooting: List[_ShootingStar] = []
        self._beat_cooldown = 0.0
        self._last_peak = 0.0
        self._intensity = 0.0
        # 漂移星云 (8 个) - 透明度低，不遮罩桌面
        self._nebula_seeds = [
            {"x": w * 0.18, "y": h * 0.25, "r": 380, "hue": 215,
             "alpha": 22, "vx": 4, "vy": 2},
            {"x": w * 0.78, "y": h * 0.65, "r": 420, "hue": 275,
             "alpha": 18, "vx": -3, "vy": 1},
            {"x": w * 0.52, "y": h * 0.85, "r": 350, "hue": 195,
             "alpha": 16, "vx": 2, "vy": -2},
            {"x": w * 0.12, "y": h * 0.75, "r": 300, "hue": 295,
             "alpha": 14, "vx": 3, "vy": -1},
            {"x": w * 0.42, "y": h * 0.42, "r": 320, "hue": 235,
             "alpha": 12, "vx": -2, "vy": 2},
            {"x": w * 0.85, "y": h * 0.20, "r": 280, "hue": 260,
             "alpha": 10, "vx": 2, "vy": 2},
            {"x": w * 0.32, "y": h * 0.60, "r": 260, "hue": 190,
             "alpha": 9, "vx": 1, "vy": -2},
            {"x": w * 0.65, "y": h * 0.45, "r": 290, "hue": 310,
             "alpha": 8, "vx": -2, "vy": 1},
        ]
        # 上一首歌 key (切歌时触发流星雨)
        self._last_song_key: str = ""
        self._meteor_shower_cooldown: float = 0.0

    def update(self, dt: float, audio: _Audio) -> None:
        super().update(dt, audio)
        # 切歌检测 → 流星雨 (从 audio.song_title + artist 拼 key)
        if audio.song_title or audio.song_artist:
            song_key = f"{audio.song_title}|{audio.song_artist}"
            if song_key != self._last_song_key:
                # 切歌 / 首次初始化！生成 6-8 颗流星雨
                import random as _r
                n = _r.randint(6, 8)
                for _ in range(n):
                    self._shooting.append(_ShootingStar(self._w, self._h))
                self._last_song_key = song_key
        # 强度追踪 (EMA 平滑) — 区分舒缓/高亢
        instant = 0.5 * audio.bass + 0.3 * audio.mid + 0.2 * audio.treble
        self._intensity = self._intensity * 0.94 + instant * 0.06
        # 漂移 (层视差)
        drift_speed = 6.0
        for star in self._stars:
            star.x += dt * drift_speed * (star.layer + 1) * 0.5
            if star.x > self._w + 5:
                star.x = -5
        # 星云漂移
        for neb in self._nebula_seeds:
            neb["x"] += neb["vx"] * dt
            neb["y"] += neb["vy"] * dt
            if neb["x"] < -neb["r"]:
                neb["x"] = self._w + neb["r"]
            elif neb["x"] > self._w + neb["r"]:
                neb["x"] = -neb["r"]
            if neb["y"] < -neb["r"]:
                neb["y"] = self._h + neb["r"]
            elif neb["y"] > self._h + neb["r"]:
                neb["y"] = -neb["r"]
        # beat 触发流星 (强度高时冷却更短, 流星更多)
        self._beat_cooldown -= dt
        beat_threshold = 0.40 - self._intensity * 0.15  # 高亢时更容易触发
        if (audio.peak > beat_threshold and audio.peak > self._last_peak * 1.2
                and self._beat_cooldown <= 0 and audio.is_playing):
            self._shooting.append(_ShootingStar(self._w, self._h))
            # 高亢时同时多个流星
            if self._intensity > 0.5 and random.random() < self._intensity:
                self._shooting.append(_ShootingStar(self._w, self._h))
            self._beat_cooldown = max(0.1, 0.4 - self._intensity * 0.25)
        self._last_peak = audio.peak * 0.7 + self._last_peak * 0.3
        self._shooting = [s for s in self._shooting if s.update(dt)]
        max_shooting = 4 + int(self._intensity * 4)
        if len(self._shooting) > max_shooting:
            self._shooting = self._shooting[-max_shooting:]

    def paint(self, p: QPainter, audio: _Audio) -> None:
        intensity = self._intensity
        # 1. 极薄渐变背景 (不遮罩桌面)
        self._paint_bg(p)
        # 2. 星云 (mid + intensity 加亮)
        for neb in self._nebula_seeds:
            alpha_mult = 0.5 + audio.mid * 0.6 + intensity * 0.5
            alpha = int(neb["alpha"] * alpha_mult)
            grad = QRadialGradient(neb["x"], neb["y"], neb["r"])
            grad.setColorAt(0.0, QColor.fromHsv(neb["hue"], 120, 255, alpha))
            grad.setColorAt(1.0, QColor.fromHsv(neb["hue"], 120, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(neb["x"], neb["y"]), neb["r"], neb["r"])
        # 3. 星星
        # 闪烁速度受 treble 影响
        twinkle_speed_mult = 1.0 + audio.treble * 1.5 + intensity * 0.8
        for star in self._stars:
            self._draw_star(p, star, audio, intensity, twinkle_speed_mult)
        # 5. 流星
        for s in self._shooting:
            self._draw_shooting_star(p, s)

    def _paint_bg(self, p: QPainter) -> None:
        """星空专用背景: 中央渐变 (不遮罩桌面)"""
        t = self._t * 0.05
        # 顶部冷调光军
        grad_top = QRadialGradient(self._w * 0.5, self._h * 0.1,
                                     max(self._w, self._h) * 0.6)
        h1 = int(220 + math.sin(t) * 10) % 360
        grad_top.setColorAt(0.0, QColor.fromHsv(h1, 60, 30, 20))
        grad_top.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad_top))
        p.drawRect(0, 0, self._w, self._h)
        # 中部微弱起晕
        grad_mid = QRadialGradient(self._w * 0.5, self._h * 0.5,
                                     max(self._w, self._h) * 0.5)
        h2 = int(250 + math.cos(t * 0.7) * 10) % 360
        grad_mid.setColorAt(0.0, QColor.fromHsv(h2, 40, 18, 15))
        grad_mid.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(grad_mid))
        p.drawRect(0, 0, self._w, self._h)

    def _draw_star(self, p: QPainter, star: _Star, audio: _Audio,
                   intensity: float, twinkle_speed_mult: float) -> None:
        """画单颗星 (含巨星十字光芒)"""
        twinkle = 0.5 + 0.5 * math.sin(
            self._t * star.twinkle_speed * twinkle_speed_mult
            + star.twinkle_phase)
        # 基础亮度
        base_alpha = {0: 80, 1: 140, 2: 210}[star.layer]
        if star.is_giant:
            base_alpha = 230
        # 音乐加成: 顶层跟 mid
        music_boost = 0
        if star.layer == 2:
            music_boost = int(audio.mid * 60)
        # 强度让所有星都更亮
        intensity_mult = 0.65 + intensity * 0.55
        alpha = min(255, int((base_alpha * (0.4 + twinkle * 0.6)
                              + music_boost) * intensity_mult))
        if alpha < 1:
            return
        # 大小也跟强度
        size = star.size * (0.85 + twinkle * 0.25 + intensity * 0.3)
        cr, cg, cb = star.color
        # 光晕: 巨星 / 大星 + 闪烁高时
        if star.is_giant:
            halo_size = size * 4.5
            halo_color = QColor(cr, cg, cb, int(alpha * 0.35))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo_color))
            p.drawEllipse(QPointF(star.x, star.y), halo_size, halo_size)
        elif star.layer == 2 and twinkle > 0.65:
            halo_color = QColor(cr, cg, cb, int(alpha * 0.25))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo_color))
            p.drawEllipse(QPointF(star.x, star.y), size * 2.5, size * 2.5)
        # 主体
        body_color = QColor(cr, cg, cb, alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(body_color))
        p.drawEllipse(QPointF(star.x, star.y), size, size)
        # 巨星十字光芒 (模拟望远镜里的星)
        if star.is_giant and twinkle > 0.4:
            spike_len = size * (6 + intensity * 4)
            spike_alpha = int(alpha * 0.5 * twinkle)
            spike_color = QColor(cr, cg, cb, spike_alpha)
            pen = QPen(spike_color, 1.0)
            pen.setCosmetic(True)
            p.setPen(pen)
            # 4 角光芒
            p.drawLine(QPointF(star.x - spike_len, star.y),
                       QPointF(star.x + spike_len, star.y))
            p.drawLine(QPointF(star.x, star.y - spike_len),
                       QPointF(star.x, star.y + spike_len))
            # 对角线细光芒
            diag = spike_len * 0.5
            p.drawLine(QPointF(star.x - diag, star.y - diag),
                       QPointF(star.x + diag, star.y + diag))
            p.drawLine(QPointF(star.x - diag, star.y + diag),
                       QPointF(star.x + diag, star.y - diag))

    def _draw_shooting_star(self, p: QPainter, s: _ShootingStar) -> None:
        """画流星 (头部光晕 + 渐变尾巴 + 拖尾 sparkle)"""
        life_ratio = s.life / s.max_life
        head_alpha = int(life_ratio * 255)
        # 尾巴方向 = 速度反方向
        speed = math.hypot(s.vx, s.vy)
        if speed < 1:
            return
        tail_len = s.length * life_ratio
        tail_x = s.x - (s.vx / speed) * tail_len
        tail_y = s.y - (s.vy / speed) * tail_len
        # 尾巴渐变 (3 段: 亮白 → 蓝白 → 透明)
        grad = QLinearGradient(s.x, s.y, tail_x, tail_y)
        grad.setColorAt(0.0, QColor(*s.head_color, head_alpha))
        grad.setColorAt(0.25, QColor(*s.head_color, int(head_alpha * 0.6)))
        grad.setColorAt(0.6, QColor(*s.trail_color, int(head_alpha * 0.3)))
        grad.setColorAt(1.0, QColor(*s.trail_color, 0))
        p.setPen(QPen(QBrush(grad), 2.5,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(tail_x, tail_y), QPointF(s.x, s.y))
        # 头部核心 (亮白点)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(*s.head_color, head_alpha)))
        p.drawEllipse(QPointF(s.x, s.y), 2.8, 2.8)
        # 头部光晕
        p.setBrush(QBrush(QColor(*s.head_color, int(head_alpha * 0.45))))
        p.drawEllipse(QPointF(s.x, s.y), 6, 6)
        # 拖尾 sparkles
        for sp in s.sparkles:
            sp_alpha = int((sp["life"] / 0.7) * 200)
            sp_color = QColor(*s.trail_color, sp_alpha)
            p.setBrush(QBrush(sp_color))
            p.drawEllipse(QPointF(sp["x"], sp["y"]),
                          sp["size"], sp["size"])


# ---------------------------------------------------------------------------
# 4. 几何曼陀罗 (Mandala)
# ---------------------------------------------------------------------------
class _MandalaParticle:
    """曼陀罗爆炸粒子: 从中心向 8 角方向飞散, 拖尾渐变"""
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "hue", "size",
                 "trail_x", "trail_y")

    def __init__(self, cx: float, cy: float, angle: float, speed: float,
                 hue: int, max_life: float, size: float):
        self.x = cx
        self.y = cy
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.max_life = max_life
        self.life = max_life
        self.hue = hue
        self.size = size
        # 拖尾 (上一帧位置)
        self.trail_x = cx - self.vx * 0.04
        self.trail_y = cy - self.vy * 0.04

    def update(self, dt: float) -> bool:
        self.trail_x = self.x
        self.trail_y = self.y
        self.x += self.vx * dt
        self.y += self.vy * dt
        # 轻微减速 (粒子飞远但不会瞬间消失)
        self.vx *= 0.985
        self.vy *= 0.985
        self.life -= dt
        return self.life > 0


class _MandalaVisualizer(_BaseVisualizer):
    """呼吸式曼陀罗: 整体随音乐呼吸缩放 + 高亢时粒子炸开"""
    NAME = "mandala"
    DISPLAY_NAME = "几何曼陀罗"

    FOLD = 8

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        random.seed()
        self._intensity = 0.0
        self._breath_t = 0.0  # 呼吸相位
        self._particles: List[_MandalaParticle] = []
        self._beat_cooldown = 0.0
        self._last_peak = 0.0
        self._flash = 0.0  # 中心闪光衰减
        # 平滑旋转 (永远不顿)
        self._smooth_angle: float = 0.0  # 累计角度 (rad)
        self._smooth_speed: float = 0.12  # 当前平滑速度 (rad/s)

    def update(self, dt: float, audio: _Audio) -> None:
        super().update(dt, audio)
        # 强度追踪 (EMA 平滑)
        instant = 0.5 * audio.bass + 0.3 * audio.mid + 0.2 * audio.treble
        self._intensity = self._intensity * 0.92 + instant * 0.08
        # 呼吸速率: 舒缓 0.5Hz, 高亢 1.5Hz (辅助)
        breath_rate = 0.5 + self._intensity * 1.0
        self._breath_t += dt * breath_rate
        # === 旋转 (主动画, EMA 平滑速度, 累计角度, 永远不顿) ===
        target_speed = 0.12 + self._intensity * 0.55  # 舒缓 0.12, 高亢 0.67
        self._smooth_speed = self._smooth_speed * 0.93 + target_speed * 0.07
        self._smooth_angle += dt * self._smooth_speed
        # 中心闪光衰减
        self._flash = max(0.0, self._flash - dt * 2.5)
        # beat 检测 → 粒子爆炸
        self._beat_cooldown -= dt
        beat_threshold = 0.40 - self._intensity * 0.15
        if (audio.peak > beat_threshold and audio.peak > self._last_peak * 1.2
                and self._beat_cooldown <= 0 and audio.is_playing):
            self._spawn_explosion(audio)
            self._flash = min(1.0, 0.4 + audio.bass * 0.6)
            self._beat_cooldown = max(0.1, 0.32 - self._intensity * 0.2)
        self._last_peak = audio.peak * 0.7 + self._last_peak * 0.3
        # 更新粒子
        self._particles = [p for p in self._particles if p.update(dt)]
        # 强度高时允许更多粒子
        max_p = 30 + int(self._intensity * 70)
        if len(self._particles) > max_p:
            self._particles = self._particles[-max_p:]

    def _spawn_explosion(self, audio: _Audio) -> None:
        """从中心向 8 角 (FOLD) 方向喷出粒子"""
        cx, cy = self._w / 2, self._h / 2
        n = self.FOLD
        # 高亢时每次炸更多粒子
        per_petal = 2 + int(self._intensity * 4)  # 2-6 颗/角
        for i in range(n):
            base_angle = (i / n) * math.pi * 2
            for _ in range(per_petal):
                # 角度随机扰动 (±0.25 rad)
                angle = base_angle + random.uniform(-0.25, 0.25)
                speed = 220 + audio.bass * 380 + random.uniform(-40, 100)
                hue = (220 + i * 12 + random.randint(-15, 15)) % 360
                max_life = 0.7 + random.random() * 0.7
                size = 2.5 + audio.bass * 3.5 + random.uniform(0, 1.5)
                self._particles.append(_MandalaParticle(
                    cx, cy, angle, speed, hue, max_life, size))

    def paint(self, p: QPainter, audio: _Audio) -> None:
        cx, cy = self._w / 2, self._h / 2
        intensity = self._intensity
        max_r = min(self._w, self._h) * 0.42

        # === 1. 背景 (与星云一致，不完全遮罩桌面) ===
        self._bg_gradient(p)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # === 2. 呼吸缩放 (辅助, 幅度小, 旋转是主角) ===
        breath_main = 0.5 + 0.5 * math.sin(self._breath_t * math.pi * 2)
        scale = 0.85 + breath_main * 0.15 + intensity * 0.15
        # 各层独立相位 (有机感)
        layer_breath = [
            breath_main,
            math.sin(self._breath_t * math.pi * 2 + math.pi * 0.5) * 0.5 + 0.5,
            math.sin(self._breath_t * math.pi * 2 + math.pi) * 0.5 + 0.5,
        ]

        # === 3. 中心能量 (跟 breath + bass) ===
        center_r = max_r * 0.45 * (0.9 + breath_main * 0.25)
        center_alpha = int(50 + audio.bass * 130 + intensity * 50)
        center_grad = QRadialGradient(cx, cy, center_r)
        center_grad.setColorAt(0.0, QColor(220, 235, 255, center_alpha))
        center_grad.setColorAt(0.6, QColor(180, 200, 240, int(center_alpha * 0.4)))
        center_grad.setColorAt(1.0, QColor(150, 180, 240, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(center_grad))
        p.drawEllipse(QPointF(cx, cy), center_r, center_r)

        # === 4. 花瓣 (3 层, 每层独立 breath, 整体随 scale 缩放) ===
        n_petals = self.FOLD
        for layer in range(3):
            # 每层基础半径受 scale + 自身 breath 影响
            layer_r = max_r * (0.3 + layer * 0.22) * scale \
                * (0.9 + layer_breath[layer] * 0.18)
            size_mult = 1.0 + audio.bass * 0.3 + intensity * 0.35
            for i in range(n_petals):
                # 角度: 用累计 _smooth_angle (永远平滑), 每层不同方向
                layer_dir = [1.0, -0.65, 0.45][layer]
                angle = (i / n_petals) * math.pi * 2 \
                    + self._smooth_angle * layer_dir
                petal_w = layer_r * 0.18
                petal_h = layer_r * 0.55 * size_mult
                color_hue = (220 + layer * 25 + i * 6) % 360
                sat = 150 + int(intensity * 70)
                if layer == 2:
                    color_alpha = int(40 + audio.treble * 110 + intensity * 50)
                else:
                    color_alpha = int(45 + audio.bass * 70 + audio.mid * 35
                                      + intensity * 30)
                color = QColor.fromHsv(color_hue, sat, 255, color_alpha)
                p.save()
                p.translate(cx, cy)
                p.rotate(math.degrees(angle))
                ellipse_grad = QRadialGradient(0, -petal_h * 0.5, petal_h)
                ellipse_grad.setColorAt(0.0, color)
                ellipse_grad.setColorAt(1.0,
                                        QColor.fromHsv(color_hue, sat, 255, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(ellipse_grad))
                p.drawEllipse(QPointF(0, -petal_h * 0.5), petal_w, petal_h)
                p.restore()

        # === 5. 外环 (整体缩放) ===
        outer_r = max_r * (0.95 + audio.bass * 0.12 + intensity * 0.18) * scale
        for i in range(n_petals * 2):
            angle = (i / (n_petals * 2)) * math.pi * 2
            r1 = outer_r * 0.92
            r2 = outer_r * 1.0
            x1 = cx + math.cos(angle) * r1
            y1 = cy + math.sin(angle) * r1
            x2 = cx + math.cos(angle) * r2
            y2 = cy + math.sin(angle) * r2
            color = QColor.fromHsv(
                (220 + i * 10) % 360,
                170 + int(intensity * 50),
                255,
                int(70 + audio.treble * 90 + intensity * 60))
            pen = QPen(color)
            pen.setWidthF(1.5 + intensity * 1.2)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # === 6. 粒子 (z-order 最高, 画在最后) ===
        for particle in self._particles:
            self._draw_particle(p, particle)

        # === 7. 中心闪光 (beat 触发) ===
        if self._flash > 0.01:
            flash_alpha = int(self._flash * 220)
            flash_color = QColor(240, 250, 255, flash_alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(flash_color))
            p.drawEllipse(QPointF(cx, cy), 15, 15)
            # 外圈柔光
            halo_alpha = int(self._flash * 80)
            p.setBrush(QBrush(QColor(200, 220, 255, halo_alpha)))
            p.drawEllipse(QPointF(cx, cy), 35, 35)

        # === 8. 中心点 (跟 bass + intensity) ===
        center_dot_alpha = int(200 + audio.bass * 55)
        center_dot_size = 6 + audio.bass * 4 + intensity * 4
        p.setBrush(QBrush(QColor(220, 235, 255, center_dot_alpha)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), center_dot_size, center_dot_size)

    def _draw_particle(self, p: QPainter, particle: _MandalaParticle) -> None:
        """画粒子 (拖尾渐变线 + 光晕 + 主体)"""
        life_ratio = particle.life / particle.max_life
        alpha = int(life_ratio * 255)
        cr, cg, cb = QColor.fromHsv(particle.hue, 200, 255).getRgb()[:3]
        # 拖尾 (从 trail 位置到当前位置的渐变线)
        tail_color = QColor(cr, cg, cb, int(alpha * 0.5))
        head_color = QColor(cr, cg, cb, alpha)
        grad = QLinearGradient(QPointF(particle.trail_x, particle.trail_y),
                                QPointF(particle.x, particle.y))
        grad.setColorAt(0.0, QColor(cr, cg, cb, 0))
        grad.setColorAt(1.0, head_color)
        pen = QPen(QBrush(grad), particle.size * 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(particle.trail_x, particle.trail_y),
                    QPointF(particle.x, particle.y))
        # 外光晕
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(cr, cg, cb, int(alpha * 0.35))))
        p.drawEllipse(QPointF(particle.x, particle.y),
                       particle.size * 2.5, particle.size * 2.5)
        # 主体
        p.setBrush(QBrush(head_color))
        p.drawEllipse(QPointF(particle.x, particle.y),
                       particle.size, particle.size)


# ---------------------------------------------------------------------------
# 5. 歌词飘字流 (Lyrics Stream) — 方案 2
# ---------------------------------------------------------------------------
class _LyricsStreamVisualizer(_BaseVisualizer):
    """当前行居中呼吸, 切行时旧行上飘+新行下飘入, 背景有微光点"""
    NAME = "lyrics_stream"
    DISPLAY_NAME = "歌词·飘字流"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        random.seed()
        self._prev_text: str = ""
        self._current_text: str = ""
        self._next_text: str = ""
        self._transition_t: float = 1.0  # 0=刚开始, 1=稳定
        self._last_idx: int = -999
        self._breath_t: float = 0.0
        # 字体缓存 (避免每帧创建 QFont)
        self._font_cache: Dict[int, QFont] = {}
        self._font_family = "Microsoft YaHei UI"
        # 背景装饰光点
        self._bg_particles: List[Dict[str, float]] = []
        for _ in range(50):
            self._bg_particles.append({
                "x": random.uniform(0, w),
                "y": random.uniform(0, h),
                "size": random.uniform(0.4, 1.6),
                "alpha": random.uniform(0.25, 0.55),
                "speed": random.uniform(4, 14),
                "phase": random.uniform(0, math.pi * 2),
            })

    def update(self, dt: float, audio: _Audio) -> None:
        super().update(dt, audio)
        self._breath_t += dt
        # 行切换
        if audio.lyric_idx != self._last_idx:
            self._last_idx = audio.lyric_idx
            self._prev_text = self._current_text
            if 0 <= audio.lyric_idx < len(audio.lyrics):
                self._current_text = audio.lyrics[audio.lyric_idx].text
            else:
                self._current_text = ""
            if 0 <= audio.lyric_idx + 1 < len(audio.lyrics):
                self._next_text = audio.lyrics[audio.lyric_idx + 1].text
            else:
                self._next_text = ""
            self._transition_t = 0.0
        # 推进过渡动画 (0 -> 1)
        if self._transition_t < 1.0:
            self._transition_t += dt * 1.6  # 约 0.62s
            if self._transition_t >= 1.0:
                self._transition_t = 1.0
                self._prev_text = ""
        # 背景光点向上飘
        for pt in self._bg_particles:
            pt["y"] -= dt * pt["speed"]
            if pt["y"] < -8:
                pt["y"] = self._h + 8
                pt["x"] = random.uniform(0, self._w)

    def _get_cached_font(self, size: int, bold: bool) -> QFont:
        """缓存 QFont, 避免每帧创建"""
        key = (size, bold)
        if key not in self._font_cache:
            font = QFont(self._font_family, size)
            font.setBold(bold)
            self._font_cache[key] = font
        return self._font_cache[key]

    def paint(self, p: QPainter, audio: _Audio) -> None:
        p.fillRect(0, 0, self._w, self._h, QColor(4, 6, 16, 240))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 1. 背景光点
        for pt in self._bg_particles:
            twinkle = 0.5 + 0.5 * math.sin(self._breath_t * 1.3 + pt["phase"])
            alpha = int(pt["alpha"] * 255 * (0.4 + twinkle * 0.6))
            color = QColor(180, 210, 255, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["size"], pt["size"])
        # 2. 上一行 (上浮+淡出)
        if self._prev_text and self._transition_t < 1.0:
            y_off = -int(self._h * 0.06 * self._transition_t)
            alpha = int(180 * (1 - self._transition_t))
            self._draw_text(p, self._prev_text,
                            y_center=self._h * 0.42 + y_off,
                            size=int(self._h * 0.022),
                            color=QColor(220, 240, 255, alpha),
                            bold=False)
        # 3. 当前行 (居中+呼吸)
        if self._current_text:
            breath = 0.5 + 0.5 * math.sin(self._breath_t * 1.3)
            scale = 1.0 + breath * 0.05
            self._draw_text(p, self._current_text,
                            y_center=self._h * 0.5,
                            size=int(self._h * 0.038 * scale),
                            color=QColor(220, 240, 255, 51),
                            bold=True)
        else:
            self._draw_text(p, "♪ 等待播放...",
                            y_center=self._h * 0.5,
                            size=int(self._h * 0.02),
                            color=QColor(220, 240, 255, 36),
                            bold=False)
        # 4. 下一行 (从下方飘入)
        if self._next_text and self._transition_t < 1.0:
            y_off = int(self._h * 0.06 * (1 - self._transition_t))
            alpha = int(180 * self._transition_t)
            self._draw_text(p, self._next_text,
                            y_center=self._h * 0.58 + y_off,
                            size=int(self._h * 0.022),
                            color=QColor(220, 240, 255, alpha),
                            bold=False)

    def _draw_text(self, p: QPainter, text: str, y_center: float,
                   size: int, color: QColor, bold: bool) -> None:
        font = self._get_cached_font(size, bold)
        p.setFont(font)
        # 飘字流整体透明度 10%
        dim = QColor(color)
        dim.setAlpha(int(color.alpha() * 0.1))
        p.setPen(QPen(dim))
        fm = QFontMetrics(font)
        max_w = self._w * 0.85
        if fm.horizontalAdvance(text) > max_w:
            text = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(max_w))
        # 垂直居中绘制
        rect = QRectF(0, y_center - size / 2, self._w, size * 1.2)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def paint_no_bg(self, p: QPainter, audio: _Audio) -> None:
        """不画黑色背景，直接叠加歌词"""
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 1. 背景光点
        for pt in self._bg_particles:
            twinkle = 0.5 + 0.5 * math.sin(self._breath_t * 1.3 + pt["phase"])
            alpha = int(pt["alpha"] * 255 * (0.4 + twinkle * 0.6))
            color = QColor(180, 210, 255, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["size"], pt["size"])
        # 2. 上一行
        if self._prev_text and self._transition_t < 1.0:
            y_off = -int(self._h * 0.06 * self._transition_t)
            alpha = int(180 * (1 - self._transition_t))
            self._draw_text(p, self._prev_text,
                            y_center=self._h * 0.42 + y_off,
                            size=int(self._h * 0.022),
                            color=QColor(220, 240, 255, alpha),
                            bold=False)
        # 3. 当前行
        if self._current_text:
            breath = 0.5 + 0.5 * math.sin(self._breath_t * 1.3)
            scale = 1.0 + breath * 0.05
            self._draw_text(p, self._current_text,
                            y_center=self._h * 0.5,
                            size=int(self._h * 0.038 * scale),
                            color=QColor(220, 240, 255, 51),
                            bold=True)
        else:
            self._draw_text(p, "♪ 等待播放...",
                            y_center=self._h * 0.5,
                            size=int(self._h * 0.02),
                            color=QColor(220, 240, 255, 36),
                            bold=False)
        # 4. 下一行
        if self._next_text and self._transition_t < 1.0:
            y_off = int(self._h * 0.06 * (1 - self._transition_t))
            alpha = int(180 * self._transition_t)
            self._draw_text(p, self._next_text,
                            y_center=self._h * 0.58 + y_off,
                            size=int(self._h * 0.022),
                            color=QColor(220, 240, 255, alpha),
                            bold=False)


# ---------------------------------------------------------------------------
# 6. 歌词粒子字 (Lyrics Particle) — 方案 4
# ---------------------------------------------------------------------------
class _CharParticle:
    """单字符粒子: flying_in -> active -> consumed"""
    __slots__ = ("char", "target_x", "target_y", "x", "y",
                 "state", "fly_t", "alpha",
                 "char_idx", "total_chars", "progress_threshold", "phase",
                 "baseline_y", "_exploded", "_explode_t")

    def __init__(self, char: str, target_x: float, target_y: float,
                 baseline_y: float, char_idx: int, total_chars: int):
        self.char = char
        self.target_x = target_x
        self.target_y = target_y
        self.x = target_x
        self.y = target_y
        self.baseline_y = baseline_y
        self.state = "flying_in"
        self.fly_t = 0.0
        self.alpha = 0.0
        self.char_idx = char_idx
        self.total_chars = total_chars
        self.progress_threshold = char_idx / max(total_chars, 1)
        self.phase = random.uniform(0, math.pi * 2)


class _ExplosionParticle:
    """字符爆开的碎片"""
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "hue")

    def __init__(self, x: float, y: float, hue_base: int):
        self.x = x
        self.y = y
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(60, 220)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.max_life = random.uniform(0.5, 1.0)
        self.life = self.max_life
        self.size = random.uniform(0.6, 1.8)
        self.hue = (hue_base + random.randint(-15, 15)) % 360


class _LyricsParticleVisualizer(_BaseVisualizer):
    """歌词粒子字: 字符从中心飞入, 唱过时爆成粒子"""
    NAME = "lyrics_particle"
    DISPLAY_NAME = "歌词·粒子字"

    FLY_DURATION = 0.55  # 字符从中心飞入时间

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        random.seed()
        self._chars: List[_CharParticle] = []
        self._explosions: List[_ExplosionParticle] = []
        self._last_idx: int = -999
        self._cx: float = w / 2
        self._cy: float = h / 2
        self._font_family = "Microsoft YaHei UI"
        # 字体缓存
        self._font_size: int = int(h * 0.035)
        self._font = QFont(self._font_family, self._font_size)
        self._font.setBold(True)
        self._fm = QFontMetrics(self._font)
        self._current_font = self._font

    def update(self, dt: float, audio: _Audio) -> None:
        super().update(dt, audio)
        # 行切换
        if audio.lyric_idx != self._last_idx:
            # 旧行全部爆散成粒子 (0.6s 动画)
            for cp in self._chars:
                if cp.state == "active" and not getattr(cp, '_exploded', False):
                    cp._exploded = True
                    cp._explode_t = 0.0
                    self._spawn_explosion(cp.x, cp.baseline_y,
                                            180 + cp.char_idx * 18)
            self._last_idx = audio.lyric_idx
            # 新行
            if 0 <= audio.lyric_idx < len(audio.lyrics):
                self._setup_new_line(audio.lyrics[audio.lyric_idx].text)
            else:
                self._chars = []
        # 行内进度
        if 0 <= audio.lyric_idx < len(audio.lyrics):
            line_start = audio.lyrics[audio.lyric_idx].time_sec
            if 0 <= audio.lyric_idx + 1 < len(audio.lyrics):
                line_end = audio.lyrics[audio.lyric_idx + 1].time_sec
            elif audio.duration_sec > line_start:
                line_end = audio.duration_sec
            else:
                line_end = line_start + 4.0
            line_dur = max(line_end - line_start, 0.5)
            line_progress = max(0.0, (audio.position_sec - line_start) / line_dur)
        else:
            line_progress = 0.0
        # 更新字符
        for cp in self._chars:
            if cp.state == "flying_in":
                cp.fly_t += dt / self.FLY_DURATION
                t = min(1.0, cp.fly_t)
                # ease out cubic
                t_eased = 1.0 - (1.0 - t) ** 3
                cp.x = self._cx + (cp.target_x - self._cx) * t_eased
                cp.y = self._cy + (cp.target_y - self._cy) * t_eased
                cp.alpha = t
                if cp.fly_t >= 1.0:
                    cp.state = "active"
                    cp.x = cp.target_x
                    cp.y = cp.target_y
                    cp.alpha = 1.0
            elif cp.state == "active":
                # 整句爆散: 切行时已标记 _exploded=True
                if getattr(cp, '_exploded', False):
                    cp._explode_t += dt
                    t = cp._explode_t / 0.6
                    if t < 1.0:
                        # 上浮 + 摇曳
                        cp.y = cp.baseline_y - t * 18
                        cp.x += math.sin(cp._explode_t * 22 + cp.phase) * 1.2
                        cp.alpha = 1.0 - t
                    else:
                        cp.state = "consumed"
                        cp.alpha = 0.0
        # 更新爆炸粒子
        for ep in self._explosions:
            ep.x += ep.vx * dt
            ep.y += ep.vy * dt
            ep.vx *= 0.95
            ep.vy *= 0.95
            ep.life -= dt
        self._explosions = [e for e in self._explosions if e.life > 0]
        if len(self._explosions) > 200:
            self._explosions = self._explosions[-200:]

    def _setup_new_line(self, text: str) -> None:
        if not text:
            self._chars = []
            return
        # 计算每个字符的宽度和目标位置
        font = QFont(self._font_family, self._font_size)
        font.setBold(True)
        fm = QFontMetrics(font)
        widths = [fm.horizontalAdvance(c) for c in text]
        spacing = max(int(self._h * 0.012), 4)
        total_w = sum(widths) + spacing * (len(text) - 1)
        # 太长则缩放字体
        actual_font = font
        if total_w > self._w * 0.85:
            scale = (self._w * 0.85) / total_w
            scaled_size = max(8, int(self._font_size * scale))
            actual_font = QFont(self._font_family, scaled_size)
            actual_font.setBold(True)
            fm = QFontMetrics(actual_font)
            widths = [fm.horizontalAdvance(c) for c in text]
            spacing = max(int(spacing * scale), 2)
            total_w = sum(widths) + spacing * (len(text) - 1)
        start_x = (self._w - total_w) / 2
        # baseline 居中
        center_y = self._h / 2
        baseline_y = center_y - fm.ascent() / 2
        self._chars = []
        x = start_x
        for i, c in enumerate(text):
            target_x = x + widths[i] / 2
            target_y = center_y
            cp = _CharParticle(c, target_x, target_y, baseline_y, i, len(text))
            cp.x = self._cx
            cp.y = self._cy
            self._chars.append(cp)
            x += widths[i] + spacing
        # 保存 current font/fm
        self._current_font = actual_font

    def _spawn_explosion(self, x: float, y: float, hue_base: int) -> None:
        n = random.randint(8, 12)
        for _ in range(n):
            self._explosions.append(_ExplosionParticle(x, y, hue_base))

    def paint(self, p: QPainter, audio: _Audio) -> None:
        p.fillRect(0, 0, self._w, self._h, QColor(4, 6, 16, 240))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 1. 字符粒子
        if self._chars:
            font = getattr(self, "_current_font", self._font)
            for cp in self._chars:
                if cp.state == "consumed":
                    continue
                alpha = int(cp.alpha * 255)
                # 字符 (整体透明度 20%)
                alpha = int(alpha * 0.2)
                color = QColor(220, 240, 255, alpha)
                p.setFont(font)
                p.setPen(QPen(color))
                tw = QFontMetrics(font).horizontalAdvance(cp.char)
                p.drawText(QPointF(cp.x - tw / 2, cp.baseline_y), cp.char)
        # 2. 爆炸粒子
        for ep in self._explosions:
            life_ratio = ep.life / ep.max_life
            alpha = int(life_ratio * 255)
            color = QColor.fromHsv(ep.hue, 200, 255, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(ep.x, ep.y), ep.size, ep.size)
        # 3. 没歌词
        if not self._chars and not self._explosions:
            p.setFont(QFont(self._font_family, int(self._h * 0.02)))
            p.setPen(QPen(QColor(220, 240, 255, 36)))
            text = "♪ 等待播放..."
            fm = QFontMetrics(p.font())
            tw = fm.horizontalAdvance(text)
            baseline_y = self._h / 2 - fm.ascent() / 2
            p.drawText(QPointF((self._w - tw) / 2, baseline_y), text)

    def paint_no_bg(self, p: QPainter, audio: _Audio) -> None:
        """不画黑色背景，直接叠加歌词"""
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._chars:
            font = getattr(self, "_current_font", self._font)
            for cp in self._chars:
                if cp.state == "consumed":
                    continue
                alpha = int(cp.alpha * 255)
                if alpha < 5:
                    continue
                alpha = int(alpha * 0.2)
                color = QColor(220, 240, 255, alpha)
                p.setFont(font)
                p.setPen(QPen(color))
                tw = QFontMetrics(font).horizontalAdvance(cp.char)
                p.drawText(QPointF(cp.x - tw / 2, cp.baseline_y), cp.char)
        for ep in self._explosions:
            life_ratio = ep.life / ep.max_life
            alpha = int(life_ratio * 255)
            color = QColor.fromHsv(ep.hue, 200, 255, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(ep.x, ep.y), ep.size, ep.size)
        if not self._chars and not self._explosions:
            p.setFont(QFont(self._font_family, int(self._h * 0.02)))
            p.setPen(QPen(QColor(220, 240, 255, 36)))
            text = "♪ 等待播放..."
            fm = QFontMetrics(p.font())
            tw = fm.horizontalAdvance(text)
            baseline_y = self._h / 2 - fm.ascent() / 2
            p.drawText(QPointF((self._w - tw) / 2, baseline_y), text)


# ---------------------------------------------------------------------------
# Manager — DesktopBackground
# ---------------------------------------------------------------------------
class DesktopBackground(QWidget):
    """音频律动全屏背景层 - 6 种动效可切换"""

    VISUALIZERS = {
        _NebulaOrbVisualizer.NAME: _NebulaOrbVisualizer,
        _StarfieldVisualizer.NAME: _StarfieldVisualizer,
        _MandalaVisualizer.NAME: _MandalaVisualizer,
    }

    DEFAULT_NAME = _NebulaOrbVisualizer.NAME

    def __init__(self, parent=None):
        super().__init__(parent)

        # 窗口标志 — 最底层、不抢焦点、不在任务栏
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 覆盖整个虚拟桌面
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.virtualGeometry()
        self.setGeometry(geo)
        self._w = geo.width()
        self._h = geo.height()

        # Windows 生效: 手动加 WS_EX_TRANSPARENT
        if sys.platform == "win32":
            try:
                import ctypes
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT)
            except Exception:
                pass

        # 音频
        from cards.music_card import audio_viz
        audio_viz.start()
        self._audio = audio_viz

        # 动效
        self._current_name: str = self.DEFAULT_NAME
        self._current: _BaseVisualizer = self.VISUALIZERS[self.DEFAULT_NAME](
            self._w, self._h)

        # 歌词动效层 (初始无)
        self._lyrics_fx: Optional[LyricsFX] = None

        # 时间
        self._last_time = time.time()

        # 60fps 主循环
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(16)

    # === 动效切换接口 ===
    def set_visualizer(self, name: str) -> bool:
        """切换动效, 成功返回 True"""
        if name not in self.VISUALIZERS:
            return False
        if name == self._current_name:
            return True
        self._current_name = name
        self._current = self.VISUALIZERS[name](self._w, self._h)
        return True

    def current_visualizer(self) -> str:
        return self._current_name

    def available_visualizers(self) -> List[str]:
        return list(self.VISUALIZERS.keys())

    def display_name(self, internal: str) -> str:
        cls = self.VISUALIZERS.get(internal)
        return cls.DISPLAY_NAME if cls else internal

    # === 歌词动效层引用 ===
    def set_lyrics_fx(self, lyrics_fx: Optional[LyricsFX]) -> None:
        """设置歌词动效层引用 (用于叠加绘制)"""
        self._lyrics_fx = lyrics_fx

    def _paint_lyrics_overlay(self, p: QPainter, audio: _Audio) -> None:
        """如果歌词动效层开启了, 叠加绘制歌词"""
        if not hasattr(self, "_lyrics_fx") or self._lyrics_fx is None:
            return
        if not self._lyrics_fx.enabled:
            return
        self._lyrics_fx.paint(p, audio)

    # === 主循环 ===
    def _on_tick(self) -> None:
        now = time.time()
        dt = min(now - self._last_time, 0.1)
        self._last_time = now

        audio = _read_audio(self._audio)
        self._current.update(dt, audio)
        # 同步更新歌词层 (避免滞后)
        if hasattr(self, '_lyrics_fx') and self._lyrics_fx and self._lyrics_fx.enabled:
            self._lyrics_fx.update(dt, audio)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 重要: 先清空 backing pixmap 为透明, 避免上一帧的像素残留导致切换动效后变黑
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver)
        audio = _read_audio(self._audio)
        self._current.paint(painter, audio)
        # 叠加歌词动效层
        self._paint_lyrics_overlay(painter, audio)
        painter.end()

    def stop(self) -> None:
        self._timer.stop()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# 歌词动效层 (LyricsFX) — 独立可叠加
# ---------------------------------------------------------------------------
class LyricsFX:
    """歌词动效层

    管理飘字流 / 粒子字两种歌词动效，独立于桌面背景层。
    由 DesktopBackground 在 paintEvent 中叠加绘制。

    托盘菜单: 歌词动效 (off / 飘字流 / 粒子字)
    快捷键: Ctrl+Alt+L 切换开关
    """

    LYRICS_VISUALIZERS = {
        "lyrics_stream": _LyricsStreamVisualizer,
        "lyrics_particle": _LyricsParticleVisualizer,
    }

    def __init__(self, w: int, h: int):
        self._w = w
        self._h = h
        self.enabled: bool = False
        self._current_name: str = "lyrics_stream"
        self._visualizer: Optional[_BaseVisualizer] = None
        self._create_visualizer()

    def _create_visualizer(self) -> None:
        cls = self.LYRICS_VISUALIZERS.get(self._current_name)
        if cls:
            self._visualizer = cls(self._w, self._h)
        else:
            self._visualizer = None

    def resize(self, w: int, h: int) -> None:
        self._w = w
        self._h = h
        if self._visualizer:
            self._visualizer.resize(w, h)

    def toggle(self) -> None:
        """切换开关"""
        self.enabled = not self.enabled

    def set_mode(self, name: str) -> bool:
        """切换歌词动效模式"""
        if name not in self.LYRICS_VISUALIZERS:
            return False
        self._current_name = name
        self._create_visualizer()
        return True

    def current_mode(self) -> str:
        return self._current_name

    def available_modes(self) -> List[str]:
        return list(self.LYRICS_VISUALIZERS.keys())

    def display_name(self, internal: str) -> str:
        cls = self.LYRICS_VISUALIZERS.get(internal)
        return cls.DISPLAY_NAME if cls else internal

    def update(self, dt: float, audio: _Audio) -> None:
        if self._visualizer:
            self._visualizer.update(dt, audio)

    def paint(self, p: QPainter, audio: _Audio) -> None:
        """叠加绘制歌词动效（半透明覆盖）"""
        if not self.enabled or not self._visualizer:
            return
        # 不画背景遮罩，直接在桌面背景上叠加歌词
        self._visualizer.paint_no_bg(p, audio)

    def stop(self) -> None:
        pass
