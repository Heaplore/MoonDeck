"""Token 卡片 - 独立可跑入口

支持两种启动方式:
1. 作为画布子卡片:画布 import 它,实例化 TokenCardController
2. 独立跑:`python -m cards.token_card`

模块独立性验证点:不依赖 canvas/ 任何东西,纯 PyQt6 + 自己的 service/widget/controller。
"""
from __future__ import annotations

import sys
import yaml
from pathlib import Path
from typing import Optional

# service 不依赖 PyQt6,可以顶层 import
from .service import TokenService, TokenUsage

# widget / controller 依赖 PyQt6,顶层 import 会强制安装 PyQt6
# 用 __getattr__ 懒加载,允许 service-only 测试不装 PyQt6
__version__ = "1.3.0"


def __getattr__(name):
    """PEP 562 懒加载 - 只在用到 widget/controller 时才 import PyQt6"""
    if name in ("TokenCardWidget", "TokenCardController", "run_standalone", "create_for_canvas", "_load_default_config"):
        from .widget import TokenCardWidget  # noqa: F401
        from .controller import TokenCardController  # noqa: F401
        if name == "TokenCardWidget":
            return TokenCardWidget
        if name == "TokenCardController":
            return TokenCardController
        if name == "run_standalone":
            return run_standalone
        if name == "create_for_canvas":
            return create_for_canvas
        if name == "_load_default_config":
            return _load_default_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _load_default_config() -> dict:
    """加载默认 config.yaml"""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # 兜底:硬编码最小配置
    return {
        "window": {"width": 340, "height": 240, "margin_right": 11, "margin_top": 10},
        "refresh": {"interval_seconds": 60, "refresh_on_show": True},
        "data_source": {"type": "mmx_cli", "mmx_path": "mmx.cmd", "timeout_seconds": 10},
    }


def run_standalone(argv: Optional[list] = None) -> int:
    """独立启动 Token 卡片(跟 v3.6 一样独立窗口)

    用途:开发期调试 + 单卡片用户使用
    """
    from PyQt6.QtWidgets import QApplication

    app = QApplication(argv or sys.argv)
    app.setApplicationName("MoonDeck-TokenCard")
    app.setOrganizationName("MoonDeck")
    app.setQuitOnLastWindowClosed(True)

    config = _load_default_config()
    # 组件三件套
    service = TokenService(
        mmx_path=config["data_source"]["mmx_path"],
        timeout=config["data_source"]["timeout_seconds"],
    )
    widget = TokenCardWidget(config_path=Path(__file__).parent / "config.yaml")
    controller = TokenCardController(widget, service, config)

    # 2026-06-12 21:55:不桥接 mouse event(防止点击触发未捕获异常崩进程)
    # widget.mousePressEvent = controller.mousePressEvent.__get__(widget)
    # widget.mouseMoveEvent = controller.mouseMoveEvent.__get__(widget)
    # widget.mouseReleaseEvent = controller.mouseReleaseEvent.__get__(widget)

    # 信号:打印日志
    controller.usage_updated.connect(
        lambda u: print(f"[TokenCard] 更新:剩余={u.remaining_quota:.0f} 用={u.usage_pct:.1f}%")
    )
    controller.error_occurred.connect(
        lambda e: print(f"[TokenCard] 错误:{e}")
    )

    controller.start()
    return app.exec()


# 画布集成 hook
def create_for_canvas(config: Optional[dict] = None):
    """给画布用的工厂函数:返回 (widget, controller) 元组

    画布只需要调这个,不用关心内部怎么组装。
    """
    from .widget import TokenCardWidget
    from .controller import TokenCardController

    cfg = config or _load_default_config()
    service = TokenService(
        mmx_path=cfg["data_source"]["mmx_path"],
        timeout=cfg["data_source"]["timeout_seconds"],
    )
    widget = TokenCardWidget(config_path=Path(__file__).parent / "config.yaml")
    # 2026-06-13 修复:与 calendar/weather 保持一致,给 widget 标 card_id
    # (calendar/weather 在类里硬编码 card_id,token 之前没设 → DragManager 收事件后
    # 拿不到 card_id,早退不响应)
    widget.card_id = "token_card"
    widget.card_name = "Token Card"
    controller = TokenCardController(widget, service, cfg)
    # 2026-06-12 21:55 修复:不桥接 mouse event(之前是 monkey-patch
    # controller.mousePressEvent 到 widget 上,会在点击时触发未捕获异常导致进程消失)
    # 临时:用 installEventFilter 替代,后续再加拖拽
    # widget.mousePressEvent = controller.mousePressEvent.__get__(widget)
    # widget.mouseMoveEvent = controller.mouseMoveEvent.__get__(widget)
    # widget.mouseReleaseEvent = controller.mouseReleaseEvent.__get__(widget)
    return widget, controller


if __name__ == "__main__":
    sys.exit(run_standalone())
