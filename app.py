# -*- coding: utf-8 -*-
"""
暗潮 Mod 管理器 - 后端
只做壳：读/写 mods/mod_load_order.txt，调用 dtkit-patch，不管 mod 加载逻辑。
"""
import json
import logging
import logging.config
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
from core import crash
from core.state import (GAME_FOLDER_NAME, APP_ID, SYSTEM_MODS,
                   load_config, detect_game_dir, find_game_dir, is_valid_game_dir,
                   apply_game_dir)
from core.load_order import (read_load_order, write_load_order, backup_load_order,
                    normalize_entries, enabled_names, is_exact_disable, set_load_order,
                    rebuild_plan, rebuild_load_order)
from core.patch import (patch_state, is_game_running, is_game_running_real,
                  autopatch_path, autopatch_off_path, auto_patch_disabled,
                  set_auto_patch_disabled, auto_patch_if_needed,
                  guard_game_running, _run_patch, CREATE_NO_WINDOW)
from core.mods import (load_notes, save_notes, scan_mods, invalidate_scan_cache,
                  read_mod_description, load_my_mods, set_my_mod,
                  store_my_mod, deploy_my_mod, my_mods_library, sync_my_mods_to_library)
from core.imports import (import_mod_archive, import_mod_from_dir, preview_pack_archive, import_pack_archive,
                     stage_pack_archive, _scan_mods_dir, diff_mods, _fmt_ts, prune_backups, export_pack,
                     backup_policy, save_backup_policy, prune_plan, backup_entries,
                     cached_backup_size, dir_size_bytes, backup_contents, restore_selected_from_backup)
from core.dmf import dmf_state, install_dmf
from core.crash import router as crash_router
from core.shader import router as shader_router
from core.theme import router as theme_router, custom_theme_state
from core.profiles import router as profiles_router, profile_path
from core.quotes import QUOTES

THEMES = ("abyss", "dawn", "pleasure", "plague", "rage", "mystic", "emperor")

app = FastAPI(title="Darktide Mod Manager")
app.include_router(crash_router)
app.include_router(shader_router)
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


def acquire_single_instance(wait: float = 2.0) -> bool:
    """返回 False 表示已有实例在运行（use_last_error 保证 get_last_error 可靠）。
    已有实例时先尝试聚焦其窗口（真多开直接拒绝，不等）；若窗口已消失（旧实例
    正在退出、互斥体尚未释放），短暂等待重试，超时才判为多开拦截。"""
    global _mutex_handle
    import ctypes
    import time
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    deadline = time.time() + wait
    while True:
        _mutex_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        if ctypes.get_last_error() != 183:  # 非 ERROR_ALREADY_EXISTS = 获得所有权
            return True
        # 已存在：释放本次句柄（无所有权），先试聚焦已有窗口，失败则等旧进程退出后重试
        kernel32.CloseHandle(_mutex_handle)
        _mutex_handle = None
        if focus_existing_window():
            return False
        if time.time() >= deadline:
            return False
        time.sleep(0.3)


def release_single_instance():
    """窗口关闭后主动释放互斥体：进程退出有延迟（Python 清理 + WebView2 子进程收尾），
    不释放会导致关窗后立刻重启被误判为多开。释放后进程退出时 OS 不会二次关闭。"""
    global _mutex_handle
    if _mutex_handle:
        try:
            ctypes.WinDLL('kernel32').CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None


def cleanup_webview_children():
    """窗口关闭后主动结束本实例的 WebView2 子进程（msedgewebview2.exe），加速用户数据目录锁释放。
    否则关窗后立刻重启时，新实例的 WebView2 要等旧进程释放锁——曾实测干等 47 秒。"""
    try:
        import psutil
        me = psutil.Process()
        for child in me.children(recursive=True):
            try:
                if child.name().lower() == "msedgewebview2.exe":
                    child.kill()
            except Exception:
                pass
    except Exception:
        pass


def focus_existing_window(title: str = "暗潮 Mod 管理器") -> bool:
    """多开被拒时尝试激活已有实例的主窗口，返回是否成功。
    校验窗口进程必须属于本程序（防误中 explorer TabProxyWindow 等同名窗口）。
    后台进程直接 SetForegroundWindow 会被 Windows 前台激活锁忽略：先 SW_RESTORE 恢复
    最小化窗口，再模拟 Alt 键绕过激活限制，最后 SetForegroundWindow + BringWindowToTop。"""
    try:
        import ctypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.FindWindowW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.SetForegroundWindow.restype = ctypes.c_bool
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.IsIconic.argtypes = [ctypes.c_void_p]
        user32.IsIconic.restype = ctypes.c_bool
        user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
        user32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool]
        user32.SetFocus.argtypes = [ctypes.c_void_p]
        user32.SetFocus.restype = ctypes.c_void_p
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        user32.RedrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
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
            if b'DarktideModManager.exe' not in (out or b''):  # bytes 比较！str in bytes 会 TypeError 被吞成 False
                return False
        except Exception:
            return False
        # 仅当窗口最小化时才还原（SW_RESTORE=9）：无条件还原会把最大化窗口打回普通大小，
        # 导致窗口尺寸突变 + WebView2 重绘白屏闪烁，且破坏用户的全屏布局
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        # AttachThreadInput 方案：当前线程 attach 到目标窗口线程 + 前台线程，
        # SetForegroundWindow 即不被前台激活锁拦截。不注入任何按键事件（keybd_event 模拟
        # Alt 可能干扰 WebView2 渲染，曾疑导致聚焦后白屏），更温和安全。
        cur = kernel32.GetCurrentThreadId()
        tgt = user32.GetWindowThreadProcessId(hwnd, None)
        fg = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        attached = []
        if tgt and tgt != cur:
            user32.AttachThreadInput(cur, tgt, True)
            attached.append(tgt)
        if fg and fg != cur and fg != tgt:
            user32.AttachThreadInput(cur, fg, True)
            attached.append(fg)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        # WebView2 最小化还原后偶发白屏（GPU 合成器未唤醒，已知问题）：强制整窗无效化重绘
        user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0080 | 0x0100)  # RDW_INVALIDATE|RDW_ALLCHILDREN|RDW_UPDATENOW
        for t in attached:
            user32.AttachThreadInput(cur, t, False)
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
        "total": _mods_dir_count(),  # 轻量计数，不触发 scan_mods（轮询每 10s 一次，别白扫）
        "enabled": len(enabled_names(read_load_order())),
        "profiles_dir": str(state.PROFILES_DIR),
        "patch": patch_state(),
        "game_running": is_game_running(),  # 快照 API 检测 <5ms，轮询无压力
        "simulated_game_running": bool(load_config().get("simulate_game_running")),
        "theme": load_config().get("theme", "abyss"),
        "grad": load_config().get("grad", "diag"),
        "custom_theme": custom_theme_state(),
        "dmf": dmf_state(),
    }


def _mods_dir_count() -> int:
    """轻量 mod 数量：只枚举目录，不读 localization/依赖（供 status 展示）"""
    try:
        return sum(1 for d in state.MODS_DIR.iterdir()
                   if d.is_dir() and d.name not in state.SYSTEM_MODS and ".bak_" not in d.name)
    except Exception:
        return 0


class PerfBody(BaseModel):
    load_ms: int = 0        # 页面 JS 启动 → 主数据接口返回
    render_ms: int = 0      # render() 渲染耗时
    total_ms: int = 0       # 页面加载 → 渲染完成总耗时
    api_ms: dict = {}       # 各接口耗时


@app.post("/api/perf")
def api_perf(body: PerfBody):
    """前端启动耗时上报（写 app.log 排错用，不影响功能）"""
    logging.getLogger().info(
        f"前端启动耗时: load={body.load_ms}ms render={body.render_ms}ms total={body.total_ms}ms "
        f"api={json.dumps(body.api_ms, ensure_ascii=False)}")
    return {"ok": True}


@app.get("/api/quotes")
def api_quotes():
    """暗潮加载画面语录（310 条），前端启动时拉取一次，本地洗牌轮换。"""
    return {"quotes": QUOTES}


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
        return {"ok": True, "message": "DMF 组件已启用，无需重复操作", **st}
    r = _run_patch("--patch")
    r["message"] = "✓ DMF 组件已启用，mods 已生效" if r.get("patched") else "✗ 启用 DMF 组件失败"
    return r


@app.post("/api/patch/uninstall")
def api_patch_uninstall():
    """卸载补丁：还原数据库 + 禁用自动装载插件（autopatch.dll 改名），
    游戏启动时不会自动重打补丁，mods 真正禁用且不崩溃。
    注意：绝不动 patch_999/mod_loader 文件。"""
    st = patch_state()
    if not st["patched"] and not autopatch_off_path().exists():
        return {"ok": True, "message": "DMF 组件本来就已启用，无需停用", **st}
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
            msgs.append("DMF 组件已停用")
        else:
            msgs.append("停用 DMF 组件失败")
    msg = "✓ " + "，".join(msgs) + "（启动游戏不会自动恢复，mods 保持禁用）" if msgs else "✓ DMF 组件已停用"
    new_st = patch_state()
    return {"ok": True, "message": msg, **new_st}


# ---------------------------------------------------------------- 启动游戏（绕过启动器）

# ---------------------------------------------------------------- mod 导入

@app.post("/api/mods/import")
async def api_import_mods(files: list[UploadFile] = File(...), force_mod: bool = Form(False),
                          overwrite_mine: bool = Form(False)):
    """导入单个 mod。overwrite_mine=1 表示用户已确认「用别人的同名版本覆盖我的 mod」。
    未确认时若撞上「我的 mod」→ 返回 is_my_mod_conflict，由前端弹窗让用户决定。"""
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
        results.append(import_mod_archive(f.filename or "mod.zip", data, force_mod=force_mod,
                                          overwrite_mine=overwrite_mine))
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
    token: str = ""     # /api/pack/stage/discard 用：要丢弃的暂存标识


@app.post("/api/pack/preview")
def api_pack_preview(body: PackPreviewBody):
    """导入整合包前的差异预览（只读，不写 mods；**会解压一次，用完即删**）。

    新前端走 `/api/pack/stage`：一次上传、一次解压，预览与导入共用暂存。"""
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


@app.post("/api/pack/stage")
async def api_pack_stage(files: list[UploadFile] = File(...)):
    """**上传并解压一次**整合包，返回 `token` + 预览。

    修的是"导入时解压两遍"：预览与随后的导入共用这次解压（导入带 `staged_token` 即可，
    不再重传包体、也不再解压）。暂存 30 分钟未用自动清理。"""
    if not is_valid_game_dir(state.GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先到「关于」页设置"}
    if not files:
        return {"ok": False, "error": "没有收到文件"}
    f = files[0]                      # 预览只看第一个包（与原行为一致）
    try:
        data = await f.read()
    except Exception as e:
        return {"ok": False, "error": f"读取失败: {e}"}
    if not data:
        return {"ok": False, "error": "文件为空"}
    return stage_pack_archive(f.filename or "pack.zip", data)


@app.post("/api/pack/import")
async def api_pack_import(files: list[UploadFile] | None = File(None),
                          mode: str = Form("replace"),
                          keep_enabled: str = Form("1"),
                          mine_choice: str = Form(""),
                          staged_token: str = Form("")):
    """整合包导入：mode=replace（默认，整体替换）| merge（叠加）
    keep_enabled=1（默认）：replace 时保留当前启用中的 mod（缺失自动补回，版本冲突返回待决策）
    mine_choice：**「我的 mod」与包内同名时的逐个决定**，JSON `{"mod名":"mine"|"pack"}`（前端逐个问过再传；
        缺省/未传 = 保留玩家自己的版本，程序不替玩家做冲突决定）
    staged_token：`/api/pack/stage` 的暂存标识。带上它就直接复用那次解压结果——**不再上传包体、不再解压第二遍**。
        files 与 token 可同时给：先导暂存的那个包，再依次导上传的其它文件。"""
    if mode not in ("replace", "merge"):
        mode = "replace"
    # 兼容：HTTP 走 Form 注入；test_guard 等直接函数调用时 keep_enabled 可能是 Form 对象/缺失
    ke = keep_enabled
    if not isinstance(ke, str):
        ke = "1"
    keep = ke.strip().lower() not in ("0", "false", "off", "")
    if not is_valid_game_dir(state.GAME_DIR):
        return {"ok": False, "results": [], "error": "未设置正确的游戏目录"}
    g = guard_game_running("导入整合包")
    if g:
        return {"ok": False, "results": [], **g}
    # 同名冲突的逐个决定（前端问过再传；解析失败就当没传 = 一律保留我的版本）
    choice = {}
    if isinstance(mine_choice, str) and mine_choice.strip():
        try:
            parsed = json.loads(mine_choice)
            if isinstance(parsed, dict):
                choice = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            choice = {}
    results = []
    tok = (staged_token or "").strip()
    if tok:
        # 复用 /api/pack/stage 的那次解压：不重传包体、不重解压
        st = None
        try:
            from core.imports import _PACK_STAGES
            st = _PACK_STAGES.get(tok)
        except Exception:
            st = None
        results.append(import_pack_archive((st or {}).get("name") or "pack.zip", b"", mode,
                                           keep_enabled=keep, mine_choice=choice, staged_token=tok))
    for f in (files or []):
        try:
            data = await f.read()
        except Exception as e:
            results.append({"file": f.filename, "ok": False, "error": f"读取失败: {e}"})
            continue
        results.append(import_pack_archive(f.filename or "pack.zip", data, mode,
                                           keep_enabled=keep, mine_choice=choice))
    if not results:
        return {"ok": False, "results": [], "error": "没有收到文件"}
    return {"ok": True, "results": results}


@app.post("/api/pack/stage/discard")
def api_pack_stage_discard(body: PackPreviewBody):
    """丢弃暂存的整合包（用户取消导入时调用，立即释放临时目录，不等 30 分钟 TTL）"""
    tok = (getattr(body, "token", "") or "").strip()
    if not tok:
        return {"ok": False, "error": "缺少 token"}
    from core.imports import _PACK_STAGES, _drop_stage
    existed = tok in _PACK_STAGES
    _drop_stage(tok)
    return {"ok": True, "discarded": existed}


class KeepConflictBody(BaseModel):
    ts: str          # 导入时的 pack_backup_<ts> 归档标识
    names: list[str] # 用户选择“补回我的版本”的 mod 名列表


@app.post("/api/pack/keep_conflicts")
def api_pack_keep_conflicts(body: KeepConflictBody):
    """换包保留的版本冲突决策：把用户选定 mod 从归档覆盖回游戏 mods/（并确保在启用清单）。
    用于导入弹窗选「补回我的版本」后执行；选「用新包」的什么都不做。"""
    ts = body.ts.strip()
    names = [n for n in (body.names or []) if n]
    if not ts or not names:
        return {"ok": False, "error": "缺少归档标识或 mod 列表"}
    bak_mods = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods"
    if not bak_mods.is_dir():
        return {"ok": False, "error": f"找不到归档 backups/pack_backup_{ts}/，可能已被清理，无法补回"}
    done, failed = [], []
    for name in names:
        src = bak_mods / name
        dst = state.MODS_DIR / name
        if not src.is_dir():
            failed.append({"name": name, "error": "归档里没有该 mod"})
            continue
        try:
            if dst.exists() or state.is_junction(dst):
                state.safe_rmtree(dst)      # 联接只摘链接，绝不递归进源码（实测 rmtree 会拒绝 junction）
            shutil.copytree(src, dst)
            done.append(name)
        except Exception as e:
            failed.append({"name": name, "error": str(e)})
    if done:
        try:
            entries = read_load_order()
            names_now = {e["name"] for e in entries if e["kind"] == "mod"}
            changed = False
            for name in done:
                if name not in names_now:
                    entries.append({"kind": "mod", "raw": name, "name": name})
                    names_now.add(name)
                    changed = True
            if changed:
                write_load_order(entries)
        except Exception:
            pass
        invalidate_scan_cache()
    return {"ok": True, "restored": done, "failed": failed}


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
    """列出归档备份：整合包归档 pack_backup_*、DMF 组件备份 dmf_backup_*、挑单恢复的原地备份 partial_*、清单备份 mod_load_order.*.bak

    2026-10-06 备份页现代化：每条带 `size_bytes`，并返回 `total_bytes` / 当前保留策略 / 「将自动清理哪些」计划
    —— 让界面能显示"已用 X / 上限 Y"，而不是让策略静默删掉唯一的回滚点。"""
    pol = backup_policy()
    if not state.BACKUP_DIR.is_dir():
        return {"backups": [], "total_bytes": 0, "policy": pol, "plan": []}
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
                    "size_bytes": cached_backup_size(d),
                })
        elif d.name.startswith("dmf_backup_"):
            files = [x for x in d.rglob("*") if x.is_file()]
            backups.append({
                "id": d.name, "type": "dmf",
                "created": _fmt_ts(d.name[len("dmf_backup_"):]),
                "count": len(files),
                "size_bytes": cached_backup_size(d),
            })
        elif d.name.startswith("partial_"):
            md = d / "mods"
            backups.append({
                "id": d.name, "type": "partial",
                "created": _fmt_ts(d.name[len("partial_"):]),
                "count": len([x for x in md.iterdir()]) if md.is_dir() else 0,
                "size_bytes": cached_backup_size(d),
            })
        elif d.name.startswith("game_dir_cleanup_"):
            md = d / "mods"
            backups.append({
                "id": d.name, "type": "game_cleanup",
                "created": _fmt_ts(d.name[len("game_dir_cleanup_"):]),
                "count": len([x for x in md.iterdir()]) if md.is_dir() else 0,
                "size_bytes": cached_backup_size(d),
            })
    # 清单备份（散文件 mod_load_order.<ts>.bak）
    for f in sorted(state.BACKUP_DIR.glob("mod_load_order.*.bak"), reverse=True):
        ts = f.stem[len("mod_load_order."):]
        backups.append({
            "id": f.name, "type": "load_order",
            "created": _fmt_ts(ts),
            "count": 1,
            "size_bytes": f.stat().st_size,
        })
    return {"backups": backups,
            "total_bytes": sum(b.get("size_bytes") or 0 for b in backups),
            "policy": pol, "plan": prune_plan()["would_remove"]}


@app.get("/api/backups/policy")
def api_backup_policy():
    """当前保留策略 + 占用 + 将自动清理哪些（备份页"占用可见可控"用）"""
    return {"ok": True, "policy": backup_policy(), "plan": prune_plan(),
            "total_bytes": sum(sz for _n, _p, sz in backup_entries())}


class BackupPolicyBody(BaseModel):
    max_per_type: int | None = None
    max_total_mb: int | None = None


@app.post("/api/backups/policy")
def api_backup_policy_save(body: BackupPolicyBody):
    """改保留策略（写 config.json，立即生效；不动任何备份内容）"""
    r = save_backup_policy(body.max_per_type, body.max_total_mb)
    if not r.get("ok"):
        return r
    return {"ok": True, "policy": backup_policy(), "plan": prune_plan()}


@app.post("/api/backups/prune")
def api_backup_prune(dry_run: bool = False):
    """按当前策略清理（dry_run=true 只列出将删的，不删）——删除前先让玩家确认"""
    names = prune_backups(dry_run=True) if dry_run else prune_backups()
    items = [{"id": n, "size_bytes": dir_size_bytes(state.BACKUP_DIR / n)} for n in names]
    return {"ok": True, "dry_run": bool(dry_run), "removed": items,
            "freed_bytes": sum(x["size_bytes"] for x in items),
            "total_bytes": sum(sz for _n, _p, sz in backup_entries())}


@app.get("/api/backups/{bid}/contents")
def api_backup_contents(bid: str):
    """看备份里有什么（详情：逐 mod 列大小 / 是否已在游戏目录 / 备份里启用没）"""
    return backup_contents(bid)


class RestoreSelectedBody(BaseModel):
    names: list[str] = []
    enable: bool = False


@app.post("/api/backups/{bid}/restore_selected")
def api_backup_restore_selected(bid: str, body: RestoreSelectedBody):
    """**从备份里挑单个/几个 mod 恢复**（可顺带启用）；整包恢复仍走 /restore"""
    if not is_valid_game_dir(state.GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先在「关于」页设置"}
    if is_game_running():
        return {"ok": False, "error": "游戏正在运行中，请先关闭游戏再恢复"}
    r = restore_selected_from_backup(bid, body.names, enable=body.enable)
    if r.get("ok"):
        invalidate_scan_cache()
    return r


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
        msg += "；游戏运行中，退出后会自动启用组件"
    else:
        r = _run_patch("--patch")
        if r.get("patched"):
            msg += "，DMF 组件已启用，mods 已就绪"
        else:
            msg += f"，但组件未能生效：{r.get('error') or '未知原因'}"
    pruned = prune_backups()
    if pruned:
        msg += f"（已清理 {len(pruned)} 个旧备份）"
    invalidate_scan_cache()  # 恢复备份改了 mods 目录
    return {"ok": True, "message": msg, "restored": restored, "archived": archived}


@app.delete("/api/backups/{bid}")
def api_backup_delete(bid: str):
    """删除归档备份（目录或清单散文件）"""
    d = state.BACKUP_DIR / bid
    ALLOWED = ("pack_backup_", "dmf_backup_", "partial_", "root_cleanup_", "game_dir_cleanup_")
    if d.is_dir() or state.is_junction(d):
        if not bid.startswith(ALLOWED):
            return {"ok": False, "error": "备份不存在"}
        state.safe_rmtree(d, ignore_errors=True)     # 联接只摘链接，不递归进目标
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


@app.post("/api/game_dir")
def api_set_game_dir(body: GameDirBody):
    """手动设置游戏目录（保存并立即生效）"""
    g = guard_game_running("切换游戏目录")
    if g:
        return g
    p = Path(body.path.strip().strip('\"'))
    if not p.is_dir():
        logging.getLogger().warning(f"手动设置游戏目录失败（目录不存在）| 输入={body.path!r}")
        return {"ok": False, "error": "目录不存在"}
    if not is_valid_game_dir(p):
        try:
            _names = sorted(d.name for d in p.iterdir() if d.is_dir())[:20]
        except Exception as e:
            _names = [f"<枚举失败 {e!r}>"]
        logging.getLogger().warning(
            f"手动设置游戏目录失败（缺 mods/bundle 目录）| 输入={p} | 该层子目录={_names}")
        return {"ok": False, "error": "该目录不是暗潮游戏目录（需包含 mods 或 bundle 文件夹）"}
    if not apply_game_dir(p):
        logging.getLogger().warning(f"手动设置游戏目录失败（写配置失败）| 输入={p}")
        return {"ok": False, "error": "写入配置失败"}
    logging.getLogger().info(f"游戏目录已手动设置 | {p} | 自动识别诊断：{state.game_dir_diagnosis()}")
    return {"ok": True, "path": str(p), "restart_required": False}


@app.post("/api/game_dir/detect")
def api_detect_game_dir():
    """自动扫描 Steam 库 + Xbox/Game Pass 常见安装位置识别游戏目录并保存（手动识别按钮，立即生效）
    ⚠️ Xbox / Game Pass 分支为实验功能：仅单测覆盖，未在真机 Game Pass 环境实测。"""
    g = guard_game_running("切换游戏目录")
    if g:
        return g
    p = detect_game_dir()
    if p is None or not is_valid_game_dir(p):
        # 识别失败留痕（Xbox / Game Pass 用户点「自动识别」失败时，app.log 里能看到扫了哪些路径）
        logging.getLogger().warning(f"自动识别游戏目录失败 | {state.game_dir_diagnosis()}")
        return {"ok": False, "error": "未在 Steam 库或 Xbox/Game Pass 默认安装位置找到暗潮游戏目录，请改用「选择文件夹」手动指定"}
    logging.getLogger().info(f"自动识别游戏目录命中 | {p} | {state.game_dir_diagnosis()}")
    if not apply_game_dir(p):
        return {"ok": False, "error": "写入配置失败"}
    return {"ok": True, "path": str(p), "restart_required": False}


@app.get("/api/mods")
def api_mods():
    return {"mods": scan_mods(), "my_mods": load_my_mods(), "my_lib": my_mods_library()}


@app.get("/api/mods/{name}/detail")
def api_mod_detail(name: str):
    """mod 详细描述（悬停浮层懒加载；列表接口不带 description 以减首屏体积）"""
    safe = Path(name).name
    d = state.MODS_DIR / safe
    if not d.is_dir():
        return {"ok": False, "error": "mod 不存在"}
    return {"ok": True, "name": safe, "description": read_mod_description(d)}


@app.get("/api/deps/check")
def api_deps_check():
    """mod 环境检查：缺依赖 + 依赖没启用 + 循环依赖 + 加载顺序。
    来源两处：.mod 的 packages（库依赖）、info.json 的 dependencies
    （required / self_after / self_before —— DMF 的声明式契约）。
    返回：missing=[{mod, needs}] / inactive=[{mod, needs}] / cycles=[[a,b,...]] /
          order_hints=[{ext, base, why}] / total / bad。

    注意 missing 与 inactive 的区别：前者是「磁盘上根本没有」，后者是「装了但没启用」。
    后者以前不报——A 依赖 B、B 装着但停用，检查照样说正常，游戏里 A 一样崩。"""
    mods = [m for m in scan_mods() if not m["missing"]]
    # 「装了」与「启用」要分开两个集合：依赖在磁盘上存在 ≠ 会被加载
    present = {m["name"].lower() for m in mods} | {s.lower() for s in SYSTEM_MODS}
    enabled_lower = {m["name"].lower() for m in mods if m["enabled"]}
    # 系统组件：base 由 DML 无条件加载；dmf 可能被用户停用（dmf.mod 改名）
    sys_enabled = {"base"}
    try:
        ds = dmf_state()
        # 只有「装了但被停用」才算不可用；压根没装/目录无效交给 DMF 横幅去说，别在这重复报
        if not (ds.get("installed") and not ds.get("enabled")):
            sys_enabled.add("dmf")
    except Exception:
        sys_enabled.add("dmf")
    loadable = enabled_lower | sys_enabled

    # 每个 mod 的依赖（packages 库名 + info.json 的 required）
    dep_map = {m["name"]: [d for d in m.get("dependencies", [])] for m in mods}
    for m in mods:
        dep_map[m["name"]] = sorted(set(dep_map[m["name"]]) | set(m.get("dep_required", [])))
    # 只有会被加载的 mod 才值得查：未启用的 mod 根本不会进游戏，
    # 它的依赖在不在、启没启用都不构成问题（查了只会给 300+ 个停用项刷噪音）。
    active_mods = [m for m in mods if m["enabled"]]
    active_names = {m["name"] for m in active_mods}
    # 小写别名（依赖声明可能是小写，mod 名可能带大小写）
    lower_to_name = {n.lower(): n for n in dep_map}
    low_active = {m["name"].lower(): m["name"] for m in active_mods}

    missing = []
    inactive = []
    for m in active_mods:
        for d in dep_map.get(m["name"], []):
            if d not in present:
                missing.append({"mod": m["name"], "needs": d})
            elif d not in loadable:
                # 显示回原始大小写（声明里常写小写，界面该看到 mod 的真名）
                inactive.append({"mod": m["name"], "needs": lower_to_name.get(d, d)})

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
            # 只追踪**已启用**的 mod 之间的依赖（系统组件不算环、未启用的不加载也就不成环）
            target = low_active.get(d)
            if target:
                dfs(target)
        path_stack.pop()
        path_set.discard(node)

    for name in active_names:
        dfs(name)

    # 加载顺序：
    # ① info.json 里显式声明的 self_after / self_before（可靠的契约，作者写明的）
    # ② mod 名包含关系（启发式，只在没被 ① 覆盖时补充）
    # 只检查双方都启用的对（未启用的不参与顺序）。
    enabled_names_list = [m["name"] for m in mods if m["enabled"]]
    enabled_pos = {n: i for i, n in enumerate(enabled_names_list)}
    low_enabled = {n.lower(): n for n in enabled_names_list}
    order_hints = []
    seen_pairs = set()

    def add_hint(ext, base, why):
        """ext 应排在 base 之后"""
        key = (ext.lower(), base.lower())
        if ext == base or key in seen_pairs:
            return
        seen_pairs.add(key)
        order_hints.append({"ext": ext, "base": base, "why": why})

    for m in mods:
        if not m["enabled"]:
            continue
        name = m["name"]
        pos_me = enabled_pos.get(name)
        if pos_me is None:
            continue
        # self_after：声明"我应排在它们之后" → 它们必须在我前面
        for d in m.get("dep_after", []):
            other = low_enabled.get(d)
            if other and enabled_pos[other] > pos_me:
                add_hint(name, other, "declared")
        # self_before：声明"我应排在它们之前" → 它们必须在我后面
        for d in m.get("dep_before", []):
            other = low_enabled.get(d)
            if other and enabled_pos[other] < pos_me:
                add_hint(other, name, "declared")

    for a in enabled_names_list:
        al = a.lower()
        for b in enabled_names_list:
            if a == b:
                continue
            bl = b.lower()
            # B 是 A 的子串（B 为本体，A 为扩展），且 B 当前排在 A 后面 → 提示
            if len(bl) >= 4 and bl in al and enabled_pos[b] > enabled_pos[a]:
                add_hint(a, b, "guess")

    return {
        "ok": True,
        "missing": missing,
        "inactive": inactive,
        "cycles": cycles,
        "order_hints": order_hints,
        "total": len(mods),
        "bad": len(missing) + len(inactive) + len(cycles) + len(order_hints),
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
    过滤空行与旧式禁用标记（--ModName，停用 = 不在清单），保留 mod 行与说明注释。"""
    g = guard_game_running("导入清单")
    if g:
        return g
    if not state.MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在"}
    content = (body.content or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in content.split("\n")]
    # 过滤空行与旧式禁用标记（--ModName）；保留说明注释与 mod 行
    keep = []
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("--") and is_exact_disable(ln):
            continue  # 旧式禁用标记：停用 = 不在清单，清理
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
    invalidate_scan_cache()  # 列表里显示备注，改了要刷新元数据缓存
    return {"ok": True, "note": notes.get(safe, "")}


class MyModBody(BaseModel):
    name: str = ""
    mine: bool = True


@app.post("/api/mods/mine")
def api_set_my_mod(body: MyModBody):
    """标记/取消「我的 mod」——自己设计/私装、整合包里没有的那些。

    标记时**顺手把游戏目录里的当前版本收进管理器库**（`my_mods/`），于是：
    ① 库里有安全副本（换包 / 清空 mods / 误删都不怕）② 换包时原地保留 + 按换包前状态保持启用
    ③ 包内有同名保留你的版本 ④ 游戏目录缺失时可从库一键部署回来。名单存 exe 旁 my_mods.json。"""
    g = guard_game_running("修改我的 mod 标记")
    if g:
        return g
    names = set_my_mod(body.name, body.mine)
    stored = None
    if body.mine:
        r = store_my_mod(body.name)
        stored = r.get("ok") and r.get("size_kb")
    invalidate_scan_cache()  # 列表要显示「我的」徽标，刷新元数据缓存
    return {"ok": True, "name": Path(body.name).name, "mine": bool(body.mine),
            "my_mods": names, "stored_kb": stored, "library": my_mods_library()}


class DeployMineBody(BaseModel):
    name: str = ""          # 空 = 把库里所有「我的 mod」都部署回游戏目录


@app.get("/api/mods/mine/library")
def api_my_mods_library():
    """管理器库总览：每个「我的 mod」是否在库里 / 是否已部署 / 是否启用 / 体积"""
    return {"ok": True, "dir": str(state.MY_MODS_DIR), "items": my_mods_library()}


@app.post("/api/mods/mine/sync")
def api_sync_my_mods(body: DeployMineBody | None = None):
    """把游戏目录里「我的 mod」的当前版本同步进管理器库（自研 mod 常在游戏目录里改着调试）。

    `name` 留空 = 全部；只读游戏目录、只写库 → 不设游戏运行守卫（游戏中也能同步）。"""
    only = (body.name if body else "") or ""
    if only:
        r = store_my_mod(only)
        stored, skipped = ([only], []) if r.get("ok") else ([], [only])
    else:
        r = sync_my_mods_to_library()
        stored, skipped = r.get("stored") or [], r.get("skipped") or []
    invalidate_scan_cache()
    return {"ok": True, "stored": stored, "skipped": skipped, "library": my_mods_library()}


@app.post("/api/mods/mine/deploy")
def api_deploy_my_mod(body: DeployMineBody):
    """从管理器库部署回游戏 mods/（游戏目录被清空、误删、换机器后恢复用）"""
    g = guard_game_running("从管理器库部署 mod")
    if g:
        return g
    want = [body.name] if body.name else [e["name"] for e in my_mods_library() if e["in_lib"]]
    if not want:
        return {"ok": False, "error": "管理器库里没有可部署的 mod"}
    done, failed = [], []
    for n in want:
        r = deploy_my_mod(n)
        (done if r.get("ok") else failed).append(n if r.get("ok") else {"name": n, "error": r.get("error")})
    invalidate_scan_cache()
    return {"ok": bool(done), "deployed": done, "failed": failed, "library": my_mods_library()}


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
    invalidate_scan_cache()
    return {"ok": True, "message": f"已删除 {safe}（可到回收站找回）"}


@app.post("/api/mods/{name}/toggle")
def api_toggle(name: str):
    g = guard_game_running("修改启停清单")
    if g:
        return g
    entries = read_load_order()
    idx = next((i for i, e in enumerate(entries) if e["kind"] == "mod" and e["name"] == name), None)
    if idx is not None:
        entries.pop(idx)  # 停用 = 从清单移除（清单只含启用中的 mod）
    else:
        idx = next((i for i, e in enumerate(entries)
                    if e["kind"] == "comment" and e["raw"].strip() == "--" + name), None)
        if idx is not None:
            entries[idx] = {"kind": "mod", "raw": name, "name": name}  # 兼容旧注释标记
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
        # 批量启停：新模型下停用 = 从清单移除、启用 = 追加/恢复，均为幂等
        want_enabled = (body.action == "enable")
        entries = read_load_order()
        on = {e["name"] for e in entries if e["kind"] == "mod"}  # 当前启用中的 mod
        changed = False
        for name in names:
            if want_enabled:
                # 启用：已在启用列表 → 跳过；有旧注释标记 → 原位恢复；否则追加
                if name in on:
                    done.append(name)
                    continue
                found = False
                for i, e in enumerate(entries):
                    if e["kind"] == "comment" and e["raw"].strip() == "--" + name:
                        entries[i] = {"kind": "mod", "raw": name, "name": name}
                        found = True
                        changed = True
                        break
                if not found:
                    entries.append({"kind": "mod", "raw": name, "name": name})
                    changed = True
                on.add(name)
            else:
                # 停用：在启用列表 → 移除；不在 → 本来就停用，跳过（幂等）
                if name in on:
                    for i, e in enumerate(entries):
                        if e["kind"] == "mod" and e["name"] == name:
                            entries.pop(i)
                            changed = True
                            break
                    on.discard(name)
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


class RebuildOrderBody(BaseModel):
    add_new: bool = False         # 是否顺带启用"磁盘上有、清单里没有"的 mod（默认否：那些多是你自己禁用的）
    strip_comments: bool = True   # 去掉整合包作者写的注释（用户要的"减少污染"，默认开）


@app.get("/api/order/rebuild_preview")
def api_rebuild_preview(add_new: bool = False, strip_comments: bool = True):
    """**手动重建当前清单**的前置预览（只读）：会移除哪些幽灵条目、会去掉多少行注释、哪些 mod 保持停用"""
    try:
        present = {d.name for d in state.MODS_DIR.iterdir()
                   if d.is_dir() and d.name not in state.SYSTEM_MODS and ".bak_" not in d.name}
    except OSError:
        return {"ok": False, "error": "mods 目录不存在"}
    return rebuild_plan(read_load_order(), present, add_new, strip_comments)


@app.post("/api/order/rebuild")
def api_rebuild_order(body: RebuildOrderBody = RebuildOrderBody()):
    """按 mods 目录现状重建 mod_load_order.txt（写前自动备份）。

    默认：保留仍存在 mod 的顺序、**去掉作者注释**、移除幽灵条目、把新增 mod 追加到末尾。
    游戏运行中拒绝（后端守卫）。"""
    g = guard_game_running("重建启停清单")
    if g:
        return g
    try:
        return rebuild_load_order(add_new=body.add_new, strip_comments=body.strip_comments)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}


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


# 本地 vendor 静态资源（SortableJS 等），避免依赖外网 CDN 导致脚本加载失败卡白屏
app.mount("/vendor", StaticFiles(directory=str(state.STATIC_DIR / "vendor")), name="vendor")


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
    parser.add_argument("--e2e", action="store_true",
                        help="E2E 测试模式：开 WebView2 远程调试端口 + 注册 /api/test/* 钩子（不动正式行为）")
    parser.add_argument("--cdp-port", type=int, default=9222,
                        help="E2E 模式下 WebView2 的 CDP 调试端口 (默认 9222)")
    args = parser.parse_args()

    state.PROFILES_DIR.mkdir(exist_ok=True)
    state.BACKUP_DIR.mkdir(exist_ok=True)

    # 日志写文件（--windowed 无控制台时也能排错）；轮转：单文件超 2MB 自动切新文件，保留 3 份
    # （前端每 10s 轮询 status 都写 access 日志，不轮转会无限增长）
    LOG_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"f": {"format": "%(asctime)s %(levelname)s %(message)s"}},
        "handlers": {"file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(state.BASE_DIR / "app.log"),
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
            "formatter": "f",
        }},
        "root": {"handlers": ["file"], "level": "INFO"},
    }
    # ⚠️ 必须在这里就装上 handler：文件 handler 原先只由 uvicorn.run(log_config=…) 安装，
    # 而它在 serve() 线程启动时才生效——启动阶段（单实例、环境诊断、端口）的日志
    # 那时还没有 handler，INFO 直接被丢弃（app.log 第一条一直是 uvicorn 自己的输出）。
    try:
        logging.config.dictConfig(LOG_CONFIG)
    except Exception as e:  # 目录不可写等：退化为默认日志，不因日志配置打断启动
        logging.basicConfig(level=logging.INFO)
        logging.getLogger().warning(f"app.log 初始化失败（不影响使用）: {e}")

    # 启动顺手清理整合包暂存：上一次会话若在预览中途被关掉/被杀，解压出来的临时目录会留在 %TEMP%
    # （`_prune_stages` 只清超过 TTL 的；不足 TTL 的下次请求还会顺手清）
    try:
        from core.imports import _prune_stages
        _prune_stages()
    except Exception:
        pass

    # 单实例保护：命名互斥体（已有实例时聚焦其窗口并静默退出，不弹提示框）
    # E2E 模式跳过：测试要能反复起停，且驱动脚本自己会先清进程
    if not args.browser and not args.e2e and not acquire_single_instance():
        focused = focus_existing_window()
        logging.getLogger().info("检测到已有实例，聚焦现有窗口后退出" + ("（已聚焦）" if focused else "（未找到窗口）"))
        sys.exit(0)

    # 端口：显式指定则用指定值，否则动态分配空闲端口
    port = args.port if args.port else find_free_port()

    # E2E：给 WebView2 开一个 CDP 远程调试端口，让 tools/e2e_ui.py 能驱动**真实界面**
    # （实测可行：WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS 里的 --remote-debugging-port 会被 WebView2 采纳）
    if args.e2e:
        _base_args = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "").strip()
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
            _base_args + f" --remote-debugging-port={args.cdp_port}").strip()
        try:
            from core import e2e as _e2e
            _e2e.INFO.update({"app": port, "cdp": args.cdp_port})
            app.include_router(_e2e.router)
            logging.getLogger().warning(
                f"E2E ready app={port} cdp={args.cdp_port}  ← 测试模式：已注册 /api/test/* 并开启 CDP")
        except Exception as e:
            logging.getLogger().error(f"E2E 模式初始化失败: {e}")

    # 构建标识：Alpha 态的每个测试包界面都只写「DMM Alpha」，靠 exe 的时间戳/大小才能区分
    # 用户手上是哪一个包（排查时最常踩的坑就是抓着一个旧 exe 反复验）
    try:
        if getattr(sys, "frozen", False):
            _exe = Path(sys.executable)
            _st = _exe.stat()
            build_tag = f"{_exe.name} {_st.st_size}B {datetime.fromtimestamp(_st.st_mtime):%Y-%m-%d %H:%M:%S}"
        else:
            build_tag = "源码运行（未打包）"
    except Exception:
        build_tag = "未知"

    logging.getLogger().info(
        f"启动 | 游戏目录={state.GAME_DIR} (valid={is_valid_game_dir(state.GAME_DIR)}) | "
        f"端口={port} | 构建={build_tag} | 预设={state.PROFILES_DIR}")
    # ★ 环境诊断留痕：Xbox / PC Game Pass 用户回报问题时，只看 exe 同目录的 app.log 就能定位
    #   （识别不到游戏目录 / 日志目录两分布不通用，这两类问题靠下面两行直接判死）
    logging.getLogger().info(f"环境诊断·游戏目录自动识别 | {state.game_dir_diagnosis()}")
    crash.log_crash_root_probe("启动", *crash.resolve_crash_root())

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
            ws = load_config().get("window", {}) or {}
            # 过滤非法窗口状态：最小化/隐藏时 Windows 返回 -32000 坐标和极小尺寸，
            # 直接用于下次启动会把窗口建到屏幕外（任务栏有图标但看不到窗口）
            try:
                if (ws.get("x", 0) < -1000 or ws.get("y", 0) < -1000
                        or ws.get("width", 0) < 200 or ws.get("height", 0) < 200):
                    return {}
            except Exception:
                return {}
            return ws

        def save_window_state(x, y, w, h):
            # 最小化/隐藏时坐标 -32000 或尺寸异常 → 不保存（下次用默认居中）
            try:
                if x < -1000 or y < -1000 or w < 200 or h < 200:
                    return
            except Exception:
                return
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

        def on_restored():
            """WebView2 最小化还原后偶发白屏（合成器未唤醒，已知问题）：
            微小 resize 往返强制重新合成（+1px 再还原）。"""
            try:
                win.resize(win.width + 1, win.height)
                win.resize(win.width - 1, win.height)
            except Exception:
                pass

        win.events.closing += on_closing
        win.events.restored += on_restored
        # private_mode 默认是 True：WebView2 每次启动都用临时配置目录，localStorage 全清空。
        # 结果就是「新手引导只弹一次」这条根本存不住，用户每次开都要重走一遍。
        # 显式给一个固定配置目录（exe 同目录，绿色版可写），localStorage 才会跨启动保留。
        profile_dir = state.BASE_DIR / "webview_profile"
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            profile_dir = None
        webview.start(private_mode=False,
                      storage_path=str(profile_dir) if profile_dir else None)
        logging.getLogger().info("窗口已关闭，程序退出")
        cleanup_webview_children()  # 先杀 WebView2 子进程（加速用户数据锁释放），再释放互斥体
        release_single_instance()
