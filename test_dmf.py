# -*- coding: utf-8 -*-
"""DMF 一键安装功能测试：模拟全新玩家目录（无 mods/base、无 tools、无自动装载插件）"""
import shutil
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app
from core import dmf
from core import patch
from core import state

ROOT = Path(__file__).resolve().parent
FRESH = ROOT / "mock_fresh"
FAILED = []


def check(name, cond, detail=""):
    mark = "OK " if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  <- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def setup_fresh():
    if FRESH.exists():
        shutil.rmtree(FRESH)
    (FRESH / "bundle").mkdir(parents=True)
    (FRESH / "bundle" / "bundle_database.data").write_bytes(b"fake db no patch_999")
    (FRESH / "binaries" / "plugins").mkdir(parents=True)
    (FRESH / "mods").mkdir()
    # 预置旧版 mod_manager.lua（测试备份）+ 自动装载禁用残留 .off
    (FRESH / "mods" / "base").mkdir()
    (FRESH / "mods" / "base" / "mod_manager.lua").write_text("-- OLD VERSION", encoding="utf-8")
    (FRESH / "binaries" / "plugins" / "_dt_mod_autopatch.dll.off").write_bytes(b"off")


def point_to(fresh: Path):
    state.GAME_DIR = fresh.resolve()
    state.MODS_DIR = state.GAME_DIR / "mods"
    state.LOAD_ORDER_FILE = state.MODS_DIR / "mod_load_order.txt"
    state.CONFIG_FILE = fresh.resolve() / "config_test.json"   # 防污染项目根 config.json


def all_payload_files():
    """payload 内全部待释放文件（相对路径）"""
    out = []
    for sub in dmf.DMF_SUBTREES:
        base = dmf.DMF_PAYLOAD_DIR / sub
        if base.is_dir():
            for f in base.rglob("*"):
                if f.is_file():
                    out.append(f.relative_to(dmf.DMF_PAYLOAD_DIR))
    return out


print("===== 1. 全新玩家：DMF 状态检测 =====")
setup_fresh()
point_to(FRESH)
st = dmf.dmf_state()
check("bundle 存在 -> 游戏目录有效", st["game_dir_valid"] is True, str(st))
check("DMF 未安装", st["installed"] is False)
check("缺失组件数 = 7（旧 mod_manager.lua + .off 禁用不算缺失）", len(st["missing"]) == len(dmf.DMF_FILES) - 2, str(st["missing"]))
check("检测到 .off 禁用残留", st["autopatch_off"] is True)
check("内置 payload 版本可读", bool(st["payload_version"]), st["payload_version"])

print("\n===== 2. 一键安装（monkeypatch 补丁成功路径） =====")
setup_fresh()
point_to(FRESH)
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock patched"}
r = app.api_dmf_install()
check("安装返回 ok", r.get("ok") is True, str(r)[:300])
expected_files = {str(x) for x in all_payload_files()}
check("全部 payload 文件已释放", set(r.get("components_installed", [])) == expected_files, f"{len(r.get('components_installed', []))} vs {len(expected_files)}")
for rel in dmf.DMF_FILES:
    check(f"关键文件到位: {rel}", (state.GAME_DIR / rel).is_file())
# 内容与 payload 一致
import hashlib
ok_hash = all(
    hashlib.sha256((dmf.DMF_PAYLOAD_DIR / x).read_bytes()).digest()
    == hashlib.sha256((state.GAME_DIR / x).read_bytes()).digest()
    for x in all_payload_files()
)
check("释放内容与内置 payload 一致", ok_hash)
# 旧版文件被备份
baks = list((ROOT / "backups").glob("dmf_backup_*/mods/base/mod_manager.lua"))
check("旧版 mod_manager.lua 已备份", len(baks) >= 1, str(baks[:1]))
check("备份内容 = 旧版", baks and baks[0].read_text(encoding="utf-8") == "-- OLD VERSION")
# 自动装载恢复
check(".off 残留已清除", not (state.GAME_DIR / dmf.AUTOPATCH_DLL_OFF).exists())
check("管理器禁用标记已清除", app.auto_patch_disabled() is False)
check("补丁已激活提示", "补丁已激活" in r["message"], r["message"])

print("\n===== 3. 重复安装（幂等，已存在不报错） =====")
r2 = app.api_dmf_install()
check("重复安装 ok", r2.get("ok") is True, r2.get("message", "")[:120])
check("重复安装不报错", "失败" not in r2.get("message", ""))

print("\n===== 4. 真实 dtkit-patch 路径（垃圾数据库 -> 不崩溃、提示合理） =====")
setup_fresh()
point_to(FRESH)
# 假数据不含 patch_999 字样
(state.GAME_DIR / "bundle" / "bundle_database.data").write_bytes(b"FAKE_DB_BINARY_DATA")
r3 = app.api_dmf_install()
check("文件已释放（即使补丁失败）", all((state.GAME_DIR / rel).is_file() for rel in dmf.DMF_FILES))
check("安装流程不崩溃且返回 ok", r3.get("ok") is True)
check("message 有明确结果", ("补丁已激活" in r3.get("message", "")) or ("补丁未打上" in r3.get("message", "")), r3.get("message", "")[:200])

print("\n===== 5. 游戏运行中 -> 拒绝安装 =====")
setup_fresh()
point_to(FRESH)
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r4 = app.api_dmf_install()
check("运行中拒绝", r4.get("ok") is False and "运行" in r4.get("error", ""), r4.get("error", ""))
app.is_game_running = app_orig_is_running = None  # 恢复由下一行做
from importlib import reload
# 直接恢复原始函数（模块里定义在 subprocess 之后，这里重新赋值）
import subprocess as _sp

def _real_is_game_running():
    try:
        out = _sp.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10,
                      creationflags=0x08000000).stdout
        return "Darktide.exe" in out
    except Exception:
        return False
app.is_game_running = _real_is_game_running

print("\n===== 6. 自动装载被禁用（.off）：不算缺失，不误报 =====")
setup_fresh()
point_to(FRESH)
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
app.is_game_running = lambda: False
patch.is_game_running = lambda: False
r6 = app.api_dmf_install()  # 先正常装好
check("安装完成", r6.get("ok") is True)
# 模拟卸载补丁：自动装载插件改名 .off（真实卸载逻辑）
ap = FRESH / "binaries" / "plugins" / "_dt_mod_autopatch.dll"
ap.rename(FRESH / "binaries" / "plugins" / "_dt_mod_autopatch.dll.off")
st6 = dmf.dmf_state()
check("missing 不含 autopatch dll", "binaries/plugins/_dt_mod_autopatch.dll" not in st6["missing"], str(st6["missing"]))
check("installed 仍为 True", st6["installed"] is True)
check("autopatch_off 标记为 True", st6["autopatch_off"] is True)
check("其他组件仍完整", st6["missing"] == [], str(st6["missing"]))

print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过 通过")
