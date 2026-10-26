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


# ---------------------------------------------------------------- 重建当前清单
# 目的：让 mod_load_order.txt 与磁盘现状对上，并**清掉整合包作者写的注释**（用户 2026-10-10：
# "重建功能可以把原作者的注释去掉减少污染"）。作者注释多是上一份整合包的说明（联系方式、链接、
# "哪些 mod 必须放前面"），留着只会污染清单；strip_comments=False 时才保留（且保持原位，不搬到最前）。
REBUILT_NOTE = "-- 本清单由 DMM 重建（原清单已备份到 backups/，需要可找回）"


def rebuild_entries(entries: list, present: set, add_new: bool = False,
                    strip_comments: bool = True) -> list:
    """按磁盘现状重排条目。

    strip_comments=True（默认）：只留启用的 mod，作者注释与空行一并去掉，首行写一句 DMM 来源说明
    strip_comments=False：注释/空行**留在原位**（不搬到最前，作者用注释分的组不会被拆散）
    add_new：把磁盘上新增的 mod 按名字追加到末尾。**默认关**——磁盘上"不在清单里"的 mod 通常
        是玩家自己禁用的（实测一个环境里 348 个），重建时批量启用等于把整个整合包全开，是灾难。
        只有调用方明确要（例如预设导入）才开。
    """
    out, kept = [], set()
    for e in entries:
        if e["kind"] == "mod":
            if e["name"] in present:
                out.append(e)
                kept.add(e["name"])
            # 目录已不存在 → 丢掉（幽灵行）
            continue
        if e["kind"] == "comment" and is_exact_disable(e["raw"]):
            continue          # 旧式精确禁用行（--ModName）：照旧清理
        if not strip_comments:
            out.append(e)     # 空行 / 说明注释：留在原位
    if add_new:
        for n in sorted(present - kept):
            out.append({"kind": "mod", "raw": n, "name": n})
    if strip_comments:
        out = [{"kind": "comment", "raw": REBUILT_NOTE}] + [e for e in out if e["kind"] == "mod"]
    return out


def rebuild_plan(entries: list, present: set, add_new: bool = False,
                 strip_comments: bool = True) -> dict:
    """重建前给玩家看的变化清单（只读，不写文件），含重建后文件的开头几行预览"""
    cur = enabled_names(entries)
    cur_set = set(cur)
    ghosts = [n for n in cur if n not in present]
    new = sorted(n for n in present if n not in cur_set)
    comments = sum(1 for e in entries if e["kind"] == "comment")
    blanks = sum(1 for e in entries if e["kind"] == "blank")
    out_entries = rebuild_entries(entries, present, add_new=add_new, strip_comments=strip_comments)
    lines = [e["raw"] for e in out_entries]
    return {
        "ok": True,
        "enabled": cur,
        "enabled_count": len(cur),
        "ghosts": ghosts,                        # 清单里有、磁盘上没有 → 会被移除
        "new": new if add_new else [],           # 磁盘上有、清单里没有 → 仅 add_new 时才启用
        "new_skipped": [] if add_new else new,   # 保持停用的那些（默认全部保持停用）
        "comments": comments,                    # 原清单里的注释行数
        "blanks": blanks,
        "comments_kept": 0 if strip_comments else comments,
        "comments_dropped": comments if strip_comments else 0,
        "add_new": add_new,
        "strip_comments": strip_comments,
        "result_count": len([e for e in out_entries if e["kind"] == "mod"]),
        "result_lines": lines[:12],              # 对话框里给玩家看个开头
        "result_total_lines": len(lines),
    }


def rebuild_load_order(add_new: bool = False, present: set | None = None,
                       strip_comments: bool = True) -> dict:
    """**手动重建当前清单**：按 mods 目录现状重写 mod_load_order.txt（写前自动备份）。

    默认：保留仍存在 mod 的原有顺序、**去掉作者注释**、移除幽灵条目；**不启用**磁盘上原本没启用的 mod
    （那些通常是你自己禁用的，重建不该替你打开）。本函数写盘前会先 backup_load_order()，原清单可找回。"""
    entries = read_load_order()
    if present is None:
        present = {d.name for d in state.MODS_DIR.iterdir()
                   if d.is_dir() and d.name not in state.SYSTEM_MODS and ".bak_" not in d.name}
    plan = rebuild_plan(entries, present, add_new, strip_comments)
    new_entries = rebuild_entries(entries, present, add_new, strip_comments)
    write_load_order(new_entries)          # 内部会先 backup_load_order()
    after = enabled_names(read_load_order())
    return {**plan, "result": after, "result_count": len(after),
            "removed": plan["ghosts"], "added": plan["new"]}


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
