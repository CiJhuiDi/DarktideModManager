# -*- coding: utf-8 -*-
"""E2E 测试钩子（APIRouter）——**只在 `--e2e` 启动时才注册**，正式构建不暴露。

存在理由：DMM 的很多功能只能"真机点"才知道对不对（多选拖动、弹窗文案、日志页渲染…），
而 WebView2 支持 CDP 远程调试（实测：给 exe 加 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222`
就能连上真界面）。于是把"驱动界面"交给 `tools/e2e_ui.py`，这里只提供**确定性钩子**：
重建测试环境、按服务端路径导包、读关键状态 —— 让断言不必去啃 DOM。

安全边界：① 仅 `--e2e` 注册；② 服务本来只绑 127.0.0.1；③ 不改任何正式构建行为。
"""
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from core import state
from core.crash import resolve_crash_root, CRASH_DISTRO_LABELS
from core import imports as _imports
from core.imports import import_pack_archive
from core.load_order import enabled_names, read_load_order
from core.mods import invalidate_scan_cache, load_my_mods, scan_mods
from core.state import is_valid_game_dir, load_config

router = APIRouter()

# 由 app.main() 在解析完端口后填：{"app": 8317, "cdp": 9222}
INFO = {"app": None, "cdp": None}


@router.get("/api/test/state")
def api_test_state():
    """关键状态 JSON（给 E2E 断言用；比解析 DOM 稳）"""
    entries = read_load_order()
    mods = scan_mods()
    root, distro = resolve_crash_root()
    return {
        "ok": True,
        "e2e": True,
        "app": {"port": INFO.get("app"), "cdp": INFO.get("cdp"),
                "frozen": bool(getattr(sys, "frozen", False))},
        "game": {"dir": str(state.GAME_DIR), "valid": is_valid_game_dir(state.GAME_DIR),
                 "mods": len(mods), "enabled": len(enabled_names(entries))},
        "my_mods": load_my_mods(),
        "load_order": enabled_names(entries),
        "theme": load_config().get("theme", ""),
        "simulated_game_running": bool(load_config().get("simulate_game_running")),
        "crash_log_root": {"dir": str(root) if root else None,
                           "distro": CRASH_DISTRO_LABELS.get(distro, "")},
        # 供 E2E 断言"一个整合包到底被解压几次"（用户报过重复解压）
        "extract_calls": _imports.EXTRACT_CALLS,
        "pack_stages": len(_imports._PACK_STAGES),
        # 启停清单的指纹：E2E 用它证明"只开预览 / 点取消 = 没有写文件"
        "load_order_file": _load_order_fingerprint(),
    }


def _load_order_fingerprint() -> dict:
    """清单文件的 size/mtime/行数（E2E 用来核对"有没有被重写"）"""
    try:
        st = state.LOAD_ORDER_FILE.stat()
        lines = len(state.LOAD_ORDER_FILE.read_text(encoding="utf-8-sig", errors="replace").splitlines())
        return {"exists": True, "size": st.st_size, "mtime": int(st.st_mtime), "lines": lines}
    except OSError:
        return {"exists": False, "size": 0, "mtime": 0, "lines": 0}


@router.post("/api/test/extract_reset")
def api_test_extract_reset():
    """把解压计数清零（E2E 里数"本次操作解压了几次"用）"""
    _imports.EXTRACT_CALLS = 0
    return {"ok": True}


@router.post("/api/test/reset")
def api_test_reset():
    """重建 mock 测试环境（复用 tools/build_mock.py）。仅源码模式可用——exe 里没有 tools/"""
    script = state.BASE_DIR / "tools" / "build_mock.py"
    if not script.is_file():
        return {"ok": False, "error": f"仅源码模式可用（找不到 {script}）"}
    r = subprocess.run([sys.executable, str(script)], cwd=str(state.BASE_DIR),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or r.stdout or "构建 mock 失败")[-500:]}
    invalidate_scan_cache()
    return {"ok": True, "output": (r.stdout or "").strip()[-300:]}


class ImportPackBody(BaseModel):
    path: str = ""              # 服务端压缩包路径（省掉前端上传大文件的编码坑）
    mode: str = "replace"
    keep_enabled: bool = True


@router.post("/api/test/import_pack")
def api_test_import_pack(body: ImportPackBody):
    """按服务端路径导入整合包（E2E 用；等价于界面上拖入一个包）"""
    p = Path(body.path)
    if not p.is_file():
        return {"ok": False, "error": f"文件不存在: {p}"}
    try:
        data = p.read_bytes()
    except Exception as e:
        return {"ok": False, "error": f"读取失败: {e}"}
    mode = "merge" if body.mode == "merge" else "replace"
    return import_pack_archive(p.name, data, mode, keep_enabled=bool(body.keep_enabled))
