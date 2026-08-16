# -*- coding: utf-8 -*-
"""顺序检查测试：本体→扩展包含关系 + 顺序反了提示"""
import sys, shutil, subprocess
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
from core import state

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_order_test.json'
state.BACKUP_DIR = MOCK / 'backups_order_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
MODS = MOCK / 'mods'

def wm(name):
    d = MODS / name
    d.mkdir(exist_ok=True)
    (d / f'{name}.mod').write_text(
        f'return {{ run = function() new_mod("{name}", {{}}) end, packages = {{}}, version = "1.0" }}',
        encoding='utf-8')

# 场景：scoreboard 本体 + 扩展；扩展排在前面（错误示范）
wm('scoreboard')
wm('ScoreboardDamage')
wm('scoreboard_extra')

# 设置启停清单：扩展在前，本体在后（故意反序）
(MODS / 'mod_load_order.txt').write_text('ScoreboardDamage\nscoreboard_extra\nscoreboard\n', encoding='utf-8')

r = app.api_deps_check()
print('order_hints:', r['order_hints'])
print('bad:', r['bad'])

# ScoreboardDamage 含 scoreboard → 应提示
hints = {(h['ext'], h['base']) for h in r['order_hints']}
assert ('ScoreboardDamage', 'scoreboard') in hints, f'缺少顺序提示: {hints}'
assert ('scoreboard_extra', 'scoreboard') in hints, f'scoreboard_extra 未提示: {hints}'
assert len(r['order_hints']) >= 2

# 修正顺序后无提示
(MODS / 'mod_load_order.txt').write_text('scoreboard\nScoreboardDamage\nscoreboard_extra\n', encoding='utf-8')
r2 = app.api_deps_check()
print('修正后 order_hints:', r2['order_hints'])
assert not any(h['ext'] == 'ScoreboardDamage' for h in r2['order_hints']), '修正后仍提示'

# 未启用不参与
(MODS / 'mod_load_order.txt').write_text('--scoreboard\nScoreboardDamage\n', encoding='utf-8')
r3 = app.api_deps_check()
print('未启用场景 hints:', r3['order_hints'])
assert not any(h['ext'] == 'ScoreboardDamage' and h['base'] == 'scoreboard' for h in r3['order_hints']), '未启用的本体不应提示'

# 清理
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)
print('\n===== 顺序检查测试全部通过 =====')
