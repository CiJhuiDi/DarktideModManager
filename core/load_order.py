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
    """写入前去重：同名 mod 行只留第一个；说明注释/空行原样保留；
    旧式精确禁用行（--ModName）一律丢弃——停用 = 不在清单，清单只含启用中的 mod。"""
    seen = set()
    out = []
    for e in entries:
        if e["kind"] == "mod":
            if e["name"] not in seen:
                seen.add(e["name"])
                out.append(e)
        elif e["kind"] == "comment" and is_exact_disable(e["raw"]):
            continue  # 旧式禁用标记：清理，不落盘
        else:
            out.append(e)  # 空行 / 说明注释
    return out


def enabled_names(entries: list) -> list:
    return [e["name"] for e in entries if e["kind"] == "mod"]


def set_load_order(mods: list) -> dict:
    """按目标启用列表重写清单：只保留启用的 mod 行与说明注释/空行。
    停用 = 从清单移除（不再写 -- 禁用行，清单保持干净）；
    旧式精确禁用行（--ModName）一并清理。
    纯逻辑（无防呆守卫），供 /api/order 与预设应用共用。"""
    entries = read_load_order()
    enabled_set = set(mods)

    # 保留空行/说明注释；旧式禁用标记丢弃
    kept = [e for e in entries
            if e["kind"] == "blank"
            or (e["kind"] == "comment" and not is_exact_disable(e["raw"]))]

    # 已知 mod 名（含旧格式精确禁用行，仅用于统计本次停用数量）
    known, seen = [], set()
    for e in entries:
        name = None
        if e["kind"] == "mod":
            name = e["name"]
        elif e["kind"] == "comment" and is_exact_disable(e["raw"]):
            name = e["raw"].strip()[2:].strip()
        if name and name not in seen:
            seen.add(name)
            known.append(name)

    disabled = [n for n in known if n not in enabled_set]
    new_lines = [{"kind": "mod", "raw": n, "name": n} for n in mods]
    out = kept + new_lines
    write_load_order(out)
    return {"ok": True, "enabled": list(mods), "disabled": disabled}
