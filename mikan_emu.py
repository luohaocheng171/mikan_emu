# -*- coding: utf-8 -*-
"""
mikan_emu v1.8.0
模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言 + 平台编辑器
+ 性能监控 + 局域网聊天/文件/共享 + 局域网传输（内嵌 LocalSend Web）
+ 封面刮削（Libretro / SteamGridDB）+ 性能档位 + 系统优先级
+ 版本适配（version_overrides）+ 打开模拟器设置
+ 引擎共享定义（_shared）+ BIOS 自动归类 + 统一代理 + 插件系统
+ 日志环形缓冲 + 崩溃诊断包 + Windows 版本检测 + 硬件探测 + 资源策略
+ ★ v1.8.0：
  - ★ Job Object 托管模拟器子进程（主程序退出时自动清理，防孤儿）
  - ★ 低级键盘钩子 KeyMapper（按键重映射，仅对模拟器子进程生效）
  - ★ 模拟器参数 schema（动态表单，支持所有可调参数）
  - ★ GitHub Releases 全量拉取（用户选版本 + 镜像加速开关）
  - ★ 统计图表悬停显示精确时间（tooltip）
  - ★ 平台列改为 QStyledItemDelegate（修复 UI 错位）
  - ★ MikanAPI 新增 keymap / job 子 API

Python 3.11+ / PySide6 / requests / loguru / py7zr / rarfile / psutil / packaging
可选：PySide6-WebEngine（内嵌浏览器）、PySocks（SOCKS5 代理）

项目地址: https://github.com/luohaocheng171/mikan_emu

【法律】不提供 BIOS、不提供 ROM、不二次分发模拟器
"""

import os

# ★ P1-14：Chromium flags 根据系统版本设置
def _setup_webengine_flags():
    flags = ["--disable-gpu", "--disable-software-rasterizer"]
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            try:
                val, _ = winreg.QueryValueEx(key, "CurrentBuild")
                build = int(str(val))
            finally:
                winreg.CloseKey(key)
            if build and build < 7601:
                flags.extend([
                    "--no-sandbox",
                    "--single-process",
                    "--disable-features=NetworkService",
                ])
        except Exception:
            pass
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", " ".join(flags))


import sys
if sys.platform == "win32":
    try:
        _setup_webengine_flags()
    except Exception:
        os.environ.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "--disable-gpu --disable-software-rasterizer")
else:
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu --disable-software-rasterizer")

os.environ["MEDNAFEN_ALLOWMULTI"] = "1"

# ============================================================
# 1. 依赖自检
# ============================================================
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
    "packaging": "packaging",
    "socks": "PySocks",
}

OPTIONAL = {
    "PySide6.QtWebEngineWidgets": "PySide6-WebEngine",
    "keyboard": "keyboard",          # ★ v1.8.0：虚拟按键映射（可选）
}

MIRRORS_PIP = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.org/simple",
]

OPTIONAL_MISSING: dict = {}


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
        for m in MIRRORS_PIP:
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


def _check_optional() -> dict:
    global OPTIONAL_MISSING
    OPTIONAL_MISSING = {}
    for mod, pkg in OPTIONAL.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            OPTIONAL_MISSING[mod] = pkg
    if OPTIONAL_MISSING:
        print(f"[启动] 可选依赖未安装: {list(OPTIONAL_MISSING.values())}")
        for pkg in OPTIONAL_MISSING.values():
            print(f"           pip install {pkg}")
    return OPTIONAL_MISSING


def install_optional_package(pkg: str, parent_widget=None) -> bool:
    if pkg not in OPTIONAL.values():
        return False
    try:
        subprocess.Popen(
            [sys.executable, "-m", "pip", "install", pkg,
             "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
            creationflags=(
                subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            ),
        )
        return True
    except Exception as e:
        print(f"[安装] 启动失败: {e}")
        return False


_ensure_deps()
_check_optional()

# ============================================================
# 2. 导入
# ============================================================
import ctypes
import ctypes.wintypes as wt
import functools
import hashlib
import importlib.util
import json
import platform as _platform
import re
import shlex
import shutil
import socket
import subprocess as sp
import tarfile
import tempfile
import threading
import time
import traceback
import uuid as _uuid
import webbrowser
import zipfile
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Any, Callable
from urllib.parse import urlparse, quote

import requests
import urllib3
from loguru import logger

from packaging.version import Version, InvalidVersion
from packaging.specifiers import SpecifierSet, InvalidSpecifier

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import keyboard as kb
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    kb = None

try:
    from PySide6.QtCore import (
        Qt, QThread, Signal, QModelIndex, QAbstractTableModel,
        QSortFilterProxyModel, QTimer, QSize, QObject, QPoint, QUrl,
        QRect, QEvent, QRectF,
    )
    from PySide6.QtGui import (
        QColor, QFont, QAction, QPixmap, QIcon, QPainter, QPen,
        QBrush, QLinearGradient, QPolygon, QPalette, QKeySequence,
        QMouseEvent, QFontMetrics, QStandardItemModel, QStandardItem,
    )
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QListWidget, QListWidgetItem, QStackedWidget, QLabel,
        QLineEdit, QPushButton, QTableView, QHeaderView, QComboBox,
        QStatusBar, QMessageBox, QFrame, QFileDialog, QGridLayout,
        QProgressBar, QGroupBox, QFormLayout, QCheckBox, QTextEdit,
        QDialog, QDialogButtonBox, QMenu, QToolButton, QTabWidget,
        QScrollArea, QInputDialog, QAbstractItemView, QSpinBox,
        QListView, QRadioButton, QButtonGroup, QSystemTrayIcon,
        QTableWidget, QTableWidgetItem, QSizePolicy, QColorDialog,
        QStyledItemDelegate, QStyleOptionViewItem, QStyle,
        QStyleOptionComboBox, QApplication as QApp,
    )
    HAS_QT = True
except ImportError:
    HAS_QT = False
    print("[启动] PySide6 导入失败，请检查安装。")
    sys.exit(1)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEngineView = None
    QWebEngineSettings = None
    QWebEngineProfile = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# 3. 路径 & 常量
# ============================================================
APP_NAME = "mikan_emu"
APP_VERSION = "1.8.0"
APP_REPO = "https://github.com/luohaocheng171/mikan_emu"

RETRO_DOCS_URL = "https://nostalibrary.tzengyuxio.me/"

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / APP_NAME
CONFIG_DIR = DATA_DIR / "config"
LANG_DIR = CONFIG_DIR / "lang"
ENGINE_DIR = DATA_DIR / "engines"
ENGINE_DOWNLOAD_DIR = ENGINE_DIR / "downloaded"
BIOS_DIR = DATA_DIR / "bios"
ROM_DIR = DATA_DIR / "roms"
SAVE_DIR = DATA_DIR / "saves"
SAVE_BACKUP_DIR = DATA_DIR / "saves_backup"
COVER_DIR = DATA_DIR / "covers"
CHEAT_DIR = DATA_DIR / "cheats"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
TEMP_DIR = DATA_DIR / "temp"
EXPORT_DIR = DATA_DIR / "exports"
LAN_DIR = DATA_DIR / "lan"
LAN_HISTORY_DIR = LAN_DIR / "history"
LAN_FILES_DIR = LAN_DIR / "received"
LAN_SHARED_DIR = LAN_DIR / "shared"
LAN_SHARED_DOWNLOAD_DIR = LAN_DIR / "shared_download"
WEBENGINE_DIR = DATA_DIR / "webengine"
SCRAPE_CACHE_DIR = DATA_DIR / "scrape_cache"
PLUGINS_DIR = DATA_DIR / "plugins"
PLUGIN_STORAGE_DIR = DATA_DIR / "plugin_storage"
CRASH_REPORT_DIR = DATA_DIR / "crash_reports"
BACKGROUND_DIR = DATA_DIR / "backgrounds"

for d in (DATA_DIR, CONFIG_DIR, LANG_DIR, ENGINE_DIR, ENGINE_DOWNLOAD_DIR,
          BIOS_DIR, ROM_DIR, SAVE_DIR, SAVE_BACKUP_DIR, COVER_DIR,
          CHEAT_DIR, BACKUP_DIR, LOG_DIR, TEMP_DIR, EXPORT_DIR,
          LAN_DIR, LAN_HISTORY_DIR, LAN_FILES_DIR, LAN_SHARED_DIR,
          LAN_SHARED_DOWNLOAD_DIR, WEBENGINE_DIR, SCRAPE_CACHE_DIR,
          PLUGINS_DIR, PLUGIN_STORAGE_DIR, CRASH_REPORT_DIR,
          BACKGROUND_DIR):
    d.mkdir(parents=True, exist_ok=True)

FOLDERS_FILE = CONFIG_DIR / "folders.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
LANG_FILE = CONFIG_DIR / "lang.json"
SAVE_PATHS_FILE = CONFIG_DIR / "save_paths.json"
MIRRORS_FILE = CONFIG_DIR / "mirrors.json"
CHEAT_PATHS_FILE = CONFIG_DIR / "cheat_paths.json"
STATS_FILE = CONFIG_DIR / "stats.json"
UPDATE_IGNORE_FILE = CONFIG_DIR / "update_ignore.json"
RESOURCES_FILE = CONFIG_DIR / "resources.json"
ENGINES_JSON = ENGINE_DIR / "engines.json"
INSTALLED_FILE = ENGINE_DIR / "installed.json"
ROMS_FILE = ROM_DIR / "roms.json"
LAN_IDENTITY_FILE = LAN_DIR / "identity.json"
BIOS_DB_FILE = CONFIG_DIR / "bios_db.json"
PLUGINS_ENABLED_FILE = CONFIG_DIR / "plugins_enabled.json"
KEYMAP_FILE = CONFIG_DIR / "keymap.json"       # ★ v1.8.0：按键映射
KEYMAP_GAMES_FILE = CONFIG_DIR / "keymap_games.json"  # ★ 按游戏覆盖

# ============================================================
# 3.1 日志初始化（环形缓冲 + 文件 + stderr）
# ============================================================
LOG_RING: deque = deque(maxlen=2000)
LOG_RING_LOCK = threading.Lock()
_LOG_SETUP_LOCK = threading.Lock()


def _ring_sink(message):
    try:
        r = message.record
        LOG_RING.append({
            "ts": r["time"].strftime("%H:%M:%S"),
            "full_ts": r["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "level": r["level"].name,
            "name": r["name"],
            "line": r["line"],
            "msg": r["message"],
        })
    except Exception:
        pass


def setup_logging():
    with _LOG_SETUP_LOCK:
        level = "INFO"
        keep = 14
        try:
            if "SETTINGS" in globals():
                level = SETTINGS.get("log_level", "INFO")
                keep = int(SETTINGS.get("log_keep_days", 14))
        except Exception:
            pass

        try:
            logger.remove()
        except Exception:
            pass

        try:
            logger.add(
                LOG_DIR / "mikan_emu_{time:YYYY-MM-DD}.log",
                rotation="10 MB",
                retention=f"{keep} days",
                encoding="utf-8",
                level="DEBUG",
                enqueue=True,
            )
        except Exception as e:
            print(f"[启动] 日志文件初始化失败: {e}")

        try:
            logger.add(_ring_sink, level=level)
        except Exception:
            pass

        if sys.stderr is not None:
            try:
                logger.add(sys.stderr, level=level)
            except Exception:
                pass


setup_logging()

if not HAS_WEBENGINE:
    logger.warning("QtWebEngine 未安装，「局域网传输」和「老游戏资料」页将降级为外部浏览器模式")
if not HAS_KEYBOARD:
    logger.warning("keyboard 库未安装，虚拟按键映射不可用（pip install keyboard）")

# ============================================================
# 3.5 内置默认 JSON 数据
# ============================================================
# ★ v1.8.0：每个引擎加 param_schema 字段，定义可调参数
#   字段：key / label / type / default / args_template / options(可选)
#   type: text / int / bool / choice / file / dir
DEFAULT_ENGINES_JSON_STR = r"""
{
  "_shared": {
    "mednafen": {
      "version": "1.32.1",
      "url": "https://mednafen.github.io/releases/files/mednafen-1.32.1-win64.zip",
      "url_type": "direct",
      "archive": "zip",
      "match": {"exe": ["mednafen.exe"], "folder": ["mednafen"], "keywords": ["mednafen"]},
      "launch_template": "{exe} \"{rom}\"",
      "settings_args": "",
      "perf_profiles": {"省电": "", "平衡": "", "高性能": "", "画质优先": ""},
      "official": true,
      "param_schema": [
        {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fs 1"},
        {"key": "video_driver", "label": "视频驱动", "type": "choice", "default": "default",
         "options": ["default", "opengl", "sdl", "softfb"], "args_template": "-video.driver {value}"},
        {"key": "sound_driver", "label": "音频驱动", "type": "choice", "default": "default",
         "options": ["default", "sdl", "oss", "jack"], "args_template": "-sound.driver {value}"},
        {"key": "sound_volume", "label": "音量(0-100)", "type": "int", "default": 100,
         "min": 0, "max": 100, "args_template": "-sound.volume {value}"},
        {"key": "fps_scale", "label": "帧率倍率", "type": "choice", "default": "1",
         "options": ["1", "2", "3"], "args_template": "-fps.autoenable 0 -fps.scale {value}"}
      ]
    },
    "mame": {
      "version": "0.289",
      "url": "https://github.com/mamedev/mame/releases/download/mame0289/mame0289b_x64.exe",
      "url_type": "direct",
      "github_repo": "mamedev/mame",
      "archive": "7z_sfx",
      "match": {"exe": ["mame.exe", "mame64.exe"], "folder": ["mame", "MAME"], "keywords": ["mame"]},
      "launch_template": "{exe} \"{rom}\"",
      "settings_args": "",
      "perf_profiles": {
        "省电": "-nothrottle -frameskip 2",
        "平衡": "",
        "高性能": "-nothrottle",
        "画质优先": "-nothrottle"
      },
      "official": true,
      "param_schema": [
        {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-nowindow"},
        {"key": "skip_gameinfo", "label": "跳过游戏信息", "type": "bool", "default": true, "args_template": "-skip_gameinfo"},
        {"key": "window", "label": "窗口模式", "type": "bool", "default": true, "args_template": "-window"},
        {"key": "frameskip", "label": "跳帧(0-10)", "type": "int", "default": 0, "min": 0, "max": 10, "args_template": "-frameskip {value}"},
        {"key": "samplerate", "label": "采样率", "type": "choice", "default": "48000",
         "options": ["22050", "44100", "48000", "96000"], "args_template": "-samplerate {value}"},
        {"key": "video", "label": "视频后端", "type": "choice", "default": "auto",
         "options": ["auto", "bgfx", "d3d", "opengl", "soft"], "args_template": "-video {value}"}
      ]
    },
    "retroarch": {
      "version": "1.22.2",
      "url": "https://buildbot.libretro.com/stable/1.22.2/windows/x86_64/RetroArch.7z",
      "url_type": "direct",
      "archive": "7z",
      "match": {"exe": ["retroarch.exe"], "folder": ["RetroArch", "retroarch"], "keywords": ["retroarch"]},
      "launch_template": "{exe} -L \"{core}\" \"{rom}\"",
      "settings_args": "",
      "perf_profiles": {
        "省电": "--menu",
        "平衡": "",
        "高性能": "--fullscreen",
        "画质优先": "--fullscreen --set-shader"
      },
      "official": true,
      "note": "libretro 前端，配合核心使用",
      "param_schema": [
        {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-f"},
        {"key": "verbose", "label": "详细日志", "type": "bool", "default": false, "args_template": "-v"},
        {"key": "config", "label": "配置文件", "type": "file", "default": "", "args_template": "--appendconfig=\"{value}\""},
        {"key": "core_config", "label": "核心配置", "type": "file", "default": "", "args_template": "-c \"{value}\""}
      ]
    }
  },

  "sfc": {
    "platform_name": "SFC / 超级任天堂",
    "rom_extensions": [".sfc", ".smc", ".fig", ".swc"],
    "engines": {
      "snes9x": {
        "version": "1.63",
        "url": "https://github.com/snes9xgit/snes9x/releases/download/1.63/snes9x-1.63-win32-x64.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["snes9x-x64.exe", "snes9x.exe"], "folder": ["snes9x"], "keywords": ["snes9x", "snes"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {
          "省电": "--frameskip 2",
          "平衡": "",
          "高性能": "--fullscreen",
          "画质优先": "--fullscreen"
        },
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fullscreen"},
          {"key": "frameskip", "label": "跳帧(0-9)", "type": "int", "default": 0, "min": 0, "max": 9, "args_template": "-frameskip {value}"},
          {"key": "sound_rate", "label": "采样率", "type": "choice", "default": "32000",
           "options": ["8000", "11025", "22050", "32000", "44100", "48000"], "args_template": "-soundrate {value}"},
          {"key": "rewind", "label": "启用回放", "type": "bool", "default": false, "args_template": "-rewind"}
        ]
      },
      "bsnes": {
        "version": "115",
        "url": "https://github.com/bsnes-emu/bsnes/releases/download/v115/bsnes_v115-windows.zip",
        "url_type": "direct",
        "github_repo": "bsnes-emu/bsnes",
        "archive": "zip",
        "match": {"exe": ["bsnes.exe"], "folder": ["bsnes"], "keywords": ["bsnes"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {
          "省电": "",
          "平衡": "",
          "高性能": "--fullscreen",
          "画质优先": "--fullscreen"
        },
        "official": true,
        "note": "精度优先，对 CPU 要求高",
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"},
          {"key": "no_audio", "label": "静音", "type": "bool", "default": false, "args_template": "--no-audio"}
        ]
      }
    }
  },

  "ps1": {
    "platform_name": "PS1 / PlayStation",
    "rom_extensions": [".bin", ".cue", ".iso", ".chd", ".pbp", ".img"],
    "engines": {
      "duckstation": {
        "version": "latest",
        "url": "https://github.com/stenzek/duckstation/releases/download/latest/duckstation-windows-x64-release.zip",
        "url_type": "direct",
        "github_repo": "stenzek/duckstation",
        "archive": "zip",
        "match": {"exe": ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt-x64-Release.exe", "duckstation-qt-x64-Debug.exe", "duckstation.exe"], "folder": ["duckstation"], "keywords": ["duckstation"]},
        "launch_template": "{exe} -batch \"{rom}\"",
        "settings_args": "-settings",
        "perf_profiles": {
          "省电": "-batch --renderer software",
          "平衡": "-batch",
          "高性能": "-batch --fullscreen",
          "画质优先": "-batch --fullscreen --renderer vulkan"
        },
        "version_overrides": [
          {
            "range": "<0.1.0",
            "launch_template": "{exe} -batch \"{rom}\"",
            "settings_args": "-settings"
          }
        ],
        "bios_dir": "bios",
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fullscreen"},
          {"key": "renderer", "label": "渲染器", "type": "choice", "default": "auto",
           "options": ["auto", "d3d11", "d3d12", "vulkan", "opengl", "software"], "args_template": "-renderer {value}"},
          {"key": "resolution", "label": "内部分辨率", "type": "choice", "default": "1",
           "options": ["1", "2", "3", "4", "5", "6", "8", "16"], "args_template": "-resolution {value}"},
          {"key": "no_gui", "label": "无界面", "type": "bool", "default": true, "args_template": "-nogui"},
          {"key": "batch", "label": "批处理模式", "type": "bool", "default": true, "args_template": "-batch"}
        ]
      },
      "epsxe": {
        "version": "2.0.18",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://www.epsxe.com/",
        "archive": "7z",
        "match": {"exe": ["ePSXe.exe"], "folder": ["ePSXe", "epsxe"], "keywords": ["epsxe"]},
        "launch_template": "{exe} -nogui -loadiso \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "闭源，需手动下载",
        "param_schema": [
          {"key": "nogui", "label": "无界面", "type": "bool", "default": true, "args_template": "-nogui"},
          {"key": "loadiso", "label": "加载 ISO", "type": "bool", "default": true, "args_template": "-loadiso"},
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fullscreen"}
        ]
      },
      "xebra": {
        "version": "221106",
        "url": "manual",
        "url_type": "manual",
        "official_site": "http://drhell.web.fc2.com/ps1/",
        "archive": "zip",
        "match": {"exe": ["xebra.exe", "XEBRA.exe"], "folder": ["xebra", "XEBRA"], "keywords": ["xebra"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "闭源，需手动下载",
        "param_schema": []
      }
    }
  },

  "ss": {
    "platform_name": "SS / 世嘉土星",
    "rom_extensions": [".bin", ".cue", ".iso", ".chd", ".mds", ".mdf"],
    "engines": {
      "mednafen": {
        "use_shared": "mednafen",
        "bios_required": true,
        "bios_files": ["mpr-17933.bin", "sega_101.bin"],
        "bios_dir": "firmware"
      },
      "ssf": {
        "version": "PreviewVer R38",
        "url": "manual",
        "url_type": "manual",
        "official_site": "http://redlotusflame.uupan.net/",
        "archive": "7z",
        "match": {"exe": ["SSF.exe", "SSF_PreviewVer.exe"], "folder": ["SSF", "SSF_PreviewVer"], "keywords": ["ssf"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "闭源，需手动下载",
        "param_schema": []
      },
      "ymir": {
        "version": "0.3.3",
        "url": "https://github.com/ymir-emu/Ymir/releases/download/v0.3.3/ymir-windows-x86_64-SSE2-v0.3.3.zip",
        "url_type": "direct",
        "github_repo": "ymir-emu/Ymir",
        "archive": "zip",
        "match": {"exe": ["Ymir.exe", "ymir.exe"], "folder": ["Ymir", "ymir"], "keywords": ["ymir"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_files": ["sega_101.bin", "mpr-17933.bin"],
        "bios_dir": "roms",
        "official": true,
        "note": "需要 IPL ROM + CD Block ROM",
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"}
        ]
      },
      "brimir": {
        "version": "0.5.4",
        "url": "https://github.com/coredds/brimir/releases/download/v0.5.4/brimir-v0.5.4-windows-x64.zip",
        "url_type": "libretro",
        "libretro_core": "brimir_libretro.dll",
        "archive": "zip",
        "match": {"exe": ["brimir_libretro.dll"], "keywords": ["brimir"]},
        "launch_template": "{retroarch} -L \"{core}\" \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "libretro 核心，需 RetroArch",
        "param_schema": []
      }
    }
  },

  "dc": {
    "platform_name": "DC / Dreamcast",
    "rom_extensions": [".gdi", ".cdi", ".chd", ".cue", ".bin", ".iso", ".mds"],
    "engines": {
      "flycast": {
        "version": "2.7",
        "url": "https://github.com/flyinghead/flycast/releases/download/v2.7/flycast-win64-2.7.zip",
        "url_type": "direct",
        "github_repo": "flyinghead/flycast",
        "archive": "zip",
        "match": {"exe": ["flycast.exe", "Flycast.exe"], "folder": ["flycast", "Flycast"], "keywords": ["flycast"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "", "平衡": "", "高性能": "", "画质优先": ""},
        "bios_required": true,
        "bios_files": ["dc_boot.bin", "dc_flash.bin"],
        "bios_dir": "data",
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fullscreen"},
          {"key": "no_audio", "label": "静音", "type": "bool", "default": false, "args_template": "-noaudio"}
        ]
      },
      "redream": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://redream.io/",
        "archive": "zip",
        "match": {"exe": ["redream.exe", "Redream.exe"], "folder": ["redream", "Redream"], "keywords": ["redream"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_files": ["dc_boot.bin", "dc_flash.bin"],
        "bios_dir": "bios",
        "official": false,
        "note": "闭源，需手动下载",
        "param_schema": []
      },
      "deecy": {
        "version": "0.6.3",
        "url": "https://github.com/Senryoku/Deecy/releases/download/v0.6.3/Deecy-x86_64_v4-windows.zip",
        "url_type": "direct",
        "github_repo": "Senryoku/Deecy",
        "archive": "zip",
        "match": {"exe": ["deecy.exe", "Deecy.exe"], "folder": ["deecy", "Deecy"], "keywords": ["deecy"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "Zig 实验性项目",
        "param_schema": []
      }
    }
  },

  "vmu": {
    "platform_name": "VMU / 记忆卡",
    "rom_extensions": [".vmu", ".vms", ".dci"],
    "engines": {
      "dreampotato": {
        "version": "0.3.1",
        "url": "https://github.com/RikkiGibson/DreamPotato/releases/download/v0.3.1/DreamPotato-Windows-x64-v0.3.1.zip",
        "url_type": "direct",
        "github_repo": "RikkiGibson/DreamPotato",
        "archive": "zip",
        "match": {"exe": ["DreamPotato.exe", "dreampotato.exe"], "folder": ["DreamPotato", "dreampotato"], "keywords": ["dreampotato"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": []
      }
    }
  },

  "gba": {
    "platform_name": "GBA",
    "rom_extensions": [".gba", ".agb"],
    "engines": {
      "mgba": {
        "version": "0.10.5",
        "url": "https://github.com/mgba-emu/mgba/releases/download/0.10.5/mGBA-0.10.5-win64.7z",
        "url_type": "direct",
        "github_repo": "mgba-emu/mgba",
        "archive": "7z",
        "match": {"exe": ["mGBA.exe", "mgba.exe", "mgba-qt.exe"], "folder": ["mgba", "mGBA"], "keywords": ["mgba"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {
          "省电": "",
          "平衡": "",
          "高性能": "--fullscreen",
          "画质优先": "--fullscreen"
        },
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"},
          {"key": "no_gui", "label": "无界面", "type": "bool", "default": false, "args_template": "-g"}
        ]
      },
      "vba-m": {
        "version": "2.2.3",
        "url": "https://github.com/visualboyadvance-m/visualboyadvance-m/releases/download/v2.2.3/visualboyadvance-m-Win-x86_64.zip",
        "url_type": "direct",
        "github_repo": "visualboyadvance-m/visualboyadvance-m",
        "archive": "zip",
        "match": {"exe": ["visualboyadvance-m.exe", "vbam.exe", "VisualBoyAdvance-M.exe"], "folder": ["visualboyadvance-m", "vbam"], "keywords": ["visualboyadvance", "vbam"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fullscreen"}
        ]
      }
    }
  },

  "ps2": {
    "platform_name": "PS2 / PlayStation 2",
    "rom_extensions": [".iso", ".bin", ".cue", ".chd", ".gz"],
    "engines": {
      "pcsx2": {
        "version": "2.8.2",
        "url": "https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-windows-x64-Qt.7z",
        "url_type": "direct",
        "github_repo": "PCSX2/pcsx2",
        "archive": "7z",
        "match": {"exe": ["pcsx2-qt.exe", "pcsx2.exe"], "folder": ["pcsx2"], "keywords": ["pcsx2"]},
        "launch_template": "{exe} -batch \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {
          "省电": "-batch --renderer software",
          "平衡": "-batch",
          "高性能": "-batch --fullscreen",
          "画质优先": "-batch --fullscreen --renderer vulkan"
        },
        "version_overrides": [
          {
            "range": "<2.0.0",
            "launch_template": "{exe} --batch \"{rom}\"",
            "settings_args": ""
          }
        ],
        "bios_required": true,
        "bios_dir": "bios",
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fullscreen"},
          {"key": "renderer", "label": "渲染器", "type": "choice", "default": "auto",
           "options": ["auto", "d3d11", "d3d12", "vulkan", "opengl", "software"], "args_template": "-renderer {value}"},
          {"key": "nogui", "label": "无界面", "type": "bool", "default": true, "args_template": "-nogui"},
          {"key": "batch", "label": "批处理", "type": "bool", "default": true, "args_template": "-batch"}
        ]
      }
    }
  },

  "fc": {
    "platform_name": "FC / NES",
    "rom_extensions": [".nes", ".fds", ".unf", ".unif"],
    "engines": {
      "fceux": {
        "version": "latest",
        "url": "https://sourceforge.net/projects/fceultra/files/latest/download",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["fceux.exe", "fceux64.exe"], "folder": ["fceux"], "keywords": ["fceux"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {
          "省电": "",
          "平衡": "",
          "高性能": "--fullscreen",
          "画质优先": "--fullscreen"
        },
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"},
          {"key": "nogui", "label": "无界面", "type": "bool", "default": false, "args_template": "--nogui"}
        ]
      },
      "mesence": {
        "version": "2.2.1",
        "url": "https://github.com/nesdev-org/MesenCE/releases/download/2.2.1/Mesen_2.2.1_Windows.zip",
        "url_type": "direct",
        "github_repo": "nesdev-org/MesenCE",
        "archive": "zip",
        "match": {"exe": ["Mesen.exe"], "folder": ["Mesen"], "keywords": ["mesen"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "/fullscreen"}
        ]
      },
      "nestopia": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://nestopia.sourceforge.net/",
        "archive": "zip",
        "match": {"exe": ["nestopia.exe"], "folder": ["nestopia", "Nestopia"], "keywords": ["nestopia"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "SourceForge 无稳定直链，需手动下载",
        "param_schema": []
      },
      "nintendulator": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "http://www.qmtpro.com/~nes/nintendulator/",
        "archive": "zip",
        "match": {"exe": ["Nintendulator.exe", "nintendulator.exe"], "folder": ["Nintendulator"], "keywords": ["nintendulator"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "精度优先，需手动下载",
        "param_schema": []
      }
    }
  },

  "n64": {
    "platform_name": "N64",
    "rom_extensions": [".n64", ".z64", ".v64", ".rom"],
    "engines": {
      "mupen64plus": {
        "version": "2.6.0",
        "url": "https://github.com/mupen64plus/mupen64plus-core/releases/download/2.6.0/mupen64plus-bundle-win64-2.6.0.zip",
        "url_type": "direct",
        "github_repo": "mupen64plus/mupen64plus-core",
        "archive": "zip",
        "match": {"exe": ["mupen64plus-ui-console.exe", "mupen64plus.exe"], "folder": ["mupen64plus"], "keywords": ["mupen64plus", "mupen"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"}
        ]
      },
      "gopher64": {
        "version": "1.1.36",
        "url": "https://github.com/gopher64/gopher64/releases/download/v1.1.36/gopher64-windows-x86_64.exe",
        "url_type": "direct",
        "github_repo": "gopher64/gopher64",
        "archive": "bare_exe",
        "match": {"exe": ["gopher64-windows-x86_64.exe", "gopher64.exe"], "keywords": ["gopher64"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "裸 exe，下载后直接使用",
        "param_schema": []
      },
      "ares": {
        "version": "148",
        "url": "https://github.com/ares-emulator/ares/releases/download/v148/ares-windows-x64.zip",
        "url_type": "direct",
        "github_repo": "ares-emulator/ares",
        "archive": "zip",
        "match": {"exe": ["ares.exe"], "folder": ["ares"], "keywords": ["ares"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "多平台模拟器",
        "param_schema": []
      },
      "simple64": {
        "version": "2024.12.1",
        "url": "https://github.com/simple64/simple64/releases/download/v2024.12.1/simple64-win64-b49e10e.zip",
        "url_type": "direct",
        "github_repo": "simple64/simple64",
        "archive": "zip",
        "match": {"exe": ["simple64-gui.exe", "simple64.exe"], "folder": ["simple64"], "keywords": ["simple64"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"}
        ]
      },
      "rmg": {
        "version": "0.9.0",
        "url": "https://github.com/Rosalie241/RMG/releases/download/v0.9.0/RMG-Portable-Windows64-v0.9.0.zip",
        "url_type": "direct",
        "github_repo": "Rosalie241/RMG",
        "archive": "zip",
        "match": {"exe": ["RMG.exe", "rmg.exe"], "folder": ["RMG", "rmg"], "keywords": ["rmg"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": []
      },
      "neon64": {
        "version": "2.0-beta.4",
        "url": "https://github.com/hcs64/neon64v2/releases/download/v2.0-beta.4/neon64v2b4.zip",
        "url_type": "direct",
        "github_repo": "hcs64/neon64v2",
        "archive": "zip",
        "match": {"exe": ["neon64.exe"], "folder": ["neon64", "neon64v2"], "keywords": ["neon64"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "轻量 N64 模拟器",
        "param_schema": []
      },
      "project64": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://www.pj64-emu.com/",
        "archive": "zip",
        "match": {"exe": ["Project64.exe", "pj64.exe"], "folder": ["Project64", "pj64"], "keywords": ["project64", "pj64"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "需手动下载",
        "param_schema": []
      },
      "cen64": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://github.com/cen64/cen64",
        "archive": "zip",
        "match": {"exe": ["cen64.exe"], "keywords": ["cen64"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "精度优先，无 Windows 预编译包",
        "param_schema": []
      }
    }
  },

  "nds": {
    "platform_name": "NDS",
    "rom_extensions": [".nds", ".dsi", ".ids"],
    "engines": {
      "desmume": {
        "version": "0.9.13",
        "url": "https://github.com/TASEmulators/desmume/releases/download/release_0_9_13/desmume-0.9.13-win64.zip",
        "url_type": "direct",
        "github_repo": "TASEmulators/desmume",
        "archive": "zip",
        "match": {"exe": ["desmume.exe", "DeSmuME.exe"], "folder": ["desmume", "DeSmuME"], "keywords": ["desmume"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"}
        ]
      },
      "melonds": {
        "version": "1.1",
        "url": "https://melonds.kuribo64.net/downloads/melonDS-1.1-windows-x86_64.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["melonDS.exe", "melonds.exe"], "folder": ["melonDS", "melonds"], "keywords": ["melonds"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-fullscreen"}
        ]
      },
      "noods": {
        "version": "latest",
        "url": "https://github.com/Hydr8gon/NooDS/releases/download/release/noods-windows.zip",
        "url_type": "direct",
        "github_repo": "Hydr8gon/NooDS",
        "archive": "zip",
        "match": {"exe": ["noods.exe", "NooDS.exe"], "folder": ["noods", "NooDS"], "keywords": ["noods"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "轻量 NDS/GBA 模拟器",
        "param_schema": []
      }
    }
  },

  "3ds": {
    "platform_name": "3DS",
    "rom_extensions": [".3ds", ".cia", ".cci", ".cxi"],
    "engines": {
      "azahar": {
        "version": "2126.1.2",
        "url": "https://github.com/azahar-emu/azahar/releases/download/2126.1.2/azahar-windows-mxe-2126.1.2.zip",
        "url_type": "direct",
        "github_repo": "azahar-emu/azahar",
        "archive": "zip",
        "match": {"exe": ["azahar.exe", "citra-qt.exe"], "folder": ["azahar", "Azahar"], "keywords": ["azahar"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "", "平衡": "", "高性能": "--fullscreen", "画质优先": "--fullscreen"},
        "official": true,
        "note": "Citra 后继项目",
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-f"}
        ]
      },
      "zakuro": {
        "version": "0.2.9",
        "url": "https://github.com/fearkov/zakuro/releases/download/v0.2.9/zakuro-windows-x86_64.zip",
        "url_type": "direct",
        "github_repo": "fearkov/zakuro",
        "archive": "zip",
        "match": {"exe": ["zakuro.exe"], "folder": ["zakuro"], "keywords": ["zakuro"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "⚠ 实验性：Rust 重写的 3DS 模拟器",
        "param_schema": []
      }
    }
  },

  "md": {
    "platform_name": "MD / Genesis",
    "rom_extensions": [".md", ".gen", ".smd", ".bin", ".32x"],
    "engines": {
      "blastem": {
        "version": "1.0.0",
        "url": "https://www.retrodev.com/blastem/blastem-win64-1.0.0.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["blastem.exe"], "folder": ["blastem"], "keywords": ["blastem"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "-f"}
        ]
      },
      "kega-fusion": {
        "version": "3.64",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://kega-fusion.com/",
        "archive": "zip",
        "match": {"exe": ["Fusion.exe", "Kega Fusion.exe"], "folder": ["Kega Fusion", "Fusion"], "keywords": ["fusion", "kega"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "闭源，需手动下载",
        "param_schema": []
      }
    }
  },

  "sms": {
    "platform_name": "Master System / Game Gear",
    "rom_extensions": [".sms", ".gg", ".sg"],
    "engines": {
      "emulicious": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://emulicious.net/",
        "archive": "zip",
        "match": {"exe": ["Emulicious.exe", "emulicious.exe"], "folder": ["Emulicious", "emulicious"], "keywords": ["emulicious"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "支持 GB/GBC/SMS/GG，需手动下载",
        "param_schema": []
      }
    }
  },

  "gb": {
    "platform_name": "GB / GBC",
    "rom_extensions": [".gb", ".gbc", ".sgb"],
    "engines": {
      "sameboy": {
        "version": "1.0.3",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://github.com/LIJI32/SameBoy/releases",
        "archive": "zip",
        "match": {"exe": ["sameboy.exe", "SameBoy.exe"], "folder": ["sameboy", "SameBoy"], "keywords": ["sameboy"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "挂官网，用户手动下载",
        "param_schema": []
      },
      "bgb": {
        "version": "1.6.5",
        "url": "manual",
        "url_type": "manual",
        "official_site": "http://bgb.bircd.org/",
        "archive": "zip",
        "match": {"exe": ["bgb.exe", "BGB.exe"], "folder": ["bgb", "BGB"], "keywords": ["bgb"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "精度优先，需手动下载",
        "param_schema": []
      },
      "gambatte": {
        "version": "0.5.0",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://github.com/sinamas/gambatte",
        "archive": "zip",
        "match": {"exe": ["gambatte_qt.exe", "gambatte_sdl.exe", "gambatte.exe"], "folder": ["gambatte", "Gambatte"], "keywords": ["gambatte"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "已停更，建议改用 mGBA",
        "param_schema": []
      }
    }
  },

  "psp": {
    "platform_name": "PSP",
    "rom_extensions": [".iso", ".cso", ".pbp"],
    "engines": {
      "ppsspp": {
        "version": "1.20.4",
        "url": "https://github.com/hrydgard/ppsspp/releases/download/v1.20.4/PPSSPP-v1.20.4-Windows-x64.zip",
        "url_type": "direct",
        "github_repo": "hrydgard/ppsspp",
        "archive": "zip",
        "match": {"exe": ["PPSSPPWindows64.exe", "PPSSPPWindows.exe", "PPSSPP.exe"], "folder": ["PPSSPP", "ppsspp"], "keywords": ["ppsspp"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "", "平衡": "", "高性能": "--fullscreen", "画质优先": "--fullscreen"},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"},
          {"key": "graphics", "label": "图形后端", "type": "choice", "default": "auto",
           "options": ["auto", "opengl", "vulkan", "d3d11"], "args_template": "--graphics={value}"}
        ]
      }
    }
  },

  "switch": {
    "platform_name": "Switch",
    "rom_extensions": [".nsp", ".xci", ".nsz", ".xcz"],
    "engines": {
      "ryujinx": {
        "version": "1.3.3",
        "url": "https://git.ryujinx.app/projects/Ryubing/releases/download/1.3.3/ryujinx-1.3.3-win_x64.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["Ryujinx.exe", "ryujinx.exe"], "folder": ["Ryujinx", "ryujinx", "publish"], "keywords": ["ryujinx"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "", "平衡": "", "高性能": "--fullscreen", "画质优先": "--fullscreen"},
        "official": true,
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"}
        ]
      },
      "yuzu": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://github.com/yuzu-mirror",
        "archive": "zip",
        "match": {"exe": ["yuzu.exe", "yuzu-cmd.exe"], "folder": ["yuzu", "Yuzu"], "keywords": ["yuzu"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "已停止分发，只剩社区镜像",
        "param_schema": []
      }
    }
  },

  "pce": {
    "platform_name": "PCE / TurboGrafx",
    "rom_extensions": [".pce", ".sgx"],
    "engines": {
      "mednafen": {"use_shared": "mednafen"},
      "geargrafx": {
        "version": "1.8.2",
        "url": "https://github.com/drhelius/Geargrafx/releases/download/1.8.2/Geargrafx-1.8.2-desktop-windows-x64.zip",
        "url_type": "direct",
        "github_repo": "drhelius/Geargrafx",
        "archive": "zip",
        "match": {"exe": ["Geargrafx.exe", "geargrafx.exe"], "folder": ["Geargrafx", "geargrafx"], "keywords": ["geargrafx"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "PC Engine / SuperGrafx 模拟器",
        "param_schema": []
      }
    }
  },

  "neogeo": {
    "platform_name": "Neo Geo",
    "rom_extensions": [".zip", ".neo"],
    "engines": {
      "mame": {"use_shared": "mame"}
    }
  },

  "arcade": {
    "platform_name": "Arcade",
    "rom_extensions": [".zip", ".7z"],
    "engines": {
      "mame": {"use_shared": "mame"}
    }
  },

  "x68000": {
    "platform_name": "Sharp X68000",
    "rom_extensions": [".dim", ".zip", ".img", ".d88", ".88d", ".hdm", ".dup", ".2hd", ".xdf", ".hdf"],
    "engines": {
      "px68k": {
        "version": "latest",
        "url": "https://github.com/libretro/px68k-libretro",
        "url_type": "libretro",
        "libretro_core": "px68k_libretro.dll",
        "archive": "none",
        "match": {"exe": ["px68k_libretro.dll"], "keywords": ["px68k"]},
        "launch_template": "{retroarch} -L \"{core}\" \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_dir": "keropi",
        "official": true,
        "note": "libretro 核心，BIOS 放 retroarch/system/keropi/",
        "param_schema": []
      }
    }
  },

  "pc98": {
    "platform_name": "NEC PC-98",
    "rom_extensions": [".hdi", ".fdi", ".d98", ".hdm", ".d88", ".zip"],
    "engines": {
      "np2kai": {
        "version": "latest",
        "url": "https://github.com/AZO234/NP2kai",
        "url_type": "libretro",
        "libretro_core": "np2kai_libretro.dll",
        "archive": "none",
        "match": {"exe": ["np2kai_libretro.dll"], "keywords": ["np2kai"]},
        "launch_template": "{retroarch} -L \"{core}\" \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_dir": "np2kai",
        "official": true,
        "note": "libretro 核心，BIOS 放 retroarch/system/np2kai/",
        "param_schema": []
      }
    }
  },

  "fmtowns": {
    "platform_name": "FM Towns",
    "rom_extensions": [".bin", ".cue", ".iso", ".chd", ".d88", ".hdm"],
    "engines": {
      "tsugaru": {
        "version": "20260522",
        "url": "https://github.com/captainys/TOWNSEMU/releases/download/v20260522/windows_binary_latest.zip",
        "url_type": "direct",
        "github_repo": "captainys/TOWNSEMU",
        "archive": "zip",
        "match": {"exe": ["Tsugaru.exe", "tsugaru.exe"], "folder": ["Tsugaru", "tsugaru"], "keywords": ["tsugaru"]},
        "launch_template": "{exe} \"{bios_rom_dir}\" -CD \"{rom}\" -TOWNSTYPE MARTY",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_dir": "rom",
        "official": true,
        "param_schema": []
      }
    }
  },

  "pcfx": {
    "platform_name": "PC-FX",
    "rom_extensions": [".cue", ".bin", ".iso", ".chd"],
    "engines": {
      "pcfxemu": {
        "version": "1.0",
        "url": "https://github.com/gameblabla/pcfxemu/releases/download/1.0/PCFXemu-win32-version121-gbb.zip",
        "url_type": "direct",
        "github_repo": "gameblabla/pcfxemu",
        "archive": "zip",
        "match": {"exe": ["pcfxemu.exe", "PCFXemu.exe"], "folder": ["pcfxemu", "PCFXemu"], "keywords": ["pcfx"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_dir": "bios",
        "official": true,
        "param_schema": []
      }
    }
  },

  "msx": {
    "platform_name": "MSX",
    "rom_extensions": [".rom", ".mx1", ".mx2", ".dsk", ".cas", ".zip"],
    "engines": {
      "openmsx": {
        "version": "21.0",
        "url": "https://github.com/openMSX/openMSX/releases/download/RELEASE_21_0/openmsx-21.0-windows-vc-x64-bin.zip",
        "url_type": "direct",
        "github_repo": "openMSX/openMSX",
        "archive": "zip",
        "match": {"exe": ["openmsx.exe"], "folder": ["openMSX", "openmsx"], "keywords": ["openmsx"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": []
      },
      "bluemsx": {
        "version": "2.8.2",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://www.msxblue.com/",
        "archive": "zip",
        "match": {"exe": ["blueMSX.exe", "bluemsx.exe"], "folder": ["blueMSX", "bluemsx"], "keywords": ["bluemsx"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "挂官网，需手动下载",
        "param_schema": []
      }
    }
  },

  "x86box": {
    "platform_name": "86Box / PC 模拟",
    "rom_extensions": [".86f", ".img", ".ima", ".vfd", ".hdd", ".bin", ".rom"],
    "engines": {
      "86box": {
        "version": "v6.0",
        "url": "https://github.com/86Box/86Box/releases/download/v6.0/86Box-Windows-64-b9001.zip",
        "url_type": "direct",
        "github_repo": "86Box/86Box",
        "archive": "zip",
        "match": {"exe": ["86Box.exe", "86box.exe"], "folder": ["86Box", "86box"], "keywords": ["86box"]},
        "launch_template": "{exe}",
        "settings_args": "",
        "perf_profiles": {},
        "bios_dir": "roms",
        "bios_required": true,
        "official": true,
        "note": "x86 PC 模拟器。BIOS ROM 放 roms/ 子目录",
        "param_schema": []
      }
    }
  },

  "pcem": {
    "platform_name": "PCem / PC 模拟",
    "rom_extensions": [".86f", ".img", ".ima", ".vfd", ".hdd", ".bin", ".rom"],
    "engines": {
      "pcem": {
        "version": "V17",
        "url": "https://github.com/sarah-walker-pcem/pcem/releases/download/v17/PCemV17Win.zip",
        "url_type": "direct",
        "github_repo": "sarah-walker-pcem/pcem",
        "archive": "zip",
        "match": {"exe": ["pcem.exe", "PCem.exe"], "folder": ["PCem", "pcem"], "keywords": ["pcem"]},
        "launch_template": "{exe}",
        "settings_args": "",
        "perf_profiles": {},
        "bios_dir": "roms",
        "bios_required": true,
        "official": true,
        "note": "x86 PC 模拟器。BIOS ROM 放 roms/ 子目录",
        "param_schema": []
      }
    }
  },

  "dos": {
    "platform_name": "DOS",
    "rom_extensions": [".exe", ".com", ".bat", ".img", ".iso", ".zip"],
    "engines": {
      "dosbox-x": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://dosbox-x.com/",
        "archive": "zip",
        "match": {"exe": ["dosbox-x.exe", "DOSBox-X.exe"], "folder": ["dosbox-x", "DOSBox-X"], "keywords": ["dosbox"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "DOSBox-X 官网无稳定直链，需手动下载",
        "param_schema": []
      }
    }
  },

  "ps4": {
    "platform_name": "PS4 / PlayStation 4",
    "rom_extensions": [".pkg", ".iso", ".bin", ".elf", ".self"],
    "engines": {
      "shadps4": {
        "version": "0.18.0",
        "url": "https://github.com/shadps4-emu/shadPS4/releases/download/v.0.18.0/shadps4-win64-sdl-0.18.0.zip",
        "url_type": "direct",
        "github_repo": "shadps4-emu/shadPS4",
        "archive": "zip",
        "match": {"exe": ["shadps4.exe", "shadPS4.exe", "shadPS4QtLauncher.exe"], "folder": ["shadPS4", "shadps4"], "keywords": ["shadps4"]},
        "launch_template": "{exe} -g \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "", "平衡": "", "高性能": "-g", "画质优先": "-g"},
        "official": true,
        "note": "⚠ 实验性：极早期",
        "param_schema": [
          {"key": "game", "label": "游戏路径", "type": "bool", "default": true, "args_template": "-g"}
        ]
      }
    }
  },

  "ps5": {
    "platform_name": "PS5 / PlayStation 5",
    "rom_extensions": [".pkg", ".elf", ".self"],
    "engines": {
      "kytyps5": {
        "version": "2026-09-30",
        "url": "https://github.com/KytyPS5/KytyPS5/releases/download/KytyPS5-2026-09-30-b7a1fac/KytyPS5-2026-09-30-b7a1fac-Windows-x64.zip",
        "url_type": "direct",
        "github_repo": "KytyPS5/KytyPS5",
        "archive": "zip",
        "match": {"exe": ["KytyPS5.exe", "kytyps5.exe"], "folder": ["KytyPS5", "kytyps5"], "keywords": ["kyty"]},
        "launch_template": "{exe} --game \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "⚠ 实验性：极早期",
        "param_schema": []
      }
    }
  },

  "xbox": {
    "platform_name": "初代 Xbox",
    "rom_extensions": [".xiso", ".iso", ".xbe"],
    "engines": {
      "xemu": {
        "version": "0.8.136",
        "url": "https://github.com/xemu-project/xemu/releases/download/v0.8.136/xemu-win-x86_64-release.zip",
        "url_type": "direct",
        "github_repo": "xemu-project/xemu",
        "archive": "zip",
        "match": {"exe": ["xemu.exe"], "folder": ["xemu"], "keywords": ["xemu"]},
        "launch_template": "{exe} -dvd_path \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_dir": "bios",
        "official": true,
        "note": "需要 Xbox BIOS",
        "param_schema": []
      }
    }
  },

  "xbox360": {
    "platform_name": "Xbox 360",
    "rom_extensions": [".iso", ".xex", ".zar", ".god"],
    "engines": {
      "xenia_canary": {
        "version": "canary",
        "url": "https://github.com/xenia-canary/xenia-canary-releases/releases/download/02d2cb5/xenia_canary_windows_.zip",
        "url_type": "direct",
        "github_repo": "xenia-canary/xenia-canary-releases",
        "archive": "zip",
        "match": {"exe": ["xenia_canary.exe", "xenia-canary.exe"], "folder": ["xenia_canary", "xenia-canary", "Xenia Canary"], "keywords": ["xenia_canary", "xenia-canary"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "Canary 分支，主开发分支",
        "param_schema": []
      },
      "xenia_edge": {
        "version": "edge",
        "url": "https://github.com/has207/xenia-edge/releases/download/95b14f5/xenia_edge_windows.zip",
        "url_type": "direct",
        "github_repo": "has207/xenia-edge",
        "archive": "zip",
        "match": {"exe": ["xenia_edge.exe", "xenia-edge.exe", "xenia.exe"], "folder": ["xenia_edge", "xenia-edge", "Xenia Edge"], "keywords": ["xenia_edge", "xenia-edge"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "第三方优化分支",
        "param_schema": []
      }
    }
  },

  "wii": {
    "platform_name": "Wii / GameCube",
    "rom_extensions": [".iso", ".gcm", ".wbfs", ".wad", ".dol", ".elf", ".rvz"],
    "engines": {
      "dolphin": {
        "version": "2506",
        "url": "https://dl.dolphin-emu.org/releases/2506/dolphin-2506-x64.7z",
        "url_type": "direct",
        "github_repo": "dolphin-emu/dolphin",
        "archive": "7z",
        "match": {"exe": ["Dolphin.exe", "dolphin.exe"], "folder": ["Dolphin", "dolphin"], "keywords": ["dolphin"]},
        "launch_template": "{exe} -b -e \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "-b", "平衡": "-b", "高性能": "-b --fullscreen", "画质优先": "-b --fullscreen"},
        "official": true,
        "note": "Wii / GameCube 通用",
        "param_schema": [
          {"key": "batch", "label": "批处理", "type": "bool", "default": true, "args_template": "-b"},
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"},
          {"key": "exec", "label": "直接执行", "type": "bool", "default": true, "args_template": "-e"}
        ]
      }
    }
  },

  "wiiu": {
    "platform_name": "Wii U",
    "rom_extensions": [".wud", ".wux", ".rpx", ".wua"],
    "engines": {
      "cemu": {
        "version": "2.6",
        "url": "https://github.com/cemu-project/Cemu/releases/download/v2.6/cemu-2.6-windows-x64.zip",
        "url_type": "direct",
        "github_repo": "cemu-project/Cemu",
        "archive": "zip",
        "match": {"exe": ["Cemu.exe", "cemu.exe"], "folder": ["Cemu", "cemu"], "keywords": ["cemu"]},
        "launch_template": "{exe} -g \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "", "平衡": "", "高性能": "-g", "画质优先": "-g"},
        "official": true,
        "note": "Wii U 模拟器。需要 keys.txt 和在线更新数据。",
        "param_schema": []
      }
    }
  },

  "ps3": {
    "platform_name": "PS3 / PlayStation 3",
    "rom_extensions": [".pkg", ".iso", ".bin", ".elf", ".self", ".sprx"],
    "engines": {
      "rpcs3": {
        "version": "0.0.38",
        "url": "https://github.com/RPCS3/rpcs3-binaries-win/releases/download/build-9c81f7be/rpcs3-v0.0.38-12345-9c81f7be_win64.zip",
        "url_type": "direct",
        "github_repo": "RPCS3/rpcs3-binaries-win",
        "archive": "zip",
        "match": {"exe": ["rpcs3.exe", "RPCS3.exe"], "folder": ["rpcs3", "RPCS3"], "keywords": ["rpcs3"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {"省电": "", "平衡": "", "高性能": "--fullscreen", "画质优先": "--fullscreen"},
        "bios_required": true,
        "bios_dir": "dev_flash",
        "official": true,
        "note": "需要 PS3 固件",
        "param_schema": [
          {"key": "fullscreen", "label": "全屏", "type": "bool", "default": false, "args_template": "--fullscreen"}
        ]
      }
    }
  },

  "psvita": {
    "platform_name": "PS Vita",
    "rom_extensions": [".vpk", ".mai", ".bin", ".elf"],
    "engines": {
      "vita3k": {
        "version": "0.2.0",
        "url": "https://github.com/Vita3K/Vita3K/releases/download/0.2.0/Vita3K-0.2.0-Windows-x64.zip",
        "url_type": "direct",
        "github_repo": "Vita3K/Vita3K",
        "archive": "zip",
        "match": {"exe": ["Vita3K.exe", "vita3k.exe"], "folder": ["Vita3K", "vita3k"], "keywords": ["vita3k"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_dir": "data",
        "official": true,
        "note": "⚠ 实验性。需要固件和 keys。",
        "param_schema": []
      }
    }
  },

  "cpc": {
    "platform_name": "Amstrad CPC",
    "rom_extensions": [".dsk", ".cdt", ".sna", ".tap", ".cpr"],
    "engines": {
      "amspirit": {
        "version": "Lite-1.16.0",
        "url": "https://github.com/AMSpiriT-Emulator/amspirit-releases/releases/download/Lite-1.16.0/Amspirit-Lite-SDL-1.16.0-win64.zip",
        "url_type": "direct",
        "github_repo": "AMSpiriT-Emulator/amspirit-releases",
        "archive": "zip",
        "match": {"exe": ["Amspirit.exe", "amspirit.exe"], "folder": ["Amspirit", "amspirit"], "keywords": ["amspirit"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": []
      },
      "caprice32": {
        "version": "latest",
        "url": "https://github.com/ColinPitrat/caprice32/releases/download/latest/cap32-win64.zip",
        "url_type": "direct",
        "github_repo": "ColinPitrat/caprice32",
        "archive": "zip",
        "match": {"exe": ["cap32.exe", "caprice32.exe"], "folder": ["caprice32", "cap32"], "keywords": ["caprice"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": []
      },
      "cpc_syntax_error": {
        "version": "0.3.0",
        "url": "https://github.com/WacKEDmaN/CPCSyntaxError/releases/download/v0.3.0/CPCSyntaxError-win64-v0.3.0.zip",
        "url_type": "direct",
        "github_repo": "WacKEDmaN/CPCSyntaxError",
        "archive": "zip",
        "match": {"exe": ["CPCSyntaxError.exe", "cpcsyntaxerror.exe"], "folder": ["CPCSyntaxError"], "keywords": ["cpcsyntax"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "⚠ 实验性：CPC 新模拟器",
        "param_schema": []
      }
    }
  },

  "c64": {
    "platform_name": "Commodore 64",
    "rom_extensions": [".d64", ".d71", ".d81", ".prg", ".tap", ".crt", ".g64", ".x64"],
    "engines": {
      "vice": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://vice-emu.sourceforge.io/",
        "archive": "zip",
        "match": {"exe": ["x64sc.exe", "x64.exe", "xvic.exe", "x128.exe"], "folder": ["VICE", "vice"], "keywords": ["vice", "x64"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "SourceForge 无稳定直链，需手动下载",
        "param_schema": []
      }
    }
  },

  "atarist": {
    "platform_name": "Atari ST",
    "rom_extensions": [".st", ".msa", ".stx", ".img", ".zip"],
    "engines": {
      "hatari": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://www.hatari-emu.org/download.html",
        "archive": "zip",
        "match": {"exe": ["hatari.exe", "Hatari.exe"], "folder": ["hatari", "Hatari"], "keywords": ["hatari"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "需手动下载",
        "param_schema": []
      }
    }
  },

  "atari2600": {
    "platform_name": "Atari 2600",
    "rom_extensions": [".a26", ".bin", ".rom", ".zip"],
    "engines": {
      "stella": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://stella-emu.github.io/",
        "archive": "zip",
        "match": {"exe": ["stella.exe", "Stella.exe"], "folder": ["stella", "Stella"], "keywords": ["stella"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "官网无稳定直链，需手动下载",
        "param_schema": []
      }
    }
  },

  "zxspectrum": {
    "platform_name": "ZX Spectrum",
    "rom_extensions": [".tzx", ".tap", ".z80", ".sna", ".szx", ".trd", ".dsk", ".zip"],
    "engines": {
      "zesarux": {
        "version": "13.0",
        "url": "https://github.com/chernandezba/zesarux/releases/download/ZEsarUX-13.0/ZEsarUX_windows-13.0.zip",
        "url_type": "direct",
        "github_repo": "chernandezba/zesarux",
        "archive": "zip",
        "match": {"exe": ["zesarux.exe", "ZEsarUX.exe"], "folder": ["ZEsarUX", "zesarux"], "keywords": ["zesarux"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": []
      },
      "1984": {
        "version": "0.4.20",
        "url": "https://github.com/salvogendut/1984/releases/download/v0.4.20/1984-v0.4.20-windows-x86_64.zip",
        "url_type": "direct",
        "github_repo": "salvogendut/1984",
        "archive": "zip",
        "match": {"exe": ["1984.exe", "emulator.exe"], "folder": ["1984"], "keywords": ["1984"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "⚠ 实验性：ZX Spectrum 新模拟器",
        "param_schema": []
      }
    }
  },

  "colecovision": {
    "platform_name": "ColecoVision",
    "rom_extensions": [".col", ".rom", ".bin", ".zip"],
    "engines": {
      "gearcoleco": {
        "version": "1.7.3",
        "url": "https://github.com/drhelius/Gearcoleco/releases/download/1.7.3/Gearcoleco-1.7.3-desktop-windows-x64.zip",
        "url_type": "direct",
        "github_repo": "drhelius/Gearcoleco",
        "archive": "zip",
        "match": {"exe": ["Gearcoleco.exe", "gearcoleco.exe"], "folder": ["Gearcoleco", "gearcoleco"], "keywords": ["gearcoleco"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "param_schema": []
      }
    }
  },

  "intellivision": {
    "platform_name": "Intellivision",
    "rom_extensions": [".int", ".bin", ".rom", ".zip"],
    "engines": {
      "jzintv": {
        "version": "2.3.7",
        "url": "https://github.com/jenergy/jzIntvImGui/releases/download/2.3.7/jzIntvImGui_2.3.7.zip",
        "url_type": "direct",
        "github_repo": "jenergy/jzIntvImGui",
        "archive": "zip",
        "match": {"exe": ["jzIntvImGui.exe", "jzintv.exe"], "folder": ["jzIntvImGui", "jzintv"], "keywords": ["jzintv"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "bios_required": true,
        "bios_files": ["exec.bin", "grom.bin"],
        "bios_dir": "rom",
        "official": true,
        "note": "需要 exec.bin / grom.bin",
        "param_schema": []
      }
    }
  },

  "bbcmicro": {
    "platform_name": "BBC Micro",
    "rom_extensions": [".ssd", ".dsd", ".adf", ".uef", ".tap", ".zip"],
    "engines": {
      "b2": {
        "version": "20260322",
        "url": "https://github.com/tom-seddon/b2/releases/download/b2-20260322-193052-51e70d7/symbols.b2-windows-20260322-193052-51e70d7.7z",
        "url_type": "direct",
        "github_repo": "tom-seddon/b2",
        "archive": "7z",
        "match": {"exe": ["b2.exe", "B2.exe"], "folder": ["b2", "B2"], "keywords": ["b2"]},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": true,
        "note": "⚠ 你提供的是符号包，若识别不到主程序请手动导入",
        "param_schema": []
      }
    }
  },

  "unknown": {
    "platform_name": "未知渠道",
    "rom_extensions": [],
    "engines": {
      "google_drive_unknown": {
        "version": "unknown",
        "url": "manual",
        "url_type": "manual",
        "official_site": "https://drive.google.com/file/d/1yqP781y-TJsB_dSBy4EgSKdNZefFdBSA/view",
        "archive": "zip",
        "match": {"exe": []},
        "launch_template": "{exe} \"{rom}\"",
        "settings_args": "",
        "perf_profiles": {},
        "official": false,
        "note": "来源不明，手动下载",
        "param_schema": []
      }
    }
  }
}
"""


DEFAULT_FOLDERS_JSON = {
    "folders": [
        {"name": "默认工作区", "path": str(DATA_DIR), "type": "mixed"}
    ],
    "active_index": 0,
}

DEFAULT_SETTINGS_JSON = {
    "download_threads": 8,
    "tray_minimize_on_close": False,
    "tray_minimize_after_launch": False,
    "hotkey_enabled": True,
    "hotkey": "Ctrl+Alt+M",
    "retroarch_core_dir": "",
    "export_format": "md",
    "export_include_cover": True,
    "check_update_on_start": True,
    "perf_monitor_on_launch": True,
    "theme": "auto",
    "accent_color": "",
    "patch_dir": "",
    "launch_profiles": {
        "默认": "",
        "全屏": "--fullscreen",
        "窗口化": "--windowed",
        "静音": "--mute",
    },
    "default_profile": "默认",
    "lan_enabled": False,
    "lan_nickname": "",
    "lan_port": 54322,
    "lan_keep_history": True,
    "lan_receive_files": True,
    "lan_password": "",
    "lan_verify_hash": True,
    "lan_max_file_mb": 512,
    "lan_share_enabled": True,
    "lan_notify_on_receive": True,
    "steamgriddb_api_key": "",
    "github_token": "",
    "scrape_image_type": "boxart",
    "scrape_overwrite": False,
    "scrape_auto_on_import": False,
    "process_priority": "normal",
    "process_priority_children": True,
    "process_priority_auto": True,
    "auto_detect_engine_version": True,
    "proxy_mode": "none",
    "proxy_host": "",
    "proxy_port": 0,
    "proxy_user": "",
    "proxy_pwd": "",
    "proxy_bypass": "",
    "plugins_auto_load": True,
    "log_level": "INFO",
    "log_keep_days": 14,
    "crash_report_enabled": True,
    "machine_tier_auto": True,
    "machine_tier": "mid",
    "low_spec_mode": False,
    "resource_policy_enabled": True,
    "resource_cpu_cores": 0,
    "resource_cpu_affinity": "",
    "resource_mem_mb": 0,
    "resource_force_unlock": False,
    "resource_safety_ratio": 85,
    "background_image": "",
    "background_mode": "cover",
    "background_opacity": 100,
    "drag_drop_enabled": True,
    "drag_drop_bios_exts": [".bin", ".rom", ".dat", ".keys"],
    "drag_drop_game_min_size": 4096,
    "job_object_kill_on_close": True,
    "keymap_enabled": False,
    "keymap_only_foreground": True,
    "keymap_show_osd": True,
    "download_use_mirror": True,
}

DEFAULT_MIRRORS_JSON = {
    "enabled": True,
    "auto": True,
    "region": "auto",
    "probe_timeout": 3.0,
    "probe_cache_ttl": 300,
    "mirrors": [
        {"url": "https://ghproxy.com/", "enabled": True, "region": "cn", "weight": 10},
        {"url": "https://gh-proxy.com/", "enabled": True, "region": "cn", "weight": 9},
        {"url": "https://github.moeyy.xyz/", "enabled": True, "region": "cn", "weight": 8},
        {"url": "", "enabled": True, "region": "direct", "weight": 1},
    ],
    "api_mirrors": [
        {"url": "https://api.kkgithub.com/", "enabled": True, "region": "cn", "weight": 10},
        {"url": "https://gh-proxy.com/https://api.github.com/", "enabled": True, "region": "cn", "weight": 8},
        {"url": "", "enabled": True, "region": "direct", "weight": 1},
    ],
}

DEFAULT_SAVE_PATHS_JSON = {}
DEFAULT_CHEAT_PATHS_JSON = {}
DEFAULT_STATS_JSON = {"daily": {}, "launches": 0}
DEFAULT_UPDATE_IGNORE_JSON = {}
DEFAULT_INSTALLED_JSON = {"engines": []}
DEFAULT_ROMS_JSON = {"games": []}

DEFAULT_RESOURCES_JSON = {
    "groups": [
        {
            "name": "安全跳转",
            "icon": "✅",
            "items": [
                {"name": "Internet Archive", "url": "https://archive.org/", "desc": "非营利数字图书馆，含合法归档的老游戏"},
                {"name": "Internet Archive 软件区", "url": "https://archive.org/details/software", "desc": "老软件、老游戏归档，分类浏览"},
                {"name": "My Abandonware", "url": "https://www.myabandonware.com/", "desc": "专注废弃软件的老 PC 游戏站"},
                {"name": "Classic Reload", "url": "https://classicreload.com/", "desc": "浏览器直接玩 DOS 老游戏"},
                {"name": "老男人模拟器", "url": "https://www.oldmantvg.net/", "desc": "国内玩家制作，涵盖模拟器和 ROM 资源"},
                {"name": "ROMhacking", "url": "https://www.romhacking.net/", "desc": "ROM 补丁、翻译、修改工具（非 ROM 下载站）"},
                {"name": "MAME 官方 ROM 页", "url": "https://www.mamedev.org/", "desc": "MAME 官方授权免费发布的街机 ROM"},
            ]
        },
        {
            "name": "灰色跳转",
            "icon": "⚠️",
            "items": [
                {"name": "Myrient", "url": "https://myrient.erista.me/", "desc": "被 Emulation Wiki 评为最好的现代 ROM 库"},
                {"name": "Vimm's Lair", "url": "https://vimm.net/", "desc": "老牌站，已下架大量第一方内容"},
                {"name": "CDRomance", "url": "https://cdromance.games/", "desc": "专注英译补丁和 ROM hack"},
                {"name": "EdgeEmu", "url": "https://edgeemu.net/", "desc": "无广告，适合老主机"},
                {"name": "Planet Emulation", "url": "https://www.planetemu.net/", "desc": "法国老牌站，街机和老电脑强"},
                {"name": "CoolROM", "url": "https://coolrom.com/", "desc": "老牌站，支持多种系统"},
                {"name": "FreeROMS", "url": "https://www.freeroms.com/", "desc": "无需注册，GBA/SNES 等"},
                {"name": "Romspedia", "url": "https://romspedia.com/", "desc": "像百科全书，提供 ROM 和封面"},
                {"name": "Emu-Land", "url": "https://www.emu-land.net/", "desc": "老牌俄罗斯站"},
                {"name": "精英模拟网", "url": "https://emu.jy6d.com/", "desc": "国内站，NDS/3DS/GBA 中文 ROM"},
                {"name": "掌机迷", "url": "https://gbarom.cn/", "desc": "专注中古掌机和 PC 旧游戏"},
            ]
        },
    ]
}

DEFAULT_BIOS_DB = {
    "version": "1.0",
    "platforms": {
        "ps1": {
            "display": "PlayStation",
            "required_any": ["scph1001.bin", "scph5501.bin", "scph7001.bin"],
            "files": {
                "scph1001.bin": {"md5": "924e392ed05558ffdb115408c263dccf", "region": "US", "ver": "2.2"},
                "scph5501.bin": {"md5": "490f666e1afb15b7362b406ed1cea246", "region": "US", "ver": "3.0"},
                "scph7001.bin": {"md5": "0555c6fae8906f3f09baf5988f00e943", "region": "EU", "ver": "4.1"},
                "scph10000.bin": {"md5": "8dd7d5296a650fac7319bcecf08d9a3c", "region": "JP", "ver": "1.0"},
                "scph7502.bin": {"md5": "b9d9a0286c33dc6b7237bb13cd46fdee", "region": "EU", "ver": "2.2"}
            },
            "aliases": {
                "SCPH1001.BIN": "scph1001.bin",
                "bios.bin": "scph1001.bin",
                "ps1bios.bin": "scph1001.bin",
                "psx.bin": "scph1001.bin"
            }
        },
        "ss": {
            "display": "Sega Saturn",
            "required_any": ["sega_101.bin", "mpr-17933.bin"],
            "files": {
                "sega_101.bin": {"md5": "85ec9ca47d8f6807718151cbcca8b9f2", "region": "JP"},
                "mpr-17933.bin": {"md5": "3240872c70984b6cbfda1586cab68dbe", "region": "US/EU"}
            },
            "aliases": {}
        },
        "dc": {
            "display": "Dreamcast",
            "required_any": ["dc_boot.bin"],
            "files": {
                "dc_boot.bin": {"md5": "e10c53c2f8b90bab96ead2d368858623"},
                "dc_flash.bin": {"md5": "0a93f7940c455905bea6e392dfde92a4"}
            },
            "aliases": {}
        },
        "gba": {
            "display": "Game Boy Advance",
            "required_any": ["gba_bios.bin"],
            "files": {
                "gba_bios.bin": {"md5": "a860e8c0b6d573d19181b6bc8e02dd4d"}
            },
            "aliases": {
                "gba_bios.rom": "gba_bios.bin",
                "gba.rom": "gba_bios.bin"
            }
        },
        "nds": {
            "display": "Nintendo DS",
            "required_any": ["bios7.bin", "bios9.bin", "firmware.bin"],
            "files": {
                "bios7.bin": {"md5": "df692a80a5b1bc90728bc3dfc76cd948"},
                "bios9.bin": {"md5": "a392174eb3e572fed6447e956bde4b25"},
                "firmware.bin": {"md5": "8ad9c21c2b3280e45e8bfd1749f0b0e8"}
            },
            "aliases": {
                "nds_bios_arm7.bin": "bios7.bin",
                "nds_bios_arm9.bin": "bios9.bin"
            }
        },
        "switch": {
            "display": "Nintendo Switch",
            "required_any": ["prod.keys"],
            "files": {
                "prod.keys": {"md5": ""},
                "title.keys": {"md5": ""}
            },
            "aliases": {}
        },
        "ps2": {
            "display": "PlayStation 2",
            "required_any": ["scph10000.bin", "scph39001.bin"],
            "files": {},
            "aliases": {}
        },
        "pce": {
            "display": "PC Engine",
            "required_any": ["syscard3.pce"],
            "files": {"syscard3.pce": {"md5": ""}},
            "aliases": {"syscard3.bin": "syscard3.pce"}
        },
        "neogeo": {
            "display": "Neo Geo",
            "required_any": ["neogeo.zip"],
            "files": {"neogeo.zip": {"md5": ""}},
            "aliases": {}
        },
        "intellivision": {
            "display": "Intellivision",
            "required_any": ["exec.bin", "grom.bin"],
            "files": {
                "exec.bin": {"md5": ""},
                "grom.bin": {"md5": ""}
            },
            "aliases": {}
        },
        "pcfx": {
            "display": "PC-FX",
            "required_any": ["pcfx.rom"],
            "files": {"pcfx.rom": {"md5": "08e36edbea1f1882b5a4f9c9d0f6e5a5"}},
            "aliases": {}
        },
        "x68000": {
            "display": "Sharp X68000",
            "required_any": ["iplrom.dat", "cgrom.dat"],
            "files": {
                "iplrom.dat": {"md5": "8dd0edcdd9f2b78a5a8b4e4c6a2b8f5e"},
                "cgrom.dat": {"md5": "1f4b0a3c8d9e6f2a3b5c7d8e9f0a1b2c"}
            },
            "aliases": {"keropi": "iplrom.dat"}
        },
        "pc98": {
            "display": "NEC PC-98",
            "required_any": ["bios.rom", "font.rom"],
            "files": {
                "bios.rom": {"md5": ""},
                "font.rom": {"md5": ""}
            },
            "aliases": {}
        }
    }
}


# ============================================================
# 4. 多语言（外置 JSON，自动生成）
# ============================================================
DEFAULT_LANG_PACKS = {
    "zh": {
        "_meta": {"name": "简体中文", "code": "zh", "translator": "官方"},
        "app_title": "mikan_emu",
        "nav_library": "游戏库", "nav_engines": "模拟器", "nav_bios": "BIOS",
        "nav_stats": "统计", "nav_resources": "资源", "nav_lan": "局域网",
        "nav_webtransfer": "局域网传输",
        "nav_retro_docs": "老游戏资料",
        "nav_settings": "设置",
        "toolbar_import_engine": "导入模拟器", "toolbar_download_engine": "下载模拟器",
        "toolbar_import_game": "导入游戏", "toolbar_export": "导出",
        "toolbar_refresh": "刷新", "toolbar_open_roms": "打开游戏文件夹",
        "toolbar_patch_tool": "🧩 补丁工具",
        "toolbar_scrape": "🎨 批量刮削",
        "library_title": "游戏库", "library_search_ph": "搜索游戏名...",
        "library_platform_all": "全部平台", "library_count": "共 {n} 个游戏",
        "library_empty": "还没有游戏。点顶部「导入游戏」或把 ROM 放进 roms/ 文件夹。",
        "library_col_name": "游戏名", "library_col_platform": "平台",
        "library_col_size": "大小", "library_col_playtime": "时长",
        "library_col_path": "路径",
        "library_filter_all": "全部", "library_filter_fav": "收藏",
        "library_filter_recent": "最近",
        "library_sort_name": "名称", "library_sort_recent": "最近玩过",
        "library_sort_playtime": "时长",
        "library_no_cover": "无封面", "library_launch_btn": "▶ 启动",
        "library_select_hint": "请先选中一个游戏",
        "library_view_grid": "网格视图",
        "library_random_btn": "随机",
        "library_view_timeline": "时间轴视图",
        "library_view_list": "列表视图",
        "engines_title": "已安装的模拟器",
        "engines_empty": "还没有模拟器。点「导入模拟器」或「下载模拟器」。",
        "engines_col_platform": "平台", "engines_col_engine": "内核",
        "engines_col_path": "路径", "engines_col_source": "来源",
        "engines_col_update": "更新",
        "engines_source_import": "手动导入", "engines_source_download": "自动下载",
        "engines_source_manual": "未知渠道",
        "engines_update_available": "↑ 可更新到 {v}",
        "engines_update_latest": "已是最新", "engines_update_checking": "检查中...",
        "engines_update_failed": "检查失败", "engines_update_btn": "更新",
        "engines_update_ignore": "跳过此版本", "engines_update_manual": "—",
        "engines_delete_btn": "🗑 删除此引擎",
        "engines_delete_ok": "已删除引擎 {engine}",
        "engines_delete_cascade": "同时删除磁盘上的引擎目录",
        "engines_delete_confirm": "删除引擎 {engine}？",
        "engines_open_dir": "打开所在目录",
        "engines_open_settings": "⚙ 打开模拟器设置",
        "engines_detect_version": "🔍 重新检测版本",
        "engines_update_all": "⬆ 全部更新",
        "engines_update_all_none": "没有可更新的引擎",
        "engines_update_all_confirm": "将更新 {n} 个引擎：",
        "engines_batch_title": "批量更新",
        "engines_batch_done": "完成：成功 {ok} / 失败 {fail}",
        "engines_version_unknown": "版本未知",
        "engines_version_detected": "检测到版本: {v}",
        "engines_version_detect_failed": "无法检测版本，将使用默认参数",
        "bios_title": "BIOS / 固件",
        "bios_hint": "把 BIOS 文件放到 bios/ 目录，点刷新扫描。",
        "bios_empty": "bios/ 目录为空。",
        "bios_col_file": "文件", "bios_col_size": "大小",
        "bios_col_md5": "MD5", "bios_col_known": "识别",
        "bios_import_pcem_rom": "导入 PCem/86Box ROM",
        "bios_import_pcem_hint": "选择 PCem / 86Box 的 roms 目录（或包含 roms 的上级目录），自动扫描 .bin/.rom/.zip 并复制到 bios/。",
        "bios_import_pcem_done": "已导入 {n} 个 ROM 文件到 bios/",
        "bios_import_pcem_no_files": "该目录下没有找到 .bin/.rom/.zip 文件",
        "bios_unknown": "未知",
        "stats_title": "游戏统计", "stats_total_time": "总时长",
        "stats_total_games": "游戏总数", "stats_total_launches": "启动次数",
        "stats_by_platform": "按平台", "stats_last_7d": "最近 7 天",
        "stats_last_30d": "最近 30 天", "stats_badges": "徽章",
        "stats_daily_table": "每日游戏时长",
        "stats_badge_first": "第一次启动", "stats_badge_10h": "累计 10 小时",
        "stats_badge_50h": "单游戏 50 小时", "stats_badge_7days": "连续 7 天",
        "stats_badge_allplat": "全平台制霸",
        "stats_badge_locked": "未解锁", "stats_badge_unlocked": "已解锁",
        "stats_badge_lib100": "收藏 100",
        "stats_badge_lib500": "收藏 500",
        "stats_badge_100h": "累计 100 小时",
        "stats_badge_1000h": "累计 1000 小时",
        "stats_badge_day8": "单日 8 小时",
        "stats_badge_week5plat": "一周 5 平台",
        "stats_badge_launch50": "启动 50 次",
        "stats_badge_launch500": "启动 500 次",
        "stats_badge_30days": "连续 30 天",
        "stats_badge_lan": "首次联机",
        "stats_badge_fav20": "收藏家（20 个）",
        "stats_badge_clear10": "通关 10 个",
        "stats_badge_wii": "Wii 启动",
        "stats_badge_ps3": "PS3 启动",
        "resources_title": "资源导航",
        "resources_hint": "以下为外部网站跳转，本项目不提供 ROM 下载。请自行判断使用。",
        "resources_safe": "✅ 安全跳转",
        "resources_gray": "⚠️ 灰色跳转",
        "resources_open": "打开",
        "resources_edit": "编辑资源列表",
        "resources_reset": "恢复默认",
        "resources_saved": "资源列表已保存",
        "settings_title": "设置", "settings_lang": "语言",
        "settings_lang_hint": "切换后需重启生效",
        "settings_theme": "外观",
        "settings_theme_auto": "跟随系统",
        "settings_theme_light": "亮色",
        "settings_theme_dark": "深色",
        "settings_accent": "主题色",
        "settings_workspace": "工作区",
        "settings_workspace_desc": "ROM / BIOS / 存档的根目录",
        "settings_open_data": "打开数据目录", "settings_open_log": "打开日志目录",
        "settings_admin": "管理员权限", "settings_relaunch": "以管理员重启",
        "settings_download": "下载设置", "settings_threads": "下载线程数",
        "settings_threads_hint": "4~16，默认 8。",
        "settings_mirrors": "GitHub 镜像站",
        "settings_mirrors_hint": "按顺序尝试，第一个成功的用。空行 = 直连。末尾带 /",
        "settings_mirrors_add": "添加", "settings_mirrors_del": "删除",
        "settings_mirrors_up": "上移", "settings_mirrors_down": "下移",
        "settings_mirrors_test": "测试全部", "settings_mirrors_reset": "恢复默认",
        "settings_mirrors_enable": "启用镜像加速（针对 GitHub）",
        "settings_mirrors_auto": "自动选路（测速后选最快）",
        "settings_mirrors_region": "地区",
        "settings_mirrors_region_auto": "自动",
        "settings_mirrors_region_cn": "国内",
        "settings_mirrors_region_overseas": "海外",
        "settings_mirrors_region_direct": "直连",
        "settings_mirrors_clear_probe": "清除测速缓存",
        "settings_mirrors_probe_cleared": "测速缓存已清除",
        "settings_mirrors_col_url": "地址",
        "settings_mirrors_col_region": "地区",
        "settings_mirrors_col_weight": "权重",
        "settings_mirrors_col_enabled": "启用",
        "settings_mirrors_testing": "测试中...",
        "settings_mirrors_result": "结果：{ok} 成功 / {fail} 失败",
        "settings_api_mirrors": "GitHub API 镜像",
        "settings_api_mirrors_hint": "用于检查更新。按顺序尝试，空行 = 直连。",
        "settings_saves": "存档路径配置",
        "settings_saves_hint": "为每个模拟器指定存档目录。留空 = 不管理。",
        "settings_saves_auto": "自动扫描常见路径",
        "settings_saves_save": "保存",
        "settings_saves_backup": "备份所有存档",
        "settings_saves_restore": "还原存档",
        "settings_saves_open": "打开备份目录",
        "settings_retroarch": "RetroArch 核心目录",
        "settings_retroarch_hint": "libretro 核心（px68k / NP2kai / Brimir）需要 RetroArch 才能运行。",
        "settings_retroarch_browse": "浏览",
        "settings_retroarch_detect": "自动检测",
        "settings_cheats": "金手指目录配置",
        "settings_cheats_hint": "为每个模拟器指定金手指目录和文件扩展名。",
        "settings_tray": "系统托盘",
        "settings_tray_minimize": "关闭时最小化到托盘",
        "settings_tray_minimize_launch": "启动游戏后最小化",
        "settings_perf_monitor": "启动游戏时弹出性能小窗",
        "settings_lan": "局域网",
        "settings_lan_hint": "启用后可在同一局域网内聊天、传文件、共享文件夹。Windows 首次会弹防火墙提示，勾「专用网络」允许。",
        "settings_hotkey": "全局热键呼出",
        "settings_export": "导出设置",
        "settings_export_format": "导出格式",
        "settings_export_include_cover": "包含封面（仅 HTML）",
        "settings_platform_mgr": "平台管理",
        "settings_platform_mgr_hint": "增删改自定义平台。改完点保存，会自动写入 engines.json。",
        "settings_platform_add": "添加平台",
        "settings_platform_save": "保存平台",
        "settings_platform_col_id": "平台 ID",
        "settings_platform_col_name": "显示名",
        "settings_platform_col_ext": "扩展名（逗号分隔）",
        "settings_platform_col_op": "操作",
        "settings_platform_del": "删除",
        "settings_platform_del_confirm": "删除平台 {pid}？（不会删除已安装引擎）",
        "settings_platform_saved": "平台已保存",
        "settings_credits": "鸣谢",
        "settings_credits_btn": "查看鸣谢",
        "settings_project": "项目",
        "settings_project_repo": "项目地址",
        "settings_project_open": "🌐 打开项目主页",
        "settings_project_hint": "点击后用系统默认浏览器打开 GitHub 仓库。",
        "settings_background": "全局背景",
        "settings_background_hint": "选择一张图片作为主窗口背景。留空 = 使用主题默认背景。",
        "settings_background_pick": "选择图片…",
        "settings_background_clear": "清除背景",
        "settings_background_mode": "填充方式",
        "settings_background_mode_cover": "铺满（裁切）",
        "settings_background_mode_contain": "适应（留边）",
        "settings_background_mode_stretch": "拉伸",
        "settings_background_mode_tile": "平铺",
        "settings_background_opacity": "不透明度",
        "settings_background_applied": "背景已更新",
        "settings_folders": "多文件夹管理",
        "settings_folders_hint": "管理多个工作区。当前工作区决定 ROM / BIOS / 存档的根目录。",
        "settings_folders_col_name": "名称",
        "settings_folders_col_path": "路径",
        "settings_folders_col_type": "类型",
        "settings_folders_col_op": "操作",
        "settings_folders_add": "添加工作区",
        "settings_folders_save": "保存工作区",
        "settings_folders_del": "删除",
        "settings_folders_del_confirm": "删除工作区「{name}」？（不会删除磁盘文件）",
        "settings_folders_saved": "工作区已保存",
        "settings_folders_active": "设为当前",
        "settings_folders_type_mixed": "综合",
        "settings_folders_type_rom": "仅 ROM",
        "settings_folders_type_bios": "仅 BIOS",
        "settings_drag_drop": "拖拽识别",
        "settings_drag_drop_enable": "启用拖拽自动识别",
        "settings_drag_drop_hint": "把文件拖到主窗口：.py → 插件；.bin/.rom 等 → BIOS；游戏后缀 → 游戏库。",
        "retro_docs_title": "老游戏资料",
        "retro_docs_hint": "内嵌资料站，方便查老游戏攻略和详情。需要联网。",
        "retro_docs_open_external": "用外部浏览器打开",
        "retro_docs_reload": "重新加载",
        "retro_docs_fallback": "未检测到 QtWebEngine，无法内嵌网页。\n\n点下方按钮用外部浏览器打开资料站。",
        "retro_docs_url": "https://nostalibrary.tzengyuxio.me/",
        "credits_title": "鸣谢",
        "credits_deps": "Python 依赖",
        "credits_emulators": "开源模拟器项目",
        "credits_data": "数据与规范",
        "credits_thanks": "特别感谢",
        "credits_thanks_text": "所有开源贡献者、所有测试用户、以及每一位使用 mikan_emu 的玩家。",
        "import_engine_title": "导入模拟器", "import_game_title": "导入游戏",
        "import_pick_archive": "选择压缩包", "import_pick_folder": "选择文件夹",
        "import_start": "开始导入", "import_scanning": "正在扫描...",
        "import_extracting": "正在解压...", "import_matching": "正在匹配...",
        "import_copying": "正在复制...", "import_found": "识别到 {n} 个",
        "import_not_found": "没识别出来，请手动指定",
        "import_success": "已导入: {name}", "import_failed": "导入失败: {err}",
        "import_done": "导入完成",
        "import_manual_exe": "手动指定可执行文件",
        "import_manual_exe_hint": "自动识别失败，请从下面选一个 .exe：",
        "import_manual_platform": "所属平台",
        "import_manual_platform_hint": "必选。游戏启动时按这个匹配。",
        "import_manual_engine_name": "引擎名",
        "import_manual_launch_tpl": "启动模板",
        "import_game_platform_col": "平台",
        "import_game_set_all": "全选设为",
        "import_game_custom": "未知/自定义",
        "import_game_custom_prompt": "输入平台名：",
        "import_dup_title": "检测到重复游戏",
        "import_dup_hint": "发现 {n} 个重复游戏（按名称 + 大小判断）。请选择处理方式：",
        "import_dup_col_new": "新文件",
        "import_dup_col_old": "已存在",
        "import_dup_col_size": "大小",
        "import_dup_skip": "跳过重复（保留现有库）",
        "import_dup_keep": "保留两份（新的重命名）",
        "import_dup_overwrite": "用新文件覆盖旧条目",
        "ctx_launch": "▶ 启动游戏", "ctx_config": "⚙️ 更多配置…",
        "ctx_open_folder": "打开所在文件夹", "ctx_remove": "从库中移除",
        "ctx_remove_confirm": "从库中移除「{name}」？（不会删除文件）",
        "ctx_fav_add": "加入收藏", "ctx_fav_remove": "取消收藏",
        "ctx_set_cover": "设置封面…", "ctx_open_save": "打开存档目录",
        "ctx_cheat": "管理金手指", "ctx_bios": "选择 BIOS…",
        "ctx_controls": "操作说明…",
        "ctx_more_config": "⚙️ 更多配置…",
        "ctx_scrape_cover": "🖼 自动刮削封面",
        "ctx_open_engine_settings": "⚙ 打开模拟器设置",
        "game_config_title": "更多配置",
        "game_config_tab_launch": "🚀 启动",
        "game_config_tab_patch": "🧩 补丁",
        "game_config_tab_cover": "🖼 封面",
        "game_config_tab_bios": "💾 BIOS",
        "game_config_tab_cheat": "🎮 金手指",
        "game_config_tab_save": "📁 存档",
        "game_config_tab_info": "ℹ️ 信息",
        "game_config_close": "关闭",
        "game_config_open_settings": "⚙ 打开此模拟器的设置界面",
        "game_config_no_save_path": "未配置存档路径。\n去「设置 → 存档路径配置」里为当前引擎指定目录。",
        "controls_title": "操作说明",
        "controls_engine": "模拟器",
        "controls_source": "来源",
        "controls_no_data": "暂无该模拟器的键位数据，请查看官网文档。",
        "controls_open_doc": "打开官方文档",
        "config_title": "配置启动方式", "config_game": "游戏",
        "config_current_platform": "当前平台", "config_engine_group": "使用模拟器",
        "config_auto": "自动（按平台匹配）", "config_manual": "手动指定",
        "config_engine": "模拟器", "config_platform_override": "覆盖平台（可选）",
        "config_platform_override_hint": "如果自动匹配的平台不对，在这里指定正确的",
        "config_platform_none": "不覆盖",
        "config_extra_args": "附加启动参数（可选）",
        "config_extra_args_ph": "例如: --fullscreen",
        "config_profile_group": "启动模板",
        "config_profile_hint": "模板在「设置 → 启动模板」里编辑",
        "config_profile_none": "（不使用模板）",
        "config_perf_group": "性能档位",
        "config_perf_hint": "为支持的模拟器预置参数档位，可在此切换",
        "config_perf_none": "（该模拟器未配置性能档位）",
        "config_save": "保存", "config_cancel": "取消", "config_saved": "已保存",
        "config_no_engine": "没有可用的模拟器，请先下载/导入",
        "bios_select_title": "选择 BIOS",
        "bios_select_hint": "选中的 BIOS 会在启动游戏时复制到模拟器 BIOS 目录。",
        "bios_select_none": "不指定（用模拟器默认）",
        "bios_select_no_files": "bios/ 目录里没有 BIOS 文件。",
        "bios_select_ok": "已设置 BIOS: {name}",
        "launch_no_engine": "没有可用于 {platform} 的模拟器。请先导入模拟器，或用「⚙️ 更多配置」手动指定。",
        "launch_select_engine": "选择用于启动的模拟器:",
        "launch_failed": "启动失败: {err}", "launch_ok": "已启动: {name}",
        "launch_cue_hint": "已自动改用 .cue",
        "launch_bios_copied": "已复制 BIOS 到模拟器目录",
        "launch_bios_failed": "复制 BIOS 失败: {err}",
        "launch_core_missing": "缺少 RetroArch 核心: {core}。请到「设置 → RetroArch 核心目录」配置。",
        "launch_retroarch_missing": "未安装 RetroArch。请先下载/导入 RetroArch。",
        "launch_diag_title": "启动失败诊断",
        "launch_diag_header": "启动 {name} 失败",
        "rom_import_no_rom": "没识别出 ROM 文件",
        "rom_import_done": "导入 {n} 个游戏",
        "rom_import_skipped": "跳过 {n} 个（平台未知）",
        "download_title": "下载模拟器", "download_tab_auto": "可自动下载",
        "download_tab_manual": "需手动下载", "download_start": "下载",
        "download_open_site": "打开官网", "download_progress": "下载中...",
        "download_done": "下载完成", "download_failed": "下载失败: {err}",
        "download_extract": "正在解压...",
        "download_no_auto": "当前没有可自动下载的模拟器",
        "download_manual_hint": "以下模拟器为闭源或来源不明，请前往官网手动下载。",
        "download_confirm": "下载 {name}？",
        "download_speed": "{speed}/s  剩余 {eta}",
        "download_trying_mirror": "尝试镜像: {url}",
        "download_bare_exe": "裸 exe，跳过解压",
        "export_title": "导出游戏库", "export_format_md": "Markdown",
        "export_format_html": "HTML", "export_format_csv": "CSV",
        "export_scope_all": "全部", "export_scope_fav": "仅收藏",
        "export_scope_platform": "仅当前平台",
        "export_include_playtime": "包含时长",
        "export_include_cover": "包含封面（HTML）",
        "export_done": "已导出到: {path}", "export_failed": "导出失败: {err}",
        "cheat_title": "金手指", "cheat_open_dir": "打开金手指目录",
        "cheat_no_dir": "未配置 {engine} 的金手指目录",
        "cheat_import": "导入金手指文件", "cheat_imported": "已导入: {name}",
        "cheat_scan": "🔄 重新扫描",
        "cheat_open_engine_dir": "📂 打开金手指目录",
        "cheat_none_engine": "没有可用引擎",
        "cheat_not_configured": "未配置 {engine} 的金手指目录。\n去「设置 → 金手指目录配置」里设置。",
        "tray_show": "显示主窗口", "tray_recent": "最近游戏",
        "tray_quit": "退出", "tray_minimized": "已最小化到托盘",
        "perf_win_title": "性能监控",
        "perf_cpu": "CPU", "perf_mem": "内存",
        "perf_disk": "磁盘", "perf_net": "网络",
        "perf_none": "N/A",
        "lang_changed_msg": "语言已切换为 {lang}，重启后全部界面才会完全生效。",
        "save_none": "没有可备份的存档路径，请先在「设置 → 存档路径配置」里设置。",
        "save_backup_done": "已备份 {path}",
        "save_backup_failed": "备份失败: {err}",
        "save_restore_confirm": "还原备份 {name}？当前存档会先自动备份。",
        "save_restore_done": "已还原: {name}",
        "save_no_backup": "没有备份",
        "save_select_backup": "选择备份:",
        "save_restore_title": "还原存档",
        "patch_title": "ROM 补丁工具",
        "patch_hint": "支持 IPS / UPS 补丁。\n把补丁文件放在 ROM 同目录（或下方「补丁目录」）会自动列出。\n应用后生成新文件，原 ROM 自动备份为 .bak。",
        "patch_state_clean": "当前是原始 ROM（未打补丁）。",
        "patch_state_patched": "此游戏是打过补丁的版本。原文件: {src}",
        "patch_state_history": "补丁历史:",
        "patch_scan": "🔄 重新扫描",
        "patch_browse": "📂 浏览补丁文件…",
        "patch_apply": "✅ 应用选中补丁",
        "patch_dir": "补丁目录（可选）",
        "patch_dir_ph": "额外的补丁搜索目录",
        "patch_none": "没发现补丁。点「浏览补丁文件…」手动选择。",
        "patch_overwrite": "覆盖原 ROM（自动备份为 .bak）",
        "patch_new_file": "生成新文件",
        "patch_output_name": "输出文件名:",
        "patch_backup": "备份原 ROM（.bak）",
        "patch_done_new": "已生成 {name}\n大小: {old} → {new}",
        "patch_done_overwrite": "已应用补丁并覆盖原文件。\n大小: {old} → {new}",
        "patch_added_to_lib": "已加入游戏库。是否关闭当前对话框？",
        "patch_rom_missing": "ROM 不存在: {path}",
        "patch_file_missing": "补丁不存在: {path}",
        "patch_bad_format": "不支持的补丁格式: {ext}（只支持 .ips / .ups）",
        "patch_ips_invalid": "不是有效的 IPS 文件",
        "patch_ups_invalid": "不是有效的 UPS 文件",
        "patch_ips_truncated": "IPS 文件在记录中途截断",
        "patch_ups_truncated": "UPS varint 截断",
        "patch_tool_title": "ROM 补丁工具",
        "patch_tool_rom": "ROM 文件",
        "patch_tool_patch": "补丁文件",
        "patch_tool_output": "输出文件",
        "patch_tool_output_ph": "留空 = 自动命名 (xxx (patched).xxx)",
        "patch_tool_browse": "浏览…",
        "patch_tool_apply": "应用补丁",
        "patch_failed": "补丁应用失败: {err}",
        "pack_title": "配置包",
        "pack_hint": "把整个配置打包成一个文件，方便迁移 / 备份。",
        "pack_export": "📦 导出完整配置包",
        "pack_import": "📥 导入配置包",
        "pack_dialog_export": "导出配置包",
        "pack_dialog_import": "导入配置包",
        "pack_export_hint": "导出为一个 .mikanpack 文件（ZIP 格式），包含：\n  · 所有配置（设置、镜像、资源、存档路径、金手指路径）\n  · 平台定义 + 已安装引擎清单\n  · 游戏库\n  · 可选：封面、存档备份、统计数据",
        "pack_import_hint": "从 .mikanpack 导入配置。\n  · 默认合并模式：不删除现有条目\n  · 已安装引擎的本地路径不会覆盖（需重新下载）\n  · 导入前会自动备份当前配置",
        "pack_path_export_ph": "保存为 .mikanpack…",
        "pack_path_import_ph": "选择 .mikanpack 文件…",
        "pack_browse": "浏览…",
        "pack_incl_covers": "包含封面图片",
        "pack_incl_saves": "包含存档备份",
        "pack_incl_stats": "包含统计数据",
        "pack_merge": "合并模式（推荐）",
        "pack_do_export": "导出",
        "pack_do_import": "导入",
        "pack_exported": "配置包已保存:\n{path}\n\n大小: {size}",
        "pack_imported": "配置: {config}\n引擎: {engines}\n游戏: {roms}\n封面: {covers}\n存档: {saves}\n\n部分设置需重启程序才完全生效。",
        "pack_file_missing": "文件不存在: {path}",
        "scrape_title": "封面刮削",
        "scrape_choose_source": "选择刮削源",
        "scrape_source_auto": "自动（Libretro 优先，失败用 SteamGridDB）",
        "scrape_source_libretro": "仅 Libretro Thumbnails（免费，无需 key）",
        "scrape_source_sgdb": "仅 SteamGridDB（需在设置里填 API key）",
        "scrape_image_type": "图片类型",
        "scrape_type_boxart": "封面盒图",
        "scrape_type_snap": "游戏截图",
        "scrape_type_title": "标题画面",
        "scrape_overwrite": "覆盖已有封面",
        "scrape_start": "开始刮削",
        "scrape_cancel": "取消",
        "scrape_close": "关闭",
        "scrape_progress": "正在刮削 {cur} / {total}",
        "scrape_searching": "正在搜索 {name}...",
        "scrape_downloading": "正在下载...",
        "scrape_ok": "✅ {name}",
        "scrape_fail": "❌ {name}",
        "scrape_done": "刮削完成：成功 {ok} / 失败 {fail} / 跳过 {skip}",
        "scrape_no_key": "未配置 SteamGridDB API key，请到设置里填写。",
        "scrape_no_platform": "平台 {platform} 不支持自动刮削（无映射）。",
        "scrape_manual_title": "手动修正搜索名",
        "scrape_manual_hint": "自动匹配失败。\nLibretro 的文件名格式通常为「游戏名 (地区)」，可尝试英文名或去掉括号内容。",
        "scrape_manual_prompt": "搜索名:",
        "scrape_manual_retry": "重试",
        "scrape_manual_skip": "跳过",
        "scrape_batch_title": "批量刮削封面",
        "scrape_batch_scope": "范围",
        "scrape_batch_all": "全部游戏",
        "scrape_batch_fav": "仅收藏",
        "scrape_batch_platform": "仅当前平台",
        "scrape_batch_count": "共 {n} 个游戏待刮削",
        "scrape_batch_none": "没有可刮削的游戏（可能都已有封面，或平台不支持）",
        "scrape_batch_start": "开始批量刮削",
        "scrape_already_has": "已有封面，跳过",
        "scrape_failed_list": "失败列表（可手动重试）",
        "scrape_retry_failed": "重试全部失败项",
        "scrape_source_note": "Libretro Thumbnails 为社区维护的免费图库，覆盖经典平台。\nSteamGridDB 覆盖现代平台，需自行申请 API key。",
        "settings_priority": "进程优先级",
        "settings_priority_hint": "启动游戏后自动提升其进程优先级，改善帧数稳定性。\n「高」不需要管理员；「实时」需要管理员，且可能拖慢整个系统。",
        "settings_priority_low": "低（IDLE）",
        "settings_priority_normal": "中（Normal，系统默认）",
        "settings_priority_high": "高（High，推荐）",
        "settings_priority_realtime": "实时（Realtime，⚠ 危险）",
        "settings_priority_children": "同时调整子进程（推荐）",
        "settings_priority_auto": "启动游戏后自动应用",
        "settings_priority_applied": "已应用优先级: {level}",
        "settings_priority_failed": "应用优先级失败（可能需要管理员）",
        "settings_priority_realtime_warn": "实时优先级会拖慢整个系统（键鼠都可能卡顿），确定？",
        "settings_priority_relaunch": "需要管理员权限，是否以管理员重启？",
        "engine_settings_title": "打开模拟器设置",
        "engine_settings_hint": "将不带游戏启动该模拟器，进入它自带的设置界面。",
        "engine_settings_launched": "已启动 {engine} 的设置界面",
        "engine_settings_failed": "启动失败: {err}",
        "engine_not_found": "找不到引擎配置",
        "settings_version": "引擎版本",
        "settings_version_auto_detect": "启动时自动探测引擎版本",
        "settings_version_hint": "探测到的版本会用于套用 version_overrides（不同版本的参数差异）。",
        "version_unknown_warn": "该引擎版本未知，将使用默认参数。可右键「重新检测版本」。",
        "lan_title": "局域网",
        "lan_tab_chat": "💬 聊天",
        "lan_tab_share": "📁 共享",
        "lan_my_name": "昵称",
        "lan_peers": "在线用户",
        "lan_broadcast_name": "全体",
        "lan_no_peers": "暂未发现其他用户。\n请确认大家在同一局域网、已启用局域网功能，并放行防火墙。",
        "lan_send": "发送",
        "lan_input_ph": "输入消息，回车发送…",
        "lan_send_file": "发送文件",
        "lan_file_offer": "[文件] {name}  ({size})",
        "lan_file_done": "已接收: {name}",
        "lan_file_failed": "文件接收失败: {err}",
        "lan_file_sent": "已发送: {name}  ({size})",
        "lan_file_rejected": "对方拒绝了文件",
        "lan_file_disabled": "已关闭文件接收（设置里可开启）",
        "lan_file_hash_ok": "文件校验通过",
        "lan_file_hash_bad": "⚠ 文件哈希不匹配，已丢弃",
        "lan_clear_history": "清空记录",
        "lan_open_received": "打开接收目录",
        "lan_open_shared": "打开共享目录",
        "lan_open_shared_download": "打开下载目录",
        "lan_enabled": "启用局域网功能",
        "lan_nickname_setting": "局域网昵称",
        "lan_port_setting": "监听端口",
        "lan_password_setting": "局域网口令",
        "lan_password_hint": "留空 = 不校验。对方必须填相同口令才能互发。",
        "lan_keep_history": "保留聊天记录到磁盘",
        "lan_receive_files": "允许接收文件",
        "lan_verify_hash": "文件哈希校验（SHA-256）",
        "lan_max_file": "单文件大小上限 (MB)",
        "lan_share_enabled": "允许别人浏览我的共享文件夹",
        "lan_notify_on_receive": "收到文件时弹窗提示",
        "lan_error_port": "端口被占用，请在设置里换一个",
        "lan_error_start": "局域网服务启动失败: {err}",
        "lan_self_msg": "我",
        "lan_peer_joined": "「{name}」上线了",
        "lan_peer_left": "「{name}」下线了",
        "lan_msg_failed": "消息发送失败（对方可能已下线）",
        "lan_firewall_hint": "首次启用 Windows 会弹防火墙提示，请勾选「专用网络」并允许。",
        "lan_proto_note": "局域网明文传输，请勿发送敏感信息。",
        "lan_pending_files": "接收中: {name}  {pct}%",
        "lan_peer_send_file": "对方正在发送文件…",
        "lan_wait_accept": "等待对方接受…",
        "lan_no_ack": "对方未确认收到文件",
        "lan_file_io_fail": "对方无法写入文件（磁盘/权限）",
        "lan_share_title": "共享文件夹",
        "lan_share_hint": "把文件放进「我共享的」，所有在线用户都能看到并下载。",
        "lan_share_my": "我共享的",
        "lan_share_others": "别人的共享",
        "lan_share_col_file": "文件",
        "lan_share_col_size": "大小",
        "lan_share_col_op": "操作",
        "lan_share_col_source": "来源",
        "lan_share_add": "➕ 添加文件",
        "lan_share_remove": "移除",
        "lan_share_remove_confirm": "取消共享 {name}？\n（只删共享区副本，不影响原文件）",
        "lan_share_refresh": "🔄 刷新",
        "lan_share_download": "下载",
        "lan_share_downloading": "下载中…",
        "lan_share_download_done": "已从 {peer} 下载 {name}\n保存到:\n{path}",
        "lan_share_download_fail": "下载失败: {name}  {reason}",
        "lan_share_no_peers": "当前没有其他在线用户。",
        "lan_share_no_port": "已发现用户，但还没拿到它们的端口。\n请等 5 秒后再试。",
        "lan_share_all_fail": "查询了 {n} 个在线用户，但都没响应。\n可能是对方关闭了共享，或被防火墙拦截。",
        "lan_share_my_dir": "本地共享区",
        "lan_ctx_open": "打开对话",
        "lan_ctx_ping": "发 ping",
        "lan_ctx_send_file": "📎 发送文件给 TA",
        "lan_ctx_send_file_all": "📎 发文件给所有人",
        "lan_ctx_clear": "清空记录",
        "lan_emoji_tip": "表情",
        "lan_broadcast_title": "📢 全体（发消息给所有在线用户）",
        "lan_broadcast_confirm": "将 {name} ({size}) 广播给 {n} 个在线用户？",
        "lan_broadcast_done": "广播完成: {name}  成功 {ok}/{total}",
        "lan_broadcast_one_ok": "✅ {peer} 已收到",
        "lan_broadcast_one_fail": "❌ {peer}: {reason}",
        "lan_broadcast_no_peers": "当前没有其他在线用户。",
        "lan_drop_title": "拖拽确认",
        "lan_drop_to_peer": "发送 {n} 个文件给 {peer}？",
        "lan_drop_to_broadcast": "把 {n} 个文件广播给所有在线用户？",
        "lan_drop_no_target": "请先在左侧选中一个用户或「全体」。",
        "lan_drop_ask_share": "拖入了 {n} 个文件。\n群聊不直接发文件，是否全部加入共享文件夹？",
        "lan_peer_offline": "该用户已离线。",
        "lan_peer_port_unknown": "还没拿到该用户的端口，请等 1~2 秒后再试。",
        "lan_port_unknown": "暂时不知道对方端口，请等 1~2 秒。",
        "webtransfer_title": "局域网传输",
        "webtransfer_hint": "内嵌 LocalSend Web，打开后会自动发现同网络的设备，可直接选文件互传。\n💡 内嵌页【上传】正常。【下载】请点右上角「用外部浏览器打开」，由浏览器保存文件。",
        "webtransfer_open_external": "用外部浏览器打开",
        "webtransfer_reload": "重新加载",
        "webtransfer_native": "打开 LocalSend 官网",
        "webtransfer_fallback": (
            "未检测到 QtWebEngine，无法内嵌网页。\n\n"
            "建议：\n"
            "1. 安装 PySide6-WebEngine 后重启程序；\n"
            "2. 或点下方按钮用外部浏览器打开 LocalSend Web。"),
        "webtransfer_url": "https://web.localsend.org/",
        "webtransfer_install_btn": "自动安装 PySide6-WebEngine",
        "webtransfer_install_confirm": "将执行：pip install PySide6-WebEngine\n\n包体积约 200MB，需要联网下载。是否继续？",
        "webtransfer_install_started": "已在新窗口开始安装。\n安装完成后请关闭并重新启动 mikan_emu。",
        "webtransfer_install_failed": "启动安装进程失败。",
        "msg_ok": "确定", "msg_cancel": "取消", "msg_warning": "警告",
        "msg_error": "错误", "msg_info": "提示", "msg_confirm": "确认",
        "plugins_title": "插件",
        "plugins_hint": "插件放在 data/mikan_emu/plugins/<id>/ 下，每个插件包含 plugin.json 和 main.py。\n启用/禁用或导入新插件后，需要点「重启程序」才能生效。",
        "plugins_col_enabled": "启用",
        "plugins_col_id": "ID",
        "plugins_col_name": "名称",
        "plugins_col_version": "版本",
        "plugins_open_dir": "📂 打开插件目录",
        "plugins_import_zip": "📥 导入插件压缩包",
        "plugins_rescan": "🔄 重新扫描",
        "plugins_restart": "♻ 重启程序",
        "plugins_import_title": "导入插件",
        "plugins_import_success": "插件「{name}」已导入。\n请点「重启程序」使其生效。",
        "plugins_import_no_meta": "压缩包里没有找到 plugin.json",
        "plugins_import_overwrite": "插件 {pid} 已存在，覆盖？",
        "plugins_import_failed": "导入失败: {err}",
        "plugins_toggle_hint": "插件 {pid} 已{state}。\n请点「重启程序」使其生效。",
        "plugins_state_enabled": "启用",
        "plugins_state_disabled": "禁用",
        "plugins_restart_confirm": "将关闭当前窗口并重新启动程序。\n继续？",
        "plugins_load_failed": "插件 {pid} 加载失败: {err}",
        "log_viewer_title": "日志与诊断",
        "log_level_all": "全部",
        "log_auto_scroll": "自动滚动",
        "log_clear_buffer": "清空缓冲",
        "log_open_dir": "打开日志目录",
        "log_export_pack": "📦 导出诊断包",
        "log_count": "显示 {shown} 条 / 缓冲共 {total} 条",
        "log_export_success": "诊断包已生成：\n{path}\n\n是否打开所在目录？",
        "log_viewer_level": "级别",
        "log_viewer_filter": "过滤",
        "log_filter_ph": "关键词（例如 plugin / download）",
        "crash_title": "程序异常",
        "crash_body": "mikan_emu 遇到一个未处理的异常。",
        "crash_pack_ready": "诊断包已生成:\n{path}",
        "crash_pack_failed": "诊断包生成失败，请手动查看日志目录。",
        "crash_save_pack": "保存诊断包…",
        "crash_open_log": "打开日志目录",
        "crash_close": "关闭",
        "settings_log_diag": "📋 日志与诊断",
        "settings_log_level": "日志级别",
        "settings_log_keep_days": "日志保留天数",
        "settings_crash_report_enabled": "未捕获异常时自动生成诊断包",
        "win_version_too_old_title": "系统版本过低",
        "win_version_too_old": "当前 Windows 构建号 {build}，低于 Qt6 要求的 17763（Win10 1809）。\n请升级系统，或使用旧版 mikan_emu。",
        "win_version_label": "系统: {name} (build {build}) · 机器档次: {tier}",
        "machine_tier_title": "资源策略",
        "machine_tier_label": "机器档次",
        "machine_tier_low": "低配 (老电脑)",
        "machine_tier_mid": "中配",
        "machine_tier_high": "高配",
        "machine_tier_auto": "自动检测",
        "machine_tier_low_spec": "低配模式（关网格视图 / 关性能小窗）",
        "machine_tier_detected": "检测到: {cpu_p}C/{cpu_l}T · {mem_gb} GB 内存 · 安全上限: {cpu_limit} 核 / {mem_limit} MB",
        "resource_policy_enable": "启用资源策略",
        "resource_cpu_cores": "CPU 核心数（0 = 自动）",
        "resource_mem_mb": "内存建议 MB（仅记录，Windows 无法强制限制）",
        "resource_force_unlock": "⚠ 强制解锁（无视 {ratio}% 上限）",
        "resource_force_unlock_warn": "强制解锁会无视 {ratio}% 安全上限，可能导致系统卡顿甚至 OOM。\n继续？",
        "resource_safety_ratio": "安全上限百分比",
        "folder_new_workspace": "新工作区",
        "folder_untitled": "未命名工作区",
        "file_not_found": "文件不存在: {path}",
        "open_failed": "打开失败: {e}",
        "copy_info_done": "已复制",
        # ★ v1.8.0 新增
        "settings_github_token": "GitHub Token（可选）",
        "settings_github_token_hint": "用于检查更新，提高 API 速率限制。不填 = 匿名（60 次/小时）。",
        "settings_job_object": "Job Object 托管",
        "settings_job_object_kill": "主程序退出时关闭模拟器",
        "settings_job_object_hint": "勾选后，关闭 mikan_emu 会自动结束所有由它启动的模拟器（防止孤儿进程）。",
        "settings_keymap": "虚拟按键映射",
        "settings_keymap_enable": "启用虚拟按键映射",
        "settings_keymap_only_foreground": "仅模拟器窗口在前台时生效",
        "settings_keymap_show_osd": "重映射时显示屏幕提示",
        "settings_keymap_hint": "把物理按键映射成模拟器需要的按键。例如：按 A 发送 B。\n注意：需要安装 keyboard 库。仅对由 mikan_emu 启动的模拟器生效。",
        "keymap_title": "虚拟按键映射",
        "keymap_add": "添加映射",
        "keymap_remove": "删除",
        "keymap_clear": "清空",
        "keymap_save": "保存",
        "keymap_col_physical": "物理按键",
        "keymap_col_virtual": "发送给模拟器",
        "keymap_col_enabled": "启用",
        "keymap_col_note": "备注",
        "keymap_record_hint": "点击「录入」后按下键盘",
        "keymap_record_btn": "录入",
        "keymap_cancel_record": "取消",
        "keymap_test": "测试",
        "keymap_test_hint": "在下方输入框按键，观察是否被映射",
        "keymap_no_keyboard": "未安装 keyboard 库，无法使用虚拟按键映射。\n请运行 pip install keyboard",
        "keymap_saved": "按键映射已保存",
        "keymap_duplicate": "物理按键 {key} 已存在",
        "keymap_recording": "请按下要映射的物理按键…",
        "keymap_recorded": "已录入: {key}",
        "keymap_virtual_ph": "例如: space / enter / a",
        "update_dialog_title": "检查更新",
        "update_dialog_check": "检查全部",
        "update_dialog_engine": "引擎",
        "update_dialog_current": "当前版本",
        "update_dialog_available": "可用版本",
        "update_dialog_published": "发布时间",
        "update_dialog_action": "操作",
        "update_dialog_use_mirror": "使用镜像加速下载",
        "update_dialog_update": "更新",
        "update_dialog_no_releases": "没有可用版本",
        "update_dialog_fetching": "正在获取版本列表…",
        "update_dialog_fetch_failed": "获取失败: {err}",
        "update_dialog_all_latest": "所有引擎已是最新",
        "update_dialog_confirm": "确认更新 {engine} 到 {version}？\n\n{notes}",
        "update_dialog_prerelease": "预发布",
        "update_dialog_select": "选择版本",
        "update_dialog_token_hint": "提示：在设置里填 GitHub Token 可提高速率限制。",
        "param_schema_title": "模拟器参数",
        "param_schema_hint": "这里定义该模拟器支持的启动参数。勾选/填写后会拼接到命令行。",
        "param_schema_empty": "该引擎暂无参数模板。可手动在「附加参数」里填。",
        "param_schema_reset": "恢复默认",
        "param_schema_preview": "命令行预览",
        "param_schema_apply": "保存参数",
        "param_schema_saved": "参数已保存",
        "osd_keymap": "🔁 {physical} → {virtual}",
        "job_running": "任务进行中…",
        "job_cancelled": "已取消",
        "job_failed": "失败: {err}",
        "job_done": "完成",
    },
    "en": {
        "_meta": {"name": "English", "code": "en", "translator": "Official"},
        "app_title": "mikan_emu",
        "nav_library": "Library", "nav_engines": "Emulators", "nav_bios": "BIOS",
        "nav_stats": "Stats", "nav_resources": "Resources", "nav_lan": "LAN",
        "nav_webtransfer": "LAN Transfer",
        "nav_retro_docs": "Retro Docs",
        "nav_settings": "Settings",
        "toolbar_import_engine": "Import Engine",
        "toolbar_download_engine": "Download Engine",
        "toolbar_import_game": "Import Game", "toolbar_export": "Export",
        "toolbar_refresh": "Refresh", "toolbar_open_roms": "Open ROMs",
        "toolbar_patch_tool": "🧩 Patch Tool",
        "toolbar_scrape": "🎨 Batch Scrape",
        "library_title": "Library", "library_search_ph": "Search game...",
        "library_platform_all": "All Platforms", "library_count": "{n} game(s)",
        "library_empty": "No games yet.",
        "library_col_name": "Name", "library_col_platform": "Platform",
        "library_col_size": "Size", "library_col_playtime": "Playtime",
        "library_col_path": "Path",
        "library_filter_all": "All", "library_filter_fav": "Fav",
        "library_filter_recent": "Recent",
        "library_sort_name": "Name", "library_sort_recent": "Recent",
        "library_sort_playtime": "Playtime",
        "library_no_cover": "No cover", "library_launch_btn": "▶ Launch",
        "library_select_hint": "Please select a game",
        "library_view_grid": "Grid View",
        "library_random_btn": "Random",
        "library_view_timeline": "Timeline View",
        "library_view_list": "List View",
        "engines_title": "Installed Emulators",
        "engines_empty": "No emulators yet.",
        "engines_col_platform": "Platform", "engines_col_engine": "Engine",
        "engines_col_path": "Path", "engines_col_source": "Source",
        "engines_col_update": "Update",
        "engines_source_import": "Imported", "engines_source_download": "Downloaded",
        "engines_source_manual": "Unknown",
        "engines_update_available": "↑ Update to {v}",
        "engines_update_latest": "Up to date",
        "engines_update_checking": "Checking...",
        "engines_update_failed": "Check failed",
        "engines_update_btn": "Update",
        "engines_update_ignore": "Skip this version",
        "engines_update_manual": "—",
        "engines_delete_btn": "🗑 Delete this engine",
        "engines_delete_ok": "Deleted engine {engine}",
        "engines_delete_cascade": "Also delete engine folder on disk",
        "engines_delete_confirm": "Delete engine {engine}?",
        "engines_open_dir": "Open folder",
        "engines_open_settings": "⚙ Open emulator settings",
        "engines_detect_version": "🔍 Re-detect version",
        "engines_update_all": "⬆ Update All",
        "engines_update_all_none": "No engines to update",
        "engines_update_all_confirm": "Update {n} engines:",
        "engines_batch_title": "Batch Update",
        "engines_batch_done": "Done: OK {ok} / Failed {fail}",
        "engines_version_unknown": "Version unknown",
        "engines_version_detected": "Detected version: {v}",
        "engines_version_detect_failed": "Cannot detect version, using defaults",
        "bios_title": "BIOS / Firmware",
        "bios_hint": "Put BIOS files into bios/ folder.",
        "bios_empty": "bios/ folder is empty.",
        "bios_col_file": "File", "bios_col_size": "Size",
        "bios_col_md5": "MD5", "bios_col_known": "Known",
        "bios_import_pcem_rom": "Import PCem/86Box ROM",
        "bios_import_pcem_hint": "Pick PCem/86Box roms dir (or parent).",
        "bios_import_pcem_done": "Imported {n} ROM files to bios/",
        "bios_import_pcem_no_files": "No .bin/.rom/.zip found in that dir",
        "bios_unknown": "Unknown",
        "stats_title": "Statistics", "stats_total_time": "Total Time",
        "stats_total_games": "Games", "stats_total_launches": "Launches",
        "stats_by_platform": "By Platform", "stats_last_7d": "Last 7 Days",
        "stats_last_30d": "Last 30 Days", "stats_badges": "Badges",
        "stats_daily_table": "Daily Playtime",
        "stats_badge_first": "First Launch", "stats_badge_10h": "10h Total",
        "stats_badge_50h": "50h Single Game", "stats_badge_7days": "7-Day Streak",
        "stats_badge_allplat": "All Platforms",
        "stats_badge_locked": "Locked", "stats_badge_unlocked": "Unlocked",
        "stats_badge_lib100": "Library 100",
        "stats_badge_lib500": "Library 500",
        "stats_badge_100h": "100h Total",
        "stats_badge_1000h": "1000h Total",
        "stats_badge_day8": "8h in One Day",
        "stats_badge_week5plat": "5 Platforms in a Week",
        "stats_badge_launch50": "50 Launches",
        "stats_badge_launch500": "500 Launches",
        "stats_badge_30days": "30-Day Streak",
        "stats_badge_lan": "First LAN",
        "stats_badge_fav20": "Collector (20 fav)",
        "stats_badge_clear10": "Beat 10 Games",
        "stats_badge_wii": "Wii Launch",
        "stats_badge_ps3": "PS3 Launch",
        "resources_title": "Resources",
        "resources_hint": "External site links. This project does NOT provide ROM downloads.",
        "resources_safe": "✅ Safe Links",
        "resources_gray": "⚠️ Gray Area Links",
        "resources_open": "Open",
        "resources_edit": "Edit Resources",
        "resources_reset": "Reset",
        "resources_saved": "Resources saved",
        "settings_title": "Settings", "settings_lang": "Language",
        "settings_lang_hint": "Restart required",
        "settings_theme": "Appearance",
        "settings_theme_auto": "System",
        "settings_theme_light": "Light",
        "settings_theme_dark": "Dark",
        "settings_accent": "Accent",
        "settings_workspace": "Workspace",
        "settings_workspace_desc": "Root for ROM / BIOS / Saves",
        "settings_open_data": "Open Data Dir", "settings_open_log": "Open Log Dir",
        "settings_admin": "Admin Rights", "settings_relaunch": "Relaunch as Admin",
        "settings_download": "Download", "settings_threads": "Threads",
        "settings_threads_hint": "4~16, default 8.",
        "settings_mirrors": "GitHub Mirrors",
        "settings_mirrors_hint": "Tried in order. Empty line = direct. End with /",
        "settings_mirrors_add": "Add", "settings_mirrors_del": "Delete",
        "settings_mirrors_up": "Up", "settings_mirrors_down": "Down",
        "settings_mirrors_test": "Test All", "settings_mirrors_reset": "Reset",
        "settings_mirrors_enable": "Enable mirror acceleration (GitHub)",
        "settings_mirrors_auto": "Auto-route (probe and pick fastest)",
        "settings_mirrors_region": "Region",
        "settings_mirrors_region_auto": "Auto",
        "settings_mirrors_region_cn": "China",
        "settings_mirrors_region_overseas": "Overseas",
        "settings_mirrors_region_direct": "Direct",
        "settings_mirrors_clear_probe": "Clear probe cache",
        "settings_mirrors_probe_cleared": "Probe cache cleared",
        "settings_mirrors_col_url": "URL",
        "settings_mirrors_col_region": "Region",
        "settings_mirrors_col_weight": "Weight",
        "settings_mirrors_col_enabled": "Enabled",
        "settings_mirrors_testing": "Testing...",
        "settings_mirrors_result": "Result: {ok} OK / {fail} failed",
        "settings_api_mirrors": "GitHub API Mirrors",
        "settings_api_mirrors_hint": "For update checks. Tried in order. Empty = direct.",
        "settings_saves": "Save Paths",
        "settings_saves_hint": "Set save directory for each emulator.",
        "settings_saves_auto": "Auto-detect", "settings_saves_save": "Save",
        "settings_saves_backup": "Backup All Saves",
        "settings_saves_restore": "Restore Saves",
        "settings_saves_open": "Open Backup Dir",
        "settings_retroarch": "RetroArch Core Dir",
        "settings_retroarch_hint": "libretro cores need RetroArch.",
        "settings_retroarch_browse": "Browse",
        "settings_retroarch_detect": "Auto Detect",
        "settings_cheats": "Cheat Paths",
        "settings_cheats_hint": "Set cheat directory and extension per emulator.",
        "settings_tray": "System Tray",
        "settings_tray_minimize": "Minimize to tray on close",
        "settings_tray_minimize_launch": "Minimize after launching game",
        "settings_perf_monitor": "Show performance window on launch",
        "settings_lan": "LAN",
        "settings_lan_hint": "Enable chat / file transfer / shared folder on LAN.",
        "settings_hotkey": "Global Hotkey",
        "settings_export": "Export Settings", "settings_export_format": "Format",
        "settings_export_include_cover": "Include cover (HTML only)",
        "settings_platform_mgr": "Platform Manager",
        "settings_platform_mgr_hint": "Add/remove/edit custom platforms.",
        "settings_platform_add": "Add Platform",
        "settings_platform_save": "Save Platforms",
        "settings_platform_col_id": "Platform ID",
        "settings_platform_col_name": "Display Name",
        "settings_platform_col_ext": "Extensions (comma sep)",
        "settings_platform_col_op": "Op",
        "settings_platform_del": "Del",
        "settings_platform_del_confirm": "Delete platform {pid}?",
        "settings_platform_saved": "Platforms saved",
        "settings_credits": "Credits",
        "settings_credits_btn": "View Credits",
        "settings_project": "Project",
        "settings_project_repo": "Project URL",
        "settings_project_open": "🌐 Open Project Homepage",
        "settings_project_hint": "Click to open the GitHub repository in your default browser.",
        "settings_background": "Global Background",
        "settings_background_hint": "Pick an image as the main window background. Empty = theme default.",
        "settings_background_pick": "Pick image…",
        "settings_background_clear": "Clear background",
        "settings_background_mode": "Fill mode",
        "settings_background_mode_cover": "Cover (crop)",
        "settings_background_mode_contain": "Contain (letterbox)",
        "settings_background_mode_stretch": "Stretch",
        "settings_background_mode_tile": "Tile",
        "settings_background_opacity": "Opacity",
        "settings_background_applied": "Background updated",
        "settings_folders": "Multi-Folder",
        "settings_folders_hint": "Manage multiple workspaces. Active workspace sets root for ROM / BIOS / Saves.",
        "settings_folders_col_name": "Name",
        "settings_folders_col_path": "Path",
        "settings_folders_col_type": "Type",
        "settings_folders_col_op": "Op",
        "settings_folders_add": "Add Workspace",
        "settings_folders_save": "Save Workspaces",
        "settings_folders_del": "Del",
        "settings_folders_del_confirm": "Delete workspace '{name}'? (Disk files untouched)",
        "settings_folders_saved": "Workspaces saved",
        "settings_folders_active": "Set Active",
        "settings_folders_type_mixed": "Mixed",
        "settings_folders_type_rom": "ROM only",
        "settings_folders_type_bios": "BIOS only",
        "settings_drag_drop": "Drag & Drop",
        "settings_drag_drop_enable": "Enable drag & drop auto-detect",
        "settings_drag_drop_hint": "Drop files onto main window: .py → plugins; .bin/.rom → BIOS; game extensions → library.",
        "retro_docs_title": "Retro Docs",
        "retro_docs_hint": "Embedded docs site for old games. Requires network.",
        "retro_docs_open_external": "Open in browser",
        "retro_docs_reload": "Reload",
        "retro_docs_fallback": "QtWebEngine not found. Cannot embed page.\n\nClick the button below to open the docs site in your browser.",
        "retro_docs_url": "https://nostalibrary.tzengyuxio.me/",
        "credits_title": "Credits",
        "credits_deps": "Python Dependencies",
        "credits_emulators": "Open Source Emulator Projects",
        "credits_data": "Data & Standards",
        "credits_thanks": "Special Thanks",
        "credits_thanks_text": "All open source contributors, all testers, and every player using mikan_emu.",
        "import_engine_title": "Import Emulator",
        "import_game_title": "Import Game",
        "import_pick_archive": "Pick Archive",
        "import_pick_folder": "Pick Folder",
        "import_start": "Start", "import_scanning": "Scanning...",
        "import_extracting": "Extracting...", "import_matching": "Matching...",
        "import_copying": "Copying...", "import_found": "Found {n}",
        "import_not_found": "Not recognized",
        "import_success": "Imported: {name}", "import_failed": "Failed: {err}",
        "import_done": "Done",
        "import_manual_exe": "Manual EXE",
        "import_manual_exe_hint": "Auto-detect failed. Pick an .exe:",
        "import_manual_platform": "Platform",
        "import_manual_platform_hint": "Required.",
        "import_manual_engine_name": "Engine Name",
        "import_manual_launch_tpl": "Launch Template",
        "import_game_platform_col": "Platform",
        "import_game_set_all": "Set all to",
        "import_game_custom": "Unknown/Custom",
        "import_game_custom_prompt": "Enter platform name:",
        "import_dup_title": "Duplicate Games Detected",
        "import_dup_hint": "Found {n} duplicates (by name + size). Choose action:",
        "import_dup_col_new": "New File",
        "import_dup_col_old": "Existing",
        "import_dup_col_size": "Size",
        "import_dup_skip": "Skip duplicates (keep existing)",
        "import_dup_keep": "Keep both (rename new)",
        "import_dup_overwrite": "Overwrite existing entries",
        "ctx_launch": "▶ Launch", "ctx_config": "⚙️ More Config…",
        "ctx_open_folder": "Open Folder", "ctx_remove": "Remove from Library",
        "ctx_remove_confirm": "Remove '{name}'?",
        "ctx_fav_add": "Add to Favorites",
        "ctx_fav_remove": "Remove from Favorites",
        "ctx_set_cover": "Set Cover…", "ctx_open_save": "Open Save Dir",
        "ctx_cheat": "Manage Cheats", "ctx_bios": "Select BIOS…",
        "ctx_controls": "Controls…",
        "ctx_more_config": "⚙️ More Config…",
        "ctx_scrape_cover": "🖼 Auto-scrape Cover",
        "ctx_open_engine_settings": "⚙ Open emulator settings",
        "game_config_title": "More Config",
        "game_config_tab_launch": "🚀 Launch",
        "game_config_tab_patch": "🧩 Patch",
        "game_config_tab_cover": "🖼 Cover",
        "game_config_tab_bios": "💾 BIOS",
        "game_config_tab_cheat": "🎮 Cheats",
        "game_config_tab_save": "📁 Saves",
        "game_config_tab_info": "ℹ️ Info",
        "game_config_close": "Close",
        "game_config_open_settings": "⚙ Open this emulator's settings",
        "game_config_no_save_path": "No save path configured.\nGo to Settings → Save Paths.",
        "controls_title": "Controls",
        "controls_engine": "Emulator",
        "controls_source": "Source",
        "controls_no_data": "No control data for this emulator.",
        "controls_open_doc": "Open Official Docs",
        "config_title": "Configure Launch", "config_game": "Game",
        "config_current_platform": "Platform",
        "config_engine_group": "Emulator",
        "config_auto": "Auto", "config_manual": "Manual",
        "config_engine": "Emulator",
        "config_platform_override": "Override platform",
        "config_platform_override_hint": "If auto-matched is wrong",
        "config_platform_none": "No override",
        "config_extra_args": "Extra args",
        "config_extra_args_ph": "e.g. --fullscreen",
        "config_profile_group": "Launch Profile",
        "config_profile_hint": "Edit profiles in Settings → Launch Profiles",
        "config_profile_none": "(no profile)",
        "config_perf_group": "Performance Profile",
        "config_perf_hint": "Preset arg sets for supported emulators",
        "config_perf_none": "(not configured for this emulator)",
        "config_save": "Save", "config_cancel": "Cancel",
        "config_saved": "Saved", "config_no_engine": "No emulator available.",
        "bios_select_title": "Select BIOS",
        "bios_select_hint": "Selected BIOS will be copied on launch.",
        "bios_select_none": "None (use emulator default)",
        "bios_select_no_files": "No BIOS files in bios/ folder.",
        "bios_select_ok": "BIOS set: {name}",
        "launch_no_engine": "No emulator for {platform}.",
        "launch_select_engine": "Choose emulator:",
        "launch_failed": "Launch failed: {err}",
        "launch_ok": "Launched: {name}",
        "launch_cue_hint": "Auto-switched to .cue",
        "launch_bios_copied": "BIOS copied to emulator dir",
        "launch_bios_failed": "BIOS copy failed: {err}",
        "launch_core_missing": "Missing RetroArch core: {core}.",
        "launch_retroarch_missing": "RetroArch not installed.",
        "launch_diag_title": "Launch Failure Diagnosis",
        "launch_diag_header": "Failed to launch {name}",
        "rom_import_no_rom": "No ROM recognized",
        "rom_import_done": "Imported {n}",
        "rom_import_skipped": "Skipped {n}",
        "download_title": "Download Emulator",
        "download_tab_auto": "Auto", "download_tab_manual": "Manual",
        "download_start": "Download", "download_open_site": "Open Site",
        "download_progress": "Downloading...", "download_done": "Done",
        "download_failed": "Failed: {err}",
        "download_extract": "Extracting...",
        "download_no_auto": "No auto-downloadable emulator",
        "download_manual_hint": "Closed-source. Please visit official sites.",
        "download_confirm": "Download {name}?",
        "download_speed": "{speed}/s  ETA {eta}",
        "download_trying_mirror": "Trying: {url}",
        "download_bare_exe": "Bare exe, skip extract",
        "export_title": "Export Library",
        "export_format_md": "Markdown", "export_format_html": "HTML",
        "export_format_csv": "CSV",
        "export_scope_all": "All", "export_scope_fav": "Favorites",
        "export_scope_platform": "Current Platform",
        "export_include_playtime": "Include playtime",
        "export_include_cover": "Include cover (HTML)",
        "export_done": "Exported to: {path}",
        "export_failed": "Export failed: {err}",
        "cheat_title": "Cheats", "cheat_open_dir": "Open Cheat Dir",
        "cheat_no_dir": "No cheat dir configured for {engine}",
        "cheat_import": "Import Cheat File", "cheat_imported": "Imported: {name}",
        "cheat_scan": "🔄 Rescan",
        "cheat_open_engine_dir": "📂 Open Cheat Dir",
        "cheat_none_engine": "No engine available",
        "cheat_not_configured": "No cheat dir configured for {engine}.\nGo to Settings → Cheat Paths.",
        "tray_show": "Show Window", "tray_recent": "Recent Games",
        "tray_quit": "Quit", "tray_minimized": "Minimized to tray",
        "perf_win_title": "Performance",
        "perf_cpu": "CPU", "perf_mem": "Memory",
        "perf_disk": "Disk", "perf_net": "Network",
        "perf_none": "N/A",
        "lang_changed_msg": "Language switched to {lang}. Restart for full effect.",
        "save_none": "No save path configured.",
        "save_backup_done": "Backed up: {path}",
        "save_backup_failed": "Backup failed: {err}",
        "save_restore_confirm": "Restore backup {name}?",
        "save_restore_done": "Restored: {name}",
        "save_no_backup": "No backup",
        "save_select_backup": "Select backup:",
        "save_restore_title": "Restore Saves",
        "patch_title": "ROM Patch Tool",
        "patch_hint": "Supports IPS / UPS. Auto-scans ROM folder for patches.\nOriginals are backed up as .bak.",
        "patch_state_clean": "Original ROM (not patched).",
        "patch_state_patched": "This is a patched version. Original: {src}",
        "patch_state_history": "Patch history:",
        "patch_scan": "🔄 Rescan",
        "patch_browse": "📂 Browse patch file…",
        "patch_apply": "✅ Apply Selected Patch",
        "patch_dir": "Patch Dir (optional)",
        "patch_dir_ph": "Extra patch search dir",
        "patch_none": "No patches found. Click Browse to select.",
        "patch_overwrite": "Overwrite original (backup as .bak)",
        "patch_new_file": "Create new file",
        "patch_output_name": "Output name:",
        "patch_backup": "Backup original (.bak)",
        "patch_done_new": "Created {name}\nSize: {old} → {new}",
        "patch_done_overwrite": "Patch applied and overwritten.\nSize: {old} → {new}",
        "patch_added_to_lib": "Added to library. Close dialog?",
        "patch_rom_missing": "ROM not found: {path}",
        "patch_file_missing": "Patch not found: {path}",
        "patch_bad_format": "Unsupported patch format: {ext} (only .ips / .ups)",
        "patch_ips_invalid": "Not a valid IPS file",
        "patch_ups_invalid": "Not a valid UPS file",
        "patch_ips_truncated": "IPS file truncated",
        "patch_ups_truncated": "UPS varint truncated",
        "patch_tool_title": "ROM Patch Tool",
        "patch_tool_rom": "ROM File",
        "patch_tool_patch": "Patch File",
        "patch_tool_output": "Output File",
        "patch_tool_output_ph": "Empty = auto (xxx (patched).xxx)",
        "patch_tool_browse": "Browse…",
        "patch_tool_apply": "Apply Patch",
        "patch_failed": "Patch failed: {err}",
        "pack_title": "Config Pack",
        "pack_hint": "Pack all config into one file for migration/backup.",
        "pack_export": "📦 Export Full Config Pack",
        "pack_import": "📥 Import Config Pack",
        "pack_dialog_export": "Export Config Pack",
        "pack_dialog_import": "Import Config Pack",
        "pack_export_hint": "Export to .mikanpack (ZIP) containing:\n  · All config (settings, mirrors, resources, save/cheat paths)\n  · Platform defs + installed engines\n  · Game library\n  · Optional: covers, save backups, stats",
        "pack_import_hint": "Import from .mikanpack.\n  · Merge mode by default\n  · Installed engine paths are not overwritten\n  · Current config auto-backed up",
        "pack_path_export_ph": "Save as .mikanpack…",
        "pack_path_import_ph": "Pick .mikanpack…",
        "pack_browse": "Browse…",
        "pack_incl_covers": "Include covers",
        "pack_incl_saves": "Include save backups",
        "pack_incl_stats": "Include stats",
        "pack_merge": "Merge mode (recommended)",
        "pack_do_export": "Export",
        "pack_do_import": "Import",
        "pack_exported": "Config pack saved:\n{path}\n\nSize: {size}",
        "pack_imported": "Config: {config}\nEngines: {engines}\nGames: {roms}\nCovers: {covers}\nSaves: {saves}\n\nRestart for some settings to take effect.",
        "pack_file_missing": "File not found: {path}",
        "scrape_title": "Cover Scraper",
        "scrape_choose_source": "Scrape Source",
        "scrape_source_auto": "Auto (Libretro first, SteamGridDB fallback)",
        "scrape_source_libretro": "Libretro Thumbnails only (free, no key)",
        "scrape_source_sgdb": "SteamGridDB only (needs API key)",
        "scrape_image_type": "Image Type",
        "scrape_type_boxart": "Boxart",
        "scrape_type_snap": "Screenshot",
        "scrape_type_title": "Title Screen",
        "scrape_overwrite": "Overwrite existing covers",
        "scrape_start": "Start Scraping",
        "scrape_cancel": "Cancel",
        "scrape_close": "Close",
        "scrape_progress": "Scraping {cur} / {total}",
        "scrape_searching": "Searching {name}...",
        "scrape_downloading": "Downloading...",
        "scrape_ok": "✅ {name}",
        "scrape_fail": "❌ {name}",
        "scrape_done": "Done: OK {ok} / Failed {fail} / Skipped {skip}",
        "scrape_no_key": "SteamGridDB API key not set. Please configure in Settings.",
        "scrape_no_platform": "Platform {platform} has no scrape mapping.",
        "scrape_manual_title": "Manual Search Name",
        "scrape_manual_hint": "Auto-match failed.\nLibretro names are usually 'Game Name (Region)'. Try English name or remove parentheses.",
        "scrape_manual_prompt": "Search name:",
        "scrape_manual_retry": "Retry",
        "scrape_manual_skip": "Skip",
        "scrape_batch_title": "Batch Scrape Covers",
        "scrape_batch_scope": "Scope",
        "scrape_batch_all": "All games",
        "scrape_batch_fav": "Favorites only",
        "scrape_batch_platform": "Current platform",
        "scrape_batch_count": "{n} games to scrape",
        "scrape_batch_none": "No games to scrape (all have covers, or platform unsupported)",
        "scrape_batch_start": "Start Batch Scrape",
        "scrape_already_has": "Already has cover, skipped",
        "scrape_failed_list": "Failed list (manual retry)",
        "scrape_retry_failed": "Retry all failed",
        "scrape_source_note": "Libretro Thumbnails is a free community library for classic platforms.\nSteamGridDB covers modern platforms, needs your own API key.",
        "settings_priority": "Process Priority",
        "settings_priority_hint": "Boost the game process priority on launch for steadier framerate.\n'High' needs no admin; 'Realtime' needs admin and may lag the whole system.",
        "settings_priority_low": "Low (IDLE)",
        "settings_priority_normal": "Normal (system default)",
        "settings_priority_high": "High (recommended)",
        "settings_priority_realtime": "Realtime (⚠ dangerous)",
        "settings_priority_children": "Also adjust child processes (recommended)",
        "settings_priority_auto": "Apply automatically after launch",
        "settings_priority_applied": "Priority applied: {level}",
        "settings_priority_failed": "Failed to set priority (may need admin)",
        "settings_priority_realtime_warn": "Realtime priority may lag the whole system (keyboard/mouse). Continue?",
        "settings_priority_relaunch": "Admin rights required. Relaunch as admin?",
        "engine_settings_title": "Open Emulator Settings",
        "engine_settings_hint": "Launches the emulator without a game, entering its own settings UI.",
        "engine_settings_launched": "Opened {engine} settings",
        "engine_settings_failed": "Launch failed: {err}",
        "engine_not_found": "Engine config not found",
        "settings_version": "Engine Version",
        "settings_version_auto_detect": "Auto-detect engine version on launch",
        "settings_version_hint": "Detected version is used to apply version_overrides (per-version arg differences).",
        "version_unknown_warn": "Engine version unknown, using defaults. Right-click 'Re-detect version' to retry.",
        "lan_title": "LAN",
        "lan_tab_chat": "💬 Chat",
        "lan_tab_share": "📁 Share",
        "lan_my_name": "Nickname",
        "lan_peers": "Peers",
        "lan_broadcast_name": "Everyone",
        "lan_no_peers": "No peers found.",
        "lan_send": "Send",
        "lan_input_ph": "Type a message, Enter to send…",
        "lan_send_file": "Send File",
        "lan_file_offer": "[File] {name}  ({size})",
        "lan_file_done": "Received: {name}",
        "lan_file_failed": "File receive failed: {err}",
        "lan_file_sent": "Sent: {name}  ({size})",
        "lan_file_rejected": "Peer declined the file",
        "lan_file_disabled": "File receiving disabled in settings",
        "lan_file_hash_ok": "File hash verified",
        "lan_file_hash_bad": "⚠ Hash mismatch, file discarded",
        "lan_clear_history": "Clear History",
        "lan_open_received": "Open Received Dir",
        "lan_open_shared": "Open Shared Dir",
        "lan_open_shared_download": "Open Download Dir",
        "lan_enabled": "Enable LAN",
        "lan_nickname_setting": "LAN nickname",
        "lan_port_setting": "Listen port",
        "lan_password_setting": "LAN password",
        "lan_password_hint": "Empty = no check.",
        "lan_keep_history": "Keep chat history on disk",
        "lan_receive_files": "Allow receiving files",
        "lan_verify_hash": "SHA-256 verification",
        "lan_max_file": "Max file size (MB)",
        "lan_share_enabled": "Allow others to browse my shared folder",
        "lan_notify_on_receive": "Popup on file received",
        "lan_error_port": "Port in use, change in settings",
        "lan_error_start": "LAN service failed: {err}",
        "lan_self_msg": "Me",
        "lan_peer_joined": "'{name}' is online",
        "lan_peer_left": "'{name}' is offline",
        "lan_msg_failed": "Message failed (peer offline?)",
        "lan_firewall_hint": "Windows will ask for firewall permission. Allow on Private networks.",
        "lan_proto_note": "Plaintext LAN traffic.",
        "lan_pending_files": "Receiving: {name}  {pct}%",
        "lan_peer_send_file": "Peer is sending a file…",
        "lan_wait_accept": "Waiting for peer to accept…",
        "lan_no_ack": "Peer did not acknowledge",
        "lan_file_io_fail": "Peer cannot write file (disk/permission)",
        "lan_share_title": "Shared Folder",
        "lan_share_hint": "Drop files into 'My shared'. All online peers can see and download them.",
        "lan_share_my": "My shared",
        "lan_share_others": "Others' shared",
        "lan_share_col_file": "File",
        "lan_share_col_size": "Size",
        "lan_share_col_op": "Op",
        "lan_share_col_source": "Source",
        "lan_share_add": "➕ Add Files",
        "lan_share_remove": "Remove",
        "lan_share_remove_confirm": "Unshare {name}?\n(Only deletes the shared copy.)",
        "lan_share_refresh": "🔄 Refresh",
        "lan_share_download": "Download",
        "lan_share_downloading": "Downloading…",
        "lan_share_download_done": "Downloaded {name} from {peer}\nSaved to:\n{path}",
        "lan_share_download_fail": "Download failed: {name}  {reason}",
        "lan_share_no_peers": "No other peers online.",
        "lan_share_no_port": "Peers found, but ports not yet known.\nWait ~5 seconds and retry.",
        "lan_share_all_fail": "Queried {n} peers, no response.\nMaybe they disabled sharing or firewall blocks.",
        "lan_share_my_dir": "Local shared dir",
        "lan_ctx_open": "Open conversation",
        "lan_ctx_ping": "Send ping",
        "lan_ctx_send_file": "📎 Send file to peer",
        "lan_ctx_send_file_all": "📎 Send file to everyone",
        "lan_ctx_clear": "Clear history",
        "lan_emoji_tip": "Emoji",
        "lan_broadcast_title": "📢 Everyone (broadcast to all peers)",
        "lan_broadcast_confirm": "Broadcast {name} ({size}) to {n} peers?",
        "lan_broadcast_done": "Broadcast done: {name}  {ok}/{total}",
        "lan_broadcast_one_ok": "✅ {peer} received",
        "lan_broadcast_one_fail": "❌ {peer}: {reason}",
        "lan_broadcast_no_peers": "No other peers online.",
        "lan_drop_title": "Drop confirm",
        "lan_drop_to_peer": "Send {n} files to {peer}?",
        "lan_drop_to_broadcast": "Broadcast {n} files to all peers?",
        "lan_drop_no_target": "Select a peer or Everyone first.",
        "lan_drop_ask_share": "Dropped {n} files.\nBroadcast doesn't send files directly. Add all to shared folder?",
        "lan_peer_offline": "Peer is offline.",
        "lan_peer_port_unknown": "Peer port not yet known, wait 1~2 seconds and retry.",
        "lan_port_unknown": "Peer port not yet known, wait 1~2 seconds.",
        "webtransfer_title": "LAN Transfer",
        "webtransfer_hint": "Embedded LocalSend Web. Auto-discovers nearby devices.\n💡 Upload works in embedded page. For download, click 'Open in browser' (top-right).",
        "webtransfer_open_external": "Open in browser",
        "webtransfer_reload": "Reload",
        "webtransfer_native": "LocalSend website",
        "webtransfer_fallback": (
            "QtWebEngine not found.\n\n"
            "1. Install PySide6-WebEngine and restart;\n"
            "2. Or open LocalSend Web in your browser."),
        "webtransfer_url": "https://web.localsend.org/",
        "webtransfer_install_btn": "Install PySide6-WebEngine",
        "webtransfer_install_confirm": "Will run: pip install PySide6-WebEngine\n\n~200MB download. Continue?",
        "webtransfer_install_started": "Installing in a new window.\nRestart mikan_emu after install finishes.",
        "webtransfer_install_failed": "Failed to start installer.",
        "msg_ok": "OK", "msg_cancel": "Cancel", "msg_warning": "Warning",
        "msg_error": "Error", "msg_info": "Info", "msg_confirm": "Confirm",
        "plugins_title": "Plugins",
        "plugins_hint": "Plugins go in data/mikan_emu/plugins/<id>/, with plugin.json and main.py.\nEnable/disable or import new plugins, then click 'Restart App' to apply.",
        "plugins_col_enabled": "Enabled",
        "plugins_col_id": "ID",
        "plugins_col_name": "Name",
        "plugins_col_version": "Version",
        "plugins_open_dir": "📂 Open Plugins Dir",
        "plugins_import_zip": "📥 Import Plugin Zip",
        "plugins_rescan": "🔄 Rescan",
        "plugins_restart": "♻ Restart App",
        "plugins_import_title": "Import Plugin",
        "plugins_import_success": "Plugin '{name}' imported.\nClick 'Restart App' to apply.",
        "plugins_import_no_meta": "No plugin.json found in the archive",
        "plugins_import_overwrite": "Plugin {pid} already exists, overwrite?",
        "plugins_import_failed": "Import failed: {err}",
        "plugins_toggle_hint": "Plugin {pid} {state}.\nClick 'Restart App' to apply.",
        "plugins_state_enabled": "enabled",
        "plugins_state_disabled": "disabled",
        "plugins_restart_confirm": "The app will close and restart.\nContinue?",
        "plugins_load_failed": "Plugin {pid} failed to load: {err}",
        "log_viewer_title": "Logs & Diagnostics",
        "log_level_all": "All",
        "log_auto_scroll": "Auto scroll",
        "log_clear_buffer": "Clear buffer",
        "log_open_dir": "Open Log Dir",
        "log_export_pack": "📦 Export Diagnostics",
        "log_count": "Showing {shown} / {total} in buffer",
        "log_export_success": "Diagnostic pack saved:\n{path}\n\nOpen containing folder?",
        "log_viewer_level": "Level",
        "log_viewer_filter": "Filter",
        "log_filter_ph": "Keyword (e.g. plugin / download)",
        "crash_title": "Application Error",
        "crash_body": "mikan_emu encountered an unhandled exception.",
        "crash_pack_ready": "Diagnostic pack saved:\n{path}",
        "crash_pack_failed": "Failed to create diagnostic pack. Please check log folder.",
        "crash_save_pack": "Save diagnostic pack…",
        "crash_open_log": "Open log folder",
        "crash_close": "Close",
        "settings_log_diag": "📋 Logs & Diagnostics",
        "settings_log_level": "Log level",
        "settings_log_keep_days": "Keep log for (days)",
        "settings_crash_report_enabled": "Auto-generate diagnostics on uncaught exception",
        "win_version_too_old_title": "OS Version Too Old",
        "win_version_too_old": "Current Windows build {build} is below Qt6 minimum 17763 (Win10 1809).\nPlease upgrade or use older mikan_emu.",
        "win_version_label": "OS: {name} (build {build}) · Machine tier: {tier}",
        "machine_tier_title": "Resource Policy",
        "machine_tier_label": "Machine tier",
        "machine_tier_low": "Low (old PC)",
        "machine_tier_mid": "Mid",
        "machine_tier_high": "High",
        "machine_tier_auto": "Auto-detect",
        "machine_tier_low_spec": "Low-spec mode (disable grid view / perf window)",
        "machine_tier_detected": "Detected: {cpu_p}C/{cpu_l}T · {mem_gb} GB RAM · limits: {cpu_limit} cores / {mem_limit} MB",
        "resource_policy_enable": "Enable resource policy",
        "resource_cpu_cores": "CPU cores (0 = auto)",
        "resource_mem_mb": "Memory suggestion MB (record only, Windows cannot enforce)",
        "resource_force_unlock": "⚠ Force unlock (ignore {ratio}% cap)",
        "resource_force_unlock_warn": "Force unlock ignores {ratio}% safety cap and may cause system lag or OOM.\nContinue?",
        "resource_safety_ratio": "Safety cap percentage",
        "folder_new_workspace": "New Workspace",
        "folder_untitled": "Untitled Workspace",
        "file_not_found": "File not found: {path}",
        "open_failed": "Open failed: {e}",
        "copy_info_done": "Copied",
        # ★ v1.8.0 新增
        "settings_github_token": "GitHub Token (optional)",
        "settings_github_token_hint": "Used for update checks, raises API rate limit. Empty = anonymous (60/hour).",
        "settings_job_object": "Job Object",
        "settings_job_object_kill": "Kill emulators when main app exits",
        "settings_job_object_hint": "When checked, closing mikan_emu will also terminate all emulators it launched (prevents orphans).",
        "settings_keymap": "Virtual Key Mapping",
        "settings_keymap_enable": "Enable virtual key mapping",
        "settings_keymap_only_foreground": "Only when emulator window is foreground",
        "settings_keymap_show_osd": "Show OSD on remap",
        "settings_keymap_hint": "Map physical keys to emulator keys. E.g. press A sends B.\nNote: requires 'keyboard' library. Only works for emulators launched by mikan_emu.",
        "keymap_title": "Virtual Key Mapping",
        "keymap_add": "Add Mapping",
        "keymap_remove": "Remove",
        "keymap_clear": "Clear",
        "keymap_save": "Save",
        "keymap_col_physical": "Physical Key",
        "keymap_col_virtual": "Send to Emulator",
        "keymap_col_enabled": "Enabled",
        "keymap_col_note": "Note",
        "keymap_record_hint": "Click 'Record' then press a key",
        "keymap_record_btn": "Record",
        "keymap_cancel_record": "Cancel",
        "keymap_test": "Test",
        "keymap_test_hint": "Press keys in the input below to test mapping",
        "keymap_no_keyboard": "'keyboard' library not installed.\nRun: pip install keyboard",
        "keymap_saved": "Key mapping saved",
        "keymap_duplicate": "Physical key {key} already exists",
        "keymap_recording": "Press the physical key to map…",
        "keymap_recorded": "Recorded: {key}",
        "keymap_virtual_ph": "e.g. space / enter / a",
        "update_dialog_title": "Check Updates",
        "update_dialog_check": "Check All",
        "update_dialog_engine": "Engine",
        "update_dialog_current": "Current",
        "update_dialog_available": "Available",
        "update_dialog_published": "Published",
        "update_dialog_action": "Action",
        "update_dialog_use_mirror": "Use mirror acceleration",
        "update_dialog_update": "Update",
        "update_dialog_no_releases": "No releases",
        "update_dialog_fetching": "Fetching release list…",
        "update_dialog_fetch_failed": "Fetch failed: {err}",
        "update_dialog_all_latest": "All engines up to date",
        "update_dialog_confirm": "Update {engine} to {version}?\n\n{notes}",
        "update_dialog_prerelease": "Pre-release",
        "update_dialog_select": "Select version",
        "update_dialog_token_hint": "Tip: set GitHub Token in Settings to raise rate limit.",
        "param_schema_title": "Emulator Parameters",
        "param_schema_hint": "Define launch parameters for this emulator. Checked/filled values are appended to the command line.",
        "param_schema_empty": "No parameter template for this engine. You can still fill 'Extra args' manually.",
        "param_schema_reset": "Reset",
        "param_schema_preview": "Command preview",
        "param_schema_apply": "Save Parameters",
        "param_schema_saved": "Parameters saved",
        "osd_keymap": "🔁 {physical} → {virtual}",
        "job_running": "Job running…",
        "job_cancelled": "Cancelled",
        "job_failed": "Failed: {err}",
        "job_done": "Done",
    },
}


def _machine_translate(zh_pack: dict, lang: str) -> dict:
    MAPS = {
        "ru": {
            "游戏库": "Библиотека", "模拟器": "Эмуляторы", "设置": "Настройки",
            "统计": "Статистика", "资源": "Ресурсы", "局域网": "Локальная сеть",
            "局域网传输": "Локальная передача",
            "导入": "Импорт", "下载": "Скачать",
            "刷新": "Обновить", "全部平台": "Все платформы",
            "名称": "Имя", "平台": "Платформа",
            "大小": "Размер", "时长": "Время", "路径": "Путь",
            "收藏": "Избранное", "最近": "Недавние", "全部": "Все",
            "启动": "Запуск", "取消": "Отмена", "确定": "OK",
            "警告": "Внимание", "错误": "Ошибка", "提示": "Инфо",
            "确认": "Подтвердить", "保存": "Сохранить",
            "语言": "Язык", "工作区": "Рабочая область",
            "管理员权限": "Права администратора",
            "下载线程数": "Потоки загрузки", "添加": "Добавить",
            "删除": "Удалить", "上移": "Вверх", "下移": "Вниз",
            "测试全部": "Проверить все", "恢复默认": "Сбросить",
            "系统托盘": "Системный трей",
        },
        "ja": {
            "游戏库": "ライブラリ", "模拟器": "エミュレータ", "设置": "設定",
            "统计": "統計", "资源": "リソース", "局域网": "LAN",
            "局域网传输": "LAN 転送",
            "导入": "インポート", "下载": "ダウンロード",
            "刷新": "更新", "全部平台": "すべてのプラットフォーム",
            "名称": "名前", "平台": "プラットフォーム",
            "大小": "サイズ", "时长": "プレイ時間", "路径": "パス",
            "收藏": "お気に入り", "最近": "最近", "全部": "すべて",
            "启动": "起動", "取消": "キャンセル", "确定": "OK",
            "警告": "警告", "错误": "エラー", "提示": "情報",
            "确认": "確認", "保存": "保存",
            "语言": "言語", "工作区": "ワークスペース",
            "管理员权限": "管理者権限",
            "下载线程数": "ダウンロードスレッド数", "添加": "追加",
            "删除": "削除", "上移": "上へ", "下移": "下へ",
            "测试全部": "すべてテスト", "恢复默认": "デフォルトに戻す",
            "系统托盘": "システムトレイ",
        },
        "fr": {
            "游戏库": "Bibliothèque", "模拟器": "Émulateurs", "设置": "Paramètres",
            "统计": "Statistiques", "资源": "Ressources", "局域网": "LAN",
            "局域网传输": "Transfert LAN",
            "导入": "Importer", "下载": "Télécharger",
            "刷新": "Actualiser", "全部平台": "Toutes les plateformes",
            "名称": "Nom", "平台": "Plateforme",
            "大小": "Taille", "时长": "Durée", "路径": "Chemin",
            "收藏": "Favoris", "最近": "Récents", "全部": "Tout",
            "启动": "Lancer", "取消": "Annuler", "确定": "OK",
            "警告": "Avertissement", "错误": "Erreur", "提示": "Info",
            "确认": "Confirmer", "保存": "Enregistrer",
            "语言": "Langue", "工作区": "Espace de travail",
            "管理员权限": "Droits admin",
            "下载线程数": "Threads de téléchargement", "添加": "Ajouter",
            "删除": "Supprimer", "上移": "Monter", "下移": "Descendre",
            "测试全部": "Tout tester", "恢复默认": "Réinitialiser",
            "系统托盘": "Barre système",
        },
    }
    m = MAPS.get(lang, {})
    out = {}
    for k, v in zh_pack.items():
        if k == "_meta":
            out[k] = {"name": {"ru": "Русский", "ja": "日本語", "fr": "Français"}.get(lang, lang),
                      "code": lang, "translator": "machine-translated"}
        elif isinstance(v, str) and v in m:
            out[k] = m[v]
        else:
            out[k] = v
    return out


def _fill_missing_langs():
    for lang in ("ru", "ja", "fr"):
        if lang not in DEFAULT_LANG_PACKS:
            DEFAULT_LANG_PACKS[lang] = _machine_translate(DEFAULT_LANG_PACKS["zh"], lang)


_fill_missing_langs()


def _ensure_lang_files():
    existing = {p.stem for p in LANG_DIR.glob("*.json")}
    for code, pack in DEFAULT_LANG_PACKS.items():
        fp = LANG_DIR / f"{code}.json"
        if code not in existing:
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(pack, f, ensure_ascii=False, indent=2)
                logger.info(f"生成语言文件: {fp}")
            except Exception as e:
                logger.exception(f"写入语言文件失败: {e}")


LANG_PACKS: dict = {}
CURRENT_LANG = "zh"


def load_all_langs():
    global LANG_PACKS
    _ensure_lang_files()
    LANG_PACKS = {}
    for fp in LANG_DIR.glob("*.json"):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            code = fp.stem
            for k, v in DEFAULT_LANG_PACKS.get("zh", {}).items():
                if k == "_meta":
                    data.setdefault("_meta", v)
                else:
                    data.setdefault(k, v)
            LANG_PACKS[code] = data
        except Exception as e:
            logger.exception(f"加载语言文件失败 {fp}: {e}")
    if not LANG_PACKS:
        LANG_PACKS = {"zh": DEFAULT_LANG_PACKS["zh"]}


def tr(key: str, **kwargs) -> str:
    pack = LANG_PACKS.get(CURRENT_LANG) or LANG_PACKS.get("zh") or {}
    text = pack.get(key) or DEFAULT_LANG_PACKS.get("zh", {}).get(key, key)
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
    load_all_langs()
    if LANG_FILE.exists():
        try:
            with open(LANG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            lang = data.get("language", "zh")
            if lang not in LANG_PACKS:
                lang = "zh"
            CURRENT_LANG = lang
            logger.info(f"已加载语言: {CURRENT_LANG}")
            return
        except Exception as e:
            logger.exception(f"加载语言失败: {e}")
    CURRENT_LANG = "zh"
    save_lang("zh")

# ============================================================
# 5. 配置加载
# ============================================================
FOLDERS_CONFIG = {"folders": [], "active_index": 0}
SETTINGS = dict(DEFAULT_SETTINGS_JSON)
SAVE_PATHS: dict = {}
CHEAT_PATHS: dict = {}
MIRRORS_CONFIG = json.loads(json.dumps(DEFAULT_MIRRORS_JSON))
RESOURCES_CONFIG = json.loads(json.dumps(DEFAULT_RESOURCES_JSON))
STATS: dict = {}
UPDATE_IGNORE: dict = {}

_FOLDER_TYPE_MIGRATION = {
    "mixed": "mixed",
    "rom": "rom",
    "bios": "bios",
    "general": "mixed",
    "": "mixed",
}


def _normalize_folder_entry(folder: dict) -> dict:
    if not isinstance(folder, dict):
        return {"name": tr("folder_untitled"), "path": str(DATA_DIR), "type": "mixed"}
    name = (folder.get("name") or tr("folder_untitled")).strip() or tr("folder_untitled")
    path = (folder.get("path") or str(DATA_DIR)).strip() or str(DATA_DIR)
    ftype = _FOLDER_TYPE_MIGRATION.get(
        (folder.get("type") or "mixed").lower(), "mixed")
    return {"name": name, "path": path, "type": ftype}


def load_folders_config():
    global FOLDERS_CONFIG
    if FOLDERS_FILE.exists():
        try:
            with open(FOLDERS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.exception(f"加载 folders 失败: {e}")
            raw = None
        if isinstance(raw, dict) and isinstance(raw.get("folders"), list):
            normalized = [_normalize_folder_entry(x) for x in raw["folders"]]
            idx = raw.get("active_index", 0)
            try:
                idx = int(idx)
            except Exception:
                idx = 0
            if not (0 <= idx < len(normalized)):
                idx = 0
            FOLDERS_CONFIG = {"folders": normalized, "active_index": idx}
            return

    FOLDERS_CONFIG = json.loads(json.dumps(DEFAULT_FOLDERS_JSON))
    FOLDERS_CONFIG["folders"] = [
        _normalize_folder_entry(x) for x in FOLDERS_CONFIG.get("folders", [])
    ]


def save_folders_config():
    try:
        with open(FOLDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(FOLDERS_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 folders 失败: {e}")


def load_settings():
    global SETTINGS
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                SETTINGS.update(json.load(f))
        except Exception as e:
            logger.exception(f"加载 settings 失败: {e}")
    for k, v in DEFAULT_SETTINGS_JSON.items():
        SETTINGS.setdefault(k, json.loads(json.dumps(v)) if isinstance(v, (dict, list)) else v)


def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(SETTINGS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 settings 失败: {e}")


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
    except Exception as e:
        logger.exception(f"保存 save_paths 失败: {e}")


def load_cheat_paths():
    global CHEAT_PATHS
    if CHEAT_PATHS_FILE.exists():
        try:
            with open(CHEAT_PATHS_FILE, "r", encoding="utf-8") as f:
                CHEAT_PATHS = json.load(f)
        except Exception:
            CHEAT_PATHS = {}


def save_cheat_paths():
    try:
        with open(CHEAT_PATHS_FILE, "w", encoding="utf-8") as f:
            json.dump(CHEAT_PATHS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 cheat_paths 失败: {e}")


def _migrate_mirrors_v1_to_v2(data: dict) -> dict:
    """把旧版 mirrors 字符串列表迁移成 dict 列表。"""
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT_MIRRORS_JSON))

    out = dict(data)
    out.setdefault("enabled", True)
    out.setdefault("auto", True)
    out.setdefault("region", "auto")
    out.setdefault("probe_timeout", 3.0)
    out.setdefault("probe_cache_ttl", 300)

    def _convert(lst, is_api=False):
        result = []
        for item in lst or []:
            if isinstance(item, dict):
                item.setdefault("enabled", True)
                item.setdefault("region", "direct" if not item.get("url") else "cn")
                item.setdefault("weight", 5)
                result.append(item)
            elif isinstance(item, str):
                result.append({
                    "url": item,
                    "enabled": True,
                    "region": "direct" if not item else "cn",
                    "weight": 5,
                })
        if not result:
            default = DEFAULT_MIRRORS_JSON["api_mirrors" if is_api else "mirrors"]
            result = json.loads(json.dumps(default))
        return result

    out["mirrors"] = _convert(out.get("mirrors", []), is_api=False)
    out["api_mirrors"] = _convert(out.get("api_mirrors", []), is_api=True)
    return out


def load_mirrors():
    global MIRRORS_CONFIG
    if MIRRORS_FILE.exists():
        try:
            with open(MIRRORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            MIRRORS_CONFIG = _migrate_mirrors_v1_to_v2(data)
        except Exception:
            MIRRORS_CONFIG = json.loads(json.dumps(DEFAULT_MIRRORS_JSON))
    else:
        MIRRORS_CONFIG = json.loads(json.dumps(DEFAULT_MIRRORS_JSON))


def save_mirrors():
    try:
        with open(MIRRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(MIRRORS_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 mirrors 失败: {e}")


def load_resources():
    global RESOURCES_CONFIG
    if RESOURCES_FILE.exists():
        try:
            with open(RESOURCES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "groups" not in data or not isinstance(data["groups"], list):
                data = json.loads(json.dumps(DEFAULT_RESOURCES_JSON))
            RESOURCES_CONFIG = data
        except Exception:
            RESOURCES_CONFIG = json.loads(json.dumps(DEFAULT_RESOURCES_JSON))


def save_resources():
    try:
        with open(RESOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(RESOURCES_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 resources 失败: {e}")


def load_stats():
    global STATS
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                STATS = json.load(f)
        except Exception:
            STATS = json.loads(json.dumps(DEFAULT_STATS_JSON))
    STATS.setdefault("daily", {})
    STATS.setdefault("launches", 0)


def save_stats():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(STATS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 stats 失败: {e}")


def load_update_ignore():
    global UPDATE_IGNORE
    if UPDATE_IGNORE_FILE.exists():
        try:
            with open(UPDATE_IGNORE_FILE, "r", encoding="utf-8") as f:
                UPDATE_IGNORE = json.load(f)
        except Exception:
            UPDATE_IGNORE = {}


def save_update_ignore():
    try:
        with open(UPDATE_IGNORE_FILE, "w", encoding="utf-8") as f:
            json.dump(UPDATE_IGNORE, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 update_ignore 失败: {e}")


def get_mirror_list() -> list:
    if not MIRRORS_CONFIG.get("enabled", True):
        return [{"url": "", "region": "direct", "enabled": True, "weight": 1}]
    mirrors = MIRRORS_CONFIG.get("mirrors", [])
    if not mirrors:
        return [{"url": "", "region": "direct", "enabled": True, "weight": 1}]
    return mirrors


def get_api_mirror_list() -> list:
    if not MIRRORS_CONFIG.get("enabled", True):
        return [{"url": "", "region": "direct", "enabled": True, "weight": 1}]
    mirrors = MIRRORS_CONFIG.get("api_mirrors", [])
    if not mirrors:
        return [{"url": "", "region": "direct", "enabled": True, "weight": 1}]
    return mirrors


def get_active_folder() -> dict:
    folders = FOLDERS_CONFIG.get("folders", [])
    idx = FOLDERS_CONFIG.get("active_index", 0)
    if folders and 0 <= idx < len(folders):
        return folders[idx]
    return {"name": tr("folder_untitled"), "path": str(DATA_DIR), "type": "mixed"}


def get_active_rom_dir() -> Path:
    f = get_active_folder()
    ftype = f.get("type", "mixed")
    base = Path(f.get("path", str(DATA_DIR)))
    if ftype == "bios":
        return ROM_DIR
    return base / "roms" if (base / "roms").exists() or ftype == "mixed" else ROM_DIR


def get_active_bios_dir() -> Path:
    f = get_active_folder()
    ftype = f.get("type", "mixed")
    base = Path(f.get("path", str(DATA_DIR)))
    if ftype == "rom":
        return BIOS_DIR
    return base / "bios" if (base / "bios").exists() or ftype == "mixed" else BIOS_DIR


def get_active_save_dir() -> Path:
    f = get_active_folder()
    base = Path(f.get("path", str(DATA_DIR)))
    return base / "saves" if (base / "saves").exists() else SAVE_DIR


load_folders_config()
load_settings()
load_save_paths()
load_cheat_paths()
load_mirrors()
load_resources()
load_stats()
load_update_ignore()

setup_logging()


# ============================================================
# 5.1 Windows 版本 + 硬件探测
# ============================================================
_HW_CACHE: dict = {}


def get_windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        try:
            for key_name in ("CurrentBuild", "CurrentBuildNumber"):
                try:
                    val, _ = winreg.QueryValueEx(key, key_name)
                    try:
                        return int(str(val))
                    except (ValueError, TypeError):
                        continue
                except FileNotFoundError:
                    continue
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass
    return 0


def check_win10_1809_minimum() -> tuple:
    build = get_windows_build()
    if build == 0:
        return True, ""
    if build < 17763:
        return False, tr("win_version_too_old", build=build)
    return True, ""


def probe_hardware(force: bool = False) -> dict:
    global _HW_CACHE
    if _HW_CACHE and not force:
        return _HW_CACHE

    info = {
        "cpu_logical": 1,
        "cpu_physical": 1,
        "mem_total_mb": 0,
        "mem_available_mb": 0,
        "has_psutil": HAS_PSUTIL,
    }
    if HAS_PSUTIL:
        try:
            info["cpu_logical"] = psutil.cpu_count(logical=True) or 1
            info["cpu_physical"] = psutil.cpu_count(logical=False) or info["cpu_logical"]
            vm = psutil.virtual_memory()
            info["mem_total_mb"] = vm.total // (1024 * 1024)
            info["mem_available_mb"] = vm.available // (1024 * 1024)
        except Exception as e:
            logger.warning(f"硬件探测失败: {e}")

    try:
        ratio = int(SETTINGS.get("resource_safety_ratio", 85)) / 100.0
    except Exception:
        ratio = 0.85
    info["cpu_limit"] = max(1, int(info["cpu_logical"] * ratio))
    info["mem_limit_mb"] = int(info["mem_total_mb"] * ratio)

    _HW_CACHE = info
    return info


def detect_machine_tier() -> str:
    hw = probe_hardware()
    cpu = hw["cpu_physical"]
    mem_gb = hw["mem_total_mb"] / 1024.0
    if cpu <= 2 or mem_gb < 4:
        return "low"
    if cpu <= 4 and mem_gb < 8:
        return "mid"
    return "high"


def refresh_machine_tier():
    if not SETTINGS.get("machine_tier_auto", True):
        return
    tier = detect_machine_tier()
    SETTINGS["machine_tier"] = tier
    SETTINGS["low_spec_mode"] = (tier == "low")
    save_settings()
    logger.info(f"机器档次: {tier}（低配模式={'开' if tier == 'low' else '关'}）")


ENGINE_RECOMMENDATIONS = {
    "pcsx2":       {"low": {"cores": 2, "mem_mb": 2048}, "mid": {"cores": 4, "mem_mb": 4096}, "high": {"cores": 6, "mem_mb": 8192}},
    "duckstation": {"low": {"cores": 2, "mem_mb": 1024}, "mid": {"cores": 2, "mem_mb": 4096}, "high": {"cores": 4, "mem_mb": 8192}},
    "rpcs3":       {"low": {"cores": 4, "mem_mb": 4096}, "mid": {"cores": 6, "mem_mb": 8192}, "high": {"cores": 8, "mem_mb": 16384}},
    "dolphin":     {"low": {"cores": 2, "mem_mb": 2048}, "mid": {"cores": 4, "mem_mb": 4096}, "high": {"cores": 4, "mem_mb": 8192}},
    "cemu":        {"low": {"cores": 4, "mem_mb": 4096}, "mid": {"cores": 4, "mem_mb": 8192}, "high": {"cores": 6, "mem_mb": 16384}},
    "shadps4":     {"low": {"cores": 4, "mem_mb": 4096}, "mid": {"cores": 6, "mem_mb": 8192}, "high": {"cores": 8, "mem_mb": 16384}},
    "xemu":        {"low": {"cores": 2, "mem_mb": 2048}, "mid": {"cores": 4, "mem_mb": 4096}, "high": {"cores": 4, "mem_mb": 8192}},
    "flycast":     {"low": {"cores": 2, "mem_mb": 1024}, "mid": {"cores": 2, "mem_mb": 2048}, "high": {"cores": 4, "mem_mb": 4096}},
    "mgba":        {"low": {"cores": 1, "mem_mb": 512},  "mid": {"cores": 2, "mem_mb": 1024}, "high": {"cores": 2, "mem_mb": 2048}},
    "snes9x":      {"low": {"cores": 1, "mem_mb": 512},  "mid": {"cores": 2, "mem_mb": 1024}, "high": {"cores": 2, "mem_mb": 2048}},
    "fceux":       {"low": {"cores": 1, "mem_mb": 256},  "mid": {"cores": 1, "mem_mb": 512},  "high": {"cores": 2, "mem_mb": 1024}},
    "desmume":     {"low": {"cores": 1, "mem_mb": 512},  "mid": {"cores": 2, "mem_mb": 1024}, "high": {"cores": 2, "mem_mb": 2048}},
    "melonds":     {"low": {"cores": 2, "mem_mb": 1024}, "mid": {"cores": 2, "mem_mb": 2048}, "high": {"cores": 4, "mem_mb": 4096}},
    "mednafen":    {"low": {"cores": 1, "mem_mb": 512},  "mid": {"cores": 2, "mem_mb": 1024}, "high": {"cores": 2, "mem_mb": 2048}},
    "retroarch":   {"low": {"cores": 1, "mem_mb": 512},  "mid": {"cores": 2, "mem_mb": 2048}, "high": {"cores": 4, "mem_mb": 4096}},
}


def get_recommended_policy(engine_name: str) -> dict:
    tier = SETTINGS.get("machine_tier", "mid")
    rec = ENGINE_RECOMMENDATIONS.get(engine_name, {})
    entry = rec.get(tier) or rec.get("mid") or {"cores": 2, "mem_mb": 2048}
    hw = probe_hardware()
    cores = min(int(entry["cores"]), int(hw["cpu_limit"]))
    mem = min(int(entry["mem_mb"]), int(hw["mem_limit_mb"]))
    return {"cores": cores, "mem_mb": mem, "tier": tier}


def validate_resource_policy(cores: int, mem_mb: int) -> tuple:
    if SETTINGS.get("resource_force_unlock", False):
        return True, ""
    hw = probe_hardware()
    if cores > hw["cpu_limit"]:
        return False, f"CPU 核心数 {cores} 超过安全上限 {hw['cpu_limit']}"
    if mem_mb > hw["mem_limit_mb"]:
        return False, f"内存 {mem_mb}MB 超过安全上限 {hw['mem_limit_mb']}MB"
    return True, ""


def apply_resource_policy(pid: int, cores: int, mem_mb: int) -> tuple:
    if not HAS_PSUTIL:
        return False, "psutil 未安装"
    try:
        proc = psutil.Process(pid)
    except Exception as e:
        return False, str(e)

    applied = []

    if cores > 0:
        try:
            hw = probe_hardware()
            n = min(int(cores), int(hw["cpu_logical"]))
            if n < 1:
                n = 1
            
            # ★ 修复：避开 0 号核心，从 1 号开始绑（如果核心数够的话）
            if hw["cpu_logical"] > 1:
                affinity = list(range(1, n + 1))
                # 如果算出来超出了总核心数，就退回到从 0 开始
                if max(affinity) >= hw["cpu_logical"]:
                    affinity = list(range(n))
            else:
                affinity = [0] # 单核老机器没办法，只能绑 0
                
            proc.cpu_affinity(affinity)
            applied.append(f"CPU 亲和性: {affinity}")
        except Exception as e:
            logger.warning(f"CPU 亲和性设置失败: {e}")

    if mem_mb > 0:
        logger.info(
            f"内存建议: 目标 {mem_mb}MB"
            f"（Windows 无原生 per-process 限额，仅记录）")

    if applied:
        logger.info(f"资源策略已应用: {'; '.join(applied)}")
        return True, ""
    return False, "无可应用的策略"

    if mem_mb > 0:
        logger.info(
            f"内存建议: 目标 {mem_mb}MB"
            f"（Windows 无原生 per-process 限额，仅记录）")

    if applied:
        logger.info(f"资源策略已应用: {'; '.join(applied)}")
        return True, ""
    return False, "无可应用的策略"


# ============================================================
# 5.2 崩溃诊断包
# ============================================================
def _collect_system_info() -> str:
    lines = []
    try:
        lines.append(f"mikan_emu {APP_VERSION}")
    except Exception:
        lines.append("mikan_emu ?")
    try:
        lines.append(f"Python {sys.version}")
    except Exception:
        pass
    try:
        lines.append(f"Platform: {sys.platform} {_platform.platform()}")
    except Exception:
        lines.append(f"Platform: {sys.platform}")
    try:
        lines.append(f"Frozen: {getattr(sys, 'frozen', False)}")
    except Exception:
        pass
    try:
        lines.append(f"Admin: {is_admin()}")
    except Exception:
        pass
    try:
        lines.append(f"Windows Build: {get_windows_build()}")
    except Exception:
        pass
    try:
        lines.append(f"Machine Tier: {SETTINGS.get('machine_tier', '?')}")
    except Exception:
        pass
    try:
        lines.append(f"BASE_DIR: {BASE_DIR}")
        lines.append(f"DATA_DIR: {DATA_DIR}")
    except Exception:
        pass

    if HAS_PSUTIL:
        try:
            lines.append(f"CPU: {psutil.cpu_count(logical=False)}C/"
                         f"{psutil.cpu_count()}T")
            vm = psutil.virtual_memory()
            lines.append(f"RAM: {vm.total / (1 << 30):.1f} GB "
                         f"(可用 {vm.available / (1 << 30):.1f} GB)")
        except Exception as e:
            lines.append(f"psutil 信息读取失败: {e}")

    for mod, pkg in OPTIONAL.items():
        try:
            importlib.import_module(mod)
            lines.append(f"opt {pkg}: OK")
        except ImportError:
            lines.append(f"opt {pkg}: MISSING")
        except Exception as e:
            lines.append(f"opt {pkg}: ERROR ({e})")

    return "\n".join(lines)


def _sanitize_settings_for_report() -> dict:
    import copy
    try:
        s = copy.deepcopy(dict(SETTINGS))
    except Exception:
        return {}
    for k in ("lan_password", "proxy_pwd", "steamgriddb_api_key", "github_token"):
        try:
            if s.get(k):
                s[k] = "***"
        except Exception:
            pass
    return s


def build_crash_report(exc_text: str = "") -> Path:
    CRASH_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = CRASH_REPORT_DIR / f"mikan_crash_{ts}.zip"

    with LOG_RING_LOCK:
        ring_snapshot = list(LOG_RING)[-500:]

    today_log = LOG_DIR / f"mikan_emu_{time.strftime('%Y-%m-%d')}.log"
    tail_text = ""
    if today_log.exists():
        try:
            with open(today_log, "r", encoding="utf-8", errors="ignore") as f:
                tail_text = "".join(f.readlines()[-2000:])
        except Exception:
            pass

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        try:
            zf.writestr("system_info.txt", _collect_system_info())
        except Exception:
            pass

        if exc_text:
            try:
                zf.writestr("exception.txt", exc_text)
            except Exception:
                pass

        try:
            zf.writestr(
                "recent_log.txt",
                "\n".join(
                    f"[{r['full_ts']}] {r['level']:8} "
                    f"{r['name']}:{r['line']}  {r['msg']}"
                    for r in ring_snapshot))
        except Exception:
            pass

        if tail_text:
            try:
                zf.writestr("today_log_tail.txt", tail_text)
            except Exception:
                pass

        try:
            zf.writestr(
                "settings_sanitized.json",
                json.dumps(_sanitize_settings_for_report(),
                           ensure_ascii=False, indent=2))
        except Exception:
            pass

        for name, path in [
            ("installed.json", INSTALLED_FILE),
            ("roms.json", ROMS_FILE),
            ("engines.json", ENGINES_JSON),
        ]:
            if path.exists():
                try:
                    zf.write(path, f"state/{name}")
                except Exception:
                    pass

        try:
            plugins_info = []
            enabled = load_plugin_enabled()
            if PLUGINS_DIR.exists():
                for d in PLUGINS_DIR.iterdir():
                    if d.is_dir():
                        mf = d / "plugin.json"
                        if mf.exists():
                            m = json.loads(mf.read_text("utf-8"))
                            plugins_info.append({
                                "id": m.get("id", d.name),
                                "version": m.get("version", "?"),
                                "enabled": enabled.get(m.get("id", d.name), True),
                            })
            zf.writestr("state/plugins.json",
                        json.dumps(plugins_info, ensure_ascii=False, indent=2))
        except Exception:
            pass

    logger.info(f"诊断包已生成: {out}")
    return out


# ============================================================
# 5.3 工具函数
# ============================================================
def get_save_path(engine_name: str) -> Optional[Path]:
    p = SAVE_PATHS.get(engine_name, "").strip()
    if p:
        path = Path(p)
        if path.exists() and path.is_dir():
            return path
    return None


def get_cheat_dir(engine_name: str) -> Optional[Path]:
    info = CHEAT_PATHS.get(engine_name, {})
    p = (info.get("dir") or "").strip()
    if p:
        path = Path(p)
        if path.exists() and path.is_dir():
            return path
    return None


def get_cheat_ext(engine_name: str) -> str:
    info = CHEAT_PATHS.get(engine_name, {})
    return (info.get("ext") or ".cht").strip()


def record_playtime(platform: str, seconds: int):
    if seconds <= 0:
        return
    today = time.strftime("%Y-%m-%d")
    daily = STATS.setdefault("daily", {})
    day = daily.setdefault(today, {})
    day[platform] = day.get(platform, 0) + seconds
    STATS["launches"] = STATS.get("launches", 0) + 1
    save_stats()


def autodetect_save_paths(engines_json: dict) -> dict:
    home = Path.home()
    docs = home / "Documents"
    appdata = Path(os.environ.get("APPDATA", ""))
    localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = {
        "snes9x": [docs / "Snes9x" / "Saves", DATA_DIR / "snes9x"],
        "duckstation": [docs / "DuckStation", home / ".local/share/DuckStation", localappdata / "DuckStation"],
        "mednafen": [home / ".mednafen" / "sav", DATA_DIR / "mednafen" / "sav"],
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
        "flycast": [docs / "Flycast", DATA_DIR / "flycast"],
        "ymir": [docs / "Ymir", appdata / "Ymir"],
        "86box": [DATA_DIR / "86box", appdata / "86Box"],
        "pcem": [DATA_DIR / "pcem", appdata / "PCem"],
        "dolphin": [docs / "Dolphin Emulator", appdata / "Dolphin Emulator"],
        "cemu": [DATA_DIR / "cemu", appdata / "Cemu"],
        "rpcs3": [DATA_DIR / "rpcs3", appdata / "rpcs3"],
        "vita3k": [appdata / "Vita3K", DATA_DIR / "Vita3K"],
        "azahar": [appdata / "azahar", DATA_DIR / "azahar"],
        "vba-m": [DATA_DIR / "vba-m", appdata / "visualboyadvance-m"],
        "noods": [DATA_DIR / "noods"],
        "geargrafx": [DATA_DIR / "geargrafx"],
        "gearcoleco": [DATA_DIR / "gearcoleco"],
    }
    result = {}
    for engine_name, paths in candidates.items():
        for p in paths:
            if p.exists() and p.is_dir():
                result[engine_name] = str(p)
                break
    return result


def autodetect_retroarch_core_dir() -> str:
    home = Path.home()
    candidates = [
        Path("C:/RetroArch-Win64/cores"),
        Path("C:/RetroArch/cores"),
        Path("D:/RetroArch-Win64/cores"),
        home / "RetroArch-Win64" / "cores",
        home / "AppData" / "Roaming" / "RetroArch" / "cores",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "RetroArch-Win64" / "cores",
    ]
    installed = load_installed()
    for e in installed:
        if e.engine == "retroarch":
            p = Path(e.engine_path).parent / "cores"
            candidates.insert(0, p)
    for c in candidates:
        if c.exists() and c.is_dir():
            return str(c)
    return ""


# ============================================================
# 5.4 ★ v1.8.0：JobObject（模拟器子进程托管）
# ============================================================
class JobObject:
    """Windows Job Object 封装。

    把模拟器进程及其子进程加入同一个 Job，
    主程序退出时（关闭 Job 句柄）自动杀掉所有成员进程，
    防止孤儿进程。

    用法：
        job = JobObject(name="mikan_emu_emulators")
        job.assign(proc.pid)     # 把模拟器加入 Job
        ...
        job.close()              # 主程序退出时调用
    """

    def __init__(self, name: str = "mikan_emu_emulators",
                 kill_on_close: bool = True):
        self._name = name
        self._handle = None
        self._kill_on_close = kill_on_close
        self._pids: set = set()
        self._lock = threading.Lock()

        if sys.platform != "win32":
            return

        try:
            kernel32 = ctypes.windll.kernel32

            self._handle = kernel32.CreateJobObjectW(None, None)
            if not self._handle:
                raise ctypes.WinError()

            # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
            # struct: BasicLimitInformation(9 DWORD/ULONG_PTR) +
            #         IoInfo(3 ULONGLONG) + ProcessMemoryLimit(ULONG_PTR) +
            #         JobMemoryLimit(ULONG_PTR) + PeakProcessMemoryUsed(ULONG_PTR) +
            #         PeakJobMemoryUsed(ULONG_PTR)
            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", ctypes.c_uint32),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0
            if kill_on_close:
                # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                info.BasicLimitInformation.LimitFlags |= 0x2000
            # JOB_OBJECT_LIMIT_BREAKAWAY_OK 不允许，防止子进程逃逸
            info.BasicLimitInformation.LimitFlags &= ~0x0800

            JobObjectExtendedLimitInformation = 9
            res = kernel32.SetInformationJobObject(
                self._handle,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not res:
                raise ctypes.WinError()

            logger.info(f"JobObject 已创建: kill_on_close={kill_on_close}")
        except Exception as e:
            logger.warning(f"JobObject 创建失败（模拟器将不受托管）: {e}")
            self._handle = None

    @property
    def available(self) -> bool:
        return self._handle is not None

    def assign(self, pid: int) -> bool:
        """把指定 PID 的进程加入 Job。"""
        if self._handle is None or sys.platform != "win32":
            return False
        if pid <= 0:
            return False
        try:
            kernel32 = ctypes.windll.kernel32
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_TERMINATE = 0x0001
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            access = PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION
            h_proc = kernel32.OpenProcess(access, False, pid)
            if not h_proc:
                raise ctypes.WinError()
            try:
                ok = kernel32.AssignProcessToJobObject(self._handle, h_proc)
                if not ok:
                    raise ctypes.WinError()
                with self._lock:
                    self._pids.add(pid)
                logger.debug(f"PID {pid} 已加入 JobObject")
                return True
            finally:
                kernel32.CloseHandle(h_proc)
        except Exception as e:
            logger.debug(f"AssignProcessToJobObject({pid}) 失败: {e}")
            return False

    def contains(self, pid: int) -> bool:
        """检查 PID 是否在本 Job 中。"""
        if self._handle is None or pid <= 0:
            return False
        with self._lock:
            if pid in self._pids:
                return True
        try:
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_proc = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h_proc:
                return False
            try:
                # IsProcessInJob(hProcess, hJob, &result)
                result = ctypes.c_int(0)
                ok = kernel32.IsProcessInJob(
                    h_proc, self._handle, ctypes.byref(result))
                if ok and result.value:
                    with self._lock:
                        self._pids.add(pid)
                    return True
                return False
            finally:
                kernel32.CloseHandle(h_proc)
        except Exception:
            return False

    def kill_all(self):
        """立即终止 Job 中所有进程。"""
        if self._handle is None or sys.platform != "win32":
            return
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.TerminateJobObject(self._handle, 1)
            logger.info("JobObject 已终止所有进程")
        except Exception as e:
            logger.warning(f"TerminateJobObject 失败: {e}")

    def close(self):
        """关闭 Job 句柄（KILL_ON_JOB_CLOSE 会触发所有进程被杀）。"""
        if self._handle is None:
            return
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle(self._handle)
            logger.info("JobObject 句柄已关闭")
        except Exception as e:
            logger.debug(f"关闭 JobObject 句柄失败: {e}")
        finally:
            self._handle = None
            with self._lock:
                self._pids.clear()


# 全局 Job 单例
_JOB_SINGLETON: Optional[JobObject] = None
_JOB_LOCK = threading.Lock()


def get_job_object() -> JobObject:
    """获取全局 Job Object 单例。"""
    global _JOB_SINGLETON
    if _JOB_SINGLETON is None:
        with _JOB_LOCK:
            if _JOB_SINGLETON is None:
                kill = bool(SETTINGS.get("job_object_kill_on_close", True))
                _JOB_SINGLETON = JobObject(kill_on_close=kill)
    return _JOB_SINGLETON


def assign_to_job(pid: int) -> bool:
    """把 PID 加入全局 Job。失败不影响启动。"""
    try:
        job = get_job_object()
        if not job.available:
            return False
        return job.assign(pid)
    except Exception as e:
        logger.debug(f"assign_to_job 失败: {e}")
        return False


def is_in_job(pid: int) -> bool:
    """检查 PID 是否由本程序启动（在 Job 中）。"""
    try:
        job = get_job_object()
        if not job.available:
            return False
        return job.contains(pid)
    except Exception:
        return False


# ============================================================
# 5.5 ★ v1.8.0：KeyMapper（虚拟按键映射）
# ============================================================
# 键名归一化：把 Qt 的 key 名称和 keyboard 库的 key 名称统一
_KEY_ALIASES = {
    "escape": "esc",
    "return": "enter",
    "control": "ctrl",
    "meta": "win",
    "super": "win",
    "cmd": "win",
    "altgr": "right alt",
    "capslock": "caps lock",
    "pageup": "page up",
    "pagedown": "page down",
    "printscreen": "print screen",
    "scrolllock": "scroll lock",
    "numlock": "num lock",
}


def normalize_key_name(name: str) -> str:
    """把键名归一化成 keyboard 库能识别的格式。"""
    if not name:
        return ""
    n = name.strip().lower()
    # 特殊键
    if n in _KEY_ALIASES:
        return _KEY_ALIASES[n]
    # 单字符
    if len(n) == 1:
        return n
    # 空格
    if n in ("space", " "):
        return "space"
    # F1-F24
    m = re.match(r"^f(\d{1,2})$", n)
    if m:
        return f"f{m.group(1)}"
    # 方向键
    if n in ("up", "down", "left", "right"):
        return n
    if n in ("arrowup", "arrowdown", "arrowleft", "arrowright"):
        return n.replace("arrow", "")
    # 其他保持原样
    return n


def qt_key_to_name(qt_key: int) -> str:
    """把 Qt.Key 枚举值转成 keyboard 库的键名。"""
    try:
        from PySide6.QtCore import Qt as _Qt
        mapping = {
            _Qt.Key_Escape: "esc",
            _Qt.Key_Tab: "tab",
            _Qt.Key_Backtab: "tab",
            _Qt.Key_Backspace: "backspace",
            _Qt.Key_Return: "enter",
            _Qt.Key_Enter: "enter",
            _Qt.Key_Insert: "insert",
            _Qt.Key_Delete: "delete",
            _Qt.Key_Pause: "pause",
            _Qt.Key_Print: "print screen",
            _Qt.Key_Home: "home",
            _Qt.Key_End: "end",
            _Qt.Key_Left: "left",
            _Qt.Key_Up: "up",
            _Qt.Key_Right: "right",
            _Qt.Key_Down: "down",
            _Qt.Key_PageUp: "page up",
            _Qt.Key_PageDown: "page down",
            _Qt.Key_Shift: "shift",
            _Qt.Key_Control: "ctrl",
            _Qt.Key_Alt: "alt",
            _Qt.Key_CapsLock: "caps lock",
            _Qt.Key_NumLock: "num lock",
            _Qt.Key_ScrollLock: "scroll lock",
            _Qt.Key_Meta: "win",
            _Qt.Key_Space: "space",
        }
        if qt_key in mapping:
            return mapping[qt_key]
        if _Qt.Key_F1 <= qt_key <= _Qt.Key_F24:
            return f"f{qt_key - _Qt.Key_F1 + 1}"
        if _Qt.Key_A <= qt_key <= _Qt.Key_Z:
            return chr(ord("a") + (qt_key - _Qt.Key_A))
        if _Qt.Key_0 <= qt_key <= _Qt.Key_9:
            return chr(ord("0") + (qt_key - _Qt.Key_0))
        # 其他按键（符号等）
        try:
            s = _Qt.Key(qt_key).name
            s = s.replace("Key_", "").lower()
            return s
        except Exception:
            return ""
    except Exception:
        return ""


def _get_foreground_pid() -> int:
    """获取当前前台窗口所属进程 PID。"""
    if sys.platform != "win32":
        return 0
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


class KeyMapEntry:
    """单条按键映射。"""

    __slots__ = ("physical", "virtual", "enabled", "note")

    def __init__(self, physical: str = "", virtual: str = "",
                 enabled: bool = True, note: str = ""):
        self.physical = normalize_key_name(physical)
        self.virtual = virtual.strip() if virtual else ""
        self.enabled = bool(enabled)
        self.note = note or ""

    def to_dict(self) -> dict:
        return {
            "physical": self.physical,
            "virtual": self.virtual,
            "enabled": self.enabled,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KeyMapEntry":
        return cls(
            physical=d.get("physical", ""),
            virtual=d.get("virtual", ""),
            enabled=d.get("enabled", True),
            note=d.get("note", ""),
        )


class KeyMapper:
    """低级键盘钩子 + 按键重映射。

    ★ 只对由本程序启动的模拟器进程生效。
    ★ 支持全局映射和按游戏覆盖。
    ★ 需要 keyboard 库（可选依赖）。

    用法：
        km = KeyMapper()
        km.set_global_map([KeyMapEntry("a", "b")])
        km.set_game_map(game_path, [KeyMapEntry("a", "b")])
        km.start()
        # 启动模拟器后：
        km.attach_pid(proc.pid)
        # 切游戏/关闭：
        km.detach_pid(pid)
        # 退出：
        km.stop()
    """

    def __init__(self):
        self._global_map: dict = {}   # physical -> KeyMapEntry
        self._game_map: dict = {}     # game_path -> {physical: KeyMapEntry}
        self._emulator_pids: set = set()
        self._lock = threading.RLock()
        self._running = False
        self._hooked = False
        self._suppress_keys: set = set()  # 防止重入：正在发送的虚拟键
        self._osd_callback: Optional[Callable[[str], None]] = None
        self._last_remap_ts: dict = {}

    # ---------- 配置 ----------
    def set_global_map(self, entries: list):
        with self._lock:
            self._global_map = {
                e.physical: e for e in entries
                if e.physical and e.virtual and e.enabled
            }

    def get_global_map(self) -> list:
        with self._lock:
            return list(self._global_map.values())

    def set_game_map(self, game_path: str, entries: list):
        with self._lock:
            if not entries:
                self._game_map.pop(game_path, None)
            else:
                self._game_map[game_path] = {
                    e.physical: e for e in entries
                    if e.physical and e.virtual and e.enabled
                }

    def get_game_map(self, game_path: str) -> list:
        with self._lock:
            return list(self._game_map.get(game_path, {}).values())

    def clear_game_map(self, game_path: str):
        with self._lock:
            self._game_map.pop(game_path, None)

    # ---------- 加载/保存 ----------
    def load_from_files(self):
        """从 keymap.json 和 keymap_games.json 加载。"""
        with self._lock:
            self._global_map = {}
            self._game_map = {}

            if KEYMAP_FILE.exists():
                try:
                    data = json.loads(KEYMAP_FILE.read_text("utf-8"))
                    for e in data.get("global", []):
                        entry = KeyMapEntry.from_dict(e)
                        if entry.physical and entry.virtual and entry.enabled:
                            self._global_map[entry.physical] = entry
                except Exception as e:
                    logger.exception(f"加载 keymap.json 失败: {e}")

            if KEYMAP_GAMES_FILE.exists():
                try:
                    data = json.loads(KEYMAP_GAMES_FILE.read_text("utf-8"))
                    for game_path, entries in data.items():
                        m = {}
                        for e in entries:
                            entry = KeyMapEntry.from_dict(e)
                            if entry.physical and entry.virtual and entry.enabled:
                                m[entry.physical] = entry
                        if m:
                            self._game_map[game_path] = m
                except Exception as e:
                    logger.exception(f"加载 keymap_games.json 失败: {e}")

    def save_to_files(self):
        with self._lock:
            try:
                KEYMAP_FILE.write_text(
                    json.dumps(
                        {"global": [e.to_dict() for e in self._global_map.values()]},
                        ensure_ascii=False, indent=2),
                    encoding="utf-8")
            except Exception as e:
                logger.exception(f"保存 keymap.json 失败: {e}")

            try:
                KEYMAP_GAMES_FILE.write_text(
                    json.dumps(
                        {k: [e.to_dict() for e in v.values()]
                         for k, v in self._game_map.items()},
                        ensure_ascii=False, indent=2),
                    encoding="utf-8")
            except Exception as e:
                logger.exception(f"保存 keymap_games.json 失败: {e}")

    # ---------- PID 管理 ----------
    def attach_pid(self, pid: int):
        if pid <= 0:
            return
        with self._lock:
            self._emulator_pids.add(pid)

    def detach_pid(self, pid: int):
        with self._lock:
            self._emulator_pids.discard(pid)

    def _is_foreground_in_emulators(self) -> bool:
        """当前前台窗口是否属于本程序的模拟器。"""
        fg_pid = _get_foreground_pid()
        if fg_pid <= 0:
            return False
        with self._lock:
            if fg_pid in self._emulator_pids:
                return True
        # 额外检查：是否在 Job Object 中（覆盖子进程）
        return is_in_job(fg_pid)

    def _lookup(self, physical: str) -> Optional[KeyMapEntry]:
        with self._lock:
            entry = self._global_map.get(physical)
            if entry:
                return entry
            # 游戏覆盖（优先级更高）
            for m in self._game_map.values():
                if physical in m:
                    return m[physical]
        return None

    # ---------- 钩子 ----------
    def set_osd_callback(self, cb: Callable[[str], None]):
        self._osd_callback = cb

    def _show_osd(self, physical: str, virtual: str):
        if not SETTINGS.get("keymap_show_osd", True):
            return
        cb = self._osd_callback
        if cb is None:
            return
        try:
            cb(tr("osd_keymap", physical=physical, virtual=virtual))
        except Exception:
            pass

    def start(self) -> bool:
        """启动键盘钩子。返回是否成功。"""
        if not HAS_KEYBOARD:
            logger.warning("keyboard 库未安装，KeyMapper 不启动")
            return False
        if not SETTINGS.get("keymap_enabled", False):
            logger.info("keymap_enabled=False，KeyMapper 不启动")
            return False
        if self._running:
            return True

        self.load_from_files()
        if not self._global_map and not self._game_map:
            logger.info("按键映射表为空，KeyMapper 不启动")
            return False

        try:
            # 只挂按下事件；抬起不处理
            kb.on_press(self._on_key_press, suppress=False)
            self._hooked = True
            self._running = True
            logger.info(
                f"KeyMapper 已启动 "
                f"（全局 {len(self._global_map)} 条 / "
                f"游戏 {len(self._game_map)} 个游戏）")
            return True
        except Exception as e:
            logger.exception(f"KeyMapper 启动失败: {e}")
            self._running = False
            return False

    def stop(self):
        if not self._hooked:
            return
        try:
            kb.unhook_all()
        except Exception:
            pass
        self._hooked = False
        self._running = False
        logger.info("KeyMapper 已停止")

    def _on_key_press(self, event):
        """键盘按下回调。"""
        if not self._running:
            return
        try:
            physical = normalize_key_name(event.name)
            if not physical:
                return

            # 防止重入：正在发送的虚拟键不再拦截
            if physical in self._suppress_keys:
                return

            entry = self._lookup(physical)
            if entry is None:
                return

            # 仅模拟器窗口在前台时生效
            if SETTINGS.get("keymap_only_foreground", True):
                if not self._is_foreground_in_emulators():
                    return

            # 防抖：同一物理键 50ms 内只重映射一次
            now = time.time()
            last = self._last_remap_ts.get(physical, 0)
            if now - last < 0.05:
                return
            self._last_remap_ts[physical] = now

            virtual = normalize_key_name(entry.virtual)
            if not virtual:
                return

            # 发送虚拟键
            self._send_virtual(virtual)
            self._show_osd(physical, entry.virtual)

            # 拦截物理键：用 keyboard 的 suppress 机制
            try:
                kb.press_and_release(virtual)
            except Exception as e:
                logger.debug(f"发送虚拟键 {virtual} 失败: {e}")

            try:
                event.suppress = True
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"KeyMapper 处理失败: {e}")

    def _send_virtual(self, virtual: str):
        """发送虚拟键。用 keyboard 库模拟按键。"""
        if not HAS_KEYBOARD:
            return
        try:
            # 注意：不要用 suppress=True，否则会被自己的钩子再次拦截
            with self._lock:
                self._suppress_keys.add(virtual)
            try:
                kb.send(virtual)
            finally:
                # 延迟移除，避免 release 事件又被拦
                def _cleanup():
                    time.sleep(0.1)
                    with self._lock:
                        self._suppress_keys.discard(virtual)
                threading.Thread(target=_cleanup, daemon=True).start()
        except Exception as e:
            logger.debug(f"_send_virtual({virtual}) 失败: {e}")

    # ---------- 测试 ----------
    def test_map(self, physical: str) -> Optional[str]:
        """测试一条映射，返回虚拟键名。"""
        entry = self._lookup(normalize_key_name(physical))
        return entry.virtual if entry else None


# 全局 KeyMapper 单例
_KEYMAPPER_SINGLETON: Optional[KeyMapper] = None
_KEYMAPPER_LOCK = threading.Lock()


def get_keymapper() -> KeyMapper:
    global _KEYMAPPER_SINGLETON
    if _KEYMAPPER_SINGLETON is None:
        with _KEYMAPPER_LOCK:
            if _KEYMAPPER_SINGLETON is None:
                _KEYMAPPER_SINGLETON = KeyMapper()
    return _KEYMAPPER_SINGLETON


def start_keymapper() -> bool:
    try:
        return get_keymapper().start()
    except Exception as e:
        logger.exception(f"start_keymapper 失败: {e}")
        return False


def stop_keymapper():
    try:
        get_keymapper().stop()
    except Exception:
        pass


# ============================================================
# 5.6 ★ v1.8.0：MikanAPI 核心
# ============================================================
class Events:
    """事件钩子名称常量。"""
    APP_START = "app.start"
    APP_QUIT = "app.quit"

    GAMES_CHANGED = "games.changed"
    GAME_ADDED = "games.added"
    GAME_REMOVED = "games.removed"
    GAME_LAUNCH_BEFORE = "game.launch.before"
    GAME_LAUNCH_AFTER = "game.launch.after"
    GAME_CLOSED = "game.closed"

    ENGINE_INSTALLED = "engine.installed"
    ENGINE_REMOVED = "engine.removed"

    DOWNLOAD_START = "download.start"
    DOWNLOAD_DONE = "download.done"
    DOWNLOAD_FAIL = "download.fail"

    COVERS_CHANGED = "covers.changed"
    SETTINGS_CHANGED = "settings.changed"
    FOLDERS_CHANGED = "folders.changed"
    KEYMAP_CHANGED = "keymap.changed"

    LAN_PEER_JOINED = "lan.peer.joined"
    LAN_PEER_LEFT = "lan.peer.left"
    LAN_MESSAGE = "lan.message"
    LAN_FILE = "lan.file"

    MIRRORS_CHANGED = "mirrors.changed"


class Job(QObject):
    """长任务句柄。包装 QThread，统一信号名。

    信号：
        progress(int, int)   当前进度 / 总数
        message(str)         状态文本
        finished(object)     结果
        failed(str)          错误
    """
    progress = Signal(int, int)
    message = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, worker: QThread, parent=None):
        super().__init__(parent)
        self._worker = worker
        self._result = None
        self._error = ""
        self._cancelled = False
        self._wire()

    def _wire(self):
        w = self._worker
        if w is None:
            return

        if hasattr(w, "progress"):
            try:
                w.progress.connect(self._on_progress)
            except Exception:
                pass

        if hasattr(w, "status"):
            try:
                w.status.connect(self.message)
            except Exception:
                pass

        if hasattr(w, "done"):
            try:
                w.done.connect(self._on_done)
            except Exception:
                pass
        elif hasattr(w, "finished"):
            try:
                w.finished.connect(self._on_done)
            except Exception:
                pass

        if hasattr(w, "fail"):
            try:
                w.fail.connect(self._on_fail)
            except Exception:
                pass

        try:
            w.finished.connect(self._on_thread_finished)
        except Exception:
            pass

    def _on_progress(self, *args):
        if self._cancelled:
            return
        if len(args) == 2:
            try:
                self.progress.emit(int(args[0]), int(args[1]))
            except Exception:
                pass
        elif len(args) == 1:
            try:
                self.progress.emit(0, int(args[0]))
            except Exception:
                pass

    def _on_done(self, result):
        self._result = result

    def _on_fail(self, err):
        self._error = str(err) if err else "unknown error"

    def _on_thread_finished(self):
        if self._cancelled:
            self.failed.emit("cancelled")
            return
        if self._error:
            self.failed.emit(self._error)
        else:
            self.finished.emit(self._result)

    def cancel(self):
        self._cancelled = True
        w = self._worker
        if w is None:
            return
        if hasattr(w, "cancel"):
            try:
                w.cancel()
            except Exception:
                pass
        try:
            w.requestInterruption()
        except Exception:
            pass

    def wait(self, ms: int = -1) -> bool:
        if self._worker is None:
            return True
        try:
            return self._worker.wait(ms)
        except Exception:
            return False

    def is_running(self) -> bool:
        if self._worker is None:
            return False
        try:
            return self._worker.isRunning()
        except Exception:
            return False

    def result(self):
        return self._result

    def error(self) -> str:
        return self._error


class MikanAPI(QObject):
    """mikan_emu 统一 API。

    用法：
        import mikan_emu
        api = mikan_emu.get_api()
        games = api.games.list()
        job = api.download.start("sfc", "snes9x")
    """

    def __init__(self, settings: Optional[dict] = None,
                 folders: Optional[dict] = None, parent=None):
        super().__init__(parent)
        if settings is not None:
            global SETTINGS
            SETTINGS = settings
        if folders is not None:
            global FOLDERS_CONFIG
            FOLDERS_CONFIG = folders

        self._hooks: dict = {}
        self._sub_apis: dict = {}

    def _register(self, name: str, api_obj):
        self._sub_apis[name] = api_obj

    def __getattr__(self, item):
        # 子 API 延迟绑定（避免循环引用）
        if item in self._sub_apis:
            return self._sub_apis[item]
        raise AttributeError(item)

    # 事件
    def on(self, event: str, callback) -> None:
        self._hooks.setdefault(event, []).append(callback)

    def off(self, event: str, callback) -> None:
        lst = self._hooks.get(event, [])
        if callback in lst:
            lst.remove(callback)

    def emit(self, event: str, **kwargs) -> None:
        self._emit(event, **kwargs)

    def _emit(self, event: str, **kwargs) -> None:
        for cb in list(self._hooks.get(event, [])):
            try:
                cb(**kwargs)
            except Exception as e:
                logger.exception(f"[api] 钩子 {event} 失败: {e}")

    # 子 API 工厂（由第 8 段填充具体实现）
    def init_sub_apis(self):
        # 这些类在第 8 段定义，这里只是延迟导入
        from mikan_emu import (  # type: ignore
            _GamesAPI, _EnginesAPI, _DownloadAPI, _ScrapeAPI,
            _PatchAPI, _BiosAPI, _StatsAPI, _SettingsAPI,
            _MirrorsAPI, _PluginsAPI, _KeymapAPI,
        )
        self._register("games", _GamesAPI(self))
        self._register("engines", _EnginesAPI(self))
        self._register("download", _DownloadAPI(self))
        self._register("scrape", _ScrapeAPI(self))
        self._register("patch", _PatchAPI(self))
        self._register("bios", _BiosAPI(self))
        self._register("stats", _StatsAPI(self))
        self._register("settings", _SettingsAPI(self))
        self._register("mirrors", _MirrorsAPI(self))
        self._register("plugins", _PluginsAPI(self))
        self._register("keymap", _KeymapAPI(self))


# 全局单例
_API_SINGLETON: Optional[MikanAPI] = None
_API_LOCK = threading.Lock()


def get_api() -> MikanAPI:
    """获取全局 API 单例。"""
    global _API_SINGLETON
    if _API_SINGLETON is None:
        with _API_LOCK:
            if _API_SINGLETON is None:
                _API_SINGLETON = MikanAPI()
    return _API_SINGLETON


# ============================================================
# 5.7 ★ v1.8.0：补丁工具（IPS/UPS）
# ============================================================
class PatchError(Exception):
    pass


def _ensure_buf_size(buf: bytearray, need: int):
    if need > len(buf):
        buf.extend(b"\x00" * (need - len(buf)))


def patch_ips(rom_data: bytes, patch_data: bytes) -> bytes:
    """IPS 补丁。支持 EEOF 扩展，越界自动扩容。"""
    if len(patch_data) < 8 or patch_data[:5] != b"PATCH":
        raise PatchError(tr("patch_ips_invalid"))

    out = bytearray(rom_data)
    pos = 5
    max_offset_3 = 0xFFFFFF

    while pos < len(patch_data):
        if patch_data[pos:pos + 3] == b"EOF":
            break
        if patch_data[pos:pos + 4] == b"EEOF":
            pos += 4
            if pos + 4 <= len(patch_data):
                offset = int.from_bytes(patch_data[pos:pos + 4], "big")
                pos += 4
                if pos + 2 > len(patch_data):
                    raise PatchError(tr("patch_ips_truncated"))
                size = int.from_bytes(patch_data[pos:pos + 2], "big")
                pos += 2
                if size == 0:
                    if pos + 4 > len(patch_data):
                        raise PatchError(tr("patch_ips_truncated"))
                    rle_size = int.from_bytes(patch_data[pos:pos + 3], "big")
                    rle_byte = patch_data[pos + 3]
                    pos += 4
                    _ensure_buf_size(out, offset + rle_size)
                    out[offset:offset + rle_size] = bytes([rle_byte]) * rle_size
                else:
                    if pos + size > len(patch_data):
                        raise PatchError(tr("patch_ips_truncated"))
                    data = patch_data[pos:pos + size]
                    pos += size
                    _ensure_buf_size(out, offset + size)
                    out[offset:offset + size] = data
            continue

        if pos + 5 > len(patch_data):
            raise PatchError(tr("patch_ips_truncated"))
        offset = int.from_bytes(patch_data[pos:pos + 3], "big")
        size = int.from_bytes(patch_data[pos + 3:pos + 5], "big")
        pos += 5

        if offset > max_offset_3:
            logger.warning(
                f"IPS 偏移 {offset:#x} 超出 3 字节范围，已跳过")
            continue

        if size == 0:
            if pos + 4 > len(patch_data):
                raise PatchError(tr("patch_ips_truncated"))
            rle_size = int.from_bytes(patch_data[pos:pos + 3], "big")
            rle_byte = patch_data[pos + 3]
            pos += 4
            _ensure_buf_size(out, offset + rle_size)
            out[offset:offset + rle_size] = bytes([rle_byte]) * rle_size
        else:
            if pos + size > len(patch_data):
                raise PatchError(tr("patch_ips_truncated"))
            data = patch_data[pos:pos + size]
            pos += size
            _ensure_buf_size(out, offset + size)
            out[offset:offset + size] = data

    return bytes(out)


def patch_ups(rom_data: bytes, patch_data: bytes) -> bytes:
    """UPS 补丁。varint 截断检测。"""
    if len(patch_data) < 4 or patch_data[:4] != b"UPS1":
        raise PatchError(tr("patch_ups_invalid"))

    def read_varint(buf, p):
        shift = 0
        val = 0
        while True:
            if p >= len(buf):
                raise PatchError(tr("patch_ups_truncated"))
            b = buf[p]
            p += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
            if shift > 35:
                raise PatchError(tr("patch_ups_truncated"))
        return val, p

    pos = 4
    src_size, pos = read_varint(patch_data, pos)
    dst_size, pos = read_varint(patch_data, pos)

    if len(rom_data) != src_size:
        logger.warning(f"UPS 声明的源大小 {src_size} != 实际 {len(rom_data)}")

    out = bytearray(dst_size)
    out[:min(len(rom_data), dst_size)] = rom_data[:min(len(rom_data), dst_size)]

    rel = 0
    while True:
        skip, pos = read_varint(patch_data, pos)
        rel += skip
        if rel == 0xFFFFFFFF:
            break

        xor_key = 0
        inner_ok = False
        while pos < len(patch_data):
            b = patch_data[pos]
            pos += 1
            if b == 0x00:
                xor_key ^= 0xFF
                inner_ok = True
                break
            data_byte = b ^ xor_key
            xor_key ^= data_byte
            if rel < len(out):
                out[rel] = out[rel] ^ data_byte
            rel += 1

        if not inner_ok:
            raise PatchError(tr("patch_ups_truncated"))

    return bytes(out)


def apply_patch_file(rom_path: Path, patch_path: Path,
                     out_path: Optional[Path] = None,
                     backup: bool = True) -> tuple:
    if not rom_path.exists():
        raise PatchError(tr("patch_rom_missing", path=str(rom_path)))
    if not patch_path.exists():
        raise PatchError(tr("patch_file_missing", path=str(patch_path)))

    rom_data = rom_path.read_bytes()
    patch_data = patch_path.read_bytes()
    ext = patch_path.suffix.lower()

    if ext == ".ips":
        new_data = patch_ips(rom_data, patch_data)
    elif ext == ".ups":
        new_data = patch_ups(rom_data, patch_data)
    else:
        raise PatchError(tr("patch_bad_format", ext=ext))

    if out_path is None:
        out_path = rom_path.with_name(
            f"{rom_path.stem} (patched){rom_path.suffix}")

    if backup:
        bak = rom_path.with_suffix(rom_path.suffix + ".bak")
        if not bak.exists():
            try:
                shutil.copy2(rom_path, bak)
                logger.info(f"ROM 备份: {bak}")
            except Exception as e:
                logger.warning(f"备份失败: {e}")

    out_path.write_bytes(new_data)
    logger.info(
        f"补丁应用成功: {rom_path.name} + {patch_path.name} -> {out_path.name}")
    return out_path, len(rom_data), len(new_data)


# ============================================================
# 5.8 其他工具函数（路径/版本/存档等）
# ============================================================
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


def md5_of_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def crc32_of_file(path: Path, chunk: int = 1 << 20) -> str:
    crc = 0
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                crc = zlib.crc32(b, crc)
    except Exception:
        return ""
    return f"{crc & 0xFFFFFFFF:08x}"


def _dir_size(p: Path) -> int:
    total = 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        pass
    return total


# ============================================================
# 6. engines.json 加载（深度合并 + 版本适配 + 共享定义）
# ============================================================
def _deep_merge_dict(base: dict, incoming: dict) -> dict:
    if not isinstance(base, dict) or not isinstance(incoming, dict):
        return incoming if incoming is not None else base
    result = dict(base)
    for k, v in incoming.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge_dict(result[k], v)
        else:
            result[k] = v
    return result


def _merge_engines_with_defaults(user_data: dict, default_data: dict) -> tuple:
    changed = False
    result = dict(user_data)

    for key in default_data:
        if key == "_shared":
            continue
        if key not in result:
            result[key] = json.loads(json.dumps(default_data[key]))
            changed = True
            continue
        pcfg_user = result[key]
        pcfg_default = default_data[key]
        if not isinstance(pcfg_user, dict):
            result[key] = json.loads(json.dumps(pcfg_default))
            changed = True
            continue
        for k in ("platform_name", "rom_extensions"):
            if k not in pcfg_user and k in pcfg_default:
                pcfg_user[k] = json.loads(json.dumps(pcfg_default[k]))
                changed = True
        if "engines" in pcfg_default:
            pcfg_user.setdefault("engines", {})
            for en, ecfg_default in pcfg_default["engines"].items():
                if en not in pcfg_user["engines"]:
                    pcfg_user["engines"][en] = json.loads(json.dumps(ecfg_default))
                    changed = True
                else:
                    ecfg_user = pcfg_user["engines"][en]
                    if not isinstance(ecfg_user, dict):
                        pcfg_user["engines"][en] = json.loads(json.dumps(ecfg_default))
                        changed = True
                        continue
                    for fk, fv in ecfg_default.items():
                        if fk not in ecfg_user:
                            ecfg_user[fk] = json.loads(json.dumps(fv))
                            changed = True
    return result, changed


def _expand_shared_engines(data: dict) -> tuple:
    shared = data.get("_shared", {})
    if not isinstance(shared, dict) or not shared:
        return data, False

    changed = False
    result = dict(data)

    for pid, pcfg in result.items():
        if pid == "_shared":
            continue
        if not isinstance(pcfg, dict):
            continue
        engines = pcfg.get("engines", {})
        if not isinstance(engines, dict):
            continue
        for en, ecfg in engines.items():
            if not isinstance(ecfg, dict):
                continue
            ref = ecfg.get("use_shared", "")
            if not ref:
                continue
            base = shared.get(ref)
            if not isinstance(base, dict):
                logger.warning(f"引擎 {pid}/{en} 引用未知共享: {ref}")
                continue
            merged = dict(base)
            for k, v in ecfg.items():
                if k == "use_shared":
                    continue
                if (k in merged
                        and isinstance(merged[k], dict)
                        and isinstance(v, dict)):
                    tmp = dict(merged[k])
                    tmp.update(v)
                    merged[k] = tmp
                else:
                    merged[k] = v
            engines[en] = merged
            changed = True

    return result, changed


def load_engines_json() -> dict:
    if not ENGINES_JSON.exists():
        try:
            data = json.loads(DEFAULT_ENGINES_JSON_STR)
            with open(ENGINES_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"生成默认 engines.json: {ENGINES_JSON}")
            return data
        except Exception as e:
            logger.exception(f"写出默认 engines.json 失败: {e}")
            return {}

    try:
        with open(ENGINES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.exception(f"读取 engines.json 失败: {e}")
        return {}

    try:
        defaults = json.loads(DEFAULT_ENGINES_JSON_STR)
        merged, changed = _merge_engines_with_defaults(data, defaults)
    except Exception as e:
        logger.debug(f"合并 engines.json 失败，使用原始数据: {e}")
        merged = data
        changed = False

    try:
        merged2, changed2 = _expand_shared_engines(merged)
        if changed2:
            merged = merged2
            changed = True
    except Exception as e:
        logger.debug(f"展开 _shared 失败: {e}")

    if changed:
        try:
            with open(ENGINES_JSON, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2, ensure_ascii=False)
            logger.info("engines.json 已自动补齐/展开")
        except Exception as e:
            logger.warning(f"回写 engines.json 失败: {e}")

    return merged


def save_engines_json(data: dict):
    try:
        with open(ENGINES_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 engines.json 失败: {e}")


def get_all_platform_rom_extensions(engines_json: dict) -> dict:
    result = {}
    for platform, pcfg in engines_json.items():
        if platform.startswith("_"):
            continue
        for ext in pcfg.get("rom_extensions", []):
            result.setdefault(ext.lower(), []).append(platform)
    return result


def _norm_version(v: str) -> Optional[Version]:
    if not v:
        return None
    v = v.strip().lstrip("vV")
    if not v or v.lower() in ("manual", "unknown", "latest"):
        return None
    try:
        return Version(v)
    except InvalidVersion:
        return None


def version_newer(a: str, b: str) -> bool:
    va, vb = _norm_version(a), _norm_version(b)
    if va is None or vb is None:
        return False
    try:
        head_a = va.release[0] if va.release else 0
        head_b = vb.release[0] if vb.release else 0
    except Exception:
        return va > vb
    lo, hi = (head_a, head_b) if head_a <= head_b else (head_b, head_a)
    if lo > 0 and hi >= lo * 1000:
        return False
    return va > vb


def match_version_range(ver: str, range_expr: str) -> bool:
    if range_expr in ("", "*", None):
        return True
    v = _norm_version(ver)
    if v is None:
        return False
    try:
        spec = SpecifierSet(range_expr)
    except InvalidSpecifier:
        logger.debug(f"无效版本约束: {range_expr}")
        return False
    try:
        return spec.contains(str(v), prereleases=True)
    except Exception:
        return False


VERSION_OVERRIDABLE_FIELDS = {
    "launch_template",
    "settings_args",
    "perf_profiles",
    "bios_files",
    "bios_dir",
    "bios_required",
}


def resolve_engine_cfg(platform: str, engine_name: str,
                       version: str = "",
                       engines_json: Optional[dict] = None) -> dict:
    if engines_json is None:
        engines_json = load_engines_json()

    pcfg = engines_json.get(platform, {})
    cfg = pcfg.get("engines", {}).get(engine_name)
    if not cfg:
        return {}

    result = dict(cfg)

    overrides = cfg.get("version_overrides") or []
    if not isinstance(overrides, list):
        overrides = []

    for ov in overrides:
        if not isinstance(ov, dict):
            continue
        rng = ov.get("range", "*")
        if match_version_range(version, rng):
            for k, v in ov.items():
                if k == "range":
                    continue
                if k in VERSION_OVERRIDABLE_FIELDS:
                    result[k] = v
            result["_matched_override"] = rng
            break

    return result


def resolve_engine_field(engine, field: str, default: Any = "") -> Any:
    if engine is None:
        return default
    version = getattr(engine, "version", "") or ""
    if version.lower() in ("manual", "unknown", "latest"):
        version = ""

    pcfg = resolve_engine_cfg(engine.platform, engine.engine, version)
    if field in pcfg:
        return pcfg[field]

    return getattr(engine, field, default)


def get_perf_profiles(engine) -> dict:
    if engine is None:
        return {}
    v = resolve_engine_field(engine, "perf_profiles", {})
    return v if isinstance(v, dict) else {}


def get_settings_args(engine) -> str:
    v = resolve_engine_field(engine, "settings_args", "")
    return v if isinstance(v, str) else ""


def get_param_schema(engine) -> list:
    """★ v1.8.0：获取引擎的 param_schema。"""
    if engine is None:
        return []
    v = resolve_engine_field(engine, "param_schema", [])
    return v if isinstance(v, list) else []


# ============================================================
# 8. 模拟器匹配 / 安装（基础函数，Worker 在第 4 段）
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


def scan_files(root: Path) -> list:
    return [p for p in root.rglob("*") if p.is_file()]


def match_engines(files: list, engines_json: dict) -> list:
    results = []
    seen = set()
    for platform, pcfg in engines_json.items():
        if platform.startswith("_"):
            continue
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
                              source_label: str = "import") -> "EmulatorConfig":
    # EmulatorConfig 在第 3 段定义，这里用字符串注解延迟
    platform = match["platform"]
    engine = match["engine"]
    cfg = match["cfg"]
    exe_path: Path = match["exe"]
    target_dir = ENGINE_DOWNLOAD_DIR / platform / engine
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        try:
            exe_path.relative_to(source_root)
        except ValueError:
            source_root = exe_path.parent
        try:
            is_root = (source_root == Path(source_root.anchor)
                       or source_root == Path.home())
        except Exception:
            is_root = False
        if is_root:
            logger.warning(f"源目录是盘根/家目录，仅复制 exe 所在目录: {source_root}")
            source_root = exe_path.parent
        else:
            try:
                file_count = sum(1 for p in source_root.rglob("*") if p.is_file())
            except Exception:
                file_count = 0
            if file_count > 5000:
                logger.warning(f"源目录文件数 {file_count} 过多，仅复制 exe 所在目录")
                source_root = exe_path.parent
    except Exception:
        pass

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

    # 延迟导入 EmulatorConfig
    from mikan_emu import EmulatorConfig  # type: ignore
    return EmulatorConfig(
        platform=platform, engine=engine,
        platform_name=cfg.get("platform_name", platform),
        engine_path=str(target_exe), engine_dir=str(target_dir),
        version=cfg.get("version", ""), official=cfg.get("official", False),
        source=source_label,
        bios_required=cfg.get("bios_required", False),
        bios_files=cfg.get("bios_files", []),
        bios_dir=cfg.get("bios_dir", ""),
        launch_template=cfg.get("launch_template", "{exe} \"{rom}\""),
        installed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        url=cfg.get("url", ""),
        url_type=cfg.get("url_type", "direct"),
        github_repo=cfg.get("github_repo", "") or (parse_github_repo(cfg.get("url", "")) or ""),
        libretro_core=cfg.get("libretro_core", ""),
        archive=cfg.get("archive", "zip"),
    )


def install_manual_engine(exe_path: Path, platform: str, engine_name: str,
                          launch_tpl: str = "{exe} \"{rom}\"",
                          platform_display: str = "") -> "EmulatorConfig":
    target_dir = ENGINE_DOWNLOAD_DIR / platform / engine_name
    target_dir.mkdir(parents=True, exist_ok=True)
    src_root = exe_path.parent
    copied = 0
    for item in src_root.rglob("*"):
        if not item.is_file():
            continue
        try:
            rel = item.relative_to(src_root)
            dst = target_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)
            copied += 1
        except Exception as e:
            logger.exception(f"复制 {item} 失败: {e}")
    target_exe = target_dir / exe_path.name
    logger.info(f"手动安装引擎: {engine_name} -> {target_exe} ({copied} files)")
    from mikan_emu import EmulatorConfig  # type: ignore
    return EmulatorConfig(
        platform=platform, engine=engine_name,
        platform_name=platform_display or platform,
        engine_path=str(target_exe), engine_dir=str(target_dir),
        version="manual", official=False, source="manual",
        launch_template=launch_tpl,
        installed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        url_type="manual", archive="none",
    )


def parse_github_repo(url: str) -> Optional[str]:
    m = re.search(r"github\.com/([^/]+)/([^/]+?)(?:/|$|\.git)", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def detect_engine_version(engine, force: bool = False) -> str:
    """探测引擎版本。优先 version/v 前缀，过滤日期。"""
    if not engine:
        return ""
    recorded = (engine.version or "").strip()
    if not force and recorded and recorded.lower() not in (
            "manual", "unknown", "latest", ""):
        return recorded

    exe = Path(engine.engine_path)
    if not exe.exists():
        return ""

    flags = ("--version", "-version", "-v", "version")
    cflags = (sp.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    detected = ""

    for flag in flags:
        try:
            r = sp.run([str(exe), flag], capture_output=True,
                       timeout=5, cwd=str(exe.parent),
                       creationflags=cflags)
            text = (r.stdout or b"") + (r.stderr or b"")
            s = text.decode("utf-8", "ignore")

            patterns = [
                r"(?:version|ver|v)\s*[:=]?\s*(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)",
                r"\b(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)\b",
            ]
            for pat in patterns:
                for m in re.finditer(pat, s, re.IGNORECASE):
                    candidate = m.group(1)
                    parts = candidate.split(".")
                    if len(parts) >= 2:
                        try:
                            y = int(parts[0])
                            mo = int(parts[1])
                            if y >= 2000 and 1 <= mo <= 12:
                                continue
                        except ValueError:
                            pass
                    detected = candidate
                    break
                if detected:
                    break
            if detected:
                break
        except Exception:
            continue

    if detected:
        engine.version = detected
        engines = load_installed()
        for e in engines:
            if e.platform == engine.platform and e.engine == engine.engine:
                e.version = detected
                break
        save_installed(engines)
        logger.info(f"检测到 {engine.engine} 版本: {detected}")

    return detected


# ============================================================
# 5.9 HttpSession（统一 HTTP + 代理 + 重试）
# ============================================================
class HttpSession:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        })
        self._verify = self._init_verify()
        self._proxy_lock = threading.RLock()
        self._refresh_proxy()

    @classmethod
    def get(cls) -> "HttpSession":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @staticmethod
    def _init_verify():
        try:
            import certifi
            return certifi.where()
        except ImportError:
            return True

    def refresh(self):
        with self._proxy_lock:
            self._refresh_proxy()

    def _refresh_proxy(self):
        mode = (SETTINGS.get("proxy_mode", "none") or "none").lower()
        proxies = {}
        if mode == "none":
            pass
        elif mode == "system":
            try:
                proxies = requests.utils.getproxies()
            except Exception:
                proxies = {}
        elif mode in ("http", "https", "socks5"):
            host = SETTINGS.get("proxy_host", "")
            port = int(SETTINGS.get("proxy_port", 0) or 0)
            if host and port:
                user = SETTINGS.get("proxy_user", "")
                pwd = SETTINGS.get("proxy_pwd", "")
                auth = f"{user}:{pwd}@" if user else ""
                url = f"{mode}://{auth}{host}:{port}"
                proxies = {"http": url, "https": url}
        self._session.proxies = proxies
        logger.debug(f"代理已刷新: mode={mode}, 有代理={bool(proxies)}")

    def _need_bypass(self, url: str) -> bool:
        """用 hostname 匹配，防止绕过。"""
        bypass = (SETTINGS.get("proxy_bypass", "") or "").strip()
        if not bypass:
            return False
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        if not host:
            return False
        for pat in bypass.split(","):
            pat = pat.strip().lower()
            if not pat:
                continue
            if host == pat or host.endswith("." + pat):
                return True
        return False

    def request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", 30)
        if "verify" not in kwargs:
            kwargs["verify"] = self._verify
        if self._need_bypass(url):
            kwargs["proxies"] = {}
        with self._proxy_lock:
            try:
                return self._session.request(method, url, **kwargs)
            except requests.exceptions.SSLError:
                logger.warning(f"SSL 失败，降级 verify=False: {url}")
                kwargs["verify"] = False
                return self._session.request(method, url, **kwargs)
            except requests.exceptions.ProxyError as e:
                logger.warning(f"代理错误: {e}，尝试直连")
                kwargs["proxies"] = {}
                return self._session.request(method, url, **kwargs)

    def http_get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def http_post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def http_head(self, url, **kwargs):
        return self.request("HEAD", url, **kwargs)

    def test(self, test_url: str = "https://api.github.com/rate_limit") -> tuple:
        try:
            r = self.http_get(test_url)
            if r.status_code < 400:
                try:
                    ip = self.http_get("https://api.ipify.org").text.strip()
                except Exception:
                    ip = "?"
                return True, f"HTTP {r.status_code}  出口 IP: {ip}"
            return False, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================
# 5.10 MirrorRouter（镜像自动选路）
# ============================================================
class MirrorRouter:
    """镜像路由器。根据 MIRRORS_CONFIG 的 enabled/auto/region 决定用哪些镜像。"""

    _probe_cache: dict = {}
    _probe_lock = threading.Lock()

    @classmethod
    def candidate_mirrors(cls, use_api: bool = False) -> list:
        cfg = MIRRORS_CONFIG
        if not cfg.get("enabled", True):
            return [{"url": "", "region": "direct", "enabled": True, "weight": 1}]

        region = cfg.get("region", "auto") or "auto"
        if region == "direct":
            return [{"url": "", "region": "direct", "enabled": True, "weight": 1}]

        mirrors = cfg.get("api_mirrors" if use_api else "mirrors", [])
        out = []
        for m in mirrors:
            if isinstance(m, str):
                m = {"url": m, "enabled": True,
                     "region": "direct" if not m else "cn", "weight": 5}
            if not m.get("enabled", True):
                continue
            m_region = m.get("region", "direct")
            if region != "auto" and m_region not in (region, "direct"):
                continue
            out.append(m)
        if not out:
            out.append({"url": "", "region": "direct", "enabled": True, "weight": 1})
        return out

    @classmethod
    def order_mirrors(cls, test_url: str, use_api: bool = False) -> list:
        cands = cls.candidate_mirrors(use_api)
        if not MIRRORS_CONFIG.get("auto", True):
            return cands

        now = time.time()
        ttl = int(MIRRORS_CONFIG.get("probe_cache_ttl", 300))
        timeout = float(MIRRORS_CONFIG.get("probe_timeout", 3.0))
        scored = []
        for m in cands:
            url = m.get("url", "")
            full = url + test_url if url else test_url
            with cls._probe_lock:
                cached = cls._probe_cache.get(full)
            if cached and now - cached[2] < ttl:
                ok, ms, _ = cached
            else:
                ok, ms = cls._probe(full, timeout)
                with cls._probe_lock:
                    cls._probe_cache[full] = (ok, ms, now)
            if ok:
                scored.append((ms, m))

        scored.sort(key=lambda x: x[0])
        result = [m for _, m in scored]
        if not any(m.get("region") == "direct" for m in result):
            result.append({"url": "", "region": "direct", "enabled": True, "weight": 1})
        return result

    @staticmethod
    def _probe(url: str, timeout: float = 3.0) -> tuple:
        try:
            t0 = time.time()
            r = HttpSession.get().http_head(url, timeout=timeout, allow_redirects=True)
            ms = (time.time() - t0) * 1000
            return (r.status_code < 400, ms)
        except Exception:
            return (False, 99999)

    @classmethod
    def clear_probe_cache(cls):
        with cls._probe_lock:
            cls._probe_cache.clear()

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
    bios_dir: str = ""
    launch_template: str = "{exe} \"{rom}\""
    installed_at: str = ""
    url: str = ""
    url_type: str = "direct"
    github_repo: str = ""
    libretro_core: str = ""
    archive: str = "zip"

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
    launch_count: int = 0
    override_platform: str = ""
    override_engine: str = ""
    extra_args: str = ""
    bios_file: str = ""
    cheat_file: str = ""
    custom_platform: str = ""
    launch_start_ts: float = 0.0
    profile: str = ""
    perf_profile: str = ""
    patched_from: str = ""
    patch_history: list = field(default_factory=list)
    cleared: bool = False
    # ★ v1.8.0：每个游戏的参数值（param_schema 的 key -> value）
    param_values: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GameEntry":
        valid = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid})


def load_installed() -> list:
    if not INSTALLED_FILE.exists():
        return []
    try:
        with open(INSTALLED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [EmulatorConfig.from_dict(x) for x in data.get("engines", [])]
    except Exception:
        return []


def save_installed(engines):
    try:
        with open(INSTALLED_FILE, "w", encoding="utf-8") as f:
            json.dump({"engines": [e.to_dict() for e in engines]},
                      f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 installed.json 失败: {e}")


def load_games() -> list:
    if not ROMS_FILE.exists():
        return []
    try:
        with open(ROMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [GameEntry.from_dict(x) for x in data.get("games", [])]
    except Exception:
        return []


def save_games(games):
    try:
        with open(ROMS_FILE, "w", encoding="utf-8") as f:
            json.dump({"games": [g.to_dict() for g in games]},
                      f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存 roms.json 失败: {e}")


# ============================================================
# 8. 管理员
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
# 9. QSS（Windows 11 风格 + 暗色覆盖）
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
QLabel#AppTitle { font-size: 14px; font-weight: 600; color: #1c1c1c; }
QListWidget#NavList {
    background-color: #f3f3f3; border: none; outline: none; padding: 6px;
}
QListWidget#NavList::item {
    padding: 9px 12px; border-radius: 5px; margin: 1px 4px; color: #1c1c1c;
}
QListWidget#NavList::item:hover { background-color: #e8e8e8; }
QListWidget#NavList::item:selected {
    background-color: #e0e0e0; color: #1c1c1c; font-weight: 600;
}
QLabel { color: #1c1c1c; background: transparent; }
QLabel#SectionTitle {
    font-size: 15px; font-weight: 600; color: #1c1c1c; padding: 4px 0;
}
QLabel#Hint { color: #767676; }
QLabel#AdminOk {
    color: #0f7b0f; background-color: #e6f4e6;
    padding: 2px 10px; border-radius: 10px;
}
QLabel#AdminNo {
    color: #c42b1c; background-color: #fdeaea;
    padding: 2px 10px; border-radius: 10px;
}
QLineEdit, QComboBox, QSpinBox {
    background-color: #fbfbfb; border: 1px solid #d9d9d9;
    border-bottom: 2px solid #d9d9d9; border-radius: 5px;
    padding: 5px 10px;
    min-height: 26px;
    selection-background-color: #0067c0; selection-color: white;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { background-color: #ffffff; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-bottom: 2px solid #0067c0; background-color: #ffffff;
}
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #666;
    margin-right: 8px;
    width: 0; height: 0;
}
QComboBox QAbstractItemView {
    background-color: #ffffff; border: 1px solid #d9d9d9;
    border-radius: 5px;
    selection-background-color: #e8e8e8;
    selection-color: #1c1c1c; outline: none; padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 6px 10px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #e8f0fa;
}
QSpinBox { padding-right: 20px; }
QSpinBox::up-button, QSpinBox::down-button {
    width: 18px; border: none; background: transparent;
}
QPushButton {
    background-color: #fbfbfb; border: 1px solid #d9d9d9;
    border-bottom: 2px solid #d9d9d9; border-radius: 5px;
    padding: 6px 14px; color: #1c1c1c; min-height: 20px;
}
QPushButton:hover { background-color: #f5f5f5; }
QPushButton:pressed {
    background-color: #ededed; border-bottom: 1px solid #d9d9d9;
}
QPushButton:disabled {
    background-color: #f5f5f5; color: #a0a0a0; border-color: #e5e5e5;
}
QPushButton#PrimaryBtn {
    background-color: #0067c0; border: 1px solid #0067c0;
    border-bottom: 2px solid #005ba8; color: #ffffff; font-weight: 600;
}
QPushButton#PrimaryBtn:hover { background-color: #1975c5; }
QPushButton#PrimaryBtn:pressed {
    background-color: #005ba8; border-bottom: 1px solid #005ba8;
}
QPushButton#DangerBtn {
    background-color: #c42b1c; border: 1px solid #c42b1c;
    border-bottom: 2px solid #a02317; color: #ffffff; font-weight: 600;
}
QPushButton#DangerBtn:hover { background-color: #d13a2b; }
QTableView, QTableWidget {
    background-color: #ffffff; alternate-background-color: #fafafa;
    gridline-color: #ededed; border: 1px solid #e5e5e5;
    border-radius: 6px; selection-background-color: #e8f0fa;
    selection-color: #1c1c1c; outline: none;
}
QTableView::item, QTableWidget::item { padding: 6px 8px; }
QHeaderView::section {
    background-color: #fafafa; color: #5c5c5c; padding: 8px 10px;
    border: none; border-bottom: 1px solid #e5e5e5;
    border-right: 1px solid #ededed; font-weight: 500;
}
QListWidget#GameGrid { background-color: #f3f3f3; border: none; outline: none; }
QListWidget#GameGrid::item {
    background-color: #ffffff; border: 1px solid #e5e5e5;
    border-radius: 6px; margin: 4px; padding: 8px; color: #1c1c1c;
}
QListWidget#GameGrid::item:hover {
    background-color: #fafafa; border: 1px solid #0067c0;
}
QListWidget#GameGrid::item:selected {
    background-color: #e8f0fa; border: 1px solid #0067c0;
}
QListWidget#TimelineList {
    background-color: #f3f3f3; border: none; outline: none; padding: 8px;
}
QListWidget#TimelineList::item {
    background-color: #ffffff; border: 1px solid #e5e5e5;
    border-radius: 6px; margin: 3px 6px; padding: 10px 14px;
}
QListWidget#TimelineList::item:hover { border: 1px solid #0067c0; }
QListWidget#TimelineList::item:selected {
    background-color: #e8f0fa; border: 1px solid #0067c0;
}
QListWidget#TimelineList::item:disabled {
    background-color: #fafafa; color: #999; border: none;
    font-weight: 600; padding: 8px 14px 4px 14px;
}
QListWidget#PeerList {
    background-color: #ffffff; border: 1px solid #e5e5e5;
    border-radius: 6px; outline: none; padding: 4px;
}
QListWidget#PeerList::item {
    padding: 8px 10px; border-radius: 4px; color: #1c1c1c;
}
QListWidget#PeerList::item:hover { background-color: #f3f3f3; }
QListWidget#PeerList::item:selected {
    background-color: #e8f0fa; color: #1c1c1c;
}
QTextEdit#ChatView {
    background-color: #ffffff; border: 1px solid #e5e5e5;
    border-radius: 6px; padding: 8px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
}
QStatusBar {
    background-color: #fafafa; color: #5c5c5c;
    border-top: 1px solid #e5e5e5;
}
QStatusBar::item { border: none; }
QSplitter::handle { background-color: #e5e5e5; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:hover { background-color: #0067c0; }
QProgressBar {
    background-color: #ededed; border: none; border-radius: 3px;
    text-align: center; height: 6px; color: transparent;
}
QProgressBar::chunk { background-color: #0067c0; border-radius: 3px; }
QGroupBox {
    background-color: #ffffff; border: 1px solid #e5e5e5;
    border-radius: 6px; margin-top: 14px;
    padding: 14px 12px 12px 12px; font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: #1c1c1c; background-color: #ffffff;
}
QScrollBar:vertical {
    background: transparent; width: 12px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c8c8c8; border-radius: 4px; min-height: 24px; margin: 0 2px;
}
QScrollBar::handle:vertical:hover { background: #a8a8a8; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal {
    background: transparent; height: 12px; margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #c8c8c8; border-radius: 4px; min-width: 24px; margin: 2px 0;
}
QScrollBar::handle:horizontal:hover { background: #a8a8a8; }
QCheckBox, QRadioButton { color: #1c1c1c; spacing: 8px; padding: 4px 0; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px; height: 18px; border-radius: 4px;
    border: 1px solid #8a8a8a; background-color: #fbfbfb;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #0067c0; border: 1px solid #0067c0;
}
QRadioButton::indicator { border-radius: 9px; }
QTextEdit {
    background-color: #ffffff; border: 1px solid #d9d9d9;
    border-radius: 5px; padding: 8px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    selection-background-color: #0067c0; selection-color: white;
}
QMenu {
    background-color: #fbfbfb; border: 1px solid #d9d9d9;
    border-radius: 6px; padding: 4px;
}
QMenu::item {
    padding: 7px 28px 7px 14px; border-radius: 4px; color: #1c1c1c;
}
QMenu::item:selected { background-color: #e8e8e8; color: #1c1c1c; }
QMenu::separator { height: 1px; background: #e5e5e5; margin: 4px 8px; }
QTabWidget::pane {
    background-color: #ffffff; border: 1px solid #e5e5e5;
    border-radius: 6px; top: -1px;
}
QTabBar::tab {
    background-color: transparent; color: #5c5c5c;
    padding: 8px 16px; border: none;
    border-bottom: 2px solid transparent; margin-right: 4px;
}
QTabBar::tab:selected {
    color: #0067c0; border-bottom: 2px solid #0067c0;
}
QTabBar::tab:hover:!selected { background-color: #f5f5f5; border-radius: 4px; }
QDialog { background-color: #f3f3f3; }
QScrollArea { border: none; background: transparent; }
QFrame#ResourceCard {
    background-color: #ffffff; border: 1px solid #e5e5e5;
    border-radius: 6px;
}
QFrame#ResourceCard:hover { border: 1px solid #0067c0; }
QToolButton {
    background-color: #fbfbfb; border: 1px solid #d9d9d9;
    border-radius: 4px;
}
QToolButton:hover { background-color: #f5f5f5; }
"""


DARK_QSS_OVERLAY = """
* { color: #e8e8e8; }
QMainWindow, QWidget { background-color: #1f1f1f; }
QFrame#TopBar { background-color: #252525; border-bottom: 1px solid #3a3a3a; }
QLabel { color: #e8e8e8; background: transparent; }
QLabel#AppTitle { color: #e8e8e8; }
QLabel#SectionTitle { color: #e8e8e8; }
QLabel#Hint { color: #a0a0a0; }
QLabel#AdminOk { color: #6dbf6d; background-color: #1e3a1e; }
QLabel#AdminNo { color: #ff6b5e; background-color: #3a1e1e; }

QListWidget#NavList { background-color: #1f1f1f; }
QListWidget#NavList::item { color: #e8e8e8; }
QListWidget#NavList::item:hover { background-color: #333333; }
QListWidget#NavList::item:selected {
    background-color: #3a3a3a; color: #4cc2ff;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #2a2a2a; color: #e8e8e8;
    border: 1px solid #454545; border-bottom: 2px solid #454545;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { background-color: #303030; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-bottom: 2px solid #4cc2ff; background-color: #303030;
}
QComboBox QAbstractItemView {
    background-color: #2b2b2b; color: #e8e8e8;
    border: 1px solid #454545;
    selection-background-color: #3a3a3a; selection-color: #4cc2ff;
}
QComboBox QAbstractItemView::item:hover { background-color: #333333; }

QPushButton {
    background-color: #2b2b2b; color: #e8e8e8;
    border: 1px solid #454545; border-bottom: 2px solid #454545;
}
QPushButton:hover { background-color: #333333; }
QPushButton:pressed { background-color: #3a3a3a; }
QPushButton:disabled { background-color: #252525; color: #666666; border-color: #333333; }
QPushButton#PrimaryBtn {
    background-color: #0067c0; border-color: #0067c0; color: #ffffff;
}
QPushButton#PrimaryBtn:hover { background-color: #1975c5; }
QPushButton#PrimaryBtn:pressed { background-color: #005ba8; }
QPushButton#DangerBtn {
    background-color: #c42b1c; border-color: #c42b1c; color: #ffffff;
}
QPushButton#DangerBtn:hover { background-color: #d13a2b; }

QTableView, QTableWidget {
    background-color: #2b2b2b; alternate-background-color: #262626;
    gridline-color: #3a3a3a; border: 1px solid #3a3a3a;
    color: #e8e8e8;
    selection-background-color: #1e3a52; selection-color: #4cc2ff;
}
QHeaderView::section {
    background-color: #252525; color: #a0a0a0;
    border-bottom: 1px solid #3a3a3a; border-right: 1px solid #3a3a3a;
}

QListWidget#GameGrid { background-color: #1f1f1f; }
QListWidget#GameGrid::item {
    background-color: #2b2b2b; border: 1px solid #3a3a3a; color: #e8e8e8;
}
QListWidget#GameGrid::item:hover {
    background-color: #333333; border: 1px solid #4cc2ff;
}
QListWidget#GameGrid::item:selected {
    background-color: #1e3a52; border: 1px solid #4cc2ff;
}

QListWidget#TimelineList { background-color: #1f1f1f; }
QListWidget#TimelineList::item {
    background-color: #2b2b2b; border: 1px solid #3a3a3a; color: #e8e8e8;
}
QListWidget#TimelineList::item:hover { border: 1px solid #4cc2ff; }
QListWidget#TimelineList::item:selected {
    background-color: #1e3a52; border: 1px solid #4cc2ff;
}
QListWidget#TimelineList::item:disabled {
    background-color: #252525; color: #808080; border: none;
}

QListWidget#PeerList {
    background-color: #262626; border: 1px solid #3a3a3a;
}
QListWidget#PeerList::item { color: #e8e8e8; }
QListWidget#PeerList::item:hover { background-color: #333333; }
QListWidget#PeerList::item:selected { background-color: #1e3a52; color: #4cc2ff; }

QTextEdit#ChatView {
    background-color: #232323; border: 1px solid #3a3a3a; color: #e8e8e8;
}
QTextEdit {
    background-color: #232323; color: #e8e8e8;
    border: 1px solid #454545;
}

QStatusBar {
    background-color: #252525; color: #a0a0a0; border-top: 1px solid #3a3a3a;
}
QSplitter::handle { background-color: #3a3a3a; }
QSplitter::handle:hover { background-color: #4cc2ff; }

QProgressBar { background-color: #3a3a3a; color: transparent; }
QProgressBar::chunk { background-color: #4cc2ff; }

QGroupBox {
    background-color: #2b2b2b; border: 1px solid #3a3a3a; color: #e8e8e8;
}
QGroupBox::title { color: #e8e8e8; background-color: #2b2b2b; }

QScrollBar:vertical { background: transparent; }
QScrollBar::handle:vertical { background: #4a4a4a; }
QScrollBar::handle:vertical:hover { background: #5a5a5a; }
QScrollBar:horizontal { background: transparent; }
QScrollBar::handle:horizontal { background: #4a4a4a; }
QScrollBar::handle:horizontal:hover { background: #5a5a5a; }

QCheckBox, QRadioButton { color: #e8e8e8; }
QCheckBox::indicator, QRadioButton::indicator {
    border: 1px solid #808080; background-color: #2a2a2a;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #4cc2ff; border: 1px solid #4cc2ff;
}

QMenu { background-color: #2b2b2b; border: 1px solid #454545; color: #e8e8e8; }
QMenu::item { color: #e8e8e8; }
QMenu::item:selected { background-color: #3a3a3a; color: #4cc2ff; }
QMenu::separator { background: #3a3a3a; }

QTabWidget::pane { background-color: #2b2b2b; border: 1px solid #3a3a3a; }
QTabBar::tab { color: #a0a0a0; }
QTabBar::tab:selected { color: #4cc2ff; border-bottom: 2px solid #4cc2ff; }
QTabBar::tab:hover:!selected { background-color: #333333; }

QDialog { background-color: #1f1f1f; }
QFrame#ResourceCard {
    background-color: #2b2b2b; border: 1px solid #3a3a3a;
}
QFrame#ResourceCard:hover { border: 1px solid #4cc2ff; }
QToolButton {
    background-color: #2b2b2b; border: 1px solid #454545; color: #e8e8e8;
}
QToolButton:hover { background-color: #333333; }
"""


# ============================================================
# 10. 表格模型
# ============================================================
class GameTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows: list = []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 7

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ["", "", tr("library_col_name"), tr("library_col_platform"),
                    tr("library_col_size"), tr("library_col_playtime"),
                    tr("library_col_path")][section]
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
                if (row.override_platform or row.override_engine
                        or row.extra_args or row.bios_file or row.profile
                        or row.perf_profile or row.patched_from
                        or getattr(row, "param_values", {})):
                    return "⚙"
                return ""
            if col == 2:
                return row.name
            if col == 3:
                return row.custom_platform or row.platform
            if col == 4:
                return format_size(row.size)
            if col == 5:
                running = row.launch_start_ts and row.launch_start_ts > 0
                base = human_duration(row.play_seconds)
                if running:
                    return f"{base} (运行中)"
                return base
            if col == 6:
                return row.path
        if role == Qt.ForegroundRole:
            if col == 0:
                return QColor("#f7b500") if row.favorite else QColor("#cccccc")
            if col == 1:
                return QColor("#c47f00")
            if col == 3:
                return QColor("#0067c0")
            if col == 5 and row.launch_start_ts and row.launch_start_ts > 0:
                return QColor("#0f7b0f")
        if role == Qt.TextAlignmentRole and col in (0, 1, 4, 5):
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return row.path
        return None

    def get(self, row: int):
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
        if lm is None:
            return False
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
        self._rows: list = []
        self._updates: dict = {}

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def set_update_info(self, platform: str, engine: str, latest: str, url: str):
        self._updates[f"{platform}/{engine}"] = (latest, url)
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 4), self.index(len(self._rows) - 1, 4))

    def get_update(self, platform: str, engine: str) -> tuple:
        return self._updates.get(f"{platform}/{engine}", ("", ""))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 5

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return [tr("engines_col_platform"), tr("engines_col_engine"),
                    tr("engines_col_path"), tr("engines_col_source"),
                    tr("engines_col_update")][section]
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
                return row.platform_name or row.platform
            if col == 1:
                v = row.version or ""
                if v.lower() in ("manual", "unknown", ""):
                    v = tr("engines_version_unknown")
                return f"{row.engine} {v}".strip()
            if col == 2:
                return row.engine_path
            if col == 3:
                src_map = {"import": tr("engines_source_import"),
                           "download": tr("engines_source_download"),
                           "manual": tr("engines_source_manual")}
                return src_map.get(row.source, row.source)
            if col == 4:
                latest, _ = self.get_update(row.platform, row.engine)
                if latest:
                    return tr("engines_update_available", v=latest)
                if row.url_type == "manual" or not (row.github_repo or parse_github_repo(row.url)):
                    return tr("engines_update_manual")
                return tr("engines_update_latest")
        if role == Qt.ForegroundRole:
            if col == 0:
                return QColor("#0067c0")
            if col == 4:
                latest, _ = self.get_update(row.platform, row.engine)
                if latest:
                    return QColor("#0f7b0f")
        return None


class BiosTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows: list = []

    def set_rows(self, rows):
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
            return [row.name, format_size(row.size), row.md5,
                    row.known_as or tr("bios_unknown")][col]
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
# 10.5 ★ v1.8.0：QStyledItemDelegate（修复平台列 UI 错位）
# ============================================================
class PlatformComboDelegate(QStyledItemDelegate):
    """平台列下拉框委托。

    替代原来的 setCellWidget(QComboBox)，修复滚动/列宽调整时的错位。
    """

    def __init__(self, parent=None, options: Optional[list] = None):
        super().__init__(parent)
        # options: [(display, value), ...]
        self._options = options or []

    def set_options(self, options: list):
        self._options = options

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        for display, value in self._options:
            combo.addItem(display, value)
        combo.currentIndexChanged.connect(
            lambda _i, c=combo: self._commit_editor(c))
        return combo

    def _commit_editor(self, combo):
        try:
            self.commitData.emit(combo)
            self.closeEditor.emit(combo)
        except Exception:
            pass

    def setEditorData(self, editor, index):
        if not isinstance(editor, QComboBox):
            return
        value = index.data(Qt.EditRole)
        idx = editor.findData(value)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        if not isinstance(editor, QComboBox):
            return
        value = editor.currentData()
        model.setData(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def paint(self, painter, option, index):
        # 让 Qt 画默认背景/选中态
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # 强制不画文字，我们自己画
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        # 画下拉框外观
        value = index.data(Qt.EditRole) or ""
        display = value
        for d, v in self._options:
            if v == value:
                display = d
                break

        rect = option.rect.adjusted(4, 3, -4, -3)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        bg = QColor("#fbfbfb") if not (option.state & QStyle.State_Selected) else QColor("#e8f0fa")
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(QColor("#d9d9d9"), 1))
        painter.drawRoundedRect(rect, 4, 4)

        # 文字
        painter.setPen(QPen(QColor("#1c1c1c")))
        text_rect = rect.adjusted(6, 0, -20, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, str(display))

        # 箭头
        arrow_x = rect.right() - 14
        arrow_y = rect.center().y()
        tri = QPolygon([
            QPoint(arrow_x - 4, arrow_y - 2),
            QPoint(arrow_x + 4, arrow_y - 2),
            QPoint(arrow_x, arrow_y + 3),
        ])
        painter.setBrush(QBrush(QColor("#666")))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(tri)

        painter.restore()


# ============================================================
# 11. BIOS 数据库 + 自动归类
# ============================================================
BIOS_DB: dict = {}
BIOS_MD5_INDEX: dict = {}


def load_bios_db():
    global BIOS_DB, BIOS_MD5_INDEX
    if BIOS_DB_FILE.exists():
        try:
            with open(BIOS_DB_FILE, "r", encoding="utf-8") as f:
                BIOS_DB = json.load(f)
        except Exception as e:
            logger.exception(f"读取 bios_db.json 失败: {e}")
            BIOS_DB = {}
    if not BIOS_DB:
        BIOS_DB = json.loads(json.dumps(DEFAULT_BIOS_DB))
        try:
            with open(BIOS_DB_FILE, "w", encoding="utf-8") as f:
                json.dump(BIOS_DB, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    BIOS_MD5_INDEX = {}
    for plat, pcfg in BIOS_DB.get("platforms", {}).items():
        for fname, finfo in (pcfg.get("files") or {}).items():
            md5 = (finfo.get("md5") or "").lower()
            if md5:
                BIOS_MD5_INDEX[md5] = (plat, fname)
    logger.info(f"BIOS DB: {len(BIOS_MD5_INDEX)} 条 MD5 记录")


def identify_bios_platform(path: Path, md5: str = "") -> Optional[str]:
    if not BIOS_DB:
        return None

    if not md5:
        try:
            md5 = md5_of_file(path)
        except Exception:
            md5 = ""
    if md5 and md5.lower() in BIOS_MD5_INDEX:
        return BIOS_MD5_INDEX[md5.lower()][0]

    fname_lower = path.name.lower()
    for plat, pcfg in BIOS_DB.get("platforms", {}).items():
        files = {k.lower() for k in (pcfg.get("files") or {})}
        aliases = {k.lower() for k in (pcfg.get("aliases") or {})}
        if fname_lower in files or fname_lower in aliases:
            return plat

    norm = re.sub(r"[\s_\-\.]", "", fname_lower)
    for plat, pcfg in BIOS_DB.get("platforms", {}).items():
        for known in (pcfg.get("files") or {}):
            if re.sub(r"[\s_\-\.]", "", known.lower()) == norm:
                return plat
    return None


def auto_organize_bios(dry_run: bool = False) -> dict:
    if not BIOS_DB:
        load_bios_db()
    result: dict = {}
    if not BIOS_DIR.exists():
        return result

    for f in BIOS_DIR.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(BIOS_DIR)
            if len(rel.parts) > 1:
                continue
        except ValueError:
            continue

        try:
            md5 = md5_of_file(f)
        except Exception:
            md5 = ""
        plat = identify_bios_platform(f, md5)
        if not plat:
            continue

        dst_dir = BIOS_DIR / plat
        dst = dst_dir / f.name
        result[plat] = result.get(plat, 0) + 1

        if dry_run:
            continue
        try:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(dst))
            logger.info(f"BIOS 归类: {f.name} -> {plat}/")
        except Exception as e:
            logger.exception(f"移动 BIOS 失败: {e}")
    return result


_BIOS_CHECK_CACHE: dict = {}
_BIOS_CHECK_LOCK = threading.Lock()
_BIOS_CHECK_TTL = 300


def clear_bios_check_cache():
    with _BIOS_CHECK_LOCK:
        _BIOS_CHECK_CACHE.clear()


def check_bios_ready(engine: "EmulatorConfig") -> tuple:
    """检查 BIOS 是否齐全。5 分钟缓存。"""
    if not engine:
        return True, []
    if not engine.bios_required:
        return True, []

    cache_key = f"{engine.platform}|{engine.engine}|{engine.engine_dir}"
    now = time.time()

    with _BIOS_CHECK_LOCK:
        cached = _BIOS_CHECK_CACHE.get(cache_key)
        if cached and now - cached[0] < _BIOS_CHECK_TTL:
            return cached[1], cached[2]

    if not BIOS_DB:
        load_bios_db()

    pcfg = BIOS_DB.get("platforms", {}).get(engine.platform, {})
    required = pcfg.get("required_any") or []
    if not required:
        required = resolve_engine_field(engine, "bios_files", []) or []

    bios_dir_rel = resolve_engine_field(engine, "bios_dir", "") or ""
    search_dirs = []
    if bios_dir_rel:
        search_dirs.append(Path(engine.engine_dir) / bios_dir_rel)
    search_dirs.append(Path(engine.engine_dir))
    search_dirs.append(BIOS_DIR)
    search_dirs.append(BIOS_DIR / engine.platform)

    missing = []
    MAX_SCAN = 5000
    for req in required:
        found = False
        req_lower = req.lower()
        for d in search_dirs:
            if not d.exists():
                continue
            try:
                count = 0
                for f in d.rglob("*"):
                    count += 1
                    if count > MAX_SCAN:
                        logger.debug(f"BIOS 扫描 {d} 超过 {MAX_SCAN} 文件，截断")
                        break
                    if f.is_file() and f.name.lower() == req_lower:
                        found = True
                        break
            except Exception:
                pass
            if found:
                break
        if not found:
            missing.append(req)

    result = (len(missing) == 0), missing
    with _BIOS_CHECK_LOCK:
        _BIOS_CHECK_CACHE[cache_key] = (now, result[0], result[1])
    return result


load_bios_db()


# ============================================================
# 12. BIOS 文件扫描
# ============================================================
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
    "dc_boot.bin": "DC BIOS",
    "dc_flash.bin": "DC Flash",
    "ymir_ipl.bin": "SS IPL ROM",
    "pcxtbios.bin": "PCem/86Box XT BIOS",
    "ibm5160.rom": "IBM 5160 BIOS",
    "ibmpc102.bin": "IBM PC 5150 BIOS (1982)",
    "ibmpc204.bin": "IBM PC 5150 BIOS (1986)",
    "ami386.bin": "AMI 386 BIOS",
    "ami286.bin": "AMI 286 BIOS",
    "award386.bin": "Award 386 BIOS",
    "award286.bin": "Award 286 BIOS",
    "mrbios.bin": "MR BIOS",
    "xtide.rom": "XT-IDE BIOS",
    "et4000.bin": "Tseng ET4000 VGA BIOS",
    "s3virge.bin": "S3 ViRGE VGA BIOS",
    "voodoo.bin": "3dfx Voodoo BIOS",
    "flash.bin": "通用 Flash BIOS",
    "bios.rom": "通用 BIOS ROM",
    "exec.bin": "Intellivision EXEC",
    "grom.bin": "Intellivision GROM",
}


@dataclass
class BiosFile:
    name: str
    path: str
    size: int
    md5: str
    known_as: str = ""


def scan_bios() -> list:
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


# ============================================================
# 13. 存档备份 / 还原
# ============================================================
def backup_all_saves() -> list:
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


def list_save_backups() -> list:
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
# ★ 导入辅助函数与 Worker (修复 NameError)
# ============================================================
def clean_game_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or path.stem


MIN_ROM_SIZE = 1024


def import_games_scan(files: list, engines_json: dict) -> tuple:
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
        
        # 依赖 guess_platform_by_ext，如果之前没定义，这里补一个简单的
        ext = f.suffix.lower()
        ext_map = get_all_platform_rom_extensions(engines_json)
        platforms = ext_map.get(ext)
        platform = platforms[0] if platforms else None
        
        if size < MIN_ROM_SIZE and f.suffix.lower() != ".cue":
            if platform not in ("pcem", "x86box"):
                continue
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


class EngineImportWorker(QThread):
    progress = Signal(str)
    done = Signal(list, list, list)
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
                temp_root = Path(tempfile.mkdtemp(
                    prefix="mikan_emu_", dir=str(TEMP_DIR)))
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
            all_exes = []
            for f in files:
                if f.suffix.lower() == ".exe":
                    all_exes.append(f)
                    if str(f) in matched_paths:
                        continue
                    try:
                        top = f.relative_to(scan_root).parts[0]
                    except ValueError:
                        top = f.name
                    if top not in unmatched:
                        unmatched.append(top)
            self.done.emit(installed, unmatched, all_exes)
        except Exception as e:
            logger.exception("导入模拟器失败")
            self.fail.emit(str(e))
        finally:
            if temp_root and temp_root.exists():
                shutil.rmtree(temp_root, ignore_errors=True)


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
                temp_root = Path(tempfile.mkdtemp(
                    prefix="mikan_emu_rom_", dir=str(TEMP_DIR)))
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
# 14. 进程监控 Worker
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
# 15. Worker: 多线程下载（接入 MirrorRouter）
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
        return HttpSession.get().request(method, url, **kwargs)

    def _try_mirrors(self, use_mirror: bool = True):
        """用 MirrorRouter 自动选路。use_mirror=False 时只直连。"""
        is_github = ("github.com/" in self._url
                     or "githubusercontent.com/" in self._url)
        if not use_mirror or not is_github:
            try:
                r = self._request("HEAD", self._url, allow_redirects=True)
                return self._url, r
            except Exception:
                return None, None

        test_url = "https://github.com/robots.txt"
        ordered = MirrorRouter.order_mirrors(test_url, use_api=False)
        for m in ordered:
            prefix = m.get("url", "")
            full = prefix + self._url if prefix else self._url
            try:
                self.status.emit(tr("download_trying_mirror", url=full))
                r = self._request("HEAD", full, allow_redirects=True)
                if r.status_code < 400:
                    return full, r
            except Exception as e:
                logger.debug(f"镜像 {full} 失败: {e}")
                continue
        return None, None

    def run(self):
        try:
            use_mirror = bool(SETTINGS.get("download_use_mirror", True))
            real_url, head = self._try_mirrors(use_mirror=use_mirror)
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
                if r.status_code == 200:
                    errors.append((idx, RuntimeError("SERVER_IGNORED_RANGE")))
                    return
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
            if any("SERVER_IGNORED_RANGE" in str(e) for _, e in errors):
                logger.warning("服务器不支持 Range，退化为单线程下载")
                for _, _, p in parts:
                    if p.exists():
                        try:
                            p.unlink()
                        except Exception:
                            pass
                self._downloaded = 0
                self._run_single(url)
                return
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
# 16. Worker: 镜像测试
# ============================================================
class MirrorTestWorker(QThread):
    one = Signal(str, bool, float)
    done = Signal(int, int)

    def __init__(self, test_url: str, use_api: bool = False):
        super().__init__()
        self._test_url = test_url
        self._use_api = use_api

    def run(self):
        mirrors = get_api_mirror_list() if self._use_api else get_mirror_list()
        ok_count = 0
        fail_count = 0
        http = HttpSession.get()

        for m in mirrors:
            prefix = m.get("url", "") if isinstance(m, dict) else m
            url = prefix + self._test_url if prefix else self._test_url
            t0 = time.time()
            ok = False
            try:
                r = http.http_head(url, timeout=5, allow_redirects=True)
                if r.status_code < 400:
                    ok = True
            except Exception:
                try:
                    r = http.http_get(url, timeout=5, stream=True, allow_redirects=True)
                    if r.status_code < 400:
                        ok = True
                    r.close()
                except Exception:
                    ok = False
            ms = (time.time() - t0) * 1000
            display = prefix if prefix else "（直连）"
            self.one.emit(display, ok, ms)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        self.done.emit(ok_count, fail_count)


# ============================================================
# 17. ★ v1.8.0：ReleasesWorker（全量拉取 GitHub Releases）
# ============================================================
class ReleasesWorker(QThread):
    """拉取指定引擎的全部 GitHub Releases。

    信号：
        one(platform, engine, releases)  releases 是 list[dict]
        progress(str)                    当前状态
        done()                           全部完成
        fail(str)                        某个失败（不中断）
    """
    one = Signal(str, str, list)
    progress = Signal(str)
    done = Signal()
    fail = Signal(str, str)

    def __init__(self, installed: list, engines_json: dict,
                 use_mirror: bool = True):
        super().__init__()
        self._installed = installed
        self._engines_json = engines_json
        self._use_mirror = use_mirror
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _api_headers(self) -> dict:
        h = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        }
        token = (SETTINGS.get("github_token", "") or "").strip()
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def _api_get(self, url: str, timeout: int = 15):
        """请求 GitHub API，自动走 API 镜像。"""
        headers = self._api_headers()
        mirrors = get_api_mirror_list() if self._use_mirror else [
            {"url": "", "region": "direct"}]

        last_err = ""
        for m in mirrors:
            if self._cancel:
                return None
            prefix = m.get("url", "") if isinstance(m, dict) else m
            full = prefix + url if prefix else url
            try:
                r = HttpSession.get().http_get(
                    full, headers=headers, timeout=timeout)
                if r.status_code == 403:
                    remaining = r.headers.get("X-RateLimit-Remaining", "?")
                    last_err = f"API 速率限制 (remaining={remaining})"
                    logger.warning(f"{last_err}: {full}")
                    continue
                if r.status_code == 404:
                    last_err = "仓库不存在或无 Releases"
                    continue
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    continue
                return r.json()
            except Exception as e:
                last_err = str(e)
                continue
        if last_err:
            logger.debug(f"_api_get({url}) 失败: {last_err}")
        return None

    def _fetch_releases(self, repo: str) -> list:
        """拉取全部 releases，按发布时间倒序。"""
        api = f"https://api.github.com/repos/{repo}/releases?per_page=30"
        data = self._api_get(api)
        if not isinstance(data, list):
            return []

        result = []
        for rel in data:
            if not isinstance(rel, dict):
                continue
            tag = (rel.get("tag_name") or "").strip()
            if not tag:
                continue

            # 找一个 Windows 资产
            assets = rel.get("assets") or []
            win_asset = None
            for a in assets:
                if not isinstance(a, dict):
                    continue
                name = (a.get("name") or "").lower()
                if not name.endswith((".zip", ".7z", ".rar", ".exe")):
                    continue
                if "win" in name or "windows" in name:
                    win_asset = a
                    break
            if win_asset is None:
                for a in assets:
                    if not isinstance(a, dict):
                        continue
                    name = (a.get("name") or "").lower()
                    if name.endswith((".zip", ".7z", ".rar", ".exe")):
                        win_asset = a
                        break

            if win_asset is None:
                continue

            result.append({
                "tag": tag,
                "name": rel.get("name") or tag,
                "published_at": rel.get("published_at") or "",
                "prerelease": bool(rel.get("prerelease", False)),
                "body": rel.get("body") or "",
                "html_url": rel.get("html_url") or "",
                "download_url": win_asset.get("browser_download_url", ""),
                "asset_name": win_asset.get("name", ""),
                "asset_size": int(win_asset.get("size", 0) or 0),
            })
        return result

    def run(self):
        total = len(self._installed)
        for idx, e in enumerate(self._installed):
            if self._cancel:
                break
            repo = e.github_repo or parse_github_repo(e.url)
            if not repo or e.url_type == "manual":
                continue

            self.progress.emit(
                f"[{idx+1}/{total}] {e.platform_name}/{e.engine} …")
            try:
                releases = self._fetch_releases(repo)
                if releases:
                    self.one.emit(e.platform, e.engine, releases)
                else:
                    self.fail.emit(
                        f"{e.platform}/{e.engine}",
                        tr("update_dialog_no_releases"))
            except Exception as ex:
                logger.exception(f"拉取 {repo} releases 失败: {ex}")
                self.fail.emit(f"{e.platform}/{e.engine}", str(ex))
        self.done.emit()


# ============================================================
# 18. ★ v1.8.0：UpdateDialog（交互式查看 + 选版本 + 镜像开关）
# ============================================================
class UpdateDialog(QDialog):
    """检查更新对话框。

    - 表格列出每个引擎的当前版本 + 可用版本下拉
    - 用户自己选版本
    - 底部有「使用镜像加速」开关
    - 点「更新」逐个下载
    """
    request_update = Signal(str, str, dict, bool)  # platform, engine, release, use_mirror

    def __init__(self, installed: list, engines_json: dict, parent=None):
        super().__init__(parent)
        self._installed = installed
        self._engines_json = engines_json
        self._releases: dict = {}   # "platform/engine" -> list[dict]
        self._workers: list = []
        self._current_worker = None
        self.setWindowTitle(tr("update_dialog_title"))
        self.setMinimumSize(960, 620)
        self._build_ui()
        QTimer.singleShot(50, self._check_all)

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(10)

        # 顶部工具栏
        top = QHBoxLayout()
        title = QLabel(tr("update_dialog_title"))
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch(1)

        self.btn_check = QPushButton(tr("update_dialog_check"))
        self.btn_check.setObjectName("PrimaryBtn")
        self.btn_check.clicked.connect(self._check_all)
        top.addWidget(self.btn_check)

        self.check_mirror = QCheckBox(tr("update_dialog_use_mirror"))
        self.check_mirror.setChecked(True)
        top.addWidget(self.check_mirror)

        self.btn_close = QPushButton(tr("msg_cancel"))
        self.btn_close.clicked.connect(self.reject)
        top.addWidget(self.btn_close)
        v.addLayout(top)

        # 提示
        hint = QLabel(tr("update_dialog_token_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        # 状态
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("Hint")
        v.addWidget(self.lbl_status)

        # 表格
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            tr("update_dialog_engine"),
            tr("update_dialog_current"),
            tr("update_dialog_available"),
            tr("update_dialog_published"),
            tr("update_dialog_prerelease"),
            tr("update_dialog_action"),
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        v.addWidget(self.table, 1)

        # 进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        v.addWidget(self.progress)

        # 日志
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.setStyleSheet(
            "font-family:'Cascadia Mono','Consolas',monospace;font-size:12px;")
        v.addWidget(self.log)

    # ---------- 检查 ----------
    def _check_all(self):
        if self._current_worker is not None and self._current_worker.isRunning():
            return
        if not self._installed:
            self.lbl_status.setText(tr("engines_empty"))
            return

        self.table.setRowCount(0)
        self._releases.clear()
        self.log.clear()
        self.btn_check.setEnabled(False)
        self.lbl_status.setText(tr("update_dialog_fetching"))

        use_mirror = self.check_mirror.isChecked()
        worker = ReleasesWorker(self._installed, self._engines_json,
                                use_mirror=use_mirror)
        worker.one.connect(self._on_releases)
        worker.progress.connect(self.lbl_status.setText)
        worker.fail.connect(self._on_fetch_fail)
        worker.done.connect(self._on_fetch_done)
        worker.finished.connect(self._on_worker_finished)
        self._current_worker = worker
        self._workers.append(worker)
        worker.start()

    def _on_releases(self, platform: str, engine: str, releases: list):
        key = f"{platform}/{engine}"
        self._releases[key] = releases
        self._add_row(platform, engine, releases)

    def _on_fetch_fail(self, key: str, err: str):
        self.log.append(f"⚠ {key}: {err}")

    def _on_fetch_done(self):
        self.lbl_status.setText("")
        if self.table.rowCount() == 0:
            self.log.append(tr("update_dialog_all_latest"))

    def _on_worker_finished(self):
        self.btn_check.setEnabled(True)
        self._current_worker = None

    def _add_row(self, platform: str, engine: str, releases: list):
        # 找到已安装的引擎
        target = None
        for e in self._installed:
            if e.platform == platform and e.engine == engine:
                target = e
                break
        if target is None:
            return

        row = self.table.rowCount()
        self.table.insertRow(row)

        name_item = QTableWidgetItem(f"{target.platform_name}/{target.engine}")
        self.table.setItem(row, 0, name_item)

        cur_ver = target.version or tr("engines_version_unknown")
        self.table.setItem(row, 1, QTableWidgetItem(cur_ver))

        combo = QComboBox()
        combo.setMinimumWidth(260)
        for rel in releases:
            tag = rel["tag"]
            mark = ""
            if rel.get("prerelease"):
                mark = " [pre]"
            if version_newer(tag, target.version):
                mark += "  ★"
            size = human_size(rel.get("asset_size", 0)) if rel.get("asset_size") else ""
            label = f"{tag}{mark}" + (f"  ({size})" if size else "")
            combo.addItem(label, tag)
        # 默认选中第一个比当前版本新的，没有就选第一个
        default_idx = 0
        for i, rel in enumerate(releases):
            if version_newer(rel["tag"], target.version):
                default_idx = i
                break
        combo.setCurrentIndex(default_idx)
        combo.currentIndexChanged.connect(
            lambda _i, p=platform, en=engine, c=combo:
                self._on_version_changed(p, en, c))
        self.table.setCellWidget(row, 2, combo)

        pub = ""
        if releases:
            pub = (releases[default_idx].get("published_at") or "")[:10]
        self.table.setItem(row, 3, QTableWidgetItem(pub))

        pre_item = QTableWidgetItem("")
        pre_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 4, pre_item)

        btn = QPushButton(tr("update_dialog_update"))
        btn.setObjectName("PrimaryBtn")
        btn.clicked.connect(
            lambda _=False, p=platform, en=engine:
                self._on_update_clicked(p, en))
        self.table.setCellWidget(row, 5, btn)

        # 存 meta
        self.table.item(row, 0).setData(Qt.UserRole, (platform, engine))
        self._update_row_preview(row, platform, engine, default_idx)

    def _on_version_changed(self, platform: str, engine: str, combo: QComboBox):
        row = self._find_row(platform, engine)
        if row < 0:
            return
        self._update_row_preview(row, platform, engine, combo.currentIndex())

    def _update_row_preview(self, row: int, platform: str, engine: str, idx: int):
        key = f"{platform}/{engine}"
        releases = self._releases.get(key) or []
        if not (0 <= idx < len(releases)):
            return
        rel = releases[idx]
        pub = (rel.get("published_at") or "")[:10]
        self.table.setItem(row, 3, QTableWidgetItem(pub))
        pre_item = self.table.item(row, 4)
        if pre_item:
            pre_item.setText("⚠" if rel.get("prerelease") else "")
            pre_item.setForeground(
                QColor("#c47f00") if rel.get("prerelease") else QColor("#999"))

    def _find_row(self, platform: str, engine: str) -> int:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.UserRole) == (platform, engine):
                return r
        return -1

    def _on_update_clicked(self, platform: str, engine: str):
        row = self._find_row(platform, engine)
        if row < 0:
            return
        combo = self.table.cellWidget(row, 2)
        if not isinstance(combo, QComboBox):
            return
        tag = combo.currentData()
        key = f"{platform}/{engine}"
        releases = self._releases.get(key) or []
        rel = None
        for x in releases:
            if x["tag"] == tag:
                rel = x
                break
        if rel is None:
            return

        notes = (rel.get("body") or "").strip()
        if len(notes) > 600:
            notes = notes[:600] + "…"
        if not notes:
            notes = rel.get("name") or tag

        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("update_dialog_confirm",
               engine=f"{platform}/{engine}", version=tag, notes=notes),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        use_mirror = self.check_mirror.isChecked()
        self.log.append(f">>> 更新 {platform}/{engine} → {tag}"
                        + ("  [镜像]" if use_mirror else "  [直连]"))
        self.request_update.emit(platform, engine, rel, use_mirror)
        self.accept()

    def closeEvent(self, event):
        for w in self._workers:
            try:
                if w.isRunning():
                    w.requestInterruption()
                    w.wait(500)
            except Exception:
                pass
        super().closeEvent(event)


# ============================================================
# 19. BatchUpdateDialog（批量更新，保留原有）
# ============================================================
class BatchUpdateDialog(QDialog):
    def __init__(self, pending, parent=None):
        super().__init__(parent)
        self._pending = pending
        self._idx = 0
        self._ok = 0
        self._fail = 0
        self._worker = None
        self.setWindowTitle(tr("engines_batch_title"))
        self.setMinimumSize(640, 420)
        self._build_ui()
        QTimer.singleShot(100, self._next)

    def _build_ui(self):
        v = QVBoxLayout(self)
        self.lbl_head = QLabel(f"共 {len(self._pending)} 个引擎待更新")
        self.lbl_head.setObjectName("SectionTitle")
        v.addWidget(self.lbl_head)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, len(self._pending))
        self.progress.setValue(0)
        v.addWidget(self.progress)

        self.progress_file = QProgressBar()
        self.progress_file.setRange(0, 100)
        self.progress_file.setValue(0)
        v.addWidget(self.progress_file)

        self.lbl_cur = QLabel("")
        self.lbl_cur.setObjectName("Hint")
        v.addWidget(self.lbl_cur)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.Close).clicked.connect(self.reject)
        v.addWidget(btns)

    def _next(self):
        if self._idx >= len(self._pending):
            self.lbl_head.setText(
                tr("engines_batch_done", ok=self._ok, fail=self._fail))
            self.lbl_cur.setText("")
            self.progress_file.setValue(100)
            return

        engine, version, url = self._pending[self._idx]
        self.progress.setValue(self._idx)
        self.lbl_cur.setText(
            f"[{self._idx + 1}/{len(self._pending)}] "
            f"{engine.platform_name}/{engine.engine} → {version}")
        self.log.append(f"\n>>> 更新 {engine.engine} → {version}")

        ext = ".zip"
        archive = engine.archive or "zip"
        if archive == "7z":
            ext = ".7z"
        elif archive in ("7z_sfx", "bare_exe"):
            ext = ".exe"
        tmp = TEMP_DIR / f"batch_{engine.platform}_{engine.engine}{ext}"

        self.progress_file.setValue(0)
        w = DownloadWorker(url, tmp, SETTINGS.get("download_threads", 8))
        self._worker = w
        w.progress.connect(
            lambda cur, total: self.progress_file.setValue(
                int(cur * 100 / total) if total > 0 else 0))
        w.status.connect(lambda s: self.log.append("  " + s))
        w.done.connect(lambda path, e=engine: self._on_one_done(e, path))
        w.fail.connect(lambda err, e=engine: self._on_one_fail(e, err))
        w.start()

    def _on_one_done(self, engine, path):
        try:
            self._install(engine, Path(path))
            self.log.append(f"  ✅ {engine.engine} 更新完成")
            self._ok += 1
        except Exception as e:
            self.log.append(f"  ❌ {engine.engine} 安装失败: {e}")
            self._fail += 1
        self._idx += 1
        QTimer.singleShot(100, self._next)

    def _on_one_fail(self, engine, err):
        self.log.append(f"  ❌ {engine.engine} 下载失败: {err}")
        self._fail += 1
        self._idx += 1
        QTimer.singleShot(100, self._next)

    def _install(self, engine, archive: Path):
        cfg = {
            "platform_name": engine.platform_name,
            "version": engine.version,
            "url": engine.url,
            "url_type": engine.url_type,
            "github_repo": engine.github_repo,
            "archive": engine.archive,
            "launch_template": engine.launch_template,
            "match": {},
        }
        engines_json = load_engines_json()
        real_cfg = (engines_json.get(engine.platform, {})
                    .get("engines", {}).get(engine.engine))
        if real_cfg:
            cfg.update(real_cfg)

        archive_type = cfg.get("archive", "zip")

        if archive_type == "bare_exe":
            target_dir = ENGINE_DOWNLOAD_DIR / engine.platform / engine.engine
            target_dir.mkdir(parents=True, exist_ok=True)
            target_exe = target_dir / archive.name
            shutil.copy2(archive, target_exe)
            engines = load_installed()
            for e in engines:
                if e.platform == engine.platform and e.engine == engine.engine:
                    e.engine_path = str(target_exe)
                    e.engine_dir = str(target_dir)
                    e.version = engine.version or e.version
                    e.installed_at = time.strftime("%Y-%m-%d %H:%M:%S")
                    break
            save_installed(engines)
            try:
                archive.unlink()
            except Exception:
                pass
            return

        tmp_root = Path(tempfile.mkdtemp(prefix="mikan_batch_", dir=str(TEMP_DIR)))
        try:
            if archive_type == "7z_sfx":
                try:
                    sp.run([str(archive), f"-o{tmp_root}", "-y"],
                           check=True, timeout=600,
                           creationflags=getattr(sp, "CREATE_NO_WINDOW", 0))
                except Exception:
                    import py7zr
                    with py7zr.SevenZipFile(archive, mode="r") as z:
                        z.extractall(tmp_root)
            else:
                extract_archive(archive, tmp_root)

            files = scan_files(tmp_root)
            matches = match_engines(
                files, {engine.platform: {"engines": {engine.engine: cfg}}})
            if not matches:
                raise RuntimeError("解压后没找到可执行文件")

            new_cfg = install_engine_from_match(matches[0], tmp_root, "download")
            new_cfg.version = engine.version or new_cfg.version

            engines = load_installed()
            engines = [e for e in engines
                       if not (e.platform == new_cfg.platform
                               and e.engine == new_cfg.engine)]
            engines.append(new_cfg)
            save_installed(engines)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
            try:
                archive.unlink()
            except Exception:
                pass

# ============================================================
# 20. 启动 / 存档 / BIOS
# ============================================================
class LaunchError(RuntimeError):
    def __init__(self, message: str, original=None, args=None):
        super().__init__(message)
        self.original = original
        self.args_list = args or []


def find_retroarch() -> Optional["EmulatorConfig"]:
    for e in load_installed():
        if e.engine == "retroarch":
            return e
    return None


def _split_cmd(cmd_str: str) -> list:
    """用 shlex 解析，失败回退到简单解析。"""
    try:
        if sys.platform == "win32":
            return shlex.split(cmd_str, posix=False)
        return shlex.split(cmd_str, posix=True)
    except ValueError as e:
        logger.warning(f"shlex 解析失败，回退: {e}")
        args = []
        buf = ""
        in_quote = False
        quote_char = ""
        i = 0
        n = len(cmd_str)
        while i < n:
            ch = cmd_str[i]
            if ch == "\\" and i + 1 < n:
                nxt = cmd_str[i + 1]
                if nxt in ('"', "'"):
                    buf += nxt
                    i += 2
                    continue
                buf += ch
                i += 1
                continue
            if in_quote:
                if ch == quote_char:
                    in_quote = False
                    quote_char = ""
                else:
                    buf += ch
            else:
                if ch in ('"', "'"):
                    in_quote = True
                    quote_char = ch
                elif ch.isspace():
                    if buf:
                        args.append(buf)
                        buf = ""
                else:
                    buf += ch
            i += 1
        if buf:
            args.append(buf)
        return args


def _build_param_args(engine: "EmulatorConfig",
                      param_values: dict) -> list:
    """★ v1.8.0：根据 param_schema 和 param_values 生成参数列表。"""
    schema = get_param_schema(engine)
    if not schema or not param_values:
        return []
    args = []
    for item in schema:
        if not isinstance(item, dict):
            continue
        key = item.get("key", "")
        if not key:
            continue
        if key not in param_values:
            continue
        val = param_values[key]
        default = item.get("default")
        if val == default:
            continue
        typ = item.get("type", "text")
        tpl = item.get("args_template", "")
        if not tpl:
            continue
        if typ == "bool":
            if not val:
                continue
            try:
                s = tpl.format(value="", key=key)
            except Exception:
                s = tpl
            if s.strip():
                args.extend(_split_cmd(s.strip()))
        else:
            try:
                s = tpl.format(value=val, key=key)
            except Exception:
                s = tpl
            if s.strip():
                args.extend(_split_cmd(s.strip()))
    return args


def resolve_launch_args(engine: "EmulatorConfig", game: "GameEntry",
                        rom_path: str = "") -> list:
    actual_rom = rom_path or game.path
    
    # ★ 修复：老版本 Snes9x 不接受带双引号的路径，强制去引号
    if engine.engine.lower() in ("snes9x", "snes9x-x64"):
        tpl = "{exe} {rom}"
    else:
        tpl = resolve_engine_field(engine, "launch_template", "{exe} \"{rom}\"")

    bios_rom_dir = ""
    bios_dir_field = resolve_engine_field(engine, "bios_dir", "") or ""
    if bios_dir_field:
        candidate = Path(engine.engine_dir) / bios_dir_field
        if candidate.exists():
            bios_rom_dir = str(candidate)
        else:
            bios_rom_dir = str(Path(engine.engine_dir))
    else:
        bios_rom_dir = str(Path(engine.engine_dir))

    extra_kwargs = {
        "exe": engine.engine_path,
        "rom": actual_rom,
        "bios_rom_dir": bios_rom_dir,
    }

    if engine.url_type == "libretro" or "{core}" in tpl:
        ra = find_retroarch()
        if not ra:
            raise RuntimeError(tr("launch_retroarch_missing"))
        core_dir = SETTINGS.get("retroarch_core_dir", "").strip()
        if not core_dir:
            core_dir = autodetect_retroarch_core_dir()
        if not core_dir:
            raise RuntimeError(tr("launch_core_missing", core=engine.libretro_core))
        core_path = Path(core_dir) / engine.libretro_core
        if not core_path.exists():
            raise RuntimeError(tr("launch_core_missing", core=engine.libretro_core))
        extra_kwargs["retroarch"] = ra.engine_path
        extra_kwargs["core"] = str(core_path)

    try:
        cmd_str = tpl.format(**extra_kwargs)
    except KeyError as e:
        raise RuntimeError(f"启动模板缺少占位符: {e}")

    args = _split_cmd(cmd_str)
    
    # 下面是你原有的附加参数拼接逻辑（保持不动）
    param_values = getattr(game, "param_values", {}) or {}
    try:
        param_args = _build_param_args(engine, param_values)
        if param_args:
            args.extend(param_args)
    except Exception as e:
        logger.debug(f"生成 param_args 失败: {e}")

    perf_arg = ""
    perf_name = getattr(game, "perf_profile", "") or ""
    if perf_name:
        profiles = get_perf_profiles(engine)
        if perf_name in profiles:
            perf_arg = (profiles[perf_name] or "").strip()

    profile_args = ""
    prof_name = game.profile or SETTINGS.get("default_profile", "")
    profiles = SETTINGS.get("launch_profiles") or {}
    if prof_name and prof_name in profiles:
        profile_args = (profiles[prof_name] or "").strip()

    if perf_arg:
        args.extend(_split_cmd(perf_arg))
    if profile_args:
        args.extend(_split_cmd(profile_args))
    if game.extra_args:
        args.extend(_split_cmd(game.extra_args))

    return args
    # ★ v1.8.0：param_schema 参数
    param_values = getattr(game, "param_values", {}) or {}
    try:
        param_args = _build_param_args(engine, param_values)
        if param_args:
            args.extend(param_args)
    except Exception as e:
        logger.debug(f"生成 param_args 失败: {e}")

    perf_arg = ""
    perf_name = getattr(game, "perf_profile", "") or ""
    if perf_name:
        profiles = get_perf_profiles(engine)
        if perf_name in profiles:
            perf_arg = (profiles[perf_name] or "").strip()

    profile_args = ""
    prof_name = game.profile or SETTINGS.get("default_profile", "")
    profiles = SETTINGS.get("launch_profiles") or {}
    if prof_name and prof_name in profiles:
        profile_args = (profiles[prof_name] or "").strip()

    if perf_arg:
        args.extend(_split_cmd(perf_arg))
    if profile_args:
        args.extend(_split_cmd(profile_args))
    if game.extra_args:
        args.extend(_split_cmd(game.extra_args))

    return args


def resolve_settings_args(engine: "EmulatorConfig") -> list:
    settings_arg = get_settings_args(engine)
    exe = engine.engine_path
    if settings_arg:
        try:
            cmd = settings_arg.format(exe=exe)
        except Exception:
            cmd = f"{exe} {settings_arg}".strip()
    else:
        cmd = exe
    return _split_cmd(cmd)


def copy_bios_for_game(engine: "EmulatorConfig", game: "GameEntry") -> Optional[str]:
    if not game.bios_file:
        return None
    src = Path(game.bios_file)
    if not src.exists():
        return None
    bios_dir_rel = resolve_engine_field(engine, "bios_dir", "") or ""
    if not bios_dir_rel:
        return None
    target_dir = Path(engine.engine_dir) / bios_dir_rel
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        dst = target_dir / src.name
        shutil.copy2(src, dst)
        logger.info(f"BIOS 复制: {src} -> {dst}")
        return str(dst)
    except Exception as e:
        logger.exception(f"BIOS 复制失败: {e}")
        return None


def diagnose_launch_failure(engine: "EmulatorConfig", game: Optional["GameEntry"],
                            exe_args: list, err: Exception) -> str:
    issues = []

    exe = Path(engine.engine_path)
    if not exe.exists():
        issues.append(f"❌ 可执行文件不存在: {exe}")
    elif not exe.is_file():
        issues.append(f"❌ 引擎路径不是文件: {exe}")

    if game is not None and not Path(game.path).exists():
        issues.append(f"❌ ROM 文件不存在: {game.path}")

    if game is not None:
        try:
            sz = Path(game.path).stat().st_size
            if sz == 0:
                issues.append("❌ ROM 文件为空")
            elif sz < 512:
                issues.append(f"⚠️ ROM 文件异常小（{sz} 字节）")
        except Exception:
            pass

    if engine.bios_required:
        bios_files = resolve_engine_field(engine, "bios_files", []) or []
        if not bios_files:
            issues.append("⚠️ 该引擎需要 BIOS，但配置里没指定文件名")
        else:
            bios_dir_rel = resolve_engine_field(engine, "bios_dir", "") or ""
            bios_dir = Path(engine.engine_dir) / bios_dir_rel
            for bf in bios_files:
                if not (bios_dir / bf).exists() and not (get_active_bios_dir() / bf).exists():
                    issues.append(f"⚠️ 可能缺少 BIOS: {bf}")

    if exe.exists():
        try:
            if not os.access(str(exe.parent), os.W_OK):
                issues.append(f"⚠️ 引擎目录不可写: {exe.parent}")
        except Exception:
            pass

    if any(ord(c) > 127 for c in engine.engine_path):
        issues.append("⚠️ 引擎路径含非 ASCII 字符，部分老模拟器会挂")

    err_text = str(err)
    low = err_text.lower()
    if "winerror 740" in low or "requires elevation" in low:
        issues.append("❌ 需要管理员权限运行（试试顶部「以管理员重启」）")
    if "winerror 2" in low or "cannot find the file" in low:
        issues.append("❌ 系统找不到指定的文件")
    if "winerror 5" in low or "access is denied" in low:
        issues.append("❌ 权限不足，可能需要管理员")

    if not issues:
        issues.append("启动失败，但没有检测出明显原因。")
        issues.append(f"命令: {' '.join(exe_args)}")
        issues.append(f"错误: {err_text}")

    return "\n".join(issues)


def _apply_priority_to_pid(pid: int, level: str,
                           include_children: bool = True) -> tuple:
    if not HAS_PSUTIL:
        return False, "psutil 未安装"
    priority_map = {
        "low": psutil.IDLE_PRIORITY_CLASS,
        "normal": psutil.NORMAL_PRIORITY_CLASS,
        "high": psutil.HIGH_PRIORITY_CLASS,
        "realtime": psutil.REALTIME_PRIORITY_CLASS,
    }
    if level not in priority_map:
        return False, f"未知优先级: {level}"

    try:
        proc = psutil.Process(pid)
    except Exception as e:
        return False, str(e)

    targets = [proc]
    if include_children:
        try:
            targets.extend(proc.children(recursive=True))
        except Exception:
            pass

    ok_any = False
    last_err = ""
    for p in targets:
        try:
            if sys.platform == "win32":
                p.nice(priority_map[level])
            else:
                nice_map = {"low": 19, "normal": 0, "high": -10, "realtime": -20}
                p.nice(nice_map[level])
            ok_any = True
        except psutil.AccessDenied as e:
            last_err = f"权限不足: {e}"
        except Exception as e:
            last_err = str(e)

    return ok_any, last_err


def _create_job_object():
    """创建一个带 KILL_ON_JOB_CLOSE 的 Job Object 句柄。"""
    return None

# ============================================================
# ★ 补全：resolve_rom_for_launch (处理 .cue 自动生成)
# ============================================================
_CUE_PLATFORMS = {"ps1", "ss", "dc", "pce", "pcfx", "fmtowns", "neogeo", "arcade"}


def resolve_rom_for_launch(path_str: str, platform: str = "") -> tuple:
    """如果传入的是 .bin/.iso，尝试找同名 .cue，或者自动生成 .mikan_auto.cue。"""
    p = Path(path_str)
    if p.suffix.lower() not in (".bin", ".iso", ".img"):
        return path_str, False
    if platform and platform not in _CUE_PLATFORMS:
        return path_str, False

    # 1. 同目录同名 .cue
    cue = p.with_suffix(".cue")
    if cue.exists():
        return str(cue), True

    # 2. 同目录同名任意 .cue（大小写不敏感）
    try:
        for f in p.parent.iterdir():
            if (f.is_file() and f.stem.lower() == p.stem.lower()
                    and f.suffix.lower() == ".cue"):
                return str(f), True
    except Exception:
        pass

    # 3. 生成 .mikan_auto.cue
    if p.suffix.lower() == ".bin":
        try:
            auto_cue = p.parent / f"{p.stem}.mikan_auto.cue"
            if auto_cue.exists():
                return str(auto_cue), True
            with open(auto_cue, "w", encoding="utf-8") as f:
                f.write(f'FILE "{p.name}" BINARY\n')
                f.write("  TRACK 01 MODE1/2352\n")
                f.write("    INDEX 01 00:00:00\n")
            logger.info(f"自动生成 .cue: {auto_cue}")
            return str(auto_cue), True
        except Exception as e:
            logger.exception(f"生成 .cue 失败: {e}")

    return path_str, False

def launch_game(engine: "EmulatorConfig", game: "GameEntry") -> tuple:
    """启动游戏（极简稳定版，不绑核，无延迟线程）。"""
    actual_rom, switched = resolve_rom_for_launch(game.path, game.platform)

    bios_msg = ""
    if game.bios_file:
        try:
            r = copy_bios_for_game(engine, game)
            if r:
                bios_msg = tr("launch_bios_copied")
        except Exception as e:
            bios_msg = tr("launch_bios_failed", err=str(e))

    args = resolve_launch_args(engine, game, rom_path=actual_rom)

    exe_dir = str(Path(engine.engine_path).parent)
    if engine.url_type == "libretro":
        ra = find_retroarch()
        if ra:
            exe_dir = str(Path(ra.engine_path).parent)

    logger.info(f"[launch] args={args!r}")

    try:
        env = os.environ.copy()
        for k in ("_MEIPASS", "_MEIPASS2", "_MEIPASS_ORIG"):
            env.pop(k, None)

        # 只保留最基础的 Popen
        proc = sp.Popen(
            args, env=env, cwd=exe_dir,
            creationflags=sp.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
    except Exception as e:
        raise LaunchError(
            diagnose_launch_failure(engine, game, args, e),
            original=e,
            args=args,
        )

    logger.info(f"已启动: {' '.join(args)}")

    # 加入 Job Object（保留，用于退出清理，但去掉任何绑核和延迟操作）
    try:
        assign_to_job(proc.pid)
    except Exception:
        pass

    # KeyMapper 生效
    try:
        if SETTINGS.get("keymap_enabled", False) and HAS_KEYBOARD:
            km = get_keymapper()
            km.attach_pid(proc.pid)
    except Exception:
        pass

    # 直接返回，不搞任何延迟线程
    return proc, switched, bios_msg

def open_engine_settings(engine: "EmulatorConfig") -> tuple:
    args = resolve_settings_args(engine)
    exe_dir = str(Path(engine.engine_path).parent)

    logger.info(f"[settings] args={args!r}")

    try:
        env = os.environ.copy()
        for k in ("_MEIPASS", "_MEIPASS2", "_MEIPASS_ORIG"):
            env.pop(k, None)
        proc = sp.Popen(
            args, env=env, cwd=exe_dir,
            creationflags=sp.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0)
    except Exception as e:
        raise LaunchError(
            diagnose_launch_failure(engine, None, args, e),
            original=e,
            args=args,
        )

    # 设置界面也加入 Job（防止孤儿）
    assign_to_job(proc.pid)

    logger.info(f"已打开设置: {' '.join(args)}")
    return proc


# ============================================================
# 21. 性能监控小窗
# ============================================================
class PerfMonitorWindow(QWidget):
    def __init__(self, pid: int, game_name: str, parent=None):
        super().__init__(parent)
        self._pid = pid
        self._game_name = game_name
        self._proc = None
        self._last_net = None
        self._last_net_t = None
        self._last_disk = None
        self._last_disk_t = None
        self._start_ts = time.time()

        self.setWindowTitle(f"{tr('perf_win_title')} - {game_name}")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(300, 230)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        if HAS_PSUTIL:
            try:
                self._proc = psutil.Process(pid)
                try:
                    self._proc.cpu_percent(interval=None)
                except Exception:
                    pass
            except Exception:
                self._proc = None

        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        self.lbl_title = QLabel(self._game_name)
        self.lbl_title.setStyleSheet("font-weight:600; color:#0067c0; font-size:13px;")
        self.lbl_title.setWordWrap(True)
        v.addWidget(self.lbl_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.lbl_cpu = QLabel("—")
        self.lbl_mem = QLabel("—")
        self.lbl_disk = QLabel("—")
        self.lbl_net = QLabel("—")
        self.lbl_elapsed = QLabel("—")
        self.lbl_elapsed.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;")
        for w in (self.lbl_cpu, self.lbl_mem, self.lbl_disk, self.lbl_net):
            w.setStyleSheet("font-family:Consolas,'Cascadia Mono',monospace;")

        rows = [
            (tr("perf_cpu"), self.lbl_cpu),
            (tr("perf_mem"), self.lbl_mem),
            (tr("perf_disk"), self.lbl_disk),
            (tr("perf_net"), self.lbl_net),
            ("运行时长", self.lbl_elapsed),
        ]
        for i, (name, w) in enumerate(rows):
            lbl = QLabel(name)
            lbl.setObjectName("Hint")
            lbl.setFixedWidth(72)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(w, i, 1)
        v.addLayout(grid)

        v.addStretch(1)
        hint = QLabel("psutil · 1 秒刷新 · 关闭游戏后自动退出")
        hint.setObjectName("Hint")
        hint.setStyleSheet("font-size:11px; color:#999;")
        v.addWidget(hint)

    def _tick(self):
        if not HAS_PSUTIL or self._proc is None:
            self.lbl_cpu.setText(tr("perf_none"))
            return
        try:
            if not self._proc.is_running():
                self.close()
                return
            with self._proc.oneshot():
                cpu = self._proc.cpu_percent(interval=None)
                try:
                    mem_mb = self._proc.memory_info().rss / (1024 * 1024)
                except Exception:
                    mem_mb = 0.0
                try:
                    io = self._proc.io_counters()
                except Exception:
                    io = None

            self.lbl_cpu.setText(f"{cpu:5.1f} %")
            self.lbl_mem.setText(f"{mem_mb:7.1f} MB")

            now = time.time()
            if io is not None:
                if self._last_disk is None:
                    self._last_disk = io.read_bytes + io.write_bytes
                    self._last_disk_t = now
                    self.lbl_disk.setText("   0.00 MB/s")
                else:
                    dt = now - self._last_disk_t
                    if dt > 0:
                        total = io.read_bytes + io.write_bytes
                        rate = (total - self._last_disk) / dt / (1024 * 1024)
                        self.lbl_disk.setText(f"{rate:7.2f} MB/s")
                        self._last_disk = total
                        self._last_disk_t = now
            else:
                self.lbl_disk.setText(tr("perf_none"))

            try:
                net = psutil.net_io_counters()
                if self._last_net is None:
                    self._last_net = net.bytes_sent + net.bytes_recv
                    self._last_net_t = now
                    self.lbl_net.setText("   0.0 KB/s")
                else:
                    dt = now - self._last_net_t
                    if dt > 0:
                        total = net.bytes_sent + net.bytes_recv
                        rate = (total - self._last_net) / dt / 1024
                        self.lbl_net.setText(f"{rate:7.1f} KB/s")
                        self._last_net = total
                        self._last_net_t = now
            except Exception:
                self.lbl_net.setText(tr("perf_none"))

            elapsed = int(time.time() - self._start_ts)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.lbl_elapsed.setText(f"{h:02d}:{m:02d}:{s:02d}")
        except psutil.NoSuchProcess:
            self.close()
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        event.accept()


# ============================================================
# 22. 局域网核心
# ============================================================
LAN_MAGIC = "mikan_lan"
LAN_DISCOVERY_PORT = 41234
LAN_BROADCAST_INTERVAL = 2.0
LAN_PEER_TIMEOUT = 6.0
LAN_MAX_TEXT = 8192
LAN_FILE_CHUNK = 64 * 1024
LAN_ACK_TIMEOUT = 3.0
LAN_TEXT_RETRY = 2
LAN_RECV_HEAD_TIMEOUT = 15.0
LAN_PORT_MAX_TRY = 20

LAN_BROADCAST_ID = "__broadcast__"

_LAN_SALT_FILE = LAN_DIR / "salt.bin"


def _lan_get_salt() -> bytes:
    try:
        if _LAN_SALT_FILE.exists():
            return _LAN_SALT_FILE.read_bytes()
    except Exception:
        pass
    salt = os.urandom(16)
    try:
        _LAN_SALT_FILE.write_bytes(salt)
    except Exception:
        pass
    return salt


def _pwd_hash(pwd: str) -> str:
    if not pwd:
        return ""
    salt = _lan_get_salt()
    return hashlib.sha256(salt + pwd.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _lan_safe_filename(name: str) -> str:
    name = Path(str(name)).name
    name = re.sub(r"[^\w\.\-\(\) \u4e00-\u9fff]", "_", name)
    return (name[:120] or "file")


def _is_port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _lan_find_free_port(base: int, max_try: int = LAN_PORT_MAX_TRY) -> int:
    for offset in range(0, max_try + 1):
        p = base + offset
        if p > 65535:
            break
        if _is_port_free(p):
            return p
    return 0


def _scan_shared_dir() -> list:
    result = []
    if not LAN_SHARED_DIR.exists():
        return result
    for f in sorted(LAN_SHARED_DIR.iterdir()):
        if not f.is_file():
            continue
        if f.name.startswith("."):
            continue
        try:
            st = f.stat()
            result.append({"name": f.name, "size": st.st_size,
                           "mtime": st.st_mtime})
        except Exception:
            continue
    return result


class LanIdentity:
    def __init__(self):
        self.id = ""
        self.name = ""
        self._load()

    def _load(self):
        data = {}
        if LAN_IDENTITY_FILE.exists():
            try:
                with open(LAN_IDENTITY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        self.id = data.get("id") or str(_uuid.uuid4())
        self.name = data.get("name") or SETTINGS.get("lan_nickname", "") or ""
        if not self.name:
            self.name = f"mikan_{self.id[:4]}"
        self._save()

    def _save(self):
        try:
            with open(LAN_IDENTITY_FILE, "w", encoding="utf-8") as f:
                json.dump({"id": self.id, "name": self.name},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception(f"保存身份失败: {e}")

    def set_name(self, name: str):
        name = (name or "").strip()[:32]
        if not name or name == self.name:
            return
        self.name = name
        SETTINGS["lan_nickname"] = name
        save_settings()
        self._save()


class LanPeer:
    __slots__ = ("id", "name", "ip", "port", "last_seen")

    def __init__(self, pid, name, ip, port, last_seen):
        self.id = pid
        self.name = name
        self.ip = ip
        self.port = port
        self.last_seen = last_seen


class LanDiscoveryWorker(QThread):
    peer_found = Signal(object)
    peer_lost = Signal(str)
    error = Signal(str)

    def __init__(self, identity: LanIdentity, tcp_port: int, pwd_hash: str):
        super().__init__()
        self._identity = identity
        self._tcp_port = tcp_port
        self._pwd_hash = pwd_hash
        self._stop = False
        self._peers: dict = {}
        self._sock = None

    def stop(self):
        self._stop = True
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    def run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._sock.bind(("", LAN_DISCOVERY_PORT))
            self._sock.settimeout(0.5)
        except Exception as e:
            self.error.emit(f"UDP 绑定失败: {e}")
            return

        logger.info(f"LAN 发现层启动，TCP 端口 {self._tcp_port}")

        last_broadcast = 0.0
        while not self._stop:
            now = time.time()
            if now - last_broadcast >= LAN_BROADCAST_INTERVAL:
                try:
                    payload = {
                        "magic": LAN_MAGIC, "ver": APP_VERSION,
                        "id": self._identity.id, "name": self._identity.name,
                        "port": self._tcp_port, "pwd": self._pwd_hash,
                    }
                    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self._sock.sendto(data, ("255.255.255.255", LAN_DISCOVERY_PORT))
                except Exception as e:
                    logger.debug(f"广播失败: {e}")
                last_broadcast = now

            try:
                data, addr = self._sock.recvfrom(2048)
            except socket.timeout:
                data = None
            except Exception:
                data = None

            if data:
                try:
                    obj = json.loads(data.decode("utf-8", errors="ignore"))
                except Exception:
                    obj = None
                if (obj and obj.get("magic") == LAN_MAGIC
                        and obj.get("id") != self._identity.id):
                    if self._pwd_hash and obj.get("pwd", "") != self._pwd_hash:
                        continue
                    pid = str(obj.get("id", ""))[:64]
                    name = str(obj.get("name", ""))[:32] or f"mikan_{pid[:4]}"
                    try:
                        port = int(obj.get("port", 0))
                    except Exception:
                        port = 0
                    if pid and 0 < port < 65536:
                        ip = addr[0]
                        existing = self._peers.get(pid)
                        if existing:
                            existing.name = name
                            existing.ip = ip
                            existing.port = port
                            existing.last_seen = now
                        else:
                            peer = LanPeer(pid, name, ip, port, now)
                            self._peers[pid] = peer
                            self.peer_found.emit(peer)

            dead = [pid for pid, p in self._peers.items()
                    if now - p.last_seen > LAN_PEER_TIMEOUT]
            for pid in dead:
                self._peers.pop(pid, None)
                self.peer_lost.emit(pid)


class LanChatServer(QThread):
    message_received = Signal(str, str, str, bool)
    file_offer = Signal(str, str, str, int)
    file_progress = Signal(str, int, int)
    file_received = Signal(str, str, bool)
    error = Signal(str)
    share_updated = Signal(str, str)
    share_list_received = Signal(str, str, list)
    peer_seen = Signal(str, str, str, int)

    def __init__(self, identity: LanIdentity, port: int, pwd_hash: str):
        super().__init__()
        self._identity = identity
        self._port = port
        self._pwd_hash = pwd_hash
        self._stop = False
        self._sock = None

    def stop(self):
        self._stop = True
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    def run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if sys.platform == "win32":
                self._sock.setsockopt(socket.SOL_SOCKET,
                                      socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                self._sock.setsockopt(socket.SOL_SOCKET,
                                      socket.SO_REUSEADDR, 1)
            self._sock.bind(("", self._port))
            self._sock.listen(16)
            self._sock.settimeout(0.5)
        except Exception as e:
            self.error.emit(f"TCP 绑定失败: {e}")
            return

        while not self._stop:
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except Exception:
                if self._stop:
                    break
                continue
            threading.Thread(target=self._handle, args=(conn, addr),
                             daemon=True).start()

    @staticmethod
    def _read_line(conn, max_len: int = 8192) -> bytes:
        buf = bytearray()
        conn.settimeout(LAN_RECV_HEAD_TIMEOUT)
        while len(buf) < max_len:
            try:
                chunk = conn.recv(min(256, max_len - len(buf)))
            except Exception:
                return b""
            if not chunk:
                break
            nl = chunk.find(b"\n")
            if nl >= 0:
                buf += chunk[:nl]
                break
            buf += chunk
        return bytes(buf)

    def _handle(self, conn, addr):
        try:
            header = self._read_line(conn)
            if not header:
                conn.close()
                return
            try:
                obj = json.loads(header.decode("utf-8", errors="ignore"))
            except Exception:
                conn.close()
                return
            if not isinstance(obj, dict) or obj.get("magic") != LAN_MAGIC:
                conn.close()
                return
            if self._pwd_hash and obj.get("pwd", "") != self._pwd_hash:
                try:
                    conn.sendall(b'{"ok":false,"reason":"bad_pwd"}\n')
                except Exception:
                    pass
                conn.close()
                return

            peer_id = str(obj.get("id", ""))[:64]
            peer_name = str(obj.get("name", ""))[:32] or f"mikan_{peer_id[:4]}"
            mtype = obj.get("type", "")

            try:
                peer_port = int(obj.get("port", 0) or 0)
            except Exception:
                peer_port = 0
            if peer_id and peer_port <= 0:
                peer_port = 0
            self.peer_seen.emit(peer_id, addr[0], peer_port, peer_name)

            if peer_id == self._identity.id:
                logger.debug("忽略自环消息")
                try:
                    conn.sendall(b'{"ok":true,"self":true}\n')
                except Exception:
                    pass
                conn.close()
                return

            if mtype == "msg":
                self._handle_msg(conn, peer_id, peer_name, obj)
            elif mtype == "file":
                self._handle_file_in(conn, peer_id, peer_name, obj)
            elif mtype == "share_update":
                self.share_updated.emit(peer_id, peer_name)
                try:
                    conn.sendall(b'{"ok":true}\n')
                except Exception:
                    pass
                conn.close()
            elif mtype == "share_list":
                files = obj.get("files") or []
                if not isinstance(files, list):
                    files = []
                clean = []
                for it in files:
                    if isinstance(it, dict) and it.get("name"):
                        clean.append({
                            "name": str(it.get("name", ""))[:200],
                            "size": int(it.get("size", 0) or 0),
                            "mtime": float(it.get("mtime", 0) or 0),
                        })
                self.share_list_received.emit(peer_id, peer_name, clean)
                try:
                    conn.sendall(b'{"ok":true}\n')
                except Exception:
                    pass
                conn.close()
            elif mtype == "share_query":
                self._handle_share_query(conn)
            elif mtype == "share_download":
                self._handle_share_download(conn, obj)
            elif mtype == "request_file":
                self._handle_request_file(conn, obj)
            elif mtype == "hello":
                # ★ 握手：回填端口
                try:
                    conn.sendall(b'{"ok":true}\n')
                except Exception:
                    pass
                conn.close()
            else:
                conn.close()
        except Exception as e:
            logger.debug(f"处理连接失败: {e}")
            try:
                conn.close()
            except Exception:
                pass

    def _handle_msg(self, conn, pid, pname, obj):
        text = str(obj.get("text", ""))[:LAN_MAX_TEXT]
        is_broadcast = bool(obj.get("broadcast", False))
        try:
            conn.sendall(b'{"ok":true}\n')
        except Exception:
            pass
        if text:
            self.message_received.emit(pid, pname, text, is_broadcast)
        conn.close()

    def _handle_file_in(self, conn, pid, pname, obj):
        fname = _lan_safe_filename(str(obj.get("fname", "file")))
        try:
            fsize = int(obj.get("size", 0))
        except Exception:
            fsize = 0
        sha_expect = str(obj.get("sha256", "")).lower()[:64]
        try:
            max_mb = int(SETTINGS.get("lan_max_file_mb", 512))
        except Exception:
            max_mb = 512
        if fsize <= 0 or fsize > max(1, max_mb) * 1024 * 1024:
            try:
                conn.sendall(b'{"ok":false,"reason":"size"}\n')
            except Exception:
                pass
            conn.close()
            return
        if not SETTINGS.get("lan_receive_files", True):
            try:
                conn.sendall(b'{"ok":false,"reason":"disabled"}\n')
            except Exception:
                pass
            conn.close()
            return
        try:
            conn.sendall(b'{"ok":true}\n')
        except Exception:
            conn.close()
            return

        ts = time.strftime("%Y%m%d_%H%M%S")
        tmp = LAN_FILES_DIR / f".part_{pid[:8]}_{ts}_{fname}"
        final = LAN_FILES_DIR / f"{ts}_{fname}"

        self.file_offer.emit(pid, pname, fname, fsize)
        conn.settimeout(LAN_RECV_HEAD_TIMEOUT)

        try:
            fh = open(tmp, "wb")
        except Exception as e:
            logger.warning(f"无法创建临时文件 {tmp}: {e}")
            try:
                conn.sendall(b'{"ok":false,"reason":"io"}\n')
            except Exception:
                pass
            self.file_received.emit(pid, fname, False)
            conn.close()
            return

        done = 0
        ok = False
        try:
            with fh:
                while done < fsize:
                    chunk = conn.recv(min(LAN_FILE_CHUNK, fsize - done))
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    self.file_progress.emit(pid, done, fsize)
            ok = (done == fsize)
        except Exception as e:
            logger.warning(f"接收文件中断: {e}")
            ok = False

        hash_ok = False
        if ok:
            if SETTINGS.get("lan_verify_hash", True) and sha_expect:
                try:
                    hash_ok = (_file_sha256(tmp) == sha_expect)
                except Exception:
                    hash_ok = False
            else:
                hash_ok = True
            if hash_ok:
                try:
                    tmp.rename(final)
                    self.file_received.emit(pid, str(final), True)
                except Exception as e:
                    logger.exception(f"重命名失败: {e}")
                    hash_ok = False
        if not hash_ok:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            self.file_received.emit(pid, fname, False)

        try:
            resp = {"ok": bool(hash_ok), "hash": "ok" if hash_ok else "bad"}
            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception:
            pass
        conn.close()

    def _handle_share_query(self, conn):
        if not SETTINGS.get("lan_share_enabled", True):
            try:
                conn.sendall(b'{"ok":false,"reason":"disabled"}\n')
            except Exception:
                pass
            conn.close()
            return
        files = _scan_shared_dir()
        try:
            resp = {"ok": True, "files": files}
            conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception:
            pass
        conn.close()

    def _handle_share_download(self, conn, obj):
        if not SETTINGS.get("lan_share_enabled", True):
            try:
                conn.sendall(b'{"ok":false,"reason":"disabled"}\n')
            except Exception:
                pass
            conn.close()
            return
        fname = _lan_safe_filename(str(obj.get("fname", "")))
        path = LAN_SHARED_DIR / fname
        if not path.exists() or not path.is_file():
            try:
                conn.sendall(b'{"ok":false,"reason":"notfound"}\n')
            except Exception:
                pass
            conn.close()
            return
        try:
            size = path.stat().st_size
        except Exception:
            try:
                conn.sendall(b'{"ok":false,"reason":"err"}\n')
            except Exception:
                pass
            conn.close()
            return
        try:
            sha = _file_sha256(path)
        except Exception:
            sha = ""
        try:
            header = {"ok": True, "size": size, "sha256": sha, "fname": fname}
            conn.sendall((json.dumps(header, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception:
            conn.close()
            return
        try:
            conn.settimeout(120.0)
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(LAN_FILE_CHUNK)
                    if not chunk:
                        break
                    conn.sendall(chunk)
        except Exception as e:
            logger.debug(f"发送共享文件失败: {e}")
        try:
            conn.close()
        except Exception:
            pass

    def _handle_request_file(self, conn, obj):
        if not SETTINGS.get("lan_share_enabled", True):
            try:
                conn.sendall(b'{"ok":false,"reason":"disabled"}\n')
            except Exception:
                pass
            conn.close()
            return
        fname = _lan_safe_filename(str(obj.get("fname", "")))
        path = LAN_SHARED_DIR / fname
        if not path.exists() or not path.is_file():
            try:
                conn.sendall(b'{"ok":false,"reason":"notfound"}\n')
            except Exception:
                pass
            conn.close()
            return
        try:
            size = path.stat().st_size
        except Exception:
            try:
                conn.sendall(b'{"ok":false,"reason":"err"}\n')
            except Exception:
                pass
            conn.close()
            return
        if size <= 0:
            try:
                conn.sendall(b'{"ok":false,"reason":"empty"}\n')
            except Exception:
                pass
            conn.close()
            return
        try:
            sha = _file_sha256(path)
        except Exception:
            sha = ""
        try:
            header = {"ok": True, "size": size, "sha256": sha, "fname": fname}
            conn.sendall((json.dumps(header, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception:
            conn.close()
            return
        try:
            conn.settimeout(120.0)
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(LAN_FILE_CHUNK)
                    if not chunk:
                        break
                    conn.sendall(chunk)
            logger.info(f"已发送请求文件给对端: {fname} ({size} 字节)")
        except Exception as e:
            logger.debug(f"发送请求文件失败: {e}")
        try:
            conn.close()
        except Exception:
            pass


class LanChatClient:
    @staticmethod
    def _connect(peer: LanPeer, timeout: float = 5.0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((peer.ip, peer.port))
        return s

    @staticmethod
    def _read_line(sock, max_len: int = 8192) -> bytes:
        buf = bytearray()
        sock.settimeout(LAN_ACK_TIMEOUT)
        while len(buf) < max_len:
            try:
                chunk = sock.recv(min(256, max_len - len(buf)))
            except Exception:
                return b""
            if not chunk:
                break
            nl = chunk.find(b"\n")
            if nl >= 0:
                buf += chunk[:nl]
                break
            buf += chunk
        return bytes(buf)

    @staticmethod
    def hello(peer: LanPeer, identity: LanIdentity,
              pwd_hash: str, my_port: int) -> bool:
        obj = {
            "magic": LAN_MAGIC, "type": "hello",
            "id": identity.id, "name": identity.name,
            "port": int(my_port), "pwd": pwd_hash,
        }
        try:
            s = LanChatClient._connect(peer, LAN_ACK_TIMEOUT)
            s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            line = LanChatClient._read_line(s)
            try:
                s.close()
            except Exception:
                pass
            if not line:
                return False
            try:
                resp = json.loads(line.decode("utf-8", errors="ignore"))
            except Exception:
                return False
            return bool(resp.get("ok"))
        except Exception as e:
            logger.debug(f"hello 失败: {e}")
            return False

    @staticmethod
    def send_message(peer: LanPeer, identity: LanIdentity, text: str,
                     pwd_hash: str, is_broadcast: bool = False) -> bool:
        obj = {
            "magic": LAN_MAGIC, "type": "msg",
            "id": identity.id, "name": identity.name,
            "text": text[:LAN_MAX_TEXT], "pwd": pwd_hash,
            "broadcast": bool(is_broadcast),
        }
        for attempt in range(LAN_TEXT_RETRY + 1):
            try:
                s = LanChatClient._connect(peer, timeout=LAN_ACK_TIMEOUT)
                s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
                line = LanChatClient._read_line(s)
                s.close()
                if not line:
                    continue
                try:
                    resp = json.loads(line.decode("utf-8", errors="ignore"))
                except Exception:
                    continue
                if resp.get("ok"):
                    return True
            except Exception as e:
                logger.debug(f"send_message 第 {attempt+1} 次失败: {e}")
        return False

    @staticmethod
    def send_file(peer: LanPeer, identity: LanIdentity, file_path: Path,
                  pwd_hash: str, want_hash: bool = True,
                  progress_cb=None, force: bool = False) -> tuple:
        try:
            fsize = file_path.stat().st_size
        except Exception:
            return False, "err"
        try:
            max_mb = int(SETTINGS.get("lan_max_file_mb", 512))
        except Exception:
            max_mb = 512
        if fsize <= 0 or fsize > max(1, max_mb) * 1024 * 1024:
            return (True, "size") if force else (False, "size")

        sha = ""
        if want_hash:
            try:
                sha = _file_sha256(file_path)
            except Exception:
                sha = ""

        header = {
            "magic": LAN_MAGIC, "type": "file",
            "id": identity.id, "name": identity.name,
            "fname": file_path.name, "size": fsize, "sha256": sha,
            "pwd": pwd_hash,
        }
        try:
            s = LanChatClient._connect(peer, timeout=10.0)
            s.sendall((json.dumps(header, ensure_ascii=False) + "\n").encode("utf-8"))
            line = LanChatClient._read_line(s)
            try:
                resp = json.loads(line.decode("utf-8", errors="ignore"))
            except Exception:
                resp = {}
            if not resp.get("ok"):
                reason = resp.get("reason", "rejected")
                try:
                    s.close()
                except Exception:
                    pass
                return (True, reason) if force else (False, reason)

            s.settimeout(120.0)
            sent = 0
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(LAN_FILE_CHUNK)
                    if not chunk:
                        break
                    s.sendall(chunk)
                    sent += len(chunk)
                    if progress_cb:
                        try:
                            progress_cb(sent, fsize)
                        except Exception:
                            pass

            try:
                s.settimeout(120.0)
                line2 = LanChatClient._read_line(s, max_len=8192)
            except Exception:
                line2 = b""
            try:
                s.close()
            except Exception:
                pass

            if not line2:
                return (True, "no_ack") if force else (False, "no_ack")
            try:
                resp2 = json.loads(line2.decode("utf-8", errors="ignore"))
            except Exception:
                return (True, "no_ack") if force else (False, "no_ack")
            if resp2.get("ok"):
                return True, ""
            if resp2.get("reason") == "io":
                return (True, "io") if force else (False, "io")
            return (True, "hash") if force else (False, "hash")
        except Exception as e:
            logger.debug(f"send_file 失败: {e}")
            return False, "err"

    @staticmethod
    def query_share(peer: LanPeer, identity: LanIdentity, pwd_hash: str) -> Optional[list]:
        obj = {"magic": LAN_MAGIC, "type": "share_query",
               "id": identity.id, "name": identity.name, "pwd": pwd_hash}
        try:
            s = LanChatClient._connect(peer, LAN_ACK_TIMEOUT)
            s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            line = LanChatClient._read_line(s, max_len=1024 * 1024)
            s.close()
            if not line:
                return None
            try:
                resp = json.loads(line.decode("utf-8", errors="ignore"))
            except Exception:
                return None
            if resp.get("ok"):
                return resp.get("files", [])
            return None
        except Exception as e:
            logger.debug(f"query_share 失败: {e}")
            return None

    @staticmethod
    def download_share(peer: LanPeer, identity: LanIdentity, fname: str,
                       pwd_hash: str, save_dir: Path,
                       progress_cb=None) -> tuple:
        obj = {"magic": LAN_MAGIC, "type": "share_download",
               "id": identity.id, "name": identity.name,
               "fname": fname, "pwd": pwd_hash}
        try:
            s = LanChatClient._connect(peer, 10.0)
            s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            line = LanChatClient._read_line(s)
            try:
                resp = json.loads(line.decode("utf-8", errors="ignore"))
            except Exception:
                resp = {}
            if not resp.get("ok"):
                try:
                    s.close()
                except Exception:
                    pass
                return False, resp.get("reason", "rejected"), ""
            fsize = int(resp.get("size", 0))
            sha_expect = str(resp.get("sha256", "")).lower()[:64]
            real_name = _lan_safe_filename(resp.get("fname", fname))
            ts = time.strftime("%Y%m%d_%H%M%S")
            tmp = save_dir / f".part_{ts}_{real_name}"
            final = save_dir / real_name
            if final.exists():
                idx = 2
                while final.exists():
                    final = save_dir / f"{final.stem}_{idx}{final.suffix}"
                    idx += 1
            s.settimeout(120.0)
            done = 0
            with open(tmp, "wb") as f:
                while done < fsize:
                    chunk = s.recv(min(LAN_FILE_CHUNK, fsize - done))
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        try:
                            progress_cb(done, fsize)
                        except Exception:
                            pass
            try:
                s.close()
            except Exception:
                pass
            if done != fsize:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                return False, "incomplete", ""
            if SETTINGS.get("lan_verify_hash", True) and sha_expect:
                try:
                    if _file_sha256(tmp) != sha_expect:
                        try:
                            tmp.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return False, "hash", ""
                except Exception:
                    pass
            tmp.rename(final)
            return True, "", str(final)
        except Exception as e:
            logger.debug(f"download_share 失败: {e}")
            return False, "err", ""

    @staticmethod
    def notify_share_update(peer: LanPeer, identity: LanIdentity,
                            pwd_hash: str) -> bool:
        obj = {
            "magic": LAN_MAGIC, "type": "share_update",
            "id": identity.id, "name": identity.name,
            "pwd": pwd_hash,
        }
        try:
            s = LanChatClient._connect(peer, LAN_ACK_TIMEOUT)
            s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            try:
                LanChatClient._read_line(s)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.debug(f"notify_share_update 失败: {e}")
            return False

    @staticmethod
    def push_share_list(peer: LanPeer, identity: LanIdentity,
                        pwd_hash: str, files: list) -> bool:
        obj = {
            "magic": LAN_MAGIC, "type": "share_list",
            "id": identity.id, "name": identity.name,
            "pwd": pwd_hash,
            "files": files or [],
        }
        try:
            s = LanChatClient._connect(peer, LAN_ACK_TIMEOUT)
            s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            try:
                LanChatClient._read_line(s)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.debug(f"push_share_list 失败: {e}")
            return False

    @staticmethod
    def fetch_file_from_peer(peer: LanPeer, identity: LanIdentity,
                              fname: str, pwd_hash: str,
                              save_dir: Path,
                              progress_cb=None) -> tuple:
        obj = {
            "magic": LAN_MAGIC, "type": "request_file",
            "id": identity.id, "name": identity.name,
            "fname": fname, "pwd": pwd_hash,
        }
        try:
            s = LanChatClient._connect(peer, 10.0)
            s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            line = LanChatClient._read_line(s)
            try:
                resp = json.loads(line.decode("utf-8", errors="ignore"))
            except Exception:
                resp = {}
            if not resp.get("ok"):
                try:
                    s.close()
                except Exception:
                    pass
                return False, resp.get("reason", "rejected"), ""

            fsize = int(resp.get("size", 0))
            sha_expect = str(resp.get("sha256", "")).lower()[:64]
            real_name = _lan_safe_filename(resp.get("fname", fname))
            ts = time.strftime("%Y%m%d_%H%M%S")
            tmp = save_dir / f".part_{ts}_{real_name}"
            final = save_dir / real_name
            if final.exists():
                idx = 2
                while final.exists():
                    final = save_dir / f"{final.stem}_{idx}{final.suffix}"
                    idx += 1

            s.settimeout(120.0)
            done = 0
            with open(tmp, "wb") as f:
                while done < fsize:
                    chunk = s.recv(min(LAN_FILE_CHUNK, fsize - done))
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        try:
                            progress_cb(done, fsize)
                        except Exception:
                            pass
            try:
                s.close()
            except Exception:
                pass

            if done != fsize:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
                return False, "incomplete", ""

            if SETTINGS.get("lan_verify_hash", True) and sha_expect:
                try:
                    if _file_sha256(tmp) != sha_expect:
                        try:
                            tmp.unlink(missing_ok=True)
                        except Exception:
                            pass
                        return False, "hash", ""
                except Exception:
                    pass

            tmp.rename(final)
            return True, "", str(final)
        except Exception as e:
            logger.debug(f"fetch_file_from_peer 失败: {e}")
            return False, "err", ""


LAN_EMOJIS = [
    "😀", "😂", "🤣", "😊", "😍", "😘", "😎", "🤔",
    "😅", "😭", "😡", "🥺", "😴", "🤯", "🥳", "😇",
    "👍", "👎", "👌", "🙏", "👏", "🤝", "💪", "✌️",
    "❤️", "💔", "🔥", "⭐", "🎉", "🎁", "✅", "❌",
    "🐱", "🐶", "🍕", "🍺", "☕", "🌸", "🌙", "☀️",
]

# ============================================================
# 23. 页面：游戏库
# ============================================================
class LibraryPage(QWidget):
    launch_requested = Signal(object)
    open_folder_requested = Signal(object)
    remove_requested = Signal(object)
    favorite_toggled = Signal(object)
    config_requested = Signal(object)
    controls_requested = Signal(object)
    scrape_requested = Signal(object)
    settings_requested = Signal(object)
    status_msg = Signal(str)

    def __init__(self):
        super().__init__()
        self._model = GameTableModel()
        self._proxy = GameFilterProxy()
        self._proxy.setSourceModel(self._model)
        self._games: list = []
        if SETTINGS.get("low_spec_mode", False):
            self._view_mode = "list"
        else:
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
        bar.addWidget(self.edit_search, 1)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(
            lambda: self._proxy.set_keyword(self.edit_search.text()))
        self.edit_search.textChanged.connect(lambda _: self._search_timer.start())

        self.combo_platform = QComboBox()
        self.combo_platform.addItem(tr("library_platform_all"), "")
        self._reload_platform_combo()
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

        self.btn_random = QPushButton("🎲")
        self.btn_random.setToolTip(tr("library_random_btn"))
        self.btn_random.setFixedWidth(40)
        self.btn_random.clicked.connect(self._on_random)
        bar.addWidget(self.btn_random)

        self.btn_scrape = QPushButton(tr("toolbar_scrape"))
        self.btn_scrape.clicked.connect(self._on_batch_scrape)
        bar.addWidget(self.btn_scrape)

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
        for i, mode in enumerate([
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
            QHeaderView.Stretch, QHeaderView.ResizeToContents,
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
            QHeaderView.Interactive]):
            self.table.horizontalHeader().setSectionResizeMode(i, mode)
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

        self.timeline = QListWidget()
        self.timeline.setObjectName("TimelineList")
        self.timeline.itemDoubleClicked.connect(self._on_timeline_double_click)
        self.timeline.setContextMenuPolicy(Qt.CustomContextMenu)
        self.timeline.customContextMenuRequested.connect(self._on_context_menu_timeline)
        self.view_stack.addWidget(self.timeline)

        root.addWidget(self.view_stack, 1)

        tip = QLabel(tr("library_empty"))
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

    def _reload_platform_combo(self):
        current = self.combo_platform.currentData()
        self.combo_platform.blockSignals(True)
        self.combo_platform.clear()
        self.combo_platform.addItem(tr("library_platform_all"), "")
        engines_json = load_engines_json()
        for p, pcfg in engines_json.items():
            if p.startswith("_"):
                continue
            self.combo_platform.addItem(pcfg.get("platform_name", p), p)
        if current:
            idx = self.combo_platform.findData(current)
            if idx >= 0:
                self.combo_platform.setCurrentIndex(idx)
        self.combo_platform.blockSignals(False)

    def refresh_platforms(self):
        self._reload_platform_combo()

    def _toggle_view(self):
        if SETTINGS.get("low_spec_mode", False):
            modes = ["list", "timeline"]
        else:
            modes = ["list", "grid", "timeline"]
        i = modes.index(self._view_mode) if self._view_mode in modes else 0
        self._view_mode = modes[(i + 1) % len(modes)]
        if self._view_mode == "list":
            self.btn_view.setText("⊞")
            self.btn_view.setToolTip(tr("library_view_grid"))
            self.view_stack.setCurrentIndex(0)
        elif self._view_mode == "grid":
            self.btn_view.setText("🕒")
            self.btn_view.setToolTip(tr("library_view_timeline"))
            self.view_stack.setCurrentIndex(1)
            self._rebuild_grid()
        else:
            self.btn_view.setText("☰")
            self.btn_view.setToolTip(tr("library_view_list"))
            self.view_stack.setCurrentIndex(2)
            self._rebuild_timeline()

    def _on_platform_changed(self, index):
        self._proxy.set_platform(self.combo_platform.itemData(index) or "")
        if self._view_mode == "grid":
            self._rebuild_grid()
        elif self._view_mode == "timeline":
            self._rebuild_timeline()

    def _on_filter_changed(self, index):
        self._proxy.set_filter_mode(self.combo_filter.itemData(index) or "all")
        if self._view_mode == "grid":
            self._rebuild_grid()
        elif self._view_mode == "timeline":
            self._rebuild_timeline()

    def _on_sort_changed(self, index):
        self._proxy.set_sort_mode(self.combo_sort.itemData(index) or "name")
        self.table.sortByColumn(2, Qt.AscendingOrder)
        if self._view_mode == "grid":
            self._rebuild_grid()
        elif self._view_mode == "timeline":
            self._rebuild_timeline()

    def set_games(self, games):
        self._games = games
        self._model.set_rows(games)
        self.lbl_count.setText(tr("library_count", n=len(games)))
        if self._view_mode == "grid":
            self._rebuild_grid()
        elif self._view_mode == "timeline":
            self._rebuild_timeline()

    def _filtered_games(self) -> list:
        rows = []
        for i in range(self._proxy.rowCount()):
            idx = self._proxy.index(i, 0)
            src = self._proxy.mapToSource(idx)
            g = self._model.get(src.row())
            if g:
                rows.append(g)
        return rows

    def _rebuild_grid(self):
        self.grid.clear()
        for g in self._filtered_games():
            cover = find_cover(g.name)
            item = QListWidgetItem()
            label = g.name
            if g.favorite:
                label = "★ " + label
            if (g.override_platform or g.override_engine or g.extra_args
                    or g.bios_file or g.profile or g.perf_profile
                    or g.patched_from or getattr(g, "param_values", {})):
                label = "⚙ " + label
            if g.launch_start_ts and g.launch_start_ts > 0:
                label = "▶ " + label
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
                f"{g.name}\n{g.custom_platform or g.platform}\n{human_duration(g.play_seconds)}")
            item.setData(Qt.UserRole, g)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.grid.addItem(item)

    def _rebuild_timeline(self):
        self.timeline.clear()
        rows = [g for g in self._filtered_games() if g.last_played]

        if not rows:
            it = QListWidgetItem("还没有玩过的游戏。")
            it.setFlags(Qt.NoItemFlags)
            self.timeline.addItem(it)
            return

        def _day_of(ts: str) -> str:
            if not ts:
                return "更早"
            d = ts.split(" ")[0]
            today = time.strftime("%Y-%m-%d")
            yesterday = time.strftime("%Y-%m-%d",
                                      time.localtime(time.time() - 86400))
            if d == today:
                return "📅 今天"
            if d == yesterday:
                return "📅 昨天"
            for k in range(2, 8):
                if d == time.strftime("%Y-%m-%d",
                                      time.localtime(time.time() - k * 86400)):
                    return f"📅 {k} 天前"
            return f"📅 {d}"

        groups: dict = {}
        for g in rows:
            groups.setdefault(_day_of(g.last_played), []).append(g)
        for key in groups:
            groups[key].sort(key=lambda x: x.last_played or "", reverse=True)

        order = list(groups.keys())

        def _sort_key(k):
            if k == "📅 今天": return (0, "")
            if k == "📅 昨天": return (1, "")
            m = re.match(r"📅 (\d+) 天前", k)
            if m: return (2, int(m.group(1)))
            if k.startswith("📅 "): return (3, k[2:])
            return (4, k)
        order.sort(key=_sort_key)

        for day in order:
            header = QListWidgetItem(day)
            header.setFlags(Qt.NoItemFlags)
            header.setData(Qt.UserRole, None)
            f = header.font()
            f.setBold(True)
            header.setFont(f)
            self.timeline.addItem(header)

            for g in groups[day]:
                cover = find_cover(g.name)
                item = QListWidgetItem()
                label = (f"{g.name}\n{g.custom_platform or g.platform}  ·  "
                         f"{human_duration(g.play_seconds)}")
                item.setText(label)
                item.setData(Qt.UserRole, g)
                if cover:
                    pix = QPixmap(str(cover))
                    if not pix.isNull():
                        pix = pix.scaled(48, 64, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
                        item.setIcon(QIcon(pix))
                self.timeline.addItem(item)

    def _selected_game(self):
        if self._view_mode == "list":
            idxs = self.table.selectionModel().selectedRows()
            if not idxs:
                return None
            src = self._proxy.mapToSource(idxs[0])
            return self._model.get(src.row())
        elif self._view_mode == "grid":
            items = self.grid.selectedItems()
            if not items:
                return None
            return items[0].data(Qt.UserRole)
        else:
            items = self.timeline.selectedItems()
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

    def _on_timeline_double_click(self, _item):
        g = self._selected_game()
        if g:
            self.launch_requested.emit(g)

    def _on_random(self):
        import random as _r
        rows = self._filtered_games()
        if not rows:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("library_select_hint"))
            return
        g = _r.choice(rows)
        self.status_msg.emit(f"🎲 随机选中: {g.name}")
        if self._view_mode == "list":
            for i in range(self._proxy.rowCount()):
                idx = self._proxy.index(i, 0)
                src = self._proxy.mapToSource(idx)
                if self._model.get(src.row()) is g:
                    self.table.selectRow(i)
                    self.table.scrollTo(idx)
                    break
        elif self._view_mode == "grid":
            for i in range(self.grid.count()):
                it = self.grid.item(i)
                if it.data(Qt.UserRole) is g:
                    self.grid.setCurrentItem(it)
                    self.grid.scrollToItem(it)
                    break
        else:
            for i in range(self.timeline.count()):
                it = self.timeline.item(i)
                if it.data(Qt.UserRole) is g:
                    self.timeline.setCurrentItem(it)
                    self.timeline.scrollToItem(it)
                    break
        self.launch_requested.emit(g)

    def _on_batch_scrape(self):
        rows = self._filtered_games()
        if not rows:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("scrape_batch_none"))
            return
        self.scrape_requested.emit(rows)

    def _show_menu(self, g, global_pos):
        menu = QMenu(self)
        a_launch = menu.addAction(tr("ctx_launch"))
        menu.addSeparator()
        a_folder = menu.addAction(tr("ctx_open_folder"))
        if g.favorite:
            a_fav = menu.addAction(tr("ctx_fav_remove"))
        else:
            a_fav = menu.addAction(tr("ctx_fav_add"))
        menu.addSeparator()
        a_scrape = menu.addAction(tr("ctx_scrape_cover"))
        a_config = menu.addAction(tr("ctx_more_config"))
        a_controls = menu.addAction(tr("ctx_controls"))
        a_settings = menu.addAction(tr("ctx_open_engine_settings"))
        menu.addSeparator()
        a_remove = menu.addAction(tr("ctx_remove"))

        act = menu.exec(global_pos)

        if act == a_launch:
            self.launch_requested.emit(g)
        elif act == a_folder:
            self.open_folder_requested.emit(g)
        elif act == a_fav:
            self.favorite_toggled.emit(g)
        elif act == a_scrape:
            self.scrape_requested.emit([g])
        elif act == a_config:
            self.config_requested.emit(g)
        elif act == a_controls:
            self.controls_requested.emit(g)
        elif act == a_settings:
            self.settings_requested.emit(g)
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

    def _on_context_menu_timeline(self, pos):
        item = self.timeline.itemAt(pos)
        if not item:
            return
        g = item.data(Qt.UserRole)
        if not g:
            return
        self._show_menu(g, self.timeline.viewport().mapToGlobal(pos))

    def refresh_grid(self):
        if self._view_mode == "grid":
            self._rebuild_grid()
        elif self._view_mode == "timeline":
            self._rebuild_timeline()


# ============================================================
# 24. 页面：模拟器
# ============================================================
class EnginePage(QWidget):
    import_requested = Signal()
    download_requested = Signal()
    update_requested = Signal(str, str, str)
    ignore_requested = Signal(str, str, str)
    settings_requested = Signal(object)
    status_message = Signal(str)
    check_update_requested = Signal()

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
        self.btn_check_update = QPushButton("检查更新")
        self.btn_check_update.clicked.connect(self.check_update_requested.emit)
        bar.addWidget(self.btn_check_update)
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
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        root.addWidget(self.table, 1)

        tip = QLabel(tr("engines_empty"))
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

    def refresh(self):
        self._model.set_rows(load_installed())

    def set_update_info(self, platform, engine, latest, url):
        self._model.set_update_info(platform, engine, latest, url)

    def clear_updates(self):
        self._model._updates.clear()
        if self._model._rows:
            self._model.dataChanged.emit(
                self._model.index(0, 4),
                self._model.index(len(self._model._rows) - 1, 4))

    def _on_context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        if row < 0 or row >= len(self._model._rows):
            return
        e = self._model._rows[row]
        latest, url = self._model.get_update(e.platform, e.engine)
        menu = QMenu(self)
        a_update = menu.addAction(tr("engines_update_btn"))
        a_update.setEnabled(bool(latest and url))
        a_ignore = menu.addAction(tr("engines_update_ignore"))
        a_ignore.setEnabled(bool(latest))
        menu.addSeparator()
        a_settings = menu.addAction(tr("engines_open_settings"))
        a_detect = menu.addAction(tr("engines_detect_version"))
        menu.addSeparator()
        a_open = menu.addAction(tr("engines_open_dir"))
        a_del = menu.addAction(tr("engines_delete_btn"))
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act == a_update and url:
            self.update_requested.emit(e.platform, e.engine, url)
        elif act == a_ignore and latest:
            self.ignore_requested.emit(e.platform, e.engine, latest)
        elif act == a_settings:
            self.settings_requested.emit(e)
        elif act == a_detect:
            v = detect_engine_version(e, force=True)
            if v:
                self.status_message.emit(
                    tr("engines_version_detected", v=v))
            else:
                self.status_message.emit(tr("engines_version_detect_failed"))
            self.refresh()
        elif act == a_open:
            try:
                os.startfile(e.engine_dir)
            except Exception as ex:
                QMessageBox.warning(self, tr("msg_warning"), str(ex))
        elif act == a_del:
            self._delete_engine(e)

    def _delete_engine(self, e):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("msg_confirm"))
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"删除引擎 <b>{e.engine}</b>？<br><br>"
            f"平台: {e.platform_name}<br>"
            f"路径: {e.engine_path}<br><br>"
            f"<b>会从引擎库移除。</b>可选是否同时删除磁盘上的引擎目录。"
        )
        cb = QCheckBox(tr("engines_delete_cascade"))
        cb.setChecked(True)
        box.setCheckBox(cb)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("删除")
        box.button(QMessageBox.Yes).setObjectName("DangerBtn")
        box.button(QMessageBox.No).setText(tr("msg_cancel"))
        if box.exec() != QMessageBox.Yes:
            return

        engines = load_installed()
        engines = [x for x in engines
                   if not (x.platform == e.platform and x.engine == e.engine)]
        save_installed(engines)

        if cb.isChecked() and e.engine_dir:
            d = Path(e.engine_dir)
            try:
                if d.exists() and d.is_dir():
                    d.resolve().relative_to(ENGINE_DOWNLOAD_DIR.resolve())
                    shutil.rmtree(d, ignore_errors=True)
                    logger.info(f"已删除引擎目录: {d}")
            except ValueError:
                logger.warning(f"拒绝删除非引擎目录: {d}")
            except Exception as ex:
                logger.exception(f"删除引擎目录失败: {ex}")
                QMessageBox.warning(self, tr("msg_warning"),
                                    f"目录删除失败: {ex}")

        self.refresh()
        self.status_message.emit(tr("engines_delete_ok", engine=e.engine))


# ============================================================
# 25. 页面：BIOS
# ============================================================
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
        btn_refresh.clicked.connect(self._refresh_with_cache_clear)
        bar.addWidget(btn_refresh)
        btn_open = QPushButton("打开 bios 目录")
        btn_open.clicked.connect(lambda: os.startfile(str(BIOS_DIR)))
        bar.addWidget(btn_open)

        btn_pcem = QPushButton(tr("bios_import_pcem_rom"))
        btn_pcem.setObjectName("PrimaryBtn")
        btn_pcem.setToolTip(tr("bios_import_pcem_hint"))
        btn_pcem.clicked.connect(self._import_pcem_rom)
        bar.addWidget(btn_pcem)

        btn_organize = QPushButton("🗂 自动归类")
        btn_organize.setToolTip("扫描 bios/，按平台识别并移动到子目录")
        btn_organize.clicked.connect(self._auto_organize)
        bar.addWidget(btn_organize)

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

    def _refresh_with_cache_clear(self):
        clear_bios_check_cache()
        self.refresh()

    def _auto_organize(self):
        if not BIOS_DB:
            QMessageBox.warning(self, tr("msg_warning"),
                                "bios_db.json 未加载")
            return
        preview = auto_organize_bios(dry_run=True)
        if not preview:
            QMessageBox.information(self, tr("msg_info"),
                                    "没有可归类的 BIOS 文件")
            return
        lines = [f"  {plat}: {n} 个" for plat, n in sorted(preview.items())]
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            "将归类以下文件：\n" + "\n".join(lines) + "\n\n继续？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        result = auto_organize_bios(dry_run=False)
        total = sum(result.values())
        QMessageBox.information(self, tr("msg_info"),
                                f"已归类 {total} 个文件")
        clear_bios_check_cache()
        self.refresh()

    def _import_pcem_rom(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("bios_import_pcem_rom"), str(DATA_DIR))
        if not d:
            return
        root = Path(d)
        roms_dir = root / "roms" if (root / "roms").is_dir() else root

        files = []
        for ext in (".bin", ".rom", ".zip"):
            files.extend(roms_dir.rglob(f"*{ext}"))
        files = sorted({f for f in files if f.is_file()})
        if not files:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("bios_import_pcem_no_files"))
            return

        copied = 0
        skipped = 0
        ts_suffix = int(time.time() * 1000) % 100000
        for f in files:
            try:
                try:
                    rel = f.relative_to(roms_dir)
                except ValueError:
                    rel = Path(f.name)
                dst = BIOS_DIR / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    dst = dst.with_name(f"{dst.stem}_{ts_suffix}{dst.suffix}")
                shutil.copy2(f, dst)
                copied += 1
            except Exception as e:
                logger.exception(f"复制 {f} 失败: {e}")
                skipped += 1

        logger.info(f"PCem/86Box ROM 导入: {copied} 成功, {skipped} 失败")
        QMessageBox.information(self, tr("msg_info"),
                                tr("bios_import_pcem_done", n=copied))
        clear_bios_check_cache()
        self.refresh()


# ============================================================
# 26. ★ v1.8.0：ChartWidget（带悬停精确时间提示）
# ============================================================
class ChartWidget(QWidget):
    def __init__(self, mode: str = "line"):
        super().__init__()
        self._data: list = []          # [(label, seconds), ...]
        self._mode = mode
        self._hover_idx = -1
        self._points: list = []
        self.setMinimumHeight(160)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def set_data(self, data):
        self._data = data
        self._hover_idx = -1
        self.update()

    def _calc_layout(self):
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 46, 12, 12, 30
        cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
        max_v = max((v for _, v in self._data), default=1) or 1
        n = len(self._data)

        points = []
        if n > 0:
            for i, (_, v) in enumerate(self._data):
                if n > 1:
                    x = pad_l + (cw * i / (n - 1))
                else:
                    x = pad_l + cw // 2
                y = pad_t + ch - (v / max_v) * ch if max_v > 0 else pad_t + ch
                points.append((int(x), int(y)))
        return pad_l, pad_r, pad_t, pad_b, cw, ch, max_v, points

    def mouseMoveEvent(self, event):
        if not self._data:
            return
        pad_l, pad_r, pad_t, pad_b, cw, ch, max_v, points = self._calc_layout()
        if not points:
            return

        mx = event.position().x()
        # 动态阈值：30 天图点很密
        n = len(points)
        gap = cw / max(1, n - 1) if n > 1 else cw
        threshold = max(12, min(40, gap * 0.6))

        best_idx = -1
        best_dist = threshold
        for i, (px, _py) in enumerate(points):
            dist = abs(mx - px)
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx != self._hover_idx:
            self._hover_idx = best_idx
            self.update()

    def leaveEvent(self, event):
        self._hover_idx = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b, cw, ch, max_v, points = self._calc_layout()
        n = len(self._data)

        painter.setPen(QPen(QColor("#e5e5e5"), 1))
        painter.drawLine(pad_l, pad_t, pad_l, pad_t + ch)
        painter.drawLine(pad_l, pad_t + ch, pad_l + cw, pad_t + ch)

        painter.setPen(QPen(QColor("#9a9a9a")))
        f = painter.font()
        f.setPointSize(8)
        painter.setFont(f)
        for i in range(5):
            v = max_v * i / 4
            y = pad_t + ch - (v / max_v) * ch
            painter.drawLine(pad_l - 3, int(y), pad_l, int(y))
            painter.drawText(0, int(y) - 7, pad_l - 6, 14,
                             Qt.AlignRight | Qt.AlignVCenter,
                             human_duration(int(v)))

        if self._mode == "line":
            if len(points) >= 2:
                fill_pts = ([(points[0][0], pad_t + ch)] + points
                            + [(points[-1][0], pad_t + ch)])
                fill_poly = QPolygon([QPoint(x, y) for x, y in fill_pts])
                poly = QPolygon([QPoint(x, y) for x, y in points])

                grad = QLinearGradient(0, pad_t, 0, pad_t + ch)
                grad.setColorAt(0, QColor(0, 103, 192, 90))
                grad.setColorAt(1, QColor(0, 103, 192, 10))
                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(fill_poly)

                painter.setPen(QPen(QColor("#0067c0"), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(poly)

            painter.setBrush(QBrush(QColor("#0067c0")))
            painter.setPen(Qt.NoPen)
            for x, y in points:
                painter.drawEllipse(x - 3, y - 3, 6, 6)

            step = max(1, n // 8)
            painter.setPen(QPen(QColor("#767676")))
            for i in range(0, n, step):
                label = self._data[i][0]
                x = points[i][0] if i < len(points) else pad_l
                painter.drawText(x - 25, pad_t + ch + 6, 50, 16,
                                 Qt.AlignCenter, label)
        else:
            gap = cw / n
            bar_w = gap * 0.7
            for i, (label, v) in enumerate(self._data):
                x = pad_l + i * gap + (gap - bar_w) / 2
                bh = (v / max_v) * ch if v > 0 else 0
                y = pad_t + ch - bh
                grad = QLinearGradient(x, y, x, pad_t + ch)
                grad.setColorAt(0, QColor("#1975c5"))
                grad.setColorAt(1, QColor("#0067c0"))
                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bh), 3, 3)
                painter.setPen(QPen(QColor("#767676")))
                painter.drawText(int(x - 5), pad_t + ch + 6,
                                 int(bar_w + 10), 16, Qt.AlignCenter, label)

        if 0 <= self._hover_idx < len(points) and self._mode == "line":
            self._draw_tooltip(painter, pad_l, pad_t, ch, cw, points)

        painter.end()

    def _draw_tooltip(self, painter, pad_l, pad_t, ch, cw, points):
        idx = self._hover_idx
        px, py = points[idx]
        label, seconds = self._data[idx]

        if seconds <= 0:
            duration_str = "0"
        else:
            h, rem = divmod(int(seconds), 3600)
            m, s = divmod(rem, 60)
            if h > 0:
                duration_str = f"{h}h {m:02d}m {s:02d}s"
            elif m > 0:
                duration_str = f"{m}m {s:02d}s"
            else:
                duration_str = f"{s}s"

        text1 = f"{label}"
        text2 = f"时长: {duration_str}"
        text3 = f"({int(seconds)} 秒)"

        f = painter.font()
        f.setPointSize(9)
        painter.setFont(f)
        fm = painter.fontMetrics()
        w1 = fm.horizontalAdvance(text1)
        w2 = fm.horizontalAdvance(text2)
        w3 = fm.horizontalAdvance(text3)
        box_w = max(w1, w2, w3) + 20
        box_h = 3 * fm.height() + 12

        box_x = px + 10
        box_y = py - box_h - 10
        if box_x + box_w > self.width() - 4:
            box_x = px - box_w - 10
        if box_y < 4:
            box_y = py + 10
        if box_x < 4:
            box_x = 4

        painter.setBrush(QBrush(QColor(30, 30, 30, 230)))
        painter.setPen(QPen(QColor(80, 80, 80, 200), 1))
        painter.drawRoundedRect(int(box_x), int(box_y),
                                int(box_w), int(box_h), 6, 6)

        painter.setPen(QPen(QColor("#ffffff")))
        tx = box_x + 10
        ty = box_y + 6 + fm.ascent()
        painter.drawText(int(tx), int(ty), text1)

        painter.setPen(QPen(QColor("#4cc2ff")))
        ty += fm.height()
        painter.drawText(int(tx), int(ty), text2)

        painter.setPen(QPen(QColor("#999999")))
        f2 = painter.font()
        f2.setPointSize(8)
        painter.setFont(f2)
        fm2 = painter.fontMetrics()
        ty += fm2.height()
        painter.drawText(int(tx), int(ty), text3)

        painter.setBrush(QBrush(QColor("#4cc2ff")))
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(px - 5, py - 5, 10, 10)


# ============================================================
# 27. 页面：统计
# ============================================================
class StatsPage(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setSpacing(12)

        title = QLabel(tr("stats_title"))
        title.setObjectName("SectionTitle")
        v.addWidget(title)

        cards = QHBoxLayout()
        self.lbl_time = self._make_card(cards, tr("stats_total_time"))
        self.lbl_games = self._make_card(cards, tr("stats_total_games"))
        self.lbl_launches = self._make_card(cards, tr("stats_total_launches"))
        v.addLayout(cards)

        self.lbl_by_platform = QLabel()
        self.lbl_by_platform.setObjectName("Hint")
        self.lbl_by_platform.setWordWrap(True)
        v.addWidget(self.lbl_by_platform)

        chart_grp = QGroupBox(tr("stats_last_7d"))
        cv = QVBoxLayout(chart_grp)
        self.chart_7d = ChartWidget(mode="line")
        self.chart_7d.setMinimumHeight(180)
        cv.addWidget(self.chart_7d)
        v.addWidget(chart_grp)

        chart_grp2 = QGroupBox(tr("stats_last_30d"))
        cv2 = QVBoxLayout(chart_grp2)
        self.chart_30d = ChartWidget(mode="line")
        self.chart_30d.setMinimumHeight(180)
        cv2.addWidget(self.chart_30d)
        v.addWidget(chart_grp2)

        table_grp = QGroupBox(tr("stats_daily_table"))
        tv = QVBoxLayout(table_grp)
        self.table_daily = QTableWidget(0, 3)
        self.table_daily.setHorizontalHeaderLabels(["日期", "总时长", "主要平台"])
        self.table_daily.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_daily.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_daily.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_daily.verticalHeader().setVisible(False)
        self.table_daily.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_daily.setAlternatingRowColors(True)
        self.table_daily.setMinimumHeight(260)
        tv.addWidget(self.table_daily)
        v.addWidget(table_grp)

        badge_grp = QGroupBox(tr("stats_badges"))
        bgrid = QGridLayout(badge_grp)
        self.badge_labels = []
        badge_keys = [
            "stats_badge_first", "stats_badge_10h", "stats_badge_50h",
            "stats_badge_100h", "stats_badge_1000h",
            "stats_badge_7days", "stats_badge_30days",
            "stats_badge_day8",
            "stats_badge_allplat", "stats_badge_week5plat",
            "stats_badge_lib100", "stats_badge_lib500",
            "stats_badge_launch50", "stats_badge_launch500",
            "stats_badge_fav20", "stats_badge_clear10",
            "stats_badge_lan", "stats_badge_wii", "stats_badge_ps3",
        ]
        for i, key in enumerate(badge_keys):
            lbl = QLabel(tr(key))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumHeight(90)
            lbl.setMinimumWidth(110)
            bgrid.addWidget(lbl, i // 6, i % 6)
            self.badge_labels.append((key, lbl))
        v.addWidget(badge_grp)

        v.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _make_card(self, layout, label_text):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #e5e5e5;border-radius:6px;}")
        v = QVBoxLayout(frame)
        t = QLabel(label_text)
        t.setObjectName("Hint")
        v.addWidget(t)
        val = QLabel("-")
        val.setStyleSheet("font-size:22px;font-weight:600;color:#0067c0;")
        v.addWidget(val)
        layout.addWidget(frame)
        return val

    def refresh(self):
        games = load_games()
        total_sec = sum(g.play_seconds for g in games)
        self.lbl_time.setText(human_duration(total_sec))
        self.lbl_games.setText(str(len(games)))
        self.lbl_launches.setText(str(STATS.get("launches", 0)))

        by_plat = {}
        for g in games:
            by_plat[g.platform] = by_plat.get(g.platform, 0) + g.play_seconds
        lines = []
        for p, sec in sorted(by_plat.items(), key=lambda x: -x[1]):
            if sec <= 0:
                continue
            lines.append(f"{p}: {human_duration(sec)}")
        self.lbl_by_platform.setText(" | ".join(lines) if lines else "-")

        daily = STATS.get("daily", {})
        self.chart_7d.set_data(self._build_series(daily, 7))
        self.chart_30d.set_data(self._build_series(daily, 30))
        self._refresh_daily_table(daily)

        badges = self._compute_badges(games, daily)
        for key, lbl in self.badge_labels:
            unlocked = badges.get(key, False)
            if unlocked:
                lbl.setText(f"🏆\n{tr(key)}\n{tr('stats_badge_unlocked')}")
                lbl.setStyleSheet(
                    "background:#e6f4e6;color:#0f7b0f;border-radius:8px;padding:8px;")
            else:
                lbl.setText(f"🔒\n{tr(key)}\n{tr('stats_badge_locked')}")
                lbl.setStyleSheet(
                    "background:#f5f5f5;color:#999;border-radius:8px;padding:8px;")

    def _build_series(self, daily, days):
        result = []
        now = time.time()
        for i in range(days - 1, -1, -1):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            total = sum((daily.get(d) or {}).values())
            result.append((d[5:], total))
        return result

    def _refresh_daily_table(self, daily):
        rows = []
        for d in sorted(daily.keys(), reverse=True)[:60]:
            plats = daily.get(d, {})
            total = sum(plats.values())
            if total <= 0:
                continue
            top = max(plats.items(), key=lambda x: x[1])[0] if plats else "-"
            rows.append((d, total, top))
        self.table_daily.setRowCount(len(rows))
        for i, (d, total, top) in enumerate(rows):
            self.table_daily.setItem(i, 0, QTableWidgetItem(d))
            self.table_daily.setItem(i, 1, QTableWidgetItem(human_duration(total)))
            self.table_daily.setItem(i, 2, QTableWidgetItem(top))

    def _compute_badges(self, games, daily):
        result = {}
        total_sec = sum(g.play_seconds for g in games)
        now = time.time()

        result["stats_badge_first"] = any(g.last_played for g in games)
        result["stats_badge_10h"] = total_sec >= 10 * 3600
        result["stats_badge_50h"] = any(g.play_seconds >= 50 * 3600 for g in games)
        result["stats_badge_100h"] = total_sec >= 100 * 3600
        result["stats_badge_1000h"] = total_sec >= 1000 * 3600

        streak = 0
        for i in range(7):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            if sum((daily.get(d) or {}).values()) > 0:
                streak += 1
            else:
                break
        result["stats_badge_7days"] = streak >= 7

        streak30 = 0
        for i in range(30):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            if sum((daily.get(d) or {}).values()) > 0:
                streak30 += 1
            else:
                break
        result["stats_badge_30days"] = streak30 >= 30

        result["stats_badge_day8"] = any(
            sum(plats.values()) >= 8 * 3600 for plats in daily.values())

        all_plats = set(k for k in load_engines_json().keys()
                        if not k.startswith("_"))
        played_plats = {g.platform for g in games if g.play_seconds > 0}
        result["stats_badge_allplat"] = bool(all_plats) and all_plats.issubset(played_plats)

        week_plats = set()
        for i in range(7):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            week_plats.update((daily.get(d) or {}).keys())
        result["stats_badge_week5plat"] = len(week_plats) >= 5

        result["stats_badge_lib100"] = len(games) >= 100
        result["stats_badge_lib500"] = len(games) >= 500

        launches = STATS.get("launches", 0)
        result["stats_badge_launch50"] = launches >= 50
        result["stats_badge_launch500"] = launches >= 500

        result["stats_badge_fav20"] = sum(1 for g in games if g.favorite) >= 20
        result["stats_badge_clear10"] = sum(
            1 for g in games if getattr(g, "cleared", False)) >= 10

        lan_used = False
        try:
            if LAN_HISTORY_DIR.exists():
                lan_used = any(LAN_HISTORY_DIR.glob("*.jsonl"))
        except Exception:
            pass
        result["stats_badge_lan"] = lan_used

        played_platforms = {g.platform for g in games if g.last_played}
        result["stats_badge_wii"] = "wii" in played_platforms
        result["stats_badge_ps3"] = "ps3" in played_platforms

        return result


# ============================================================
# 28. 页面：资源
# ============================================================
class ResourcesPage(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel(tr("resources_title"))
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        hint = QLabel(tr("resources_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        bar = QHBoxLayout()
        btn_reset = QPushButton(tr("resources_reset"))
        btn_reset.clicked.connect(self._reset)
        bar.addWidget(btn_reset)
        btn_edit = QPushButton(tr("resources_edit"))
        btn_edit.clicked.connect(self._edit)
        bar.addWidget(btn_edit)
        bar.addStretch(1)
        root.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(14)
        scroll.setWidget(self._content)
        root.addWidget(scroll, 1)

    def refresh(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            else:
                lay = item.layout()
                if lay:
                    while lay.count():
                        sub = lay.takeAt(0)
                        sw = sub.widget()
                        if sw:
                            sw.deleteLater()
                    lay.deleteLater()

        for grp in RESOURCES_CONFIG.get("groups", []):
            grp_box = QGroupBox(f"{grp.get('icon', '')} {grp.get('name', '')}")
            gv = QVBoxLayout(grp_box)
            gv.setSpacing(6)
            for it in grp.get("items", []):
                card = QFrame()
                card.setObjectName("ResourceCard")
                ch = QHBoxLayout(card)
                ch.setContentsMargins(12, 8, 12, 8)
                ch.setSpacing(10)

                info = QVBoxLayout()
                info.setSpacing(2)
                name_lbl = QLabel(f"<b>{it.get('name', '')}</b>")
                name_lbl.setTextFormat(Qt.RichText)
                info.addWidget(name_lbl)
                desc_lbl = QLabel(it.get("desc", ""))
                desc_lbl.setObjectName("Hint")
                desc_lbl.setWordWrap(True)
                info.addWidget(desc_lbl)
                ch.addLayout(info, 1)

                btn = QPushButton(tr("resources_open"))
                btn.setObjectName("PrimaryBtn")
                url = it.get("url", "")
                btn.clicked.connect(lambda _=False, u=url: self._open_url(u))
                ch.addWidget(btn)
                gv.addWidget(card)
            self._content_layout.addWidget(grp_box)

        self._content_layout.addStretch(1)

    def _open_url(self, url: str):
        if not url:
            return
        try:
            webbrowser.open(url)
            logger.info(f"打开资源: {url}")
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("open_failed", e=str(e)))

    def _reset(self):
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     tr("resources_reset") + "?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        global RESOURCES_CONFIG
        RESOURCES_CONFIG = json.loads(json.dumps(DEFAULT_RESOURCES_JSON))
        save_resources()
        self.refresh()

    def _edit(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("resources_edit"), str(CONFIG_DIR), "JSON (*.json)")
        if not fp:
            os.startfile(str(RESOURCES_FILE))
            return
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "groups" in data:
                global RESOURCES_CONFIG
                RESOURCES_CONFIG = data
                save_resources()
                self.refresh()
                QMessageBox.information(self, tr("msg_info"),
                                        tr("resources_saved"))
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

# ============================================================
# 29. 页面：局域网（聊天 + 文件传输）
# ============================================================
class EmojiPanel(QDialog):
    emoji_picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setWindowTitle("")
        grid = QGridLayout(self)
        grid.setSpacing(2)
        grid.setContentsMargins(6, 6, 6, 6)
        cols = 8
        for i, e in enumerate(LAN_EMOJIS):
            btn = QPushButton(e)
            btn.setFixedSize(36, 36)
            btn.setStyleSheet(
                "QPushButton{border:none;font-size:18px;}"
                "QPushButton:hover{background:#e8f0fa;border-radius:4px;}")
            btn.clicked.connect(lambda _=False, ch=e: self._pick(ch))
            grid.addWidget(btn, i // cols, i % cols)

    def _pick(self, ch: str):
        self.emoji_picked.emit(ch)
        self.accept()


class LanPage(QWidget):
    settings_requested = Signal()

    def __init__(self):
        super().__init__()
        self._identity = LanIdentity()
        self._peers: dict = {}
        self._current_peer = None
        self._current_is_broadcast = False
        self._history: dict = {}
        self._discovery = None
        self._server = None
        self._seen_peer_ids: set = set()
        self._file_send_busy = False
        self._actual_port = 0
        self._build_ui()
        self._load_history_index()
        self._rebuild_peer_list()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        topbar = QHBoxLayout()
        title = QLabel(tr("lan_title"))
        title.setObjectName("SectionTitle")
        topbar.addWidget(title)

        topbar.addWidget(QLabel(tr("lan_my_name") + ":"))
        self.edit_nick = QLineEdit()
        self.edit_nick.setPlaceholderText(tr("lan_my_name"))
        self.edit_nick.setFixedWidth(180)
        self.edit_nick.setText(self._identity.name)
        self.edit_nick.editingFinished.connect(self._on_nickname_changed)
        topbar.addWidget(self.edit_nick)

        topbar.addStretch(1)

        self.lbl_status = QLabel("正在启动…")
        self.lbl_status.setObjectName("Hint")
        topbar.addWidget(self.lbl_status)

        btn_open_recv = QPushButton(tr("lan_open_received"))
        btn_open_recv.clicked.connect(lambda: os.startfile(str(LAN_FILES_DIR)))
        topbar.addWidget(btn_open_recv)

        btn_settings = QPushButton("⚙ " + tr("nav_settings"))
        btn_settings.clicked.connect(self.settings_requested.emit)
        topbar.addWidget(btn_settings)
        root.addLayout(topbar)

        note = QLabel(tr("lan_proto_note") + "  " + tr("lan_firewall_hint"))
        note.setObjectName("Hint")
        note.setWordWrap(True)
        root.addWidget(note)

        body = QHBoxLayout()
        body.setSpacing(12)

        left = QVBoxLayout()
        lbl_peers = QLabel(tr("lan_peers"))
        lbl_peers.setObjectName("Hint")
        left.addWidget(lbl_peers)
        self.list_peers = QListWidget()
        self.list_peers.setObjectName("PeerList")
        self.list_peers.setFixedWidth(190)
        self.list_peers.currentItemChanged.connect(self._on_peer_selected)
        self.list_peers.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_peers.customContextMenuRequested.connect(self._on_peer_menu)
        left.addWidget(self.list_peers, 1)
        self.lbl_empty = QLabel(tr("lan_no_peers"))
        self.lbl_empty.setObjectName("Hint")
        self.lbl_empty.setWordWrap(True)
        self.lbl_empty.setFixedWidth(190)
        left.addWidget(self.lbl_empty)
        body.addLayout(left)

        chat_box = QWidget()
        chat_layout = QVBoxLayout(chat_box)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(8)

        self.lbl_chat_title = QLabel("—")
        self.lbl_chat_title.setObjectName("SectionTitle")
        chat_layout.addWidget(self.lbl_chat_title)

        self.chat_view = QTextEdit()
        self.chat_view.setObjectName("ChatView")
        self.chat_view.setReadOnly(True)
        chat_layout.addWidget(self.chat_view, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        chat_layout.addWidget(self.progress)

        input_row = QHBoxLayout()
        self.edit_msg = QLineEdit()
        self.edit_msg.setPlaceholderText(tr("lan_input_ph"))
        self.edit_msg.returnPressed.connect(self._on_send_msg)
        input_row.addWidget(self.edit_msg, 1)

        self.btn_emoji = QToolButton()
        self.btn_emoji.setText("😊")
        self.btn_emoji.setFixedSize(34, 30)
        self.btn_emoji.clicked.connect(self._popup_emoji)
        input_row.addWidget(self.btn_emoji)

        self.btn_send = QPushButton(tr("lan_send"))
        self.btn_send.setObjectName("PrimaryBtn")
        self.btn_send.clicked.connect(self._on_send_msg)
        input_row.addWidget(self.btn_send)

        self.btn_file = QPushButton("📤 " + tr("lan_send_file"))
        self.btn_file.setToolTip("选中文件后强制发给所有在线用户")
        self.btn_file.clicked.connect(self._on_send_file)
        input_row.addWidget(self.btn_file)

        self.btn_clear = QPushButton(tr("lan_clear_history"))
        self.btn_clear.clicked.connect(self._on_clear_history)
        input_row.addWidget(self.btn_clear)
        chat_layout.addLayout(input_row)

        body.addWidget(chat_box, 1)
        root.addLayout(body, 1)

        self.setAcceptDrops(True)
        self._refresh_input_state()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [Path(u.toLocalFile()) for u in urls]
        files = [p for p in paths if p.is_file()]
        if not files:
            return
        if not self._peers:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("lan_broadcast_no_peers"))
            return
        reply = QMessageBox.question(
            self, tr("lan_drop_title"),
            f"把 {len(files)} 个文件强制广播给全部 {len(self._peers)} 个在线用户？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for f in files:
            self._force_broadcast_file(f)
        event.acceptProposedAction()

    def start_service(self):
        if self._discovery is not None and self._discovery.isRunning():
            return
        base_port = int(SETTINGS.get("lan_port", 54322))
        pwd_hash = _pwd_hash(SETTINGS.get("lan_password", ""))

        free_port = _lan_find_free_port(base_port)
        if free_port == 0:
            QMessageBox.critical(
                self, tr("msg_error"),
                f"端口 {base_port}~{base_port + LAN_PORT_MAX_TRY} 全部被占用")
            self.lbl_status.setText("❌ 无可用端口")
            return

        self._actual_port = free_port
        logger.info(f"LAN 端口: {free_port}")

        try:
            self._server = LanChatServer(self._identity, free_port, pwd_hash)
            self._server.message_received.connect(self._on_message_received)
            self._server.file_offer.connect(self._on_file_offer)
            self._server.file_progress.connect(self._on_file_progress)
            self._server.file_received.connect(self._on_file_received)
            self._server.peer_seen.connect(self._on_peer_seen)
            self._server.error.connect(
                lambda e: logger.warning(f"LAN server: {e}"))
            self._server.start()
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("lan_error_start", err=str(e)))
            return

        try:
            self._discovery = LanDiscoveryWorker(self._identity, free_port, pwd_hash)
            self._discovery.peer_found.connect(self._on_peer_found)
            self._discovery.peer_lost.connect(self._on_peer_lost)
            self._discovery.error.connect(
                lambda e: logger.warning(f"LAN discovery: {e}"))
            self._discovery.start()
            self.lbl_status.setText(
                f"运行中 · TCP {free_port} / UDP {LAN_DISCOVERY_PORT}")
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("lan_error_start", err=str(e)))

    def stop_service(self):
        for attr in ("_discovery", "_server"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                obj.stop()
                obj.wait(2000)
            except Exception:
                pass
            try:
                obj.deleteLater()
            except Exception:
                pass
            setattr(self, attr, None)
        self.lbl_status.setText("已停止")

    def restart_service(self):
        self.stop_service()
        self._peers.clear()
        self._seen_peer_ids.clear()
        self._rebuild_peer_list()
        self._current_peer = None
        self._current_is_broadcast = False
        self.lbl_chat_title.setText("—")
        self.chat_view.clear()
        self._refresh_input_state()
        self.lbl_status.setText("正在重启…")
        QTimer.singleShot(500, self.start_service)

    def shutdown(self):
        self.stop_service()

    def _on_nickname_changed(self):
        name = self.edit_nick.text().strip()
        if not name or name == self._identity.name:
            return
        self._identity.set_name(name)

    def _on_peer_found(self, peer):
        is_new = peer.id not in self._seen_peer_ids
        self._seen_peer_ids.add(peer.id)
        self._peers[peer.id] = peer
        self._rebuild_peer_list()
        self._refresh_input_state()
        if is_new:
            self._append_system(peer.id, tr("lan_peer_joined", name=peer.name))
            if not self._current_peer and not self._current_is_broadcast:
                self._select_peer(peer.id)

    def _on_peer_seen(self, info):
        try:
            peer_id, ip, port, name = info
        except Exception:
            return
        if not peer_id:
            return
        try:
            port = int(port or 0)
        except Exception:
            port = 0
        peer = self._peers.get(peer_id)
        if peer is None:
            peer = LanPeer(peer_id, name or f"mikan_{peer_id[:4]}",
                           ip or "", port, time.time())
            self._peers[peer_id] = peer
            self._seen_peer_ids.add(peer_id)
            self._rebuild_peer_list()
        else:
            if ip and not peer.ip:
                peer.ip = ip
            if port > 0:
                peer.port = port
            if name:
                peer.name = name
            peer.last_seen = time.time()
        self._refresh_input_state()

    def _on_peer_lost(self, peer_id: str):
        peer = self._peers.pop(peer_id, None)
        self._rebuild_peer_list()
        if peer:
            self._append_system(peer_id, tr("lan_peer_left", name=peer.name))
            if self._current_peer and self._current_peer.id == peer_id:
                if self._peers:
                    nxt = sorted(self._peers.values(), key=lambda p: p.name.lower())[0]
                    self._select_peer(nxt.id)
                else:
                    self._current_peer = None
                    self.lbl_chat_title.setText("—")
                    self.chat_view.clear()
                    self._refresh_input_state()
        self._refresh_input_state()

    def _rebuild_peer_list(self):
        cur_kind = "broadcast" if self._current_is_broadcast else (
            "peer" if self._current_peer else None)
        cur_id = self._current_peer.id if self._current_peer else None
        self.list_peers.blockSignals(True)
        self.list_peers.clear()

        it_b = QListWidgetItem(f"📢 {tr('lan_broadcast_name')}")
        it_b.setData(Qt.UserRole, ("broadcast", LAN_BROADCAST_ID))
        it_b.setForeground(QColor("#c47f00"))
        self.list_peers.addItem(it_b)
        if cur_kind == "broadcast":
            self.list_peers.setCurrentItem(it_b)

        for peer in sorted(self._peers.values(), key=lambda p: p.name.lower()):
            it = QListWidgetItem(f"● {peer.name}")
            it.setData(Qt.UserRole, ("peer", peer.id))
            it.setForeground(QColor("#0f7b0f"))
            self.list_peers.addItem(it)
            if cur_kind == "peer" and peer.id == cur_id:
                self.list_peers.setCurrentItem(it)

        self.list_peers.blockSignals(False)
        self.lbl_empty.setVisible(len(self._peers) == 0)

    def _select_peer(self, peer_id: str):
        peer = self._peers.get(peer_id)
        if not peer:
            return
        self._current_peer = peer
        self._current_is_broadcast = False
        self.lbl_chat_title.setText(f"💬 {peer.name}  ({peer.ip}:{peer.port})")
        self._render_history(peer.id)
        self._refresh_input_state()
        self._rebuild_peer_list()

    def _on_peer_selected(self, current, _previous):
        if not current:
            return
        data = current.data(Qt.UserRole)
        if not data:
            return
        kind, key = data
        if kind == "broadcast":
            self._current_peer = None
            self._current_is_broadcast = True
            self.lbl_chat_title.setText(tr("lan_broadcast_title"))
            self._render_history(LAN_BROADCAST_ID)
            self._refresh_input_state()
        else:
            self._select_peer(key)

    def _refresh_input_state(self):
        has = self._current_peer is not None or self._current_is_broadcast
        self.edit_msg.setEnabled(has)
        self.btn_send.setEnabled(has)
        self.btn_file.setEnabled(bool(self._peers) and not self._file_send_busy)
        self.btn_emoji.setEnabled(has)
        self.btn_clear.setEnabled(has)

    def _load_history_index(self):
        if not LAN_HISTORY_DIR.exists():
            return
        for fp in LAN_HISTORY_DIR.glob("*.jsonl"):
            pid = fp.stem
            try:
                items = []
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            items.append(json.loads(line))
                        except Exception:
                            continue
                self._history[pid] = items[-500:]
            except Exception:
                pass

    def _history_file(self, peer_id: str) -> Path:
        return LAN_HISTORY_DIR / f"{peer_id}.jsonl"

    def _append_history(self, peer_id: str, who: str, text: str, extra=None):
        rec = {"who": who, "text": text, "ts": time.time()}
        if extra:
            rec.update(extra)
        self._history.setdefault(peer_id, []).append(rec)
        if len(self._history[peer_id]) > 1000:
            self._history[peer_id] = self._history[peer_id][-500:]
        if not SETTINGS.get("lan_keep_history", True):
            return
        try:
            with open(self._history_file(peer_id), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"写历史失败: {e}")

    def _render_history(self, key: str):
        self.chat_view.clear()
        for rec in self._history.get(key, []):
            self._append_line(
                rec.get("who", "peer"),
                rec.get("text", ""),
                rec.get("ts", 0),
                rec.get("kind", "text"),
                rec.get("sender_name", ""),
                peer_id=key)

    def _append_line(self, who, text, ts, kind="text",
                     sender_name="", peer_id=""):
        if who == "me":
            who_label = tr("lan_self_msg")
        elif sender_name:
            who_label = sender_name
        elif peer_id == LAN_BROADCAST_ID:
            who_label = tr("lan_broadcast_name")
        else:
            peer = self._peers.get(peer_id) if peer_id else self._current_peer
            who_label = peer.name if peer else "?"
        ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else ""
        color = "#0067c0" if who == "me" else "#0f7b0f"
        prefix = (f"<span style='color:{color};font-weight:600;'>"
                  f"[{ts_str}] {who_label}:</span>")
        if kind == "system":
            self.chat_view.append(f"<i style='color:#999;'>{text}</i>")
        elif kind == "file":
            safe = (text or "").replace("<", "&lt;").replace(">", "&gt;")
            self.chat_view.append(
                f"{prefix} <span style='color:#c47f00;'>{safe}</span>")
        else:
            safe = ((text or "")
                    .replace("<", "&lt;").replace(">", "&gt;")
                    .replace("\n", "<br>"))
            self.chat_view.append(f"{prefix} {safe}")
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _append_system(self, peer_id: str, text: str):
        self._append_history(peer_id, "system", text, {"kind": "system"})
        cur_key = LAN_BROADCAST_ID if self._current_is_broadcast else (
            self._current_peer.id if self._current_peer else "")
        if cur_key == peer_id:
            self._append_line("system", text, time.time(),
                              kind="system", peer_id=peer_id)

    def _is_viewing(self, key: str) -> bool:
        if key == LAN_BROADCAST_ID:
            return self._current_is_broadcast
        if self._current_peer is None:
            return False
        return self._current_peer.id == key

    def _on_message_received(self, pid, pname, text, is_broadcast):
        if pid not in self._peers:
            self._peers[pid] = LanPeer(pid, pname, "", 0, time.time())
            self._seen_peer_ids.add(pid)
            self._rebuild_peer_list()
            self._refresh_input_state()
        else:
            self._peers[pid].last_seen = time.time()

        if is_broadcast:
            self._append_history(LAN_BROADCAST_ID, "peer", text,
                                 {"sender_name": pname})
            if self._is_viewing(LAN_BROADCAST_ID):
                self._append_line("peer", text, time.time(),
                                  sender_name=pname, peer_id=LAN_BROADCAST_ID)
        else:
            self._append_history(pid, "peer", text, {"sender_name": pname})
            if self._is_viewing(pid):
                self._append_line("peer", text, time.time(),
                                  sender_name=pname, peer_id=pid)

    def _on_file_offer(self, peer_id, peer_name, fname, fsize):
        msg = tr("lan_peer_send_file") + f"  {fname}  ({human_size(fsize)})"
        self._append_system(peer_id, msg)

    def _on_file_progress(self, peer_id, done, total):
        if total <= 0:
            return
        if self._current_peer and self._current_peer.id == peer_id:
            self.progress.setVisible(True)
            self.progress.setRange(0, 100)
            self.progress.setValue(int(done * 100 / total))

    def _on_file_received(self, peer_id, path_or_name, ok):
        self.progress.setVisible(False)
        if ok:
            msg = tr("lan_file_done", name=Path(path_or_name).name)
        else:
            msg = tr("lan_file_hash_bad")
        self._append_system(peer_id, msg)

        if SETTINGS.get("lan_notify_on_receive", True):
            peer_name = self._peers[peer_id].name if peer_id in self._peers else peer_id[:8]
            if ok:
                QMessageBox.information(
                    self, tr("msg_info"),
                    f"来自 {peer_name}：\n{Path(path_or_name).name}\n\n"
                    f"{LAN_FILES_DIR}")
            else:
                QMessageBox.warning(
                    self, tr("msg_warning"),
                    f"来自 {peer_name} 的文件未能接收/校验失败。")

    def _popup_emoji(self):
        panel = EmojiPanel(self)
        pos = self.btn_emoji.mapToGlobal(
            QPoint(0, -panel.sizeHint().height() - 4))
        panel.move(pos)
        panel.emoji_picked.connect(self._insert_emoji)
        panel.exec()

    def _insert_emoji(self, ch: str):
        self.edit_msg.insert(ch)
        self.edit_msg.setFocus()

    def _on_send_msg(self):
        text = self.edit_msg.text().strip()
        if not text:
            return
        self.edit_msg.clear()
        self._do_send_text(text)

    def _do_send_text(self, text: str):
        if not self._current_peer and not self._current_is_broadcast:
            return
        pwd_hash = _pwd_hash(SETTINGS.get("lan_password", ""))

        if self._current_is_broadcast:
            peers = [p for p in self._peers.values() if p.port > 0]
            if not peers:
                QMessageBox.information(self, tr("msg_info"),
                                        tr("lan_broadcast_no_peers"))
                return
            ok_count = 0
            for p in peers:
                if LanChatClient.send_message(p, self._identity, text,
                                              pwd_hash, is_broadcast=True):
                    ok_count += 1
            self._append_history(LAN_BROADCAST_ID, "me", text)
            self._append_line("me", text, time.time(), peer_id=LAN_BROADCAST_ID)
            if ok_count == 0:
                QMessageBox.warning(self, tr("msg_warning"),
                                    tr("lan_msg_failed"))
            return

        peer = self._current_peer
        if peer.port == 0:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("lan_port_unknown"))
            return
        self.btn_send.setEnabled(False)
        QApplication.processEvents()
        try:
            ok = LanChatClient.send_message(peer, self._identity, text,
                                            pwd_hash, is_broadcast=False)
        finally:
            self.btn_send.setEnabled(True)
        if ok:
            self._append_history(peer.id, "me", text)
            self._append_line("me", text, time.time(), peer_id=peer.id)
        else:
            QMessageBox.warning(self, tr("msg_warning"), tr("lan_msg_failed"))

    def _on_send_file(self):
        if not self._peers:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("lan_broadcast_no_peers"))
            return
        fps, _ = QFileDialog.getOpenFileNames(
            self, tr("lan_send_file"), str(Path.home()), "所有文件 (*)")
        if not fps:
            return
        for fp in fps:
            self._force_broadcast_file(Path(fp))

    def _force_broadcast_file(self, path: Path):
        try:
            size = path.stat().st_size
        except Exception:
            return

        peers = list(self._peers.values())
        if not peers:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("lan_broadcast_no_peers"))
            return

        default_port = int(SETTINGS.get("lan_port", 54322))
        for p in peers:
            if p.port <= 0 and p.ip:
                p.port = default_port

        pwd_hash = _pwd_hash(SETTINGS.get("lan_password", ""))
        want_hash = bool(SETTINGS.get("lan_verify_hash", True))
        offer = tr("lan_file_offer", name=path.name, size=human_size(size))

        self._append_history(
            LAN_BROADCAST_ID, "me",
            f"{offer}  → 强制发给 {len(peers)} 个在线用户",
            {"kind": "file"})
        if self._current_is_broadcast:
            self._append_line(
                "me",
                f"{offer}  → 强制发给 {len(peers)} 个在线用户",
                time.time(), kind="file", peer_id=LAN_BROADCAST_ID)

        total = len(peers)
        counter = {"done": 0, "ok": 0, "fail": 0}
        lock = threading.Lock()

        self._file_send_busy = True
        self._refresh_input_state()
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        def one_send(peer):
            ok, reason = LanChatClient.send_file(
                peer, self._identity, path, pwd_hash, want_hash,
                None, force=True)
            with lock:
                counter["done"] += 1
                if ok:
                    counter["ok"] += 1
                else:
                    counter["fail"] += 1
                cur = counter["done"]
            QTimer.singleShot(
                0, lambda c=cur, o=ok, r=reason, p=peer:
                self._on_broadcast_one(path, p, c, total, o, r))

        for p in peers:
            threading.Thread(target=one_send, args=(p,),
                             daemon=True).start()

        def watcher():
            while True:
                with lock:
                    if counter["done"] >= total:
                        break
                time.sleep(0.2)
            with lock:
                ok_n = counter["ok"]
                fail_n = counter["fail"]
            QTimer.singleShot(
                0, lambda: self._on_force_broadcast_done(
                    path, ok_n, fail_n, total))

        threading.Thread(target=watcher, daemon=True).start()

    def _on_force_broadcast_done(self, path, ok_n, fail_n, total):
        self._file_send_busy = False
        self._refresh_input_state()
        self.progress.setVisible(False)
        self._append_system(
            LAN_BROADCAST_ID,
            f"强制广播完成: {path.name}  成功 {ok_n}/{total}  失败 {fail_n}")

    def _on_broadcast_one(self, path, peer, done, total, ok, reason):
        pct = int(done * 100 / total)
        self.progress.setValue(pct)
        if ok:
            self._append_system(LAN_BROADCAST_ID,
                                tr("lan_broadcast_one_ok", peer=peer.name))
        else:
            self._append_system(
                LAN_BROADCAST_ID,
                tr("lan_broadcast_one_fail", peer=peer.name, reason=reason))

    def _on_clear_history(self):
        if self._current_is_broadcast:
            key = LAN_BROADCAST_ID
        elif self._current_peer:
            key = self._current_peer.id
        else:
            return
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("lan_clear_history") + "?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self._history[key] = []
        try:
            fp = self._history_file(key)
            if fp.exists():
                fp.unlink()
        except Exception:
            pass
        self.chat_view.clear()

    def _on_peer_menu(self, pos):
        it = self.list_peers.itemAt(pos)
        if not it:
            return
        data = it.data(Qt.UserRole)
        if not data:
            return
        kind, key = data

        menu = QMenu(self)
        a_open = menu.addAction(tr("lan_ctx_open"))
        menu.addSeparator()
        if kind == "broadcast":
            a_send_file = menu.addAction(tr("lan_ctx_send_file_all"))
        else:
            a_send_file = menu.addAction(tr("lan_ctx_send_file"))
        a_ping = menu.addAction(tr("lan_ctx_ping"))
        menu.addSeparator()
        a_clear = menu.addAction(tr("lan_ctx_clear"))

        act = menu.exec(self.list_peers.viewport().mapToGlobal(pos))

        if act == a_open:
            self.list_peers.setCurrentItem(it)
        elif act == a_ping:
            self.list_peers.setCurrentItem(it)
            self._do_send_text("ping")
        elif act == a_send_file:
            if not self._peers:
                QMessageBox.information(self, tr("msg_info"),
                                        tr("lan_broadcast_no_peers"))
                return
            fp, _ = QFileDialog.getOpenFileName(
                self, tr("lan_ctx_send_file_all") if kind == "broadcast"
                else (tr("lan_ctx_send_file")),
                str(Path.home()), "所有文件 (*)")
            if not fp:
                return
            self._force_broadcast_file(Path(fp))
        elif act == a_clear:
            target_key = LAN_BROADCAST_ID if kind == "broadcast" else key
            self._history[target_key] = []
            try:
                fp = LAN_HISTORY_DIR / f"{target_key}.jsonl"
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass
            if kind == "broadcast" and self._current_is_broadcast:
                self.chat_view.clear()
            elif (kind == "peer" and self._current_peer
                  and self._current_peer.id == key):
                self.chat_view.clear()


# ============================================================
# 30. 页面：局域网传输（内嵌 LocalSend Web）
# ============================================================
class WebTransferPage(QWidget):
    def __init__(self):
        super().__init__()
        self._view = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel(tr("webtransfer_title"))
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch(1)

        btn_reload = QPushButton(tr("webtransfer_reload"))
        btn_reload.clicked.connect(self._reload)
        top.addWidget(btn_reload)

        btn_ext = QPushButton(tr("webtransfer_open_external"))
        btn_ext.clicked.connect(self._open_external)
        top.addWidget(btn_ext)

        root.addLayout(top)

        hint = QLabel(tr("webtransfer_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        if HAS_WEBENGINE:
            self._setup_webengine()
        else:
            self._setup_fallback()

    def _setup_webengine(self):
        try:
            profile = QWebEngineProfile("mikan_emu_webtransfer", self)
            try:
                profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
                profile.setPersistentCookiesPolicy(
                    QWebEngineProfile.AllowPersistentCookies)
                cache_dir = WEBENGINE_DIR / "cache"
                storage_dir = WEBENGINE_DIR / "storage"
                cache_dir.mkdir(parents=True, exist_ok=True)
                storage_dir.mkdir(parents=True, exist_ok=True)
                try:
                    profile.setCachePath(str(cache_dir))
                    profile.setPersistentStoragePath(str(storage_dir))
                except Exception as e:
                    logger.warning(f"设置 WebEngine 缓存目录失败: {e}")
            except Exception as e:
                logger.debug(f"WebEngine profile 配置: {e}")

            try:
                profile.downloadRequested.connect(self._on_download_requested)
            except Exception as e:
                logger.debug(f"连接 profile.downloadRequested 失败: {e}")

            self._view = QWebEngineView()
            try:
                page = self._view.page()
                if page:
                    page.setProfile(profile)
                    try:
                        page.downloadRequested.connect(self._on_download_requested)
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                s = self._view.settings()
                s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                s.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
                s.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
                s.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            except Exception as e:
                logger.debug(f"WebEngine 设置失败: {e}")

            self._view.load(QUrl(tr("webtransfer_url")))
            self._stack.addWidget(self._view)
        except Exception as e:
            logger.exception(f"QtWebEngine 初始化失败: {e}")
            self._setup_fallback()

    def _setup_fallback(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        lbl = QLabel(tr("webtransfer_fallback"))
        lbl.setWordWrap(True)
        v.addWidget(lbl)

        v.addStretch(1)

        row = QHBoxLayout()

        if "PySide6.QtWebEngineWidgets" in OPTIONAL_MISSING:
            btn_install = QPushButton(tr("webtransfer_install_btn"))
            btn_install.setObjectName("PrimaryBtn")
            btn_install.clicked.connect(self._install_webengine)
            row.addWidget(btn_install)

        btn1 = QPushButton(tr("webtransfer_open_external"))
        btn1.clicked.connect(self._open_external)
        row.addWidget(btn1)

        btn2 = QPushButton(tr("webtransfer_native"))
        btn2.clicked.connect(lambda: webbrowser.open("https://localsend.org/"))
        row.addWidget(btn2)

        row.addStretch(1)
        v.addLayout(row)

        self._stack.addWidget(w)

    def _reload(self):
        if HAS_WEBENGINE and self._view is not None:
            try:
                self._view.load(QUrl(tr("webtransfer_url")))
            except Exception as e:
                logger.warning(f"重新加载失败: {e}")
        else:
            self._open_external()

    def _open_external(self):
        try:
            webbrowser.open(tr("webtransfer_url"))
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("open_failed", e=str(e)))

    def _install_webengine(self):
        reply = QMessageBox.question(
            self, tr("msg_confirm"), tr("webtransfer_install_confirm"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        ok = install_optional_package("PySide6-WebEngine", self)
        if ok:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("webtransfer_install_started"))
        else:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("webtransfer_install_failed"))

    def _on_download_requested(self, download):
        target_dir = None
        try:
            from PySide6.QtCore import QStandardPaths
            target_dir = QStandardPaths.writableLocation(
                QStandardPaths.DownloadLocation)
        except Exception:
            target_dir = None
        if not target_dir:
            target_dir = str(Path.home() / "Downloads")
        try:
            Path(target_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        fname = ""
        for method_name in ("downloadFileName", "suggestedFileName"):
            try:
                fn = getattr(download, method_name)()
                if fn:
                    fname = fn
                    break
            except Exception:
                continue
        if not fname:
            fname = "download"

        target_path = Path(target_dir) / fname
        if target_path.exists():
            stem, suf = target_path.stem, target_path.suffix
            idx = 2
            while target_path.exists():
                target_path = Path(target_dir) / f"{stem}_{idx}{suf}"
                idx += 1

        accepted = False
        try:
            download.setDownloadDirectory(target_dir)
            download.setDownloadFileName(target_path.name)
            download.accept()
            accepted = True
        except Exception:
            pass
        if not accepted:
            try:
                download.setPath(str(target_path))
                download.accept()
                accepted = True
            except Exception:
                pass
        if not accepted:
            logger.error("无法接受下载请求")
            try:
                download.cancel()
            except Exception:
                pass
            return
        logger.info(f"WebEngine 下载已接受: {target_path}")

        try:
            download.isFinishedChanged.connect(
                lambda d=download, p=target_path:
                    self._on_download_finished(d, p))
        except Exception:
            pass

    def _on_download_finished(self, download, target_path):
        try:
            if not download.isFinished():
                return
        except Exception:
            return
        state_ok = True
        try:
            state = download.state()
            if state in (3, 4):
                state_ok = False
        except Exception:
            pass
        if state_ok:
            logger.info(f"下载完成: {target_path}")
            QMessageBox.information(
                self, tr("msg_info"),
                f"文件已保存到:\n{target_path}")
        else:
            logger.warning(f"下载未完成: {target_path}")
            try:
                if Path(target_path).exists():
                    Path(target_path).unlink()
            except Exception:
                pass


# ============================================================
# 31. 页面：老游戏资料
# ============================================================
class RetroDocsPage(QWidget):
    def __init__(self):
        super().__init__()
        self._view = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel(tr("retro_docs_title"))
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch(1)

        btn_reload = QPushButton(tr("retro_docs_reload"))
        btn_reload.clicked.connect(self._reload)
        top.addWidget(btn_reload)

        btn_ext = QPushButton(tr("retro_docs_open_external"))
        btn_ext.clicked.connect(self._open_external)
        top.addWidget(btn_ext)

        root.addLayout(top)

        hint = QLabel(tr("retro_docs_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        if HAS_WEBENGINE:
            self._setup_webengine()
        else:
            self._setup_fallback()

    def _setup_webengine(self):
        try:
            profile = QWebEngineProfile("mikan_emu_retro_docs", self)
            try:
                cache_dir = WEBENGINE_DIR / "retro_cache"
                storage_dir = WEBENGINE_DIR / "retro_storage"
                cache_dir.mkdir(parents=True, exist_ok=True)
                storage_dir.mkdir(parents=True, exist_ok=True)
                try:
                    profile.setCachePath(str(cache_dir))
                    profile.setPersistentStoragePath(str(storage_dir))
                except Exception as e:
                    logger.debug(f"设置资料站缓存目录失败: {e}")
            except Exception:
                pass

            self._view = QWebEngineView()
            try:
                page = self._view.page()
                if page:
                    page.setProfile(profile)
            except Exception:
                pass

            try:
                s = self._view.settings()
                s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                s.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
            except Exception:
                pass

            url = tr("retro_docs_url") or RETRO_DOCS_URL
            self._view.load(QUrl(url))
            self._stack.addWidget(self._view)
        except Exception as e:
            logger.exception(f"资料站 WebEngine 初始化失败: {e}")
            self._setup_fallback()

    def _setup_fallback(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        lbl = QLabel(tr("retro_docs_fallback"))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        v.addStretch(1)

        row = QHBoxLayout()
        btn = QPushButton(tr("retro_docs_open_external"))
        btn.setObjectName("PrimaryBtn")
        btn.clicked.connect(self._open_external)
        row.addWidget(btn)
        row.addStretch(1)
        v.addLayout(row)

        self._stack.addWidget(w)

    def _reload(self):
        if HAS_WEBENGINE and self._view is not None:
            try:
                url = tr("retro_docs_url") or RETRO_DOCS_URL
                self._view.load(QUrl(url))
            except Exception as e:
                logger.warning(f"资料站重新加载失败: {e}")
        else:
            self._open_external()

    def _open_external(self):
        try:
            url = tr("retro_docs_url") or RETRO_DOCS_URL
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("open_failed", e=str(e)))

# ============================================================
# 32. 页面：设置
# ============================================================
class SettingsPage(QWidget):
    lang_changed = Signal(str)
    saves_changed = Signal()
    retroarch_changed = Signal()
    platforms_changed = Signal()
    lan_changed = Signal()
    theme_changed = Signal(str, str)
    plugins_changed = Signal()
    machine_tier_changed = Signal()
    background_changed = Signal()
    folders_changed = Signal()
    keymap_changed = Signal()     # ★ v1.8.0

    def __init__(self):
        super().__init__()
        self._mirror_test_worker = None
        self._api_test_worker = None
        self._save_rows = {}
        self._cheat_rows = {}
        self._build_ui()
        self._refresh()
        self.setAcceptDrops(True)

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

        # ---- 外观 ----
        box_theme = QGroupBox(tr("settings_theme"))
        ft = QVBoxLayout(box_theme)

        row_t = QHBoxLayout()
        row_t.addWidget(QLabel(tr("settings_theme")))
        self.combo_theme = QComboBox()
        self.combo_theme.addItem(tr("settings_theme_auto"), "auto")
        self.combo_theme.addItem(tr("settings_theme_light"), "light")
        self.combo_theme.addItem(tr("settings_theme_dark"), "dark")
        idx = self.combo_theme.findData(SETTINGS.get("theme", "auto"))
        if idx >= 0:
            self.combo_theme.setCurrentIndex(idx)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_changed)
        row_t.addWidget(self.combo_theme)
        row_t.addStretch(1)
        ft.addLayout(row_t)

        row_c = QHBoxLayout()
        row_c.addWidget(QLabel(tr("settings_accent")))
        self.btn_accent = QPushButton("选择…")
        self.btn_accent.clicked.connect(self._pick_accent)
        row_c.addWidget(self.btn_accent)
        self.btn_accent_reset = QPushButton("重置")
        self.btn_accent_reset.clicked.connect(self._reset_accent)
        row_c.addWidget(self.btn_accent_reset)
        row_c.addStretch(1)
        ft.addLayout(row_c)

        cur_accent = SETTINGS.get("accent_color", "")
        if cur_accent:
            self.btn_accent.setStyleSheet(
                f"background:{cur_accent};color:white;"
                f"border-radius:4px;padding:4px 12px;")
            self.btn_accent.setText(cur_accent)
        v.addWidget(box_theme)

        # ---- 全局背景 ----
        box_bg = QGroupBox(tr("settings_background"))
        fbg = QVBoxLayout(box_bg)
        h_bg = QLabel(tr("settings_background_hint"))
        h_bg.setObjectName("Hint")
        h_bg.setWordWrap(True)
        fbg.addWidget(h_bg)

        row_bg1 = QHBoxLayout()
        self.edit_bg_path = QLineEdit(SETTINGS.get("background_image", ""))
        self.edit_bg_path.setPlaceholderText("（未设置）")
        self.edit_bg_path.setReadOnly(True)
        row_bg1.addWidget(self.edit_bg_path, 1)
        b_pick = QPushButton(tr("settings_background_pick"))
        b_pick.setObjectName("PrimaryBtn")
        b_pick.clicked.connect(self._pick_background)
        row_bg1.addWidget(b_pick)
        b_clear = QPushButton(tr("settings_background_clear"))
        b_clear.clicked.connect(self._clear_background)
        row_bg1.addWidget(b_clear)
        fbg.addLayout(row_bg1)

        row_bg2 = QHBoxLayout()
        row_bg2.addWidget(QLabel(tr("settings_background_mode")))
        self.combo_bg_mode = QComboBox()
        self.combo_bg_mode.addItem(tr("settings_background_mode_cover"), "cover")
        self.combo_bg_mode.addItem(tr("settings_background_mode_contain"), "contain")
        self.combo_bg_mode.addItem(tr("settings_background_mode_stretch"), "stretch")
        self.combo_bg_mode.addItem(tr("settings_background_mode_tile"), "tile")
        idx = self.combo_bg_mode.findData(SETTINGS.get("background_mode", "cover"))
        if idx >= 0:
            self.combo_bg_mode.setCurrentIndex(idx)
        self.combo_bg_mode.currentIndexChanged.connect(self._on_bg_mode_changed)
        row_bg2.addWidget(self.combo_bg_mode)

        row_bg2.addWidget(QLabel(tr("settings_background_opacity")))
        self.spin_bg_opacity = QSpinBox()
        self.spin_bg_opacity.setRange(10, 100)
        self.spin_bg_opacity.setSuffix(" %")
        self.spin_bg_opacity.setValue(int(SETTINGS.get("background_opacity", 100)))
        self.spin_bg_opacity.valueChanged.connect(self._on_bg_opacity_changed)
        row_bg2.addWidget(self.spin_bg_opacity)

        row_bg2.addStretch(1)
        fbg.addLayout(row_bg2)
        v.addWidget(box_bg)

        # ---- 网络代理 ----
        box_proxy = QGroupBox("网络代理")
        fp = QVBoxLayout(box_proxy)

        row_p1 = QHBoxLayout()
        row_p1.addWidget(QLabel("模式"))
        self.combo_proxy_mode = QComboBox()
        self.combo_proxy_mode.addItem("不使用", "none")
        self.combo_proxy_mode.addItem("跟随系统", "system")
        self.combo_proxy_mode.addItem("HTTP", "http")
        self.combo_proxy_mode.addItem("HTTPS", "https")
        self.combo_proxy_mode.addItem("SOCKS5", "socks5")
        idx = self.combo_proxy_mode.findData(SETTINGS.get("proxy_mode", "none"))
        if idx >= 0:
            self.combo_proxy_mode.setCurrentIndex(idx)
        self.combo_proxy_mode.currentIndexChanged.connect(self._on_proxy_changed)
        row_p1.addWidget(self.combo_proxy_mode)
        row_p1.addStretch(1)
        fp.addLayout(row_p1)

        row_p2 = QHBoxLayout()
        row_p2.addWidget(QLabel("地址"))
        self.edit_proxy_host = QLineEdit(SETTINGS.get("proxy_host", ""))
        self.edit_proxy_host.setPlaceholderText("127.0.0.1")
        self.edit_proxy_host.editingFinished.connect(self._on_proxy_changed)
        row_p2.addWidget(self.edit_proxy_host, 1)
        row_p2.addWidget(QLabel("端口"))
        self.spin_proxy_port = QSpinBox()
        self.spin_proxy_port.setRange(0, 65535)
        self.spin_proxy_port.setValue(int(SETTINGS.get("proxy_port", 0)))
        self.spin_proxy_port.valueChanged.connect(self._on_proxy_changed)
        row_p2.addWidget(self.spin_proxy_port)
        fp.addLayout(row_p2)

        row_p3 = QHBoxLayout()
        row_p3.addWidget(QLabel("用户名"))
        self.edit_proxy_user = QLineEdit(SETTINGS.get("proxy_user", ""))
        self.edit_proxy_user.editingFinished.connect(self._on_proxy_changed)
        row_p3.addWidget(self.edit_proxy_user, 1)
        row_p3.addWidget(QLabel("密码"))
        self.edit_proxy_pwd = QLineEdit(SETTINGS.get("proxy_pwd", ""))
        self.edit_proxy_pwd.setEchoMode(QLineEdit.Password)
        self.edit_proxy_pwd.editingFinished.connect(self._on_proxy_changed)
        row_p3.addWidget(self.edit_proxy_pwd, 1)
        fp.addLayout(row_p3)

        row_p4 = QHBoxLayout()
        row_p4.addWidget(QLabel("直连域名"))
        self.edit_proxy_bypass = QLineEdit(SETTINGS.get("proxy_bypass", ""))
        self.edit_proxy_bypass.setPlaceholderText("逗号分隔，例如 github.com,localhost")
        self.edit_proxy_bypass.editingFinished.connect(self._on_proxy_changed)
        row_p4.addWidget(self.edit_proxy_bypass, 1)
        fp.addLayout(row_p4)

        row_p5 = QHBoxLayout()
        btn_proxy_test = QPushButton("测试代理")
        btn_proxy_test.setObjectName("PrimaryBtn")
        btn_proxy_test.clicked.connect(self._test_proxy)
        row_p5.addWidget(btn_proxy_test)
        self.lbl_proxy_test = QLabel("")
        self.lbl_proxy_test.setObjectName("Hint")
        row_p5.addWidget(self.lbl_proxy_test, 1)
        fp.addLayout(row_p5)
        v.addWidget(box_proxy)

        # ---- 语言 ----
        box1 = QGroupBox(tr("settings_lang"))
        f1 = QVBoxLayout(box1)
        row1 = QHBoxLayout()
        self.combo_lang = QComboBox()
        for code, pack in sorted(LANG_PACKS.items()):
            name = pack.get("_meta", {}).get("name", code)
            self.combo_lang.addItem(name, code)
        self.combo_lang.currentIndexChanged.connect(self._on_lang)
        row1.addWidget(self.combo_lang)
        row1.addStretch(1)
        f1.addLayout(row1)
        h1 = QLabel(tr("settings_lang_hint"))
        h1.setObjectName("Hint")
        f1.addWidget(h1)
        v.addWidget(box1)

        # ---- 系统优先级 ----
        box_prio = QGroupBox(tr("settings_priority"))
        fprio = QVBoxLayout(box_prio)
        h_prio = QLabel(tr("settings_priority_hint"))
        h_prio.setObjectName("Hint")
        h_prio.setWordWrap(True)
        fprio.addWidget(h_prio)

        self.prio_group = QButtonGroup(self)
        self.rb_prio_low = QRadioButton(tr("settings_priority_low"))
        self.rb_prio_normal = QRadioButton(tr("settings_priority_normal"))
        self.rb_prio_high = QRadioButton(tr("settings_priority_high"))
        self.rb_prio_realtime = QRadioButton(tr("settings_priority_realtime"))
        for rb, lv in (
            (self.rb_prio_low, "low"),
            (self.rb_prio_normal, "normal"),
            (self.rb_prio_high, "high"),
            (self.rb_prio_realtime, "realtime"),
        ):
            rb.setProperty("prio_level", lv)
            self.prio_group.addButton(rb)
            fprio.addWidget(rb)
        cur_prio = SETTINGS.get("process_priority", "normal")
        for rb in self.prio_group.buttons():
            if rb.property("prio_level") == cur_prio:
                rb.setChecked(True)
                break
        else:
            self.rb_prio_normal.setChecked(True)

        self.prio_group.buttonToggled.connect(self._on_priority_toggled)

        self.check_prio_children = QCheckBox(tr("settings_priority_children"))
        self.check_prio_children.setChecked(
            bool(SETTINGS.get("process_priority_children", True)))
        self.check_prio_children.toggled.connect(
            lambda val: self._set_setting("process_priority_children", val))
        fprio.addWidget(self.check_prio_children)

        self.check_prio_auto = QCheckBox(tr("settings_priority_auto"))
        self.check_prio_auto.setChecked(
            bool(SETTINGS.get("process_priority_auto", True)))
        self.check_prio_auto.toggled.connect(
            lambda val: self._set_setting("process_priority_auto", val))
        fprio.addWidget(self.check_prio_auto)
        v.addWidget(box_prio)

        # ---- 资源策略 ----
        box_res = QGroupBox(tr("machine_tier_title"))
        fres = QVBoxLayout(box_res)

        self.lbl_hw_info = QLabel()
        self.lbl_hw_info.setObjectName("Hint")
        self.lbl_hw_info.setWordWrap(True)
        fres.addWidget(self.lbl_hw_info)
        self._refresh_hw_info()

        row_mt = QHBoxLayout()
        row_mt.addWidget(QLabel(tr("machine_tier_label")))
        self.combo_tier = QComboBox()
        self.combo_tier.addItem(tr("machine_tier_low"), "low")
        self.combo_tier.addItem(tr("machine_tier_mid"), "mid")
        self.combo_tier.addItem(tr("machine_tier_high"), "high")
        idx = self.combo_tier.findData(SETTINGS.get("machine_tier", "mid"))
        if idx >= 0:
            self.combo_tier.setCurrentIndex(idx)
        self.combo_tier.currentIndexChanged.connect(self._on_tier_changed)
        row_mt.addWidget(self.combo_tier)

        self.check_tier_auto = QCheckBox(tr("machine_tier_auto"))
        self.check_tier_auto.setChecked(
            bool(SETTINGS.get("machine_tier_auto", True)))
        self.check_tier_auto.toggled.connect(self._on_tier_auto_toggled)
        row_mt.addWidget(self.check_tier_auto)
        row_mt.addStretch(1)
        fres.addLayout(row_mt)

        self.check_low_spec = QCheckBox(tr("machine_tier_low_spec"))
        self.check_low_spec.setChecked(bool(SETTINGS.get("low_spec_mode", False)))
        self.check_low_spec.toggled.connect(
            lambda val: self._set_setting("low_spec_mode", val))
        fres.addWidget(self.check_low_spec)

        self.check_res_enabled = QCheckBox(tr("resource_policy_enable"))
        self.check_res_enabled.setChecked(
            bool(SETTINGS.get("resource_policy_enabled", True)))
        self.check_res_enabled.toggled.connect(
            lambda val: self._set_setting("resource_policy_enabled", val))
        fres.addWidget(self.check_res_enabled)

        row_rc = QHBoxLayout()
        row_rc.addWidget(QLabel(tr("resource_cpu_cores")))
        self.spin_res_cores = QSpinBox()
        self.spin_res_cores.setRange(0, 64)
        self.spin_res_cores.setValue(int(SETTINGS.get("resource_cpu_cores", 0)))
        self.spin_res_cores.valueChanged.connect(
            lambda val: self._set_setting("resource_cpu_cores", int(val)))
        row_rc.addWidget(self.spin_res_cores)
        row_rc.addStretch(1)
        fres.addLayout(row_rc)

        row_rm = QHBoxLayout()
        row_rm.addWidget(QLabel(tr("resource_mem_mb")))
        self.spin_res_mem = QSpinBox()
        self.spin_res_mem.setRange(0, 65536)
        self.spin_res_mem.setSuffix(" MB")
        self.spin_res_mem.setValue(int(SETTINGS.get("resource_mem_mb", 0)))
        self.spin_res_mem.valueChanged.connect(
            lambda val: self._set_setting("resource_mem_mb", int(val)))
        row_rm.addWidget(self.spin_res_mem)
        row_rm.addStretch(1)
        fres.addLayout(row_rm)

        row_rs = QHBoxLayout()
        row_rs.addWidget(QLabel(tr("resource_safety_ratio")))
        self.spin_safety = QSpinBox()
        self.spin_safety.setRange(50, 100)
        self.spin_safety.setSuffix(" %")
        self.spin_safety.setValue(int(SETTINGS.get("resource_safety_ratio", 85)))
        self.spin_safety.valueChanged.connect(self._on_safety_changed)
        row_rs.addWidget(self.spin_safety)
        row_rs.addStretch(1)
        fres.addLayout(row_rs)

        self.check_force = QCheckBox(
            tr("resource_force_unlock",
               ratio=int(SETTINGS.get("resource_safety_ratio", 85))))
        self.check_force.setChecked(
            bool(SETTINGS.get("resource_force_unlock", False)))
        self.check_force.toggled.connect(self._on_force_toggled)
        fres.addWidget(self.check_force)
        v.addWidget(box_res)

        # ---- ★ v1.8.0：Job Object ----
        box_job = QGroupBox(tr("settings_job_object"))
        fjob = QVBoxLayout(box_job)
        h_job = QLabel(tr("settings_job_object_hint"))
        h_job.setObjectName("Hint")
        h_job.setWordWrap(True)
        fjob.addWidget(h_job)
        self.check_job_kill = QCheckBox(tr("settings_job_object_kill"))
        self.check_job_kill.setChecked(
            bool(SETTINGS.get("job_object_kill_on_close", True)))
        self.check_job_kill.toggled.connect(
            lambda val: self._set_setting("job_object_kill_on_close", val))
        fjob.addWidget(self.check_job_kill)
        v.addWidget(box_job)

        # ---- ★ v1.8.0：虚拟按键映射 ----
        box_keymap = QGroupBox(tr("settings_keymap"))
        fkm = QVBoxLayout(box_keymap)
        h_km = QLabel(tr("settings_keymap_hint"))
        h_km.setObjectName("Hint")
        h_km.setWordWrap(True)
        fkm.addWidget(h_km)

        if not HAS_KEYBOARD:
            warn = QLabel(tr("keymap_no_keyboard"))
            warn.setStyleSheet("color:#c42b1c;")
            warn.setWordWrap(True)
            fkm.addWidget(warn)

        self.check_keymap_enabled = QCheckBox(tr("settings_keymap_enable"))
        self.check_keymap_enabled.setChecked(
            bool(SETTINGS.get("keymap_enabled", False)))
        self.check_keymap_enabled.setEnabled(HAS_KEYBOARD)
        self.check_keymap_enabled.toggled.connect(self._on_keymap_enabled)
        fkm.addWidget(self.check_keymap_enabled)

        self.check_keymap_fg = QCheckBox(tr("settings_keymap_only_foreground"))
        self.check_keymap_fg.setChecked(
            bool(SETTINGS.get("keymap_only_foreground", True)))
        self.check_keymap_fg.toggled.connect(
            lambda val: self._set_setting("keymap_only_foreground", val))
        fkm.addWidget(self.check_keymap_fg)

        self.check_keymap_osd = QCheckBox(tr("settings_keymap_show_osd"))
        self.check_keymap_osd.setChecked(
            bool(SETTINGS.get("keymap_show_osd", True)))
        self.check_keymap_osd.toggled.connect(
            lambda val: self._set_setting("keymap_show_osd", val))
        fkm.addWidget(self.check_keymap_osd)

        row_km = QHBoxLayout()
        btn_edit_keymap = QPushButton("🎹 编辑按键映射…")
        btn_edit_keymap.setObjectName("PrimaryBtn")
        btn_edit_keymap.clicked.connect(self._open_keymap_editor)
        row_km.addWidget(btn_edit_keymap)
        row_km.addStretch(1)
        fkm.addLayout(row_km)
        v.addWidget(box_keymap)

        # ---- 拖拽识别 ----
        box_drag = QGroupBox(tr("settings_drag_drop"))
        fdrag = QVBoxLayout(box_drag)
        h_drag = QLabel(tr("settings_drag_drop_hint"))
        h_drag.setObjectName("Hint")
        h_drag.setWordWrap(True)
        fdrag.addWidget(h_drag)

        self.check_drag = QCheckBox(tr("settings_drag_drop_enable"))
        self.check_drag.setChecked(bool(SETTINGS.get("drag_drop_enabled", True)))
        self.check_drag.toggled.connect(
            lambda val: self._set_setting("drag_drop_enabled", val))
        fdrag.addWidget(self.check_drag)
        v.addWidget(box_drag)

        # ---- 局域网 ----
        box_lan = QGroupBox(tr("settings_lan"))
        fl = QVBoxLayout(box_lan)
        h_lan = QLabel(tr("settings_lan_hint"))
        h_lan.setObjectName("Hint")
        h_lan.setWordWrap(True)
        fl.addWidget(h_lan)

        self.check_lan = QCheckBox(tr("lan_enabled"))
        self.check_lan.setChecked(SETTINGS.get("lan_enabled", False))
        self.check_lan.toggled.connect(self._on_lan_enabled)
        fl.addWidget(self.check_lan)

        row_lan1 = QHBoxLayout()
        row_lan1.addWidget(QLabel(tr("lan_nickname_setting")))
        self.edit_lan_nick = QLineEdit(SETTINGS.get("lan_nickname", ""))
        self.edit_lan_nick.setPlaceholderText("mikan_xxxx")
        self.edit_lan_nick.editingFinished.connect(self._on_lan_nick_saved)
        row_lan1.addWidget(self.edit_lan_nick, 1)
        fl.addLayout(row_lan1)

        row_lan2 = QHBoxLayout()
        row_lan2.addWidget(QLabel(tr("lan_port_setting")))
        self.spin_lan_port = QSpinBox()
        self.spin_lan_port.setRange(1024, 65535)
        self.spin_lan_port.setValue(int(SETTINGS.get("lan_port", 54322)))
        self.spin_lan_port.valueChanged.connect(self._on_lan_port_changed)
        row_lan2.addWidget(self.spin_lan_port)
        row_lan2.addStretch(1)
        fl.addLayout(row_lan2)

        row_lan3 = QHBoxLayout()
        row_lan3.addWidget(QLabel(tr("lan_password_setting")))
        self.edit_lan_pwd = QLineEdit(SETTINGS.get("lan_password", ""))
        self.edit_lan_pwd.setEchoMode(QLineEdit.Password)
        self.edit_lan_pwd.editingFinished.connect(self._on_lan_pwd_changed)
        row_lan3.addWidget(self.edit_lan_pwd, 1)
        fl.addLayout(row_lan3)
        hint_pwd = QLabel(tr("lan_password_hint"))
        hint_pwd.setObjectName("Hint")
        hint_pwd.setWordWrap(True)
        fl.addWidget(hint_pwd)

        self.check_lan_history = QCheckBox(tr("lan_keep_history"))
        self.check_lan_history.setChecked(SETTINGS.get("lan_keep_history", True))
        self.check_lan_history.toggled.connect(
            lambda val: self._set_setting("lan_keep_history", val))
        fl.addWidget(self.check_lan_history)

        self.check_lan_files = QCheckBox(tr("lan_receive_files"))
        self.check_lan_files.setChecked(SETTINGS.get("lan_receive_files", True))
        self.check_lan_files.toggled.connect(
            lambda val: self._set_setting("lan_receive_files", val))
        fl.addWidget(self.check_lan_files)

        self.check_lan_hash = QCheckBox(tr("lan_verify_hash"))
        self.check_lan_hash.setChecked(SETTINGS.get("lan_verify_hash", True))
        self.check_lan_hash.toggled.connect(
            lambda val: self._set_setting("lan_verify_hash", val))
        fl.addWidget(self.check_lan_hash)

        self.check_lan_share = QCheckBox(tr("lan_share_enabled"))
        self.check_lan_share.setChecked(SETTINGS.get("lan_share_enabled", True))
        self.check_lan_share.toggled.connect(
            lambda val: self._set_setting("lan_share_enabled", val))
        fl.addWidget(self.check_lan_share)

        self.check_lan_notify = QCheckBox(tr("lan_notify_on_receive"))
        self.check_lan_notify.setChecked(SETTINGS.get("lan_notify_on_receive", True))
        self.check_lan_notify.toggled.connect(
            lambda val: self._set_setting("lan_notify_on_receive", val))
        fl.addWidget(self.check_lan_notify)

        row_lan4 = QHBoxLayout()
        row_lan4.addWidget(QLabel(tr("lan_max_file")))
        self.spin_lan_max = QSpinBox()
        self.spin_lan_max.setRange(1, 8192)
        self.spin_lan_max.setValue(int(SETTINGS.get("lan_max_file_mb", 512)))
        self.spin_lan_max.setSuffix(" MB")
        self.spin_lan_max.valueChanged.connect(
            lambda val: self._set_setting("lan_max_file_mb", val))
        row_lan4.addWidget(self.spin_lan_max)
        row_lan4.addStretch(1)
        fl.addLayout(row_lan4)

        row_lan5 = QHBoxLayout()
        btn_open_recv = QPushButton(tr("lan_open_received"))
        btn_open_recv.clicked.connect(lambda: os.startfile(str(LAN_FILES_DIR)))
        row_lan5.addWidget(btn_open_recv)
        btn_open_shared = QPushButton(tr("lan_open_shared"))
        btn_open_shared.clicked.connect(lambda: os.startfile(str(LAN_SHARED_DIR)))
        row_lan5.addWidget(btn_open_shared)
        btn_open_dl = QPushButton(tr("lan_open_shared_download"))
        btn_open_dl.clicked.connect(lambda: os.startfile(str(LAN_SHARED_DOWNLOAD_DIR)))
        row_lan5.addWidget(btn_open_dl)
        row_lan5.addStretch(1)
        fl.addLayout(row_lan5)
        v.addWidget(box_lan)

        # ---- 刮削 ----
        box_scrape = QGroupBox(tr("scrape_title"))
        fs = QVBoxLayout(box_scrape)
        row_s1 = QHBoxLayout()
        row_s1.addWidget(QLabel("SteamGridDB API Key"))
        self.edit_sgdb_key = QLineEdit(SETTINGS.get("steamgriddb_api_key", ""))
        self.edit_sgdb_key.setEchoMode(QLineEdit.Password)
        self.edit_sgdb_key.setPlaceholderText("留空 = 只用 Libretro")
        self.edit_sgdb_key.editingFinished.connect(
            lambda: self._set_setting("steamgriddb_api_key",
                                       self.edit_sgdb_key.text().strip()))
        row_s1.addWidget(self.edit_sgdb_key, 1)
        fs.addLayout(row_s1)

        row_s2 = QHBoxLayout()
        row_s2.addWidget(QLabel(tr("scrape_image_type")))
        self.combo_scrape_type = QComboBox()
        self.combo_scrape_type.addItem(tr("scrape_type_boxart"), "boxart")
        self.combo_scrape_type.addItem(tr("scrape_type_snap"), "snap")
        self.combo_scrape_type.addItem(tr("scrape_type_title"), "title")
        idx = self.combo_scrape_type.findData(SETTINGS.get("scrape_image_type", "boxart"))
        if idx >= 0:
            self.combo_scrape_type.setCurrentIndex(idx)
        self.combo_scrape_type.currentIndexChanged.connect(
            lambda: self._set_setting("scrape_image_type",
                                       self.combo_scrape_type.currentData()))
        row_s2.addWidget(self.combo_scrape_type)
        row_s2.addStretch(1)
        fs.addLayout(row_s2)

        self.check_scrape_ow = QCheckBox(tr("scrape_overwrite"))
        self.check_scrape_ow.setChecked(bool(SETTINGS.get("scrape_overwrite", False)))
        self.check_scrape_ow.toggled.connect(
            lambda val: self._set_setting("scrape_overwrite", val))
        fs.addWidget(self.check_scrape_ow)

        btn_open_covers = QPushButton("📂 打开封面目录")
        btn_open_covers.clicked.connect(lambda: os.startfile(str(COVER_DIR)))
        fs.addWidget(btn_open_covers)
        v.addWidget(box_scrape)

        # ---- 版本探测 ----
        box_ver = QGroupBox(tr("settings_version"))
        fver = QVBoxLayout(box_ver)
        h_ver = QLabel(tr("settings_version_hint"))
        h_ver.setObjectName("Hint")
        h_ver.setWordWrap(True)
        fver.addWidget(h_ver)
        self.check_ver_auto = QCheckBox(tr("settings_version_auto_detect"))
        self.check_ver_auto.setChecked(
            bool(SETTINGS.get("auto_detect_engine_version", True)))
        self.check_ver_auto.toggled.connect(
            lambda val: self._set_setting("auto_detect_engine_version", val))
        fver.addWidget(self.check_ver_auto)
        v.addWidget(box_ver)

        # ---- 日志与诊断 ----
        box_log = QGroupBox(tr("log_viewer_title"))
        flog = QVBoxLayout(box_log)

        row_log1 = QHBoxLayout()
        row_log1.addWidget(QLabel(tr("settings_log_level")))
        self.combo_log_level = QComboBox()
        for lv in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.combo_log_level.addItem(lv, lv)
        idx = self.combo_log_level.findData(SETTINGS.get("log_level", "INFO"))
        if idx >= 0:
            self.combo_log_level.setCurrentIndex(idx)
        self.combo_log_level.currentIndexChanged.connect(self._on_log_level_changed)
        row_log1.addWidget(self.combo_log_level)
        row_log1.addStretch(1)
        flog.addLayout(row_log1)

        row_log2 = QHBoxLayout()
        row_log2.addWidget(QLabel(tr("settings_log_keep_days")))
        self.spin_log_keep = QSpinBox()
        self.spin_log_keep.setRange(1, 365)
        self.spin_log_keep.setValue(int(SETTINGS.get("log_keep_days", 14)))
        self.spin_log_keep.valueChanged.connect(
            lambda val: self._set_setting("log_keep_days", int(val)))
        row_log2.addWidget(self.spin_log_keep)
        row_log2.addStretch(1)
        flog.addLayout(row_log2)

        self.check_crash_report = QCheckBox(tr("settings_crash_report_enabled"))
        self.check_crash_report.setChecked(
            bool(SETTINGS.get("crash_report_enabled", True)))
        self.check_crash_report.toggled.connect(
            lambda val: self._set_setting("crash_report_enabled", val))
        flog.addWidget(self.check_crash_report)

        row_log3 = QHBoxLayout()
        btn_open_logviewer = QPushButton(tr("settings_log_diag"))
        btn_open_logviewer.setObjectName("PrimaryBtn")
        btn_open_logviewer.clicked.connect(self._open_log_viewer)
        row_log3.addWidget(btn_open_logviewer)
        btn_open_logdir = QPushButton(tr("log_open_dir"))
        btn_open_logdir.clicked.connect(lambda: os.startfile(str(LOG_DIR)))
        row_log3.addWidget(btn_open_logdir)
        row_log3.addStretch(1)
        flog.addLayout(row_log3)
        v.addWidget(box_log)

        # ---- 插件 ----
        box_plug = QGroupBox(tr("plugins_title"))
        fplug = QVBoxLayout(box_plug)

        h_plug = QLabel(tr("plugins_hint"))
        h_plug.setObjectName("Hint")
        h_plug.setWordWrap(True)
        fplug.addWidget(h_plug)

        hint_import = QLabel(
            "💡 小贴士：直接把 .zip / .7z / .json / .py / 插件文件夹"
            "拖到设置页任意位置，即可一键导入。")
        hint_import.setObjectName("Hint")
        hint_import.setWordWrap(True)
        fplug.addWidget(hint_import)

        self.table_plug = QTableWidget(0, 4)
        self.table_plug.setHorizontalHeaderLabels([
            tr("plugins_col_enabled"), tr("plugins_col_id"),
            tr("plugins_col_name"), tr("plugins_col_version")])
        self.table_plug.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_plug.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_plug.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_plug.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_plug.verticalHeader().setVisible(False)
        self.table_plug.setMinimumHeight(200)
        fplug.addWidget(self.table_plug)

        row_plug = QHBoxLayout()
        b_open_plug = QPushButton(tr("plugins_open_dir"))
        b_open_plug.clicked.connect(lambda: os.startfile(str(PLUGINS_DIR)))
        row_plug.addWidget(b_open_plug)
        b_import_plug = QPushButton("📥 导入插件（zip / 7z / json / 文件夹）")
        b_import_plug.setToolTip(
            "支持一次性多选：\n"
            "  • .zip / .7z / .rar  插件压缩包\n"
            "  • plugin.json       单个元数据（自动生成骨架代码）\n"
            "  • main.py           单个脚本（自动生成 plugin.json）\n"
            "  • 文件夹            直接拖进窗口也行\n\n"
            "缺什么会自动补什么，导入后点「♻ 重启程序」生效。")
        b_import_plug.setObjectName("PrimaryBtn")
        b_import_plug.clicked.connect(self._import_plugin_zip)
        row_plug.addWidget(b_import_plug)
        b_reload_plug = QPushButton(tr("plugins_rescan"))
        b_reload_plug.clicked.connect(self._reload_plugin_table)
        row_plug.addWidget(b_reload_plug)
        row_plug.addStretch(1)
        b_restart = QPushButton(tr("plugins_restart"))
        b_restart.setObjectName("DangerBtn")
        b_restart.clicked.connect(self._restart_app)
        row_plug.addWidget(b_restart)
        fplug.addLayout(row_plug)
        v.addWidget(box_plug)

        # ---- 可选依赖 ----
        box_opt = QGroupBox("可选依赖")
        fopt = QVBoxLayout(box_opt)
        self.lbl_opt = QLabel()
        self.lbl_opt.setObjectName("Hint")
        self.lbl_opt.setWordWrap(True)
        self._refresh_optional_label()
        fopt.addWidget(self.lbl_opt)
        row_opt = QHBoxLayout()
        btn_check = QPushButton("刷新状态")
        btn_check.clicked.connect(self._refresh_optional_label)
        row_opt.addWidget(btn_check)
        btn_install_opt = QPushButton("安装缺失项")
        btn_install_opt.setObjectName("PrimaryBtn")
        btn_install_opt.clicked.connect(self._install_missing_optional)
        row_opt.addWidget(btn_install_opt)
        row_opt.addStretch(1)
        fopt.addLayout(row_opt)
        v.addWidget(box_opt)

        # ---- 配置包 ----
        box_pack = QGroupBox(tr("pack_title"))
        fpack = QVBoxLayout(box_pack)
        h_pack = QLabel(tr("pack_hint"))
        h_pack.setObjectName("Hint")
        h_pack.setWordWrap(True)
        fpack.addWidget(h_pack)

        row_pack = QHBoxLayout()
        b_exp = QPushButton(tr("pack_export"))
        b_exp.setObjectName("PrimaryBtn")
        b_exp.clicked.connect(self._export_pack)
        row_pack.addWidget(b_exp)
        b_imp = QPushButton(tr("pack_import"))
        b_imp.clicked.connect(self._import_pack)
        row_pack.addWidget(b_imp)
        row_pack.addStretch(1)
        fpack.addLayout(row_pack)
        v.addWidget(box_pack)

        # ---- 平台管理 ----
        box_plat = QGroupBox(tr("settings_platform_mgr"))
        fpl = QVBoxLayout(box_plat)
        hint_pl = QLabel(tr("settings_platform_mgr_hint"))
        hint_pl.setObjectName("Hint")
        hint_pl.setWordWrap(True)
        fpl.addWidget(hint_pl)

        self.table_plat = QTableWidget(0, 4)
        self.table_plat.setHorizontalHeaderLabels([
            tr("settings_platform_col_id"),
            tr("settings_platform_col_name"),
            tr("settings_platform_col_ext"),
            tr("settings_platform_col_op"),
        ])
        self.table_plat.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_plat.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_plat.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_plat.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_plat.verticalHeader().setVisible(False)
        self.table_plat.setMinimumHeight(240)
        self._reload_platform_table()
        fpl.addWidget(self.table_plat)

        row_pl = QHBoxLayout()
        b_add_pl = QPushButton(tr("settings_platform_add"))
        b_add_pl.clicked.connect(self._add_platform)
        row_pl.addWidget(b_add_pl)
        b_save_pl = QPushButton(tr("settings_platform_save"))
        b_save_pl.setObjectName("PrimaryBtn")
        b_save_pl.clicked.connect(self._save_platforms)
        row_pl.addWidget(b_save_pl)
        row_pl.addStretch(1)
        fpl.addLayout(row_pl)
        v.addWidget(box_plat)

        # ---- 多文件夹管理 ----
        box_folders = QGroupBox(tr("settings_folders"))
        ff = QVBoxLayout(box_folders)
        h_folders = QLabel(tr("settings_folders_hint"))
        h_folders.setObjectName("Hint")
        h_folders.setWordWrap(True)
        ff.addWidget(h_folders)

        self.table_folders = QTableWidget(0, 4)
        self.table_folders.setHorizontalHeaderLabels([
            tr("settings_folders_col_name"),
            tr("settings_folders_col_path"),
            tr("settings_folders_col_type"),
            tr("settings_folders_col_op"),
        ])
        self.table_folders.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_folders.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_folders.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_folders.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_folders.verticalHeader().setVisible(False)
        self.table_folders.setMinimumHeight(180)
        self._reload_folders_table()
        ff.addWidget(self.table_folders)

        row_folders = QHBoxLayout()
        b_add_folder = QPushButton(tr("settings_folders_add"))
        b_add_folder.clicked.connect(self._add_folder)
        row_folders.addWidget(b_add_folder)
        b_save_folders = QPushButton(tr("settings_folders_save"))
        b_save_folders.setObjectName("PrimaryBtn")
        b_save_folders.clicked.connect(self._save_folders)
        row_folders.addWidget(b_save_folders)
        row_folders.addStretch(1)
        ff.addLayout(row_folders)
        v.addWidget(box_folders)

        # ---- GitHub Token ----
        box_gh = QGroupBox(tr("settings_github_token"))
        fgh = QVBoxLayout(box_gh)
        h_gh = QLabel(tr("settings_github_token_hint"))
        h_gh.setObjectName("Hint")
        h_gh.setWordWrap(True)
        fgh.addWidget(h_gh)
        self.edit_gh_token = QLineEdit(SETTINGS.get("github_token", ""))
        self.edit_gh_token.setEchoMode(QLineEdit.Password)
        self.edit_gh_token.setPlaceholderText("ghp_xxx / github_pat_xxx")
        self.edit_gh_token.editingFinished.connect(
            lambda: self._set_setting("github_token",
                                       self.edit_gh_token.text().strip()))
        fgh.addWidget(self.edit_gh_token)
        v.addWidget(box_gh)

        # ---- 下载与镜像 ----
        box_dl = QGroupBox(tr("settings_download"))
        fdl = QVBoxLayout(box_dl)

        row_dl = QHBoxLayout()
        row_dl.addWidget(QLabel(tr("settings_threads")))
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(4, 16)
        self.spin_threads.setValue(SETTINGS.get("download_threads", 8))
        self.spin_threads.valueChanged.connect(self._on_threads_changed)
        row_dl.addWidget(self.spin_threads)

        self.check_dl_mirror = QCheckBox("下载默认走镜像")
        self.check_dl_mirror.setChecked(
            bool(SETTINGS.get("download_use_mirror", True)))
        self.check_dl_mirror.toggled.connect(
            lambda val: self._set_setting("download_use_mirror", val))
        row_dl.addWidget(self.check_dl_mirror)

        row_dl.addStretch(1)
        fdl.addLayout(row_dl)

        self.check_mirror_enabled = QCheckBox(tr("settings_mirrors_enable"))
        self.check_mirror_enabled.setChecked(MIRRORS_CONFIG.get("enabled", True))
        self.check_mirror_enabled.toggled.connect(self._on_mirror_enabled)
        fdl.addWidget(self.check_mirror_enabled)

        self.check_mirror_auto = QCheckBox(tr("settings_mirrors_auto"))
        self.check_mirror_auto.setChecked(MIRRORS_CONFIG.get("auto", True))
        self.check_mirror_auto.setToolTip(
            "开启后会先测速，再按延迟从低到高尝试镜像。\n"
            "关闭后按列表顺序尝试。")
        self.check_mirror_auto.toggled.connect(self._on_mirror_auto)
        fdl.addWidget(self.check_mirror_auto)

        row_region = QHBoxLayout()
        row_region.addWidget(QLabel(tr("settings_mirrors_region")))
        self.combo_mirror_region = QComboBox()
        self.combo_mirror_region.addItem(tr("settings_mirrors_region_auto"), "auto")
        self.combo_mirror_region.addItem(tr("settings_mirrors_region_cn"), "cn")
        self.combo_mirror_region.addItem(tr("settings_mirrors_region_overseas"), "overseas")
        self.combo_mirror_region.addItem(tr("settings_mirrors_region_direct"), "direct")
        idx = self.combo_mirror_region.findData(MIRRORS_CONFIG.get("region", "auto"))
        if idx >= 0:
            self.combo_mirror_region.setCurrentIndex(idx)
        self.combo_mirror_region.currentIndexChanged.connect(self._on_mirror_region)
        row_region.addWidget(self.combo_mirror_region)
        row_region.addStretch(1)
        fdl.addLayout(row_region)

        hint_mirror = QLabel(tr("settings_mirrors_hint"))
        hint_mirror.setObjectName("Hint")
        hint_mirror.setWordWrap(True)
        fdl.addWidget(hint_mirror)

        fdl.addWidget(QLabel(tr("settings_mirrors")))
        self.table_mirrors = QTableWidget(0, 4)
        self.table_mirrors.setHorizontalHeaderLabels([
            tr("settings_mirrors_col_enabled"),
            tr("settings_mirrors_col_url"),
            tr("settings_mirrors_col_region"),
            tr("settings_mirrors_col_weight"),
        ])
        self.table_mirrors.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_mirrors.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_mirrors.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_mirrors.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_mirrors.verticalHeader().setVisible(False)
        self.table_mirrors.setMinimumHeight(160)
        self._reload_mirrors_table()
        fdl.addWidget(self.table_mirrors)

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
        b_clear_probe = QPushButton(tr("settings_mirrors_clear_probe"))
        b_clear_probe.clicked.connect(self._clear_probe_cache)
        row_mir.addWidget(b_clear_probe)
        b_reset = QPushButton(tr("settings_mirrors_reset"))
        b_reset.clicked.connect(self._mirror_reset)
        row_mir.addWidget(b_reset)
        fdl.addLayout(row_mir)

        self.lbl_mirror_result = QLabel("")
        self.lbl_mirror_result.setObjectName("Hint")
        fdl.addWidget(self.lbl_mirror_result)

        fdl.addWidget(QLabel(tr("settings_api_mirrors")))
        hint_api = QLabel(tr("settings_api_mirrors_hint"))
        hint_api.setObjectName("Hint")
        fdl.addWidget(hint_api)
        self.list_api_mirrors = QListWidget()
        self.list_api_mirrors.setMinimumHeight(90)
        fdl.addWidget(self.list_api_mirrors)
        self._refresh_api_mirror_list()

        row_api = QHBoxLayout()
        b_add_api = QPushButton(tr("settings_mirrors_add"))
        b_add_api.clicked.connect(self._api_mirror_add)
        row_api.addWidget(b_add_api)
        b_del_api = QPushButton(tr("settings_mirrors_del"))
        b_del_api.clicked.connect(self._api_mirror_del)
        row_api.addWidget(b_del_api)
        row_api.addStretch(1)
        b_test_api = QPushButton("测试 API")
        b_test_api.clicked.connect(self._api_mirror_test)
        row_api.addWidget(b_test_api)
        fdl.addLayout(row_api)

        self.lbl_api_result = QLabel("")
        self.lbl_api_result.setObjectName("Hint")
        fdl.addWidget(self.lbl_api_result)
        v.addWidget(box_dl)

        # ---- RetroArch ----
        box_ra = QGroupBox(tr("settings_retroarch"))
        fra = QVBoxLayout(box_ra)
        h_ra = QLabel(tr("settings_retroarch_hint"))
        h_ra.setObjectName("Hint")
        h_ra.setWordWrap(True)
        fra.addWidget(h_ra)
        row_ra = QHBoxLayout()
        self.edit_ra_core = QLineEdit(SETTINGS.get("retroarch_core_dir", ""))
        row_ra.addWidget(self.edit_ra_core, 1)
        b_browse = QPushButton(tr("settings_retroarch_browse"))
        b_browse.clicked.connect(self._browse_ra_core)
        row_ra.addWidget(b_browse)
        b_detect = QPushButton(tr("settings_retroarch_detect"))
        b_detect.clicked.connect(self._detect_ra_core)
        row_ra.addWidget(b_detect)
        fra.addLayout(row_ra)
        v.addWidget(box_ra)

        # ---- 启动模板 ----
        box_prof = QGroupBox(tr("config_profile_group"))
        fprof = QVBoxLayout(box_prof)
        hint_prof = QLabel(tr("config_profile_hint"))
        hint_prof.setObjectName("Hint")
        hint_prof.setWordWrap(True)
        fprof.addWidget(hint_prof)

        self.table_prof = QTableWidget(0, 2)
        self.table_prof.setHorizontalHeaderLabels(["名称", "参数"])
        self.table_prof.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_prof.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_prof.verticalHeader().setVisible(False)
        self.table_prof.setMinimumHeight(140)
        self._reload_profiles_table()
        fprof.addWidget(self.table_prof)

        row_pf = QHBoxLayout()
        b_add_pf = QPushButton("添加模板")
        b_add_pf.clicked.connect(self._add_profile_row)
        row_pf.addWidget(b_add_pf)
        b_save_pf = QPushButton(tr("settings_saves_save"))
        b_save_pf.setObjectName("PrimaryBtn")
        b_save_pf.clicked.connect(self._save_profiles)
        row_pf.addWidget(b_save_pf)
        row_pf.addStretch(1)
        fprof.addLayout(row_pf)
        v.addWidget(box_prof)

        engines_json = load_engines_json()
        all_engines = set()
        for pcfg in engines_json.values():
            if not isinstance(pcfg, dict):
                continue
            for eng in pcfg.get("engines", {}):
                all_engines.add(eng)

        # ---- 金手指 ----
        box_ch = QGroupBox(tr("settings_cheats"))
        fch = QVBoxLayout(box_ch)
        h_ch = QLabel(tr("settings_cheats_hint"))
        h_ch.setObjectName("Hint")
        h_ch.setWordWrap(True)
        fch.addWidget(h_ch)
        for eng in sorted(all_engines):
            row = QHBoxLayout()
            label = QLabel(eng)
            label.setFixedWidth(120)
            row.addWidget(label)
            info = CHEAT_PATHS.get(eng, {})
            edit_dir = QLineEdit(info.get("dir", ""))
            edit_dir.setPlaceholderText("目录")
            row.addWidget(edit_dir, 2)
            edit_ext = QLineEdit(info.get("ext", ".cht"))
            edit_ext.setPlaceholderText("扩展名")
            edit_ext.setFixedWidth(80)
            row.addWidget(edit_ext)
            browse = QPushButton("…")
            browse.setFixedWidth(36)
            browse.clicked.connect(
                lambda _=False, e=edit_dir: self._browse_save_dir(e))
            row.addWidget(browse)
            fch.addLayout(row)
            self._cheat_rows[eng] = (edit_dir, edit_ext)
        b_save_ch = QPushButton(tr("settings_saves_save"))
        b_save_ch.setObjectName("PrimaryBtn")
        b_save_ch.clicked.connect(self._save_cheat_paths)
        fch.addWidget(b_save_ch)
        v.addWidget(box_ch)

        # ---- 托盘 + 性能 ----
        box_tray = QGroupBox(tr("settings_tray"))
        ftr = QVBoxLayout(box_tray)
        self.check_tray_min = QCheckBox(tr("settings_tray_minimize"))
        self.check_tray_min.setChecked(SETTINGS.get("tray_minimize_on_close", False))
        self.check_tray_min.toggled.connect(
            lambda val: self._set_setting("tray_minimize_on_close", val))
        ftr.addWidget(self.check_tray_min)
        self.check_tray_launch = QCheckBox(tr("settings_tray_minimize_launch"))
        self.check_tray_launch.setChecked(SETTINGS.get("tray_minimize_after_launch", False))
        self.check_tray_launch.toggled.connect(
            lambda val: self._set_setting("tray_minimize_after_launch", val))
        ftr.addWidget(self.check_tray_launch)

        self.check_perf = QCheckBox(tr("settings_perf_monitor"))
        self.check_perf.setChecked(SETTINGS.get("perf_monitor_on_launch", True))
        self.check_perf.toggled.connect(
            lambda val: self._set_setting("perf_monitor_on_launch", val))
        ftr.addWidget(self.check_perf)
        v.addWidget(box_tray)

        # ---- 工作区 ----
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

        # ---- 存档 ----
        box_sv = QGroupBox(tr("settings_saves"))
        fsv = QVBoxLayout(box_sv)
        hint_sv = QLabel(tr("settings_saves_hint"))
        hint_sv.setObjectName("Hint")
        hint_sv.setWordWrap(True)
        fsv.addWidget(hint_sv)

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
            browse.clicked.connect(
                lambda _=False, e=edit: self._browse_save_dir(e))
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

        # ---- 管理员 + 系统版本 + 鸣谢 ----
        box3 = QGroupBox(tr("settings_admin"))
        f3v = QVBoxLayout(box3)

        row_admin = QHBoxLayout()
        self.lbl_admin = QLabel()
        row_admin.addWidget(self.lbl_admin)

        self.lbl_winver = QLabel()
        self.lbl_winver.setObjectName("Hint")
        self._refresh_winver_label()
        row_admin.addWidget(self.lbl_winver)

        row_admin.addStretch(1)
        btn_admin = QPushButton(tr("settings_relaunch"))
        btn_admin.clicked.connect(self._relaunch_admin)
        row_admin.addWidget(btn_admin)
        btn_credits = QPushButton(tr("settings_credits_btn"))
        btn_credits.clicked.connect(self._show_credits)
        row_admin.addWidget(btn_credits)
        f3v.addLayout(row_admin)
        v.addWidget(box3)

        # ---- 目录 ----
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

        # ---- 项目地址 ----
        box_proj = QGroupBox(tr("settings_project"))
        fproj = QVBoxLayout(box_proj)
        h_proj = QLabel(tr("settings_project_hint"))
        h_proj.setObjectName("Hint")
        h_proj.setWordWrap(True)
        fproj.addWidget(h_proj)

        row_proj = QHBoxLayout()
        lbl_repo = QLabel(f"{tr('settings_project_repo')}: {APP_REPO}")
        lbl_repo.setObjectName("Hint")
        lbl_repo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row_proj.addWidget(lbl_repo, 1)

        btn_open_repo = QPushButton(tr("settings_project_open"))
        btn_open_repo.setObjectName("PrimaryBtn")
        btn_open_repo.clicked.connect(self._open_project_repo)
        row_proj.addWidget(btn_open_repo)
        fproj.addLayout(row_proj)
        v.addWidget(box_proj)

        v.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        QTimer.singleShot(0, self._reload_plugin_table)

    # ===== 镜像 =====
    def _reload_mirrors_table(self):
        self.table_mirrors.setRowCount(0)
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        for i, m in enumerate(mirrors):
            if not isinstance(m, dict):
                continue
            row = self.table_mirrors.rowCount()
            self.table_mirrors.insertRow(row)

            cb = QCheckBox()
            cb.setChecked(m.get("enabled", True))
            cb.toggled.connect(
                lambda checked, idx=i: self._on_mirror_row_enabled(idx, checked))
            self.table_mirrors.setCellWidget(row, 0, cb)

            url_item = QTableWidgetItem(m.get("url", ""))
            url_item.setFlags(url_item.flags() | Qt.ItemIsEditable)
            self.table_mirrors.setItem(row, 1, url_item)

            combo = QComboBox()
            combo.addItem(tr("settings_mirrors_region_cn"), "cn")
            combo.addItem(tr("settings_mirrors_region_overseas"), "overseas")
            combo.addItem(tr("settings_mirrors_region_direct"), "direct")
            idx = combo.findData(m.get("region", "cn"))
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentIndexChanged.connect(
                lambda _idx, r=i, c=combo: self._on_mirror_row_region(r, c.currentData()))
            self.table_mirrors.setCellWidget(row, 2, combo)

            spin = QSpinBox()
            spin.setRange(1, 100)
            spin.setValue(int(m.get("weight", 5)))
            spin.valueChanged.connect(
                lambda val, idx=i: self._on_mirror_row_weight(idx, int(val)))
            self.table_mirrors.setCellWidget(row, 3, spin)

        try:
            self.table_mirrors.itemChanged.disconnect()
        except Exception:
            pass
        self.table_mirrors.itemChanged.connect(self._on_mirror_url_edited)

    def _on_mirror_url_edited(self, item):
        if item.column() != 1:
            return
        row = item.row()
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        if 0 <= row < len(mirrors):
            mirrors[row]["url"] = item.text().strip()
            save_mirrors()

    def _on_mirror_row_enabled(self, idx: int, checked: bool):
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        if 0 <= idx < len(mirrors):
            mirrors[idx]["enabled"] = bool(checked)
            save_mirrors()

    def _on_mirror_row_region(self, idx: int, region: str):
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        if 0 <= idx < len(mirrors):
            mirrors[idx]["region"] = region or "cn"
            save_mirrors()

    def _on_mirror_row_weight(self, idx: int, weight: int):
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        if 0 <= idx < len(mirrors):
            mirrors[idx]["weight"] = int(weight)
            save_mirrors()

    def _on_mirror_auto(self, checked: bool):
        MIRRORS_CONFIG["auto"] = bool(checked)
        save_mirrors()

    def _on_mirror_region(self, _idx):
        MIRRORS_CONFIG["region"] = self.combo_mirror_region.currentData() or "auto"
        save_mirrors()

    def _clear_probe_cache(self):
        MirrorRouter.clear_probe_cache()
        QMessageBox.information(self, tr("msg_info"),
                                tr("settings_mirrors_probe_cleared"))

    def _refresh_api_mirror_list(self):
        self.list_api_mirrors.clear()
        for m in MIRRORS_CONFIG.get("api_mirrors", []):
            if isinstance(m, dict):
                prefix = m.get("url", "")
                region = m.get("region", "direct")
                enabled = m.get("enabled", True)
                label = (f"{prefix or '（直连）'}   [{region}]"
                         + ("" if enabled else "  (禁用)"))
            else:
                label = m if m else "（直连）"
            self.list_api_mirrors.addItem(label)

    def _on_mirror_enabled(self, checked):
        MIRRORS_CONFIG["enabled"] = bool(checked)
        save_mirrors()

    def _mirror_add(self):
        text, ok = QInputDialog.getText(
            self, tr("settings_mirrors_add"),
            "输入镜像前缀（末尾带 /）:", text="https://")
        if ok and text.strip():
            MIRRORS_CONFIG.setdefault("mirrors", []).append({
                "url": text.strip(), "enabled": True,
                "region": "cn", "weight": 5,
            })
            save_mirrors()
            self._reload_mirrors_table()

    def _mirror_del(self):
        row = self.table_mirrors.currentRow()
        if row < 0:
            return
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        if 0 <= row < len(mirrors):
            mirrors.pop(row)
            save_mirrors()
            self._reload_mirrors_table()

    def _mirror_move(self, delta):
        row = self.table_mirrors.currentRow()
        if row < 0:
            return
        mirrors = MIRRORS_CONFIG.get("mirrors", [])
        new_row = row + delta
        if not (0 <= new_row < len(mirrors)):
            return
        mirrors[row], mirrors[new_row] = mirrors[new_row], mirrors[row]
        save_mirrors()
        self._reload_mirrors_table()
        self.table_mirrors.selectRow(new_row)

    def _mirror_reset(self):
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     "恢复默认镜像列表？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        MIRRORS_CONFIG["mirrors"] = json.loads(
            json.dumps(DEFAULT_MIRRORS_JSON["mirrors"]))
        MIRRORS_CONFIG["api_mirrors"] = json.loads(
            json.dumps(DEFAULT_MIRRORS_JSON["api_mirrors"]))
        MIRRORS_CONFIG["enabled"] = True
        MIRRORS_CONFIG["auto"] = True
        MIRRORS_CONFIG["region"] = "auto"
        save_mirrors()
        self._reload_mirrors_table()
        self._refresh_api_mirror_list()
        self.check_mirror_enabled.setChecked(True)
        self.check_mirror_auto.setChecked(True)
        idx = self.combo_mirror_region.findData("auto")
        if idx >= 0:
            self.combo_mirror_region.setCurrentIndex(idx)

    def _mirror_test(self):
        if self._mirror_test_worker is not None and self._mirror_test_worker.isRunning():
            return
        test_url = "https://github.com/robots.txt"
        self.lbl_mirror_result.setText(tr("settings_mirrors_testing"))
        self._mirror_test_worker = MirrorTestWorker(test_url, use_api=False)
        self._mirror_test_worker.one.connect(self._on_mirror_test_one)
        self._mirror_test_worker.done.connect(self._on_mirror_test_done)
        self._mirror_test_worker.start()

    def _on_mirror_test_one(self, mirror: str, ok: bool, ms: float):
        status = f"✅ {ms:.0f} ms" if ok else "❌ 失败"
        self.lbl_mirror_result.setText(f"{mirror}    {status}")

    def _on_mirror_test_done(self, ok_count: int, fail_count: int):
        self.lbl_mirror_result.setText(
            tr("settings_mirrors_result", ok=ok_count, fail=fail_count))

    def _api_mirror_test(self):
        if self._api_test_worker is not None and self._api_test_worker.isRunning():
            return
        test_url = "https://api.github.com/rate_limit"
        self.lbl_api_result.setText(tr("settings_mirrors_testing"))
        self.list_api_mirrors.clear()
        self._api_test_worker = MirrorTestWorker(test_url, use_api=True)
        self._api_test_worker.one.connect(
            lambda m, ok, ms: self.list_api_mirrors.addItem(
                f"{m}    {'✅' if ok else '❌'} {ms:.0f}ms"))
        self._api_test_worker.done.connect(
            lambda ok, fail: self.lbl_api_result.setText(
                tr("settings_mirrors_result", ok=ok, fail=fail)))
        self._api_test_worker.start()

    def _api_mirror_add(self):
        text, ok = QInputDialog.getText(self, tr("settings_mirrors_add"),
                                        "输入 API 镜像前缀（末尾带 /）:",
                                        text="https://")
        if ok and text.strip():
            MIRRORS_CONFIG.setdefault("api_mirrors", []).append({
                "url": text.strip(), "enabled": True,
                "region": "cn", "weight": 5,
            })
            save_mirrors()
            self._refresh_api_mirror_list()

    def _api_mirror_del(self):
        row = self.list_api_mirrors.currentRow()
        if row < 0:
            return
        api_m = MIRRORS_CONFIG.get("api_mirrors", [])
        if 0 <= row < len(api_m):
            api_m.pop(row)
            save_mirrors()
            self._refresh_api_mirror_list()

    def _open_project_repo(self):
        try:
            webbrowser.open(APP_REPO)
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("open_failed", e=str(e)))

    # ===== 背景 =====
    def _pick_background(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("settings_background_pick"), str(BACKGROUND_DIR),
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)")
        if not fp:
            return
        src = Path(fp)
        try:
            dst = BACKGROUND_DIR / src.name
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
            SETTINGS["background_image"] = str(dst)
            save_settings()
            self.edit_bg_path.setText(str(dst))
            self.background_changed.emit()
            QMessageBox.information(self, tr("msg_info"),
                                    tr("settings_background_applied"))
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

    def _clear_background(self):
        SETTINGS["background_image"] = ""
        save_settings()
        self.edit_bg_path.setText("")
        self.background_changed.emit()
        QMessageBox.information(self, tr("msg_info"),
                                tr("settings_background_applied"))

    def _on_bg_mode_changed(self, _idx):
        SETTINGS["background_mode"] = self.combo_bg_mode.currentData() or "cover"
        save_settings()
        self.background_changed.emit()

    def _on_bg_opacity_changed(self, val):
        SETTINGS["background_opacity"] = int(val)
        save_settings()
        self.background_changed.emit()

    # ===== 文件夹 =====
    def _reload_folders_table(self):
        self.table_folders.setRowCount(0)
        for i, folder in enumerate(FOLDERS_CONFIG.get("folders", [])):
            row = self.table_folders.rowCount()
            self.table_folders.insertRow(row)
            self.table_folders.setItem(row, 0, QTableWidgetItem(folder.get("name", "")))
            self.table_folders.setItem(row, 1, QTableWidgetItem(folder.get("path", "")))

            combo = QComboBox()
            combo.addItem(tr("settings_folders_type_mixed"), "mixed")
            combo.addItem(tr("settings_folders_type_rom"), "rom")
            combo.addItem(tr("settings_folders_type_bios"), "bios")
            idx = combo.findData(folder.get("type", "mixed"))
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self.table_folders.setCellWidget(row, 2, combo)

            op_box = QWidget()
            op_layout = QHBoxLayout(op_box)
            op_layout.setContentsMargins(0, 0, 0, 0)
            op_layout.setSpacing(4)

            b_active = QPushButton(tr("settings_folders_active"))
            b_active.setFixedWidth(80)
            b_active.clicked.connect(
                lambda _=False, r=i: self._set_active_folder(r))
            op_layout.addWidget(b_active)

            b_del = QPushButton(tr("settings_folders_del"))
            b_del.setFixedWidth(60)
            b_del.clicked.connect(
                lambda _=False, r=row: self._del_folder_row(r))
            op_layout.addWidget(b_del)

            self.table_folders.setCellWidget(row, 3, op_box)

    def _set_active_folder(self, idx: int):
        if 0 <= idx < len(FOLDERS_CONFIG.get("folders", [])):
            FOLDERS_CONFIG["active_index"] = idx
            save_folders_config()
            self.folders_changed.emit()
            QMessageBox.information(
                self, tr("msg_info"),
                f"当前工作区已切换: {FOLDERS_CONFIG['folders'][idx].get('name')}")

    def _add_folder(self):
        row = self.table_folders.rowCount()
        self.table_folders.insertRow(row)
        self.table_folders.setItem(row, 0,
                                   QTableWidgetItem(tr("folder_new_workspace")))
        self.table_folders.setItem(row, 1, QTableWidgetItem(str(DATA_DIR)))

        combo = QComboBox()
        combo.addItem(tr("settings_folders_type_mixed"), "mixed")
        combo.addItem(tr("settings_folders_type_rom"), "rom")
        combo.addItem(tr("settings_folders_type_bios"), "bios")
        self.table_folders.setCellWidget(row, 2, combo)

        b_del = QPushButton(tr("settings_folders_del"))
        b_del.setFixedWidth(60)
        b_del.clicked.connect(lambda _=False, r=row: self._del_folder_row(r))
        self.table_folders.setCellWidget(row, 3, b_del)

    def _del_folder_row(self, row: int):
        name_item = self.table_folders.item(row, 0)
        name = name_item.text() if name_item else "?"
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("settings_folders_del_confirm", name=name),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.table_folders.removeRow(row)
        self._reload_folders_table()

    def _save_folders(self):
        folders = []
        for row in range(self.table_folders.rowCount()):
            name_item = self.table_folders.item(row, 0)
            path_item = self.table_folders.item(row, 1)
            if not name_item or not path_item:
                continue
            name = name_item.text().strip()
            path = path_item.text().strip()
            if not name or not path:
                continue
            combo = self.table_folders.cellWidget(row, 2)
            ftype = combo.currentData() if combo else "mixed"
            folders.append({"name": name, "path": path, "type": ftype})

        if not folders:
            QMessageBox.warning(self, tr("msg_warning"), "至少保留一个工作区")
            return

        FOLDERS_CONFIG["folders"] = folders
        if FOLDERS_CONFIG.get("active_index", 0) >= len(folders):
            FOLDERS_CONFIG["active_index"] = 0
        save_folders_config()
        self._reload_folders_table()
        self._reload_workspace_combo()
        self.folders_changed.emit()
        QMessageBox.information(self, tr("msg_info"), tr("settings_folders_saved"))

    def _reload_workspace_combo(self):
        self.combo_workspace.blockSignals(True)
        self.combo_workspace.clear()
        for i, folder in enumerate(FOLDERS_CONFIG.get("folders", [])):
            self.combo_workspace.addItem(
                f"{folder.get('name')}  [{folder.get('path')}]", i)
        self.combo_workspace.setCurrentIndex(FOLDERS_CONFIG.get("active_index", 0))
        self.combo_workspace.blockSignals(False)

    # ===== 主题 =====
    def _on_theme_changed(self, _i):
        mode = self.combo_theme.currentData()
        SETTINGS["theme"] = mode
        save_settings()
        self.theme_changed.emit(mode, SETTINGS.get("accent_color", ""))

    def _pick_accent(self):
        c = QColorDialog.getColor(
            QColor(SETTINGS.get("accent_color") or "#0067c0"),
            self, tr("settings_accent"))
        if not c.isValid():
            return
        SETTINGS["accent_color"] = c.name()
        save_settings()
        self.btn_accent.setStyleSheet(
            f"background:{c.name()};color:white;"
            f"border-radius:4px;padding:4px 12px;")
        self.btn_accent.setText(c.name())
        self.theme_changed.emit(SETTINGS.get("theme", "auto"), c.name())

    def _reset_accent(self):
        SETTINGS["accent_color"] = ""
        save_settings()
        self.btn_accent.setStyleSheet("")
        self.btn_accent.setText("选择…")
        self.theme_changed.emit(SETTINGS.get("theme", "auto"), "")

    # ===== 代理 =====
    def _on_proxy_changed(self, *_):
        SETTINGS["proxy_mode"] = self.combo_proxy_mode.currentData()
        SETTINGS["proxy_host"] = self.edit_proxy_host.text().strip()
        SETTINGS["proxy_port"] = int(self.spin_proxy_port.value())
        SETTINGS["proxy_user"] = self.edit_proxy_user.text().strip()
        SETTINGS["proxy_pwd"] = self.edit_proxy_pwd.text()
        SETTINGS["proxy_bypass"] = self.edit_proxy_bypass.text().strip()
        save_settings()
        try:
            HttpSession.get().refresh()
        except Exception as e:
            logger.debug(f"刷新代理失败: {e}")

    def _test_proxy(self):
        self.lbl_proxy_test.setText("测试中…")
        QApplication.processEvents()
        ok, msg = HttpSession.get().test()
        if ok:
            self.lbl_proxy_test.setText(f"✅ {msg}")
            self.lbl_proxy_test.setStyleSheet("color:#0f7b0f;")
        else:
            self.lbl_proxy_test.setText(f"❌ {msg}")
            self.lbl_proxy_test.setStyleSheet("color:#c42b1c;")

    # ===== 优先级 =====
    def _on_priority_toggled(self, btn, checked):
        if not checked:
            return
        level = btn.property("prio_level")
        if level == "realtime":
            reply = QMessageBox.question(
                self, tr("msg_confirm"),
                tr("settings_priority_realtime_warn"),
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                cur = SETTINGS.get("process_priority", "normal")
                for rb in self.prio_group.buttons():
                    if rb.property("prio_level") == cur:
                        rb.setChecked(True)
                        break
                return
        self._set_setting("process_priority", level)

    # ===== 机器档次 =====
    def _refresh_hw_info(self):
        try:
            hw = probe_hardware(force=True)
            cpu_p = hw["cpu_physical"]
            cpu_l = hw["cpu_logical"]
            mem_gb = hw["mem_total_mb"] / 1024.0
            cpu_limit = hw["cpu_limit"]
            mem_limit = hw["mem_limit_mb"]
            self.lbl_hw_info.setText(tr(
                "machine_tier_detected",
                cpu_p=cpu_p, cpu_l=cpu_l, mem_gb=f"{mem_gb:.1f}",
                cpu_limit=cpu_limit, mem_limit=mem_limit))
        except Exception as e:
            self.lbl_hw_info.setText(f"硬件探测失败: {e}")

    def _on_tier_changed(self, _idx):
        tier = self.combo_tier.currentData() or "mid"
        SETTINGS["machine_tier"] = tier
        save_settings()
        self.machine_tier_changed.emit()

    def _on_tier_auto_toggled(self, checked):
        SETTINGS["machine_tier_auto"] = bool(checked)
        save_settings()
        if checked:
            refresh_machine_tier()
            idx = self.combo_tier.findData(SETTINGS.get("machine_tier", "mid"))
            if idx >= 0:
                self.combo_tier.blockSignals(True)
                self.combo_tier.setCurrentIndex(idx)
                self.combo_tier.blockSignals(False)
            self.combo_tier.setEnabled(False)
        else:
            self.combo_tier.setEnabled(True)

    def _on_safety_changed(self, val):
        SETTINGS["resource_safety_ratio"] = int(val)
        save_settings()
        global _HW_CACHE
        _HW_CACHE = {}
        self._refresh_hw_info()
        self.check_force.setText(tr("resource_force_unlock", ratio=int(val)))

    def _on_force_toggled(self, checked):
        if checked:
            ratio = int(SETTINGS.get("resource_safety_ratio", 85))
            reply = QMessageBox.question(
                self, tr("msg_confirm"),
                tr("resource_force_unlock_warn", ratio=ratio),
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                self.check_force.blockSignals(True)
                self.check_force.setChecked(False)
                self.check_force.blockSignals(False)
                return
        SETTINGS["resource_force_unlock"] = bool(checked)
        save_settings()

    # ===== 日志 =====
    def _on_log_level_changed(self, _idx):
        level = self.combo_log_level.currentData() or "INFO"
        SETTINGS["log_level"] = level
        save_settings()
        try:
            setup_logging()
            logger.info(f"日志级别已切换为 {level}")
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"), str(e))

    def _open_log_viewer(self):
        LogViewerDialog(self).exec()

    def _refresh_winver_label(self):
        try:
            build = get_windows_build()
            if build == 0:
                self.lbl_winver.setText("系统: 非 Windows")
                return
            if build >= 22000:
                name = "Win11"
            elif build >= 17763:
                name = "Win10 1809+"
            else:
                name = "⚠ 版本过低"
            tier = SETTINGS.get("machine_tier", "?")
            self.lbl_winver.setText(
                tr("win_version_label", name=name, build=build, tier=tier))
        except Exception:
            self.lbl_winver.setText("")

    # ===== 可选依赖 =====
    def _refresh_optional_label(self):
        lines = []
        for mod, pkg in OPTIONAL.items():
            try:
                importlib.import_module(mod)
                lines.append(f"✅ {pkg}  已安装")
            except ImportError:
                lines.append(
                    f"❌ {pkg}  未安装（局域网传输 / 资料站 / 按键映射可能受限）")
        self.lbl_opt.setText("\n".join(lines))

    def _install_missing_optional(self):
        missing = []
        for mod, pkg in OPTIONAL.items():
            try:
                importlib.import_module(mod)
            except ImportError:
                missing.append(pkg)
        if not missing:
            QMessageBox.information(self, tr("msg_info"), "所有可选依赖已安装。")
            return
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            f"将安装以下包：\n" + "\n".join(missing) +
            "\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for pkg in missing:
            install_optional_package(pkg, self)
        QMessageBox.information(
            self, tr("msg_info"),
            "已在新窗口开始安装。\n"
            "安装完成后请关闭并重新启动 mikan_emu。")

    # ===== 配置包 =====
    def _export_pack(self):
        dlg = ConfigPackDialog("export", self)
        dlg.exec()

    def _import_pack(self):
        dlg = ConfigPackDialog("import", self)
        if dlg.exec() == QDialog.Accepted:
            self.platforms_changed.emit()
            self.saves_changed.emit()

    # ===== 启动模板 =====
    def _reload_profiles_table(self):
        self.table_prof.setRowCount(0)
        profiles = SETTINGS.get("launch_profiles", {}) or {}
        for name, args in profiles.items():
            r = self.table_prof.rowCount()
            self.table_prof.insertRow(r)
            self.table_prof.setItem(r, 0, QTableWidgetItem(name))
            self.table_prof.setItem(r, 1, QTableWidgetItem(args))

    def _add_profile_row(self):
        r = self.table_prof.rowCount()
        self.table_prof.insertRow(r)
        self.table_prof.setItem(r, 0, QTableWidgetItem("新模板"))
        self.table_prof.setItem(r, 1, QTableWidgetItem(""))

    def _save_profiles(self):
        profiles = {}
        for r in range(self.table_prof.rowCount()):
            n = self.table_prof.item(r, 0)
            a = self.table_prof.item(r, 1)
            if not n or not n.text().strip():
                continue
            profiles[n.text().strip()] = (a.text() if a else "").strip()
        SETTINGS["launch_profiles"] = profiles
        save_settings()
        QMessageBox.information(self, tr("msg_info"), "启动模板已保存")

    # ===== 局域网 =====
    def _on_lan_enabled(self, checked: bool):
        self._set_setting("lan_enabled", checked)
        self.lan_changed.emit()

    def _on_lan_nick_saved(self):
        name = self.edit_lan_nick.text().strip()
        if name:
            self._set_setting("lan_nickname", name)

    def _on_lan_port_changed(self, val):
        self._set_setting("lan_port", int(val))

    def _on_lan_pwd_changed(self):
        self._set_setting("lan_password", self.edit_lan_pwd.text())

    # ===== 按键映射 =====
    def _on_keymap_enabled(self, checked: bool):
        if checked and not HAS_KEYBOARD:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("keymap_no_keyboard"))
            self.check_keymap_enabled.setChecked(False)
            return
        self._set_setting("keymap_enabled", checked)
        self.keymap_changed.emit()

    def _open_keymap_editor(self):
        if not HAS_KEYBOARD:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("keymap_no_keyboard"))
            return
        dlg = KeyMapDialog(self)
        dlg.exec()
        self.keymap_changed.emit()

    def _show_credits(self):
        CreditsDialog(self).exec()

    # ===== 平台 =====
    def _reload_platform_table(self):
        self.table_plat.setRowCount(0)
        engines_json = load_engines_json()
        for p, pcfg in engines_json.items():
            if p.startswith("_"):
                continue
            row = self.table_plat.rowCount()
            self.table_plat.insertRow(row)
            self.table_plat.setItem(row, 0, QTableWidgetItem(p))
            self.table_plat.setItem(row, 1,
                                    QTableWidgetItem(pcfg.get("platform_name", p)))
            self.table_plat.setItem(row, 2, QTableWidgetItem(
                ", ".join(pcfg.get("rom_extensions", []))))
            btn_del = QPushButton(tr("settings_platform_del"))
            btn_del.setFixedWidth(70)
            btn_del.clicked.connect(lambda _=False, pp=p: self._del_platform(pp))
            self.table_plat.setCellWidget(row, 3, btn_del)

    def _add_platform(self):
        row = self.table_plat.rowCount()
        self.table_plat.insertRow(row)
        self.table_plat.setItem(row, 0, QTableWidgetItem(""))
        self.table_plat.setItem(row, 1, QTableWidgetItem(""))
        self.table_plat.setItem(row, 2, QTableWidgetItem(""))
        btn_del = QPushButton(tr("settings_platform_del"))
        btn_del.setFixedWidth(70)
        btn_del.clicked.connect(
            lambda _=False, r=row: self.table_plat.removeRow(r))
        self.table_plat.setCellWidget(row, 3, btn_del)

    def _del_platform(self, platform_id: str):
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("settings_platform_del_confirm", pid=platform_id),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        engines_json = load_engines_json()
        engines_json.pop(platform_id, None)
        save_engines_json(engines_json)
        self._reload_platform_table()
        self.platforms_changed.emit()

    def _save_platforms(self):
        engines_json = load_engines_json()
        for row in range(self.table_plat.rowCount()):
            pid_item = self.table_plat.item(row, 0)
            name_item = self.table_plat.item(row, 1)
            ext_item = self.table_plat.item(row, 2)
            if pid_item is None or not pid_item.text().strip():
                continue
            pid = pid_item.text().strip()
            name = (name_item.text().strip() if name_item else pid)
            exts = []
            if ext_item:
                for e in ext_item.text().split(","):
                    e = e.strip()
                    if not e:
                        continue
                    if not e.startswith("."):
                        e = "." + e
                    exts.append(e)
            if pid not in engines_json:
                engines_json[pid] = {"engines": {}}
            engines_json[pid]["platform_name"] = name
            engines_json[pid]["rom_extensions"] = exts
        save_engines_json(engines_json)
        QMessageBox.information(self, tr("msg_info"),
                                tr("settings_platform_saved"))
        self._reload_platform_table()
        self.platforms_changed.emit()

    # ===== RetroArch =====
    def _browse_ra_core(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("settings_retroarch"), str(DATA_DIR))
        if d:
            self.edit_ra_core.setText(d)
            self._set_setting("retroarch_core_dir", d)

    def _detect_ra_core(self):
        d = autodetect_retroarch_core_dir()
        if d:
            self.edit_ra_core.setText(d)
            self._set_setting("retroarch_core_dir", d)
            QMessageBox.information(self, tr("msg_info"), f"找到: {d}")
        else:
            QMessageBox.warning(self, tr("msg_warning"),
                                "未找到 RetroArch 核心目录")

    def _refresh(self):
        idx = self.combo_lang.findData(CURRENT_LANG)
        if idx >= 0:
            self.combo_lang.blockSignals(True)
            self.combo_lang.setCurrentIndex(idx)
            self.combo_lang.blockSignals(False)
        self.lbl_admin.setText("已获得管理员权限" if is_admin() else "普通用户")
        self.edit_lan_nick.setText(
            SETTINGS.get("lan_nickname", "") or LanIdentity().name)
        self.edit_lan_pwd.setText(SETTINGS.get("lan_password", ""))
        if SETTINGS.get("machine_tier_auto", True):
            self.combo_tier.setEnabled(False)
        else:
            self.combo_tier.setEnabled(True)
        self._refresh_hw_info()
        self._refresh_winver_label()

    def _set_setting(self, key, value):
        SETTINGS[key] = value
        save_settings()

    def _on_lang(self, index):
        global CURRENT_LANG
        lang = self.combo_lang.itemData(index)
        if not lang or lang == CURRENT_LANG:
            return
        CURRENT_LANG = lang
        save_lang(lang)
        self.lang_changed.emit(lang)

    def _on_threads_changed(self, v):
        self._set_setting("download_threads", v)

    def _on_workspace(self, index):
        idx = self.combo_workspace.itemData(index)
        if idx is None:
            return
        FOLDERS_CONFIG["active_index"] = idx
        save_folders_config()
        self.folders_changed.emit()

    def _browse_save_dir(self, edit: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "选择目录", str(DATA_DIR))
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

    def _save_cheat_paths(self):
        global CHEAT_PATHS
        for eng, (edit_dir, edit_ext) in self._cheat_rows.items():
            d = edit_dir.text().strip()
            e = edit_ext.text().strip() or ".cht"
            if d:
                CHEAT_PATHS[eng] = {"dir": d, "ext": e}
            else:
                CHEAT_PATHS.pop(eng, None)
        save_cheat_paths()
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
            QMessageBox.information(self, tr("msg_info"), tr("save_no_backup"))
            return
        items = [b.name for b in backups]
        choice, ok = QInputDialog.getItem(self, tr("save_restore_title"),
                                          tr("save_select_backup"),
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

    # ===== 插件 =====
    def _reload_plugin_table(self):
        pm = getattr(self.window(), "_plugin_manager", None)
        if pm is None:
            return
        infos = pm.scan_all()
        self.table_plug.setRowCount(len(infos))
        for i, info in enumerate(infos):
            cb = QCheckBox()
            cb.setChecked(info.get("enabled", True))
            cb.toggled.connect(
                lambda checked, pid=info["id"]:
                    self._toggle_plugin(pid, checked))
            self.table_plug.setCellWidget(i, 0, cb)

            self.table_plug.setItem(i, 1, QTableWidgetItem(info["id"]))

            meta = info.get("meta", {})
            name = meta.get("name", info["id"])
            if info.get("error"):
                name += f"   ⚠ {info['error']}"
            self.table_plug.setItem(i, 2, QTableWidgetItem(name))
            self.table_plug.setItem(
                i, 3, QTableWidgetItem(str(meta.get("version", "?"))))

    def _toggle_plugin(self, pid: str, enabled: bool):
        pm = getattr(self.window(), "_plugin_manager", None)
        if pm is None:
            return
        pm.set_enabled(pid, enabled)
        QMessageBox.information(
            self, tr("msg_info"),
            f"插件 {pid} 已{'启用' if enabled else '禁用'}。\n"
            f"请点「重启程序」使其生效。")

    def _import_plugin_zip(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("plugins_import_title"), str(Path.home()),
            "插件包 (*.zip *.7z *.rar *.json *.py);;所有文件 (*)")
        if not files:
            reply = QMessageBox.question(
                self, tr("plugins_import_title"),
                "没有选择文件。是否改为选择一个插件文件夹？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            d = QFileDialog.getExistingDirectory(
                self, tr("plugins_import_title"), str(Path.home()))
            if not d:
                return
            files = [d]
        self._do_batch_import(files, source="文件")

    def _do_batch_import(self, paths, source="文件"):
        ok_list = []
        fail_list = []
        filled_all = []

        for fp in paths:
            src = Path(fp)
            try:
                ok, pid, filled, msg = _import_plugin_any(src, overwrite=True)
            except Exception as e:
                logger.exception(f"导入插件失败: {src}")
                ok, pid, filled, msg = False, "", [], str(e)

            if ok:
                ok_list.append(pid)
                if filled:
                    filled_all.append((pid, filled))
                logger.info(f"插件已导入: {pid}  自动补全: {filled}")
            else:
                fail_list.append((src.name, msg or "未知错误"))

        lines = []
        if ok_list:
            lines.append(f"✅ 成功导入 {len(ok_list)} 个插件：")
            for pid in ok_list:
                lines.append(f"   • {pid}")
        if filled_all:
            lines.append("")
            lines.append("🔧 自动补全的字段：")
            for pid, keys in filled_all:
                lines.append(f"   • {pid}: {', '.join(keys)}")
        if fail_list:
            lines.append("")
            lines.append(f"❌ 失败 {len(fail_list)} 个：")
            for name, msg in fail_list:
                lines.append(f"   • {name}: {msg}")
        lines.append("")
        lines.append("点「♻ 重启程序」后生效。")

        title = f"{source}导入"
        if ok_list and not fail_list:
            QMessageBox.information(self, title, "\n".join(lines))
        elif ok_list and fail_list:
            QMessageBox.warning(self, title, "\n".join(lines))
        else:
            QMessageBox.critical(self, title, "\n".join(lines))

        self._reload_plugin_table()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = [u.toLocalFile() for u in urls]
        paths = [p for p in paths if Path(p).exists()]
        if not paths:
            return
        self._do_batch_import(paths, source="拖拽")

    def _restart_app(self):
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("plugins_restart_confirm"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        win = self.window()
        try:
            win._force_quit = True
        except Exception:
            pass
        if getattr(sys, "frozen", False):
            sp.Popen([sys.executable])
        else:
            sp.Popen([sys.executable] + sys.argv)
        QApplication.quit()

    def _relaunch_admin(self):
        if is_admin():
            QMessageBox.information(self, tr("msg_info"), "已是管理员")
            return
        if relaunch_as_admin():
            QApplication.quit()
        else:
            QMessageBox.critical(self, tr("msg_error"), "提权失败")

# ============================================================
# 33. 主窗口
# ============================================================
class MainWindow(QMainWindow):
    NAV_LIBRARY = 0
    NAV_ENGINES = 1
    NAV_BIOS = 2
    NAV_STATS = 3
    NAV_RESOURCES = 4
    NAV_LAN = 5
    NAV_WEBTRANSFER = 6
    NAV_RETRO_DOCS = 7
    NAV_SETTINGS = 8

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 800)
        self.setMinimumSize(960, 580)

        self._load_lang()
        self._engines_json = load_engines_json()
        self._monitor_workers: list = []
        self._perf_windows: list = []
        self._tray = None
        self._force_quit = False
        self._current_theme_dark = False
        self._theme_watcher = None
        self._plugin_manager = PluginManager(self)
        self._plugin_page_widgets: list = []
        self._bg_pixmap: Optional[QPixmap] = None
        self._drop_import_workers: list = []

        self._settle_stale_launches()

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
                     tr("nav_bios"), tr("nav_stats"),
                     tr("nav_resources"), tr("nav_lan"),
                     tr("nav_webtransfer"), tr("nav_retro_docs"),
                     tr("nav_settings")]:
            QListWidgetItem(name, self.nav)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        splitter.addWidget(self.nav)

        self.stack = QStackedWidget()

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_status = QLabel(f"就绪  |  数据目录: {DATA_DIR}")
        self.status.addWidget(self.lbl_status)
        self.lbl_admin = QLabel()
        self.status.addPermanentWidget(self.lbl_admin)
        self._refresh_admin_label()

        self.page_library = LibraryPage()
        self.page_library.launch_requested.connect(self._launch_game)
        self.page_library.open_folder_requested.connect(self._open_game_folder)
        self.page_library.remove_requested.connect(self._remove_game)
        self.page_library.favorite_toggled.connect(self._toggle_favorite)
        self.page_library.config_requested.connect(self._config_launch)
        self.page_library.controls_requested.connect(self._show_controls)
        self.page_library.scrape_requested.connect(self._scrape_covers)
        self.page_library.settings_requested.connect(
            self._open_engine_settings_for_game)
        self.page_library.status_msg.connect(self.status.showMessage)
        self.stack.addWidget(self.page_library)

        self.page_engines = EnginePage()
        self.page_engines.import_requested.connect(self._import_engine)
        self.page_engines.download_requested.connect(self._download_engine)
        self.page_engines.update_requested.connect(self._update_engine)
        self.page_engines.ignore_requested.connect(self._ignore_update)
        self.page_engines.settings_requested.connect(self._open_engine_settings)
        self.page_engines.status_message.connect(self.status.showMessage)
        self.page_engines.check_update_requested.connect(lambda: self._open_update_dialog(force=True))
        self.stack.addWidget(self.page_engines)

        self.page_bios = BiosPage()
        self.stack.addWidget(self.page_bios)

        self.page_stats = StatsPage()
        self.stack.addWidget(self.page_stats)

        self.page_resources = ResourcesPage()
        self.stack.addWidget(self.page_resources)

        self.page_lan = LanPage()
        self.page_lan.settings_requested.connect(
            lambda: self.nav.setCurrentRow(self.NAV_SETTINGS))
        self.stack.addWidget(self.page_lan)

        self.page_webtransfer = WebTransferPage()
        self.stack.addWidget(self.page_webtransfer)

        self.page_retro_docs = RetroDocsPage()
        self.stack.addWidget(self.page_retro_docs)

        self.page_settings = SettingsPage()
        self.page_settings.lang_changed.connect(self._on_lang_changed)
        self.page_settings.platforms_changed.connect(self._on_platforms_changed)
        self.page_settings.lan_changed.connect(self._on_lan_changed)
        self.page_settings.theme_changed.connect(self._on_theme_changed)
        self.page_settings.saves_changed.connect(self._reload_games)
        self.page_settings.plugins_changed.connect(self._load_plugins)
        self.page_settings.machine_tier_changed.connect(self._on_machine_tier_changed)
        self.page_settings.background_changed.connect(self._apply_background)
        self.page_settings.folders_changed.connect(self._on_folders_changed)
        self.page_settings.keymap_changed.connect(self._on_keymap_changed)
        self.stack.addWidget(self.page_settings)

        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([170, 1110])
        root.addWidget(splitter, 1)

        self.setAcceptDrops(True)

        self._apply_theme()
        self._apply_background()
        self._setup_tray()
        self._reload_games()

        self._load_plugins()

#        if SETTINGS.get("check_update_on_start", False):
#            QTimer.singleShot(3000, self._auto_check_updates)

        if SETTINGS.get("lan_enabled", False):
            QTimer.singleShot(800, self.page_lan.start_service)

        # ★ v1.8.0：启动 KeyMapper
        QTimer.singleShot(1500, self._start_keymapper_if_needed)

        self._watch_system_theme()

        QTimer.singleShot(300, self._check_win_version_startup)

    # ---------- ★ v1.8.0：KeyMapper 启动 ----------
    def _start_keymapper_if_needed(self):
        try:
            if SETTINGS.get("keymap_enabled", False) and HAS_KEYBOARD:
                km = get_keymapper()
                km.set_osd_callback(self._show_keymap_osd)
                if km.start():
                    logger.info("KeyMapper 已启动")
                else:
                    logger.info("KeyMapper 未启动（无映射或未启用）")
        except Exception as e:
            logger.exception(f"KeyMapper 启动失败: {e}")

    def _show_keymap_osd(self, text: str):
        self.status.showMessage(text, 1500)

    def _on_keymap_changed(self):
        """设置页改动按键映射后，重启 KeyMapper。"""
        try:
            km = get_keymapper()
            km.stop()
            if SETTINGS.get("keymap_enabled", False) and HAS_KEYBOARD:
                km.set_osd_callback(self._show_keymap_osd)
                km.start()
        except Exception as e:
            logger.exception(f"重启 KeyMapper 失败: {e}")

    # ---------- 清理残留启动标记 ----------
    def _settle_stale_launches(self):
        """启动时只归零 launch_start_ts，不结算时长。"""
        try:
            games = load_games()
            changed = False
            for g in games:
                if g.launch_start_ts and g.launch_start_ts > 0:
                    logger.info(
                        f"清理残留启动标记: {g.name} "
                        f"(ts={g.launch_start_ts})，不结算时长")
                    g.launch_start_ts = 0.0
                    changed = True
            if changed:
                save_games(games)
        except Exception as e:
            logger.exception(f"清理残留启动标记失败: {e}")

    def _check_win_version_startup(self):
        try:
            ok, msg = check_win10_1809_minimum()
            if not ok:
                QMessageBox.warning(self, tr("win_version_too_old_title"), msg)
        except Exception as e:
            logger.debug(f"Windows 版本检查失败: {e}")

    def _on_machine_tier_changed(self):
        refresh_machine_tier()
        self.status.showMessage(
            f"机器档次已更新为: {SETTINGS.get('machine_tier', '?')}")

    # ---------- 全局背景 ----------
    def _load_background_pixmap(self) -> Optional[QPixmap]:
        path = (SETTINGS.get("background_image", "") or "").strip()
        if not path:
            return None
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None
        pix = QPixmap(str(p))
        if pix.isNull():
            return None
        return pix

    def _apply_background(self):
        self._bg_pixmap = self._load_background_pixmap()
        if self._bg_pixmap is None:
            self.setAutoFillBackground(False)
            self.update()
            return
        try:
            palette = self.palette()
            brush = QBrush(self._bg_pixmap)
            palette.setBrush(QPalette.Window, brush)
            self.setPalette(palette)
            self.setAutoFillBackground(True)
        except Exception as e:
            logger.warning(f"设置背景失败: {e}")
        self.update()

    def paintEvent(self, event):
        mode = SETTINGS.get("background_mode", "cover")
        opacity = int(SETTINGS.get("background_opacity", 100))
        if self._bg_pixmap is None:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        try:
            painter.setOpacity(max(0.05, min(1.0, opacity / 100.0)))
            rect = self.rect()
            pix = self._bg_pixmap

            if mode == "stretch":
                painter.drawPixmap(rect, pix)
            elif mode == "tile":
                pw, ph = pix.width(), pix.height()
                if pw > 0 and ph > 0:
                    for x in range(0, rect.width(), pw):
                        for y in range(0, rect.height(), ph):
                            painter.drawPixmap(x, y, pix)
            elif mode == "contain":
                scaled = pix.scaled(rect.size(), Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
                x = (rect.width() - scaled.width()) // 2
                y = (rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            else:
                scaled = pix.scaled(rect.size(), Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation)
                x = (rect.width() - scaled.width()) // 2
                y = (rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
        finally:
            painter.end()

        super().paintEvent(event)

    def _on_folders_changed(self):
        self._engines_json = load_engines_json()
        self.page_library.refresh_platforms()
        self._reload_games()
        self.status.showMessage("工作区已切换")

    # ---------- 拖拽识别 ----------
    def dragEnterEvent(self, event):
        if not SETTINGS.get("drag_drop_enabled", True):
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not SETTINGS.get("drag_drop_enabled", True):
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not SETTINGS.get("drag_drop_enabled", True):
            return
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = []
        for u in urls:
            try:
                p = Path(u.toLocalFile())
                if p.exists():
                    paths.append(p)
            except Exception:
                pass
        if not paths:
            return
        event.acceptProposedAction()
        self._handle_dropped_paths(paths)

    def _handle_dropped_paths(self, paths: list):
        plugins = []
        bios_files = []
        game_files = []
        unknown = []

        bios_exts = {e.lower() for e in
                     SETTINGS.get("drag_drop_bios_exts",
                                  [".bin", ".rom", ".dat", ".keys"])}

        engines_json = load_engines_json()
        rom_ext_map = get_all_platform_rom_extensions(engines_json)

        for p in paths:
            if p.is_dir():
                plugins.append(p)
                continue

            ext = p.suffix.lower()

            if ext == ".py":
                plugins.append(p)
                continue

            if ext in (".zip", ".7z", ".rar") and "plugin" in p.stem.lower():
                plugins.append(p)
                continue

            if ext in rom_ext_map:
                game_files.append(p)
                continue

            if ext in bios_exts:
                try:
                    md5 = md5_of_file(p)
                except Exception:
                    md5 = ""
                if identify_bios_platform(p, md5):
                    bios_files.append(p)
                    continue
                game_files.append(p)
                continue

            unknown.append(p)

        summary = []

        if plugins:
            srcs = [str(x) for x in plugins]
            self._import_plugins_from_drop(srcs)
            summary.append(f"插件: {len(plugins)} 个")

        if bios_files:
            ok = 0
            for bf in bios_files:
                try:
                    dst = BIOS_DIR / bf.name
                    if dst.exists():
                        dst = dst.with_name(
                            f"{dst.stem}_{int(time.time())}{dst.suffix}")
                    shutil.copy2(bf, dst)
                    ok += 1
                except Exception as e:
                    logger.exception(f"复制 BIOS 失败: {e}")
            if ok:
                try:
                    auto_organize_bios(dry_run=False)
                except Exception:
                    pass
                clear_bios_check_cache()
                self.page_bios.refresh()
            summary.append(f"BIOS: {ok} 个")

        if game_files:
            self._import_games_from_drop(game_files)
            summary.append(f"游戏: {len(game_files)} 个")

        if unknown:
            summary.append(f"未识别: {len(unknown)} 个")

        if summary:
            self.status.showMessage("拖拽导入完成 - " + " / ".join(summary))
        else:
            self.status.showMessage("拖拽的文件无法识别")

    def _import_plugins_from_drop(self, paths: list):
        ok_list = []
        fail_list = []
        for fp in paths:
            try:
                ok, pid, filled, msg = _import_plugin_any(
                    Path(fp), overwrite=True)
                if ok:
                    ok_list.append(pid)
                else:
                    fail_list.append((Path(fp).name, msg or "未知错误"))
            except Exception as e:
                logger.exception(f"拖拽导入插件失败: {fp}")
                fail_list.append((Path(fp).name, str(e)))
        if ok_list:
            logger.info(f"拖拽导入插件成功: {ok_list}")
            QMessageBox.information(
                self, tr("msg_info"),
                f"已导入 {len(ok_list)} 个插件：\n"
                + "\n".join(f"  • {x}" for x in ok_list)
                + "\n\n请点「设置 → 重启程序」使其生效。")
        if fail_list:
            logger.warning(f"拖拽导入插件失败: {fail_list}")

    def _import_games_from_drop(self, paths: list):
        if not paths:
            return
        engines_json = load_engines_json()
        worker = _DropImportWorker(paths, engines_json)
        worker.done.connect(self._on_drop_import_done)
        worker.fail.connect(
            lambda e: self.status.showMessage(f"导入失败: {e}"))
        worker.start()
        self._drop_import_workers.append(worker)

    def _on_drop_import_done(self, new_games, skipped):
        if new_games:
            existing = load_games()
            existing_paths = {g.path for g in existing}
            for g in new_games:
                if g.path not in existing_paths:
                    existing.append(g)
            save_games(existing)
            self._reload_games()
            QMessageBox.information(
                self, tr("msg_info"),
                f"已导入 {len(new_games)} 个游戏"
                + (f"\n跳过 {skipped} 个" if skipped else ""))
        elif skipped:
            QMessageBox.information(
                self, tr("msg_info"),
                f"没有识别出游戏，跳过 {skipped} 个")

    # ---------- 顶部工具栏 ----------
    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        title = QLabel("mikan_emu")
        title.setObjectName("AppTitle")
        lay.addWidget(title)

        self.btn_recent = QToolButton()
        self.btn_recent.setText("▶")
        self.btn_recent.setToolTip(tr("tray_recent"))
        self.btn_recent.setPopupMode(QToolButton.InstantPopup)
        self.btn_recent.setFixedWidth(40)
        self.btn_recent.setStyleSheet(
            "QToolButton{font-size:14px;font-weight:bold;color:#0067c0;}")
        lay.addWidget(self.btn_recent)

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

        btn_patch = QPushButton(tr("toolbar_patch_tool"))
        btn_patch.clicked.connect(self._open_patch_tool)
        lay.addWidget(btn_patch)

        btn_scrape = QPushButton(tr("toolbar_scrape"))
        btn_scrape.clicked.connect(self._scrape_all_covers)
        lay.addWidget(btn_scrape)

        btn_export = QPushButton(tr("toolbar_export"))
        btn_export.clicked.connect(self._export_library)
        lay.addWidget(btn_export)

        btn_open_roms = QPushButton(tr("toolbar_open_roms"))
        btn_open_roms.clicked.connect(lambda: os.startfile(str(ROM_DIR)))
        lay.addWidget(btn_open_roms)

        btn_refresh = QPushButton(tr("toolbar_refresh"))
        btn_refresh.clicked.connect(self._refresh_all)
        lay.addWidget(btn_refresh)

        return bar

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        try:
            self._tray = QSystemTrayIcon(self)
            pix = QPixmap(64, 64)
            pix.fill(QColor("#0067c0"))
            p = QPainter(pix)
            p.setPen(QPen(QColor("#ffffff"), 4))
            p.drawText(pix.rect(), Qt.AlignCenter, "M")
            p.end()
            self._tray.setIcon(QIcon(pix))
            self._tray.setToolTip(f"{APP_NAME} v{APP_VERSION}")

            menu = QMenu()
            a_show = menu.addAction(tr("tray_show"))
            a_show.triggered.connect(self._show_from_tray)
            menu.addSeparator()

            games = sorted(load_games(), key=lambda g: g.last_played or "",
                           reverse=True)
            recent = [g for g in games if g.last_played][:5]
            if recent:
                sub = menu.addMenu(tr("tray_recent"))
                for g in recent:
                    a = sub.addAction(g.name)
                    a.triggered.connect(
                        lambda _=False, gg=g: self._launch_game(gg))
            menu.addSeparator()
            a_quit = menu.addAction(tr("tray_quit"))
            a_quit.triggered.connect(self._quit_app)
            self._tray.setContextMenu(menu)

            self._tray.activated.connect(self._on_tray_activated)
            self._tray.show()
        except Exception as e:
            logger.warning(f"托盘初始化失败: {e}")
            self._tray = None

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self):
        self._force_quit = True
        QApplication.quit()

    def closeEvent(self, event):
        if (not self._force_quit
                and SETTINGS.get("tray_minimize_on_close", False)
                and self._tray):
            event.ignore()
            self.hide()
            self._tray.showMessage(APP_NAME, tr("tray_minimized"),
                                   QSystemTrayIcon.Information, 2000)
            return
        try:
            self.page_lan.shutdown()
        except Exception:
            pass
        try:
            self._plugin_manager.emit("app_quit")
        except Exception:
            pass
        try:
            stop_keymapper()
        except Exception:
            pass
        for w in list(self._perf_windows):
            try:
                w.close()
            except Exception:
                pass
        # ★ v1.8.0：关闭 Job Object（KILL_ON_JOB_CLOSE 会自动杀模拟器）
        try:
            job = get_job_object()
            job.close()
        except Exception:
            pass
        event.accept()

    # ---------- 插件 ----------
    def _load_plugins(self):
        self._unload_plugin_pages()

        if not SETTINGS.get("plugins_auto_load", True):
            return

        try:
            self._plugin_manager.load_all()
        except Exception as e:
            logger.exception(f"插件加载失败: {e}")
            return

        pages = self._plugin_manager.get_pages()
        if not pages:
            return

        insert_at = self.NAV_SETTINGS
        for i, (title, widget, icon) in enumerate(pages):
            try:
                w = widget() if callable(widget) else widget
                if not isinstance(w, QWidget):
                    logger.warning(f"插件页面 {title} 不是 QWidget")
                    continue
                label = f"{icon} {title}" if icon else title
                item = QListWidgetItem(label)
                self.nav.insertItem(insert_at + i, item)
                self.stack.insertWidget(insert_at + i, w)
                self._plugin_page_widgets.append((insert_at + i, w))
                logger.info(f"插件页面已插入: {label} @ {insert_at + i}")
            except Exception as e:
                logger.exception(f"插件页面 {title} 加载失败: {e}")

        self.NAV_SETTINGS = insert_at + len(self._plugin_page_widgets)

    def _unload_plugin_pages(self):
        for _idx, w in reversed(self._plugin_page_widgets):
            try:
                self.stack.removeWidget(w)
                w.deleteLater()
            except Exception:
                pass
        self._plugin_page_widgets.clear()

        builtin_count = 9
        while self.nav.count() > builtin_count:
            item = self.nav.takeItem(self.nav.count() - 1)
            del item

        self.NAV_SETTINGS = 8

    # ---------- 主题 ----------
    def _apply_theme(self):
        mode = SETTINGS.get("theme", "auto")
        if mode == "auto":
            dark = self._is_system_dark()
        else:
            dark = (mode == "dark")

        accent = SETTINGS.get("accent_color", "")
        base = WIN11_QSS

        if dark:
            base = base + "\n" + DARK_QSS_OVERLAY
            if accent:
                try:
                    base = base.replace("#4cc2ff", accent)
                    base = base.replace("#1e3a52",
                                        QColor(accent).darker(300).name())
                except Exception:
                    pass
        elif accent:
            base = base.replace("#0067c0", accent)
            try:
                c = QColor(accent)
                base = base.replace("#1975c5", c.lighter(115).name())
                base = base.replace("#005ba8", c.darker(115).name())
                base = base.replace("#e8f0fa", c.lighter(180).name())
            except Exception:
                pass

        QApplication.instance().setStyleSheet(base)
        self._current_theme_dark = dark

    def _is_system_dark(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return int(val) == 0
        except Exception:
            return False

    def _on_theme_changed(self, mode: str, accent: str):
        self._apply_theme()

    def _watch_system_theme(self):
        self._theme_watcher = QTimer(self)
        self._theme_watcher.setInterval(3000)
        self._theme_watcher.timeout.connect(self._check_theme_drift)
        self._theme_watcher.start()

    def _check_theme_drift(self):
        if SETTINGS.get("theme", "auto") != "auto":
            return
        cur = self._is_system_dark()
        if cur != self._current_theme_dark:
            logger.info(f"系统主题变化: dark={cur}，重新应用")
            self._apply_theme()

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
        elif row == self.NAV_STATS:
            self.page_stats.refresh()
        elif row == self.NAV_RESOURCES:
            self.page_resources.refresh()
        elif row == self.NAV_LIBRARY:
            self.page_library.refresh_grid()

    def _reload_games(self):
        self.page_library.set_games(load_games())
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        menu = QMenu(self)
        games = [g for g in load_games() if g.last_played]
        games.sort(key=lambda x: x.last_played or "", reverse=True)

        if not games:
            act = menu.addAction("（还没有玩过的游戏）")
            act.setEnabled(False)
        else:
            for g in games[:10]:
                cover = find_cover(g.name)
                icon = QIcon(str(cover)) if cover else QIcon()
                label = g.name
                if g.play_seconds > 0:
                    label += f"   ({human_duration(g.play_seconds)})"
                act = menu.addAction(icon, label)
                act.setToolTip(g.path)
                act.triggered.connect(
                    lambda _=False, gg=g: self._launch_game(gg))

        menu.addSeparator()

        by_count = sorted(load_games(),
                          key=lambda x: x.launch_count or 0,
                          reverse=True)[:5]
        by_count = [g for g in by_count if (g.launch_count or 0) > 0]
        if by_count:
            sub = menu.addMenu("🔥 最常玩")
            for g in by_count:
                cover = find_cover(g.name)
                icon = QIcon(str(cover)) if cover else QIcon()
                act = sub.addAction(icon, f"{g.name}  ×{g.launch_count}")
                act.triggered.connect(
                    lambda _=False, gg=g: self._launch_game(gg))
            menu.addSeparator()

        a_more = menu.addAction("查看全部 →")
        a_more.triggered.connect(
            lambda: self.nav.setCurrentRow(self.NAV_LIBRARY))
        self.btn_recent.setMenu(menu)

    def _refresh_all(self):
        self._engines_json = load_engines_json()
        self.page_engines.refresh()
        self.page_bios.refresh()
        self.page_stats.refresh()
        self.page_resources.refresh()
        self.page_library.refresh_platforms()
        self._reload_games()
        self.status.showMessage("已刷新")

    def _on_platforms_changed(self):
        self._engines_json = load_engines_json()
        self.page_library.refresh_platforms()

    def _on_lan_changed(self):
        try:
            self.page_lan.restart_service()
        except Exception as e:
            logger.exception(f"重启局域网服务失败: {e}")

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

    def _open_patch_tool(self):
        dlg = PatchToolDialog(parent=self)
        dlg.exec()

    def _scrape_covers(self, games):
        dlg = CoverScrapeDialog(games, self)
        dlg.exec()
        self._reload_games()

    def _scrape_all_covers(self):
        games = load_games()
        if not games:
            QMessageBox.information(self, tr("msg_info"), "游戏库为空")
            return
        dlg = CoverScrapeDialog(games, self)
        dlg.exec()
        self._reload_games()

    def _export_library(self):
        games = load_games()
        if not games:
            QMessageBox.information(self, tr("msg_info"), "游戏库为空")
            return
        dlg = ExportDialog(games, self)
        if dlg.exec() != QDialog.Accepted:
            return
        r = dlg.result_data()
        if not r:
            return
        try:
            path = export_library(games, r["format"], r["scope"],
                                  r["playtime"], r["cover"])
            QMessageBox.information(self, tr("msg_info"),
                                    tr("export_done", path=str(path)))
            os.startfile(str(path.parent))
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("export_failed", err=str(e)))

    def _config_launch(self, game):
        dlg = GameConfigCenterDialog(game, self)
        dlg.launch_requested.connect(self._launch_game)
        dlg.open_folder_requested.connect(self._open_game_folder)
        dlg.engine_settings_requested.connect(self._open_engine_settings)
        dlg.exec()
        self._reload_games()

    def _show_controls(self, game):
        engine = self._resolve_engine(game, silent=True)
        engine_name = engine.engine if engine else ""
        if not engine_name:
            installed = load_installed()
            for e in installed:
                if e.platform == (game.override_platform or game.platform):
                    engine_name = e.engine
                    break
        dlg = ControlsDialog(engine_name or "unknown", self)
        dlg.exec()

    def _open_engine_settings_for_game(self, game):
        engine = self._resolve_engine(game, silent=True)
        if not engine:
            QMessageBox.warning(
                self, tr("msg_warning"),
                tr("launch_no_engine", platform=game.platform))
            return
        self._open_engine_settings(engine)

    def _open_engine_settings(self, engine):
        try:
            open_engine_settings(engine)
            self.status.showMessage(
                tr("engine_settings_launched", engine=engine.engine))
        except LaunchError as e:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle(tr("engine_settings_title"))
            box.setText(tr("engine_settings_failed", err=engine.engine))
            box.setDetailedText(str(e))
            box.exec()
        except Exception as e:
            QMessageBox.critical(
                self, tr("msg_error"),
                tr("engine_settings_failed", err=str(e)))

    def _resolve_engine(self, game, silent=False):
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
                candidates = [e for e in installed
                              if e.platform == game.platform]
            if not candidates:
                return None
        if len(candidates) == 1 or silent:
            return candidates[0]
        items = [f"{e.platform_name} / {e.engine} {e.version}".strip()
                 for e in candidates]
        choice, ok = QInputDialog.getItem(self, tr("launch_select_engine"),
                                          tr("launch_select_engine"),
                                          items, 0, False)
        if not ok:
            return None
        return candidates[items.index(choice)]

    def _launch_game(self, game):
        engine = self._resolve_engine(game)
        if not engine:
            QMessageBox.warning(
                self, tr("msg_warning"),
                tr("launch_no_engine", platform=game.platform))
            return

        try:
            ok, missing = check_bios_ready(engine)
            if not ok:
                reply = QMessageBox.question(
                    self, tr("msg_confirm"),
                    f"「{engine.engine}」缺少以下 BIOS：\n\n"
                    + "\n".join(f"  · {m}" for m in missing)
                    + f"\n\nBIOS 目录: {BIOS_DIR}\n\n仍然启动？",
                    QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return
        except Exception as e:
            logger.debug(f"BIOS 体检失败: {e}")

        if SETTINGS.get("auto_detect_engine_version", True):
            try:
                detect_engine_version(engine)
            except Exception as e:
                logger.debug(f"版本探测失败: {e}")

        try:
            self._plugin_manager.emit("before_launch",
                                      game=game, engine=engine)
        except Exception:
            pass

        try:
            proc, switched, bios_msg = launch_game(engine, game)
            msg = tr("launch_ok", name=game.name)
            if switched:
                msg += "  (" + tr("launch_cue_hint") + ")"
            if bios_msg:
                msg += "  (" + bios_msg + ")"
            self.status.showMessage(msg)

            games = load_games()
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            for g in games:
                if g.path == game.path:
                    g.last_played = now
                    g.launch_count = (g.launch_count or 0) + 1
                    g.launch_start_ts = time.time()
                    break
            save_games(games)
            self._reload_games()

            try:
                self._plugin_manager.emit("after_launch",
                                          game=game, engine=engine, proc=proc)
            except Exception:
                pass

            show_perf = SETTINGS.get("perf_monitor_on_launch", True)
            if SETTINGS.get("low_spec_mode", False):
                show_perf = False

            if proc and show_perf:
                try:
                    pw = PerfMonitorWindow(proc.pid, game.name, self)
                    self._perf_windows.append(pw)
                    pw.destroyed.connect(
                        lambda _=None, w=pw: self._perf_windows.remove(w)
                        if w in self._perf_windows else None)
                    pw.show()
                except Exception as e:
                    logger.warning(f"性能小窗启动失败: {e}")



            if HAS_PSUTIL and proc:
                monitor = ProcessMonitorWorker(proc.pid)
                monitor.finished.connect(
                    lambda secs, gp=game.path, pf=game.platform:
                        self._on_game_closed(gp, secs, pf))
                monitor.start()
                self._monitor_workers.append(monitor)
        except LaunchError as e:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle(tr("launch_diag_title"))
            box.setText(tr("launch_diag_header", name=game.name))
            box.setDetailedText(str(e))
            box.exec()
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("launch_failed", err=str(e)))

    def _on_game_closed(self, game_path: str, _seconds_unused: int,
                        platform: str):
        """正常退出时结算时长。"""
        try:
            games = load_games()
            now = time.time()
            secs = 0
            game = None
            for g in games:
                if g.path == game_path:
                    game = g
                    if g.launch_start_ts and g.launch_start_ts > 0:
                        try:
                            secs = int(max(0, now - g.launch_start_ts))
                            g.play_seconds += secs
                            record_playtime(platform, secs)
                        except Exception as e:
                            logger.exception(f"结算 {g.name} 时长失败: {e}")
                        finally:
                            g.launch_start_ts = 0.0
                    break
            save_games(games)
            self._reload_games()
            logger.info(f"游戏关闭: {game_path}")

            # ★ v1.8.0：KeyMapper 解除绑定
            try:
                if HAS_KEYBOARD:
                    km = get_keymapper()
                    # 从进程表里移除（按路径找不到 pid，但进程已退出，
                    # 下次 attach 前 KeyMapper 会清理）
                    # 这里简单调用 stop 里的清理逻辑
                    pass
            except Exception:
                pass

            try:
                self._plugin_manager.emit("after_close",
                                          game=game, seconds=secs)
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"结算时长失败: {e}")

    def _open_game_folder(self, game):
        folder = str(Path(game.path).parent)
        if os.path.isdir(folder):
            os.startfile(folder)

    def _remove_game(self, game):
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     tr("ctx_remove_confirm", name=game.name),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        games = load_games()
        games = [g for g in games if g.path != game.path]
        save_games(games)
        self._reload_games()

    def _toggle_favorite(self, game):
        games = load_games()
        for g in games:
            if g.path == game.path:
                g.favorite = not g.favorite
                break
        save_games(games)
        self._reload_games()

    def _on_lang_changed(self, lang: str):
        name = LANG_PACKS.get(lang, {}).get("_meta", {}).get("name", lang)
        QMessageBox.information(self, tr("msg_info"),
                                tr("lang_changed_msg", lang=name))

    def _load_lang(self):
        load_lang()

    def _auto_check_updates(self):
        if not SETTINGS.get("check_update_on_start", True):
            return
        try:
            self._open_update_dialog()
        except Exception as e:
            logger.debug(f"自动检查更新失败: {e}")

    # ---------- ★ v1.8.0：更新对话框 ----------
    def _open_update_dialog(self, force=False):
        # ★ force 参数：用于区分是“自动启动”还是“手动点击按钮”
        # 如果不是手动点开（force=False），且设置里没开启“启动时检查更新”，直接拦截！
        if not force and not SETTINGS.get("check_update_on_start", False):
            return

        installed = load_installed()
        if not installed:
            QMessageBox.information(self, tr("msg_info"), tr("engines_empty"))
            return
        engines_json = load_engines_json()
        dlg = UpdateDialog(installed, engines_json, self)
        dlg.request_update.connect(self._on_update_requested)
        dlg.exec()
        self.page_engines.refresh()

    def _on_update_requested(self, platform: str, engine: str,
                             rel: dict, use_mirror: bool):
        """UpdateDialog 选中版本后，真正执行下载安装。"""
        url = rel.get("download_url", "")
        version = rel.get("tag", "")
        if not url:
            QMessageBox.warning(self, tr("msg_warning"), "该版本没有可用下载")
            return

        engines_json = load_engines_json()
        pcfg = engines_json.get(platform, {})
        cfg = pcfg.get("engines", {}).get(engine)
        if not cfg:
            QMessageBox.warning(self, tr("msg_warning"), tr("engine_not_found"))
            return
        cfg = dict(cfg)
        cfg["url"] = url
        cfg["version"] = version

        # 根据资产名推断扩展名
        asset_name = rel.get("asset_name", "").lower()
        if asset_name.endswith(".7z"):
            ext = ".7z"
        elif asset_name.endswith(".rar"):
            ext = ".rar"
        elif asset_name.endswith(".exe"):
            ext = ".exe"
        else:
            ext = ".zip"
        tmp = TEMP_DIR / f"upd_{platform}_{engine}_{version}{ext}"

        # 临时设置镜像开关
        old_use_mirror = SETTINGS.get("download_use_mirror", True)
        SETTINGS["download_use_mirror"] = use_mirror
        try:
            save_settings()
        except Exception:
            pass

        w = DownloadWorker(url, tmp, SETTINGS.get("download_threads", 8))

        # 用一个小对话框显示进度
        prog_dlg = QDialog(self)
        prog_dlg.setWindowTitle(f"更新 {platform}/{engine} → {version}")
        prog_dlg.setMinimumWidth(520)
        pv = QVBoxLayout(prog_dlg)
        lbl_cur = QLabel(f"{platform}/{engine} → {version}")
        lbl_cur.setObjectName("SectionTitle")
        pv.addWidget(lbl_cur)
        bar = QProgressBar()
        bar.setRange(0, 100)
        pv.addWidget(bar)
        lbl_status = QLabel("")
        lbl_status.setObjectName("Hint")
        pv.addWidget(lbl_status)
        log = QTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(140)
        pv.addWidget(log)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton(tr("msg_cancel"))
        btn_cancel.clicked.connect(w.cancel)
        btn_row.addWidget(btn_cancel)
        pv.addLayout(btn_row)

        def on_progress(cur, total):
            if total > 0:
                bar.setRange(0, 100)
                bar.setValue(int(cur * 100 / total))
            else:
                bar.setRange(0, 0)

        def on_status(s):
            lbl_status.setText(s)
            log.append(s)

        def on_done(path):
            try:
                self._install_update(platform, engine, cfg, Path(path))
                log.append(f"✅ {engine} 更新完成")
                QMessageBox.information(prog_dlg, tr("msg_info"),
                                        f"{engine} 已更新到 {version}")
                prog_dlg.accept()
                self.page_engines.refresh()
            except Exception as e:
                logger.exception("安装更新失败")
                log.append(f"❌ {e}")
                QMessageBox.critical(prog_dlg, tr("msg_error"), str(e))

        def on_fail(err):
            log.append(f"❌ 下载失败: {err}")
            QMessageBox.critical(prog_dlg, tr("msg_error"), err)

        w.progress.connect(on_progress)
        w.status.connect(on_status)
        w.done.connect(on_done)
        w.fail.connect(on_fail)
        w.finished.connect(
            lambda: SETTINGS.__setitem__("download_use_mirror", old_use_mirror))
        w.start()

        prog_dlg.exec()

    def _install_update(self, platform: str, engine: str,
                        cfg: dict, archive: Path):
        """安装下载好的更新包。"""
        archive_type = cfg.get("archive", "zip")
        asset_name = archive.name.lower()
        if asset_name.endswith(".7z"):
            archive_type = "7z"
        elif asset_name.endswith(".exe"):
            archive_type = "7z_sfx" if cfg.get("archive") == "7z_sfx" else "bare_exe"
        elif asset_name.endswith(".rar"):
            archive_type = "rar"

        if archive_type == "bare_exe":
            target_dir = ENGINE_DOWNLOAD_DIR / platform / engine
            target_dir.mkdir(parents=True, exist_ok=True)
            target_exe = target_dir / archive.name
            shutil.copy2(archive, target_exe)
            engines = load_installed()
            for e in engines:
                if e.platform == platform and e.engine == engine:
                    e.engine_path = str(target_exe)
                    e.engine_dir = str(target_dir)
                    e.version = cfg.get("version", e.version)
                    e.installed_at = time.strftime("%Y-%m-%d %H:%M:%S")
                    break
            save_installed(engines)
            try:
                archive.unlink()
            except Exception:
                pass
            return

        tmp_root = Path(tempfile.mkdtemp(prefix="mikan_upd_", dir=str(TEMP_DIR)))
        try:
            if archive_type == "7z_sfx":
                try:
                    sp.run([str(archive), f"-o{tmp_root}", "-y"],
                           check=True, timeout=600,
                           creationflags=getattr(sp, "CREATE_NO_WINDOW", 0))
                except Exception:
                    import py7zr
                    with py7zr.SevenZipFile(archive, mode="r") as z:
                        z.extractall(tmp_root)
            else:
                extract_archive(archive, tmp_root)

            files = scan_files(tmp_root)
            matches = match_engines(
                files, {platform: {"engines": {engine: cfg}}})
            if not matches:
                raise RuntimeError("解压后没找到可执行文件")

            new_cfg = install_engine_from_match(matches[0], tmp_root, "download")
            new_cfg.version = cfg.get("version", new_cfg.version)

            engines = load_installed()
            engines = [e for e in engines
                       if not (e.platform == new_cfg.platform
                               and e.engine == new_cfg.engine)]
            engines.append(new_cfg)
            save_installed(engines)
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
            try:
                archive.unlink()
            except Exception:
                pass

    def _update_engine(self, platform: str, engine: str, url: str):
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            f"更新 {platform}/{engine}？\n{url}",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        engines_json = load_engines_json()
        pcfg = engines_json.get(platform, {})
        cfg = pcfg.get("engines", {}).get(engine)
        if not cfg:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("engine_not_found"))
            return
        cfg = dict(cfg)
        cfg["url"] = url
        ext = ".zip"
        archive = cfg.get("archive", "zip")
        if archive in ("7z",):
            ext = ".7z"
        elif archive in ("7z_sfx", "bare_exe"):
            ext = ".exe"
        tmp = TEMP_DIR / f"upd_{platform}_{engine}{ext}"
        dlg = DownloadDialog(engines_json, self)
        dlg._current_engine = (platform, engine, cfg)
        w = DownloadWorker(url, tmp, SETTINGS.get("download_threads", 8))
        dlg._worker = w

        def on_done(path):
            try:
                dlg._install_downloaded(Path(path))
                QMessageBox.information(self, tr("msg_info"),
                                        tr("download_done"))
                self.page_engines.refresh()
            except Exception as e:
                QMessageBox.critical(self, tr("msg_error"), str(e))

        w.done.connect(on_done)
        w.fail.connect(lambda e: QMessageBox.critical(
            self, tr("msg_error"), tr("download_failed", err=e)))
        w.start()
        self.page_engines._update_worker = w

    def _ignore_update(self, platform: str, engine: str, version: str):
        UPDATE_IGNORE[f"{platform}/{engine}"] = version
        save_update_ignore()
        self.page_engines._model._updates.pop(f"{platform}/{engine}", None)
        self.page_engines.refresh()
        self.status.showMessage(f"已跳过 {platform}/{engine} {version}")

# ============================================================
# 34. 基础对话框
# ============================================================
class LaunchConfigDialog(QDialog):
    def __init__(self, game, parent=None):
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
            f"{tr('config_current_platform')}: <b>{self._game.custom_platform or self._game.platform}</b>"
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
        engines_json = load_engines_json()
        for p, pcfg in engines_json.items():
            if p.startswith("_"):
                continue
            self.combo_override.addItem(pcfg.get("platform_name", p), p)
        gp.addWidget(self.combo_override)
        layout.addWidget(grp_plat)

        grp_prof = QGroupBox(tr("config_profile_group"))
        gpr = QVBoxLayout(grp_prof)
        self.combo_profile = QComboBox()
        self.combo_profile.addItem(tr("config_profile_none"), "")
        for name in (SETTINGS.get("launch_profiles") or {}):
            self.combo_profile.addItem(name, name)
        gpr.addWidget(self.combo_profile)
        hint_p = QLabel(tr("config_profile_hint"))
        hint_p.setObjectName("Hint")
        gpr.addWidget(hint_p)
        layout.addWidget(grp_prof)

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
        idx = self.combo_profile.findData(getattr(g, "profile", "") or "")
        if idx >= 0:
            self.combo_profile.setCurrentIndex(idx)
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
            "profile": self.combo_profile.currentData() or "",
        }
        self.accept()

    def result_data(self):
        return self._result


class BiosSelectDialog(QDialog):
    def __init__(self, game, parent=None):
        super().__init__(parent)
        self._game = game
        self._result = None
        self.setWindowTitle(tr("bios_select_title"))
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        hint = QLabel(tr("bios_select_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_bios = QListWidget()
        self.list_bios.addItem(tr("bios_select_none"))
        bios_files = scan_bios()
        if not bios_files:
            self.list_bios.addItem(tr("bios_select_no_files"))
            self.list_bios.setEnabled(False)
        else:
            for b in bios_files:
                label = b.name
                if b.known_as:
                    label += f"  [{b.known_as}]"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, b.path)
                self.list_bios.addItem(item)
        self.list_bios.setCurrentRow(0)
        layout.addWidget(self.list_bios, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("config_save"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("config_cancel"))
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_save(self):
        item = self.list_bios.currentItem()
        if item is None:
            self._result = ""
        else:
            self._result = item.data(Qt.UserRole) or ""
        self.accept()

    def result_data(self) -> str:
        return self._result or ""


class ControlsDialog(QDialog):
    def __init__(self, engine_name: str, parent=None):
        super().__init__(parent)
        self._engine_name = engine_name
        self.setWindowTitle(f"{tr('controls_title')} - {engine_name}")
        self.setMinimumSize(480, 520)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        data = get_controls(self._engine_name) or get_generic_controls()

        head = QLabel(f"<b>{tr('controls_engine')}:</b> {self._engine_name}<br>")
        head.setWordWrap(True)
        layout.addWidget(head)

        keys = data.get("keys", {})
        if not keys:
            layout.addWidget(QLabel(tr("controls_no_data")))
        else:
            table = QTableWidget(len(keys), 2)
            table.setHorizontalHeaderLabels(["按键", "功能"])
            table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.Stretch)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for i, (k, v) in enumerate(keys.items()):
                table.setItem(i, 0, QTableWidgetItem(k))
                table.setItem(i, 1, QTableWidgetItem(v))
            layout.addWidget(table, 1)

        source = data.get("source", "")
        if source:
            src_lbl = QLabel(
                f"{tr('controls_source')}: <a href='{source}'>{source}</a>")
            src_lbl.setOpenExternalLinks(True)
            src_lbl.setObjectName("Hint")
            src_lbl.setWordWrap(True)
            layout.addWidget(src_lbl)

        btn_row = QHBoxLayout()
        if source:
            btn_doc = QPushButton(tr("controls_open_doc"))
            btn_doc.clicked.connect(lambda: webbrowser.open(source))
            btn_row.addWidget(btn_doc)
        btn_row.addStretch(1)
        btn_close = QPushButton(tr("msg_ok"))
        btn_close.setObjectName("PrimaryBtn")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class CreditsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("credits_title"))
        self.setMinimumSize(560, 620)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setSpacing(14)

        title = QLabel(tr("credits_title"))
        title.setObjectName("SectionTitle")
        v.addWidget(title)

        g1 = QGroupBox(tr("credits_deps"))
        f1 = QVBoxLayout(g1)
        deps_text = (
            "<b>PySide6</b> — Qt for Python, LGPL v3<br>"
            "<b>requests</b> — Apache 2.0<br>"
            "<b>loguru</b> — MIT<br>"
            "<b>py7zr</b> — LGPL v2.1+<br>"
            "<b>rarfile</b> — ISC<br>"
            "<b>certifi</b> — MPL 2.0<br>"
            "<b>psutil</b> — BSD-3-Clause<br>"
            "<b>packaging</b> — Apache 2.0 / BSD<br>"
            "<b>PySocks</b> — BSD<br>"
            "<b>keyboard</b> — MIT<br>"
            "<b>PySide6-WebEngine</b>（可选）— LGPL v3<br>"
            "<b>LocalSend</b>（Web 版）— MIT"
        )
        lbl1 = QLabel(deps_text)
        lbl1.setWordWrap(True)
        lbl1.setTextFormat(Qt.RichText)
        f1.addWidget(lbl1)
        v.addWidget(g1)

        g2 = QGroupBox(tr("credits_emulators"))
        f2 = QVBoxLayout(g2)
        emu_text = (
            "MAME · RetroArch / Libretro · Mednafen · DuckStation · PCSX2<br>"
            "mGBA · melonDS · DeSmuME · Flycast · ares · SameBoy<br>"
            "PPSSPP · Ryujinx · Ymir · Brimir · simple64 · RMG<br>"
            "Mupen64Plus · Project64 · cen64 · gopher64 · BlastEm<br>"
            "FCEUX · Mesen · openMSX · blueMSX · Tsugaru · PCFXemu<br>"
            "PX68k · NP2kai · DreamPotato · Deecy · Snes9x · ePSXe<br>"
            "XEBRA · SSF · Yaba Sanshiro · Redream · Kega Fusion<br>"
            "86Box · PCem · Dolphin · Cemu · RPCS3 · Vita3K<br>"
            "bsnes · Neon64 · NooDS · Azahar · VBA-M · Nestopia<br>"
            "Nintendulator · BGB · VICE · Hatari · DOSBox-X · Stella<br>"
            "Emulicious · Caprice32 · CPCSyntaxError · 1984 · b2<br>"
            "ZEsarUX · Gearcoleco · jzIntv · Geargrafx · AMSpiriT<br>"
            "<br>感谢以上所有开源/闭源模拟器项目的作者与贡献者。"
        )
        lbl2 = QLabel(emu_text)
        lbl2.setWordWrap(True)
        f2.addWidget(lbl2)
        v.addWidget(g2)

        g3 = QGroupBox(tr("credits_data"))
        f3 = QVBoxLayout(g3)
        data_text = (
            "<b>No-Intro</b> — ROM 命名规范<br>"
            "<b>Redump</b> — 光盘校验数据库<br>"
            "<b>MAME 键位文档</b><br>"
            "<b>Libretro Thumbnails</b> — 封面图库<br>"
            "<b>SteamGridDB</b> — 现代平台封面<br>"
            "<b>Libretro 文档</b><br>"
            "<b>LocalSend Web</b> — 局域网传输后端<br>"
            "<b>IPS / UPS 格式文档</b> — 补丁工具<br>"
            "<b>骨灰集散地</b> — 老游戏资料"
        )
        lbl3 = QLabel(data_text)
        lbl3.setWordWrap(True)
        lbl3.setTextFormat(Qt.RichText)
        f3.addWidget(lbl3)
        v.addWidget(g3)

        g4 = QGroupBox(tr("credits_thanks"))
        f4 = QVBoxLayout(g4)
        lbl4 = QLabel(tr("credits_thanks_text"))
        lbl4.setWordWrap(True)
        f4.addWidget(lbl4)
        v.addWidget(g4)

        v.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton(tr("msg_ok"))
        btn_close.setObjectName("PrimaryBtn")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class LogViewerDialog(QDialog):
    LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("log_viewer_title"))
        self.setMinimumSize(820, 560)
        self._keyword = ""
        self._auto_scroll = True
        self._last_rendered_count = 0
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("log_viewer_level")))
        self.combo_level = QComboBox()
        self.combo_level.addItem(tr("log_level_all"), "ALL")
        for lv in self.LEVELS:
            self.combo_level.addItem(lv, lv)
        self.combo_level.setCurrentIndex(3)
        self.combo_level.currentIndexChanged.connect(self._on_level_changed)
        top.addWidget(self.combo_level)

        top.addWidget(QLabel(tr("log_viewer_filter")))
        self.edit_kw = QLineEdit()
        self.edit_kw.setPlaceholderText(tr("log_filter_ph"))
        self.edit_kw.setClearButtonEnabled(True)
        top.addWidget(self.edit_kw, 1)

        self._kw_timer = QTimer(self)
        self._kw_timer.setSingleShot(True)
        self._kw_timer.setInterval(200)
        self._kw_timer.timeout.connect(self._on_kw_changed)
        self.edit_kw.textChanged.connect(lambda _: self._kw_timer.start())

        self.check_scroll = QCheckBox(tr("log_auto_scroll"))
        self.check_scroll.setChecked(True)
        self.check_scroll.toggled.connect(self._on_autoscroll_toggled)
        top.addWidget(self.check_scroll)

        v.addLayout(top)

        row2 = QHBoxLayout()
        btn_clear = QPushButton(tr("log_clear_buffer"))
        btn_clear.clicked.connect(self._on_clear)
        row2.addWidget(btn_clear)

        btn_open = QPushButton(tr("log_open_dir"))
        btn_open.clicked.connect(self._open_log_dir)
        row2.addWidget(btn_open)

        btn_export = QPushButton(tr("log_export_pack"))
        btn_export.setObjectName("PrimaryBtn")
        btn_export.clicked.connect(self._export_pack)
        row2.addWidget(btn_export)

        row2.addStretch(1)
        v.addLayout(row2)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QTextEdit.NoWrap)
        self.view.setStyleSheet(
            "font-family: 'Cascadia Mono', 'Consolas', monospace; "
            "font-size: 12px;")
        v.addWidget(self.view, 1)

        bottom = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("Hint")
        bottom.addWidget(self.lbl_count, 1)

        btn_close = QPushButton(tr("crash_close"))
        btn_close.setObjectName("PrimaryBtn")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        v.addLayout(bottom)

    def _on_level_changed(self, _idx):
        self._tick()

    def _on_kw_changed(self):
        self._keyword = self.edit_kw.text().strip().lower()
        self._tick()

    def _on_autoscroll_toggled(self, checked):
        self._auto_scroll = bool(checked)
        if self._auto_scroll:
            sb = self.view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_clear(self):
        with LOG_RING_LOCK:
            LOG_RING.clear()
        self.view.clear()
        self.lbl_count.setText(tr("log_count", shown=0, total=0))

    def _open_log_dir(self):
        try:
            os.startfile(str(LOG_DIR))
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"), str(e))

    def _export_pack(self):
        try:
            p = build_crash_report("用户手动导出诊断包")
            reply = QMessageBox.question(
                self, tr("msg_info"),
                tr("log_export_success", path=str(p)),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    os.startfile(str(p.parent))
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

    def _level_ok(self, level_name: str) -> bool:
        cur = self.combo_level.currentData()
        if cur == "ALL":
            return True
        try:
            cur_idx = self.LEVELS.index(cur)
            got_idx = self.LEVELS.index(level_name)
        except ValueError:
            return True
        return got_idx >= cur_idx

    def _tick(self):
        with LOG_RING_LOCK:
            snapshot = list(LOG_RING)
        total = len(snapshot)

        lines_html = []
        shown = 0
        for r in snapshot:
            lv = r.get("level", "INFO")
            if not self._level_ok(lv):
                continue
            msg = r.get("msg", "")
            if self._keyword and self._keyword not in msg.lower():
                continue
            shown += 1

            color = {
                "DEBUG":    "#888888",
                "INFO":     "#1c1c1c",
                "WARNING":  "#b27300",
                "ERROR":    "#c42b1c",
                "CRITICAL": "#8a00a0",
            }.get(lv, "#1c1c1c")

            safe_msg = (msg
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;"))
            html = (
                f"<span style='color:#888;'>[{r.get('full_ts', '')}]</span> "
                f"<span style='color:{color};font-weight:600;'>{lv:8}</span> "
                f"<span style='color:#555;'>{r.get('name', '')}:{r.get('line', '')}</span>  "
                f"<span style='color:{color};'>{safe_msg}</span>"
            )
            lines_html.append(html)

        if shown != self._last_rendered_count or len(lines_html) > 0:
            new_html = "<br>".join(lines_html[-1500:])
            self.view.setHtml(new_html)
            self._last_rendered_count = shown

        self.lbl_count.setText(tr("log_count", shown=shown, total=total))
        if self._auto_scroll:
            sb = self.view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            self._kw_timer.stop()
        except Exception:
            pass
        event.accept()


class ManualEngineDialog(QDialog):
    def __init__(self, exe_files, engines_json, parent=None):
        super().__init__(parent)
        self._exe_files = exe_files
        self._engines_json = engines_json
        self._result = None
        self.setWindowTitle(tr("import_manual_exe"))
        self.setMinimumWidth(560)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        hint = QLabel(tr("import_manual_exe_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_exe = QListWidget()
        for f in self._exe_files:
            item = QListWidgetItem(str(f))
            item.setData(Qt.UserRole, str(f))
            self.list_exe.addItem(item)
        if self._exe_files:
            self.list_exe.setCurrentRow(0)
        layout.addWidget(self.list_exe, 1)

        form = QFormLayout()
        self.combo_platform = QComboBox()
        for p, pcfg in self._engines_json.items():
            if p.startswith("_"):
                continue
            self.combo_platform.addItem(pcfg.get("platform_name", p), p)
        self.combo_platform.addItem(tr("import_game_custom"), "unknown")
        form.addRow(tr("import_manual_platform"), self.combo_platform)
        ph = QLabel(tr("import_manual_platform_hint"))
        ph.setObjectName("Hint")
        form.addRow("", ph)

        self.edit_engine = QLineEdit()
        self.edit_engine.setPlaceholderText("my_emulator")
        form.addRow(tr("import_manual_engine_name"), self.edit_engine)

        self.edit_tpl = QLineEdit()
        self.edit_tpl.setText('{exe} "{rom}"')
        form.addRow(tr("import_manual_launch_tpl"), self.edit_tpl)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("config_save"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("config_cancel"))
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_save(self):
        item = self.list_exe.currentItem()
        if item is None:
            QMessageBox.warning(self, tr("msg_warning"), "请选择一个 exe")
            return
        exe_path = item.data(Qt.UserRole)
        platform = self.combo_platform.currentData() or "unknown"
        engine_name = self.edit_engine.text().strip() or "manual_engine"
        tpl = self.edit_tpl.text().strip() or '{exe} "{rom}"'
        self._result = {
            "exe": exe_path,
            "platform": platform,
            "engine": engine_name,
            "launch_template": tpl,
            "platform_display": self.combo_platform.currentText(),
        }
        self.accept()

    def result_data(self):
        return self._result


class ExportDialog(QDialog):
    def __init__(self, games, parent=None):
        super().__init__(parent)
        self._games = games
        self._result = None
        self.setWindowTitle(tr("export_title"))
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combo_format = QComboBox()
        self.combo_format.addItem(tr("export_format_md"), "md")
        self.combo_format.addItem(tr("export_format_html"), "html")
        self.combo_format.addItem(tr("export_format_csv"), "csv")
        form.addRow(tr("export_format"), self.combo_format)

        self.combo_scope = QComboBox()
        self.combo_scope.addItem(tr("export_scope_all"), "all")
        self.combo_scope.addItem(tr("export_scope_fav"), "fav")
        form.addRow("范围", self.combo_scope)

        self.check_playtime = QCheckBox(tr("export_include_playtime"))
        self.check_playtime.setChecked(True)
        form.addRow("", self.check_playtime)

        self.check_cover = QCheckBox(tr("export_include_cover"))
        self.check_cover.setChecked(True)
        form.addRow("", self.check_cover)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("config_save"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("config_cancel"))
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_save(self):
        self._result = {
            "format": self.combo_format.currentData(),
            "scope": self.combo_scope.currentData(),
            "playtime": self.check_playtime.isChecked(),
            "cover": self.check_cover.isChecked(),
        }
        self.accept()

    def result_data(self):
        return self._result


class PlatformConfirmDialog(QDialog):
    def __init__(self, games, engines_json, parent=None):
        super().__init__(parent)
        self._games = games
        self._engines_json = engines_json
        self.setWindowTitle(tr("import_game_title"))
        self.setMinimumSize(720, 480)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("import_game_set_all")))
        self.combo_set_all = QComboBox()
        for p, pcfg in self._engines_json.items():
            if p.startswith("_"):
                continue
            self.combo_set_all.addItem(pcfg.get("platform_name", p), p)
        top.addWidget(self.combo_set_all)
        btn_set = QPushButton("应用")
        btn_set.clicked.connect(self._apply_all)
        top.addWidget(btn_set)
        top.addStretch(1)
        layout.addLayout(top)

        self.table = QTableWidget(len(self._games), 3)
        self.table.setHorizontalHeaderLabels(
            [tr("library_col_name"), tr("library_col_platform"),
             tr("library_col_path")])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        self._combos = []
        for i, g in enumerate(self._games):
            self.table.setItem(i, 0, QTableWidgetItem(g.name))
            combo = QComboBox()
            for p, pcfg in self._engines_json.items():
                if p.startswith("_"):
                    continue
                combo.addItem(pcfg.get("platform_name", p), p)
            combo.addItem(tr("import_game_custom"), "__custom__")
            idx = combo.findData(g.platform)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self.table.setCellWidget(i, 1, combo)
            self._combos.append(combo)
            self.table.setItem(i, 2, QTableWidgetItem(g.path))
        layout.addWidget(self.table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("config_save"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("config_cancel"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _apply_all(self):
        p = self.combo_set_all.currentData()
        for combo in self._combos:
            idx = combo.findData(p)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def result_games(self):
        for i, g in enumerate(self._games):
            combo = self._combos[i]
            p = combo.currentData()
            if p == "__custom__":
                name, ok = QInputDialog.getText(
                    self, tr("import_game_custom"),
                    tr("import_game_custom_prompt"))
                if ok and name.strip():
                    g.custom_platform = name.strip()
                    g.platform = "unknown"
                else:
                    g.platform = "unknown"
                    g.custom_platform = tr("bios_unknown")
            else:
                g.platform = p
        return self._games


class DupResolveDialog(QDialog):
    def __init__(self, dup_pairs, parent=None):
        super().__init__(parent)
        self._dup = dup_pairs
        self._action = ("skip",)
        self.setWindowTitle(tr("import_dup_title"))
        self.setMinimumSize(720, 480)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        lbl = QLabel(tr("import_dup_hint", n=len(self._dup)))
        lbl.setTextFormat(Qt.RichText)
        v.addWidget(lbl)

        table = QTableWidget(len(self._dup), 3)
        table.setHorizontalHeaderLabels([
            tr("import_dup_col_new"),
            tr("import_dup_col_old"),
            tr("import_dup_col_size")])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i, (new_g, old_g) in enumerate(self._dup):
            table.setItem(i, 0, QTableWidgetItem(new_g.name))
            table.setItem(i, 1, QTableWidgetItem(old_g.name))
            try:
                sz = Path(new_g.path).stat().st_size
            except Exception:
                sz = new_g.size
            table.setItem(i, 2, QTableWidgetItem(format_size(sz)))
        v.addWidget(table, 1)

        group = QButtonGroup(self)
        self.rb_skip = QRadioButton(tr("import_dup_skip"))
        self.rb_keep = QRadioButton(tr("import_dup_keep"))
        self.rb_over = QRadioButton(tr("import_dup_overwrite"))
        self.rb_skip.setChecked(True)
        group.addButton(self.rb_skip)
        group.addButton(self.rb_keep)
        group.addButton(self.rb_over)
        v.addWidget(self.rb_skip)
        v.addWidget(self.rb_keep)
        v.addWidget(self.rb_over)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("msg_ok"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("msg_cancel"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def accept(self):
        if self.rb_skip.isChecked():
            self._action = ("skip",)
        elif self.rb_keep.isChecked():
            self._action = ("keep",)
        else:
            self._action = ("overwrite",)
        super().accept()

    def result_action(self):
        a = self._action
        return (a[0] == "keep", a[0] == "skip", a[0] == "overwrite")


class PatchToolDialog(QDialog):
    def __init__(self, initial_rom: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._rom: Optional[Path] = initial_rom
        self._patch: Optional[Path] = None
        self.setWindowTitle(tr("patch_tool_title"))
        self.setMinimumWidth(600)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        info = QLabel(tr("patch_hint"))
        info.setObjectName("Hint")
        info.setWordWrap(True)
        v.addWidget(info)

        form = QFormLayout()
        self.edit_rom = QLineEdit(str(self._rom) if self._rom else "")
        b_rom = QPushButton(tr("patch_tool_browse"))
        b_rom.clicked.connect(self._pick_rom)
        h_rom = QHBoxLayout()
        h_rom.addWidget(self.edit_rom, 1)
        h_rom.addWidget(b_rom)
        form.addRow(tr("patch_tool_rom"), h_rom)

        self.edit_patch = QLineEdit()
        b_patch = QPushButton(tr("patch_tool_browse"))
        b_patch.clicked.connect(self._pick_patch)
        h_patch = QHBoxLayout()
        h_patch.addWidget(self.edit_patch, 1)
        h_patch.addWidget(b_patch)
        form.addRow(tr("patch_tool_patch"), h_patch)

        self.edit_out = QLineEdit()
        self.edit_out.setPlaceholderText(tr("patch_tool_output_ph"))
        b_out = QPushButton(tr("patch_tool_browse"))
        b_out.clicked.connect(self._pick_out)
        h_out = QHBoxLayout()
        h_out.addWidget(self.edit_out, 1)
        h_out.addWidget(b_out)
        form.addRow(tr("patch_tool_output"), h_out)

        self.check_backup = QCheckBox(tr("patch_backup"))
        self.check_backup.setChecked(True)
        form.addRow("", self.check_backup)
        v.addLayout(form)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        v.addWidget(self.log)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("patch_tool_apply"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("msg_cancel"))
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _pick_rom(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("patch_tool_rom"), str(ROM_DIR), "所有文件 (*)")
        if fp:
            self.edit_rom.setText(fp)

    def _pick_patch(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("patch_tool_patch"), str(Path.home()),
            "ROM 补丁 (*.ips *.ups);;所有文件 (*)")
        if fp:
            self.edit_patch.setText(fp)

    def _pick_out(self):
        fp, _ = QFileDialog.getSaveFileName(
            self, tr("patch_tool_output"), str(ROM_DIR), "所有文件 (*)")
        if fp:
            self.edit_out.setText(fp)

    def _apply(self):
        rom = Path(self.edit_rom.text().strip())
        patch = Path(self.edit_patch.text().strip())
        out = self.edit_out.text().strip()
        out_path = Path(out) if out else None

        if not rom.exists():
            QMessageBox.warning(self, tr("msg_warning"),
                                "请选择有效的 ROM 文件")
            return
        if not patch.exists():
            QMessageBox.warning(self, tr("msg_warning"),
                                "请选择有效的补丁文件")
            return

        self.log.append(f"ROM: {rom}")
        self.log.append(f"补丁: {patch}")
        try:
            result, old, new = apply_patch_file(
                rom, patch, out_path, self.check_backup.isChecked())
            self.log.append(f"✅ 输出: {result}")
            self.log.append(f"   大小: {format_size(old)} → {format_size(new)}")
            QMessageBox.information(
                self, "完成",
                tr("patch_done_new", name=result.name,
                   old=format_size(old), new=format_size(new)))
        except PatchError as e:
            self.log.append(f"❌ {e}")
            QMessageBox.critical(self, tr("msg_error"), str(e))
        except Exception as e:
            self.log.append(f"❌ {e}")
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("patch_failed", err=str(e)))


class ConfigPackDialog(QDialog):
    def __init__(self, mode: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._pack: Optional[Path] = None
        title = (tr("pack_dialog_export") if mode == "export"
                 else tr("pack_dialog_import"))
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        hint_text = (tr("pack_export_hint") if self._mode == "export"
                     else tr("pack_import_hint"))
        hint = QLabel(hint_text)
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        row = QHBoxLayout()
        self.edit_path = QLineEdit()
        self.edit_path.setPlaceholderText(
            tr("pack_path_import_ph") if self._mode == "import"
            else tr("pack_path_export_ph"))
        row.addWidget(self.edit_path, 1)
        b = QPushButton(tr("pack_browse"))
        b.clicked.connect(self._pick)
        row.addWidget(b)
        v.addLayout(row)

        self.check_covers = QCheckBox(tr("pack_incl_covers"))
        self.check_covers.setChecked(True)
        v.addWidget(self.check_covers)

        self.check_saves = QCheckBox(tr("pack_incl_saves"))
        self.check_saves.setChecked(True)
        v.addWidget(self.check_saves)

        self.check_stats = QCheckBox(tr("pack_incl_stats"))
        self.check_stats.setChecked(True)
        v.addWidget(self.check_stats)

        if self._mode == "import":
            self.check_merge = QCheckBox(tr("pack_merge"))
            self.check_merge.setChecked(True)
            v.addWidget(self.check_merge)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        v.addWidget(self.log)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(
            tr("pack_do_export") if self._mode == "export"
            else tr("pack_do_import"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("msg_cancel"))
        btns.accepted.connect(self._go)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _pick(self):
        if self._mode == "export":
            fp, _ = QFileDialog.getSaveFileName(
                self, tr("pack_dialog_export"),
                str(EXPORT_DIR / f"mikan_config_{time.strftime('%Y%m%d')}.mikanpack"),
                "mikan 配置包 (*.mikanpack);;所有文件 (*)")
        else:
            fp, _ = QFileDialog.getOpenFileName(
                self, tr("pack_dialog_import"), str(Path.home()),
                "mikan 配置包 (*.mikanpack *.zip);;所有文件 (*)")
        if fp:
            self.edit_path.setText(fp)

    def _go(self):
        path_str = self.edit_path.text().strip()
        if not path_str:
            QMessageBox.warning(self, tr("msg_warning"), "请选择文件路径")
            return
        path = Path(path_str)
        try:
            if self._mode == "export":
                out = export_config_pack(
                    path,
                    include_covers=self.check_covers.isChecked(),
                    include_saves=self.check_saves.isChecked(),
                    include_stats=self.check_stats.isChecked(),
                )
                self.log.append(f"✅ 已导出: {out}")
                size = format_size(out.stat().st_size)
                self.log.append(f"   大小: {size}")
                QMessageBox.information(
                    self, tr("msg_info"),
                    tr("pack_exported", path=str(out), size=size))
                self._pack = out
                self.accept()
            else:
                merge = self.check_merge.isChecked()
                info = import_config_pack(
                    path,
                    import_covers=self.check_covers.isChecked(),
                    import_saves=self.check_saves.isChecked(),
                    import_stats=self.check_stats.isChecked(),
                    merge=merge,
                )
                self.log.append(f"✅ 导入完成:")
                self.log.append(f"   配置: {info['config']}")
                self.log.append(f"   引擎: {info['engines']}")
                self.log.append(f"   游戏: {info['roms']}")
                self.log.append(f"   封面: {info['covers']}")
                self.log.append(f"   存档: {info['saves']}")
                QMessageBox.information(
                    self, tr("msg_info"),
                    tr("pack_imported",
                       config=info['config'], engines=info['engines'],
                       roms=info['roms'], covers=info['covers'],
                       saves=info['saves']))
                self.accept()
        except Exception as e:
            logger.exception("配置包操作失败")
            self.log.append(f"❌ {e}")
            QMessageBox.critical(self, tr("msg_error"), str(e))


class CoverScrapeDialog(QDialog):
    def __init__(self, games, parent=None):
        super().__init__(parent)
        self._games = list(games)
        self._worker = None
        self._failed = []
        self._auto_mode = False
        self._all_games = list(games)
        self.setWindowTitle(tr("scrape_title"))
        self.setMinimumSize(720, 560)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(10)
        note = QLabel(tr("scrape_source_note"))
        note.setObjectName("Hint")
        note.setWordWrap(True)
        v.addWidget(note)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("scrape_choose_source")))
        self.combo_source = QComboBox()
        self.combo_source.addItem(tr("scrape_source_auto"), "auto")
        self.combo_source.addItem(tr("scrape_source_libretro"), "libretro")
        self.combo_source.addItem(tr("scrape_source_sgdb"), "sgdb")
        top.addWidget(self.combo_source)

        top.addWidget(QLabel(tr("scrape_image_type")))
        self.combo_type = QComboBox()
        self.combo_type.addItem(tr("scrape_type_boxart"), "boxart")
        self.combo_type.addItem(tr("scrape_type_snap"), "snap")
        self.combo_type.addItem(tr("scrape_type_title"), "title")
        idx = self.combo_type.findData(SETTINGS.get("scrape_image_type", "boxart"))
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)
        top.addWidget(self.combo_type)

        self.check_overwrite = QCheckBox(tr("scrape_overwrite"))
        self.check_overwrite.setChecked(
            bool(SETTINGS.get("scrape_overwrite", False)))
        top.addWidget(self.check_overwrite)
        top.addStretch(1)
        v.addLayout(top)

        self.lbl_count = QLabel(tr("scrape_batch_count", n=len(self._games)))
        self.lbl_count.setObjectName("Hint")
        v.addWidget(self.lbl_count)

        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, len(self._games)))
        self.progress.setValue(0)
        v.addWidget(self.progress)

        self.lbl_cur = QLabel("")
        self.lbl_cur.setObjectName("Hint")
        v.addWidget(self.lbl_cur)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        v.addWidget(self.log, 1)

        row = QHBoxLayout()
        self.btn_start = QPushButton(tr("scrape_start"))
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.clicked.connect(self._start)
        row.addWidget(self.btn_start)

        self.btn_close = QPushButton(tr("scrape_close"))
        self.btn_close.clicked.connect(self._on_close)
        row.addWidget(self.btn_close)

        self.btn_retry = QPushButton(tr("scrape_retry_failed"))
        self.btn_retry.setEnabled(False)
        self.btn_retry.clicked.connect(self._retry_failed)
        row.addWidget(self.btn_retry)

        row.addStretch(1)
        v.addLayout(row)

    def _make_worker(self, games: list, force_source: str = ""):
        source = force_source or self.combo_source.currentData() or "auto"
        img_type = self.combo_type.currentData() or "boxart"
        overwrite = self.check_overwrite.isChecked()
        SETTINGS["scrape_image_type"] = img_type
        SETTINGS["scrape_overwrite"] = overwrite
        save_settings()

        if source == "sgdb":
            key = SETTINGS.get("steamgriddb_api_key", "").strip()
            return SteamGridDBScraperWorker(games, key, img_type, overwrite)
        elif source == "libretro":
            return LibretroScraperWorker(games, img_type, overwrite)
        else:
            return LibretroScraperWorker(games, img_type, overwrite)

    def _start(self):
        if not self._games:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("scrape_batch_none"))
            return
        self._auto_mode = (self.combo_source.currentData() or "auto") == "auto"
        self._all_games = list(self._games)
        self._start_worker(self._games, force_source="")

    def _start_worker(self, games, force_source: str = ""):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, tr("msg_info"),
                                    "上一次刮削还在进行中，请稍候。")
            return

        self.log.clear()
        self.progress.setRange(0, max(1, len(games)))
        self.progress.setValue(0)
        self.btn_start.setEnabled(False)
        self.btn_retry.setEnabled(False)

        self._worker = self._make_worker(games, force_source=force_source)
        self._worker.progress.connect(self._on_progress)
        self._worker.one_done.connect(self._on_one)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, cur, total):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(cur)

    def _on_one(self, path, ok, msg):
        g = None
        for x in self._all_games:
            if x.path == path:
                g = x
                break
        name = g.name if g else Path(path).stem
        if ok:
            self.log.append(tr("scrape_ok", name=name) + f"  {msg}")
        else:
            self.log.append(tr("scrape_fail", name=name) + f"  {msg}")

    def _on_done(self, ok, fail, failed):
        self._failed = list(failed or [])
        if (self._auto_mode
                and self._failed
                and SETTINGS.get("steamgriddb_api_key", "").strip()):
            retry_games = [g for g, _ in self._failed]
            self._auto_mode = False
            self.log.append("")
            self.log.append(
                f"Libretro 未命中 {len(retry_games)} 个，改用 SteamGridDB 兜底…")
            QTimer.singleShot(
                200,
                lambda: self._start_worker(retry_games, force_source="sgdb"))
            return

        self.btn_start.setEnabled(True)
        self.btn_retry.setEnabled(len(self._failed) > 0)
        self.log.append("")
        self.log.append(tr("scrape_done", ok=ok, fail=fail, skip=0))
        if self._failed:
            self.log.append(tr("scrape_failed_list") + ":")
            for g, reason in self._failed:
                self.log.append(f"  · {g.name}  ({reason})")

    def _retry_failed(self):
        if not self._failed:
            return
        self._auto_mode = False
        games = [g for g, _ in self._failed]
        self._start_worker(games, force_source="")

    def _on_close(self):
        w = self._worker
        if w is not None and w.isRunning():
            try:
                if hasattr(w, "stop"):
                    w.stop()
            except Exception:
                pass
            try:
                if not w.wait(3000):
                    w.terminate()
                    w.wait(1000)
            except Exception:
                pass
        self.accept()

    def closeEvent(self, event):
        w = self._worker
        if w is not None and w.isRunning():
            try:
                if hasattr(w, "stop"):
                    w.stop()
            except Exception:
                pass
            try:
                if not w.wait(3000):
                    w.terminate()
                    w.wait(1000)
            except Exception:
                pass
        super().closeEvent(event)


class ImportDialog(QDialog):
    def __init__(self, mode: str, engines_json: dict, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._engines_json = engines_json
        self._source = None
        self._is_archive = False
        self._worker = None
        self.setWindowTitle(tr("import_engine_title") if mode == "engine"
                            else tr("import_game_title"))
        self.setMinimumWidth(640)
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
        self.log_view.setMaximumHeight(240)
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
        d = QFileDialog.getExistingDirectory(
            self, tr("import_pick_folder"), str(DATA_DIR))
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
            self._worker = EngineImportWorker(
                self._source, self._engines_json, self._is_archive)
            self._worker.progress.connect(self._on_progress)
            self._worker.done.connect(self._on_engine_done)
            self._worker.fail.connect(self._on_fail)
        else:
            self._worker = GameImportWorker(
                self._source, self._engines_json, self._is_archive)
            self._worker.progress.connect(self._on_progress)
            self._worker.done.connect(self._on_game_done)
            self._worker.fail.connect(self._on_fail)
        self._worker.finished.connect(lambda: self.progress.setVisible(False))
        self._worker.start()

    def _on_progress(self, msg):
        self.lbl_status.setText(msg)
        self.log_view.append(msg)

    def _on_engine_done(self, installed, unmatched, all_exes):
        if installed:
            self.log_view.append(tr("import_found", n=len(installed)))
            engines = load_installed()
            for cfg in installed:
                engines = [e for e in engines
                           if not (e.platform == cfg.platform
                                   and e.engine == cfg.engine)]
                engines.append(cfg)
                self.log_view.append(f"  • {cfg.platform_name} / {cfg.engine}")
            save_installed(engines)
            self.accept()
            return
        if unmatched and all_exes:
            self.log_view.append(f"⚠️ {tr('import_not_found')}")
            dlg = ManualEngineDialog(all_exes, self._engines_json, self)
            if dlg.exec() == QDialog.Accepted:
                r = dlg.result_data()
                if r:
                    try:
                        cfg = install_manual_engine(
                            Path(r["exe"]), r["platform"], r["engine"],
                            r["launch_template"], r["platform_display"])
                        engines = load_installed()
                        engines = [e for e in engines
                                   if not (e.platform == cfg.platform
                                           and e.engine == cfg.engine)]
                        engines.append(cfg)
                        save_installed(engines)
                        self.accept()
                        return
                    except Exception as e:
                        QMessageBox.critical(self, tr("msg_error"), str(e))
        elif not all_exes:
            self.log_view.append("⚠️ 没有找到任何 .exe，请检查压缩包内容。")
        self.accept()

    def _on_game_done(self, games, skipped):
        if not games:
            if skipped:
                self.log_view.append(tr("rom_import_skipped", n=skipped))
            self.accept()
            return

        self.log_view.append(tr("rom_import_done", n=len(games)))

        existing = load_games()
        existing_keys = {}
        for g in existing:
            try:
                sz = Path(g.path).stat().st_size
            except Exception:
                sz = g.size
            existing_keys[(g.name.lower(), sz)] = g

        dup = []
        fresh = []
        for g in games:
            try:
                sz = Path(g.path).stat().st_size
            except Exception:
                sz = g.size
            k = (g.name.lower(), sz)
            if k in existing_keys:
                dup.append((g, existing_keys[k]))
            else:
                fresh.append(g)

        if dup:
            dlg = DupResolveDialog(dup, self)
            if dlg.exec() == QDialog.Accepted:
                keep, skip, overwrite = dlg.result_action()
                if overwrite:
                    for new_g, old_g in dup:
                        existing = [x for x in existing
                                    if x.path != old_g.path]
                        fresh.append(new_g)
                elif keep:
                    fresh.extend(g for g, _ in dup)

        if fresh:
            dlg = PlatformConfirmDialog(fresh, self._engines_json, self)
            if dlg.exec() == QDialog.Accepted:
                fresh = dlg.result_games()
            paths = {g.path for g in existing}
            for g in fresh:
                if g.path in paths:
                    continue
                existing.append(g)

        save_games(existing)
        if skipped:
            self.log_view.append(tr("rom_import_skipped", n=skipped))
        self.accept()

    def _on_fail(self, err):
        self.progress.setVisible(False)
        self.log_view.append(f"❌ {tr('import_failed', err=err)}")
        QMessageBox.critical(self, tr("msg_error"), err)


class DownloadDialog(QDialog):
    def __init__(self, engines_json: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("download_title"))
        self.setMinimumSize(780, 640)
        self._engines_json = engines_json
        self._worker = None
        self._test_worker = None
        self._current_engine = None
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
            if platform.startswith("_"):
                continue
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
            if platform.startswith("_"):
                continue
            for engine_name, cfg in pcfg.get("engines", {}).items():
                if cfg.get("url", "manual") != "manual":
                    continue
                box = QGroupBox(
                    f"[{pcfg.get('platform_name', platform)}] {engine_name}")
                bl = QVBoxLayout(box)
                bl.addWidget(QLabel(
                    f"版本: {cfg.get('version', '未知')}\n"
                    f"备注: {cfg.get('note', '')}"))
                site = cfg.get("official_site", "")
                if site:
                    btn = QPushButton(f"{tr('download_open_site')}: {site}")
                    btn.clicked.connect(
                        lambda _=False, s=site: self._open_site(s))
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
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("open_failed", e=str(e)))

    def _test_mirrors(self):
        items = self.list_auto.selectedItems()
        if not items:
            QMessageBox.information(self, tr("msg_info"),
                                    "请先在列表里选中一个模拟器")
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
            QMessageBox.information(self, tr("msg_info"),
                                    "请先在列表里选中一个模拟器")
            return
        platform, engine_name, cfg = items[0].data(Qt.UserRole)
        url = cfg.get("url", "")
        archive = cfg.get("archive", "zip")
        if not url or url == "manual":
            return
        reply = QMessageBox.question(self, tr("msg_confirm"),
                                     tr("download_confirm",
                                        name=f"{platform}/{engine_name}"),
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        ext = ".zip"
        if archive == "7z":
            ext = ".7z"
        elif archive in ("7z_sfx", "bare_exe"):
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
            + tr("download_speed", speed=human_size(int(speed)),
                 eta=human_eta(remain)))

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
        QMessageBox.critical(self, tr("msg_error"),
                             tr("download_failed", err=err))

    def _on_dl_finished(self):
        self.progress.setVisible(False)
        self.btn_start.setEnabled(True)

    def _install_downloaded(self, archive: Path):
        if not self._current_engine:
            raise RuntimeError("内部错误")
        platform, engine_name, cfg = self._current_engine
        archive_type = cfg.get("archive", "zip")

        if archive_type == "bare_exe":
            target_dir = ENGINE_DOWNLOAD_DIR / platform / engine_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_exe = target_dir / archive.name
            shutil.copy2(archive, target_exe)
            installed = EmulatorConfig(
                platform=platform, engine=engine_name,
                platform_name=cfg.get("platform_name", platform),
                engine_path=str(target_exe), engine_dir=str(target_dir),
                version=cfg.get("version", ""), official=True,
                source="download",
                launch_template=cfg.get("launch_template", "{exe} \"{rom}\""),
                installed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                url=cfg.get("url", ""), url_type="direct",
                github_repo=cfg.get("github_repo", ""),
                archive="bare_exe",
            )
            engines = load_installed()
            engines = [e for e in engines
                       if not (e.platform == installed.platform
                               and e.engine == installed.engine)]
            engines.append(installed)
            save_installed(engines)
            try:
                archive.unlink()
            except Exception:
                pass
            return

        tmp_root = Path(tempfile.mkdtemp(prefix="mikan_emu_dl_", dir=str(TEMP_DIR)))
        try:
            if archive_type == "7z_sfx":
                try:
                    sp.run([str(archive), f"-o{tmp_root}", "-y"],
                           check=True, timeout=600,
                           creationflags=getattr(sp, "CREATE_NO_WINDOW", 0))
                except Exception:
                    import py7zr
                    with py7zr.SevenZipFile(archive, mode="r") as z:
                        z.extractall(tmp_root)
            else:
                extract_archive(archive, tmp_root)

            files = scan_files(tmp_root)
            matches = match_engines(
                files, {platform: {"engines": {engine_name: cfg}}})
            if not matches:
                raise RuntimeError(
                    f"解压后没找到 {engine_name} 的可执行文件")

            installed = install_engine_from_match(
                matches[0], tmp_root, "download")
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
# 35. ★ v1.8.0：KeyMapDialog（虚拟按键映射编辑器）
# ============================================================
class KeyMapDialog(QDialog):
    """按键映射编辑器。

    - 表格：物理按键 / 发送给模拟器 / 启用 / 备注
    - 「录入」按钮：点击后按下键盘，自动填入物理按键
    - 支持全局映射 + 按游戏覆盖（下拉切换）
    - 保存到 keymap.json / keymap_games.json
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._km = get_keymapper()
        self._recording_row = -1
        self._recording_btn = None
        self._current_game_path = ""   # "" = 全局
        self.setWindowTitle(tr("keymap_title"))
        self.setMinimumSize(820, 560)
        self._build_ui()
        self._load_global()
        self.setFocusPolicy(Qt.StrongFocus)

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(10)

        # 顶部说明
        hint = QLabel(tr("settings_keymap_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        if not HAS_KEYBOARD:
            warn = QLabel(tr("keymap_no_keyboard"))
            warn.setStyleSheet("color:#c42b1c;")
            warn.setWordWrap(True)
            v.addWidget(warn)

        # 作用域选择
        row_scope = QHBoxLayout()
        row_scope.addWidget(QLabel("作用域:"))
        self.combo_scope = QComboBox()
        self.combo_scope.addItem("🌐 全局（所有游戏）", "")
        games = load_games()
        for g in sorted(games, key=lambda x: x.name.lower()):
            self.combo_scope.addItem(f"🎮 {g.name}", g.path)
        self.combo_scope.currentIndexChanged.connect(self._on_scope_changed)
        row_scope.addWidget(self.combo_scope, 1)
        row_scope.addStretch(1)
        v.addLayout(row_scope)

        # 表格
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            tr("keymap_col_physical"),
            tr("keymap_col_virtual"),
            tr("keymap_record_btn"),
            tr("keymap_col_enabled"),
            tr("keymap_col_note"),
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        v.addWidget(self.table, 1)

        # 按钮
        row = QHBoxLayout()
        b_add = QPushButton(tr("keymap_add"))
        b_add.setObjectName("PrimaryBtn")
        b_add.clicked.connect(self._add_row)
        row.addWidget(b_add)

        b_del = QPushButton(tr("keymap_remove"))
        b_del.clicked.connect(self._del_row)
        row.addWidget(b_del)

        b_clear = QPushButton(tr("keymap_clear"))
        b_clear.clicked.connect(self._clear_all)
        row.addWidget(b_clear)

        row.addStretch(1)

        b_save = QPushButton(tr("keymap_save"))
        b_save.setObjectName("PrimaryBtn")
        b_save.clicked.connect(self._save)
        row.addWidget(b_save)

        b_close = QPushButton(tr("msg_cancel"))
        b_close.clicked.connect(self.reject)
        row.addWidget(b_close)
        v.addLayout(row)

        # 测试区
        test_grp = QGroupBox(tr("keymap_test"))
        ft = QVBoxLayout(test_grp)
        ft.addWidget(QLabel(tr("keymap_test_hint")))
        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("在此按键…")
        ft.addWidget(self.test_input)
        v.addWidget(test_grp)

    # ---------- 录入 ----------
    def _start_record(self, row: int, btn: QPushButton):
        if not HAS_KEYBOARD:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("keymap_no_keyboard"))
            return
        self._recording_row = row
        self._recording_btn = btn
        btn.setText("…")
        btn.setEnabled(False)
        self.setFocus()
        self.grabKeyboard()
        self.setWindowTitle(tr("keymap_recording"))

    def _stop_record(self):
        self._recording_row = -1
        if self._recording_btn is not None:
            try:
                self._recording_btn.setText(tr("keymap_record_btn"))
                self._recording_btn.setEnabled(True)
            except Exception:
                pass
        self._recording_btn = None
        self.releaseKeyboard()
        self.setWindowTitle(tr("keymap_title"))

    def keyPressEvent(self, event):
        if self._recording_row >= 0:
            key_name = qt_key_to_name(event.key())
            if key_name:
                item = self.table.item(self._recording_row, 0)
                if item is None:
                    item = QTableWidgetItem("")
                    self.table.setItem(self._recording_row, 0, item)
                item.setText(key_name)
                self._stop_record()
                self.statusBar_msg(tr("keymap_recorded", key=key_name))
                return
            event.ignore()
            return
        super().keyPressEvent(event)

    def statusBar_msg(self, msg: str):
        # 没有状态栏，用窗口标题短暂显示
        old = self.windowTitle()
        self.setWindowTitle(f"{old} — {msg}")

    # ---------- 表格操作 ----------
    def _add_row(self, physical="", virtual="", enabled=True, note=""):
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QTableWidgetItem(physical))

        v_item = QTableWidgetItem(virtual)
        self.table.setItem(row, 1, v_item)

        btn = QPushButton(tr("keymap_record_btn"))
        btn.setFixedWidth(70)
        btn.clicked.connect(
            lambda _=False, r=row, b=btn: self._start_record(r, b))
        self.table.setCellWidget(row, 2, btn)

        cb = QCheckBox()
        cb.setChecked(enabled)
        cb_wrap = QWidget()
        cb_layout = QHBoxLayout(cb_wrap)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setAlignment(Qt.AlignCenter)
        cb_layout.addWidget(cb)
        self.table.setCellWidget(row, 3, cb_wrap)
        cb.setProperty("row", row)

        self.table.setItem(row, 4, QTableWidgetItem(note))

    def _del_row(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.removeRow(row)

    def _clear_all(self):
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            "清空当前作用域的所有映射？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.table.setRowCount(0)

    # ---------- 加载/保存 ----------
    def _on_scope_changed(self, _idx):
        self._current_game_path = self.combo_scope.currentData() or ""
        if self._current_game_path:
            self._load_game(self._current_game_path)
        else:
            self._load_global()

    def _load_global(self):
        self.table.setRowCount(0)
        for e in self._km.get_global_map():
            self._add_row(e.physical, e.virtual, e.enabled, e.note)

    def _load_game(self, game_path: str):
        self.table.setRowCount(0)
        for e in self._km.get_game_map(game_path):
            self._add_row(e.physical, e.virtual, e.enabled, e.note)

    def _collect_rows(self) -> list:
        entries = []
        seen = set()
        for row in range(self.table.rowCount()):
            phys_item = self.table.item(row, 0)
            phys = (phys_item.text().strip() if phys_item else "")
            if not phys:
                continue
            phys_norm = normalize_key_name(phys)
            if not phys_norm or phys_norm in seen:
                continue
            seen.add(phys_norm)

            virt_item = self.table.item(row, 1)
            virt = (virt_item.text().strip() if virt_item else "")
            if not virt:
                continue

            cb_wrap = self.table.cellWidget(row, 3)
            enabled = True
            if cb_wrap:
                cb = cb_wrap.findChild(QCheckBox)
                if cb:
                    enabled = cb.isChecked()

            note_item = self.table.item(row, 4)
            note = note_item.text().strip() if note_item else ""

            entries.append(KeyMapEntry(phys_norm, virt, enabled, note))
        return entries

    def _save(self):
        entries = self._collect_rows()

        # 查重
        seen = set()
        for e in entries:
            if e.physical in seen:
                QMessageBox.warning(
                    self, tr("msg_warning"),
                    tr("keymap_duplicate", key=e.physical))
                return
            seen.add(e.physical)

        if self._current_game_path:
            self._km.set_game_map(self._current_game_path, entries)
        else:
            self._km.set_global_map(entries)

        self._km.save_to_files()

        # 重启 KeyMapper（让新映射生效）
        try:
            self._km.stop()
            if SETTINGS.get("keymap_enabled", False) and HAS_KEYBOARD:
                self._km.start()
        except Exception as e:
            logger.debug(f"重启 KeyMapper 失败: {e}")

        QMessageBox.information(self, tr("msg_info"), tr("keymap_saved"))

    def closeEvent(self, event):
        if self._recording_row >= 0:
            self._stop_record()
        super().closeEvent(event)

# ============================================================
# 36. ★ v1.8.0：ParamSchemaDialog（模拟器参数动态表单）
# ============================================================
class ParamSchemaDialog(QDialog):
    """根据引擎的 param_schema 动态生成参数表单。

    - 每个参数一行：label + 输入控件（bool=勾选, int=SpinBox,
      choice=ComboBox, text/file/dir=QLineEdit + 浏览按钮）
    - 底部显示命令行预览
    - 保存后写入 game.param_values
    """

    def __init__(self, engine: "EmulatorConfig", game: "GameEntry",
                 parent=None):
        super().__init__(parent)
        self._engine = engine
        self._game = game
        self._schema = get_param_schema(engine)
        self._widgets: dict = {}   # key -> (widget, getter)
        self._result: dict = {}
        self.setWindowTitle(
            f"{tr('param_schema_title')} - {engine.engine}")
        self.setMinimumSize(620, 560)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(10)

        head = QLabel(
            f"<b>{self._engine.engine}</b>  "
            f"<span style='color:#767676;'>"
            f"({self._game.name})</span>")
        head.setTextFormat(Qt.RichText)
        v.addWidget(head)

        hint = QLabel(tr("param_schema_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        if not self._schema:
            empty = QLabel(tr("param_schema_empty"))
            empty.setObjectName("Hint")
            empty.setWordWrap(True)
            v.addWidget(empty)
            v.addStretch(1)
            btns = QDialogButtonBox(QDialogButtonBox.Close)
            btns.button(QDialogButtonBox.Close).setText(tr("msg_ok"))
            btns.button(QDialogButtonBox.Close).setObjectName("PrimaryBtn")
            btns.rejected.connect(self.reject)
            btns.button(QDialogButtonBox.Close).clicked.connect(self.reject)
            v.addWidget(btns)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(10)

        for item in self._schema:
            if not isinstance(item, dict):
                continue
            key = item.get("key", "")
            if not key:
                continue
            label = item.get("label", key)
            typ = item.get("type", "text")
            default = item.get("default")

            if typ == "bool":
                w = QCheckBox()
                w.setChecked(bool(default))
                form.addRow(label, w)
                self._widgets[key] = (w, lambda x=w: x.isChecked())

            elif typ == "int":
                w = QSpinBox()
                w.setRange(int(item.get("min", -999999)),
                           int(item.get("max", 999999)))
                try:
                    w.setValue(int(default) if default is not None else 0)
                except Exception:
                    w.setValue(0)
                form.addRow(label, w)
                self._widgets[key] = (w, lambda x=w: x.value())

            elif typ == "choice":
                w = QComboBox()
                options = item.get("options") or []
                for opt in options:
                    w.addItem(str(opt), str(opt))
                if default is not None:
                    idx = w.findData(str(default))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                form.addRow(label, w)
                self._widgets[key] = (
                    w, lambda x=w: x.currentData())

            elif typ in ("file", "dir"):
                row_w = QWidget()
                hl = QHBoxLayout(row_w)
                hl.setContentsMargins(0, 0, 0, 0)
                hl.setSpacing(6)
                edit = QLineEdit()
                edit.setText(str(default or ""))
                hl.addWidget(edit, 1)
                btn = QPushButton("…")
                btn.setFixedWidth(36)
                if typ == "file":
                    btn.clicked.connect(
                        lambda _=False, e=edit: self._pick_file(e))
                else:
                    btn.clicked.connect(
                        lambda _=False, e=edit: self._pick_dir(e))
                hl.addWidget(btn)
                form.addRow(label, row_w)
                self._widgets[key] = (edit, lambda x=edit: x.text().strip())

            else:  # text
                w = QLineEdit()
                w.setText(str(default or ""))
                form.addRow(label, w)
                self._widgets[key] = (w, lambda x=w: x.text().strip())

        scroll.setWidget(content)
        v.addWidget(scroll, 1)

        # 命令行预览
        preview_grp = QGroupBox(tr("param_schema_preview"))
        pv = QVBoxLayout(preview_grp)
        self.edit_preview = QTextEdit()
        self.edit_preview.setReadOnly(True)
        self.edit_preview.setMaximumHeight(90)
        self.edit_preview.setStyleSheet(
            "font-family:'Cascadia Mono','Consolas',monospace;font-size:12px;")
        pv.addWidget(self.edit_preview)
        v.addWidget(preview_grp)

        # 每次改动刷新预览
        for w, getter in self._widgets.values():
            try:
                if isinstance(w, QCheckBox):
                    w.toggled.connect(self._refresh_preview)
                elif isinstance(w, QSpinBox):
                    w.valueChanged.connect(self._refresh_preview)
                elif isinstance(w, QComboBox):
                    w.currentIndexChanged.connect(self._refresh_preview)
                elif isinstance(w, QLineEdit):
                    w.textChanged.connect(self._refresh_preview)
            except Exception:
                pass

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("param_schema_apply"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("msg_cancel"))
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)

        # 恢复默认按钮
        btn_reset = QPushButton(tr("param_schema_reset"))
        btn_reset.clicked.connect(self._reset_defaults)
        btns.addButton(btn_reset, QDialogButtonBox.ResetRole)

        v.addWidget(btns)

    def _pick_file(self, edit: QLineEdit):
        fp, _ = QFileDialog.getOpenFileName(
            self, "选择文件", str(Path.home()), "所有文件 (*)")
        if fp:
            edit.setText(fp)

    def _pick_dir(self, edit: QLineEdit):
        d = QFileDialog.getExistingDirectory(
            self, "选择目录", str(Path.home()))
        if d:
            edit.setText(d)

    def _reset_defaults(self):
        for item in self._schema:
            key = item.get("key", "")
            if key not in self._widgets:
                continue
            w, _getter = self._widgets[key]
            default = item.get("default")
            typ = item.get("type", "text")
            try:
                if typ == "bool":
                    w.setChecked(bool(default))
                elif typ == "int":
                    w.setValue(int(default) if default is not None else 0)
                elif typ == "choice":
                    idx = w.findData(str(default))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                else:
                    w.setText(str(default or ""))
            except Exception:
                pass
        self._refresh_preview()

    def _load_values(self):
        """把 game.param_values 填回控件。"""
        values = getattr(self._game, "param_values", {}) or {}
        for key, (w, _getter) in self._widgets.items():
            if key not in values:
                continue
            val = values[key]
            try:
                if isinstance(w, QCheckBox):
                    w.setChecked(bool(val))
                elif isinstance(w, QSpinBox):
                    w.setValue(int(val))
                elif isinstance(w, QComboBox):
                    idx = w.findData(str(val))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                elif isinstance(w, QLineEdit):
                    w.setText(str(val))
            except Exception:
                pass
        self._refresh_preview()

    def _collect_values(self) -> dict:
        result = {}
        for key, (_w, getter) in self._widgets.items():
            try:
                result[key] = getter()
            except Exception:
                pass
        return result

    def _refresh_preview(self, *_args):
        try:
            values = self._collect_values()
            args = _build_param_args(self._engine, values)
            # 用真实 exe / rom 占位
            base = _split_cmd(
                resolve_engine_field(
                    self._engine, "launch_template", "{exe} \"{rom}\""))
            preview = " ".join(base) + (" " + " ".join(args) if args else "")
            self.edit_preview.setPlainText(preview)
        except Exception as e:
            self.edit_preview.setPlainText(f"预览失败: {e}")

    def _on_save(self):
        self._result = self._collect_values()
        self.accept()

    def result_values(self) -> dict:
        return self._result


# ============================================================
# 37. GameConfigCenterDialog（统一配置中心）
# ============================================================
class GameConfigCenterDialog(QDialog):
    launch_requested = Signal(object)
    open_folder_requested = Signal(object)
    engine_settings_requested = Signal(object)

    def __init__(self, game: GameEntry, parent=None):
        super().__init__(parent)
        self._game = game
        self._dirty = False
        self.setWindowTitle(f"{tr('game_config_title')} - {game.name}")
        self.setMinimumSize(760, 660)
        self._build_ui()
        self._reload()
        QTimer.singleShot(0, self._auto_scan)

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setSpacing(10)

        head = QFrame()
        head.setObjectName("ResourceCard")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(12, 10, 12, 10)

        cover = find_cover(self._game.name)
        if cover:
            pix = QPixmap(str(cover))
            if not pix.isNull():
                pix = pix.scaled(48, 64, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
                lbl_cover = QLabel()
                lbl_cover.setPixmap(pix)
                hl.addWidget(lbl_cover)

        info = QVBoxLayout()
        info.setSpacing(2)
        title = QLabel(f"<b>{self._game.name}</b>")
        title.setTextFormat(Qt.RichText)
        info.addWidget(title)
        sub = QLabel(
            f"{self._game.custom_platform or self._game.platform}  ·  "
            f"{format_size(self._game.size)}  ·  "
            f"时长 {human_duration(self._game.play_seconds)}")
        sub.setObjectName("Hint")
        info.addWidget(sub)
        path_lbl = QLabel(self._game.path)
        path_lbl.setObjectName("Hint")
        path_lbl.setWordWrap(True)
        info.addWidget(path_lbl)
        hl.addLayout(info, 1)

        btn_launch = QPushButton(tr("ctx_launch"))
        btn_launch.setObjectName("PrimaryBtn")
        btn_launch.clicked.connect(
            lambda: self.launch_requested.emit(self._game))
        hl.addWidget(btn_launch)

        v.addWidget(head)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_launch_tab(),
                         tr("game_config_tab_launch"))
        self.tabs.addTab(self._build_patch_tab(),
                         tr("game_config_tab_patch"))
        self.tabs.addTab(self._build_cover_tab(),
                         tr("game_config_tab_cover"))
        self.tabs.addTab(self._build_bios_tab(),
                         tr("game_config_tab_bios"))
        self.tabs.addTab(self._build_cheat_tab(),
                         tr("game_config_tab_cheat"))
        self.tabs.addTab(self._build_save_tab(),
                         tr("game_config_tab_save"))
        self.tabs.addTab(self._build_info_tab(),
                         tr("game_config_tab_info"))
        v.addWidget(self.tabs, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.button(QDialogButtonBox.Close).setText(tr("game_config_close"))
        btns.button(QDialogButtonBox.Close).setObjectName("PrimaryBtn")
        btns.rejected.connect(self.accept)
        btns.button(QDialogButtonBox.Close).clicked.connect(self.accept)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btns)
        v.addLayout(row)

    def _persist(self):
        games = load_games()
        for g in games:
            if g.path == self._game.path:
                for f in GameEntry.__dataclass_fields__:
                    setattr(g, f, getattr(self._game, f))
                break
        save_games(games)

    def _reload(self):
        for g in load_games():
            if g.path == self._game.path:
                self._game = g
                break

    def _auto_scan(self):
        try:
            self._scan_patches()
            self._refresh_patch_state()
        except Exception as e:
            logger.debug(f"补丁扫描失败: {e}")
        try:
            self._scan_cheats()
        except Exception as e:
            logger.debug(f"金手指扫描失败: {e}")
        try:
            self._refresh_cover_preview()
        except Exception as e:
            logger.debug(f"封面刷新失败: {e}")
        self._update_tab_badges()

    def _update_tab_badges(self):
        def _set(idx, text, badge):
            self.tabs.setTabText(idx, f"{text}{badge}")

        has_patch = any(
            self.list_patches.item(i).data(Qt.UserRole)
            for i in range(self.list_patches.count()))
        _set(1, tr("game_config_tab_patch"), "  ✱" if has_patch else "")

        cover = find_cover(self._game.name)
        _set(2, tr("game_config_tab_cover"), "" if cover else "  (缺)")

        engine = self._resolve_engine_silent()
        if engine and engine.bios_required and not self._game.bios_file:
            _set(3, tr("game_config_tab_bios"), "  ⚠")

        has_cheat = any(
            self.list_cheats.item(i).data(Qt.UserRole)
            for i in range(self.list_cheats.count()))
        _set(4, tr("game_config_tab_cheat"), "  ★" if has_cheat else "")

        if engine and not get_save_path(engine.engine):
            _set(5, tr("game_config_tab_save"), "  ⚠")

    # ---------- 启动 Tab ----------
    def _build_launch_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        grp_e = QGroupBox(tr("config_engine_group"))
        fe = QVBoxLayout(grp_e)
        self.radio_auto = QRadioButton(tr("config_auto"))
        self.radio_manual = QRadioButton(tr("config_manual"))
        grp = QButtonGroup(self)
        grp.addButton(self.radio_auto, 0)
        grp.addButton(self.radio_manual, 1)
        fe.addWidget(self.radio_auto)
        fe.addWidget(self.radio_manual)

        self.combo_engine = QComboBox()
        for e in load_installed():
            self.combo_engine.addItem(
                f"[{e.platform_name}] {e.engine} {e.version}".strip(),
                f"{e.platform}/{e.engine}")
        fe.addWidget(self.combo_engine)
        self.radio_auto.toggled.connect(self._on_launch_changed)
        self.radio_manual.toggled.connect(self._on_launch_changed)
        self.combo_engine.currentIndexChanged.connect(
            self._on_launch_changed)
        v.addWidget(grp_e)

        grp_p = QGroupBox(tr("config_platform_override"))
        fp = QVBoxLayout(grp_p)
        hint = QLabel(tr("config_platform_override_hint"))
        hint.setObjectName("Hint")
        fp.addWidget(hint)
        self.combo_override = QComboBox()
        self.combo_override.addItem(tr("config_platform_none"), "")
        for p, pcfg in load_engines_json().items():
            if p.startswith("_"):
                continue
            self.combo_override.addItem(pcfg.get("platform_name", p), p)
        self.combo_override.currentIndexChanged.connect(
            self._on_launch_changed)
        fp.addWidget(self.combo_override)
        v.addWidget(grp_p)

        grp_perf = QGroupBox(tr("config_perf_group"))
        fperf = QVBoxLayout(grp_perf)
        self.combo_perf = QComboBox()
        self.combo_perf.addItem(tr("config_perf_none"), "")
        self._reload_perf_combo()
        self.combo_perf.currentIndexChanged.connect(self._on_launch_changed)
        fperf.addWidget(self.combo_perf)
        hint_perf = QLabel(tr("config_perf_hint"))
        hint_perf.setObjectName("Hint")
        hint_perf.setWordWrap(True)
        fperf.addWidget(hint_perf)
        v.addWidget(grp_perf)

        grp_pr = QGroupBox(tr("config_profile_group"))
        fpr = QVBoxLayout(grp_pr)
        self.combo_profile = QComboBox()
        self.combo_profile.addItem(tr("config_profile_none"), "")
        for name in (SETTINGS.get("launch_profiles") or {}):
            self.combo_profile.addItem(name, name)
        self.combo_profile.currentIndexChanged.connect(
            self._on_launch_changed)
        fpr.addWidget(self.combo_profile)
        hint_pr = QLabel(tr("config_profile_hint"))
        hint_pr.setObjectName("Hint")
        fpr.addWidget(hint_pr)
        v.addWidget(grp_pr)

        grp_a = QGroupBox(tr("config_extra_args"))
        fa = QVBoxLayout(grp_a)
        self.edit_args = QLineEdit()
        self.edit_args.setPlaceholderText(tr("config_extra_args_ph"))
        self.edit_args.editingFinished.connect(self._on_launch_changed)
        fa.addWidget(self.edit_args)
        v.addWidget(grp_a)

        # ★ v1.8.0：参数 schema 按钮
        row_param = QHBoxLayout()
        btn_param = QPushButton("🎛 模拟器参数（schema）…")
        btn_param.setObjectName("PrimaryBtn")
        btn_param.clicked.connect(self._open_param_schema)
        row_param.addWidget(btn_param)
        row_param.addStretch(1)
        v.addLayout(row_param)

        row_btn = QHBoxLayout()
        btn_open_settings = QPushButton(tr("game_config_open_settings"))
        btn_open_settings.clicked.connect(self._open_engine_settings)
        row_btn.addWidget(btn_open_settings)
        row_btn.addStretch(1)
        v.addLayout(row_btn)

        v.addStretch(1)

        g = self._game
        if g.override_engine:
            self.radio_manual.setChecked(True)
            idx = self.combo_engine.findData(g.override_engine)
            if idx >= 0:
                self.combo_engine.setCurrentIndex(idx)
        else:
            self.radio_auto.setChecked(True)
        idx = self.combo_override.findData(g.override_platform or "")
        if idx >= 0:
            self.combo_override.setCurrentIndex(idx)
        idx = self.combo_profile.findData(getattr(g, "profile", "") or "")
        if idx >= 0:
            self.combo_profile.setCurrentIndex(idx)
        idx = self.combo_perf.findData(getattr(g, "perf_profile", "") or "")
        if idx >= 0:
            self.combo_perf.setCurrentIndex(idx)
        self.edit_args.setText(g.extra_args or "")

        return w

    def _reload_perf_combo(self):
        self.combo_perf.blockSignals(True)
        self.combo_perf.clear()
        self.combo_perf.addItem(tr("config_perf_none"), "")
        engine = self._resolve_engine_silent()
        if engine:
            profiles = get_perf_profiles(engine)
            for name in profiles:
                self.combo_perf.addItem(name, name)
            self.combo_perf.setEnabled(bool(profiles))
        else:
            self.combo_perf.setEnabled(False)
        self.combo_perf.blockSignals(False)

    def _on_launch_changed(self, *_):
        if self.radio_manual.isChecked():
            self._game.override_engine = self.combo_engine.currentData() or ""
        else:
            self._game.override_engine = ""
        self._game.override_platform = self.combo_override.currentData() or ""
        self._game.profile = self.combo_profile.currentData() or ""
        self._game.perf_profile = self.combo_perf.currentData() or ""
        self._game.extra_args = self.edit_args.text().strip()
        self._persist()
        # 引擎变了，刷新性能档位和参数按钮状态
        self._reload_perf_combo()

    def _open_param_schema(self):
        engine = self._resolve_engine_silent()
        if not engine:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("config_no_engine"))
            return
        if not get_param_schema(engine):
            QMessageBox.information(
                self, tr("msg_info"), tr("param_schema_empty"))
            return
        dlg = ParamSchemaDialog(engine, self._game, self)
        if dlg.exec() == QDialog.Accepted:
            self._game.param_values = dlg.result_values()
            self._persist()
            QMessageBox.information(self, tr("msg_info"),
                                    tr("param_schema_saved"))

    def _open_engine_settings(self):
        engine = self._resolve_engine_silent()
        if engine:
            self.engine_settings_requested.emit(engine)

    # ---------- 补丁 Tab ----------
    def _build_patch_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        hint = QLabel(tr("patch_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.lbl_patch_state = QLabel()
        self.lbl_patch_state.setObjectName("Hint")
        self.lbl_patch_state.setWordWrap(True)
        v.addWidget(self.lbl_patch_state)

        grp = QGroupBox("可用补丁")
        fg = QVBoxLayout(grp)

        self.list_patches = QListWidget()
        self.list_patches.setMinimumHeight(140)
        self.list_patches.itemDoubleClicked.connect(
            lambda _: self._apply_selected_patch())
        fg.addWidget(self.list_patches)

        row = QHBoxLayout()
        b_scan = QPushButton(tr("patch_scan"))
        b_scan.clicked.connect(self._scan_patches)
        row.addWidget(b_scan)
        b_browse = QPushButton(tr("patch_browse"))
        b_browse.clicked.connect(self._pick_patch_file)
        row.addWidget(b_browse)
        b_apply = QPushButton(tr("patch_apply"))
        b_apply.setObjectName("PrimaryBtn")
        b_apply.clicked.connect(self._apply_selected_patch)
        row.addWidget(b_apply)
        row.addStretch(1)
        fg.addLayout(row)

        v.addWidget(grp)

        grp2 = QGroupBox(tr("patch_dir"))
        fg2 = QVBoxLayout(grp2)
        row2 = QHBoxLayout()
        self.edit_patch_dir = QLineEdit(SETTINGS.get("patch_dir", "") or "")
        self.edit_patch_dir.setPlaceholderText(tr("patch_dir_ph"))
        self.edit_patch_dir.editingFinished.connect(self._save_patch_dir)
        row2.addWidget(self.edit_patch_dir, 1)
        b_dir = QPushButton("…")
        b_dir.setFixedWidth(36)
        b_dir.clicked.connect(self._pick_patch_dir)
        row2.addWidget(b_dir)
        fg2.addLayout(row2)
        v.addWidget(grp2)

        v.addStretch(1)

        self._scan_patches()
        self._refresh_patch_state()
        return w

    def _scan_patches(self):
        self.list_patches.clear()
        rom = Path(self._game.path)
        dirs = [rom.parent]

        extra = SETTINGS.get("patch_dir", "").strip()
        if extra:
            p = Path(extra)
            if p.exists() and p.is_dir():
                dirs.append(p)

        stem_lower = rom.stem.lower()
        matched = []
        others = []
        seen = set()

        for d in dirs:
            for ext in (".ips", ".ups"):
                try:
                    for f in d.glob(f"*{ext}"):
                        if not f.is_file():
                            continue
                        if str(f) in seen:
                            continue
                        seen.add(str(f))
                        name_lower = f.stem.lower()
                        if (stem_lower in name_lower
                                or name_lower in stem_lower):
                            matched.append(f)
                        else:
                            others.append(f)
                except Exception:
                    pass

        def _add(f, is_match):
            item = QListWidgetItem()
            prefix = "⭐ " if is_match else "   "
            try:
                sz = format_size(f.stat().st_size)
            except Exception:
                sz = "?"
            item.setText(f"{prefix}{f.name}  ({sz})")
            item.setData(Qt.UserRole, str(f))
            item.setToolTip(str(f))
            if is_match:
                item.setForeground(QColor("#0f7b0f"))
            self.list_patches.addItem(item)

        for f in sorted(matched, key=lambda x: x.name.lower()):
            _add(f, True)
        for f in sorted(others, key=lambda x: x.name.lower()):
            _add(f, False)

        if self.list_patches.count() == 0:
            it = QListWidgetItem(tr("patch_none"))
            it.setFlags(Qt.NoItemFlags)
            self.list_patches.addItem(it)

    def _refresh_patch_state(self):
        g = self._game
        if getattr(g, "patched_from", ""):
            src = Path(g.patched_from)
            lines = [tr("patch_state_patched", src=src.name)]
            history = getattr(g, "patch_history", []) or []
            if history:
                lines.append(tr("patch_state_history"))
                for h in history:
                    lines.append(f"  · {Path(h.get('patch', '?')).name}"
                                 f"  @ {h.get('ts', '')}")
            self.lbl_patch_state.setText("\n".join(lines))
        else:
            self.lbl_patch_state.setText(tr("patch_state_clean"))

    def _save_patch_dir(self):
        SETTINGS["patch_dir"] = self.edit_patch_dir.text().strip()
        save_settings()
        self._scan_patches()

    def _pick_patch_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("patch_dir"), str(Path(self._game.path).parent))
        if d:
            self.edit_patch_dir.setText(d)
            self._save_patch_dir()

    def _pick_patch_file(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("patch_browse"), str(Path(self._game.path).parent),
            "ROM 补丁 (*.ips *.ups);;所有文件 (*)")
        if not fp:
            return
        f = Path(fp)
        item = QListWidgetItem(
            f"⭐ {f.name}  ({format_size(f.stat().st_size)})")
        item.setData(Qt.UserRole, str(f))
        item.setForeground(QColor("#0f7b0f"))
        self.list_patches.insertItem(0, item)
        self.list_patches.setCurrentItem(item)

    def _apply_selected_patch(self):
        item = self.list_patches.currentItem()
        if not item:
            QMessageBox.information(self, tr("msg_info"), "先选中一个补丁")
            return
        patch_path_str = item.data(Qt.UserRole)
        if not patch_path_str:
            return
        patch_path = Path(patch_path_str)
        rom = Path(self._game.path)

        try:
            info = (
                f"ROM: {rom.name}  ({format_size(rom.stat().st_size)})\n"
                f"补丁: {patch_path.name}  "
                f"({format_size(patch_path.stat().st_size)})")
        except Exception:
            info = f"ROM: {rom.name}\n补丁: {patch_path.name}"

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("patch_apply"))
        dv = QVBoxLayout(dlg)
        dv.addWidget(QLabel(info))
        dv.addSpacing(8)

        rb_overwrite = QRadioButton(tr("patch_overwrite"))
        rb_new = QRadioButton(tr("patch_new_file"))
        rb_new.setChecked(True)
        dv.addWidget(rb_overwrite)
        dv.addWidget(rb_new)

        dv.addWidget(QLabel(tr("patch_output_name")))
        edit_out = QLineEdit(f"{rom.stem} (patched){rom.suffix}")
        dv.addWidget(edit_out)

        def _toggle_out():
            edit_out.setEnabled(rb_new.isChecked())
        rb_new.toggled.connect(_toggle_out)

        dv.addSpacing(8)
        cb_backup = QCheckBox(tr("patch_backup"))
        cb_backup.setChecked(True)
        dv.addWidget(cb_backup)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("patch_apply"))
        btns.button(QDialogButtonBox.Ok).setObjectName("PrimaryBtn")
        btns.button(QDialogButtonBox.Cancel).setText(tr("msg_cancel"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dv.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        overwrite = rb_overwrite.isChecked()
        out_name = edit_out.text().strip()
        if overwrite:
            out_path = rom
        else:
            if not out_name:
                QMessageBox.warning(self, tr("msg_warning"),
                                    "请填写输出文件名")
                return
            out_path = rom.parent / out_name
            if out_path.exists():
                reply = QMessageBox.question(
                    self, tr("msg_confirm"),
                    f"{out_path.name} 已存在，覆盖？",
                    QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return

        try:
            _, old_sz, new_sz = apply_patch_file(
                rom, patch_path, out_path,
                backup=cb_backup.isChecked() and not overwrite)
        except PatchError as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("patch_failed", err=str(e)))
            return

        history = list(getattr(self._game, "patch_history", []) or [])
        history.append({
            "patch": str(patch_path),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._game.patch_history = history

        if overwrite:
            self._game.size = out_path.stat().st_size
            self._game.patched_from = str(rom) + ".bak"
            self._persist()
            QMessageBox.information(
                self, "完成",
                tr("patch_done_overwrite",
                   old=format_size(old_sz), new=format_size(new_sz)))
        else:
            games = load_games()
            new_g = GameEntry(
                name=clean_game_name(out_path),
                path=str(out_path),
                platform=self._game.platform,
                size=out_path.stat().st_size,
                added_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                custom_platform=self._game.custom_platform,
                patched_from=str(rom),
                patch_history=history,
            )
            games.append(new_g)
            save_games(games)

            reply = QMessageBox.question(
                self, "完成",
                tr("patch_done_new", name=out_path.name,
                   old=format_size(old_sz), new=format_size(new_sz))
                + "\n\n" + tr("patch_added_to_lib"),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.accept()

        self._refresh_patch_state()
        self._scan_patches()

    # ---------- 封面 Tab ----------
    def _build_cover_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumHeight(280)
        preview.setStyleSheet(
            "background:#fafafa;border:1px solid #e5e5e5;border-radius:6px;")
        self._cover_preview = preview
        v.addWidget(preview, 1)

        row = QHBoxLayout()
        b_pick = QPushButton("📂 选择图片")
        b_pick.setObjectName("PrimaryBtn")
        b_pick.clicked.connect(self._pick_cover)
        row.addWidget(b_pick)

        b_remove = QPushButton("🗑 删除封面")
        b_remove.clicked.connect(self._remove_cover)
        row.addWidget(b_remove)

        b_scrape = QPushButton("🎨 自动刮削")
        b_scrape.clicked.connect(self._scrape_this_cover)
        row.addWidget(b_scrape)

        b_online = QPushButton("🌐 在线搜索")
        b_online.clicked.connect(self._search_cover_online)
        row.addWidget(b_online)

        row.addStretch(1)
        v.addLayout(row)

        hint = QLabel(
            "封面文件保存在 covers/ 目录，文件名与游戏名一致。\n"
            "支持的格式: PNG / JPG / WEBP。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self._refresh_cover_preview()
        return w

    def _refresh_cover_preview(self):
        cover = find_cover(self._game.name)
        if cover:
            pix = QPixmap(str(cover))
            if not pix.isNull():
                self._cover_preview.setPixmap(
                    pix.scaled(360, 480, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation))
                return
        self._cover_preview.setText(tr("library_no_cover"))

    def _pick_cover(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("ctx_set_cover"), str(DATA_DIR),
            "图片 (*.png *.jpg *.jpeg *.webp);;所有文件 (*)")
        if not fp:
            return
        src = Path(fp)
        dst = COVER_DIR / f"{self._game.name}{src.suffix.lower()}"
        try:
            shutil.copy2(src, dst)
            for e in (".png", ".jpg", ".jpeg", ".webp"):
                old = COVER_DIR / f"{self._game.name}{e}"
                if old.exists() and old != dst:
                    old.unlink()
            self._refresh_cover_preview()
            self._update_tab_badges()
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

    def _remove_cover(self):
        reply = QMessageBox.question(
            self, tr("msg_confirm"), "删除封面？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for e in (".png", ".jpg", ".jpeg", ".webp"):
            p = COVER_DIR / f"{self._game.name}{e}"
            if p.exists():
                p.unlink()
        self._refresh_cover_preview()
        self._update_tab_badges()

    def _scrape_this_cover(self):
        dlg = CoverScrapeDialog([self._game], self)
        dlg.exec()
        self._refresh_cover_preview()
        self._update_tab_badges()

    def _search_cover_online(self):
        q = quote(
            f"{self._game.name} "
            f"{self._game.custom_platform or self._game.platform} box art")
        url = f"https://www.google.com/search?tbm=isch&q={q}"
        webbrowser.open(url)

    # ---------- BIOS Tab ----------
    def _build_bios_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        hint = QLabel(tr("bios_select_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.list_bios = QListWidget()
        self.list_bios.addItem(tr("bios_select_none"))
        bios_files = scan_bios()
        if not bios_files:
            self.list_bios.addItem(tr("bios_select_no_files"))
            self.list_bios.setEnabled(False)
        else:
            for b in bios_files:
                label = b.name
                if b.known_as:
                    label += f"  [{b.known_as}]"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, b.path)
                self.list_bios.addItem(item)
        cur = self._game.bios_file
        if cur:
            for i in range(self.list_bios.count()):
                it = self.list_bios.item(i)
                if it.data(Qt.UserRole) == cur:
                    self.list_bios.setCurrentRow(i)
                    break
        else:
            self.list_bios.setCurrentRow(0)
        self.list_bios.currentItemChanged.connect(self._on_bios_changed)
        v.addWidget(self.list_bios, 1)

        row = QHBoxLayout()
        b_import = QPushButton("📥 导入 BIOS 文件")
        b_import.clicked.connect(self._import_bios_file)
        row.addWidget(b_import)
        b_open = QPushButton("📂 打开 BIOS 目录")
        b_open.clicked.connect(lambda: os.startfile(str(BIOS_DIR)))
        row.addWidget(b_open)
        row.addStretch(1)
        v.addLayout(row)

        return w

    def _on_bios_changed(self, current, _prev):
        if current is None:
            return
        path = current.data(Qt.UserRole) or ""
        self._game.bios_file = path
        self._persist()

    def _import_bios_file(self):
        fps, _ = QFileDialog.getOpenFileNames(
            self, "导入 BIOS", str(Path.home()), "所有文件 (*)")
        if not fps:
            return
        count = 0
        for fp in fps:
            try:
                shutil.copy2(fp, BIOS_DIR / Path(fp).name)
                count += 1
            except Exception as e:
                logger.exception(f"复制 BIOS 失败: {e}")
        if count:
            QMessageBox.information(self, tr("msg_info"),
                                    f"已导入 {count} 个 BIOS 文件")
            idx = self.tabs.currentIndex()
            self.tabs.removeTab(idx)
            self.tabs.insertTab(idx, self._build_bios_tab(),
                                tr("game_config_tab_bios"))
            self.tabs.setCurrentIndex(idx)

    # ---------- 金手指 Tab ----------
    def _build_cheat_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        hint = QLabel(tr("settings_cheats_hint"))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        engine = self._resolve_engine_silent()
        self.lbl_engine = QLabel(
            f"<b>当前引擎:</b> {engine.engine if engine else '—'}")
        self.lbl_engine.setTextFormat(Qt.RichText)
        v.addWidget(self.lbl_engine)

        self.list_cheats = QListWidget()
        self.list_cheats.setMinimumHeight(180)
        self.list_cheats.itemDoubleClicked.connect(
            lambda _: self._open_selected_cheat())
        v.addWidget(self.list_cheats, 1)

        row = QHBoxLayout()
        b_scan = QPushButton(tr("cheat_scan"))
        b_scan.clicked.connect(self._scan_cheats)
        row.addWidget(b_scan)
        b_import = QPushButton("📥 导入金手指")
        b_import.clicked.connect(self._import_cheat)
        row.addWidget(b_import)
        b_open = QPushButton(tr("cheat_open_engine_dir"))
        b_open.clicked.connect(self._open_cheat_dir)
        row.addWidget(b_open)
        row.addStretch(1)
        v.addLayout(row)

        self._scan_cheats()
        return w

    def _resolve_engine_silent(self):
        installed = load_installed()
        if self._game.override_engine:
            try:
                plat, eng = self._game.override_engine.split("/", 1)
                for e in installed:
                    if e.platform == plat and e.engine == eng:
                        return e
            except Exception:
                pass
        target = self._game.override_platform or self._game.platform
        for e in installed:
            if e.platform == target:
                return e
        return None

    def _scan_cheats(self):
        self.list_cheats.clear()
        engine = self._resolve_engine_silent()
        if not engine:
            it = QListWidgetItem(tr("cheat_none_engine"))
            it.setFlags(Qt.NoItemFlags)
            self.list_cheats.addItem(it)
            return
        d = get_cheat_dir(engine.engine)
        if not d:
            it = QListWidgetItem(
                tr("cheat_not_configured", engine=engine.engine))
            it.setFlags(Qt.NoItemFlags)
            self.list_cheats.addItem(it)
            return

        ext = get_cheat_ext(engine.engine)
        game_lower = self._game.name.lower()
        matched = []
        others = []
        for f in d.rglob(f"*{ext}"):
            if not f.is_file():
                continue
            name_lower = f.stem.lower()
            words = [game_lower] + game_lower.split()
            if any(w in name_lower or name_lower in w for w in words):
                matched.append(f)
            else:
                others.append(f)

        for f in sorted(matched, key=lambda x: x.name.lower()):
            item = QListWidgetItem(f"⭐ {f.name}")
            item.setData(Qt.UserRole, str(f))
            item.setForeground(QColor("#0f7b0f"))
            self.list_cheats.addItem(item)
        for f in sorted(others, key=lambda x: x.name.lower())[:200]:
            item = QListWidgetItem(f"   {f.name}")
            item.setData(Qt.UserRole, str(f))
            self.list_cheats.addItem(item)

    def _open_selected_cheat(self):
        item = self.list_cheats.currentItem()
        if not item:
            return
        path = item.data(Qt.UserRole)
        if not path:
            return
        p = Path(path)
        if p.exists():
            try:
                os.startfile(str(p))
            except Exception:
                pass

    def _open_cheat_dir(self):
        engine = self._resolve_engine_silent()
        if engine:
            d = get_cheat_dir(engine.engine)
            if d:
                os.startfile(str(d))
                return
        os.startfile(str(CHEAT_DIR))

    def _import_cheat(self):
        engine = self._resolve_engine_silent()
        if not engine:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("config_no_engine"))
            return
        d = get_cheat_dir(engine.engine)
        if not d:
            d = CHEAT_DIR / engine.engine
            d.mkdir(parents=True, exist_ok=True)
            CHEAT_PATHS[engine.engine] = {
                "dir": str(d), "ext": get_cheat_ext(engine.engine)}
            save_cheat_paths()
        fps, _ = QFileDialog.getOpenFileNames(
            self, "导入金手指", str(Path.home()), "所有文件 (*)")
        count = 0
        for fp in fps:
            try:
                shutil.copy2(fp, d / Path(fp).name)
                count += 1
            except Exception as e:
                logger.exception(f"复制金手指失败: {e}")
        if count:
            QMessageBox.information(self, tr("msg_info"),
                                    f"已导入 {count} 个金手指文件")
            self._scan_cheats()

    # ---------- 存档 Tab ----------
    def _build_save_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        engine = self._resolve_engine_silent()
        save_path = get_save_path(engine.engine) if engine else None

        if save_path:
            info = QLabel(f"<b>存档目录:</b> {save_path}")
        else:
            info = QLabel(tr("game_config_no_save_path"))
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        v.addWidget(info)

        row = QHBoxLayout()
        b_open = QPushButton("📂 打开存档目录")
        b_open.setEnabled(bool(save_path))
        b_open.clicked.connect(
            lambda: os.startfile(str(save_path)) if save_path else None)
        row.addWidget(b_open)

        b_backup = QPushButton("💾 立即备份此引擎存档")
        b_backup.setEnabled(bool(save_path))
        b_backup.clicked.connect(self._backup_engine_save)
        row.addWidget(b_backup)

        b_restore = QPushButton("↩ 从备份还原")
        b_restore.clicked.connect(self._restore_engine_save)
        row.addWidget(b_restore)

        row.addStretch(1)
        v.addLayout(row)

        if engine:
            backups = [b for b in list_save_backups()
                       if b.name.startswith(engine.engine + "_")]
            if backups:
                grp = QGroupBox(f"{engine.engine} 的备份")
                fg = QVBoxLayout(grp)
                self.list_backups = QListWidget()
                for b in backups[:30]:
                    item = QListWidgetItem(
                        f"{b.name}  ({human_size(_dir_size(b))})")
                    item.setData(Qt.UserRole, str(b))
                    self.list_backups.addItem(item)
                self.list_backups.itemDoubleClicked.connect(
                    lambda _: self._restore_engine_save())
                fg.addWidget(self.list_backups)
                v.addWidget(grp, 1)

        v.addStretch(1)
        return w

    def _backup_engine_save(self):
        try:
            results = backup_all_saves()
            QMessageBox.information(
                self, tr("msg_info"),
                f"已备份 {len(results)} 个引擎的存档")
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

    def _restore_engine_save(self):
        list_w = getattr(self, "list_backups", None)
        if not list_w:
            return
        cur = list_w.currentItem()
        if not cur:
            return
        path = Path(cur.data(Qt.UserRole))
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("save_restore_confirm", name=path.name),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            restore_save_backup(path)
            QMessageBox.information(self, tr("msg_info"),
                                    tr("save_restore_done", name=path.name))
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))

    # ---------- 信息 Tab ----------
    def _build_info_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)

        g = self._game
        rows = [
            ("游戏名", g.name),
            ("平台", g.custom_platform or g.platform),
            ("路径", g.path),
            ("大小", format_size(g.size)),
            ("加入时间", g.added_at or "—"),
            ("最后游玩", g.last_played or "—"),
            ("累计时长", human_duration(g.play_seconds)),
            ("启动次数", str(g.launch_count)),
            ("收藏", "是" if g.favorite else "否"),
            ("通关", "是" if getattr(g, "cleared", False) else "否"),
        ]

        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["字段", "值"])
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i, (k, val) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(k))
            table.setItem(i, 1, QTableWidgetItem(str(val)))
        v.addWidget(table, 1)

        row = QHBoxLayout()
        b_copy = QPushButton("📋 复制信息")
        b_copy.clicked.connect(self._copy_info)
        row.addWidget(b_copy)

        b_toggle_clear = QPushButton(
            "取消通关标记" if getattr(g, "cleared", False) else "✅ 标记为通关")
        b_toggle_clear.clicked.connect(self._toggle_cleared)
        row.addWidget(b_toggle_clear)

        b_open_folder = QPushButton(tr("ctx_open_folder"))
        b_open_folder.clicked.connect(
            lambda: self.open_folder_requested.emit(self._game))
        row.addWidget(b_open_folder)

        row.addStretch(1)
        v.addLayout(row)

        return w

    def _copy_info(self):
        g = self._game
        text = (
            f"游戏名: {g.name}\n"
            f"平台: {g.custom_platform or g.platform}\n"
            f"路径: {g.path}\n"
            f"大小: {format_size(g.size)}\n"
            f"时长: {human_duration(g.play_seconds)}\n"
            f"启动: {g.launch_count}\n"
        )
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, tr("msg_info"),
                                tr("copy_info_done"))

    def _toggle_cleared(self):
        self._game.cleared = not getattr(self._game, "cleared", False)
        self._persist()
        idx = self.tabs.currentIndex()
        self.tabs.removeTab(idx)
        self.tabs.insertTab(idx, self._build_info_tab(),
                            tr("game_config_tab_info"))
        self.tabs.setCurrentIndex(idx)

# ============================================================
# 38. 插件系统
# ============================================================
PLUGIN_API_VERSION = "1.0"

PLUGIN_TEMPLATE_MAIN = '''# -*- coding: utf-8 -*-
"""
{name}
自动生成的插件骨架
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton
)


class MainPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self._api = api
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(30, 30, 30, 30)
        v.setSpacing(16)

        title = QLabel("{name}")
        title.setObjectName("SectionTitle")
        v.addWidget(title)

        hint = QLabel("这是一个自动生成的插件骨架。\\n"
                      "打开 main.py 修改 register() 里的内容即可。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        btn = QPushButton("测试按钮")
        btn.setObjectName("PrimaryBtn")
        btn.clicked.connect(self._on_click)
        v.addWidget(btn)

        self.lbl = QLabel("")
        v.addWidget(self.lbl)

    def _on_click(self):
        games = self._api.get_games()
        self.lbl.setText(f"游戏库里有 {{len(games)}} 个游戏")


def register(api):
    api.add_page("{name}", lambda: MainPage(api), icon="{icon}")
    api.log("{name} 已加载")
'''


def _safe_plugin_id(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"[^\w\-]", "_", raw, flags=re.UNICODE)
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw:
        return ""
    if raw[0].isdigit():
        raw = "p_" + raw
    return raw[:64]


def _validate_and_fill_plugin_meta(meta: dict, fallback_id: str = "",
                                    fallback_name: str = "") -> tuple:
    meta = dict(meta or {})
    filled = []

    pid = _safe_plugin_id(meta.get("id") or fallback_id)
    if not pid:
        pid = _safe_plugin_id(fallback_name) or "plugin"
    if meta.get("id") != pid:
        meta["id"] = pid
        filled.append("id")

    if not meta.get("name"):
        meta["name"] = fallback_name or pid
        filled.append("name")

    if not meta.get("version"):
        meta["version"] = "1.0.0"
        filled.append("version")

    if not meta.get("author"):
        meta["author"] = "unknown"
        filled.append("author")

    if not meta.get("description"):
        meta["description"] = meta["name"]
        filled.append("description")

    if not meta.get("api_version"):
        meta["api_version"] = PLUGIN_API_VERSION
        filled.append("api_version")

    if not meta.get("min_app_version"):
        meta["min_app_version"] = APP_VERSION
        filled.append("min_app_version")

    if not meta.get("entry"):
        meta["entry"] = "main.py"
        filled.append("entry")

    if not meta.get("icon"):
        meta["icon"] = "🔌"
        filled.append("icon")

    if not isinstance(meta.get("permissions"), list):
        meta["permissions"] = ["read_games"]
        filled.append("permissions")

    return meta, filled


def _find_plugin_root(scan_root: Path) -> Optional[Path]:
    if not scan_root.exists():
        return None

    candidates = sorted(
        scan_root.rglob("plugin.json"),
        key=lambda p: len(p.relative_to(scan_root).parts),
    )
    if candidates:
        return candidates[0].parent

    candidates = sorted(
        scan_root.rglob("main.py"),
        key=lambda p: len(p.relative_to(scan_root).parts),
    )
    if candidates:
        return candidates[0].parent

    candidates = sorted(
        (p for p in scan_root.rglob("*.py")),
        key=lambda p: len(p.relative_to(scan_root).parts),
    )
    if candidates:
        return candidates[0].parent

    subdirs = [d for d in scan_root.iterdir() if d.is_dir()]
    files = [f for f in scan_root.iterdir() if f.is_file()]
    if not files and len(subdirs) == 1:
        return subdirs[0]

    return scan_root


def _read_plugin_meta_safe(plugin_root: Path) -> tuple:
    meta_file = plugin_root / "plugin.json"
    if not meta_file.exists():
        return {}, "", False
    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}, "plugin.json 顶层必须是对象", True
        return data, "", True
    except json.JSONDecodeError as e:
        return {}, f"plugin.json 语法错误: {e}", True
    except Exception as e:
        return {}, f"plugin.json 读取失败: {e}", True


def _install_plugin_from_dir(plugin_root: Path, fallback_id: str = "",
                              fallback_name: str = "",
                              overwrite: bool = True) -> tuple:
    meta, err, _ = _read_plugin_meta_safe(plugin_root)
    if err:
        return False, "", [], err

    if not fallback_name:
        fallback_name = plugin_root.name

    meta, filled = _validate_and_fill_plugin_meta(
        meta,
        fallback_id=fallback_id or plugin_root.name,
        fallback_name=fallback_name,
    )
    pid = meta["id"]
    dst = PLUGINS_DIR / pid

    if dst.exists():
        if not overwrite:
            return False, pid, filled, f"插件 {pid} 已存在"
        try:
            old_meta_file = dst / "plugin.json"
            if old_meta_file.exists():
                old_meta = json.loads(old_meta_file.read_text("utf-8"))
                if isinstance(old_meta, dict):
                    for k, v in old_meta.items():
                        meta.setdefault(k, v)
        except Exception:
            pass
        shutil.rmtree(dst, ignore_errors=True)

    try:
        shutil.copytree(plugin_root, dst)
    except Exception as e:
        return False, pid, filled, f"复制失败: {e}"

    entry_name = meta.get("entry", "main.py")
    entry_file = dst / entry_name
    if not entry_file.exists():
        pys = [p for p in dst.rglob("*.py") if p.name != "__init__.py"]
        if pys:
            rel = pys[0].relative_to(dst)
            meta["entry"] = str(rel).replace("\\", "/")
            filled.append("entry(自动识别)")
        else:
            entry_file.parent.mkdir(parents=True, exist_ok=True)
            entry_file.write_text(
                PLUGIN_TEMPLATE_MAIN.format(
                    name=meta["name"], icon=meta.get("icon", "🔌")),
                encoding="utf-8",
            )
            filled.append("main.py(生成骨架)")

    try:
        with open(dst / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        return False, pid, filled, f"写入 plugin.json 失败: {e}"

    return True, pid, filled, ""


def _install_plugin_from_json_file(json_path: Path,
                                    overwrite: bool = True) -> tuple:
    try:
        data = json.loads(json_path.read_text("utf-8"))
        if not isinstance(data, dict):
            return False, "", [], "json 顶层必须是对象"
    except json.JSONDecodeError as e:
        return False, "", [], f"JSON 语法错误: {e}"
    except Exception as e:
        return False, "", [], f"读取失败: {e}"

    fallback_name = json_path.stem
    meta, filled = _validate_and_fill_plugin_meta(
        data,
        fallback_id=fallback_name,
        fallback_name=fallback_name,
    )
    pid = meta["id"]
    dst = PLUGINS_DIR / pid

    if dst.exists():
        if not overwrite:
            return False, pid, filled, f"插件 {pid} 已存在"
        shutil.rmtree(dst, ignore_errors=True)

    dst.mkdir(parents=True, exist_ok=True)

    entry_name = meta.get("entry", "main.py")
    (dst / entry_name).parent.mkdir(parents=True, exist_ok=True)
    (dst / entry_name).write_text(
        PLUGIN_TEMPLATE_MAIN.format(
            name=meta["name"], icon=meta.get("icon", "🔌")),
        encoding="utf-8",
    )
    filled.append(f"{entry_name}(生成骨架)")

    with open(dst / "plugin.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return True, pid, filled, ""


def _import_plugin_any(src: Path, overwrite: bool = True) -> tuple:
    if not src.exists():
        return False, "", [], f"路径不存在: {src}"

    if src.is_file() and src.suffix.lower() == ".json":
        return _install_plugin_from_json_file(src, overwrite)

    if src.is_file() and src.suffix.lower() in (".zip", ".7z", ".rar"):
        tmp = Path(tempfile.mkdtemp(
            prefix="mikan_plugin_", dir=str(TEMP_DIR)))
        try:
            extract_archive(src, tmp)
            root = _find_plugin_root(tmp)
            if root is None:
                return False, "", [], "压缩包为空"
            return _install_plugin_from_dir(
                root,
                fallback_id=src.stem,
                fallback_name=src.stem,
                overwrite=overwrite,
            )
        except Exception as e:
            return False, "", [], f"解压失败: {e}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if src.is_dir():
        root = _find_plugin_root(src)
        if root is None:
            return False, "", [], "文件夹为空"
        return _install_plugin_from_dir(
            root,
            fallback_id=src.name,
            fallback_name=src.name,
            overwrite=overwrite,
        )

    if src.is_file() and src.suffix.lower() == ".py":
        pid = _safe_plugin_id(src.stem) or "my_plugin"
        dst = PLUGINS_DIR / pid
        if dst.exists() and not overwrite:
            return False, pid, [], f"插件 {pid} 已存在"
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst / "main.py")
        meta, filled = _validate_and_fill_plugin_meta(
            {},
            fallback_id=pid,
            fallback_name=src.stem,
        )
        with open(dst / "plugin.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        filled.append("plugin.json(生成)")
        return True, pid, filled, ""

    return False, "", [], f"不支持的类型: {src.suffix or '未知'}"


def load_plugin_enabled() -> dict:
    if PLUGINS_ENABLED_FILE.exists():
        try:
            with open(PLUGINS_ENABLED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_plugin_enabled(data: dict):
    try:
        with open(PLUGINS_ENABLED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"保存插件启用状态失败: {e}")


class PluginAPI:
    """旧版插件 API（保留兼容）。"""

    def __init__(self, main_window):
        self._mw = main_window
        self._hooks: dict = {}
        self._pages: list = []
        self._actions: list = []

    def get_games(self):
        return load_games()

    def get_game(self, path: str):
        for g in load_games():
            if g.path == path:
                return g
        return None

    def get_engines(self):
        return load_installed()

    def get_platforms(self):
        return load_engines_json()

    def get_paths(self) -> dict:
        return {
            "data": DATA_DIR, "covers": COVER_DIR, "roms": ROM_DIR,
            "bios": BIOS_DIR, "saves": SAVE_DIR, "logs": LOG_DIR,
            "plugins": PLUGINS_DIR, "config": CONFIG_DIR,
            "crash_reports": CRASH_REPORT_DIR,
        }

    def get_settings(self) -> dict:
        return dict(SETTINGS)

    def set_setting(self, key: str, value):
        SETTINGS[key] = value
        save_settings()

    def update_game(self, path: str, **fields):
        games = load_games()
        for g in games:
            if g.path == path:
                for k, v in fields.items():
                    if hasattr(g, k):
                        setattr(g, k, v)
                break
        save_games(games)
        self.emit("games_changed")

    def set_cover(self, game_path: str, image: Path):
        g = self.get_game(game_path)
        if not g:
            return
        dst = COVER_DIR / f"{g.name}{image.suffix}"
        shutil.copy2(image, dst)
        self.emit("covers_changed")

    def launch_game(self, game):
        self._mw._launch_game(game)

    def open_url(self, url: str):
        webbrowser.open(url)

    def open_folder(self, path):
        try:
            os.startfile(str(path))
        except Exception:
            pass

    def notify(self, title: str, message: str):
        if self._mw._tray:
            self._mw._tray.showMessage(
                title, message, QSystemTrayIcon.Information, 4000)

    def add_page(self, title: str, widget, icon: str = "🔌"):
        self._pages.append((title, widget, icon))

    def add_menu_action(self, menu_name: str, label: str, callback):
        self._actions.append((menu_name, label, callback))

    def add_tray_action(self, label: str, callback):
        if self._mw._tray:
            menu = self._mw._tray.contextMenu()
            if menu:
                menu.addAction(label, callback)

    def show_dialog(self, widget: QWidget):
        widget.exec()

    def on(self, event: str, callback):
        self._hooks.setdefault(event, []).append(callback)

    def emit(self, event: str, **kwargs):
        for cb in self._hooks.get(event, []):
            try:
                cb(**kwargs)
            except Exception as e:
                logger.exception(f"[plugin] 钩子 {event} 失败: {e}")

    def http(self):
        return HttpSession.get()

    def storage_get(self, key: str, default=None):
        store_file = PLUGIN_STORAGE_DIR / "shared.json"
        try:
            if store_file.exists():
                data = json.loads(store_file.read_text("utf-8"))
                return data.get(key, default)
        except Exception:
            pass
        return default

    def storage_set(self, key: str, value):
        store_file = PLUGIN_STORAGE_DIR / "shared.json"
        try:
            data = {}
            if store_file.exists():
                data = json.loads(store_file.read_text("utf-8"))
            data[key] = value
            store_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            logger.exception(f"插件存储失败: {e}")

    def log(self, msg: str, level: str = "INFO"):
        logger.log(level, f"[plugin] {msg}")

    # ★ v1.8.0：插件可以访问完整 MikanAPI
    @property
    def full(self):
        return get_api()


class PluginManager:
    def __init__(self, main_window):
        self._mw = main_window
        self.api = PluginAPI(main_window)
        self.plugins: dict = {}
        self.enabled_state = load_plugin_enabled()

    def scan_all(self) -> list:
        result = []
        if not PLUGINS_DIR.exists():
            return result
        for d in sorted(PLUGINS_DIR.iterdir()):
            if not d.is_dir():
                continue
            meta_file = d / "plugin.json"
            if not meta_file.exists():
                continue
            info = {"id": d.name, "path": str(d),
                    "enabled": False, "error": ""}
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                info["meta"] = meta
                info["id"] = meta.get("id", d.name)
                info["enabled"] = bool(
                    self.enabled_state.get(info["id"], True))
            except Exception as e:
                info["error"] = f"元数据解析失败: {e}"
            result.append(info)
        return result

    def load_all(self):
        self.plugins.clear()
        for info in self.scan_all():
            if info.get("error"):
                logger.warning(
                    f"跳过插件 {info['id']}: {info['error']}")
                continue
            if not info["enabled"]:
                logger.info(f"插件 {info['id']} 已禁用")
                continue
            self._load_one(info)

    def _load_one(self, info):
        pid = info["id"]
        meta = info["meta"]
        path = Path(info["path"])
        entry = path / meta.get("entry", "main.py")
        if not entry.exists():
            logger.warning(f"插件 {pid} 缺少入口 {entry}")
            return

        api_ver = meta.get("api_version", "1.0")
        if api_ver != PLUGIN_API_VERSION:
            logger.warning(f"插件 {pid} API 版本不匹配: {api_ver}")
            return

        mod_name = f"mikan_plugin_{pid}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, entry)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            logger.exception(f"插件 {pid} 加载失败: {e}")
            return

        if not hasattr(module, "register"):
            logger.warning(f"插件 {pid} 缺少 register(api)")
            return

        try:
            module.register(self.api)
        except Exception as e:
            logger.exception(f"插件 {pid} register 失败: {e}")
            return

        self.plugins[pid] = {
            "meta": meta,
            "module": module,
            "path": path,
            "enabled": True,
        }
        logger.info(
            f"插件已加载: {meta.get('name', pid)} "
            f"v{meta.get('version', '?')}")

    def get_pages(self) -> list:
        return list(self.api._pages)

    def clear_pages(self):
        self.api._pages.clear()

    def emit(self, event: str, **kwargs):
        self.api.emit(event, **kwargs)

    def set_enabled(self, pid: str, enabled: bool):
        self.enabled_state[pid] = enabled
        save_plugin_enabled(self.enabled_state)


# ============================================================
# 39. ★ v1.8.0：MikanAPI 子类实现（补齐第 2 段骨架）
# ============================================================
class _GamesAPI:
    """游戏库 API。"""

    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def list(self) -> list:
        return [g.to_dict() for g in load_games()]

    def get(self, path: str) -> Optional[dict]:
        for g in load_games():
            if g.path == path:
                return g.to_dict()
        return None

    def add(self, entry: dict) -> dict:
        games = load_games()
        g = GameEntry.from_dict(entry)
        if not g.added_at:
            g.added_at = time.strftime("%Y-%m-%d %H:%M:%S")
        games.append(g)
        save_games(games)
        self._parent._emit(Events.GAMES_CHANGED)
        self._parent._emit(Events.GAME_ADDED, path=g.path)
        return g.to_dict()

    def update(self, path: str, **fields) -> bool:
        games = load_games()
        found = False
        for g in games:
            if g.path == path:
                for k, v in fields.items():
                    if hasattr(g, k):
                        setattr(g, k, v)
                found = True
                break
        if found:
            save_games(games)
            self._parent._emit(Events.GAMES_CHANGED)
        return found

    def remove(self, path: str) -> bool:
        games = load_games()
        new_games = [g for g in games if g.path != path]
        if len(new_games) == len(games):
            return False
        save_games(new_games)
        self._parent._emit(Events.GAMES_CHANGED)
        self._parent._emit(Events.GAME_REMOVED, path=path)
        return True

    def favorite(self, path: str, value: Optional[bool] = None) -> bool:
        games = load_games()
        for g in games:
            if g.path == path:
                g.favorite = (not g.favorite) if value is None else bool(value)
                save_games(games)
                self._parent._emit(Events.GAMES_CHANGED)
                return g.favorite
        return False

    def launch(self, path: str) -> Job:
        class _LaunchWorker(QThread):
            progress = Signal(int, int)
            status = Signal(str)
            done = Signal(object)
            fail = Signal(str)

            def __init__(self, path):
                super().__init__()
                self._path = path

            def run(self):
                try:
                    game = None
                    for g in load_games():
                        if g.path == self._path:
                            game = g
                            break
                    if game is None:
                        self.fail.emit(f"game not found: {self._path}")
                        return
                    engine = None
                    installed = load_installed()
                    if game.override_engine:
                        try:
                            plat, eng = game.override_engine.split("/", 1)
                            for e in installed:
                                if e.platform == plat and e.engine == eng:
                                    engine = e
                                    break
                        except Exception:
                            pass
                    if engine is None:
                        target = game.override_platform or game.platform
                        for e in installed:
                            if e.platform == target:
                                engine = e
                                break
                    if engine is None:
                        self.fail.emit(
                            f"no engine for platform {game.platform}")
                        return
                    proc, switched, bios_msg = launch_game(engine, game)
                    games = load_games()
                    now = time.strftime("%Y-%m-%d %H:%M:%S")
                    for g in games:
                        if g.path == game.path:
                            g.last_played = now
                            g.launch_count = (g.launch_count or 0) + 1
                            g.launch_start_ts = time.time()
                            break
                    save_games(games)
                    self.done.emit({
                        "pid": getattr(proc, "pid", 0),
                        "switched": switched,
                        "bios_msg": bios_msg,
                        "game": game.to_dict(),
                    })
                except Exception as e:
                    logger.exception("API launch_game 失败")
                    self.fail.emit(str(e))

        worker = _LaunchWorker(path)
        return Job(worker)

    def scan_dir(self, path: str) -> list:
        root = Path(path)
        if not root.exists() or not root.is_dir():
            return []
        engines_json = load_engines_json()
        files = scan_files(root)
        games, _ = import_games_scan(files, engines_json)
        return [g.to_dict() for g in games]

    def import_from(self, source: str) -> Job:
        p = Path(source)
        is_archive = p.is_file() and p.suffix.lower() in ARCHIVE_EXTS
        engines_json = load_engines_json()
        worker = GameImportWorker(p, engines_json, is_archive)
        return Job(worker)


class _EnginesAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def list(self) -> list:
        return [e.to_dict() for e in load_installed()]

    def get(self, platform: str, engine: str) -> Optional[dict]:
        for e in load_installed():
            if e.platform == platform and e.engine == engine:
                return e.to_dict()
        return None

    def install_from_dir(self, path: str, platform: str,
                         engine_name: str,
                         launch_template: str = '{exe} "{rom}"',
                         platform_display: str = "") -> dict:
        p = Path(path)
        if not p.exists():
            raise RuntimeError(f"path not found: {path}")
        exe_path = p
        if p.is_dir():
            exes = list(p.rglob("*.exe"))
            if not exes:
                raise RuntimeError(f"no .exe found in {path}")
            exe_path = exes[0]
        cfg = install_manual_engine(exe_path, platform, engine_name,
                                    launch_template, platform_display)
        engines = load_installed()
        engines = [e for e in engines
                   if not (e.platform == cfg.platform
                           and e.engine == cfg.engine)]
        engines.append(cfg)
        save_installed(engines)
        self._parent._emit(Events.ENGINE_INSTALLED,
                           platform=cfg.platform, engine=cfg.engine)
        return cfg.to_dict()

    def remove(self, platform: str, engine: str,
               delete_files: bool = False) -> bool:
        engines = load_installed()
        target = None
        for e in engines:
            if e.platform == platform and e.engine == engine:
                target = e
                break
        if target is None:
            return False
        engines = [e for e in engines
                   if not (e.platform == platform and e.engine == engine)]
        save_installed(engines)
        if delete_files and target.engine_dir:
            d = Path(target.engine_dir)
            try:
                d.resolve().relative_to(ENGINE_DOWNLOAD_DIR.resolve())
                shutil.rmtree(d, ignore_errors=True)
            except ValueError:
                logger.warning(f"拒绝删除非引擎目录: {d}")
            except Exception as e:
                logger.exception(f"删除引擎目录失败: {e}")
        self._parent._emit(Events.ENGINE_REMOVED,
                           platform=platform, engine=engine)
        return True

    def detect_version(self, platform: str, engine: str) -> str:
        for e in load_installed():
            if e.platform == platform and e.engine == engine:
                return detect_engine_version(e, force=True)
        return ""

    def open_settings(self, platform: str, engine: str) -> Job:
        class _SettingsWorker(QThread):
            status = Signal(str)
            done = Signal(object)
            fail = Signal(str)

            def __init__(self, platform, engine):
                super().__init__()
                self._platform = platform
                self._engine = engine

            def run(self):
                try:
                    target = None
                    for e in load_installed():
                        if (e.platform == self._platform
                                and e.engine == self._engine):
                            target = e
                            break
                    if target is None:
                        self.fail.emit("engine not found")
                        return
                    proc = open_engine_settings(target)
                    self.done.emit({"pid": getattr(proc, "pid", 0)})
                except Exception as e:
                    self.fail.emit(str(e))

        worker = _SettingsWorker(platform, engine)
        return Job(worker)

    def check_updates(self) -> Job:
        installed = load_installed()
        engines_json = load_engines_json()
        worker = ReleasesWorker(installed, engines_json, use_mirror=True)
        return Job(worker)


class _DownloadAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def start(self, platform: str, engine: str) -> Job:
        engines_json = load_engines_json()
        pcfg = engines_json.get(platform, {})
        cfg = pcfg.get("engines", {}).get(engine)
        if not cfg:
            raise RuntimeError(f"engine not found: {platform}/{engine}")
        url = cfg.get("url", "")
        if not url or url == "manual":
            raise RuntimeError(f"engine {platform}/{engine} is manual-only")

        archive = cfg.get("archive", "zip")
        ext = ".zip"
        if archive == "7z":
            ext = ".7z"
        elif archive in ("7z_sfx", "bare_exe"):
            ext = ".exe"
        elif archive == "rar":
            ext = ".rar"
        tmp = TEMP_DIR / f"api_dl_{platform}_{engine}{ext}"

        threads = int(SETTINGS.get("download_threads", 8))
        worker = DownloadWorker(url, tmp, threads)

        class _InstallAfterDownload(QObject):
            def __init__(self, worker, platform, engine, cfg):
                super().__init__()
                self._worker = worker
                self._platform = platform
                self._engine = engine
                self._cfg = cfg
                self._archive = tmp
                worker.done.connect(self._on_done)
                worker.fail.connect(self._on_fail)
                self.done = Signal(object)
                self.fail = Signal(str)

            def _on_done(self, path):
                try:
                    self._install(Path(path))
                    self.done.emit(str(path))
                except Exception as e:
                    self.fail.emit(str(e))

            def _on_fail(self, err):
                self.fail.emit(str(err))

            def _install(self, archive_path: Path):
                archive_type = self._cfg.get("archive", "zip")
                if archive_type == "bare_exe":
                    target_dir = (ENGINE_DOWNLOAD_DIR
                                  / self._platform / self._engine)
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_exe = target_dir / archive_path.name
                    shutil.copy2(archive_path, target_exe)
                    installed = EmulatorConfig(
                        platform=self._platform, engine=self._engine,
                        platform_name=self._cfg.get(
                            "platform_name", self._platform),
                        engine_path=str(target_exe),
                        engine_dir=str(target_dir),
                        version=self._cfg.get("version", ""),
                        official=True, source="download",
                        launch_template=self._cfg.get(
                            "launch_template", '{exe} "{rom}"'),
                        installed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                        url=self._cfg.get("url", ""),
                        url_type="direct",
                        github_repo=self._cfg.get("github_repo", ""),
                        archive="bare_exe",
                    )
                    engines = load_installed()
                    engines = [e for e in engines
                               if not (e.platform == installed.platform
                                       and e.engine == installed.engine)]
                    engines.append(installed)
                    save_installed(engines)
                    try:
                        archive_path.unlink()
                    except Exception:
                        pass
                    return

                tmp_root = Path(tempfile.mkdtemp(
                    prefix="mikan_api_dl_", dir=str(TEMP_DIR)))
                try:
                    if archive_type == "7z_sfx":
                        try:
                            sp.run(
                                [str(archive_path), f"-o{tmp_root}", "-y"],
                                check=True, timeout=600,
                                creationflags=getattr(
                                    sp, "CREATE_NO_WINDOW", 0))
                        except Exception:
                            import py7zr
                            with py7zr.SevenZipFile(
                                    archive_path, mode="r") as z:
                                z.extractall(tmp_root)
                    else:
                        extract_archive(archive_path, tmp_root)
                    files = scan_files(tmp_root)
                    matches = match_engines(
                        files,
                        {self._platform:
                         {"engines": {self._engine: self._cfg}}})
                    if not matches:
                        raise RuntimeError(
                            f"解压后没找到 {self._engine} 的可执行文件")
                    installed = install_engine_from_match(
                        matches[0], tmp_root, "download")
                    engines = load_installed()
                    engines = [e for e in engines
                               if not (e.platform == installed.platform
                                       and e.engine == installed.engine)]
                    engines.append(installed)
                    save_installed(engines)
                finally:
                    shutil.rmtree(tmp_root, ignore_errors=True)
                    try:
                        if archive_path.exists():
                            archive_path.unlink()
                    except Exception:
                        pass

        installer = _InstallAfterDownload(worker, platform, engine, cfg)
        job = Job(worker)
        installer.done.connect(lambda r: job.finished.emit(r))
        installer.fail.connect(lambda e: job.failed.emit(e))

        self._parent._emit(Events.DOWNLOAD_START,
                           platform=platform, engine=engine)
        return job

    def start_url(self, url: str, target: str,
                  threads: int = 0) -> Job:
        threads = threads or int(SETTINGS.get("download_threads", 8))
        worker = DownloadWorker(url, Path(target), threads)
        self._parent._emit(Events.DOWNLOAD_START, url=url, target=target)
        return Job(worker)


class _ScrapeAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def libretro(self, game_paths: list,
                 img_type: str = "boxart",
                 overwrite: bool = False) -> Job:
        games = self._resolve_games(game_paths)
        worker = LibretroScraperWorker(games, img_type, overwrite)
        return Job(worker)

    def steamgriddb(self, game_paths: list,
                    api_key: str = "",
                    img_type: str = "boxart",
                    overwrite: bool = False) -> Job:
        key = api_key or SETTINGS.get("steamgriddb_api_key", "")
        games = self._resolve_games(game_paths)
        worker = SteamGridDBScraperWorker(games, key, img_type, overwrite)
        return Job(worker)

    def _resolve_games(self, game_paths: list) -> list:
        all_games = load_games()
        by_path = {g.path: g for g in all_games}
        result = []
        for p in game_paths:
            if p in by_path:
                result.append(by_path[p])
        return result


class _PatchAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def apply_ips(self, rom: str, patch: str,
                  out: str = "", backup: bool = True) -> dict:
        return self._apply(Path(rom), Path(patch),
                           Path(out) if out else None, backup)

    def apply_ups(self, rom: str, patch: str,
                  out: str = "", backup: bool = True) -> dict:
        return self._apply(Path(rom), Path(patch),
                           Path(out) if out else None, backup)

    def apply_auto(self, rom: str, patch: str,
                   out: str = "", backup: bool = True) -> dict:
        return self._apply(Path(rom), Path(patch),
                           Path(out) if out else None, backup)

    def _apply(self, rom: Path, patch: Path,
               out: Optional[Path], backup: bool) -> dict:
        try:
            result, old_sz, new_sz = apply_patch_file(rom, patch, out, backup)
            return {
                "ok": True,
                "output": str(result),
                "old_size": old_sz,
                "new_size": new_sz,
            }
        except PatchError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class _BiosAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def scan(self) -> list:
        result = []
        for b in scan_bios():
            result.append({
                "name": b.name,
                "path": b.path,
                "size": b.size,
                "md5": b.md5,
                "known_as": b.known_as,
            })
        return result

    def identify(self, path: str) -> Optional[str]:
        p = Path(path)
        if not p.exists():
            return None
        return identify_bios_platform(p)

    def organize(self, dry_run: bool = False) -> dict:
        result = auto_organize_bios(dry_run=dry_run)
        if not dry_run:
            clear_bios_check_cache()
        return result

    def import_files(self, paths: list) -> int:
        count = 0
        for p in paths:
            src = Path(p)
            if not src.exists() or not src.is_file():
                continue
            try:
                dst = BIOS_DIR / src.name
                if dst.exists():
                    dst = dst.with_name(
                        f"{dst.stem}_{int(time.time() * 1000) % 100000}"
                        f"{dst.suffix}")
                shutil.copy2(src, dst)
                count += 1
            except Exception as e:
                logger.exception(f"导入 BIOS 失败: {src}")
        if count:
            clear_bios_check_cache()
        return count


class _StatsAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def summary(self) -> dict:
        games = load_games()
        total_sec = sum(g.play_seconds for g in games)
        by_plat = {}
        for g in games:
            by_plat[g.platform] = by_plat.get(g.platform, 0) + g.play_seconds
        return {
            "total_seconds": total_sec,
            "total_games": len(games),
            "total_launches": STATS.get("launches", 0),
            "by_platform": by_plat,
        }

    def daily(self, days: int = 30) -> list:
        daily = STATS.get("daily", {})
        result = []
        now = time.time()
        for i in range(days - 1, -1, -1):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            day_data = daily.get(d, {}) or {}
            result.append({
                "date": d,
                "total_seconds": sum(day_data.values()),
                "by_platform": dict(day_data),
            })
        return result

    def record_playtime(self, platform: str, seconds: int) -> None:
        record_playtime(platform, int(seconds))


class _SettingsAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def get(self, key: str, default=None):
        return SETTINGS.get(key, default)

    def set(self, key: str, value) -> bool:
        SETTINGS[key] = value
        save_settings()
        self._parent._emit(Events.SETTINGS_CHANGED, key=key, value=value)
        return True

    def all(self) -> dict:
        return dict(SETTINGS)

    def save(self) -> bool:
        try:
            save_settings()
            return True
        except Exception:
            return False

    def reload(self) -> dict:
        load_settings()
        return dict(SETTINGS)

    def folders(self) -> list:
        return list(FOLDERS_CONFIG.get("folders", []))

    def active_folder(self) -> dict:
        return get_active_folder()

    def set_active_folder(self, index: int) -> bool:
        folders = FOLDERS_CONFIG.get("folders", [])
        if not (0 <= index < len(folders)):
            return False
        FOLDERS_CONFIG["active_index"] = index
        save_folders_config()
        self._parent._emit(Events.FOLDERS_CHANGED)
        return True


class _MirrorsAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def list(self, use_api: bool = False) -> list:
        return list(get_api_mirror_list() if use_api else get_mirror_list())

    def set_enabled(self, value: bool) -> bool:
        MIRRORS_CONFIG["enabled"] = bool(value)
        save_mirrors()
        self._parent._emit(Events.MIRRORS_CHANGED)
        return True

    def set_auto(self, value: bool) -> bool:
        MIRRORS_CONFIG["auto"] = bool(value)
        save_mirrors()
        self._parent._emit(Events.MIRRORS_CHANGED)
        return True

    def set_region(self, region: str) -> bool:
        if region not in ("auto", "cn", "overseas", "direct"):
            return False
        MIRRORS_CONFIG["region"] = region
        save_mirrors()
        self._parent._emit(Events.MIRRORS_CHANGED)
        return True

    def get_region(self) -> str:
        return MIRRORS_CONFIG.get("region", "auto")

    def test_all(self, use_api: bool = False) -> Job:
        test_url = ("https://api.github.com/rate_limit" if use_api
                    else "https://github.com/robots.txt")
        worker = MirrorTestWorker(test_url, use_api=use_api)
        return Job(worker)

    def order(self, test_url: str = "", use_api: bool = False) -> list:
        url = test_url or ("https://api.github.com/rate_limit" if use_api
                           else "https://github.com/robots.txt")
        return MirrorRouter.order_mirrors(url, use_api=use_api)

    def clear_probe_cache(self) -> None:
        MirrorRouter.clear_probe_cache()
        self._parent._emit(Events.MIRRORS_CHANGED)


class _PluginsAPI:
    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def list(self) -> list:
        result = []
        if not PLUGINS_DIR.exists():
            return result
        enabled_state = load_plugin_enabled()
        for d in sorted(PLUGINS_DIR.iterdir()):
            if not d.is_dir():
                continue
            mf = d / "plugin.json"
            if not mf.exists():
                continue
            try:
                meta = json.loads(mf.read_text("utf-8"))
                pid = meta.get("id", d.name)
                result.append({
                    "id": pid,
                    "path": str(d),
                    "meta": meta,
                    "enabled": bool(enabled_state.get(pid, True)),
                })
            except Exception as e:
                result.append({
                    "id": d.name,
                    "path": str(d),
                    "meta": {},
                    "enabled": False,
                    "error": str(e),
                })
        return result

    def enable(self, plugin_id: str, value: bool) -> bool:
        state = load_plugin_enabled()
        state[plugin_id] = bool(value)
        save_plugin_enabled(state)
        return True

    def import_zip(self, path: str) -> dict:
        ok, pid, filled, msg = _import_plugin_any(
            Path(path), overwrite=True)
        return {
            "ok": ok,
            "id": pid,
            "filled": filled,
            "error": msg,
        }


class _KeymapAPI:
    """★ v1.8.0：按键映射 API。"""

    def __init__(self, parent: "MikanAPI"):
        self._parent = parent

    def get_global(self) -> list:
        return [e.to_dict() for e in get_keymapper().get_global_map()]

    def set_global(self, entries: list) -> bool:
        km = get_keymapper()
        km.set_global_map([KeyMapEntry.from_dict(e) for e in entries])
        km.save_to_files()
        self._parent._emit(Events.KEYMAP_CHANGED)
        return True

    def get_game(self, game_path: str) -> list:
        return [e.to_dict()
                for e in get_keymapper().get_game_map(game_path)]

    def set_game(self, game_path: str, entries: list) -> bool:
        km = get_keymapper()
        km.set_game_map(game_path,
                        [KeyMapEntry.from_dict(e) for e in entries])
        km.save_to_files()
        self._parent._emit(Events.KEYMAP_CHANGED)
        return True

    def clear_game(self, game_path: str) -> bool:
        km = get_keymapper()
        km.clear_game_map(game_path)
        km.save_to_files()
        self._parent._emit(Events.KEYMAP_CHANGED)
        return True

    def is_available(self) -> bool:
        return HAS_KEYBOARD

    def start(self) -> bool:
        return start_keymapper()

    def stop(self) -> None:
        stop_keymapper()


def _init_mikan_api_subclasses():
    """把子 API 类注册到 MikanAPI.__init__ 里。"""
    original_init = MikanAPI.__init__

    def new_init(self, settings=None, folders=None, parent=None):
        original_init(self, settings, folders, parent)
        self._register("games", _GamesAPI(self))
        self._register("engines", _EnginesAPI(self))
        self._register("download", _DownloadAPI(self))
        self._register("scrape", _ScrapeAPI(self))
        self._register("patch", _PatchAPI(self))
        self._register("bios", _BiosAPI(self))
        self._register("stats", _StatsAPI(self))
        self._register("settings", _SettingsAPI(self))
        self._register("mirrors", _MirrorsAPI(self))
        self._register("plugins", _PluginsAPI(self))
        self._register("keymap", _KeymapAPI(self))

    MikanAPI.__init__ = new_init


_init_mikan_api_subclasses()


# ============================================================
# 40. 全局异常钩子
# ============================================================
_CRASH_DIALOG_SHOWN = False


def _show_crash_dialog(tb_text: str, zip_path):
    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle(tr("crash_title"))
        box.setText(tr("crash_body"))
        if zip_path:
            box.setInformativeText(tr("crash_pack_ready", path=str(zip_path)))
        else:
            box.setInformativeText(tr("crash_pack_failed"))
        box.setDetailedText(tb_text)
        btn_save = box.addButton(tr("crash_save_pack"),
                                 QMessageBox.ActionRole)
        btn_open = box.addButton(tr("crash_open_log"),
                                 QMessageBox.ActionRole)
        btn_close = box.addButton(tr("crash_close"),
                                  QMessageBox.AcceptRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_save and zip_path:
            dst, _ = QFileDialog.getSaveFileName(
                None, tr("crash_save_pack"),
                str(Path.home() / Path(zip_path).name),
                "ZIP (*.zip)")
            if dst:
                try:
                    shutil.copy2(zip_path, dst)
                except Exception:
                    pass
        elif clicked == btn_open:
            try:
                os.startfile(str(LOG_DIR))
            except Exception:
                pass
    except Exception:
        pass
    finally:
        try:
            QApplication.quit()
        except Exception:
            pass


def _excepthook(exc_type, exc_value, exc_tb):
    global _CRASH_DIALOG_SHOWN
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    tb_text = "".join(
        traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        logger.error(f"未捕获异常:\n{tb_text}")
    except Exception:
        pass

    try:
        if not SETTINGS.get("crash_report_enabled", True):
            return
    except Exception:
        pass

    if _CRASH_DIALOG_SHOWN:
        return
    _CRASH_DIALOG_SHOWN = True

    path = None
    try:
        path = build_crash_report(exc_text=tb_text)
    except Exception:
        pass

    try:
        app = QApplication.instance()
        if app is None:
            return
        _show_crash_dialog(tb_text, path)
    except Exception:
        pass


def _threading_excepthook(args):
    _excepthook(args.exc_type, args.exc_value, args.exc_traceback)


sys.excepthook = _excepthook
threading.excepthook = _threading_excepthook


# ============================================================
# 41. 入口
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    try:
        refresh_machine_tier()
    except Exception as e:
        logger.debug(f"刷新机器档次失败: {e}")

    try:
        setup_logging()
    except Exception:
        pass

    win = MainWindow()
    win.show()

    try:
        ok, msg = check_win10_1809_minimum()
        if not ok:
            QTimer.singleShot(500, lambda: QMessageBox.warning(
                win, tr("win_version_too_old_title"), msg))
    except Exception as e:
        logger.debug(f"Win 版本检查失败: {e}")

    try:
        win._plugin_manager.emit("app_start")
    except Exception:
        pass

    sys.exit(app.exec())


# ============================================================
# 42. __all__
# ============================================================
__all__ = [
    # 入口
    "get_api",
    "MikanAPI",
    "Job",
    "Events",
    # 数据结构
    "GameEntry",
    "EmulatorConfig",
    "BiosFile",
    "KeyMapEntry",
    # 核心工具
    "load_games",
    "save_games",
    "load_installed",
    "save_installed",
    "load_engines_json",
    "save_engines_json",
    "load_settings",
    "save_settings",
    "load_folders_config",
    "save_folders_config",
    "load_mirrors",
    "save_mirrors",
    # 补丁
    "patch_ips",
    "patch_ups",
    "apply_patch_file",
    "PatchError",
    # 镜像
    "MirrorRouter",
    # Job Object
    "JobObject",
    "get_job_object",
    "assign_to_job",
    "is_in_job",
    # KeyMapper
    "KeyMapper",
    "KeyMapEntry",
    "get_keymapper",
    "start_keymapper",
    "stop_keymapper",
    # 启动
    "launch_game",
    "open_engine_settings",
    "LaunchError",
    # 常量
    "APP_NAME",
    "APP_VERSION",
    "APP_REPO",
    "DATA_DIR",
    "ROM_DIR",
    "BIOS_DIR",
    "COVER_DIR",
    "SAVE_DIR",
    "LOG_DIR",
    "PLUGINS_DIR",
    "KEYMAP_FILE",
    "KEYMAP_GAMES_FILE",
]


# ============================================================
# 43. 迁移说明
# ============================================================
"""
【v1.7.0 → v1.8.0 迁移说明】

一、新增功能

1. Job Object 托管模拟器子进程
   - 新增 JobObject 类（ctypes 封装 Windows Job Object）
   - launch_game 启动后自动 assign_to_job(proc.pid)
   - 主窗口 closeEvent 里 job.close() → 自动杀模拟器
   - 设置项：job_object_kill_on_close（默认 True）

2. 虚拟按键映射（KeyMapper）
   - 新增 KeyMapper 类（keyboard 库低级键盘钩子）
   - 仅当模拟器窗口在前台（且 PID 在 Job 中）时生效
   - 支持全局映射 + 按游戏覆盖
   - 设置项：keymap_enabled / keymap_only_foreground / keymap_show_osd
   - UI：设置页新增「虚拟按键映射」块 + KeyMapDialog 编辑器
   - 文件：config/keymap.json / config/keymap_games.json

3. 模拟器参数 schema（ParamSchemaDialog）
   - engines.json 每个引擎新增 param_schema 字段
   - ParamSchemaDialog 根据 schema 动态生成表单
   - 支持的控件：bool / int / choice / text / file / dir
   - GameEntry 新增 param_values 字段（dict）
   - _build_param_args() 把 param_values 拼成命令行参数
   - resolve_launch_args() 集成 param_args

4. GitHub Releases 全量拉取（ReleasesWorker + UpdateDialog）
   - 新增 ReleasesWorker：拉取 /releases?per_page=30
   - 新增 UpdateDialog：表格列出每个引擎的可用版本，用户自己选
   - 支持 GitHub Token（settings.github_token），提高速率限制
   - 支持镜像开关（UpdateDialog 底部勾选）
   - 支持预发布版本标记

5. ChartWidget 悬停精确时间提示
   - 鼠标悬停显示「日期 / 精确时长 / 原始秒数」
   - 动态阈值（7 天图约 40px，30 天图约 15px）
   - 自动避让窗口边缘

6. 平台列 UI 错位修复
   - 新增 PlatformComboDelegate（QStyledItemDelegate）
   - 替代原来的 setCellWidget(QComboBox)
   - 修复滚动/列宽调整时的错位

7. MikanAPI 新增子 API
   - games / engines / download / scrape / patch / bios / stats /
     settings / mirrors / plugins / keymap

二、新增设置项

- github_token: ""                GitHub Token
- job_object_kill_on_close: True  主程序退出时杀模拟器
- keymap_enabled: False           启用按键映射
- keymap_only_foreground: True    仅前台生效
- keymap_show_osd: True           显示 OSD
- download_use_mirror: True       下载默认走镜像

三、新增文件

- config/keymap.json              全局按键映射
- config/keymap_games.json        按游戏覆盖

四、新增可选依赖

- keyboard: 虚拟按键映射（pip install keyboard）

五、API 使用示例

import mikan_emu
api = mikan_emu.get_api()

# 游戏库
games = api.games.list()
api.games.launch(games[0]["path"])

# 下载（自动走镜像）
job = api.download.start("sfc", "snes9x")
job.progress.connect(lambda cur, total: print(f"{cur}/{total}"))

# 镜像
api.mirrors.set_region("overseas")
api.mirrors.clear_probe_cache()

# 按键映射
api.keymap.set_global([
    {"physical": "a", "virtual": "b", "enabled": True, "note": ""},
])

# 订阅事件
api.on(mikan_emu.Events.GAMES_CHANGED, lambda: print("changed"))
api.on(mikan_emu.Events.GAME_CLOSED, lambda game, seconds: print(seconds))

# 补丁
result = api.patch.apply_ips("game.bin", "trans.ips")

六、注意事项

1. Job Object 只在 Windows 生效；Linux/macOS 上 assign_to_job 返回 False。
2. KeyMapper 需要 keyboard 库；未安装时设置页会提示，不影响其他功能。
3. keyboard 库的全局钩子可能被杀毒软件拦截，请加白名单。
4. param_schema 只对已配置的引擎生效；未配置的引擎显示「暂无参数模板」。
5. GitHub Token 可在 https://github.com/settings/tokens 申请（只需 public_repo 权限）。
"""


if __name__ == "__main__":
    main()