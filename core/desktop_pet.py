"""小紫 Desktop Pet v0.7 — 矢量版 (v1, 无 sprite 资源)

视觉: 银瀑长发 + 紫瞳 + 仙侠冷淡感 + 半透面纱 + 蓝色发饰
尺寸: 96x96
行为:
  - 闲置: 缓慢上下浮动 + 头发轻摇 + 随机眨眼
  - 悬停: 眼睛跟随鼠标方向, 头微转
  - 点击: 弹出小气泡 (随机台词)
  - 音乐播放: 头发随节拍跳, 偶尔发"灵力"粒子
  - 拖动: 跟随鼠标, 松开吸附到最近的屏幕边缘

不依赖外部 sprite — 纯 QPainter 绘制, 后续可替换为 AIGC 角色图。
"""
from __future__ import annotations

import math
import random
import time
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QPoint
from PyQt6.QtGui import (QPixmap, QPainter, QColor, QLinearGradient, QRadialGradient,
                         QBrush, QPen, QPainterPath, QGuiApplication, QFont)
from PyQt6.QtWidgets import QWidget


# ---------------------------------------------------------------------------
# 粒子 (头发/灵力粒子)
# ---------------------------------------------------------------------------
class _Sparkle:
    __slots__ = ("x", "y", "vx", "vy", "size", "life", "max_life", "hue")

    def __init__(self, x: float, y: float, hue: float):
        self.x = x
        self.y = y
        self.vx = random.uniform(-0.4, 0.4)
        self.vy = random.uniform(-0.6, -0.2)
        self.size = random.uniform(1.0, 2.2)
        self.max_life = random.uniform(0.4, 0.8)
        self.life = self.max_life
        self.hue = hue

    def update(self, dt: float) -> bool:
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.005  # 微重力
        self.life -= dt * 1.4
        return self.life > 0


# ---------------------------------------------------------------------------
# SpriteSheet - 动画播放器
# ---------------------------------------------------------------------------
class _SpriteSheet:
    """Petdex codex 格式: 1536x1872 = 8 列 x 9 行, cell 192x208
    行定义: 0=idle(6帧) 1=running-right 2=running-left 3=waving(4)
            4=jumping 5=failed 6=waiting 7=running 8=review
    """
    COLS = 8
    ROWS = 9
    CELL_W = 192
    CELL_H = 208

    # 每行帧数 (按 codex 规范, 不够的填 0 表示空)
    ROW_FRAMES = {
        0: 6,  # idle
        1: 8,  # running-right
        2: 8,  # running-left
        3: 4,  # waving
        4: 5,  # jumping
        5: 8,  # failed
        6: 6,  # waiting
        7: 6,  # running
        8: 6,  # review
    }

    def __init__(self, sheet: QPixmap):
        self.sheet = sheet
        # 预裁剪各行到 QPixmap 列表
        self.frames: Dict[int, List[QPixmap]] = {}
        for row, n in self.ROW_FRAMES.items():
            self.frames[row] = []
            for col in range(n):
                px = sheet.copy(col * self.CELL_W, row * self.CELL_H,
                                 self.CELL_W, self.CELL_H)
                self.frames[row].append(px)

    def get_frame(self, row: int, col: int) -> QPixmap:
        if row not in self.frames:
            return self.frames[0][0]
        frames = self.frames[row]
        if col >= len(frames):
            col = col % len(frames)
        return frames[col]


# ---------------------------------------------------------------------------
# Pet
# ---------------------------------------------------------------------------
class DesktopPet(QWidget):
    SIZE = 128       # 单帧渲染尺寸 (192 的 2/3)
    BUBBLE_H = 24    # 气泡预留区高度 (上方, 按比例缩小)

    # 可用角色列表 (key, 显示名, sprite sheet 文件名, 默认 row)
    CHARACTERS = [
        ("chen_qianyu",  "陈千语",     "chen-qianyu_sheet.png",       0),
        ("wang_lin",     "问鼎王林",   "wang-lin-wending-pixel_sheet.png", 0),
        ("xiyue",        "汐月同学",   "xiyue_sheet.png",              0),
        ("yunyun",       "晕晕",       "yunyun_sheet.png",             0),
        ("lian",         "Lian",       "lian_sheet.png",               0),
    ]

    # 随机台词 (可放 yaml 配置, 暂写死)
    BUBBLE_LINES = [
        "主人好呀",
        "今天深圳下雨哦",
        "音乐好听吗？",
        "别忘了喝水",
        "月色真美",
        "再忙也要休息",
        "加油~",
        "...",
        "夜深了，早点睡",
        "工作顺利吗",
        "吃点东西吧",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        # 窗口: 无边框、置顶、tool (不抢任务栏)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.resize(self.SIZE, self.SIZE + self.BUBBLE_H)

        # 加载所有角色的 sprite sheet (1536x1872 Petdex codex 格式)
        from pathlib import Path
        _here = Path(__file__).parent.parent
        _assets = _here / "assets" / "pet"
        self._sheets: Dict[str, _SpriteSheet] = {}
        self._default_pixmap = QPixmap(self.SIZE, self.SIZE)
        self._default_pixmap.fill(QColor(60, 40, 80, 255))
        for key, _name, fname, _row in self.CHARACTERS:
            path = _assets / fname
            if path.exists():
                sheet_img = QPixmap(str(path))
                self._sheets[key] = _SpriteSheet(sheet_img)
                print(f"[pet] loaded {key}: {fname} ({sheet_img.size().width()}x{sheet_img.size().height()})")
            else:
                print(f"[pet] MISSING {key}: {path}")

        # 动画状态
        self._current_char = ""  # 当前角色 key
        self._current_row = 0    # 当前 sprite row (动画状态)
        self._current_frame = 0  # 当前帧
        self._frame_time = 0.0   # 当前帧累计时间
        self._action_timer = 0.0 # 随机动作计时

        # 屏幕右下角 (留 30px 边距)
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        self._home_x = avail.right() - self.SIZE - 30
        self._home_y = avail.bottom() - self.SIZE - 30
        self.move(self._home_x, self._home_y)

        # 状态机
        self._state = "idle"  # idle / hover / click / drag
        self._t = 0.0
        self._last_time = time.time()
        self._blink_cd = random.uniform(2.0, 4.5)
        self._blinking = False
        self._blink_time = 0.0
        self._head_tilt = 0.0  # 弧度
        self._hair_phase = 0.0
        self._hover = False
        self._float_y = 0.0
        self._float_x = 0.0
        self._breath = 1.0

        # 气泡
        self._bubble_text = ""
        self._bubble_time = 0.0
        self._bubble_alpha = 0.0
        self._bubble_showing = False

        # 拖动
        self._drag_active = False
        self._drag_offset: Optional[QPoint] = None
        self._docked_edge = "br"  # br/bl/tr/tl (默认右下)

        # 灵力粒子
        self._sparkles: List[_Sparkle] = []

        # 音频
        from cards.music_card import audio_viz
        audio_viz.start()
        self._audio = audio_viz
        self._last_peak = 0.0
        self._beat_pulse = 0.0

        # 动画
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(50)  # 20fps

    # ==================================================================
    # 主循环
    # ==================================================================
    def _on_tick(self) -> None:
        now = time.time()
        dt = min(now - self._last_time, 0.1)
        self._last_time = now
        self._t += dt

        # 闲置浮动 (加大幅度 + 微横向漂移)
        self._float_y = math.sin(self._t * 1.8) * 8.0
        self._float_x = math.sin(self._t * 1.3) * 2.5
        # 呼吸缩放 (持续, 不依赖音乐)
        self._breath = math.sin(self._t * 1.4) * 0.025 + 1.0
        # 头发相位
        self._hair_phase += dt * 0.9

        # 眨眼
        self._blink_cd -= dt
        if self._blinking:
            self._blink_time += dt
            if self._blink_time > 0.12:
                self._blinking = False
                self._blink_cd = random.uniform(2.5, 5.0)
                self._blink_time = 0.0
        elif self._blink_cd <= 0 and not self._hover:
            self._blinking = True

        # 音频节拍
        peak = self._audio.get_peak()
        if peak > self._last_peak + 0.08 and peak > 0.25:
            self._beat_pulse = 1.0
            # 节拍时偶尔放灵力
            if random.random() < 0.3:
                self._emit_sparkle()
        self._beat_pulse *= 0.85
        self._last_peak = peak

        # 灵力更新
        self._sparkles = [s for s in self._sparkles if s.update(dt)]
        if len(self._sparkles) > 18:
            self._sparkles = self._sparkles[-18:]

        # Sprite sheet 动画推进
        self._advance_animation(dt)

        # 气泡
        if self._bubble_showing:
            self._bubble_time -= dt
            self._bubble_alpha = min(1.0, self._bubble_alpha + dt * 4)
            if self._bubble_time <= 0:
                self._bubble_showing = False
        else:
            self._bubble_alpha = max(0.0, self._bubble_alpha - dt * 4)

        # 应用浮动偏移
        if not self._drag_active:
            self.move(self._home_x + int(self._float_x), self._home_y + int(self._float_y))

        self.update()

    def _emit_sparkle(self) -> None:
        # 从头顶附近散出 (192 尺寸下从肩部上方), BUBBLE_H 是气泡预留偏移
        for _ in range(2):
            sx = self.SIZE * 0.5 + random.uniform(-16, 16)
            sy = self.BUBBLE_H + self.SIZE * 0.30 + random.uniform(-8, 8)
            hue = random.uniform(200, 290)
            self._sparkles.append(_Sparkle(sx, sy, hue))

    # ==================================================================
    # 鼠标事件
    # ==================================================================
    def enterEvent(self, event):
        self._hover = True

    def leaveEvent(self, event):
        self._hover = False
        self._head_tilt = 0.0

    def mouseMoveEvent(self, event):
        if self._drag_active and self._drag_offset is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
        else:
            # 头转向鼠标方向 (考虑 BUBBLE_H 偏移, 贴图中心在 cy = BUBBLE_H + SIZE/2)
            local = event.position()
            cx = self.SIZE / 2
            cy_pet = self.BUBBLE_H + self.SIZE / 2
            dx = local.x() - cx
            dy = local.y() - cy_pet
            if abs(dx) > 4 and abs(dy) < self.SIZE * 0.4:
                self._head_tilt = math.copysign(0.15, dx)
            elif abs(dx) > 4:
                # 鼠标在气泡区时也响应但幅度小
                self._head_tilt = math.copysign(0.08, dx)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._drag_offset = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_active:
            self._drag_active = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._dock_to_edge()
            # 弹个气泡
            self._show_bubble(random.choice(self.BUBBLE_LINES))
            # 点击 → waving 动作 (row 3, 4 帧)
            self._current_row = 3
            self._current_frame = 0
            self._frame_time = 0.0
            self._action_timer = 0.0

    def _dock_to_edge(self) -> None:
        """吸附到最近的屏幕边缘"""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x, y = self.x(), self.y()
        # 找最近的边缘
        dist_left = x - avail.left()
        dist_right = avail.right() - (x + self.SIZE)
        dist_top = y - avail.top()
        dist_bottom = avail.bottom() - (y + self.SIZE)
        min_d = min(dist_left, dist_right, dist_top, dist_bottom)
        margin = 20
        if min_d == dist_left:
            self._home_x = avail.left() + margin
            self._home_y = max(avail.top() + margin,
                               min(y, avail.bottom() - self.SIZE - margin))
            self._docked_edge = "bl" if y > avail.center().y() else "tl"
        elif min_d == dist_right:
            self._home_x = avail.right() - self.SIZE - margin
            self._home_y = max(avail.top() + margin,
                               min(y, avail.bottom() - self.SIZE - margin))
            self._docked_edge = "br" if y > avail.center().y() else "tr"
        elif min_d == dist_top:
            self._home_x = max(avail.left() + margin,
                               min(x, avail.right() - self.SIZE - margin))
            self._home_y = avail.top() + margin
            self._docked_edge = "tl" if x < avail.center().x() else "tr"
        else:
            self._home_x = max(avail.left() + margin,
                               min(x, avail.right() - self.SIZE - margin))
            self._home_y = avail.bottom() - self.SIZE - margin
            self._docked_edge = "bl" if x < avail.center().x() else "br"

    # ==================================================================
    # 气泡
    # ==================================================================
    # ==================================================================
    # 角色切换 (从托盘菜单调用)
    # ==================================================================
    def set_character(self, key: str) -> bool:
        """切换桌宠角色, 返回 True 表示成功"""
        if key not in self._sheets:
            return False
        if key == self._current_char:
            return True
        self._current_char = key
        self._current_row = 0
        self._current_frame = 0
        self._frame_time = 0.0
        self._action_timer = 0.0
        return True

    def current_character(self) -> str:
        """当前角色 key"""
        return self._current_char

    def available_characters(self) -> List[Tuple[str, str]]:
        """所有可用角色 [(key, display_name), ...]"""
        return [(k, name) for k, name, _, _ in self.CHARACTERS]

    # ==================================================================
    # 动画推进
    # ==================================================================
    def _advance_animation(self, dt: float) -> None:
        """推进 sprite sheet 动画 + 随机动作切换"""
        if not self._current_char or self._current_char not in self._sheets:
            return
        sheet = self._sheets[self._current_char]
        n_frames = _SpriteSheet.ROW_FRAMES.get(self._current_row, 6)
        # 帧间隔: idle 0.16s (6 帧循环约 1s), 其他动作 0.1s 快速
        frame_dur = 0.10 if self._current_row != 0 else 0.16
        self._frame_time += dt
        if self._frame_time >= frame_dur:
            self._frame_time = 0.0
            self._current_frame += 1
            if self._current_frame >= n_frames:
                # 动作 (非 idle) 播完回到 idle
                if self._current_row != 0:
                    self._current_row = 0
                    self._current_frame = 0
                else:
                    self._current_frame = 0  # idle 循环
        # 随机触发动作: 闲置 4-8s 切换到 waving/jumping/waiting 增加趣味
        self._action_timer += dt
        if self._current_row == 0 and self._action_timer > random.uniform(4.0, 8.0):
            self._action_timer = 0.0
            # 随机动作 (waving=3, jumping=4, waiting=6)
            self._current_row = random.choice([3, 4, 6])
            self._current_frame = 0
            self._frame_time = 0.0
            # 拖动时不触发动作 (不扰动)
            if not self._drag_active:
                self._current_row = self._current_row
        # 被点击 → waving 动作
        # (在 mouseReleaseEvent 里直接 set, 不依赖这里)

    def _show_bubble(self, text: str) -> None:
        self._bubble_text = text
        self._bubble_time = 3.0
        self._bubble_showing = True

    # ==================================================================
    # 绘制
    # ==================================================================
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 整体缩放 = 呼吸 (持续 3%) + 节拍律动 (音乐 8%) + 头微转
        # 缩放中心取在贴图中心 (cx, cy = SIZE/2, BUBBLE_H + SIZE/2)
        scale = self._breath + self._beat_pulse * 0.08
        tilt = math.degrees(self._head_tilt)
        cx = self.SIZE / 2
        cy = self.BUBBLE_H + self.SIZE / 2

        p.translate(cx, cy)
        p.rotate(tilt)
        p.scale(scale, scale)
        p.translate(-cx, -cy)

        # 1. 背景光晕 (aura, 在贴图背后)
        self._draw_glow(p)

        # 2. 主体贴图 (sprite sheet 当前帧, 下移 BUBBLE_H 给气泡预留区)
        frame = self._get_current_frame()
        if frame is not None and not frame.isNull():
            scaled = frame.scaled(
                self.SIZE, self.SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(0, self.BUBBLE_H, scaled)

        # 3. 灵力粒子 (头发/肩旁漂浮的细小光点)
        self._draw_sparkles(p)

        p.end()

        # 4. 气泡 (在 widget 坐标系, 不参与旋转/缩放, y=0 在 widget 顶部)
        if self._bubble_alpha > 0.01:
            p2 = QPainter(self)
            p2.setRenderHint(QPainter.RenderHint.Antialiasing)
            p2.setOpacity(self._bubble_alpha)
            self._draw_bubble(p2)
            p2.end()

    # ------------------------------------------------------------------

    def _get_current_frame(self) -> Optional[QPixmap]:
        """获取当前动画帧 (192x208 原图, paintEvent 负责缩放)"""
        if not self._current_char or self._current_char not in self._sheets:
            return None
        sheet = self._sheets[self._current_char]
        return sheet.get_frame(self._current_row, self._current_frame)

    def _draw_glow(self, p: QPainter) -> None:
        # 贴图中心 (BUBBLE_H 偏移)
        cx = self.SIZE / 2
        cy = self.BUBBLE_H + self.SIZE * 0.45
        r = self.SIZE * 0.55
        grad = QRadialGradient(cx, cy, r)
        grad.setColorAt(0.0, QColor(180, 200, 255, 35))
        grad.setColorAt(0.5, QColor(140, 160, 220, 18))
        grad.setColorAt(1.0, QColor(100, 120, 200, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _draw_sparkles(self, p: QPainter) -> None:
        for s in self._sparkles:
            life_ratio = max(0.0, s.life / s.max_life)
            alpha = int(220 * life_ratio)
            color = QColor.fromHsv(int(s.hue) % 360, 150, 255, alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(QPointF(s.x, s.y), s.size, s.size)
            # 光晕
            halo = QColor.fromHsv(int(s.hue) % 360, 120, 255, alpha // 3)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(s.x, s.y), s.size * 2.5, s.size * 2.5)

    def _draw_bubble(self, p: QPainter) -> None:
        """气泡: 在小紫头顶上方 (widget 上方 BUBBLE_H 区)"""
        if not self._bubble_text:
            return
        font = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)
        p.setFont(font)
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(self._bubble_text)
        bw = max(text_w + 24, 64)
        bh = 24
        bx = (self.SIZE - bw) / 2
        by = 4  # widget 顶部留 4px
        # 圆角矩形
        rect = QRectF(bx, by, bw, bh)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        # 小尾巴指向小紫头顶 (BUBBLE_H 处)
        tail = QPainterPath()
        tail.moveTo(self.SIZE / 2 - 6, by + bh)
        tail.lineTo(self.SIZE / 2, self.BUBBLE_H - 2)
        tail.lineTo(self.SIZE / 2 + 6, by + bh)
        tail.closeSubpath()
        path.addPath(tail)
        # 玻璃质感
        grad = QLinearGradient(0, by, 0, by + bh)
        grad.setColorAt(0.0, QColor(245, 240, 255, 225))
        grad.setColorAt(1.0, QColor(220, 210, 240, 210))
        p.setPen(QPen(QColor(180, 160, 200, 180), 1))
        p.setBrush(QBrush(grad))
        p.drawPath(path)
        # 文字
        p.setPen(QColor(60, 50, 80, 255))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._bubble_text)

    # ==================================================================
    def stop(self) -> None:
        self._timer.stop()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
