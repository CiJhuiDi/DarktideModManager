# -*- coding: utf-8 -*-
"""归档备份管理测试：列表 / 恢复 / 删除"""
import shutil
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app
import patch
import state

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
check("提示打补丁", "补丁已激活" in r3.get("message", ""), r3.get("message", "")[:120])

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

print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过 通过")
