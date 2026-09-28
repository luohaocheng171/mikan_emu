MikanEmu v0.9.2
模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言 + 平台编辑器
https://img.shields.io/badge/License-GPLv3-blue.svg
https://img.shields.io/badge/Python-3.11+-green.svg
https://img.shields.io/badge/GUI-PySide6-purple.svg
https://img.shields.io/badge/Platform-Windows-blue.svg

项目介绍
MikanEmu 是一款功能强大的模拟器前端管理工具，集游戏库管理、模拟器引擎配置、BIOS 管理、存档备份、多语言支持、平台编辑器于一体。内置 24 个平台 / 44 个模拟器的完整配置数据，支持自动下载、导入、更新检查、版本识别等功能，提供 Windows 11 浅色风格的图形界面，是模拟器玩家的一站式管理利器。

【法律声明】本项目不提供 BIOS、不提供 ROM、不二次分发模拟器。

功能特性
游戏库管理：支持网格视图 / 列表视图，搜索、筛选（全部/收藏/最近）、排序（名称/最近玩过/时长），右键菜单支持启动、配置、设置封面、管理金手指等

模拟器引擎管理：已安装模拟器列表管理，支持导入（压缩包/文件夹/手动指定）、自动下载（GitHub Releases / 直接 URL / libretro / 裸 exe）、更新检查、跳过版本

BIOS / 固件管理：自动扫描 bios/ 目录，显示文件大小、MD5、识别状态，支持为游戏指定 BIOS 文件，启动时自动复制到模拟器 BIOS 目录

存档管理：自动扫描常见存档路径，支持备份所有存档、还原存档、管理存档目录

金手指管理：为每个模拟器指定金手指目录和文件扩展名，一键打开对应目录

版本识别与更新检查：自动识别已安装模拟器版本，通过 GitHub API 检查更新（仅 GitHub Releases 源），支持镜像加速

多语言支持：内置简体中文 / English / Русский / 日本語 / Français 五种语言，语言包外置 JSON 格式，支持用户自行编辑翻译或新增语言

资源导航页：内置 18 个老游戏 / ROM 站点跳转链接（安全 / 灰色分类），用户可增删改

操作说明：内置 40 个引擎的默认键位表，可查看官方文档

鸣谢页：列出所有依赖项目和开源模拟器项目

游戏统计：总时长、游戏总数、启动次数统计，按平台 / 最近 7 天 / 最近 30 天分类，含徽章系统

导出游戏库：支持导出为 Markdown / HTML / CSV 格式，可选包含封面、收藏过滤、平台过滤

平台编辑器：设置页内置平台管理器，可增删改自定义平台，自动写入 engines.json

系统托盘：支持关闭时最小化到托盘、启动游戏后最小化、托盘右键快速启动最近游戏

GitHub 镜像加速：可配置多个 GitHub 镜像站（按顺序尝试）、API 镜像、一键测试全部

依赖自动安装：首次运行自动检测缺失依赖，多镜像源（清华 / 阿里云 / PyPI）自动下载安装

多工作区管理：支持多个工作区文件夹切换，配置文件持久化

Windows 11 风格 UI：PySide6 构建的浅色主题图形界面

技术栈
Python 3.11+ — 编程语言

PySide6 — GUI 框架

requests — HTTP 请求库

loguru — 日志管理

py7zr — 7z 压缩文件处理

rarfile — RAR 压缩文件处理

psutil — 进程 / 系统信息

zipfile / tarfile — ZIP / TAR 压缩文件处理

hashlib — MD5 哈希计算

json — 配置持久化

pathlib — 路径管理

threading / QThread — 多线程并发

webbrowser — 外部链接打开

安装与运行
环境要求
Python 3.11+

仅支持 Windows（使用 ctypes.windll / os.startfile / CREATE_NEW_CONSOLE 等 Windows API）

运行步骤
下载项目文件 mikan_emu.py

在终端中运行：python mikan_emu.py

首次运行会自动安装所有依赖（PySide6、requests、loguru、py7zr、rarfile、certifi、psutil）

配置文件自动在脚本同级目录生成 mikan_emu/ 文件夹

目录结构
text
mikan_emu/
|-- config/
|   |-- folders.json          工作区配置
|   |-- settings.json         应用设置
|   |-- lang.json             当前语言
|   |-- mirrors.json          GitHub 镜像站
|   |-- save_paths.json       存档路径配置
|   |-- cheat_paths.json      金手指路径配置
|   |-- stats.json            游戏统计数据
|   |-- update_ignore.json    跳过更新版本
|   |-- resources.json        资源导航链接
|   |-- lang/                 语言包目录（zh / en / ru / ja / fr）
|-- engines/
|   |-- engines.json          平台/模拟器配置（含 24 平台 44 引擎）
|   |-- installed.json        已安装模拟器记录
|   |-- downloaded/           已安装引擎的存放目录
|-- bios/                     BIOS / 固件文件
|-- roms/
|   |-- roms.json             游戏库索引
|-- saves/                    存档文件
|-- saves_backup/             存档备份
|-- covers/                   游戏封面
|-- cheats/                   金手指文件
|-- backups/                  备份目录
|-- logs/                     日志文件
|-- temp/                     临时文件
|-- exports/                  导出文件
注意事项
首次运行需联网以自动安装依赖

本项目不提供 BIOS、ROM、模拟器二进制文件，请自行准备

部分模拟器（如 ePSXe、XEBRA、SSF 等）为闭源软件，需手动从官网下载

libretro 核心（px68k / NP2kai / Brimir）需要安装 RetroArch 并在设置页配置核心目录

游戏封面需手动设置（右键 → 设置封面），当前版本不自动抓取

杀毒软件可能误报，可将程序加入白名单

打包模式已验证 PyInstaller，打包后数据放在 exe 所在目录

游戏统计中的徽章系统需要一定游戏时长才能解锁

项目结构
mikan_emu.py 主程序（单文件，包含所有逻辑 + 内置 24 平台配置）

本项目采用单文件架构，所有逻辑、配置数据、UI 代码均包含在一个 Python 文件中。

支持的模拟器引擎
SFC / 超级任天堂：snes9x（自动下载）

PS1 / PlayStation：duckstation / ePSXe / XEBRA（自动下载 + 手动）

SS / 世嘉土星：mednafen / SSF / Ymir / Brimir / YabaSanshiro2（自动下载 + 手动）

DC / Dreamcast：flycast / redream / Deecy（自动下载 + 手动）

VMU / 记忆卡：DreamPotato（自动下载）

GBA：mGBA（自动下载）

PS2 / PlayStation 2：PCSX2（自动下载）

FC / NES：fceux / Mesen（自动下载）

N64：mupen64plus / gopher64 / ares / simple64 / RMG / Project64 / cen64（自动下载 + 手动）

NDS：DeSmuME / melonDS（自动下载）

MD / Genesis：blastem / Kega Fusion（自动下载 + 手动）

GB / GBC：SameBoy / gambatte（自动下载 + 手动）

PSP：PPSSPP（自动下载）

Switch：Ryujinx / yuzu（自动下载 + 手动）

PCE / TurboGrafx：mednafen（自动下载）

Neo Geo：MAME（自动下载）

Arcade：MAME（自动下载）

Sharp X68000：px68k (libretro)（自动下载）

NEC PC-98：NP2kai (libretro)（自动下载）

FM Towns：Tsugaru（自动下载）

PC-FX：PCFXemu（自动下载）

MSX：openMSX / blueMSX（自动下载）

万能 / 前端：RetroArch（自动下载）

未知渠道：Google Drive 手动链接（手动）

模块说明
EmulatorConfig：模拟器配置数据类，定义引擎版本、URL、匹配规则、启动模板等

GameEntry：游戏条目数据类，封装游戏名、平台、路径、封面、时长等属性

EngineImportWorker：模拟器导入工作线程，支持压缩包扫描、解压、匹配、复制

GameImportWorker：游戏导入工作线程，扫描 ROM 文件并添加到游戏库

DownloadWorker：模拟器下载工作线程，支持多线程下载、进度显示、镜像切换

MirrorTestWorker：GitHub 镜像站测试工作线程

UpdateCheckWorker：版本更新检查 worker，通过 GitHub API 对比版本号

BiosFile：BIOS 文件数据类，封装文件名、大小、MD5、识别状态

ProcessMonitorWorker：进程监控工作线程，跟踪模拟器进程生命周期

GameTableModel：游戏库表格模型（QAbstractTableModel），支持排序和筛选

GameFilterProxy：游戏筛选代理模型，支持平台/收藏/最近/搜索等多条件筛选

EngineTableModel：模拟器列表表格模型

BiosTableModel：BIOS 文件列表表格模型

LaunchConfigDialog：启动方式配置对话框，支持自动/手动选择模拟器、覆盖平台、附加参数

BiosSelectDialog：BIOS 选择对话框

ControlsDialog：操作说明对话框，展示模拟器默认键位表

CreditsDialog：鸣谢对话框，列出依赖和开源项目

ManualEngineDialog：手动指定模拟器对话框（自动识别失败时使用）

ExportDialog：导出对话框，支持 MD/HTML/CSV 格式选择

PlatformConfirmDialog：平台确认对话框（导入未知平台游戏时使用）

LibraryPage：游戏库页面，网格/列表视图切换、搜索、右键菜单

EnginePage：模拟器管理页面，列表展示、导入、下载、更新

BiosPage：BIOS 管理页面，扫描、识别、文件详情

ChartWidget：统计图表组件

StatsPage：游戏统计页面，含徽章系统和时间统计

ResourcesPage：资源导航页面，外部网站跳转链接

SettingsPage：设置页面，含语言、工作区、镜像、存档、金手指、RetroArch、平台管理等子页

ImportDialog：导入对话框（模拟器/游戏通用）

DownloadDialog：下载模拟器对话框，分"可自动下载"和"需手动下载"两个标签页

MainWindow：主窗口 UI，侧边栏导航 + 堆叠页面 + 工具栏 + 状态栏

开发指南
代码风格
遵循 PEP 8 规范

使用中文注释

单文件架构，按功能区块用注释分隔

添加新平台支持
在 DEFAULT_ENGINES_JSON_STR 的 JSON 数据中添加新的平台对象，包含 platform_name、rom_extensions 和 engines 配置即可。

添加新模拟器引擎
在对应平台的 engines 对象中添加新的引擎配置，定义版本、下载 URL、匹配规则（exe/folder/keywords）、启动模板等。

扩展多语言支持
在 DEFAULT_LANG_PACKS 字典中添加新的语言代码（如 "de"），提供完整的翻译键值对。或直接在 config/lang/ 目录下新增 JSON 文件，程序会自动加载。

扩展资源导航
编辑 config/resources.json 中的 groups 数组，或修改内置的 DEFAULT_RESOURCES_JSON 添加新的网站跳转链接。

添加操作说明键位
在 CONTROLS_DB 字典中添加新的引擎条目，包含 source（官方文档链接）和 keys（键位表）即可。

许可证
本项目采用 GPL-3.0 许可证开源。

致谢
本项目由 DeepSeek AI 辅助开发完成。

支持的开源模拟器项目包括但不限于：snes9x、duckstation、PCSX2、PPSSPP、Ryujinx、mGBA、DeSmuME、melonDS、flycast、Mednafen、MAME、RetroArch、fceux、Mesen、mupen64plus、ares、simple64、RMG、blastem、SameBoy、gambatte、Ymir、Brimir、DreamPotato、Deecy、redream、YabaSanshiro2、XEBRA、ePSXe、SSF、px68k、NP2kai、Tsugaru、PCFXemu、openMSX、blueMSX 等。