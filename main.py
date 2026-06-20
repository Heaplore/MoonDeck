"""MoonDeck 月坞 - 桌面浮窗卡片系统入口 (Phase 1)

启动流程:
1. 加载 config/default.yaml + theme.yaml + hotkeys.yaml
2. 初始化 StorageManager (SQLite)
3. 初始化 ThemeManager (单例)
4. 初始化 EventBus (单例)
5. 创建 QApplication + Canvas
6. 根据 config.cards.startup 加载卡片
7. 进入主循环

用法:
    python main.py                    # 正常启动
    python main.py --debug            # 调试模式(详细日志)
    python main.py --reset-layout     # 重置所有卡片布局
"""
from __future__ import annotations

import argparse
import logging
import sys
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication
from PyQt6.QtWidgets import QApplication

# 让相对导入工作
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from core import EventBus, ThemeManager, StorageManager  # noqa: E402
from core.canvas import Canvas  # noqa: E402  # noqa: F401  (保留 import 兼容,实际不再用)


def register_cjk_fonts() -> str:
    """注册中文字体(解决 offscreen 平台中文乱码)

    PyQt6 offscreen platform plugin 不读 Windows 字体目录,必须手动 addApplicationFont。
    按优先级尝试,第一个成功的设为默认应用字体。
    """
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",    # 黑体
        r"C:\Windows\Fonts\simsun.ttc",    # 宋体
        r"C:\Windows\Fonts\simkai.ttf",    # 楷体
    ]
    for path in candidates:
        if not Path(path).exists():
            continue
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(fid)
        if not families:
            continue
        # 用第一个家族名设默认
        default_family = families[0]
        QApplication.setFont(QFont(default_family, 10))
        return f"{Path(path).name} → {default_family}"
    return "未找到(中文可能乱码)"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """配置日志(写文件 + 控制台)"""
    log_dir = _HERE / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "moondeck.log"

    logger = logging.getLogger("moondeck")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    # 文件
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(fh)

    # 控制台
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    return logger


def load_yaml(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    """加载 yaml,失败返回 default"""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return default
        return data
    except Exception as e:
        print(f"[main] 加载 {path.name} 失败: {e}", file=sys.stderr)
        return default


def load_config() -> Dict[str, Any]:
    """加载 default.yaml + theme.yaml + hotkeys.yaml,合并为单 config"""
    default = load_yaml(_HERE / "config" / "default.yaml", {})
    theme = load_yaml(_HERE / "config" / "theme.yaml", {})
    hotkeys = load_yaml(_HERE / "config" / "hotkeys.yaml", {})

    # 合并:default 顶层 + theme 顶层 + hotkeys 顶层 + 用户偏好
    merged = {}
    merged.update(default)
    if "themes" in theme or "fonts" in theme or "animation" in theme:
        merged["_theme_yaml"] = theme
    merged["_hotkeys_yaml"] = hotkeys
    # 用户偏好覆盖默认 (用于保存桌面动效 / 歌词动效等运行时偏好)
    user = load_user_config()
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def get_user_config_path() -> Path:
    """用户偏好配置文件路径 (Windows: %APPDATA%/MoonDeck/preferences.yaml)"""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    user_dir = Path(appdata) / "MoonDeck"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "preferences.yaml"


def load_user_config() -> Dict[str, Any]:
    """加载用户偏好配置 (启动后覆盖 default.yaml)"""
    path = get_user_config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[main] 加载用户偏好失败: {e}", file=sys.stderr)
        return {}


def save_config_value(key_path: str, value: Any) -> None:
    """持久化单个配置项到用户偏好文件 (key_path 支持点分路径如 'desktop_background.visualizer')
    写到 %APPDATA%/MoonDeck/preferences.yaml, 避免修改源码中的 default.yaml
    """
    try:
        path = get_user_config_path()
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}
        if not isinstance(data, dict):
            data = {}
        keys = key_path.split(".")
        d = data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        print(f"[main] save_config_value({key_path}) 失败: {e}", file=sys.stderr)


def init_storage(config: Dict[str, Any]) -> None:
    """初始化 SQLite"""
    db_path = _HERE / config.get("storage", {}).get("db_path", "cache/moondeck.db")
    if not db_path.is_absolute():
        db_path = _HERE / db_path
    StorageManager.init_instance(db_path)


def init_theme(config: Dict[str, Any]) -> ThemeManager:
    """初始化 ThemeManager(单例)"""
    theme_yaml = _HERE / "config" / "theme.yaml"
    default_name = config.get("theme", {}).get("default", "dark")
    # 直接构造,不依赖单例
    tm = ThemeManager(theme_yaml_path=theme_yaml, default_name=default_name)
    # 注册到单例
    ThemeManager._instance = tm
    return tm


def load_cards_for_canvas(canvas: Canvas, config: Dict[str, Any], logger: logging.Logger) -> int:
    """根据 config.cards.startup 加载卡片

    Returns:
        成功加载的卡片数
    """
    startup = config.get("cards", {}).get("startup", [])
    loaded = 0
    for card_id in startup:
        try:
            result = _instantiate_card(card_id, config, logger)
        except Exception as e:
            logger.error(f"实例化卡片 {card_id} 失败: {e}", exc_info=True)
            continue
        if result is None:
            logger.warning(f"卡片 {card_id} 未找到,跳过")
            continue
        kind, widget, controller = result
        try:
            if kind == "widget":
                # 修复 2026-06-12: 独立 QWidget 卡片直接走"顶层独立窗口"模式
                # 不调 canvas.add_widget_card (它内部 setParent 会让子窗口坐标被画布 bug 牵连)
                # 流程:1) 读 config 位置 2) widget.move + show + raise 3) 保存到 storage
                # 修复 2026-06-14: 把 controller 注入 widget(否则 widget._on_send_clicked 找不到)
                if controller is not None and hasattr(widget, "controller"):
                    widget.controller = controller
                _show_top_level_widget(card_id, widget, config, logger)
            else:
                canvas.add_card(widget)
            # 启动 controller(如果存在)
            if controller is not None and hasattr(controller, "start"):
                try:
                    controller.start()
                except Exception as e:
                    logger.warning(f"卡片 {card_id} controller.start() 失败: {e}")
            loaded += 1
        except Exception as e:
            logger.error(f"添加卡片 {card_id} 到画布失败: {e}", exc_info=True)
    return loaded


def _instantiate_card(card_id: str, config: Dict[str, Any], logger: logging.Logger):
    """根据 card_id 返回 (widget, controller) 元组供画布使用

    当前实现:硬编码映射
    未来:用 entry_points / registry 机制
    """
    if card_id == "calendar_card":
        from cards.calendar_card import create_for_canvas
        widget, controller = create_for_canvas()
        return ("widget", widget, controller)
    if card_id == "music_card":
        from cards.music_card import create_for_canvas
        widget, controller = create_for_canvas()
        return ("widget", widget, controller)
    # 已砍掉的卡片
    if card_id in ("weather_card", "token_card", "monitor_card", "note_card", "gallery_card", "file_card", "silvermoon_card"):
        logger.warning(f"卡片 {card_id} 已被砍掉,跳过")
        return None
    # 未来扩展:elif card_id == "xxx_card": ...
    logger.warning(f"未知的 card_id: {card_id}")
    return None


# 全局持有 widget 引用,防止 Python GC 回收顶层孤儿窗口
# BUG: 之前在启动循环里 widget = ... 后下一轮就被覆盖,GC 回收导致窗口消失
_live_widgets: Dict[str, Any] = {}


def _show_top_level_widget(card_id: str, widget, config: Dict[str, Any], logger: logging.Logger) -> None:
    """把独立 QWidget 卡片作为顶层独立窗口显示(不嵌进画布)

    修复 2026-06-12: 画布的 add_widget_card 内部 widget.setParent(self) 会让子窗口
    坐标受画布 backbuffer bug 牵连(位置显示正确但不参与 DWM 合成)。
    改成走 token_card 模式:widget 当成独立顶层窗口,show() 后用 Windows 原生位置。

    修复 2026-06-12 19:59: 老大反馈天气卡片置顶挡其他程序
    → 强制覆盖 window flags: 去掉 WindowStaysOnTopHint,改用 Tool (不抢任务栏+不抢焦点)
    → 加 WA_ShowWithoutActivating + WS_EX_NOACTIVATE (完全不抢焦点)
    → 这样卡片就在普通程序 z-order 层,跟浏览器/编辑器一样能被遮挡

    流程:
    1. 强制 setWindowFlags(无 StaysOnTop,有 Tool)
    2. 从 config.default_positions 读位置
    3. widget.move + show + raise
    4. 写 SQLite layout(保证下次启动恢复一致位置)
    """
    import sys as _sys
    import ctypes as _ctypes

    # 强制 z-order:不置顶,工具窗口(不抢任务栏),无焦点
    widget.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.Tool  # 工具窗口:不在任务栏,不参与 alt-tab
    )
    # 显式不抢焦点
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    # Windows 扩展样式: NOACTIVATE 防止 alt-tab 抢焦点
    if _sys.platform == "win32":
        try:
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            hwnd = int(widget.winId())
            ex_style = _ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_NOACTIVATE
            _ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception as _e:
            logger.debug(f"设置 {card_id} WS_EX_NOACTIVATE 失败(可能未 show): {_e}")

    default_pos = config.get("cards", {}).get("default_positions", {}).get(card_id, {})
    # 优先 storage,其次 config,最后 (0,0)
    x = y = None
    w = h = None

    # 2026-06-13 22:59 fix: 用所有 screen 虚拟并集判断,不再被 webchat 容器 800x800 误判
    # 默认位置是按多屏设计的;EasyClaw webchat 容器 primaryScreen()=800x800,
    # 但月坞是跨屏 app,真实环境可能是 1920x1080 / 多屏,所以用 screens virtualGeometry 并集
    try:
        from PyQt6.QtGui import QGuiApplication as _QGA
        _app = _QGA.instance()
        # 用 screens 列表里最大的 width,或 virtualGeometry() 拿全屏并集
        _virt_w = 0
        if _app:
            try:
                from PyQt6.QtCore import QRect
                _virt = QRect()
                for _s in _app.screens():
                    _virt = _virt.united(_s.geometry())
                _virt_w = _virt.width() if _virt else 0
            except Exception:
                _virt_w = 0
        if _virt_w < 1200 and _app:
            _scr = _app.primaryScreen()
            _sw = _scr.geometry().width()
            _sh = _scr.geometry().height()
            # 重新归位:卡片紧凑摆(右上角优先)
            _compact = {
                "token_card":   (10, 10, 320, 220),
                "calendar_card":(_sw - 390, 10, 380, 0),  # 高度自适应
                "weather_card": (340, 10, 280, 240),
            }
            if card_id in _compact:
                x, y, w, h = _compact[card_id]
                if h == 0:
                    widget.resize(w, widget.sizeHint().height())
                else:
                    widget.resize(w, h)
                widget.move(x, y)
                storage = StorageManager.instance()
                storage.save_layout(card_id, x, y, w, h, visible=1)
                logger.info(f"[main] {card_id} 小屏 fallback -> ({x},{y}) {w}x{h}")
                return
    except Exception as _e:
        logger.debug(f"小屏 fallback 失败 (忽略): {_e}")

    # 2026-06-13 fix: 特殊 anchor 模式 (如 'left_quarter' = 左 1/4 上下铺满)
    # 用 PyQt 拿真实主屏尺寸 (不是 storage 存的过期值)
    anchor = default_pos.get("anchor")
    if anchor == "left_quarter":
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        sg = screen.geometry()
        # 减去任务栏可用区域
        avail = screen.availableGeometry()
        x = sg.x()
        y = avail.y()
        w = max(200, sg.width() // 4)  # 至少 200 宽
        h = avail.height()
        logger.info(f"[main] {card_id} anchor=left_quarter -> ({x},{y}) {w}x{h}")
        # 走完整流程(保存到 storage)
        try:
            widget.resize(w, h)
            widget.move(x, y)
            widget.show()
            widget.raise_()
            widget.update()
            storage = StorageManager.instance()
            storage.save_layout(card_id, x, y, w, h, visible=1)
        except Exception as e:
            logger.error(f"left_quarter 初始化 {card_id} 失败: {e}", exc_info=True)
        return
    elif anchor == "top_right":
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        sg = screen.geometry()
        avail = screen.availableGeometry()
        w = int(default_pos.get("width", 380))
        h = int(default_pos.get("height", 700))
        if h == 0:
            h = 529  # calendar_card 默认高度
        x = sg.x() + sg.width() - w - 16  # 右侧留 16px 边距
        y = avail.y() + 16  # 顶部留 16px
        logger.info(f"[main] {card_id} anchor=top_right -> ({x},{y}) {w}x{h}")
        try:
            widget.resize(w, h)
            widget.move(x, y)
            widget.show()
            widget.raise_()
            widget.update()
            storage = StorageManager.instance()
            storage.save_layout(card_id, x, y, w, h, visible=1)
        except Exception as e:
            logger.error(f"top_right 初始化 {card_id} 失败: {e}", exc_info=True)
        return
    elif anchor == "top_right_col2":
        # 2026-06-14 fix: 第二列,往左挪一卡 + 16px 间隔,避免和 top_right 重叠
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        sg = screen.geometry()
        avail = screen.availableGeometry()
        w = int(default_pos.get("width", 380))
        h = int(default_pos.get("height", 700))
        x = sg.x() + sg.width() - w - 16 - w - 16  # 右 1 列 + 16 + 左 1 列
        y = avail.y() + 16
        logger.info(f"[main] {card_id} anchor=top_right_col2 -> ({x},{y}) {w}x{h}")
        try:
            widget.resize(w, h)
            widget.move(x, y)
            widget.show()
            widget.raise_()
            widget.update()
            storage = StorageManager.instance()
            storage.save_layout(card_id, x, y, w, h, visible=1)
        except Exception as e:
            logger.error(f"top_right 初始化 {card_id} 失败: {e}", exc_info=True)
        return
    elif anchor == "bottom_left":
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        sg = screen.geometry()
        avail = screen.availableGeometry()
        w = int(default_pos.get("width", 280))
        h = int(default_pos.get("height", 160))
        x = sg.x() + 16
        # 计算 y:找到已有的 bottom_left 卡片,往上堆叠
        storage = StorageManager.instance()
        base_y = avail.y() + avail.height() - 50  # 底部留 50px
        y = base_y - h  # 第一张卡片位置
    elif anchor == "custom":
        # 自定义位置: x/y 为负数时表示从右/下边缘计算
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        sg = screen.geometry()
        avail = screen.availableGeometry()
        w = int(default_pos.get("width", 380))
        h = int(default_pos.get("height", 200))
        raw_x = int(default_pos.get("x", 0))
        raw_y = int(default_pos.get("y", 0))
        # x < 0 表示从右边缘算, y < 0 表示从下边缘算
        if raw_x < 0:
            x = sg.x() + sg.width() + raw_x  # raw_x 是负数
        else:
            x = sg.x() + raw_x
        if raw_y < 0:
            y = avail.y() + avail.height() + raw_y  # raw_y 是负数
        else:
            y = avail.y() + raw_y
        logger.info(f"[main] {card_id} anchor=custom -> ({x},{y}) {w}x{h}")
        try:
            widget.resize(w, h)
            widget.move(x, y)
            widget.show()
            widget.raise_()
            widget.update()
            storage = StorageManager.instance()
            storage.save_layout(card_id, x, y, w, h, visible=1)
        except Exception as e:
            logger.error(f"custom 初始化 {card_id} 失败: {e}", exc_info=True)
        return
        # 检查已加载的 bottom_left 卡片,堆叠
        all_pos = config.get("cards", {}).get("default_positions", {})
        for other_id, other_val in _live_widgets.items():
            if other_id == card_id:
                continue
            other_pos = all_pos.get(other_id, {})
            if other_pos.get("anchor") == "bottom_left":
                other_w = other_val[0] if isinstance(other_val, tuple) else other_val
                other_h = other_w.height()
                y = min(y, other_w.y() - other_h - 8)  # 8px 间距
        logger.info(f"[main] {card_id} anchor=bottom_left -> ({x},{y}) {w}x{h}")
        try:
            widget.resize(w, h)
            widget.move(x, y)
            widget.show()
            widget.raise_()
            widget.update()
            storage.save_layout(card_id, x, y, w, h, visible=1)
        except Exception as e:
            logger.error(f"bottom_left 初始化 {card_id} 失败: {e}", exc_info=True)
        return

    try:
        storage = StorageManager.instance()
        saved = storage.load_layout(card_id)
        if saved:
            x = int(saved.get("x", 0))
            y = int(saved.get("y", 0))
            # 2026-06-13 fix:widget 自己的 size 优先(避免存储里的过期尺寸/位置拉死)
            w = int(saved.get("w", 0)) or widget.width()
            h = int(saved.get("h", 0)) or widget.height()
            # 如果存的 w/h 跟 widget 实际不同,优先信 widget (widget 可能瘦身后尺寸变了)
            if saved.get("w") and int(saved["w"]) != widget.width():
                w = widget.width()
            if saved.get("h") and int(saved["h"]) != widget.height():
                h = widget.height()
            logger.debug(f"[main] {card_id} 位置从 storage 读取 ({x},{y})")
    except Exception as e:
        logger.warning(f"读 {card_id} storage layout 失败: {e}")
    if x is None and default_pos:
        x = int(default_pos.get("x", 100))
        y = int(default_pos.get("y", 100))
        w = int(default_pos.get("width", widget.width() or 320))
        h = int(default_pos.get("height", widget.height() or 320))
        logger.debug(f"[main] {card_id} 位置从 config 读取 ({x},{y})")
    if x is None:
        logger.warning(f"卡片 {card_id} 没有 storage 也没有 config 位置,使用 widget 默认")
        widget.show()
        widget.raise_()
        return
    try:
        widget.resize(w, h)
        widget.move(x, y)
        widget.show()
        widget.raise_()
        # 显式触发 repaint
        widget.update()
        logger.info(f"[main] 独立顶层卡片 {card_id} at ({x},{y}) size {w}x{h}")
        # 保存到 storage (保证下次启动能恢复)
        try:
            storage = StorageManager.instance()
            storage.save_layout(card_id, x, y, w, h, visible=1)
        except Exception as e:
            logger.warning(f"保存 {card_id} layout 失败: {e}")
    except Exception as e:
        logger.error(f"独立顶层卡片 {card_id} 初始化失败: {e}", exc_info=True)
        try:
            widget.show()
            widget.raise_()
        except Exception:
            pass


def reset_layout(logger: logging.Logger) -> None:
    """重置布局:删除 SQLite 里所有 layout 记录"""
    try:
        storage = StorageManager.instance()
    except RuntimeError:
        # storage 未初始化,先建一个
        db_path = _HERE / "cache" / "moondeck.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        storage = StorageManager.init_instance(db_path)
    for row in storage.load_all_layouts():
        storage.delete_layout(row["card_id"])
    logger.info("布局已重置")


def _refresh_all_widgets(logger: logging.Logger) -> None:
    """重置布局后,重新把每个 widget 移到 config.default_positions 里读到的位置
    (供 tray 的'重置布局'调用)
    """
    config = load_config()
    for card_id, (widget, _ctrl) in _live_widgets.items():
        pos = config.get("cards", {}).get("default_positions", {}).get(card_id)
        if not pos:
            continue
        x = int(pos.get("x", 100))
        y = int(pos.get("y", 100))
        widget.move(x, y)
        widget.show()
        widget.raise_()
        # 同步写回 storage
        try:
            storage = StorageManager.instance()
            storage.save_layout(card_id, x, y, widget.width(), widget.height(), visible=1)
        except Exception:
            pass
    logger.info("布局已重新应用")


def main() -> int:
    parser = argparse.ArgumentParser(description="MoonDeck 月坞 桌面浮窗卡片系统")
    parser.add_argument("--debug", action="store_true", help="调试模式(详细日志)")
    parser.add_argument("--reset-layout", action="store_true", help="重置所有卡片布局后退出")
    args = parser.parse_args()

    # 日志
    level = "DEBUG" if args.debug else "INFO"
    logger = setup_logging(level)
    logger.info("=" * 60)
    logger.info("🌙 MoonDeck 月坞 启动")
    logger.info(f"Python: {sys.version.split()[0]}  平台: {sys.platform}")

    # 加载配置
    config = load_config()
    logger.debug(f"配置加载完成,顶层 keys: {list(config.keys())}")

    # 重置布局模式
    if args.reset_layout:
        init_storage(config)
        reset_layout(logger)
        return 0

    # 初始化顺序很重要
    init_storage(config)
    init_theme(config)
    # EventBus 单例在首次调用 .instance() 时创建

    # QApplication
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 画布关闭不应退出(我们用快捷键管理)
    app.setApplicationName(config.get("app", {}).get("name", "MoonDeck"))
    app.setOrganizationName("MoonDeck")

    # 注册中文字体(必须在创建任何 widget 之前)
    font_info = register_cjk_fonts()
    logger.info(f"字体: {font_info}")

    # C 方案 2026-06-12 17:11: 不创建 Canvas 透明覆盖层
    # 根因:WS_EX_LAYERED + WA_TranslucentBackground + 全屏 DWM 合成 bug
    # → 画布上方的 widget 即便正确 show() 也不参与 DWM 合成
    # C 方案:让所有 widget 自己当独立顶层窗口,完全跳过画布层
    from PyQt6.QtWidgets import QWidget
    logger.info("🚫 Canvas 透明覆盖层已禁用 (C 方案)")

    # v0.9 音频律动背景 + 歌词动效 (双层架构)
    _bg = None
    _lyrics_fx = None
    _extra_widgets: Dict[str, Any] = {}  # 不进 DragManager 的控件
    if config.get("desktop_background", {}).get("enabled", True):
        try:
            from core.desktop_bg import DesktopBackground, LyricsFX
            _bg = DesktopBackground()
            _bg.show()
            _bg.lower()
            _extra_widgets["_desktop_bg"] = _bg

            # 歌词动效层 (在背景层之上)
            _lyrics_fx = LyricsFX(_bg._w, _bg._h)
            _lyrics_fx.enabled = True  # 默认开启
            _bg.set_lyrics_fx(_lyrics_fx)
            _extra_widgets["_lyrics_fx"] = _lyrics_fx

            # 恢复上次选择 (desktop_bg + lyrics_fx)
            saved_viz = config.get("desktop_background", {}).get("visualizer", "nebula")
            if saved_viz in _bg.VISUALIZERS:
                _bg.set_visualizer(saved_viz)
                logger.info(f"🎨 恢复桌面动效: {_bg.display_name(saved_viz)}")
            saved_lyrics = config.get("desktop_background", {}).get("lyrics_mode", "lyrics_particle")
            if saved_lyrics in _lyrics_fx.available_modes():
                _lyrics_fx.set_mode(saved_lyrics)
                logger.info(f"🎤 恢复歌词动效: {_lyrics_fx.display_name(saved_lyrics)}")

            logger.info("✅ 音频律动背景已启动 (粒子+渐变+频谱条)")
            logger.info("✅ 歌词动效层已启动 (飘字流/粒子字)")
        except Exception as e:
            logger.error(f"💥 音频律动背景启动失败: {e}", exc_info=True)

    # 加载卡片 (走 _show_top_level_widget 独立顶层模式,不需要 canvas)
    # BUG 修复 2026-06-12 21:30: widget 是顶层孤儿窗口(parent=None),Python GC
    # 会在循环结束时回收被覆盖的 widget → token 卡窗口消失
    # 修复:把 widget + controller 存到 _live_widgets 字典,主程序持有引用防 GC
    n = 0
    for card_id in config.get("cards", {}).get("startup", []):
        try:
            result = _instantiate_card(card_id, config, logger)
        except Exception as e:
            logger.error(f"实例化卡片 {card_id} 失败: {e}", exc_info=True)
            continue
        if result is None:
            logger.warning(f"卡片 {card_id} 未找到,跳过")
            continue
        kind, widget, controller = result
        # 关键:把 widget 存到全局字典,防止 Python GC 回收孤儿窗口
        _live_widgets[card_id] = (widget, controller)
        try:
            # 所有 widget 都走独立顶层模式
            _show_top_level_widget(card_id, widget, config, logger)
            if controller is not None and hasattr(controller, "start"):
                try:
                    controller.start()
                except Exception as e:
                    logger.warning(f"卡片 {card_id} controller.start() 失败: {e}")
            n += 1
        except Exception as e:
            logger.error(f"添加卡片 {card_id} 失败: {e}", exc_info=True)
    logger.info(f"✅ 独立顶层卡片启动,加载 {n} 张")
    if n == 0:
        logger.warning("⚠️ 没有加载任何卡片,可在 config/default.yaml 的 cards.startup 添加")

    # v0.7 小紫桌宠 (z-order 最上, 独立于 DragManager)
    _pet = None
    if config.get("desktop_pet", {}).get("enabled", True):
        try:
            from core.desktop_pet import DesktopPet
            _pet = DesktopPet()
            _pet.show()
            _extra_widgets["_desktop_pet"] = _pet
            logger.info("✅ 桌宠已启动 (sprite sheet 多角色)")
            # 恢复上次选择角色
            saved_char = config.get("desktop_pet", {}).get("character", "chen_qianyu")
            if _pet.set_character(saved_char):
                logger.info(f"🎭 恢复桌宠角色: {saved_char}")
        except Exception as e:
            logger.error(f"💥 小紫桌宠启动失败: {e}", exc_info=True)
            _pet = None

    # === 交互层 2026-06-13 v2: 装 DragManager + ClickManager (Phase 2 完整版) ===
    # 独立顶层 widget 架构:不挂全屏画布,而是把 DragManager 的 eventFilter 装到每张卡
    from PyQt6.QtWidgets import QWidget
    from core.drag_manager import DragManager
    from core.click_manager import ClickManager
    from core.event_bus import EventBus as _EventBusCls
    bus = _EventBusCls.instance()

    class _Dispatcher:
        """把事件过滤器转发到所有 live widget 的伪画布

        独立顶层 widget 架构没有全屏画布,但 DragManager 期望一个能枚举卡片的容器。
        这里 _Dispatcher 转发 all_cards() / mapFromGlobal() / install_event_filter_to_all()
        """
        def __init__(self, widgets_dict: dict):
            self._widgets = widgets_dict  # card_id -> (widget, controller)

        def all_cards(self):
            return [w for w, _ in self._widgets.values()]

        def get_card(self, card_id):
            v = self._widgets.get(card_id)
            return v[0] if v else None

        def mapFromGlobal(self, pos):
            # 独立顶层模式:本地坐标 ≈ 全局
            return pos

        def width(self):
            from PyQt6.QtGui import QGuiApplication
            s = QGuiApplication.primaryScreen()
            return s.geometry().width() if s else 1920

        def height(self):
            from PyQt6.QtGui import QGuiApplication
            s = QGuiApplication.primaryScreen()
            return s.geometry().height() if s else 1080

        def install_event_filter_to_all(self, event_filter):
            for w, _ in self._widgets.values():
                try:
                    w.installEventFilter(event_filter)
                except Exception:
                    pass

    canvas = _Dispatcher(_live_widgets)

    try:
        drag_mgr = DragManager(canvas, bus=bus, snap_threshold=10)
        click_mgr = ClickManager(canvas, bus=bus)
        logger.info("✅ DragManager 启动 (移动 + 缩放 + 吸附)")
        logger.info("✅ ClickManager 启动 (右键菜单)")
    except Exception as e:
        logger.critical(f"💥 DragManager/ClickManager 初始化失败: {e}", exc_info=True)
        drag_mgr = None
        click_mgr = None

    # === 交互层 2026-06-13: 装 4 个管理器(Phase 2 交互层) ===
    try:
        from core.hotkey_manager import HotkeyManager

        # 1. HotkeyManager:Alt 唤起/Esc 退出/1/2/3 切布局
        hkm = HotkeyManager()
        hkm.set_verbose(args.debug)
        def _interactive_on():
            print("[hotkey] interactive ON", flush=True)
            for card_id, (w, _) in _live_widgets.items():
                try:
                    w.raise_()
                except Exception:
                    pass
        def _interactive_off():
            print("[hotkey] interactive OFF", flush=True)
        hkm.register("<alt>", _interactive_on)
        hkm.register("<alt_l>", _interactive_on)
        hkm.register("<escape>", _interactive_off)

        # 主题切换快捷键
        def _cycle_theme():
            from core.theme import ThemeManager
            tm = ThemeManager.instance()
            new_theme = tm.cycle_theme()
            print(f"[hotkey] 主题切换: {new_theme}", flush=True)
            logger.info(f"🎨 主题切换: {new_theme}")
            # 刷新所有卡片
            for card_id, (w, _) in _live_widgets.items():
                try:
                    w.update()
                except Exception:
                    pass

        hkm.register("<ctrl>+<alt>+t", _cycle_theme)

        # v0.7 新增: 音频律动背景 / 小紫桌宠 切换热键
        if _bg is not None:
            bg_hotkey = config.get("desktop_background", {}).get(
                "hotkey_toggle", "<ctrl>+<alt>+b")
            def _toggle_bg():
                if _bg.isVisible():
                    _bg.hide()
                    logger.info("🎨 音频律动背景已隐藏")
                else:
                    _bg.show()
                    _bg.lower()
                    logger.info("🎨 音频律动背景已显示")
            try:
                hkm.register(bg_hotkey, _toggle_bg)
                logger.info(f"   背景切换热键: {bg_hotkey}")
            except Exception as e:
                logger.warning(f"注册背景热键失败: {e}")

        # v0.9: 歌词动效切换热键
        if _lyrics_fx is not None:
            lyrics_hotkey = config.get("desktop_background", {}).get(
                "hotkey_lyrics_fx", "<ctrl>+<alt>+l")
            def _toggle_lyrics_fx():
                _lyrics_fx.toggle()
                status = "开启" if _lyrics_fx.enabled else "关闭"
                logger.info(f"🎤 歌词动效已{status}")
            try:
                hkm.register(lyrics_hotkey, _toggle_lyrics_fx)
                logger.info(f"   歌词动效切换热键: {lyrics_hotkey}")
            except Exception as e:
                logger.warning(f"注册歌词动效热键失败: {e}")

        if _pet is not None:
            pet_hotkey = config.get("desktop_pet", {}).get(
                "hotkey_toggle", "<ctrl>+<alt>+p")
            def _toggle_pet():
                if _pet.isVisible():
                    _pet.hide()
                    logger.info("🐱 小紫已隐藏")
                else:
                    _pet.show()
                    _pet.raise_()
                    logger.info("🐱 小紫已显示")
            try:
                hkm.register(pet_hotkey, _toggle_pet)
                logger.info(f"   桌宠切换热键: {pet_hotkey}")
            except Exception as e:
                logger.warning(f"注册桌宠热键失败: {e}")

        if hkm.start():
            logger.info("✅ HotkeyManager 启动 (Alt 唤起 / Esc 退出)")
        else:
            logger.warning("⚠️ HotkeyManager 启动失败")
    except Exception as e:
        logger.critical(f"💥 HotkeyManager 初始化失败: {e}", exc_info=True)
        hkm = None

    # 2026-06-12 22:20 新增:系统托盘(右键出菜单:全显/全隐/单卡/重置/退出)
    try:
        from core.tray import MoonDeckTray
        # v0.8 新增: 桌面动效切换菜单
        _available_viz: Dict[str, str] = {}
        _current_viz: str = ""
        _on_viz_change = (lambda name: None)
        if _bg is not None:
            from core.desktop_bg import DesktopBackground as _DB
            _available_viz = {
                name: _DB.VISUALIZERS[name].DISPLAY_NAME
                for name in _DB.VISUALIZERS
            }
            _current_viz = _bg.current_visualizer()
            def _on_viz_change(name: str) -> None:
                if _bg is not None:
                    ok = _bg.set_visualizer(name)
                    if ok:
                        logger.info(f"🎨 桌面动效已切换: {_bg.display_name(name)}")
                        save_config_value("desktop_background.visualizer", name)
                    else:
                        logger.warning(f"⚠️ 切换动效失败: {name}")

        # v0.9: 歌词动效切换菜单
        _available_lyrics: Dict[str, str] = {}
        _current_lyrics: str = ""
        _on_lyrics_change = (lambda name: None)
        if _lyrics_fx is not None:
            _available_lyrics = {
                name: _lyrics_fx.display_name(name)
                for name in _lyrics_fx.available_modes()
            }
            _current_lyrics = _lyrics_fx.current_mode()
            def _on_lyrics_change(name: str) -> None:
                if _lyrics_fx is not None:
                    ok = _lyrics_fx.set_mode(name)
                    if ok:
                        logger.info(f"🎤 歌词动效已切换: {_lyrics_fx.display_name(name)}")
                        save_config_value("desktop_background.lyrics_mode", name)
                    else:
                        logger.warning(f"⚠️ 切换歌词动效失败: {name}")

        # 桌宠角色菜单
        _available_pet_chars: Dict[str, str] = {}
        _current_pet_char: str = ""
        _on_pet_char_change = (lambda name: None)
        if _pet is not None:
            from core.desktop_pet import DesktopPet as _DP
            _available_pet_chars = {
                k: n for k, n, _, _ in _DP.CHARACTERS
            }
            _current_pet_char = _pet.current_character()
            def _on_pet_char_change(name: str) -> None:
                if _pet is not None:
                    ok = _pet.set_character(name)
                    if ok:
                        logger.info(f"🎀 桌宠角色已切换: {name}")
                        save_config_value("desktop_pet.character", name)
                    else:
                        logger.warning(f"⚠️ 切换桌宠角色失败: {name}")

        tray = MoonDeckTray(
            live_widgets=_live_widgets,
            on_reset_layout=lambda: (reset_layout(logger), _refresh_all_widgets(logger)),
            on_visualizer_change=_on_viz_change,
            available_visualizers=_available_viz,
            current_visualizer=_current_viz,
            on_lyrics_fx_change=_on_lyrics_change,
            available_lyrics_fx=_available_lyrics,
            current_lyrics_fx=_current_lyrics,
            on_pet_character_change=_on_pet_char_change,
            available_pet_characters=_available_pet_chars,
            current_pet_character=_current_pet_char,
        )
        logger.info("✅ 系统托盘初始化完成")
    except Exception as e:
        logger.critical(f"💥 托盘初始化失败: {e}", exc_info=True)
        tray = None

    # 显式 print 一行,不管 logger 能不能写
    print("[main] tray init done, entering exec()", flush=True)
    logger.info("🚪 准备进入 app.exec() 主循环")

    # 简单快捷键:Esc 退出(全屏覆盖时只能这样)
    from PyQt6.QtCore import QTimer
    logger.info("💡 右键托盘图标 → 退出 / 设置 / 单卡显隐")
    logger.info(f"   屏幕: {[f'{s.geometry().width()}x{s.geometry().height()}' for s in QGuiApplication.screens()]}")

    # 注册退出 hook
    def on_quit():
        logger.info("退出中,保存布局...")
        # 停 HotkeyManager
        if hkm is not None:
            try:
                hkm.stop()
            except Exception:
                pass
        # 停 v0.7 新模块
        for _name, _w in _extra_widgets.items():
            try:
                if hasattr(_w, "stop"):
                    _w.stop()
            except Exception:
                pass
        canvas.shutdown()
        app.quit()
    app.aboutToQuit.connect(on_quit)

    # 装全局异常钩子(2026-06-12 21:55 新增)
    _install_global_excepthook(logger)

    return app.exec()


# 2026-06-12 21:55: 加全局异常钩子,捕获 PyQt 回调里的未捕获异常
# 原因:老大反馈点 token 卡导致进程消失,但日志没记录 → 怀疑是 PyQt 回调里
# 抛了未捕获异常被 PyQt 内部吞了。装上钩子后所有异常都会写日志。
def _install_global_excepthook(logger):
    """装 sys.excepthook + PyQt 的 excepthook,所有未捕获异常都进 logger"""
    import traceback as _tb
    _orig_sys_hook = sys.excepthook

    def _sys_hook(exc_type, exc_value, exc_tb):
        msg = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
        logger.critical(f"💥 [sys.excepthook] 未捕获异常:\n{msg}")
        try:
            _orig_sys_hook(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _sys_hook

    # PyQt6 的回调异常钩子(Qt 6.5+ 才有)
    try:
        from PyQt6.QtCore import qInstallMessageHandler
        def _qt_hook(mode, ctx, msg):
            # 抓到 fatal/warning 级别异常
            if mode in (0, 4):  # 0=QtWarningMsg, 4=QtFatalMsg
                logger.critical(f"💥 [Qt msg] {ctx.file}:{ctx.line} {msg}")
            else:
                logger.debug(f"[Qt msg] {msg}")
        qInstallMessageHandler(_qt_hook)
    except Exception as e:
        logger.debug(f"qInstallMessageHandler 不可用: {e}")


if __name__ == "__main__":
    try:
        # 在 main() 里装钩子需要 logger, 提到这里
        # 但 main() 自己创建 logger, 所以直接在 main() 末尾 return 之前装
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[MoonDeck] 用户中断,退出")
        sys.exit(0)
