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


def make_pack_zip(mods: dict, load_order=None, root_wrap="", with_list=True):
    """mods: {mod名: 版本}; 组装整合包 zip（可带外层目录）。

    with_list=False → 包里**不带** mod_load_order.txt（有些整合包确实没有，DMM 必须重建）"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        base = f"{root_wrap}/mods" if root_wrap else "mods"
        for name, ver in mods.items():
            z.writestr(f"{base}/{name}/{name}.mod", mod_body(name, ver))
            z.writestr(f"{base}/{name}/scripts/{name}.lua", f"-- {name}")
        if with_list:
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
    """包里有同名、**未传选择**时 → 默认保留我的版本（安全项），不用包的覆盖"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    data = make_pack_zip({"MyPriv": "3.0"}, ["MyPriv"])
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True)
    check("我的版本没被覆盖（仍是 2.1）", mod_version("MyPriv") == "2.1", f"当前 {mod_version('MyPriv')}")
    check("同名冲突已上报", "MyPriv" in (r.get("mine_pack_conflict") or []), str(r.get("mine_pack_conflict")))
    check("消息说明「保留你的版本」", "保留你的版本" in (r.get("message") or ""), (r.get("message") or "")[:200])
    check("仍在启用清单", "MyPriv" in enabled_names(read_load_order()), str(enabled_names(read_load_order())))


def test_mine_conflict_choice():
    """同名冲突：**逐个选择**决定用谁（程序不替玩家决定）——预览给足信息、导入按选择执行"""
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    write_mod(MOCK / "mods", "MyOther", "1.0")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\nMyOther\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv", "MyOther"])
    core_mods.store_my_mod("MyPriv")
    core_mods.store_my_mod("MyOther")
    data = make_pack_zip({"MyPriv": "3.0", "MyOther": "9.9", "PackModA": "1.0"},
                         ["MyPriv", "MyOther", "PackModA"])

    # ① 预览：如实反映（我的 mod 不算"移除"，冲突带两边版本供玩家选）
    p = preview_pack_archive("p.zip", data)
    check("预览列出两个同名冲突", p.get("my_conflicts") == ["MyOther", "MyPriv"], str(p.get("my_conflicts")))
    det = {x["name"]: x for x in (p.get("my_conflict_details") or [])}
    check("冲突详情带两边版本",
          det.get("MyPriv", {}).get("mine_version") == "2.1" and det.get("MyPriv", {}).get("pack_version") == "3.0",
          str(det.get("MyPriv")))
    check("我的 mod 不出现在「移除」里",
          not (set(p.get("removed") or []) & {"MyPriv", "MyOther"}), str(p.get("removed")))

    # ② 逐个选择：MyPriv 改用包里的、MyOther 保留我的
    r = import_pack_archive("p.zip", data, "replace", keep_enabled=True,
                            mine_choice={"MyPriv": "pack", "MyOther": "mine"})
    check("导入成功", r.get("ok") is True, str(r.get("error"))[:120])
    check("选「用包里的」→ 版本变成包的 3.0", mod_version("MyPriv") == "3.0", mod_version("MyPriv"))
    check("选「保留我的」→ 仍是 1.0", mod_version("MyOther") == "1.0", mod_version("MyOther"))
    check("回报用了包版本的清单", r.get("mine_used_pack") == ["MyPriv"], str(r.get("mine_used_pack")))
    check("两个仍记为同名冲突", set(r.get("mine_pack_conflict") or []) == {"MyPriv", "MyOther"},
          str(r.get("mine_pack_conflict")))
    check("消息区分两种处理", "保留你的版本" in (r.get("message") or "")
          and "按你的选择改用包里版本" in (r.get("message") or ""), (r.get("message") or "")[:240])
    # 管理器库里留着的仍是你自己的版本（包覆盖的是游戏目录那份，回滚靠库）
    import re as _re
    lf = MOCK / "my_mods" / "MyPriv" / "MyPriv.mod"
    lib_v = ""
    if lf.is_file():
        m = _re.search(r'version\s*=\s*"([^"]+)"', lf.read_text(encoding='utf-8'))
        lib_v = m.group(1) if m else ""
    check("库里副本仍是你自己的版本（未被包覆盖）", lib_v == "2.1", f"库内 {lib_v}")

    # ③ 不传选择 = 一律保留我的（安全默认）
    setup()
    write_mod(MOCK / "mods", "MyPriv", "2.1")
    (MOCK / "mods" / "mod_load_order.txt").write_text("MyPriv\n", encoding='utf-8')
    core_mods.save_my_mods(["MyPriv"])
    data2 = make_pack_zip({"MyPriv": "3.0"}, ["MyPriv"])
    r2 = import_pack_archive("p.zip", data2, "replace", keep_enabled=True)
    check("未传选择 → 默认保留我的（2.1）", mod_version("MyPriv") == "2.1", mod_version("MyPriv"))
    check("未传选择 → 不上报 used_pack", not (r2.get("mine_used_pack") or []), str(r2.get("mine_used_pack")))


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


def test_rebuild_load_order_when_pack_has_none():
    """包里没有 mod_load_order.txt → **必须重建**，否则 replace 归档掉旧清单后一个 mod 都不启用。

    用户 2026-10-10 报的「导入的新整合包没有重建 mod_load_order」就是这个场景。"""
    setup()
    write_mod(MOCK / "mods", "OldMod", "1.0")
    (MOCK / "mods" / "mod_load_order.txt").write_text("-- 我写的说明\nOldMod\n", encoding='utf-8')
    data = make_pack_zip({"NewA": "1.0", "NewB": "1.0"}, with_list=False)   # ← 包里不带清单

    p = preview_pack_archive("p.zip", data)
    check("预览就说明会重建清单", p.get("will_rebuild_load_order") is True, str(p.get("has_load_order")))

    r = import_pack_archive("p.zip", data, "replace")
    check("导入成功", r.get("ok") is True, str(r.get("error"))[:120])
    en = enabled_names(read_load_order())
    check("重建后包内 mod 都启用（不再是 0 个）", set(en) == {"NewA", "NewB"}, str(en))
    check("结果里带重建清单", set(r.get("load_order_rebuilt") or []) == {"NewA", "NewB"},
          str(r.get("load_order_rebuilt")))
    check("消息说明已重建清单", "没有启用清单，已重建" in (r.get("message") or ""), (r.get("message") or "")[:240])
    text = (MOCK / "mods" / "mod_load_order.txt").read_text(encoding='utf-8')
    check("**不搬运**旧清单的注释（那注释描述的是上一个包）", "-- 我写的说明" not in text,
          text.replace("\n", " | ")[:140])
    check("新清单带一行 DMM 自己的来源说明", text.lstrip().startswith("-- 本清单由 DMM"), text[:90])
    check("已不存在的旧条目被丢掉（不留幽灵行）", "OldMod" not in text, text.replace("\n", " | ")[:120])


def test_rebuild_keeps_order_and_merge_case():
    """重建时：仍存在的旧条目保持原有相对顺序，新增的按名字排在后面（merge 模式下最明显）"""
    setup()
    for n in ("Zeta", "Alpha", "Middle"):
        write_mod(MOCK / "mods", n, "1.0")
    # 旧清单顺序：Zeta、Middle（只启用两个；Alpha 没启用）
    (MOCK / "mods" / "mod_load_order.txt").write_text("Zeta\nMiddle\n", encoding='utf-8')
    data = make_pack_zip({"BrandNew": "1.0", "BrandNew2": "1.0"}, with_list=False)  # merge：不动旧 mod，只加两个
    r = import_pack_archive("p.zip", data, "merge")
    check("merge 导入成功", r.get("ok") is True, str(r.get("error"))[:120])
    en = enabled_names(read_load_order())
    check("旧条目顺序保留，包内新条目追加在后",
          en[:2] == ["Zeta", "Middle"] and en[2:] == ["BrandNew", "BrandNew2"], str(en))
    check("原来没启用的 Alpha 仍不启用（不擅自替玩家开）", "Alpha" not in en, str(en))


def test_pack_with_list_unchanged():
    """包**自带**清单：条目与顺序照作者，但**作者的注释不落盘**（2026-10-10 用户：
    「重新导入并没有重建清单」—— 他刚清掉 412 行作者注释，一导入又被搬回来）"""
    setup()
    write_mod(MOCK / "mods", "OldMod", "1.0")
    (MOCK / "mods" / "mod_load_order.txt").write_text("OldMod\n", encoding='utf-8')
    # 作者清单带注释与空行（真实整合包就是这样）
    data = make_pack_zip({"AuthorA": "1.0", "AuthorB": "1.0"}, ["-- 作者说明", "AuthorB", "", "-- === 分组 ===", "AuthorA"])
    p = preview_pack_archive("p.zip", data)
    check("预览统计包内注释行数", p.get("pack_lo_comments") == 2, str(p.get("pack_lo_comments")))
    r = import_pack_archive("p.zip", data, "replace")
    check("导入成功", r.get("ok") is True, str(r.get("error"))[:120])
    check("用的是作者清单（顺序也照作者）", enabled_names(read_load_order()) == ["AuthorB", "AuthorA"],
          str(enabled_names(read_load_order())))
    check("没有触发重建", not (r.get("load_order_rebuilt") or []), str(r.get("load_order_rebuilt")))
    text = (MOCK / "mods" / "mod_load_order.txt").read_text(encoding='utf-8')
    lines = text.splitlines()
    check("作者注释没落盘", "作者说明" not in text and "分组" not in text, text.replace("\n", " | ")[:120])
    check("作者的空行也没落盘", "" not in lines, str(lines))
    check("首行换成 DMM 的来源说明", lines[0].startswith("-- 本清单由 DMM"), lines[0] if lines else "")
    check("结果里报告丢掉的注释行数", (r.get("author_load_order") or {}).get("comments_dropped") == 2,
          str(r.get("author_load_order")))
    check("消息说明注释已备份", "注释" in (r.get("message") or "") and "备份" in (r.get("message") or ""),
          (r.get("message") or "")[:220])
    # 作者原清单整份留档（注释还在里面，随时能翻出作者的说明）
    arch = list((MOCK / "backups").glob("pack_backup_*/author_mod_load_order.txt"))
    check("作者原清单已归档", bool(arch), str(arch[:1]))
    if arch:
        at = arch[0].read_text(encoding='utf-8')
        check("归档里保留作者注释原文", "作者说明" in at and "分组" in at, at.replace("\n", " | ")[:120])

    # 作者清单里指向包内不存在的 mod → 该条移除（避免幽灵）
    setup()
    write_mod(MOCK / "mods", "OldMod", "1.0")
    data2 = make_pack_zip({"AuthorA": "1.0"}, ["-- 说明", "AuthorA", "NotInPack"])
    r2 = import_pack_archive("p.zip", data2, "replace")
    check("作者清单里的幽灵条目被移除", enabled_names(read_load_order()) == ["AuthorA"],
          str(enabled_names(read_load_order())))
    check("结果报告幽灵条目", (r2.get("author_load_order") or {}).get("dropped") == ["NotInPack"],
          str(r2.get("author_load_order")))


if __name__ == "__main__":
    test_missing_auto_restore()
    test_same_version_silent()
    test_version_conflict_pending()
    test_keep_off_restores_nothing()
    test_mine_kept_and_reenabled()
    test_mine_disabled_stays_disabled()
    test_mine_wins_over_pack_same_name()
    test_mine_conflict_choice()
    test_preview_reports_my_conflict()
    test_single_mod_import_guard()
    test_single_mod_import_unmarked_overwrites()
    test_unmark_restores_old_behavior()
    test_library_store_and_overview()
    test_library_sync_from_game()
    test_library_survives_pack_swap()
    test_library_restores_wiped_mod_on_pack_swap()
    test_rebuild_load_order_when_pack_has_none()
    test_rebuild_keeps_order_and_merge_case()
    test_pack_with_list_unchanged()
    print(f"\n结果: {len(FAILED)} 项失败")
    sys.exit(1 if FAILED else 0)
