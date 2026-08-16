# -*- coding: utf-8 -*-
"""游戏启动 / 崩溃检测 / 崩溃日志（APIRouter 路由）。"""
import json
import os
import re
import subprocess
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from core import patch
from core import state
from core.state import APP_ID, is_valid_game_dir

router = APIRouter()

GAME_LAUNCH_ARGS = [
    "--bundle-dir", "../bundle", "--ini", "settings",
    "--backend-auth-service-url", "https://bsp-auth-prod.atoma.cloud",
    "--backend-title-service-url", "https://bsp-td-prod.atoma.cloud",
    "--lua-heap-mb-size", "2048",
]

_launched_game = None  # 管理器启动的游戏进程（崩溃检测读退出码用）

CRASH_ROOT = Path(os.environ.get("APPDATA", "")) / "Fatshark" / "Darktide"


@router.post("/api/game/launch")
def api_launch_game():
    if not is_valid_game_dir(state.GAME_DIR):
        return {"ok": False, "error": "未设置正确的游戏目录"}
    if patch.is_game_running():
        return {"ok": False, "error": "游戏已在运行"}
    # 自动装载：启动游戏前补打补丁（若用户未手动禁用）
    patch.auto_patch_if_needed()
    exe = state.GAME_DIR / "binaries" / "Darktide.exe"
    if not exe.exists():
        exe = state.GAME_DIR / "content" / "binaries" / "Darktide.exe"
    if not exe.exists():
        return {"ok": False, "error": "未找到 Darktide.exe，请检查游戏文件完整性"}
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=patch.CREATE_NO_WINDOW).stdout
        if "steam.exe" not in out.lower():
            return {"ok": False, "error": "未检测到 Steam 客户端，请先启动 Steam 并登录"}
    except Exception:
        pass
    env = os.environ.copy()
    env["SteamAppId"] = APP_ID
    try:
        proc = subprocess.Popen([str(exe)] + GAME_LAUNCH_ARGS, cwd=str(exe.parent),
                                env=env, creationflags=patch.CREATE_NO_WINDOW)
        # 保存句柄：崩溃检测时可读取退出码（异常退出码为负值，如 0xC0000005）
        global _launched_game
        _launched_game = {"proc": proc, "pid": proc.pid}
        return {"ok": True, "message": "游戏启动中，请稍候…"}
    except Exception as e:
        return {"ok": False, "error": f"启动失败: {e}"}


def is_crash_code(code) -> bool:
    """NTSTATUS 异常码识别：0xC0000000~0xCFFFFFFF（崩溃/错误状态）。
    Windows 下 GetExitCodeProcess 可能返回有符号负数或对应无符号值，两种都覆盖。"""
    if code is None:
        return False
    u = (code & 0xFFFFFFFF)
    return 0xC0000000 <= u <= 0xCFFFFFFF


@router.get("/api/game/launched_exit")
def api_launched_exit():
    """管理器启动的游戏进程退出状态：运行中 exit_code=None；已退出返回退出码。
    崩溃时 Windows 返回 NTSTATUS 异常码（如 0xC0000005），crashed=True。"""
    global _launched_game
    proc = _launched_game.get("proc") if _launched_game else None
    if proc is None:
        return {"ok": True, "launched": False, "exit_code": None, "crashed": False}
    code = proc.poll()
    if code is None:
        return {"ok": True, "launched": True, "exit_code": None, "crashed": False}  # 仍在运行
    # 已退出：取回句柄状态后清除，避免重复读取
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    _launched_game = None
    return {"ok": True, "launched": True, "exit_code": code, "crashed": is_crash_code(code)}


def _latest_log_file(d: Path):
    """目录内最新文件 {name,time}；目录不存在或为空返回 None"""
    if not d.is_dir():
        return None
    files = [f for f in d.iterdir() if f.is_file()]
    if not files:
        return None
    newest = max(files, key=lambda f: f.stat().st_mtime)
    return {
        "name": newest.name,
        "time": datetime.fromtimestamp(newest.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/api/crash_logs")
def api_crash_logs():
    """崩溃排查信息：console_logs（教程说的控制台文本日志）+ crash_dumps 最新文件"""
    if not CRASH_ROOT.is_dir():
        return {"ok": False, "error": "未找到 Fatshark 游戏日志目录（%APPDATA%\\Fatshark\\Darktide）"}
    return {
        "ok": True,
        "dir": str(CRASH_ROOT),
        "console": _latest_log_file(CRASH_ROOT / "console_logs"),  # 控制台日志（文本，可直接看报错）
        "latest": _latest_log_file(CRASH_ROOT / "crash_dumps"),    # 崩溃转储（.dmp 二进制）
    }


@router.post("/api/crash_logs/open")
def api_crash_logs_open():
    """打开排查日志目录：优先 console_logs（文本控制台日志），其次 crash_dumps，最后根目录"""
    if not CRASH_ROOT.is_dir():
        return {"ok": False, "error": "未找到 Fatshark 游戏日志目录"}
    for name in ("console_logs", "crash_dumps"):
        target = CRASH_ROOT / name
        if not target.is_dir():
            continue
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
            hint = "（文本日志，可直接用记事本打开看报错）" if name == "console_logs" else "（.dmp 二进制转储，需专业工具分析）"
            return {"ok": True, "message": f"已打开 {name} 目录 {hint}"}
        except Exception as e:
            return {"ok": False, "error": f"打开失败: {e}"}
    try:
        os.startfile(str(CRASH_ROOT))
        return {"ok": True, "message": "已打开 Fatshark 游戏日志目录"}
    except Exception as e:
        return {"ok": False, "error": f"打开失败: {e}"}


class UrlBody(BaseModel):
    url: str


@router.post("/api/open_url")
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


# ---------------------------------------------------------------- 实验模式：日志预览 / 崩溃报告导出

LOG_ERROR_PATTERN = re.compile(r'(?i)(error|exception|fatal|critical|failed|luascript|lua error)')
LOG_WARN_PATTERN = re.compile(r'(?i)(warning|\bwarn\b)')


def classify_log_line(ln: str) -> str:
    """日志行分类：err（错误）/ warn（警告）/ ok（通常）"""
    if LOG_ERROR_PATTERN.search(ln):
        return 'err'
    if LOG_WARN_PATTERN.search(ln):
        return 'warn'
    return 'ok'


def _row(ln: str) -> dict:
    level = classify_log_line(ln)
    return {"text": ln, "err": level == 'err', "warn": level == 'warn', "level": level}


def _read_latest_console(tail: int = 300) -> dict | None:
    """读最新控制台日志尾部，行分类；无日志返回 None"""
    if not CRASH_ROOT.is_dir():
        return None
    latest = _latest_log_file(CRASH_ROOT / "console_logs")
    if not latest:
        return None
    p = CRASH_ROOT / "console_logs" / latest["name"]
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    lines = text.splitlines()[-tail:]
    rows = [_row(ln) for ln in lines]
    return {"file": latest["name"], "time": latest["time"], "lines": rows, "total": len(lines)}


@router.get("/api/crash_logs/read")
def api_crash_logs_read(tail: int = 300):
    """【实验】读取最新控制台日志尾部，疑似错误行 err=True（供预览高亮）"""
    data = _read_latest_console(max(50, min(tail, 1000)))
    if data is None:
        return {"ok": False, "error": "未找到控制台日志"}
    return {"ok": True, **data}


class LogAnalyzeBody(BaseModel):
    name: str = ""
    content: str = ""


@router.post("/api/crash_logs/analyze")
def api_crash_logs_analyze(body: LogAnalyzeBody):
    """【实验】分析导入的旧日志文本：行分类（err/warn/ok，限制 2MB / 尾部 2000 行）"""
    content = (body.content or "")[:2_000_000]
    lines = content.splitlines()[-2000:]
    rows = [_row(ln) for ln in lines]
    return {"ok": True, "file": (body.name or "导入日志"), "lines": rows, "total": len(lines)}


@router.post("/api/crash_logs/export")
def api_crash_logs_export():
    """【实验】导出崩溃报告 zip：最新控制台日志 + 崩溃转储清单 + 报告信息（发作者/群友用）"""
    out_dir = state.BASE_DIR / "exports"
    try:
        out_dir.mkdir(exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": f"无法创建导出目录: {e}"}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = out_dir / f"crash_report_{ts}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            latest = _latest_log_file(CRASH_ROOT / "console_logs") if CRASH_ROOT.is_dir() else None
            if latest:
                p = CRASH_ROOT / "console_logs" / latest["name"]
                try:
                    z.write(p, "console_logs/" + latest["name"])
                except Exception:
                    pass
            dump_count = 0
            dumps = CRASH_ROOT / "crash_dumps"
            if dumps.is_dir():
                for f in sorted(dumps.iterdir()):
                    if f.is_file():
                        try:
                            z.write(f, "crash_dumps/" + f.name)
                            dump_count += 1
                        except Exception:
                            pass
            info = {
                "导出时间": datetime.now().isoformat(timespec="seconds"),
                "版本": "Alpha 测试版",
                "游戏目录": str(state.GAME_DIR),
                "最新控制台日志": latest["name"] if latest else None,
                "崩溃转储文件数": dump_count,
            }
            z.writestr("report_info.json", json.dumps(info, ensure_ascii=False, indent=2))
    except Exception as e:
        return {"ok": False, "error": f"导出失败: {e}"}
    return {"ok": True, "path": str(zip_path), "name": zip_path.name}
