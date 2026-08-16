# -*- coding: utf-8 -*-
"""mod_load_order.txt 读写与规范化（纯逻辑，无 FastAPI 依赖）。"""
import shutil
from datetime import datetime

from core import state


def read_load_order() -> list:
    """解析 mod_load_order.txt 为行条目: {kind: mod|comment|blank, raw, name?}"""
    if not state.LOAD_ORDER_FILE.exists():
        return []
    try:
        text = state.LOAD_ORDER_FILE.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return []
    entries = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            entries.append({"kind": "blank", "raw": raw})
        elif s.startswith("--"):
            entries.append({"kind": "comment", "raw": raw})
        else:
            entries.append({"kind": "mod", "raw": raw, "name": s})
    return entries


def backup_load_order():
    if not state.LOAD_ORDER_FILE.exists():
        return
    state.BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(state.LOAD_ORDER_FILE, state.BACKUP_DIR / f"mod_load_order.{ts}.bak")
    # 只留最近 10 份
    baks = sorted(state.BACKUP_DIR.glob("mod_load_order.*.bak"))
    for old in baks[:-10]:
        old.unlink(missing_ok=True)


def write_load_order(entries: list) -> None:
    if state.LOAD_ORDER_FILE is None or not state.MODS_DIR.is_dir():
        raise FileNotFoundError("游戏 mods 目录不存在，请先设置正确的游戏目录")
    backup_load_order()
    entries = normalize_entries(entries)
    text = "\n".join(e["raw"] for e in entries).rstrip("\n") + "\n"
    state.LOAD_ORDER_FILE.write_text(text, encoding="utf-8")


def is_exact_disable(raw: str) -> bool:
    """是否精确禁用行：--名字（无多余说明文字）"""
    s = raw.strip()
    return s.startswith("--") and len(s) > 2 and not any(c in s[2:] for c in " \t")


def normalize_entries(entries: list) -> list:
    """写入前去重：同名 mod 行优先，精确禁用行只留第一个；说明注释/空行原样保留"""
    has_mod = {}
    for e in entries:
        if e["kind"] == "mod":
            has_mod[e["name"]] = True
    seen = set()
    out = []
    for e in entries:
        if e["kind"] == "mod":
            if e["name"] not in seen:
                seen.add(e["name"])
                out.append(e)
        elif e["kind"] == "comment" and is_exact_disable(e["raw"]):
            name = e["raw"].strip()[2:].strip()
            if has_mod.get(name):
                continue  # 有启用行，禁用残留删掉
            if name not in seen:
                seen.add(name)
                out.append(e)
        else:
            out.append(e)
    return out


def enabled_names(entries: list) -> list:
    return [e["name"] for e in entries if e["kind"] == "mod"]


def set_load_order(mods: list) -> dict:
    """按目标启用列表重写清单：说明注释/空行保留，其余已知 mod 转为禁用行。
    纯逻辑（无防呆守卫），供 /api/order 与预设应用共用。"""
    entries = read_load_order()
    enabled_set = set(mods)

    # 收集已知 mod（含精确禁用行），说明注释/空行原样保留
    known, seen, kept = [], set(), []
    for e in entries:
        name = None
        if e["kind"] == "mod":
            name = e["name"]
        elif e["kind"] == "comment" and is_exact_disable(e["raw"]):
            name = e["raw"].strip()[2:].strip()
        if name:
            if name not in seen:
                seen.add(name)
                known.append((name, e["kind"] == "mod"))
        else:
            kept.append(e)

    disabled = [n for n, _ in known if n not in enabled_set]
    new_lines = (
        [{"kind": "mod", "raw": n, "name": n} for n in mods]
        + [{"kind": "comment", "raw": "--" + n} for n in disabled]
    )
    out = kept + new_lines
    write_load_order(out)
    return {"ok": True, "enabled": list(mods), "disabled": disabled}
