# mikan_emu

> 模拟器前端 + 配置管家 + 版本识别器

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.5+-green.svg)](https://doc.qt.io/qtforpython/)

## 项目简介

mikan_emu 是一款基于 PySide6 开发的模拟器前端管理工具，提供游戏库管理、模拟器下载/导入、BIOS 管理、存档备份还原、多语言支持等一站式功能。单文件应用，开箱即用，无需复杂配置。

> **法律声明**：本项目不提供任何 BIOS 文件、ROM 镜像或模拟器二进制文件。请用户自行从官方渠道获取。

## 功能特性

### 核心功能

- **游戏库管理** — 列表/网格双视图，支持搜索、筛选、排序、收藏、封面图展示、游戏时长统计
- **模拟器管理** — 支持导入/下载模拟器引擎，支持压缩包和文件夹两种导入方式
- **BIOS 管理** — 自动扫描 bios/ 目录，MD5 文件识别
- **智能启动器** — 每款游戏可单独配置模拟器、平台覆盖、附加启动参数
- **多线程下载器** — 支持多线程下载模拟器，进度显示，自动解压安装
- **存档管理** — 自动备份/还原游戏存档，支持多模拟器路径自动检测

### 技术特性

- **单文件应用** — 全部逻辑集成在单个 Python 文件中，便于分发和部署
- **自启动依赖检查** — 首次运行自动检测并安装缺失的 Python 依赖包
- **多镜像源支持** — 内置清华/阿里/pypi.org 等多 PyPI 镜像源，自动切换
- **GitHub 镜像加速** — 设置页可自定义镜像站地址，支持增删/排序/测试
- **完整 I18N** — 内置中文/英文国际化，tr() 函数处理翻译
- **Windows 11 风格 UI** — 基于 PySide6 的现代化界面，大量 QSS 样式表定制
- **日志系统** — 基于 loguru 按天轮转，14 天自动保留
- **进程监控** — 基于 psutil 记录游戏运行时长
- **代理支持** — 支持 PROXY_URL 环境变量配置代理
- **提权重启** — Windows UAC 管理员权限自动提权

### 支持平台

| 平台 | 模拟器引擎 |
|------|-----------|
| SFC / 超级任天堂 | snes9x |
| PS1 / PlayStation | duckstation, ePSXe, xebra |
| SS / 世嘉土星 | mednafen, SSF |
| GBA | mgba |
| PS2 / PlayStation 2 | pcsx2 |
| FC / NES | fceux, Mesen |
| N64 | mupen64plus |
| PSP | ppsspp |
| NDS / DS | desmume, melonds |
| Switch | ryujinx |
| 其他 | blastem, sameboy, gambatte 等 |

## 安装运行

### 环境要求

- Python 3.11 或更高版本
- Windows 10/11（当前主要支持平台）

### 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/<your-username>/mikan_emu.git
cd mikan_emu

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python mikan_emu.py
```

首次运行会自动检测并安装缺失的依赖包。

## 项目结构

```
mikan_emu/
├── mikan_emu.py          # 主程序（单文件应用）
├── requirements.txt      # Python 依赖
├── LICENSE               # GPL v3 许可证
├── README.md             # 项目说明
├── .gitignore
└── mikan_emu/            # 运行时数据目录（自动创建）
    ├── config/           # 配置文件
    ├── engines/          # 模拟器引擎
    ├── bios/             # BIOS 文件
    ├── roms/             # 游戏 ROM
    ├── saves/            # 游戏存档
    ├── saves_backup/     # 存档备份
    ├── covers/           # 游戏封面
    ├── backups/          # 系统备份
    ├── logs/             # 日志文件
    └── temp/             # 临时文件
```

## 开发说明

### 代码结构

主文件按注释区块组织，分为以下逻辑段：

| 区块 | 内容 |
|------|------|
| 0 | 代理 + 环境变量配置 |
| 1 | 依赖自检与自动安装 |
| 2 | 模块导入 |
| 3 | 路径与常量定义 |
| 4 | 多语言（I18N） |
| 5 | 配置管理 |
| 6 | 模拟器引擎定义（engines.json） |
| ... | 更多模块... |

### 添加新模拟器

在 engines.json 中添加新的平台/引擎配置即可，支持定义下载 URL、匹配规则、启动模板等。

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 免责声明

- 本项目仅为模拟器前端管理工具，不提供任何游戏 ROM、BIOS 或模拟器二进制文件
- 用户应自行从官方渠道获取所需的游戏 ROM 和模拟器软件
- 使用本项目产生的任何法律问题由用户自行承担

## 开源许可

本项目采用 [GNU General Public License v3](LICENSE) 开源许可。

---

Made with love by mikan_emu contributors
