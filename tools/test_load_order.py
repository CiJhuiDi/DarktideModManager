# -*- coding: utf-8 -*-
"""导入清单 API 测试：替换清单、保留注释、防呆"""
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
state.CONFIG_FILE = MOCK / 'config_lo_test.json'
state.BACKUP_DIR = MOCK / 'backups_lo_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

lo = MOCK / 'mods' / 'mod_load_order.txt'

print('=== 导入清单 ===')
content = 'TestModC\n--TestModA\nTestModB\n'
r = app.api_load_order_import(app.LoadOrderImportBody(content=content))
test('导入 ok', r.get('ok'), r.get('message'))
lines = lo.read_text(encoding='utf-8').splitlines()
test('清单已替换（旧式禁用标记被清理）', set(lines) == {'TestModC', 'TestModB'}, lines)

print('=== 带空行/CRLF 清洗 ===')
r = app.api_load_order_import(app.LoadOrderImportBody(content='TestModA\r\n\r\n--TestModB\r\n'))
test('CRLF+空行清洗 ok', r.get('ok'))
lines = lo.read_text(encoding='utf-8').splitlines()
test('空行被过滤（旧式禁用标记被清理）', '' not in lines and set(lines) == {'TestModA'}, lines)

print('=== 空内容拒绝 ===')
r = app.api_load_order_import(app.LoadOrderImportBody(content='  \n\n'))
test('空内容拒绝', not r.get('ok'))

print('=== 旧清单已备份 ===')
baks = list((state.BACKUP_DIR).glob('mod_load_order.*.bak'))
test('有备份', len(baks) >= 1, len(baks))

print('=== 游戏运行中拒绝 ===')
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r = app.api_load_order_import(app.LoadOrderImportBody(content='TestModA'))
test('游戏运行中拒绝', not r.get('ok') and '游戏正在运行' in r.get('error',''), r)
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
