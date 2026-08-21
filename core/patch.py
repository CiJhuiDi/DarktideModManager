# -*- coding: utf-8 -*-
"""补丁检测/打补丁/游戏运行状态/防呆守卫（纯逻辑 + 子进程，无 FastAPI 依赖）。"""
import json
import subprocess
from pathlib import Path

from core import state

CREATE_NO_WINDOW = 0x08000000

# 自动装载插件：游戏启动时引擎加载它，它会检测并自动重新打补丁
AUTOPATCH_DLL = Path("binaries") / "plugins" / "_dt_mod_autopatch.dll"


def patch_state() -> dict:
    """权威检测：bundle_database.data 是否被 dtkit-patch 注入补丁引用。
    注意：不能用 *.patch_999 文件存在性判断——卸载补丁后该文件仍在。
    警告：永远不要改名/删除 patch_999 或 mod_loader 文件——游戏启动时
    自动装载会重新打补丁，文件缺失会导致游戏 Fatal Error 崩溃。"""
    tool = state.GAME_DIR / "tools" / "dtkit-patch.exe"
    patched = False
    db = state.GAME_DIR / "bundle" / "bundle_database.data"
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


def _darktide_running_via_snapshot() -> bool:
    """用 CreateToolhelp32Snapshot 枚举进程（<5ms），替代 tasklist 子进程（~350ms）。
    status 每 10s 轮询一次，tasklist 起进程的开销没必要。"""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    TH32CS_SNAPPROCESS = 0x00000002
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return False
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return False
        while True:
            if entry.szExeFile.lower() == "darktide.exe":
                return True
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                return False
    finally:
        kernel32.CloseHandle(snap)


def _game_running_impl() -> bool:
    """真实进程检测：优先快照 API（<5ms），异常回退 tasklist（兼容性兜底）"""
    try:
        return _darktide_running_via_snapshot()
    except Exception:
        pass
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        return "Darktide.exe" in out.decode("gbk", errors="ignore")
    except Exception:
        return False


def is_game_running() -> bool:
    """真实检测：进程列表里有 Darktide.exe 即运行中。
    测试模式：simulate_game_running=True 时直接返回 True（用于模拟环境测试防呆，不用真开游戏）。"""
    if state.load_config().get("simulate_game_running"):
        return True
    return _game_running_impl()


def is_game_running_real() -> bool:
    """只看真实进程，不看模拟开关"""
    return _game_running_impl()


def autopatch_path() -> Path:
    return state.GAME_DIR / AUTOPATCH_DLL


def autopatch_off_path() -> Path:
    return state.GAME_DIR / "binaries" / "plugins" / "_dt_mod_autopatch.dll.off"


def auto_patch_disabled() -> bool:
    """用户手动卸载过（禁用自动装载）"""
    return state.load_config().get("auto_patch_disabled", False)


def set_auto_patch_disabled(v: bool):
    cfg = state.load_config()
    cfg["auto_patch_disabled"] = v
    try:
        state.CONFIG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
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


def _run_patch(action: str) -> dict:
    """执行 dtkit-patch（--patch / --unpatch）"""
    st = patch_state()
    if not st["tool_exists"]:
        return {"ok": False, "error": "未找到 tools\\dtkit-patch.exe，无法操作补丁", **st}
    if is_game_running():
        return {"ok": False, "error": "游戏正在运行，请先关闭游戏再操作补丁", **st}
    try:
        r = subprocess.run(
            [str(st["tool_path"]), action, str(state.GAME_DIR / "bundle")],
            cwd=str(state.GAME_DIR), capture_output=True, text=True, timeout=120,
            creationflags=CREATE_NO_WINDOW)
        new_st = patch_state()
        return {"ok": r.returncode == 0, "returncode": r.returncode,
                "output": (r.stdout or r.stderr or "")[-600:], **new_st}
    except Exception as e:
        return {"ok": False, "error": str(e)}
