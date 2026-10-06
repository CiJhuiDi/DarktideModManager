# -*- coding: utf-8 -*-
"""真机 E2E 校验：DMM 写入的清单，在运行中的游戏里是否真的生效。

依赖 dt-cli（随 LuaExec mod 分发，<game>/mods/LuaExec/bin/dt-cli.exe）。
未安装 / 游戏没运行 / 管道不可用 -> 打印 SKIP 并以 0 退出（可安全并入 test_full）。

校验逻辑：
  1. 读取 DMM 视角的启用清单（mod_load_order.txt，剔除 dmf/base/注释）
  2. 用 dt-cli 在游戏 Lua 里批量查询每个 mod 的注册与启用状态
  3. 对比：
       * 清单里有、游戏里查不到      -> FAIL（写入未生效，DMM 的问题）
       * 清单里有、注册但 disabled   -> INFO（DMF 内部关闭，属另一层；游戏里按 F4 可查看/开启）
       * 清单里没有、游戏里却注册着  -> INFO（本次会话历史残留，重启即消失）

层级说明（别搞混）：
  * DMM 的启用/停用 = mod 清单（mod_load_order.txt）层面，决定 DML 底层**加不加载**
  * DMF 自带另一层 per-mod 开关（user_settings.config 的 disabled_mods_list），决定加载后**生不生效**
  * 两层互相独立，所以「清单已启用 + DMF 内部关闭」是正常组合，不是 DMM 的 bug

用法：
    python tools/e2e_dtcli.py [--game <游戏目录>] [--pid <pid>] [--verbose]
"""
import argparse
import io
import json
import os
import subprocess
import sys
from pathlib import Path

# 用 reconfigure 而非重建 TextIOWrapper：后者在本脚本被 import 时会因旧 wrapper 被 GC
# 而关闭底层 buffer，导致调用方 print 报 "I/O operation on closed file"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SYSTEM_MODS = {"base", "dmf"}   # DML 自动插入/框架自身，不属用户清单


def resolve_game_dir(arg: str | None) -> Path | None:
    """解析真实游戏目录。

    注意：不能直接用 core.state.GAME_DIR —— 开发环境仓库根的 config.json 常把 game_dir
    指向 mock/（测试用），会误把 mock 当成游戏。这里只信 Steam 库扫描 + 显式参数。
    """
    if arg:
        p = Path(arg)
        return p if p.is_dir() else None
    try:
        from core.state import detect_game_dir
        p = detect_game_dir()          # 只扫 Steam 库，忽略 config.json
        if p and p.is_dir() and p.name == "Warhammer 40,000 DARKTIDE":
            return p
    except Exception:
        pass
    for cand in (os.environ.get("DARKTIDE_DIR"),
                 r"D:\SteamLibrary\steamapps\common\Warhammer 40,000 DARKTIDE"):
        if cand and Path(cand).is_dir():
            return Path(cand)
    return None


def load_enabled_names(game: Path) -> list:
    order = game / "mods" / "mod_load_order.txt"
    if not order.exists():
        return []
    names = []
    for ln in order.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("--"):
            continue
        if ln in SYSTEM_MODS or ln in names:
            continue
        names.append(ln)
    return names


def run_dtcli(dtcli: Path, args: list) -> tuple[bool, str]:
    try:
        r = subprocess.run([str(dtcli)] + args, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        return False, f"调用失败: {e}"
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def lua_probe(names: list) -> str:
    """一行 Lua：批量查注册+启用状态，返回 name=on|off|missing 串联串"""
    quoted = ",".join('"%s"' % n.replace('"', '') for n in names)
    return (
        'local n={%s} local o={} for _,x in ipairs(n) do '
        'local ok,m=pcall(get_mod,x) '
        'o[#o+1]=x.."="..((ok and m) and (m:is_enabled() and "on" or "off") or "missing") '
        'end return table.concat(o,";")' % quoted
    )


def lua_list_registered() -> str:
    """一行 Lua：枚举 DMF 已注册的全部 mod 名（Managers.mod._mods 是数字索引表）"""
    return (
        'local t={} for _,m in pairs(Managers.mod._mods) do '
        'local ok,n=pcall(function() return m:get_name() end) '
        'if ok and n then t[#t+1]=n end end '
        'table.sort(t) return table.concat(t, ",")'
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=None)
    ap.add_argument("--pid", default=None, help="多开时指定游戏进程 PID（dt-cli -p）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    game = resolve_game_dir(args.game)
    if not game:
        print("SKIP: 未能解析游戏目录（用 --game 指定）")
        return 0
    print(f"游戏目录: {game}")

    dtcli = game / "mods" / "LuaExec" / "bin" / "dt-cli.exe"
    if not dtcli.exists():
        print("SKIP: dt-cli 未安装 —— 需要 LuaExec mod（Nexus 暗潮 mod 1016）")
        print(f"      期望位置: {dtcli}")
        print("      安装：python D:\\DeepseekWorkspace\\暗潮\\tools\\install_luaexec.py <下载的压缩包> --enable")
        return 0

    pre = ["-p", args.pid] if args.pid else []
    ok, out = run_dtcli(dtcli, pre + ["version"])
    if not ok:
        print("SKIP: dt-cli 无法执行:", out.strip()[:300])
        return 0
    print("dt-cli:", out.strip().splitlines()[0] if out.strip() else "(无输出)")
    if args.verbose:
        print("       完整输出:", out.strip()[:300])

    names = load_enabled_names(game)
    if not names:
        print("SKIP: 清单里没有用户 mod（mod_load_order.txt 为空或只有系统项）")
        return 0
    print(f"清单启用项: {len(names)} 个")

    ok, out = run_dtcli(dtcli, pre + ["exec", lua_probe(names)])
    if not ok:
        print("SKIP: 游戏未运行或 LuaExec 未加载（管道不可用）")
        print("      dt-cli 原话:", out.strip()[:300])
        return 0

    # 解析 dt-cli 的 JSON 输出
    try:
        payload = json.loads(out.strip().splitlines()[-1])
    except Exception:
        print("SKIP: dt-cli 输出不是预期 JSON:", out.strip()[:300])
        return 0
    if not payload.get("ok"):
        print("SKIP: Lua 执行失败:", str(payload.get("error"))[:300])
        return 0

    text = str(payload.get("output") or "")
    state = {}
    for item in text.split(";"):
        if "=" in item:
            k, v = item.rsplit("=", 1)
            state[k] = v

    missing, disabled = [], []
    for n in names:
        st = state.get(n, "missing")
        if st == "missing":
            missing.append(n)
        elif st == "off":
            disabled.append(n)

    # 反向检查：游戏里注册着、但 DMM 清单里没有的（历史残留 / 手工加过）
    extras = []
    ok2, out2 = run_dtcli(dtcli, pre + ["exec", lua_list_registered()])
    if ok2:
        try:
            p2 = json.loads(out2.strip().splitlines()[-1])
            if p2.get("ok"):
                registered = [x for x in str(p2.get("output") or "").split(",") if x]
                known = set(names) | SYSTEM_MODS
                extras = [x for x in registered if x not in known]
        except Exception:
            pass

    print("\n=== 结果 ===")
    print(f"  生效（已注册且启用）: {sum(1 for n in names if state.get(n) == 'on')}/{len(names)}")
    if disabled:
        print(f"  [INFO] DMF 内部关闭（mod 已加载，但不在游戏内生效；游戏里按 F4 可查看/开启）: {disabled}")
    if extras:
        print(f"  [INFO] 游戏里注册但清单里没有（历史残留，重启即消失）: {extras}")
    if missing:
        print(f"  [FAIL] 清单里有但游戏里查不到（DMM 写入未生效）: {missing}")
    else:
        print("  PASS: 清单里的 mod 全部已在游戏内加载（DMM 写入有效）")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
