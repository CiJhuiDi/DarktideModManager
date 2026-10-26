# -*- coding: utf-8 -*-
"""着色器缓存：复刻原版启动器「启动前那一步」（用户 2026-10-06 要求，默认自动跑）。

**原版启动器做了什么**（证据：`%APPDATA%\\Fatshark\\Darktide\\darktide_launcher.log`）：
    [Launcher] Running shader cache builder
    Executing darktide_shader_cache_builder.exe with args:
      -i "<游戏>\\shader_cache\\bundled_shader_cache.hans"
      -o "%APPDATA%\\Fatshark\\Darktide\\shader_cache.hans"
      -device-index 0
    [ShaderCacheBuilder] Choosing adapter: NVIDIA GeForce RTX 3060 Laptop GPU
    [ShaderCacheBuilder] Validating Cache                       ← 缓存有效时到此为止（约 2 秒）
    [ShaderCacheBuilder] Compressing cache original 132711922 → 34083112   ← 需要重建时约 14 秒
    Shader cache builder completed.

`launcher.config` 里**没有**任何着色器选项——对启动器来说这是每次启动的固定步骤，不是可选项。

**DMM 为什么要做**：DMM 直接起 `binaries/Darktide.exe` 绕过启动器，于是这一步被跳过，
着色器缓存不再校验/重建 → 首次进图、换显卡驱动或游戏更新后现场编译着色器，卡顿明显。

**纪律**：这一步只写游戏自己的缓存文件（`%APPDATA%` 下），不碰游戏安装目录；
任何失败都**只记日志、绝不阻止启动**（见 `prepare_for_launch`）。
"""
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter

from core import crash as _crash
from core import state

router = APIRouter()

CREATE_NO_WINDOW = 0x08000000          # 不弹控制台窗口（与 core/patch.py 保持同样的值）
DEFAULT_TIMEOUT = 180                  # 构建器上限：冷缓存时实测约 14 秒，给足余量
SHADER_SUBDIR = "shader_cache"
BUILDER_NAME = "darktide_shader_cache_builder.exe"
BUNDLED_NAME = "bundled_shader_cache.hans"    # 游戏自带的输入缓存（8.9 MB）
OUTPUT_NAME = "shader_cache.hans"             # 输出：游戏真正读的那份


# ------------------------------------------------------------------ 路径解析
def data_dir() -> tuple[Path, str]:
    """当前发行版的 Fatshark 数据目录 (路径, 发行版)。

    复用崩溃日志那套双发行版解析：Steam 版 `%APPDATA%\\Fatshark\\Darktide`，
    Xbox / Game Pass 版 `%APPDATA%\\Fatshark\\MicrosoftStore\\Darktide`。"""
    root, distro = _crash.resolve_crash_root()
    if root:
        return root, distro
    # 兜底：没有日志/转储（全新安装）时，挑一个已存在（或默认第一个）候选
    cands = _crash.crash_root_candidates()
    for distro, p in cands:
        try:
            if p.is_dir():
                return p, distro
        except OSError:
            continue
    return (cands[0][1], cands[0][0]) if cands else (Path(os.environ.get("APPDATA", "")) / "Fatshark" / "Darktide", _crash.CRASH_DISTRO_STEAM)


def builder_path() -> Path:
    """游戏自带的着色器缓存构建器"""
    return Path(state.GAME_DIR) / SHADER_SUBDIR / BUILDER_NAME


def bundled_path() -> Path:
    """游戏自带的输入缓存（构建器的 -i）"""
    return Path(state.GAME_DIR) / SHADER_SUBDIR / BUNDLED_NAME


def output_path() -> Path:
    """构建器的 -o：游戏启动时读的那份缓存"""
    return data_dir()[0] / OUTPUT_NAME


def _stat(p: Path) -> dict:
    try:
        st = p.stat()
        return {"exists": True, "size": st.st_size, "mtime": int(st.st_mtime)}
    except OSError:
        return {"exists": False, "size": 0, "mtime": 0}


def status() -> dict:
    """只读状态：构建器在不在、缓存多大/多久没动过。给界面显示与排错用。"""
    root, distro = data_dir()
    b, o, bund = builder_path(), output_path(), bundled_path()
    bs, os_, bus = _stat(b), _stat(o), _stat(bund)
    return {
        "ok": True,
        "distro": distro,
        "data_dir": str(root),
        "builder": {"path": str(b), **bs},
        "output": {"path": str(o), **os_, "age_seconds": int(time.time() - os_["mtime"]) if os_["exists"] else None},
        "bundled": {"path": str(bund), **bus},
        # 能不能跑这一步：构建器与输入都在就行
        "ready": bool(bs["exists"] and bus["exists"]),
    }


# ------------------------------------------------------------------ 跑构建器
_LINE_PATTERNS = (
    ("adapter", re.compile(r"Choosing adapter:\s*(.+?)\s*$")),
    ("cache_valid", re.compile(r"Cache is valid", re.I)),
    ("compressing", re.compile(r"Compressing cache", re.I)),
    ("compressed", re.compile(r"original size\s+(\d+)\s+new size\s+(\d+)", re.I)),
)


def _parse_lines(text: str) -> dict:
    """从构建器输出里挑出有用的信息（它把进度打在 stdout，启动器就是转发这些行）"""
    info = {"adapter": "", "cache_valid": False, "compressed": None, "lines": []}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(info["lines"]) < 40:
            info["lines"].append(line[:200])
        for key, pat in _LINE_PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            if key == "adapter":
                info["adapter"] = m.group(1).strip()
            elif key == "compressed":
                info["compressed"] = {"original": int(m.group(1)), "new": int(m.group(2))}
            else:
                info[key] = True
    return info


def build(*, timeout: int = DEFAULT_TIMEOUT, runner=None, builder: Path | None = None,
          bundled: Path | None = None, out: Path | None = None, device_index: int = 0) -> dict:
    """跑一次构建器（参数与原版启动器完全一致）。**任何异常都吞掉并返回 ok=False**。

    runner 可注入（测试用）：签名 runner(argv, cwd, timeout) -> 带 returncode/stdout/stderr 的对象。
    """
    b = Path(builder) if builder else builder_path()
    i = Path(bundled) if bundled else bundled_path()
    o = Path(out) if out else output_path()
    res = {"ok": False, "kind": "failed", "seconds": 0.0, "error": "",
           "builder": str(b), "out": str(o), "adapter": "", "out_size_before": _stat(o)["size"]}
    if not b.is_file():
        res.update(kind="no_builder", error=f"找不到构建器: {b}")
        return res
    if not i.is_file():
        res.update(kind="no_input", error=f"找不到输入缓存: {i}")
        return res
    argv = [str(b), "-i", str(i), "-o", str(o), "-device-index", str(device_index)]
    t0 = time.time()
    try:
        if runner is not None:
            cp = runner(argv, str(b.parent), timeout)
        else:
            cp = subprocess.run(argv, cwd=str(b.parent), capture_output=True, timeout=timeout,
                                creationflags=CREATE_NO_WINDOW)
        res["seconds"] = round(time.time() - t0, 1)
        raw = b""
        for attr in ("stdout", "stderr"):
            v = getattr(cp, attr, None)
            if isinstance(v, bytes):
                raw += v
            elif isinstance(v, str):
                raw += v.encode("utf-8", "replace")
        info = _parse_lines(raw.decode("utf-8", "replace").replace("\x00", ""))
        res.update(info)
        rc = getattr(cp, "returncode", None)
        out_stat = _stat(o)
        res["out_size"] = out_stat["size"]
        if rc not in (0, None):
            res.update(kind="failed", error=f"构建器退出码 {rc}")
        elif not out_stat["exists"]:
            res.update(kind="failed", error="构建器没有产出缓存文件")
        elif info["cache_valid"]:
            res.update(ok=True, kind="valid")
        elif info["compressed"] or out_stat["size"] != res["out_size_before"]:
            res.update(ok=True, kind="rebuilt")
        else:
            # 既没报"有效"也没报压缩，但文件在：当作成功（不同版本输出文案可能不一样）
            res.update(ok=True, kind="done")
        return res
    except subprocess.TimeoutExpired:
        res.update(seconds=round(time.time() - t0, 1), kind="timeout",
                   error=f"构建器超过 {timeout} 秒未结束")
        return res
    except Exception as e:                      # 权限、文件被占、构建器崩溃……
        res.update(seconds=round(time.time() - t0, 1), kind="failed", error=f"{type(e).__name__}: {e}")
        return res


def prepare_for_launch() -> dict:
    """启动游戏前调用：跑一次构建器并写 app.log。**绝不抛异常、绝不阻止启动。**"""
    log = logging.getLogger("dmm.shader")
    try:
        r = build()
    except Exception as e:                      # build 内部已兜底，这里是双保险
        r = {"ok": False, "kind": "failed", "error": f"{type(e).__name__}: {e}", "seconds": 0.0}
    kb = (r.get("out_size") or 0) / 1048576
    if r.get("ok"):
        if r.get("kind") == "valid":
            log.info("着色器缓存：校验通过（%.1fs，%.1f MB）", r.get("seconds", 0), kb)
        else:
            log.info("着色器缓存：已重建（%.1fs，%.1f MB%s）", r.get("seconds", 0), kb,
                     f"，{r['compressed']['original']} → {r['compressed']['new']} 字节"
                     if r.get("compressed") else "")
    else:
        log.warning("着色器缓存：这一步没做成（%s），照常启动游戏。%s",
                    r.get("kind"), r.get("error", ""))
    return r


def summary_text(r: dict) -> str:
    """给界面用的一句话说明（少用括号，直接说结论）"""
    kind = (r or {}).get("kind")
    secs = (r or {}).get("seconds") or 0
    if not r or not r.get("ok"):
        return "着色器缓存这步跳过"
    if kind == "valid":
        return f"着色器缓存已校验，用时 {secs} 秒"
    return f"着色器缓存已重建，用时 {secs} 秒"


# ------------------------------------------------------------------ HTTP
@router.get("/api/shader/status")
def api_shader_status():
    """只读：构建器在不在、缓存多大、多久没更新（给界面显示一行状态）"""
    try:
        return status()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
