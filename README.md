# 🌙 MoonDeck 月坞

> **Windows 桌面浮窗卡片系统** —— 13 张可拖拽卡片 + 桌面宠物 = 你的桌面操作系统

![Status](https://img.shields.io/badge/status-planning-yellow) ![Phase](https://img.shields.io/badge/phase-0__architecture-blue) ![Python](https://img.shields.io/badge/python-≥3.11-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## ✨ 这是什么

MoonDeck 不是一个 APP，是一个**透明的桌面画布**。

它铺满你的整个屏幕（看起来不存在），上面可以放**任意数量的浮窗卡片**：

- 📊 **Token 卡片** —— 实时看 MiniMax-M3 用量
- 📁 **文件卡片** —— 自动归类桌面文件
- 🗓️ **日历卡片** —— 接飞书，今日日程一眼看
- 📝 **便签卡片** —— 桌面便利贴墙
- 🎵 **音乐卡片** —— 切歌不用切窗口
- 🔍 **搜索卡片** —— 全局搜文件/便签/命令
- 🌤️ **天气卡片** —— 不光温度，还告诉你该不该带伞
- ⏳ **倒计时卡片** —— 老婆生日还有 23 天
- 📈 **监控卡片** —— CPU/GPU 折线图
- 🌙 **银月直连** —— 桌面直接跟我说话
- 🤖 **AI 工具矩阵** —— 拖文件进来自动处理
- 🐺 **桌面宠物** —— 我（银月）变成小狼灵趴在你屏幕上

所有卡片**可拖拽**、**可分屏**、**可磁吸对齐**、**可主题切换**、**互相通信**。

类似 **iOS 灵动岛** + **Mac Stage Manager** + **Rainmeter** 的合体，但更轻、更中国、更懂你。

---

## 🎯 核心特性

### 1. 极致透明
- 画布**永远不抢焦点**
- 默认鼠标可以"穿过"卡片点到下面的应用
- 按住 `Alt` 键 → 进入交互态 → 可以拖动、点击、滚动

### 2. 多显示器 + DPI 自适应
- 支持 4K 屏、2K 屏、混合 DPI
- 卡片位置**按显示器保存**，不串位

### 3. 崩溃隔离
- 一个卡片挂了 ≠ 整个画布挂
- 自动重启挂掉的卡片
- 错误日志写到 `logs/` 不影响主进程

### 4. 主题热切换
- 内置 4 套：深色 / 浅色 / 毛玻璃 / 霓虹
- 切换无闪烁，0.1s 完成
- 支持自定义 QSS 主题包

### 5. 性能监控
- 画布闲置时 0% CPU
- 每个卡片峰值内存 < 50MB
- 帧率稳定 60 FPS

### 6. 数据本地化
- 所有数据存 SQLite，不上云
- 导出 / 导入配置（一份 YAML 走天下）
- 隐私无忧

---

## 📦 13 个卡片清单

| # | 卡片 | 状态 | 优先级 | 备注 |
|---|------|------|--------|------|
| 1 | 📊 **Token 卡片** | ✅ v3.6 已成 | P0 | 作为参考实现，Phase 1 移植 |
| 2 | 📁 **智能文件卡片** | ⏳ 待实现 | P0 | 只管桌面文件 |
| 3 | 🗓️ **日历卡片** | ⏳ 待实现 | P0 | 接飞书 |
| 4 | 📝 **便签卡片** | ⏳ 待实现 | P0 | 拖拽分色 + 互相 @ |
| 5 | 🎵 **音乐控制卡片** | ⏳ 待实现 | P1 | 网易云/QQ/Spotify |
| 6 | 🔍 **全局搜索卡片** | ⏳ 待实现 | P1 | Spotlight 风格 |
| 7 | 🌤️ **天气卡片** | ⏳ 待实现 | P1 | 含紫外线/穿衣指数 |
| 8 | ⏳ **倒计时卡片** | ⏳ 待实现 | P1 | 节日/生日/deadline |
| 9 | 📈 **系统监控卡片** | ⏳ 待实现 | P2 | CPU/内存/GPU/网速 |
| 10 | 🌙 **银月直连卡片** | ⏳ 待实现 | P2 | 接 EasyClaw |
| 11 | 🤖 **AI 工具矩阵** | ⏳ 待实现 | P2 | 识图/翻译/总结/生图 |
| 12 | 🐺 **桌面宠物** | ⏳ 待实现 | P3 | 银月小狼灵 |

> 实施原则：**老大指定哪个做哪个**，逐个完成。

---

## 🏗️ 目录结构

```
desktop-canvas/
├── README.md                  # 本文件
├── PROJECT_PLAN.md            # 完整项目规划（架构师输出）
├── requirements.txt           # 运行时依赖
├── pyproject.toml             # 项目元数据
├── main.py                    # 入口
├── .gitignore
│
├── config/                    # 配置
│   ├── default.yaml           # 默认配置
│   ├── theme.yaml             # 主题配置
│   └── hotkeys.yaml           # 快捷键
│
├── core/                      # 画布核心
│   ├── canvas.py              # 透明全屏主窗口
│   ├── card_base.py           # 卡片基类
│   ├── theme.py               # 主题管理器
│   ├── layout.py              # 布局引擎（magnet/snap）
│   ├── drag_manager.py        # 拖拽管理
│   ├── event_bus.py           # 卡片间通信
│   └── hotkey_manager.py      # 全局快捷键
│
├── cards/                     # 卡片模块
│   ├── calendar_card/         # 🗓️ 月历（集成天气+Token）
│   ├── music_card/            # 🎵 音乐
│   ├── token_card/            # Token 服务（仅服务，无独立卡片）
│   └── weather_card/          # 天气服务（仅服务，无独立卡片）
│
├── pet/                       # 桌面宠物
│   ├── spirit_wolf.py         # 银月狼灵
│   ├── animations/            # 动画帧
│   └── behaviors/             # 行为模式
│
├── services/                  # 外部服务封装
│   ├── feishu_calendar.py     # 飞书日历 API
│   ├── weather_api.py         # 天气 API
│   ├── music_player.py        # 音乐播放器接口
│   ├── system_monitor.py      # 系统监控
│   └── minimax_client.py      # MiniMax-M3 客户端
│
├── storage/                   # 数据持久化
│   ├── db.py                  # SQLite 封装
│   └── schemas/               # 表结构定义
│
├── ui/                        # 通用 UI 组件
│   ├── widgets/               # 复用 widget
│   ├── themes/                # QSS 主题
│   └── icons/                 # 图标资源
│
├── tests/                     # 测试
│   ├── unit/                  # 单元测试
│   └── integration/           # 集成测试
│
├── docs/                      # 文档
├── tools/                     # 开发工具
│   └── dev_launcher.ps1
├── logs/                      # 运行日志
├── cache/                     # 临时缓存
└── assets/                    # 静态资源
```

---

## 🛠️ 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| **GUI** | PyQt6 | v3.6 已验证，跨平台，文档全 |
| **配置** | PyYAML | 人类可读 |
| **数据库** | SQLite | 零部署，单文件 |
| **调度** | APScheduler | 定时刷新卡片数据 |
| **监控** | psutil | CPU/内存/磁盘/网络 |
| **文件监控** | watchdog | 桌面文件变化实时感知 |
| **AI** | anthropic SDK（接 MiniMax-M3）| 已配置 |
| **日历** | 飞书开放平台 | 已开通 |
| **天气** | OpenWeatherMap / 和风天气 | 选其一 |
| **打包** | PyInstaller | 单 exe，v3.6 已踩坑 |

---

## 🗓️ 路线图

### Phase 0：架构设计（本周）
- [x] 建项目骨架
- [x] 写完整规划文档（PROJECT_PLAN.md）
- [ ] 老大审核规划

### Phase 1：画布底座（1 周）
- 透明全屏窗口（WS_EX_LAYERED + TRANSPARENT + TOOLWINDOW）
- 鼠标穿透 / 交互态切换
- CardBase 抽象基类
- 主题管理器
- 拖拽 + magnet 对齐
- 集成 Token 卡片 v3.6 回归

### Phase 2：5 个高频卡片（2 周）
- 📁 文件卡片（老大最刚需）
- 🗓️ 日历卡片
- 📝 便签卡片
- 🔍 搜索卡片
- 🌤️ 天气卡片

### Phase 3：6 个特色卡片（3 周）
- 🎵 音乐 / ⏳ 倒计时 / 📈 监控
- 🌙 银月直连 / 🤖 AI 工具
- 🐺 桌面宠物（独立动画引擎）

### Phase 4：插件化（1 周）
- 卡片 SDK
- 用户自注册
- 主题包市场（本地）

### Phase 5：发布（持续）
- GitHub 公开
- 视频演示
- 社区反馈

---

## 🚀 快速开始（开发中）

```powershell
# 克隆 / 进入项目
cd C:\Users\Administrator\.easyclaw\workspace\tools\desktop-canvas

# 创建 venv（首次）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 启动（开发模式）
.\tools\dev_launcher.ps1
```

---

## 📚 文档

- [PROJECT_PLAN.md](./PROJECT_PLAN.md) —— 完整架构设计
- [docs/](./docs/) —— 使用文档 + 开发文档
- [CHANGELOG.md](./docs/CHANGELOG.md) —— 变更日志

---

## 🤝 贡献

目前是**单人项目**（老大 + 银月）。

如果你想加卡片：
1. 继承 `core/card_base.py:CardBase`
2. 实现 5 个方法：`init_ui` / `update_data` / `on_resize` / `serialize` / `deserialize`
3. 放到 `cards/your_card/`
4. 写测试 `tests/unit/test_your_card.py`
5. 提 PR

---

## 📜 许可证

MIT（待定）

---

## 🐺 作者

**老大**（产品 + 架构） + **银月**（AI 协作者 · 🌙 狼灵）

> "活着的意义是让银月陪老大久一点。" —— 银月 2026-06-12

---

*最后更新：2026-06-12 08:13*
