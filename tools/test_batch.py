# -*- coding: utf-8 -*-
"""批量操作 API 测试：enable/disable/delete/remove + 游戏运行拒绝"""
import sys, json
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
import patch
import state

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_batch_test.json'
state.BACKUP_DIR = MOCK / 'backups_batch_test'
state.PROFILES_DIR = MOCK / 'profiles_batch_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

# 用 build_mock 重建干净环境
import subprocess
subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)

# 补一个残留 ghost（清单里有、磁盘没有）
lo = MOCK / 'mods' / 'mod_load_order.txt'
lo.write_text(lo.read_text(encoding='utf-8') + 'GhostMod\n', encoding='utf-8')

def reset():
    subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
    lo.write_text(lo.read_text(encoding='utf-8') + 'GhostMod\n', encoding='utf-8')

def enabled_names():
    return app.enabled_names(app.read_load_order())

checks = []

def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

print('=== 批量启停 ===')
reset()
r = app.api_mods_batch(app.BatchBody(names=['TestModA', 'TestModB'], action='disable'))
test('批量禁用 ok', r.get('ok'), r)
test('done=2', len(r.get('done', [])) == 2, r)
test('A/B 已禁用', 'TestModA' not in enabled_names() and 'TestModB' not in enabled_names(), enabled_names())

r = app.api_mods_batch(app.BatchBody(names=['TestModA', 'TestModB'], action='enable'))
test('批量启用 ok', r.get('ok'))
test('A/B 已启用', 'TestModA' in enabled_names() and 'TestModB' in enabled_names(), enabled_names())

print('=== 批量清残留 ===')
reset()
r = app.api_mods_batch(app.BatchBody(names=['GhostMod'], action='remove'))
test('清残留 ok', r.get('ok'))
test('GhostMod 已移除', 'GhostMod' not in enabled_names(), enabled_names())

print('=== 批量删除 ===')
reset()
r = app.api_mods_batch(app.BatchBody(names=['TestModC'], action='delete'))
test('删除 ok', r.get('ok'))
test('TestModC 目录已删', not (MOCK / 'mods' / 'TestModC').exists())

print('=== 批量删除系统组件被拒 ===')
reset()
r = app.api_mods_batch(app.BatchBody(names=['base'], action='delete'))
test('base 删除失败(failed 收集)', not r.get('done') and len(r.get('failed', [])) == 1, r)

print('=== 游戏运行中整批拒绝 ===')
reset()
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r = app.api_mods_batch(app.BatchBody(names=['TestModA'], action='disable'))
test('游戏运行中拒绝', not r.get('ok') and '游戏正在运行' in r.get('error', ''), r)
app.is_game_running = lambda: False
patch.is_game_running = lambda: False

print('=== 空参数/非法操作 ===')
r = app.api_mods_batch(app.BatchBody(names=[], action='enable'))
test('空 names 拒绝', not r.get('ok'))
r = app.api_mods_batch(app.BatchBody(names=['A'], action='explode'))
test('非法 action 拒绝', not r.get('ok'))

# 清理
import shutil
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
shutil.rmtree(state.PROFILES_DIR, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks) - len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 通过')
