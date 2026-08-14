# -*- coding: utf-8 -*-
"""
暗潮 Mod 管理器 - 后端
只做壳：读/写 mods/mod_load_order.txt，调用 dtkit-patch，不管 mod 加载逻辑。
"""
import json
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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

app = FastAPI(title="Darktide Mod Manager")


class _JsApi:
    """pywebview js_api：供前端调用原生能力（如目录选择对话框）。"""
    def pick_folder(self):
        """弹出原生目录选择对话框，返回所选路径（取消返回 None）"""
        try:
            import webview
            win = webview.windows[0] if webview.windows else None
            if win is None:
                return None
            result = win.create_file_dialog(webview.FOLDER_DIALOG)
            if result:
                return str(result[0] if isinstance(result, (list, tuple)) else result)
            return None
        except Exception:
            return None

# 单实例锁（Windows 命名互斥体，比端口检测可靠）
_MUTEX_NAME = "Global\\DarktideModManager_Mutex"
_mutex_handle = None


def acquire_single_instance() -> bool:
    """返回 False 表示已有实例在运行"""
    global _mutex_handle
    import ctypes
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def find_free_port(start: int = 8317, tries: int = 50) -> int:
    """动态找空闲端口，避免与其他程序冲突"""
    import socket as _socket
    for port in range(start, start + tries):
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


# ---------------------------------------------------------------- 路径探测

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))  # utf-8-sig 防 BOM
        except Exception:
            pass
    return {}


def find_game_dir() -> Path:
    """优先级: config.json 覆盖 > Steam libraryfolders.vdf 探测 > 默认路径"""
    cfg = load_config()
    if cfg.get("game_dir"):
        p = Path(cfg["game_dir"])
        if p.exists():
            return p

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

    return Path(r"D:\SteamLibrary\steamapps\common") / GAME_FOLDER_NAME


def is_valid_game_dir(p: Path) -> bool:
    """游戏目录判定：mods 存在（已装 DMF）或 bundle 存在（原版新装）都算"""
    return p.is_dir() and ((p / "mods").is_dir() or (p / "bundle").is_dir())


GAME_DIR = find_game_dir()
MODS_DIR = GAME_DIR / "mods"
LOAD_ORDER_FILE = MODS_DIR / "mod_load_order.txt"


# ---------------------------------------------------------------- load_order 读写

def read_load_order() -> list:
    """解析 mod_load_order.txt 为行条目: {kind: mod|comment|blank, raw, name?}"""
    if not LOAD_ORDER_FILE.exists():
        return []
    try:
        text = LOAD_ORDER_FILE.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return []
    entries = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            entries.append({"kind": "blank", "raw": raw})
        elif s.startswith("--"):
            entries.append({"kind": "comment", "raw": raw})
        else:
            entries.append({"kind": "mod", "raw": raw, "name": s})
    return entries


def backup_load_order():
    if not LOAD_ORDER_FILE.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(LOAD_ORDER_FILE, BACKUP_DIR / f"mod_load_order.{ts}.bak")
    # 只留最近 10 份
    baks = sorted(BACKUP_DIR.glob("mod_load_order.*.bak"))
    for old in baks[:-10]:
        old.unlink(missing_ok=True)


def write_load_order(entries: list) -> None:
    if LOAD_ORDER_FILE is None or not MODS_DIR.is_dir():
        raise FileNotFoundError("游戏 mods 目录不存在，请先设置正确的游戏目录")
    backup_load_order()
    entries = normalize_entries(entries)
    text = "\n".join(e["raw"] for e in entries).rstrip("\n") + "\n"
    LOAD_ORDER_FILE.write_text(text, encoding="utf-8")


def is_exact_disable(raw: str) -> bool:
    """是否精确禁用行：--名字（无多余说明文字）"""
    s = raw.strip()
    return s.startswith("--") and len(s) > 2 and not any(c in s[2:] for c in " \t")


def normalize_entries(entries: list) -> list:
    """写入前去重：同名 mod 行优先，精确禁用行只留第一个；说明注释/空行原样保留"""
    has_mod = {}
    for e in entries:
        if e["kind"] == "mod":
            has_mod[e["name"]] = True
    seen = set()
    out = []
    for e in entries:
        if e["kind"] == "mod":
            if e["name"] not in seen:
                seen.add(e["name"])
                out.append(e)
        elif e["kind"] == "comment" and is_exact_disable(e["raw"]):
            name = e["raw"].strip()[2:].strip()
            if has_mod.get(name):
                continue  # 有启用行，禁用残留删掉
            if name not in seen:
                seen.add(name)
                out.append(e)
        else:
            out.append(e)
    return out

def enabled_names(entries: list) -> list:
    return [e["name"] for e in entries if e["kind"] == "mod"]


# ---------------------------------------------------------------- mod 扫描

NOTES_FILE = BASE_DIR / "notes.json"
_notes_cache: dict | None = None


def load_notes() -> dict:
    """读取 mod 备注表（exe 旁 notes.json）"""
    global _notes_cache
    if _notes_cache is None:
        try:
            _notes_cache = json.loads(NOTES_FILE.read_text(encoding="utf-8")) if NOTES_FILE.exists() else {}
        except Exception:
            _notes_cache = {}
    return _notes_cache


def save_notes(notes: dict):
    global _notes_cache
    _notes_cache = notes
    try:
        NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


_DISPLAY_CACHE = {}  # mod名 -> (localization mtime, 显示名)


def clean_display_name(s: str) -> str:
    """清理显示名：去富文本颜色标签 {#...}、私用区图标字符、字面反斜杠 xNN 字节转义（Lua 源码风格）"""
    s = re.sub(r'\{#[^}]*\}', '', s)
    s = re.sub(r'[\ue000-\uf8ff]', '', s)
    s = re.sub(r'\\x[0-9a-fA-F]{2}', '', s)
    return s.strip()


def read_display_name(d: Path) -> str:
    """从 mod 的 localization 文件读取显示名（优先 zh-cn，其次 en）；无则返回空串"""
    try:
        locs = [f for f in d.rglob("*localization*.lua") if f.is_file()]
    except Exception:
        locs = []
    if not locs:
        return ""
    try:
        mt = max(f.stat().st_mtime for f in locs)
    except Exception:
        mt = 0
    hit = _DISPLAY_CACHE.get(d.name)
    if hit and hit[0] == mt:
        return hit[1]
    name = ""
    for loc in locs:
        try:
            if loc.stat().st_size > 256 * 1024:
                continue
            text = loc.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for key in ("mod_name", "display_name"):
            m = re.search(key + r"\s*=\s*\{", text)
            if not m:
                continue
            seg = text[m.end():m.end() + 3000]
            mz = re.search(r'\["zh-cn"\]\s*=\s*"([^"]+)"', seg)
            if mz:
                name = mz.group(1).strip()
                break
            me = re.search(r'\ben\s*=\s*"([^"]+)"', seg)
            if me:
                name = me.group(1).strip()
                break
        if name:
            break
    name = clean_display_name(name)
    _DISPLAY_CACHE[d.name] = (mt, name)
    return name
def parse_mod_deps(mod_dir: Path) -> list:
    """解析 .mod 文件声明的库依赖（packages 字段）。
    支持格式：packages = { "lib1", "lib2" } 或 packages = { lib1 = true }。
    注意：packages 里的游戏资源路径（含 / 的 content/wwise 等）是资源声明不是库依赖，跳过。
    返回依赖名列表（小写规范化）。"""
    deps = []
    try:
        for f in mod_dir.glob("*.mod"):
            content = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'packages\s*=\s*\{([^}]*)\}', content, re.S)
            if not m:
                continue
            body = m.group(1)
            # 列表形式："lib1", "lib2" / 'lib1', 'lib2'
            for s in re.findall(r'"([^"]+)"', body):
                if s.strip():
                    deps.append(s.strip())
            for s in re.findall(r"'([^']+)'", body):
                if s.strip():
                    deps.append(s.strip())
            # 表形式：lib1 = true / lib1 = 1
            for s in re.findall(r'([a-zA-Z_][\w-]*)\s*=\s*(?:true|false|\d)', body):
                if s.strip():
                    deps.append(s.strip())
            break  # 只读第一个 .mod
    except Exception:
        pass
    # 过滤：跳过游戏资源路径（含 / 或 \ 的 content/wwise/units 等），去重保序
    seen, out = set(), []
    for d in deps:
        dl = d.lower().strip()
        if '/' in d or '\\' in d or dl.startswith(("content", "wwise", "units")):
            continue  # 游戏资源路径，不是库依赖
        if dl not in seen:
            seen.add(dl)
            out.append(dl)
    return out


def scan_mods() -> list:
    entries = read_load_order()
    enabled = enabled_names(entries)
    enabled_set = set(enabled)
    result = []
    seen = set()

    if MODS_DIR.is_dir():
        for d in sorted(MODS_DIR.iterdir()):
            if not d.is_dir() or d.name in SYSTEM_MODS:
                continue
            if ".bak_" in d.name:
                continue  # 导入备份残留目录，不当 mod 显示
            name = d.name
            seen.add(name)
            version = ""
            try:
                for f in d.glob("*.mod"):
                    m = re.search(r'version\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8", errors="ignore"))
                    if m:
                        version = m.group(1)
                        break
            except Exception:
                pass
            result.append({
                "name": name,
                "display_name": read_display_name(d),
                "note": load_notes().get(name, ""),
                "version": version,
                "enabled": name in enabled_set,
                "order": enabled.index(name) if name in enabled_set else None,
                "missing": False,
                "dependencies": parse_mod_deps(d),
            })

    # 清单里有但磁盘上找不到的（用户删了文件夹）
    for i, n in enumerate(enabled):
        if n not in seen:
            result.append({"name": n, "display_name": "", "version": "", "enabled": True, "order": i, "missing": True, "dependencies": []})

    result.sort(key=lambda x: (x["enabled"] is False, x["order"] if x["order"] is not None else 10**9))
    return result


# ---------------------------------------------------------------- API

@app.get("/api/status")
def api_status():
    valid = is_valid_game_dir(GAME_DIR)
    return {
        "game_dir": str(GAME_DIR),
        "game_dir_valid": valid,
        "mods_dir": str(MODS_DIR),
        "load_order_exists": LOAD_ORDER_FILE.exists() if LOAD_ORDER_FILE else False,
        "total": len(scan_mods()),
        "enabled": len(enabled_names(read_load_order())),
        "profiles_dir": str(PROFILES_DIR),
        "patch": patch_state(),
        "game_running": is_game_running(),
        "simulated_game_running": bool(load_config().get("simulate_game_running")),
        "dmf": dmf_state(),
    }


# ---------------------------------------------------------------- 补丁检测/一键打补丁

def patch_state() -> dict:
    """权威检测：bundle_database.data 是否被 dtkit-patch 注入补丁引用。
    注意：不能用 *.patch_999 文件存在性判断——卸载补丁后该文件仍在。
    警告：永远不要改名/删除 patch_999 或 mod_loader 文件——游戏启动时
    自动装载会重新打补丁，文件缺失会导致游戏 Fatal Error 崩溃。"""
    tool = GAME_DIR / "tools" / "dtkit-patch.exe"
    patched = False
    db = GAME_DIR / "bundle" / "bundle_database.data"
    try:
        if db.is_file():
            with open(db, "rb") as f:
                head = f.read(64 * 1024 * 1024)
            patched = b"patch_999" in head
    except Exception:
        patched = False
    return {
        "patched": patched,
        "tool_exists": tool.exists(),
        "tool_path": str(tool),
        "database_exists": db.is_file(),
    }


def is_game_running() -> bool:
    """真实检测：进程列表里有 Darktide.exe 即运行中。
    测试模式：simulate_game_running=True 时直接返回 True（用于模拟环境测试防呆，不用真开游戏）。"""
    if load_config().get("simulate_game_running"):
        return True
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        return "Darktide.exe" in out.decode("gbk", errors="ignore")
    except Exception:
        return False


class SimulateGameBody(BaseModel):
    running: bool


@app.post("/api/simulate_game")
def api_simulate_game(body: SimulateGameBody):
    """测试专用：模拟游戏运行/退出状态，便于在不开游戏的情况下验证防呆逻辑。
    真实游戏运行时不可覆盖为 False（避免误判）。"""
    real_running = is_game_running_real()
    if real_running and not body.running:
        return {"ok": False, "error": "检测到真实游戏正在运行，无法模拟为已退出"}
    cfg = load_config()
    cfg["simulate_game_running"] = body.running
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入配置失败: {e}"}
    return {"ok": True, "running": body.running, "simulated": True}


def is_game_running_real() -> bool:
    """只看真实进程，不看模拟开关"""
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        return "Darktide.exe" in out.decode("gbk", errors="ignore")
    except Exception:
        return False


CREATE_NO_WINDOW = 0x08000000


# 自动装载插件：游戏启动时引擎加载它，它会检测并自动重新打补丁
AUTOPATCH_DLL = Path("binaries") / "plugins" / "_dt_mod_autopatch.dll"


def autopatch_path() -> Path:
    return GAME_DIR / AUTOPATCH_DLL


def autopatch_off_path() -> Path:
    return GAME_DIR / "binaries" / "plugins" / "_dt_mod_autopatch.dll.off"


def auto_patch_disabled() -> bool:
    """用户手动卸载过（禁用自动装载）"""
    return load_config().get("auto_patch_disabled", False)


def set_auto_patch_disabled(v: bool):
    cfg = load_config()
    cfg["auto_patch_disabled"] = v
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def auto_patch_if_needed() -> dict:
    """管理器版自动装载：补丁未打 + 未手动禁用 + 游戏未运行 -> 自动打补丁"""
    st = patch_state()
    if st["patched"]:
        return {"ok": True, "message": "补丁已激活"}
    if auto_patch_disabled():
        return {"ok": True, "message": "自动装载已禁用（手动卸载状态）"}
    if is_game_running():
        return {"ok": True, "message": "游戏运行中，跳过自动打补丁"}
    r = _run_patch("--patch")
    r["message"] = "✓ 自动装载：补丁已重新打上" if r.get("patched") else "✗ 自动打补丁失败"
    return r


def guard_game_running(action: str = "此操作") -> dict | None:
    """防呆：游戏运行时拒绝会改动 mods/启停清单的操作。返回 None=放行，否则返回拒绝响应。"""
    if is_game_running():
        return {"ok": False, "error": f"游戏正在运行，{action}需先关闭游戏"}
    return None


@app.post("/api/patch/auto")
def api_patch_auto():
    return auto_patch_if_needed()


def _run_patch(action: str) -> dict:
    """执行 dtkit-patch（--patch / --unpatch）"""
    st = patch_state()
    if not st["tool_exists"]:
        return {"ok": False, "error": "未找到 tools\\dtkit-patch.exe，无法操作补丁", **st}
    if is_game_running():
        return {"ok": False, "error": "游戏正在运行，请先关闭游戏再操作补丁", **st}
    try:
        r = subprocess.run(
            [str(st["tool_path"]), action, str(GAME_DIR / "bundle")],
            cwd=str(GAME_DIR), capture_output=True, text=True, timeout=120,
            creationflags=CREATE_NO_WINDOW)
        new_st = patch_state()
        return {"ok": r.returncode == 0, "returncode": r.returncode,
                "output": (r.stdout or r.stderr or "")[-600:], **new_st}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/patch/install")
def api_patch_install():
    """安装补丁：恢复自动装载插件 + 清除禁用标记 + 打补丁"""
    off = autopatch_off_path()
    if off.exists():
        try:
            off.rename(autopatch_path())
        except Exception:
            pass
    set_auto_patch_disabled(False)
    st = patch_state()
    if st["patched"]:
        return {"ok": True, "message": "补丁已激活，无需重复安装", **st}
    r = _run_patch("--patch")
    r["message"] = "✓ 补丁已安装，mods 已激活" if r.get("patched") else "✗ 补丁安装失败"
    return r


@app.post("/api/patch/uninstall")
def api_patch_uninstall():
    """卸载补丁：还原数据库 + 禁用自动装载插件（autopatch.dll 改名），
    游戏启动时不会自动重打补丁，mods 真正禁用且不崩溃。
    注意：绝不动 patch_999/mod_loader 文件。"""
    st = patch_state()
    if not st["patched"] and not autopatch_off_path().exists():
        return {"ok": True, "message": "补丁未激活，无需卸载", **st}
    msgs = []
    # 1. 禁用自动装载插件
    ap = autopatch_path()
    if ap.exists():
        try:
            ap.rename(autopatch_off_path())
            msgs.append("已禁用自动装载")
        except Exception as e:
            msgs.append(f"禁用自动装载失败: {e}")
    # 2. 记录禁用标记（管理器也不再自动打）
    set_auto_patch_disabled(True)
    # 2. 还原数据库
    if st["patched"]:
        r = _run_patch("--unpatch")
        if not r.get("patched"):
            msgs.append("补丁已卸载")
        else:
            msgs.append("补丁卸载失败")
    msg = "✓ " + "，".join(msgs) + "（启动游戏不会自动恢复，mods 保持禁用）" if msgs else "✓ 补丁未激活"
    new_st = patch_state()
    return {"ok": True, "message": msg, **new_st}


# ---------------------------------------------------------------- 启动游戏（绕过启动器）

GAME_LAUNCH_ARGS = [
    "--bundle-dir", "../bundle", "--ini", "settings",
    "--backend-auth-service-url", "https://bsp-auth-prod.atoma.cloud",
    "--backend-title-service-url", "https://bsp-td-prod.atoma.cloud",
    "--lua-heap-mb-size", "2048",
]


@app.post("/api/game/launch")
def api_launch_game():
    if not is_valid_game_dir(GAME_DIR):
        return {"ok": False, "error": "未设置正确的游戏目录"}
    if is_game_running():
        return {"ok": False, "error": "游戏已在运行"}
    # 自动装载：启动游戏前补打补丁（若用户未手动禁用）
    auto_patch_if_needed()
    exe = GAME_DIR / "binaries" / "Darktide.exe"
    if not exe.exists():
        exe = GAME_DIR / "content" / "binaries" / "Darktide.exe"
    if not exe.exists():
        return {"ok": False, "error": "未找到 Darktide.exe，请检查游戏文件完整性"}
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=CREATE_NO_WINDOW).stdout
        if "steam.exe" not in out.lower():
            return {"ok": False, "error": "未检测到 Steam 客户端，请先启动 Steam 并登录"}
    except Exception:
        pass
    env = os.environ.copy()
    env["SteamAppId"] = APP_ID
    try:
        subprocess.Popen([str(exe)] + GAME_LAUNCH_ARGS, cwd=str(exe.parent),
                         env=env, creationflags=CREATE_NO_WINDOW)
        return {"ok": True, "message": "游戏启动中，请稍候…"}
    except Exception as e:
        return {"ok": False, "error": f"启动失败: {e}"}


# ---------------------------------------------------------------- mod 导入

def find_rar_tool() -> str | None:
    """找系统里能解 rar 的工具：WinRAR / 7-Zip"""
    try:
        import winreg
        for key in (r"SOFTWARE\WinRAR", r"SOFTWARE\WOW6432Node\WinRAR"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                    for val in ("exe64", "exe"):
                        try:
                            exe = winreg.QueryValueEx(k, val)[0]
                            if exe and os.path.isfile(exe):
                                return exe
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception:
        pass
    for p in (r"C:\Program Files\WinRAR\UnRAR.exe", r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
              r"C:\Program Files\WinRAR\WinRAR.exe", r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
              r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if os.path.isfile(p):
            return p
    return None


def extract_archive(data: bytes, filename: str, out_dir: Path) -> str | None:
    """按格式解压到 out_dir；返回 None 成功，否则错误信息"""
    import tarfile
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    fd, tmp_path = tempfile.mkstemp(suffix="." + (ext or "bin"))
    os.close(fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)

        if ext == "zip":
            try:
                with zipfile.ZipFile(tmp_path) as z:
                    for i in z.infolist():
                        if ".." in i.filename.replace("\\", "/").split("/"):
                            return "压缩包包含非法路径，已拒绝"
                    z.extractall(out_dir)
            except zipfile.BadZipFile:
                return "不是有效的 zip 文件（文件损坏或格式不对）"
        elif ext in ("tar", "gz", "tgz", "bz2", "xz"):
            with tarfile.open(tmp_path) as t:
                for m in t.getmembers():
                    if ".." in m.name.replace("\\", "/").split("/"):
                        return "压缩包包含非法路径，已拒绝"
                t.extractall(out_dir, filter="data")
        elif ext == "7z":
            import py7zr
            with py7zr.SevenZipFile(tmp_path) as z:
                z.extractall(out_dir)
        elif ext == "rar":
            tool = find_rar_tool()
            if not tool:
                return "解压 rar 需要系统安装 WinRAR 或 7-Zip（未检测到）。可安装 WinRAR 后用本工具导入，或用 7-Zip 把 rar 转为 zip"
            tool_l = tool.lower()
            if tool_l.endswith("7z.exe"):
                r = subprocess.run([tool, "x", "-y", "-o" + str(out_dir), tmp_path],
                                   capture_output=True, text=True, timeout=180,
                                   creationflags=CREATE_NO_WINDOW)
            else:  # UnRAR.exe / WinRAR.exe
                r = subprocess.run([tool, "x", "-y", "-o+", tmp_path, str(out_dir) + "\\"],
                                   capture_output=True, text=True, timeout=180,
                                   creationflags=CREATE_NO_WINDOW)
            if r.returncode != 0:
                return f"rar 解压失败: {(r.stdout or r.stderr or '')[-200:]}"
        else:
            # 未知扩展名：先试 zip，再试 7z
            try:
                with zipfile.ZipFile(tmp_path) as z:
                    for i in z.infolist():
                        if ".." in i.filename.replace("\\", "/").split("/"):
                            return "压缩包包含非法路径，已拒绝"
                    z.extractall(out_dir)
            except zipfile.BadZipFile:
                try:
                    import py7zr
                    with py7zr.SevenZipFile(tmp_path) as z:
                        z.extractall(out_dir)
                except Exception:
                    return f"不支持的压缩格式: {ext or '未知'}"
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def import_mod_archive(filename: str, data: bytes, force_mod: bool = False) -> dict:
    if not MODS_DIR.is_dir():
        return {"file": filename, "ok": False, "error": "mods 目录不存在，请先设置游戏目录"}
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        out.mkdir()
        err = extract_archive(data, filename, out)
        if err:
            return {"file": filename, "ok": False, "error": err}
        return import_mod_from_dir(out, filename, force_mod=force_mod)


def import_mod_from_dir(out: Path, filename: str, force_mod: bool = False) -> dict:
    """从已解压目录导入 mod（压缩包解压后 / 用户选择的文件夹共用）。"""
    if not MODS_DIR.is_dir():
        return {"file": filename, "ok": False, "error": "mods 目录不存在，请先设置游戏目录"}
    # 整合包结构（mods/ 或 binaries/mod_loader 等）→ 提示走整合包导入（前端会自动转）
    # force_mod=True 时跳过分类，强制按单个 mod 处理（用户确认过）
    if not force_mod:
        kind = classify_archive(out)
        if kind == "pack":
            return {"file": filename, "ok": False, "is_pack": True,
                    "error": "检测到整合包结构，请用「导入整合包」流程"}
        if kind == "ambiguous":
            # 模棱两可：mods/ 下只有一个 mod 且无清单，可能是单 mod 包裹或精简整合包
            return {"file": filename, "ok": False, "ambiguous": True,
                    "error": "检测到 mods/ 目录结构，无法确定是单个 mod 还是整合包"}
        mod_files = list(out.rglob("*.mod"))
        if not mod_files:
            return {"file": filename, "ok": False,
                    "error": "所选内容内没有 .mod 文件，不是 DMF mod 包（整个整合包请用「导入整合包」）"}
    else:
        mod_files = list(out.rglob("*.mod"))
        if not mod_files:
            return {"file": filename, "ok": False,
                    "error": "所选内容内没有 .mod 文件，不是 DMF mod 包"}
    first = mod_files[0]

    # 从 .mod 内容提取真实 mod 名
    try:
        content = first.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        content = ""
    real_name = ""
    m = re.search(r'new_mod\(\s*"([^"]+)"', content)
    if m:
        real_name = m.group(1).strip()
    if not real_name:
        m2 = re.search(r'mod_script\s*=\s*"([^"]+)"', content)
        if m2:
            seg = m2.group(1).replace("\\", "/").split("/")
            if len(seg) >= 3:
                real_name = seg[-2] or seg[-1]
    if not real_name:
        parts = str(first.relative_to(out)).replace("\\", "/").split("/")
        real_name = parts[-2] if len(parts) >= 2 else first.stem
    real_name = re.sub(r'[\\/:*?"<>|]', "_", real_name).strip()
    if not real_name:
        return {"file": filename, "ok": False, "error": "无法确定 mod 名称"}

    target = MODS_DIR / real_name
    if target.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = target.with_name(f"{real_name}.bak_{ts}")
        i = 2
        while bak.exists():
            bak = target.with_name(f"{real_name}.bak_{ts}_{i}")
            i += 1
        target.rename(bak)
    target.mkdir(parents=True, exist_ok=True)

    # 拷贝 .mod 所在目录的内容；根目录的散文件也一并拷贝
    src_root = first.parent
    for item in src_root.iterdir():
        if item.is_dir():
            shutil.copytree(item, target / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target / item.name)
    if src_root != out:
        for item in out.iterdir():
            if item.is_file():
                shutil.copy2(item, target / item.name)

    # 加入启用清单（末尾）
    entries = read_load_order()
    names_in_file = {e["name"] for e in entries if e["kind"] == "mod"}
    added = real_name not in names_in_file
    if added:
        entries.append({"kind": "mod", "raw": real_name, "name": real_name})
        write_load_order(entries)
    return {"file": filename, "ok": True, "mod": real_name, "added_to_load_order": added}


@app.post("/api/mods/import")
async def api_import_mods(files: list[UploadFile] = File(...), force_mod: bool = Form(False)):
    if not is_valid_game_dir(GAME_DIR):
        return {"ok": False, "results": [], "error": "未设置正确的游戏目录"}
    g = guard_game_running("导入 mod")
    if g:
        return {"ok": False, "results": [], **g}
    results = []
    for f in files:
        try:
            data = await f.read()
        except Exception as e:
            results.append({"file": f.filename, "ok": False, "error": f"读取失败: {e}"})
            continue
        results.append(import_mod_archive(f.filename or "mod.zip", data, force_mod=force_mod))
    return {"ok": True, "results": results}


class ImportFolderBody(BaseModel):
    path: str
    force_mod: bool = False


@app.post("/api/mods/import_folder")
def api_import_folder(body: ImportFolderBody):
    """导入文件夹形式的 mod：直接把文件夹当已解压的包处理（走与压缩包相同的识别/拷贝逻辑）。"""
    g = guard_game_running("导入 mod")
    if g:
        return g
    p = Path(body.path)
    if not p.is_dir():
        return {"ok": False, "error": "文件夹不存在或不是目录"}
    # 若选中的是 mod 文件夹本身（含 .mod），或它的父级是 mods 目录，做归一化：
    # 用户可能选中：ModA/（mod 根）、mods/ModA/、或 mods/（含多个 mod）
    r = import_mod_from_dir(p, p.name, force_mod=bool(body.force_mod))
    return r


# ---------------------------------------------------------------- DMF 一键安装

# 内置 DMF 组件：关键文件清单（用于检测"是否装齐"；释放按 payload 子树全量拷贝）
DMF_FILES = [
    "mods/base/mod_manager.lua",
    "mods/base/function/class.lua",
    "mods/base/function/hook.lua",
    "mods/base/function/require.lua",
    "mods/dmf/dmf.mod",
    "mods/dmf/localization/dmf.lua",
    "mods/dmf/scripts/mods/dmf/dmf_loader.lua",
    "tools/dtkit-patch.exe",
    "binaries/plugins/_dt_mod_autopatch.dll",
]
# 释放时只拷这些子树（保持相对游戏目录结构；payload 根文件如 VERSION.txt 不释放）
DMF_SUBTREES = ["mods", "tools", "binaries"]
DMF_PAYLOAD_DIR = RESOURCE_DIR / "dmf_payload"
AUTOPATCH_DLL_OFF = Path("binaries") / "plugins" / "_dt_mod_autopatch.dll.off"


def dmf_payload_files() -> list:
    """payload 内待释放文件（相对游戏目录路径）"""
    files = []
    for sub in DMF_SUBTREES:
        base = DMF_PAYLOAD_DIR / sub
        if base.is_dir():
            for f in base.rglob("*"):
                if f.is_file():
                    files.append(f.relative_to(DMF_PAYLOAD_DIR))
    return files


def dmf_payload_version() -> str:
    """内置 DMF 组件版本说明（VERSION.txt 首行，仅供展示）"""
    try:
        v = (DMF_PAYLOAD_DIR / "VERSION.txt").read_text(encoding="utf-8", errors="ignore")
        return v.strip().splitlines()[0] if v.strip() else ""
    except Exception:
        return ""


def dmf_state() -> dict:
    """检测游戏目录 DMF 组件齐全度（自动装载插件被主动禁用 .off 不算缺失）"""
    valid = is_valid_game_dir(GAME_DIR)
    missing = []
    if valid:
        off_exists = (GAME_DIR / AUTOPATCH_DLL_OFF).exists()
        for rel in DMF_FILES:
            if not (GAME_DIR / rel).is_file():
                # 卸载补丁会把自动装载插件改名 .off 禁用——那是用户主动操作，不是缺失
                if rel == "binaries/plugins/_dt_mod_autopatch.dll" and off_exists:
                    continue
                missing.append(rel)
    return {
        "game_dir_valid": valid,
        "installed": valid and not missing,
        "missing": missing,
        "autopatch_off": (GAME_DIR / AUTOPATCH_DLL_OFF).exists() if valid else False,
        "payload_version": dmf_payload_version(),
    }


class DmfInstallBody(BaseModel):
    force: bool = False


@app.post("/api/dmf/install")
def api_dmf_install(body: DmfInstallBody = Body(default=None)):
    """一键安装/覆盖更新 DMF：释放内置组件（已有文件先备份）→ 恢复自动装载 → 打补丁激活 mods。
    force=True 时即使已装完整也强制用内置组件覆盖（用于更新/去除旧版私货）。"""
    if not GAME_DIR.is_dir():
        return {"ok": False, "error": "未设置正确的游戏目录，请先到「关于」页设置"}
    if not is_valid_game_dir(GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先到「关于」页设置正确的游戏目录"}
    if not DMF_PAYLOAD_DIR.is_dir():
        return {"ok": False, "error": "内置 DMF 组件缺失（打包不完整），请重新下载管理器"}
    if is_game_running():
        return {"ok": False, "error": "游戏正在运行，请先关闭游戏再安装 DMF"}

    # 兼容：FastAPI 路由调用（body=None 或缺省）与测试直接调用（无参）
    force = False
    if body is not None:
        try:
            force = bool(body.force)
        except AttributeError:
            force = False
    # 1. 释放组件；已有同名文件先备份到 backups\dmf_backup_<时间戳>\
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_root = BACKUP_DIR / f"dmf_backup_{ts}"
    files = dmf_payload_files()
    if not files:
        return {"ok": False, "error": "内置 DMF 组件缺失（打包不完整），请重新下载管理器"}
    installed, backed = [], []
    for rel in files:
        src = DMF_PAYLOAD_DIR / rel
        dst = GAME_DIR / rel
        try:
            if dst.exists():
                b = bak_root / rel
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, b)
                backed.append(str(rel))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            installed.append(str(rel))
        except Exception as e:
            return {"ok": False, "error": f"释放 {rel} 失败: {e}"}

    # 2. 恢复自动装载插件（清除 .off 残留 + 管理器禁用标记）
    off = GAME_DIR / AUTOPATCH_DLL_OFF
    if off.exists():
        try:
            off.unlink()
        except Exception:
            pass
    set_auto_patch_disabled(False)

    # 3. 打补丁激活 mods
    act = "覆盖更新" if force else "安装"
    msg = f"✓ DMF {act}完成（{len(installed)} 个组件）"
    if installed:
        r = _run_patch("--patch")
        if r.get("patched"):
            msg += "，补丁已激活，mods 已就绪"
        else:
            msg += f"，但补丁未打上：{r.get('error') or (r.get('output') or '未知原因')[-200:]}"
    pruned = prune_backups()
    if pruned:
        msg += f"（已清理 {len(pruned)} 个旧备份）"
    return {"ok": True, "message": msg, "components_installed": installed, "backed_up": backed, **dmf_state()}


class GameDirBody(BaseModel):
    path: str


# ---------------------------------------------------------------- 整合包导入

PACK_BAK_PREFIX = "pack_import_"


def is_pack_root(p: Path) -> bool:
    """判断目录是否是整合包根（mods/ 或 binaries/mod_loader 或 bundle/*.patch_999）"""
    if (p / "mods").is_dir():
        return True
    if (p / "binaries" / "mod_loader").is_file():
        return True
    b = p / "bundle"
    if b.is_dir() and list(b.glob("*.patch_999")):
        return True
    return False


def locate_pack_root(out: Path) -> Path:
    """整合包解压根：若只套了一层目录且其下是游戏结构，则进入该层"""
    subs = [d for d in out.iterdir() if d.is_dir()]
    files = [f for f in out.iterdir() if f.is_file()]
    if not files and len(subs) == 1 and is_pack_root(subs[0]):
        return subs[0]
    return out


def classify_archive(out: Path) -> str:
    """分类压缩包内容：'mod'（单个 mod）| 'pack'（整合包）| 'ambiguous'（模棱两可，需用户确认）
    整合包判定：mods/ 带系统组件/加载器/清单，或多于 1 个 mod 文件夹。
    只有一个 mod 文件夹且无清单 → ambiguous（可能是单 mod 的 mods/ 包裹，也可能是精简整合包）。"""
    root = locate_pack_root(out)
    if not is_pack_root(root):
        return "mod"
    mods_dir = root / "mods"
    if mods_dir.is_dir():
        mod_folders = [d for d in mods_dir.iterdir() if d.is_dir()]
        # 带系统组件或加载器文件 → 肯定是整合包
        if (mods_dir / "base").is_dir() or (mods_dir / "dmf").is_dir():
            return "pack"
        if (root / "binaries" / "mod_loader").is_file():
            return "pack"
        if (root / "bundle").is_dir() and list((root / "bundle").glob("*.patch_999")):
            return "pack"
        # 只有 1 个 mod 文件夹：带启停清单 → 整合包；否则模棱两可（防呆：让用户确认）
        if len(mod_folders) <= 1:
            if (mods_dir / "mod_load_order.txt").is_file():
                return "pack"
            return "ambiguous"
    return "pack"


def is_pack_like(out: Path) -> bool:
    """宽松判定：像整合包（用于 mod 导入时自动转整合包流程）。
    排除"mods/ 下只有一个 mod"的单 mod 包裹结构，避免误判。"""
    return classify_archive(out) == "pack"


def _bak_path(dst: Path, ts: str) -> Path:
    """生成不冲突的备份路径"""
    bak = dst.with_name(f"{dst.name}.bak_{ts}")
    i = 2
    while bak.exists():
        bak = dst.with_name(f"{dst.name}.bak_{ts}_{i}")
        i += 1
    return bak


def _scan_mods_dir(mods_root: Path) -> dict:
    """扫描一个 mods 目录：{mod名: 版本}（排除系统组件/备份残留）"""
    result = {}
    if not mods_root.is_dir():
        return result
    for d in sorted(mods_root.iterdir()):
        if not d.is_dir() or d.name in SYSTEM_MODS or ".bak_" in d.name:
            continue
        ver = ""
        for f in d.glob("*.mod"):
            m = re.search(r'version\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8", errors="ignore"))
            if m:
                ver = m.group(1)
                break
        result[d.name] = ver
    return result


def diff_mods(pack_mods: dict, cur_mods: dict) -> dict:
    """对比两套 mods：新增/移除/更新/相同"""
    added = [n for n in pack_mods if n not in cur_mods]
    removed = [n for n in cur_mods if n not in pack_mods]
    updated = [n for n in pack_mods if n in cur_mods and pack_mods[n] and pack_mods[n] != cur_mods[n]]
    same = [n for n in pack_mods if n in cur_mods and n not in updated]
    return {"added": added, "removed": removed, "updated": updated, "same": same}


def preview_pack_archive(filename: str, data: bytes) -> dict:
    """只读预览整合包：解压后对比当前 mods，返回新增/移除/更新/相同（不写任何文件）。"""
    if not MODS_DIR.is_dir():
        return {"file": filename, "ok": False, "error": "mods 目录不存在，请先设置游戏目录"}
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        out.mkdir()
        err = extract_archive(data, filename, out)
        if err:
            return {"file": filename, "ok": False, "error": err}
        root = locate_pack_root(out)
        if not is_pack_like(out):
            return {"file": filename, "ok": False,
                    "error": "压缩包内没有 mods/ 或加载器文件，不是暗潮整合包（单个 mod 请用「导入 mod」）"}

        src_mods = root / "mods"
        pack_mods = _scan_mods_dir(src_mods) if src_mods.is_dir() else {}

        # 当前 mods
        cur_mods = _scan_mods_dir(MODS_DIR)

        diff = diff_mods(pack_mods, cur_mods)
        added, removed, updated, same = diff["added"], diff["removed"], diff["updated"], diff["same"]

        # 包内清单信息
        has_load_order = (src_mods / "mod_load_order.txt").is_file()
        pack_lo_count = 0
        if has_load_order:
            try:
                pack_lo_count = sum(
                    1 for ln in (src_mods / "mod_load_order.txt").read_text(encoding="utf-8", errors="ignore").splitlines()
                    if ln.strip() and not ln.strip().startswith("--"))
            except Exception:
                pass

        return {
            "file": filename,
            "ok": True,
            "is_pack": True,
            "added": added,
            "removed": removed,
            "updated": updated,
            "same": same,
            "pack_count": len(pack_mods),
            "cur_count": len(cur_mods),
            "has_load_order": has_load_order,
            "pack_lo_count": pack_lo_count,
        }


class PackPreviewBody(BaseModel):
    filename: str = ""
    data_b64: str = ""  # 压缩包 base64（前端读取后传入）


@app.post("/api/pack/preview")
def api_pack_preview(body: PackPreviewBody):
    """导入整合包前的差异预览（只读，不写文件）"""
    g = guard_game_running("预览整合包")
    if g:
        return g
    if not body.data_b64:
        return {"ok": False, "error": "缺少文件数据"}
    import base64
    try:
        data = base64.b64decode(body.data_b64)
    except Exception as e:
        return {"ok": False, "error": f"解码失败: {e}"}
    return preview_pack_archive(body.filename or "pack.zip", data)


def import_pack_archive(filename: str, data: bytes, mode: str = "replace") -> dict:
    """导入整合包：解压 -> 定位根 -> 备份 -> 合并（replace 先归档旧 mods）-> 返回统计
    mode=replace：旧 mods 整体归档到 backups/pack_backup_<ts>/mods/，mods 始终保持当前包
    mode=merge：增量叠加（同名覆盖备份）"""
    if not is_valid_game_dir(GAME_DIR):
        return {"file": filename, "ok": False, "error": "游戏目录无效，请先到「关于」页设置"}
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        out.mkdir()
        err = extract_archive(data, filename, out)
        if err:
            return {"file": filename, "ok": False, "error": err}
        root = locate_pack_root(out)
        if not is_pack_like(out):
            return {"file": filename, "ok": False,
                    "error": "压缩包内没有 mods/ 或加载器文件，不是暗潮整合包（单个 mod 请用「导入 mod」）"}

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        added, replaced, root_files = [], [], []
        archived = []
        MODS_DIR.mkdir(parents=True, exist_ok=True)

        # 0. replace 模式：先把现有 mods 整体归档；base/dmf 仅当新包也带同名时才归档
        #    （新包没带则保留旧的，保证框架不缺失）；归档备份统一进 BACKUP_DIR
        if mode == "replace":
            src_mods0 = root / "mods"
            pack_has = {d.name for d in src_mods0.iterdir() if d.is_dir()} if src_mods0.is_dir() else set()
            bak_mods = BACKUP_DIR / f"pack_backup_{ts}" / "mods"
            bak_mods.mkdir(parents=True, exist_ok=True)
            for item in sorted(MODS_DIR.iterdir()):
                if item.is_dir() and item.name in SYSTEM_MODS:
                    if item.name not in pack_has:
                        continue  # 新包没有该系统组件，保留旧的
                try:
                    shutil.move(str(item), str(bak_mods / item.name))
                    archived.append(item.name)
                except Exception as e:
                    return {"file": filename, "ok": False, "error": f"归档 {item.name} 失败: {e}"}

        # 1. mods/ 增量合并（跳过 mod_load_order.txt，后面单独处理）
        src_mods = root / "mods"
        for d in sorted(src_mods.iterdir()) if src_mods.is_dir() else []:
            if not d.is_dir():
                continue
            if d.name.lower() == "mod_load_order.txt":
                continue
            target = MODS_DIR / d.name
            if target.exists():
                target.rename(_bak_path(target, ts))
                replaced.append(d.name)
            try:
                shutil.copytree(d, target)
            except Exception as e:
                return {"file": filename, "ok": False, "error": f"拷贝 mod {d.name} 失败: {e}"}
            added.append(d.name)

        # 2. mods/mod_load_order.txt：用整合包作者的推荐清单（先备份现有）
        lo_src = src_mods / "mod_load_order.txt"
        if lo_src.is_file():
            lo_dst = MODS_DIR / "mod_load_order.txt"
            if lo_dst.exists():
                b = BACKUP_DIR / f"pack_backup_{ts}" / "mods" / lo_dst.name
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(lo_dst), str(b))
            shutil.copy2(lo_src, lo_dst)

        # 3. 加载器相关文件：tools/ 散文件、binaries/mod_loader、bundle/*.patch_999
        #    冲突备份统一进 BACKUP_DIR（不在游戏目录留 .bak_ 文件）
        comp_files = []
        tools_src = root / "tools"
        if tools_src.is_dir():
            for f in tools_src.iterdir():
                if f.is_file():
                    comp_files.append((f, GAME_DIR / "tools" / f.name))
        for rel in ("binaries/mod_loader",):
            s = root / rel
            if s.is_file():
                comp_files.append((s, GAME_DIR / rel))
        b_src = root / "bundle"
        if b_src.is_dir():
            for f in b_src.glob("*.patch_999"):
                comp_files.append((f, GAME_DIR / "bundle" / f.name))
        comp_bak = BACKUP_DIR / f"pack_backup_{ts}" / "loader"
        for src, dst in comp_files:
            if dst.exists():
                b = comp_bak / src.name
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(b))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            root_files.append(dst.name)

        # 4. 根目录散文件（.bat/.txt/.md 教程/脚本）不再导入——避免反复装包堆积重复文件；
        #    replace 模式下顺带把根目录已有的散文件归档（排除 mod_load_order.txt 参考副本和 steam_appid.txt）
        archived_root = []
        if mode == "replace":
            root_bak = BACKUP_DIR / f"root_cleanup_{ts}"
            for f in GAME_DIR.iterdir():
                if not f.is_file() or f.suffix.lower() not in (".bat", ".txt", ".md"):
                    continue
                if f.name.lower() in ("mod_load_order.txt", "steam_appid.txt"):
                    continue
                try:
                    b = root_bak / f.name
                    b.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(b))
                    archived_root.append(f.name)
                except Exception as e:
                    return {"file": filename, "ok": False, "error": f"归档根目录文件 {f.name} 失败: {e}"}

        # 5. 打补丁激活 mods（游戏关闭时）
        msg = f"✓ 整合包导入完成：新增/更新 {len(added)} 个 mod"
        if mode == "replace":
            msg = f"✓ 整合包已生效：{len(added)} 个 mod 就绪"
            if archived:
                msg += f"（原 {len(archived)} 个旧 mod 已归档到 backups/pack_backup_{ts}/，可随时找回）"
            if archived_root:
                msg += f"，根目录 {len(archived_root)} 个说明/脚本文件已归档（backups/root_cleanup_{ts}/）"
        else:
            if replaced:
                msg += f"（覆盖 {len(replaced)} 个，旧版已备份）"
        if root_files:
            msg += f"，加载器/工具文件 {len(root_files)} 个"
        if is_game_running():
            msg += "；游戏运行中，退出后会自动补打补丁"
        else:
            r = _run_patch("--patch")
            if r.get("patched"):
                msg += "，补丁已激活，mods 已就绪"
            else:
                msg += f"，但补丁未打上：{r.get('error') or (r.get('output') or '未知原因')[-200:]}"
        pruned = prune_backups()
        if pruned:
            msg += f"（已清理 {len(pruned)} 个旧备份）"
        return {"file": filename, "ok": True, "message": msg,
                "mods": added, "replaced": replaced, "archived": archived,
                "root_files": root_files, "load_order": lo_src.is_file(), "mode": mode}


@app.post("/api/pack/import")
async def api_pack_import(files: list[UploadFile] = File(...),
                          mode: str = Form("replace")):
    """整合包导入：mode=replace（默认，整体替换）| merge（叠加）"""
    if mode not in ("replace", "merge"):
        mode = "replace"
    if not is_valid_game_dir(GAME_DIR):
        return {"ok": False, "results": [], "error": "未设置正确的游戏目录"}
    g = guard_game_running("导入整合包")
    if g:
        return {"ok": False, "results": [], **g}
    results = []
    for f in files:
        try:
            data = await f.read()
        except Exception as e:
            results.append({"file": f.filename, "ok": False, "error": f"读取失败: {e}"})
            continue
        results.append(import_pack_archive(f.filename or "pack.zip", data, mode))
    return {"ok": True, "results": results}


# ---------------------------------------------------------------- 归档备份管理

def _fmt_ts(ts: str) -> str:
    """时间戳 20260814_235000 → 2026-08-14 23:50（解析失败原样返回）"""
    try:
        return datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


@app.post("/api/backups/{bid}/preview")
def api_backup_preview(bid: str):
    """备份恢复前的差异预览（只读）：备份内 mods vs 当前 mods"""
    if not is_valid_game_dir(GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先到「关于」页设置"}
    g = guard_game_running("预览备份")
    if g:
        return g
    src = BACKUP_DIR / bid / "mods"
    if not src.is_dir():
        return {"ok": False, "error": "备份不存在或不是整合包归档"}
    bak_mods = _scan_mods_dir(src)
    cur_mods = _scan_mods_dir(MODS_DIR)
    diff = diff_mods(bak_mods, cur_mods)
    return {
        "ok": True,
        "added": diff["added"],
        "removed": diff["removed"],
        "updated": diff["updated"],
        "same": diff["same"],
        "bak_count": len(bak_mods),
        "cur_count": len(cur_mods),
    }


# 备份保留策略：单类最多保留份数 / backups 总大小上限（字节）
BACKUP_MAX_PER_TYPE = 10
BACKUP_MAX_TOTAL_BYTES = 5 * 1024 * 1024 * 1024  # 5GB


def prune_backups():
    """备份清理：
    1. 单类上限：pack_backup_/dmf_backup_ 各保留最近 BACKUP_MAX_PER_TYPE 份；
    2. 总量上限：backups 总大小超 BACKUP_MAX_TOTAL_BYTES 时从最旧开始删，直到达标。
    返回删除的条目列表。"""
    if not BACKUP_DIR.is_dir():
        return []
    removed = []

    # 1. 单类数量上限（pack / dmf 目录类）
    for prefix in ("pack_backup_", "dmf_backup_"):
        dirs = sorted((d for d in BACKUP_DIR.iterdir() if d.is_dir() and d.name.startswith(prefix)),
                      key=lambda d: d.name)
        for old in dirs[:-BACKUP_MAX_PER_TYPE]:
            try:
                shutil.rmtree(old, ignore_errors=True)
                removed.append(old.name)
            except Exception:
                pass

    # 2. 总量上限（含清单散文件）
    def _dir_size(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

    # 收集所有备份条目（目录 + 清单散文件），按名称排序（旧在前）
    entries = []
    for d in BACKUP_DIR.iterdir():
        if d.is_dir() and (d.name.startswith("pack_backup_") or d.name.startswith("dmf_backup_")):
            entries.append((d.name, _dir_size(d)))
        elif d.is_file() and d.name.startswith("mod_load_order.") and d.name.endswith(".bak"):
            entries.append((d.name, d.stat().st_size))
    entries.sort(key=lambda x: x[0])

    total = sum(sz for _, sz in entries)
    for name, sz in entries:
        if total <= BACKUP_MAX_TOTAL_BYTES:
            break
        target = BACKUP_DIR / name
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
            total -= sz
            removed.append(name)
        except Exception:
            pass

    return removed


@app.get("/api/backups")
def api_backups():
    """列出归档备份：整合包归档 pack_backup_*、DMF 组件备份 dmf_backup_*、清单备份 mod_load_order.*.bak"""
    if not BACKUP_DIR.is_dir():
        return {"backups": []}
    backups = []
    for d in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        if d.name.startswith("pack_backup_"):
            mods_dir = d / "mods"
            if mods_dir.is_dir():
                mods = sorted(x.name for x in mods_dir.iterdir() if x.is_dir())
                # 启用数：从备份内的 mod_load_order.txt 统计（无清单则 None）
                enabled_count = None
                lo_f = mods_dir / "mod_load_order.txt"
                if lo_f.is_file():
                    try:
                        enabled_count = sum(
                            1 for ln in lo_f.read_text(encoding="utf-8", errors="ignore").splitlines()
                            if ln.strip() and not ln.strip().startswith("--"))
                    except Exception:
                        enabled_count = None
                backups.append({
                    "id": d.name, "type": "pack",
                    "created": _fmt_ts(d.name[len("pack_backup_"):]),
                    "mods": mods, "count": len(mods),
                    "enabled_count": enabled_count,
                    "has_load_order": lo_f.is_file(),
                })
        elif d.name.startswith("dmf_backup_"):
            files = [x for x in d.rglob("*") if x.is_file()]
            backups.append({
                "id": d.name, "type": "dmf",
                "created": _fmt_ts(d.name[len("dmf_backup_"):]),
                "count": len(files),
            })
    # 清单备份（散文件 mod_load_order.<ts>.bak）
    for f in sorted(BACKUP_DIR.glob("mod_load_order.*.bak"), reverse=True):
        ts = f.stem[len("mod_load_order."):]
        backups.append({
            "id": f.name, "type": "load_order",
            "created": _fmt_ts(ts),
            "count": 1,
        })
    return {"backups": backups}


@app.post("/api/backups/{bid}/restore")
def api_backup_restore(bid: str):
    """恢复备份：pack=整合包归档（当前 mods 先归档再换回），load_order=清单备份（当前清单先备份再覆盖）"""
    if not is_valid_game_dir(GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先到「关于」页设置"}
    if is_game_running():
        return {"ok": False, "error": "游戏正在运行，请先关闭游戏再恢复"}

    # 清单备份恢复：mod_load_order.<ts>.bak -> mod_load_order.txt（当前先备份）
    if bid.startswith("mod_load_order.") and bid.endswith(".bak"):
        bak_file = BACKUP_DIR / bid
        if not bak_file.is_file():
            return {"ok": False, "error": "备份不存在"}
        if not MODS_DIR.is_dir():
            return {"ok": False, "error": "mods 目录不存在"}
        # 先读内容再备份当前（避免 backup_load_order 的保留 10 份逻辑误删目标）
        try:
            content = bak_file.read_text(encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"读取备份失败: {e}"}
        backup_load_order()  # 当前清单先备份
        try:
            LOAD_ORDER_FILE.write_text(content, encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"恢复失败: {e}"}
        return {"ok": True, "message": f"✓ 已恢复清单备份 {bid}（当前清单已备份）"}

    src = BACKUP_DIR / bid / "mods"
    if not src.is_dir():
        return {"ok": False, "error": "备份不存在或不是整合包归档"}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 1. 当前 mods 先归档（防误操作丢状态）
    MODS_DIR.mkdir(parents=True, exist_ok=True)
    cur_bak = BACKUP_DIR / f"pack_backup_{ts}" / "mods"
    cur_bak.mkdir(parents=True, exist_ok=True)
    archived = []
    for item in sorted(MODS_DIR.iterdir()):
        if item.is_dir() and item.name in SYSTEM_MODS:
            continue
        try:
            shutil.move(str(item), str(cur_bak / item.name))
            archived.append(item.name)
        except Exception as e:
            return {"ok": False, "error": f"归档当前 mods 失败: {e}"}
    # 2. 恢复备份内容（冲突文件备份进 BACKUP_DIR，不在游戏目录留 .bak_）
    restored = []
    for item in sorted(src.iterdir()):
        target = MODS_DIR / item.name
        if target.exists():
            b = BACKUP_DIR / f"pack_backup_{ts}" / "mods" / item.name
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(b))
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
        restored.append(item.name)
    # 3. 打补丁
    msg = f"✓ 已恢复备份 {bid}：{len(restored)} 项（当前 mods 已归档到 pack_backup_{ts}）"
    if is_game_running():
        msg += "；游戏运行中，退出后自动补打补丁"
    else:
        r = _run_patch("--patch")
        if r.get("patched"):
            msg += "，补丁已激活，mods 已就绪"
        else:
            msg += f"，但补丁未打上：{r.get('error') or '未知原因'}"
    pruned = prune_backups()
    if pruned:
        msg += f"（已清理 {len(pruned)} 个旧备份）"
    return {"ok": True, "message": msg, "restored": restored, "archived": archived}


@app.delete("/api/backups/{bid}")
def api_backup_delete(bid: str):
    """删除归档备份（目录或清单散文件）"""
    d = BACKUP_DIR / bid
    if d.is_dir():
        if not (bid.startswith("pack_backup_") or bid.startswith("dmf_backup_")):
            return {"ok": False, "error": "备份不存在"}
        shutil.rmtree(d, ignore_errors=True)
    elif d.is_file() and bid.startswith("mod_load_order.") and bid.endswith(".bak"):
        d.unlink(missing_ok=True)
    else:
        return {"ok": False, "error": "备份不存在"}
    return {"ok": True, "message": f"已删除备份 {bid}"}


class ExportBody(BaseModel):
    name: str = ""  # 包名（不含扩展名），留空用时间戳
    mode: str = "all"  # all=全部导出（所有 mod + 全量清单）| enabled=按启用导出 | load_order=仅导出干净的启停清单


@app.post("/api/export")
def api_export(body: ExportBody):
    """导出为整合包 zip（不含系统组件 base/dmf）：
    mode=all：打包全部 mod，清单列全部；
    mode=enabled：只打包启用的 mod，清单只列启用的；
    mode=load_order：不打包 mod，只生成干净的 mod_load_order.txt（当前启用的 mod，按顺序）。
    产出可直接再「导入整合包」（自产自销闭环），保存到 exe 旁 exports/ 目录。"""
    g = guard_game_running("导出整合包")
    if g:
        return g
    if not MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在，无法导出"}

    mode = body.mode if body.mode in ("all", "enabled", "load_order") else "all"
    # 收集 mod 文件夹（排除系统组件）
    all_dirs = sorted(
        (d for d in MODS_DIR.iterdir() if d.is_dir() and d.name not in SYSTEM_MODS),
        key=lambda d: d.name.lower())
    if not all_dirs:
        return {"ok": False, "error": "mods 目录下没有可导出的 mod"}

    enabled_set = set(enabled_names(read_load_order()))

    # 按模式筛选
    if mode == "enabled":
        mod_dirs = [d for d in all_dirs if d.name in enabled_set]
        if not mod_dirs:
            return {"ok": False, "error": "当前没有启用中的 mod，无法按启用导出"}
    else:
        mod_dirs = all_dirs

    # 包名
    name = re.sub(r'[\\/:*?"<>|]', "_", (body.name or "").strip())
    if not name:
        name = f"整合包_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 导出目录
    export_dir = BASE_DIR / "exports"
    export_dir.mkdir(exist_ok=True)

    if mode == "load_order":
        # 仅导出干净清单：只列当前启用中的 mod（按当前顺序），无注释/无禁用行
        dir_names = {d.name for d in all_dirs}
        ordered = [n for n in enabled_names(read_load_order()) if n in dir_names]
        if not ordered:
            return {"ok": False, "error": "当前没有启用中的 mod，无法导出清单"}
        out_path = export_dir / f"mod_load_order_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            out_path.write_text("\n".join(ordered) + "\n", encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"导出失败: {e}"}
        return {
            "ok": True,
            "message": f"✓ 已导出干净清单（{len(ordered)} 个启用 mod）",
            "path": str(out_path),
            "count": len(ordered),
            "mode": mode,
        }

    out_path = export_dir / f"{name}.zip"

    try:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            # mods/ 下每个 mod 文件夹
            for d in mod_dirs:
                for f in sorted(d.rglob("*")):
                    if f.is_file():
                        z.write(f, f"mods/{d.name}/{f.relative_to(d)}")
            # 启停清单：all=全部 mod（按目录序），enabled=只列启用的（按当前顺序）
            ordered = [d.name for d in mod_dirs]
            if ordered:
                z.writestr("mods/mod_load_order.txt", "\n".join(ordered) + "\n")
    except Exception as e:
        return {"ok": False, "error": f"导出失败: {e}"}

    return {
        "ok": True,
        "message": f"✓ 已导出 {len(mod_dirs)} 个 mod 到 {out_path.name}",
        "path": str(out_path),
        "count": len(mod_dirs),
        "mode": mode,
    }


@app.post("/api/settings/game_dir")
def api_set_game_dir(body: GameDirBody):
    """手动设置游戏目录（写入 config.json，重启后生效）"""
    p = Path(body.path.strip().strip('\"'))
    if not p.is_dir():
        return {"ok": False, "error": "目录不存在"}
    if not is_valid_game_dir(p):
        return {"ok": False, "error": "该目录不是暗潮游戏目录（需包含 mods 或 bundle 文件夹）"}
    cfg = load_config()
    cfg["game_dir"] = str(p)
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入配置失败: {e}"}
    return {"ok": True, "path": str(p), "restart_required": True}


@app.get("/api/mods")
def api_mods():
    return {"mods": scan_mods()}


@app.get("/api/deps/check")
def api_deps_check():
    """依赖检查：缺依赖 + 循环依赖。
    基于 .mod 显式声明的 packages（DMF 惯例：mod 名即其提供的库名）。
    返回：missing=[{mod, needs}] / cycles=[[a,b,...]] / total / bad。"""
    mods = [m for m in scan_mods() if not m["missing"]]
    # 可用库 = 所有 mod 名（小写）+ base/dmf 系统组件
    available = {m["name"].lower() for m in mods} | {s.lower() for s in SYSTEM_MODS}
    # 每个 mod 的依赖
    dep_map = {m["name"]: [d for d in m.get("dependencies", [])] for m in mods}
    # 小写别名（依赖声明可能是小写，mod 名可能带大小写）
    lower_to_name = {n.lower(): n for n in dep_map}

    missing = []
    for m in mods:
        for d in dep_map.get(m["name"], []):
            if d not in available:
                missing.append({"mod": m["name"], "needs": d})

    # 循环依赖（DFS 找环）
    cycles = []
    visited = set()
    path_stack = []
    path_set = set()

    def dfs(node):
        if node in path_set:
            # 找到环：从当前节点截取
            i = path_stack.index(node)
            cycle = path_stack[i:] + [node]
            # 规范化：从最小名字开始，去重
            if len(cycle) >= 3:
                norm = cycle[:-1]
                shift = norm.index(min(norm))
                norm = norm[shift:] + norm[:shift]
                if norm not in cycles:
                    cycles.append(norm)
            return
        if node in visited:
            return
        visited.add(node)
        path_set.add(node)
        path_stack.append(node)
        for d in dep_map.get(node, []):
            # 只追踪已知 mod 之间的依赖（系统组件不算环），小写匹配
            target = lower_to_name.get(d)
            if target and target in dep_map:
                dfs(target)
        path_stack.pop()
        path_set.discard(node)

    for name in dep_map:
        dfs(name)

    # 加载顺序提示：mod 名包含另一个已启用 mod 名（本体→扩展），扩展应排在本体之后。
    # 只检查双方都启用的对（未启用的不参与顺序）。
    enabled_names_list = [m["name"] for m in mods if m["enabled"]]
    enabled_pos = {n: i for i, n in enumerate(enabled_names_list)}
    order_hints = []
    for a in enabled_names_list:
        al = a.lower()
        for b in enabled_names_list:
            if a == b:
                continue
            bl = b.lower()
            # B 是 A 的子串（B 为本体，A 为扩展），且 B 当前排在 A 后面 → 提示
            if len(bl) >= 4 and bl in al and enabled_pos[b] > enabled_pos[a]:
                order_hints.append({"ext": a, "base": b})

    return {
        "ok": True,
        "missing": missing,
        "cycles": cycles,
        "order_hints": order_hints,
        "total": len(mods),
        "bad": len(missing) + len(cycles) + len(order_hints),
    }


@app.post("/api/mods/{name}/open_folder")
def api_open_folder(name: str):
    """在资源管理器中打开 mod 文件夹（右键菜单用）"""
    if not MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在"}
    safe = Path(name).name  # 防路径穿越
    if safe in ("", "null", "undefined"):
        return {"ok": False, "error": "mod 名称无效，请重新右键后重试"}
    target = MODS_DIR / safe
    if not target.is_dir():
        return {"ok": False, "error": "mod 文件夹不存在（可能是清单残留）"}
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return {"ok": True, "message": f"已打开 {safe}"}
    except Exception as e:
        return {"ok": False, "error": f"打开失败: {e}"}


class NoteBody(BaseModel):
    note: str


class UrlBody(BaseModel):
    url: str


@app.post("/api/open_url")
def api_open_url(body: UrlBody):
    """在系统默认浏览器打开链接（关于页项目主页用）"""
    url = body.url.strip()
    if not url.startswith(("https://", "http://")):
        return {"ok": False, "error": "无效链接"}
    try:
        webbrowser.open(url)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/export/open_folder")
def api_export_open_folder():
    """打开导出目录（exports/）"""
    d = BASE_DIR / "exports"
    if not d.is_dir():
        return {"ok": False, "error": "导出目录不存在（还没导出过）"}
    try:
        os.startfile(str(d))  # type: ignore[attr-defined]
        return {"ok": True, "message": f"已打开 {d}"}
    except Exception as e:
        return {"ok": False, "error": f"打开失败: {e}"}


class LoadOrderImportBody(BaseModel):
    content: str  # 清单文本内容


class LoadOrderPreviewBody(BaseModel):
    content: str = ""  # 目标清单内容（可选，与 source 二选一）
    source: str = ""  # 来源：backup:<bid> 或 profile:<name>


@app.post("/api/load_order/preview")
def api_load_order_preview(body: LoadOrderPreviewBody):
    """启停清单差异预览（只读）：目标清单 vs 当前清单。
    返回：turn_on（将启用）/ turn_off（将禁用）/ keep_on / keep_off / 统计。"""
    g = guard_game_running("预览清单")
    if g:
        return g

    # 解析目标清单内容
    target_lines = []
    if body.source.startswith("backup:"):
        bak = BACKUP_DIR / body.source[len("backup:"):]
        if not bak.is_file() or not body.source.endswith(".bak"):
            return {"ok": False, "error": "清单备份不存在"}
        try:
            target_lines = bak.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            return {"ok": False, "error": f"读取备份失败: {e}"}
    elif body.source.startswith("profile:"):
        p = profile_path(body.source[len("profile:"):])
        if not p.exists():
            return {"ok": False, "error": "预设不存在"}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            target_lines = data.get("mods", [])
        except Exception as e:
            return {"ok": False, "error": f"读取预设失败: {e}"}
    elif body.content.strip():
        target_lines = body.content.splitlines()
    else:
        return {"ok": False, "error": "缺少目标清单"}

    # 目标启用集（mod 行，忽略注释/空行）
    target_on = set()
    for ln in target_lines:
        s = ln.strip()
        if s and not s.startswith("--"):
            target_on.add(s)

    # 当前启用集
    cur_entries = read_load_order()
    cur_on = {e["name"] for e in cur_entries if e["kind"] == "mod"}
    cur_off = set()
    for e in cur_entries:
        if e["kind"] == "comment" and is_exact_disable(e["raw"]):
            cur_off.add(e["raw"].strip()[2:].strip())
    # 已知 mod = 当前清单里出现过的（含禁用行）
    known = cur_on | cur_off

    turn_on = sorted(target_on - cur_on)
    turn_off = sorted((known & cur_on) - target_on)
    keep_on = sorted(cur_on & target_on)

    return {
        "ok": True,
        "turn_on": turn_on,
        "turn_off": turn_off,
        "keep_on": keep_on,
        "target_count": len(target_on),
        "cur_on_count": len(cur_on),
    }


@app.post("/api/load_order/import")
def api_load_order_import(body: LoadOrderImportBody):
    """导入启停清单：用提供的清单内容替换当前 mod_load_order.txt（先备份）。
    自动过滤空行/注释，只保留 mod 行（与现有格式兼容）。"""
    g = guard_game_running("导入清单")
    if g:
        return g
    if not MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在"}
    content = (body.content or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in content.split("\n")]
    # 保留注释（--开头）与 mod 行，过滤纯空行
    keep = []
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("--"):
            keep.append(ln)  # 保留注释行（如禁用标记 --ModName）
        else:
            keep.append(ln)
    if not keep:
        return {"ok": False, "error": "清单内容为空或无效"}
    backup_load_order()
    try:
        LOAD_ORDER_FILE.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入失败: {e}"}
    return {"ok": True, "message": f"✓ 已导入清单（{len(keep)} 行），旧清单已备份"}


@app.post("/api/mods/{name}/note")
def api_set_note(name: str, body: NoteBody):
    """设置/清除 mod 备注（空字符串 = 清除）；显示为 mod名(备注)"""
    safe = Path(name).name
    notes = load_notes()
    if body.note.strip():
        notes[safe] = body.note.strip()
    else:
        notes.pop(safe, None)
    save_notes(notes)
    return {"ok": True, "note": notes.get(safe, "")}


@app.post("/api/mods/{name}/remove_from_load_order")
def api_remove_from_load_order(name: str):
    """从启停清单移除该 mod（含禁用注释行）——清理磁盘上已不存在的残留条目"""
    g = guard_game_running("修改启停清单")
    if g:
        return g
    safe = Path(name).name
    entries = read_load_order()
    out = [e for e in entries
           if not (e["kind"] == "mod" and e["name"] == safe)
           and not (e["kind"] == "comment" and e["raw"].strip() == "--" + safe)]
    if len(out) == len(entries):
        return {"ok": False, "error": "清单中没有该 mod"}
    write_load_order(out)
    return {"ok": True, "message": f"已从清单移除 {safe}"}


def send_to_trash(path: Path) -> bool:
    """把文件/文件夹移到回收站（Windows Shell API，可恢复）"""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT = 3, 0x40, 0x10, 0x4
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = str(path) + "\0\0"  # 双 null 结尾（路径列表）
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0


@app.delete("/api/mods/{name}")
def api_delete_mod(name: str):
    """彻底删除 mod：文件夹移入回收站 + 从启停清单移除（系统组件 base/dmf 不可删）"""
    if not MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在"}
    g = guard_game_running("删除 mod")
    if g:
        return g
    safe = Path(name).name
    if safe in ("", "null", "undefined"):
        return {"ok": False, "error": "mod 名称无效"}
    if safe in SYSTEM_MODS:
        return {"ok": False, "error": f"{safe} 是系统组件（DMF 框架），不可删除"}
    target = MODS_DIR / safe
    if not target.is_dir():
        return {"ok": False, "error": "mod 文件夹不存在（可用右键「从清单移除」清理残留）"}
    # 1. 从清单移除（含禁用注释行）
    entries = read_load_order()
    out = [e for e in entries
           if not (e["kind"] == "mod" and e["name"] == safe)
           and not (e["kind"] == "comment" and e["raw"].strip() == "--" + safe)]
    if len(out) != len(entries):
        write_load_order(out)
    # 2. 文件夹移入回收站
    try:
        if not send_to_trash(target):
            return {"ok": False, "error": "移入回收站失败（文件可能被占用）"}
    except Exception as e:
        return {"ok": False, "error": f"删除失败: {e}"}
    # 3. 清理备注
    notes = load_notes()
    if safe in notes:
        notes.pop(safe, None)
        save_notes(notes)
    return {"ok": True, "message": f"已删除 {safe}（可到回收站找回）"}


@app.post("/api/mods/{name}/toggle")
def api_toggle(name: str):
    g = guard_game_running("修改启停清单")
    if g:
        return g
    entries = read_load_order()
    idx = next((i for i, e in enumerate(entries) if e["kind"] == "mod" and e["name"] == name), None)
    if idx is not None:
        entries[idx] = {"kind": "comment", "raw": "--" + entries[idx]["raw"]}
    else:
        idx = next((i for i, e in enumerate(entries)
                    if e["kind"] == "comment" and e["raw"].strip() == "--" + name), None)
        if idx is not None:
            entries[idx] = {"kind": "mod", "raw": name, "name": name}
        else:
            entries.append({"kind": "mod", "raw": name, "name": name})
    write_load_order(entries)
    return {"ok": True, "name": name, "enabled": name in enabled_names(read_load_order())}


class OrderBody(BaseModel):
    mods: list[str]  # 启用的 mod 完整有序列表


class BatchBody(BaseModel):
    names: list[str]  # 目标 mod 列表
    action: str  # enable | disable | delete | remove


@app.post("/api/mods/batch")
def api_mods_batch(body: BatchBody):
    """批量操作：enable/disable（改启停清单）/ delete（删文件进回收站）/ remove（清残留）
    逐个执行，失败项收集返回，不中断；游戏运行时整批拒绝。"""
    g = guard_game_running("批量修改")
    if g:
        return g
    names = [Path(n).name for n in (body.names or []) if n and Path(n).name not in ("", "null", "undefined")]
    if not names:
        return {"ok": False, "error": "没有有效的 mod 目标"}
    if body.action not in ("enable", "disable", "delete", "remove"):
        return {"ok": False, "error": f"未知操作: {body.action}"}

    done, failed = [], []
    if body.action in ("enable", "disable"):
        # 批量启停：直接操作清单设置目标状态（比逐个 toggle 更稳）
        want_enabled = (body.action == "enable")
        entries = read_load_order()
        # 收集已知 mod（含精确禁用行）
        known = set()
        for e in entries:
            if e["kind"] == "mod":
                known.add(e["name"])
            elif e["kind"] == "comment" and is_exact_disable(e["raw"]):
                known.add(e["raw"].strip()[2:].strip())
        changed = False
        for name in names:
            if name not in known:
                failed.append({"name": name, "error": "清单中没有该 mod"})
                continue
            if want_enabled:
                # 找禁用行移除
                for i, e in enumerate(entries):
                    if e["kind"] == "comment" and e["raw"].strip() == "--" + name:
                        entries[i] = {"kind": "mod", "raw": name, "name": name}
                        changed = True
                        break
            else:
                # 找启用行转禁用
                for i, e in enumerate(entries):
                    if e["kind"] == "mod" and e["name"] == name:
                        entries[i] = {"kind": "comment", "raw": "--" + name}
                        changed = True
                        break
            done.append(name)
        if changed:
            write_load_order(entries)
    else:
        for name in names:
            try:
                if body.action == "delete":
                    r = api_delete_mod(name)
                    if r.get("ok"):
                        done.append(name)
                    else:
                        failed.append({"name": name, "error": r.get("error") or "删除失败"})
                elif body.action == "remove":
                    r = api_remove_from_load_order(name)
                    if r.get("ok"):
                        done.append(name)
                    else:
                        failed.append({"name": name, "error": r.get("error") or "移除失败"})
            except Exception as e:
                failed.append({"name": name, "error": str(e)})

    msg = f"✓ 批量{ {'enable':'启用','disable':'禁用','delete':'删除','remove':'清残留'}[body.action] }：{len(done)} 个成功"
    if failed:
        msg += f"，{len(failed)} 个失败"
    return {"ok": True, "message": msg, "action": body.action, "done": done, "failed": failed}


@app.post("/api/order")
def api_set_order(body: OrderBody):
    g = guard_game_running("修改启停清单")
    if g:
        return g
    entries = read_load_order()
    enabled_set = set(body.mods)

    # 收集已知 mod（含精确禁用行），说明注释/空行原样保留
    known, seen, kept = [], set(), []
    for e in entries:
        name = None
        if e["kind"] == "mod":
            name = e["name"]
        elif e["kind"] == "comment" and is_exact_disable(e["raw"]):
            name = e["raw"].strip()[2:].strip()
        if name:
            if name not in seen:
                seen.add(name)
                known.append((name, e["kind"] == "mod"))
        else:
            kept.append(e)

    disabled = [n for n, _ in known if n not in enabled_set]
    new_lines = (
        [{"kind": "mod", "raw": n, "name": n} for n in body.mods]
        + [{"kind": "comment", "raw": "--" + n} for n in disabled]
    )
    out = kept + new_lines
    write_load_order(out)
    return {"ok": True, "enabled": body.mods, "disabled": disabled}


# ---------------------------------------------------------------- 预设

def profile_path(name: str) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
    if not safe:
        raise HTTPException(400, "预设名不能为空")
    return PROFILES_DIR / f"{safe}.json"


@app.get("/api/profiles")
def api_profiles():
    if not PROFILES_DIR.is_dir():
        return {"profiles": []}
    profiles = []
    for f in sorted(PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            profiles.append({
                "name": data.get("name", f.stem),
                "mods": data.get("mods", []),
                "count": len(data.get("mods", [])),
                "created": data.get("created", ""),
            })
        except Exception:
            continue
    return {"profiles": profiles}


class ProfileBody(BaseModel):
    name: str


@app.post("/api/profiles")
def api_profile_save(body: ProfileBody):
    entries = read_load_order()
    mods = enabled_names(entries)
    PROFILES_DIR.mkdir(exist_ok=True)
    data = {"name": body.name.strip(), "mods": mods, "created": datetime.now().isoformat(timespec="seconds")}
    profile_path(body.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "profile": data}


@app.post("/api/profiles/{name}/apply")
def api_profile_apply(name: str):
    p = profile_path(name)
    if not p.exists():
        raise HTTPException(404, "预设不存在")
    data = json.loads(p.read_text(encoding="utf-8"))
    return api_set_order(OrderBody(mods=data.get("mods", [])))


@app.delete("/api/profiles/{name}")
def api_profile_delete(name: str):
    p = profile_path(name)
    if p.exists():
        p.unlink()
    return {"ok": True}


# ---------------------------------------------------------------- 静态页

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import argparse
    import logging
    import socket
    import threading
    import time
    import uvicorn

    parser = argparse.ArgumentParser(description="暗潮 Mod 管理器")
    parser.add_argument("--port", type=int, default=None,
                        help="监听端口 (默认自动选择空闲端口)")
    parser.add_argument("--browser", action="store_true",
                        help="用浏览器打开而不是独立窗口 (默认独立窗口)")
    args = parser.parse_args()

    PROFILES_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)

    # 日志写文件（--windowed 无控制台时也能排错）
    LOG_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"f": {"format": "%(asctime)s %(levelname)s %(message)s"}},
        "handlers": {"file": {
            "class": "logging.FileHandler",
            "filename": str(BASE_DIR / "app.log"),
            "encoding": "utf-8",
            "formatter": "f",
        }},
        "root": {"handlers": ["file"], "level": "INFO"},
    }

    # 单实例保护：命名互斥体
    if not args.browser and not acquire_single_instance():
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, "暗潮 Mod 管理器已经在运行中。\n请查看任务栏或系统托盘。",
            "暗潮 Mod 管理器", 0x40)
        sys.exit(0)

    # 端口：显式指定则用指定值，否则动态分配空闲端口
    port = args.port if args.port else find_free_port()

    logging.getLogger().info(
        f"启动 | 游戏目录={GAME_DIR} (valid={is_valid_game_dir(GAME_DIR)}) | "
        f"端口={port} | 预设={PROFILES_DIR}")

    url = f"http://127.0.0.1:{port}"

    def serve():
        uvicorn.run(app, host="127.0.0.1", port=port, log_config=LOG_CONFIG)

    def wait_port(port, timeout=15):
        """等服务就绪，避免窗口打开时页面加载失败"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    return True
            except OSError:
                time.sleep(0.2)
        return False

    threading.Thread(target=serve, daemon=True).start()
    ready = wait_port(port)
    logging.getLogger().info(f"服务就绪={ready}")

    if args.browser:
        webbrowser.open(url)
        # 浏览器模式下保持前台运行直到 Ctrl+C
        while True:
            time.sleep(3600)
    else:
        import webview

        def load_window_state():
            return load_config().get("window", {})

        def save_window_state(x, y, w, h):
            cfg = load_config()
            cfg["window"] = {"x": x, "y": y, "width": w, "height": h}
            try:
                CONFIG_FILE.write_text(
                    json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        ws = load_window_state()
        win = webview.create_window(
            "暗潮 Mod 管理器", url,
            width=ws.get("width", 1020), height=ws.get("height", 760),
            x=ws.get("x"), y=ws.get("y"),
            min_size=(760, 520),
            js_api=_JsApi())

        def on_closing():
            try:
                save_window_state(win.x, win.y, win.width, win.height)
            except Exception:
                pass

        win.events.closing += on_closing
        webview.start()
        logging.getLogger().info("窗口已关闭，程序退出")
