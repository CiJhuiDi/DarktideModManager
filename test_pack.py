# -*- coding: utf-8 -*-
"""整合包导入功能测试：真实样品包（小程哥稳定包 07.25.zip）导入 mock 游戏目录"""
import io
import shutil
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app
from core import patch
from core import state

ROOT = Path(__file__).resolve().parent
# 真实整合包样例（可选）：有真实整合包时测试更全面；缺失则自动跳过场景 1/2/7
# 可把任意整合包路径填到这里，例如：SAMPLE = Path(r"D:\你的路径\整合包.zip")
SAMPLE = Path("")  # 留空 = 跳过真实包场景
HAVE_SAMPLE = SAMPLE.is_file()
MOCK = ROOT / "mock_pack"
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


def setup_fresh_mock():
    if MOCK.exists():
        shutil.rmtree(MOCK)
    (MOCK / "bundle").mkdir(parents=True)
    (MOCK / "bundle" / "bundle_database.data").write_bytes(b"FAKE_DB")
    (MOCK / "binaries" / "plugins").mkdir(parents=True)
    (MOCK / "mods").mkdir()


def make_single_mod_zip(name="TestModA"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{name}/{name}.mod",
                   f'return {{ run = function() new_mod("{name}", {{}}) end, packages = {{}}, version = "1.0.0" }}')
        z.writestr(f"{name}/scripts/mods/{name}/{name}.lua", "-- single mod")
    return buf.getvalue()


def make_nested_pack():
    """构造外层套一层目录的整合包"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p, c in {
            "Warhammer 40,000 DARKTIDE/mods/NestedMod/NestedMod.mod":
                'return { run = function() new_mod("NestedMod", {}) end, packages = {}, version = "1.0.0" }',
            "Warhammer 40,000 DARKTIDE/mods/mod_load_order.txt": "NestedMod\n",
            "Warhammer 40,000 DARKTIDE/binaries/mod_loader": "fake loader",
            "Warhammer 40,000 DARKTIDE/bundle/9ba626afa44a3aa3.patch_999": "fake patch",
        }.items():
            z.writestr(p, c)
    return buf.getvalue()


print("===== 前置检查：样品包存在 =====")
check("样品包存在", SAMPLE.is_file(), str(SAMPLE))

if not HAVE_SAMPLE:
    print("  SKIP（无样品包，跳过真实整合包场景）")
else:
    print("\n===== 1. 全新玩家：导入真实样品包（小程哥稳定包） =====")
    setup_fresh_mock()
    point_to(MOCK)
    app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
    app.is_game_running = lambda: False
    patch.is_game_running = lambda: False
    data = SAMPLE.read_bytes()
    r = app.import_pack_archive(SAMPLE.name, data, "replace")
    check("导入返回 ok", r.get("ok") is True, str(r)[:250])
    check("mode=replace", r.get("mode") == "replace")
    check("mods 已填充（>100 个）", len(r.get("mods", [])) > 100, f"{len(r.get('mods', []))} 个")
    check("base 已导入", (state.MODS_DIR / "base" / "mod_manager.lua").is_file())
    check("dmf 已导入", (state.MODS_DIR / "dmf" / "dmf.mod").is_file())
    check("mod_load_order.txt 已替换", (state.MODS_DIR / "mod_load_order.txt").is_file())
    check("binaries/mod_loader 已导入", (state.GAME_DIR / "binaries" / "mod_loader").is_file())
    check("bundle patch_999 已导入", bool(list((state.GAME_DIR / "bundle").glob("*.patch_999"))))
    check("补丁已激活提示", "补丁已激活" in r.get("message", ""), r.get("message", "")[:150])
    # load_order 内容应包含包内清单的 mod（抽查 animation_events 这种常见 mod）
    lo = (state.MODS_DIR / "mod_load_order.txt").read_text(encoding="utf-8", errors="ignore")
    check("load_order 非空", len(lo.strip()) > 10)

    print("\n===== 2. 合并模式（merge）：同名 mod 自动备份 =====")
    setup_fresh_mock()
    point_to(MOCK)
    # 预置一个包内存在的 mod（animation_events）旧版 + 旧启停清单
    ( MOCK / "mods" / "animation_events").mkdir(parents=True)
    (MOCK / "mods" / "animation_events" / "OLD.txt").write_text("old version", encoding="utf-8")
    (MOCK / "mods" / "mod_load_order.txt").write_text("-- OLD LOAD ORDER\nanimation_events\n", encoding="utf-8")
    app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
    app.is_game_running = lambda: False
    patch.is_game_running = lambda: False
    r2 = app.import_pack_archive(SAMPLE.name, SAMPLE.read_bytes(), "merge")
    check("导入 ok", r2.get("ok") is True)
    check("animation_events 被覆盖", "animation_events" in r2.get("replaced", []), str(r2.get("replaced", []))[:150])
    baks = list((MOCK / "mods").glob("animation_events.bak_*"))
    check("旧版已备份", len(baks) == 1, [b.name for b in baks])
    check("备份内容是旧版", baks and (baks[0] / "OLD.txt").exists())
    # 旧 load_order 备份进 BACKUP_DIR（不再留在 mods 目录）
    lo_baks = list((ROOT / "backups").glob("pack_backup_*/mods/mod_load_order.txt"))
    check("旧 load_order 已备份到 backups", len(lo_baks) >= 1, str(lo_baks[:1]))

print("\n===== 3. 非整合包（单 mod zip）拒绝 =====")
setup_fresh_mock()
point_to(MOCK)
r3 = app.import_pack_archive("single.zip", make_single_mod_zip())
check("单 mod 被拒绝", r3.get("ok") is False and "整合包" in r3.get("error", ""), r3.get("error", ""))

print("\n===== 4. 外层套目录的整合包 =====")
setup_fresh_mock()
point_to(MOCK)
r4 = app.import_pack_archive("nested.zip", make_nested_pack())
check("识别并导入 ok", r4.get("ok") is True, str(r4)[:200])
check("NestedMod 导入", (state.MODS_DIR / "NestedMod" / "NestedMod.mod").is_file())
check("mod_loader 导入", (state.GAME_DIR / "binaries" / "mod_loader").is_file())
check("patch_999 导入", bool(list((state.GAME_DIR / "bundle").glob("*.patch_999"))))

print("\n===== 5. bundle_database.data 不导入 =====")
setup_fresh_mock()
point_to(MOCK)
# 构造带数据库文件的整合包
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("mods/XMod/XMod.mod", 'return { run = function() new_mod("XMod", {}) end, packages = {}, version = "1.0.0" }')
    z.writestr("mods/mod_load_order.txt", "XMod\n")
    z.writestr("bundle/bundle_database.data", "HACKED_DB")
r5 = app.import_pack_archive("withdb.zip", buf.getvalue())
check("导入 ok", r5.get("ok") is True)
db = (state.GAME_DIR / "bundle" / "bundle_database.data").read_bytes()
check("数据库未被覆盖（仍为原内容）", db == b"FAKE_DB", db)

print("\n===== 6. 游戏运行中：不打断，提示稍后补丁 =====")
setup_fresh_mock()
point_to(MOCK)
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r6 = app.import_pack_archive("nested.zip", make_nested_pack())
check("导入 ok", r6.get("ok") is True)
check("提示游戏运行中", "游戏运行中" in r6.get("message", ""), r6.get("message", "")[:150])
app.is_game_running = lambda: False
patch.is_game_running = lambda: False

if not HAVE_SAMPLE:
    print("  SKIP（无样品包，跳过真实整合包场景）")
else:
    print("\n===== 7. 替换模式（replace）：旧 mods 整体归档，不叠加 =====")
    setup_fresh_mock()
    point_to(MOCK)
    # 预置旧包内容：两个普通 mod + 旧 load_order
    for m in ("TestModA", "TestModB"):
        (MOCK / "mods" / m).mkdir(parents=True)
        (MOCK / "mods" / m / f"{m}.mod").write_text(
            f'return {{ run = function() new_mod("{m}", {{}}) end, packages = {{}}, version = "0.1" }}', encoding="utf-8")
    (MOCK / "mods" / "mod_load_order.txt").write_text("TestModA\nTestModB\n", encoding="utf-8")
    app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
    app.is_game_running = lambda: False
    patch.is_game_running = lambda: False
    r7 = app.import_pack_archive(SAMPLE.name, SAMPLE.read_bytes(), "replace")
    check("导入 ok", r7.get("ok") is True)
    check("旧 mod 被归档", "TestModA" in r7.get("archived", []) and "TestModB" in r7.get("archived", []), str(r7.get("archived", []))[:200])
    check("mods 目录不再有旧 mod", not (MOCK / "mods" / "TestModA").exists() and not (MOCK / "mods" / "TestModB").exists())
    check("新包 mod 已就位", (MOCK / "mods" / "animation_events").is_dir())
    arch_bak = list((ROOT / "backups").glob("pack_backup_*/mods/TestModA"))
    check("归档备份可找回", len(arch_bak) == 1, str(arch_bak[:1]))
    check("归档里有旧 load_order", list((ROOT / "backups").glob("pack_backup_*/mods/mod_load_order.txt")))
    # 系统组件保留：mock 预置旧 base，包内也有 base -> 应被覆盖而非丢失
    check("base 仍在 mods", (MOCK / "mods" / "base").is_dir())
    lo7 = (MOCK / "mods" / "mod_load_order.txt").read_text(encoding="utf-8", errors="ignore")
    check("load_order 已换成新包清单", "TestModA" not in lo7 and len(lo7.strip()) > 10)

print("\n===== 8. 单 mod 的 mods/ 包裹结构不被误判为整合包 =====")
setup_fresh_mock()
point_to(MOCK)
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
app.is_game_running = lambda: False
patch.is_game_running = lambda: False
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("mods/WrappedMod/WrappedMod.mod",
               'return { run = function() new_mod("WrappedMod", {}) end, packages = {}, version = "1.0.0" }')
    z.writestr("mods/WrappedMod/scripts/mods/WrappedMod/WrappedMod.lua", "-- wrapped")
r8 = app.import_pack_archive("wrapped.zip", buf.getvalue())
check("单 mod 包裹被拒绝（不是整合包）", r8.get("ok") is False and "整合包" in r8.get("error", ""), r8.get("error", ""))
# 而 mod 导入通道能正常处理它（v0.3.0 起防呆：先返回 ambiguous 待用户确认，force 后导入）
r8b = app.import_mod_archive("wrapped.zip", buf.getvalue())
check("mod 导入通道：包裹结构返回 ambiguous 待确认", r8b.get("ok") is False and r8b.get("ambiguous") is True, str(r8b)[:150])
r8c = app.import_mod_archive("wrapped.zip", buf.getvalue(), force_mod=True)
check("mod 导入通道 force 后正常导入", r8c.get("ok") is True and r8c.get("mod") == "WrappedMod", str(r8c)[:150])

print("\n===== 9. 根目录散文件：不再导入，replace 时归档旧的（A+B 方案） =====")
setup_fresh_mock()
point_to(MOCK)
# 预置游戏根目录已有旧包残留（README.md + 参考副本 mod_load_order.txt + tools 工具）
(MOCK / "README.md").write_text("OLD README", encoding="utf-8")
(MOCK / "tools").mkdir(parents=True, exist_ok=True)
(MOCK / "tools" / "dtkit-patch.exe").write_bytes(b"OLD TOOL")
(MOCK / "mod_load_order.txt").write_text("-- REF COPY", encoding="utf-8")
(MOCK / "tools").mkdir(exist_ok=True)
(MOCK / "tools" / "dtkit-patch.exe").write_bytes(b"old tool")
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
app.is_game_running = lambda: False
patch.is_game_running = lambda: False
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("mods/NewMod/NewMod.mod",
               'return { run = function() new_mod("NewMod", {}) end, packages = {}, version = "1.0.0" }')
    z.writestr("mods/mod_load_order.txt", "NewMod\n")
    z.writestr("README.md", "NEW README")
    z.writestr("tools/dtkit-patch.exe", b"new tool")
r9 = app.import_pack_archive("rootfiles.zip", buf.getvalue(), "replace")
check("导入 ok", r9.get("ok") is True)
check("新包 README 不再拷入根目录（A）", not (MOCK / "README.md").exists())
check("旧 README 归档进 root_cleanup", len(list((ROOT / "backups").glob("root_cleanup_*/README.md"))) == 1)
check("mod_load_order.txt 参考副本保留", (MOCK / "mod_load_order.txt").is_file())
check("旧 dtkit 备份进 pack_backup", len(list((ROOT / "backups").glob("pack_backup_*/loader/dtkit-patch.exe"))) == 1)
check("tools 新 dtkit 已就位", (MOCK / "tools" / "dtkit-patch.exe").read_bytes() == b"new tool")
check("游戏根目录无 .bak_ 残留", not list(MOCK.glob("*.bak_*")))
check("tools 目录无 .bak_ 残留", not list((MOCK / "tools").glob("*.bak_*")))

print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过 通过")
