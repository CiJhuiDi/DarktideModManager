# -*- coding: utf-8 -*-
"""归档备份管理测试：列表 / 恢复 / 删除"""
import shutil
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app
from core import patch
from core import state

ROOT = Path(__file__).resolve().parent
MOCK = ROOT / "mock_bak"
FAILED = []


def check(name, cond, detail=""):
    mark = "OK " if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  <- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def point_to(mock: Path):
    state.GAME_DIR = mock.resolve()
    state.MODS_DIR = state.GAME_DIR / "mods"
    state.LOAD_ORDER_FILE = state.MODS_DIR / "mod_load_order.txt"
    state.CONFIG_FILE = mock.resolve() / "config_test.json"
    state.BACKUP_DIR = mock.resolve() / "backups"


def setup():
    if MOCK.exists():
        shutil.rmtree(MOCK)
    (MOCK / "bundle").mkdir(parents=True)
    (MOCK / "bundle" / "bundle_database.data").write_bytes(b"FAKE_DB")
    (MOCK / "binaries" / "plugins").mkdir(parents=True)
    (MOCK / "mods").mkdir()
    point_to(MOCK)
    (state.BACKUP_DIR).mkdir(parents=True)


def make_mods(root: Path, names: list, with_lo=True):
    for n in names:
        d = root / n
        d.mkdir(parents=True)
        (d / f"{n}.mod").write_text(
            f'return {{ run = function() new_mod("{n}", {{}}) end, packages = {{}}, version = "1.0.0" }}', encoding="utf-8")
    if with_lo:
        (root / "mod_load_order.txt").write_text("\n".join(names) + "\n", encoding="utf-8")


print("===== 1. 空列表 =====")
setup()
r = app.api_backups()
check("空列表", r["backups"] == [])

print("\n===== 2. 列表识别 pack/dmf 备份 =====")
setup()
# 造一个整合包归档：pack_backup_20260813_100000/mods/{XMod,YMod} + load_order
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["XMod", "YMod"])
# 造一个 DMF 组件备份
dmf = state.BACKUP_DIR / "dmf_backup_20260813_100100" / "mods" / "base"
dmf.mkdir(parents=True)
(dmf / "mod_manager.lua").write_text("-- old", encoding="utf-8")
r2 = app.api_backups()
packs = [b for b in r2["backups"] if b["type"] == "pack"]
dmfs = [b for b in r2["backups"] if b["type"] == "dmf"]
check("识别 pack 备份", len(packs) == 1 and packs[0]["count"] == 2 and packs[0]["has_load_order"], str(packs))
check("识别 dmf 备份", len(dmfs) == 1 and dmfs[0]["count"] == 1, str(dmfs))

print("\n===== 3. 恢复：当前 mods 归档 + 备份生效 =====")
setup()
make_mods(state.MODS_DIR, ["CurA", "CurB"])          # 当前状态
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["OldX", "OldY"])  # 要恢复的备份
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
app.is_game_running = lambda: False
patch.is_game_running = lambda: False
r3 = app.api_backup_restore("pack_backup_20260813_100000")
check("恢复 ok", r3.get("ok") is True, str(r3)[:200])
check("备份的 mod 已恢复", (state.MODS_DIR / "OldX" / "OldX.mod").is_file() and (state.MODS_DIR / "OldY").is_dir())
check("当前 mod 已移走", not (state.MODS_DIR / "CurA").exists() and not (state.MODS_DIR / "CurB").exists())
check("当前 mod 已归档", (state.BACKUP_DIR / "pack_backup_20260813_100001" / "mods" / "CurA").is_dir() or
      len(list(state.BACKUP_DIR.glob("pack_backup_*/mods/CurA"))) >= 1)
lo = (state.MODS_DIR / "mod_load_order.txt").read_text(encoding="utf-8")
check("load_order 已恢复", "OldX" in lo and "CurA" not in lo, lo)
check("提示自动重载", "DMF 组件已启用" in r3.get("message", ""), r3.get("message", "")[:120])

print("\n===== 4. 恢复不存在的备份 =====")
setup()
r4 = app.api_backup_restore("pack_backup_99999999_000000")
check("拒绝", r4.get("ok") is False and "不存在" in r4.get("error", ""), r4.get("error", ""))

print("\n===== 5. 游戏运行中拒绝恢复 =====")
setup()
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["OldX"])
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r5 = app.api_backup_restore("pack_backup_20260813_100000")
check("拒绝", r5.get("ok") is False and "运行" in r5.get("error", ""), r5.get("error", ""))
app.is_game_running = lambda: False
patch.is_game_running = lambda: False

print("\n===== 6. 删除备份 =====")
setup()
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["OldX"])
r6 = app.api_backup_delete("pack_backup_20260813_100000")
check("删除 ok", r6.get("ok") is True)
check("目录已删", not (state.BACKUP_DIR / "pack_backup_20260813_100000").exists())
check("列表为空", app.api_backups()["backups"] == [])
# 防删除非备份目录
r7 = app.api_backup_delete("..%2f..%2fwhatever")
check("非法 id 拒绝", r7.get("ok") is False)

print("\n===== 7. 列表带体积 / 策略 / 清理计划（备份页现代化）=====")
setup()
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["OldX", "OldY"])
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100100" / "mods", ["OldX"])
r8 = app.api_backups()
check("每条都有 size_bytes", all("size_bytes" in b and b["size_bytes"] > 0 for b in r8["backups"]),
      [b.get("size_bytes") for b in r8["backups"]])
check("返回总体积", r8.get("total_bytes", 0) > 0, r8.get("total_bytes"))
check("返回保留策略", r8["policy"]["max_per_type"] >= 1 and r8["policy"]["max_total_mb"] >= 64, r8["policy"])
check("返回清理计划字段", isinstance(r8.get("plan"), list), type(r8.get("plan")))

print("\n===== 8. 策略可配 + 清理预览不删 =====")
setup()
for i in range(5):
    make_mods(state.BACKUP_DIR / f"pack_backup_20260813_10000{i}" / "mods", [f"M{i}"])
app.save_backup_policy(max_per_type=2)
pol = app.backup_policy()
check("策略已生效（每类 2 份）", pol["max_per_type"] == 2, str(pol))
plan = app.prune_plan()
doomed = [x["id"] for x in plan["would_remove"]]
check("计划删掉旧的 3 份", len(doomed) == 3 and doomed == [f"pack_backup_20260813_10000{i}" for i in range(3)], doomed)
check("dry_run 只算不删", len(app.prune_backups(dry_run=True)) == 3
      and len(list(state.BACKUP_DIR.glob("pack_backup_*"))) == 5, "dry_run 竟然删了")
removed = app.prune_backups()
left = sorted(d.name for d in state.BACKUP_DIR.iterdir() if d.is_dir())
check("真清理后只剩最新 2 份", len(left) == 2 and removed == doomed, f"{left} / {removed}")
app.save_backup_policy(max_per_type=10)

print("\n===== 9. 备份内容可浏览（逐 mod 大小/是否在游戏目录/启用没）=====")
setup()
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["OldX", "OldY"])
make_mods(state.MODS_DIR, ["OldX"])          # OldX 当前已在游戏目录，OldY 不在
c = app.api_backup_contents("pack_backup_20260813_100000")
check("内容读取 ok", c.get("ok") is True and c.get("type") == "pack", str(c)[:150])
by = {x["name"]: x for x in c.get("items", [])}
check("列出两个 mod", set(by) == {"OldX", "OldY"}, list(by))
check("带体积", all(x["size_kb"] >= 1 for x in by.values()), {k: v["size_kb"] for k, v in by.items()})
check("标出哪个已在游戏目录", by["OldX"]["in_game"] is True and by["OldY"]["in_game"] is False, str(by))
check("标出备份里启用状态", by["OldX"]["enabled"] and by["OldY"]["enabled"], str(by))
check("不存在的备份报错", app.api_backup_contents("pack_backup_99999999_000000").get("ok") is False)

print("\n===== 10. 挑单个 mod 恢复（不整包换回）=====")
setup()
make_mods(state.MODS_DIR, ["CurA"])                                   # 当前只有一个
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["OldX", "OldY", "CurA"])
app.is_game_running = lambda: False
patch.is_game_running = lambda: False
# 只挑 OldX（不带启用）
rs = app.api_backup_restore_selected("pack_backup_20260813_100000", app.RestoreSelectedBody(names=["OldX"]))
check("挑单恢复 ok", rs.get("ok") is True and rs["restored"] == ["OldX"], str(rs)[:200])
check("选中的回来了", (state.MODS_DIR / "OldX" / "OldX.mod").is_file())
check("没选的没动（OldY 仍不在）", not (state.MODS_DIR / "OldY").exists())
check("当前的其他 mod 没被动（CurA 还在，这是与整包恢复的区别）", (state.MODS_DIR / "CurA").is_dir())
check("未启用（enable=False）", "OldX" not in (state.MODS_DIR / "mod_load_order.txt").read_text(encoding="utf-8")
      if (state.MODS_DIR / "mod_load_order.txt").exists() else True, "清单被改了")
# 挑一个已存在的同名 → 先备份再覆盖
rs2 = app.api_backup_restore_selected("pack_backup_20260813_100000",
                                      app.RestoreSelectedBody(names=["CurA", "OldY"], enable=True))
check("覆盖同名成功", rs2.get("ok") is True and set(rs2["restored"]) == {"CurA", "OldY"}, str(rs2)[:200])
check("被覆盖的旧版进了 partial_ 备份（不在游戏目录里留 .bak_）",
      bool(list(state.BACKUP_DIR.glob("partial_*/mods/CurA"))), "没找到 partial 备份")
check("enable=True 已补进清单", "OldY" in (state.MODS_DIR / "mod_load_order.txt").read_text(encoding="utf-8"),
      (state.MODS_DIR / "mod_load_order.txt").read_text(encoding="utf-8"))
# 备份里没有的名字
rs3 = app.api_backup_restore_selected("pack_backup_20260813_100000",
                                      app.RestoreSelectedBody(names=["NoSuchMod"]))
check("备份里没有 → missing 且 ok=False", rs3.get("ok") is False and rs3["missing"] == ["NoSuchMod"], str(rs3)[:160])
rs4 = app.api_backup_restore_selected("pack_backup_20260813_100000", app.RestoreSelectedBody(names=[]))
check("空选择被拒", rs4.get("ok") is False and "选择" in rs4.get("error", ""), rs4.get("error", ""))
# partial 类型应出现在列表里（可回滚）
r9 = app.api_backups()
check("partial 备份出现在列表里", any(b["type"] == "partial" for b in r9["backups"]),
      [b["type"] for b in r9["backups"]])

print("\n===== 11. 游戏运行中拒绝挑单恢复 =====")
setup()
make_mods(state.MODS_DIR, ["CurA"])
make_mods(state.BACKUP_DIR / "pack_backup_20260813_100000" / "mods", ["OldX"])
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
rs5 = app.api_backup_restore_selected("pack_backup_20260813_100000", app.RestoreSelectedBody(names=["OldX"]))
check("游戏运行中拒绝", rs5.get("ok") is False and "运行" in rs5.get("error", ""), rs5.get("error", ""))
app.is_game_running = lambda: False
patch.is_game_running = lambda: False

print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过 通过")
