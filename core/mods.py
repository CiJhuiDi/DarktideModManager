# -*- coding: utf-8 -*-
"""mod 扫描 / 显示名 / 备注 / 依赖解析（纯逻辑，无 FastAPI 依赖）。"""
import json
import re
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


_DISPLAY_CACHE = {}  # mod名 -> (localization mtime, 显示名, 描述)


def clean_display_name(s: str) -> str:
    """清理显示名：去富文本颜色标签 {#...}、私用区图标字符、字面反斜杠 xNN 字节转义（Lua 源码风格）"""
    s = re.sub(r'\{#[^}]*\}', '', s)
    s = re.sub(r'[\ue000-\uf8ff]', '', s)
    s = re.sub(r'\\x[0-9a-fA-F]{2}', '', s)
    return s.strip()


class _LocInfo:
    __slots__ = ('name', 'desc')
    def __init__(self, name='', desc=''):
        self.name = name
        self.desc = desc


def _read_locale(d: Path) -> _LocInfo:
    """读 localization 文件，提取显示名 + 描述（均优先 zh-cn，其次 en）；带缓存"""
    try:
        locs = [f for f in d.rglob("*localization*.lua") if f.is_file()]
    except Exception:
        locs = []
    if not locs:
        return _LocInfo()
    try:
        mt = max(f.stat().st_mtime for f in locs)
    except Exception:
        mt = 0
    hit = _DISPLAY_CACHE.get(d.name)
    if hit and hit[0] == mt:
        return _LocInfo(hit[1], hit[2])
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
    _DISPLAY_CACHE[d.name] = (mt, info.name, info.desc)
    return info


def read_display_name(d: Path) -> str:
    """从 mod 的 localization 文件读取显示名（优先 zh-cn，其次 en）；无则返回空串"""
    return _read_locale(d).name


def read_mod_description(d: Path) -> str:
    """从 mod 的 localization 文件读取描述（优先 zh-cn，其次 en）；无则返回空串"""
    return _read_locale(d).desc


def parse_mod_deps(mod_dir: Path) -> list:
    """解析 .mod 文件声明的库依赖（packages 字段）。
    支持格式：packages = { "lib1", "lib2" } 或 packages = { lib1 = true }。
    注意：packages 里的游戏资源路径（含 / 的 content/wwise 等）是资源声明不是库依赖，跳过。
    返回依赖名列表（小写规范化）。"""
    deps = []
    try:
        for f in mod_dir.glob("*.mod"):
            content = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'packages\s*=\s*\{([^}]*)\}', content, re.S)
            if not m:
                continue
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
            break  # 只读第一个 .mod
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
    return out


def scan_mods() -> list:
    entries = read_load_order()
    enabled = enabled_names(entries)
    enabled_set = set(enabled)
    result = []
    seen = set()

    if state.MODS_DIR.is_dir():
        for d in sorted(state.MODS_DIR.iterdir()):
            if not d.is_dir() or d.name in state.SYSTEM_MODS:
                continue
            if ".bak_" in d.name:
                continue  # 导入备份残留目录，不当 mod 显示
            name = d.name
            seen.add(name)
            version = ""
            try:
                for f in d.glob("*.mod"):
                    m = re.search(r'version\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8", errors="ignore"))
                    if m:
                        version = m.group(1)
                        break
            except Exception:
                pass
            result.append({
                "name": name,
                "display_name": read_display_name(d),
                "description": read_mod_description(d),
                "note": load_notes().get(name, ""),
                "version": version,
                "enabled": name in enabled_set,
                "order": enabled.index(name) if name in enabled_set else None,
                "missing": False,
                "dependencies": parse_mod_deps(d),
            })

    # 清单里有但磁盘上找不到的（用户删了文件夹）
    for i, n in enumerate(enabled):
        if n not in seen:
            result.append({"name": n, "display_name": "", "version": "", "enabled": True, "order": i, "missing": True, "dependencies": []})

    result.sort(key=lambda x: (x["enabled"] is False, x["order"] if x["order"] is not None else 10**9))
    return result
