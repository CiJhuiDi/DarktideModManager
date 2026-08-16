# -*- coding: utf-8 -*-
"""依赖检查测试：packages 解析 / 缺依赖 / 循环依赖"""
import sys, shutil, subprocess
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
from core import mods
from core import state

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_deps_test.json'
state.BACKUP_DIR = MOCK / 'backups_deps_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

# 重建 mock 并构造依赖场景
subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
MODS = MOCK / 'mods'

def write_mod(name, packages=None, body_extra=''):
    d = MODS / name
    d.mkdir(exist_ok=True)
    pkgs = ''
    if packages:
        pkgs = 'packages = {' + ', '.join(f'"{p}"' for p in packages) + '}, '
    (d / f'{name}.mod').write_text(
        f'return {{ run = function() new_mod("{name}", {{}}) end, {pkgs}version = "1.0" {body_extra}}}',
        encoding='utf-8')

print('=== packages 解析格式 ===')
# 列表形式
write_mod('LibA', packages=[])
write_mod('LibB', packages=[])
write_mod('NeedsLib', packages=['liba'])
r = mods.parse_mod_deps(MODS / 'NeedsLib')
print('  列表形式:', r)
assert 'liba' in r

# 表形式 lib = true
(MODS / 'NeedsLib2').mkdir(exist_ok=True)
(MODS / 'NeedsLib2' / 'NeedsLib2.mod').write_text(
    'return { run = function() new_mod("NeedsLib2", {}) end, packages = { libb = true }, version = "1.0" }',
    encoding='utf-8')
r = mods.parse_mod_deps(MODS / 'NeedsLib2')
print('  表形式:', r)
assert 'libb' in r

# 无 packages
r = mods.parse_mod_deps(MODS / 'TestModA')
print('  无 packages:', r)
assert r == []

# 重建干净场景做分析
subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
MODS = MOCK / 'mods'
# 场景：A 依赖 B；C 依赖 X（缺失）；D 依赖 E，E 依赖 D（循环）
write_mod('ModA', packages=['modb'])
write_mod('ModB', packages=[])
write_mod('ModC', packages=['missinglib'])
write_mod('ModD', packages=['mode'])
write_mod('ModE', packages=['modd'])

print('=== 依赖检查 ===')
r = app.api_deps_check()
print('  missing:', r['missing'])
print('  cycles:', r['cycles'])
print('  total:', r['total'], 'bad:', r['bad'])

missing_names = {(x['mod'], x['needs']) for x in r['missing']}
assert ('ModC', 'missinglib') in missing_names, '缺依赖未检出'
assert not any(x['mod'] == 'ModA' for x in r['missing']), 'A 依赖 B 不应报缺'
assert r['cycles'] and any('ModD' in c and 'ModE' in c for c in r['cycles']), '循环依赖未检出'
assert r['bad'] >= 2

print('=== scan_mods 带 dependencies 字段 ===')
mods = app.scan_mods()
dmap = {m['name']: m.get('dependencies', []) for m in mods}
print('  ModA deps:', dmap.get('ModA'))
print('  ModC deps:', dmap.get('ModC'))
assert 'modb' in dmap.get('ModA', [])
assert 'missinglib' in dmap.get('ModC', [])

# 清理
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)
print('\n===== 依赖检查测试全部通过 =====')
