# -*- coding: utf-8 -*-
"""清单差异预览测试：备份来源 / 预设来源 / 内容来源"""
import sys, shutil, subprocess, json
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
state.CONFIG_FILE = MOCK / 'config_lopv_test.json'
state.BACKUP_DIR = MOCK / 'backups_lopv_test'
state.PROFILES_DIR = MOCK / 'profiles_lopv_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
MODS = MOCK / 'mods'
# 当前：TestModA/B/C 启用，DisabledMod 禁用
lo = MODS / 'mod_load_order.txt'

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

print('=== 内容来源 ===')
# 目标：TestModA + DisabledMod（开）+ NewMod（新）→ A 保持、DisabledMod 启用、NewMod 启用、B/C 禁用
r = app.api_load_order_preview(app.LoadOrderPreviewBody(content='TestModA\nDisabledMod\nNewMod\n'))
test('预览 ok', r.get('ok'), r.get('error'))
test('启用 DisabledMod', 'DisabledMod' in r['turn_on'], r['turn_on'])
test('启用 NewMod', 'NewMod' in r['turn_on'], r['turn_on'])
test('禁用 B/C', set(r['turn_off']) == {'TestModB', 'TestModC'}, r['turn_off'])
test('保持 A', r['keep_on'] == ['TestModA'], r['keep_on'])
test('计数', r['target_count'] == 3 and r['cur_on_count'] == 3, (r['target_count'], r['cur_on_count']))

print('=== 备份来源 ===')
state.BACKUP_DIR.mkdir(exist_ok=True)
bak = state.BACKUP_DIR / 'mod_load_order.20260815_000000.bak'
bak.write_text('TestModC\nTestModA\n', encoding='utf-8')
r = app.api_load_order_preview(app.LoadOrderPreviewBody(source='backup:mod_load_order.20260815_000000.bak'))
test('备份来源 ok', r.get('ok'))
test('禁用 B', 'TestModB' in r['turn_off'], r['turn_off'])
test('备份不存在拒绝', not app.api_load_order_preview(app.LoadOrderPreviewBody(source='backup:nope.bak')).get('ok'))

print('=== 预设来源 ===')
state.PROFILES_DIR.mkdir(exist_ok=True)
(state.PROFILES_DIR / '打宝流.json').write_text(json.dumps({'mods': ['TestModB']}), encoding='utf-8')
r = app.api_load_order_preview(app.LoadOrderPreviewBody(source='profile:打宝流'))
test('预设来源 ok', r.get('ok'))
test('只留 B 启用', r['keep_on'] == ['TestModB'] and set(r['turn_off']) == {'TestModA', 'TestModC'}, (r['keep_on'], r['turn_off']))

print('=== 防呆 ===')
r = app.api_load_order_preview(app.LoadOrderPreviewBody(content=''))
test('空内容拒绝', not r.get('ok'))
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r = app.api_load_order_preview(app.LoadOrderPreviewBody(content='TestModA'))
test('游戏运行中拒绝', not r.get('ok') and '游戏正在运行' in r.get('error', ''), r)
app.is_game_running = lambda: False
patch.is_game_running = lambda: False

# 清理
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
shutil.rmtree(state.PROFILES_DIR, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 通过')
