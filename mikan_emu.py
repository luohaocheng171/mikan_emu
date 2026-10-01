# -*- coding: utf-8 -*-
"""
mikan_emu v1.1.0
模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言 + 平台编辑器
+ 性能监控 + 局域网聊天/文件/共享 + 局域网传输（内嵌 LocalSend Web）

Python 3.11+ / PySide6 / requests / loguru / py7zr / rarfile / psutil
可选：PySide6-WebEngine（内嵌浏览器）

【法律】不提供 BIOS、不提供 ROM、不二次分发模拟器

v1.1.0 变更：
- ★ 重写「局域网」页：独立版 mikan_lan v1.2.x 全功能整合
    · 聊天 Tab + 共享文件夹 Tab
    · 右键「发送文件给 TA」/「发文件给所有人」
    · 拖拽文件直接发送 / 广播
    · 表情面板
    · 共享文件夹（上传 + 浏览 + 下载）
    · 消息 broadcast 标记，私聊/全体分离
    · 接收方弹窗提示
- ★ 协议统一为 mikan_lan v1.2.x（magic = mikan_lan）
- ★ 旧版 mikan_emu v1.0.0 及独立版 mikan_lan 与本版不互通
- ★ 保留 v1.0.0 全部功能（含 LocalSend Web 内嵌页）
"""

# ============================================================
# 0. 代理 + 环境变量
# ============================================================
import os

os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu --disable-software-rasterizer"
)

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

OPTIONAL = {
    "PySide6.QtWebEngineWidgets": "PySide6-WebEngine",
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
        print(f"       如需完整功能（内嵌浏览器），执行:")
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
import hashlib
import hmac
import json
import re
import shutil
import socket
import subprocess as sp
import tarfile
import tempfile
import threading
import time
import uuid as _uuid
import webbrowser
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

try:
    from PySide6.QtCore import (
        Qt, QThread, Signal, QModelIndex, QAbstractTableModel,
        QSortFilterProxyModel, QTimer, QSize, QObject, QPoint, QUrl,
    )
    from PySide6.QtGui import (
        QColor, QFont, QAction, QPixmap, QIcon, QPainter, QPen,
        QBrush, QLinearGradient, QPolygon
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
        QTableWidget, QTableWidgetItem, QSizePolicy
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
APP_VERSION = "1.1.0"

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

for d in (DATA_DIR, CONFIG_DIR, LANG_DIR, ENGINE_DIR, ENGINE_DOWNLOAD_DIR,
          BIOS_DIR, ROM_DIR, SAVE_DIR, SAVE_BACKUP_DIR, COVER_DIR,
          CHEAT_DIR, BACKUP_DIR, LOG_DIR, TEMP_DIR, EXPORT_DIR,
          LAN_DIR, LAN_HISTORY_DIR, LAN_FILES_DIR, LAN_SHARED_DIR,
          LAN_SHARED_DOWNLOAD_DIR, WEBENGINE_DIR):
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

logger.remove()
logger.add(
    LOG_DIR / "mikan_emu_{time:YYYY-MM-DD}.log",
    rotation="10 MB", retention="14 days",
    encoding="utf-8", level="DEBUG",
)
if sys.stderr is not None:
    logger.add(sys.stderr, level="INFO")

if not HAS_WEBENGINE:
    logger.warning("QtWebEngine 未安装，「局域网传输」页将降级为外部浏览器模式")

# ============================================================
# 3.5 内置默认 JSON 数据
# ============================================================
DEFAULT_ENGINES_JSON_STR = r"""
{
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
        "official": true
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
        "archive": "zip",
        "match": {"exe": ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt-x64-Release.exe", "duckstation-qt-x64-Debug.exe", "duckstation.exe"], "folder": ["duckstation"], "keywords": ["duckstation"]},
        "launch_template": "{exe} -batch \"{rom}\"",
        "bios_dir": "bios",
        "official": true
      },
      "epsxe": {
        "version": "2.0.18",
        "url": "manual",
        "official_site": "https://www.epsxe.com/",
        "archive": "7z",
        "match": {"exe": ["ePSXe.exe"], "folder": ["ePSXe", "epsxe"], "keywords": ["epsxe"]},
        "launch_template": "{exe} -nogui -loadiso \"{rom}\"",
        "official": false,
        "note": "闭源，需手动下载"
      },
      "xebra": {
        "version": "221106",
        "url": "manual",
        "official_site": "http://drhell.web.fc2.com/ps1/",
        "archive": "zip",
        "match": {"exe": ["xebra.exe", "XEBRA.exe"], "folder": ["xebra", "XEBRA"], "keywords": ["xebra"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "闭源，需手动下载"
      }
    }
  },
  "ss": {
    "platform_name": "SS / 世嘉土星",
    "rom_extensions": [".bin", ".cue", ".iso", ".chd", ".mds", ".mdf"],
    "engines": {
      "mednafen": {
        "version": "1.32.1",
        "url": "https://mednafen.github.io/releases/files/mednafen-1.32.1-win64.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["mednafen.exe"], "folder": ["mednafen"], "keywords": ["mednafen"]},
        "bios_required": true,
        "bios_files": ["mpr-17933.bin", "sega_101.bin"],
        "bios_dir": "firmware",
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      },
      "ssf": {
        "version": "PreviewVer R38",
        "url": "manual",
        "official_site": "http://redlotusflame.uupan.net/",
        "archive": "7z",
        "match": {"exe": ["SSF.exe", "SSF_PreviewVer.exe"], "folder": ["SSF", "SSF_PreviewVer"], "keywords": ["ssf"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "闭源，需手动下载"
      },
      "ymir": {
        "version": "0.3.3",
        "url": "https://github.com/ymir-emu/Ymir/releases/download/v0.3.3/ymir-windows-x86_64-SSE2-v0.3.3.zip",
        "url_type": "github_release",
        "github_repo": "ymir-emu/Ymir",
        "archive": "zip",
        "match": {"exe": ["Ymir.exe", "ymir.exe"], "folder": ["Ymir", "ymir"], "keywords": ["ymir"]},
        "bios_required": true,
        "bios_files": ["sega_101.bin", "mpr-17933.bin"],
        "bios_dir": "roms",
        "launch_template": "{exe} \"{rom}\"",
        "official": true,
        "note": "需要 IPL ROM + CD Block ROM"
      },
      "brimir": {
        "version": "0.5.4",
        "url": "https://github.com/coredds/brimir/releases/download/v0.5.4/brimir-v0.5.4-windows-x64.zip",
        "url_type": "libretro",
        "libretro_core": "brimir_libretro.dll",
        "archive": "zip",
        "match": {"exe": ["brimir_libretro.dll"], "keywords": ["brimir"]},
        "launch_template": "{retroarch} -L \"{core}\" \"{rom}\"",
        "official": true,
        "note": "libretro 核心，需 RetroArch"
      },
      "yaba_sanshiro_2": {
        "version": "unknown",
        "url": "manual",
        "official_site": "https://www.uoyabause.org/",
        "archive": "zip",
        "match": {"exe": ["YabaSanshiro.exe", "yabasanshiro.exe"], "folder": ["YabaSanshiro", "yabasanshiro"], "keywords": ["yaba"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "闭源/移动端，需手动下载"
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
        "archive": "zip",
        "match": {"exe": ["flycast.exe", "Flycast.exe"], "folder": ["flycast", "Flycast"], "keywords": ["flycast"]},
        "bios_required": true,
        "bios_files": ["dc_boot.bin", "dc_flash.bin"],
        "bios_dir": "data",
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      },
      "redream": {
        "version": "unknown",
        "url": "manual",
        "official_site": "https://redream.io/",
        "archive": "zip",
        "match": {"exe": ["redream.exe", "Redream.exe"], "folder": ["redream", "Redream"], "keywords": ["redream"]},
        "bios_required": true,
        "bios_files": ["dc_boot.bin", "dc_flash.bin"],
        "bios_dir": "bios",
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "闭源，需手动下载"
      },
      "deecy": {
        "version": "0.6.3",
        "url": "https://github.com/Senryoku/Deecy/releases/download/v0.6.3/Deecy-x86_64_v4-windows.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["deecy.exe", "Deecy.exe"], "folder": ["deecy", "Deecy"], "keywords": ["deecy"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true,
        "note": "Zig 实验性项目"
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
        "archive": "zip",
        "match": {"exe": ["DreamPotato.exe", "dreampotato.exe"], "folder": ["DreamPotato", "dreampotato"], "keywords": ["dreampotato"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "archive": "7z",
        "match": {"exe": ["mGBA.exe", "mgba.exe", "mgba-qt.exe"], "folder": ["mgba", "mGBA"], "keywords": ["mgba"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "archive": "7z",
        "match": {"exe": ["pcsx2-qt.exe", "pcsx2.exe"], "folder": ["pcsx2"], "keywords": ["pcsx2"]},
        "bios_required": true,
        "bios_dir": "bios",
        "launch_template": "{exe} -batch \"{rom}\"",
        "official": true
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
        "official": true
      },
      "mesence": {
        "version": "2.2.1",
        "url": "https://github.com/nesdev-org/MesenCE/releases/download/2.2.1/Mesen_2.2.1_Windows.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["Mesen.exe"], "folder": ["Mesen"], "keywords": ["mesen"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "archive": "zip",
        "match": {"exe": ["mupen64plus-ui-console.exe", "mupen64plus.exe"], "folder": ["mupen64plus"], "keywords": ["mupen64plus", "mupen"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      },
      "gopher64": {
        "version": "1.1.36",
        "url": "https://github.com/gopher64/gopher64/releases/download/v1.1.36/gopher64-windows-x86_64.exe",
        "url_type": "direct",
        "archive": "bare_exe",
        "match": {"exe": ["gopher64-windows-x86_64.exe", "gopher64.exe"], "keywords": ["gopher64"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true,
        "note": "裸 exe，下载后直接使用"
      },
      "ares": {
        "version": "148",
        "url": "https://github.com/ares-emulator/ares/releases/download/v148/ares-windows-x64.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["ares.exe"], "folder": ["ares"], "keywords": ["ares"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true,
        "note": "多平台模拟器"
      },
      "simple64": {
        "version": "2024.12.1",
        "url": "https://github.com/simple64/simple64/releases/download/v2024.12.1/simple64-win64-b49e10e.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["simple64-gui.exe", "simple64.exe"], "folder": ["simple64"], "keywords": ["simple64"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      },
      "rmg": {
        "version": "0.9.0",
        "url": "https://github.com/Rosalie241/RMG/releases/download/v0.9.0/RMG-Portable-Windows64-v0.9.0.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["RMG.exe", "rmg.exe"], "folder": ["RMG", "rmg"], "keywords": ["rmg"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      },
      "project64": {
        "version": "unknown",
        "url": "manual",
        "official_site": "https://www.pj64-emu.com/",
        "archive": "zip",
        "match": {"exe": ["Project64.exe", "pj64.exe"], "folder": ["Project64", "pj64"], "keywords": ["project64", "pj64"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "需手动下载"
      },
      "cen64": {
        "version": "unknown",
        "url": "manual",
        "official_site": "https://github.com/cen64/cen64",
        "archive": "zip",
        "match": {"exe": ["cen64.exe"], "keywords": ["cen64"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true,
        "note": "精度优先，无 Windows 预编译包"
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
        "archive": "zip",
        "match": {"exe": ["desmume.exe", "DeSmuME.exe"], "folder": ["desmume", "DeSmuME"], "keywords": ["desmume"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      },
      "melonds": {
        "version": "1.1",
        "url": "https://melonds.kuribo64.net/downloads/melonDS-1.1-windows-x86_64.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["melonDS.exe", "melonds.exe"], "folder": ["melonDS", "melonds"], "keywords": ["melonds"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "official": true
      },
      "kega-fusion": {
        "version": "3.64",
        "url": "manual",
        "official_site": "https://kega-fusion.com/",
        "archive": "zip",
        "match": {"exe": ["Fusion.exe", "Kega Fusion.exe"], "folder": ["Kega Fusion", "Fusion"], "keywords": ["fusion", "kega"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "闭源，需手动下载"
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
        "official_site": "https://github.com/LIJI32/SameBoy/releases",
        "archive": "zip",
        "match": {"exe": ["sameboy.exe", "SameBoy.exe"], "folder": ["sameboy", "SameBoy"], "keywords": ["sameboy"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true,
        "note": "挂官网，用户手动下载"
      },
      "gambatte": {
        "version": "0.5.0",
        "url": "manual",
        "official_site": "https://github.com/sinamas/gambatte",
        "archive": "zip",
        "match": {"exe": ["gambatte_qt.exe", "gambatte_sdl.exe", "gambatte.exe"], "folder": ["gambatte", "Gambatte"], "keywords": ["gambatte"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "已停更，需手动下载。建议改用 mGBA"
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
        "archive": "zip",
        "match": {"exe": ["PPSSPPWindows64.exe", "PPSSPPWindows.exe", "PPSSPP.exe"], "folder": ["PPSSPP", "ppsspp"], "keywords": ["ppsspp"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "official": true
      },
      "yuzu": {
        "version": "unknown",
        "url": "manual",
        "official_site": "https://github.com/yuzu-mirror",
        "archive": "zip",
        "match": {"exe": ["yuzu.exe", "yuzu-cmd.exe"], "folder": ["yuzu", "Yuzu"], "keywords": ["yuzu"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "已停止分发，只剩社区镜像"
      }
    }
  },
  "pce": {
    "platform_name": "PCE / TurboGrafx",
    "rom_extensions": [".pce", ".sgx"],
    "engines": {
      "mednafen": {
        "version": "1.32.1",
        "url": "https://mednafen.github.io/releases/files/mednafen-1.32.1-win64.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["mednafen.exe"], "folder": ["mednafen"], "keywords": ["mednafen"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      }
    }
  },
  "neogeo": {
    "platform_name": "Neo Geo",
    "rom_extensions": [".zip", ".neo"],
    "engines": {
      "mame": {
        "version": "0.289",
        "url": "https://github.com/mamedev/mame/releases/download/mame0289/mame0289b_x64.exe",
        "url_type": "direct",
        "archive": "7z_sfx",
        "match": {"exe": ["mame.exe", "mame64.exe"], "folder": ["mame", "MAME"], "keywords": ["mame"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      }
    }
  },
  "arcade": {
    "platform_name": "Arcade",
    "rom_extensions": [".zip", ".7z"],
    "engines": {
      "mame": {
        "version": "0.289",
        "url": "https://github.com/mamedev/mame/releases/download/mame0289/mame0289b_x64.exe",
        "url_type": "direct",
        "archive": "7z_sfx",
        "match": {"exe": ["mame.exe", "mame64.exe"], "folder": ["mame", "MAME"], "keywords": ["mame"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      }
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
        "bios_required": true,
        "bios_dir": "keropi",
        "launch_template": "{retroarch} -L \"{core}\" \"{rom}\"",
        "official": true,
        "note": "libretro 核心，BIOS 放 retroarch/system/keropi/"
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
        "bios_required": true,
        "bios_dir": "np2kai",
        "launch_template": "{retroarch} -L \"{core}\" \"{rom}\"",
        "official": true,
        "note": "libretro 核心，BIOS 放 retroarch/system/np2kai/"
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
        "archive": "zip",
        "match": {"exe": ["Tsugaru.exe", "tsugaru.exe"], "folder": ["Tsugaru", "tsugaru"], "keywords": ["tsugaru"]},
        "bios_required": true,
        "bios_dir": "rom",
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "archive": "zip",
        "match": {"exe": ["pcfxemu.exe", "PCFXemu.exe"], "folder": ["pcfxemu", "PCFXemu"], "keywords": ["pcfx"]},
        "bios_required": true,
        "bios_dir": "bios",
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "archive": "zip",
        "match": {"exe": ["openmsx.exe"], "folder": ["openMSX", "openmsx"], "keywords": ["openmsx"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
      },
      "bluemsx": {
        "version": "2.8.2",
        "url": "https://www.msxblue.com/bluemsx/rel_download/blueMSXv282.zip",
        "url_type": "direct",
        "archive": "zip",
        "match": {"exe": ["blueMSX.exe", "bluemsx.exe"], "folder": ["blueMSX", "bluemsx"], "keywords": ["bluemsx"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true
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
        "archive": "zip",
        "match": {"exe": ["86Box.exe", "86box.exe"], "folder": ["86Box", "86box"], "keywords": ["86box"]},
        "launch_template": "{exe}",
        "bios_dir": "roms",
        "bios_required": true,
        "official": true,
        "note": "x86 PC 模拟器。BIOS ROM 放 roms/ 子目录（86Box 默认）。启动后需在 UI 里选机型。"
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
        "archive": "zip",
        "match": {"exe": ["pcem.exe", "PCem.exe"], "folder": ["PCem", "pcem"], "keywords": ["pcem"]},
        "launch_template": "{exe}",
        "bios_dir": "roms",
        "bios_required": true,
        "official": true,
        "note": "x86 PC 模拟器。BIOS ROM 放 roms/ 子目录。启动后需在 UI 里选机型。"
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
        "official": true,
        "note": "⚠ 实验性：极早期，能跑的游戏有限。需要从自己的 PS4 导出游戏。"
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
        "official": true,
        "note": "⚠ 实验性：极早期，目前只能跑极少数游戏，需要高端硬件。"
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
        "bios_required": true,
        "bios_dir": "bios",
        "official": true,
        "note": "需要 Xbox BIOS（mcpx_1.0.bin 等），游戏需从自己光盘提取。"
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
        "official": true,
        "note": "Canary 分支，主开发分支。需要 64 位 CPU + AVX。"
      },
      "xenia_edge": {
        "version": "edge",
        "url": "https://github.com/has207/xenia-edge/releases/download/95b14f5/xenia_edge_windows.zip",
        "url_type": "direct",
        "github_repo": "has207/xenia-edge",
        "archive": "zip",
        "match": {"exe": ["xenia_edge.exe", "xenia-edge.exe", "xenia.exe"], "folder": ["xenia_edge", "xenia-edge", "Xenia Edge"], "keywords": ["xenia_edge", "xenia-edge"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "第三方优化分支，兼容性可能不如 Canary。"
      }
    }
  },
  "switch_alt": {
    "platform_name": "Switch（备用引擎）",
    "rom_extensions": [".nsp", ".xci", ".nsz", ".xcz"],
    "engines": {
      "suyu": {
        "version": "0.0.12",
        "url": "https://github.com/suyu-emu/suyu-main/releases/download/v0.0.12/suyu-windows-x86_64.zip",
        "url_type": "direct",
        "github_repo": "suyu-emu/suyu-main",
        "archive": "zip",
        "match": {"exe": ["suyu.exe"], "folder": ["suyu"], "keywords": ["suyu"]},
        "launch_template": "{exe} -g \"{rom}\"",
        "bios_required": true,
        "bios_dir": "keys",
        "official": false,
        "note": "基于 yuzu 的分支，已停止开发。需要 prod.keys 和固件。"
      }
    }
  },
  "3ds": {
    "platform_name": "3DS",
    "rom_extensions": [".3ds", ".cia", ".cci", ".cxi"],
    "engines": {
      "zakuro": {
        "version": "0.2.9",
        "url": "https://github.com/fearkov/zakuro/releases/download/v0.2.9/zakuro-windows-x86_64.zip",
        "url_type": "direct",
        "github_repo": "fearkov/zakuro",
        "archive": "zip",
        "match": {"exe": ["zakuro.exe"], "folder": ["zakuro"], "keywords": ["zakuro"]},
        "launch_template": "{exe} \"{rom}\"",
        "official": true,
        "note": "⚠ 实验性：Rust 重写的 3DS 模拟器，用 AOT 重编译。极早期，兼容性极差。"
      }
    }
  },
  "multi": {
    "platform_name": "万能 / 前端",
    "rom_extensions": [],
    "engines": {
      "retroarch": {
        "version": "1.22.2",
        "url": "https://buildbot.libretro.com/stable/1.22.2/windows/x86_64/RetroArch.7z",
        "url_type": "direct",
        "archive": "7z",
        "match": {"exe": ["retroarch.exe"], "folder": ["RetroArch", "retroarch"], "keywords": ["retroarch"]},
        "launch_template": "{exe} -L \"{core}\" \"{rom}\"",
        "official": true,
        "note": "libretro 前端，配合核心使用"
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
        "official_site": "https://drive.google.com/file/d/1yqP781y-TJsB_dSBy4EgSKdNZefFdBSA/view",
        "archive": "zip",
        "match": {"exe": []},
        "launch_template": "{exe} \"{rom}\"",
        "official": false,
        "note": "来源不明，手动下载"
      }
    }
  }
}
"""

DEFAULT_FOLDERS_JSON = {
    "folders": [{"name": "默认工作区", "path": str(DATA_DIR)}],
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
    # 局域网
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
}

DEFAULT_MIRRORS_JSON = {
    "enabled": True,
    "mirrors": [
        "https://ghproxy.com/",
        "https://gh-proxy.com/",
        "https://github.moeyy.xyz/",
        "",
    ],
    "api_mirrors": [
        "https://api.kkgithub.com/",
        "https://gh-proxy.com/https://api.github.com/",
        "",
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


def _ensure_json_file(path: Path, default_data):
    if path.exists():
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2, ensure_ascii=False)
        logger.info(f"生成默认配置: {path}")
    except Exception as e:
        logger.exception(f"写出 {path} 失败: {e}")


def _ensure_all_json_files():
    _ensure_json_file(FOLDERS_FILE, DEFAULT_FOLDERS_JSON)
    _ensure_json_file(SETTINGS_FILE, DEFAULT_SETTINGS_JSON)
    _ensure_json_file(MIRRORS_FILE, DEFAULT_MIRRORS_JSON)
    _ensure_json_file(SAVE_PATHS_FILE, DEFAULT_SAVE_PATHS_JSON)
    _ensure_json_file(CHEAT_PATHS_FILE, DEFAULT_CHEAT_PATHS_JSON)
    _ensure_json_file(STATS_FILE, DEFAULT_STATS_JSON)
    _ensure_json_file(UPDATE_IGNORE_FILE, DEFAULT_UPDATE_IGNORE_JSON)
    _ensure_json_file(RESOURCES_FILE, DEFAULT_RESOURCES_JSON)
    _ensure_json_file(INSTALLED_FILE, DEFAULT_INSTALLED_JSON)
    _ensure_json_file(ROMS_FILE, DEFAULT_ROMS_JSON)
    if not ENGINES_JSON.exists():
        try:
            data = json.loads(DEFAULT_ENGINES_JSON_STR)
            with open(ENGINES_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"生成默认 engines.json: {ENGINES_JSON}")
        except Exception as e:
            logger.exception(f"写出 engines.json 失败: {e}")


_ensure_all_json_files()
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
        "nav_settings": "设置",
        "toolbar_import_engine": "导入模拟器", "toolbar_download_engine": "下载模拟器",
        "toolbar_import_game": "导入游戏", "toolbar_export": "导出",
        "toolbar_refresh": "刷新", "toolbar_open_roms": "打开游戏文件夹",
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
        "bios_title": "BIOS / 固件",
        "bios_hint": "把 BIOS 文件放到 bios/ 目录，点刷新扫描。",
        "bios_empty": "bios/ 目录为空。",
        "bios_col_file": "文件", "bios_col_size": "大小",
        "bios_col_md5": "MD5", "bios_col_known": "识别",
        "bios_import_pcem_rom": "导入 PCem/86Box ROM",
        "bios_import_pcem_hint": "选择 PCem / 86Box 的 roms 目录（或包含 roms 的上级目录），自动扫描 .bin/.rom/.zip 并复制到 bios/。",
        "bios_import_pcem_done": "已导入 {n} 个 ROM 文件到 bios/",
        "bios_import_pcem_no_files": "该目录下没有找到 .bin/.rom/.zip 文件",
        "stats_title": "游戏统计", "stats_total_time": "总时长",
        "stats_total_games": "游戏总数", "stats_total_launches": "启动次数",
        "stats_by_platform": "按平台", "stats_last_7d": "最近 7 天",
        "stats_last_30d": "最近 30 天", "stats_badges": "徽章",
        "stats_daily_table": "每日游戏时长",
        "stats_badge_first": "第一次启动", "stats_badge_10h": "累计 10 小时",
        "stats_badge_50h": "单游戏 50 小时", "stats_badge_7days": "连续 7 天",
        "stats_badge_allplat": "全平台制霸",
        "stats_badge_locked": "未解锁", "stats_badge_unlocked": "已解锁",
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
        "ctx_launch": "▶ 启动游戏", "ctx_config": "⚙️ 配置启动方式…",
        "ctx_open_folder": "打开所在文件夹", "ctx_remove": "从库中移除",
        "ctx_remove_confirm": "从库中移除「{name}」？（不会删除文件）",
        "ctx_fav_add": "加入收藏", "ctx_fav_remove": "取消收藏",
        "ctx_set_cover": "设置封面…", "ctx_open_save": "打开存档目录",
        "ctx_cheat": "管理金手指", "ctx_bios": "选择 BIOS…",
        "ctx_controls": "操作说明…",
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
        "config_save": "保存", "config_cancel": "取消", "config_saved": "已保存",
        "config_no_engine": "没有可用的模拟器，请先下载/导入",
        "bios_select_title": "选择 BIOS",
        "bios_select_hint": "选中的 BIOS 会在启动游戏时复制到模拟器 BIOS 目录。",
        "bios_select_none": "不指定（用模拟器默认）",
        "bios_select_no_files": "bios/ 目录里没有 BIOS 文件。",
        "bios_select_ok": "已设置 BIOS: {name}",
        "launch_no_engine": "没有可用于 {platform} 的模拟器。请先导入模拟器，或用「⚙️ 配置启动方式」手动指定。",
        "launch_select_engine": "选择用于启动的模拟器:",
        "launch_failed": "启动失败: {err}", "launch_ok": "已启动: {name}",
        "launch_cue_hint": "已自动改用 .cue",
        "launch_bios_copied": "已复制 BIOS 到模拟器目录",
        "launch_bios_failed": "复制 BIOS 失败: {err}",
        "launch_core_missing": "缺少 RetroArch 核心: {core}。请到「设置 → RetroArch 核心目录」配置。",
        "launch_retroarch_missing": "未安装 RetroArch。请先下载/导入 RetroArch。",
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
        # ---- 局域网聊天 ----
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
        # 共享
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
        # 右键菜单
        "lan_ctx_open": "打开对话",
        "lan_ctx_ping": "发 ping",
        "lan_ctx_send_file": "📎 发送文件给 TA",
        "lan_ctx_send_file_all": "📎 发文件给所有人",
        "lan_ctx_clear": "清空记录",
        # 表情
        "lan_emoji_tip": "表情",
        # 群聊
        "lan_broadcast_title": "📢 全体（发消息给所有在线用户）",
        "lan_broadcast_confirm": "将 {name} ({size}) 广播给 {n} 个在线用户？",
        "lan_broadcast_done": "广播完成: {name}  成功 {ok}/{total}",
        "lan_broadcast_one_ok": "✅ {peer} 已收到",
        "lan_broadcast_one_fail": "❌ {peer}: {reason}",
        "lan_broadcast_no_peers": "当前没有其他在线用户。",
        # 拖拽
        "lan_drop_title": "拖拽确认",
        "lan_drop_to_peer": "发送 {n} 个文件给 {peer}？",
        "lan_drop_to_broadcast": "把 {n} 个文件广播给所有在线用户？",
        "lan_drop_no_target": "请先在左侧选中一个用户或「全体」。",
        "lan_drop_ask_share": "拖入了 {n} 个文件。\n群聊不直接发文件，是否全部加入共享文件夹？",
        # ---- 局域网传输（LocalSend Web）----
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
    },
    "en": {
        "_meta": {"name": "English", "code": "en", "translator": "Official"},
        "app_title": "mikan_emu",
        "nav_library": "Library", "nav_engines": "Emulators", "nav_bios": "BIOS",
        "nav_stats": "Stats", "nav_resources": "Resources", "nav_lan": "LAN",
        "nav_webtransfer": "LAN Transfer",
        "nav_settings": "Settings",
        "toolbar_import_engine": "Import Engine",
        "toolbar_download_engine": "Download Engine",
        "toolbar_import_game": "Import Game", "toolbar_export": "Export",
        "toolbar_refresh": "Refresh", "toolbar_open_roms": "Open ROMs",
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
        "bios_title": "BIOS / Firmware",
        "bios_hint": "Put BIOS files into bios/ folder.",
        "bios_empty": "bios/ folder is empty.",
        "bios_col_file": "File", "bios_col_size": "Size",
        "bios_col_md5": "MD5", "bios_col_known": "Known",
        "bios_import_pcem_rom": "Import PCem/86Box ROM",
        "bios_import_pcem_hint": "Pick PCem/86Box roms dir (or parent).",
        "bios_import_pcem_done": "Imported {n} ROM files to bios/",
        "bios_import_pcem_no_files": "No .bin/.rom/.zip found in that dir",
        "stats_title": "Statistics", "stats_total_time": "Total Time",
        "stats_total_games": "Games", "stats_total_launches": "Launches",
        "stats_by_platform": "By Platform", "stats_last_7d": "Last 7 Days",
        "stats_last_30d": "Last 30 Days", "stats_badges": "Badges",
        "stats_daily_table": "Daily Playtime",
        "stats_badge_first": "First Launch", "stats_badge_10h": "10h Total",
        "stats_badge_50h": "50h Single Game", "stats_badge_7days": "7-Day Streak",
        "stats_badge_allplat": "All Platforms",
        "stats_badge_locked": "Locked", "stats_badge_unlocked": "Unlocked",
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
        "ctx_launch": "▶ Launch", "ctx_config": "⚙️ Configure Launch…",
        "ctx_open_folder": "Open Folder", "ctx_remove": "Remove from Library",
        "ctx_remove_confirm": "Remove '{name}'?",
        "ctx_fav_add": "Add to Favorites",
        "ctx_fav_remove": "Remove from Favorites",
        "ctx_set_cover": "Set Cover…", "ctx_open_save": "Open Save Dir",
        "ctx_cheat": "Manage Cheats", "ctx_bios": "Select BIOS…",
        "ctx_controls": "Controls…",
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
    },
}


def _machine_translate(zh_pack: dict, lang: str) -> dict:
    """轻量机器翻译，只翻译界面里几个常用词，其它保留中文。"""
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

# ===== 第 1/5 段结束，回复"继续"输出第 2/5 段 =====

# ============================================================
# 5. 配置
# ============================================================
FOLDERS_CONFIG = {"folders": [], "active_index": 0}
SETTINGS = {
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
}
SAVE_PATHS: dict = {}
CHEAT_PATHS: dict = {}
MIRRORS_CONFIG = json.loads(json.dumps(DEFAULT_MIRRORS_JSON))
RESOURCES_CONFIG = json.loads(json.dumps(DEFAULT_RESOURCES_JSON))
STATS: dict = {}
UPDATE_IGNORE: dict = {}


def load_folders_config():
    global FOLDERS_CONFIG
    if FOLDERS_FILE.exists():
        try:
            with open(FOLDERS_FILE, "r", encoding="utf-8") as f:
                FOLDERS_CONFIG = json.load(f)
        except Exception:
            FOLDERS_CONFIG = json.loads(json.dumps(DEFAULT_FOLDERS_JSON))
    if not FOLDERS_CONFIG.get("folders"):
        FOLDERS_CONFIG = json.loads(json.dumps(DEFAULT_FOLDERS_JSON))


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
    except Exception:
        pass


def load_mirrors():
    global MIRRORS_CONFIG
    if MIRRORS_FILE.exists():
        try:
            with open(MIRRORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "mirrors" not in data:
                data["mirrors"] = list(DEFAULT_MIRRORS_JSON["mirrors"])
            if "api_mirrors" not in data:
                data["api_mirrors"] = list(DEFAULT_MIRRORS_JSON["api_mirrors"])
            if "enabled" not in data:
                data["enabled"] = True
            MIRRORS_CONFIG = data
        except Exception:
            MIRRORS_CONFIG = json.loads(json.dumps(DEFAULT_MIRRORS_JSON))


def save_mirrors():
    try:
        with open(MIRRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(MIRRORS_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


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
    except Exception:
        pass


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
    except Exception:
        pass


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
    except Exception:
        pass


def get_mirror_list() -> list:
    if not MIRRORS_CONFIG.get("enabled", True):
        return [""]
    mirrors = MIRRORS_CONFIG.get("mirrors", [])
    if not mirrors:
        return [""]
    return mirrors


def get_api_mirror_list() -> list:
    if not MIRRORS_CONFIG.get("enabled", True):
        return [""]
    mirrors = MIRRORS_CONFIG.get("api_mirrors", [])
    if not mirrors:
        return [""]
    return mirrors


def get_active_folder() -> dict:
    folders = FOLDERS_CONFIG.get("folders", [])
    idx = FOLDERS_CONFIG.get("active_index", 0)
    if folders and 0 <= idx < len(folders):
        return folders[idx]
    return {"name": "默认工作区", "path": str(DATA_DIR)}


load_folders_config()
load_settings()
load_save_paths()
load_cheat_paths()
load_mirrors()
load_resources()
load_stats()
load_update_ignore()


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
        "duckstation": [docs / "DuckStation",
                        home / ".local/share/DuckStation",
                        localappdata / "DuckStation"],
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
# 5.5 操作说明数据库
# ============================================================
CONTROLS_DB = {
    "snes9x": {"source": "https://www.snes9x.com/", "keys": {
        "方向": "方向键", "A/B/X/Y": "A / S / D / X 或键盘映射",
        "L/R": "Q / W", "Start": "Enter", "Select": "Shift",
        "存档/读档": "F5 / F7", "快进": "Tab", "全屏": "Alt+Enter", "截图": "F12"}},
    "duckstation": {"source": "https://github.com/stenzek/duckstation/wiki", "keys": {
        "方向": "WASD / 方向键", "△○×□": "I / L / K / J",
        "L1/R1/L2/R2": "Q / E / 1 / 3", "Start/Select": "Enter / Backspace",
        "存档/读档": "F1 / F4", "快进": "Tab", "全屏": "Alt+Enter"}},
    "epsxe": {"source": "https://www.epsxe.com/", "keys": {
        "方向": "方向键", "△○×□": "I / L / K / J",
        "L1/R1/L2/R2": "Q / E / 1 / 3", "Start/Select": "Enter / Space",
        "存档/读档": "F1 / F3", "全屏": "Alt+Enter"}},
    "xebra": {"source": "http://drhell.web.fc2.com/ps1/", "keys": {
        "方向": "方向键", "按键": "Z / X / C / V 等（可在设置里改）",
        "全屏": "Alt+Enter"}},
    "mednafen": {"source": "https://mednafen.github.io/documentation/", "keys": {
        "方向": "WASD 或方向键", "A/B": "K / L 或 Keypad 2/3",
        "Start/Select": "Enter / Tab", "存档/读档": "F5 / F7",
        "快进": "Tab（需配置）", "全屏": "Alt+Enter", "配置菜单": "F1"}},
    "ssf": {"source": "http://redlotusflame.uupan.net/", "keys": {
        "方向": "方向键", "按键": "Z / X / C / V / A / S / D / F",
        "Start": "Enter", "全屏": "Alt+Enter"}},
    "ymir": {"source": "https://github.com/ymir-emu/Ymir", "keys": {
        "方向": "方向键 / 手柄", "A/B/C": "Z / X / C",
        "X/Y/Z": "A / S / D", "L/R": "Q / E",
        "Start": "Enter", "全屏": "Alt+Enter"}},
    "brimir": {"source": "https://github.com/coredds/brimir", "keys": {
        "说明": "libretro 核心，键位由 RetroArch 管理",
        "方向": "方向键 / 手柄", "A/B": "RetroArch 默认映射",
        "热键": "F1 打开 RetroArch 菜单"}},
    "flycast": {"source": "https://github.com/flyinghead/flycast", "keys": {
        "方向": "方向键", "A/B/X/Y": "A / S / D / X",
        "L/R": "Q / W", "Start": "Enter",
        "存档/读档": "F5 / F7", "全屏": "Alt+Enter"}},
    "redream": {"source": "https://redream.io/", "keys": {
        "方向": "方向键 / 手柄", "A/B/X/Y": "手柄默认",
        "Start": "Enter", "全屏": "Alt+Enter"}},
    "deecy": {"source": "https://github.com/Senryoku/Deecy", "keys": {
        "说明": "Zig 实验性项目，键位参考源码或 README"}},
    "dreampotato": {"source": "https://github.com/RikkiGibson/DreamPotato", "keys": {
        "说明": "VMU 记忆卡模拟器，无游戏键位"}},
    "mgba": {"source": "https://mgba.io/", "keys": {
        "方向": "方向键", "A": "Z", "B": "X", "L": "A", "R": "S",
        "Start": "Enter", "Select": "Backspace", "快进": "Tab",
        "存档/读档": "F5 / F7", "全屏": "Alt+Enter"}},
    "pcsx2": {"source": "https://pcsx2.net/docs/", "keys": {
        "方向": "WASD / 方向键", "△○×□": "I / L / K / J",
        "L1/R1/L2/R2": "Q / E / 1 / 3", "Start/Select": "Enter / Backspace",
        "存档/读档": "F1 / F3", "快进": "Tab", "全屏": "Alt+Enter", "暂停": "Space"}},
    "fceux": {"source": "https://fceux.com/web/home.html", "keys": {
        "方向": "方向键", "A/B": "Z / X", "连发 A/B": "A / S",
        "Start/Select": "Enter / Shift",
        "存档/读档": "F5 / F7（F1-F4 快存）",
        "快进": "Tab", "全屏": "Alt+Enter"}},
    "mesence": {"source": "https://github.com/nesdev-org/MesenCE", "keys": {
        "方向": "方向键", "A/B": "Z / X", "连发 A/B": "A / S",
        "Start/Select": "Enter / Shift",
        "存档/读档": "F5 / F7", "快进": "Tab", "全屏": "Alt+Enter"}},
    "mupen64plus": {"source": "https://mupen64plus.org/", "keys": {
        "方向": "方向键", "A/B": "X / C", "C 按键": "J / K / L / I",
        "L/R/Z": "Q / W / E", "Start": "Enter",
        "存档/读档": "F5 / F7", "全屏": "Alt+Enter"}},
    "gopher64": {"source": "https://github.com/gopher64/gopher64", "keys": {
        "说明": "键位参考 README 或源码默认值"}},
    "ares": {"source": "https://ares-emu.net/", "keys": {
        "说明": "多平台模拟器，键位在设置里逐平台配置",
        "菜单": "F1 或手柄 Start"}},
    "simple64": {"source": "https://simple64.github.io/", "keys": {
        "方向": "方向键", "A/B": "X / C", "C 按键": "J / K / L / I",
        "L/R/Z": "Q / W / E", "Start": "Enter", "存档/读档": "F5 / F7"}},
    "rmg": {"source": "https://github.com/Rosalie241/RMG", "keys": {
        "方向": "方向键", "A/B": "X / C", "C 按键": "J / K / L / I",
        "L/R/Z": "Q / W / E", "Start": "Enter", "存档/读档": "F5 / F7"}},
    "project64": {"source": "https://www.pj64-emu.com/", "keys": {
        "方向": "方向键", "A/B": "X / C", "C 按键": "J / K / L / I",
        "L/R/Z": "Q / W / E", "Start": "Enter", "存档/读档": "F5 / F7"}},
    "desmume": {"source": "https://desmume.org/", "keys": {
        "方向": "方向键", "A/B/X/Y": "X / Z / S / A", "L/R": "Q / W",
        "Start/Select": "Enter / Backspace", "触摸屏": "鼠标",
        "存档/读档": "Shift+F1 / F1", "全屏": "Alt+Enter"}},
    "melonds": {"source": "https://melonds.kuribo64.net/", "keys": {
        "方向": "方向键", "A/B/X/Y": "X / Z / S / A", "L/R": "Q / W",
        "Start/Select": "Enter / Backspace", "触摸屏": "鼠标",
        "存档/读档": "F5 / F7", "全屏": "Alt+Enter"}},
    "blastem": {"source": "https://www.retrodev.com/blastem/", "keys": {
        "方向": "方向键", "A/B/C": "A / S / D", "X/Y/Z": "Z / X / C",
        "Start/Mode": "Enter / Shift", "全屏": "Alt+Enter"}},
    "kega-fusion": {"source": "https://kega-fusion.com/", "keys": {
        "方向": "方向键", "A/B/C": "A / S / D", "X/Y/Z": "Z / X / C",
        "Start": "Enter", "存档/读档": "F5 / F8", "全屏": "Alt+Enter"}},
    "sameboy": {"source": "https://github.com/LIJI32/SameBoy", "keys": {
        "方向": "方向键", "A/B": "A / S",
        "Start/Select": "Enter / Backspace",
        "存档/读档": "F5 / F7", "快进": "Tab"}},
    "gambatte": {"source": "https://github.com/sinamas/gambatte", "keys": {
        "方向": "方向键", "A/B": "Z / X",
        "Start/Select": "Enter / Backspace", "存档/读档": "F5 / F7"}},
    "ppsspp": {"source": "https://www.ppsspp.org/docs/", "keys": {
        "方向": "WASD / 方向键", "○×△□": "L / K / I / J", "L/R": "Q / E",
        "Start/Select": "Enter / Backspace", "存档/读档": "F2 / F4",
        "快进": "Tab", "全屏": "Alt+Enter"}},
    "ryujinx": {"source": "https://ryujinx.app/", "keys": {
        "方向": "WASD / 方向键", "A/B/X/Y": "手柄默认",
        "L/R/ZL/ZR": "手柄默认", "全屏": "F11"}},
    "yuzu": {"source": "https://yuzu-mirror.github.io/", "keys": {
        "方向": "WASD", "A/B/X/Y": "手柄默认",
        "L/R/ZL/ZR": "手柄默认", "全屏": "F11"}},
    "mame": {"source": "https://docs.mamedev.org/usingmame/defaultkeys.html", "keys": {
        "投币": "5 / 6", "开始": "1 / 2", "移动": "方向键",
        "按钮 1-6": "Left Ctrl / Left Alt / Space / Left Shift / Z / X",
        "配置菜单": "Tab", "暂停": "P", "存档/读档": "Shift+F7 / F7",
        "全屏": "Alt+Enter", "退出": "Esc"}},
    "px68k": {"source": "https://github.com/libretro/px68k-libretro", "keys": {
        "说明": "libretro 核心，键位由 RetroArch 管理",
        "菜单": "F1（RetroArch）"}},
    "np2kai": {"source": "https://github.com/AZO234/NP2kai", "keys": {
        "说明": "libretro 核心，键位由 RetroArch 管理",
        "菜单": "F1（RetroArch）"}},
    "tsugaru": {"source": "https://github.com/captainys/TOWNSEMU", "keys": {
        "说明": "键位参考 README，可在设置里改"}},
    "pcfxemu": {"source": "https://github.com/gameblabla/pcfxemu", "keys": {
        "方向": "方向键", "I/II/III/IV/V/VI": "Z / X / C / V / A / S",
        "Start/Select": "Enter / Shift", "全屏": "Alt+Enter"}},
    "openmsx": {"source": "https://openmsx.org/manual/", "keys": {
        "方向": "方向键", "A/B": "Space / 左 Alt", "空格": "Space",
        "配置菜单": "F10", "全屏": "Alt+Enter"}},
    "bluemsx": {"source": "https://www.msxblue.com/", "keys": {
        "方向": "方向键", "A/B": "Z / X", "空格": "Space",
        "开始": "Enter", "全屏": "Alt+Enter"}},
    "retroarch": {"source": "https://docs.libretro.com/guides/retroarch-basics/", "keys": {
        "菜单导航": "方向键", "选择": "Enter / X", "返回": "Backspace / Z",
        "A/B": "X / Z（默认）", "X/Y": "S / A（默认）", "L/R": "Q / W（默认）",
        "Start/Select": "Enter / RShift", "热键": "F1 打开菜单",
        "快进": "Space", "存档/读档": "F2 / F4"}},
    "86box": {"source": "https://86box.readthedocs.io/", "keys": {
        "说明": "x86 PC 模拟器，键位在「设置 → 输入」里逐机型配置",
        "释放鼠标": "Ctrl+Alt 或鼠标中键（默认）",
        "退出": "Alt+F4 或菜单", "软复位": "Ctrl+Alt+Del（直通给虚拟机）"}},
    "pcem": {"source": "https://pcem-emulator.co.uk/", "keys": {
        "说明": "x86 PC 模拟器，键位在「Settings → Configure」里配置",
        "释放鼠标": "鼠标中键或 Ctrl+End", "暂停": "Pause",
        "软复位": "Ctrl+Alt+Del（直通给虚拟机）"}},
}


def get_controls(engine_name: str) -> Optional[dict]:
    return CONTROLS_DB.get(engine_name)


def get_generic_controls() -> dict:
    return {
        "source": "",
        "keys": {
            "方向": "方向键 或 WASD",
            "确认": "Enter / Z / X",
            "返回": "Esc / Backspace",
            "存档/读档": "F5 / F7（多数模拟器通用）",
            "全屏": "Alt+Enter",
            "提示": "不同模拟器键位不同，请查看对应官网文档。",
        }
    }


# ============================================================
# 6. engines.json 加载
# ============================================================
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
        try:
            defaults = json.loads(DEFAULT_ENGINES_JSON_STR)
            changed = False
            for pid in ("pcem", "x86box"):
                if pid not in data and pid in defaults:
                    data[pid] = defaults[pid]
                    changed = True
            if changed:
                with open(ENGINES_JSON, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info("engines.json 已自动补齐 pcem / x86box")
        except Exception:
            pass
        return data
    except Exception as e:
        logger.exception(f"读取 engines.json 失败: {e}")
        return {}


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
    except Exception:
        pass


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
    except Exception:
        pass


# ============================================================
# 8. 工具函数
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


_CUE_PLATFORMS = {"ps1", "ss", "dc", "pce", "pcfx", "fmtowns", "neogeo", "arcade"}


def resolve_rom_for_launch(path_str: str, platform: str = "") -> tuple:
    p = Path(path_str)
    if p.suffix.lower() not in (".bin", ".iso", ".img"):
        return path_str, False
    if platform and platform not in _CUE_PLATFORMS:
        return path_str, False

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


def parse_github_repo(url: str) -> Optional[str]:
    m = re.search(r"github\.com/([^/]+)/([^/]+?)(?:/|$|\.git)", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def version_newer(a: str, b: str) -> bool:
    def _parse(v):
        v = v.lstrip("vV")
        nums = re.findall(r"\d+", v)
        if not nums:
            return None
        return tuple(int(x) for x in nums[:4])
    pa, pb = _parse(a), _parse(b)
    if pa is None or pb is None:
        return False
    return pa > pb


# ============================================================
# 9. 模拟器匹配 / 安装
# ============================================================
def match_engines(files: list, engines_json: dict) -> list:
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
                file_count = sum(1 for _ in source_root.rglob("*") if _.is_file())
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
                          platform_display: str = "") -> EmulatorConfig:
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
    return EmulatorConfig(
        platform=platform, engine=engine_name,
        platform_name=platform_display or platform,
        engine_path=str(target_exe), engine_dir=str(target_dir),
        version="manual", official=False, source="manual",
        launch_template=launch_tpl,
        installed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        url_type="manual", archive="none",
    )


# ============================================================
# 10. Worker: 导入模拟器
# ============================================================
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


# ============================================================
# 11. 游戏扫描 / 导入
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
        pcfg = engines_json.get(platform, {})
        label = pcfg.get("platform_name", platform).lower()
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
        platform = guess_platform_by_ext(f, engines_json)
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
# 12. Worker: 多线程下载
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
# 13. Worker: 镜像测试 / 更新检查
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


class UpdateCheckWorker(QThread):
    one = Signal(str, str, str, str)
    done = Signal()

    def __init__(self, installed: list, engines_json: dict):
        super().__init__()
        self._installed = installed
        self._engines_json = engines_json

    def _api_get(self, url: str, timeout: int = 10):
        headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}",
                   "Accept": "application/vnd.github+json"}
        try:
            import certifi
            verify_opt = certifi.where()
        except ImportError:
            verify_opt = True
        for m in get_api_mirror_list():
            test_url = m + url if m else url
            try:
                r = requests.get(test_url, headers=headers, timeout=timeout,
                                 verify=verify_opt)
                if r.status_code < 400:
                    return r.json()
            except Exception:
                continue
        return None

    def run(self):
        for e in self._installed:
            try:
                repo = e.github_repo or parse_github_repo(e.url)
                if not repo or e.url_type == "manual":
                    continue
                api = f"https://api.github.com/repos/{repo}/releases/latest"
                data = self._api_get(api)
                if not data:
                    continue
                latest = (data.get("tag_name") or "").lstrip("vV")
                if not latest:
                    continue
                ignored = UPDATE_IGNORE.get(f"{e.platform}/{e.engine}", "")
                if ignored == latest:
                    continue
                if version_newer(latest, e.version):
                    dl_url = ""
                    for asset in data.get("assets", []):
                        name = asset.get("name", "").lower()
                        if ("win" in name or "windows" in name) and name.endswith(
                                (".zip", ".7z", ".exe")):
                            dl_url = asset.get("browser_download_url", "")
                            break
                    if not dl_url:
                        dl_url = data.get("html_url", "")
                    self.one.emit(e.platform, e.engine, latest, dl_url)
            except Exception as ex:
                logger.debug(f"检查 {e.engine} 更新失败: {ex}")
        self.done.emit()


# ============================================================
# 14. 启动 / 存档 / BIOS
# ============================================================
def find_retroarch() -> Optional[EmulatorConfig]:
    for e in load_installed():
        if e.engine == "retroarch":
            return e
    return None


def resolve_launch_args(engine: EmulatorConfig, game: GameEntry,
                        rom_path: str = "") -> list:
    actual_rom = rom_path or game.path
    tpl = engine.launch_template or "{exe} \"{rom}\""
    extra_kwargs = {"exe": engine.engine_path, "rom": actual_rom}

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

    cmd_str = tpl.format(**extra_kwargs)
    if game.extra_args:
        cmd_str = cmd_str + " " + game.extra_args

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


def copy_bios_for_game(engine: EmulatorConfig, game: GameEntry) -> Optional[str]:
    if not game.bios_file:
        return None
    src = Path(game.bios_file)
    if not src.exists():
        return None
    bios_dir_rel = engine.bios_dir or ""
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


def launch_game(engine: EmulatorConfig, game: GameEntry) -> tuple:
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

    proc = sp.Popen(args, cwd=exe_dir,
                    creationflags=sp.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0)
    logger.info(f"已启动: {' '.join(args)}" + (" (auto .cue)" if switched else ""))
    return proc, switched, bios_msg


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
}
KNOWN_BIOS.update({
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
})


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
# 16. 性能监控小窗
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
# 16.5 局域网核心（独立版 mikan_lan v1.2.x 协议）
# ============================================================
LAN_MAGIC = "mikan_lan"
LAN_DISCOVERY_PORT = 54321
LAN_BROADCAST_INTERVAL = 2.0
LAN_PEER_TIMEOUT = 6.0
LAN_MAX_TEXT = 8192
LAN_FILE_CHUNK = 64 * 1024
LAN_ACK_TIMEOUT = 3.0
LAN_TEXT_RETRY = 2
LAN_RECV_HEAD_TIMEOUT = 15.0
LAN_PORT_MAX_TRY = 20

LAN_BROADCAST_ID = "__broadcast__"


def _pwd_hash(pwd: str) -> str:
    if not pwd:
        return ""
    return hashlib.sha256(("mikan_lan::" + pwd).encode("utf-8")).hexdigest()[:16]


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
    # 消息信号：pid, pname, text, is_broadcast
    message_received = Signal(str, str, str, bool)
    file_offer = Signal(str, str, str, int)
    file_progress = Signal(str, int, int)
    file_received = Signal(str, str, bool)
    error = Signal(str)

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
                ch = conn.recv(1)
            except Exception:
                return b""
            if not ch:
                break
            if ch == b"\n":
                break
            buf += ch
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
            elif mtype == "share_query":
                self._handle_share_query(conn)
            elif mtype == "share_download":
                self._handle_share_download(conn, obj)
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
                ch = sock.recv(1)
            except Exception:
                return b""
            if not ch:
                break
            if ch == b"\n":
                break
            buf += ch
        return bytes(buf)

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
                  progress_cb=None) -> tuple:
        try:
            fsize = file_path.stat().st_size
        except Exception:
            return False, "err"
        try:
            max_mb = int(SETTINGS.get("lan_max_file_mb", 512))
        except Exception:
            max_mb = 512
        if fsize <= 0 or fsize > max(1, max_mb) * 1024 * 1024:
            return False, "size"

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
                return False, reason

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
                return False, "no_ack"
            try:
                resp2 = json.loads(line2.decode("utf-8", errors="ignore"))
            except Exception:
                return False, "no_ack"
            if resp2.get("ok"):
                return True, ""
            if resp2.get("reason") == "io":
                return False, "io"
            return False, "hash"
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


# 表情
LAN_EMOJIS = [
    "😀", "😂", "🤣", "😊", "😍", "😘", "😎", "🤔",
    "😅", "😭", "😡", "🥺", "😴", "🤯", "🥳", "😇",
    "👍", "👎", "👌", "🙏", "👏", "🤝", "💪", "✌️",
    "❤️", "💔", "🔥", "⭐", "🎉", "🎁", "✅", "❌",
    "🐱", "🐶", "🍕", "🍺", "☕", "🌸", "🌙", "☀️",
]

# ===== 第 2/5 段结束，回复"继续"输出第 3/5 段 =====

# ============================================================
# 17. QSS
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


# ============================================================
# 18. 管理员
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
# 19. 数据模型
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
                if row.override_platform or row.override_engine or row.extra_args or row.bios_file:
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
                return f"{row.engine} {row.version}".strip()
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
# 20. 对话框
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
            self.combo_override.addItem(pcfg.get("platform_name", p), p)
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
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for i, (k, v) in enumerate(keys.items()):
                table.setItem(i, 0, QTableWidgetItem(k))
                table.setItem(i, 1, QTableWidgetItem(v))
            layout.addWidget(table, 1)

        source = data.get("source", "")
        if source:
            src_lbl = QLabel(f"{tr('controls_source')}: <a href='{source}'>{source}</a>")
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
            "86Box · PCem<br>"
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
            "<b>Libretro 文档</b><br>"
            "<b>LocalSend Web</b> — 局域网传输后端"
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
            self.combo_platform.addItem(pcfg.get("platform_name", p), p)
        self.combo_platform.addItem("未知/自定义", "unknown")
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
            self.combo_set_all.addItem(pcfg.get("platform_name", p), p)
        top.addWidget(self.combo_set_all)
        btn_set = QPushButton("应用")
        btn_set.clicked.connect(self._apply_all)
        top.addWidget(btn_set)
        top.addStretch(1)
        layout.addLayout(top)

        self.table = QTableWidget(len(self._games), 3)
        self.table.setHorizontalHeaderLabels(
            [tr("library_col_name"), tr("library_col_platform"), tr("library_col_path")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        self._combos = []
        for i, g in enumerate(self._games):
            self.table.setItem(i, 0, QTableWidgetItem(g.name))
            combo = QComboBox()
            for p, pcfg in self._engines_json.items():
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
                    g.custom_platform = "未知"
            else:
                g.platform = p
        return self._games

# ===== 第 3/5 段结束，回复"继续"输出第 4/5 段 =====

# ============================================================
# 21. 页面：游戏库
# ============================================================
class LibraryPage(QWidget):
    launch_requested = Signal(object)
    open_folder_requested = Signal(object)
    remove_requested = Signal(object)
    favorite_toggled = Signal(object)
    set_cover_requested = Signal(object)
    open_save_requested = Signal(object)
    config_requested = Signal(object)
    cheat_requested = Signal(object)
    bios_requested = Signal(object)
    controls_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self._model = GameTableModel()
        self._proxy = GameFilterProxy()
        self._proxy.setSourceModel(self._model)
        self._games: list = []
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
            self.combo_platform.addItem(pcfg.get("platform_name", p), p)
        if current:
            idx = self.combo_platform.findData(current)
            if idx >= 0:
                self.combo_platform.setCurrentIndex(idx)
        self.combo_platform.blockSignals(False)

    def refresh_platforms(self):
        self._reload_platform_combo()

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

    def set_games(self, games):
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
            if g.override_platform or g.override_engine or g.extra_args or g.bios_file:
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

    def _selected_game(self):
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

    def _show_menu(self, g, global_pos):
        menu = QMenu(self)
        a_launch = menu.addAction(tr("ctx_launch"))
        a_config = menu.addAction(tr("ctx_config"))
        a_controls = menu.addAction(tr("ctx_controls"))
        menu.addSeparator()
        a_folder = menu.addAction(tr("ctx_open_folder"))
        a_save = menu.addAction(tr("ctx_open_save"))
        a_cheat = menu.addAction(tr("ctx_cheat"))
        a_bios = menu.addAction(tr("ctx_bios"))
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
        elif act == a_controls:
            self.controls_requested.emit(g)
        elif act == a_folder:
            self.open_folder_requested.emit(g)
        elif act == a_save:
            self.open_save_requested.emit(g)
        elif act == a_cheat:
            self.cheat_requested.emit(g)
        elif act == a_bios:
            self.bios_requested.emit(g)
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
# 22. 页面：模拟器 / BIOS / 统计 / 资源
# ============================================================
class EnginePage(QWidget):
    import_requested = Signal()
    download_requested = Signal()
    update_requested = Signal(str, str, str)
    ignore_requested = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self._model = EngineTableModel()
        self._update_worker = None
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
        self.btn_check_update.clicked.connect(self.check_updates)
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

    def check_updates(self):
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        installed = load_installed()
        if not installed:
            return
        engines_json = load_engines_json()
        self._update_worker = UpdateCheckWorker(installed, engines_json)
        self._update_worker.one.connect(self._on_update_found)
        self._update_worker.done.connect(lambda: self.refresh())
        self._update_worker.start()

    def _on_update_found(self, platform, engine, latest, url):
        self._model.set_update_info(platform, engine, latest, url)

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
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act == a_update and url:
            self.update_requested.emit(e.platform, e.engine, url)
        elif act == a_ignore and latest:
            self.ignore_requested.emit(e.platform, e.engine, latest)


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

        btn_pcem = QPushButton(tr("bios_import_pcem_rom"))
        btn_pcem.setObjectName("PrimaryBtn")
        btn_pcem.setToolTip(tr("bios_import_pcem_hint"))
        btn_pcem.clicked.connect(self._import_pcem_rom)
        bar.addWidget(btn_pcem)

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
        self.refresh()


class ChartWidget(QWidget):
    def __init__(self, mode: str = "line"):
        super().__init__()
        self._data: list = []
        self._mode = mode
        self.setMinimumHeight(160)

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 46, 12, 12, 30
        cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
        max_v = max((v for _, v in self._data), default=1) or 1

        painter.setPen(QPen(QColor("#e5e5e5"), 1))
        painter.drawLine(pad_l, pad_t, pad_l, pad_t + ch)
        painter.drawLine(pad_l, pad_t + ch, pad_l + cw, pad_t + ch)

        n = len(self._data)
        if n == 0:
            painter.end()
            return

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
            points = []
            for i, (_, v) in enumerate(self._data):
                x = pad_l + (cw * i / max(1, n - 1)) if n > 1 else pad_l + cw // 2
                y = pad_t + ch - (v / max_v) * ch if max_v > 0 else pad_t + ch
                points.append((int(x), int(y)))

            if len(points) >= 2:
                fill_pts = [(points[0][0], pad_t + ch)] + points + [(points[-1][0], pad_t + ch)]
                poly = QPolygon([QPoint(x, y) for x, y in points])
                fill_poly = QPolygon([QPoint(x, y) for x, y in fill_pts])

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
        painter.end()


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
        bv = QHBoxLayout(badge_grp)
        self.badge_labels = []
        for key in ("stats_badge_first", "stats_badge_10h", "stats_badge_50h",
                    "stats_badge_7days", "stats_badge_allplat"):
            lbl = QLabel(tr(key))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumHeight(80)
            lbl.setMinimumWidth(110)
            bv.addWidget(lbl)
            self.badge_labels.append((key, lbl))
        v.addWidget(badge_grp)

        v.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _make_card(self, layout, label_text):
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#fff;border:1px solid #e5e5e5;border-radius:6px;}")
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
        result["stats_badge_first"] = any(g.last_played for g in games)
        result["stats_badge_10h"] = total_sec >= 10 * 3600
        result["stats_badge_50h"] = any(g.play_seconds >= 50 * 3600 for g in games)

        streak = 0
        now = time.time()
        for i in range(7):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            if sum((daily.get(d) or {}).values()) > 0:
                streak += 1
            else:
                break
        result["stats_badge_7days"] = streak >= 7

        all_plats = set(load_engines_json().keys())
        played_plats = {g.platform for g in games if g.play_seconds > 0}
        result["stats_badge_allplat"] = bool(all_plats) and all_plats.issubset(played_plats)
        return result


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
            QMessageBox.warning(self, tr("msg_warning"), f"打开失败: {e}")

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
                QMessageBox.information(self, tr("msg_info"), tr("resources_saved"))
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"), str(e))


# ============================================================
# 22.5 页面：局域网（独立版完整功能）
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
    """独立版 mikan_lan v1.2.x 完整整合：聊天 + 共享 + 拖拽 + 表情 + 右键。"""
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
        self._remote_files: dict = {}
        self._build_ui()
        self._load_history_index()
        self._rebuild_peer_list()

    # ---------- UI 构建 ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 顶栏
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

        # 主体：左侧用户列表 + 右侧 Tab（聊天 / 共享）
        body = QHBoxLayout()
        body.setSpacing(12)

        # 左：在线用户
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

        # 右：Tab
        self.tabs = QTabWidget()

        # --- 聊天 Tab ---
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)
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

        self.btn_file = QPushButton(tr("lan_send_file"))
        self.btn_file.clicked.connect(self._on_send_file)
        input_row.addWidget(self.btn_file)

        self.btn_clear = QPushButton(tr("lan_clear_history"))
        self.btn_clear.clicked.connect(self._on_clear_history)
        input_row.addWidget(self.btn_clear)
        chat_layout.addLayout(input_row)

        self.tabs.addTab(chat_tab, tr("lan_tab_chat"))

        # --- 共享 Tab ---
        share_tab = QWidget()
        share_layout = QVBoxLayout(share_tab)
        share_layout.setContentsMargins(0, 0, 0, 0)
        share_layout.setSpacing(8)

        share_title = QLabel(tr("lan_share_title"))
        share_title.setObjectName("SectionTitle")
        share_layout.addWidget(share_title)

        share_hint = QLabel(tr("lan_share_hint"))
        share_hint.setObjectName("Hint")
        share_hint.setWordWrap(True)
        share_layout.addWidget(share_hint)

        split = QSplitter(Qt.Horizontal)

        # 左：我共享的
        left_box = QWidget()
        lv = QVBoxLayout(left_box)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr("lan_share_my")))
        self.table_local = QTableWidget(0, 3)
        self.table_local.setHorizontalHeaderLabels([
            tr("lan_share_col_file"), tr("lan_share_col_size"),
            tr("lan_share_col_op")])
        self.table_local.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_local.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_local.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_local.verticalHeader().setVisible(False)
        self.table_local.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_local.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_local.setAlternatingRowColors(True)
        lv.addWidget(self.table_local, 1)

        lrow = QHBoxLayout()
        b_add = QPushButton(tr("lan_share_add"))
        b_add.clicked.connect(self._share_add_files)
        lrow.addWidget(b_add)
        b_open = QPushButton(tr("lan_open_shared"))
        b_open.clicked.connect(lambda: os.startfile(str(LAN_SHARED_DIR)))
        lrow.addWidget(b_open)
        lrow.addStretch(1)
        lv.addLayout(lrow)
        split.addWidget(left_box)

        # 右：别人的共享
        right_box = QWidget()
        rv = QVBoxLayout(right_box)
        rv.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel(tr("lan_share_others")))
        head.addStretch(1)
        b_refresh = QPushButton(tr("lan_share_refresh"))
        b_refresh.clicked.connect(self._share_refresh_remote)
        head.addWidget(b_refresh)
        b_open_dl = QPushButton(tr("lan_open_shared_download"))
        b_open_dl.clicked.connect(lambda: os.startfile(str(LAN_SHARED_DOWNLOAD_DIR)))
        head.addWidget(b_open_dl)
        rv.addLayout(head)

        self.table_remote = QTableWidget(0, 4)
        self.table_remote.setHorizontalHeaderLabels([
            tr("lan_share_col_source"), tr("lan_share_col_file"),
            tr("lan_share_col_size"), tr("lan_share_col_op")])
        self.table_remote.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_remote.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_remote.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_remote.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_remote.verticalHeader().setVisible(False)
        self.table_remote.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_remote.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_remote.setAlternatingRowColors(True)
        rv.addWidget(self.table_remote, 1)
        split.addWidget(right_box)

        split.setSizes([400, 600])
        share_layout.addWidget(split, 1)

        self.share_progress = QProgressBar()
        self.share_progress.setVisible(False)
        share_layout.addWidget(self.share_progress)

        self.tabs.addTab(share_tab, tr("lan_tab_share"))

        body.addWidget(self.tabs, 1)
        root.addLayout(body, 1)

        # 拖拽
        self.setAcceptDrops(True)

        self._refresh_my_label()
        self._update_empty_hint()
        self._refresh_input_state()
        self._share_refresh_local()

    # ---------- 拖拽 ----------
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
        if self._current_is_broadcast:
            reply = QMessageBox.question(
                self, tr("lan_drop_title"),
                tr("lan_drop_ask_share", n=len(files)),
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._share_add_paths(files)
                self.tabs.setCurrentIndex(1)
            event.acceptProposedAction()
            return
        if not self._current_peer:
            QMessageBox.information(self, tr("msg_info"), tr("lan_drop_no_target"))
            return
        if len(files) == 1:
            self._send_file_path(files[0])
        else:
            reply = QMessageBox.question(
                self, tr("lan_drop_title"),
                tr("lan_drop_to_peer", n=len(files),
                   peer=self._current_peer.name),
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            for f in files:
                self._send_file_path(f)
        event.acceptProposedAction()

    # ---------- 生命周期 ----------
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
            self.lbl_status.setText(f"运行中 · TCP {free_port} / UDP {LAN_DISCOVERY_PORT}")
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

    # ---------- 昵称 ----------
    def _refresh_my_label(self):
        pass

    def _on_nickname_changed(self):
        name = self.edit_nick.text().strip()
        if not name or name == self._identity.name:
            return
        self._identity.set_name(name)

    # ---------- 用户列表 ----------
    def _on_peer_found(self, peer):
        is_new = peer.id not in self._seen_peer_ids
        self._seen_peer_ids.add(peer.id)
        self._peers[peer.id] = peer
        self._rebuild_peer_list()
        if is_new:
            self._append_system(peer.id, tr("lan_peer_joined", name=peer.name))
            if not self._current_peer and not self._current_is_broadcast:
                self._select_peer(peer.id)

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
        self._update_empty_hint()

    def _update_empty_hint(self):
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
        self.btn_file.setEnabled(has and not self._file_send_busy
                                 and not self._current_is_broadcast)
        self.btn_emoji.setEnabled(has)
        self.btn_clear.setEnabled(has)

    # ---------- 历史 ----------
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

    # ---------- 收消息 / 文件 ----------
    def _on_message_received(self, pid, pname, text, is_broadcast):
        # 从消息补入 peer
        if pid not in self._peers:
            self._peers[pid] = LanPeer(pid, pname, "", 0, time.time())
            self._seen_peer_ids.add(pid)
            self._rebuild_peer_list()
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

        # 弹窗提示
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

    # ---------- 发消息 ----------
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
                QMessageBox.warning(self, tr("msg_warning"), tr("lan_msg_failed"))
            return

        peer = self._current_peer
        if peer.port == 0:
            QMessageBox.warning(self, tr("msg_warning"),
                                "暂时不知道对方端口，请等 1~2 秒。")
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

    # ---------- 发文件 ----------
    def _on_send_file(self):
        if not self._current_peer:
            return
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("lan_send_file"), str(Path.home()), "所有文件 (*)")
        if not fp:
            return
        self._send_file_path(Path(fp))

    def _send_file_path(self, path: Path):
        if not self._current_peer:
            return
        peer = self._current_peer
        if peer.port == 0:
            QMessageBox.warning(self, tr("msg_warning"),
                                "暂时不知道对方端口，请等 1~2 秒。")
            return
        try:
            size = path.stat().st_size
        except Exception:
            return
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            f"发送 {path.name} ({human_size(size)}) 给 {peer.name}？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        pwd_hash = _pwd_hash(SETTINGS.get("lan_password", ""))
        want_hash = bool(SETTINGS.get("lan_verify_hash", True))
        offer = tr("lan_file_offer", name=path.name, size=human_size(size))
        self._append_history(peer.id, "me", offer, {"kind": "file"})
        if self._is_viewing(peer.id):
            self._append_line("me", offer, time.time(), kind="file", peer_id=peer.id)

        self._file_send_busy = True
        self._refresh_input_state()
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        def progress_cb(sent, total):
            if total > 0:
                pct = int(sent * 100 / total)
                QTimer.singleShot(0, lambda p=pct: self.progress.setValue(p))

        def worker():
            ok, reason = LanChatClient.send_file(
                peer, self._identity, path, pwd_hash, want_hash, progress_cb)
            QTimer.singleShot(0, lambda: self._on_send_file_done(
                peer, path, size, ok, reason))

        threading.Thread(target=worker, daemon=True).start()
        QTimer.singleShot(120000, self._restore_file_btn)

    def _on_send_file_done(self, peer, path, size, ok, reason):
        self._restore_file_btn()
        if ok:
            msg = tr("lan_file_sent", name=path.name, size=human_size(size))
        else:
            tag = {
                "size": "❌ 文件超过对方设置的大小上限",
                "disabled": "❌ 对方关闭了文件接收",
                "no_ack": "❌ " + tr("lan_no_ack"),
                "io": "❌ " + tr("lan_file_io_fail"),
                "rejected": "❌ " + tr("lan_file_rejected"),
                "bad_pwd": "❌ 口令不匹配",
                "hash": "❌ " + tr("lan_file_hash_bad"),
                "err": "❌ 网络错误",
            }.get(reason, "❌ 发送失败")
            msg = tag
        self._append_system(peer.id, msg)

    def _restore_file_btn(self):
        if not self._file_send_busy:
            return
        self._file_send_busy = False
        self._refresh_input_state()
        self.progress.setVisible(False)

    # ---------- 清空 ----------
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

    # ---------- 右键菜单 ----------
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
            a_ping = menu.addAction(tr("lan_ctx_ping"))
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
            if kind == "broadcast":
                self.list_peers.setCurrentItem(it)
                self._broadcast_file_dialog()
            else:
                peer = self._peers.get(key)
                if peer is None:
                    QMessageBox.warning(self, tr("msg_warning"),
                                        "该用户已离线。")
                    return
                if peer.port == 0:
                    QMessageBox.warning(self, tr("msg_warning"),
                                        "还没拿到该用户的端口，请等 1~2 秒后再试。")
                    return
                fp, _ = QFileDialog.getOpenFileName(
                    self, tr("lan_ctx_send_file") + f" - {peer.name}",
                    str(Path.home()), "所有文件 (*)")
                if not fp:
                    return
                self._select_peer(peer.id)
                self._send_file_path(Path(fp))
        elif act == a_clear:
            target_key = LAN_BROADCAST_ID if kind == "broadcast" else key
            self._history[target_key] = []
            try:
                fp = HISTORY_DIR / f"{target_key}.jsonl"
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass
            if kind == "broadcast" and self._current_is_broadcast:
                self.chat_view.clear()
            elif (kind == "peer" and self._current_peer
                  and self._current_peer.id == key):
                self.chat_view.clear()

    def _broadcast_file_dialog(self):
        peers = [p for p in self._peers.values() if p.port > 0]
        if not peers:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("lan_broadcast_no_peers"))
            return
        fp, _ = QFileDialog.getOpenFileName(
            self, tr("lan_ctx_send_file_all"),
            str(Path.home()), "所有文件 (*)")
        if not fp:
            return
        path = Path(fp)
        try:
            size = path.stat().st_size
        except Exception:
            return
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("lan_broadcast_confirm", name=path.name,
               size=human_size(size), n=len(peers)),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        pwd_hash = _pwd_hash(SETTINGS.get("lan_password", ""))
        want_hash = bool(SETTINGS.get("lan_verify_hash", True))
        self._append_history(
            LAN_BROADCAST_ID, "me",
            f"[文件] {path.name}  ({human_size(size)}) → {len(peers)} 人",
            {"kind": "file"})
        if self._current_is_broadcast:
            self._append_line(
                "me",
                f"[文件] {path.name}  ({human_size(size)}) → {len(peers)} 人",
                time.time(), kind="file", peer_id=LAN_BROADCAST_ID)

        total = len(peers)
        counter = {"done": 0, "ok": 0}
        lock = threading.Lock()

        self._file_send_busy = True
        self._refresh_input_state()
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        def one_send(peer):
            ok, reason = LanChatClient.send_file(
                peer, self._identity, path, pwd_hash, want_hash,
                None)
            with lock:
                counter["done"] += 1
                if ok:
                    counter["ok"] += 1
                cur = counter["done"]
            QTimer.singleShot(0, lambda c=cur, o=ok, r=reason, p=peer:
                              self._on_broadcast_one(path, p, c, total, o, r))

        for p in peers:
            threading.Thread(target=one_send, args=(p,), daemon=True).start()

        def watcher():
            while True:
                with lock:
                    if counter["done"] >= total:
                        break
                time.sleep(0.2)
            with lock:
                ok_n = counter["ok"]
            QTimer.singleShot(0, lambda: self._on_broadcast_done(
                path, ok_n, total))

        threading.Thread(target=watcher, daemon=True).start()

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

    def _on_broadcast_done(self, path, ok_n, total):
        self._file_send_busy = False
        self._refresh_input_state()
        self.progress.setVisible(False)
        self._append_system(
            LAN_BROADCAST_ID,
            tr("lan_broadcast_done", name=path.name, ok=ok_n, total=total))

    # ---------- 共享 ----------
    def _share_refresh_local(self):
        files = _scan_shared_dir()
        self.table_local.setRowCount(len(files))
        for i, f in enumerate(files):
            self.table_local.setItem(i, 0, QTableWidgetItem(f["name"]))
            self.table_local.setItem(i, 1, QTableWidgetItem(human_size(f["size"])))
            btn = QPushButton(tr("lan_share_remove"))
            btn.setFixedWidth(70)
            btn.clicked.connect(
                lambda _=False, n=f["name"]: self._share_remove(n))
            self.table_local.setCellWidget(i, 2, btn)

    def _share_add_files(self):
        fps, _ = QFileDialog.getOpenFileNames(
            self, tr("lan_share_add"), str(Path.home()), "所有文件 (*)")
        if not fps:
            return
        self._share_add_paths([Path(fp) for fp in fps])

    def _share_add_paths(self, paths):
        count = 0
        for src in paths:
            try:
                dst = LAN_SHARED_DIR / src.name
                if dst.exists():
                    base = dst.stem
                    suf = dst.suffix
                    idx = 2
                    while dst.exists():
                        dst = LAN_SHARED_DIR / f"{base}_{idx}{suf}"
                        idx += 1
                shutil.copy2(src, dst)
                count += 1
            except Exception as e:
                logger.exception(f"添加共享失败 {src}: {e}")
        if count:
            self._share_refresh_local()

    def _share_remove(self, name: str):
        reply = QMessageBox.question(
            self, tr("msg_confirm"),
            tr("lan_share_remove_confirm", name=name),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            (LAN_SHARED_DIR / name).unlink()
        except Exception as e:
            logger.exception(f"删除共享失败: {e}")
        self._share_refresh_local()

    def _share_refresh_remote(self):
        peers = list(self._peers.values())
        self.table_remote.setRowCount(0)
        if not peers:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("lan_share_no_peers"))
            return
        valid = [p for p in peers if p.port > 0]
        if not valid:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("lan_share_no_port"))
            return
        pwd_hash = _pwd_hash(SETTINGS.get("lan_password", ""))

        def worker():
            result = {}
            fail_count = 0
            for p in valid:
                files = LanChatClient.query_share(p, self._identity, pwd_hash)
                if files is None:
                    fail_count += 1
                elif files:
                    result[p.id] = (p, files)
            QTimer.singleShot(0, lambda: self._share_apply_remote(result, fail_count))

        threading.Thread(target=worker, daemon=True).start()

    def _share_apply_remote(self, result, fail_count=0):
        rows = []
        for pid, (peer, files) in result.items():
            for f in files:
                rows.append((peer, f))
        self.table_remote.setRowCount(len(rows))
        for i, (peer, f) in enumerate(rows):
            self.table_remote.setItem(i, 0, QTableWidgetItem(peer.name))
            self.table_remote.setItem(i, 1, QTableWidgetItem(f.get("name", "?")))
            self.table_remote.setItem(i, 2, QTableWidgetItem(human_size(f.get("size", 0))))
            btn = QPushButton(tr("lan_share_download"))
            btn.setObjectName("PrimaryBtn")
            btn.setFixedWidth(80)
            btn.clicked.connect(
                lambda _=False, pp=peer, ff=f: self._share_download(pp, ff))
            self.table_remote.setCellWidget(i, 3, btn)
        if not rows and fail_count > 0:
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("lan_share_all_fail", n=fail_count))

    def _share_download(self, peer, f):
        fname = f.get("name", "")
        if not fname:
            return
        pwd_hash = _pwd_hash(SETTINGS.get("lan_password", ""))
        self.share_progress.setVisible(True)
        self.share_progress.setRange(0, 100)
        self.share_progress.setValue(0)

        def progress_cb(done, total):
            if total > 0:
                pct = int(done * 100 / total)
                QTimer.singleShot(0, lambda p=pct: self.share_progress.setValue(p))

        def worker():
            ok, reason, path = LanChatClient.download_share(
                peer, self._identity, fname, pwd_hash,
                LAN_SHARED_DOWNLOAD_DIR, progress_cb)
            QTimer.singleShot(0, lambda: self._share_download_done(
                peer, fname, ok, reason, path))

        threading.Thread(target=worker, daemon=True).start()

    def _share_download_done(self, peer, fname, ok, reason, path):
        self.share_progress.setVisible(False)
        if ok:
            QMessageBox.information(
                self, tr("msg_info"),
                tr("lan_share_download_done",
                   peer=peer.name, name=fname, path=path))
        else:
            msg_map = {
                "notfound": "对方删除了该文件",
                "incomplete": "传输中断",
                "hash": "哈希校验失败",
                "disabled": "对方关闭了共享",
                "err": "网络错误",
            }
            QMessageBox.warning(self, tr("msg_warning"),
                                tr("lan_share_download_fail", name=fname,
                                   reason=msg_map.get(reason, reason)))


# ============================================================
# 22.7 页面：局域网传输（内嵌 LocalSend Web）
# ============================================================
class WebTransferPage(QWidget):
    """内嵌 LocalSend Web。若 QtWebEngine 不可用，降级为外部浏览器。"""

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

            # 下载处理：保存到系统默认下载目录
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
            QMessageBox.warning(self, tr("msg_warning"), f"打开失败: {e}")

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

    # ---------- 下载处理 ----------
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

# ===== 第 4/5 段结束，回复"继续"输出第 5/5 段 =====

# ============================================================
# 23. 页面：设置
# ============================================================
class SettingsPage(QWidget):
    lang_changed = Signal(str)
    saves_changed = Signal()
    retroarch_changed = Signal()
    platforms_changed = Signal()
    lan_changed = Signal()

    def __init__(self):
        super().__init__()
        self._mirror_test_worker = None
        self._api_test_worker = None
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

        # --- 语言 ---
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

        # --- 局域网 ---
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

        # --- 可选依赖 ---
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

        # --- 平台管理 ---
        box_plat = QGroupBox(tr("settings_platform_mgr"))
        fp = QVBoxLayout(box_plat)
        hint_p = QLabel(tr("settings_platform_mgr_hint"))
        hint_p.setObjectName("Hint")
        hint_p.setWordWrap(True)
        fp.addWidget(hint_p)

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
        fp.addWidget(self.table_plat)

        row_p = QHBoxLayout()
        b_add_p = QPushButton(tr("settings_platform_add"))
        b_add_p.clicked.connect(self._add_platform)
        row_p.addWidget(b_add_p)
        b_save_p = QPushButton(tr("settings_platform_save"))
        b_save_p.setObjectName("PrimaryBtn")
        b_save_p.clicked.connect(self._save_platforms)
        row_p.addWidget(b_save_p)
        row_p.addStretch(1)
        fp.addLayout(row_p)

        v.addWidget(box_plat)

        # --- 下载 + 镜像 ---
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

        self.check_mirror_enabled = QCheckBox(tr("settings_mirrors_enable"))
        self.check_mirror_enabled.setChecked(MIRRORS_CONFIG.get("enabled", True))
        self.check_mirror_enabled.toggled.connect(self._on_mirror_enabled)
        fdl.addWidget(self.check_mirror_enabled)

        hint_mirror = QLabel(tr("settings_mirrors_hint"))
        hint_mirror.setObjectName("Hint")
        hint_mirror.setWordWrap(True)
        fdl.addWidget(hint_mirror)

        fdl.addWidget(QLabel(tr("settings_mirrors")))
        self.list_mirrors = QListWidget()
        self.list_mirrors.setMinimumHeight(120)
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

        # --- RetroArch ---
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

        # --- 金手指 ---
        box_ch = QGroupBox(tr("settings_cheats"))
        fch = QVBoxLayout(box_ch)
        h_ch = QLabel(tr("settings_cheats_hint"))
        h_ch.setObjectName("Hint")
        h_ch.setWordWrap(True)
        fch.addWidget(h_ch)
        self._cheat_rows = {}
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
            browse.clicked.connect(lambda _=False, e=edit_dir: self._browse_save_dir(e))
            row.addWidget(browse)
            fch.addLayout(row)
            self._cheat_rows[eng] = (edit_dir, edit_ext)
        b_save_ch = QPushButton(tr("settings_saves_save"))
        b_save_ch.setObjectName("PrimaryBtn")
        b_save_ch.clicked.connect(self._save_cheat_paths)
        fch.addWidget(b_save_ch)
        v.addWidget(box_ch)

        # --- 托盘 + 性能小窗 ---
        box_tray = QGroupBox(tr("settings_tray"))
        ft = QVBoxLayout(box_tray)
        self.check_tray_min = QCheckBox(tr("settings_tray_minimize"))
        self.check_tray_min.setChecked(SETTINGS.get("tray_minimize_on_close", False))
        self.check_tray_min.toggled.connect(
            lambda val: self._set_setting("tray_minimize_on_close", val))
        ft.addWidget(self.check_tray_min)
        self.check_tray_launch = QCheckBox(tr("settings_tray_minimize_launch"))
        self.check_tray_launch.setChecked(SETTINGS.get("tray_minimize_after_launch", False))
        self.check_tray_launch.toggled.connect(
            lambda val: self._set_setting("tray_minimize_after_launch", val))
        ft.addWidget(self.check_tray_launch)

        self.check_perf = QCheckBox(tr("settings_perf_monitor"))
        self.check_perf.setChecked(SETTINGS.get("perf_monitor_on_launch", True))
        self.check_perf.toggled.connect(
            lambda val: self._set_setting("perf_monitor_on_launch", val))
        ft.addWidget(self.check_perf)
        v.addWidget(box_tray)

        # --- 工作区 ---
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

        # --- 存档 ---
        box_sv = QGroupBox(tr("settings_saves"))
        fsv = QVBoxLayout(box_sv)
        hint_sv = QLabel(tr("settings_saves_hint"))
        hint_sv.setObjectName("Hint")
        hint_sv.setWordWrap(True)
        fsv.addWidget(hint_sv)

        self._save_rows = {}
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

        # --- 管理员 + 鸣谢 ---
        box3 = QGroupBox(tr("settings_admin"))
        f3 = QHBoxLayout(box3)
        self.lbl_admin = QLabel()
        f3.addWidget(self.lbl_admin)
        f3.addStretch(1)
        btn_admin = QPushButton(tr("settings_relaunch"))
        btn_admin.clicked.connect(self._relaunch_admin)
        f3.addWidget(btn_admin)
        btn_credits = QPushButton(tr("settings_credits_btn"))
        btn_credits.clicked.connect(self._show_credits)
        f3.addWidget(btn_credits)
        v.addWidget(box3)

        # --- 目录 ---
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

    # ---- 可选依赖 ----
    def _refresh_optional_label(self):
        lines = []
        for mod, pkg in OPTIONAL.items():
            try:
                importlib.import_module(mod)
                lines.append(f"✅ {pkg}  已安装")
            except ImportError:
                lines.append(f"❌ {pkg}  未安装（局域网传输页将降级为外部浏览器）")
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
            "\n\n总计约 200MB。是否继续？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for pkg in missing:
            install_optional_package(pkg, self)
        QMessageBox.information(
            self, tr("msg_info"),
            "已在新窗口开始安装。\n"
            "安装完成后请关闭并重新启动 mikan_emu。")

    # ---- 局域网回调 ----
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
        pwd = self.edit_lan_pwd.text()
        self._set_setting("lan_password", pwd)

    def _show_credits(self):
        dlg = CreditsDialog(self)
        dlg.exec()

    # ---- 平台编辑器 ----
    def _reload_platform_table(self):
        self.table_plat.setRowCount(0)
        engines_json = load_engines_json()
        for p, pcfg in engines_json.items():
            row = self.table_plat.rowCount()
            self.table_plat.insertRow(row)
            self.table_plat.setItem(row, 0, QTableWidgetItem(p))
            self.table_plat.setItem(row, 1, QTableWidgetItem(pcfg.get("platform_name", p)))
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
        btn_del.clicked.connect(lambda _=False, r=row: self.table_plat.removeRow(r))
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
        QMessageBox.information(self, tr("msg_info"), tr("settings_platform_saved"))
        self._reload_platform_table()
        self.platforms_changed.emit()

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

    def _refresh_api_mirror_list(self):
        self.list_api_mirrors.clear()
        for m in MIRRORS_CONFIG.get("api_mirrors", []):
            self.list_api_mirrors.addItem(m if m else "（直连）")

    def _on_mirror_item_changed(self, item):
        idx = self.list_mirrors.row(item)
        new_text = item.text().strip()
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
        MIRRORS_CONFIG["mirrors"] = list(DEFAULT_MIRRORS_JSON["mirrors"])
        MIRRORS_CONFIG["api_mirrors"] = list(DEFAULT_MIRRORS_JSON["api_mirrors"])
        MIRRORS_CONFIG["enabled"] = True
        save_mirrors()
        self._refresh_mirror_list()
        self._refresh_api_mirror_list()
        self.check_mirror_enabled.setChecked(True)

    def _mirror_test(self):
        if self._mirror_test_worker is not None and self._mirror_test_worker.isRunning():
            return
        test_url = "https://github.com/robots.txt"
        self.lbl_mirror_result.setText(tr("settings_mirrors_testing"))
        self.list_mirrors.clear()
        self._mirror_test_worker = MirrorTestWorker(test_url, use_api=False)
        self._mirror_test_worker.one.connect(self._on_mirror_test_one)
        self._mirror_test_worker.done.connect(self._on_mirror_test_done)
        self._mirror_test_worker.start()

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

    def _api_mirror_add(self):
        text, ok = QInputDialog.getText(self, tr("settings_mirrors_add"),
                                        "输入 API 镜像前缀（末尾带 /）:",
                                        text="https://")
        if ok and text.strip():
            MIRRORS_CONFIG.setdefault("api_mirrors", []).append(text.strip())
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

    def _browse_ra_core(self):
        d = QFileDialog.getExistingDirectory(self, tr("settings_retroarch"), str(DATA_DIR))
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
            QMessageBox.warning(self, tr("msg_warning"), "未找到 RetroArch 核心目录")

    def _refresh(self):
        idx = self.combo_lang.findData(CURRENT_LANG)
        if idx >= 0:
            self.combo_lang.blockSignals(True)
            self.combo_lang.setCurrentIndex(idx)
            self.combo_lang.blockSignals(False)
        self.lbl_admin.setText("已获得管理员权限" if is_admin() else "普通用户")
        self.edit_lan_nick.setText(SETTINGS.get("lan_nickname", "") or
                                    LanIdentity().name)
        self.edit_lan_pwd.setText(SETTINGS.get("lan_password", ""))

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
                                    tr("save_backup_done", path=f"{len(results)} 个模拟器"))
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
# 24. 导入对话框
# ============================================================
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

    def _on_engine_done(self, installed, unmatched, all_exes):
        if installed:
            self.log_view.append(tr("import_found", n=len(installed)))
            engines = load_installed()
            for cfg in installed:
                engines = [e for e in engines
                           if not (e.platform == cfg.platform and e.engine == cfg.engine)]
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
                                   if not (e.platform == cfg.platform and e.engine == cfg.engine)]
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
        if games:
            self.log_view.append(tr("rom_import_done", n=len(games)))
            dlg = PlatformConfirmDialog(games, self._engines_json, self)
            if dlg.exec() == QDialog.Accepted:
                games = dlg.result_games()
            existing = load_games()
            paths = {g.path for g in existing}
            for g in games:
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


# ============================================================
# 25. 下载对话框
# ============================================================
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
                       if not (e.platform == installed.platform and e.engine == installed.engine)]
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
# 26. 导出功能
# ============================================================
def export_library(games, fmt, scope, include_playtime, include_cover) -> Path:
    if scope == "fav":
        games = [g for g in games if g.favorite]
    if not games:
        raise RuntimeError("没有可导出的游戏")

    ts = time.strftime("%Y%m%d_%H%M%S")
    ext = ".md" if fmt == "md" else (".html" if fmt == "html" else ".csv")
    out = EXPORT_DIR / f"library_{ts}{ext}"

    if fmt == "md":
        lines = [f"# mikan_emu 游戏库\n", f"共 {len(games)} 个游戏\n"]
        by_plat = {}
        for g in games:
            by_plat.setdefault(g.platform, []).append(g)
        for p, items in sorted(by_plat.items()):
            lines.append(f"\n## {p}\n")
            lines.append("| 名称 | 大小 |" + (" 时长 |" if include_playtime else ""))
            lines.append("|------|------|" + ("------|" if include_playtime else ""))
            for g in items:
                row = f"| {g.name} | {format_size(g.size)} |"
                if include_playtime:
                    row += f" {human_duration(g.play_seconds)} |"
                lines.append(row)
        out.write_text("\n".join(lines), encoding="utf-8")

    elif fmt == "html":
        import base64
        html = ['<!DOCTYPE html><html><head><meta charset="utf-8">',
                '<title>mikan_emu 游戏库</title>',
                '<style>body{font-family:sans-serif;background:#f3f3f3;padding:20px;}',
                '.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;}',
                '.card{background:#fff;border:1px solid #e5e5e5;border-radius:8px;padding:12px;}',
                '.card img{width:100%;height:240px;object-fit:cover;border-radius:4px;}',
                '.card h3{font-size:14px;margin:8px 0 4px;}',
                '.card p{font-size:12px;color:#767676;margin:2px 0;}',
                '</style></head><body>',
                f'<h1>mikan_emu 游戏库</h1><p>共 {len(games)} 个游戏</p>',
                '<div class="grid">']
        for g in games:
            cover_html = ""
            if include_cover:
                cover = find_cover(g.name)
                if cover:
                    try:
                        data = base64.b64encode(cover.read_bytes()).decode()
                        mime = "image/png" if cover.suffix.lower() == ".png" else "image/jpeg"
                        cover_html = f'<img src="data:{mime};base64,{data}">'
                    except Exception:
                        pass
            pt = f"<p>时长: {human_duration(g.play_seconds)}</p>" if include_playtime else ""
            html.append(
                f'<div class="card">{cover_html}<h3>{g.name}</h3>'
                f'<p>{g.platform}</p><p>{format_size(g.size)}</p>{pt}</div>')
        html.append('</div></body></html>')
        out.write_text("\n".join(html), encoding="utf-8")

    else:
        import csv
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            header = ["名称", "平台", "大小", "路径"]
            if include_playtime:
                header.append("时长(秒)")
            w.writerow(header)
            for g in games:
                row = [g.name, g.platform, format_size(g.size), g.path]
                if include_playtime:
                    row.append(g.play_seconds)
                w.writerow(row)

    return out


# ============================================================
# 27. 主窗口 + 托盘
# ============================================================
class MainWindow(QMainWindow):
    NAV_LIBRARY = 0
    NAV_ENGINES = 1
    NAV_BIOS = 2
    NAV_STATS = 3
    NAV_RESOURCES = 4
    NAV_LAN = 5
    NAV_WEBTRANSFER = 6
    NAV_SETTINGS = 7

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
                     tr("nav_webtransfer"),
                     tr("nav_settings")]:
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
        self.page_library.cheat_requested.connect(self._manage_cheat)
        self.page_library.bios_requested.connect(self._select_bios)
        self.page_library.controls_requested.connect(self._show_controls)
        self.stack.addWidget(self.page_library)

        self.page_engines = EnginePage()
        self.page_engines.import_requested.connect(self._import_engine)
        self.page_engines.download_requested.connect(self._download_engine)
        self.page_engines.update_requested.connect(self._update_engine)
        self.page_engines.ignore_requested.connect(self._ignore_update)
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

        self.page_settings = SettingsPage()
        self.page_settings.lang_changed.connect(self._on_lang_changed)
        self.page_settings.platforms_changed.connect(self._on_platforms_changed)
        self.page_settings.lan_changed.connect(self._on_lan_changed)
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

        self._setup_tray()
        self._reload_games()

        if SETTINGS.get("check_update_on_start", True):
            QTimer.singleShot(3000, self._auto_check_updates)

        if SETTINGS.get("lan_enabled", False):
            QTimer.singleShot(800, self.page_lan.start_service)

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

            games = sorted(load_games(), key=lambda g: g.last_played or "", reverse=True)
            recent = [g for g in games if g.last_played][:5]
            if recent:
                sub = menu.addMenu(tr("tray_recent"))
                for g in recent:
                    a = sub.addAction(g.name)
                    a.triggered.connect(lambda _=False, gg=g: self._launch_game(gg))
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
        if not self._force_quit and SETTINGS.get("tray_minimize_on_close", False) and self._tray:
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
            if HAS_WEBENGINE:
                try:
                    prof = QWebEngineProfile.defaultProfile()
                    if prof:
                        prof.clearHttpCache()
                except Exception:
                    pass
        except Exception:
            pass
        for w in list(self._perf_windows):
            try:
                w.close()
            except Exception:
                pass
        event.accept()

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

    def _select_bios(self, game):
        dlg = BiosSelectDialog(game, self)
        if dlg.exec() != QDialog.Accepted:
            return
        path = dlg.result_data()
        games = load_games()
        for g in games:
            if g.path == game.path:
                g.bios_file = path
                break
        save_games(games)
        self._reload_games()
        if path:
            self.status.showMessage(tr("bios_select_ok", name=Path(path).name))
        else:
            self.status.showMessage("已清除 BIOS 设置")

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

    def _manage_cheat(self, game):
        engine = self._resolve_engine(game, silent=True)
        if not engine:
            QMessageBox.information(self, tr("msg_info"), tr("config_no_engine"))
            return
        cheat_dir = get_cheat_dir(engine.engine)
        if cheat_dir:
            os.startfile(str(cheat_dir))
        else:
            QMessageBox.information(self, tr("msg_info"),
                                    tr("cheat_no_dir", engine=engine.engine))
            os.startfile(str(CHEAT_DIR))

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
                candidates = [e for e in installed if e.platform == game.platform]
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

            if proc and SETTINGS.get("perf_monitor_on_launch", True):
                try:
                    pw = PerfMonitorWindow(proc.pid, game.name, self)
                    self._perf_windows.append(pw)
                    pw.destroyed.connect(
                        lambda _=None, w=pw: self._perf_windows.remove(w)
                        if w in self._perf_windows else None)
                    pw.show()
                except Exception as e:
                    logger.warning(f"性能小窗启动失败: {e}")

            if SETTINGS.get("tray_minimize_after_launch", False) and self._tray:
                self.hide()

            if HAS_PSUTIL and proc:
                monitor = ProcessMonitorWorker(proc.pid)
                monitor.finished.connect(
                    lambda secs, gp=game.path, pf=game.platform:
                        self._on_game_closed(gp, secs, pf))
                monitor.start()
                self._monitor_workers.append(monitor)
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("launch_failed", err=str(e)))

    def _on_game_closed(self, game_path: str, _seconds_unused: int, platform: str):
        try:
            games = load_games()
            now = time.time()
            for g in games:
                if g.path == game_path:
                    if g.launch_start_ts and g.launch_start_ts > 0:
                        secs = int(max(0, now - g.launch_start_ts))
                        g.play_seconds += secs
                        record_playtime(platform, secs)
                        g.launch_start_ts = 0.0
                    break
            save_games(games)
            self._reload_games()
            logger.info(f"游戏关闭: {game_path}")
        except Exception as e:
            logger.exception(f"结算时长失败: {e}")

    def _settle_stale_launches(self):
        try:
            games = load_games()
            now = time.time()
            changed = False
            for g in games:
                if g.launch_start_ts and g.launch_start_ts > 0:
                    secs = int(max(0, now - g.launch_start_ts))
                    if 0 < secs < 7 * 24 * 3600:
                        g.play_seconds += secs
                        record_playtime(g.platform, secs)
                        logger.info(f"结算残留时长: {g.name} +{secs}s")
                    g.launch_start_ts = 0.0
                    changed = True
            if changed:
                save_games(games)
        except Exception as e:
            logger.exception(f"结算残留时长失败: {e}")

    def _open_game_folder(self, game):
        folder = str(Path(game.path).parent)
        if os.path.isdir(folder):
            os.startfile(folder)

    def _open_save_dir(self, game):
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

    def _set_cover(self, game):
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
        name = LANG_PACKS.get(lang, {}).get("_meta", {}).get("name", lang)
        QMessageBox.information(self, tr("msg_info"),
                                tr("lang_changed_msg", lang=name))

    def _load_lang(self):
        load_lang()

    def _auto_check_updates(self):
        try:
            self.page_engines.check_updates()
        except Exception as e:
            logger.debug(f"自动检查更新失败: {e}")

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
            QMessageBox.warning(self, tr("msg_warning"), "找不到引擎配置")
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
                QMessageBox.information(self, tr("msg_info"), tr("download_done"))
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
# 28. 入口
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(WIN11_QSS)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
# ===== 全部完成 =====