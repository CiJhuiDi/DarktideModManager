# -*- coding: utf-8 -*-
"""游戏启动 / 崩溃检测 / 崩溃日志（APIRouter 路由）。"""
import json
import logging
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

# Fatshark 日志根目录：Steam 版与 Xbox app / PC Game Pass（Microsoft Store）版**互不通用**，
#   Steam 版                            %APPDATA%\Fatshark\Darktide
#   Xbox app / PC Game Pass / MS 商店版  %APPDATA%\Fatshark\MicrosoftStore\Darktide
# 两分布可能同时存在（装过两个版本）→ resolve_crash_root() 两候选都查，
# 按「有日志 > 仅目录存在」选优，同分优先 Steam。
# ⚠️ 实验功能：双分布解析目前只经单测覆盖（tools/test_crash_root.py），未在真机 Game Pass 环境实测。
CRASH_DISTRO_STEAM = "steam"
CRASH_DISTRO_STORE = "microsoft_store"
CRASH_DISTRO_LABELS = {CRASH_DISTRO_STEAM: "Steam 版", CRASH_DISTRO_STORE: "Xbox / Game Pass 版"}
CRASH_ROOT_CANDIDATES = (
    (CRASH_DISTRO_STEAM, ("Darktide",)),
    (CRASH_DISTRO_STORE, ("MicrosoftStore", "Darktide")),
)


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
    # 启动前先做原版启动器那一步：校验/重建着色器缓存（DMM 直接起 Darktide.exe 会跳过它）。
    # 失败只记日志，绝不阻止启动 —— 见 core/shader.py 顶部说明。
    shader_info = {}
    try:
        from core import shader as _shader
        shader_info = _shader.prepare_for_launch()
    except Exception as e:
        logging.getLogger("dmm.shader").warning("着色器缓存步骤异常，照常启动: %s", e)

    env = os.environ.copy()
    env["SteamAppId"] = APP_ID
    try:
        proc = subprocess.Popen([str(exe)] + GAME_LAUNCH_ARGS, cwd=str(exe.parent),
                                env=env, creationflags=patch.CREATE_NO_WINDOW)
        # 保存句柄：崩溃检测时可读取退出码（异常退出码为负值，如 0xC0000005）
        global _launched_game
        _launched_game = {"proc": proc, "pid": proc.pid}
        msg = "游戏启动中，请稍候…"
        if shader_info.get("ok"):
            try:
                from core import shader as _s
                msg = _s.summary_text(shader_info) + "，游戏启动中…"
            except Exception:
                pass
        return {"ok": True, "message": msg, "shader": shader_info}
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


def crash_root_candidates() -> list:
    """候选日志根目录 [(分布, 路径)]，按优先级排序（只看路径，不判断存在性）"""
    appdata = Path(os.environ.get("APPDATA", ""))
    return [(distro, appdata / "Fatshark" / Path(*parts)) for distro, parts in CRASH_ROOT_CANDIDATES]


def _crash_root_score(root: Path) -> int:
    """候选目录评分：有控制台日志 2 分 + 有 crash_dumps 目录 1 分（仅存在目录记 0 分）"""
    score = 0
    if _latest_log_file(root / "console_logs"):
        score += 2
    if (root / "crash_dumps").is_dir():
        score += 1
    return score


def resolve_crash_root():
    """当前有效的日志根目录 (路径, 分布)：Steam / MicrosoftStore 两候选都查，
    取有日志者优先、仅目录存在者次之（同分优先 Steam）；两个都没有返回 (None, "")。"""
    best = None
    for idx, (distro, root) in enumerate(crash_root_candidates()):
        if not root.is_dir():
            continue
        cand = (_crash_root_score(root), -idx, distro, root)  # -idx：同分时靠前的候选胜出
        if best is None or cand[:2] > best[:2]:
            best = cand
    return (None, "") if best is None else (best[3], best[2])


def crash_root_hint() -> str:
    """未找到日志时的提示：把两个分布的实际路径都列出来"""
    return "；".join(f"{CRASH_DISTRO_LABELS.get(d, d)} {p}" for d, p in crash_root_candidates())


def crash_root_report() -> list:
    """各候选日志根目录的诊断明细（写 app.log / 进导出报告，供 Xbox·Game Pass 用户回报问题）"""
    rows = []
    for distro, root in crash_root_candidates():
        console = _latest_log_file(root / "console_logs")
        dumps_dir = root / "crash_dumps"
        try:
            dumps = len([f for f in dumps_dir.iterdir() if f.is_file()]) if dumps_dir.is_dir() else 0
        except Exception:
            dumps = -1  # 枚举失败（权限等）
        rows.append({
            "distro": distro,
            "label": CRASH_DISTRO_LABELS.get(distro, distro),
            "path": str(root),
            "exists": root.is_dir(),
            "console": console["name"] if console else None,
            "console_time": console["time"] if console else None,
            "dumps": dumps,
            "score": _crash_root_score(root),
        })
    return rows


def crash_root_diagnosis() -> str:
    """日志目录探测诊断摘要（单行，写 app.log）：逐候选标存在/日志/转储/评分 + APPDATA 实际值。
    APPDATA 一定要留——商店版日志路径全挂在它下面，被重定向（域账号 / OneDrive）时最难看出的就是这个。"""
    parts = []
    for r in crash_root_report():
        parts.append(
            f"{r['label']}={r['path']}（{'存在' if r['exists'] else '缺失'}"
            f"，控制台日志={r['console'] or '无'}，转储={r['dumps']}个，评分={r['score']}）")
    return "；".join(parts) + f" | APPDATA={os.environ.get('APPDATA', '')}"


_last_probe_sig = None  # 上次留痕内容：环境没变就不重复写，app.log 保持可读


def log_crash_root_probe(reason: str, root=None, distro: str = "") -> None:
    """把日志目录探测结果写进 app.log（★ Xbox / PC Game Pass 用户回报问题时直接发 app.log 即可定位）。

    命中 → INFO 一行（哪个分布 + 路径）；未命中 → WARNING，附全部候选的存在性/日志数/评分与 APPDATA。
    相同环境重复触发只记一次（用户反复点「打开控制台日志文件夹」不会刷屏）。"""
    global _last_probe_sig
    diag = crash_root_diagnosis()
    sig = f"{root}|{distro}|{diag}"
    if sig == _last_probe_sig:
        return
    _last_probe_sig = sig
    log = logging.getLogger()
    if root is None:
        log.warning(f"日志目录探测失败 | 触发={reason} | 已查候选：{diag}")
    else:
        log.info(f"日志目录探测 | 触发={reason} | 命中={CRASH_DISTRO_LABELS.get(distro, distro)} {root}")


@router.get("/api/crash_logs")
def api_crash_logs():
    """崩溃排查信息：console_logs（教程说的控制台文本日志）+ crash_dumps 最新文件。
    日志根目录按分布解析（Steam / Xbox·Game Pass，实验功能），见 CRASH_ROOT_CANDIDATES。"""
    root, distro = resolve_crash_root()
    if root is None:
        log_crash_root_probe("GET /api/crash_logs（崩溃弹窗 / 关于页）")
        return {"ok": False, "error": f"未找到 Fatshark 游戏日志目录（已查 {crash_root_hint()}）"}
    log_crash_root_probe("GET /api/crash_logs（崩溃弹窗 / 关于页）", root, distro)
    return {
        "ok": True,
        "dir": str(root),
        "distro": distro,                                    # 日志来自哪个分布：steam / microsoft_store
        "console": _latest_log_file(root / "console_logs"),  # 控制台日志（文本，可直接看报错）
        "latest": _latest_log_file(root / "crash_dumps"),    # 崩溃转储（.dmp 二进制）
    }


@router.post("/api/crash_logs/open")
def api_crash_logs_open():
    """打开排查日志目录：优先 console_logs（文本控制台日志），其次 crash_dumps，最后根目录"""
    root, distro = resolve_crash_root()
    if root is None:
        log_crash_root_probe("POST /api/crash_logs/open（打开日志文件夹）")
        return {"ok": False, "error": f"未找到 Fatshark 游戏日志目录（已查 {crash_root_hint()}）"}
    log_crash_root_probe("POST /api/crash_logs/open（打开日志文件夹）", root, distro)
    label = CRASH_DISTRO_LABELS.get(distro, distro)  # 提示里带上分布，避免用户看错版本的日志
    for name in ("console_logs", "crash_dumps"):
        target = root / name
        if not target.is_dir():
            continue
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
            hint = "（文本日志，可直接用记事本打开看报错）" if name == "console_logs" else "（.dmp 二进制转储，需专业工具分析）"
            return {"ok": True, "message": f"已打开 {label} {name} 目录 {hint}"}
        except Exception as e:
            return {"ok": False, "error": f"打开失败: {e}"}
    try:
        os.startfile(str(root))
        return {"ok": True, "message": f"已打开 {label} Fatshark 游戏日志目录"}
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

# 真错误判定：crashify-exception 块内 / attempt 类 Lua 错误 / 明确的 error 行
# （排除 ParameterResolver/ErrorCodes 等 INFO 噪声与 Unit childs 等引擎清理警告）
LOG_ERROR_PATTERN = re.compile(
    r'(?i)(\[error\]|\[lua\]\s*error|attempt to (call|index|perform|get|concat)|'
    r'stack traceback|nil value \(field|undefined|exception.*\.lua|'
    r'lua.*exception|crashify-exception)'
)
LOG_WARN_PATTERN = re.compile(r'(?i)(^|\s)(warning|warn):|\[warning\]|unhandled cache|has still childs|orphaned unit')

# 明确无害的“伪错误”行（关键词命中 error 但实际是 INFO/说明）：整体仍标 ok
LOG_FALSE_ERROR = re.compile(
    r'(?i)(exceptions will be handled|error_codes_crashifyreport|errorcode|'
    r'erroronempty|is_error:|error_code|error_codes|has still childs|'
    r'orphaned unit|dlss failed|unlink them before destroying)'
)

MOD_PATH_RE = re.compile(r'(?:scripts[/\\]mods[/\\]|\.\./mods/)([A-Za-z0-9_.\-]+)')
# 行内 mod 自报标记：DMF 系 mod 的日志普遍形如
#   "17:02:01.406 [Lua] [MOD][guarantee_weapon_swap][ERROR] (hook_safe): trying to hook ..."
# 这是**比路径更直接**的归属信号（实测 8 份真实日志里路径式命中 0 条、该标记 8 条）
MOD_TAG_RE = re.compile(r'\[MOD\]\[([^\]]+)\]')
# 「hook 目标不存在」= 该 mod 与当前游戏版本不兼容的典型特征，最值得提示玩家
HOOK_MISSING_RE = re.compile(r"trying to hook [^\n]*?doesn'?t exist", re.I)

# callstack 帧行（逐行匹配，避免跨行贪婪）：
#   形如 "  [3] @scripts/ui/xxx.lua:569: in function func" 或
#   "  [4] ./../mods/SpecialsTracker/scripts/mods/SpecialsTracker/SpecialsTracker.lua:651: in function func"
FRAME_RE = re.compile(r'\s*\[(\d+)\]\s*(?:@)?\s*((?:\./)?(?:\.\./mods/|scripts/|@scripts/)[^\s:]+):(\d+)(?::\s*in (?:function|method|field) ([\w.]+))?')
# 帧路径里若含 mods/ 则归属 mod，否则算游戏本体；dmf/base 单独标记


def _frame_owner(path: str) -> dict:
    """帧归属：{kind: 'mod'|'dmf'|'game', mod: 名称或 None, file: 短路径}"""
    m = MOD_PATH_RE.search(path)
    if m:
        mod = m.group(1)
        kind = 'dmf' if mod.lower() in ('dmf', 'base') else 'mod'
        return {'kind': kind, 'mod': None if kind == 'dmf' else mod, 'file': path}
    # 游戏本体：scripts/ 开头（无 mods/）或 mod_loader
    if path.startswith('scripts/') or 'mod_loader' in path or path.startswith('@scripts'):
        return {'kind': 'game', 'mod': None, 'file': path}
    return {'kind': 'game', 'mod': None, 'file': path}


def classify_log_line(ln: str) -> str:
    """日志行分类：err（真错误）/ warn（警告）/ ok（通常）。
    关键词噪声过滤：命中 error 但属于已知无害模式（INFO 说明/引擎清理/后端 error_code）不标红。"""
    if LOG_FALSE_ERROR.search(ln):
        return 'ok'
    if LOG_ERROR_PATTERN.search(ln):
        return 'err'
    if LOG_WARN_PATTERN.search(ln):
        return 'warn'
    return 'ok'


def parse_crashify_blocks(content: str) -> list:
    """解析日志中的 <<crashify-exception>> 块，提取诊断信息。
    返回 [{system, message, mods[], frames[], line, summary}]；无异常块返回 []。
    frames：callstack 逐帧 [{idx, kind: mod|dmf|game, mod, file, line, fn}]，
            kind=mod 的帧就是玩家要排查的 mod 参与点。"""
    out = []
    # 块起点：<<crashify-exception>>，块内容到 <</crashify-exception>> 结束（可跨行）
    for m in re.finditer(r'<<crashify-exception>>(.*?)<</crashify-exception>>', content, re.S):
        block = m.group(1)
        sys_m = re.search(r'<<system>>(.*?)<</system>>', block, re.S)
        msg_m = re.search(r'<<message>>(.*?)<</message>>', block, re.S)
        system = (sys_m.group(1).strip() if sys_m else '') or '未知系统'
        message = (msg_m.group(1).strip() if msg_m else '') or ''
        # callstack 逐帧：对 block 按行匹配（帧行格式固定，逐行解析无跨行问题）
        frames = []
        mods = []
        seen_mods = set()
        for bline in block.splitlines():
            fm = FRAME_RE.search(bline)
            if not fm:
                continue
            idx = int(fm.group(1))
            path = fm.group(2).replace('\\', '/')
            line = int(fm.group(3))
            fn = fm.group(4) or ''
            owner = _frame_owner(path)
            frames.append({'idx': idx, 'kind': owner['kind'], 'mod': owner['mod'],
                           'file': owner['file'], 'line': line, 'fn': fn})
            if owner['kind'] == 'mod' and owner['mod'] not in seen_mods:
                seen_mods.add(owner['mod'])
                mods.append(owner['mod'])
        # 行号：内容在原文的偏移 -> 行号
        line_no = content[:m.start()].count('\n') + 1
        out.append({
            'kind': 'exception',
            'system': system,
            'message': message[:500],
            'mods': mods,
            'frames': frames,
            'line': line_no,
            'summary': _diag_summary(system, message, mods),
        })
    return out


NATIVE_ERR_RE = re.compile(r'<<(?:Lua|Script) Error>>(.*?)<</(?:Lua|Script) Error>>', re.S)
LUA_STACK_RE = re.compile(r'<<Lua Stack>>(.*?)<</Lua Stack>>', re.S)
ERR_CONTEXT_RE = re.compile(r'<<Error Context>>(.*?)<</Error Context>>', re.S)

REDACT_RES = [
    (re.compile(r'(machine_id\s*=\s*)\S+'), r'\1<hidden>'),
    (re.compile(r'(steam_id\s*=\s*)\S+'), r'\1<hidden>'),
    (re.compile(r'(steam_user_name\s*=\s*)\S+'), r'\1<hidden>'),
]
MAX_EXPORT_DUMPS = 5
# 导入旧日志时的分析窗口（字符）。⚠️ 取的是**末尾**：玩家要看的永远是最近的崩溃/报错。
# 早期实现取开头，实测一份 3.0MB 真实日志（32,378 行）只剩 6 条诊断，全文有 44 条 —— 丢 86%。
MAX_ANALYZE_CHARS = 2_000_000


def redact_log_text(text: str) -> str:
    """导出前脱敏：抹掉 machine_id / steam_id / steam_user_name 再发给他人"""
    for rx, rep_s in REDACT_RES:
        text = rx.sub(rep_s, text)
    return text


def parse_native_crash_blocks(content: str) -> list:
    """解析游戏原生致命崩溃：<<Lua Error>> / <<Script Error>> + <<Lua Stack>>。

    这是真崩溃（会落 crash_dumps/*.dmp）的格式，与 crashify 软异常的
    <<crashify-exception>> 块不同。两者都要覆盖，否则玩家最需要的那类崩溃会漏。
    """
    out = []
    seen = set()
    for m in NATIVE_ERR_RE.finditer(content):
        message = m.group(1).strip()
        if not message:
            continue
        system = ''
        ctx = ERR_CONTEXT_RE.search(content, m.end(), m.end() + 4000)
        if ctx:
            first = ctx.group(1).strip().splitlines()
            system = first[0].strip()[:80] if first else ''
        key = (message[:200], system)
        if key in seen:
            continue
        seen.add(key)
        frames = []
        mods = []
        seen_mods = set()
        sm = LUA_STACK_RE.search(content, m.end())
        if sm:
            for bline in sm.group(1).splitlines():
                fm = FRAME_RE.search(bline)
                if not fm:
                    continue
                idx = int(fm.group(1))
                path = fm.group(2).replace(chr(92), '/')
                line = int(fm.group(3))
                fn = fm.group(4) or ''
                owner = _frame_owner(path)
                frames.append({'idx': idx, 'kind': owner['kind'], 'mod': owner['mod'],
                               'file': owner['file'], 'line': line, 'fn': fn})
                if owner['kind'] == 'mod' and owner['mod'] not in seen_mods:
                    seen_mods.add(owner['mod'])
                    mods.append(owner['mod'])
        line_no = content[:m.start()].count(chr(10)) + 1
        out.append({
            'kind': 'crash',
            'system': system or 'Lua 崩溃',
            'message': message[:500],
            'mods': mods,
            'frames': frames,
            'line': line_no,
            'summary': _diag_summary(system or 'Lua 崩溃', message, mods),
        })
    return out


def parse_crash_blocks(content: str) -> list:
    """统一诊断入口：crashify 软异常 + 游戏原生致命崩溃，按行号排序"""
    items = parse_crashify_blocks(content) + parse_native_crash_blocks(content)
    items.sort(key=lambda d: d.get('line', 0))
    return items


def _stackish(ln: str) -> bool:
    """该行是否像 callstack 帧/续行——用于把「错误行 → 后随栈」的归属限定在紧跟的栈内，
    避免把后面无关 mod 的栈错算到本条错误头上。"""
    s = ln.strip()
    if not s:
        return False
    if FRAME_RE.search(s):
        return True
    if s.startswith('='):
        return True
    return s.startswith('[') and ']' in s[:6]


def _line_mod_owner(ln: str):
    """从**单行**日志里取 mod 归属：先路径式引用，其次 `[MOD][名]` 自报标记。

    框架（dmf / base）一律返回 None —— 与路径式归属同一约定（不算玩家 mod）。"""
    m = MOD_PATH_RE.search(ln)
    if m and m.group(1).lower() not in ('dmf', 'base'):
        return m.group(1)
    t = MOD_TAG_RE.search(ln)
    if t:
        name = t.group(1).strip()
        if name and name.lower() not in ('dmf', 'base'):
            return name
    return None


def aggregate_mod_errors(lines) -> list:
    """按 mod 聚合错误行次数（降序）——玩家据此决定更新/停用哪个 mod。

    归属顺序（先命中先用）：
      ① 错误行自带的路径式引用 `scripts/mods/<名>` / `../mods/<名>`
      ② 错误行自带的 `[MOD][<名>]` 自报标记（DMF 系 mod 普遍用它，比路径更常见）
      ③ 其后 ≤8 行**紧跟的** callstack 续行里的路径式引用
      ④ 都归不到 → 「游戏本体」
    框架（dmf / base）按三种来源都不计入玩家 mod。

    条目额外带 `hook_missing`（该类错误的条数）与 `hint`：命中
    「trying to hook … doesn't exist」说明该 mod 的 hook 目标在当前游戏版本里已不存在，
    即**与游戏版本不兼容** —— 对玩家最有指导意义（更新该作者的 mod 或暂时停用）。
    """
    counts = {}
    hint = re.compile(r'(?i)error|attempt|exception|traceback|nil value|undefined|crash')
    for idx, ln in enumerate(lines):
        if not hint.search(ln):
            continue
        if classify_log_line(ln) != 'err':
            continue
        mod = _line_mod_owner(ln)
        if not mod:
            for j in range(idx + 1, min(len(lines), idx + 9)):
                if not _stackish(lines[j]):
                    break
                m2 = MOD_PATH_RE.search(lines[j])
                if m2:
                    if m2.group(1).lower() not in ('dmf', 'base'):
                        mod = m2.group(1)
                    break
        key = mod or '(游戏本体)'
        e = counts.get(key)
        if e is None:
            e = counts[key] = {'mod': mod, 'count': 0, 'sample': '', 'line': 0,
                               'hook_missing': 0, 'hint': ''}
        e['count'] += 1
        if not e['sample']:
            e['sample'] = ln.strip()[:220]
        e['line'] = idx + 1
        if HOOK_MISSING_RE.search(ln):
            e['hook_missing'] += 1
            e['hint'] = '与当前游戏版本不兼容（hook 目标不存在）：更新该作者的 mod，或暂时停用'
    return sorted(counts.values(), key=lambda x: -x['count'])


ABSORBED_RE = re.compile(r'(?i)\babsorbed\b[^\n]*?\berror\b')


def aggregate_absorbed_errors(lines) -> list:
    """统计「被 mod 主动吞掉的引擎错误」——这类 mod 用 crash-fix 把引擎报错压成 INFO。

    它们在 MOD 错误排行里**天然看不见**（自己没报错），但排查时可能正是它们在掩盖真实问题：
    真实形态 `[Lua] [MOD][Weapon_XP_Farm][INFO] [WXF] crash-fix: absorbed draw error (…): scripts/managers/ui/…`。
    只按 `[MOD][名]` 标记 / 路径式引用归属（框架不计），归不到 mod 的行不统计
    （避免把引擎自己打印的 absorbed 文案算到某个人头上）。"""
    counts = {}
    for idx, ln in enumerate(lines):
        if not ABSORBED_RE.search(ln):
            continue
        mod = _line_mod_owner(ln)
        if not mod:
            continue
        e = counts.get(mod)
        if e is None:
            e = counts[mod] = {'mod': mod, 'count': 0, 'sample': '', 'line': 0}
        e['count'] += 1
        if not e['sample']:
            e['sample'] = ln.strip()[:220]
        e['line'] = idx + 1
    return sorted(counts.values(), key=lambda x: -x['count'])


def _diag_summary(system: str, message: str, mods: list) -> str:
    """异常结论一句话：涉及 mod 优先，其次 message 截断"""
    if mods:
        return '可能涉及: ' + '、'.join(mods[:4]) + (f' 等 {len(mods)} 个 mod' if len(mods) > 4 else '')
    if message:
        return message[:120]
    return system


def enrich_log_rows(lines_text: str) -> tuple:
    """行分类 + 块级诊断，一次扫描"""
    rows = [_row(ln) for ln in lines_text.splitlines()]
    diag = parse_crash_blocks(lines_text)
    return rows, diag

def _row(ln: str) -> dict:
    level = classify_log_line(ln)
    return {"text": ln, "err": level == 'err', "warn": level == 'warn', "level": level}


def _read_latest_console(tail: int = 300) -> dict | None:
    """读最新控制台日志尾部，行分类 + 块级诊断；无日志返回 None"""
    root, _ = resolve_crash_root()
    if root is None:
        return None
    latest = _latest_log_file(root / "console_logs")
    if not latest:
        return None
    p = root / "console_logs" / latest["name"]
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    lines = text.splitlines()[-tail:]
    # 尾部截断可能切掉异常块起始标记：块级诊断用全文（尾部足够覆盖最近异常）
    tail_text = "\n".join(lines)
    rows = [_row(ln) for ln in lines]
    diag = parse_crash_blocks(tail_text)
    window = text.splitlines()[-200000:]        # 排行只看近 20 万行，避免超大日志全量聚合
    return {"file": latest["name"], "time": latest["time"], "lines": rows,
            "total": len(lines), "full_total": len(text.splitlines()), "diag": diag,
            "mod_errors": aggregate_mod_errors(window),
            "absorbed_errors": aggregate_absorbed_errors(window)}


@router.get("/api/crash_logs/read")
def api_crash_logs_read(tail: int = 300):
    """【实验】读取最新控制台日志尾部，疑似错误行 err=True + crashify 异常诊断 diag"""
    data = _read_latest_console(max(50, min(tail, 1000)))
    if data is None:
        root, distro = resolve_crash_root()
        log_crash_root_probe("GET /api/crash_logs/read（日志预览）", root, distro)
        hint = "未找到控制台日志" if root else f"未找到 Fatshark 游戏日志目录（已查 {crash_root_hint()}）"
        return {"ok": False, "error": hint}
    return {"ok": True, **data}


class LogAnalyzeBody(BaseModel):
    name: str = ""
    content: str = ""


def _count_lines(text: str) -> int:
    """行数（不 splitlines，避免对大文本建大列表）——与 splitlines 的计数一致"""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _tail_window(raw: str, limit: int):
    """取文本**末尾** limit 个字符，且从行边界开始。

    返回 (窗口文本, 前面丢弃的行数, 是否发生截断)。丢弃行数用于把窗口内的相对行号
    平移成全文行号 —— 前端按 `full_total - total` 换算定位，两边必须对齐。"""
    if len(raw) <= limit:
        return raw, 0, False
    cut = len(raw) - limit
    nl = raw.find("\n", cut)          # 取 cut 之后第一个换行，避免窗口首行是半行
    if nl < 0:
        return raw, 0, False
    return raw[nl + 1:], raw[:nl + 1].count("\n"), True


def _shift_lines(items: list, dropped: int) -> list:
    """把条目里的相对行号平移到全文行号（原地，返回同一列表）"""
    if dropped:
        for it in items:
            if isinstance(it.get("line"), int):
                it["line"] += dropped
    return items


@router.post("/api/crash_logs/analyze")
def api_crash_logs_analyze(body: LogAnalyzeBody):
    """【实验】分析导入的旧日志文本：行分类 + 块级诊断（**末尾** 2MB / 尾部 3000 行）。

    ⚠️ 取末尾不取开头：崩溃与报错都在日志最后，实测 3.0MB 真实日志取开头只剩 6/44 条诊断。
    大日志会返回 `trimmed` / `trimmed_lines`，前端据此提示「只分析了末尾」。"""
    raw = body.content or ""
    content, dropped, trimmed = _tail_window(raw, MAX_ANALYZE_CHARS)
    lines = content.splitlines()[-3000:]
    rows = [_row(ln) for ln in lines]
    diag = _shift_lines(parse_crash_blocks(content), dropped)
    mod_errors = _shift_lines(aggregate_mod_errors(content.splitlines()), dropped)
    absorbed = _shift_lines(aggregate_absorbed_errors(content.splitlines()), dropped)
    return {"ok": True, "file": (body.name or "导入日志"), "lines": rows,
            "total": len(lines), "full_total": _count_lines(raw), "diag": diag,
            "mod_errors": mod_errors, "absorbed_errors": absorbed,
            "trimmed": trimmed, "trimmed_lines": dropped}


@router.post("/api/crash_logs/export")
def api_crash_logs_export():
    """【实验】导出崩溃报告 zip：最新控制台日志 + 崩溃转储清单 + 报告信息（发作者/群友用）

    定位：给**不懂怎么修**的崩溃玩家一个「打包发给懂行人看」的入口——所以 zip 里只放
    **游戏侧材料**（控制台日志、崩溃转储、报告信息）。管理器自身的诊断（扫了哪些目录、
    命中哪个分布、APPDATA 实际值等）不进这个 zip，它写在 exe 同目录 app.log 里，
    需要时单独发 app.log（见 log_crash_root_probe / state.game_dir_diagnosis）。
    日志根目录按分布解析（Steam / Xbox·Game Pass 实验功能），见 CRASH_ROOT_CANDIDATES。"""
    root, distro = resolve_crash_root()
    log_crash_root_probe("POST /api/crash_logs/export（导出崩溃报告）", root, distro)
    out_dir = state.BASE_DIR / "exports"
    try:
        out_dir.mkdir(exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": f"无法创建导出目录: {e}"}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = out_dir / f"crash_report_{ts}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            latest = _latest_log_file(root / "console_logs") if root else None
            if latest:
                p = root / "console_logs" / latest["name"]
                try:
                    _raw = p.read_text(encoding="utf-8", errors="replace")
                    z.writestr("console_logs/" + latest["name"], redact_log_text(_raw))
                except Exception:
                    pass
            dump_count = 0
            dumps = root / "crash_dumps" if root else None
            if dumps is not None and dumps.is_dir():
                for f in sorted(dumps.iterdir(), key=lambda x: x.stat().st_mtime,
                                reverse=True)[:MAX_EXPORT_DUMPS]:
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
                "日志目录": str(root) if root else None,
                "日志目录分布": CRASH_DISTRO_LABELS.get(distro, "-"),
                "最新控制台日志": latest["name"] if latest else None,
                "崩溃转储文件数": dump_count,
            }
            z.writestr("report_info.json", json.dumps(info, ensure_ascii=False, indent=2))
    except Exception as e:
        return {"ok": False, "error": f"导出失败: {e}"}
    return {"ok": True, "path": str(zip_path), "name": zip_path.name}
