# -*- coding: utf-8 -*-
"""mod/整合包导入、归档备份、导出（纯逻辑，无 FastAPI 依赖）。"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from core import state
from core import patch
from core.load_order import enabled_names, read_load_order, write_load_order, backup_load_order
from core.mods import load_my_mods, is_my_mod, deploy_my_mod, sync_my_mods_to_library
from core.state import load_config
from core.mods import invalidate_scan_cache


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


# 解压调用计数：只为"一个包到底被解压几次"提供可断言的事实（单元测试与 --e2e 用）
EXTRACT_CALLS = 0


def extract_archive(data: bytes, filename: str, out_dir: Path) -> str | None:
    """按格式解压到 out_dir；返回 None 成功，否则错误信息"""
    global EXTRACT_CALLS
    EXTRACT_CALLS += 1
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
                                   creationflags=patch.CREATE_NO_WINDOW)
            else:  # UnRAR.exe / WinRAR.exe
                r = subprocess.run([tool, "x", "-y", "-o+", tmp_path, str(out_dir) + "\\"],
                                   capture_output=True, text=True, timeout=180,
                                   creationflags=patch.CREATE_NO_WINDOW)
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


def import_mod_archive(filename: str, data: bytes, force_mod: bool = False,
                       overwrite_mine: bool = False) -> dict:
    if not state.MODS_DIR.is_dir():
        return {"file": filename, "ok": False, "error": "mods 目录不存在，请先设置游戏目录"}
    # 先试**不解压**判定：zip/7z 的目录索引里就能看出是不是整合包。
    # 这一步以前会把整合包整个解压一遍（用户报的"解压两次/三次"其中一次就在这），现在直接返回。
    if not force_mod:
        kind0 = classify_archive_index(data, filename)
        if kind0 == "pack":
            return {"file": filename, "ok": False, "is_pack": True,
                    "error": "检测到整合包结构，请用「导入整合包」流程"}
        if kind0 == "ambiguous":
            return {"file": filename, "ok": False, "ambiguous": True,
                    "error": "检测到 mods/ 目录结构，无法确定是单个 mod 还是整合包"}
        if kind0 is None:
            # 索引读不到（rar / tar / 未知扩展名…）→ 解压一次到**暂存区**，判定结果连 token 一起回前端，
            # 让整合包流程直接复用这次解压。**这是用户 2026-10-10 报的"仍然解压两次"的根源**：
            # 老写法在这里整包解压只为判定类型，判定为整合包后前端又 stage 一次 → 一个包解两遍。
            return _classify_by_staged_extract(filename, data, overwrite_mine)
    with _TempExtractDir() as td:
        out = Path(td) / "out"
        out.mkdir()
        err = extract_archive(data, filename, out)
        if err:
            return {"file": filename, "ok": False, "error": err}
        return import_mod_from_dir(out, filename, force_mod=force_mod, overwrite_mine=overwrite_mine)


def _classify_by_staged_extract(filename: str, data: bytes, overwrite_mine: bool = False) -> dict:
    """索引读不到时：解压一次到暂存区 → 判定类型。

    · 整合包 / 模棱两可 → 保留暂存并回传 `staged_token`（前端把它交给 /api/pack/import 复用，不再解压第二遍）
    · 单个 mod → 直接用这份已解压目录导入，然后释放暂存
    """
    _prune_stages()
    token = uuid.uuid4().hex
    base = _PACK_STAGE_ROOT / token
    out = base / "out"
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"file": filename, "ok": False, "error": f"暂存目录不可用: {e}"}
    err = extract_archive(data, filename, out)
    if err:
        state.safe_rmtree(base, ignore_errors=True)
        return {"file": filename, "ok": False, "error": err}
    kind = classify_archive(out)
    if kind in ("pack", "ambiguous"):
        _PACK_STAGES[token] = {"dir": base, "name": filename, "size": len(data), "ts": time.time()}
        res = {"file": filename, "ok": False, "is_pack": kind == "pack",
               "ambiguous": kind == "ambiguous", "staged_token": token,
               "error": "检测到整合包结构，请用「导入整合包」流程"}
        if kind == "pack":
            p = _preview_from_dir(filename, out)
            p["staged_token"] = token
            p["staged"] = True
            res["preview"] = p
        return res
    try:
        return import_mod_from_dir(out, filename, overwrite_mine=overwrite_mine)
    finally:
        state.safe_rmtree(base, ignore_errors=True)


def import_mod_from_dir(out: Path, filename: str, force_mod: bool = False,
                        overwrite_mine: bool = False) -> dict:
    """从已解压目录导入 mod（压缩包解压后 / 用户选择的文件夹共用）。"""
    if not state.MODS_DIR.is_dir():
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

    target = state.MODS_DIR / real_name
    if target.exists():
        if is_my_mod(real_name) and not overwrite_mine:
            # 撞名且对方是玩家自己标记的「我的 mod」：绝不擅自顶掉用户的作品，交前端确认
            return {"file": filename, "ok": False, "is_my_mod_conflict": True, "name": real_name,
                    "error": f"「{real_name}」是你标记的「我的 mod」——导入会用别人的同名版本覆盖你自己的，已暂停"}
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
    invalidate_scan_cache()  # mods 目录内容变了，强制下次扫描重建元数据缓存
    return {"file": filename, "ok": True, "mod": real_name, "added_to_load_order": added}


# ---------------------------------------------------------------- 整合包识别

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


# ---------------------------------------------------- 不解压判定（省掉"为了判断类型"的解压）
def _archive_index_names(data: bytes, filename: str) -> list[tuple[str, bool]] | None:
    """只读压缩包**目录索引**，返回 [(相对路径, 是否目录)]；读不到索引（rar 等）返回 None。

    动机（2026-10-06 用户反馈）：走「＋ 导入」选到整合包时，后端为了判断"这是不是整合包"
    会把整个包解压一遍（`import_mod_archive` → `classify_archive`），随后预览又解压、
    真正导入再解压 —— 一个包被解了三遍。zip/7z 的索引里已经能看出结构，不必解压。"""
    low = (filename or "").lower()
    try:
        if low.endswith(".zip") or low.endswith(".zipx"):
            import io as _io
            with zipfile.ZipFile(_io.BytesIO(data)) as z:
                return [(n, n.endswith('/')) for n in z.namelist()]
        if low.endswith(".7z"):
            import io as _io
            import py7zr
            with py7zr.SevenZipFile(_io.BytesIO(data)) as z:
                return [(n, n.endswith('/')) for n in z.getnames()]
        if low.endswith((".tar", ".gz", ".tgz", ".bz2", ".xz")):
            # tar 家族也能只读索引；成员类型里带目录标记
            import io as _io
            import tarfile
            with tarfile.open(fileobj=_io.BytesIO(data)) as t:
                return [(m.name, m.isdir()) for m in t.getmembers()]
    except Exception:
        return None
    return None


def classify_archive_index(data: bytes, filename: str) -> str | None:
    """**不解压**判定压缩包类型：'mod' | 'pack' | 'ambiguous'；读不到索引时返回 None（调用方再解压判定）。

    规则与 `classify_archive()`（基于解压结果）保持一致，两边都改了才算改。"""
    names = _archive_index_names(data, filename)
    if names is None:
        return None
    files = {n.strip('/') for n, is_dir in names if not is_dir and n.strip('/')}
    dirs = {n.strip('/') for n, is_dir in names if is_dir and n.strip('/')}
    # 归档里**常常没有独立的目录条目**（Python zipfile.writestr 就不写）→ 从文件路径补出目录集合，
    # 否则会看不到 mods/ 而把整合包误判成单个 mod
    for f in list(files):
        parts = f.split('/')[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add('/'.join(parts[:i]))
    tops = {f.split('/')[0] for f in files} | {d.split('/')[0] for d in dirs}
    prefix = ""
    if len(tops) == 1:                       # 与 locate_pack_root 同规则：只套一层目录则下钻
        t = next(iter(tops))
        if f"{t}/mods" in dirs or f"{t}/binaries/mod_loader" in files \
                or any(n.startswith(f"{t}/bundle/") and n.endswith(".patch_999") for n in files):
            prefix = f"{t}/"

    def is_dir_(p: str) -> bool:
        return (prefix + p).strip('/') in dirs

    def is_file_(p: str) -> bool:
        return (prefix + p).strip('/') in files

    if not (is_dir_("mods") or is_file_("binaries/mod_loader")
            or (is_dir_("bundle") and any(n.startswith(prefix + "bundle/") and n.endswith(".patch_999")
                                          for n in files))):
        return "mod"                          # 不是整合包结构 → 按单个 mod 处理（才需要解压）
    if is_dir_("mods"):
        if is_dir_("mods/base") or is_dir_("mods/dmf"):
            return "pack"
        if is_file_("binaries/mod_loader"):
            return "pack"
        if any(n.startswith(prefix + "bundle/") and n.endswith(".patch_999") for n in files):
            return "pack"
        mod_names = {n[len(prefix) + 5:].split('/')[0] for n in (dirs | files)
                     if n.startswith(prefix + "mods/") and len(n[len(prefix) + 5:].split('/')) >= 2}
        mod_names = {m for m in mod_names if m}
        if len(mod_names) <= 1:
            return "pack" if is_file_("mods/mod_load_order.txt") else "ambiguous"
    return "pack"


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
        if not d.is_dir() or d.name in state.SYSTEM_MODS or ".bak_" in d.name:
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
    """只读预览整合包（**会解压一次，用完即删**）。前端新流程请用 `preview_staged_pack`：
    它把解压结果暂存起来，供随后真正导入时复用，避免同一个包解压两遍、上传两遍。"""
    with _TempExtractDir() as td:
        out = Path(td) / "out"
        out.mkdir()
        err = extract_archive(data, filename, out)
        if err:
            return {"file": filename, "ok": False, "error": err}
        return _preview_from_dir(filename, out)


# ---------------------------------------------------------------- 整合包暂存区
# 背景（2026-10-06 用户反馈"导入别人的整合包触发了两次解压缩"）：
# 旧流程 = 预览解压一次（且包体走 base64 上传，体积 +33%）+ 导入再解压一次。
# 新流程 = /api/pack/stage 上传一次、解压一次 → 返回 token；/api/pack/import 带 token 直接复用，
# 不再重复上传与解压。token 只在本次会话内有效，30 分钟未用即清理。
_PACK_STAGE_ROOT = Path(tempfile.gettempdir()) / "dmm_pack_stage"
_PACK_STAGE_TTL = 30 * 60
_PACK_STAGES: dict = {}          # token -> {"dir": Path, "name": str, "size": int, "ts": float}


def _drop_stage(token: str) -> None:
    st = _PACK_STAGES.pop(token, None)
    if st:
        state.safe_rmtree(st["dir"], ignore_errors=True)     # 只读文件也能删（见 state._force_writable）


def _prune_stages() -> None:
    """清理过期暂存（含进程重启后遗留的目录）"""
    now = time.time()
    for tok in list(_PACK_STAGES):
        st = _PACK_STAGES[tok]
        if now - st["ts"] > _PACK_STAGE_TTL or not st["dir"].is_dir():
            _drop_stage(tok)
    try:
        if _PACK_STAGE_ROOT.is_dir():
            for d in _PACK_STAGE_ROOT.iterdir():
                if d.is_dir() and now - d.stat().st_mtime > _PACK_STAGE_TTL:
                    state.safe_rmtree(d, ignore_errors=True)
    except Exception:
        pass


class _TempExtractDir:
    """临时解压目录（替代 tempfile.TemporaryDirectory）：退出时用 safe_rmtree 清。

    必要性：包里可能有只读文件，`TemporaryDirectory` 的清理走的是普通 rmtree，
    删不掉就把整份解压副本留在 %TEMP%（实测踩到过）。"""

    def __init__(self):
        self.path = None

    def __enter__(self) -> str:
        self.path = Path(tempfile.mkdtemp(prefix="dmm_extract_"))
        return str(self.path)

    def __exit__(self, *exc) -> bool:
        if self.path is not None:
            state.safe_rmtree(self.path, ignore_errors=True)
        return False


class _StagedContext:
    """把暂存目录包装成 TemporaryDirectory 那样的上下文：进入给出暂存父目录，退出即删除。"""

    def __init__(self, token: str):
        self.token = token

    def __enter__(self) -> str:
        return str(_PACK_STAGES[self.token]["dir"])

    def __exit__(self, *exc) -> bool:
        _drop_stage(self.token)
        return False


def stage_pack_archive(filename: str, data: bytes) -> dict:
    """上传并**解压一次**到暂存区，返回 token（供预览与随后导入共用）。

    成功后返回 `{ok, token, filename, size, preview}`；失败时清理并返回错误。"""
    _prune_stages()
    token = uuid.uuid4().hex
    base = _PACK_STAGE_ROOT / token
    out = base / "out"
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"ok": False, "error": f"暂存目录不可用: {e}"}
    err = extract_archive(data, filename, out)
    if err:
        state.safe_rmtree(base, ignore_errors=True)
        return {"ok": False, "error": err}
    if not is_pack_like(out):
        state.safe_rmtree(base, ignore_errors=True)
        return {"ok": False,
                "error": "压缩包内没有 mods/ 或加载器文件，不是暗潮整合包（单个 mod 请用「导入 mod」）"}
    _PACK_STAGES[token] = {"dir": base, "name": filename, "size": len(data), "ts": time.time()}
    p = _preview_from_dir(filename, out)
    p["staged_token"] = token
    p["staged"] = True
    return {"ok": True, "token": token, "filename": filename, "size": len(data), "preview": p}


def preview_staged_pack(filename: str, data: bytes) -> dict:
    """预览 = 暂存 + 预览（一次解压），返回带 `staged_token` 的预览结果（兼容旧调用）"""
    r = stage_pack_archive(filename, data)
    if not r.get("ok"):
        return {"file": filename, "ok": False, "error": r.get("error")}
    return r["preview"]


def _preview_from_dir(filename: str, out: Path) -> dict:
    """从**已解压**的目录生成预览（预览逻辑只此一份，避免两处漂移）"""
    if not state.MODS_DIR.is_dir():
        return {"file": filename, "ok": False, "error": "mods 目录不存在，请先设置游戏目录"}
    root = locate_pack_root(out)
    if not is_pack_like(out):
        return {"file": filename, "ok": False,
                "error": "压缩包内没有 mods/ 或加载器文件，不是暗潮整合包（单个 mod 请用「导入 mod」）"}

    src_mods = root / "mods"
    pack_mods = _scan_mods_dir(src_mods) if src_mods.is_dir() else {}

    # 当前 mods
    cur_mods = _scan_mods_dir(state.MODS_DIR)

    diff = diff_mods(pack_mods, cur_mods)
    added, updated, same = diff["added"], diff["updated"], diff["same"]
    # 「我的 mod」不会被移除（原地保留）→ 从"移除"里剔除、单列出来，否则预览会吓人也与实际不符
    mine = set(load_my_mods())
    removed = [n for n in diff["removed"] if n not in mine]
    my_kept = [n for n in diff["removed"] if n in mine]
    # 同名冲突：包里有、也是「我的 mod」→ **不替玩家决定**，把两边信息都给出来让前端逐个问
    # （注意 _scan_mods_dir 的值是版本字符串，不是 dict）
    conflicts = sorted(set(pack_mods) & mine)
    conflict_details = []
    for n in conflicts[:20]:                      # 正常就几个；防御性截断，避免极端情况下遍历过久
        mine_dir, pack_dir = state.MODS_DIR / n, src_mods / n
        conflict_details.append({
            "name": n,
            "mine_version": str(cur_mods.get(n) or ""),
            "pack_version": str(pack_mods.get(n) or ""),
            "mine_kb": max(1, -(-dir_size_bytes(mine_dir) // 1024)) if mine_dir.exists() else 0,
            "pack_kb": max(1, -(-dir_size_bytes(pack_dir) // 1024)) if pack_dir.exists() else 0,
        })

    # 包内清单信息
    has_load_order = (src_mods / "mod_load_order.txt").is_file()
    pack_lo_count = 0
    pack_lo_comments = 0
    if has_load_order:
        try:
            for ln in (src_mods / "mod_load_order.txt").read_text(encoding="utf-8", errors="ignore").splitlines():
                s = ln.strip()
                if not s:
                    continue
                if s.startswith("--"):
                    pack_lo_comments += 1
                else:
                    pack_lo_count += 1
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
        # 包里清单里的注释行数：导入时**不搬**这些注释（用户 2026-10-10：注释太多，减少污染）
        "pack_lo_comments": pack_lo_comments,
        # 包里没有启用清单 → 导入后会**重建**一份（否则 replace 归档掉旧清单后一个 mod 都不启用）
        "will_rebuild_load_order": not has_load_order,
        # 「我的 mod」相关：包内没有的（会被原地保留，不算移除）+ 与包内同名的冲突（**交给玩家逐个决定**）
        "my_kept": my_kept,
        "my_conflicts": conflicts,
        "my_conflict_details": conflict_details,
    }


# 重建清单时写在首行的一句话：说明这份清单是谁生成的（原清单连同注释已归档，不搬运过来）
REBUILT_LO_NOTE = "-- 本清单由 DMM 依据当前 mods 目录重建（原清单已备份到 backups/，需要可找回）"
# 采用整合包作者清单时写在首行的一句话：条目照作者，作者注释不落盘（整份原清单已归档）
AUTHOR_LO_NOTE = "-- 本清单由 DMM 依据整合包作者的清单生成（作者的注释与原始清单已备份到 backups/，需要可找回）"


def import_pack_archive(filename: str, data: bytes, mode: str = "replace",
                       keep_enabled: bool = False, mine_choice: dict | None = None,
                       staged_token: str = "") -> dict:
    """导入整合包：解压（或复用暂存）-> 定位根 -> 备份 -> 合并（replace 先归档旧 mods）-> 返回统计
    mode=replace：旧 mods 整体归档到 backups/pack_backup_<ts>/mods/，mods 始终保持当前包
    mode=merge：增量叠加（同名覆盖备份）
    keep_enabled=True（仅 replace）：换包时保留当前启用中的 mod——新包缺失的自动从归档补回；
        同名但版本不同则返回 pending_conflicts 供前端弹窗决策（本函数不擅自覆盖）。
    mine_choice：**「我的 mod」与包内同名时的逐个决定** `{mod名: 'mine'|'pack'}`，缺省 `'mine'`
        （保留玩家自己的版本）。前端会**逐个问过**再传进来——程序不替玩家决定冲突。
    staged_token：`/api/pack/stage` 返回的暂存标识。带上它就**直接用已解压的暂存目录**，
        既不再上传包体、也不再解压第二遍（旧调用不传 token 时行为不变）。"""
    if not state.is_valid_game_dir(state.GAME_DIR):
        return {"file": filename, "ok": False, "error": "游戏目录无效，请先到「关于」页设置"}
    staged = _PACK_STAGES.get(staged_token) if staged_token else None
    if staged_token and not staged:
        return {"file": filename, "ok": False,
                "error": "整合包暂存已过期，请重新选择压缩包导入"}
    with (_StagedContext(staged_token) if staged else _TempExtractDir()) as td:
        out = Path(td) / "out"
        if not staged:
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
        state.MODS_DIR.mkdir(parents=True, exist_ok=True)

        # 0. 先记下换包前的清单原文：replace 会把 mod_load_order.txt 一起归档搬走，
        #    而**包里没有清单**时我们要靠它重建（见第 2 步）。注释行也要留着（作者/玩家写的说明）。
        prev_lo_text = ""
        try:
            if state.LOAD_ORDER_FILE.is_file():
                prev_lo_text = state.LOAD_ORDER_FILE.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            prev_lo_text = ""
        prev_lo_names = [ln.strip() for ln in prev_lo_text.splitlines()
                         if ln.strip() and not ln.strip().startswith("--")]

        # 0. keep_enabled 快照：记录当前“启用中”的 mod（清单 enabled + 磁盘存在），供换包后补回
        #    （必须在归档前拍，归档后旧目录就没了）
        keep_snapshot = {}
        if mode == "replace" and keep_enabled:
            try:
                lo_names = enabled_names(read_load_order())
            except Exception:
                lo_names = []
            cur_mods = _scan_mods_dir(state.MODS_DIR)
            for n in lo_names:
                if n in cur_mods:
                    keep_snapshot[n] = cur_mods[n]

        # 0a. 「我的 mod」名单 + 管理器库：玩家自研/私装、整合包里没有的那些。
        #     ① 不搬进归档（留在原地）② 换完包按换包前的启用状态补回清单 ③ 包内同名不覆盖我的版本
        #     ④ **换包前先把游戏目录里的当前状态同步进库**（自研 mod 常在游戏目录里改着调试，库里那份可能是旧的）
        mine = set(load_my_mods())
        # 同名冲突的逐个决定：缺省/未指定 = 保留我的（安全项）。前端会逐个问过再传。
        def _take_pack(n: str) -> bool:
            return str((mine_choice or {}).get(n, "mine")).lower() == "pack"
        mine_enabled_before = []
        lib_synced = []
        if mine:
            try:
                mine_enabled_before = [n for n in enabled_names(read_load_order()) if n in mine]
            except Exception:
                mine_enabled_before = []
            try:
                lib_synced = sync_my_mods_to_library().get("stored") or []
            except Exception:
                lib_synced = []

        # 0b. replace 模式：先把现有 mods 整体归档；base/dmf 仅当新包也带同名时才归档
        #    （新包没带则保留旧的，保证框架不缺失）；归档备份统一进 state.BACKUP_DIR
        mine_kept = []
        if mode == "replace":
            src_mods0 = root / "mods"
            pack_has = {d.name for d in src_mods0.iterdir() if d.is_dir()} if src_mods0.is_dir() else set()
            bak_mods = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods"
            bak_mods.mkdir(parents=True, exist_ok=True)
            for item in sorted(state.MODS_DIR.iterdir()):
                if item.name in mine and not _take_pack(item.name):
                    mine_kept.append(item.name)   # 我的 mod（玩家选了保留）：原地不动，永不进归档
                    continue
                if item.is_dir() and item.name in state.SYSTEM_MODS:
                    if item.name not in pack_has:
                        continue  # 新包没有该系统组件，保留旧的
                try:
                    shutil.move(str(item), str(bak_mods / item.name))
                    archived.append(item.name)
                except Exception as e:
                    return {"file": filename, "ok": False, "error": f"归档 {item.name} 失败: {e}"}

        # 1. mods/ 增量合并（跳过 mod_load_order.txt，后面单独处理）
        src_mods = root / "mods"
        mine_pack_conflict = []
        mine_used_pack = []
        pack_names = set()          # 包内带来的 mod 名（重建清单时只补这些，别把玩家磁盘上的都启用）
        for d in sorted(src_mods.iterdir()) if src_mods.is_dir() else []:
            if not d.is_dir():
                continue
            pack_names.add(d.name)
            if d.name.lower() == "mod_load_order.txt":
                continue
            if d.name in mine:
                # 包内有同名且是「我的 mod」→ 按玩家的逐个决定走；没决定就保留我的（绝不自作主张覆盖作品）
                mine_pack_conflict.append(d.name)
                if not _take_pack(d.name):
                    continue
                mine_used_pack.append(d.name)
            target = state.MODS_DIR / d.name
            if target.exists():
                target.rename(_bak_path(target, ts))
                replaced.append(d.name)
            try:
                shutil.copytree(d, target)
            except Exception as e:
                return {"file": filename, "ok": False, "error": f"拷贝 mod {d.name} 失败: {e}"}
            added.append(d.name)

        # 2. mods/mod_load_order.txt：采用整合包作者的推荐清单（**条目照作者，注释不搬**）
        #    用户 2026-10-10 报「重新导入并没有重建清单」：他刚用「重建清单」清掉 412 行作者注释，
        #    一导入又被原样搬回来。所以这里改成：作者的 mod 条目与顺序照抄，`--` 注释与空行不落盘，
        #    整份作者原清单归档到 backups/pack_backup_<ts>/author_mod_load_order.txt（随时可找回）。
        lo_src = src_mods / "mod_load_order.txt"
        lo_rebuilt = []
        lo_author_kept, lo_author_dropped = [], []
        lo_author_comments = 0
        if lo_src.is_file():
            lo_dst = state.MODS_DIR / "mod_load_order.txt"
            try:
                src_text = lo_src.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                src_text = ""
            author_names, comments = [], 0
            for raw in src_text.splitlines():
                s = raw.strip()
                if not s:
                    continue
                if s.startswith("--"):
                    comments += 1
                    continue
                if s not in author_names:          # 作者清单里的重复行去掉
                    author_names.append(s)
            lo_author_comments = comments
            if lo_dst.exists():
                b = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods" / lo_dst.name
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(lo_dst), str(b))
            # 作者原清单整份留档（含注释），随时能翻出作者的说明与原始顺序
            try:
                arch = state.BACKUP_DIR / f"pack_backup_{ts}" / "author_mod_load_order.txt"
                arch.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(lo_src, arch)
            except Exception:
                pass
            try:
                present_now = {d.name for d in state.MODS_DIR.iterdir()
                               if d.is_dir() and d.name not in state.SYSTEM_MODS and ".bak_" not in d.name}
            except OSError:
                present_now = set(author_names)
            lo_author_kept = [n for n in author_names if n in present_now]
            lo_author_dropped = [n for n in author_names if n not in present_now]
            text = "\n".join([AUTHOR_LO_NOTE] + lo_author_kept)
            lo_dst.write_text(text + ("\n" if lo_author_kept else ""), encoding="utf-8")
        else:
            # 包里**没有**清单 → 必须重建一份。否则 replace 把旧清单归档后就什么都不剩，
            # 玩家进游戏会发现一个 mod 都没加载（2026-10-10 用户报「导入的新整合包没有重建
            # mod_load_order」，实验复现：包内无清单时启用数 0）。
            # 规则：① 旧清单里**仍然存在**的 mod 保持原有相对顺序 ② 只补**包内带来的** mod，
            # 按名字排序追加（merge 模式下玩家磁盘上原有的、自己禁用的 mod 不动，别覆盖玩家的选择）
            # ③ 已不存在的条目丢掉（避免幽灵行）
            # ④ **不搬运旧注释**（用户 2026-10-10 拍板）：注释密集的清单多是整合包作者写的说明，
            #    内容是描述**上一个包**的（链接、群号、"哪些 mod 必须放前面"），搬到新清单就是脏数据；
            #    旧清单连着注释一起进 pack_backup 归档，随时可找回。新清单只留一行 DMM 自己的来源说明。
            lo_dst = state.MODS_DIR / "mod_load_order.txt"
            try:
                present = {d.name for d in state.MODS_DIR.iterdir()
                           if d.is_dir() and d.name not in state.SYSTEM_MODS and ".bak_" not in d.name}
            except OSError:
                present = set()
            kept = [n for n in prev_lo_names if n in present]
            fresh = sorted(n for n in pack_names if n in present and n not in kept)
            lo_rebuilt = kept + fresh
            text = "\n".join([REBUILT_LO_NOTE] + lo_rebuilt) + ("\n" if lo_rebuilt else "")
            try:
                lo_dst.write_text(text, encoding="utf-8")
            except Exception as e:
                lo_rebuilt = []
                root_files.append(f"(清单重建失败: {e})")

        # 2a. 「我的 mod」管理器库：① 换包前已把游戏目录里的当前状态同步进库（见 0a）
        #     ② 游戏目录里缺失但库里有 → 从库部署回来（被清空 / 误删 / 换了台机器都能恢复）
        #     ③ 作者清单会整体覆盖玩家清单 → 把换包前**启用中**的「我的 mod」补回清单（文本追加，不打乱作者清单）
        mine_restored_from_lib, mine_missing = [], []
        mine_reenabled = []
        try:
            present = {d.name for d in state.MODS_DIR.iterdir() if d.is_dir()}
            for n in load_my_mods():
                if n in present or not (state.MY_MODS_DIR / n).is_dir():
                    continue
                if deploy_my_mod(n).get("ok"):
                    mine_restored_from_lib.append(n)
                    present.add(n)
        except Exception:
            pass
        if mine_enabled_before and lo_src.is_file():
            try:
                lo_dst = state.MODS_DIR / "mod_load_order.txt"
                have = {e["name"] for e in read_load_order() if e["kind"] == "mod"}
                present = {d.name for d in state.MODS_DIR.iterdir() if d.is_dir()}
                add = []
                for n in mine_enabled_before:
                    if n not in present:
                        mine_missing.append(n)
                    elif n not in have:
                        add.append(n)
                if add:
                    backup_load_order()
                    text = lo_dst.read_text(encoding="utf-8-sig", errors="replace") if lo_dst.exists() else ""
                    if text and not text.endswith("\n"):
                        text += "\n"
                    lo_dst.write_text(text + "\n".join(add) + "\n", encoding="utf-8")
                    mine_reenabled = add
            except Exception:
                pass

        # 2b. keep_enabled：换包后把“我启用但新包没有”的 mod 从归档补回（缺失自动补；版本冲突留待决策）
        pending_conflicts = []
        restored_mods = []
        if keep_snapshot:
            new_mods = _scan_mods_dir(state.MODS_DIR)
            bak_mods = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods"
            # 冲突收集：新包有同名且版本不同（快照有版本才比；新包/旧的任一为空版本都不判冲突）
            for name, old_ver in keep_snapshot.items():
                if name in new_mods and old_ver and new_mods[name] and old_ver != new_mods[name]:
                    pending_conflicts.append({"name": name, "old_version": old_ver,
                                             "new_version": new_mods[name]})
            # 缺失自动补：归档里找同名目录复制回 mods/
            for name in keep_snapshot:
                if name in new_mods:
                    continue
                src_dir = bak_mods / name
                if not src_dir.is_dir():
                    continue
                try:
                    shutil.copytree(src_dir, state.MODS_DIR / name)
                    restored_mods.append(name)
                except Exception:
                    continue  # 单个失败不影响整体
            if restored_mods:
                # 只保留文件、不写清单：作者清单全权，补回的 mod 由用户手动决定是否启用
                invalidate_scan_cache()

        # 3. 加载器相关文件：tools/ 散文件、binaries/mod_loader、bundle/*.patch_999
        #    冲突备份统一进 state.BACKUP_DIR（不在游戏目录留 .bak_ 文件）
        comp_files = []
        tools_src = root / "tools"
        if tools_src.is_dir():
            for f in tools_src.iterdir():
                if f.is_file():
                    comp_files.append((f, state.GAME_DIR / "tools" / f.name))
        for rel in ("binaries/mod_loader",):
            s = root / rel
            if s.is_file():
                comp_files.append((s, state.GAME_DIR / rel))
        b_src = root / "bundle"
        if b_src.is_dir():
            for f in b_src.glob("*.patch_999"):
                comp_files.append((f, state.GAME_DIR / "bundle" / f.name))
        comp_bak = state.BACKUP_DIR / f"pack_backup_{ts}" / "loader"
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
            root_bak = state.BACKUP_DIR / f"root_cleanup_{ts}"
            for f in state.GAME_DIR.iterdir():
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
        # 文案约定（2026-10-06 用户要求）：少用 emoji、少用括号塞提示 —— 补充说明写成正常分句
        msg = f"整合包导入完成：新增/更新 {len(added)} 个 mod"
        if mode == "replace":
            msg = f"整合包已生效：{len(added)} 个 mod 就绪"
            if archived:
                msg += f"；原 {len(archived)} 个旧 mod 已归档到 backups/pack_backup_{ts}/，可随时找回"
            if archived_root:
                msg += f"；根目录 {len(archived_root)} 个说明/脚本文件已归档到 backups/root_cleanup_{ts}/"
        else:
            if replaced:
                msg += f"；覆盖 {len(replaced)} 个，旧版已备份"
        if lo_rebuilt:
            msg += (f"；包内没有启用清单，已重建一份：{len(lo_rebuilt)} 个 mod 已启用"
                    f"（你原来的相对顺序尽量保留，新增的按名字排在后面）")
        if lo_author_kept or lo_author_comments:
            msg += f"；已采用作者清单：{len(lo_author_kept)} 个 mod 按作者顺序启用"
            if lo_author_comments:
                msg += f"，作者的 {lo_author_comments} 行注释与原始清单已备份，需要可找回"
            if lo_author_dropped:
                msg += f"；作者清单里 {len(lo_author_dropped)} 条对应的 mod 包内没有，已移除"
        if restored_mods:
            msg += f"；已保留你之前启用的 {len(restored_mods)} 个 mod 文件。新包没有它们，未自动启用，需要请在列表手动开启"
        if mine_kept:
            msg += f"；你的 mod {len(mine_kept)} 个已原地保留"
            if mine_reenabled:
                msg += f"，其中 {len(mine_reenabled)} 个保持启用"
        if mine_restored_from_lib:
            msg += f"；已从管理器库恢复 {len(mine_restored_from_lib)} 个：{'、'.join(mine_restored_from_lib[:3])}"
        if mine_missing:
            msg += f"；你的 mod {len(mine_missing)} 个在游戏目录和管理器库里都没有：{'、'.join(mine_missing[:3])}"
        if mine_pack_conflict:
            kept_n = [n for n in mine_pack_conflict if n not in mine_used_pack]
            msg += f"；包内有同名 {len(mine_pack_conflict)} 个：{'、'.join(mine_pack_conflict[:3])}。"
            parts = []
            if kept_n:
                parts.append(f"{len(kept_n)} 个保留你的版本，游戏加载的是你的")
            if mine_used_pack:
                parts.append(f"{len(mine_used_pack)} 个按你的选择改用包里版本")
            msg += '；'.join(parts) if parts else '已按你的选择处理'
        if root_files:
            msg += f"；加载器/工具文件 {len(root_files)} 个"
        if patch.is_game_running():
            msg += "；游戏运行中，退出后会自动启用组件"
        else:
            r = patch._run_patch("--patch")
            if r.get("patched"):
                msg += "，DMF 组件已启用，mods 已就绪"
            else:
                msg += f"，但组件未能生效：{r.get('error') or (r.get('output') or '未知原因')[-200:]}"
        pruned = prune_backups()
        if pruned:
            msg += f"（已清理 {len(pruned)} 个旧备份）"
        invalidate_scan_cache()  # mods 目录内容变了，强制下次扫描重建元数据缓存
        return {"file": filename, "ok": True, "message": msg,
                "mods": added, "replaced": replaced, "archived": archived,
                "root_files": root_files, "load_order": lo_src.is_file(), "mode": mode,
                "load_order_rebuilt": lo_rebuilt,
                "author_load_order": {"kept": lo_author_kept, "dropped": lo_author_dropped,
                                      "comments_dropped": lo_author_comments},
                "restored": restored_mods, "pending_conflicts": pending_conflicts, "ts": ts,
                "mine_kept": mine_kept, "mine_reenabled": mine_reenabled,
                "mine_missing": mine_missing, "mine_pack_conflict": mine_pack_conflict,
                "mine_used_pack": mine_used_pack,
                "mine_lib_synced": lib_synced, "mine_restored_from_lib": mine_restored_from_lib}


# ---------------------------------------------------------------- 归档备份

def _fmt_ts(ts: str) -> str:
    """时间戳 20260814_235000 → 2026-08-14 23:50（解析失败原样返回）"""
    try:
        return datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


# 备份保留策略：单类最多保留份数 / backups 总大小上限（字节）
# 默认值只是缺省——实际生效值可在「备份」页设置里改（存 config.json），见 backup_policy()
BACKUP_MAX_PER_TYPE = 10
BACKUP_MAX_TOTAL_BYTES = 5 * 1024 * 1024 * 1024  # 5GB
BACKUP_POLICY_KEY = ("backup_max_per_type", "backup_max_total_mb")

# 备份体积缓存：{bid: (目录 mtime, size)}——一份 353 mod 的备份要遍历上万文件，别每次刷新都重算
_BACKUP_SIZE_CACHE: dict = {}


def dir_size_bytes(p: Path) -> int:
    """目录/文件总字节数（失败返回 0）"""
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except Exception:
        return 0


def cached_backup_size(p: Path) -> int:
    """带缓存的备具体积（目录 mtime 变了就重算）"""
    try:
        key = p.name
        mt = p.stat().st_mtime
        hit = _BACKUP_SIZE_CACHE.get(key)
        if hit and hit[0] == mt:
            return hit[1]
        size = dir_size_bytes(p)
        _BACKUP_SIZE_CACHE[key] = (mt, size)
        return size
    except Exception:
        return 0


def backup_policy() -> dict:
    """当前生效的保留策略（读完即生效，不需重启）"""
    cfg = load_config()
    per = cfg.get("backup_max_per_type")
    mb = cfg.get("backup_max_total_mb")
    try:
        per = int(per) if per not in (None, "") else BACKUP_MAX_PER_TYPE
    except Exception:
        per = BACKUP_MAX_PER_TYPE
    try:
        mb = int(mb) if mb not in (None, "") else BACKUP_MAX_TOTAL_BYTES // (1024 * 1024)
    except Exception:
        mb = BACKUP_MAX_TOTAL_BYTES // (1024 * 1024)
    return {"max_per_type": max(1, min(200, per)), "max_total_mb": max(64, min(102400, mb))}


def save_backup_policy(max_per_type=None, max_total_mb=None) -> dict:
    """写回策略到 config.json（缺省值会随时生效）"""
    cfg = load_config()
    if max_per_type is not None:
        cfg["backup_max_per_type"] = max(1, min(200, int(max_per_type)))
    if max_total_mb is not None:
        cfg["backup_max_total_mb"] = max(64, min(102400, int(max_total_mb)))
    try:
        state.CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入配置失败: {e}"}
    return {"ok": True, **backup_policy()}


def backup_entries() -> list:
    """backups 目录下所有条目：[(name, path, size_bytes)]（旧在前，含清单散文件）"""
    if not state.BACKUP_DIR.is_dir():
        return []
    out = []
    for d in state.BACKUP_DIR.iterdir():
        if d.is_dir() and (d.name.startswith("pack_backup_") or d.name.startswith("dmf_backup_")):
            out.append((d.name, d, cached_backup_size(d)))
        elif d.is_file() and d.name.startswith("mod_load_order.") and d.name.endswith(".bak"):
            out.append((d.name, d, dir_size_bytes(d)))
    out.sort(key=lambda x: x[0])
    return out


def prune_plan(max_per_type=None, max_total_mb=None) -> dict:
    """按策略算出"将会被删掉哪些"（不落盘）——给前端删除前确认用"""
    pol = backup_policy()
    per = pol["max_per_type"] if max_per_type is None else max(1, int(max_per_type))
    mb = pol["max_total_mb"] if max_total_mb is None else max(1, int(max_total_mb))
    cap = mb * 1024 * 1024
    entries = backup_entries()
    doomed = {}
    # 1. 单类数量上限
    for prefix in ("pack_backup_", "dmf_backup_"):
        same = [e for e in entries if e[0].startswith(prefix)]
        for name, _p, sz in same[:-per]:
            doomed[name] = sz
    # 2. 总量上限（在已删掉的基础上继续按最旧删）
    total = sum(sz for n, _p, sz in entries if n not in doomed)
    for name, _p, sz in entries:
        if total <= cap:
            break
        if name in doomed:
            continue
        doomed[name] = sz
        total -= sz
    total_all = sum(sz for _n, _p, sz in entries)
    return {
        "would_remove": [{"id": n, "size_bytes": doomed[n]} for n, _p, _s in entries if n in doomed],
        "total_bytes": total_all,
        "after_bytes": total_all - sum(doomed.values()),
        "max_per_type": per, "max_total_mb": mb,
    }


def prune_backups(dry_run: bool = False):
    """备份清理（策略可配，见 backup_policy）：
    1. 单类上限：pack_backup_/dmf_backup_ 各保留最近 max_per_type 份；
    2. 总量上限：backups 总大小超 max_total_mb 时从最旧开始删，直到达标。
    dry_run=True 时只算不删（返回将删条目）。返回删除（或将删）的条目名列表。"""
    plan = prune_plan()
    names = [x["id"] for x in plan["would_remove"]]
    if dry_run:
        return names
    removed = []
    for name in names:
        target = state.BACKUP_DIR / name
        try:
            if target.is_dir() or (state.is_junction(target) if hasattr(state, "is_junction") else False):
                state.safe_rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
            removed.append(name)
            _BACKUP_SIZE_CACHE.pop(name, None)
        except Exception:
            pass
    return removed


def backup_contents(bid: str) -> dict:
    """看某个备份里有什么（详情弹窗用；只读）。

    pack 备份：逐 mod 列 {name, size_kb, in_game(游戏目录里有没有), enabled(备份清单里开着没)}
    dmf 备份：列文件；清单备份：返回文本内容。"""
    p = state.BACKUP_DIR / Path(bid).name
    if not p.exists():
        return {"ok": False, "error": "备份不存在"}
    if p.is_file():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"ok": False, "error": f"读取失败: {e}"}
        return {"ok": True, "type": "load_order", "id": p.name,
                "items": [], "text": text[:20000], "size_bytes": p.stat().st_size}
    if p.name.startswith("dmf_backup_"):
        items = [{"name": str(f.relative_to(p)), "size_kb": max(1, -(-f.stat().st_size // 1024))}
                 for f in sorted(p.rglob("*")) if f.is_file()]
        return {"ok": True, "type": "dmf", "id": p.name, "items": items,
                "size_bytes": dir_size_bytes(p)}
    mods_dir = p / "mods"
    if not mods_dir.is_dir():
        return {"ok": False, "error": "这个备份里没有 mods 目录"}
    order = set()
    lo = mods_dir / "mod_load_order.txt"
    if lo.is_file():
        try:
            order = {ln.strip() for ln in lo.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if ln.strip() and not ln.strip().startswith("--")}
        except Exception:
            order = set()
    items = []
    for d in sorted(mods_dir.iterdir()):
        if not d.is_dir():
            continue
        items.append({
            "name": d.name,
            "size_kb": max(1, -(-dir_size_bytes(d) // 1024)),
            "enabled": d.name in order,
            "in_game": (state.MODS_DIR / d.name).is_dir(),
        })
    return {"ok": True, "type": "pack", "id": p.name, "items": items,
            "size_bytes": cached_backup_size(p),
            "enabled_count": sum(1 for x in items if x["enabled"])}


def restore_selected_from_backup(bid: str, names, enable: bool = False) -> dict:
    """**从备份里挑单个/几个 mod 恢复**（整包恢复之外的另一种粒度）。

    · 备份里没有的名字 → 记 missing
    · 游戏目录里已有同名 → 先移进 `backups/partial_<ts>/mods/` 再覆盖（绝不直接删用户文件）
    · enable=True → 把恢复的名字补进启停清单末尾（找回丢失的 mod 通常就要它启用）
    """
    p = state.BACKUP_DIR / Path(bid).name
    src_mods = p / "mods"
    if not src_mods.is_dir():
        return {"ok": False, "error": "备份不存在或不是整合包归档"}
    want = [str(n).strip() for n in (names or []) if str(n).strip()]
    if not want:
        return {"ok": False, "error": "没有选择要恢复的 mod"}
    if not state.MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在，请先设置游戏目录"}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    replaced_bak = state.BACKUP_DIR / f"partial_{ts}" / "mods"
    restored, replaced, missing = [], [], []
    for n in want:
        s = src_mods / n
        if not s.is_dir():
            missing.append(n)
            continue
        d = state.MODS_DIR / n
        try:
            if d.exists():
                replaced_bak.mkdir(parents=True, exist_ok=True)
                dst = replaced_bak / n
                if dst.exists() or state.is_junction(dst):
                    state.safe_rmtree(dst, ignore_errors=True)
                shutil.move(str(d), str(dst))
                replaced.append(n)
            shutil.copytree(s, d)
            restored.append(n)
        except Exception as e:
            missing.append(f"{n}({e})")
    enabled = []
    if enable and restored:
        try:
            entries = read_load_order()
            have = {e["name"] for e in entries if e["kind"] == "mod"}
            add = [n for n in restored if n not in have]
            if add:
                backup_load_order()
                text = state.LOAD_ORDER_FILE.read_text(encoding="utf-8-sig", errors="replace") \
                    if state.LOAD_ORDER_FILE.exists() else ""
                if text and not text.endswith("\n"):
                    text += "\n"
                state.LOAD_ORDER_FILE.write_text(text + "\n".join(add) + "\n", encoding="utf-8")
                enabled = add
        except Exception:
            pass
    return {"ok": bool(restored), "restored": restored, "replaced": replaced,
            "missing": missing, "enabled": enabled, "partial_backup": replaced_bak.parent.name if replaced else "",
            "error": "" if restored else "选中的 mod 在备份里都没找到"}


# ---------------------------------------------------------------- 导出

def export_pack(name: str = "", mode: str = "all") -> dict:
    """导出为整合包 zip（不含系统组件 base/dmf）：
    mode=all：打包全部 mod，清单列全部；
    mode=enabled：只打包启用的 mod，清单只列启用的；
    mode=load_order：不打包 mod，只生成干净的 mod_load_order.txt（当前启用的 mod，按顺序）。
    产出可直接再「导入整合包」（自产自销闭环），保存到 exe 旁 exports/ 目录。"""
    if not state.MODS_DIR.is_dir():
        return {"ok": False, "error": "mods 目录不存在，无法导出"}

    mode = mode if mode in ("all", "enabled", "load_order") else "all"
    # 收集 mod 文件夹（排除系统组件）
    all_dirs = sorted(
        (d for d in state.MODS_DIR.iterdir() if d.is_dir() and d.name not in state.SYSTEM_MODS),
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
    name = re.sub(r'[\\/:*?"<>|]', "_", (name or "").strip())
    if not name:
        name = f"整合包_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 导出目录
    export_dir = state.BASE_DIR / "exports"
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
