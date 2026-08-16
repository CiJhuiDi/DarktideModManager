# -*- coding: utf-8 -*-
"""
暗潮 Mod 管理器 - 后端
只做壳：读/写 mods/mod_load_order.txt，调用 dtkit-patch，不管 mod 加载逻辑。
"""
import json
import random
import io
import os
import re
import shutil
import subprocess
import threading
import sys
import tempfile
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Body
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import state
from core.state import (GAME_FOLDER_NAME, APP_ID, SYSTEM_MODS,
                   load_config, detect_game_dir, find_game_dir, is_valid_game_dir,
                   apply_game_dir)
from core.load_order import (read_load_order, write_load_order, backup_load_order,
                    normalize_entries, enabled_names, is_exact_disable, set_load_order)
from core.patch import (patch_state, is_game_running, is_game_running_real,
                  autopatch_path, autopatch_off_path, auto_patch_disabled,
                  set_auto_patch_disabled, auto_patch_if_needed,
                  guard_game_running, _run_patch, CREATE_NO_WINDOW)
from core.mods import (load_notes, save_notes, scan_mods)
from core.imports import (import_mod_archive, import_mod_from_dir,
                     preview_pack_archive, import_pack_archive, _scan_mods_dir,
                     diff_mods, _fmt_ts, prune_backups, export_pack)
from core.dmf import dmf_state, install_dmf
from core.crash import router as crash_router
from core.theme import router as theme_router, custom_theme_state
from core.profiles import router as profiles_router, profile_path

THEMES = ("abyss", "dawn", "pleasure", "plague", "rage", "mystic", "emperor")

app = FastAPI(title="Darktide Mod Manager")
app.include_router(crash_router)
app.include_router(theme_router)
app.include_router(profiles_router)


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

# 单实例锁（Windows 命名互斥体；Local\ 前缀避免 Global\ 的 SeCreateGlobalPrivilege 权限误判）
_MUTEX_NAME = "Local\\DarktideModManager_Mutex"
_mutex_handle = None


def acquire_single_instance() -> bool:
    """返回 False 表示已有实例在运行（use_last_error 保证 get_last_error 可靠）"""
    global _mutex_handle
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _mutex_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def focus_existing_window(title: str = "暗潮 Mod 管理器") -> bool:
    """多开被拒时尝试激活已有实例的主窗口，返回是否成功。
    校验窗口进程必须属于本程序（防误中 explorer TabProxyWindow 等同名窗口）。"""
    try:
        import ctypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.FindWindowW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.SetForegroundWindow.restype = ctypes.c_bool
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        # 校验窗口属于 DarktideModManager.exe（防误中同名窗口）
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            out = subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid.value, '/FO', 'CSV', '/NH'],
                                 capture_output=True, timeout=5,
                                 creationflags=CREATE_NO_WINDOW).stdout
            if 'DarktideModManager.exe' not in (out or b''):
                return False
        except Exception:
            return False
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


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


# ---------------------------------------------------------------- API

@app.get("/api/status")
def api_status():
    valid = is_valid_game_dir(state.GAME_DIR)
    return {
        "game_dir": str(state.GAME_DIR),
        "game_dir_valid": valid,
        "mods_dir": str(state.MODS_DIR),
        "load_order_exists": state.LOAD_ORDER_FILE.exists() if state.LOAD_ORDER_FILE else False,
        "total": len(scan_mods()),
        "enabled": len(enabled_names(read_load_order())),
        "profiles_dir": str(state.PROFILES_DIR),
        "patch": patch_state(),
        "game_running": is_game_running(),
        "simulated_game_running": bool(load_config().get("simulate_game_running")),
        "theme": load_config().get("theme", "abyss"),
        "grad": load_config().get("grad", "diag"),
        "custom_theme": custom_theme_state(),
        "dmf": dmf_state(),
    }


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
        state.CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入配置失败: {e}"}
    return {"ok": True, "running": body.running, "simulated": True}


@app.post("/api/patch/auto")
def api_patch_auto():
    return auto_patch_if_needed()


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

# ---------------------------------------------------------------- mod 导入

@app.post("/api/mods/import")
async def api_import_mods(files: list[UploadFile] = File(...), force_mod: bool = Form(False)):
    if not is_valid_game_dir(state.GAME_DIR):
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
class DmfInstallBody(BaseModel):
    force: bool = False


@app.post("/api/dmf/install")
def api_dmf_install(body: DmfInstallBody = Body(default=None)):
    """一键安装/覆盖更新 DMF（逻辑见 dmf.install_dmf）"""
    force = False
    if body is not None:
        try:
            force = bool(body.force)
        except AttributeError:
            force = False
    return install_dmf(force)


class GameDirBody(BaseModel):
    path: str


PACK_BAK_PREFIX = "pack_import_"


class PackPreviewBody(BaseModel):
    filename: str = ""
    data_b64: str = ""  # 压缩包 base64（前端读取后传入）


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


@app.post("/api/pack/import")
async def api_pack_import(files: list[UploadFile] = File(...),
                          mode: str = Form("replace")):
    """整合包导入：mode=replace（默认，整体替换）| merge（叠加）"""
    if mode not in ("replace", "merge"):
        mode = "replace"
    if not is_valid_game_dir(state.GAME_DIR):
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

@app.post("/api/backups/{bid}/preview")
def api_backup_preview(bid: str):
    """备份恢复前的差异预览（只读）：备份内 mods vs 当前 mods"""
    if not is_valid_game_dir(state.GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先到「关于」页设置"}
    g = guard_game_running("预览备份")
    if g:
        return g
    src = state.BACKUP_DIR / bid / "mods"
    if not src.is_dir():
        return {"ok": False, "error": "备份不存在或不是整合包归档"}
    bak_mods = _scan_mods_dir(src)
    cur_mods = _scan_mods_dir(state.MODS_DIR)
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
@app.get("/api/backups")
def api_backups():
    """列出归档备份：整合包归档 pack_backup_*、DMF 组件备份 dmf_backup_*、清单备份 mod_load_order.*.bak"""
    if not state.BACKUP_DIR.is_dir():
        return {"backups": []}
    backups = []
    for d in sorted(state.BACKUP_DIR.iterdir(), reverse=True):
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
    for f in sorted(state.BACKUP_DIR.glob("mod_load_order.*.bak"), reverse=True):
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
    if not is_valid_game_dir(state.GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先到「关于」页设置"}
    if is_game_running():
        return {"ok": False, "error": "游戏正在运行，请先关闭游戏再恢复"}

    # 清单备份恢复：mod_load_order.<ts>.bak -> mod_load_order.txt（当前先备份）
    if bid.startswith("mod_load_order.") and bid.endswith(".bak"):
        bak_file = state.BACKUP_DIR / bid
        if not bak_file.is_file():
            return {"ok": False, "error": "备份不存在"}
        if not state.MODS_DIR.is_dir():
            return {"ok": False, "error": "mods 目录不存在"}
        # 先读内容再备份当前（避免 backup_load_order 的保留 10 份逻辑误删目标）
        try:
            content = bak_file.read_text(encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"读取备份失败: {e}"}
        backup_load_order()  # 当前清单先备份
        try:
            state.LOAD_ORDER_FILE.write_text(content, encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": f"恢复失败: {e}"}
        return {"ok": True, "message": f"✓ 已恢复清单备份 {bid}（当前清单已备份）"}

    src = state.BACKUP_DIR / bid / "mods"
    if not src.is_dir():
        return {"ok": False, "error": "备份不存在或不是整合包归档"}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 1. 当前 mods 先归档（防误操作丢状态）
    state.MODS_DIR.mkdir(parents=True, exist_ok=True)
    cur_bak = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods"
    cur_bak.mkdir(parents=True, exist_ok=True)
    archived = []
    for item in sorted(state.MODS_DIR.iterdir()):
        if item.is_dir() and item.name in SYSTEM_MODS:
            continue
        try:
            shutil.move(str(item), str(cur_bak / item.name))
            archived.append(item.name)
        except Exception as e:
            return {"ok": False, "error": f"归档当前 mods 失败: {e}"}
    # 2. 恢复备份内容（冲突文件备份进 state.BACKUP_DIR，不在游戏目录留 .bak_）
    restored = []
    for item in sorted(src.iterdir()):
        target = state.MODS_DIR / item.name
        if target.exists():
            b = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods" / item.name
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
    d = state.BACKUP_DIR / bid
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
    """导出为整合包 zip（逻辑见 imports.export_pack）"""
    g = guard_game_running("导出整合包")
    if g:
        return g
    return export_pack(body.name, body.mode)

def api_set_game_dir(body: GameDirBody):
    """手动设置游戏目录（保存并立即生效）"""
    g = guard_game_running("切换游戏目录")
    if g:
        return g
    p = Path(body.path.strip().strip('\"'))
    if not p.is_dir():
        return {"ok": False, "error": "目录不存在"}
    if not is_valid_game_dir(p):
        return {"ok": False, "error": "该目录不是暗潮游戏目录（需包含 mods 或 bundle 文件夹）"}
    if not apply_game_dir(p):
        return {"ok": False, "error": "写入配置失败"}
    return {"ok": True, "path": str(p), "restart_required": False}


@app.post("/api/game_dir/detect")
def api_detect_game_dir():
    """自动扫描 Steam 库识别游戏目录并保存（手动识别按钮，立即生效）"""
    g = guard_game_running("切换游戏目录")
    if g:
        return g
    p = detect_game_dir()
    if p is None or not is_valid_game_dir(p):
        return {"ok": False, "error": "未在 Steam 库中找到暗潮游戏目录，请改用「选择文件夹」手动指定"}
    if not apply_game_dir(p):
        return {"ok": False, "error": "写入配置失败"}
    return {"ok": True, "path": str(p), "restart_required": False}


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
    if not state.MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在"}
    safe = Path(name).name  # 防路径穿越
    if safe in ("", "null", "undefined"):
        return {"ok": False, "error": "mod 名称无效，请重新右键后重试"}
    target = state.MODS_DIR / safe
    if not target.is_dir():
        return {"ok": False, "error": "mod 文件夹不存在（可能是清单残留）"}
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return {"ok": True, "message": f"已打开 {safe}"}
    except Exception as e:
        return {"ok": False, "error": f"打开失败: {e}"}


class NoteBody(BaseModel):
    note: str


# ---------------------------------------------------------------- 崩溃日志

@app.post("/api/export/open_folder")
def api_export_open_folder():
    """打开导出目录（exports/）"""
    d = state.BASE_DIR / "exports"
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
        bak = state.BACKUP_DIR / body.source[len("backup:"):]
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
    if not state.MODS_DIR.is_dir():
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
        state.LOAD_ORDER_FILE.write_text("\n".join(keep) + "\n", encoding="utf-8")
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
    if not state.MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在"}
    g = guard_game_running("删除 mod")
    if g:
        return g
    safe = Path(name).name
    if safe in ("", "null", "undefined"):
        return {"ok": False, "error": "mod 名称无效"}
    if safe in SYSTEM_MODS:
        return {"ok": False, "error": f"{safe} 是系统组件（DMF 框架），不可删除"}
    target = state.MODS_DIR / safe
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
    return set_load_order(body.mods)


@app.get("/")
def index():
    """返回主页面，并把持久化主题内联进 body 标签，避免启动闪默认色"""
    html = (state.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    cfg = load_config()
    theme = cfg.get("theme", "abyss")
    grad = cfg.get("grad", "diag")
    if theme == "random":
        # 每次启动随机一个主题（不固化，保持随机状态）
        theme = random.choice(THEMES)
    if theme == "custom":
        mode = cfg.get("custom_theme_mode", "dark")
        html = html.replace(
            '<body data-theme="abyss" data-grad="diag">',
            f'<body data-theme="custom" data-custom-mode="{mode}" data-grad="{grad}">'
        )
    else:
        html = html.replace(
            '<body data-theme="abyss" data-grad="diag">',
            f'<body data-theme="{theme}" data-grad="{grad}">'
        )
    return HTMLResponse(html)


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

    state.PROFILES_DIR.mkdir(exist_ok=True)
    state.BACKUP_DIR.mkdir(exist_ok=True)

    # 日志写文件（--windowed 无控制台时也能排错）
    LOG_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"f": {"format": "%(asctime)s %(levelname)s %(message)s"}},
        "handlers": {"file": {
            "class": "logging.FileHandler",
            "filename": str(state.BASE_DIR / "app.log"),
            "encoding": "utf-8",
            "formatter": "f",
        }},
        "root": {"handlers": ["file"], "level": "INFO"},
    }

    # 单实例保护：命名互斥体
    if not args.browser and not acquire_single_instance():
        focused = focus_existing_window()
        logging.getLogger().info("检测到已有实例，拒绝多开" + ("（已聚焦现有窗口）" if focused else "（未找到窗口）"))
        import ctypes
        msg = "暗潮 Mod 管理器已经在运行中。"
        msg += "\n已切换到现有窗口。" if focused else "\n请查看任务栏或系统托盘。"
        ctypes.windll.user32.MessageBoxW(0, msg, "暗潮 Mod 管理器", 0x40)
        sys.exit(0)

    # 端口：显式指定则用指定值，否则动态分配空闲端口
    port = args.port if args.port else find_free_port()

    logging.getLogger().info(
        f"启动 | 游戏目录={state.GAME_DIR} (valid={is_valid_game_dir(state.GAME_DIR)}) | "
        f"端口={port} | 预设={state.PROFILES_DIR}")

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
                state.CONFIG_FILE.write_text(
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
