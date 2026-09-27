# -*- coding: utf-8 -*-
"""
mikan_emu v0.8
模拟器前端 + 配置管家 + 版本识别器
Python 3.11+ / PySide6 / requests / loguru / py7zr / rarfile / psutil

【法律】不提供 BIOS、不提供 ROM、不二次分发模拟器

v0.8 变更：
- ★ 修复 .cue 被 MIN_ROM_SIZE 过滤的问题
- ★ 新增 .cue 自动生成（.bin 无 .cue 时）
- ★ 新增自定义镜像站（设置页可增删/排序/测试）
- ★ 镜像配置存 config/mirrors.json
"""

# ============================================================
# 0. 代理 + 环境变量
# ============================================================
import os
PROXY_URL = ""
if PROXY_URL:
    os.environ["HTTP_PROXY"] = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL
    os.environ["ALL_PROXY"] = PROXY_URL

os.environ["MEDNAFEN_ALLOWMULTI"] = "1"

# ============================================================
# 1. 依赖自检与自动安装
# ============================================================
import sys
import subprocess
import importlib

REQUIRED = {
    "PySide6": "PySide6",
    "requests": "requests",
    "loguru": "loguru",
    "py7zr": "py7zr",
    "rarfile": "rarfile",
    "certifi": "certifi",
    "psutil": "psutil",
}

MIRRORS = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.org/simple",
]


def _ensure_deps():
    missing = []
    for mod, pkg in REQUIRED.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return
    print(f"[启动] 检测到缺失依赖: {missing}，正在安装...")
    for pkg in missing:
        ok = False
        for m in MIRRORS:
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install",
                    pkg, "-i", m, "--quiet"
                ])
                ok = True
                break
            except subprocess.CalledProcessError:
                continue
        if not ok:
            print(f"[启动] 安装 {pkg} 失败，请手动安装后重试。")
            sys.exit(1)
    print("[启动] 依赖安装完成。")


_ensure_deps()

# ============================================================
# 2. 导入
# ============================================================
import ctypes
import hashlib
import json
import re
import shutil
import subprocess as sp
import tarfile
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Any

import requests
import urllib3
from loguru import logger

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from PySide6.QtCore import (
    Qt, QThread, Signal, QModelIndex, QAbstractTableModel,
    QSortFilterProxyModel, QTimer, QSize
)
from PySide6.QtGui import QColor, QFont, QAction, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QStackedWidget, QLabel,
    QLineEdit, QPushButton, QTableView, QHeaderView, QComboBox,
    QStatusBar, QMessageBox, QFrame, QFileDialog, QGridLayout,
    QProgressBar, QGroupBox, QFormLayout, QCheckBox, QTextEdit,
    QDialog, QDialogButtonBox, QMenu, QToolButton, QTabWidget,
    QScrollArea, QInputDialog, QAbstractItemView, QSpinBox,
    QListView, QRadioButton, QButtonGroup
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# 3. 路径 & 常量
# ============================================================
APP_NAME = "mikan_emu"
APP_VERSION = "0.8"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / APP_NAME
CONFIG_DIR = DATA_DIR / "config"
ENGINE_DIR = DATA_DIR / "engines"
ENGINE_DOWNLOAD_DIR = ENGINE_DIR / "downloaded"
BIOS_DIR = DATA_DIR / "bios"
ROM_DIR = DATA_DIR / "roms"
SAVE_DIR = DATA_DIR / "saves"
SAVE_BACKUP_DIR = DATA_DIR / "saves_backup"
COVER_DIR = DATA_DIR / "covers"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
TEMP_DIR = DATA_DIR / "temp"

for d in (DATA_DIR, CONFIG_DIR, ENGINE_DIR, ENGINE_DOWNLOAD_DIR,
          BIOS_DIR, ROM_DIR, SAVE_DIR, SAVE_BACKUP_DIR, COVER_DIR,
          BACKUP_DIR, LOG_DIR, TEMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

FOLDERS_FILE = CONFIG_DIR / "folders.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
LANG_FILE = CONFIG_DIR / "lang.json"
SAVE_PATHS_FILE = CONFIG_DIR / "save_paths.json"
MIRRORS_FILE = CONFIG_DIR / "mirrors.json"
ENGINES_JSON = ENGINE_DIR / "engines.json"
INSTALLED_FILE = ENGINE_DIR / "installed.json"
ROMS_FILE = ROM_DIR / "roms.json"

logger.remove()
logger.add(
    LOG_DIR / "mikan_emu_{time:YYYY-MM-DD}.log",
    rotation="10 MB", retention="14 days",
    encoding="utf-8", level="DEBUG",
)
logger.add(sys.stderr, level="INFO")

if PROXY_URL:
    logger.info(f"已启用代理: {PROXY_URL}")

# ============================================================
# 4. 多语言
# ============================================================
I18N = {
    "zh": {
        "app_title": "mikan_emu",
        "nav_library": "游戏库",
        "nav_engines": "模拟器",
        "nav_bios": "BIOS",
        "nav_settings": "设置",
        "toolbar_import_engine": "导入模拟器",
        "toolbar_download_engine": "下载模拟器",
        "toolbar_import_game": "导入游戏",
        "toolbar_refresh": "刷新",
        "toolbar_open_roms": "打开游戏文件夹",
        "library_title": "游戏库",
        "library_search_ph": "搜索游戏名...",
        "library_platform_all": "全部平台",
        "library_count": "共 {n} 个游戏",
        "library_empty": "还没有游戏。点顶部「导入游戏」或把 ROM 放进 roms/ 文件夹。",
        "library_col_name": "游戏名",
        "library_col_platform": "平台",
        "library_col_size": "大小",
        "library_col_path": "路径",
        "library_filter_all": "全部",
        "library_filter_fav": "收藏",
        "library_filter_recent": "最近",
        "library_sort_name": "名称",
        "library_sort_recent": "最近玩过",
        "library_sort_playtime": "时长",
        "library_no_cover": "无封面",
        "library_launch_btn": "▶ 启动",
        "library_select_hint": "请先选中一个游戏",
        "engines_title": "已安装的模拟器",
        "engines_empty": "还没有模拟器。点「导入模拟器」或「下载模拟器」。",
        "engines_col_platform": "平台",
        "engines_col_engine": "内核",
        "engines_col_path": "路径",
        "engines_col_source": "来源",
        "bios_title": "BIOS / 固件",
        "bios_hint": "把 BIOS 文件放到 bios/ 目录，点刷新扫描。",
        "bios_empty": "bios/ 目录为空。",
        "bios_col_file": "文件",
        "bios_col_size": "大小",
        "bios_col_md5": "MD5",
        "bios_col_known": "识别",
        "settings_title": "设置",
        "settings_lang": "语言",
        "settings_lang_hint": "切换后需重启生效",
        "settings_workspace": "工作区",
        "settings_workspace_desc": "ROM / BIOS / 存档的根目录",
        "settings_open_data": "打开数据目录",
        "settings_open_log": "打开日志目录",
        "settings_admin": "管理员权限",
        "settings_relaunch": "以管理员重启",
        "settings_download": "下载设置",
        "settings_threads": "下载线程数",
        "settings_threads_hint": "4~16，默认 8。",
        "settings_mirrors": "GitHub 镜像站",
        "settings_mirrors_hint": "按顺序尝试，第一个成功的用。空行 = 直连。末尾带 /",
        "settings_mirrors_add": "添加",
        "settings_mirrors_del": "删除",
        "settings_mirrors_up": "上移",
        "settings_mirrors_down": "下移",
        "settings_mirrors_test": "测试全部",
        "settings_mirrors_reset": "恢复默认",
        "settings_mirrors_enable": "启用镜像加速（针对 GitHub）",
        "settings_mirrors_testing": "测试中...",
        "settings_mirrors_result": "结果：{ok} 成功 / {fail} 失败",
        "settings_saves": "存档路径配置",
        "settings_saves_hint": "为每个模拟器指定存档目录。留空 = 不管理。",
        "settings_saves_auto": "自动扫描常见路径",
        "settings_saves_save": "保存",
        "settings_saves_backup": "备份所有存档",
        "settings_saves_restore": "还原存档",
        "settings_saves_open": "打开备份目录",
        "import_engine_title": "导入模拟器",
        "import_game_title": "导入游戏",
        "import_pick_archive": "选择压缩包",
        "import_pick_folder": "选择文件夹",
        "import_start": "开始导入",
        "import_scanning": "正在扫描...",
        "import_extracting": "正在解压...",
        "import_matching": "正在匹配...",
        "import_copying": "正在复制...",
        "import_found": "识别到 {n} 个",
        "import_not_found": "没识别出来，请手动指定",
        "import_success": "已导入: {name}",
        "import_failed": "导入失败: {err}",
        "import_done": "导入完成",
        "ctx_launch": "▶ 启动游戏",
        "ctx_config": "⚙️ 配置启动方式…",
        "ctx_open_folder": "打开所在文件夹",
        "ctx_remove": "从库中移除",
        "ctx_remove_confirm": "从库中移除「{name}」？（不会删除文件）",
        "ctx_fav_add": "加入收藏",
        "ctx_fav_remove": "取消收藏",
        "ctx_set_cover": "设置封面…",
        "ctx_open_save": "打开存档目录",
        "config_title": "配置启动方式",
        "config_game": "游戏",
        "config_current_platform": "当前平台",
        "config_engine_group": "使用模拟器",
        "config_auto": "自动（按平台匹配）",
        "config_manual": "手动指定",
        "config_engine": "模拟器",
        "config_platform_override": "覆盖平台（可选）",
        "config_platform_override_hint": "如果自动匹配的平台不对，在这里指定正确的",
        "config_platform_none": "不覆盖",
        "config_extra_args": "附加启动参数（可选）",
        "config_extra_args_ph": "例如: --fullscreen",
        "config_save": "保存",
        "config_cancel": "取消",
        "config_saved": "已保存",
        "config_no_engine": "没有可用的模拟器，请先下载/导入",
        "launch_no_engine": "没有可用于 {platform} 的模拟器。请先导入模拟器，或用「⚙️ 配置启动方式」手动指定。",
        "launch_select_engine": "选择用于启动的模拟器:",
        "launch_failed": "启动失败: {err}",
        "launch_ok": "已启动: {name}",
        "launch_cue_hint": "已自动改用 .cue",
        "rom_import_no_rom": "没识别出 ROM 文件",
        "rom_import_done": "导入 {n} 个游戏",
        "rom_import_skipped": "跳过 {n} 个（平台未知）",
        "download_title": "下载模拟器",
        "download_tab_auto": "可自动下载",
        "download_tab_manual": "需手动下载",
        "download_start": "下载",
        "download_open_site": "打开官网",
        "download_progress": "下载中...",
        "download_done": "下载完成",
        "download_failed": "下载失败: {err}",
        "download_extract": "正在解压...",
        "download_no_auto": "当前没有可自动下载的模拟器",
        "download_manual_hint": "以下模拟器为闭源或来源不明，请前往官网手动下载。",
        "download_confirm": "下载 {name}？",
        "download_speed": "{speed}/s  剩余 {eta}",
        "download_trying_mirror": "尝试镜像: {url}",
        "lang_changed_msg": "语言已切换为「{lang}」。重启后完整生效。",
        "save_backup_done": "存档已备份到: {path}",
        "save_backup_failed": "存档备份失败: {err}",
        "save_restore_confirm": "从备份还原 {name}？",
        "save_restore_done": "存档已还原: {name}",
        "save_none": "没有配置任何存档路径。",
        "msg_ok": "确定",
        "msg_cancel": "取消",
        "msg_warning": "警告",
        "msg_error": "错误",
        "msg_info": "提示",
        "msg_confirm": "确认",
    },
    "en": {
        "app_title": "mikan_emu",
        "nav_library": "Library",
        "nav_engines": "Emulators",
        "nav_bios": "BIOS",
        "nav_settings": "Settings",
        "toolbar_import_engine": "Import Engine",
        "toolbar_download_engine": "Download Engine",
        "toolbar_import_game": "Import Game",
        "toolbar_refresh": "Refresh",
        "toolbar_open_roms": "Open ROMs",
        "library_title": "Library",
        "library_search_ph": "Search game...",
        "library_platform_all": "All Platforms",
        "library_count": "{n} game(s)",
        "library_empty": "No games yet.",
        "library_col_name": "Name",
        "library_col_platform": "Platform",
        "library_col_size": "Size",
        "library_col_path": "Path",
        "library_filter_all": "All",
        "library_filter_fav": "Fav",
        "library_filter_recent": "Recent",
        "library_sort_name": "Name",
        "library_sort_recent": "Recent",
        "library_sort_playtime": "Playtime",
        "library_no_cover": "No cover",
        "library_launch_btn": "▶ Launch",
        "library_select_hint": "Please select a game",
        "engines_title": "Installed Emulators",
        "engines_empty": "No emulators yet.",
        "engines_col_platform": "Platform",
        "engines_col_engine": "Engine",
        "engines_col_path": "Path",
        "engines_col_source": "Source",
        "bios_title": "BIOS / Firmware",
        "bios_hint": "Put BIOS files into bios/ folder.",
        "bios_empty": "bios/ folder is empty.",
        "bios_col_file": "File",
        "bios_col_size": "Size",
        "bios_col_md5": "MD5",
        "bios_col_known": "Known",
        "settings_title": "Settings",
        "settings_lang": "Language",
        "settings_lang_hint": "Restart required",
        "settings_workspace": "Workspace",
        "settings_workspace_desc": "Root for ROM / BIOS / Saves",
        "settings_open_data": "Open Data Dir",
        "settings_open_log": "Open Log Dir",
        "settings_admin": "Admin Rights",
        "settings_relaunch": "Relaunch as Admin",
        "settings_download": "Download",
        "settings_threads": "Threads",
        "settings_threads_hint": "4~16, default 8.",
        "settings_mirrors": "GitHub Mirrors",
        "settings_mirrors_hint": "Tried in order. Empty line = direct. End with /",
        "settings_mirrors_add": "Add",
        "settings_mirrors_del": "Delete",
        "settings_mirrors_up": "Up",
        "settings_mirrors_down": "Down",
        "settings_mirrors_test": "Test All",
        "settings_mirrors_reset": "Reset",
        "settings_mirrors_enable": "Enable mirror acceleration (GitHub)",
        "settings_mirrors_testing": "Testing...",
        "settings_mirrors_result": "Result: {ok} OK / {fail} failed",
        "settings_saves": "Save Paths",
        "settings_saves_hint": "Set save directory for each emulator.",
        "settings_saves_auto": "Auto-detect",
        "settings_saves_save": "Save",
        "settings_saves_backup": "Backup All Saves",
        "settings_saves_restore": "Restore Saves",
        "settings_saves_open": "Open Backup Dir",
        "import_engine_title": "Import Emulator",
        "import_game_title": "Import Game",
        "import_pick_archive": "Pick Archive",
        "import_pick_folder": "Pick Folder",
        "import_start": "Start",
        "import_scanning": "Scanning...",
        "import_extracting": "Extracting...",
        "import_matching": "Matching...",
        "import_copying": "Copying...",
        "import_found": "Found {n}",
        "import_not_found": "Not recognized",
        "import_success": "Imported: {name}",
        "import_failed": "Failed: {err}",
        "import_done": "Done",
        "ctx_launch": "▶ Launch",
        "ctx_config": "⚙️ Configure Launch…",
        "ctx_open_folder": "Open Folder",
        "ctx_remove": "Remove from Library",
        "ctx_remove_confirm": "Remove '{name}'?",
        "ctx_fav_add": "Add to Favorites",
        "ctx_fav_remove": "Remove from Favorites",
        "ctx_set_cover": "Set Cover…",
        "ctx_open_save": "Open Save Dir",
        "config_title": "Configure Launch",
        "config_game": "Game",
        "config_current_platform": "Platform",
        "config_engine_group": "Emulator",
        "config_auto": "Auto",
        "config_manual": "Manual",
        "config_engine": "Emulator",
        "config_platform_override": "Override platform",
        "config_platform_override_hint": "If auto-matched is wrong",
        "config_platform_none": "No override",
        "config_extra_args": "Extra args",
        "config_extra_args_ph": "e.g. --fullscreen",
        "config_save": "Save",
        "config_cancel": "Cancel",
        "config_saved": "Saved",
        "config_no_engine": "No emulator available.",
        "launch_no_engine": "No emulator for {platform}.",
        "launch_select_engine": "Choose emulator:",
        "launch_failed": "Launch failed: {err}",
        "launch_ok": "Launched: {name}",
        "launch_cue_hint": "Auto-switched to .cue",
        "rom_import_no_rom": "No ROM recognized",
        "rom_import_done": "Imported {n}",
        "rom_import_skipped": "Skipped {n}",
        "download_title": "Download Emulator",
        "download_tab_auto": "Auto",
        "download_tab_manual": "Manual",
        "download_start": "Download",
        "download_open_site": "Open Site",
        "download_progress": "Downloading...",
        "download_done": "Done",
        "download_failed": "Failed: {err}",
        "download_extract": "Extracting...",
        "download_no_auto": "No auto-downloadable emulator",
        "download_manual_hint": "Closed-source. Please visit official sites.",
        "download_confirm": "Download {name}?",
        "download_speed": "{speed}/s  ETA {eta}",
        "download_trying_mirror": "Trying: {url}",
        "lang_changed_msg": "Language switched to '{lang}'. Restart to apply.",
        "save_backup_done": "Backed up to: {path}",
        "save_backup_failed": "Backup failed: {err}",
        "save_restore_confirm": "Restore {name}?",
        "save_restore_done": "Restored: {name}",
        "save_none": "No save path configured.",
        "msg_ok": "OK",
        "msg_cancel": "Cancel",
        "msg_warning": "Warning",
        "msg_error": "Error",
        "msg_info": "Info",
        "msg_confirm": "Confirm",
    },
}

CURRENT_LANG = "zh"


def tr(key: str, **kwargs) -> str:
    text = I18N.get(CURRENT_LANG, I18N["zh"]).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def save_lang(lang: str) -> bool:
    try:
        with open(LANG_FILE, "w", encoding="utf-8") as f:
            json.dump({"language": lang}, f, ensure_ascii=False, indent=2)
        logger.info(f"语言已保存: {lang}")
        return True
    except Exception as e:
        logger.exception(f"保存语言失败: {e}")
        return False


def load_lang():
    global CURRENT_LANG
    if LANG_FILE.exists():
        try:
            with open(LANG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            lang = data.get("language", "zh")
            if lang not in I18N:
                lang = "zh"
            CURRENT_LANG = lang
            logger.info(f"已加载语言: {CURRENT_LANG}")
            return
        except Exception as e:
            logger.exception(f"加载语言失败: {e}")
    CURRENT_LANG = "zh"
    save_lang("zh")


# ============================================================
# 5. 配置
# ============================================================
DEFAULT_WORKSPACE = str(DATA_DIR)
FOLDERS_CONFIG = {"folders": [], "active_index": 0}
SETTINGS = {"download_threads": 8}
SAVE_PATHS: dict[str, str] = {}

DEFAULT_MIRRORS = {
    "enabled": True,
    "mirrors": [
        "https://ghproxy.com/",
        "https://gh-proxy.com/",
        "https://github.moeyy.xyz/",
        "",
    ],
}
MIRRORS_CONFIG = json.loads(json.dumps(DEFAULT_MIRRORS))


def load_folders_config():
    global FOLDERS_CONFIG
    if FOLDERS_FILE.exists():
        try:
            with open(FOLDERS_FILE, "r", encoding="utf-8") as f:
                FOLDERS_CONFIG = json.load(f)
        except Exception:
            FOLDERS_CONFIG = {"folders": [], "active_index": 0}
    if not FOLDERS_CONFIG.get("folders"):
        FOLDERS_CONFIG = {
            "folders": [{"name": "默认工作区", "path": DEFAULT_WORKSPACE}],
            "active_index": 0,
        }


def save_folders_config():
    try:
        with open(FOLDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(FOLDERS_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_settings():
    global SETTINGS
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                SETTINGS.update(json.load(f))
        except Exception:
            pass


def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(SETTINGS, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_save_paths():
    global SAVE_PATHS
    if SAVE_PATHS_FILE.exists():
        try:
            with open(SAVE_PATHS_FILE, "r", encoding="utf-8") as f:
                SAVE_PATHS = json.load(f)
        except Exception:
            SAVE_PATHS = {}


def save_save_paths():
    try:
        with open(SAVE_PATHS_FILE, "w", encoding="utf-8") as f:
            json.dump(SAVE_PATHS, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_mirrors():
    global MIRRORS_CONFIG
    if MIRRORS_FILE.exists():
        try:
            with open(MIRRORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "mirrors" not in data:
                data["mirrors"] = list(DEFAULT_MIRRORS["mirrors"])
            if "enabled" not in data:
                data["enabled"] = True
            MIRRORS_CONFIG = data
        except Exception:
            MIRRORS_CONFIG = json.loads(json.dumps(DEFAULT_MIRRORS))


def save_mirrors():
    try:
        with open(MIRRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(MIRRORS_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_mirror_list() -> list:
    if not MIRRORS_CONFIG.get("enabled", True):
        return [""]
    mirrors = MIRRORS_CONFIG.get("mirrors", [])
    if not mirrors:
        return [""]
    return mirrors


def get_active_folder() -> dict:
    folders = FOLDERS_CONFIG.get("folders", [])
    idx = FOLDERS_CONFIG.get("active_index", 0)
    if folders and 0 <= idx < len(folders):
        return folders[idx]
    return {"name": "默认工作区", "path": DEFAULT_WORKSPACE}


load_folders_config()
load_settings()
load_save_paths()
load_mirrors()


def get_save_path(engine_name: str) -> Optional[Path]:
    p = SAVE_PATHS.get(engine_name, "").strip()
    if p:
        path = Path(p)
        if path.exists() and path.is_dir():
            return path
    return None


def autodetect_save_paths(engines_json: dict) -> dict:
    home = Path.home()
    docs = home / "Documents"
    appdata = Path(os.environ.get("APPDATA", ""))
    localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = {
        "snes9x": [docs / "Snes9x" / "Saves", DATA_DIR / "snes9x"],
        "duckstation": [docs / "DuckStation",
                        home / ".local/share/DuckStation",
                        localappdata / "DuckStation"],
        "mednafen": [home / ".mednafen" / "sav",
                     DATA_DIR / "mednafen" / "sav"],
        "mgba": [docs / "mGBA", DATA_DIR / "mgba"],
        "pcsx2": [docs / "PCSX2" / "memcards", home / ".config" / "PCSX2"],
        "ppsspp": [docs / "PPSSPP" / "PSP" / "SAVEDATA"],
        "desmume": [docs / "DeSmuME" / "Battery"],
        "melonds": [docs / "melonDS"],
        "ryujinx": [appdata / "Ryujinx" / "bis" / "user" / "save"],
        "fceux": [DATA_DIR / "fceux" / "fcs"],
        "mesen": [docs / "Mesen" / "saves"],
        "mupen64plus": [DATA_DIR / "mupen64plus" / "save"],
        "mame": [DATA_DIR / "mame" / "nvram"],
        "blastem": [DATA_DIR / "blastem"],
        "sameboy": [docs / "SameBoy"],
        "gambatte": [DATA_DIR / "gambatte"],
    }
    result = {}
    for engine_name, paths in candidates.items():
        for p in paths:
            if p.exists() and p.is_dir():
                result[engine_name] = str(p)
                break
    return result


# ============================================================
# 6. engines.json（内容同 v0.7，省略重复展示 —— 完整保留）
# ============================================================
DEFAULT_ENGINES = {
    "sfc": {
        "platform_name": "SFC / 超级任天堂",
        "rom_extensions": [".sfc", ".smc", ".fig", ".swc"],
        "engines": {
            "snes9x": {
                "version": "1.63",
                "url": "https://github.com/snes9xgit/snes9x/releases/download/1.63/snes9x-1.63-win32-x64.zip",
                "archive": "zip",
                "match": {"exe": ["snes9x-x64.exe", "snes9x.exe"],
                          "folder": ["snes9x"],
                          "keywords": ["snes9x", "snes"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "ps1": {
        "platform_name": "PS1 / PlayStation",
        "rom_extensions": [".bin", ".cue", ".iso", ".chd", ".pbp", ".img"],
        "engines": {
            "duckstation": {
                "version": "latest",
                "url": "https://github.com/stenzek/duckstation/releases/download/latest/duckstation-windows-x64-release.zip",
                "archive": "zip",
                "match": {"exe": ["duckstation-qt-x64-ReleaseLTCG.exe",
                                   "duckstation-qt-x64-Release.exe",
                                   "duckstation-qt-x64-Debug.exe",
                                   "duckstation.exe"],
                          "folder": ["duckstation"],
                          "keywords": ["duckstation"]},
                "launch_template": "{exe} -batch \"{rom}\"",
                "official": True,
            },
            "epsxe": {
                "version": "2.0.18",
                "url": "manual",
                "official_site": "https://www.epsxe.com/",
                "archive": "7z",
                "match": {"exe": ["ePSXe.exe"],
                          "folder": ["ePSXe", "epsxe"],
                          "keywords": ["epsxe"]},
                "launch_template": "{exe} -nogui -loadiso \"{rom}\"",
                "official": False,
                "note": "闭源，需手动下载",
            },
            "xebra": {
                "version": "221106",
                "url": "manual",
                "official_site": "http://drhell.web.fc2.com/ps1/",
                "archive": "zip",
                "match": {"exe": ["xebra.exe", "XEBRA.exe"],
                          "folder": ["xebra", "XEBRA"],
                          "keywords": ["xebra"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": False,
                "note": "闭源，需手动下载",
            },
        },
    },
    "ss": {
        "platform_name": "SS / 世嘉土星",
        "rom_extensions": [".bin", ".cue", ".iso", ".chd", ".mds", ".mdf"],
        "engines": {
            "mednafen": {
                "version": "1.32.1",
                "url": "https://mednafen.github.io/releases/files/mednafen-1.32.1-win64.zip",
                "archive": "zip",
                "match": {"exe": ["mednafen.exe"],
                          "folder": ["mednafen"],
                          "keywords": ["mednafen"]},
                "bios_required": True,
                "bios_files": ["mpr-17933.bin", "sega_101.bin"],
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
            "ssf": {
                "version": "PreviewVer R38",
                "url": "manual",
                "official_site": "http://redlotusflame.uupan.net/",
                "archive": "7z",
                "match": {"exe": ["SSF.exe", "SSF_PreviewVer.exe"],
                          "folder": ["SSF", "SSF_PreviewVer"],
                          "keywords": ["ssf"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": False,
                "note": "闭源，需手动下载",
            },
        },
    },
    "gba": {
        "platform_name": "GBA",
        "rom_extensions": [".gba", ".agb"],
        "engines": {
            "mgba": {
                "version": "0.10.5",
                "url": "https://github.com/mgba-emu/mgba/releases/download/0.10.5/mGBA-0.10.5-win64.7z",
                "archive": "7z",
                "match": {"exe": ["mGBA.exe", "mgba.exe", "mgba-qt.exe"],
                          "folder": ["mgba", "mGBA"],
                          "keywords": ["mgba"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "ps2": {
        "platform_name": "PS2 / PlayStation 2",
        "rom_extensions": [".iso", ".bin", ".cue", ".chd", ".gz"],
        "engines": {
            "pcsx2": {
                "version": "2.8.2",
                "url": "https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-windows-x64-Qt.7z",
                "archive": "7z",
                "match": {"exe": ["pcsx2-qt.exe", "pcsx2.exe"],
                          "folder": ["pcsx2"],
                          "keywords": ["pcsx2"]},
                "launch_template": "{exe} -batch \"{rom}\"",
                "official": True,
            },
        },
    },
    "fc": {
        "platform_name": "FC / NES",
        "rom_extensions": [".nes", ".fds", ".unf", ".unif"],
        "engines": {
            "fceux": {
                "version": "latest",
                "url": "https://sourceforge.net/projects/fceultra/files/latest/download",
                "archive": "zip",
                "match": {"exe": ["fceux.exe", "fceux64.exe"],
                          "folder": ["fceux"],
                          "keywords": ["fceux"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
            "mesence": {
                "version": "2.2.1",
                "url": "https://github.com/nesdev-org/MesenCE/releases/download/2.2.1/Mesen_2.2.1_Windows.zip",
                "archive": "zip",
                "match": {"exe": ["Mesen.exe"],
                          "folder": ["Mesen"],
                          "keywords": ["mesen"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "n64": {
        "platform_name": "N64",
        "rom_extensions": [".n64", ".z64", ".v64", ".rom"],
        "engines": {
            "mupen64plus": {
                "version": "2.6.0",
                "url": "https://github.com/mupen64plus/mupen64plus-core/releases/download/2.6.0/mupen64plus-bundle-win64-2.6.0.zip",
                "archive": "zip",
                "match": {"exe": ["mupen64plus-ui-console.exe", "mupen64plus.exe"],
                          "folder": ["mupen64plus"],
                          "keywords": ["mupen64plus", "mupen"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "nds": {
        "platform_name": "NDS",
        "rom_extensions": [".nds", ".dsi", ".ids"],
        "engines": {
            "desmume": {
                "version": "0.9.13",
                "url": "https://github.com/TASEmulators/desmume/releases/download/release_0_9_13/desmume-0.9.13-win64.zip",
                "archive": "zip",
                "match": {"exe": ["desmume.exe", "DeSmuME.exe"],
                          "folder": ["desmume", "DeSmuME"],
                          "keywords": ["desmume"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
            "melonds": {
                "version": "1.1",
                "url": "https://melonds.kuribo64.net/downloads/melonDS-1.1-windows-x86_64.zip",
                "archive": "zip",
                "match": {"exe": ["melonDS.exe", "melonds.exe"],
                          "folder": ["melonDS", "melonds"],
                          "keywords": ["melonds"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "md": {
        "platform_name": "MD / Genesis",
        "rom_extensions": [".md", ".gen", ".smd", ".bin", ".32x"],
        "engines": {
            "blastem": {
                "version": "1.0.0",
                "url": "https://www.retrodev.com/blastem/blastem-win64-1.0.0.zip",
                "archive": "zip",
                "match": {"exe": ["blastem.exe"],
                          "folder": ["blastem"],
                          "keywords": ["blastem"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
            "kega-fusion": {
                "version": "3.64",
                "url": "manual",
                "official_site": "https://kega-fusion.com/",
                "archive": "zip",
                "match": {"exe": ["Fusion.exe", "Kega Fusion.exe"],
                          "folder": ["Kega Fusion", "Fusion"],
                          "keywords": ["fusion", "kega"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": False,
                "note": "闭源，需手动下载",
            },
        },
    },
    "gb": {
        "platform_name": "GB / GBC",
        "rom_extensions": [".gb", ".gbc", ".sgb"],
        "engines": {
            "sameboy": {
                "version": "1.0.3",
                "url": "manual",
                "official_site": "https://github.com/LIJI32/SameBoy/releases",
                "archive": "zip",
                "match": {"exe": ["sameboy.exe", "SameBoy.exe"],
                          "folder": ["sameboy", "SameBoy"],
                          "keywords": ["sameboy"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
                "note": "挂官网，用户手动下载",
            },
            "gambatte": {
                "version": "0.5.0",
                "url": "manual",
                "official_site": "https://github.com/sinamas/gambatte",
                "archive": "zip",
                "match": {"exe": ["gambatte_qt.exe", "gambatte_sdl.exe", "gambatte.exe"],
                          "folder": ["gambatte", "Gambatte"],
                          "keywords": ["gambatte"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": False,
                "note": "已停更，需手动下载。建议改用 mGBA",
            },
        },
    },
    "psp": {
        "platform_name": "PSP",
        "rom_extensions": [".iso", ".cso", ".pbp"],
        "engines": {
            "ppsspp": {
                "version": "1.20.4",
                "url": "https://github.com/hrydgard/ppsspp/releases/download/v1.20.4/PPSSPP-v1.20.4-Windows-x64.zip",
                "archive": "zip",
                "match": {"exe": ["PPSSPPWindows64.exe", "PPSSPPWindows.exe", "PPSSPP.exe"],
                          "folder": ["PPSSPP", "ppsspp"],
                          "keywords": ["ppsspp"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "switch": {
        "platform_name": "Switch",
        "rom_extensions": [".nsp", ".xci", ".nsz", ".xcz"],
        "engines": {
            "ryujinx": {
                "version": "1.3.3",
                "url": "https://git.ryujinx.app/projects/Ryubing/releases/download/1.3.3/ryujinx-1.3.3-win_x64.zip",
                "archive": "zip",
                "match": {"exe": ["Ryujinx.exe", "ryujinx.exe"],
                          "folder": ["Ryujinx", "ryujinx", "publish"],
                          "keywords": ["ryujinx"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
            "yuzu": {
                "version": "unknown",
                "url": "manual",
                "official_site": "https://github.com/yuzu-mirror",
                "archive": "zip",
                "match": {"exe": ["yuzu.exe", "yuzu-cmd.exe"],
                          "folder": ["yuzu", "Yuzu"],
                          "keywords": ["yuzu"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": False,
                "note": "已停止分发，只剩社区镜像",
            },
        },
    },
    "pce": {
        "platform_name": "PCE / TurboGrafx",
        "rom_extensions": [".pce", ".sgx"],
        "engines": {
            "mednafen": {
                "version": "1.32.1",
                "url": "https://mednafen.github.io/releases/files/mednafen-1.32.1-win64.zip",
                "archive": "zip",
                "match": {"exe": ["mednafen.exe"],
                          "folder": ["mednafen"],
                          "keywords": ["mednafen"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "neogeo": {
        "platform_name": "Neo Geo",
        "rom_extensions": [".zip", ".neo"],
        "engines": {
            "mame": {
                "version": "0.289",
                "url": "https://github.com/mamedev/mame/releases/download/mame0289/mame0289b_x64.exe",
                "archive": "7z_sfx",
                "match": {"exe": ["mame.exe", "mame64.exe"],
                          "folder": ["mame", "MAME"],
                          "keywords": ["mame"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
    "arcade": {
        "platform_name": "Arcade",
        "rom_extensions": [".zip", ".7z"],
        "engines": {
            "mame": {
                "version": "0.289",
                "url": "https://github.com/mamedev/mame/releases/download/mame0289/mame0289b_x64.exe",
                "archive": "7z_sfx",
                "match": {"exe": ["mame.exe", "mame64.exe"],
                          "folder": ["mame", "MAME"],
                          "keywords": ["mame"]},
                "launch_template": "{exe} \"{rom}\"",
                "official": True,
            },
        },
    },
}

PLATFORM_LABELS = {
    "sfc": "SFC / 超级任天堂",
    "ss": "SS / 世嘉土星",
    "ps1": "PS1 / PlayStation",
    "ps2": "PS2 / PlayStation 2",
    "fc": "FC / NES",
    "n64": "N64",
    "gba": "GBA",
    "nds": "NDS",
    "md": "MD / Genesis",
    "gb": "GB / GBC",
    "psp": "PSP",
    "switch": "Switch",
    "pce": "PCE / TurboGrafx",
    "neogeo": "Neo Geo",
    "arcade": "Arcade",
}


def _migrate_engines_structure(data: dict) -> dict:
    new_data = {}
    for platform, pcfg in data.items():
        if isinstance(pcfg, dict) and "engines" in pcfg and isinstance(pcfg["engines"], dict):
            new_data[platform] = pcfg
        else:
            new_data[platform] = {
                "platform_name": PLATFORM_LABELS.get(platform, platform),
                "rom_extensions": DEFAULT_ENGINES.get(platform, {}).get("rom_extensions", []),
                "engines": pcfg if isinstance(pcfg, dict) else {},
            }
    for platform, pcfg in DEFAULT_ENGINES.items():
        if platform not in new_data:
            new_data[platform] = pcfg
        else:
            new_data[platform].setdefault("platform_name", pcfg.get("platform_name", platform))
            new_data[platform].setdefault("rom_extensions", pcfg.get("rom_extensions", []))
            engines = new_data[platform].setdefault("engines", {})
            for eng_name, eng_cfg in pcfg.get("engines", {}).items():
                engines.setdefault(eng_name, eng_cfg)
    return new_data


def load_engines_json() -> dict:
    if not ENGINES_JSON.exists():
        with open(ENGINES_JSON, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_ENGINES, f, indent=2, ensure_ascii=False)
        return json.loads(json.dumps(DEFAULT_ENGINES))
    try:
        with open(ENGINES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        migrated = _migrate_engines_structure(data)
        if migrated != data:
            with open(ENGINES_JSON, "w", encoding="utf-8") as f:
                json.dump(migrated, f, indent=2, ensure_ascii=False)
        return migrated
    except Exception as e:
        logger.exception(f"读取 engines.json 失败: {e}")
        return json.loads(json.dumps(DEFAULT_ENGINES))


def save_engines_json(data: dict):
    try:
        with open(ENGINES_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_all_platform_rom_extensions(engines_json: dict) -> dict:
    result = {}
    for platform, pcfg in engines_json.items():
        for ext in pcfg.get("rom_extensions", []):
            result.setdefault(ext.lower(), []).append(platform)
    return result


# ============================================================
# 7. 数据结构
# ============================================================
@dataclass
class EmulatorConfig:
    platform: str
    engine: str
    platform_name: str = ""
    engine_path: str = ""
    engine_dir: str = ""
    version: str = ""
    official: bool = False
    source: str = "import"
    bios_required: bool = False
    bios_files: list = field(default_factory=list)
    launch_template: str = "{exe} \"{rom}\""
    installed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EmulatorConfig":
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


@dataclass
class GameEntry:
    name: str
    path: str
    platform: str
    size: int = 0
    added_at: str = ""
    favorite: bool = False
    last_played: str = ""
    play_seconds: int = 0
    override_platform: str = ""
    override_engine: str = ""
    extra_args: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GameEntry":
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


def load_installed() -> list[EmulatorConfig]:
    if not INSTALLED_FILE.exists():
        return []
    try:
        with open(INSTALLED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [EmulatorConfig.from_dict(x) for x in data.get("engines", [])]
    except Exception:
        return []


def save_installed(engines: list[EmulatorConfig]):
    try:
        with open(INSTALLED_FILE, "w", encoding="utf-8") as f:
            json.dump({"engines": [e.to_dict() for e in engines]},
                      f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_games() -> list[GameEntry]:
    if not ROMS_FILE.exists():
        return []
    try:
        with open(ROMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [GameEntry.from_dict(x) for x in data.get("games", [])]
    except Exception:
        return []


def save_games(games: list[GameEntry]):
    try:
        with open(ROMS_FILE, "w", encoding="utf-8") as f:
            json.dump({"games": [g.to_dict() for g in games]},
                      f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ============================================================
# 8. 工具（★ 修复 .cue）
# ============================================================
ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}


def extract_archive(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest)
    elif name.endswith(".7z"):
        import py7zr
        with py7zr.SevenZipFile(archive, mode="r") as z:
            z.extractall(dest)
    elif name.endswith(".rar"):
        import rarfile
        with rarfile.RarFile(archive) as rf:
            rf.extractall(dest)
    elif any(name.endswith(x) for x in (".tar", ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz")):
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(dest)
    else:
        raise ValueError(f"不支持的压缩格式: {archive.name}")


def scan_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


def md5_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def human_size(n: int) -> str:
    if n <= 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def format_size(size: int) -> str:
    return human_size(size)


def human_eta(seconds: float) -> str:
    if seconds <= 0 or seconds > 86400:
        return "?"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h{m}m"
    if m > 0:
        return f"{m}m{s}s"
    return f"{s}s"


def human_duration(seconds: int) -> str:
    if seconds <= 0:
        return "-"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def resolve_rom_for_launch(path_str: str) -> tuple[str, bool]:
    """
    ★ v0.8 修复：
    1. 如果 ROM 是 .bin/.iso/.img，同目录有同名 .cue → 用 .cue
    2. 如果没有 .cue 且是 .bin → 自动生成一个（Mednafen 需要）
    返回: (最终路径, 是否发生了切换)
    """
    p = Path(path_str)
    if p.suffix.lower() not in (".bin", ".iso", ".img"):
        return path_str, False

    # 1. 找同名 .cue
    cue = p.with_suffix(".cue")
    if cue.exists():
        return str(cue), True
    try:
        for f in p.parent.iterdir():
            if (f.is_file() and f.stem.lower() == p.stem.lower()
                    and f.suffix.lower() == ".cue"):
                return str(f), True
    except Exception:
        pass

    # 2. 没有 .cue → 为 .bin 自动生成
    if p.suffix.lower() == ".bin":
        try:
            with open(cue, "w", encoding="utf-8") as f:
                f.write(f'FILE "{p.name}" BINARY\n')
                f.write("  TRACK 01 MODE1/2352\n")
                f.write("    INDEX 01 00:00:00\n")
            logger.info(f"自动生成 .cue: {cue}")
            return str(cue), True
        except Exception as e:
            logger.exception(f"生成 .cue 失败: {e}")

    return path_str, False


# ============================================================
# 9. 模拟器匹配 / 安装
# ============================================================
def match_engines(files: list[Path], engines_json: dict) -> list[dict]:
    results = []
    seen = set()
    for platform, pcfg in engines_json.items():
        engines = pcfg.get("engines", {})
        for engine_name, cfg in engines.items():
            match = cfg.get("match", {})
            exe_names = [n.lower() for n in match.get("exe", [])]
            folder_names = [n.lower() for n in match.get("folder", [])]
            keywords = [k.lower() for k in match.get("keywords", [])]
            for f in files:
                fname = f.name.lower()
                if fname in exe_names:
                    key = (platform, engine_name, str(f))
                    if key not in seen:
                        seen.add(key)
                        results.append({"platform": platform, "engine": engine_name,
                                        "exe": f, "cfg": cfg, "match_type": "exe"})
                    continue
                parent_name = f.parent.name.lower()
                if parent_name in folder_names and f.suffix.lower() == ".exe":
                    key = (platform, engine_name, str(f))
                    if key not in seen:
                        seen.add(key)
                        results.append({"platform": platform, "engine": engine_name,
                                        "exe": f, "cfg": cfg, "match_type": "folder"})
                    continue
                if f.suffix.lower() == ".exe" and keywords:
                    for kw in keywords:
                        if kw in fname:
                            key = (platform, engine_name, str(f))
                            if key not in seen:
                                seen.add(key)
                                results.append({"platform": platform, "engine": engine_name,
                                                "exe": f, "cfg": cfg, "match_type": "keyword"})
                            break
    return results


def install_engine_from_match(match: dict, source_root: Path,
                              source_label: str = "import") -> EmulatorConfig:
    platform = match["platform"]
    engine = match["engine"]
    cfg = match["cfg"]
    exe_path: Path = match["exe"]
    target_dir = ENGINE_DOWNLOAD_DIR / platform / engine
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        exe_rel = exe_path.relative_to(source_root)
    except ValueError:
        source_root = exe_path.parent
        exe_rel = Path(exe_path.name)

    copied = 0
    for item in source_root.rglob("*"):
        if not item.is_file():
            continue
        try:
            rel = item.relative_to(source_root)
            dst = target_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)
            copied += 1
        except Exception as e:
            logger.exception(f"复制 {item} 失败: {e}")
    logger.info(f"已复制 {copied} 个文件到 {target_dir}")

    target_exe = target_dir / exe_rel

    return EmulatorConfig(
        platform=platform, engine=engine,
        platform_name=cfg.get("platform_name", PLATFORM_LABELS.get(platform, platform)),
        engine_path=str(target_exe), engine_dir=str(target_dir),
        version=cfg.get("version", ""), official=cfg.get("official", False),
        source=source_label,
        bios_required=cfg.get("bios_required", False),
        bios_files=cfg.get("bios_files", []),
        launch_template=cfg.get("launch_template", "{exe} \"{rom}\""),
        installed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


# ============================================================
# 10. Worker: 导入模拟器
# ============================================================
class EngineImportWorker(QThread):
    progress = Signal(str)
    done = Signal(list, list)
    fail = Signal(str)

    def __init__(self, source: Path, engines_json: dict, is_archive: bool):
        super().__init__()
        self._source = source
        self._engines_json = engines_json
        self._is_archive = is_archive

    def run(self):
        temp_root = None
        try:
            if self._is_archive:
                self.progress.emit(tr("import_extracting"))
                temp_root = Path(tempfile.mkdtemp(prefix="mikan_emu_", dir=str(TEMP_DIR)))
                extract_archive(self._source, temp_root)
                scan_root = temp_root
            else:
                scan_root = self._source
            self.progress.emit(tr("import_scanning"))
            files = scan_files(scan_root)
            self.progress.emit(tr("import_matching"))
            matches = match_engines(files, self._engines_json)
            installed = []
            for m in matches:
                try:
                    cfg = install_engine_from_match(m, scan_root, "import")
                    installed.append(cfg)
                except Exception as e:
                    logger.exception(f"安装 {m['engine']} 失败: {e}")
            matched_paths = {str(m["exe"]) for m in matches}
            unmatched = []
            for f in files:
                if str(f) in matched_paths:
                    continue
                if f.suffix.lower() == ".exe":
                    try:
                        top = f.relative_to(scan_root).parts[0]
                    except ValueError:
                        top = f.name
                    if top not in unmatched:
                        unmatched.append(top)
            self.done.emit(installed, unmatched)
        except Exception as e:
            logger.exception("导入模拟器失败")
            self.fail.emit(str(e))
        finally:
            if temp_root and temp_root.exists():
                shutil.rmtree(temp_root, ignore_errors=True)


# ============================================================
# 11. 游戏扫描 / 导入（★ 不过滤 .cue）
# ============================================================
def guess_platform_by_ext(path: Path, engines_json: dict) -> Optional[str]:
    ext = path.suffix.lower()
    ext_map = get_all_platform_rom_extensions(engines_json)
    platforms = ext_map.get(ext)
    if not platforms:
        return None
    if len(platforms) == 1:
        return platforms[0]
    p = str(path).lower()
    for platform in platforms:
        label = PLATFORM_LABELS.get(platform, platform).lower()
        key = platform.lower()
        if key in p or label.split("/")[0].strip() in p:
            return platform
    return platforms[0]


def clean_game_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or path.stem


MIN_ROM_SIZE = 1024


def import_games_scan(files: list[Path], engines_json: dict) -> tuple[list[GameEntry], list[Path]]:
    games = []
    unknown = []
    seen_paths = set()
    for f in files:
        if f.suffix.lower() in ARCHIVE_EXTS:
            continue
        if not f.is_file():
            continue
        try:
            size = f.stat().st_size
        except Exception:
            continue
        # ★ 修复：.cue 不过滤（它通常只有 100~300 字节）
        if size < MIN_ROM_SIZE and f.suffix.lower() != ".cue":
            continue
        platform = guess_platform_by_ext(f, engines_json)
        if not platform:
            unknown.append(f)
            continue
        if str(f) in seen_paths:
            continue
        seen_paths.add(str(f))
        games.append(GameEntry(
            name=clean_game_name(f), path=str(f), platform=platform,
            size=size, added_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    return games, unknown


class GameImportWorker(QThread):
    progress = Signal(str)
    done = Signal(list, int)
    fail = Signal(str)

    def __init__(self, source: Path, engines_json: dict, is_archive: bool):
        super().__init__()
        self._source = source
        self._engines_json = engines_json
        self._is_archive = is_archive

    def run(self):
        temp_root = None
        try:
            if self._is_archive:
                self.progress.emit(tr("import_extracting"))
                temp_root = Path(tempfile.mkdtemp(prefix="mikan_emu_rom_", dir=str(TEMP_DIR)))
                extract_archive(self._source, temp_root)
                scan_root = temp_root
            else:
                scan_root = self._source
            self.progress.emit(tr("import_scanning"))
            files = scan_files(scan_root)
            self.progress.emit(tr("import_matching"))
            games_raw, unknown = import_games_scan(files, self._engines_json)
            if not games_raw:
                self.fail.emit(tr("rom_import_no_rom"))
                return
            self.progress.emit(tr("import_copying"))
            final_games = []
            for g in games_raw:
                src = Path(g.path)
                platform_dir = ROM_DIR / g.platform
                platform_dir.mkdir(parents=True, exist_ok=True)
                dst = platform_dir / src.name
                if dst.exists():
                    base = dst.stem
                    suffix = dst.suffix
                    idx = 2
                    while dst.exists():
                        dst = platform_dir / f"{base}_{idx}{suffix}"
                        idx += 1
                try:
                    shutil.copy2(src, dst)
                    g.path = str(dst)
                    g.size = dst.stat().st_size
                    final_games.append(g)
                except Exception as e:
                    logger.exception(f"复制 {src} 失败: {e}")
            self.done.emit(final_games, len(unknown))
        except Exception as e:
            logger.exception("导入游戏失败")
            self.fail.emit(str(e))
        finally:
            if temp_root and temp_root.exists():
                shutil.rmtree(temp_root, ignore_errors=True)


# ============================================================
# 12. Worker: 多线程下载（★ 读镜像配置）
# ============================================================
class DownloadWorker(QThread):
    progress = Signal(int, int)
    speed = Signal(float, float)
    status = Signal(str)
    done = Signal(str)
    fail = Signal(str)

    def __init__(self, url: str, target: Path, threads: int = 8):
        super().__init__()
        self._url = url
        self._target = target
        self._threads = max(1, min(16, threads))
        self._cancel = False
        self._lock = threading.Lock()
        self._downloaded = 0
        self._total = 0
        self._start_time = 0.0

    def cancel(self):
        self._cancel = True

    def _request(self, method: str, url: str, **kwargs):
        headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
        headers.update(kwargs.pop("headers", {}) or {})
        try:
            import certifi
            verify_opt = certifi.where()
        except ImportError:
            verify_opt = True
        try:
            return requests.request(method, url, headers=headers,
                                    timeout=30, verify=verify_opt, **kwargs)
        except requests.exceptions.SSLError:
            logger.warning("SSL 验证失败，降级 verify=False")
            return requests.request(method, url, headers=headers,
                                    timeout=30, verify=False, **kwargs)

    def _try_mirrors(self):
        """★ v0.8：从 mirrors.json 读镜像列表"""
        mirrors = get_mirror_list()
        if "github.com/" in self._url or "githubusercontent.com/" in self._url:
            for m in mirrors:
                test_url = m + self._url if m else self._url
                try:
                    self.status.emit(tr("download_trying_mirror", url=test_url))
                    r = self._request("HEAD", test_url, allow_redirects=True)
                    if r.status_code < 400:
                        return test_url, r
                except Exception as e:
                    logger.debug(f"镜像 {test_url} 失败: {e}")
                    continue
            return None, None
        else:
            try:
                r = self._request("HEAD", self._url, allow_redirects=True)
                return self._url, r
            except Exception:
                return None, None

    def run(self):
        try:
            real_url, head = self._try_mirrors()
            if not real_url:
                self.fail.emit("所有镜像均不可用，请检查网络/代理")
                return
            total = int(head.headers.get("Content-Length", 0))
            accept_ranges = head.headers.get("Accept-Ranges", "").lower() == "bytes"
            self._total = total
            self._target.parent.mkdir(parents=True, exist_ok=True)
            if accept_ranges and total > 4 * 1024 * 1024 and self._threads > 1:
                self._run_multi(real_url, total)
            else:
                self._run_single(real_url)
            if not self._target.exists() or self._target.stat().st_size == 0:
                self.fail.emit("下载文件为空")
                return
            self.done.emit(str(self._target))
        except Exception as e:
            logger.exception("下载失败")
            self.fail.emit(str(e))

    def _run_single(self, url: str):
        r = self._request("GET", url, stream=True)
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        self._total = total
        self._start_time = time.time()
        downloaded = 0
        last_emit = 0.0
        with open(self._target, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if self._cancel:
                    self.status.emit("已取消")
                    return
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                self._downloaded = downloaded
                now = time.time()
                if now - last_emit > 0.3:
                    self._emit_progress()
                    last_emit = now

    def _run_multi(self, url: str, total: int):
        self._start_time = time.time()
        n = self._threads
        chunk_size = total // n
        parts = []
        for i in range(n):
            start = i * chunk_size
            end = (start + chunk_size - 1) if i < n - 1 else (total - 1)
            parts.append((start, end,
                          self._target.with_suffix(self._target.suffix + f".part{i}")))
        self._downloaded = 0
        errors = []

        def download_part(idx, start, end, path):
            try:
                headers = {"Range": f"bytes={start}-{end}"}
                r = self._request("GET", url, stream=True, headers=headers)
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if self._cancel:
                            return
                        if not chunk:
                            continue
                        f.write(chunk)
                        with self._lock:
                            self._downloaded += len(chunk)
            except Exception as e:
                errors.append((idx, e))

        threads = []
        for idx, (s, e, p) in enumerate(parts):
            t = threading.Thread(target=download_part, args=(idx, s, e, p))
            t.daemon = True
            t.start()
            threads.append(t)

        while any(t.is_alive() for t in threads):
            if self._cancel:
                self.status.emit("已取消")
                return
            self._emit_progress()
            time.sleep(0.3)

        for t in threads:
            t.join()

        if errors:
            raise RuntimeError(f"部分线程失败: {errors[0][1]}")

        with open(self._target, "wb") as out:
            for _, _, p in parts:
                if p.exists():
                    with open(p, "rb") as f:
                        shutil.copyfileobj(f, out)
                    p.unlink()

        self._downloaded = total
        self._emit_progress()

    def _emit_progress(self):
        self.progress.emit(self._downloaded, self._total)
        elapsed = time.time() - self._start_time
        if elapsed > 0:
            speed = self._downloaded / elapsed
            remain = (self._total - self._downloaded) / speed if speed > 0 else 0
            self.speed.emit(speed, remain)


# ============================================================
# 13. Worker: 镜像测试（★ 新增）
# ============================================================
class MirrorTestWorker(QThread):
    """测试每个镜像的可用性。用当前下载 URL 或一个固定小文件"""
    one = Signal(str, bool, float)     # (mirror, ok, ms)
    done = Signal(int, int)            # (ok_count, fail_count)

    def __init__(self, test_url: str):
        super().__init__()
        self._test_url = test_url

    def run(self):
        mirrors = get_mirror_list()
        ok_count = 0
        fail_count = 0
        headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
        try:
            import certifi
            verify_opt = certifi.where()
        except ImportError:
            verify_opt = True

        for m in mirrors:
            url = m + self._test_url if m else self._test_url
            t0 = time.time()
            ok = False
            try:
                r = requests.head(url, headers=headers, timeout=5,
                                  verify=verify_opt, allow_redirects=True)
                if r.status_code < 400:
                    ok = True
            except Exception:
                try:
                    # HEAD 失败，降级 GET（只读前 1KB）
                    r = requests.get(url, headers=headers, timeout=5,
                                     verify=verify_opt, stream=True,
                                     allow_redirects=True)
                    if r.status_code < 400:
                        ok = True
                    r.close()
                except Exception:
                    ok = False
            ms = (time.time() - t0) * 1000
            display = m if m else "（直连）"
            self.one.emit(display, ok, ms)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        self.done.emit(ok_count, fail_count)

# ============================================================
# 14. 启动 / 存档 / BIOS
# ============================================================
def build_launch_command(engine: EmulatorConfig, game: GameEntry,
                         rom_path: str = "", extra_args: str = "") -> list[str]:
    actual_rom = rom_path or game.path
    tpl = engine.launch_template or "{exe} \"{rom}\""
    cmd_str = tpl.format(exe=engine.engine_path, rom=actual_rom)
    if extra_args:
        cmd_str = cmd_str + " " + extra_args
    args = []
    buf = ""
    in_quote = False
    for ch in cmd_str:
        if ch == '"':
            in_quote = not in_quote
        elif ch == " " and not in_quote:
            if buf:
                args.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        args.append(buf)
    return args


def launch_game(engine: EmulatorConfig, game: GameEntry) -> tuple:
    actual_rom, switched = resolve_rom_for_launch(game.path)
    args = build_launch_command(engine, game, rom_path=actual_rom,
                                extra_args=game.extra_args)
    exe_dir = str(Path(engine.engine_path).parent)
    proc = sp.Popen(args, cwd=exe_dir,
                    creationflags=sp.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0)
    logger.info(f"已启动: {' '.join(args)}" + (" (auto .cue)" if switched else ""))
    return proc, switched


KNOWN_BIOS = {
    "mpr-17933.bin": "SS BIOS (美/欧)",
    "sega_101.bin": "SS BIOS (日版)",
    "scph10000.bin": "PS1 BIOS (日版 1.0)",
    "scph39001.bin": "PS1 BIOS (美版)",
    "scph70012.bin": "PS1 BIOS (欧版)",
    "scph1001.bin": "PS1 BIOS (美版 2.2)",
    "scph7001.bin": "PS1 BIOS (美版 2.2)",
    "bios.bin": "通用 BIOS",
    "gba_bios.bin": "GBA BIOS",
    "gba_bios.rom": "GBA BIOS",
    "nds_bios_arm7.bin": "NDS ARM7 BIOS",
    "nds_bios_arm9.bin": "NDS ARM9 BIOS",
    "prod.keys": "Switch prod.keys",
}


@dataclass
class BiosFile:
    name: str
    path: str
    size: int
    md5: str
    known_as: str = ""


def scan_bios() -> list[BiosFile]:
    result = []
    if not BIOS_DIR.exists():
        return result
    for f in BIOS_DIR.rglob("*"):
        if not f.is_file():
            continue
        try:
            size = f.stat().st_size
        except Exception:
            size = 0
        try:
            md5 = md5_of_file(f)
        except Exception:
            md5 = ""
        known = KNOWN_BIOS.get(f.name.lower(), "")
        result.append(BiosFile(name=f.name, path=str(f), size=size, md5=md5, known_as=known))
    return result


def backup_all_saves() -> list[str]:
    results = []
    if not SAVE_PATHS:
        raise RuntimeError(tr("save_none"))
    ts = time.strftime("%Y%m%d_%H%M%S")
    for engine_name, path_str in SAVE_PATHS.items():
        path_str = (path_str or "").strip()
        if not path_str:
            continue
        src = Path(path_str)
        if not src.exists() or not src.is_dir():
            continue
        dst = SAVE_BACKUP_DIR / f"{engine_name}_{ts}"
        try:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            results.append(dst.name)
            logger.info(f"存档备份: {src} -> {dst}")
        except Exception as e:
            logger.exception(f"备份 {engine_name} 失败: {e}")
    return results


def list_save_backups() -> list[Path]:
    if not SAVE_BACKUP_DIR.exists():
        return []
    return sorted([p for p in SAVE_BACKUP_DIR.iterdir() if p.is_dir()],
                  key=lambda x: x.stat().st_mtime, reverse=True)


def restore_save_backup(backup_dir: Path) -> bool:
    name = backup_dir.name
    if "_" not in name:
        raise ValueError(f"无效的备份目录名: {name}")
    engine_name = name.rsplit("_", 2)[0]
    target = SAVE_PATHS.get(engine_name, "").strip()
    if not target:
        raise RuntimeError(f"未配置 {engine_name} 的存档路径")
    target_path = Path(target)
    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    pre_backup = SAVE_BACKUP_DIR / f"{engine_name}_pre_restore_{ts}"
    try:
        if target_path.exists() and any(target_path.iterdir()):
            shutil.copytree(target_path, pre_backup)
    except Exception:
        pass
    for item in backup_dir.iterdir():
        dst = target_path / item.name
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)
    logger.info(f"存档还原: {backup_dir} -> {target_path}")
    return True


# ============================================================
# 15. Worker: 进程监控
# ============================================================
class ProcessMonitorWorker(QThread):
    elapsed = Signal(int)
    finished = Signal(int)

    def __init__(self, pid: int):
        super().__init__()
        self._pid = pid
        self._stop = False
        self._start = time.time()

    def stop(self):
        self._stop = True

    def run(self):
        if not HAS_PSUTIL:
            return
        try:
            proc = psutil.Process(self._pid)
        except Exception:
            return
        while not self._stop:
            try:
                if not proc.is_running():
                    break
                status = proc.status()
                if status == psutil.STATUS_ZOMBIE:
                    break
            except psutil.NoSuchProcess:
                break
            except Exception:
                break
            elapsed = int(time.time() - self._start)
            self.elapsed.emit(elapsed)
            time.sleep(1)
        total = int(time.time() - self._start)
        self.finished.emit(total)


# ============================================================
# 16. QSS — Windows 11 / Fluent 风
# ============================================================
WIN11_QSS = """
* {
    font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: #1c1c1c;
}
QMainWindow, QWidget { background-color: #f3f3f3; }

QFrame#TopBar {
    background-color: #fafafa;
    border-bottom: 1px solid #e5e5e5;
}
QLabel#AppTitle {
    font-size: 14px;
    font-weight: 600;
    color: #1c1c1c;
}

QListWidget#NavList {
    background-color: #f3f3f3;
    border: none;
    outline: none;
    padding: 6px;
}
QListWidget#NavList::item {
    padding: 9px 12px;
    border-radius: 5px;
    margin: 1px 4px;
    color: #1c1c1c;
}
QListWidget#NavList::item:hover { background-color: #e8e8e8; }
QListWidget#NavList::item:selected {
    background-color: #e0e0e0;
    color: #1c1c1c;
    font-weight: 600;
}

QLabel { color: #1c1c1c; background: transparent; }
QLabel#SectionTitle {
    font-size: 15px;
    font-weight: 600;
    color: #1c1c1c;
    padding: 4px 0;
}
QLabel#Hint { color: #767676; }
QLabel#AdminOk {
    color: #0f7b0f;
    background-color: #e6f4e6;
    padding: 2px 10px;
    border-radius: 10px;
}
QLabel#AdminNo {
    color: #c42b1c;
    background-color: #fdeaea;
    padding: 2px 10px;
    border-radius: 10px;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #fbfbfb;
    border: 1px solid #d9d9d9;
    border-bottom: 2px solid #d9d9d9;
    border-radius: 5px;
    padding: 6px 10px;
    selection-background-color: #0067c0;
    selection-color: white;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { background-color: #ffffff; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-bottom: 2px solid #0067c0;
    background-color: #ffffff;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #666;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 5px;
    selection-background-color: #e8e8e8;
    selection-color: #1c1c1c;
    outline: none;
    padding: 4px;
}

QPushButton {
    background-color: #fbfbfb;
    border: 1px solid #d9d9d9;
    border-bottom: 2px solid #d9d9d9;
    border-radius: 5px;
    padding: 6px 14px;
    color: #1c1c1c;
    min-height: 18px;
}
QPushButton:hover { background-color: #f5f5f5; }
QPushButton:pressed {
    background-color: #ededed;
    border-bottom: 1px solid #d9d9d9;
}
QPushButton:disabled {
    background-color: #f5f5f5;
    color: #a0a0a0;
    border-color: #e5e5e5;
}
QPushButton#PrimaryBtn {
    background-color: #0067c0;
    border: 1px solid #0067c0;
    border-bottom: 2px solid #005ba8;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#PrimaryBtn:hover { background-color: #1975c5; }
QPushButton#PrimaryBtn:pressed {
    background-color: #005ba8;
    border-bottom: 1px solid #005ba8;
}
QPushButton#DangerBtn {
    background-color: #c42b1c;
    border: 1px solid #c42b1c;
    border-bottom: 2px solid #a02317;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#DangerBtn:hover { background-color: #d13a2b; }

QTableView {
    background-color: #ffffff;
    alternate-background-color: #fafafa;
    gridline-color: #ededed;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
    selection-background-color: #e8f0fa;
    selection-color: #1c1c1c;
    outline: none;
}
QTableView::item { padding: 6px 8px; }
QHeaderView::section {
    background-color: #fafafa;
    color: #5c5c5c;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #e5e5e5;
    border-right: 1px solid #ededed;
    font-weight: 500;
}

QListWidget#GameGrid {
    background-color: #f3f3f3;
    border: none;
    outline: none;
}
QListWidget#GameGrid::item {
    background-color: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
    margin: 4px;
    padding: 8px;
    color: #1c1c1c;
}
QListWidget#GameGrid::item:hover {
    background-color: #fafafa;
    border: 1px solid #0067c0;
}
QListWidget#GameGrid::item:selected {
    background-color: #e8f0fa;
    border: 1px solid #0067c0;
}

QStatusBar {
    background-color: #fafafa;
    color: #5c5c5c;
    border-top: 1px solid #e5e5e5;
}
QStatusBar::item { border: none; }

QSplitter::handle { background-color: #e5e5e5; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:hover { background-color: #0067c0; }

QProgressBar {
    background-color: #ededed;
    border: none;
    border-radius: 3px;
    text-align: center;
    height: 6px;
    color: transparent;
}
QProgressBar::chunk { background-color: #0067c0; border-radius: 3px; }

QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #1c1c1c;
    background-color: #ffffff;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c8c8c8;
    border-radius: 4px;
    min-height: 24px;
    margin: 0 2px;
}
QScrollBar::handle:vertical:hover { background: #a8a8a8; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #c8c8c8;
    border-radius: 4px;
    min-width: 24px;
    margin: 2px 0;
}
QScrollBar::handle:horizontal:hover { background: #a8a8a8; }

QCheckBox, QRadioButton {
    color: #1c1c1c;
    spacing: 8px;
    padding: 4px 0;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #8a8a8a;
    background-color: #fbfbfb;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #0067c0;
    border: 1px solid #0067c0;
}
QRadioButton::indicator { border-radius: 9px; }

QTextEdit {
    background-color: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 5px;
    padding: 8px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    selection-background-color: #0067c0;
    selection-color: white;
}

QMenu {
    background-color: #fbfbfb;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 7px 28px 7px 14px;
    border-radius: 4px;
    color: #1c1c1c;
}
QMenu::item:selected { background-color: #e8e8e8; color: #1c1c1c; }
QMenu::separator { height: 1px; background: #e5e5e5; margin: 4px 8px; }

QTabWidget::pane {
    background-color: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background-color: transparent;
    color: #5c5c5c;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 4px;
}
QTabBar::tab:selected {
    color: #0067c0;
    border-bottom: 2px solid #0067c0;
}
QTabBar::tab:hover:!selected {
    background-color: #f5f5f5;
    border-radius: 4px;
}

QDialog { background-color: #f3f3f3; }
QScrollArea { border: none; background: transparent; }
"""


# ============================================================
# 17. 管理员
# ============================================================
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{a}"' for a in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        return True
    except Exception:
        return False


# ============================================================
# 18. 数据模型
# ============================================================
class GameTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows: list[GameEntry] = []

    def set_rows(self, rows: list[GameEntry]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 6

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ["", "", tr("library_col_name"), tr("library_col_platform"),
                    tr("library_col_size"), tr("library_col_path")][section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        try:
            row = self._rows[index.row()]
        except IndexError:
            return None
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == 0:
                return "★" if row.favorite else ""
            if col == 1:
                if row.override_platform or row.override_engine or row.extra_args:
                    return "⚙"
                return ""
            if col == 2:
                return row.name
            if col == 3:
                return PLATFORM_LABELS.get(row.platform, row.platform)
            if col == 4:
                return format_size(row.size)
            if col == 5:
                return row.path
        if role == Qt.ForegroundRole:
            if col == 0:
                return QColor("#f7b500") if row.favorite else QColor("#cccccc")
            if col == 1:
                return QColor("#c47f00")
            if col == 3:
                return QColor("#0067c0")
        if role == Qt.TextAlignmentRole and col in (0, 1, 4):
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return row.path
        return None

    def get(self, row: int) -> Optional[GameEntry]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class GameFilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self._keyword = ""
        self._platform = ""
        self._filter_mode = "all"
        self._sort_mode = "name"
        self.setDynamicSortFilter(False)

    def set_keyword(self, kw: str):
        self._keyword = kw.strip().lower()
        self._safe_invalidate()

    def set_platform(self, p: str):
        self._platform = p
        self._safe_invalidate()

    def set_filter_mode(self, mode: str):
        self._filter_mode = mode
        self._safe_invalidate()

    def set_sort_mode(self, mode: str):
        self._sort_mode = mode
        self._safe_invalidate()

    def _safe_invalidate(self):
        try:
            self.invalidateFilter()
            self.invalidate()
        except Exception:
            pass

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if model is None:
            return False
        try:
            g = model.get(source_row)
        except Exception:
            return False
        if g is None:
            return False
        if self._platform and g.platform != self._platform:
            return False
        if self._keyword and self._keyword not in g.name.lower():
            return False
        if self._filter_mode == "favorite" and not g.favorite:
            return False
        if self._filter_mode == "recent" and not g.last_played:
            return False
        return True

    def lessThan(self, left, right):
        lm = self.sourceModel()
        lg = lm.get(left.row())
        rg = lm.get(right.row())
        if lg is None or rg is None:
            return False
        if self._sort_mode == "recent":
            return (lg.last_played or "") > (rg.last_played or "")
        elif self._sort_mode == "playtime":
            return lg.play_seconds > rg.play_seconds
        return lg.name.lower() < rg.name.lower()


class EngineTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows: list[EmulatorConfig] = []

    def set_rows(self, rows: list[EmulatorConfig]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return [tr("engines_col_platform"), tr("engines_col_engine"),
                    tr("engines_col_path"), tr("engines_col_source")][section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        try:
            row = self._rows[index.row()]
        except IndexError:
            return None
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            return [row.platform_name or row.platform,
                    f"{row.engine} {row.version}".strip(),
                    row.engine_path, row.source][col]
        if role == Qt.ForegroundRole and col == 0:
            return QColor("#0067c0")
        return None


class BiosTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows: list[BiosFile] = []

    def set_rows(self, rows: list[BiosFile]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return [tr("bios_col_file"), tr("bios_col_size"),
                    tr("bios_col_md5"), tr("bios_col_known")][section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        try:
            row = self._rows[index.row()]
        except IndexError:
            return None
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            return [row.name, format_size(row.size), row.md5, row.known_as or "未知"][col]
        if role == Qt.ForegroundRole and col == 3:
            return QColor("#0f7b0f") if row.known_as else QColor("#767676")
        return None


def find_cover(name: str) -> Optional[Path]:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = COVER_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


# ============================================================
# 19. 启动配置对话框
# ============================================================
class LaunchConfigDialog(QDialog):
    def __init__(self, game: GameEntry, parent=None):
        super().__init__(parent)
        self._game = game
        self._result = None
        self.setWindowTitle(f"{tr('config_title')} - {game.name}")
        self.setMinimumWidth(520)
        self._build_ui()
        self._load_current()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info = QLabel(
            f"{tr('config_game')}: <b>{self._game.name}</b><br>"
            f"{tr('config_current_platform')}: "
            f"<b>{PLATFORM_LABELS.get(self._game.platform, self._game.platform)}</b>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        grp_engine = QGroupBox(tr("config_engine_group"))
        ge = QVBoxLayout(grp_engine)
        self.radio_auto = QRadioButton(tr("config_auto"))
        self.radio_manual = QRadioButton(tr("config_manual"))
        self.radio_group = QButtonGroup(self)
        self.radio_group.addButton(self.radio_auto, 0)
        self.radio_group.addButton(self.radio_manual, 1)
        ge.addWidget(self.radio_auto)
        ge.addWidget(self.radio_manual)
        self.combo_engine = QComboBox()
        self._populate_engines()
        ge.addWidget(self.combo_engine)
        layout.addWidget(grp_engine)

        grp_plat = QGroupBox(tr("config_platform_override"))
        gp = QVBoxLayout(grp_plat)
        hint = QLabel(tr("config_platform_override_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        gp.addWidget(hint)
        self.combo_override = QComboBox()
        self.combo_override.addItem(tr("config_platform_none"), "")
        for p in PLATFORM_LABELS:
            self.combo_override.addItem(PLATFORM_LABELS[p], p)
        gp.addWidget(self.combo_override)
        layout.addWidget(grp_plat)

        grp_args = QGroupBox(tr("config_extra_args"))
        ga = QVBoxLayout(grp_args)
        self.edit_args = QLineEdit()
        self.edit_args.setPlaceholderText(tr("config_extra_args_ph"))
        ga.addWidget(self.edit_args)
        layout.addWidget(grp_args)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("config_save"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("config_cancel"))
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _populate_engines(self):
        installed = load_installed()
        self.combo_engine.clear()
        if not installed:
            self.combo_engine.addItem(tr("config_no_engine"), "")
            self.combo_engine.setEnabled(False)
            return
        for e in installed:
            label = f"[{e.platform_name}] {e.engine} {e.version}".strip()
            key = f"{e.platform}/{e.engine}"
            self.combo_engine.addItem(label, key)

    def _load_current(self):
        g = self._game
        idx = self.combo_override.findData(g.override_platform or "")
        if idx >= 0:
            self.combo_override.setCurrentIndex(idx)
        if g.override_engine:
            self.radio_manual.setChecked(True)
            idx = self.combo_engine.findData(g.override_engine)
            if idx >= 0:
                self.combo_engine.setCurrentIndex(idx)
        else:
            self.radio_auto.setChecked(True)
        self.edit_args.setText(g.extra_args or "")

    def _on_save(self):
        override_platform = self.combo_override.currentData() or ""
        override_engine = ""
        if self.radio_manual.isChecked():
            override_engine = self.combo_engine.currentData() or ""
        extra_args = self.edit_args.text().strip()
        self._result = {
            "override_platform": override_platform,
            "override_engine": override_engine,
            "extra_args": extra_args,
        }
        self.accept()

    def result_data(self) -> Optional[dict]:
        return self._result


# ============================================================
# 20. 页面：游戏库
# ============================================================
class LibraryPage(QWidget):
    launch_requested = Signal(GameEntry)
    open_folder_requested = Signal(GameEntry)
    remove_requested = Signal(GameEntry)
    favorite_toggled = Signal(GameEntry)
    set_cover_requested = Signal(GameEntry)
    open_save_requested = Signal(GameEntry)
    config_requested = Signal(GameEntry)

    def __init__(self):
        super().__init__()
        self._model = GameTableModel()
        self._proxy = GameFilterProxy()
        self._proxy.setSourceModel(self._model)
        self._games: list[GameEntry] = []
        self._view_mode = "list"
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(tr("library_title"))
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText(tr("library_search_ph"))
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.textChanged.connect(self._proxy.set_keyword)
        bar.addWidget(self.edit_search, 1)

        self.combo_platform = QComboBox()
        self.combo_platform.addItem(tr("library_platform_all"), "")
        for p in PLATFORM_LABELS:
            self.combo_platform.addItem(PLATFORM_LABELS[p], p)
        self.combo_platform.currentIndexChanged.connect(self._on_platform_changed)
        bar.addWidget(self.combo_platform)

        self.combo_filter = QComboBox()
        self.combo_filter.addItem(tr("library_filter_all"), "all")
        self.combo_filter.addItem(tr("library_filter_fav"), "favorite")
        self.combo_filter.addItem(tr("library_filter_recent"), "recent")
        self.combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        bar.addWidget(self.combo_filter)

        self.combo_sort = QComboBox()
        self.combo_sort.addItem(tr("library_sort_name"), "name")
        self.combo_sort.addItem(tr("library_sort_recent"), "recent")
        self.combo_sort.addItem(tr("library_sort_playtime"), "playtime")
        self.combo_sort.currentIndexChanged.connect(self._on_sort_changed)
        bar.addWidget(self.combo_sort)

        self.btn_view = QPushButton("⊞")
        self.btn_view.setToolTip(tr("library_view_grid"))
        self.btn_view.setFixedWidth(40)
        self.btn_view.clicked.connect(self._toggle_view)
        bar.addWidget(self.btn_view)

        self.btn_launch = QPushButton(tr("library_launch_btn"))
        self.btn_launch.setObjectName("PrimaryBtn")
        self.btn_launch.clicked.connect(self._on_launch_clicked)
        bar.addWidget(self.btn_launch)

        self.lbl_count = QLabel(tr("library_count", n=0))
        self.lbl_count.setObjectName("Hint")
        bar.addWidget(self.lbl_count)
        root.addLayout(bar)

        self.view_stack = QStackedWidget()

        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu_list)
        self.table.setSortingEnabled(True)
        self.view_stack.addWidget(self.table)

        self.grid = QListWidget()
        self.grid.setObjectName("GameGrid")
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setIconSize(QSize(160, 220))
        self.grid.setGridSize(QSize(190, 290))
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setSpacing(8)
        self.grid.setWordWrap(True)
        self.grid.itemDoubleClicked.connect(self._on_grid_double_click)
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._on_context_menu_grid)
        self.view_stack.addWidget(self.grid)

        root.addWidget(self.view_stack, 1)

        tip = QLabel(tr("library_empty"))
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

    def _toggle_view(self):
        if self._view_mode == "list":
            self._view_mode = "grid"
            self.btn_view.setText("☰")
            self.view_stack.setCurrentIndex(1)
            self._rebuild_grid()
        else:
            self._view_mode = "list"
            self.btn_view.setText("⊞")
            self.view_stack.setCurrentIndex(0)

    def _on_platform_changed(self, index):
        self._proxy.set_platform(self.combo_platform.itemData(index) or "")
        if self._view_mode == "grid":
            self._rebuild_grid()

    def _on_filter_changed(self, index):
        self._proxy.set_filter_mode(self.combo_filter.itemData(index) or "all")
        if self._view_mode == "grid":
            self._rebuild_grid()

    def _on_sort_changed(self, index):
        self._proxy.set_sort_mode(self.combo_sort.itemData(index) or "name")
        self.table.sortByColumn(2, Qt.AscendingOrder)
        if self._view_mode == "grid":
            self._rebuild_grid()

    def set_games(self, games: list[GameEntry]):
        self._games = games
        self._model.set_rows(games)
        self.lbl_count.setText(tr("library_count", n=len(games)))
        if self._view_mode == "grid":
            self._rebuild_grid()

    def _rebuild_grid(self):
        self.grid.clear()
        rows = []
        for i in range(self._proxy.rowCount()):
            idx = self._proxy.index(i, 0)
            src = self._proxy.mapToSource(idx)
            g = self._model.get(src.row())
            if g:
                rows.append(g)

        for g in rows:
            cover = find_cover(g.name)
            item = QListWidgetItem()
            label = g.name
            if g.favorite:
                label = "★ " + label
            if g.override_platform or g.override_engine or g.extra_args:
                label = "⚙ " + label
            item.setText(label)
            if cover:
                pix = QPixmap(str(cover))
                if not pix.isNull():
                    pix = pix.scaled(160, 220, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
                    item.setIcon(QIcon(pix))
            else:
                item.setText(f"{label}\n\n{tr('library_no_cover')}")
            item.setToolTip(
                f"{g.name}\n{PLATFORM_LABELS.get(g.platform, g.platform)}\n"
                f"{human_duration(g.play_seconds)}")
            item.setData(Qt.UserRole, g)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.grid.addItem(item)

    def _selected_game(self) -> Optional[GameEntry]:
        if self._view_mode == "list":
            idxs = self.table.selectionModel().selectedRows()
            if not idxs:
                return None
            src = self._proxy.mapToSource(idxs[0])
            return self._model.get(src.row())
        else:
            items = self.grid.selectedItems()
            if not items:
                return None
            return items[0].data(Qt.UserRole)

    def _on_launch_clicked(self):
        g = self._selected_game()
        if not g:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("library_select_hint"))
            return
        self.launch_requested.emit(g)

    def _on_double_click(self, _index):
        g = self._selected_game()
        if g:
            self.launch_requested.emit(g)

    def _on_grid_double_click(self, _item):
        g = self._selected_game()
        if g:
            self.launch_requested.emit(g)

    def _show_menu(self, g: GameEntry, global_pos):
        menu = QMenu(self)
        a_launch = menu.addAction(tr("ctx_launch"))
        a_config = menu.addAction(tr("ctx_config"))
        menu.addSeparator()
        a_folder = menu.addAction(tr("ctx_open_folder"))
        a_save = menu.addAction(tr("ctx_open_save"))
        menu.addSeparator()
        if g.favorite:
            a_fav = menu.addAction(tr("ctx_fav_remove"))
        else:
            a_fav = menu.addAction(tr("ctx_fav_add"))
        a_cover = menu.addAction(tr("ctx_set_cover"))
        menu.addSeparator()
        a_remove = menu.addAction(tr("ctx_remove"))
        act = menu.exec(global_pos)
        if act == a_launch:
            self.launch_requested.emit(g)
        elif act == a_config:
            self.config_requested.emit(g)
        elif act == a_folder:
            self.open_folder_requested.emit(g)
        elif act == a_save:
            self.open_save_requested.emit(g)
        elif act == a_fav:
            self.favorite_toggled.emit(g)
        elif act == a_cover:
            self.set_cover_requested.emit(g)
        elif act == a_remove:
            self.remove_requested.emit(g)

    def _on_context_menu_list(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        src = self._proxy.mapToSource(idx)
        g = self._model.get(src.row())
        if not g:
            return
        self._show_menu(g, self.table.viewport().mapToGlobal(pos))

    def _on_context_menu_grid(self, pos):
        item = self.grid.itemAt(pos)
        if not item:
            return
        g = item.data(Qt.UserRole)
        if not g:
            return
        self._show_menu(g, self.grid.viewport().mapToGlobal(pos))

    def refresh_grid(self):
        if self._view_mode == "grid":
            self._rebuild_grid()


# ============================================================
# 21. 页面：模拟器 / BIOS
# ============================================================
class EnginePage(QWidget):
    import_requested = Signal()
    download_requested = Signal()

    def __init__(self):
        super().__init__()
        self._model = EngineTableModel()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        title = QLabel(tr("engines_title"))
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        bar = QHBoxLayout()
        self.btn_import = QPushButton(tr("toolbar_import_engine"))
        self.btn_import.setObjectName("PrimaryBtn")
        self.btn_import.clicked.connect(self.import_requested.emit)
        bar.addWidget(self.btn_import)
        self.btn_download = QPushButton(tr("toolbar_download_engine"))
        self.btn_download.clicked.connect(self.download_requested.emit)
        bar.addWidget(self.btn_download)
        self.btn_refresh = QPushButton(tr("toolbar_refresh"))
        self.btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(self.btn_refresh)
        bar.addStretch(1)
        root.addLayout(bar)

        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)

        tip = QLabel(tr("engines_empty"))
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

    def refresh(self):
        self._model.set_rows(load_installed())


class BiosPage(QWidget):
    def __init__(self):
        super().__init__()
        self._model = BiosTableModel()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        title = QLabel(tr("bios_title"))
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        bar = QHBoxLayout()
        btn_refresh = QPushButton(tr("toolbar_refresh"))
        btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(btn_refresh)
        btn_open = QPushButton("打开 bios 目录")
        btn_open.clicked.connect(lambda: os.startfile(str(BIOS_DIR)))
        bar.addWidget(btn_open)
        bar.addStretch(1)
        root.addLayout(bar)

        hint = QLabel(tr("bios_hint"))
        hint.setObjectName("Hint")
        root.addWidget(hint)

        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)

    def refresh(self):
        self._model.set_rows(scan_bios())


# ============================================================
# 22. 页面：设置（★ 加镜像区块）
# ============================================================
class SettingsPage(QWidget):
    lang_changed = Signal(str)
    saves_changed = Signal()

    def __init__(self):
        super().__init__()
        self._mirror_test_worker: Optional[MirrorTestWorker] = None
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setSpacing(12)

        title = QLabel(tr("settings_title"))
        title.setObjectName("SectionTitle")
        v.addWidget(title)

        # 语言
        box1 = QGroupBox(tr("settings_lang"))
        f1 = QVBoxLayout(box1)
        row1 = QHBoxLayout()
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("简体中文", "zh")
        self.combo_lang.addItem("English", "en")
        self.combo_lang.currentIndexChanged.connect(self._on_lang)
        row1.addWidget(self.combo_lang)
        row1.addStretch(1)
        f1.addLayout(row1)
        h1 = QLabel(tr("settings_lang_hint"))
        h1.setObjectName("Hint")
        f1.addWidget(h1)
        v.addWidget(box1)

        # 下载 + 镜像
        box_dl = QGroupBox(tr("settings_download"))
        fdl = QVBoxLayout(box_dl)

        row_dl = QHBoxLayout()
        row_dl.addWidget(QLabel(tr("settings_threads")))
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(4, 16)
        self.spin_threads.setValue(SETTINGS.get("download_threads", 8))
        self.spin_threads.valueChanged.connect(self._on_threads_changed)
        row_dl.addWidget(self.spin_threads)
        row_dl.addStretch(1)
        fdl.addLayout(row_dl)

        # 镜像开关
        self.check_mirror_enabled = QCheckBox(tr("settings_mirrors_enable"))
        self.check_mirror_enabled.setChecked(MIRRORS_CONFIG.get("enabled", True))
        self.check_mirror_enabled.toggled.connect(self._on_mirror_enabled)
        fdl.addWidget(self.check_mirror_enabled)

        hint_mirror = QLabel(tr("settings_mirrors_hint"))
        hint_mirror.setObjectName("Hint")
        hint_mirror.setWordWrap(True)
        fdl.addWidget(hint_mirror)

        self.list_mirrors = QListWidget()
        self.list_mirrors.setMinimumHeight(160)
        self.list_mirrors.itemChanged.connect(self._on_mirror_item_changed)
        fdl.addWidget(self.list_mirrors)
        self._refresh_mirror_list()

        row_mir = QHBoxLayout()
        b_add = QPushButton(tr("settings_mirrors_add"))
        b_add.clicked.connect(self._mirror_add)
        row_mir.addWidget(b_add)
        b_del = QPushButton(tr("settings_mirrors_del"))
        b_del.clicked.connect(self._mirror_del)
        row_mir.addWidget(b_del)
        b_up = QPushButton(tr("settings_mirrors_up"))
        b_up.clicked.connect(lambda: self._mirror_move(-1))
        row_mir.addWidget(b_up)
        b_down = QPushButton(tr("settings_mirrors_down"))
        b_down.clicked.connect(lambda: self._mirror_move(1))
        row_mir.addWidget(b_down)
        row_mir.addStretch(1)
        b_test = QPushButton(tr("settings_mirrors_test"))
        b_test.setObjectName("PrimaryBtn")
        b_test.clicked.connect(self._mirror_test)
        row_mir.addWidget(b_test)
        b_reset = QPushButton(tr("settings_mirrors_reset"))
        b_reset.clicked.connect(self._mirror_reset)
        row_mir.addWidget(b_reset)
        fdl.addLayout(row_mir)

        self.lbl_mirror_result = QLabel("")
        self.lbl_mirror_result.setObjectName("Hint")
        fdl.addWidget(self.lbl_mirror_result)
        v.addWidget(box_dl)

        # 工作区
        box2 = QGroupBox(tr("settings_workspace"))
        f2 = QVBoxLayout(box2)
        desc = QLabel(tr("settings_workspace_desc"))
        desc.setObjectName("Hint")
        f2.addWidget(desc)
        self.combo_workspace = QComboBox()
        for i, folder in enumerate(FOLDERS_CONFIG.get("folders", [])):
            self.combo_workspace.addItem(
                f"{folder.get('name')}  [{folder.get('path')}]", i)
        self.combo_workspace.setCurrentIndex(FOLDERS_CONFIG.get("active_index", 0))
        self.combo_workspace.currentIndexChanged.connect(self._on_workspace)
        f2.addWidget(self.combo_workspace)
        f2.addWidget(QLabel(f"数据目录: {DATA_DIR}"))
        v.addWidget(box2)

        # 存档
        box_sv = QGroupBox(tr("settings_saves"))
        fsv = QVBoxLayout(box_sv)
        hint_sv = QLabel(tr("settings_saves_hint"))
        hint_sv.setObjectName("Hint")
        hint_sv.setWordWrap(True)
        fsv.addWidget(hint_sv)

        self._save_rows: dict[str, QLineEdit] = {}
        engines_json = load_engines_json()
        all_engines = set()
        for pcfg in engines_json.values():
            for eng in pcfg.get("engines", {}):
                all_engines.add(eng)
        for eng in sorted(all_engines):
            row = QHBoxLayout()
            label = QLabel(eng)
            label.setFixedWidth(120)
            row.addWidget(label)
            edit = QLineEdit(SAVE_PATHS.get(eng, ""))
            edit.setPlaceholderText("留空 = 不管理")
            row.addWidget(edit, 1)
            browse = QPushButton("…")
            browse.setFixedWidth(36)
            browse.clicked.connect(lambda _=False, e=edit: self._browse_save_dir(e))
            row.addWidget(browse)
            fsv.addLayout(row)
            self._save_rows[eng] = edit

        row_sv = QHBoxLayout()
        btn_auto = QPushButton(tr("settings_saves_auto"))
        btn_auto.clicked.connect(self._auto_save_paths)
        row_sv.addWidget(btn_auto)
        btn_save_sv = QPushButton(tr("settings_saves_save"))
        btn_save_sv.setObjectName("PrimaryBtn")
        btn_save_sv.clicked.connect(self._save_save_paths)
        row_sv.addWidget(btn_save_sv)
        row_sv.addStretch(1)
        fsv.addLayout(row_sv)

        row_sv2 = QHBoxLayout()
        btn_backup = QPushButton(tr("settings_saves_backup"))
        btn_backup.clicked.connect(self._backup_saves)
        row_sv2.addWidget(btn_backup)
        btn_restore = QPushButton(tr("settings_saves_restore"))
        btn_restore.clicked.connect(self._restore_saves)
        row_sv2.addWidget(btn_restore)
        btn_open_bk = QPushButton(tr("settings_saves_open"))
        btn_open_bk.clicked.connect(lambda: os.startfile(str(SAVE_BACKUP_DIR)))
        row_sv2.addWidget(btn_open_bk)
        row_sv2.addStretch(1)
        fsv.addLayout(row_sv2)
        v.addWidget(box_sv)

        # 管理员
        box3 = QGroupBox(tr("settings_admin"))
        f3 = QHBoxLayout(box3)
        self.lbl_admin = QLabel()
        f3.addWidget(self.lbl_admin)
        f3.addStretch(1)
        btn_admin = QPushButton(tr("settings_relaunch"))
        btn_admin.clicked.connect(self._relaunch_admin)
        f3.addWidget(btn_admin)
        v.addWidget(box3)

        # 目录
        box4 = QGroupBox("目录")
        f4 = QHBoxLayout(box4)
        b1 = QPushButton(tr("settings_open_data"))
        b1.clicked.connect(lambda: os.startfile(str(DATA_DIR)))
        f4.addWidget(b1)
        b2 = QPushButton(tr("settings_open_log"))
        b2.clicked.connect(lambda: os.startfile(str(LOG_DIR)))
        f4.addWidget(b2)
        f4.addStretch(1)
        v.addWidget(box4)

        v.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    # ---- 镜像列表 ----
    def _refresh_mirror_list(self):
        self.list_mirrors.blockSignals(True)
        self.list_mirrors.clear()
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        for m in mirrors:
            display = m if m else "（直连）"
            item = QListWidgetItem(display)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setData(Qt.UserRole, m)
            self.list_mirrors.addItem(item)
        self.list_mirrors.blockSignals(False)

    def _on_mirror_item_changed(self, item):
        """用户编辑后同步到配置"""
        idx = self.list_mirrors.row(item)
        new_text = item.text().strip()
        # "（直连）" 代表空
        if new_text in ("（直连）", "(direct)", ""):
            new_text = ""
        mirrors = MIRRORS_CONFIG.setdefault("mirrors", [])
        if 0 <= idx < len(mirrors):
            mirrors[idx] = new_text
            save_mirrors()

    def _on_mirror_enabled(self, checked):
        MIRRORS_CONFIG["enabled"] = checked
        save_mirrors()

    def _mirror_add(self):
        text, ok = QInputDialog.getText(
            self, tr("settings_mirrors_add"),
            "输入镜像前缀（末尾带 /）:",
            text="https://")
        if ok and text.strip():
            MIRRORS_CONFIG.setdefault("mirrors", []).append(text.strip())
            save_mirrors()
            self._refresh_mirror_list()

    def _mirror_del(self):
        row = self.list_mirrors.currentRow()
        if row < 0:
            return
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        if 0 <= row < len(mirrors):
            mirrors.pop(row)
            save_mirrors()
            self._refresh_mirror_list()

    def _mirror_move(self, delta):
        row = self.list_mirrors.currentRow()
        if row < 0:
            return
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        new_row = row + delta
        if not (0 <= new_row < len(mirrors)):
            return
        mirrors[row], mirrors[new_row] = mirrors[new_row], mirrors[row]
        save_mirrors()
        self._refresh_mirror_list()
        self.list_mirrors.setCurrentRow(new_row)

    def _mirror_reset(self):
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     "恢复默认镜像列表？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        MIRRORS_CONFIG["mirrors"] = list(DEFAULT_MIRRORS["mirrors"])
        MIRRORS_CONFIG["enabled"] = True
        save_mirrors()
        self._refresh_mirror_list()
        self.check_mirror_enabled.setChecked(True)

    def _mirror_test(self):
        test_url = "https://github.com/robots.txt"
        self.lbl_mirror_result.setText(tr("settings_mirrors_testing"))
        self.list_mirrors.clear()
        self._mirror_test_worker = MirrorTestWorker(test_url)
        self._mirror_test_worker.one.connect(self._on_mirror_test_one)
        self._mirror_test_worker.done.connect(self._on_mirror_test_done)
        self._mirror_test_worker.start()

    def _on_mirror_test_one(self, mirror: str, ok: bool, ms: float):
        status = f"✅ {ms:.0f} ms" if ok else "❌ 失败"
        item = QListWidgetItem(f"{mirror}    {status}")
        if ok:
            item.setForeground(QColor("#0f7b0f"))
        else:
            item.setForeground(QColor("#c42b1c"))
        self.list_mirrors.addItem(item)

    def _on_mirror_test_done(self, ok_count: int, fail_count: int):
        self.lbl_mirror_result.setText(
            tr("settings_mirrors_result", ok=ok_count, fail=fail_count))
        QTimer.singleShot(1500, self._refresh_mirror_list)

    # ---- 其它 ----
    def _refresh(self):
        idx = self.combo_lang.findData(CURRENT_LANG)
        if idx >= 0:
            self.combo_lang.blockSignals(True)
            self.combo_lang.setCurrentIndex(idx)
            self.combo_lang.blockSignals(False)
        self.lbl_admin.setText("已获得管理员权限" if is_admin() else "普通用户")

    def _on_lang(self, index):
        global CURRENT_LANG
        lang = self.combo_lang.itemData(index)
        if not lang or lang == CURRENT_LANG:
            return
        CURRENT_LANG = lang
        save_lang(lang)
        self.lang_changed.emit(lang)

    def _on_threads_changed(self, v):
        SETTINGS["download_threads"] = v
        save_settings()

    def _on_workspace(self, index):
        idx = self.combo_workspace.itemData(index)
        if idx is None:
            return
        FOLDERS_CONFIG["active_index"] = idx
        save_folders_config()

    def _browse_save_dir(self, edit: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "选择存档目录", str(DATA_DIR))
        if d:
            edit.setText(d)

    def _auto_save_paths(self):
        engines_json = load_engines_json()
        detected = autodetect_save_paths(engines_json)
        count = 0
        for eng, edit in self._save_rows.items():
            if not edit.text().strip() and eng in detected:
                edit.setText(detected[eng])
                count += 1
        QMessageBox.information(self, tr("msg_info"),
                                f"自动识别到 {count} 个存档路径，请确认后点保存。")

    def _save_save_paths(self):
        global SAVE_PATHS
        for eng, edit in self._save_rows.items():
            SAVE_PATHS[eng] = edit.text().strip()
        save_save_paths()
        self.saves_changed.emit()
        QMessageBox.information(self, tr("msg_info"), "已保存")

    def _backup_saves(self):
        try:
            results = backup_all_saves()
            if not results:
                QMessageBox.warning(self, tr("msg_warning"), tr("save_none"))
                return
            QMessageBox.information(self, tr("msg_info"),
                                    tr("save_backup_done",
                                       path=f"{len(results)} 个模拟器"))
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("save_backup_failed", err=str(e)))

    def _restore_saves(self):
        backups = list_save_backups()
        if not backups:
            QMessageBox.information(self, tr("msg_info"), "没有备份")
            return
        items = [b.name for b in backups]
        choice, ok = QInputDialog.getItem(self, "还原存档", "选择备份:",
                                          items, 0, False)
        if not ok:
            return
        b = backups[items.index(choice)]
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     tr("save_restore_confirm", name=b.name),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            restore_save_backup(b)
            QMessageBox.information(self, tr("msg_info"),
                                    tr("save_restore_done", name=b.name))
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

    def _relaunch_admin(self):
        if is_admin():
            QMessageBox.information(self, tr("msg_info"), "已是管理员")
            return
        if relaunch_as_admin():
            QApplication.quit()
        else:
            QMessageBox.critical(self, tr("msg_error"), "提权失败")


# ============================================================
# 23. 导入对话框
# ============================================================
class ImportDialog(QDialog):
    def __init__(self, mode: str, engines_json: dict, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._engines_json = engines_json
        self._source: Optional[Path] = None
        self._is_archive = False
        self._worker: Optional[QThread] = None
        self.setWindowTitle(tr("import_engine_title") if mode == "engine"
                            else tr("import_game_title"))
        self.setMinimumWidth(560)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        row = QHBoxLayout()
        btn_archive = QPushButton(tr("import_pick_archive"))
        btn_archive.clicked.connect(self._pick_archive)
        row.addWidget(btn_archive)
        btn_folder = QPushButton(tr("import_pick_folder"))
        btn_folder.clicked.connect(self._pick_folder)
        row.addWidget(btn_folder)
        layout.addLayout(row)

        self.lbl_path = QLabel("—")
        self.lbl_path.setObjectName("Hint")
        self.lbl_path.setWordWrap(True)
        layout.addWidget(self.lbl_path)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("Hint")
        layout.addWidget(self.lbl_status)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(200)
        self.log_view.setVisible(False)
        layout.addWidget(self.log_view)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._btn_ok = btns.button(QDialogButtonBox.Ok)
        self._btn_ok.setText(tr("import_start"))
        self._btn_ok.setObjectName("PrimaryBtn")
        self._btn_ok.setEnabled(False)
        btns.accepted.connect(self._start)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _pick_archive(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("import_pick_archive"), str(DATA_DIR),
            "压缩包 (*.zip *.7z *.rar *.tar *.tar.gz *.tgz);;所有文件 (*)")
        if fp:
            self._source = Path(fp)
            self._is_archive = True
            self.lbl_path.setText(fp)
            self._btn_ok.setEnabled(True)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("import_pick_folder"), str(DATA_DIR))
        if d:
            self._source = Path(d)
            self._is_archive = False
            self.lbl_path.setText(d)
            self._btn_ok.setEnabled(True)

    def _start(self):
        if not self._source:
            return
        self._btn_ok.setEnabled(False)
        self.progress.setVisible(True)
        self.log_view.setVisible(True)
        if self._mode == "engine":
            self._worker = EngineImportWorker(self._source, self._engines_json, self._is_archive)
            self._worker.progress.connect(self._on_progress)
            self._worker.done.connect(self._on_engine_done)
            self._worker.fail.connect(self._on_fail)
        else:
            self._worker = GameImportWorker(self._source, self._engines_json, self._is_archive)
            self._worker.progress.connect(self._on_progress)
            self._worker.done.connect(self._on_game_done)
            self._worker.fail.connect(self._on_fail)
        self._worker.finished.connect(lambda: self.progress.setVisible(False))
        self._worker.start()

    def _on_progress(self, msg):
        self.lbl_status.setText(msg)
        self.log_view.append(msg)

    def _on_engine_done(self, installed, unmatched):
        if installed:
            self.log_view.append(f"识别到 {len(installed)} 个")
            engines = load_installed()
            for cfg in installed:
                engines = [e for e in engines
                           if not (e.platform == cfg.platform and e.engine == cfg.engine)]
                engines.append(cfg)
                self.log_view.append(f"  • {cfg.platform_name} / {cfg.engine}")
            save_installed(engines)
        if unmatched:
            self.log_view.append(f"⚠️ {tr('import_not_found')}: {', '.join(unmatched)}")
        self.accept()

    def _on_game_done(self, games, skipped):
        if games:
            self.log_view.append(tr("rom_import_done", n=len(games)))
            existing = load_games()
            paths = {g.path for g in existing}
            for g in games:
                if g.path in paths:
                    continue
                existing.append(g)
                self.log_view.append(f"  • {g.name} [{g.platform}]")
            save_games(existing)
        if skipped:
            self.log_view.append(tr("rom_import_skipped", n=skipped))
        self.accept()

    def _on_fail(self, err):
        self.progress.setVisible(False)
        self.log_view.append(f"❌ {tr('import_failed', err=err)}")
        QMessageBox.critical(self, tr("msg_error"), err)


# ============================================================
# 24. 下载对话框（★ 加测试镜像按钮）
# ============================================================
class DownloadDialog(QDialog):
    def __init__(self, engines_json: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("download_title"))
        self.setMinimumSize(760, 620)
        self._engines_json = engines_json
        self._worker: Optional[DownloadWorker] = None
        self._test_worker: Optional[MirrorTestWorker] = None
        self._current_engine: Optional[tuple] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_auto_tab(), tr("download_tab_auto"))
        self.tabs.addTab(self._build_manual_tab(), tr("download_tab_manual"))
        layout.addWidget(self.tabs, 1)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("Hint")
        layout.addWidget(self.lbl_status)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.Close).clicked.connect(self.reject)
        layout.addWidget(btns)

    def _build_auto_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self.list_auto = QListWidget()
        for platform, pcfg in self._engines_json.items():
            for engine_name, cfg in pcfg.get("engines", {}).items():
                url = cfg.get("url", "manual")
                if url == "manual" or not url:
                    continue
                label = (f"[{pcfg.get('platform_name', platform)}] "
                         f"{engine_name}  {cfg.get('version', '')}")
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, (platform, engine_name, cfg))
                self.list_auto.addItem(item)
        if self.list_auto.count() == 0:
            lay.addWidget(QLabel(tr("download_no_auto")))
        lay.addWidget(self.list_auto, 1)
        row = QHBoxLayout()
        btn_test = QPushButton(tr("settings_mirrors_test"))
        btn_test.clicked.connect(self._test_mirrors)
        row.addWidget(btn_test)
        row.addStretch(1)
        self.btn_start = QPushButton(tr("download_start"))
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.clicked.connect(self._start_download)
        row.addWidget(self.btn_start)
        lay.addLayout(row)
        return w

    def _build_manual_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        hint = QLabel(tr("download_manual_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setSpacing(8)
        for platform, pcfg in self._engines_json.items():
            for engine_name, cfg in pcfg.get("engines", {}).items():
                if cfg.get("url", "manual") != "manual":
                    continue
                box = QGroupBox(f"[{pcfg.get('platform_name', platform)}] {engine_name}")
                bl = QVBoxLayout(box)
                bl.addWidget(QLabel(
                    f"版本: {cfg.get('version', '未知')}\n备注: {cfg.get('note', '')}"))
                site = cfg.get("official_site", "")
                if site:
                    btn = QPushButton(f"{tr('download_open_site')}: {site}")
                    btn.clicked.connect(lambda _=False, s=site: self._open_site(s))
                    bl.addWidget(btn)
                else:
                    bl.addWidget(QLabel("官网未知，请自行搜索"))
                v.addWidget(box)
        v.addStretch(1)
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)
        return w

    def _open_site(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"), f"打开失败: {e}")

    def _test_mirrors(self):
        items = self.list_auto.selectedItems()
        if not items:
            QMessageBox.information(self, tr("msg_info"), "请先在列表里选中一个模拟器")
            return
        platform, engine_name, cfg = items[0].data(Qt.UserRole)
        test_url = cfg.get("url", "")
        if not test_url or test_url == "manual":
            return
        self.lbl_status.setText(tr("settings_mirrors_testing"))
        self._test_worker = MirrorTestWorker(test_url)
        self._test_worker.one.connect(self._on_test_one)
        self._test_worker.done.connect(self._on_test_done)
        self._test_worker.start()

    def _on_test_one(self, mirror: str, ok: bool, ms: float):
        status = f"✅ {ms:.0f} ms" if ok else "❌ 失败"
        self.lbl_status.setText(f"{mirror}    {status}")

    def _on_test_done(self, ok_count: int, fail_count: int):
        self.lbl_status.setText(
            tr("settings_mirrors_result", ok=ok_count, fail=fail_count))

    def _start_download(self):
        items = self.list_auto.selectedItems()
        if not items:
            QMessageBox.information(self, tr("msg_info"), "请先在列表里选中一个模拟器")
            return
        platform, engine_name, cfg = items[0].data(Qt.UserRole)
        url = cfg.get("url", "")
        archive = cfg.get("archive", "zip")
        if not url or url == "manual":
            return
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     tr("download_confirm", name=f"{platform}/{engine_name}"),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        ext = ".zip"
        if archive == "7z":
            ext = ".7z"
        elif archive == "7z_sfx":
            ext = ".exe"
        elif archive == "rar":
            ext = ".rar"
        tmp_file = TEMP_DIR / f"dl_{platform}_{engine_name}{ext}"
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.lbl_status.setText(tr("download_progress"))
        self.btn_start.setEnabled(False)
        threads = SETTINGS.get("download_threads", 8)
        self._current_engine = (platform, engine_name, cfg)
        self._worker = DownloadWorker(url, tmp_file, threads)
        self._worker.progress.connect(self._on_dl_progress)
        self._worker.speed.connect(self._on_dl_speed)
        self._worker.status.connect(self.lbl_status.setText)
        self._worker.done.connect(self._on_dl_done)
        self._worker.fail.connect(self._on_dl_fail)
        self._worker.finished.connect(self._on_dl_finished)
        self._worker.start()

    def _on_dl_progress(self, cur, total):
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(cur * 100 / total))
        else:
            self.progress.setRange(0, 0)

    def _on_dl_speed(self, speed, remain):
        self.lbl_status.setText(
            f"{tr('download_progress')} "
            + tr("download_speed", speed=human_size(int(speed)), eta=human_eta(remain)))

    def _on_dl_done(self, path):
        self.lbl_status.setText(tr("download_extract"))
        p = Path(path)
        try:
            self._install_downloaded(p)
            self.lbl_status.setText(f"✅ {tr('download_done')}")
            QMessageBox.information(self, tr("msg_info"), tr("download_done"))
        except Exception as e:
            logger.exception("安装下载的模拟器失败")
            self.lbl_status.setText(f"❌ {e}")
            QMessageBox.critical(self, tr("msg_error"), str(e))

    def _on_dl_fail(self, err):
        self.lbl_status.setText(f"❌ {tr('download_failed', err=err)}")
        QMessageBox.critical(self, tr("msg_error"), tr("download_failed", err=err))

    def _on_dl_finished(self):
        self.progress.setVisible(False)
        self.btn_start.setEnabled(True)

    def _install_downloaded(self, archive: Path):
        if not self._current_engine:
            raise RuntimeError("内部错误")
        platform, engine_name, cfg = self._current_engine
        archive_type = cfg.get("archive", "zip")
        tmp_root = Path(tempfile.mkdtemp(prefix="mikan_emu_dl_", dir=str(TEMP_DIR)))
        try:
            if archive_type == "7z_sfx":
                try:
                    sp.run([str(archive), "-y", f"-o{tmp_root}"],
                           check=True, timeout=300,
                           creationflags=sp.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                except Exception:
                    import py7zr
                    with py7zr.SevenZipFile(archive, mode="r") as z:
                        z.extractall(tmp_root)
            else:
                extract_archive(archive, tmp_root)

            files = scan_files(tmp_root)
            matches = match_engines(files, {platform: {"engines": {engine_name: cfg}}})
            if not matches:
                raise RuntimeError(f"解压后没找到 {engine_name} 的可执行文件")

            installed = install_engine_from_match(matches[0], tmp_root, "download")
            engines = load_installed()
            engines = [e for e in engines
                       if not (e.platform == installed.platform
                               and e.engine == installed.engine)]
            engines.append(installed)
            save_installed(engines)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
            try:
                if archive.exists():
                    archive.unlink()
            except Exception:
                pass


# ============================================================
# 25. 主窗口
# ============================================================
class MainWindow(QMainWindow):
    NAV_LIBRARY = 0
    NAV_ENGINES = 1
    NAV_BIOS = 2
    NAV_SETTINGS = 3

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 800)
        self.setMinimumSize(960, 580)

        self._load_lang()
        self._engines_json = load_engines_json()
        self._monitor_workers: list[ProcessMonitorWorker] = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        self.nav.setFixedWidth(170)
        for name in [tr("nav_library"), tr("nav_engines"),
                     tr("nav_bios"), tr("nav_settings")]:
            QListWidgetItem(name, self.nav)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        splitter.addWidget(self.nav)

        self.stack = QStackedWidget()

        self.page_library = LibraryPage()
        self.page_library.launch_requested.connect(self._launch_game)
        self.page_library.open_folder_requested.connect(self._open_game_folder)
        self.page_library.remove_requested.connect(self._remove_game)
        self.page_library.favorite_toggled.connect(self._toggle_favorite)
        self.page_library.set_cover_requested.connect(self._set_cover)
        self.page_library.open_save_requested.connect(self._open_save_dir)
        self.page_library.config_requested.connect(self._config_launch)
        self.stack.addWidget(self.page_library)

        self.page_engines = EnginePage()
        self.page_engines.import_requested.connect(self._import_engine)
        self.page_engines.download_requested.connect(self._download_engine)
        self.stack.addWidget(self.page_engines)

        self.page_bios = BiosPage()
        self.stack.addWidget(self.page_bios)

        self.page_settings = SettingsPage()
        self.page_settings.lang_changed.connect(self._on_lang_changed)
        self.stack.addWidget(self.page_settings)

        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([170, 1110])
        root.addWidget(splitter, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_status = QLabel(f"就绪  |  数据目录: {DATA_DIR}")
        self.status.addWidget(self.lbl_status)
        self.lbl_admin = QLabel()
        self.status.addPermanentWidget(self.lbl_admin)
        self._refresh_admin_label()

        self._reload_games()

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        title = QLabel(f"mikan_emu")
        title.setObjectName("AppTitle")
        lay.addWidget(title)
        lay.addStretch(1)

        self.lbl_admin_top = QLabel()
        lay.addWidget(self.lbl_admin_top)

        btn_import_engine = QPushButton(tr("toolbar_import_engine"))
        btn_import_engine.clicked.connect(self._import_engine)
        lay.addWidget(btn_import_engine)

        btn_download_engine = QPushButton(tr("toolbar_download_engine"))
        btn_download_engine.clicked.connect(self._download_engine)
        lay.addWidget(btn_download_engine)

        btn_import_game = QPushButton(tr("toolbar_import_game"))
        btn_import_game.clicked.connect(self._import_game)
        lay.addWidget(btn_import_game)

        btn_open_roms = QPushButton(tr("toolbar_open_roms"))
        btn_open_roms.clicked.connect(lambda: os.startfile(str(ROM_DIR)))
        lay.addWidget(btn_open_roms)

        btn_refresh = QPushButton(tr("toolbar_refresh"))
        btn_refresh.clicked.connect(self._refresh_all)
        lay.addWidget(btn_refresh)

        return bar

    def _refresh_admin_label(self):
        if is_admin():
            self.lbl_admin_top.setText("管理员")
            self.lbl_admin_top.setObjectName("AdminOk")
            self.lbl_admin.setText("管理员")
        else:
            self.lbl_admin_top.setText("普通用户")
            self.lbl_admin_top.setObjectName("AdminNo")
            self.lbl_admin.setText("普通用户")
        self.lbl_admin_top.style().unpolish(self.lbl_admin_top)
        self.lbl_admin_top.style().polish(self.lbl_admin_top)

    def _on_nav_changed(self, row):
        self.stack.setCurrentIndex(row)
        if row == self.NAV_ENGINES:
            self.page_engines.refresh()
        elif row == self.NAV_BIOS:
            self.page_bios.refresh()
        elif row == self.NAV_LIBRARY:
            self.page_library.refresh_grid()

    def _reload_games(self):
        self.page_library.set_games(load_games())

    def _refresh_all(self):
        self._engines_json = load_engines_json()
        self.page_engines.refresh()
        self.page_bios.refresh()
        self._reload_games()
        self.status.showMessage("已刷新")

    def _import_engine(self):
        dlg = ImportDialog("engine", self._engines_json, self)
        dlg.exec()
        self.page_engines.refresh()

    def _download_engine(self):
        dlg = DownloadDialog(self._engines_json, self)
        dlg.exec()
        self.page_engines.refresh()

    def _import_game(self):
        dlg = ImportDialog("game", self._engines_json, self)
        dlg.exec()
        self._reload_games()

    def _config_launch(self, game: GameEntry):
        dlg = LaunchConfigDialog(game, self)
        if dlg.exec() != QDialog.Accepted:
            return
        result = dlg.result_data()
        if not result:
            return
        games = load_games()
        for g in games:
            if g.path == game.path:
                g.override_platform = result["override_platform"]
                g.override_engine = result["override_engine"]
                g.extra_args = result["extra_args"]
                break
        save_games(games)
        self._reload_games()
        self.status.showMessage(f"已保存 {game.name} 的启动配置")

    def _resolve_engine(self, game: GameEntry) -> Optional[EmulatorConfig]:
        installed = load_installed()
        if not installed:
            return None
        if game.override_engine:
            try:
                plat, eng = game.override_engine.split("/", 1)
                for e in installed:
                    if e.platform == plat and e.engine == eng:
                        return e
            except Exception:
                pass
        target_platform = game.override_platform or game.platform
        candidates = [e for e in installed if e.platform == target_platform]
        if not candidates:
            if game.override_platform:
                candidates = [e for e in installed if e.platform == game.platform]
            if not candidates:
                return None
        if len(candidates) == 1:
            return candidates[0]
        items = [f"{e.platform_name} / {e.engine} {e.version}".strip()
                 for e in candidates]
        choice, ok = QInputDialog.getItem(self, tr("launch_select_engine"),
                                          tr("launch_select_engine"),
                                          items, 0, False)
        if not ok:
            return None
        return candidates[items.index(choice)]

    def _launch_game(self, game: GameEntry):
        engine = self._resolve_engine(game)
        if not engine:
            QMessageBox.warning(
                self, tr("msg_warning"),
                tr("launch_no_engine",
                   platform=PLATFORM_LABELS.get(game.platform, game.platform)))
            return
        try:
            proc, switched = launch_game(engine, game)
            msg = tr("launch_ok", name=game.name)
            if switched:
                msg += "  (" + tr("launch_cue_hint") + ")"
            self.status.showMessage(msg)
            games = load_games()
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            for g in games:
                if g.path == game.path:
                    g.last_played = now
                    break
            save_games(games)
            self._reload_games()
            if HAS_PSUTIL and proc:
                monitor = ProcessMonitorWorker(proc.pid)
                monitor.finished.connect(
                    lambda secs, gp=game.path: self._on_game_closed(gp, secs))
                monitor.start()
                self._monitor_workers.append(monitor)
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("launch_failed", err=str(e)))

    def _on_game_closed(self, game_path: str, seconds: int):
        try:
            games = load_games()
            for g in games:
                if g.path == game_path:
                    g.play_seconds += seconds
                    break
            save_games(games)
            self._reload_games()
            logger.info(f"游戏关闭: {game_path} 本次 {seconds}s")
        except Exception as e:
            logger.exception(f"保存游戏时间失败: {e}")

    def _open_game_folder(self, game: GameEntry):
        folder = str(Path(game.path).parent)
        if os.path.isdir(folder):
            os.startfile(folder)

    def _open_save_dir(self, game: GameEntry):
        installed = load_installed()
        target_platform = game.override_platform or game.platform
        engines = [e for e in installed if e.platform == target_platform]
        if not engines:
            QMessageBox.information(self, tr("msg_info"), "没有可用的模拟器")
            return
        for e in engines:
            p = get_save_path(e.engine)
            if p:
                os.startfile(str(p))
                return
        QMessageBox.information(self, tr("msg_info"),
                                "没配置存档路径。到「设置 → 存档路径配置」里设置。")

    def _remove_game(self, game: GameEntry):
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     tr("ctx_remove_confirm", name=game.name),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        games = load_games()
        games = [g for g in games if g.path != game.path]
        save_games(games)
        self._reload_games()

    def _toggle_favorite(self, game: GameEntry):
        games = load_games()
        for g in games:
            if g.path == game.path:
                g.favorite = not g.favorite
                break
        save_games(games)
        self._reload_games()

    def _set_cover(self, game: GameEntry):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("ctx_set_cover"), str(DATA_DIR),
            "图片 (*.png *.jpg *.jpeg *.webp);;所有文件 (*)")
        if not fp:
            return
        src = Path(fp)
        ext = src.suffix.lower()
        dst = COVER_DIR / f"{game.name}{ext}"
        try:
            shutil.copy2(src, dst)
            for e in (".png", ".jpg", ".jpeg", ".webp"):
                old = COVER_DIR / f"{game.name}{e}"
                if old.exists() and old != dst:
                    old.unlink()
            self._reload_games()
            self.status.showMessage(f"封面已设置: {dst.name}")
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

    def _on_lang_changed(self, lang: str):
        name = "简体中文" if lang == "zh" else "English"
        QMessageBox.information(self, tr("msg_info"),
                                tr("lang_changed_msg", lang=name))

    def _load_lang(self):
        load_lang()


# ============================================================
# 26. 入口
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(WIN11_QSS)
    app.setApplicationName(APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()