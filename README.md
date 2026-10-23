# MikanEmu v1.8.0 官方文档

<div align="center">

[![GPL-3.0 License](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-Qt6-brightgreen.svg)](https://www.qt.io/)

**MikanEmu** — 模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言 + 平台编辑器 + 性能监控 + 局域网协作 + 插件系统

*AI辅助开发工具：DeepSeek*

</div>

---

## 项目概述

MikanEmu 是一款功能极其丰富的模拟器前端管理工具，集游戏库管理、引擎下载/安装、局域网协作、插件扩展、封面刮削、性能监控、按键映射、参数动态配置等于一体。本项目已使用 PyInstaller 打包为独立可执行文件（exe），可直接运行无需配置 Python 环境。

### 版本信息

- **当前版本**：v1.8.0
- **框架**：PySide6 (Qt6)
- **Python 要求**：3.11+
- **支持平台**：44 个（FC/N64/PS1/PS2/PS3/PS4/PS5/SFC/GBA/GB/PSP/SS/DC/Xbox/Xbox360/Wii/WiiU/PSVita/3DS/NDS/PC-98/X68000/FM Towns/PC-FX/MSX/86Box/PCem/DOS/Amstrad CPC/C64/Atari ST/Atari 2600/ZX Spectrum/ColecoVision/Intellivision/BBC Micro/Switch 等）
- **引擎数量**：76 个（+ 3 个共享引擎定义）
- **核心类**：75 个
- **顶层函数**：148 个
- **许可证**：GPL-3.0

---

## 核心功能特性

### 基础功能

- **综合管理**：模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言支持 + 平台编辑器
- **游戏库管理**：游戏扫描、导入/导出、封面刮削（Libretro / SteamGridDB）、金手指管理、BIOS 自动归类
- **引擎管理**：引擎下载/安装/卸载、版本识别、引擎共享定义（_shared）、版本适配（version_overrides）
- **多文件夹/工作区**：多工作区管理、路径重定向、全局背景自定义
- **性能监控**：CPU/内存/磁盘实时监测、性能档位切换（省电/平衡/高性能/画质优先）、系统优先级调整

### v1.8.0 新增核心功能

- **Job Object 托管模拟器子进程**：Windows Job Object 封装，主程序退出时自动清理模拟器进程，彻底杜绝孤儿进程问题
- **低级键盘钩子 KeyMapper**：基于 keyboard 库的全局键盘钩子，支持按键重映射，仅对模拟器子进程生效，支持全局映射 + 按游戏覆盖
- **模拟器参数 schema（ParamSchemaDialog）**：每个引擎可在 engines.json 中定义 param_schema，UI 根据 schema 动态生成参数表单（支持 bool/int/choice/text/file/dir 六种控件类型），用户无需手动编辑命令行参数
- **GitHub Releases 全量拉取**：ReleasesWorker 拉取 GitHub Releases API，UpdateDialog 以表格形式列出每个引擎的可用版本，用户自主选择下载，支持 GitHub Token 提高速率限制、镜像加速开关、预发布版本标记
- **统计图表悬停精确时间**：ChartWidget 鼠标悬停显示「日期 / 精确时长 / 原始秒数」，动态阈值适配不同时间范围，自动避让窗口边缘
- **平台列 UI 错位修复**：平台列改用 QStyledItemDelegate 实现，彻底修复滚动/列宽调整时的 QComboBox 错位问题
- **MikanAPI 新增 keymap / job 子 API**：插件可通过 api.keymap 和 api.job 直接操作按键映射和任务管理

### 网络与协作

- **局域网聊天**：基于 UDP 广播的局域网发现 + TCP 聊天服务器，支持多实例
- **局域网文件传输**：内置 Web 服务（基于 http.server），支持文件夹级实时同步、传输进度百分比显示、自动重传与接收确认
- **MirrorRouter 镜像自动选路**：自动探测并选择最快的资源镜像服务器，支持手动配置和开关控制

### 扩展与开发

- **插件系统**：完整的插件目录结构、plugin.json 元数据规范、PluginAPI 接口（游戏库操作/启动与系统/UI 扩展/通知与日志/配置与存储/网络与事件）、插件隔离加载
- **MikanAPI 统一接口**：11 个子 API（games/engines/download/scrape/patch/bios/stats/settings/mirrors/plugins/keymap），标准化外部调用
- **Job 统一长任务句柄**：标准化后台任务管理框架，支持进度回调、取消、超时和错误处理
- **补丁工具**：IPS（EEOF 扩展支持）和 UPS（varint 截断检测）补丁应用，自动格式识别

### 系统兼容与诊断

- **日志环形缓冲**：deque(maxlen=2000) 内存缓冲 + 文件日志（自动轮转 10MB）+ stderr 输出，日志保留天数可配置
- **崩溃诊断包**：自动收集系统信息、设置、日志片段，生成 crash_reports 目录下的诊断包
- **Windows 版本检测**：启动时检测 Windows 版本，低版本弹出警告
- **硬件探测**：probe_hardware() 探测 CPU/内存/磁盘/GPU 信息，detect_machine_tier() 自动分级
- **资源策略**：get_recommended_policy() / validate_resource_policy() / apply_resource_policy() 三级资源管理

---

## v1.8.0 关键技术与功能详解

### 1. Job Object 进程托管

**问题**：模拟器进程由 MikanEmu 子进程启动，当主程序异常退出或被强制关闭时，模拟器进程会变成孤儿进程残留于系统中，占用 CPU/内存资源。

**解决方案**：封装 Windows Job Object API（kernel32.CreateJobObjectW），将模拟器子进程加入 Job 组。主窗口 closeEvent 中调用 job.close()，操作系统会自动终止 Job 组内所有进程。

**核心类**：

| 类/函数 | 说明 |
| :--- | :--- |
| JobObject | Windows Job Object 封装类，支持 name 命名、kill_on_close 开关 |
| get_job_object() | 获取全局 JobObject 单例 |
| assign_to_job(pid) | 将指定 PID 加入 Job 组 |
| is_in_job(pid) | 检查进程是否在 Job 组中 |

**使用方式**：launch_game() 启动模拟器后自动调用 assign_to_job(proc.pid)；MainWindow.closeEvent 中调用 job.close()。

**设置项**：`job_object_kill_on_close`（默认 True）

### 2. KeyMapper 虚拟按键映射

**功能**：通过低级键盘钩子（keyboard 库）拦截物理按键，重映射后发送给模拟器窗口。仅对由本程序启动的模拟器进程生效。

**核心特性**：

- **全局映射**：对所有游戏统一生效
- **按游戏覆盖**：为单个游戏设置独立的按键映射（keymap_games.json）
- **OSD 提示**：映射生效时屏幕显示提示
- **前台检测**：仅当模拟器窗口在前台时生效（keymap_only_foreground）
- **防重入**：_suppress_keys 集合防止虚拟按键被再次钩住形成死循环

**核心类**：

| 类/函数 | 说明 |
| :--- | :--- |
| KeyMapEntry | 按键映射条目数据类（physical/virtual/enabled/note） |
| KeyMapper | 键盘钩子管理器（全局+按游戏映射） |
| KeyMapDialog | UI 编辑器（表格形式编辑映射关系） |
| get_keymapper() | 获取全局 KeyMapper 单例 |
| start_keymapper() / stop_keymapper() | 启停钩子 |

**设置项**：

| 设置项 | 默认值 | 说明 |
| :--- | :--- | :--- |
| keymap_enabled | False | 启用按键映射 |
| keymap_only_foreground | True | 仅前台生效 |
| keymap_show_osd | True | 显示 OSD 提示 |

**依赖**：keyboard 库（可选依赖，pip install keyboard）

### 3. 模拟器参数 schema（ParamSchemaDialog）

**功能**：在 engines.json 中为每个引擎定义 param_schema 数组，UI 根据 schema 动态生成参数配置表单，用户无需记忆命令行参数格式。

**支持的控件类型**：

| type | UI 控件 | 示例 |
| :--- | :--- | :--- |
| bool | QCheckBox | fullscreen（全屏开关） |
| int | QSpinBox | frameskip（跳帧 0-10） |
| choice | QComboBox | renderer（渲染器选择） |
| text | QLineEdit | 自由文本输入 |
| file | QLineEdit + 浏览按钮 | 配置文件路径 |
| dir | QLineEdit + 浏览按钮 | 目录路径 |

**schema 字段定义**：

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| key | str | 参数键名（代码中引用用） |
| label | str | UI 显示标签 |
| type | str | 控件类型 |
| default | Any | 默认值 |
| args_template | str | 命令行参数模板（{value} 为占位符） |
| options | list[str] | choice 类型的可选值（可选） |
| min/max | int | int 类型的范围限制（可选） |

**GameEntry 新增字段**：`param_values`（dict），存储每个游戏独立的参数覆盖值。

**渲染流程**：_build_param_args() 读取 param_schema + param_values → 生成命令行参数字符串 → resolve_launch_args() 集成到启动命令。

### 4. GitHub Releases 全量拉取

**功能**：ReleasesWorker 通过 GitHub API（/repos/{owner}/{repo}/releases?per_page=30）拉取所有引擎的 Release 列表，UpdateDialog 以表格形式展示每个引擎的可用版本，用户自主选择下载。

**核心特性**：

- **GitHub Token 支持**：settings.github_token 配置 Token 可提高 API 速率限制（从 60/h 提升到 5000/h）
- **镜像加速开关**：下载时可选是否走镜像服务器
- **预发布版本标记**：is_prerelease 标记的版本在 UI 中以不同样式显示
- **版本对比**：自动对比已安装版本与最新版本，标记可更新项

### 5. ChartWidget 统计图表增强

**改进**：鼠标悬停时显示精确的时间信息（日期 + 精确时长 + 原始秒数），替代之前的粗略显示。

**技术细节**：

- 动态阈值：7 天图约 40px/条、30 天图约 15px/条，自动调整柱状图宽度
- 自动避让：tooltip 根据鼠标位置自动选择显示在柱状图上方或下方，避免超出窗口边界
- 精确时间：显示格式化为「YYYY-MM-DD HH:MM:SS」

### 6. QStyledItemDelegate 平台列修复

**问题**：原实现使用 QTableView.setCellWidget(QComboBox) 方式嵌入下拉框，在滚动或调整列宽时容易出现 UI 错位（下拉框位置偏移、内容重叠）。

**解决方案**：改用 QStyledItemDelegate 子类（PlatformComboDelegate）实现自定义绘制和编辑，完全接管单元格的绘制和编辑生命周期，消除错位问题。

---

## API 参考手册

### MikanAPI 统一接口

MikanAPI 是 v1.8.0 的核心抽象层，提供 11 个子 API，所有子 API 通过事件系统（Events）进行通信。

**获取 API 实例**：

```python
import mikan_emu
api = mikan_emu.get_api()
```

**事件系统**：

| 方法 | 说明 |
| :--- | :--- |
| api.on(event, callback) | 订阅事件 |
| api.off(event, callback) | 取消订阅 |
| api.emit(event, **kwargs) | 触发事件 |

**事件类型**（Events 类）：GAMES_CHANGED、GAME_ADDED、GAME_CLOSED、SETTINGS_CHANGED、MIRRORS_CHANGED、KEYMAP_CHANGED 等。

### 子 API 一览

#### 1. games（游戏库 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| list | list() -> list[dict] | 获取游戏库列表 |
| get | get(path: str) -> Optional[dict] | 获取单个游戏详情 |
| add | add(entry: dict) -> dict | 添加游戏到库 |
| update | update(path: str, **fields) -> bool | 更新游戏元数据 |
| remove | remove(path: str) -> bool | 从库中移除游戏 |
| launch | launch(path: str) -> Optional[Job] | 启动游戏（返回 Job 句柄） |

#### 2. engines（引擎管理 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| list | list() -> list[dict] | 列出所有已安装引擎 |
| get | get(platform: str, engine: str) -> Optional[dict] | 获取引擎详情 |
| install_from_dir | install_from_dir(path, platform, engine_name, ...) -> dict | 从本地目录安装引擎 |
| install_from_url | install_from_url(platform, engine, progress_cb) -> Job | 从 URL 下载并安装 |
| uninstall | uninstall(platform, engine) -> bool | 卸载引擎 |

#### 3. download（下载 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| start | start(platform: str, engine: str) -> Job | 启动下载任务（自动走镜像） |
| cancel | cancel(job_id: str) -> bool | 取消下载任务 |
| list | list() -> list[dict] | 列出所有下载任务状态 |

#### 4. scrape（封面刮削 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| libretro | libretro(game_paths, img_type, overwrite) -> Job | 从 Libretro 刮削封面 |
| steamgriddb | steamgriddb(game_paths, api_key, img_type, overwrite) -> Job | 从 SteamGridDB 刮削封面 |

#### 5. patch（补丁 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| apply_ips | apply_ips(rom, patch, out, backup) -> dict | 应用 IPS 补丁 |
| apply_ups | apply_ups(rom, patch, out, backup) -> dict | 应用 UPS 补丁 |
| apply_auto | apply_auto(rom, patch, out, backup) -> dict | 自动识别格式并应用补丁 |

#### 6. bios（BIOS API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| scan | scan() -> list[dict] | 扫描 BIOS 目录 |
| identify | identify(path: str) -> Optional[str] | 识别 BIOS 文件对应的平台 |
| organize | organize(dry_run) -> dict | 自动整理 BIOS 文件 |
| import_files | import_files(paths) -> int | 批量导入 BIOS 文件 |

#### 7. stats（统计 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| summary | summary() -> dict | 获取统计汇总（总时长/总游戏数/总启动次数/按平台统计） |
| daily | daily(days=30) -> list[dict] | 获取最近 N 天的每日统计 |

#### 8. settings（设置 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| get | get(key: str, default=None) -> Any | 获取设置项 |
| set | set(key: str, value) -> bool | 设置配置项并持久化 |
| all | all() -> dict | 获取所有设置 |
| save | save() -> bool | 手动保存设置 |
| reload | reload() -> dict | 重新加载设置 |
| folders | folders() -> list | 获取文件夹配置列表 |

#### 9. mirrors（镜像 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| list | list(use_api=False) -> list[str] | 列出可用镜像 |
| set_enabled | set_enabled(value: bool) -> bool | 启用/禁用镜像 |
| set_auto | set_auto(value: bool) -> bool | 启用/禁用自动选路 |
| set_region | set_region(region: str) -> bool | 设置区域（auto/cn/overseas/direct） |
| get_region | get_region() -> str | 获取当前区域设置 |

#### 10. plugins（插件 API）

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| list | list() -> list[dict] | 列出所有插件及状态 |
| set_enabled | set_enabled(plugin_id: str, enabled: bool) -> bool | 启用/禁用插件 |
| install_from_dir | install_from_dir(path: str) -> bool | 从目录安装插件 |
| install_from_json | install_from_json(path: str) -> bool | 从 JSON 文件安装插件 |

#### 11. keymap（按键映射 API）★ v1.8.0 新增

| 方法 | 签名 | 描述 |
| :--- | :--- | :--- |
| get_global | get_global() -> list[dict] | 获取全局按键映射 |
| set_global | set_global(entries: list) -> bool | 设置全局按键映射 |
| get_game | get_game(game_path: str) -> list[dict] | 获取指定游戏的按键映射 |
| set_game | set_game(game_path: str, entries: list) -> bool | 设置指定游戏的按键映射 |
| clear_game | clear_game(game_path: str) -> bool | 清除指定游戏的按键映射 |

### Job 统一长任务句柄

Job 是所有后台异步任务的统一抽象，封装了 QThread + Worker 模式。

| 方法 | 说明 |
| :--- | :--- |
| Job(worker) | 构造函数，传入继承自 QObject 的 Worker |
| job.progress.connect(callback) | 订阅进度信号 (current, total) |
| job.finished.connect(callback) | 订阅完成信号 (result) |
| job.error.connect(callback) | 订阅错误信号 (error) |
| job.cancel() | 取消任务 |
| job.is_done | 是否已完成 |
| job.is_cancelled | 是否已取消 |

### MirrorRouter 镜像自动选路

MirrorRouter 是资源下载的镜像自动选择器，支持：

- **自动探测**：按顺序 ping 各镜像，选择延迟最低的
- **手动配置**：用户可在 settings.json 中手动指定镜像 URL 列表和优先级
- **开关控制**：settings.download_use_mirror 控制是否走镜像
- **Fallback 机制**：主镜像失败时自动切换备用镜像，全部失败时直连源站
- **探针缓存**：探测结果缓存 5 分钟，避免重复探测

---

## 插件系统

### 目录结构

插件必须放置在 `plugins/` 目录下，每个插件一个独立文件夹：

```
plugins/
├── my_plugin/
│   ├── plugin.json          # 插件元数据（必填）
│   ├── main.py              # 插件入口（必填）
│   └── ...                  # 其他资源文件
└── another_plugin/
    ├── plugin.json
    └── main.py
```

### plugin.json 格式

```json
{
  "id": "my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件描述",
  "author": "作者名",
  "api_version": "1.0",
  "entry": "main.py",
  "settings": {
    "some_key": "default_value"
  }
}
```

### PluginAPI 接口参考

PluginAPI 是插件开发的核心接口，提供以下功能模块：

**游戏库操作**：

| 方法 | 说明 |
| :--- | :--- |
| get_games() | 获取游戏库列表 |
| get_game(path) | 获取单个游戏详情 |
| update_game(path, **fields) | 更新游戏元数据 |
| set_cover(game_path, image) | 设置游戏封面图片 |

**引擎与平台**：

| 方法 | 说明 |
| :--- | :--- |
| get_engines() | 获取已安装引擎列表 |
| get_platforms() | 获取平台/引擎定义 |

**路径与配置**：

| 方法 | 说明 |
| :--- | :--- |
| get_paths() | 获取各目录路径（data/roms/bios/saves/logs/plugins 等） |
| get_settings() | 获取所有设置项 |
| set_setting(key, value) | 设置配置项并持久化 |

**启动与系统**：

| 方法 | 说明 |
| :--- | :--- |
| launch_game(game) | 启动游戏 |
| open_url(url) | 在系统默认浏览器打开 URL |
| open_folder(path) | 打开文件夹 |

**UI 扩展**：

| 方法 | 说明 |
| :--- | :--- |
| add_page(title, widget, icon) | 在侧边栏添加新页面 |
| add_menu_action(menu_name, label, callback) | 在菜单中添加动作 |
| add_tray_action(label, callback) | 在系统托盘菜单中添加动作 |
| show_dialog(widget) | 显示对话框 |

**通知与日志**：

| 方法 | 说明 |
| :--- | :--- |
| notify(title, message) | 发送系统通知（托盘气泡） |

**事件与订阅**：

| 方法 | 说明 |
| :--- | :--- |
| on(event, callback) | 订阅事件 |
| emit(event, **kwargs) | 触发事件 |

### 编写插件步骤

1. 在 `plugins/` 目录下创建插件文件夹
2. 编写 `plugin.json` 元数据文件
3. 编写 `main.py` 入口文件，实现 `register(api)` 函数
4. 重启 MikanEmu 或点击「加载插件」按钮

### 示例插件（随机启动页面）

插件 `main.py` 结构：

```python
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

def register(api):
    """插件入口函数，由 PluginManager 调用"""
    
    class RandomPage(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("随机启动页面"))
    
    # 注册侧边栏页面
    api.add_page("随机启动", RandomPage(), icon="🎲")
```

---

## 项目结构

```
mikan_emu/
├── config/                    # 配置文件目录
│   ├── folders.json           # 文件夹路径配置
│   ├── settings.json          # 应用设置
│   ├── lang.json              # 语言配置
│   ├── save_paths.json        # 存档路径
│   ├── cheat_paths.json       # 金手指路径
│   ├── mirrors.json           # 镜像配置
│   ├── stats.json             # 统计数据
│   ├── update_ignore.json     # 更新忽略列表
│   ├── resources.json         # 资源策略
│   ├── bios_db.json           # BIOS 数据库
│   ├── plugins_enabled.json   # 插件启用状态
│   ├── keymap.json            # ★ v1.8.0：全局按键映射
│   └── keymap_games.json      # ★ v1.8.0：按游戏按键映射
├── engines/                   # 引擎定义与下载
│   ├── engines.json           # 引擎定义（含 param_schema）
│   ├── installed.json         # 已安装引擎列表
│   └── downloaded/            # 下载临时文件
├── bios/                      # BIOS 文件
├── roms/                      # ROM 游戏文件
│   └── roms.json              # 游戏库索引
├── saves/                     # 存档文件
├── saves_backup/              # 存档备份
├── covers/                    # 封面图片
├── cheats/                    # 金手指代码
├── backups/                   # 备份文件
├── logs/                      # 日志文件（自动轮转）
├── temp/                      # 临时文件
├── exports/                   # 导出文件
├── lan/                       # 局域网
│   ├── history/               # 聊天记录
│   ├── received/              # 接收文件
│   ├── shared/                # 共享文件夹
│   ├── shared_download/       # 共享下载
│   └── identity.json          # 局域网身份
├── webengine/                 # QtWebEngine 缓存
├── scrape_cache/              # 刮削缓存
├── plugins/                   # 插件目录
├── plugin_storage/            # 插件私有存储
├── crash_reports/             # ★ v1.8.0：崩溃诊断包
├── backgrounds/               # 全局背景图片
└── mikan_emu.py               # 主程序（单文件架构）
```

---

## 技术栈与依赖

### 核心依赖

| 依赖 | 说明 |
| :--- | :--- |
| PySide6 | Qt6 Python 绑定（GUI 框架） |
| requests | HTTP 请求库 |
| loguru | 日志管理 |
| py7zr | 7z 压缩包处理 |
| rarfile | RAR 压缩包处理 |
| certifi | SSL 证书包 |
| psutil | 系统监控（CPU/内存/磁盘/进程） |
| packaging | 版本号解析与比较 |

### 可选依赖

| 依赖 | 说明 | 功能 |
| :--- | :--- | :--- |
| PySide6-WebEngine | QtWebEngine | 内嵌浏览器（局域网传输/老游戏资料页） |
| keyboard | 低级键盘钩子 | 虚拟按键映射（KeyMapper） |
| PySocks | SOCKS5 代理 | SOCKS5 代理支持 |

### 运行时依赖（模拟器侧）

| 依赖 | 说明 |
| :--- | :--- |
| Python 3.11+ | 运行环境 |
| Visual C++ Redistributable | Windows 运行时库 |

---

## 打包与运行说明

### 方式一：已打包 exe（推荐）

直接运行下载的 exe 文件即可，无需安装 Python 环境。

**注意事项**：
- 首次运行可能触发 Windows SmartScreen 警告，点击「更多信息」→「仍要运行」即可
- 如被杀毒软件误报，请将程序目录加入杀毒软件白名单
- 按键映射功能（KeyMapper）需要 keyboard 库支持，如未安装则按键映射功能不可用但不影响其他功能

### 方式二：源代码运行

```bash
# 安装依赖
pip install PySide6 requests loguru py7zr rarfile certifi psutil packaging

# 可选：安装 WebEngine
pip install PySide6-WebEngine

# 可选：安装按键映射支持
pip install keyboard

# 运行
python mikan_emu.py
```

### PyInstaller 打包命令

```bash
# 基础打包
pyinstaller --onefile --name mikan_emu --add-data "config;config" --add-data "engines;engines" mikan_emu.py

# 带图标打包
pyinstaller --onefile --name mikan_emu --icon=app.ico --add-data "config;config" --add-data "engines;engines" mikan_emu.py

# 注意事项：
# 1. 如需包含 keyboard 库支持，确保 pip install keyboard 已执行
# 2. PySide6 需要额外指定隐藏导入：
#    pyinstaller --hiddenimport=PySide6.QtWebEngineWidgets ...
# 3. 打包后首次运行会提示安装缺失依赖，也可预先手动安装
```

---

## 注意事项

1. **管理员权限**：部分功能（如进程管理、某些模拟器启动）可能需要管理员权限运行
2. **杀毒软件**：PyInstaller 打包的 exe 可能被杀毒软件误报，建议将程序目录加入白名单；keyboard 库的全局钩子也可能被拦截
3. **可选依赖降级**：PySide6-WebEngine（内嵌浏览器）、psutil（系统监控）、keyboard（按键映射）均为可选依赖，缺失时对应功能降级但程序可正常运行
4. **MEDNAFEN 多实例**：程序自动设置 MEDNAFEN_ALLOWMULTI=1 环境变量，支持同时运行多个 MEDNAFEN 实例
5. **局域网协议**：局域网聊天和文件传输使用自定义二进制协议，不同版本间可能不互通，建议保持版本一致
6. **QtWebEngine 独立进程**：QtWebEngine 在独立进程中运行，任务管理器中可能看到多个 mikan_emu 进程
7. **Job Object 平台限制**：Job Object 仅 Windows 平台生效，Linux/macOS 上 assign_to_job 返回 False 但不影响功能
8. **GitHub API 速率限制**：未配置 Token 时 GitHub API 限制为 60 请求/小时，配置 Token 后可提升至 5000 请求/小时

---

## 开发指南

### 添加新平台/引擎

1. 编辑 `engines/engines.json`，在顶层添加平台对象
2. 平台对象需包含 `platform_name`、`rom_extensions`、`engines` 字段
3. 每个引擎需定义 `version`、`url`、`url_type`、`archive`、`match`、`launch_template` 等字段
4. ★ v1.8.0 新增：可为引擎添加 `param_schema` 数组定义可调参数
5. ★ v1.8.0 新增：可使用 `version_overrides` 数组定义版本范围适配规则
6. ★ 新增：可使用 `_shared` 引擎定义实现引擎定义复用

### 扩展局域网模块

局域网模块基于 UDP 广播发现 + TCP 数据传输，扩展点包括：

- `LanDiscoveryWorker`：局域网发现逻辑
- `LanChatServer`/`LanChatClient`：聊天服务器/客户端
- `LanPage`：局域网功能 UI 页面
- `_scan_shared_dir`/`_scan_shared_download_dir`：共享目录扫描

### 编写插件

1. 参考「插件系统」章节的目录结构和 plugin.json 格式
2. 实现 `register(api)` 函数作为入口
3. 通过 api 对象调用 PluginAPI 提供的接口
4. 可使用 `api.add_page()` 添加侧边栏页面
5. 可使用 `api.on()/emit()` 订阅/触发事件
6. ★ v1.8.0 新增：插件可通过 `mikan_emu.get_api()` 获取完整 MikanAPI（含 keymap/download 等子 API）

### 模拟器参数 schema 编写指南

在 engines.json 的引擎定义中添加 `param_schema` 数组：

```json
{
  "snes9x": {
    "param_schema": [
      {
        "key": "fullscreen",
        "label": "全屏",
        "type": "bool",
        "default": false,
        "args_template": "-fullscreen"
      },
      {
        "key": "frameskip",
        "label": "跳帧(0-9)",
        "type": "int",
        "default": 0,
        "min": 0,
        "max": 9,
        "args_template": "-frameskip {value}"
      },
      {
        "key": "sound_rate",
        "label": "采样率",
        "type": "choice",
        "default": "32000",
        "options": ["8000", "11025", "22050", "32000", "44100", "48000"],
        "args_template": "-soundrate {value}"
      }
    ]
  }
}
```

---

## 许可证

```
MikanEmu - 模拟器前端管理工具
Copyright (C) 2024-2025 mikan_emu contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```

**法律声明**：本项目不提供任何 BIOS、ROM 或模拟器二进制文件。用户需自行准备合法获取的模拟器文件和 BIOS 文件。本项目仅作为前端管理工具存在。

---

## 项目地址

[https://github.com/luohaocheng171/mikan_emu](https://github.com/luohaocheng171/mikan_emu)

---

## 致谢

- **DeepSeek** — AI 辅助开发工具
- **PySide6 / Qt6** — 跨平台 GUI 框架
- **QEMU** — 开源虚拟机监控器
- **PCSX2** — PS2 模拟器
- **DuckStation** — PS1 模拟器
- **Flycast** — Dreamcast 模拟器
- **RetroArch** — 多平台模拟器前端
- **Mednafen** — 多平台模拟器
- **Snes9x** — SFC 模拟器
- **mgba** — GBA 模拟器
- **bsnes** — SFC 高精度模拟器
- **Ymir** — SS 模拟器
- **brimir** — SS libretro 核心
- **Deecy** — DC 实验性模拟器
- **DreamPotato** — VMU 模拟器
- **visualboyadvance-m** — GBA 模拟器
- **ppsspp** — PSP 模拟器
- **RPCS3** — PS3 模拟器
- **yuzu** — 3DS/NX 模拟器
- **citra** — 3DS 模拟器
- **melonDS** — NDS 模拟器
- **FCEUX** — FC 模拟器
- **Nestopia** — FC 模拟器
- **Nintendulator** — FC 模拟器
- **BGB** — GB 模拟器
- **VBA-M** — GB/GBA 模拟器
- **ZSNES** — SFC 模拟器
- **mame** — 街机模拟器
- **OpenBOR** — 横版过关游戏引擎
- **DOSBox-X** — DOS 模拟器
- **PCem** — PC 模拟器
- **86Box** — PC 模拟器
- **VICE** — C64 模拟器
- **Hatari** — Atari ST 模拟器
- **Stella** — Atari 2600 模拟器
- **bsnes** — SFC 高精度模拟器
- **NooDS** — NDS 模拟器
- **Geargrafx** — GB 模拟器
- **Emulicious** — GBA 模拟器
- **Caprice32** — Amstrad CPC 模拟器
- **CPCSyntaxError** — Amstrad CPC 模拟器
- **1984** — Apple II 模拟器
- **b2** — BBC Micro 模拟器
- **ZEsarUX** — ZX Spectrum 模拟器
- **Gearcoleco** — ColecoVision 模拟器
- **jzIntv** — Intellivision 模拟器
- **redream** — Dreamcast 模拟器
- **flycast** — Dreamcast 模拟器
- **PCSX2** — PS2 模拟器
- **rpcs3** — PS3 模拟器
- **yuzu** — 3DS/NX 模拟器
- **citra** — 3DS 模拟器
- **melonDS** — NDS 模拟器
- **loguru** — 日志库
- **py7zr** — 7z 处理库
- **rarfile** — RAR 处理库
- **psutil** — 系统监控库
- **requests** — HTTP 库
- **packaging** — 版本解析库
- **keyboard** — 键盘钩子库（可选）
- **PySocks** — SOCKS5 代理库（可选）
