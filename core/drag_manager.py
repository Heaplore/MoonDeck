"""MoonDeck 卡片拖动 + 缩放 + 吸附管理器

职责(本次大改):
- 鼠标在卡片内按下并拖动 → 移动整张卡
- 鼠标在 8 个边缘/角手柄上按下并拖动 → 缩放
- 移动/缩放 释放时 → 检查吸附(屏边 + 其他卡片边),距离 < snap_threshold 自动贴齐
- 通过安装事件过滤器监听画布上的鼠标事件

设计:
- 单卡片 drag/resize session 状态机: IDLE → PRESSED → ACTIVE → IDLE
- 移动阈值(threshold):按下到移动超过 5px 才算 drag/resize,避免误触
- 缩放手柄:右下角 12x12 矩形 + 4 边各 6px 命中带(右下角为主,但边/角都可缩)
- 吸附:边/角 4 个参考(屏 + 其他卡片),取最近边吸附
- 8 方向缩放:NW/N/NE/E/SE/S/SW/W(本次先做 4 角 + 4 边,完整 8 向)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QWidget

from .event_bus import EventBus


# === 8 个缩放方向 ===
class ResizeHandle(Enum):
    NONE = "none"
    NW = "nw"  # 左上
    N = "n"    # 上
    NE = "ne"  # 右上
    E = "e"    # 右
    SE = "se"  # 右下
    S = "s"    # 下
    SW = "sw"  # 左下
    W = "w"    # 左


# 8 个方向对应的光标(留作日后用,本次实现先不强求)
_HANDLE_CURSORS: Dict[ResizeHandle, Qt.CursorShape] = {
    ResizeHandle.NW: Qt.CursorShape.SizeFDiagCursor,
    ResizeHandle.NE: Qt.CursorShape.SizeBDiagCursor,
    ResizeHandle.SE: Qt.CursorShape.SizeFDiagCursor,
    ResizeHandle.SW: Qt.CursorShape.SizeBDiagCursor,
    ResizeHandle.N: Qt.CursorShape.SizeVerCursor,
    ResizeHandle.S: Qt.CursorShape.SizeVerCursor,
    ResizeHandle.E: Qt.CursorShape.SizeHorCursor,
    ResizeHandle.W: Qt.CursorShape.SizeHorCursor,
}


@dataclass
class _DragState:
    """单次 drag/resize session 状态"""

    card_id: str
    widget: QWidget
    press_pos: QPoint           # 鼠标按下时的全局坐标
    widget_geo: QRect           # 鼠标按下时 widget 的 geometry
    threshold: int = 5
    is_active: bool = False     # 超过阈值后置 True(超过阈值 → 真正在拖)
    mode: str = "drag"          # "drag" / "resize"
    handle: ResizeHandle = ResizeHandle.NONE

    @property
    def is_dragging(self) -> bool:
        """兼容旧 API(老测试用)"""
        return self.is_active


class DragManager(QObject):
    """卡片拖动 + 缩放 + 吸附管理器

    用法:
        dm = DragManager(canvas, bus=bus, snap_threshold=10, min_size=(120, 80))
        # 自动 install event filter on canvas
        # 释放时:
        #   - 计算吸附位置 → widget.setGeometry
        #   - emit "card:moved" 或 "card:resized" 事件
        #   - canvas 监听后会 save_layout 到 storage
    """

    def __init__(
        self,
        canvas: QWidget,
        bus: Optional[EventBus] = None,
        threshold: int = 5,
        snap_threshold: int = 10,
        min_size: Tuple[int, int] = (120, 80),
        max_size: Tuple[int, int] = (2000, 1600),
        handle_size: int = 12,        # 4 角手柄矩形边长
        edge_band: int = 8,           # 4 边命中带宽度
        enabled: bool = True,
    ):
        # 兼容两种模式:
        #   1. canvas 是真画布(全屏):在画布上装 eventFilter,所有事件都过它
        #   2. canvas 是 "dispatcher 容器"(独立顶层 widget 架构):在每个 widget 上装 eventFilter
        # 区分点: dispatcher 有 install_event_filter_to_all 方法(且不是 QObject 子类)
        self._is_dispatcher = hasattr(canvas, "install_event_filter_to_all")
        if self._is_dispatcher:
            super().__init__()  # 无 parent
        else:
            super().__init__(canvas)
        self._canvas = canvas
        self._bus = bus or EventBus.instance()
        self._threshold = int(threshold)
        self._snap_threshold = int(snap_threshold)
        self._min_w, self._min_h = int(min_size[0]), int(min_size[1])
        self._max_w, self._max_h = int(max_size[0]), int(max_size[1])
        self._handle_size = int(handle_size)
        self._edge_band = int(edge_band)
        self._enabled = bool(enabled)
        self._state: Optional[_DragState] = None
        # 缩放时,绘制 8 个手柄的视觉提示
        self._handles_drawn: List[Tuple[ResizeHandle, QRect]] = []
        if self._is_dispatcher:
            canvas.install_event_filter_to_all(self)
        else:
            self._canvas.installEventFilter(self)

    # === 开关 ===

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_snap_threshold(self, px: int) -> None:
        """设置吸附阈值(屏边/卡边对齐距离)"""
        self._snap_threshold = max(0, int(px))

    # === 事件过滤器 ===

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        # 关键修复:dispatcher 模式下,obj 是 widget(不是 dispatcher 本身)
        # 传统画布模式下,obj 就是 canvas
        if self._is_dispatcher:
            # 必须是已知 card widget(走 canvas.all_cards 验证)
            try:
                known = [w for w, _ in [(c, None) for c in self._canvas.all_cards()]]
            except Exception:
                known = []
            if obj not in known:
                return False
        else:
            if obj is not self._canvas:
                return False
        if not self._enabled:
            return False

        etype = event.type()
        # dispatcher 模式:把触发事件的 widget 传下去,免去 _card_at 推断
        target = obj if self._is_dispatcher else None
        if etype == QEvent.Type.MouseButtonPress:
            self._handle_press(event, target_widget=target)
            return False
        elif etype == QEvent.Type.MouseMove:
            self._handle_move(event, target_widget=target)
            return False
        elif etype == QEvent.Type.MouseButtonRelease:
            self._handle_release(event, target_widget=target)
            return False
        return False

    # === 命中检测 ===

    def _hit_test(self, widget: QWidget, local_pos: QPoint) -> ResizeHandle:
        """检测 local_pos 命中 widget 的哪个手柄(8 向)"""
        g = widget.geometry()
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        hs = self._handle_size
        eb = self._edge_band
        lx, ly = local_pos.x() - x, local_pos.y() - y
        # 必须落在 widget 内
        if not (0 <= lx <= w and 0 <= ly <= h):
            return ResizeHandle.NONE

        on_left = lx <= eb
        on_right = lx >= w - eb
        on_top = ly <= eb
        on_bottom = ly >= h - eb
        on_lc = lx <= hs  # 在角手柄矩形内
        on_rc = lx >= w - hs
        on_tc = ly <= hs
        on_bc = ly >= h - hs

        # 4 角优先(命中手柄矩形)
        if on_lc and on_tc:
            return ResizeHandle.NW
        if on_rc and on_tc:
            return ResizeHandle.NE
        if on_rc and on_bc:
            return ResizeHandle.SE
        if on_lc and on_bc:
            return ResizeHandle.SW
        # 4 边(命中边带)
        if on_top and not on_left and not on_right:
            return ResizeHandle.N
        if on_bottom and not on_left and not on_right:
            return ResizeHandle.S
        if on_left and not on_top and not on_bottom:
            return ResizeHandle.W
        if on_right and not on_top and not on_bottom:
            return ResizeHandle.E
        return ResizeHandle.NONE

    def _handles_for(self, widget: QWidget) -> List[Tuple[ResizeHandle, QRect]]:
        """返回 8 个手柄的 (handle, local_rect) 列表,用于 paintEvent 画视觉提示

        实际绘制由 canvas 在 paintEvent 里订阅"drag:handles_changed"事件后画
        """
        g = widget.geometry()
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        hs = self._handle_size
        out: List[Tuple[ResizeHandle, QRect]] = []
        for h_dir, rx, ry in [
            (ResizeHandle.NW, x, y),
            (ResizeHandle.NE, x + w - hs, y),
            (ResizeHandle.SE, x + w - hs, y + h - hs),
            (ResizeHandle.SW, x, y + h - hs),
        ]:
            out.append((h_dir, QRect(rx, ry, hs, hs)))
        return out

    # === 内部:按下 ===

    def _handle_press(self, event: QMouseEvent, target_widget: Optional[QWidget] = None) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if target_widget is not None:
            # dispatcher 模式:eventFilter 已锁定 widget,跳过 _card_at
            widget = target_widget
        else:
            global_pos = event.globalPosition().toPoint()
            widget = self._card_at(global_pos)
        if widget is None:
            return
        card_id = getattr(widget, "card_id", None)
        if not card_id:
            return
        # 命中断手柄?
        if self._is_dispatcher:
            local = event.position().toPoint()
        else:
            local = self._canvas.mapFromGlobal(event.globalPosition().toPoint())
        handle = self._hit_test(widget, local)
        mode = "resize" if handle != ResizeHandle.NONE else "drag"
        # dispatcher 模式:用 event.position() (widget 内 local) 作为 press_pos
        # 真画布模式:用 globalPosition
        if self._is_dispatcher:
            press_pos = event.position().toPoint()
        else:
            press_pos = event.globalPosition().toPoint()
        self._state = _DragState(
            card_id=card_id,
            widget=widget,
            press_pos=press_pos,
            widget_geo=QRect(widget.x(), widget.y(), widget.width(), widget.height()),
            threshold=self._threshold,
            mode=mode,
            handle=handle,
        )

    def _card_at(self, global_pos: QPoint) -> Optional[QWidget]:
        """找鼠标下的卡片(走 canvas.all_cards)"""
        local = self._canvas.mapFromGlobal(global_pos)
        for card in reversed(self._canvas.all_cards() if hasattr(self._canvas, "all_cards") else []):
            if not card.isVisible():
                continue
            if card.geometry().contains(local):
                return card
        return None

    # === 内部:移动 ===

    def _handle_move(self, event: QMouseEvent, target_widget: Optional[QWidget] = None) -> None:
        if self._state is None:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        # dispatcher 模式:用 event.position() 算 delta(都是 widget 内 local)
        if self._is_dispatcher:
            cur_pos = event.position().toPoint()
        else:
            cur_pos = event.globalPosition().toPoint()
        delta = cur_pos - self._state.press_pos

        # 超过阈值才进入 active
        if not self._state.is_active:
            if abs(delta.x()) < self._threshold and abs(delta.y()) < self._threshold:
                return
            self._state.is_active = True

        if self._state.mode == "drag":
            self._apply_drag(self._state, delta)
        else:  # resize
            self._apply_resize(self._state, delta)

    def _apply_drag(self, state: _DragState, delta: QPoint) -> None:
        """移动整张卡(暂不吸附,释放时再吸)"""
        new_x = state.widget_geo.x() + delta.x()
        new_y = state.widget_geo.y() + delta.y()
        state.widget.move(new_x, new_y)

    def _apply_resize(self, state: _DragState, delta: QPoint) -> None:
        """根据手柄方向调整 x/y/w/h

        保持对侧不动,只动命中侧。例如命中 SE → 调右下角;
        命中 N → 调 y/h(下边不动);命中 W → 调 x/w(右边不动)
        """
        old = state.widget_geo
        x, y, w, h = old.x(), old.y(), old.width(), old.height()
        h_dir = state.handle

        new_x, new_y, new_w, new_h = x, y, w, h
        dx, dy = delta.x(), delta.y()

        if h_dir in (ResizeHandle.NW, ResizeHandle.W, ResizeHandle.SW):
            new_x = x + dx
            new_w = w - dx
        if h_dir in (ResizeHandle.NE, ResizeHandle.E, ResizeHandle.SE):
            new_w = w + dx
        if h_dir in (ResizeHandle.NW, ResizeHandle.N, ResizeHandle.NE):
            new_y = y + dy
            new_h = h - dy
        if h_dir in (ResizeHandle.SW, ResizeHandle.S, ResizeHandle.SE):
            new_h = h + dy

        # 限制最小/最大
        if new_w < self._min_w:
            # 保持右边不动(右把手柄/边/角时);保持左边不动(左把手柄时)
            if h_dir in (ResizeHandle.NW, ResizeHandle.W, ResizeHandle.SW):
                new_x = old.x() + old.width() - self._min_w
            new_w = self._min_w
        if new_h < self._min_h:
            if h_dir in (ResizeHandle.NW, ResizeHandle.N, ResizeHandle.NE):
                new_y = old.y() + old.height() - self._min_h
            new_h = self._min_h
        new_w = min(new_w, self._max_w)
        new_h = min(new_h, self._max_h)

        state.widget.setGeometry(new_x, new_y, new_w, new_h)

    # === 内部:释放 ===

    def _handle_release(self, event: QMouseEvent, target_widget: Optional[QWidget] = None) -> None:
        if self._state is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        state = self._state
        self._state = None
        if not state.is_active:
            # 当 click 处理,不做事
            return

        # === 吸附 ===
        snapped_geo = self._compute_snap(state.widget, state.widget_geo)
        if snapped_geo != state.widget.geometry():
            state.widget.setGeometry(snapped_geo)

        # 通知画布更新布局(画布订阅后会 save_layout)
        payload: Dict[str, Any] = {
            "card_id": state.card_id,
            "x": state.widget.x(),
            "y": state.widget.y(),
            "w": state.widget.width(),
            "h": state.widget.height(),
            "mode": state.mode,
        }
        event_name = "card:resized" if state.mode == "resize" else "card:moved"
        try:
            self._bus.emit(event_name, payload)
        except Exception:
            pass

    # === 吸附算法 ===

    def _compute_snap(self, widget: QWidget, original_geo: QRect) -> QRect:
        """计算吸附后的 geometry

        参考目标(候选边/角):
        1. 画布四边(0,0,cw,ch)
        2. 其他卡片的四边/四角

        对当前 widget 的 6 个吸附点(左上 x/y、右上 x、右下 x/y、左下 y)做检查,
        与每个候选边的距离 < snap_threshold → 吸附对齐。
        返回调整后的 QRect。
        """
        st = self._snap_threshold
        if st <= 0:
            return widget.geometry()

        cur = QRect(widget.geometry())
        new_x, new_y, new_w, new_h = cur.x(), cur.y(), cur.width(), cur.height()

        # 收集候选竖线(x) 和 水平线(y)
        vlines: List[int] = [0]
        hlines: List[int] = [0]
        # 画布宽高
        try:
            cw = int(self._canvas.width())
            ch = int(self._canvas.height())
            vlines.append(cw)
            hlines.append(ch)
        except Exception:
            cw, ch = 1920, 1080
        # 其他卡片的边
        try:
            cards = self._canvas.all_cards() if hasattr(self._canvas, "all_cards") else []
        except Exception:
            cards = []
        for other in cards:
            if other is widget:
                continue
            if not other.isVisible():
                continue
            try:
                og = other.geometry()
            except RuntimeError:
                continue
            vlines.extend([og.x(), og.x() + og.width()])
            hlines.extend([og.y(), og.y() + og.height()])

        # 当前 widget 的候选吸附点
        # 左 x、右 x、顶 y、底 y
        points_x = [new_x, new_x + new_w]
        points_y = [new_y, new_y + new_h]

        # 找 x 方向吸附:取离 new_x 最近的 vlines,同理 new_x+new_w
        snap_left = self._nearest_within(points_x[0], vlines, st)
        if snap_left is not None:
            new_x = snap_left
        else:
            snap_right = self._nearest_within(points_x[1], vlines, st)
            if snap_right is not None:
                # 右边对齐 → 调 x
                new_x = snap_right - new_w
        snap_top = self._nearest_within(points_y[0], hlines, st)
        if snap_top is not None:
            new_y = snap_top
        else:
            snap_bottom = self._nearest_within(points_y[1], hlines, st)
            if snap_bottom is not None:
                new_y = snap_bottom - new_h

        if (new_x, new_y, new_w, new_h) == (cur.x(), cur.y(), cur.width(), cur.height()):
            return cur
        return QRect(new_x, new_y, new_w, new_h)

    @staticmethod
    def _nearest_within(value: int, candidates: List[int], threshold: int) -> Optional[int]:
        """找 candidates 里离 value 最近的,距离 < threshold 返回该值,否则 None"""
        best: Optional[int] = None
        best_d = threshold + 1
        for c in candidates:
            d = abs(int(c) - int(value))
            if d <= threshold and d < best_d:
                best_d = d
                best = int(c)
        return best
