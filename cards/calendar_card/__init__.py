"""Calendar Card - 月历卡片 v0.6 (集成天气+Token+音乐)

v0.6 (2026-06-17 音乐集成到月历):
- 音乐卡片集成到月历底部
- 月历卡片整体高度自适应
- 天气、月历、Token 布局样式严格不变

提供:
- create_for_canvas() -> (widget, controller) 工厂方法
- CalendarCardWidget  主 widget(继承 CardBase)
- MonthView           月历自绘子控件
- CalendarEventStore  事件存储(JSON)
- lunar.py            农历/节气/节日算法
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

# 注入路径
_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 顶层导入以便外部 from cards.calendar_card import CalendarCardWidget 能直接用
from .widget_v06 import CalendarCardWidget, MonthView


def create_for_canvas() -> Tuple:
    """被 main.py 调用的工厂

    Returns:
        (widget, controller)  controller 负责定时刷新
    """
    # 延迟导入避免循环
    from .widget import CalendarCardWidget

    widget = CalendarCardWidget()

    # 简易 controller:1 分钟触发 update_data + 启动天气/token
    from PyQt6.QtCore import QTimer
    timer = QTimer(widget)
    timer.setInterval(widget.update_interval_ms)
    timer.timeout.connect(widget.update_data)
    timer.start()

    class _Controller:
        def start(self_inner):
            timer.start()
            widget.start_data_sources()

        def stop(self_inner):
            timer.stop()

    controller = _Controller()
    # 立即启动天气/token(不等 controller.start)
    widget.start_data_sources()
    return widget, controller


__all__ = ["create_for_canvas", "CalendarCardWidget", "MonthView", "CalendarEventStore"]
