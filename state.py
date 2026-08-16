# -*- coding: utf-8 -*-
"""全局状态与基础配置：路径常量、config 读写、游戏目录探测与切换。

被 app.py 及各业务模块共享。

⚠️ 关键约定：GAME_DIR / MODS_DIR / LOAD_ORDER_FILE 是**可变状态**（apply_game_dir 会热切换），
引用方必须用 `state.GAME_DIR` 属性访问（动态取最新值），
**不要** `from state import GAME_DIR`（那是值拷贝，切换后拿不到新值）。
函数与不可变常量可以 from-import。
"""
import json
import os
import re
import sys
import threading
from pathlib import Path

IS_FROZEN = getattr(sys, "frozen", False)

# 开发模式: 脚本目录；frozen(exe) 模式: exe 所在目录（可写数据放这里）
BASE_DIR = Path(sys.executable if IS_FROZEN else __file__).resolve().parent
# 资源目录: frozen 时是 PyInstaller 解压的临时目录（只读资源）
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

CONFIG_FILE = BASE_DIR / "config.json"
PROFILES_DIR = BASE_DIR / "profiles"
BACKUP_DIR = BASE_DIR / "backups"
STATIC_DIR = RESOURCE_DIR / "static"
GAME_FOLDER_NAME = "Warhammer 40,000 DARKTIDE"
APP_ID = "1361210"
SYSTEM_MODS = {"base", "dmf"}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))  # utf-8-sig 防 BOM
        except Exception:
            pass
    return {}


def detect_game_dir() -> Path | None:
    """纯 Steam 库扫描（忽略 config）：在常见 Steam 库路径中找暗潮游戏目录，找不到返回 None"""
    cands = []
    steam_roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"D:\Steam"),
        Path(r"D:\SteamLibrary"),
    ]
    for root in steam_roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                text = vdf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                lib = m.group(1).replace("\\\\", "\\")
                cands.append(Path(lib) / "steamapps" / "common" / GAME_FOLDER_NAME)

    for c in cands:
        if is_valid_game_dir(c):
            return c

    return None


def find_game_dir() -> Path | None:
    """优先级: config.json 覆盖 > Steam libraryfolders.vdf 探测；找不到返回 None"""
    cfg = load_config()
    if cfg.get("game_dir"):
        p = Path(cfg["game_dir"])
        if p.exists():
            return p

    return detect_game_dir()


def is_valid_game_dir(p: Path) -> bool:
    """游戏目录判定：mods 存在（已装 DMF）或 bundle 存在（原版新装）都算"""
    return p.is_dir() and ((p / "mods").is_dir() or (p / "bundle").is_dir())


GAME_DIR = find_game_dir() or Path.cwd()  # 找不到时用当前目录占位（game_dir_valid=False，UI 显示缺失）
MODS_DIR = GAME_DIR / "mods"
LOAD_ORDER_FILE = MODS_DIR / "mod_load_order.txt"


# 游戏目录三全局变量切换锁：apply_game_dir 内整体持锁，防止并发读读到
# GAME_DIR 已是新值、MODS_DIR 还是旧值的跨帧组合（写方原子；读方单次取值本身原子）
_paths_lock = threading.RLock()


def apply_game_dir(p: Path) -> bool:
    """保存游戏目录到 config 并立即生效（更新全局变量，无需重启）"""
    global GAME_DIR, MODS_DIR, LOAD_ORDER_FILE
    with _paths_lock:
        cfg = load_config()
        cfg["game_dir"] = str(p)
        try:
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            return False
        GAME_DIR = p
        MODS_DIR = p / "mods"
        LOAD_ORDER_FILE = MODS_DIR / "mod_load_order.txt"
    return True
