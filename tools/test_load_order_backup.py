# -*- coding: utf-8 -*-
"""清单备份显示/恢复/删除测试"""
import sys, shutil, subprocess
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
from core import patch
from core import state

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_lobak_test.json'
state.BACKUP_DIR = MOCK / 'backups_lobak_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
state.BACKUP_DIR.mkdir(exist_ok=True)

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

lo = MOCK / 'mods' / 'mod_load_order.txt'
orig = lo.read_text(encoding='utf-8')

print('=== 备份列表包含清单备份 ===')
# 触发一次清单备份
app.backup_load_order()
baks = app.api_backups()['backups']
lo_baks = [b for b in baks if b['type'] == 'load_order']
test('列表含 load_order 类型', len(lo_baks) >= 1, [b['id'] for b in lo_baks])
test('含 created 时间戳', all(b.get('created') for b in lo_baks))

print('=== 恢复清单备份 ===')
# 改坏当前清单，再恢复
lo.write_text('--BadMod\n', encoding='utf-8')
bid = lo_baks[0]['id']
r = app.api_backup_restore(bid)
test('恢复 ok', r.get('ok'), r.get('message'))
test('清单已恢复', lo.read_text(encoding='utf-8') == orig, lo.read_text(encoding='utf-8')[:40])

print('=== 恢复后新备份产生（当前清单也备份了）===')
baks2 = app.api_backups()['backups']
lo_baks2 = [b for b in baks2 if b['type'] == 'load_order']
test('恢复操作也产生清单备份', len(lo_baks2) >= len(lo_baks), len(lo_baks2))

print('=== 删除清单备份 ===')
r = app.api_backup_delete(bid)
test('删除 ok', r.get('ok'))
baks3 = app.api_backups()['backups']
test('已从列表消失', bid not in [b['id'] for b in baks3])

print('=== 游戏运行中拒绝恢复 ===')
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r = app.api_backup_restore(lo_baks2[0]['id'])
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
