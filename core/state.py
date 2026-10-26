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

# 开发模式项目根：core/ 的父目录（本文件在 core/ 子包内）
_DEV_ROOT = Path(__file__).resolve().parent.parent

# 开发模式: 项目根；frozen(exe) 模式: exe 所在目录（可写数据放这里，注意取 sys.executable 的父目录）
BASE_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else _DEV_ROOT
# 资源目录: frozen 时是 PyInstaller 解压的临时目录（只读资源）
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", _DEV_ROOT))

CONFIG_FILE = BASE_DIR / "config.json"
PROFILES_DIR = BASE_DIR / "profiles"
BACKUP_DIR = BASE_DIR / "backups"
# 「我的 mod」管理器库区：自研/私装 mod 的家（换包不会碰它）。游戏目录只是部署目标，
# 库才是安全副本——换包/清空游戏目录/误删都能从这里恢复。
MY_MODS_DIR = BASE_DIR / "my_mods"
STATIC_DIR = RESOURCE_DIR / "static"


def is_junction(p: Path) -> bool:
    """是不是目录联接/符号链接（开发机常用 Junction 把源码工程直连进游戏 mods 目录）。

    ⚠️ 实测（Python 3.12）：`shutil.rmtree(junction)` 会**直接抛错拒绝**；
    rmtree 一个"内含 junction 的父目录"只会摘掉链接、**不穿透删目标内容**。
    所以不会误删源码，但顶层删除会失败——需要按链接单独处理（见 safe_rmtree）。"""
    try:
        if p.is_symlink():
            return True
        return bool(hasattr(os, "path") and os.path.isjunction(p))
    except OSError:
        return False


def _force_writable(func, path, exc_info) -> None:
    """删除失败时清掉**只读位**再试一次（Windows 上 rmtree 遇只读文件直接 WinError 5 拒绝访问）。

    ⚠️ 实测（2026-10-06）：整合包里常有 git 检出，`.git/objects/*` 之类文件是只读的，
    `shutil.rmtree(..., ignore_errors=True)` 会**静默失败**——暂存目录、临时解压目录、
    备份清理全都删不掉，磁盘上悄悄堆垃圾（用户那次导入就留下了整份解压副本）。
    还有"文件被占用"（WinError 32）也走这里：清位后重试一次，仍失败就放弃（不抛）。"""
    try:
        import stat as _stat
        os.chmod(path, _stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def safe_rmtree(p: Path, ignore_errors: bool = False) -> bool:
    """删除目录/文件，但**联接与符号链接只摘链接、绝不递归进目标**；返回是否真的动了东西。

    用在会碰到游戏 mods 目录 / 管理器库 / 备份目录的删除动作上。只读文件会自动清位重试。"""
    import shutil as _shutil
    try:
        if not p.exists() and not is_junction(p):
            return False
        if is_junction(p):
            try:
                os.rmdir(p)          # 目录联接：摘链接（目标不受影响）
            except OSError:
                p.unlink()           # 文件符号链接
            return True
        if p.is_dir():
            # 注意：ignore_errors=True 时 shutil 不会调用 onerror，只读文件会静默留下；
            # 所以这里始终挂 onerror（内部自己吞异常），ignore_errors 只影响最后的兜底行为。
            _shutil.rmtree(p, onerror=_force_writable)
        else:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                _force_writable(os.unlink, str(p), None)
        return True
    except Exception:
        if not ignore_errors:
            raise
        return False
GAME_FOLDER_NAME = "Warhammer 40,000 DARKTIDE"
# Xbox app / PC Game Pass 安装根目录名（Xbox app 让用户选盘，默认整盘根下的 XboxGames），
# 游戏目录形如 <盘>:\XboxGames\<游戏名>\Content（bundle/、mods/ 在 Content 下）
# ⚠️ 该分支为实验功能（2026-10-02 从 snapshot 并回）：仅单测覆盖，未在真机 Game Pass 环境实测
XBOX_GAMES_DIR_NAME = "XboxGames"
XBOX_DRIVE_LETTERS = tuple("CDEFGHIJ")
# 目录名过滤：只在名字像暗潮的目录里找，避免把 XboxGames 下其它游戏当候选
XBOX_NAME_HINTS = ("darktide", "warhammer")
APP_ID = "1361210"
SYSTEM_MODS = {"base", "dmf"}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))  # utf-8-sig 防 BOM
        except Exception:
            pass
    return {}


def _steam_game_candidates() -> list[Path]:
    """Steam 库里的暗潮目录候选项（解析各库 libraryfolders.vdf）"""
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
    # 去重（同一个库会被多个 libraryfolders.vdf 列出：C:\…\Steam 与 D:\SteamLibrary 互相登记）——
    # 不去重时 app.log 的环境诊断里同一路径会出现两次，看着像扫了两遍
    return list(dict.fromkeys(cands))


def _xbox_games_dirs() -> list[Path]:
    """各盘符下存在的 XboxGames 根目录（Xbox app / PC Game Pass 默认安装位置）"""
    out = []
    for letter in XBOX_DRIVE_LETTERS:
        d = Path(f"{letter}:\\") / XBOX_GAMES_DIR_NAME
        if d.is_dir():
            out.append(d)
    return out


def _xbox_game_candidates() -> list[Path]:
    """Xbox app / PC Game Pass 常见安装位置的暗潮目录候选项。
    ⚠️ 实验功能：仅经单测覆盖（tools/test_crash_root.py），未在真机 Game Pass 环境实测。
    WindowsApps 下的 MSIX 安装包目录 ACL 受限不可枚举，不在此列（这类安装需手动指定游戏目录）。"""
    cands = []
    for root in _xbox_games_dirs():
        try:
            children = [d for d in root.iterdir() if d.is_dir()]
        except Exception:
            continue
        for d in children:
            if not any(h in d.name.lower() for h in XBOX_NAME_HINTS):
                continue
            cands.append(d / "Content")
            cands.append(d)
    return cands


def detect_game_dir() -> Path | None:
    """自动探测游戏目录（忽略 config）：Steam 库 → Xbox app / PC Game Pass 常见安装位置；找不到返回 None"""
    for c in _steam_game_candidates() + _xbox_game_candidates():
        if is_valid_game_dir(c):
            return c

    return None


def find_game_dir() -> Path | None:
    """优先级: config.json 覆盖 > 自动探测（Steam 库 → Xbox/Game Pass 常见安装位置）；找不到返回 None"""
    cfg = load_config()
    if cfg.get("game_dir"):
        p = Path(cfg["game_dir"])
        if p.exists():
            return p

    return detect_game_dir()


def game_dir_diagnosis() -> str:
    """自动识别诊断摘要（单行，留痕到 app.log 供用户回报问题）。

    覆盖三个来源并逐个标「存在 / 有效」：Steam 库候选、Xbox·Game Pass 候选、
    各盘符 XboxGames 根目录——Xbox / PC Game Pass 用户报「识别不到游戏目录」时，
    靠这一行就能判断是没装、盘符不在扫描列表、还是目录层级选错。"""
    def _mark(c: Path) -> str:
        return f"{c}（{'存在' if c.is_dir() else '缺失'}{'/有效' if is_valid_game_dir(c) else ''}）"

    parts = []
    for label, scan in (("Steam 库", _steam_game_candidates), ("Xbox·GamePass", _xbox_game_candidates)):
        try:
            cands = scan()
        except Exception as e:  # 扫描异常（权限 / 盘符）也要留痕，否则查不出原因
            parts.append(f"{label}=扫描异常 {e!r}")
            continue
        parts.append(f"{label}=" + ("；".join(_mark(c) for c in cands) if cands else "无候选"))
    try:
        xdirs = _xbox_games_dirs()
    except Exception as e:
        parts.append(f"XboxGames 根目录=枚举异常 {e!r}")
    else:
        parts.append("XboxGames 根目录=" + ("；".join(str(d) for d in xdirs) if xdirs
                                          else f"未发现（已查 {''.join(XBOX_DRIVE_LETTERS)} 盘）"))
    return " | ".join(parts)


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
