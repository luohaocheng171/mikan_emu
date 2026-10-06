# MikanEmu v1.4.0

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/Qt-PySide6-orange)](https://www.qt.io/qt-for-python)

> 模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言 + 平台编辑器
> + 性能监控 + 局域网聊天/文件/共享 + 局域网传输（内嵌 LocalSend Web）
> + 封面刮削（Libretro / SteamGridDB）+ 性能档位 + 系统优先级
> + 版本适配（version_overrides）+ 打开模拟器设置
> + 引擎共享定义（_shared）+ BIOS 自动归类 + 统一代理 + 插件系统

Python 3.11+ / PySide6 / requests / loguru / py7zr / rarfile / psutil / packaging
可选：PySide6-WebEngine（内嵌浏览器）、PySocks（SOCKS5 代理）

**【法律】** 不提供 BIOS、不提供 ROM、不二次分发模拟器

---

## 功能特性

| 模块 | 功能说明 |
|------|---------|
| 游戏库管理 | 多文件夹/工作区扫描、自动识别平台、去重合并、批量导入/导出、游戏统计 |
| 模拟器引擎管理 | 内置 76 个引擎（45 平台）、自动下载/安装/更新、多镜像源、版本识别与匹配 |
| BIOS 管理 | BIOS 扫描/自动归类、BIOS 需求检测、BIOS 文件复制、bios_db.json 数据库 |
| 存档管理 | 存档自动路径检测、存档备份/还原、存档路径自定义 |
| 金手指管理 | 金手指代码管理、金手指路径配置 |
| 封面刮削 | Libretro Thumbnails + SteamGridDB 兜底、本地缓存 |
| 性能监控 | CPU/内存/GPU/网络实时监测、性能档位（省电/平衡/高性能/画质优先） |
| 局域网功能 | 聊天（广播/私聊/表情面板）、文件传输、共享文件夹实时同步 |
| Web 传输 | 内嵌 LocalSend Web 传输页（QtWebEngine）、降级为外部浏览器 |
| 版本适配 | version_overrides 引擎版本差异适配、engines.json 深度合并 |
| 插件系统 | 插件目录扫描、plugin.json 元数据、动态加载/卸载、插件存储隔离 |
| 多语言支持 | 内置中/英文、自动检测系统语言、热切换、缺失翻译自动回退 |
| 平台编辑器 | 手动添加/编辑平台、自定义 ROM 扩展名、引擎绑定 |
| 配置包管理 | 导出/导入完整配置包（引擎+BIOS+设置+金手指+存档路径） |
| ROM 补丁 | IPS/UPS 补丁应用 |
| 系统托盘 | 最小化至托盘、托盘通知、托盘菜单快捷操作 |
| UI 特性 | 暗黑赛博朋克风格、侧边栏导航、Tab 页签、资源导航页、鸣谢页 |
| 更新检查 | 自动检查更新、更新日志、忽略版本 |
| 启动优化 | 依赖自动安装、镜像源自动切换、启动器自检 |
| 模拟器设置 | 直接打开模拟器原生设置界面 |
| 引擎共享定义 | _shared 共享引擎定义（mednafen/mame/retroarch）跨平台复用 |
| 系统优先级 | 启动时自动设置进程优先级和 IO 优先级 |

---

## 技术栈

| 技术 | 说明 |
|------|------|
| Python 3.11+ | 基础运行环境 |
| PySide6 | Qt6 Python 绑定，UI 框架 |
| PySide6-WebEngine | 内嵌 Chromium 浏览器（局域网传输页可选） |
| requests | HTTP 请求（下载/刮削/API） |
| loguru | 日志记录 |
| py7zr | 7z 压缩格式支持 |
| rarfile | RAR 压缩格式支持 |
| psutil | 系统监控（CPU/内存/进程/网络） |
| packaging | 版本号解析与比较 |
| certifi | SSL 证书包 |
| PySocks | SOCKS5 代理支持（可选） |
| urllib3 | HTTP 底层库 |
| ctypes | 系统 API 调用 |

---

## 安装与运行

### 方式一：已打包 exe（推荐）

直接运行发布的 `.exe` 文件即可，无需安装 Python 环境。

### 方式二：源代码运行

1. 安装 Python 3.11+
2. 安装依赖：

```bash
pip install PySide6 requests loguru py7zr rarfile psutil packaging certifi
# 可选：pip install PySide6-WebEngine  （内嵌浏览器）
# 可选：pip install PySocks              （SOCKS5 代理）
```

3. 运行：

```bash
python mikan_emu_5.py
```

### PyInstaller 打包

```bash
pyinstaller --name mikan_emu --onedir --add-data "config;config" --add-data "lang;lang" mikan_emu_5.py
```

---

## 项目结构

```
mikan_emu/                    # 程序根目录（data 目录）
├── config/                   # 配置文件
│   ├── folders.json          # 游戏文件夹配置
│   ├── settings.json         # 程序设置
│   ├── lang.json             # 语言文件
│   ├── lang/                 # 多语言文件目录
│   ├── save_paths.json       # 存档路径
│   ├── mirrors.json          # 镜像源
│   ├── cheat_paths.json      # 金手指路径
│   ├── stats.json            # 游戏统计
│   ├── update_ignore.json    # 忽略更新版本
│   ├── resources.json        # 资源导航
│   ├── bios_db.json          # BIOS 数据库
│   ├── plugins_enabled.json  # 插件启用状态
│   └── plugin_storage/       # 插件独立存储
├── engines/                  # 模拟器引擎
│   ├── engines.json          # 引擎定义（含 _shared 共享定义）
│   ├── installed.json        # 已安装引擎记录
│   └── downloaded/           # 下载临时目录
├── bios/                     # BIOS 文件
├── roms/                     # 游戏 ROM
│   └── roms.json             # ROM 索引
├── saves/                    # 游戏存档
├── saves_backup/             # 存档备份
├── covers/                   # 游戏封面
├── cheats/                   # 金手指文件
├── backups/                  # 配置备份
├── logs/                     # 日志文件
├── temp/                     # 临时文件
├── exports/                  # 导出文件
├── lan/                      # 局域网
│   ├── history/              # 聊天记录
│   ├── received/             # 接收文件
│   ├── shared/               # 共享文件夹
│   ├── shared_download/      # 共享下载
│   └── identity.json         # 局域网身份
├── webengine/                # QtWebEngine 缓存
├── scrape_cache/             # 刮削缓存
├── plugins/                  # 插件目录（每个插件为子文件夹）
│   └── <plugin_id>/          # 插件目录
│       ├── plugin.json       # 插件元数据
│       └── main.py           # 插件入口
├── plugin_storage/           # 插件共享存储
└── random_launch/            # 示例插件（随机启动）
    ├── plugin.json
    └── main.py
```

---

## 支持的平台与引擎

**45 个平台 / 76 个引擎**（含 3 个共享引擎），完整对照表：

| 平台 | 引擎 | 来源 |
|------|------|------|
| SFC / 超级任天堂 | snes9x, bsnes | direct |
| PS1 / PlayStation | duckstation, epsxe, xebra | direct / manual |
| SS / 世嘉土星 | mednafen(shared), ssf, ymir, brimir, yaba_sanshiro_2 | direct / manual / libretro |
| DC / Dreamcast | flycast, redream, deecy | direct / manual |
| VMU / 记忆卡 | dreampotato | direct |
| GBA | mgba, vba-m | direct |
| PS2 / PlayStation 2 | pcsx2 | direct |
| FC / NES | fceux, mesence, nestopia, nintendulator | direct / manual |
| N64 | mupen64plus, gopher64, ares, simple64, rmg, neon64, project64, cen64 | direct / manual |
| NDS | desmume, melonds, noods | direct |
| 3DS | azahar, zakuro | direct |
| MD / Genesis | blastem, kega-fusion | direct |
| Master System / Game Gear | emulicious | direct |
| GB / GBC | sameboy, bgb, gambatte | direct |
| PSP | ppsspp | direct |
| Switch | ryujinx, yuzu | direct |
| PCE / TurboGrafx | mednafen(shared), geargrafx | direct |
| Neo Geo | mame(shared) | direct |
| Arcade | mame(shared) | direct |
| Sharp X68000 | px68k | direct |
| NEC PC-98 | np2kai | direct |
| FM Towns | tsugaru | direct |
| PC-FX | pcfxemu | direct |
| MSX | openmsx, bluemsx | direct |
| 86Box / PC 模拟 | 86box | direct |
| PCem / PC 模拟 | pcem | direct |
| DOS | dosbox-x | direct |
| PS4 / PlayStation 4 | shadps4 | direct |
| PS5 / PlayStation 5 | kytyps5 | direct |
| 初代 Xbox | xemu | direct |
| Xbox 360 | xenia_canary, xenia_edge | direct |
| 万能 / 前端 | retroarch(shared) | direct |
| Wii / GameCube | dolphin | direct |
| Wii U | cemu | direct |
| PS3 / PlayStation 3 | rpcs3 | direct |
| PS Vita | vita3k | direct |
| Amstrad CPC | amspirit, caprice32, cpc_syntax_error | direct |
| Commodore 64 | vice | direct |
| Atari ST | hatari | direct |
| Atari 2600 | stella | direct |
| ZX Spectrum | zesarux, 1984 | direct |
| ColecoVision | gearcoleco | direct |
| Intellivision | jzintv | direct |
| BBC Micro | b2 | direct |
| 未知渠道 | google_drive_unknown | direct |
| _shared 共享 | mednafen, mame, retroarch | direct |

> 引擎来源说明：direct = 直接下载链接；manual = 需手动下载；libretro = Libretro 核心

---

## 模块说明

### 核心类（53 个）

| 类名 | 功能 |
|------|------|
| EmulatorConfig | 模拟器配置数据类 |
| GameEntry | 游戏条目数据类 |
| HttpSession | HTTP 会话管理（连接池/代理/超时） |
| EngineImportWorker | 引擎导入工作线程 |
| GameImportWorker | 游戏导入工作线程 |
| DownloadWorker | 文件下载工作线程 |
| MirrorTestWorker | 镜像源测速工作线程 |
| UpdateCheckWorker | 更新检查工作线程 |
| ProcessMonitorWorker | 进程监控工作线程 |
| PerfMonitorWindow | 性能监控窗口 |
| LanIdentity | 局域网身份标识 |
| LanPeer | 局域网对等节点 |
| LanDiscoveryWorker | 局域网发现工作线程 |
| LanChatServer | 局域网聊天服务器 |
| LanChatClient | 局域网聊天客户端 |
| GameTableModel | 游戏表模型 |
| GameFilterProxy | 游戏过滤代理模型 |
| EngineTableModel | 引擎表模型 |
| BiosTableModel | BIOS 表模型 |
| LibretroScraperWorker | Libretro 封面刮削工作线程 |
| SteamGridDBScraperWorker | SteamGridDB 封面刮削工作线程 |
| LaunchConfigDialog | 启动配置对话框 |
| BiosSelectDialog | BIOS 选择对话框 |
| ControlsDialog | 键位设置对话框 |
| CreditsDialog | 鸣谢对话框 |
| ManualEngineDialog | 手动引擎安装对话框 |
| ExportDialog | 导出对话框 |
| PlatformConfirmDialog | 平台确认对话框 |
| DupResolveDialog | 重复文件解决对话框 |
| PatchToolDialog | ROM 补丁工具对话框 |
| ConfigPackDialog | 配置包对话框 |
| CoverScrapeDialog | 封面刮削对话框 |
| LibraryPage | 游戏库页面 |
| GameConfigCenterDialog | 游戏配置中心对话框 |
| EnginePage | 引擎管理页面 |
| BiosPage | BIOS 管理页面 |
| ChartWidget | 性能图表控件 |
| StatsPage | 统计页面 |
| ResourcesPage | 资源导航页面 |
| EmojiPanel | 表情面板 |
| LanPage | 局域网页面（聊天+文件+共享） |
| WebTransferPage | Web 传输页面（LocalSend Web） |
| SettingsPage | 设置页面 |
| ImportDialog | 导入对话框 |
| DownloadDialog | 下载对话框 |
| BatchUpdateDialog | 批量更新对话框 |
| MainPage | 主页面（Tab 导航） |
| PluginAPI | 插件 API（提供给插件的接口） |
| PluginManager | 插件管理器（扫描/加载/卸载） |
| MainWindow | 主窗口 |

### 核心函数（119 个顶层函数）

涵盖依赖自检、多语言翻译、配置读写、引擎管理、游戏导入、存档管理、BIOS 管理、游戏启动、局域网通信、封面刮削、配置包导出导入、插件加载、版本检测等全部功能。

---

## 插件系统

> 示例插件 `random_launch`（随机启动）展示了完整的插件编写格式与 API 用法。
> 该插件已打包为独立 exe 可执行文件，可直接运行体验。

### 插件目录结构

插件放在 `data/mikan_emu/plugins/<id>/` 目录下，每个插件包含：

```
plugins/
└── my_plugin/
    ├── plugin.json       # 插件元数据（id/name/version/description/entry/api_version）
    └── main.py           # 插件入口文件（必须包含 register(api) 函数）
```

#### plugin.json 格式

```json
{
    "id": "my_plugin",
    "name": "我的插件",
    "version": "1.0.0",
    "description": "插件描述",
    "entry": "main.py",
    "api_version": "1.0"
}
```

### PluginAPI 接口参考

插件通过 `register(api)` 函数入口接收 PluginAPI 实例，可调用以下方法：

#### 游戏库操作

| 方法 | 说明 |
|------|------|
| api.get_games() | 获取游戏库列表，返回 GameEntry 对象列表 |
| api.get_game(path) | 根据文件路径获取单个游戏对象 |
| api.update_game(path, **fields) | 更新游戏字段（如自定义平台名等） |
| api.set_cover(game_path, image) | 为游戏设置封面图片 |

#### 引擎与平台

| 方法 | 说明 |
|------|------|
| api.get_engines() | 获取已安装引擎列表 |
| api.get_platforms() | 获取平台/引擎定义 |

#### 路径与配置

| 方法 | 说明 |
|------|------|
| api.get_paths() | 获取关键目录路径字典（data/roms/bios/saves/logs/plugins 等） |
| api.get_settings() | 获取当前程序设置字典 |
| api.set_setting(key, value) | 设置程序配置项 |

#### 启动与系统

| 方法 | 说明 |
|------|------|
| api.launch_game(game) | 启动指定游戏 |
| api.open_url(url) | 在默认浏览器中打开网页 |
| api.open_folder(path) | 打开系统文件夹 |

#### UI 扩展

| 方法 | 说明 |
|------|------|
| api.add_page(title, widget, icon) | 在侧边栏添加新页面（title 为标签名，widget 为 QWidget 实例，icon 为 emoji 图标） |
| api.add_menu_action(menu_name, label, callback) | 在指定菜单下添加动作 |
| api.add_tray_action(label, callback) | 在系统托盘菜单中添加动作 |
| api.show_dialog(widget) | 以对话框形式显示 Widget |

#### 通知与日志

| 方法 | 说明 |
|------|------|
| api.notify(title, message) | 发送系统托盘通知（4秒自动消失） |
| api.log(msg, level) | 写入日志（level 可选 INFO/WARNING/ERROR/DEBUG） |

#### 网络与事件

| 方法 | 说明 |
|------|------|
| api.http() | 获取共享 HTTP 会话实例（支持代理/超时配置） |
| api.on(event, callback) | 注册事件监听器 |
| api.emit(event, **kwargs) | 触发事件（插件内部或跨插件通信） |

#### 插件私有存储

| 方法 | 说明 |
|------|------|
| api.storage_get(key, default) | 读取插件私有存储（JSON 文件） |
| api.storage_set(key, value) | 写入插件私有存储 |

### 编写自己的插件 - 步骤

#### 步骤 1：创建插件目录

在 MikanEmu 的 `data/mikan_emu/plugins/` 目录下创建新文件夹，文件夹名称即为插件 ID：

```
plugins/
└── my_custom_plugin/
```

#### 步骤 2：创建 plugin.json

```json
{
    "id": "my_custom_plugin",
    "name": "我的自定义插件",
    "version": "1.0.0",
    "description": "插件功能描述",
    "entry": "main.py",
    "api_version": "1.0"
}
```

#### 步骤 3：创建 main.py

插件入口文件必须包含一个 `register(api)` 函数，程序加载插件时会调用该函数并传入 PluginAPI 实例。

```python
# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class MyPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self._api = api
        v = QVBoxLayout(self)
        title = QLabel("我的插件页面")
        v.addWidget(title)

    def some_action(self):
        games = self._api.get_games()
        self._api.notify("提示", f"游戏库共有 {len(games)} 个游戏")

def register(api):
    api.add_page("我的插件", lambda: MyPage(api), icon="tool")
    api.log("我的插件已加载")
```

#### 步骤 4：重启程序

在 MikanEmu 设置页面点击「重启程序」，插件将被自动扫描并加载。

### 示例插件：随机启动

本项目附带一个示例插件 `random_launch`（随机启动），实现了一个简单的"随机启动"功能：点击按钮从游戏库中随机选取一个游戏并直接启动。

该插件演示了以下插件开发要点：

- 插件目录结构与 plugin.json 元数据
- register(api) 入口函数的编写规范
- 使用 PluginAPI 操作游戏库（读取/启动）
- 创建自定义 QWidget 页面并注册到侧边栏
- 使用通知系统和日志系统
- 插件私有存储的使用

#### RandomPage 类

继承 QWidget，实现插件的 UI 页面：

```python
class RandomPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self._api = api          # 保存 API 引用
        self._current = None     # 当前选中的游戏
        self._build_ui()         # 构建界面

    def _build_ui(self):
        # 使用 QVBoxLayout 布局
        # 创建 QLabel/QPushButton/QListWidget 等控件
        # 绑定信号槽

    def _roll(self):
        # 核心逻辑：获取游戏列表 -> 随机选择 -> 显示 -> 启动

    def _relaunch(self):
        # 重新启动上次抽到的游戏
```

#### register 函数

插件加载入口，程序启动时调用一次：

```python
def register(api):
    # 插件入口。程序加载时调用一次。
    api.add_page("随机启动", lambda: RandomPage(api), icon="random")
    api.log("随机启动插件已加载")
```

### 插件运行与测试

#### 方式一：通过 MikanEmu 加载

1. 将插件文件夹放入 `data/mikan_emu/plugins/` 目录
2. 启动 MikanEmu
3. 在侧边栏找到插件页面

#### 方式二：独立运行（已打包 exe）

示例插件已打包为独立 exe，可直接运行体验随机启动功能（需依赖 MikanEmu 主程序的 data 目录）。

### 插件注意事项

1. **插件隔离**：每个插件拥有独立的 plugin_storage 目录，插件间数据不共享
2. **API 版本**：插件的 api_version 必须与主程序兼容，否则插件将被跳过
3. **异常处理**：插件内的异常不会导致主程序崩溃，但会在日志中记录
4. **UI 线程**：所有 UI 操作必须在主线程执行，耗时操作应使用 QThread
5. **资源清理**：插件不需要手动卸载，重启程序时会重新扫描加载
6. **图标**：add_page 的 icon 参数支持 emoji 字符，如 random/tool/chart 等

---

## 注意事项

1. **管理员权限**：部分功能（如进程优先级设置）可能需要管理员权限，可右键选择"以管理员身份运行"
2. **杀毒软件**：打包后的 exe 可能被杀毒软件误报，请将程序目录加入杀毒软件白名单
3. **依赖安装**：首次运行会自动检测并安装缺失依赖，需保持网络连接
4. **QtWebEngine**：内嵌浏览器功能需要安装 PySide6-WebEngine，未安装时局域网传输页将降级为外部浏览器打开
5. **psutil**：性能监控功能需要 psutil，未安装时性能监控模块不可用
6. **BIOS/ROM 法律**：本项目不提供任何 BIOS/ROM 文件，请自行准备合法获取的文件
7. **MEDNAFEN 多实例**：程序已设置 MEDNAFEN_ALLOWMULTI=1 以支持多实例运行
8. **局域网协议**：局域网功能使用自定义协议，不同版本间可能不互通，建议统一版本
9. **PyInstaller 打包**：打包时需注意 --add-data 参数包含 config/lang 等静态资源目录

---

## 开发指南

### 代码风格

- 统一 UTF-8 编码，文件头部声明 `# -*- coding: utf-8 -*-`
- 使用 loguru 进行日志记录，避免 print
- 异步操作使用 QThread + Signal/Slot 机制
- 配置文件使用 JSON 格式，提供默认值兜底

### 添加新平台支持

1. 在 `DEFAULT_ENGINES_JSON_STR` 的 JSON 中添加新平台对象
2. 定义 platform_name、rom_extensions 和 engines 字段
3. 每个引擎需定义 version/url/url_type/match/launch_template 等字段

### 添加新引擎支持

1. 在对应平台的 engines 对象下添加新引擎定义
2. 或使用 _shared 共享定义（适用于跨平台复用如 mednafen/mame/retroarch）
3. url_type 支持：direct（直链）、github_release（GitHub Release）、libretro（Libretro 核心）、manual（手动下载）

### 添加新语言支持

1. 在 config/lang/ 目录下创建新的语言 JSON 文件（如 ja.json）
2. 复制 lang.json 的键结构并翻译值
3. 程序启动时自动检测系统语言并加载

### 开发插件

1. 在 plugins/ 目录下创建插件文件夹
2. 创建 plugin.json 元数据文件
3. 创建 main.py 入口文件，实现 register(api) 函数
4. 参考内置示例插件 random_launch 了解 API 用法
5. 重启程序后插件自动扫描加载

---

## 许可证

GNU General Public License v3.0

本程序是自由软件：你可以自由修改和重新分发它。
不提供任何担保，甚至不包括适销性或特定用途适用性的隐含担保。

详见 [LICENSE](LICENSE) 文件。

---

## 致谢

本项目的开发离不开以下开源项目和工具的支持：

- [PySide6](https://www.qt.io/qt-for-python) - Qt6 Python 绑定
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
