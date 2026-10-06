# -*- coding: utf-8 -*-
"""原生崩溃解析 + MOD 错误排行 + 导出脱敏（回归测试）

覆盖 2026-10-01 新增/修复的 core/crash.py 能力：
- parse_native_crash_blocks：<<Lua Error>> / <<Script Error>> + <<Lua Stack>> 逐帧归属，Lua/Script 双报去重
- parse_crash_blocks：软异常 + 真崩溃合并并按行号排序
- aggregate_mod_errors：错误行直接归属 / 后随栈归属 / dmf 不归属 / 无线索记游戏本体
- redact_log_text：machine_id / steam_id / steam_user_name 抹除
- enrich_log_rows：返回行数 = 行数（不是字符数）

样本全部内置，不依赖 %APPDATA% 下会被游戏轮转清理的 console_logs。
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.crash import (parse_native_crash_blocks, parse_crash_blocks,
                        aggregate_mod_errors, aggregate_absorbed_errors,
                        enrich_log_rows, redact_log_text,
                        _tail_window, _count_lines, _shift_lines,
                        api_crash_logs_analyze, LogAnalyzeBody)

FAILED = []


def check(name, cond, detail=""):
    print("[%s] %s%s" % ("OK " if cond else "FAIL", name, ("  <- %s" % detail) if detail else ""))
    if not cond:
        FAILED.append(name)


NATIVE = "\n".join([
    '17:32:22.230 [Lua] <<crashify-property>>machine_id = 7acef6a6-30d2-4c32-b2ac-4e17d570c653<</crashify-property>>',
    '17:32:50.636 <<Lua Error>>[string "./../mods/psych_ward/scripts/mods/psych_ward/psych_ward.lua"]:468: attempt to index upvalue SINGLEPLAY_TYPES (a nil value)<</Lua Error>>',
    '<<Script Error>>[string "./../mods/psych_ward/scripts/mods/psych_ward/psych_ward.lua"]:468: attempt to index upvalue SINGLEPLAY_TYPES (a nil value)<</Script Error>>',
    '<<Lua Stack>>  [1] ./../mods/psych_ward/scripts/mods/psych_ward/psych_ward.lua:468: in function func',
    '  [2] ./../mods/SoloPlay/scripts/mods/SoloPlay/SoloPlay.lua:372: in function hook_chain',
    '  [3] ./../mods/dmf/scripts/mods/dmf/modules/core/hooks.lua:199: in function update',
    '  [4] @scripts/foundation/utilities/game_state_machine.lua:119: in function update',
    '  [5] ./mod_loader:371:in function <[string "./mod_loader"]:361>',
    '<</Lua Stack>>',
    '<<Lua Locals>>  [1] foo = 1',
    '<</Lua Locals>>',
])

EXC = "\n".join([
    '14:16:06.096 [Lua] <<crashify-exception>>',
    '              \t<<system>>ConstantElementNotificationFeed<</system>>',
    '              \t<<message>>Item type WEAPON_MELEE is not defined!<</message>>',
    '              \t<<callstack>><Lua Script.Callstack>',
    '  [1] @scripts/foundation/utilities/crashify.lua:82: in function print_exception',
    '  [2] ./../mods/WhosNotReady/scripts/mods/WhosNotReady/WhosNotReady.lua:67',
    '  [3] ./../mods/dmf/scripts/mods/dmf/modules/core/hooks.lua:199',
    '</Lua Script.Callstack>',
    '<</callstack>>',
    '              <</crashify-exception>>',
])

AGG = "\n".join([
    "17:34:50.978 [Lua] [MOD][AUPM][ERROR] (safe_hook): ./../mods/AUPM/scripts/mods/AUPM/AUPM.lua:88: attempt to call method max_ability_cooldown (a nil value)",
    "17:34:50.979   [1] =[C]: in function callstack",
    "17:34:50.979   [2] ./../mods/dmf/scripts/mods/dmf/modules/core/safe_calls.lua:44: in function safe_call_nr",
    "17:35:01.000 error: [Lua] ERROR dmf internal at ./../mods/dmf/scripts/mods/dmf/modules/core/hooks.lua:199",
    "17:36:00.000 [Lua] ERROR SoloPlay blew up:",
    "17:36:00.001   [1] ./../mods/SoloPlay/scripts/mods/SoloPlay/SoloPlay.lua:94: in function f",
    "17:36:00.002   [2] @scripts/ui/base_view.lua:578: in function _draw_widgets",
    "17:37:00.000 error:   [Lua] ERROR [ItemPackage] Unable to find item content/item",
])


def test_native_crash():
    b = parse_native_crash_blocks(NATIVE)
    check("原生崩溃识别为 1 块（Lua/Script 双报去重）", len(b) == 1, str(len(b)))
    if not b:
        return
    d = b[0]
    check("kind=crash", d.get("kind") == "crash", str(d.get("kind")))
    check("mods = psych_ward + SoloPlay（dmf 不算玩家 mod）",
          d["mods"] == ["psych_ward", "SoloPlay"], str(d["mods"]))
    check("帧数 4（./mod_loader 行不算帧）", len(d["frames"]) == 4, str(len(d["frames"])))
    f0 = d["frames"][0] if d["frames"] else {}
    check("最内层 mod 帧 = psych_ward:468",
          f0.get("mod") == "psych_ward" and f0.get("line") == 468, str(f0))
    check("dmf 帧归 kind=dmf", any(f.get("kind") == "dmf" for f in d["frames"]), "")
    check("游戏帧归 kind=game", any(f.get("kind") == "game" for f in d["frames"]), "")
    check("无 Error Context 时 system 回落 Lua 崩溃", d["system"] == "Lua 崩溃", d["system"])
    check("summary 指出涉及 psych_ward", "psych_ward" in d["summary"], d["summary"])


def test_mixed_blocks():
    both = parse_crash_blocks(EXC + "\n" + NATIVE)
    kinds = [d.get("kind") for d in both]
    check("软异常 + 真崩溃都产出", sorted(kinds) == ["crash", "exception"], str(kinds))
    check("按行号排序（exception 在前）", kinds and kinds[0] == "exception", str(kinds))
    check("软异常块 mods 正确", both and both[0]["mods"] == ["WhosNotReady"], str(both[0]["mods"] if both else None))


def test_aggregate():
    agg = aggregate_mod_errors(AGG.splitlines())
    got = {}
    for e in agg:
        got[e["mod"]] = e["count"]
    check("AUPM 由错误行自带路径直接归属 1 次", got.get("AUPM") == 1, str(got))
    check("SoloPlay 由后随调用栈归属 1 次", got.get("SoloPlay") == 1, str(got))
    check("dmf/base 不算玩家 mod", "dmf" not in got and "base" not in got, str(got))
    check("无 mod 线索记游戏本体 2 次", got.get(None) == 2, str(got))
    counts = [e["count"] for e in agg]
    check("按次数降序", counts == sorted(counts, reverse=True), str(counts))
    check("每条都有错误样例", all(e.get("sample") for e in agg), "")


# [MOD][名] 自报标记：形态取自用户真实日志（2026-10-06 console_logs）
TAG_AGG = "\n".join([
    "17:02:01.406 [Lua] [MOD][guarantee_weapon_swap][ERROR] (hook_safe): trying to hook function or method that doesn't exist: [PlayerUnitAbilityExtension.use_ability_charge]",
    "17:02:01.407 [Lua] [MOD][guarantee_ability_activation][ERROR] (hook_safe): trying to hook function or method that doesn't exist: [PlayerUnitAbilityExtension.use_ability_charge]",
    "17:03:00.000 [Lua] [MOD][RimWorldAlerts][ERROR] attempt to index a nil value (field 'alert_queue')",
    "17:04:00.000 [Lua] [MOD][DMF][ERROR] dmf internal blew up",
    "17:05:00.000 [Lua] [MOD][Weapon_XP_Farm][INFO] [WXF] crash-fix: absorbed draw error (ignored)",
    "17:06:00.000 error: [Lua] ERROR something bad at ./../mods/PathWins/scripts/mods/PathWins/PathWins.lua:10 [MOD][OtherTag]",
])


def test_aggregate_mod_tag():
    agg = aggregate_mod_errors(TAG_AGG.splitlines())
    got = {e["mod"]: e for e in agg}
    check("[MOD][名] 标记可归属（不再算游戏本体）",
          got.get("guarantee_weapon_swap") is not None and got.get("RimWorldAlerts") is not None,
          str(list(got)))
    check("hook 类与普通类各计 1 次",
          got["guarantee_weapon_swap"]["count"] == 1 and got["RimWorldAlerts"]["count"] == 1,
          str({k: v["count"] for k, v in got.items()}))
    check("hook 目标不存在 → hook_missing=1 且带「不兼容」提示",
          got["guarantee_weapon_swap"]["hook_missing"] == 1 and "不兼容" in got["guarantee_weapon_swap"]["hint"],
          str(got["guarantee_weapon_swap"]))
    check("非 hook 类不带 hint（hook_missing=0）",
          got["RimWorldAlerts"]["hook_missing"] == 0 and got["RimWorldAlerts"]["hint"] == "",
          str(got["RimWorldAlerts"]))
    check("[MOD][DMF] 不算玩家 mod", "DMF" not in got and "dmf" not in got, str(list(got)))
    check("INFO 级 absorbed 行不入排行（classify=warn/ok）",
          "Weapon_XP_Farm" not in got, str(list(got)))
    check("同一行路径与标记并存时路径优先",
          got.get("PathWins") is not None and "OtherTag" not in got, str(list(got)))


def test_redact():
    s = ('<<crashify-property>>machine_id = 7acef6a6-30d2-4c32-b2ac-4e17d570c653<</crashify-property>> '
         'steam_id = 011000010e39bdb9 steam_user_name = CJDYZ111')
    out = redact_log_text(s)
    check("machine_id 已抹除", "7acef6a6" not in out, out)
    check("steam_id 已抹除", "011000010e39bdb9" not in out, out)
    check("steam_user_name 已抹除", "CJDYZ111" not in out, out)
    check("保留字段名便于阅读", "machine_id = <hidden>" in out, out)


def test_enrich_rows():
    rows, diag = enrich_log_rows("a\nb\nc\n")
    check("行数 = 3（不是字符数 6）", len(rows) == 3, str(len(rows)))
    check("无异常块时 diag 为空", diag == [], str(diag))
    rows2, diag2 = enrich_log_rows(EXC)
    check("软异常仍能解析出 1 块", len(diag2) == 1, str(len(diag2)))


# 被 mod 主动吞掉的引擎错误：形态取自用户真实日志（Weapon_XP_Farm 的 crash-fix）
ABSORBED = "\n".join([
    "20:46:19.218 [Lua] [MOD][Weapon_XP_Farm][INFO] [WXF] crash-fix: absorbed draw error (barter view closing): scripts/managers/ui/ui_passes.lua:114: bad argument #1",
    "20:46:19.229 [Lua] [MOD][Weapon_XP_Farm][INFO] [WXF] crash-fix: absorbed draw error (barter view closing): scripts/managers/ui/ui_passes.lua:114: bad argument #1",
    "20:46:19.285 [Lua] [MOD][Weapon_XP_Farm][INFO] [WXF] crash-fix: absorbed destroy error (barter view): scripts/managers/ui/ui_renderer.lua:278: bad argument #1",
    "20:46:20.000 [Lua] [MOD][OtherMod][INFO] absorbed nothing here",
    "20:46:21.000 [Lua] [MOD][DMF][INFO] absorbed error something",
])


def test_aggregate_absorbed():
    got = {e["mod"]: e["count"] for e in aggregate_absorbed_errors(ABSORBED.splitlines())}
    check("absorbed 引擎错误归到吞它的 mod（3 条）", got.get("Weapon_XP_Farm") == 3, str(got))
    check("无 error 字样的 absorbed 不计 / 框架不计",
          "OtherMod" not in got and "DMF" not in got, str(got))


def test_tail_window():
    s = "".join(f"line{i}\n" for i in range(100))
    w, dropped, trimmed = _tail_window(s, 40)
    check("窗口从行边界开始（不留半行）", w.startswith("line") and not w.startswith("ine"), repr(w[:12]))
    check("截断标记 + 丢弃行数与两端一致",
          trimmed is True and dropped + _count_lines(w) == _count_lines(s),
          str((dropped, _count_lines(w), _count_lines(s))))
    check("窗口内容 = 原文末尾", w.endswith("line99\n"), repr(w[-10:]))
    w2, d2, t2 = _tail_window(s, 100000)
    check("未超限时不截断（原文原样返回）", t2 is False and d2 == 0 and w2 == s, str((t2, d2)))
    check("_count_lines 边界（空/无换行/带尾换行）",
          _count_lines("") == 0 and _count_lines("a") == 1 and _count_lines("a\n") == 1 and _count_lines("a\nb") == 2,
          str((_count_lines(""), _count_lines("a"), _count_lines("a\n"), _count_lines("a\nb"))))
    items = [{"line": 5}, {"line": 9}]
    _shift_lines(items, 100)
    check("行号平移成全文行号", [x["line"] for x in items] == [105, 109], str(items))


def test_analyze_tail_fields():
    r = api_crash_logs_analyze(LogAnalyzeBody(
        name="t.log", content="17:00:00 [Lua] [MOD][SomeMod][ERROR] attempt to index a nil value\n"))
    check("analyze 返回 trimmed / trimmed_lines（小文本不截断）",
          r.get("ok") and r.get("trimmed") is False and r.get("trimmed_lines") == 0, sorted(r.keys()))
    check("analyze 返回 absorbed_errors 字段（可为空）", r.get("absorbed_errors") == [], r.get("absorbed_errors"))
    check("analyze 的 mod_errors 仍正常归属", any(e["mod"] == "SomeMod" for e in r["mod_errors"]), r["mod_errors"])
    r2 = api_crash_logs_analyze(LogAnalyzeBody(name="t.log", content=ABSORBED + "\n"))
    check("analyze 能带出被吞的引擎错误",
          [e["mod"] for e in r2["absorbed_errors"]] == ["Weapon_XP_Farm"], r2["absorbed_errors"])


if __name__ == "__main__":
    test_native_crash()
    test_mixed_blocks()
    test_aggregate()
    test_aggregate_mod_tag()
    test_aggregate_absorbed()
    test_tail_window()
    test_analyze_tail_fields()
    test_redact()
    test_enrich_rows()
    print()
    print("结果: %d 项失败" % len(FAILED))
    if FAILED:
        for f in FAILED:
            print("  FAILED:", f)
    sys.exit(1 if FAILED else 0)

