# 🌙 MoonDeck 月坞

> **Windows 桌面浮窗卡片系统** —— 透明画布 + 月历 + 音乐 + 桌面宠物 + 粒子动效

![Python](https://img.shields.io/badge/python-%E2%89%A53.11-green)
![PyQt](https://img.shields.io/badge/gui-PyQt6-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2B-lightgrey)

---

## 这是什么

MoonDeck 不是传统 APP，它是一个**透明的桌面画布**，铺满整个屏幕（看起来不存在），上面可以放任意数量的浮窗卡片。

## 已实现

| # | 组件 | 说明 |
|---|------|------|
| 1 | 🗓️ **月历卡** | 农历 + 飞书日程 + Token 额度 + 天气集成 + 底部音乐区域 |
| 2 | 🎵 **音乐卡** | 独立音乐卡片：WASAPI 频谱律动 + SMTC 元数据 + 歌词滚动 + 播放控制 |
| 3 | 🌌 **桌面背景动效** | 粒子星云 / 星空 / 几何曼陀罗，70 粒子随音乐律动 |
| 4 | 💬 **歌词动效** | 飘字流 / 粒子字两种模式 |
| 5 | 🐾 **小紫桌宠** | 5 角色切换 + 气泡台词 + 拖拽跟随 |
| 6 | 🎨 **主题切换** | 深色 / 浅色 / 毛玻璃 / 霓虹，4 套主题 |
| 7 | ⌨️ **快捷键系统** | Alt 唤起交互 / Ctrl+Alt+T 切换主题 / 背景/桌宠/歌词动效切换 |
| 8 | 📋 **系统托盘** | 右键菜单：全显/全隐/单卡显隐/主题切换/动效切换/退出 |

## 核心特性

### 极致透明
- 画布**永远不抢焦点**
- 默认鼠标可以"穿过"卡片点到下面的应用
- 按住 `Alt` 键 → 进入交互态 → 可以拖动、点击、滚动

### 多显示器 + DPI 自适应
- 支持 4K 屏、2K 屏、混合 DPI
- 卡片位置**按显示器保存**，不串位

### 崩溃隔离
- 一个卡片挂了 ≠ 整个画布挂
- 错误日志写到 `logs/` 不影响主进程

### 数据本地化
- 所有数据存 SQLite，不上云
- 导出 / 导入配置（一份 YAML 走天下）

---

## 🏗️ 目录结构

```
MoonDeck/
├── main.py                    # 入口
├── config/                    # 配置
│   ├── default.yaml           # 默认配置（卡片列表、位置、快捷键）
│   ├── theme.yaml             # 主题配置
│   └── hotkeys.yaml           # 快捷键
├── core/                      # 画布核心
│   ├── canvas.py              # 透明全屏主窗口
│   ├── card_base.py           # 卡片基类
│   ├── theme.py               # 主题管理器
│   ├── drag_manager.py        # 拖拽 + 缩放 + 吸附
│   ├── click_manager.py       # 右键菜单
│   ├── event_bus.py           # 卡片间通信
│   ├── hotkey_manager.py      # 全局快捷键
│   ├── desktop_bg.py          # 桌面背景动效（粒子/星空/曼陀罗）
│   ├── desktop_pet.py         # 小紫桌宠（sprite sheet + 多角色）
│   └── tray.py                # 系统托盘
├── cards/                     # 卡片模块
│   ├── calendar_card/         # 🗓️ 月历（农历+日程+Token+天气+音乐区）
│   ├── music_card/            # 🎵 音乐（频谱+SMTC+歌词+控制）
│   ├── token_card/            # Token 服务（已集成进月历）
│   └── weather_card/          # 天气服务（已集成进月历）
├── tests/                     # 测试
├── docs/                      # 文档
├── PROJECT_PLAN.md            # 完整项目规划
├── requirements.txt           # 依赖
└── MoonDeck.spec              # PyInstaller 打包配置
```

---

## 🛠️ 技术栈

| 层 | 选型 |
|----|------|
| **GUI** | PyQt6 |
| **配置** | PyYAML |
| **数据库** | SQLite |
| **音频采集** | pyaudiowpatch (WASAPI Loopback) |
| **系统媒体控制** | winrt (SMTC) |
| **系统监控** | psutil |
| **文件监控** | watchdog |
| **打包** | PyInstaller |

---

## 🚀 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python main.py

# 调试模式
python main.py --debug
```

---

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Alt` | 进入交互态（可拖拽/点击） |
| `Esc` | 退出交互态 |
| `Ctrl+Alt+T` | 切换主题 |
| `Ctrl+Alt+B` | 切换桌面背景动效 |
| `Ctrl+Alt+L` | 切换歌词动效 |
| `Ctrl+Alt+P` | 切换桌宠显示 |

---

## 📚 文档

- [PROJECT_PLAN.md](./PROJECT_PLAN.md) —— 完整架构设计
- [config/default.yaml](./config/default.yaml) —— 配置说明

---

## 第三方资源

本项目使用的部分桌宠 sprite sheet 来自 [Petdex](https://petdex.dev)（开源 Codex 宠物画廊，3000+ 社区提交角色）：

| 角色 | Petdex 信息 |
|------|-------------|
| 陈千语 (chen-qianyu) | [Petdex #2028](https://petdex.dev/pets/chen-qianyu) by ZIHAN L. |
| 汐月同学 (xiyue) | [Petdex](https://petdex.dev/pets/xiyue) by bluefrog |
| 晕晕 (yunyun) | [Petdex](https://petdex.dev/pets/yunyun) by march-7th-mini |
| Lian | [Petdex](https://petdex.dev/pets/lian) by ustinaian |
| 问鼎王林 (wang-lin-wending) | [Petdex](https://petdex.dev/pets/wang-lin-wending-pixel) by 15821914639 |

> 以上角色 sprite sheet 遵循 Petdex 项目许可协议。

其余资源均为本项目原创：
- **小紫桌宠（矢量版）**：纯 QPainter 绘制，不依赖外部 sprite
- **桌面背景动效**：粒子星云 / 星空 / 几何曼陀罗 / 歌词飘字流 / 歌词粒子字
- **pet_gen/** 目录：AI 生成素材，不随仓库分发

---

## 🐺 作者

**老大**（产品 + 架构） + **银月**（AI 协作者 · 🌙 狼灵）

---

*最后更新：2026-06-20*
