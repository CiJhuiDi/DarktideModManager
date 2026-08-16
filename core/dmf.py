# -*- coding: utf-8 -*-
"""DMF 一键安装/检测（纯逻辑，无 FastAPI 依赖）。"""
import shutil
from datetime import datetime
from pathlib import Path

from core import state
from core import patch
from core.imports import prune_backups

# 内置 DMF 组件：关键文件清单（用于检测"是否装齐"；释放按 payload 子树全量拷贝）
DMF_FILES = [
    "mods/base/mod_manager.lua",
    "mods/base/function/class.lua",
    "mods/base/function/hook.lua",
    "mods/base/function/require.lua",
    "mods/dmf/dmf.mod",
    "mods/dmf/localization/dmf.lua",
    "mods/dmf/scripts/mods/dmf/dmf_loader.lua",
    "tools/dtkit-patch.exe",
    "binaries/plugins/_dt_mod_autopatch.dll",
]
# 释放时只拷这些子树（保持相对游戏目录结构；payload 根文件如 VERSION.txt 不释放）
DMF_SUBTREES = ["mods", "tools", "binaries"]
DMF_PAYLOAD_DIR = state.RESOURCE_DIR / "dmf_payload"
AUTOPATCH_DLL_OFF = Path("binaries") / "plugins" / "_dt_mod_autopatch.dll.off"


def dmf_payload_files() -> list:
    """payload 内待释放文件（相对游戏目录路径）"""
    files = []
    for sub in DMF_SUBTREES:
        base = DMF_PAYLOAD_DIR / sub
        if base.is_dir():
            for f in base.rglob("*"):
                if f.is_file():
                    files.append(f.relative_to(DMF_PAYLOAD_DIR))
    return files


def dmf_payload_version() -> str:
    """内置 DMF 组件版本说明（VERSION.txt 首行，仅供展示）"""
    try:
        v = (DMF_PAYLOAD_DIR / "VERSION.txt").read_text(encoding="utf-8", errors="ignore")
        return v.strip().splitlines()[0] if v.strip() else ""
    except Exception:
        return ""


def dmf_state() -> dict:
    """检测游戏目录 DMF 组件齐全度（自动装载插件被主动禁用 .off 不算缺失）"""
    valid = state.is_valid_game_dir(state.GAME_DIR)
    missing = []
    if valid:
        off_exists = (state.GAME_DIR / AUTOPATCH_DLL_OFF).exists()
        for rel in DMF_FILES:
            if not (state.GAME_DIR / rel).is_file():
                # 卸载补丁会把自动装载插件改名 .off 禁用——那是用户主动操作，不是缺失
                if rel == "binaries/plugins/_dt_mod_autopatch.dll" and off_exists:
                    continue
                missing.append(rel)
    return {
        "game_dir_valid": valid,
        "installed": valid and not missing,
        "missing": missing,
        "autopatch_off": (state.GAME_DIR / AUTOPATCH_DLL_OFF).exists() if valid else False,
        "payload_version": dmf_payload_version(),
    }


def install_dmf(force: bool = False) -> dict:
    """一键安装/覆盖更新 DMF：释放内置组件（已有文件先备份）→ 恢复自动装载 → 打补丁激活 mods。
    force=True 时即使已装完整也强制用内置组件覆盖（用于更新/清除旧版残留组件）。"""
    if not state.GAME_DIR.is_dir():
        return {"ok": False, "error": "未设置正确的游戏目录，请先到「关于」页设置"}
    if not state.is_valid_game_dir(state.GAME_DIR):
        return {"ok": False, "error": "游戏目录无效，请先到「关于」页设置正确的游戏目录"}
    if not DMF_PAYLOAD_DIR.is_dir():
        return {"ok": False, "error": "内置 DMF 组件缺失（打包不完整），请重新下载管理器"}
    if patch.is_game_running():
        return {"ok": False, "error": "游戏正在运行，请先关闭游戏再安装 DMF"}

    # 1. 释放组件；已有同名文件先备份到 backups\dmf_backup_<时间戳>\
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_root = state.BACKUP_DIR / f"dmf_backup_{ts}"
    files = dmf_payload_files()
    if not files:
        return {"ok": False, "error": "内置 DMF 组件缺失（打包不完整），请重新下载管理器"}
    installed, backed = [], []
    for rel in files:
        src = DMF_PAYLOAD_DIR / rel
        dst = state.GAME_DIR / rel
        try:
            if dst.exists():
                b = bak_root / rel
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, b)
                backed.append(str(rel))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            installed.append(str(rel))
        except Exception as e:
            return {"ok": False, "error": f"释放 {rel} 失败: {e}"}

    # 2. 恢复自动装载插件（清除 .off 残留 + 管理器禁用标记）
    off = state.GAME_DIR / AUTOPATCH_DLL_OFF
    if off.exists():
        try:
            off.unlink()
        except Exception:
            pass
    patch.set_auto_patch_disabled(False)

    # 3. 打补丁激活 mods
    act = "覆盖更新" if force else "安装"
    msg = f"✓ DMF {act}完成（{len(installed)} 个组件）"
    if installed:
        r = patch._run_patch("--patch")
        if r.get("patched"):
            msg += "，补丁已激活，mods 已就绪"
        else:
            msg += f"，但补丁未打上：{r.get('error') or (r.get('output') or '未知原因')[-200:]}"
    pruned = prune_backups()
    if pruned:
        msg += f"（已清理 {len(pruned)} 个旧备份）"
    return {"ok": True, "message": msg, "components_installed": installed, "backed_up": backed, **dmf_state()}
