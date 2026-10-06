# -*- coding: utf-8 -*-
"""目录联接（Junction）安全回归：开发机常把源码工程 Junction 直连进游戏 mods 目录。

实测事实（Python 3.12）：
  · `shutil.rmtree(junction)` 直接抛 OSError 拒绝 —— 顶层删除会失败
  · `rmtree(内含 junction 的父目录)` 只摘链接、**不穿透删目标内容**
  · `copytree(junction)` 复制的是**真实内容**；`move(junction)` 搬的是**链接**
本测试守住的是：**管理器的所有删除动作都不能碰坏联接目标（= 用户的源码）**，
以及"部署回游戏"遇到联接时按链接摘除、并如实回报。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import state                       # noqa: E402
from core import mods as core_mods           # noqa: E402
from core import imports as core_imports     # noqa: E402

MOCK = ROOT / 'mock_junction'
FAILED = []


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f"  <- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


def make_junction(link: Path, target: Path) -> bool:
    """建目录联接（不需要管理员权限）；失败返回 False"""
    link.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
    return link.exists() and state.is_junction(link)


def setup():
    if MOCK.exists():
        # 先把可能残留的联接摘掉，避免 rmtree 撞上
        for p in MOCK.rglob('*'):
            if state.is_junction(p):
                try:
                    os.rmdir(p)
                except OSError:
                    pass
        shutil.rmtree(MOCK, ignore_errors=True)
    (MOCK / 'src').mkdir(parents=True)
    (MOCK / 'src' / 'scripts').mkdir()
    (MOCK / 'src' / 'keep_me.lua').write_text('-- 源码，绝不能被删', encoding='utf-8')
    (MOCK / 'src' / 'my_mod.mod').write_text('return {}', encoding='utf-8')
    (MOCK / 'game' / 'mods').mkdir(parents=True)
    (MOCK / 'backups').mkdir(parents=True)
    state.GAME_DIR = MOCK / 'game'
    state.MODS_DIR = state.GAME_DIR / 'mods'
    state.LOAD_ORDER_FILE = state.MODS_DIR / 'mod_load_order.txt'
    state.BACKUP_DIR = MOCK / 'backups'
    state.MY_MODS_DIR = MOCK / 'my_mods'
    state.CONFIG_FILE = MOCK / 'config_test.json'
    core_mods.MY_MODS_FILE = MOCK / 'my_mods.json'
    core_mods._my_mods_cache = None


if not hasattr(os.path, 'isjunction'):
    print('本机 Python 不支持 os.path.isjunction，跳过')
    print("===== 0/0 通过 =====")
    sys.exit(0)

print("===== 1. 建联接 + 识别 =====")
setup()
link = state.MODS_DIR / 'my_mod'
ok = make_junction(link, MOCK / 'src')
if not ok:
    print('本机无法建目录联接（非 NTFS？），跳过')
    shutil.rmtree(MOCK, ignore_errors=True)
    print("===== 0/0 通过 =====")
    sys.exit(0)
check('联接建立并被识别', state.is_junction(link), str(link))

print("\n===== 2. safe_rmtree(联接) 只摘链接，源码完好 =====")
state.safe_rmtree(link)
check('链接已摘', not link.exists())
check('源码文件仍在', (MOCK / 'src' / 'keep_me.lua').is_file())
check('源码目录仍在', (MOCK / 'src' / 'scripts').is_dir())

print("\n===== 3. safe_rmtree(内含联接的父目录) 不穿透 =====")
link = state.MODS_DIR / 'my_mod'
make_junction(link, MOCK / 'src')
parent = MOCK / 'backup_like' / 'mods'
shutil.copytree(state.MODS_DIR, parent)
# 父目录里塞一个联接（模拟归档后再清理）
os.rmdir(link)
make_junction(parent / 'linked', MOCK / 'src')
state.safe_rmtree(MOCK / 'backup_like', ignore_errors=True)
check('父目录已删', not (MOCK / 'backup_like').exists())
check('源码仍然完好（父目录删除没穿透）', (MOCK / 'src' / 'keep_me.lua').is_file())

print("\n===== 4. 收进库：复制的是真实内容（不是链接） =====")
setup()
link = state.MODS_DIR / 'my_mod'
make_junction(link, MOCK / 'src')
r = core_mods.store_my_mod('my_mod')
check('收库成功', r.get('ok') is True, str(r))
check('库内拿到的不是链接', not state.is_junction(state.MY_MODS_DIR / 'my_mod'))
check('库内有真实文件', (state.MY_MODS_DIR / 'my_mod' / 'my_mod.mod').is_file())

print("\n===== 5. 部署回游戏：遇到联接只摘链接，源码不受影响 =====")
r2 = core_mods.deploy_my_mod('my_mod')
check('部署成功', r2.get('ok') is True, str(r2))
check('如实回报"原来那份是联接"', r2.get('junction_replaced') is True, str(r2))
check('源码仍然完好', (MOCK / 'src' / 'keep_me.lua').is_file())
check('游戏目录里现在是真实副本（不再是链接）', not state.is_junction(state.MODS_DIR / 'my_mod')
      and (state.MODS_DIR / 'my_mod' / 'my_mod.mod').is_file())

print("\n===== 6. 清理备份时不会穿透联接 =====")
setup()
link = MOCK / 'backups' / 'pack_backup_20260101_000000' / 'mods' / 'linked'
make_junction(link, MOCK / 'src')
for i in range(3):                                   # 造几个备份触发清理
    d = MOCK / 'backups' / f'pack_backup_2026010{i}_000000' / 'mods' / f'M{i}'
    d.mkdir(parents=True)
    (d / 'x.mod').write_text('x', encoding='utf-8')
core_imports.save_backup_policy(max_per_type=2)
core_imports.prune_backups()
check('清理执行后源码仍完好', (MOCK / 'src' / 'keep_me.lua').is_file())
check('联接目标目录内容没少', (MOCK / 'src' / 'my_mod.mod').is_file())

# 收尾
for p in MOCK.rglob('*'):
    if state.is_junction(p):
        try:
            os.rmdir(p)
        except OSError:
            pass
shutil.rmtree(MOCK, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)

print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过 通过")
