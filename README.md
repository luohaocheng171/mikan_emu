# MikanEmu v1.7.0 官方文档

## 项目概述

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/Qt-PySide6%2FPyQt5-orange)](https://www.qt.io/qt-for-python)

MikanEmu 是一款集模拟器前端、配置管家、版本识别器与更新检查于一体的综合性工具。它不仅提供游戏库管理、引擎下载、局域网协作和插件扩展等核心功能，还针对不同操作系统进行了深度优化。

本项目提供两个独立版本，均已使用 PyInstaller 打包为独立可执行文件（exe）：

1. **最新版 (PySide6)**: 基于 PySide6 (Qt6) 框架，要求 Python 3.11+，功能最全，支持最新特性。
2. **Win7兼容版 (PyQt5)**: 基于 PyQt5 5.15.4 框架，要求 Python 3.8，专为 Windows 7 环境设计。

## 版本对比

| 对比项 | 最新版 (PySide6) | Win7兼容版 (PyQt5) |
| :--- | :--- | :--- |
| **GUI 框架** | PySide6 (Qt6) | PyQt5 5.15.4 |
| **Python 版本** | 3.11+ | 3.8 |
| **WebEngine 导入** | PySide6.QtWebEngineCore | PyQt5.QtWebEngineWidgets |
| **Signal 语法** | Signal | pyqtSignal |
| **依赖版本策略** | 不锁定 (使用最新版) | 全部锁定 (Win7可用版) |
| **PyInstaller 版本** | 最新版 | 4.10 (5.x 不支持 Win7) |
| **额外依赖** | 无 | pywin32==228 |
| **DPI 缩放** | 自动 (Chromium flags 按需设置) | 强制关闭 (QT_AUTO_SCREEN_SCALE_FACTOR=0) |
| **Chromium Flags** | _setup_webengine_flags() 根据 Win 版本动态设置 | _setup_qt_flags() 为空函数 |
| **日志路径处理** | Path 对象 | str() 转换 |
| **random 模块导入** | 模块内按需使用 | 顶部 import random as _random |

## 核心功能特性

MikanEmu v1.7.0 提供了极其丰富的功能矩阵，涵盖从基础模拟到高级系统管理的各个方面：

- **综合管理**：模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言支持 + 平台编辑器
- **性能与网络**：性能监控 + 局域网聊天/文件/共享 + 内嵌 LocalSend Web 局域网传输
- **资源管理**：封面刮削（支持 Libretro / SteamGridDB）+ BIOS 自动归类 + 多文件夹/工作区管理
- **性能调优**：支持性能档位切换（省电/平衡/高性能/画质优先）+ 系统优先级调整
- **高级配置**：版本适配 (version_overrides) + 打开模拟器设置 + 引擎共享定义 (_shared) + 统一代理
- **扩展与诊断**：插件系统 + 日志环形缓冲 (deque maxlen=2000) + 崩溃诊断包生成
- **系统兼容**：Windows 版本检测 + 硬件探测 + 资源策略 + 全局背景自定义
- **交互体验**：老游戏资料站侧边栏 + 拖拽自动识别 + 补丁工具（支持 IPS/UPS 格式）
- **统一接口**：MikanAPI 统一接口（包含 10 个子 API）+ Job 统一长任务句柄 + MirrorRouter 镜像自动选路

## v1.7.0 关键修复与技术革新

本次更新在底层架构和稳定性上进行了重大技术革新，修复了多个严重问题：

### P0 级修复（严重问题）

- **P0-1**: patch_ips 增加 EEOF 支持及越界扩容机制，彻底解决静默损坏 ROM 的问题。当 IPS 补丁的修改范围超出 ROM 文件大小时，不再静默丢弃多余数据，而是自动扩容 ROM 文件以容纳完整补丁。
- **P0-2**: patch_ups 增加 varint 截断检测，防止产生半成品补丁文件。UPS 格式使用 varint 编码长度信息，旧版在遇到截断的 varint 时会继续处理导致产生损坏文件，新版在检测到截断时立即中止并报错。
- **P0-3**: 将 os.chdir 替换为 Popen(cwd=...)，修复多线程环境下的竞态条件。旧版在子线程中调用 os.chdir 切换工作目录会影响其他并发线程的文件操作路径，导致文件读写错误和引擎启动失败。修复后通过 Popen 的 cwd 参数为每个子进程独立指定工作目录，彻底消除全局状态竞争。
- **P0-4**: _settle_stale_launches 逻辑调整为只归零不结算，修复游戏运行时长统计失真问题。旧版在检测到停滞的启动进程时会将其运行时长累加到统计中，但这些进程实际上并未成功启动游戏，导致时长虚增。修复后仅将计时器归零而不进行结算。

### P1 级修复（重要问题）

- **P1-5**: .cue 文件生成改用 .mikan_auto.cue 后缀，避免覆盖用户自定义文件。旧版在生成 CUE 文件时直接使用目标文件名，如果用户已有同名文件会被静默覆盖。新版使用 .mikan_auto.cue 后缀确保不会覆盖用户文件。
- **P1-6**: HttpSession 增加读写锁及 hostname 匹配 bypass 机制，提升线程安全性。旧版 HTTP 会话对象在多线程并发访问时缺乏同步保护，可能导致请求头损坏或响应解析错误。修复后引入 threading.RLock 读写锁，并对同一 hostname 的请求进行串行化处理。
- **P1-7**: detect_engine_version 正则优先匹配 version/v 前缀，并过滤日期格式。旧版版本检测正则表达式无法正确处理包含日期信息的版本号字符串（如 "2024.12.1-beta"），导致版本识别错误。修复后优先匹配 version/v 前缀后的数字序列，并过滤纯日期格式。
- **P1-8**: check_bios_ready 增加 5 分钟缓存，减少重复扫描开销。旧版每次启动或切换平台时都会重新扫描 BIOS 目录检查文件完整性，在 BIOS 目录包含大量文件时导致启动缓慢。修复后缓存检查结果 5 分钟，期间直接返回缓存结果。
- **P1-9**: _split_cmd 改用 shlex 模块，安全处理含空格路径的命令。旧版使用简单的 str.split() 分割命令字符串，无法正确处理带引号的路径（如 "C:\\Program Files\\game.exe"），导致含空格路径的命令执行失败。修复后使用 shlex.split() 进行符合 Shell 语法的分割。
- **P1-10**: 所有硬编码中文字符串统一走 tr() 国际化流程。旧版部分界面文本直接硬编码中文字符串，未通过 tr() 函数包装，导致多语言切换时这些文本不会翻译。修复后所有硬编码中文均通过 tr() 包装，支持完整的多语言切换。
- **P1-11**: 拖拽导入功能移至 QThread 异步处理，杜绝 UI 卡死。旧版拖拽文件导入时在主线程中执行文件扫描和类型识别，当拖入大量文件或大型 ROM 文件时 UI 完全卡死。修复后将所有耗时操作移至 QThread 后台线程执行，通过信号槽机制更新 UI。
- **P1-13**: QWebEngineProfile 采用命名 profile，隔离多实例配置。旧版使用 QtWebEngine 默认 profile，当同时运行多个 MikanEmu 实例时配置会互相覆盖（如代理设置、缓存路径）。修复后为每个实例创建命名 profile（如 "mikan_emu_instance_X"），实现配置完全隔离。
- **P1-14**: --no-sandbox 参数仅在 Windows 7 环境下开启，提升高版本系统安全性。旧版对所有 Windows 版本都启用 Chromium 的 --no-sandbox 启动参数，降低了非 Win7 系统的安全性。修复后通过读取 Windows 版本信息（CurrentBuild 注册表值），仅在 build number < 7601（即 Windows 7）时启用该参数。

### P2 级优化与新增

- **P2-16**: random 模块移至顶部导入。旧版 random 模块在模块内部某处导入，导致部分代码在模块加载阶段调用 random 函数时出现 NameError。修复后将 import random 移至文件顶部统一导入。
- **P2-18**: 局域网口令哈希计算不再截断，修复认证碰撞隐患。旧版在计算局域网连接口令的哈希值时截断了部分字节，导致不同口令可能产生相同哈希（碰撞），存在安全风险。修复后使用完整的 SHA-256 哈希输出，不再截断。
- **新增 - MikanAPI 统一接口（10个子API）**: 全新的统一 API 层，将 ROM 管理、引擎管理、配置管理、游戏库、存档管理、金手指、封面刮削、局域网、插件、系统等功能抽象为标准化接口，方便插件和外部工具调用。
- **新增 - Job 统一长任务句柄**: 标准化的后台任务管理框架，支持进度回调、取消、超时和错误处理，统一接管所有耗时操作。
- **新增 - MirrorRouter 镜像自动选路（可开关）**: 自动探测并选择最快的 PyPI/资源镜像服务器，支持手动配置和开关控制，主镜像失败时自动切换备用。

## API 参考手册

### 1. ROM 管理 API

用于管理游戏 ROM 文件的添加、移除、查询和元数据更新。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| add_rom | add_rom(path: Path, metadata: dict) -> RomInfo | 添加 ROM 文件到游戏库，自动识别平台类型并提取元数据 |
| remove_rom | remove_rom(rom_id: str) -> bool | 从游戏库中移除指定 ROM 的记录（不删除文件） |
| get_rom | get_rom(rom_id: str) -> Optional[RomInfo] | 获取单个 ROM 的完整信息，包括平台、引擎、封面路径等 |
| list_roms | list_roms(platform: Optional[str] = None) -> List[RomInfo] | 列出游戏库中所有 ROM，支持按平台名称过滤 |
| update_rom | update_rom(rom_id: str, metadata: dict) -> bool | 更新 ROM 的元数据（名称、封面、自定义标签等） |

### 2. 引擎管理 API

用于管理模拟器引擎的下载、安装、卸载和版本查询。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| get_engine | get_engine(engine_id: str) -> Optional[EngineInfo] | 获取指定引擎的详细信息（版本、URL、匹配规则等） |
| list_engines | list_engines() -> List[EngineInfo] | 列出所有已配置引擎（含已安装和未安装状态） |
| install_engine | install_engine(engine_id: str, progress_callback: Callable) -> bool | 从配置 URL 下载并安装引擎，支持进度回调 |
| uninstall_engine | uninstall_engine(engine_id: str) -> bool | 卸载指定引擎并清理相关文件 |

### 3. 配置管理 API

用于读写应用配置项和文件夹路径。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| get_setting | get_setting(key: str) -> Any | 获取指定配置项的值，不存在时返回 None |
| set_setting | set_setting(key: str, value: Any) -> bool | 设置配置项值并自动保存到 settings.json |
| get_folder | get_folder(folder_type: str) -> Path | 获取指定类型文件夹的当前路径（如 roms、bios、saves） |
| set_folder | set_folder(folder_type: str, path: Path) -> bool | 设置指定类型文件夹路径并持久化 |

### 4. 游戏库 API

用于游戏库的整体管理操作（扫描、导出、导入）。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| get_library | get_library() -> List[GameEntry] | 获取完整游戏库列表（含所有 ROM 元数据） |
| scan_library | scan_library(paths: List[Path]) -> int | 扫描指定路径下的游戏文件，返回新增 ROM 数量 |
| export_library | export_library(path: Path) -> bool | 将游戏库导出为 JSON 文件，支持备份和迁移 |
| import_library | import_library(path: Path) -> int | 从 JSON 文件导入游戏库，返回导入的 ROM 数量 |

### 5. 存档管理 API

用于模拟器即时存档的保存、加载和管理。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| save_state | save_state(rom_id: str, slot: int, data: bytes) -> bool | 保存即时存档数据到指定槽位 |
| load_state | load_state(rom_id: str, slot: int) -> Optional[bytes] | 从指定槽位加载存档数据 |
| list_saves | list_saves(rom_id: str) -> List[SaveInfo] | 列出指定 ROM 的所有存档槽位及元信息 |
| delete_save | delete_save(rom_id: str, slot: int) -> bool | 删除指定槽位的存档文件 |

### 6. 金手指 API

用于管理 ROM 的金手指（作弊码）代码。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| add_cheat | add_cheat(rom_id: str, code: str, name: str) -> bool | 为指定 ROM 添加金手指代码 |
| remove_cheat | remove_cheat(rom_id: str, cheat_id: str) -> bool | 移除指定金手指 |
| list_cheats | list_cheats(rom_id: str) -> List[CheatInfo] | 列出指定 ROM 的所有金手指代码 |
| toggle_cheat | toggle_cheat(rom_id: str, cheat_id: str) -> bool | 切换金手指的启用/禁用状态 |

### 7. 封面刮削 API

用于从网络自动获取游戏封面图片。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| scrape_cover | scrape_cover(rom_id: str) -> Optional[Path] | 从 Libretro/SteamGridDB 刮削封面并保存到本地 |
| get_cover | get_cover(rom_id: str) -> Optional[Path] | 获取指定 ROM 的本地封面文件路径 |
| clear_cover_cache | clear_cover_cache(rom_id: Optional[str] = None) -> int | 清除封面缓存，指定 rom_id 则只清该游戏，否则清空全部 |

### 8. 局域网 API

用于局域网聊天和文件传输。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| lan_chat_send | lan_chat_send(peer_id: str, message: str) -> bool | 向指定局域网节点发送聊天消息 |
| lan_chat_recv | lan_chat_recv() -> List[ChatMessage] | 获取未读的局域网聊天消息列表 |
| lan_file_send | lan_file_send(peer_id: str, file_path: Path) -> bool | 向指定节点发送文件 |
| lan_file_recv | lan_file_recv(file_id: str) -> Path | 接收并保存文件，返回本地存储路径 |

### 9. 插件 API

用于插件的生命周期管理和方法调用。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| load_plugin | load_plugin(plugin_path: Path) -> PluginHandle | 从指定路径加载插件，执行 plugin.json 和 main.py |
| unload_plugin | unload_plugin(plugin_id: str) -> bool | 卸载指定插件并清理资源 |
| list_plugins | list_plugins() -> List[PluginInfo] | 列出所有已加载插件及其状态 |
| call_plugin | call_plugin(plugin_id: str, method: str, **kwargs) -> Any | 动态调用插件注册的任意方法 |

### 10. 系统 API

用于获取系统信息和应用状态。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| get_system_info | get_system_info() -> SystemInfo | 获取操作系统、CPU、GPU、内存等硬件信息 |
| check_updates | check_updates() -> Optional[UpdateInfo] | 检查 GitHub 仓库是否有新版本可用 |
| get_stats | get_stats() -> AppStats | 获取应用运行统计（启动次数、游戏时长、ROM 数量等） |
| crash_report | crash_report(exception: Exception) -> Path | 生成崩溃诊断包（含堆栈追踪、系统信息、日志片段），返回文件路径 |

## 核心组件说明

### Job 统一长任务句柄

Job 类用于统一管理耗时操作（如下载、扫描、刮削等后台任务），提供标准化的生命周期管理。

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| __init__ | Job.__init__(name: str, priority: int = 0) | 创建任务句柄，可指定优先级（数字越大优先级越高） |
| start | Job.start() | 启动任务执行（在后台线程中运行） |
| cancel | Job.cancel() | 请求取消正在执行的任务 |
| wait | Job.wait(timeout: Optional[float] = None) -> bool | 阻塞等待任务完成，可设置超时（秒），返回是否完成 |
| on_progress | Job.on_progress(callback: Callable) | 注册进度更新回调函数 |
| on_complete | Job.on_complete(callback: Callable) | 注册任务完成回调函数 |
| on_error | Job.on_error(callback: Callable) | 注册错误处理回调函数 |

**使用示例：**

```python
job = Job("scanning", priority=1)
job.on_progress(lambda pct: print(f"进度: {pct}%"))
job.on_complete(lambda: print("扫描完成"))
job.on_error(lambda err: print(f"错误: {err}"))
job.start()
job.wait(timeout=30.0)
```

### MirrorRouter 镜像自动选路

MirrorRouter 自动选择延迟最低的 PyPI 或资源镜像服务器，提升下载速度和可靠性。

**核心功能：**

- **自动探测**：启动时自动对配置的镜像列表进行延迟探测，选择响应最快的镜像
- **手动配置**：支持通过 config/mirrors.json 手动指定镜像优先级和备用地址
- **开关控制**：可通过设置项随时开启或关闭自动选路功能
- **Fallback 机制**：主镜像连接失败或超时后，自动无缝切换至下一个备用镜像
- **持久化**：最优镜像选择结果会缓存，避免每次启动都重新探测

### 补丁工具

#### IPS 补丁

- 支持标准 IPS (International Patching System) 格式
- 支持 EEOF (End Of File) 扩展标记，允许补丁修改范围超出原始 ROM 文件大小
- 自动扩容 ROM 文件以容纳超出边界的补丁数据
- 修复前静默丢弃超出范围的补丁数据导致 ROM 损坏的问题

#### UPS 补丁

- 支持 UPS (Universal Patch System) 格式
- 内置 varint 变长整数截断检测，遇到不完整的 varint 序列时立即中止
- 提供完整的错误处理和操作回滚机制
- 修复前产生半成品补丁文件导致 ROM 不可用的问题

### 插件系统

插件采用独立目录结构，支持热加载与隔离运行。

**目录结构：**

```
plugins/
  <plugin_name>/
    plugin.json          # 插件描述文件（必填）
    main.py              # 插件主代码入口（必填）
    requirements.txt     # 插件额外依赖（可选）
    assets/              # 插件资源文件（可选）
```

**plugin.json 格式规范：**

```json
{
  "name": "插件显示名称",
  "version": "1.0.0",
  "description": "插件功能描述",
  "author": "作者名称",
  "api_version": "1.0",
  "entry": "main.py",
  "dependencies": ["插件依赖ID列表"]
}
```

**编写插件步骤：**

1. 在 plugins/ 目录下创建插件文件夹（文件夹名作为插件 ID）
2. 创建 plugin.json 描述文件，填写名称、版本、入口等元信息
3. 创建 main.py 实现插件逻辑，可调用 PluginAPI 提供的各类接口
4. 在应用设置的插件管理中启用该插件

**PluginAPI 核心接口：**

- 游戏库操作：add_rom, remove_rom, get_rom, list_roms
- 引擎与平台：get_engine, list_engines, get_platforms
- 路径与配置：get_config_dir, get_data_dir, get_setting, set_setting
- 启动与系统/UI：launch_emulator, show_notification, log_message
- 通知与日志：show_info, show_warning, show_error, debug_log
- 网络与事件：http_get, http_post, register_event_handler
- 插件私有存储：plugin_get, plugin_set, plugin_delete

## 历史问题修复详解

以下详细说明了 v1.7.0 版本修复的 12 个历史问题，包括问题原因、影响范围和具体修复方案。

### 问题 1: os.chdir 竞态条件

- **原因**：旧代码在多线程环境中调用 os.chdir() 切换全局工作目录。Python 的 os.chdir() 修改的是进程级别的全局状态，当多个线程同时调用时，一个线程切换目录后另一个线程的文件操作会指向错误的目录。
- **影响**：文件读写错误、引擎启动时找不到 ROM/BIOS 文件、引擎启动失败。
- **修复方案**：移除所有 os.chdir() 调用，改为使用 subprocess.Popen 的 cwd 参数为每个子进程独立指定工作目录。这样每个子进程有独立的工作目录，互不影响。

### 问题 2: 时长结算失真

- **原因**：_settle_stale_launches 函数在检测到停滞的模拟器进程时，会将该进程从启动到终止的时间间隔全部累加到游戏运行时长统计中。但有些进程实际上并未成功启动游戏（如配置错误导致启动失败），这些时间不应计入。
- **影响**：游戏运行时长统计不准确，用户看到的游玩时间比实际长。
- **修复方案**：修改结算逻辑为"只归零不结算"——检测到停滞进程时仅将计时器归零，不进行时长累加。只有明确标记为"游戏已开始运行"的进程才会计入时长。

### 问题 3: .cue 文件覆盖

- **原因**：旧版在处理某些光盘镜像格式时，需要生成配套的 .cue 轨道索引文件。生成时直接使用目标文件名（如 "game.cue"），如果用户目录下已有同名文件会被静默覆盖。
- **影响**：用户自定义的 .cue 文件内容丢失。
- **修复方案**：所有自动生成的 .cue 文件使用 .mikan_auto.cue 后缀（如 "game.mikan_auto.cue"），与用户文件完全隔离，永不覆盖用户文件。

### 问题 4: HttpSession 线程安全

- **原因**：旧版 HTTP 请求使用共享的 HttpSession 对象，多个线程同时发起请求时，请求头、Cookie、连接状态等共享数据可能发生竞态条件。
- **影响**：网络请求失败、响应数据损坏、Cookie 丢失导致认证失败。
- **修复方案**：为 HttpSession 添加 threading.RLock 读写锁，所有读写操作先获取读锁/写锁。同时对同一 hostname 的请求进行串行化处理（通过 hostname 匹配 bypass 优化并发性能），避免同一服务器的请求互相干扰。

### 问题 5: 引擎版本检测误判

- **原因**：detect_engine_version 函数使用的正则表达式过于简单，无法正确处理包含日期信息或其他非标准字符的版本号字符串。例如 "v2024.12.1-beta" 可能被错误解析。
- **影响**：引擎版本识别错误，导致版本比较逻辑判断失误，可能下载错误版本或误报更新可用。
- **修复方案**：重写版本检测正则表达式，优先匹配 "version/" 或 "v" 前缀后的数字序列（如 "v1.2.3"），过滤掉纯日期格式（如 "2024.12.01"），并增加版本号规范化逻辑。

### 问题 6: BIOS 检查性能

- **原因**：每次启动应用或切换到不同平台页面时，check_bios_ready 函数都会重新扫描整个 BIOS 目录，检查每个文件的存在性和完整性。当 BIOS 目录包含大量文件时，扫描操作耗时显著。
- **影响**：应用启动缓慢，切换平台时界面卡顿。
- **修复方案**：引入 5 分钟时间窗口的结果缓存。首次扫描后缓存结果，5 分钟内直接返回缓存数据。缓存失效条件：目录文件列表变更（通过 inode/mtime 检测）或超过 5 分钟。

### 问题 7: 命令分割不安全

- **原因**：旧版 _split_cmd 函数使用简单的 str.split() 按空格分割命令行参数。这种方式无法处理带引号的路径（如 "C:\\Program Files\\Emulator\\emu.exe"），会导致路径被错误分割成多个参数。
- **影响**：安装路径或 ROM 路径包含空格时，模拟器命令无法正确执行，导致启动失败。
- **修复方案**：替换为 Python 标准库 shlex.split() 函数，该函数遵循 Shell 命令行解析规则，正确处理单引号、双引号转义和空格路径。

### 问题 8: 硬编码中文国际化

- **原因**：旧版代码中部分界面文本（如按钮标签、提示信息、对话框文字）直接硬编码为中文字符串，未通过 tr() 国际化函数包装。
- **影响**：当用户切换语言包时，这些硬编码中文不会翻译成目标语言，导致界面出现中英文混排的不一致现象。
- **修复方案**：全局搜索所有硬编码中文字符串，逐一替换为 tr("中文文本") 调用。同时确保 QCoreApplication 的翻译系统在启动时正确加载语言文件。

### 问题 9: UI 阻塞

- **原因**：旧版拖拽文件导入功能在主线程（GUI 线程）中执行文件类型识别、文件大小检查、ROM 元数据解析等耗时操作。
- **影响**：拖入大量文件或大型 ROM 文件（如几百 MB 的 ISO）时，整个 UI 界面卡死无响应，用户体验极差。
- **修复方案**：将所有拖拽导入的耗时操作移至 QThread 后台线程执行。主线程仅负责接收拖拽事件并启动后台线程，后台线程通过 Qt 信号槽机制将进度和结果回调到主线程更新 UI。

### 问题 10: QtWebEngineProfile 冲突

- **原因**：旧版 QtWebEngine 使用默认的全局 profile 存储浏览器数据（缓存、Cookie、配置等）。当同时运行多个 MikanEmu 实例时，所有实例共享同一个 profile，导致配置互相覆盖。
- **影响**：多开时代理设置、Cookie、缓存等配置混乱，可能出现登录状态丢失、代理不生效等问题。
- **修复方案**：为每个 MikanEmu 实例创建独立的命名 QWebEngineProfile（如 "mikan_emu_profile_1"、"mikan_emu_profile_2"），通过实例 ID 区分，实现完全的配置隔离。

### 问题 11: --no-sandbox 过度启用

- **原因**：旧版为所有 Windows 版本统一设置 Chromium 启动参数 --no-sandbox，目的是解决 Win7 上 QtWebEngine 的沙箱兼容性问题。
- **影响**：在 Windows 10/11 等现代系统上，禁用沙箱会降低浏览器的安全隔离级别，增加潜在的安全风险。
- **修复方案**：通过读取 Windows 注册表 HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\CurrentBuild 获取系统内部版本号，仅在 build number < 7601（Windows 7 的 build号）时启用 --no-sandbox 参数，现代系统保持默认沙箱开启。

### 问题 12: 局域网口令截断

- **原因**：旧版在计算局域网连接口令的哈希值时，为了节省带宽对 SHA-256 输出进行了截断（只取前 16 字节）。虽然 16 字节的哈希空间仍然很大，但截断操作本身引入了不必要的攻击面。
- **影响**：理论上存在哈希碰撞风险，极端情况下可能导致不同口令被识别为相同身份。
- **修复方案**：移除哈希截断逻辑，使用完整的 SHA-256 输出（32 字节），彻底消除碰撞可能性。同时优化网络传输协议，采用二进制格式而非文本格式传输哈希值，减少带宽占用。

## 项目结构

```
mikan_emu/
├── config/                   # 配置文件目录
│   ├── folders.json          # 文件夹路径配置
│   ├── settings.json         # 应用设置
│   ├── lang.json             # 多语言配置
│   ├── save_paths.json       # 存档路径
│   ├── mirrors.json          # 镜像服务器配置
│   ├── cheat_paths.json      # 金手指文件路径
│   ├── stats.json            # 运行统计数据
│   ├── update_ignore.json    # 更新忽略列表
│   ├── resources.json        # 资源配置
│   ├── bios_db.json          # BIOS 数据库
│   └── plugins_enabled.json  # 插件启用状态
├── engines/                  # 引擎定义目录
│   ├── engines.json          # 引擎配置（含下载URL、匹配规则等）
│   └── downloaded/           # 已下载引擎文件
├── bios/                     # BIOS 文件目录
├── roms/                     # ROM 游戏文件目录
│   └── roms.json             # ROM 元数据索引
├── saves/                    # 存档文件目录
├── saves_backup/             # 存档备份目录
├── covers/                   # 游戏封面图片目录
├── cheats/                   # 金手指代码目录
├── backups/                  # 备份文件目录
├── logs/                     # 日志文件目录
├── temp/                     # 临时文件目录
├── exports/                  # 导出文件目录
├── lan/                      # 局域网相关目录
│   ├── history/              # 聊天历史记录
│   ├── received/             # 接收到的文件
│   ├── shared/               # 共享文件夹
│   └── shared_download/      # 共享下载目录
├── webengine/                # QtWebEngine 浏览器缓存
├── scrape_cache/             # 封面刮削缓存
├── plugins/                  # 插件目录
├── plugin_storage/           # 插件私有存储
├── crash_reports/            # 崩溃诊断报告
└── backgrounds/              # 全局背景图片
```

## 技术栈与依赖

### 最新版依赖（PySide6）

| 依赖包 | 版本要求 | 用途 |
| :--- | :--- | :--- |
| PySide6 | 最新版 | Qt6 GUI 框架 |
| PySide6-WebEngine | 可选 | 内嵌浏览器（局域网传输/资料站） |
| requests | 最新版 | HTTP 客户端 |
| loguru | 最新版 | 日志记录 |
| py7zr | 最新版 | 7z 格式解压 |
| rarfile | 最新版 | RAR 格式解压 |
| certifi | 最新版 | CA 证书包 |
| psutil | 可选 | 系统资源监控 |
| packaging | 最新版 | 版本号解析与比较 |
| PySocks | 可选 | SOCKS5 代理支持 |

### Win7 兼容版依赖（PyQt5，全部锁定版本）

| 依赖包 | 锁定版本 | 用途 |
| :--- | :--- | :--- |
| PyQt5 | ==5.15.4 | Qt5 GUI 框架（Win7 最后支持的版本） |
| PyQtWebEngine | ==5.15.4（可选） | 内嵌浏览器 |
| requests | ==2.25.1 | HTTP 客户端 |
| loguru | ==0.5.3 | 日志记录 |
| py7zr | ==0.16.1 | 7z 格式解压 |
| rarfile | ==4.0 | RAR 格式解压 |
| certifi | ==2020.12.5 | CA 证书包 |
| psutil | ==5.8.0 | 系统资源监控 |
| packaging | ==20.9 | 版本号解析与比较 |
| PySocks | ==1.7.1 | SOCKS5 代理支持 |
| pywin32 | ==228 | Windows API 绑定（PyInstaller 需要） |

## 打包与运行说明

### 方式一：已打包 exe（推荐）

两个版本均已使用 PyInstaller 打包为独立 exe 可执行文件，下载后直接运行即可，无需安装 Python 环境。

**注意事项：**
- 首次运行可能触发 Windows SmartScreen 警告，点击"更多信息"→"仍要运行"即可
- 如被杀毒软件拦截，请将程序目录加入白名单
- 程序运行后会在同级目录生成 mikan_emu/ 文件夹存放配置和数据

### 方式二：源代码运行

**最新版（PySide6）：**

```bash
# 安装依赖
pip install PySide6 requests loguru py7zr rarfile certifi psutil packaging PySocks

# 可选：安装 WebEngine
pip install PySide6-WebEngine

# 运行
python mikan_emu_7.py
```

**Win7兼容版（PyQt5）：**

```bash
# 安装依赖（Python 3.8 环境）
python -m pip install PyQt5==5.15.4 PyQtWebEngine==5.15.4 requests==2.25.1 loguru==0.5.3 py7zr==0.16.1 rarfile==4.0 certifi==2020.12.5 psutil==5.8.0 packaging==20.9 PySocks==1.7.1 pywin32==228

# 运行
python mikan_emu_pyqt5_3.py
```

### PyInstaller 打包命令

**最新版打包：**

```bash
pyinstaller --noconfirm --clean --windowed --name mikan_emu mikan_emu_7.py
```

**Win7兼容版打包：**

```bash
# 必须先安装指定版本的 PyInstaller
pip install "pyinstaller==4.10"
pyinstaller --noconfirm --clean --windowed --name mikan_emu mikan_emu_pyqt5_3.py
```

### 杀毒软件误报说明

由于 PyInstaller 打包机制会将 Python 解释器和依赖库打包进单个 exe 文件，部分杀毒软件（尤其是 Windows Defender）可能将其误报为威胁。这是 PyInstaller 打包工具的已知行为，并非代码存在问题。

**处理建议：**
1. 将程序安装目录添加到杀毒软件的排除/白名单中
2. 在 Windows Defender 中：设置 → 病毒和威胁防护 → 管理设置 → 排除项 → 添加目录
3. 如需验证代码安全性，可从 GitHub 下载源码自行编译

## 注意事项

1. **版权合规**：本项目不提供 BIOS、不提供 ROM、不二次分发模拟器软件。用户需自行准备合法的 BIOS 文件和游戏 ROM。
2. **协议不兼容**：v1.7.0 局域网协议与旧版（v1.0.x 及之前）不互通，不同版本的 MikanEmu 无法进行局域网聊天和文件传输。
3. **可选依赖降级**：未安装 QtWebEngine 时，局域网传输和老游戏资料站功能降级为打开系统默认浏览器；未安装 psutil 时性能监控功能不可用。
4. **MEDNAFEN 多实例**：已设置环境变量 MEDNAFEN_ALLOWMULTI=1，允许同时运行多个 MEDNAFEN 模拟器实例。
5. **系统要求**：Windows 7 用户请务必使用 PyQt5 版本（mikan_emu_pyqt5_3.py），PySide6 版本需要 Windows 10 版本 1809 或更高版本。
6. **安全白名单**：已打包的 exe 文件可能被杀毒软件误报，建议运行前将程序目录加入白名单。
7. **引擎下载**：部分引擎需要手动下载（url_type 为 "manual"），请在设置中查看具体说明。
8. **Linux/macOS**：本项目主要针对 Windows 平台开发，Linux/macOS 支持有限，部分功能（如硬件检测）可能不可用。

## 开发指南

### 添加新平台/引擎

1. 在源码顶部的 DEFAULT_ENGINES_JSON_STR 常量中添加新的平台配置 JSON 块
2. 配置 match 规则（exe 文件名、文件夹名、关键词）用于自动检测已安装的引擎
3. 配置 launch_template 启动模板（{exe} 和 {rom} 占位符）
4. 可选配置 perf_profiles（性能档位参数）和 version_overrides（版本兼容适配）
5. 设置 url_type 为 "direct"（直链下载）、"github_release"（GitHub Release 自动查找）或 "manual"（需手动下载）

### 扩展局域网模块

1. 实现 LanChatServer（服务器端）和 LanDiscoveryWorker（发现_worker）相关接口
2. 遵循 mikan_lan 协议格式（magic 标识 + 消息类型 + 序列化数据）
3. 注意线程安全和口令哈希完整性，避免使用截断哈希

### 编写插件

1. 参考本文档"插件系统"章节了解目录结构和 plugin.json 格式
2. 遵循 PluginAPI 接口规范调用主程序功能
3. 注意插件隔离：每个插件运行在独立命名空间中，避免全局变量污染
4. 注意异常处理：插件中的未捕获异常不应导致主程序崩溃

### 从 PyQt5 移植到 PySide6

如需将 PyQt5 版本移植到 PySide6 框架，需要注意以下变更：

1. **import 路径变更**：PyQt5 → PySide6（如 from PyQt5.QtCore → from PySide6.QtCore）
2. **Signal 语法变更**：pyqtSignal → Signal（属性名和用法一致，但导入路径不同）
3. **QWebEngine 导入路径变更**：PyQt5.QtWebEngineWidgets → PySide6.QtWebEngineCore（Settings 和 Profile）
4. **移除 Win7 特殊处理**：_setup_qt_flags() 空函数、QT_AUTO_SCREEN_SCALE_FACTOR 强制关闭等代码可移除
5. **依赖版本**：移除所有 == 版本锁定，允许使用最新版依赖

## 许可证

本项目采用 **GNU General Public License v3.0 (GPL-3.0)** 许可证。

这意味着：
- 您可以自由地使用、修改和分发本软件
- 修改后的代码也必须以 GPL-3.0 开源
- 不提供任何担保

详见项目根目录的 LICENSE 文件或访问 https://www.gnu.org/licenses/gpl-3.0.html

## 项目地址

https://github.com/luohaocheng171/mikan_emu

## 致谢

本项目的开发离不开以下开源项目和工具的支持：

- [PySide6](https://www.qt.io/qt-for-python) - Qt6 Python 绑定
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) - Qt5 Python 绑定
- [snes9x](https://github.com/snes9xgit/snes9x) - SFC 模拟器
- [duckstation](https://github.com/stenzek/duckstation) - PS1 模拟器
- [pcsx2](https://github.com/PCSX2/pcsx2) - PS2 模拟器
- [RPCS3](https://github.com/RPCS3/rpcs3) - PS3 模拟器
- [yuzu](https://github.com/yuzu-emu/yuzu) - Switch 模拟器
- [RYJinx](https://github.com/Ryujinx/Ryujinx) - Switch 模拟器
- [Xenia](https://github.com/xenia-project/xenia) - Xbox 360 模拟器
- [Dolphin](https://github.com/dolphin-emu/dolphin) - Wii/GameCube 模拟器
- [Cemu](https://github.com/cemu-project/Cemu) - Wii U 模拟器
- [PPSSPP](https://github.com/hrydgard/ppsspp) - PSP 模拟器
- [Vita3K](https://github.com/Vita3K/Vita3K) - PS Vita 模拟器
- [MAME](https://github.com/mamedev/mame) - 街机模拟器
- [RetroArch](https://github.com/libretro/RetroArch) - 多平台前端
- [mednafen](https://github.com/mednafen/mednafen) - 多平台模拟器
- [mgba](https://github.com/mgba-emu/mgba) - GBA 模拟器
- [bsnes](https://github.com/bsnes-emu/bsnes) - SFC 高精度模拟器
- [flycast](https://github.com/flyinghead/flycast) - Dreamcast 模拟器
- 以及众多 Libretro 核心开发者

同时感谢 [DeepSeek](https://www.deepseek.com/) 提供的 AI 辅助开发支持。
