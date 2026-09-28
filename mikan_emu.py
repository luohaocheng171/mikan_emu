# -*- coding: utf-8 -*-
"""
mikan_emu v0.9.2
模拟器前端 + 配置管家 + 版本识别器 + 更新检查 + 多语言 + 平台编辑器
Python 3.11+ / PySide6 / requests / loguru / py7zr / rarfile / psutil

【法律】不提供 BIOS、不提供 ROM、不二次分发模拟器

v0.9.2 变更：
- ★ 侧边栏新增"资源"页（18 个老游戏/ROM 站点跳转，用户可增删改）
- ★ 操作说明：内置 40 个引擎的默认键位表
- ★ 鸣谢页：列出所有依赖和开源项目
- ★ 保留 v0.9.1 全部功能
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

MIRRORS_PIP = [
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
import webbrowser
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
        QSortFilterProxyModel, QTimer, QSize, QObject
    )
    from PySide6.QtGui import (
        QColor, QFont, QAction, QPixmap, QIcon, QPainter, QPen,
        QBrush, QLinearGradient
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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# 3. 路径 & 常量
# ============================================================
APP_NAME = "mikan_emu"
APP_VERSION = "0.9.2"

if getattr(sys, 'frozen', False):
    # 打包后（PyInstaller/Nuitka）：数据放在 exe 所在目录
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    # 开发环境：放在脚本旁边
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

for d in (DATA_DIR, CONFIG_DIR, LANG_DIR, ENGINE_DIR, ENGINE_DOWNLOAD_DIR,
          BIOS_DIR, ROM_DIR, SAVE_DIR, SAVE_BACKUP_DIR, COVER_DIR,
          CHEAT_DIR, BACKUP_DIR, LOG_DIR, TEMP_DIR, EXPORT_DIR):
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

logger.remove()
logger.add(
    LOG_DIR / "mikan_emu_{time:YYYY-MM-DD}.log",
    rotation="10 MB", retention="14 days",
    encoding="utf-8", level="DEBUG",
)
if sys.stderr is not None:
    logger.add(sys.stderr, level="INFO")

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
        "nav_stats": "统计", "nav_resources": "资源", "nav_settings": "设置",
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
        "stats_title": "游戏统计", "stats_total_time": "总时长",
        "stats_total_games": "游戏总数", "stats_total_launches": "启动次数",
        "stats_by_platform": "按平台", "stats_last_7d": "最近 7 天",
        "stats_last_30d": "最近 30 天", "stats_badges": "徽章",
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
        "msg_ok": "确定", "msg_cancel": "取消", "msg_warning": "警告",
        "msg_error": "错误", "msg_info": "提示", "msg_confirm": "确认",
    },
    "en": {
        "_meta": {"name": "English", "code": "en", "translator": "Official"},
        "app_title": "mikan_emu",
        "nav_library": "Library", "nav_engines": "Emulators", "nav_bios": "BIOS",
        "nav_stats": "Stats", "nav_resources": "Resources", "nav_settings": "Settings",
        "toolbar_import_engine": "Import Engine",
        "toolbar_download_engine": "Download Engine",
        "toolbar_import_game": "Import Game", "toolbar_export": "Export",
        "toolbar_refresh": "Refresh", "toolbar_open_roms": "Open ROMs",
        "library_title": "Library", "library_search_ph": "Search game...",
        "library_platform_all": "All Platforms", "library_count": "{n} game(s)",
        "library_empty": "No games yet. Click 'Import Game' or drop ROMs into roms/ folder.",
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
        "stats_title": "Statistics", "stats_total_time": "Total Time",
        "stats_total_games": "Games", "stats_total_launches": "Launches",
        "stats_by_platform": "By Platform", "stats_last_7d": "Last 7 Days",
        "stats_last_30d": "Last 30 Days", "stats_badges": "Badges",
        "stats_badge_first": "First Launch", "stats_badge_10h": "10h Total",
        "stats_badge_50h": "50h Single Game", "stats_badge_7days": "7-Day Streak",
        "stats_badge_allplat": "All Platforms",
        "stats_badge_locked": "Locked", "stats_badge_unlocked": "Unlocked",
        "resources_title": "Resources",
        "resources_hint": "External site links. This project does NOT provide ROM downloads. Use at your own discretion.",
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
        "settings_retroarch_hint": "libretro cores (px68k / NP2kai / Brimir) need RetroArch.",
        "settings_retroarch_browse": "Browse",
        "settings_retroarch_detect": "Auto Detect",
        "settings_cheats": "Cheat Paths",
        "settings_cheats_hint": "Set cheat directory and extension per emulator.",
        "settings_tray": "System Tray",
        "settings_tray_minimize": "Minimize to tray on close",
        "settings_tray_minimize_launch": "Minimize after launching game",
        "settings_hotkey": "Global Hotkey",
        "settings_export": "Export Settings", "settings_export_format": "Format",
        "settings_export_include_cover": "Include cover (HTML only)",
        "settings_platform_mgr": "Platform Manager",
        "settings_platform_mgr_hint": "Add/remove/edit custom platforms. Saved to engines.json.",
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
        "import_manual_platform_hint": "Required. Used to match games.",
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
        "controls_no_data": "No control data for this emulator. Check official docs.",
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
        "bios_select_hint": "Selected BIOS will be copied to emulator's BIOS dir on launch.",
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
        "launch_core_missing": "Missing RetroArch core: {core}. Configure in Settings → RetroArch Core Dir.",
        "launch_retroarch_missing": "RetroArch not installed. Please download/import RetroArch.",
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
        "msg_ok": "OK", "msg_cancel": "Cancel", "msg_warning": "Warning",
        "msg_error": "Error", "msg_info": "Info", "msg_confirm": "Confirm",
    },
}


def _machine_translate(zh_pack: dict, lang: str) -> dict:
    MAPS = {
        "ru": {
            "游戏库": "Библиотека", "模拟器": "Эмуляторы", "设置": "Настройки",
            "统计": "Статистика", "资源": "Ресурсы",
            "导入": "Импорт", "下载": "Скачать",
            "刷新": "Обновить", "搜索游戏名...": "Поиск игры...",
            "全部平台": "Все платформы", "名称": "Имя", "平台": "Платформа",
            "大小": "Размер", "时长": "Время", "路径": "Путь",
            "收藏": "Избранное", "最近": "Недавние", "全部": "Все",
            "请先选中一个游戏": "Сначала выберите игру",
            "启动": "Запуск", "取消": "Отмена", "确定": "OK",
            "警告": "Внимание", "错误": "Ошибка", "提示": "Инфо",
            "确认": "Подтвердить", "保存": "Сохранить",
            "语言": "Язык", "工作区": "Рабочая область",
            "管理员权限": "Права администратора",
            "以管理员重启": "Перезапуск от администратора",
            "下载线程数": "Потоки загрузки", "添加": "Добавить",
            "删除": "Удалить", "上移": "Вверх", "下移": "Вниз",
            "测试全部": "Проверить все", "恢复默认": "Сбросить",
            "已导出到: {path}": "Экспортировано: {path}",
            "还没有游戏。": "Игр пока нет.",
            "系统托盘": "Системный трей",
            "平台管理": "Управление платформами",
            "添加平台": "Добавить платформу",
            "保存平台": "Сохранить платформы",
            "平台 ID": "ID платформы",
            "显示名": "Отображаемое имя",
            "扩展名（逗号分隔）": "Расширения (запятая)",
            "操作": "Действие",
            "鸣谢": "Благодарности",
            "查看鸣谢": "Показать благодарности",
            "资源导航": "Навигация по ресурсам",
            "打开": "Открыть",
            "操作说明": "Управление",
            "来源": "Источник",
            "Python 依赖": "Зависимости Python",
            "开源模拟器项目": "Открытые эмуляторы",
            "数据与规范": "Данные и стандарты",
            "特别感谢": "Особая благодарность",
        },
        "ja": {
            "游戏库": "ライブラリ", "模拟器": "エミュレータ", "设置": "設定",
            "统计": "統計", "资源": "リソース",
            "导入": "インポート", "下载": "ダウンロード",
            "刷新": "更新", "搜索游戏名...": "ゲームを検索...",
            "全部平台": "すべてのプラットフォーム", "名称": "名前",
            "平台": "プラットフォーム", "大小": "サイズ",
            "时长": "プレイ時間", "路径": "パス",
            "收藏": "お気に入り", "最近": "最近", "全部": "すべて",
            "请先选中一个游戏": "ゲームを選択してください",
            "启动": "起動", "取消": "キャンセル", "确定": "OK",
            "警告": "警告", "错误": "エラー", "提示": "情報",
            "确认": "確認", "保存": "保存",
            "语言": "言語", "工作区": "ワークスペース",
            "管理员权限": "管理者権限",
            "以管理员重启": "管理者として再起動",
            "下载线程数": "ダウンロードスレッド数", "添加": "追加",
            "删除": "削除", "上移": "上へ", "下移": "下へ",
            "测试全部": "すべてテスト", "恢复默认": "デフォルトに戻す",
            "已导出到: {path}": "エクスポート先: {path}",
            "还没有游戏。": "ゲームがありません。",
            "系统托盘": "システムトレイ",
            "平台管理": "プラットフォーム管理",
            "添加平台": "プラットフォーム追加",
            "保存平台": "プラットフォーム保存",
            "平台 ID": "プラットフォーム ID",
            "显示名": "表示名",
            "扩展名（逗号分隔）": "拡張子（カンマ区切り）",
            "操作": "操作",
            "鸣谢": "謝辞",
            "查看鸣谢": "謝辞を表示",
            "资源导航": "リソースナビ",
            "打开": "開く",
            "操作说明": "操作方法",
            "来源": "出典",
            "Python 依赖": "Python 依存関係",
            "开源模拟器项目": "オープンソースエミュレータ",
            "数据与规范": "データと標準",
            "特别感谢": "特別な感謝",
        },
        "fr": {
            "游戏库": "Bibliothèque", "模拟器": "Émulateurs", "设置": "Paramètres",
            "统计": "Statistiques", "资源": "Ressources",
            "导入": "Importer", "下载": "Télécharger",
            "刷新": "Actualiser", "搜索游戏名...": "Rechercher un jeu...",
            "全部平台": "Toutes les plateformes", "名称": "Nom",
            "平台": "Plateforme", "大小": "Taille", "时长": "Durée",
            "路径": "Chemin",
            "收藏": "Favoris", "最近": "Récents", "全部": "Tout",
            "请先选中一个游戏": "Sélectionnez un jeu",
            "启动": "Lancer", "取消": "Annuler", "确定": "OK",
            "警告": "Avertissement", "错误": "Erreur", "提示": "Info",
            "确认": "Confirmer", "保存": "Enregistrer",
            "语言": "Langue", "工作区": "Espace de travail",
            "管理员权限": "Droits admin",
            "以管理员重启": "Relancer en admin",
            "下载线程数": "Threads de téléchargement", "添加": "Ajouter",
            "删除": "Supprimer", "上移": "Monter", "下移": "Descendre",
            "测试全部": "Tout tester", "恢复默认": "Réinitialiser",
            "已导出到: {path}": "Exporté vers : {path}",
            "还没有游戏。": "Aucun jeu.",
            "系统托盘": "Barre système",
            "平台管理": "Gestion des plateformes",
            "添加平台": "Ajouter une plateforme",
            "保存平台": "Enregistrer les plateformes",
            "平台 ID": "ID de plateforme",
            "显示名": "Nom affiché",
            "扩展名（逗号分隔）": "Extensions (séparées par virgule)",
            "操作": "Opération",
            "鸣谢": "Remerciements",
            "查看鸣谢": "Voir les remerciements",
            "资源导航": "Navigation des ressources",
            "打开": "Ouvrir",
            "操作说明": "Commandes",
            "来源": "Source",
            "Python 依赖": "Dépendances Python",
            "开源模拟器项目": "Émulateurs open source",
            "数据与规范": "Données et normes",
            "特别感谢": "Remerciements spéciaux",
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


LANG_PACKS: dict[str, dict] = {}
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

# ===== 第 1/3 部分结束，回复"继续"输出第 2/3 部分 =====

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
}
SAVE_PATHS: dict[str, str] = {}
CHEAT_PATHS: dict[str, dict] = {}
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
# 5.5 操作说明数据库（内置 40 个引擎）
# ============================================================
CONTROLS_DB = {
    "snes9x": {
        "source": "https://www.snes9x.com/",
        "keys": {
            "方向": "方向键",
            "A/B/X/Y": "A / S / D / X 或键盘映射",
            "L/R": "Q / W",
            "Start": "Enter",
            "Select": "Shift",
            "存档/读档": "F5 / F7",
            "快进": "Tab",
            "全屏": "Alt+Enter",
            "截图": "F12",
        }
    },
    "duckstation": {
        "source": "https://github.com/stenzek/duckstation/wiki",
        "keys": {
            "方向": "WASD / 方向键",
            "△○×□": "I / L / K / J",
            "L1/R1/L2/R2": "Q / E / 1 / 3",
            "Start/Select": "Enter / Backspace",
            "存档/读档": "F1 / F4",
            "快进": "Tab",
            "全屏": "Alt+Enter",
        }
    },
    "epsxe": {
        "source": "https://www.epsxe.com/",
        "keys": {
            "方向": "方向键",
            "△○×□": "I / L / K / J",
            "L1/R1/L2/R2": "Q / E / 1 / 3",
            "Start/Select": "Enter / Space",
            "存档/读档": "F1 / F3",
            "全屏": "Alt+Enter",
        }
    },
    "xebra": {
        "source": "http://drhell.web.fc2.com/ps1/",
        "keys": {
            "方向": "方向键",
            "按键": "Z / X / C / V 等（可在设置里改）",
            "全屏": "Alt+Enter",
        }
    },
    "mednafen": {
        "source": "https://mednafen.github.io/documentation/",
        "keys": {
            "方向": "WASD 或方向键",
            "A/B": "K / L 或 Keypad 2/3",
            "Start/Select": "Enter / Tab",
            "存档/读档": "F5 / F7",
            "快进": "Tab（需配置）",
            "全屏": "Alt+Enter",
            "配置菜单": "F1",
        }
    },
    "ssf": {
        "source": "http://redlotusflame.uupan.net/",
        "keys": {
            "方向": "方向键",
            "按键": "Z / X / C / V / A / S / D / F",
            "Start": "Enter",
            "全屏": "Alt+Enter",
        }
    },
    "ymir": {
        "source": "https://github.com/ymir-emu/Ymir",
        "keys": {
            "方向": "方向键 / 手柄",
            "A/B/C": "Z / X / C",
            "X/Y/Z": "A / S / D",
            "L/R": "Q / E",
            "Start": "Enter",
            "全屏": "Alt+Enter",
        }
    },
    "brimir": {
        "source": "https://github.com/coredds/brimir",
        "keys": {
            "说明": "libretro 核心，键位由 RetroArch 管理",
            "方向": "方向键 / 手柄",
            "A/B": "RetroArch 默认映射",
            "热键": "F1 打开 RetroArch 菜单",
        }
    },
    "flycast": {
        "source": "https://github.com/flyinghead/flycast",
        "keys": {
            "方向": "方向键",
            "A/B/X/Y": "A / S / D / X",
            "L/R": "Q / W",
            "Start": "Enter",
            "存档/读档": "F5 / F7",
            "全屏": "Alt+Enter",
        }
    },
    "redream": {
        "source": "https://redream.io/",
        "keys": {
            "方向": "方向键 / 手柄",
            "A/B/X/Y": "手柄默认",
            "Start": "Enter",
            "全屏": "Alt+Enter",
        }
    },
    "deecy": {
        "source": "https://github.com/Senryoku/Deecy",
        "keys": {
            "说明": "Zig 实验性项目，键位参考源码或 README",
        }
    },
    "dreampotato": {
        "source": "https://github.com/RikkiGibson/DreamPotato",
        "keys": {
            "说明": "VMU 记忆卡模拟器，无游戏键位",
        }
    },
    "mgba": {
        "source": "https://mgba.io/",
        "keys": {
            "方向": "方向键",
            "A": "Z",
            "B": "X",
            "L": "A",
            "R": "S",
            "Start": "Enter",
            "Select": "Backspace",
            "快进": "Tab",
            "存档/读档": "F5 / F7",
            "全屏": "Alt+Enter",
        }
    },
    "pcsx2": {
        "source": "https://pcsx2.net/docs/",
        "keys": {
            "方向": "WASD / 方向键",
            "△○×□": "I / L / K / J",
            "L1/R1/L2/R2": "Q / E / 1 / 3",
            "Start/Select": "Enter / Backspace",
            "存档/读档": "F1 / F3",
            "快进": "Tab",
            "全屏": "Alt+Enter",
            "暂停": "Space",
        }
    },
    "fceux": {
        "source": "https://fceux.com/web/home.html",
        "keys": {
            "方向": "方向键",
            "A/B": "Z / X",
            "连发 A/B": "A / S",
            "Start/Select": "Enter / Shift",
            "存档/读档": "F5 / F7（F1-F4 快存）",
            "快进": "Tab",
            "全屏": "Alt+Enter",
        }
    },
    "mesence": {
        "source": "https://github.com/nesdev-org/MesenCE",
        "keys": {
            "方向": "方向键",
            "A/B": "Z / X",
            "连发 A/B": "A / S",
            "Start/Select": "Enter / Shift",
            "存档/读档": "F5 / F7",
            "快进": "Tab",
            "全屏": "Alt+Enter",
        }
    },
    "mupen64plus": {
        "source": "https://mupen64plus.org/",
        "keys": {
            "方向": "方向键",
            "A/B": "X / C",
            "C 按键": "J / K / L / I",
            "L/R/Z": "Q / W / E",
            "Start": "Enter",
            "存档/读档": "F5 / F7",
            "全屏": "Alt+Enter",
        }
    },
    "gopher64": {
        "source": "https://github.com/gopher64/gopher64",
        "keys": {
            "说明": "键位参考 README 或源码默认值",
        }
    },
    "ares": {
        "source": "https://ares-emu.net/",
        "keys": {
            "说明": "多平台模拟器，键位在设置里逐平台配置",
            "菜单": "F1 或手柄 Start",
        }
    },
    "simple64": {
        "source": "https://simple64.github.io/",
        "keys": {
            "方向": "方向键",
            "A/B": "X / C",
            "C 按键": "J / K / L / I",
            "L/R/Z": "Q / W / E",
            "Start": "Enter",
            "存档/读档": "F5 / F7",
        }
    },
    "rmg": {
        "source": "https://github.com/Rosalie241/RMG",
        "keys": {
            "方向": "方向键",
            "A/B": "X / C",
            "C 按键": "J / K / L / I",
            "L/R/Z": "Q / W / E",
            "Start": "Enter",
            "存档/读档": "F5 / F7",
        }
    },
    "project64": {
        "source": "https://www.pj64-emu.com/",
        "keys": {
            "方向": "方向键",
            "A/B": "X / C",
            "C 按键": "J / K / L / I",
            "L/R/Z": "Q / W / E",
            "Start": "Enter",
            "存档/读档": "F5 / F7",
        }
    },
    "desmume": {
        "source": "https://desmume.org/",
        "keys": {
            "方向": "方向键",
            "A/B/X/Y": "X / Z / S / A",
            "L/R": "Q / W",
            "Start/Select": "Enter / Backspace",
            "触摸屏": "鼠标",
            "存档/读档": "Shift+F1 / F1",
            "全屏": "Alt+Enter",
        }
    },
    "melonds": {
        "source": "https://melonds.kuribo64.net/",
        "keys": {
            "方向": "方向键",
            "A/B/X/Y": "X / Z / S / A",
            "L/R": "Q / W",
            "Start/Select": "Enter / Backspace",
            "触摸屏": "鼠标",
            "存档/读档": "F5 / F7",
            "全屏": "Alt+Enter",
        }
    },
    "blastem": {
        "source": "https://www.retrodev.com/blastem/",
        "keys": {
            "方向": "方向键",
            "A/B/C": "A / S / D",
            "X/Y/Z": "Z / X / C",
            "Start/Mode": "Enter / Shift",
            "全屏": "Alt+Enter",
        }
    },
    "kega-fusion": {
        "source": "https://kega-fusion.com/",
        "keys": {
            "方向": "方向键",
            "A/B/C": "A / S / D",
            "X/Y/Z": "Z / X / C",
            "Start": "Enter",
            "存档/读档": "F5 / F8",
            "全屏": "Alt+Enter",
        }
    },
    "sameboy": {
        "source": "https://github.com/LIJI32/SameBoy",
        "keys": {
            "方向": "方向键",
            "A/B": "A / S",
            "Start/Select": "Enter / Backspace",
            "存档/读档": "F5 / F7",
            "快进": "Tab",
        }
    },
    "gambatte": {
        "source": "https://github.com/sinamas/gambatte",
        "keys": {
            "方向": "方向键",
            "A/B": "Z / X",
            "Start/Select": "Enter / Backspace",
            "存档/读档": "F5 / F7",
        }
    },
    "ppsspp": {
        "source": "https://www.ppsspp.org/docs/",
        "keys": {
            "方向": "WASD / 方向键",
            "○×△□": "L / K / I / J",
            "L/R": "Q / E",
            "Start/Select": "Enter / Backspace",
            "存档/读档": "F2 / F4",
            "快进": "Tab",
            "全屏": "Alt+Enter",
        }
    },
    "ryujinx": {
        "source": "https://ryujinx.app/",
        "keys": {
            "方向": "WASD / 方向键",
            "A/B/X/Y": "手柄默认",
            "L/R/ZL/ZR": "手柄默认",
            "全屏": "F11",
        }
    },
    "yuzu": {
        "source": "https://yuzu-mirror.github.io/",
        "keys": {
            "方向": "WASD",
            "A/B/X/Y": "手柄默认",
            "L/R/ZL/ZR": "手柄默认",
            "全屏": "F11",
        }
    },
    "mame": {
        "source": "https://docs.mamedev.org/usingmame/defaultkeys.html",
        "keys": {
            "投币": "5 / 6",
            "开始": "1 / 2",
            "移动": "方向键",
            "按钮 1-6": "Left Ctrl / Left Alt / Space / Left Shift / Z / X",
            "配置菜单": "Tab",
            "暂停": "P",
            "存档/读档": "Shift+F7 / F7",
            "全屏": "Alt+Enter",
            "退出": "Esc",
        }
    },
    "px68k": {
        "source": "https://github.com/libretro/px68k-libretro",
        "keys": {
            "说明": "libretro 核心，键位由 RetroArch 管理",
            "菜单": "F1（RetroArch）",
        }
    },
    "np2kai": {
        "source": "https://github.com/AZO234/NP2kai",
        "keys": {
            "说明": "libretro 核心，键位由 RetroArch 管理",
            "菜单": "F1（RetroArch）",
        }
    },
    "tsugaru": {
        "source": "https://github.com/captainys/TOWNSEMU",
        "keys": {
            "说明": "键位参考 README，可在设置里改",
        }
    },
    "pcfxemu": {
        "source": "https://github.com/gameblabla/pcfxemu",
        "keys": {
            "方向": "方向键",
            "I/II/III/IV/V/VI": "Z / X / C / V / A / S",
            "Start/Select": "Enter / Shift",
            "全屏": "Alt+Enter",
        }
    },
    "openmsx": {
        "source": "https://openmsx.org/manual/",
        "keys": {
            "方向": "方向键",
            "A/B": "Space / 左 Alt",
            "空格": "Space",
            "配置菜单": "F10",
            "全屏": "Alt+Enter",
        }
    },
    "bluemsx": {
        "source": "https://www.msxblue.com/",
        "keys": {
            "方向": "方向键",
            "A/B": "Z / X",
            "空格": "Space",
            "开始": "Enter",
            "全屏": "Alt+Enter",
        }
    },
    "retroarch": {
        "source": "https://docs.libretro.com/guides/retroarch-basics/",
        "keys": {
            "菜单导航": "方向键",
            "选择": "Enter / X",
            "返回": "Backspace / Z",
            "A/B": "X / Z（默认）",
            "X/Y": "S / A（默认）",
            "L/R": "Q / W（默认）",
            "Start/Select": "Enter / RShift",
            "热键": "F1 打开菜单",
            "快进": "Space",
            "存档/读档": "F2 / F4",
        }
    },
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
    p = Path(path_str)
    if p.suffix.lower() not in (".bin", ".iso", ".img"):
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

    def __init__(self, installed: list[EmulatorConfig], engines_json: dict):
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
                        rom_path: str = "") -> list[str]:
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
    actual_rom, switched = resolve_rom_for_launch(game.path)

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

# ===== 第 2/3 部分结束，回复"继续"输出第 3/3 部分 =====

# ============================================================
# 16. QSS
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
    padding: 6px 10px;
    selection-background-color: #0067c0; selection-color: white;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { background-color: #ffffff; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-bottom: 2px solid #0067c0; background-color: #ffffff;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #666; margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff; border: 1px solid #d9d9d9;
    border-radius: 5px; selection-background-color: #e8e8e8;
    selection-color: #1c1c1c; outline: none; padding: 4px;
}
QPushButton {
    background-color: #fbfbfb; border: 1px solid #d9d9d9;
    border-bottom: 2px solid #d9d9d9; border-radius: 5px;
    padding: 6px 14px; color: #1c1c1c; min-height: 18px;
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
                return human_duration(row.play_seconds)
            if col == 6:
                return row.path
        if role == Qt.ForegroundRole:
            if col == 0:
                return QColor("#f7b500") if row.favorite else QColor("#cccccc")
            if col == 1:
                return QColor("#c47f00")
            if col == 3:
                return QColor("#0067c0")
        if role == Qt.TextAlignmentRole and col in (0, 1, 4, 5):
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
        self._updates: dict[str, tuple] = {}

    def set_rows(self, rows: list[EmulatorConfig]):
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
# 19. 对话框
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

    def result_data(self) -> Optional[dict]:
        return self._result


class BiosSelectDialog(QDialog):
    def __init__(self, game: GameEntry, parent=None):
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
    """操作说明弹窗"""
    def __init__(self, engine_name: str, parent=None):
        super().__init__(parent)
        self._engine_name = engine_name
        self.setWindowTitle(f"{tr('controls_title')} - {engine_name}")
        self.setMinimumSize(480, 520)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        data = get_controls(self._engine_name)
        if data is None:
            data = get_generic_controls()

        head = QLabel(
            f"<b>{tr('controls_engine')}:</b> {self._engine_name}<br>"
        )
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
    """鸣谢"""
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

        # Python 依赖
        g1 = QGroupBox(tr("credits_deps"))
        f1 = QVBoxLayout(g1)
        deps_text = (
            "<b>PySide6</b> — Qt for Python, LGPL v3<br>"
            "<b>requests</b> — Apache 2.0<br>"
            "<b>loguru</b> — MIT<br>"
            "<b>py7zr</b> — LGPL v2.1+<br>"
            "<b>rarfile</b> — ISC<br>"
            "<b>certifi</b> — MPL 2.0<br>"
            "<b>psutil</b> — BSD-3-Clause"
        )
        lbl1 = QLabel(deps_text)
        lbl1.setWordWrap(True)
        lbl1.setTextFormat(Qt.RichText)
        f1.addWidget(lbl1)
        v.addWidget(g1)

        # 开源模拟器项目
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
            "<br>感谢以上所有开源/闭源模拟器项目的作者与贡献者。"
        )
        lbl2 = QLabel(emu_text)
        lbl2.setWordWrap(True)
        f2.addWidget(lbl2)
        v.addWidget(g2)

        # 数据与规范
        g3 = QGroupBox(tr("credits_data"))
        f3 = QVBoxLayout(g3)
        data_text = (
            "<b>No-Intro</b> — ROM 命名规范<br>"
            "<b>Redump</b> — 光盘校验数据库<br>"
            "<b>MAME 键位文档</b><br>"
            "<b>Libretro 文档</b>"
        )
        lbl3 = QLabel(data_text)
        lbl3.setWordWrap(True)
        lbl3.setTextFormat(Qt.RichText)
        f3.addWidget(lbl3)
        v.addWidget(g3)

        # 特别感谢
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
    def __init__(self, exe_files: list[Path], engines_json: dict, parent=None):
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

    def result_data(self) -> Optional[dict]:
        return self._result


class ExportDialog(QDialog):
    def __init__(self, games: list[GameEntry], parent=None):
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

    def result_data(self) -> Optional[dict]:
        return self._result


class PlatformConfirmDialog(QDialog):
    def __init__(self, games: list[GameEntry], engines_json: dict, parent=None):
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

    def result_games(self) -> list[GameEntry]:
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
    cheat_requested = Signal(GameEntry)
    bios_requested = Signal(GameEntry)
    controls_requested = Signal(GameEntry)

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
            if g.override_platform or g.override_engine or g.extra_args or g.bios_file:
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
                f"{g.name}\n{g.custom_platform or g.platform}\n{human_duration(g.play_seconds)}")
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
# 21. 页面：模拟器 / BIOS / 统计 / 资源
# ============================================================
class EnginePage(QWidget):
    import_requested = Signal()
    download_requested = Signal()
    update_requested = Signal(str, str, str)
    ignore_requested = Signal(str, str, str)

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

        self._update_worker: Optional[UpdateCheckWorker] = None

    def refresh(self):
        self._model.set_rows(load_installed())

    def check_updates(self):
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


class ChartWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._data: list[tuple[str, int]] = []
        self.setMinimumHeight(160)

    def set_data(self, data):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 10, 10, 28
        cw = w - pad_l - pad_r
        ch = h - pad_t - pad_b
        max_v = max((v for _, v in self._data), default=1)
        if max_v <= 0:
            max_v = 1
        n = len(self._data)
        if n == 0:
            return
        bar_w = cw / n * 0.7
        gap = cw / n

        painter.setPen(QPen(QColor("#e5e5e5"), 1))
        painter.drawLine(pad_l, pad_t + ch, pad_l + cw, pad_t + ch)

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
            f = painter.font()
            f.setPointSize(8)
            painter.setFont(f)
            painter.drawText(int(x - 5), pad_t + ch + 14,
                             int(bar_w + 10), 14,
                             Qt.AlignCenter, label)

        painter.end()


class StatsPage(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        title = QLabel(tr("stats_title"))
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        cards = QHBoxLayout()
        self.lbl_time = self._make_card(cards, tr("stats_total_time"))
        self.lbl_games = self._make_card(cards, tr("stats_total_games"))
        self.lbl_launches = self._make_card(cards, tr("stats_total_launches"))
        root.addLayout(cards)

        self.lbl_by_platform = QLabel()
        self.lbl_by_platform.setObjectName("Hint")
        self.lbl_by_platform.setWordWrap(True)
        root.addWidget(self.lbl_by_platform)

        chart_grp = QGroupBox(tr("stats_last_7d"))
        cv = QVBoxLayout(chart_grp)
        self.chart_7d = ChartWidget()
        self.chart_7d.setMinimumHeight(180)
        cv.addWidget(self.chart_7d)
        root.addWidget(chart_grp)

        chart_grp2 = QGroupBox(tr("stats_last_30d"))
        cv2 = QVBoxLayout(chart_grp2)
        self.chart_30d = ChartWidget()
        self.chart_30d.setMinimumHeight(180)
        cv2.addWidget(self.chart_30d)
        root.addWidget(chart_grp2)

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
        root.addWidget(badge_grp)

        root.addStretch(1)

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

        by_plat: dict[str, int] = {}
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

    def _build_series(self, daily: dict, days: int) -> list[tuple[str, int]]:
        result = []
        now = time.time()
        for i in range(days - 1, -1, -1):
            d = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            total = sum((daily.get(d) or {}).values())
            result.append((d[5:], total))
        return result

    def _compute_badges(self, games: list[GameEntry], daily: dict) -> dict:
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
    """资源跳转页"""
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
        # 清空
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            else:
                # layout
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
            # 直接打开文件
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
# 22. 页面：设置
# ============================================================
class SettingsPage(QWidget):
    lang_changed = Signal(str)
    saves_changed = Signal()
    retroarch_changed = Signal()
    platforms_changed = Signal()

    def __init__(self):
        super().__init__()
        self._mirror_test_worker: Optional[MirrorTestWorker] = None
        self._api_test_worker: Optional[MirrorTestWorker] = None
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

        # 平台管理
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

        # RetroArch 核心
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

        # 金手指
        box_ch = QGroupBox(tr("settings_cheats"))
        fch = QVBoxLayout(box_ch)
        h_ch = QLabel(tr("settings_cheats_hint"))
        h_ch.setObjectName("Hint")
        h_ch.setWordWrap(True)
        fch.addWidget(h_ch)
        self._cheat_rows: dict[str, tuple[QLineEdit, QLineEdit]] = {}
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

        # 托盘
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
        v.addWidget(box_tray)

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

        # 管理员 + 鸣谢
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
        test_url = "https://github.com/robots.txt"
        self.lbl_mirror_result.setText(tr("settings_mirrors_testing"))
        self.list_mirrors.clear()
        self._mirror_test_worker = MirrorTestWorker(test_url, use_api=False)
        self._mirror_test_worker.one.connect(self._on_mirror_test_one)
        self._mirror_test_worker.done.connect(self._on_mirror_test_done)
        self._mirror_test_worker.start()

    def _api_mirror_test(self):
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
# 24. 下载对话框
# ============================================================
class DownloadDialog(QDialog):
    def __init__(self, engines_json: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("download_title"))
        self.setMinimumSize(780, 640)
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
# 25. 导出功能
# ============================================================
def export_library(games: list[GameEntry], fmt: str, scope: str,
                   include_playtime: bool, include_cover: bool) -> Path:
    if scope == "fav":
        games = [g for g in games if g.favorite]
    if not games:
        raise RuntimeError("没有可导出的游戏")

    ts = time.strftime("%Y%m%d_%H%M%S")
    ext = ".md" if fmt == "md" else (".html" if fmt == "html" else ".csv")
    out = EXPORT_DIR / f"library_{ts}{ext}"

    if fmt == "md":
        lines = [f"# mikan_emu 游戏库\n", f"共 {len(games)} 个游戏\n"]
        by_plat: dict[str, list[GameEntry]] = {}
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
# 26. 主窗口 + 托盘
# ============================================================
class MainWindow(QMainWindow):
    NAV_LIBRARY = 0
    NAV_ENGINES = 1
    NAV_BIOS = 2
    NAV_STATS = 3
    NAV_RESOURCES = 4
    NAV_SETTINGS = 5

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 800)
        self.setMinimumSize(960, 580)

        self._load_lang()
        self._engines_json = load_engines_json()
        self._monitor_workers: list[ProcessMonitorWorker] = []
        self._tray = None
        self._force_quit = False

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
                     tr("nav_resources"), tr("nav_settings")]:
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

        self.page_settings = SettingsPage()
        self.page_settings.lang_changed.connect(self._on_lang_changed)
        self.page_settings.platforms_changed.connect(self._on_platforms_changed)
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

    def _select_bios(self, game: GameEntry):
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

    def _show_controls(self, game: GameEntry):
        engine = self._resolve_engine(game, silent=True)
        engine_name = engine.engine if engine else ""
        if not engine_name:
            # 尝试按平台猜
            installed = load_installed()
            for e in installed:
                if e.platform == (game.override_platform or game.platform):
                    engine_name = e.engine
                    break
        dlg = ControlsDialog(engine_name or "unknown", self)
        dlg.exec()

    def _manage_cheat(self, game: GameEntry):
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

    def _resolve_engine(self, game: GameEntry,
                        silent: bool = False) -> Optional[EmulatorConfig]:
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

    def _launch_game(self, game: GameEntry):
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
                    break
            save_games(games)
            self._reload_games()

            if SETTINGS.get("tray_minimize_after_launch", False) and self._tray:
                self.hide()

            if HAS_PSUTIL and proc:
                monitor = ProcessMonitorWorker(proc.pid)
                monitor.finished.connect(
                    lambda secs, gp=game.path, pf=game.platform: self._on_game_closed(gp, secs, pf))
                monitor.start()
                self._monitor_workers.append(monitor)
        except Exception as e:
            QMessageBox.critical(self, tr("msg_error"),
                                 tr("launch_failed", err=str(e)))

    def _on_game_closed(self, game_path: str, seconds: int, platform: str):
        try:
            games = load_games()
            for g in games:
                if g.path == game_path:
                    g.play_seconds += seconds
                    break
            save_games(games)
            record_playtime(platform, seconds)
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
# 27. 入口
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