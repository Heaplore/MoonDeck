"""Music Card - 音乐卡片 v0.5 (Phase 4)

对齐月历 theme:
- 颜色全走 ThemeManager (紫 #9F7CFF + 冷青 #B4C8DC)
- 圆角 24 (与月历 corner_radius 一致)
- 律动条紫青渐变
- 删粒子动画
- 歌词过滤元数据行

数据源 (Phase 2/3 重写):
- audio_viz: WASAPI loopback FFT 48 bands
- service: SMTC 元数据 (含 position_sec / duration_sec)
- lyrics_loader: 网易云 + LrcAPI 双源

提供:
- MusicCardWidget    主 widget (继承 CardBase)
- create_for_canvas() 工厂方法 (被 main.py 调用)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 顶层导入以便外部 from cards.music_card import MusicCardWidget 能直接用
from .widget import MusicCardWidget


def create_for_canvas() -> Tuple:
    """被 main.py 调用的工厂

    Returns:
        (widget, controller)  controller 负责定时刷新
    """
    from .widget import MusicCardWidget

    widget = MusicCardWidget()

    from PyQt6.QtCore import QTimer
    timer = QTimer(widget)
    timer.setInterval(widget.update_interval_ms)
    timer.timeout.connect(widget.update_data)
    timer.start()

    class _Controller:
        def start(self_inner):
            timer.start()
            # 启动音频采样 (Phase 2 重写后的 audio_viz)
            from . import audio_viz
            audio_viz.start()

        def stop(self_inner):
            timer.stop()
            from . import audio_viz
            audio_viz.stop()

    controller = _Controller()

    # 立即拉一次数据 (不要等 controller.start)
    widget.update_data()
    return widget, controller


__all__ = ["MusicCardWidget", "create_for_canvas"]
