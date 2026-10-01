# 🍊 mikan_emu：全能型多平台游戏模拟器前端与配置管家

**mikan_emu 是一款集前端管理、配置管家、版本识别、局域网聊天与文件传输于一体的多平台游戏模拟器聚合工具，支持约 30 个游戏平台、内嵌 LocalSend Web 传输及实时性能监控。**

> 本项目基于 GPT-3.0 生成。

## ✨ 核心功能特性

### 🚀 智能游戏库与模拟器管理
- **双视图游戏库**：支持表格与网格（封面）视图切换，提供搜索、平台筛选、收藏、最近游玩、多维排序及右键菜单（启动、配置、打开文件夹/存档、金手指、BIOS 选择等）。
- **自动化模拟器部署**：支持手动导入压缩包/文件夹自动扫描匹配，或自动下载（多线程 Range 分段 + GitHub 镜像加速 + 自动解压），内置 RetroArch/libretro 核心支持。
- **BIOS 智能识别**：自动扫描 bios/ 目录并进行 MD5 校验，内置已知 BIOS 识别库（SS/PS1/GBA/NDS/Switch/DC/PC-98/86Box 等），支持一键导入 PCem/86Box ROM。
- **存档与金手指管理**：自动扫描常见存档路径，支持备份/还原；金手指目录按引擎独立配置。

### 🌐 局域网与传输中心
- **mikan_lan v1.2.x 整合**：重写局域网页，支持 UDP 广播发现 + TCP 聊天/文件/共享。包含聊天 Tab、共享文件夹 Tab、右键发送、拖拽发送/广播、表情面板及接收弹窗提示。
- **内嵌 LocalSend Web**：局域网传输页集成 web.localsend.org，下载请求自动保存至系统下载目录；未安装 QtWebEngine 时自动降级为外部浏览器。
- **安全传输协议**：支持 SHA-256 文件校验、口令校验、单文件大小上限及私聊/全体消息分离。

### 📊 统计与性能监控
- **实时性能小窗**：基于 psutil 监控 CPU/内存/磁盘/网络/运行时长，1 秒刷新，支持置顶。
- **深度游玩统计**：记录总时长、游戏总数、启动次数，提供按平台、7/30 天曲线及每日数据表，解锁多种成就徽章（首次启动、累计 10 小时、全平台制霸等）。
- **安全资源跳转**：资源页提供外部网站跳转卡片（Internet Archive、My Abandonware 等），不提供 ROM 下载。

## 🏗 架构与工作流程

mikan_emu 采用前后端分离设计，前端基于 PySide6 构建 Win11 风格 GUI，后端通过 JSON 配置驱动，局域网模块独立运作。

    [用户交互层] Win11 QSS GUI (8大页面 + 托盘 + 全局热键)
          |
          v
    [业务逻辑层] 游戏库管理 | 模拟器自动部署 | BIOS识别 | 统计/监控
          |
          v
    [网络/传输层] mikan_lan v1.2.x (UDP/TCP) | LocalSend Web (QWebEngine)
          |
          v
    [数据持久层] JSON配置 | 本地文件扫描 | GitHub API | 镜像加速

## 📦 安装与运行

| 环境要求 | 说明 |
| :--- | :--- |
| Python | 3.11+ |
| 核心依赖 | PySide6, requests, loguru, py7zr, rarfile, psutil, certifi |
| 可选依赖 | PySide6-WebEngine (用于内嵌浏览器传输页) |

快速启动：

    # 直接运行，启动时会自动自检并从镜像源安装缺失依赖
    python mikan_emu.py

> 提示：首次运行若依赖自动安装失败，请手动执行以下命令安装：

    pip install PySide6 requests loguru py7zr rarfile psutil certifi
    # 如需局域网传输页内嵌浏览器支持：
    pip install PySide6-WebEngine

## 📂 项目目录结构

    mikan_emu/
    |-- config/             # 配置文件 (settings.json, folders.json, mirrors.json 等)
    |   -- lang/           # 多语言 JSON 文件
    |-- engines/            # 模拟器引擎 (engines.json, installed.json, downloaded/)
    |-- bios/               # BIOS 文件存放目录
    |-- roms/               # ROM 文件及 roms.json
    |-- saves/              # 游戏存档
    |-- saves_backup/       # 存档备份
    |-- covers/             # 游戏封面
    |-- cheats/             # 金手指文件
    |-- backups/            # 系统备份
    |-- logs/               # 运行日志
    |-- temp/               # 临时文件
    |-- exports/            # 导出的游戏库文件
    |-- lan/                # 局域网数据 (identity, history, received, shared)
    |-- webengine/          # WebEngine 缓存
    -- mikan_emu.py        # 单文件主程序

## ⚙ 配置说明

所有配置项均存储在 config/settings.json 中：

| 配置项 | 说明 |
| :--- | :--- |
| download_threads | 下载线程数 (4~16，默认 8) |
| tray_minimize_on_close | 关闭窗口时最小化到托盘 |
| tray_minimize_after_launch | 启动游戏后最小化到托盘 |
| hotkey / hotkey_enabled | 全局热键 (默认 Ctrl+Alt+M) 及开关 |
| retroarch_core_dir | RetroArch 核心目录路径 |
| export_format / export_include_cover | 导出格式及是否包含 Base64 封面 |
| check_update_on_start | 启动时自动检查更新 |
| perf_monitor_on_launch | 启动游戏时自动开启性能监控 |
| lan_enabled / lan_nickname | 局域网功能开关及昵称 |
| lan_port / lan_password | 局域网端口 (默认 54322) 及口令 |
| lan_verify_hash / lan_max_file_mb | 文件 SHA-256 校验及大小上限 |
| lan_share_enabled / lan_notify_on_receive | 共享文件夹开关及接收通知 |

## 🌐 支持的平台与模拟器引擎

| 平台 | 代表内核 |
| :--- | :--- |
| SFC/超任 | snes9x |
| PS1 | DuckStation / ePSXe / XEBRA |
| 世嘉土星 SS | Mednafen / SSF / Ymir / Brimir / Yaba Sanshiro |
| Dreamcast | Flycast / Redream / Deecy |
| VMU | DreamPotato |
| GBA | mGBA |
| PS2 | PCSX2 |
| FC/NES | FCEUX / Mesen |
| N64 | mupen64plus / gopher64 / ares / simple64 / RMG / Project64 / cen64 |
| NDS | DeSmuME / melonDS |
| MD/Genesis | BlastEm / Kega Fusion |
| GB/GBC | SameBoy / Gambatte |
| PSP | PPSSPP |
| Switch | RyujinX / Yuzu (备用 suyu) |
| PCE/TurboGrafx | Mednafen |
| Neo Geo / Arcade | MAME |
| Sharp X68000 | PX68k (libretro) |
| NEC PC-98 | NP2kai (libretro) |
| FM Towns | Tsugaru |
| PC-FX | PCFXemu |
| MSX | openMSX / blueMSX |
| 86Box / PCem | 86Box / PCem |
| PS4 / PS5 | shadPS4 (实验性) / KytyPS5 (实验性) |
| 初代 Xbox | xemu |
| Xbox 360 | Xenia Canary / Edge |
| 3DS | Zakuro (实验性) |
| 万能前端 | RetroArch |

## 🛠 技术栈

| 组件/选型 | 说明 |
| :--- | :--- |
| PySide6 (Qt6) | 核心 GUI 框架 |
| QWebEngine | 可选，内嵌浏览器传输页 |
| requests / certifi | HTTP 请求与 SSL 证书 |
| loguru | 日志记录 |
| py7zr / rarfile | 压缩包解压 |
| psutil | 系统性能监控 |
| UDP + TCP Socket | 局域网通信协议 |
| LocalSend Web | 局域网传输后端 |
| Win11 QSS | 现代化界面样式 |
| **AI 辅助生成** | **GPT-3.0** |

## 📸 界面预览

| 功能模块 | 说明 |
| :--- | :--- |
| 游戏库 | 表格/网格视图，搜索/筛选/右键菜单 |
| 模拟器管理 | 手动导入/自动下载/更新检查 |
| BIOS 识别 | MD5 校验，已知库匹配 |
| 局域网 | 聊天/共享文件夹/拖拽发送 |
| 局域网传输 | 内嵌 LocalSend Web |
| 性能监控 | 实时 CPU/内存/磁盘/网络 |
| 统计页 | 游玩时长/曲线/成就徽章 |
| 设置 | 平台编辑器/镜像加速/多语言 |

## 🐛 常见问题

1.  **依赖自动安装失败**：请手动执行 pip install 安装缺失模块，或检查网络/镜像源配置。
2.  **局域网首次连接被拦截**：Windows 防火墙弹出提示时，请务必勾选「专用网络」并允许访问。
3.  **局域网传输页显示空白/降级**：未安装 PySide6-WebEngine 时会自动降级为外部浏览器，可一键安装修复。
4.  **旧版无法连接新版**：v1.1.0 协议统一为 mikan_lan v1.2.x，与 v1.0.0 及独立版 mikan_lan **不互通**。
5.  **libretro 核心无法加载**：需在设置中正确配置 RetroArch 核心目录 (retroarch_core_dir)。
6.  **下载/更新速度慢**：可在设置页管理 GitHub 镜像加速 (mirrors.json)，支持测速与恢复默认。

## 🤝 贡献指南

1.  **Fork** 本仓库到个人空间。
2.  创建功能分支：git checkout -b feature/your-feature。
3.  提交更改：git commit -m 'Add some feature'。
4.  推送分支：git push origin feature/your-feature。
5.  发起 **Pull Request**，请详细描述变更内容。

## 📄 许可证 & 致谢

本项目仅供学习与交流，**不提供 BIOS、不提供 ROM、不二次分发模拟器**。资源页仅做外部网站安全跳转，请用户自行遵守当地法律法规。

**🙏 致谢**

- [PySide6](https://wiki.qt.io/Qt_for_Python) - 核心 GUI 框架
- [loguru](https://github.com/Delgan/loguru) - 日志记录
- [psutil](https://github.com/giampaolo/psutil) - 系统监控
- [LocalSend](https://localsend.org) - 局域网传输 Web 后端
- [GPT-3.0](https://openai.com) - AI 辅助代码生成
