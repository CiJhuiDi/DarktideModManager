# -*- coding: utf-8 -*-
"""备份恢复预览测试：备份 vs 当前差异"""
import sys, shutil, subprocess
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
state.CONFIG_FILE = MOCK / 'config_bprev_test.json'
state.BACKUP_DIR = MOCK / 'backups_bprev_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
MODS = MOCK / 'mods'

def wm(name, ver):
    d = MODS / name
    d.mkdir(exist_ok=True)
    (d / f'{name}.mod').write_text(
        f'return {{ run = function() new_mod("{name}", {{}}) end, packages = {{}}, version = "{ver}" }}',
        encoding='utf-8')

# 当前：TestModA(1.2) TestModB(0.5) TestModC(无) + NewMod(1.0)
wm('NewMod', '1.0')

# 构造备份：TestModA(2.0 更新) TestModB(0.5 相同) OldMod(新增回) 无 NewMod(移除)
ts = '20260815_000000'
bak_mods = state.BACKUP_DIR / f'pack_backup_{ts}' / 'mods'
bak_mods.mkdir(parents=True)
for name, ver in [('TestModA', '2.0'), ('TestModB', '0.5'), ('OldMod', '1.0')]:
    d = bak_mods / name
    d.mkdir()
    (d / f'{name}.mod').write_text(
        f'return {{ run = function() new_mod("{name}", {{}}) end, packages = {{}}, version = "{ver}" }}',
        encoding='utf-8')

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

print('=== 备份预览 ===')
r = app.api_backup_preview(f'pack_backup_{ts}')
test('预览 ok', r.get('ok'), r.get('error'))
print('  added:', r['added'], 'removed:', r['removed'], 'updated:', r['updated'], 'same:', r['same'])
test('新增 OldMod', r['added'] == ['OldMod'], r['added'])
test('移除含 NewMod', 'NewMod' in r['removed'], r['removed'])
test('更新 TestModA', r['updated'] == ['TestModA'], r['updated'])
test('相同 TestModB', r['same'] == ['TestModB'], r['same'])
test('计数', r['bak_count'] == 3 and r['cur_count'] == 5, (r['bak_count'], r['cur_count']))

print('=== 只读（不写文件）===')
test('mock 未被改动', (MODS / 'NewMod').exists() and not (MODS / 'OldMod').exists())

print('=== 防呆 ===')
r = app.api_backup_preview('pack_backup_nonexist')
test('不存在拒绝', not r.get('ok'))
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r = app.api_backup_preview(f'pack_backup_{ts}')
test('游戏运行中拒绝', not r.get('ok') and '游戏正在运行' in r.get('error', ''), r)
app.is_game_running = lambda: False
patch.is_game_running = lambda: False

# 清理
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 通过')
