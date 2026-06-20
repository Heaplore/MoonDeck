# 🌙 MoonDeck 月坞 · 项目规划文档

> **版本**：v1.0  
> **日期**：2026-06-12  
> **作者**：老大（产品架构）+ 银月（执行落地）  
> **状态**：Phase 0 - 架构设计 ✅

---

## 📑 目录

1. [项目愿景与定位](#1-项目愿景与定位)
2. [整体架构](#2-整体架构)
3. [目录结构详解](#3-目录结构详解)
4. [画布核心设计](#4-画布核心设计)
5. [卡片间通信机制](#5-卡片间通信机制)
6. [性能与稳定性](#6-性能与稳定性)
7. [实施路线图](#7-实施路线图)
8. [风险与对策](#8-风险与对策)
9. [配置文件 Schema](#9-配置文件-schema)
10. [下一步行动](#10-下一步行动)

---

## 1. 项目愿景与定位

### 1.1 解决的痛点

**当前桌面环境的问题**：

1. **任务切换成本高**：查日历要切浏览器、看天气要切 App、查文件要开资源管理器
2. **信息分散**：日程、便签、文件、系统状态散落在不同软件
3. **个性化不足**：Windows 原生桌面太"空"，Rainmeter 太 Geek、BitDock 太工具化
4. **AI 入口割裂**：想用 AI 得开浏览器/客户端，复制粘贴来回调

**MoonDeck 的承诺**：

> "**桌面** = **仪表盘**。所有你关心的信息，**一眼可见、随手可触**。"

### 1.2 与现有方案对比

| 方案 | 类型 | 优势 | 劣势 |
|------|------|------|------|
| **Rainmeter** | 桌面挂件引擎 | 极强自定义 | 上手成本高，皮肤要自己写 |
| **BitDock** | 顶部 Dock 栏 | 类似 Mac Dock | 占用顶部一整条，限制布局 |
| **MagicDock** | Mac 风格启动器 | 美观 | 偏启动器，桌面交互弱 |
| **uTools** | 快捷启动 + 插件 | 插件生态强 | 仍要主动唤起，不"常驻" |
| **Windows Widgets** | 系统小组件 | 系统集成 | 不可定制，位置固定 |
| **Spotlight** | 全局搜索 | 快速 | 只是搜索，不是信息展示 |

**MoonDeck 的差异化**：

- ✅ **真的"画布"**（不是 Dock、不是 Widget 板）—— 自由摆放
- ✅ **不抢焦点**（不打扰你工作，需要时按 Alt 唤起交互）
- ✅ **13 个内置卡片**（开箱即用，不用折腾）
- ✅ **AI 原生**（银月直连 + AI 工具矩阵）
- ✅ **桌面宠物**（唯一一个把 AI 拟人化的方案）
- ✅ **轻量**（Python 单 exe，100MB 内）

### 1.3 一句话定位

> **MoonDeck = 你的桌面仪表盘 + AI 副驾 + 桌面宠物，一块透明画布全搞定。**

---

## 2. 整体架构

### 2.1 进程模型

**单进程多 QWidget 架构**（推荐）：

```
┌─────────────────────────────────────────────┐
│  MoonDeck.exe (主进程)                      │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │ Canvas (QWidget, 全屏透明)          │    │
│  │  ├── TokenCard (QWidget)            │    │
│  │  ├── FileCard (QWidget)             │    │
│  │  ├── CalendarCard (QWidget)         │    │
│  │  ├── StickyCard (QWidget)           │    │
│  │  └── ... (任意数量)                 │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │ Core (单例)                          │    │
│  │  ├── EventBus                       │    │
│  │  ├── ThemeManager                   │    │
│  │  ├── LayoutManager                  │    │
│  │  ├── HotkeyManager                  │    │
│  │  └── StorageManager (SQLite)        │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │ Services (后台线程)                  │    │
│  │  ├── FeishuCalendarPoller           │    │
│  │  ├── WeatherUpdater                 │    │
│  │  ├── SystemMonitor                  │    │
│  │  └── MusicController                │    │
│  └─────────────────────────────────────┘    │
│                                              │
│  ┌─────────────────────────────────────┐    │
│  │ Pet (独立 QWidget, 可拖到任意位置)  │    │
│  │  └── SpiritWolf                     │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**备选方案：多进程**（不推荐，初期不做）

- 每个卡片独立 exe
- 优点：彻底崩溃隔离
- 缺点：进程间通信复杂、资源占用高、开发成本 ×3

**决策**：单进程 + 模块化，崩溃隔离靠**线程隔离 + try/except** 实现。

### 2.2 通信机制

**三层通信**：

```
┌──────────────────────────────────────────┐
│ Layer 1: EventBus（核心）                 │
│  - 同进程内卡片间通信                     │
│  - Qt Signal/Slot 实现                    │
│  - 同步/异步可选                          │
└──────────────────────────────────────────┘
                ↓↑
┌──────────────────────────────────────────┐
│ Layer 2: StorageManager (SQLite)          │
│  - 卡片间共享数据                         │
│  - 布局/主题/便签/配置持久化              │
│  - 读写加锁                              │
└──────────────────────────────────────────┘
                ↓↑
┌──────────────────────────────────────────┐
│ Layer 3: 外部服务                         │
│  - 飞书日历 API（HTTP）                   │
│  - 天气 API（HTTP）                       │
│  - 音乐 API（COM/Window Message）         │
│  - MiniMax-M3（Anthropic SDK）            │
└──────────────────────────────────────────┘
```

### 2.3 数据流

```
外部数据源 ──HTTP/COM──> Services (后台轮询) ──Signal──> Cards (UI 更新)
                                                       │
                                                       └─Signal──> EventBus ──> 其他卡片
```

**示例**：
- 飞书日历每 5 分钟轮询一次 → 拉取今日日程 → CalendarCard 收到 signal → UI 更新
- 倒计时到时间 → CountdownCard 发 `countdown_fired` 事件 → StickyCard 订阅 → 弹便签提醒

### 2.4 画布层级

```
Window (Desktop)
└── Canvas (QWidget, 全屏透明, 不抢焦点)
    ├── CardLayer (管理所有卡片)
    │   ├── TokenCard
    │   ├── FileCard
    │   └── ...
    └── PetLayer (独立 z-order)
        └── SpiritWolf
```

**Z-Order 管理**：
- 卡片之间：可手动置顶/置底，存到布局配置
- 宠物永远在最上层（可被点击，但不挡操作）

---

## 3. 目录结构详解

### 3.1 顶层文件

| 文件 | 职责 |
|------|------|
| `README.md` | 项目介绍、用户指南 |
| `PROJECT_PLAN.md` | 架构设计（本文档） |
| `requirements.txt` | 运行时依赖 |
| `pyproject.toml` | 项目元数据 + 打包配置 |
| `main.py` | 入口：创建 QApplication + Canvas |
| `.gitignore` | Git 忽略规则 |

### 3.2 `config/`

| 文件 | 职责 | 关键配置项 |
|------|------|-----------|
| `default.yaml` | 默认配置 | 画布尺寸/缩放/默认主题/启动卡片列表 |
| `theme.yaml` | 主题配置 | 颜色/字体/圆角/阴影/动画时长 |
| `hotkeys.yaml` | 快捷键配置 | 唤起交互/切换主题/打开搜索 |

### 3.3 `core/` （核心，画布基类）

| 文件 | 关键类/函数 | 职责 |
|------|-------------|------|
| `canvas.py` | `Canvas(QWidget)` | 透明全屏主窗口，WS_EX_* 标志位，鼠标穿透 |
| `card_base.py` | `CardBase(QWidget)` | 卡片抽象基类，定义 5 个虚函数 |
| `theme.py` | `ThemeManager` | 主题加载/切换/热更新 |
| `layout.py` | `LayoutManager` | 磁吸对齐、栅格、保存布局 |
| `drag_manager.py` | `DragManager` | 拖拽逻辑、ghost preview |
| `event_bus.py` | `EventBus` | 全局事件总线（单例） |
| `hotkey_manager.py` | `HotkeyManager` | 全局快捷键监听（pynput） |

### 3.4 `cards/` （13 个卡片）

每个卡片一个目录，结构统一：

```
cards/<card_name>/
├── __init__.py
├── widget.py        # QWidget 实现
├── service.py       # 数据获取（可选）
├── schema.sql       # 数据库表结构
├── README.md        # 卡片说明
└── tests/
    └── test_widget.py
```

**13 个卡片详细规划**：

#### 1. `token_card/` ✅ v3.6 已完成
- **职责**：实时显示 MiniMax-M3 token 用量
- **数据源**：`https://api.minimaxi.com/v1/usage`（需 token）
- **更新频率**：30s
- **状态**：v3.6 在 `tools/minimax-token-card/`，Phase 1 移植到新画布

#### 2. `file_card/`
- **职责**：自动归类桌面文件
- **数据源**：`watchdog` 监控 `~/Desktop/`
- **分类规则**：
  - 按类型：图片/文档/视频/压缩包/快捷方式
  - 按时间：今日/本周/本月/更早
  - 按项目：匹配文件名前缀（如 `moondeck_*` → "MoonDeck 项目"）
- **操作**：一键归档 / 一键删除 / 打开所在文件夹

#### 3. `calendar_card/`
- **职责**：显示今日/本周日程
- **数据源**：飞书日历 API（已开通）
- **更新频率**：5min
- **特性**：今日/明日切换、农历、节日高亮

#### 4. `sticky_card/`
- **职责**：桌面便签墙
- **数据存储**：SQLite
- **特性**：
  - 拖拽分色（黄/粉/蓝/绿）
  - 互相 `@` 引用
  - 自动按日期归档
  - 全局搜索

#### 5. `music_card/`
- **职责**：音乐播放控制
- **数据源**：
  - 网易云（API + UWP 后台进程）
  - QQ 音乐（UWP）
  - Spotify（Web API + 本地客户端）
- **特性**：封面/进度条/切歌/音量

#### 6. `search_card/`
- **职责**：全局搜索
- **数据源**：本地索引（whoosh / 自建倒排）
- **索引范围**：便签/文件/命令/历史
- **特性**：模糊匹配、自然语言（"上周的 PPT"）

#### 7. `weather_card/`
- **职责**：天气显示
- **数据源**：和风天气 API（免费层）
- **更新频率**：30min
- **特性**：实时/24h/7天、紫外线、穿衣、洗车、运动

#### 8. `countdown_card/`
- **职责**：倒计时显示
- **数据存储**：SQLite
- **预设**：老婆生日/纪念日/节假日
- **特性**：自定义事件、桌面通知、提前 N 天提醒

#### 9. `monitor_card/`
- **职责**：系统资源监控
- **数据源**：`psutil` + `nvidia-smi`
- **更新频率**：2s
- **特性**：CPU/内存/GPU/网速/硬盘温度迷你折线图

#### 10. `silvermoon_card/`
- **职责**：银月直连聊天
- **数据源**：EasyClaw `feishu_mcp` / `sessions_send`
- **特性**：头像动态、消息流、快速指令

#### 11. `ai_tools_card/`
- **职责**：AI 工具矩阵
- **工具集**：
  - 🖼️ 识图（拖入图片 → 文字描述）
  - 🌐 翻译（中/英/日/韩）
  - 📝 总结（拖入 PDF/长文 → TL;DR）
  - 🎨 生图（输入描述 → MiniMax / DALL-E）
  - 🎙️ 配音（文字 → 语音）
- **数据源**：MiniMax-M3 多模态 API

#### 12. `pet/` (独立模块)
- **职责**：桌面宠物
- **主角**：银月小狼灵
- **行为**：
  - 趴在屏幕角落睡觉
  - 鼠标经过会跑过来看
  - 拖文件给它"吃"，自动归类
  - 心情系统（陪你久了会累）
  - 节庆变装（圣诞/春节）
- **技术**：SpriteSheet 帧动画 + 状态机

### 3.5 `pet/`

```
pet/
├── spirit_wolf.py     # SpiritWolf(QWidget) 主类
├── sprite.py          # 精灵渲染
├── state_machine.py   # 状态机（睡觉/醒来/跟随/吃东西）
├── animations/        # 帧动画
│   ├── idle.png
│   ├── walk.png
│   └── sleep.png
└── behaviors/         # 行为脚本
    ├── follow_mouse.py
    └── eat_file.py
```

### 3.6 `services/`

| 文件 | 职责 | API |
|------|------|-----|
| `feishu_calendar.py` | 飞书日历拉取 | `feishu_mcp call calendar event.list` |
| `weather_api.py` | 天气数据 | 和风天气 HTTP |
| `music_player.py` | 音乐播放控制 | Windows Media COM / Spotify Web API |
| `system_monitor.py` | 系统监控 | `psutil` |
| `minimax_client.py` | MiniMax-M3 客户端 | `anthropic` SDK |

### 3.7 `storage/`

```
storage/
├── db.py             # SQLite 封装（单例连接）
└── schemas/          # 各卡片的表结构
    ├── token_card.sql
    ├── sticky_card.sql
    ├── countdown_card.sql
    └── layout.sql
```

### 3.8 `ui/`

```
ui/
├── widgets/          # 通用 widget
│   ├── frosted_panel.py
│   ├── circular_progress.py
│   └── sparkline.py
├── themes/           # QSS 主题
│   ├── dark.qss
│   ├── light.qss
│   ├── glass.qss
│   └── neon.qss
└── icons/            # 图标资源
```

### 3.9 `tests/`

```
tests/
├── unit/             # 单元测试
│   ├── test_canvas.py
│   ├── test_event_bus.py
│   └── test_<card_name>.py
└── integration/      # 集成测试
    ├── test_card_communication.py
    └── test_full_launch.py
```

### 3.10 `docs/`

```
docs/
├── CHANGELOG.md
├── USER_GUIDE.md
├── CARD_DEV_GUIDE.md   # 卡片开发指南
└── ARCHITECTURE.md     # 架构详解
```

---

## 4. 画布核心设计

### 4.1 `Canvas` 主类

**职责**：透明全屏窗口，承载所有卡片

**关键代码（伪代码）**：

```python
class Canvas(QWidget):
    """透明全屏主窗口"""

    def __init__(self, config: dict):
        super().__init__()
        # 窗口标志
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.Tool
        )
        # 透明属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 永远不抢焦点
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Windows 扩展样式
        self._setup_win32_exstyle()

        # 全屏覆盖所有显示器
        self._span_all_screens()

        # 子组件
        self.event_bus = EventBus.instance()
        self.theme_manager = ThemeManager(config["theme"])
        self.layout_manager = LayoutManager()
        self.drag_manager = DragManager(self)
        self.card_layer = CardLayer(self)
        self.pet_layer = PetLayer(self)

    def _setup_win32_exstyle(self):
        """设置 Windows 扩展样式"""
        import ctypes
        hwnd = int(self.winId())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= (
            WS_EX_LAYERED          # 分层窗口
            | WS_EX_TRANSPARENT    # 鼠标穿透
            | WS_EX_TOOLWINDOW     # 不在任务栏
            | WS_EX_NOACTIVATE     # 不抢焦点
        )
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    def _span_all_screens(self):
        """覆盖所有显示器"""
        from PyQt6.QtGui import QGuiApplication
        geo = QGuiApplication.primaryScreen().virtualGeometry()
        for screen in QGuiApplication.screens():
            geo = geo.united(screen.geometry())
        self.setGeometry(geo)

    def enter_interactive_mode(self):
        """进入交互态（按 Alt 时）"""
        # 暂时关闭鼠标穿透
        self._set_transparent(False)
        self.event_bus.emit("canvas:interactive_on")

    def exit_interactive_mode(self):
        """退出交互态"""
        self._set_transparent(True)
        self.event_bus.emit("canvas:interactive_off")
```

### 4.2 `CardBase` 抽象基类

```python
from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget

class CardBase(QWidget, ABC):
    """所有卡片必须继承的基类"""

    # 元信息（子类必须设置）
    card_id: str = ""
    card_name: str = ""
    card_icon: str = ""
    default_size: tuple = (300, 200)
    update_interval_ms: int = 5000  # 5s

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.event_bus = EventBus.instance()
        self.theme = ThemeManager.instance()
        self.last_update = 0
        self.init_ui()
        self.apply_theme()
        self.update_data()  # 首次拉取

    @abstractmethod
    def init_ui(self):
        """初始化 UI（子类实现）"""
        ...

    @abstractmethod
    def update_data(self):
        """更新数据（子类实现，update_interval_ms 触发）"""
        ...

    def on_resize(self):
        """窗口大小变化（可选重写）"""
        pass

    def on_drag_start(self):
        """开始拖拽（可选重写）"""
        pass

    def on_drag_end(self, final_pos: tuple):
        """拖拽结束（保存位置）"""
        self.layout_manager.save_card_position(
            self.card_id, final_pos
        )

    def on_dock(self, target_card_id: str):
        """被吸附到其他卡片（可选重写）"""
        pass

    def serialize(self) -> dict:
        """序列化（保存到 SQLite）"""
        return {
            "card_id": self.card_id,
            "x": self.x(),
            "y": self.y(),
            "w": self.width(),
            "h": self.height(),
        }

    def deserialize(self, data: dict):
        """反序列化（从 SQLite 恢复）"""
        self.setGeometry(data["x"], data["y"], data["w"], data["h"])
```

### 4.3 主题管理器

```python
class ThemeManager:
    """主题管理器（单例）"""

    THEMES = {
        "dark": {"bg": "#1a1a2e", "fg": "#e0e0ff", "accent": "#b794f4"},
        "light": {"bg": "#ffffff", "fg": "#1a1a2e", "accent": "#3182ce"},
        "glass": {"bg": "rgba(255,255,255,0.1)", "fg": "#fff", "accent": "#f6ad55"},
        "neon": {"bg": "#0a0a1a", "fg": "#00ff88", "accent": "#ff00ff"},
    }

    def __init__(self, config: dict):
        self.current = config.get("default", "dark")
        self._observers = []

    def set_theme(self, name: str):
        self.current = name
        # 通知所有观察者
        for obs in self._observers:
            obs.on_theme_changed(self.THEMES[name])

    def get_qss(self) -> str:
        """返回 QSS 字符串"""
        t = self.THEMES[self.current]
        return f"""
        QWidget {{ background: {t['bg']}; color: {t['fg']}; }}
        QPushButton {{ color: {t['accent']}; }}
        """

    def subscribe(self, callback):
        self._observers.append(callback)
```

### 4.4 拖拽管理器

```python
class DragManager:
    """拖拽管理"""

    def __init__(self, canvas: Canvas):
        self.canvas = canvas
        self.dragging = None
        self.snap_threshold = 15  # 磁吸阈值

    def start_drag(self, card: CardBase, global_pos: QPoint):
        self.dragging = card
        self.drag_offset = global_pos - card.mapToGlobal(QPoint(0, 0))

    def on_mouse_move(self, global_pos: QPoint):
        if not self.dragging:
            return
        new_pos = global_pos - self.drag_offset
        # 磁吸到屏幕边缘
        new_pos = self._snap_to_edge(new_pos)
        # 磁吸到其他卡片
        new_pos = self._snap_to_cards(new_pos)
        self.dragging.move(new_pos)

    def end_drag(self):
        if self.dragging:
            self.dragging.on_drag_end((self.dragging.x(), self.dragging.y()))
        self.dragging = None

    def _snap_to_edge(self, pos: QPoint) -> QPoint:
        screen = QGuiApplication.primaryScreen().geometry()
        if pos.x() < self.snap_threshold:
            pos.setX(0)
        if pos.y() < self.snap_threshold:
            pos.setY(0)
        if pos.x() + self.dragging.width() > screen.width() - self.snap_threshold:
            pos.setX(screen.width() - self.dragging.width())
        return pos

    def _snap_to_cards(self, pos: QPoint) -> QPoint:
        """吸附到其他卡片边缘"""
        for other in self.canvas.card_layer.cards.values():
            if other == self.dragging:
                continue
            if abs(pos.x() - other.x()) < self.snap_threshold:
                pos.setX(other.x())
            if abs(pos.y() - other.y()) < self.snap_threshold:
                pos.setY(other.y())
        return pos
```

---

## 5. 卡片间通信机制

### 5.1 EventBus 设计

**基于 Qt Signal 的全局事件总线**：

```python
from PyQt6.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    """全局事件总线（单例）"""
    _instance = None

    event = pyqtSignal(str, object)  # event_name, payload

    def __init__(self):
        super().__init__()

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = EventBus()
        return cls._instance

    def emit(self, event_name: str, payload: object = None):
        self.event.emit(event_name, payload)

    def subscribe(self, event_name: str, callback):
        self.event.connect(lambda name, payload: (
            callback(payload) if name == event_name else None
        ))
```

### 5.2 使用示例

**场景 1：Token 卡片点击「充值」→ 打开银月卡片询问**

```python
# TokenCard 中
def on_recharge_clicked(self):
    self.event_bus.emit("token:recharge_requested", {
        "current_balance": self.current_balance,
    })

# SilvermoonCard 中
def __init__(self, ...):
    super().__init__(...)
    self.event_bus.subscribe("token:recharge_requested", self._handle_recharge)

def _handle_recharge(self, payload):
    # 自动向银月发消息
    self.ask_silvermoon(f"我的 token 余额是 {payload['current_balance']}，怎么充值？")
```

**场景 2：日历提醒 → 桌面宠物跳出来提醒**

```python
# CalendarCard 中
def check_upcoming_events(self):
    for event in self.upcoming_events:
        if event.start_in_minutes == 10:
            self.event_bus.emit("calendar:reminder", event)

# Pet 中
def __init__(self, ...):
    self.event_bus.subscribe("calendar:reminder", self._on_reminder)

def _on_reminder(self, event):
    self.play_animation("wake_up")
    self.show_speech_bubble(f"老大，{event.title} 还有 10 分钟开始！")
```

### 5.3 事件命名规范

- `card:<card_id>:<action>` —— 卡片主动发的事件
- `system:<action>` —— 系统事件
- `user:<action>` —— 用户操作事件
- `service:<service>:<event>` —— 服务层事件

---

## 6. 模块化、质量保障与性能

> **核心理念**：每个卡片是**独立可拔插的模块** —— 能单测、能独立跑、能被核心以外的宿主程序引用、出 bug 不会拖垮其他卡片。

### 6.1 模块独立性（强约束）

> 这是老大最关心的：**每卡片独立 → 排查 bug 简单、单独升级迭代不踩雷**

#### 6.1.1 卡片目录强制结构

每个卡片目录（如 `cards/token_card/`）**必须**包含：

```
token_card/
├── __init__.py           # 导出 TokenCard 类
├── widget.py             # PyQt6 widget 主体（UI 渲染）
├── controller.py         # 业务逻辑（与 widget 解耦）
├── service.py            # 外部数据获取（API / 本地 IO）
├── config.py             # 卡片专属配置 schema
├── README.md             # 卡片独立文档
├── CHANGELOG.md          # 卡片独立版本日志
├── tests/
│   ├── __init__.py
│   ├── test_widget.py    # UI 测试（mock controller）
│   ├── test_controller.py # 业务逻辑单测
│   └── test_service.py   # 数据层单测
└── requirements.txt      # 卡片专属依赖（可选）
```

#### 6.1.2 独立导入 / 独立运行

**每个卡片必须能单独跑起来**（不需要整个 MoonDeck 启动）：

```bash
# 单独运行 Token 卡片
python -m cards.token_card          # 显示占位 widget
python -m cards.token_card --demo   # 用 mock 数据演示
python -m cards.token_card --test   # 跑自测
```

**独立导入**（不依赖 core）：

```python
# ✓ 任何宿主都能直接用
from cards.token_card import TokenCard
card = TokenCard()
card.start()

# ✗ 反例：core 反向依赖卡片
from core.canvas import Canvas
canvas = Canvas()
canvas.add(TokenCard())  # 也不禁止，只是要单向
```

**独立打包**（PyInstaller spec 每个卡片一个）：

```bash
# 单卡片独立 exe（调试用）
pyinstaller cards/token_card/packaging/token_card.spec
```

#### 6.1.3 依赖反向：卡片 → core，**绝不** core → 卡片

```python
# ✓ 正确：卡片 import core 的基类
from core.card_base import CardBase
from core.event_bus import EventBus

# ✗ 错误：core 不允许 import 任何具体卡片
# core/canvas.py 里绝不能出现 from cards.token_card import ...
```

这样新增/删除卡片**不会影响 core 稳定性**。

#### 6.1.4 卡片间通信**只**走 EventBus

```python
# ✓ 正确
event_bus.subscribe("calendar:event_added", self.on_event)
event_bus.emit("sticky:new", {"text": "..."})

# ✗ 错误：卡片 A 直接 import 卡片 B
from cards.calendar_card import CalendarCard  # 禁止！
```

### 6.2 进程隔离与崩溃恢复

#### 6.2.1 单进程多 widget（轻量隔离）

**不是**多进程（多进程 IPC 复杂），而是用 **try/except + QTimer watchdog** 实现软隔离：

```python
# core/safety.py
import functools, traceback
from core.event_bus import event_bus
from core.logger import logger

def safe_run(card_id: str):
    """卡片所有方法的装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                logger.exception(f"[{card_id}] {func.__name__} crashed")
                event_bus.emit("card:crashed", {
                    "card_id": card_id,
                    "func": func.__name__,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })
                # 卡片自动降级：UI 显示错误占位，**不影响其他卡片**
                self._show_error_state(f"⚠️ {func.__name__} 异常")
                return None
        return wrapper
    return decorator
```

#### 6.2.2 三级崩溃处理

| 级别 | 触发 | 处理 |
|------|------|------|
| **L1 单方法异常** | 卡片某个 API 调用失败 | `safe_run` 装饰器捕获，记录日志，UI 标"⚠️" |
| **L2 卡片整体崩溃** | 卡片反复抛异常（3 次/分钟） | 自动隐藏卡片 + 弹通知 "卡片 X 暂时禁用" |
| **L3 主进程崩溃** | 整个 MoonDeck 挂掉 | Windows Service 看门狗自动重启（**已有 easyclaw 经验**） |

#### 6.2.3 看门狗实现（参考 easyclaw 经验）

> **教训**：easyclaw watchdog 之前端口写错（18789 实际是 10089），导致误重启。**这次必须先验证端口再写**

```python
# core/health_check.py
from PyQt6.QtCore import QTimer
from core.event_bus import event_bus

class HealthMonitor:
    def __init__(self, canvas):
        self.canvas = canvas
        self.timer = QTimer()
        self.timer.timeout.connect(self._check)
        self.timer.start(60_000)  # 每 60s 一次
        self.failure_counts = {}  # card_id -> count

    def _check(self):
        for card in self.canvas.cards.values():
            if card.last_heartbeat is None:
                continue
            age = (now() - card.last_heartbeat).total_seconds()
            if age > card.update_interval_ms / 1000 * 3:
                self.failure_counts[card.card_id] = self.failure_counts.get(card.card_id, 0) + 1
                if self.failure_counts[card.card_id] >= 3:
                    event_bus.emit("card:disabled", {"card_id": card.card_id})
                    card.disable()
                    self.failure_counts[card.card_id] = 0
```

### 6.3 性能指标

| 指标 | 目标 | 实测 |
|------|------|------|
| 启动时间 | < 3s | TBD |
| 闲置 CPU | 0% | TBD |
| 工作 CPU | < 5% | TBD |
| 内存（空载）| < 100MB | TBD |
| 内存（满载 13 卡）| < 500MB | TBD |
| 帧率 | 60 FPS | TBD |

### 6.4 性能优化策略

1. **按需刷新**：每个卡片有 `update_interval_ms`，定时器触发
2. **数据缓存**：外部 API 数据缓存到 SQLite，避免重复请求
3. **懒加载**：未展开的卡片不创建 widget
4. **GPU 加速**：PyQt6 启用 OpenGL 渲染
5. **避免阻塞**：所有 IO 操作放后台线程（QThread / QThreadPool）

### 6.5 状态保存与优雅退出

1. **状态保存**：每 5s 序列化一次所有卡片状态到 SQLite
2. **优雅退出**：Ctrl+C 触发，先保存状态再退出
3. **错误处理**：
   - **网络错误**：降级到缓存数据 + 标记"离线"
   - **API 限流**：退避重试（exponential backoff）
   - **数据库锁**：重试 3 次
   - **渲染错误**：自动隐藏卡片 + 通知用户

---

## 7. 实施路线图

### Phase 1：画布底座（1 周）⭐ 当前阶段

**目标**：搭好画布 + 集成 Token 卡片，验证整套架构可行

| Day | 任务 | 验收 |
|-----|------|------|
| Day 1 | 透明全屏窗口（WS_EX_*）+ 多显示器 | 启动后画布覆盖所有屏幕，鼠标可穿透 |
| Day 2 | CardBase 抽象基类 + 主题管理器 | 写一个测试卡片能正常显示 |
| Day 3 | 拖拽管理 + 磁吸对齐 | 拖动卡片能磁吸到边缘 |
| Day 4 | 布局保存/恢复（SQLite）| 重启后卡片位置保持 |
| Day 5 | 集成 v3.6 Token 卡片 | Token 卡片在新画布上工作 |
| Day 6 | 快捷键（Alt 切换交互态）| 按 Alt 鼠标能点穿/不穿切换 |
| Day 7 | 打包 + 自测 | 单 exe 可运行 |

**交付**：`MoonDeck.exe` + 1 个 Token 卡片 ✅

### Phase 2：5 个高频卡片（2 周）

- 📁 文件卡片（4 天）：watchdog 监控桌面、自动归类、操作
- 🗓️ 日历卡片（2 天）：飞书 API 拉取
- 📝 便签卡片（3 天）：CRUD + 拖拽分色
- 🔍 搜索卡片（2 天）：whoosh 索引
- 🌤️ 天气卡片（1 天）：和风 API

**交付**：5 个卡片全部可用 + 卡片间通信 demo

### Phase 3：6 个特色卡片（3 周）

- 🎵 音乐卡片（4 天）：网易云/QQ/Spotify
- ⏳ 倒计时卡片（1 天）
- 📈 监控卡片（3 天）：psutil + nvidia-smi
- 🌙 银月直连卡片（3 天）：EasyClaw 集成
- 🤖 AI 工具卡片（4 天）：识图/翻译/总结/生图
- 🐺 桌面宠物（5 天）：独立动画引擎

**交付**：13 卡片全功能

### Phase 4：插件化（1 周）

- 卡片 SDK 文档
- 用户自注册
- 主题包市场（本地）

**交付**：用户可开发自定义卡片

### Phase 5：发布与社区（持续）

- GitHub 公开
- 视频演示
- 用户反馈
- 持续迭代

### Phase 6：铁律 —— 每卡片走完 §12 checklist 才能进下一个

> **强约束**（老大重点关注的质量门）

```
实施顺序（每张卡片）：
  1. 实现（按目录结构 + EventBus 隔离）
  2. 自测（单测 + 独立跑 + 降级 UI）
  3. 质量门（ruff + mypy + 覆盖率）
  4. 老大 review（§11.1 阶段 2 走查 10 项）
  5. 集成联调（跟 ≥3 个其他卡片跑）
  6. 打 tag v0.1.0（进入下一张）
```

**不允许**：
- ✗ 连续写两个卡片，中间不 review
- ✗ “等 Phase 2 写完一起查”
- ✗ “这个简单不用 review”

**允许**：
- ✓ 简单卡片 review 0.5 天
- ✓ 老大请假 = 整个项目暂停 1~N 天（人是最严的质量门）

---



## 8. 风险与对策

### 8.1 技术风险

| 风险 | 等级 | 对策 |
|------|------|------|
| 透明窗口鼠标穿透失效 | 中 | 用 Win32 API 动态切换 WS_EX_TRANSPARENT |
| EasyClaw 客户端 canvas 限制（headless）| 高 | 真实显示器部署测试，必要时绕过 |
| 多显示器 DPI 缩放不一致 | 中 | Qt 自带 high-DPI 支持，启用 PassThrough |
| 飞书 API 限流 | 低 | 本地缓存 + 退避重试 |
| 网易云/QQ 音乐接口变更 | 高 | 抽象 MusicPlayer 接口，失败时降级到本地 |
| PyInstaller 打包体积大 | 中 | UPX 压缩 + 排除不必要包 |

### 8.2 体验风险

| 风险 | 对策 |
|------|------|
| 卡片太占视野 | 默认紧凑尺寸（200×150），可调 |
| 桌面宠物太烦人 | 默认隐藏，按快捷键召唤 |
| 主题切换不流畅 | 用 QPropertyAnimation 渐变 |
| 启动太慢 | 懒加载未启用的卡片 |
| 用户找不到功能 | 引导式新手教程（首次启动） |

### 8.3 安全风险

| 风险 | 对策 |
|------|------|
| 飞书 API 密钥泄露 | 加密存储到 Windows Credential Manager |
| SQLite 数据未加密 | 用 SQLCipher 加密敏感数据（便签内容）|
| 第三方 API 注入 | requests 默认 verify=True，禁用 HTTP |

### 8.4 质量风险（老大重点关注）

| 风险 | 严重度 | 对策 | 对应章节 |
|------|--------|------|----------|
| **Bug 越堆越多，后期难修** | ⚠️ 极高 | 每卡片完成后**立刻 review**，不允许"写完再统一查" | §11 |
| **13 卡片代码 6000+ 行，模块边界不清** | ⚠️ 高 | 强制 §6.1 目录结构 + EventBus 隔离 + 卡片独立可跑 | §6.1 |
| **单卡片崩拖垮全部** | ⚠️ 高 | §6.2 三级崩溃隔离（safe_run + watchdog） | §6.2 |
| **卡片耦合度高，改一个坏一片** | 中 | §6.1.3 依赖反向（core 不 import 卡片）| §6.1.3 |
| **没有回归测试，bug 反复出现** | 中 | §11.5 每次修复必加回归测试 | §11.5 |
| **跳过审查，最后大返工** | ⚠️ 极高 | §11.3 审查节奏时间盒 + 铁律"不允许跳 review" | §11.3 |

> **反例**：如果 Phase 2 写完 5 卡片不审查，Phase 3 写完才发现 EventBus 命名错，**改 1 个 key 要扫 13 个文件的引用**。**第 11 章的 review 是乘数效应**。

---

## 9. 配置文件 Schema

### 9.1 `config/default.yaml`

```yaml
# MoonDeck 默认配置
version: "0.1.0"

# 画布
canvas:
  # 缩放因子（0.5-2.0）
  scale: 1.0
  # 启动时全屏铺满
  fullscreen: true
  # 默认主题
  default_theme: "dark"
  # 开机自启
  auto_start: true

# 启动时启用的卡片
enabled_cards:
  - token_card
  - file_card
  - calendar_card
  - sticky_card
  # - music_card
  # - search_card
  # - weather_card
  # - countdown_card
  # - monitor_card
  # - silvermoon_card
  # - ai_tools_card

# 卡片默认位置（首次启动用，后续自动保存）
card_positions:
  token_card: { x: 1500, y: 10 }
  file_card: { x: 1500, y: 200 }
  calendar_card: { x: 20, y: 20 }
  sticky_card: { x: 340, y: 20 }
  music_card: { x: 20, y: 600 }
  search_card: { x: 660, y: 20 }
  weather_card: { x: 980, y: 20 }
  countdown_card: { x: 1300, y: 20 }
  monitor_card: { x: 1500, y: 400 }
  silvermoon_card: { x: 660, y: 600 }
  ai_tools_card: { x: 980, y: 600 }

# 桌面宠物
pet:
  enabled: true
  position: { x: 1820, y: 980 }  # 右下角
  size: 100
  initial_mood: "sleeping"

# 日志
logging:
  level: "INFO"
  file: "logs/moondeck.log"
  rotation: "10MB"
  retention: 7
```

### 9.2 `config/theme.yaml`

```yaml
# 主题配置
themes:
  dark:
    background: "#1a1a2e"
    foreground: "#e0e0ff"
    accent: "#b794f4"
    accent2: "#f6ad55"
    success: "#48bb78"
    error: "#f56565"
    border: "#2d3748"
    shadow: "rgba(0,0,0,0.5)"
    font: "Microsoft YaHei UI"
    border_radius: 12
    animation_ms: 200

  light:
    background: "#ffffff"
    foreground: "#1a1a2e"
    accent: "#3182ce"
    accent2: "#dd6b20"
    success: "#38a169"
    error: "#e53e3e"
    border: "#e2e8f0"
    shadow: "rgba(0,0,0,0.1)"
    font: "Microsoft YaHei UI"
    border_radius: 12
    animation_ms: 200

  glass:
    background: "rgba(255,255,255,0.15)"
    foreground: "#ffffff"
    accent: "#f6ad55"
    accent2: "#b794f4"
    success: "#48bb78"
    error: "#fc8181"
    border: "rgba(255,255,255,0.3)"
    shadow: "rgba(0,0,0,0.3)"
    font: "Microsoft YaHei UI"
    border_radius: 16
    animation_ms: 250

  neon:
    background: "#0a0a1a"
    foreground: "#00ff88"
    accent: "#ff00ff"
    accent2: "#00ffff"
    success: "#00ff00"
    error: "#ff0055"
    border: "#ff00ff"
    shadow: "rgba(255,0,255,0.5)"
    font: "Consolas"
    border_radius: 4
    animation_ms: 100
```

### 9.3 SQLite Schema

```sql
-- 布局
CREATE TABLE IF NOT EXISTS layout (
    card_id TEXT PRIMARY KEY,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    w INTEGER NOT NULL,
    h INTEGER NOT NULL,
    z_order INTEGER DEFAULT 0,
    visible INTEGER DEFAULT 1,
    last_updated INTEGER NOT NULL
);

-- 便签
CREATE TABLE IF NOT EXISTS sticky_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    color TEXT NOT NULL DEFAULT 'yellow',
    title TEXT,
    content TEXT NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    w INTEGER NOT NULL DEFAULT 250,
    h INTEGER NOT NULL DEFAULT 200,
    tags TEXT,                -- JSON array
    refs TEXT,                -- JSON array of other note ids
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    archived INTEGER DEFAULT 0
);
CREATE INDEX idx_sticky_archived ON sticky_notes(archived);
CREATE INDEX idx_sticky_updated ON sticky_notes(updated_at DESC);

-- 倒计时事件
CREATE TABLE IF NOT EXISTS countdown_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    target_date TEXT NOT NULL,         -- ISO 8601
    color TEXT DEFAULT '#f6ad55',
    icon TEXT,
    remind_days_before INTEGER DEFAULT 7,
    note TEXT,
    created_at INTEGER NOT NULL
);

-- 全局配置
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

-- 卡片运行时数据（缓存）
CREATE TABLE IF NOT EXISTS card_cache (
    card_id TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    data TEXT NOT NULL,                -- JSON
    expires_at INTEGER NOT NULL,
    PRIMARY KEY (card_id, cache_key)
);
CREATE INDEX idx_cache_expires ON card_cache(expires_at);

-- Token 卡片专用
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    used_tokens INTEGER NOT NULL,
    remaining_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    model TEXT NOT NULL
);
CREATE INDEX idx_token_ts ON token_usage(timestamp DESC);

-- 文件卡片专用
CREATE TABLE IF NOT EXISTS desktop_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    ext TEXT,
    size INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    category TEXT,             -- image/doc/video/archive/shortcut/other
    project TEXT,              -- 匹配前缀
    status TEXT DEFAULT 'present'  -- present/archived/deleted
);
CREATE INDEX idx_files_modified ON desktop_files(modified_at DESC);
CREATE INDEX idx_files_category ON desktop_files(category);
```

### 9.4 主题文件路径

```
config/
├── default.yaml      # 全局配置
├── theme.yaml        # 主题配置
├── hotkeys.yaml      # 快捷键
└── cards/
    ├── token_card.yaml
    ├── file_card.yaml
    └── ... (每个卡片一份)
```

---

## 10. 下一步行动

### 10.1 现在马上要做的 3 件事

1. **老大审核本规划文档**
   - 重点看 13 个卡片清单（顺序/优先级）
   - 重点看第 7 章路线图（4 阶段时间表）
   - 重点看第 9 章配置 schema（是否符合预期）

2. **确认 Phase 1 起手式**
   - 画布底座 1 周，Day 1-7 任务表已列
   - 建议老大指定**第一个要做的卡片**（按你之前的话："每完成一个我会指定下一个"）
   - 默认是 **Token 卡片移植**（已存在，参考实现价值最高）

3. **敲定技术细节**
   - 进程模型（已选单进程多 widget）
   - 数据库方案（已选 SQLite + SQLCipher 加密）
   - 打包方案（已选 PyInstaller）

### 10.2 第一个卡片：Token 卡片移植

**目标**：把 v3.6 的 Token 卡片从独立进程 → 跑在新画布上

**步骤**：

1. **Day 1**：新建 `core/canvas.py` + `core/card_base.py`，实现透明全屏
2. **Day 2**：移植 `minimax-token-card/card.py` → `cards/token_card/widget.py`
   - 重写类继承：`CardBase` 替代 `QWidget`
   - 实现 5 个方法：`init_ui / update_data / on_resize / serialize / deserialize`
3. **Day 3**：在 `main.py` 中实例化 `Canvas` + `TokenCard`
4. **Day 4**：打包测试

**验证标准**：

- [ ] 启动后画布**全屏透明**，不抢焦点
- [ ] 鼠标默认**穿透**到下方应用
- [ ] 按 Alt 键 → 卡片**可点击可拖动**
- [ ] 拖动卡片有磁吸效果
- [ ] 关闭后**位置保存**，下次启动恢复
- [ ] Token 卡片**每 30s 拉取数据**，UI 更新
- [ ] 切换主题（Dark / Light / Glass）→ 卡片**实时变色**
- [ ] 卡片**崩溃不影响画布**

### 10.3 风险预案

- **如果画布透明不生效** → 回退到 v3.6 验证过的 win32 API 路径
- **如果多显示器异常** → 先做主屏，全屏方案 v2 再加多屏
- **如果打包失败** → 先用 `python main.py` 跑通，再考虑打包

### 10.4 关键决策记录

| # | 决策 | 理由 |
|---|------|------|
| 1 | **单进程多 widget**（不是多进程）| 通信简单、资源省、开发快 |
| 2 | **基于 Qt Signal 的 EventBus**（不是 Redis/MQ）| 进程内通信够用，零依赖 |
| 3 | **SQLite 单文件**（不是 PostgreSQL/MySQL）| 零部署、便携、够用 |
| 4 | **PyQt6**（不是 PySide6 / Tkinter）| v3.6 已验证，社区资源多 |
| 5 | **PyInstaller 单 exe**（不是源码分发）| 用户友好 |
| 6 | **Alt 键切换交互态**（不是悬浮检测）| 简单、明确、不误触 |
| 7 | **和风天气 API**（不是 OpenWeatherMap）| 中国数据准、免费层够用 |

---

## 11. 代码审查与质量保障

> **核心问题**：13 个卡片、6000+ 行代码，**如果不在每个卡片完成后立刻审查**，bug 越堆越多，最后一起修等于重写。

### 11.1 三阶段审查机制（强制流程）

每个卡片完成时，**必须**走完三个阶段才能标记为 ✅：

```
[实现]  → [自测]  → [Code Review]  → [集成验证]  → [打 tag]
  ↓         ↓             ↓                ↓            ↓
开发        pytest      老大审核        跟其他卡片   v0.1.0
                          走查         联调跑一遍
```

#### 阶段 1：开发自测（开发者责任）

- [ ] 卡片单独 `python -m cards.<name>` 能跑起来
- [ ] 卡片 `tests/` 目录单测覆盖率 ≥ 70%
- [ ] 手动跑 5 个常见场景，截图存档
- [ ] 用 `ruff check` + `mypy --strict` 0 错

#### 阶段 2：Code Review（老大审核）

> **关键**：这一环**不能省**。就算开发者是 AI，也必须由老大走查一次。

老大走查清单（10 项）：

```markdown
□ 1. 卡片是否遵循 §6.1.1 目录结构？
□ 2. 卡片能否独立运行（`python -m cards.X`）？
□ 3. 卡片是否只用 EventBus 跟其他卡片通信（不直接 import）？
□ 4. 所有外部 IO 是否放在 service.py（不混在 widget.py）？
□ 5. 异常处理是否走 safe_run 装饰器？
□ 6. 是否有"独立 README + CHANGELOG"？
□ 7. 单测是否覆盖了 controller 和 service 两层？
□ 8. 是否有可能阻塞主线程的同步 IO？
□ 9. 卡片是否有"最坏情况降级 UI"（API 挂了显示什么）？
□ 10. 是否在 v3.6 token 卡片里复用过好用的代码（不重写）？
```

#### 阶段 3：集成验证（跟其他卡片一起跑）

- [ ] 启动完整 MoonDeck，加载这个卡片 + 至少 3 个其他卡片
- [ ] 让这个卡片通过 EventBus **主动**触发另一个卡片（如：日历卡片点事件 → 便签卡片自动建一条）
- [ ] 让另一个卡片**主动**触发这个卡片（如：银月卡片点 "查询 Token" → Token 卡片刷新）
- [ ] 关掉这个卡片，其他卡片不受影响
- [ ] 让这个卡片抛异常一次，其他卡片不崩

### 11.2 质量门槛（不达标不许进入下一卡）

| 指标 | 门槛 | 验证方式 |
|------|------|----------|
| **单测覆盖率** | ≥ 70% | `pytest --cov=cards.X --cov-report=term-missing` |
| **Linter** | 0 错 | `ruff check cards/X/` |
| **类型检查** | 0 错 | `mypy --strict cards/X/` |
| **代码行数** | 单文件 ≤ 500 行 | `cloc cards/X/` |
| **复杂度** | 单函数圈复杂度 ≤ 10 | `radon cc cards/X/ -a -s` |
| **审查清单** | 10 项全打勾 | 老大走查 |

### 11.3 审查节奏（每卡片时间盒）

| 卡片类型 | 实现 | 自测 | 老大 review | 集成 | 合计 |
|----------|------|------|------------|------|------|
| **简单**（Token / 天气 / 倒计时）| 1 天 | 0.5 天 | 0.5 天 | 0.5 天 | **2.5 天** |
| **中**（文件 / 日历 / 便签 / 搜索）| 2 天 | 1 天 | 1 天 | 1 天 | **5 天** |
| **复杂**（音乐 / 监控 / 银月 / AI）| 3 天 | 1.5 天 | 1.5 天 | 1.5 天 | **7.5 天** |

> **铁律**：老大 review 阶段**不允许跳**，不管卡片多简单。**简单卡片 review 0.5 天，复杂卡片 1.5 天**。

### 11.4 持续集成（CI / 本地脚本）

虽然 13 个卡片工作量小，但**留个本地脚本**让所有卡片统一跑一遍质控：

```bash
# tools/qa_check.sh（或 .ps1）
#!/bin/bash
# 每个卡片跑一遍
for card in cards/*/; do
    echo "=== QA: $card ==="
    cd "$card"
    pytest tests/ -v --tb=short || exit 1
    ruff check . || exit 1
    mypy --strict . || exit 1
    cd ../..
done
echo "✅ ALL CARDS PASS"
```

### 11.5 Bug 反馈通道

如果老大跑的过程中发现 bug：

1. 老大描述复现步骤 + 截图
2. 银月在**该卡片的 CHANGELOG.md** 追加 `[BUG]` 段
3. 银月修完，在 CHANGELOG 写 `[FIX]`，并补一个**回归测试**
4. 回归测试失败 → 不能算修完

```markdown
# TokenCard CHANGELOG

## v0.3.0 (2026-06-15)
- [BUG] Token 折线图刷新后残影（位置 Y=120 重叠）
- [FIX] 在 paintEvent 里加 `self.background = QPixmap(self.size())` 重绘背景
- [TEST] test_widget.py::test_line_chart_no_residual 回归测试

## v0.2.0 (2026-06-13)
- 首次发布
```

### 11.6 跳过审查的代价（反面教材）

> 老大原话："万一有 bug 等到最后才发现，代码太多了就不好发现了"

**真实场景推演**：
- Phase 2 写完 5 个卡片（2500 行），Phase 3 写完 6 个（3000 行）
- Phase 3 后期发现 Token 卡片的 EventBus emit 写错 key 名（`token:update` 写成 `tokens:update`）
- 这时候有 3 个卡片订阅了错误 key 名，2 个卡片 emit 了错误 key 名
- **修 1 个错 = 改 5 处**，还要担心改 key 时漏改订阅方
- **如果在 Phase 1 写 Token 时就审查**：1 处错，0 订阅方，0 风险

**结论**：审查**不是浪费时间**，是**乘数效应** —— Phase 1 审 0.5 天，Phase 3 节省 5 天。

---

## 12. 卡片独立交付 Checklist（每个卡片必走）

> 把 §6.1 + §11 浓缩成一个**可勾选的清单**，每完成一个卡片打勾一次。

### 交付前 24 项 Checklist

#### A. 目录结构（6 项）
- [ ] A1. `__init__.py` 导出主类
- [ ] A2. `widget.py` UI 渲染（与 controller 解耦）
- [ ] A3. `controller.py` 业务逻辑
- [ ] A4. `service.py` 外部数据获取
- [ ] A5. `config.py` 卡片专属配置
- [ ] A6. `tests/` 三层测试齐全

#### B. 独立性（4 项）
- [ ] B1. `python -m cards.<name>` 单独跑起来
- [ ] B2. 卡片能脱离 MoonDeck 单独 import 使用
- [ ] B3. 卡片能单独 PyInstaller 打包
- [ ] B4. 卡片不需要 core 之外的任何外部模块

#### C. 通信（3 项）
- [ ] C1. 卡片只用 EventBus 跟其他卡片通信
- [ ] C2. 卡片不直接 import 任何其他卡片
- [ ] C3. 卡片所有 emit 的事件在 `core/events.py` 注册（命名规范）

#### D. 健壮性（4 项）
- [ ] D1. 所有外部 IO 在 service.py 异步
- [ ] D2. 所有 controller 方法用 `@safe_run` 装饰
- [ ] D3. 卡片有"降级 UI"（API 挂了显示什么）
- [ ] D4. 异常不影响其他卡片（L2 隔离已验证）

#### E. 文档（4 项）
- [ ] E1. `README.md`（用途 / 截图 / 配置项 / 事件）
- [ ] E2. `CHANGELOG.md`（版本 / BUG / FIX 记录）
- [ ] E3. 卡片配置 schema 在 `config.py` 有 dataclass + docstring
- [ ] E4. 至少 1 个使用示例在 README

#### F. 质量（3 项）
- [ ] F1. `pytest tests/` 全过 + 覆盖率 ≥ 70%
- [ ] F2. `ruff check` + `mypy --strict` 0 错
- [ ] F3. 单文件 ≤ 500 行

#### G. 集成（2 项）
- [ ] G1. 跟至少 3 个其他卡片联调跑过
- [ ] G2. **老大 review 10 项走查全部打勾**

### 完成后输出

```markdown
## [CardName] v0.1.0 ✅

**交付日期**：2026-06-XX
**代码量**：XXX 行
**单测覆盖率**：XX%
**Linter / Type Check**：0 错

### 独立运行
\`\`\`bash
python -m cards.card_name
\`\`\`

### 截图
[附 desktop_clean.png]

### 审查记录
- 老大 review 日期：2026-06-XX
- review checklist：24/24 ✅

### 已知问题
- 无 / [如有，列在 CHANGELOG]
```

---

## 📌 附录

### 附录 A：参考资源

- [PyQt6 透明窗口最佳实践](https://doc.qt.io/qt-6/qwidget.html#transparency-and-drag-and-drop)
- [Windows WS_EX_LAYERED 文档](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-styles)
- [飞书开放平台](https://open.feishu.cn/)
- [和风天气 API](https://dev.qweather.com/)
- [Rainmeter 设计理念](https://docs.rainmeter.net/)

### 附录 B：变更日志

| 版本 | 日期 | 作者 | 变更 |
|------|------|------|------|
| v1.0 | 2026-06-12 | 银月 | 初版规划 |

---

*文档结束 🌙*

> "好的架构不是设计出来的，是**演进**出来的。" —— 银月 2026-06-12
