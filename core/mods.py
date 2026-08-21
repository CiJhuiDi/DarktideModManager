# -*- coding: utf-8 -*-
"""mod 扫描 / 显示名 / 备注 / 依赖解析（纯逻辑，无 FastAPI 依赖）。"""
import json
import os
import re
import time
from pathlib import Path

from core import state
from core.load_order import enabled_names, read_load_order

NOTES_FILE = state.BASE_DIR / "notes.json"
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


_DISPLAY_CACHE = {}  # mod名 -> (locs_mtime, 显示名, 描述, locs_tuple)；locs 缓存避免重复全树搜索


def clean_display_name(s: str) -> str:
    """清理显示名：去富文本颜色标签 {#...}、私用区图标字符、字面反斜杠 xNN 字节转义（Lua 源码风格）"""
    s = re.sub(r'\{#[^}]*\}', '', s)
    s = re.sub(r'[\ue000-\uf8ff]', '', s)
    s = re.sub(r'\\x[0-9a-fA-F]{2}', '', s)
    return s.strip()


def _find_loc_files(d: Path, maxdepth: int = 4) -> list:
    """深度受限查找 localization lua 文件（替代 rglob 全树遍历，HDD 上避免全树 IO）。
    localization 文件一般位于 mod 根 / localization / scripts 下 4 层以内。"""
    out = []
    base = str(d)
    try:
        for root, dirs, files in os.walk(d, topdown=True):
            depth = 0 if root == base else root[len(base):].count(os.sep)
            if depth >= maxdepth:
                dirs[:] = []  # 剪枝：不再深入
            for fn in files:
                if "localization" in fn and fn.endswith(".lua"):
                    out.append(Path(root) / fn)
    except Exception:
        return []
    return out


class _LocInfo:
    __slots__ = ('name', 'desc')
    def __init__(self, name='', desc=''):
        self.name = name
        self.desc = desc


def _read_locale(d: Path) -> _LocInfo:
    """读 localization 文件，提取显示名 + 描述（均优先 zh-cn，其次 en）；带缓存。
    缓存含文件列表：命中后仅 stat 少量文件验证 mtime，不再 rglob 全树遍历。
    注：新增 localization 文件需重启管理器才生效（低频场景，可接受）。"""
    hit = _DISPLAY_CACHE.get(d.name)
    if hit:
        mt, name, desc, locs = hit
        if not locs:
            return _LocInfo(name, desc)
        try:
            if max(f.stat().st_mtime for f in locs) == mt:
                return _LocInfo(name, desc)
        except Exception:
            pass
    locs = _find_loc_files(d)
    if not locs:
        _DISPLAY_CACHE[d.name] = (0, "", "", ())
        return _LocInfo()
    try:
        mt = max(f.stat().st_mtime for f in locs)
    except Exception:
        mt = 0
    info = _LocInfo()
    for loc in locs:
        try:
            if loc.stat().st_size > 512 * 1024:
                continue
            text = loc.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for key, slot in (("mod_name", 'name'), ("display_name", 'name'), ("mod_description", 'desc')):
            if getattr(info, slot):
                continue
            m = re.search(key + r"\s*=\s*\{", text)
            if not m:
                continue
            seg = text[m.end():m.end() + 3000]
            mz = re.search(r'\["zh-cn"\]\s*=\s*"([^"]+)"', seg)
            if mz:
                setattr(info, slot, mz.group(1).strip())
                continue
            me = re.search(r'\ben\s*=\s*"([^"]+)"', seg)
            if me:
                setattr(info, slot, me.group(1).strip())
        if info.name and info.desc:
            break
    info.name = clean_display_name(info.name)
    info.desc = clean_display_name(info.desc)
    _DISPLAY_CACHE[d.name] = (mt, info.name, info.desc, tuple(locs))
    return info


def read_display_name(d: Path) -> str:
    """从 mod 的 localization 文件读取显示名（优先 zh-cn，其次 en）；无则返回空串"""
    return _read_locale(d).name


def read_mod_description(d: Path) -> str:
    """从 mod 的 localization 文件读取描述（优先 zh-cn，其次 en）；无则返回空串"""
    return _read_locale(d).desc


_DEPS_CACHE = {}  # mod名 -> (mod文件mtime, deps)


def parse_mod_deps(mod_dir: Path, content: str | None = None) -> list:
    """解析 .mod 文件声明的库依赖（packages 字段）。
    支持格式：packages = { "lib1", "lib2" } 或 packages = { lib1 = true }。
    注意：packages 里的游戏资源路径（含 / 的 content/wwise 等）是资源声明不是库依赖，跳过。
    返回依赖名列表（小写规范化）。带 mtime 缓存；content 可由调用方传入避免二次读盘。"""
    deps = []
    mt = 0
    try:
        mod_files = list(mod_dir.glob("*.mod"))
        if not mod_files:
            return []
        f = mod_files[0]
        mt = f.stat().st_mtime
        hit = _DEPS_CACHE.get(mod_dir.name)
        if hit and hit[0] == mt:
            return hit[1]
        if content is None:
            content = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'packages\s*=\s*\{([^}]*)\}', content, re.S)
        if not m:
            _DEPS_CACHE[mod_dir.name] = (mt, [])
            return []
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
    if mt:
        _DEPS_CACHE[mod_dir.name] = (mt, out)
    return out


def scan_mods() -> list:
    entries = read_load_order()
    enabled = enabled_names(entries)
    enabled_set = set(enabled)
    seen = set()
    result = []
    # 磁盘元数据走缓存（30s TTL + 目录 mtime 签名自动失效），enabled/order 每次现算
    for meta in _scan_meta():
        name = meta["name"]
        seen.add(name)
        m = dict(meta)
        m["enabled"] = name in enabled_set
        m["order"] = enabled.index(name) if name in enabled_set else None
        result.append(m)

    # 清单里有但磁盘上找不到的（用户删了文件夹）
    for i, n in enumerate(enabled):
        if n not in seen:
            result.append({"name": n, "display_name": "", "version": "", "enabled": True, "order": i, "missing": True, "dependencies": []})

    result.sort(key=lambda x: (x["enabled"] is False, x["order"] if x["order"] is not None else 10**9))
    return result


_META_TTL = 30.0  # 元数据缓存 30s（游戏运行时刷新/轮询不再扫盘；写操作会显式失效 + 目录 mtime 自动失效）
_meta_cache = {"t": 0.0, "sig": None, "mods_dir": None, "data": None}


def invalidate_scan_cache():
    """mods 目录内容变化时调用（导入/删除/恢复备份/改备注后），强制下次扫描重建元数据缓存"""
    _meta_cache["t"] = 0.0


def _mods_dir_sig() -> int:
    """mods 目录变更签名（直接子项增删时 mtime 变化）"""
    try:
        return state.MODS_DIR.stat().st_mtime_ns
    except Exception:
        return -1


def _scan_meta() -> list:
    """扫描磁盘 mod 元数据（显示名/描述/版本/依赖）——重活，带 30s TTL + 目录 mtime 签名缓存。
    enabled/order 不在缓存内（每次从 load_order 现算）。"""
    now = time.monotonic()
    sig = _mods_dir_sig()
    c = _meta_cache
    if (c["data"] is not None and now - c["t"] < _META_TTL
            and c["sig"] == sig and c["mods_dir"] == state.MODS_DIR):
        return c["data"]

    metas = []
    if state.MODS_DIR.is_dir():
        for d in sorted(state.MODS_DIR.iterdir()):
            if not d.is_dir() or d.name in state.SYSTEM_MODS:
                continue
            if ".bak_" in d.name:
                continue  # 导入备份残留目录，不当 mod 显示
            # .mod 文件只读一次：version + packages 一起解析（content 复用避免二次读盘）
            mod_content = ""
            try:
                for f in d.glob("*.mod"):
                    mod_content = f.read_text(encoding="utf-8", errors="ignore")
                    break
            except Exception:
                pass
            version = ""
            if mod_content:
                m = re.search(r'version\s*=\s*"([^"]+)"', mod_content)
                if m:
                    version = m.group(1)
            loc = _read_locale(d)
            metas.append({
                "name": d.name,
                "display_name": loc.name,
                # description 不进列表接口（悬停浮层懒加载走 /api/mods/{name}/detail，减首屏体积）
                "note": load_notes().get(d.name, ""),
                "version": version,
                "missing": False,
                "dependencies": parse_mod_deps(d, mod_content or None),
            })
    c["t"] = now
    c["sig"] = sig
    c["mods_dir"] = state.MODS_DIR
    c["data"] = metas
    return metas
