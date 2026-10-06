# -*- coding: utf-8 -*-
"""换包保留：keep_enabled（缺失补回 / 同版本静默 / 版本冲突待决策）+ 「我的 mod」名单
（原地保留 / 保持启用 / 包内同名不覆盖 / 取消标记回老行为）"""
import io
import shutil
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import state
from core import mods as core_mods
from core.imports import import_pack_archive, import_mod_archive, preview_pack_archive
from core.load_order import enabled_names, read_load_order

ROOT = Path(__file__).resolve().parent.parent
MOCK = ROOT / "mock_keep"
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
    state.BACKUP_DIR = mock.resolve() / "backups"
    state.MY_MODS_DIR = mock.resolve() / "my_mods"          # 管理器库区（换包不碰它）
    # ⚠️ MY_MODS_FILE 在 core/mods.py import 时就按 BASE_DIR 定死了 —— 改 state.BASE_DIR 无效，
    #    必须直接替换模块常量并清缓存（与 theme.CUSTOM_THEME_DIR 同一类坑）
    core_mods.MY_MODS_FILE = mock.resolve() / "my_mods.json"
    core_mods._my_mods_cache = None


def mod_body(name, ver):
    return f'return {{ run = function() new_mod("{name}", {{}}) end, packages = {{}}, version = "{ver}" }}'


def write_mod(mods_dir, name, ver, extra_dir=True):
    d = mods_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.mod").write_text(mod_body(name, ver), encoding='utf-8')
    if extra_dir:
        (d / "scripts").mkdir(exist_ok=True)
        (d / "scripts" / f"{name}.lua").write_text(f"-- {name} v{ver}", encoding='utf-8')
    return d


def make_pack_zip(mods: dict, load_order=None, root_wrap=""):
    """mods: {mod名: 版本}; 组装整合包 zip（可带外层目录）"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        base = f"{root_wrap}/mods" if root_wrap else "mods"
        for name, ver in mods.items():
            z.writestr(f"{base}/{name}/{name}.mod", mod_body(name, ver))
            z.writestr(f"{base}/{name}/scripts/{name}.lua", f"-- {name}")
        lo = load_order if load_order is not None else list(mods)
        z.writestr(f"{base}/mod_load_order.txt", "\n".join(lo) + "\n")
    return buf.getvalue()


def make_mod_zip(name, ver):
    """单个 mod 的 zip（<名>/<名>.mod，不是整合包的 mods/ 结构）"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{name}/{name}.mod", mod_body(name, ver))
        z.writestr(f"{name}/scripts/{name}.lua", f"-- {name} v{ver}")
    return buf.getvalue()


def setup():
    if MOCK.exists():
        shutil.rmtree(MOCK)
    (MOCK / "mods").mkdir(parents=True)
    (MOCK / "backups").mkdir(parents=True)
    point_to(MOCK)


def test_missing_auto_restore():
    """我启用的 MyMod 新包没有 → 自动补回 + 进清单末尾"""
    setup()
    # 旧环境：启用 A、B、MyMod（我的私有）
    write_mod(MOCK / "mods", "PackModA", "1.0")
    write_mod(MOCK / "mods", "PackModB", "1.0")
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("PackModA\nPackModB\nMyPriv\n", encoding='utf-8')
    # 新包：只有 A、B（没有 MyPriv）
    data = make_pack_zip({"PackModA": "1.1", "PackModB": "1.0"}, ["PackModA", "PackModB"])
    r = import_pack_archive("newpack.zip", data, "replace", keep_enabled=True)
    check("导入成功", r.get("ok") is True, str(r.get("error") or "")[:100])
    check("MyPriv 自动补回", "MyPriv" in (r.get("restored") or []), str(r.get("restored")))
    check("MyPriv 目录回来了", (MOCK / "mods" / "MyPriv").is_dir())
    enabled = enabled_names(read_load_order())
    check("MyPriv 不在清单（作者清单全权，手动开启）", "MyPriv" not in enabled, str(enabled))
    # 新包 PackModA 1.1 vs 我旧 1.0 → 属版本冲突（待决策），不自动覆盖
    pc = r.get("pending_conflicts") or []
    check("PackModA 升级判为冲突", any(x["name"] == "PackModA" for x in pc), str(pc))
    check("MyPriv 缺失不判冲突", all(x["name"] != "MyPriv" for x in pc), str(pc))
    check("消息含文件保留提示", "已保留你之前启用的 1 个 mod 文件" in (r.get("message") or ""), r.get("message"))


def test_same_version_silent():
    """新包带同名同版本 → 不判冲突、不补回、用新包的"""
    setup()
    write_mod(MOCK / "mods", "PackModA", "1.0")
    (MOCK / "mods" / "mod_load_order.txt").write_text("PackModA\n", encoding='utf-8')
    data = make_pack_zip({"PackModA": "1.0"}, ["PackModA"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    check("同版本无冲突", not (r.get("pending_conflicts") or []), str(r.get("pending_conflicts")))
    check("同版本无补回", not (r.get("restored") or []), str(r.get("restored")))


def test_version_conflict_pending():
    """新包带同名不同版本 → 返回 pending_conflicts，不擅自覆盖"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    data = make_pack_zip({"MyPriv": "3.0"}, ["MyPriv"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    pc = r.get("pending_conflicts") or []
    check("版本冲突已返回", len(pc) == 1, str(pc))
    if pc:
        check("冲突含新旧版本", pc[0]["old_version"] == "2.1" and pc[0]["new_version"] == "3.0", str(pc[0]))
    # 当前应是新包版 3.0（未被旧版覆盖）
    ver = ""
    f = MOCK / "mods" / "MyPriv" / "MyPriv.mod"
    if f.exists():
        import re
        m = re.search(r'version\s*=\s*"([^"]+)"', f.read_text(encoding='utf-8'))
        if m:
            ver = m.group(1)
    check("未擅自覆盖（保持新包 3.0）", ver == "3.0", f"当前 {ver}")


def test_keep_off_restores_nothing():
    """keep_enabled=False（勾掉）= 老行为，我的 mod 不补回"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    data = make_pack_zip({"PackModA": "1.0"}, ["PackModA"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=False)
    check("keep=False 不补回", not (r.get("restored") or []), str(r.get("restored")))
    check("MyPriv 被归档（老行为）", not (MOCK / "mods" / "MyPriv").exists())


def mod_version(name):
    import re
    f = MOCK / "mods" / name / f"{name}.mod"
    if not f.exists():
        return ""
    m = re.search(r'version\s*=\s*"([^"]+)"', f.read_text(encoding='utf-8'))
    return m.group(1) if m else ""


# ---- 「我的 mod」名单：自研/私装、整合包里没有的那些 ----

def test_mine_kept_and_reenabled():
    """标记为「我的」+ 包内没有 → 原地保留、不进归档、换完包仍启用"""
    setup()
    write_mod(MOCK / "mods", "PackModA", "1.0")
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("PackModA\nMyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    data = make_pack_zip({"PackModA": "1.1"}, ["PackModA"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    check("导入成功", r.get("ok") is True, str(r.get("error") or "")[:120])
    check("我的 mod 原地保留（没被搬走）", (MOCK / "mods" / "MyPriv").is_dir())
    check("没进归档列表", "MyPriv" not in (r.get("archived") or []), str(r.get("archived")))
    check("mine_kept 记录到它", "MyPriv" in (r.get("mine_kept") or []), str(r.get("mine_kept")))
    enabled = enabled_names(read_load_order())
    check("换完包仍在启用清单里（这是需求核心）", "MyPriv" in enabled, str(enabled))
    check("mine_reenabled 记录到它", "MyPriv" in (r.get("mine_reenabled") or []), str(r.get("mine_reenabled")))
    check("作者清单项仍在（没被打乱）", "PackModA" in enabled, str(enabled))
    check("消息里说明了保留情况", "你的 mod 1 个已原地保留" in (r.get("message") or ""), (r.get("message") or "")[:160])


def test_mine_disabled_stays_disabled():
    """标记为「我的」但换包前是关着的 → 文件留下、仍不开（不擅自替玩家开）"""
    setup()
    write_mod(MOCK / "mods", "PackModA", "1.0")
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("PackModA\n", encoding='utf-8')  # MyPriv 未启用
    core_mods.save_my_mods(["MyPriv"])
    data = make_pack_zip({"PackModA": "1.1"}, ["PackModA"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    check("文件仍原地保留", (MOCK / "mods" / "MyPriv").is_dir())
    check("没有被补进清单（保持你原来的关闭状态）", "MyPriv" not in enabled_names(read_load_order()),
          str(enabled_names(read_load_order())))
    check("mine_reenabled 为空", not (r.get("mine_reenabled") or []), str(r.get("mine_reenabled")))


def test_mine_wins_over_pack_same_name():
    """包里有同名 → 保留我的版本，不用包的覆盖"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    data = make_pack_zip({"MyPriv": "3.0"}, ["MyPriv"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    check("我的版本没被覆盖（仍是 2.1）", mod_version("MyPriv") == "2.1", f"当前 {mod_version('MyPriv')}")
    check("同名冲突已上报", "MyPriv" in (r.get("mine_pack_conflict") or []), str(r.get("mine_pack_conflict")))
    check("消息说明「加载的是你的版本」", "游戏加载的是你的版本" in (r.get("message") or ""), (r.get("message") or "")[:200])
    check("仍在启用清单", "MyPriv" in enabled_names(read_load_order()), str(enabled_names(read_load_order())))


def test_preview_reports_my_conflict():
    """导入前预览就要看到「包内与你的 mod 同名」"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    data = make_pack_zip({"MyPriv": "3.0", "PackModA": "1.0"}, ["MyPriv", "PackModA"])
    p = preview_pack_archive("p.zip", data)
    check("预览成功", p.get("ok") is True, str(p.get("error") or "")[:120])
    check("预览报出我的 mod 撞名", p.get("my_conflicts") == ["MyPriv"], str(p.get("my_conflicts")))


def test_single_mod_import_guard():
    """「＋ 导入 mod」撞上我的 mod：默认不覆盖、报冲突；确认后才覆盖"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    data = make_mod_zip("MyPriv", "3.0")
    r = import_mod_archive("m.zip", data, force_mod=True)
    check("默认拒绝覆盖并上报", r.get("ok") is False and r.get("is_my_mod_conflict") is True, str(r)[:150])
    check("磁盘版本未被动（仍 2.1）", mod_version("MyPriv") == "2.1", f"当前 {mod_version('MyPriv')}")
    check("目录里没留下 .bak_ 残留", not list((MOCK / "mods").glob("MyPriv.bak_*")), "有残留")
    # 用户确认覆盖后
    r2 = import_mod_archive("m.zip", data, force_mod=True, overwrite_mine=True)
    check("确认后导入成功", r2.get("ok") is True, str(r2.get("error") or "")[:120])
    check("确认后版本变成新的 3.0", mod_version("MyPriv") == "3.0", f"当前 {mod_version('MyPriv')}")


def test_single_mod_import_unmarked_overwrites():
    """未标记的 mod 撞名 = 老行为（直接覆盖，旧版改名备份）"""
    setup()
    write_mod(MOCK / "mods", "Other", "1.0")
    (MOCK / "mods" / "mod_load_order.txt").write_text("Other\n", encoding='utf-8')
    data = make_mod_zip("Other", "2.0")
    r = import_mod_archive("m.zip", data, force_mod=True)
    check("未标记 → 直接导入成功", r.get("ok") is True, str(r.get("error") or "")[:120])
    check("版本已更新到 2.0", mod_version("Other") == "2.0", f"当前 {mod_version('Other')}")
    check("旧版作为 .bak_ 留在 mods 里（老行为）", bool(list((MOCK / "mods").glob("Other.bak_*"))), "没找到备份")


def test_unmark_restores_old_behavior():
    """取消标记后 = 老行为（会被归档、不保留）"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    core_mods.set_my_mod("MyPriv", False)          # 取消标记
    check("名单已清空", core_mods.load_my_mods() == [], str(core_mods.load_my_mods()))
    data = make_pack_zip({"PackModA": "1.0"}, ["PackModA"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=False)
    check("未标记 → 目录被归档搬走", not (MOCK / "mods" / "MyPriv").exists())
    check("mine_kept 为空", not (r.get("mine_kept") or []), str(r.get("mine_kept")))


# ---- 「我的 mod」管理器库区（my_mods/）：自研 mod 的家 ----

def test_library_store_and_overview():
    """收进库 / 列库 / 手动部署回游戏"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    r = core_mods.store_my_mod("MyPriv")
    check("收进库成功", r.get("ok") is True, str(r.get("error")))
    check("库里有目录 + 有内容", (MOCK / "my_mods" / "MyPriv").is_dir() and r.get("size_kb", 0) > 0,
          f"size={r.get('size_kb')}")
    lib = core_mods.my_mods_library()
    check("列库：1 项且在库/已部署/已启用",
          len(lib) == 1 and lib[0]["in_lib"] and lib[0]["deployed"] and lib[0]["enabled"], str(lib))
    # 模拟游戏目录被清空 → 从库部署回来
    shutil.rmtree(MOCK / "mods" / "MyPriv")
    check("已模拟删除（游戏目录里没有它了）", not (MOCK / "mods" / "MyPriv").exists())
    d = core_mods.deploy_my_mod("MyPriv")
    check("从库部署成功", d.get("ok") is True, str(d.get("error")))
    check("部署后版本 = 库里那份（2.1）", mod_version("MyPriv") == "2.1", mod_version("MyPriv"))


def test_library_sync_from_game():
    """在游戏目录里改了代码 → 同步进库（库 = 最新已知良好版本）"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    core_mods.save_my_mods(["MyPriv"])
    core_mods.store_my_mod("MyPriv")
    # 在游戏目录里改成 2.2（模拟玩家直接改代码调试）
    write_mod(MOCK / "mods", "MyPriv", "2.2")
    r = core_mods.sync_my_mods_to_library()
    check("同步清单含它", "MyPriv" in (r.get("stored") or []), str(r))
    # 库被更新：删掉游戏目录再部署，应拿到 2.2
    shutil.rmtree(MOCK / "mods" / "MyPriv")
    core_mods.deploy_my_mod("MyPriv")
    check("库已更新到 2.2", mod_version("MyPriv") == "2.2", mod_version("MyPriv"))


def test_library_survives_pack_swap():
    """换包：库不受影响；游戏目录里原地保留；仍启用"""
    setup()
    write_mod(MOCK / "mods", "PackModA", "1.0")
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("PackModA\nMyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    core_mods.store_my_mod("MyPriv")
    data = make_pack_zip({"PackModA": "1.1"}, ["PackModA"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    check("换包成功", r.get("ok") is True, str(r.get("error"))[:120])
    check("库里副本仍在", (MOCK / "my_mods" / "MyPriv").is_dir())
    check("游戏目录里仍在", (MOCK / "mods" / "MyPriv").is_dir())
    check("仍启用", "MyPriv" in enabled_names(read_load_order()), str(enabled_names(read_load_order())))
    check("换包前做过库同步", "MyPriv" in (r.get("mine_lib_synced") or []), str(r.get("mine_lib_synced")))


def test_library_restores_wiped_mod_on_pack_swap():
    """**游戏目录被清空**后换包 → 从管理器库自动恢复 + 保持启用（库的核心价值）"""
    setup()
    write_mod(MOCK / "mods", "PackModA", "1.0")
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("PackModA\nMyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    core_mods.store_my_mod("MyPriv")            # 库里有副本
    shutil.rmtree(MOCK / "mods" / "MyPriv")     # ← 模拟"自己的 mod 被清空"（用户报的原始问题）
    data = make_pack_zip({"PackModA": "1.1"}, ["PackModA"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    check("导入成功", r.get("ok") is True, str(r.get("error"))[:120])
    check("从管理器库恢复", "MyPriv" in (r.get("mine_restored_from_lib") or []), str(r.get("mine_restored_from_lib")))
    check("目录回来了", (MOCK / "mods" / "MyPriv").is_dir())
    check("内容正确（2.1）", mod_version("MyPriv") == "2.1", mod_version("MyPriv"))
    check("并且仍是启用状态", "MyPriv" in enabled_names(read_load_order()), str(enabled_names(read_load_order())))
    check("消息提示从库恢复", "从管理器库恢复" in (r.get("message") or ""), (r.get("message") or "")[:220])


if __name__ == "__main__":
    test_missing_auto_restore()
    test_same_version_silent()
    test_version_conflict_pending()
    test_keep_off_restores_nothing()
    test_mine_kept_and_reenabled()
    test_mine_disabled_stays_disabled()
    test_mine_wins_over_pack_same_name()
    test_preview_reports_my_conflict()
    test_single_mod_import_guard()
    test_single_mod_import_unmarked_overwrites()
    test_unmark_restores_old_behavior()
    test_library_store_and_overview()
    test_library_sync_from_game()
    test_library_survives_pack_swap()
    test_library_restores_wiped_mod_on_pack_swap()
    print(f"\n结果: {len(FAILED)} 项失败")
    sys.exit(1 if FAILED else 0)
