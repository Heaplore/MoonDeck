"""Weather Card - 天气卡片

提供:
- create_for_canvas() -> (widget, controller) 工厂方法
- WeatherCardWidget    主 widget(自绘 PyQt6)
- WeatherService       数据源(和风 REST,30 分钟缓存)

老大原则:卡片严格独立模块,只通过 create_for_canvas 接入画布。
数据源:和风天气(API key 在 service.py 顶层常量,后续可移到 config)
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


def create_for_canvas() -> Tuple:
    """被 main.py 调用的工厂

    Returns:
        (widget, controller)  controller 负责定时刷新(30 分钟)
    """
    # 延迟导入避免循环
    from .widget import WeatherCardWidget
    from .service import WeatherService

    widget = WeatherCardWidget()
    service = WeatherService(widget=widget, interval_ms=widget.update_interval_ms)
    # 关键:连 signal → widget(否则 service 拉完数据,widget 收不到通知)
    service.data_ready.connect(widget.update_weather)

    class _Controller:
        def start(self_inner):
            service.start()

        def stop(self_inner):
            service.stop()

    controller = _Controller()
    return widget, controller


__all__ = ["create_for_canvas", "WeatherCardWidget", "WeatherService"]
