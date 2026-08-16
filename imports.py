# -*- coding: utf-8 -*-
"""mod/整合包导入、归档备份、导出（纯逻辑，无 FastAPI 依赖）。"""
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import state
import patch
from load_order import enabled_names, read_load_order, write_load_order


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


def import_mod_archive(filename: str, data: bytes, force_mod: bool = False) -> dict:
    if not state.MODS_DIR.is_dir():
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
    """只读预览整合包：解压后对比当前 mods，返回新增/移除/更新/相同（不写任何文件）。"""
    if not state.MODS_DIR.is_dir():
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
        cur_mods = _scan_mods_dir(state.MODS_DIR)

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


def import_pack_archive(filename: str, data: bytes, mode: str = "replace") -> dict:
    """导入整合包：解压 -> 定位根 -> 备份 -> 合并（replace 先归档旧 mods）-> 返回统计
    mode=replace：旧 mods 整体归档到 backups/pack_backup_<ts>/mods/，mods 始终保持当前包
    mode=merge：增量叠加（同名覆盖备份）"""
    if not state.is_valid_game_dir(state.GAME_DIR):
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
        state.MODS_DIR.mkdir(parents=True, exist_ok=True)

        # 0. replace 模式：先把现有 mods 整体归档；base/dmf 仅当新包也带同名时才归档
        #    （新包没带则保留旧的，保证框架不缺失）；归档备份统一进 state.BACKUP_DIR
        if mode == "replace":
            src_mods0 = root / "mods"
            pack_has = {d.name for d in src_mods0.iterdir() if d.is_dir()} if src_mods0.is_dir() else set()
            bak_mods = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods"
            bak_mods.mkdir(parents=True, exist_ok=True)
            for item in sorted(state.MODS_DIR.iterdir()):
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
        for d in sorted(src_mods.iterdir()) if src_mods.is_dir() else []:
            if not d.is_dir():
                continue
            if d.name.lower() == "mod_load_order.txt":
                continue
            target = state.MODS_DIR / d.name
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
            lo_dst = state.MODS_DIR / "mod_load_order.txt"
            if lo_dst.exists():
                b = state.BACKUP_DIR / f"pack_backup_{ts}" / "mods" / lo_dst.name
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(lo_dst), str(b))
            shutil.copy2(lo_src, lo_dst)

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
        if patch.is_game_running():
            msg += "；游戏运行中，退出后会自动补打补丁"
        else:
            r = patch._run_patch("--patch")
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


# ---------------------------------------------------------------- 归档备份

def _fmt_ts(ts: str) -> str:
    """时间戳 20260814_235000 → 2026-08-14 23:50（解析失败原样返回）"""
    try:
        return datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts


# 备份保留策略：单类最多保留份数 / backups 总大小上限（字节）
BACKUP_MAX_PER_TYPE = 10
BACKUP_MAX_TOTAL_BYTES = 5 * 1024 * 1024 * 1024  # 5GB


def prune_backups():
    """备份清理：
    1. 单类上限：pack_backup_/dmf_backup_ 各保留最近 BACKUP_MAX_PER_TYPE 份；
    2. 总量上限：backups 总大小超 BACKUP_MAX_TOTAL_BYTES 时从最旧开始删，直到达标。
    返回删除的条目列表。"""
    if not state.BACKUP_DIR.is_dir():
        return []
    removed = []

    # 1. 单类数量上限（pack / dmf 目录类）
    for prefix in ("pack_backup_", "dmf_backup_"):
        dirs = sorted((d for d in state.BACKUP_DIR.iterdir() if d.is_dir() and d.name.startswith(prefix)),
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
    for d in state.BACKUP_DIR.iterdir():
        if d.is_dir() and (d.name.startswith("pack_backup_") or d.name.startswith("dmf_backup_")):
            entries.append((d.name, _dir_size(d)))
        elif d.is_file() and d.name.startswith("mod_load_order.") and d.name.endswith(".bak"):
            entries.append((d.name, d.stat().st_size))
    entries.sort(key=lambda x: x[0])

    total = sum(sz for _, sz in entries)
    for name, sz in entries:
        if total <= BACKUP_MAX_TOTAL_BYTES:
            break
        target = state.BACKUP_DIR / name
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
