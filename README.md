# MikanEmu v1.2.0

## 模拟器前端一体化管家

<p>
  <img alt="license GPL-3.0" src="https://img.shields.io/badge/license-GPL--3.0-green">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11+-blue">
  <img alt="PySide6" src="https://img.shields.io/badge/PySide6-6.x-brightgreen">
</p>

> **版本 v1.2.0** ｜ 模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言 + 平台编辑器 + 性能监控 + 局域网聊天 / 文件 / 共享（内嵌 LocalSend Web）+ ROM 补丁 + 配置包迁移 + 深色模式

---

## 项目介绍

**MikanEmu** 是一款基于 PySide6 的桌面级模拟器综合管理前端，把「游戏库管理、模拟器引擎配置、BIOS 管理、存档备份、金手指管理、版本识别与更新检查、性能监控、多语言、平台编辑器」整合到一个统一界面中，并在 v1.1.0 起将局域网协作能力（聊天 / 文件传输 / 文件夹共享 / 内嵌 LocalSend Web）完整内置。v1.2.0 进一步新增深色模式、ROM 补丁工具、配置包导出/导入、统一配置中心等核心功能。

- **36 个游戏 / 计算平台**，覆盖 SFC、PS1/2/3/4/5、N64、Switch、GBA、MD、DC、街机、X68000、PC-98、FM Towns、Wii/Wii U、Xbox/Xbox 360、PS Vita、86Box/PCem 等主机与复古 PC 平台。
- **57 个内置引擎配置**，内置官方直链、GitHub Release、libretro 核心与手动下载指引，自动识别已安装的引擎目录与可执行文件。
- **局域网一体化**：v1.1.0 将独立版 `mikan_lan v1.2.x` 全功能整合，聊天、共享、拖拽、表情、右键发送一应俱全，并内嵌 LocalSend Web 传输页。
- **深色模式**：支持跟随系统 / 亮色 / 深色 + 自定义主题色。
- **ROM 补丁工具**：支持 IPS / UPS 补丁，独立工具 + 游戏右键应用。
- **配置包迁移**：.mikanpack 导出/导入，跨机器迁移配置。
- **统一配置中心**：右键"更多配置"整合启动/补丁/封面/BIOS/金手指/存档/信息。

### v1.2.0 变更亮点

- **深色模式**：跟随系统 / 亮色 / 深色 + 自定义主题色
- **ROM 补丁工具**：支持 IPS / UPS 补丁，独立工具 + 游戏右键应用
- **配置包导出/导入**：.mikanpack 格式，跨机器迁移配置
- **新增平台**：Wii / GameCube（合并）、Wii U、PS3、PS Vita
- **统一配置中心**：右键"更多配置"整合 启动/补丁/封面/BIOS/金手指/存档/信息
- **load_engines_json 全量补齐缺失平台**
- **保留 v1.1.0 全部功能**（含 LocalSend Web 内嵌页）

### v1.1.0 变更亮点

- **重写「局域网」页**：完整整合独立版 `mikan_lan v1.2.x`
  - 聊天 Tab + 共享文件夹 Tab
  - 右键「发送文件给 TA」/「发文件给所有人」
  - 拖拽文件直接发送 / 广播
  - 表情面板
  - 共享文件夹（上传 + 浏览 + 下载）
  - 消息 `broadcast` 标记，私聊 / 全体分离
  - 接收方弹窗提示
- **协议统一** 为 `mikan_lan v1.2.x`（magic = `mikan_lan`）。
- **不互通提示**：旧版 `mikan_emu v1.0.0` 及独立版 `mikan_lan` 与本版**不互通**。
- **保留 v1.0.0 全部功能**（含 LocalSend Web 内嵌页）。

---

## 功能特性

### 游戏库管理
- 多文件夹游戏库管理，支持扫描导入 ROM / 压缩包
- 游戏表格视图（`GameTableModel` + `GameFilterProxy`），列排序与关键词筛选
- 封面（`covers/`）展示、平台编辑器自定义平台与 ROM 扩展名
- 游戏统计与图表（`StatsPage` + `ChartWidget`），导出游戏库（`ExportDialog`）
- 重复游戏检测与处理（`DupResolveDialog`）

### 模拟器引擎管理
- 36 平台 / 57 引擎的内置配置库，支持官方直链、GitHub Release、libretro 核心、手动下载四类来源
- 引擎目录自动匹配（按 exe / folder / keywords 识别已安装引擎）
- 引擎下载（`DownloadWorker`）与镜像测速（`MirrorTestWorker`）
- 版本识别（`version`）与更新检查（`UpdateCheckWorker`），可忽略指定版本
- 启动模板引擎（`launch_template`），支持 `{exe} {rom} {retroarch} {core}` 变量
- 手动引擎登记（`ManualEngineDialog`）
- 批量更新（`BatchUpdateDialog`）

### BIOS 管理
- BIOS 需求标记（`bios_required` / `bios_files` / `bios_dir`）
- BIOS 文件列表（`BiosTableModel`）与选择对话框（`BiosSelectDialog`）
- 按引擎约定目录放置 BIOS 的提示指引
- PCem/86Box ROM 批量导入

### 存档 / 金手指
- 存档目录与备份（`saves/` / `saves_backup/`），存档路径映射（`save_paths.json`）
- 金手指管理与路径映射（`cheats/` / `cheat_paths.json`）

### ROM 补丁工具（v1.2.0 新增）
- 支持 IPS / UPS 补丁格式
- 自动扫描 ROM 目录查找补丁文件
- 应用补丁后生成新文件，原 ROM 自动备份为 .bak
- 补丁历史追踪，标记已打补丁的游戏
- 独立工具对话框（`PatchToolDialog`）+ 游戏右键菜单集成

### 配置包管理（v1.2.0 新增）
- 导出完整配置包（`.mikanpack`，ZIP 格式），包含所有配置、平台定义、引擎清单、游戏库
- 可选包含封面图片、存档备份、统计数据
- 导入配置包，合并模式不删除现有条目
- 导入前自动备份当前配置

### 统一配置中心（v1.2.0 新增）
- 右键游戏"更多配置"整合以下子页：
  - 启动配置（选择模拟器、覆盖平台、附加参数、启动模板）
  - 补丁配置（IPS/UPS 补丁应用）
  - 封面设置
  - BIOS 选择
  - 金手指管理
  - 存档管理
  - 游戏信息

### 深色模式（v1.2.0 新增）
- 跟随系统 / 亮色 / 深色 三种外观模式
- 自定义主题色（强调色）配置

### 启动与运行
- 进程启动与进程监控（`ProcessMonitorWorker`）
- 性能监控窗口（`PerfMonitorWindow`，基于 psutil，可选依赖缺失时降级）
- 键位说明（`ControlsDialog`）
- 启动失败诊断（`LaunchError` 详细错误信息）

### 局域网协作（v1.1.0 核心）
- **聊天 Tab + 共享文件夹 Tab**：UDP 发现（`LanDiscoveryWorker`）+ TCP 聊天服务 / 客户端（`LanChatServer` / `LanChatClient`）
- **文件传输**：右键「发送文件给 TA」/「发文件给所有人」、拖拽文件直接发送 / 广播
- **文件夹共享**：上传 + 浏览 + 下载（`lan/shared/` 等目录）
- **表情面板**（`EmojiPanel`），消息 `broadcast` 标记，私聊 / 全体分离
- **接收方弹窗提示**，消息历史落盘（`lan/history/`）
- **内嵌 LocalSend Web 传输页**（`WebTransferPage`，基于 QtWebEngine；不可用时降级为外部浏览器）
- **协议统一** `mikan_lan v1.2.x`（magic = `mikan_lan`）

### 通用
- 多语言支持（简体中文 / English / Русский / 日本語 / Français，外置 JSON 语言包）
- 资源导航页（`ResourcesPage`，`resources.json`）、操作说明 / 鸣谢页（`CreditsDialog`）
- GitHub / pip 镜像加速、依赖自动安装、可选依赖一键安装
- 系统托盘、配置 / 统计 / 设置持久化（`config/`）
- 管理员权限支持、以管理员身份重启

---

## 技术栈

| 技术 | 用途 | 说明 |
| --- | --- | --- |
| Python 3.11+ | 运行环境 | 主语言 |
| PySide6 | GUI 框架 | Qt6 Python 绑定，表格 / 模型视图 / 多线程 |
| PySide6-WebEngine | 内嵌浏览器 | **可选**，用于 LocalSend Web 传输页，缺失时降级外部浏览器 |
| requests | 网络请求 | 引擎下载、更新检查、镜像测速 |
| urllib3 | 连接 / 证书 | 关闭不安全请求告警 |
| loguru | 日志 | 按天 + 10MB 轮转，保留 14 天 |
| py7zr / rarfile | 解压 | 7z / RAR 引擎包解压（zip / tar 用标准库） |
| psutil | 性能监控 | 进程 / CPU / 内存监控，缺失时降级 |
| certifi | 证书 | HTTPS 根证书 |
| socket / threading | 局域网 | UDP 发现 + TCP 聊天 / 文件传输 |
| hashlib / hmac | 安全 | 文件 SHA-256 校验、局域网口令哈希 |

---

## 安装与运行

### 环境要求
- Windows（引擎配置以 Windows x64 为主），Python 3.11 及以上。
- 首次运行会自动检测并安装缺失的必需依赖（PySide6 / requests / loguru / py7zr / rarfile / certifi / psutil），优先使用清华 / 阿里镜像，失败回退官方 PyPI。

### 运行
```bash
python mikan_emu_3.py
```
- 可选内嵌浏览器（LocalSend Web 页）：`pip install PySide6-WebEngine`，未安装时「局域网传输」页自动降级为外部浏览器模式。
- 打包分发可使用 PyInstaller，程序会自动识别 `sys.frozen` 并以可执行文件所在目录为根目录。

---

## 项目结构

```
mikan_emu_3.py                 # 单文件主程序（约 12809 行）
mikan_emu/                    # 运行时自动创建的数据根目录
├── config/                  # 配置：folders / settings / lang / save_paths /
│   │                       #   mirrors / cheat_paths / stats / update_ignore / resources
│   └── lang/                # 多语言资源（zh.json / en.json / ru.json / ja.json / fr.json）
├── engines/                 # 引擎配置 engines.json + installed.json
│   └── downloaded/          # 引擎下载缓存
├── bios/                    # BIOS 文件
├── roms/                    # 游戏 ROM + roms.json 索引
├── saves/ saves_backup/     # 存档与存档备份
├── covers/                  # 游戏封面
├── cheats/                  # 金手指
├── backups/                 # 通用备份
├── logs/                    # loguru 日志（按天轮转）
├── temp/ exports/           # 临时文件 / 导出产物
├── lan/                     # 局域网数据
│   ├── identity.json        # 本机身份
│   ├── history/             # 聊天消息历史
│   ├── received/            # 接收文件
│   ├── shared/              # 共享文件夹（上传源）
│   └── shared_download/     # 共享下载
└── webengine/               # QtWebEngine 缓存（LocalSend Web）
```

---

## 支持的平台与引擎（内置 36 平台 / 57 引擎）

| 平台键 | 平台名称 | 引擎 |
| --- | --- | --- |
| sfc | SFC / 超级任天堂 | snes9x |
| ps1 | PS1 / PlayStation | duckstation, epsxe, xebra |
| ss | SS / 世嘉土星 | mednafen, ssf, ymir, brimir, yaba_sanshiro_2 |
| dc | DC / Dreamcast | flycast, redream, deecy |
| vmu | VMU / 记忆卡 | dreampotato |
| gba | GBA | mgba |
| ps2 | PS2 / PlayStation 2 | pcsx2 |
| fc | FC / NES | fceux, mesence |
| n64 | N64 | mupen64plus, gopher64, ares, simple64, rmg, project64, cen64 |
| nds | NDS | desmume, melonds |
| md | MD / Genesis | blastem, kega-fusion |
| gb | GB / GBC | sameboy, gambatte |
| psp | PSP | ppsspp |
| switch | Switch | ryujinx, yuzu |
| pce | PCE / TurboGrafx | mednafen |
| neogeo | Neo Geo | mame |
| arcade | Arcade | mame |
| x68000 | Sharp X68000 | px68k（libretro） |
| pc98 | NEC PC-98 | np2kai（libretro） |
| fmtowns | FM Towns | tsugaru |
| pcfx | PC-FX | pcfxemu |
| msx | MSX | openmsx, bluemsx |
| x86box | 86Box / PC 模拟 | 86box |
| pcem | PCem / PC 模拟 | pcem |
| ps4 | PS4 / PlayStation 4 | shadps4 |
| ps5 | PS5 / PlayStation 5 | kytyps5 |
| xbox | 初代 Xbox | xemu |
| xbox360 | Xbox 360 | xenia_canary, xenia_edge |
| switch_alt | Switch（备用引擎） | suyu |
| 3ds | 3DS | zakuro |
| multi | 万能 / 前端 | retroarch |
| wii | Wii / GameCube | dolphin |
| wiiu | Wii U | cemu |
| ps3 | PS3 / PlayStation 3 | rpcs3 |
| psvita | PS Vita | vita3k |
| unknown | 未知渠道 | google_drive_unknown |

> 引擎来源分为 `direct`（官方直链）、`github_release`、`libretro`（需 RetroArch）与 `manual`（闭源 / 需手动下载，附官网指引）四类。BIOS 由各引擎 `bios_required` / `bios_files` / `bios_dir` 声明，本工具**不提供 BIOS、不提供 ROM、不二次分发模拟器**。

---

## 模块说明

| 类 / 模块 | 功能 |
| --- | --- |
| `EmulatorConfig` | 全局配置单例，加载 / 保存 folders / settings / mirrors 等 |
| `GameEntry` | 单条游戏记录（路径 / 平台 / 封面 / 元数据） |
| `PatchError` | ROM 补丁工具异常类 |
| `EngineImportWorker` | 引擎目录导入与自动匹配线程 |
| `GameImportWorker` | 游戏库扫描导入线程 |
| `DownloadWorker` | 引擎下载线程 |
| `MirrorTestWorker` | 下载镜像测速线程 |
| `UpdateCheckWorker` | 引擎版本更新检查线程 |
| `BiosFile` | BIOS 文件记录 |
| `ProcessMonitorWorker` | 模拟器进程运行状态监控线程 |
| `PerfMonitorWindow` | 性能监控窗口（psutil：CPU / 内存等） |
| `LanIdentity` / `LanPeer` | 本机身份 / 局域网对等节点模型 |
| `LanDiscoveryWorker` | 局域网设备发现线程（UDP） |
| `LanChatServer` / `LanChatClient` | 聊天 / 文件传输的服务端与客户端（TCP，协议 magic = mikan_lan） |
| `GameTableModel` / `GameFilterProxy` | 游戏库表格模型与筛选代理 |
| `EngineTableModel` / `BiosTableModel` | 引擎 / BIOS 表格模型 |
| `LaunchConfigDialog` | 引擎启动配置对话框 |
| `BiosSelectDialog` | BIOS 选择对话框 |
| `ControlsDialog` | 键位说明对话框 |
| `CreditsDialog` | 鸣谢页对话框 |
| `ManualEngineDialog` | 手动引擎登记对话框 |
| `ExportDialog` | 游戏库导出对话框 |
| `PlatformConfirmDialog` | 平台确认 / 平台编辑器对话框 |
| `DupResolveDialog` | 重复游戏检测与处理对话框 |
| `PatchToolDialog` | ROM 补丁工具对话框（IPS / UPS） |
| `ConfigPackDialog` | 配置包导出/导入对话框（.mikanpack） |
| `LibraryPage` | 游戏库主页（表格 / 筛选 / 封面 / 右键发送文件） |
| `GameConfigCenterDialog` | 统一配置中心（启动/补丁/封面/BIOS/金手指/存档/信息） |
| `EnginePage` | 引擎管理页（下载 / 导入 / 更新检查 / 镜像测速） |
| `BiosPage` | BIOS 管理页 |
| `ChartWidget` | 统计图表绘制控件 |
| `StatsPage` | 游戏统计页 |
| `ResourcesPage` | 资源导航页 |
| `EmojiPanel` | 表情面板控件 |
| `LanPage` | 局域网页（聊天 + 共享，整合独立版 mikan_lan v1.2.x） |
| `WebTransferPage` | 内嵌 LocalSend Web 传输页（QtWebEngine 不可用时降级外部浏览器） |
| `SettingsPage` | 设置页（语言 / 主题 / 路径 / 镜像 / 托盘 / 局域网等） |
| `ImportDialog` / `DownloadDialog` | 游戏导入 / 引擎下载对话框 |
| `BatchUpdateDialog` | 批量更新对话框 |
| `MainWindow` | 主窗口（左侧导航 + 多页堆叠 + 状态栏 + 系统托盘） |

---

## 注意事项

- **管理员权限**：注册文件关联、写入系统目录或某些存档路径时可能需要以管理员身份运行。
- **杀毒软件**：单文件脚本自动 pip 安装依赖、调用子进程启动模拟器，可能被杀毒软件 / Windows Defender 拦截，请添加信任。
- **依赖安装**：首次启动自动联网安装依赖，需可访问清华 / 阿里 / 官方 PyPI 镜像；离线环境需预先 `pip install`。
- **QtWebEngine**：可选依赖，未安装时「局域网传输」页降级为外部浏览器模式（启动时 `QTWEBENGINE_CHROMIUM_FLAGS` 已带 `--disable-gpu --disable-software-rasterizer` 以提升兼容性）。
- **psutil**：可选，缺失时性能监控功能降级，不影响主流程。
- **局域网协议**：本版使用 `mikan_lan v1.2.x`（magic = `mikan_lan`），与旧版 `mikan_emu v1.0.0` 及独立版 `mikan_lan` **不互通**，需统一版本。
- **法律合规**：本工具**不提供 BIOS、不提供 ROM、不二次分发模拟器**，仅管理用户自行获取的引擎与镜像；请遵守各模拟器与主机的版权 / 许可条款。
- **网络与镜像**：部分引擎为 `manual` 闭源（如 ePSXe、SSF、Kega Fusion、Redream、Project64），需用户前往官网手动下载，工具仅提供官网指引与目录匹配。
- **MEDNAFEN**：内置 `MEDNAFEN_ALLOWMULTI=1`，支持 Mednafen 多实例并行运行。

---

## 开发指南

- **代码风格**：单文件结构，按编号注释分节（0 代理 / 1 依赖自检 / 2 导入 / 3 路径常量 / 3.5 内置 JSON / ... / 18 管理员 / 主程序）；类按「数据模型 → Worker 线程 → 表格模型 → 对话框 → 页面 → 主窗口」分层。
- **扩展新平台**：在 `DEFAULT_ENGINES_JSON_STR` 中按 `{platform_id: {platform_name, rom_extensions, engines:{...}}}` 结构追加，声明 `match`（exe / folder / keywords）与 `launch_template`。
- **扩展新引擎**：在对应平台 `engines` 下新增条目，区分 `url_type`（`direct` / `github_release` / `libretro` / `manual`），libretro 核心需同时声明 `libretro_core` 并使用 `{retroarch} -L "{core}" "{rom}"` 模板。
- **扩展 BIOS 约定**：通过 `bios_required` / `bios_files` / `bios_dir` 声明，前端在 BIOS 页据此提示放置路径。
- **扩展局域网功能**：聊天 / 文件收发逻辑在 `LanChatServer` / `LanChatClient`，发现逻辑在 `LanDiscoveryWorker`，消息 `broadcast` 标记区分私聊与全体；修改需保持 magic = `mikan_lan` 协议兼容。
- **扩展多语言**：在 `DEFAULT_LANG_PACKS` 中追加语言包（zh / en 为完整翻译，ru / ja / fr 为机器翻译），运行时自动写入 `config/lang/` 目录，用户也可自行编辑 JSON 语言包。

---

## 许可证

本项目基于 **GNU General Public License v3.0（GPL-3.0）** 开源发布。完整条款见项目 `LICENSE` 文件。

> 本软件以自由软件协议发布，但**不提供 BIOS、不提供 ROM、不二次分发任何模拟器**。使用者需自行遵守各主机与模拟器的版权与许可条款。

---

## 致谢

- **DeepSeek** —— 本项目在开发过程中由 DeepSeek 提供 AI 辅助编码支持。
- 内置引擎所依赖的开源模拟器项目：snes9x、duckstation、ePSXe、XEBRA、Mednafen、SSF、Ymir、Brimir、Yaba Sanshiro、Flycast、Redream、Deecy、DreamPotato、mGBA、PCSX2、RetroArch、Mesen、MAME、openMSX、blueMSX、86Box、PCem、PPSSPP、Ryujinx、Yuzu、suyu、desmume、melonDS、blastem、Kega Fusion、SameBoy、Gambatte、px68k、NP2kai、Tsugaru、PCFXemu、ares、simple64、RMG、cen64、Project64、gopher64、mupen64plus、shadPS4、KytyPS5、xemu、Xenia Canary、Xenia Edge、zakuro、Vita3K、Cemu、Dolphin、RPCS3 等。
- 框架与库：PySide6、PySide6-WebEngine、requests、urllib3、loguru、py7zr、rarfile、psutil、certifi。

---

*Built with PySide6 ｜ AI-assisted by DeepSeek ｜ GPL-3.0*
