# -*- coding: utf-8 -*-
"""依赖检查测试：packages 解析 / info.json 声明式依赖 / 缺依赖 / 循环依赖 / 顺序冲突"""
import sys, json, shutil, subprocess
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app
from core import mods
from core import state

MOCK = ROOT / 'mock'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_deps_test.json'
state.BACKUP_DIR = MOCK / 'backups_deps_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

# 重建 mock 并构造依赖场景
subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_mock.py')], check=True)
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
subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_mock.py')], check=True)
MODS = MOCK / 'mods'
# 场景：A 依赖 B；C 依赖 X（缺失）；D 依赖 E，E 依赖 D（循环）
write_mod('ModA', packages=['modb'])
write_mod('ModB', packages=[])
write_mod('ModC', packages=['missinglib'])
write_mod('ModD', packages=['mode'])
write_mod('ModE', packages=['modd'])
# 只有启用的 mod 才参与检查（未启用的不会加载，查它没意义）
(MODS / 'mod_load_order.txt').write_text('ModA\nModB\nModC\nModD\nModE\n', encoding='utf-8')

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

print('=== info.json 的 dependencies（声明式依赖） ===')
subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_mock.py')], check=True)
MODS = MOCK / 'mods'


def write_info(name, deps, bom=True):
    """顺带用 utf-8-sig 写，覆盖「info.json 带 BOM」的情况"""
    d = MODS / name
    d.mkdir(exist_ok=True)
    enc = 'utf-8-sig' if bom else 'utf-8'
    (d / 'info.json').write_text(
        json.dumps({"name": name, "dependencies": deps}, ensure_ascii=False), encoding=enc)


# required：存在的库不报、缺的必须报
write_mod('LibX', packages=[])
write_mod('NeedsX', packages=[])
write_info('NeedsX', {"required": ["libx"]})
write_mod('NeedsAbsent', packages=[])
write_info('NeedsAbsent', {"required": ["no_such_lib"]})
(MODS / 'mod_load_order.txt').write_text('LibX\nNeedsX\nNeedsAbsent\n', encoding='utf-8')
r = app.api_deps_check()
miss = {(x['mod'], x['needs'].lower()) for x in r['missing']}
print('  missing:', r['missing'])
assert ('NeedsAbsent', 'no_such_lib') in miss, f'info.json required 缺失未报: {miss}'
assert not any(x['mod'] == 'NeedsX' for x in r['missing']), 'LibX 存在，不该报缺'

# self_after：BaseA 声明要排在 BaseB 之后，实际排在前面 → 必须报冲突
write_mod('BaseA', packages=[])
write_mod('BaseB', packages=[])
write_info('BaseA', {"self_after": ["baseb"]})
(MODS / 'mod_load_order.txt').write_text('BaseA\nBaseB\n', encoding='utf-8')
r = app.api_deps_check()
print('  顺序冲突:', r['order_hints'])
hints = {(h['ext'], h['base'], h['why']) for h in r['order_hints']}
assert ('BaseA', 'BaseB', 'declared') in hints, f'声明式顺序冲突未报: {hints}'
assert r['bad'] >= 1

# 顺序换对之后不该再报
(MODS / 'mod_load_order.txt').write_text('BaseB\nBaseA\n', encoding='utf-8')
r = app.api_deps_check()
assert not any(h['ext'] == 'BaseA' and h['why'] == 'declared' for h in r['order_hints']), \
    f'顺序正确仍报冲突: {r["order_hints"]}'

# self_before：反过来写也要生效（BaseC 声明排在 BaseD 之前，实际在后面）。
# 违反时的表达是「BaseD 应排在 BaseC 之后」——与 self_after 统一成 (ext, base) 一种说法。
write_mod('BaseC', packages=[])
write_mod('BaseD', packages=[])
write_info('BaseC', {"self_before": ["based"]})
(MODS / 'mod_load_order.txt').write_text('BaseD\nBaseC\n', encoding='utf-8')
r = app.api_deps_check()
hints = {(h['ext'], h['base'], h['why']) for h in r['order_hints']}
assert ('BaseD', 'BaseC', 'declared') in hints, f'self_before 冲突未报: {hints}'

# 顺序换对后不报
(MODS / 'mod_load_order.txt').write_text('BaseC\nBaseD\n', encoding='utf-8')
r = app.api_deps_check()
assert not any(h['why'] == 'declared' for h in r['order_hints']), \
    f'顺序正确仍报冲突: {r["order_hints"]}'

# 坏 info.json 不能让扫描炸掉（dependencies 不是 dict）
write_mod('BadInfo', packages=[])
(MODS / 'BadInfo' / 'info.json').write_text('{"dependencies": ["oops"]}', encoding='utf-8')
r2 = app.api_deps_check()
assert r2['ok'] is True, '坏 info.json 让依赖检查挂了'

print('=== 依赖装着但没启用（不等于缺依赖） ===')
subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_mock.py')], check=True)
MODS = MOCK / 'mods'

write_mod('NeedOff', packages=[])
write_mod('LibOff', packages=[])
write_info('NeedOff', {"required": ["liboff"]})
# LibOff 在磁盘上，但清单里只有 NeedOff → 不会被加载
(MODS / 'mod_load_order.txt').write_text('NeedOff\n', encoding='utf-8')
r = app.api_deps_check()
idle = {(x['mod'], x['needs'].lower()) for x in r['inactive']}
miss = {(x['mod'], x['needs'].lower()) for x in r['missing']}
print('  inactive:', r['inactive'])
assert ('NeedOff', 'liboff') in idle, f'依赖没启用未报: inactive={idle} missing={miss}'
assert ('NeedOff', 'liboff') not in miss, f'没启用被误报成缺依赖: {miss}'
assert r['bad'] >= 1

# 启用依赖后不再报
(MODS / 'mod_load_order.txt').write_text('LibOff\nNeedOff\n', encoding='utf-8')
r = app.api_deps_check()
assert not any(x['mod'] == 'NeedOff' for x in r['inactive']), f'启用依赖后仍报: {r["inactive"]}'

# 依赖根本不存在 → 只算 missing，不该同时算 inactive（两类互斥）
write_mod('NeedGhost', packages=[])
write_info('NeedGhost', {"required": ["ghost_lib"]})
(MODS / 'mod_load_order.txt').write_text('NeedGhost\n', encoding='utf-8')
r = app.api_deps_check()
assert any(x['mod'] == 'NeedGhost' for x in r['missing']), f'缺依赖未报: {r["missing"]}'
assert not any(x['mod'] == 'NeedGhost' for x in r['inactive']), f'不存在的依赖被误报成没启用: {r["inactive"]}'

# dmf 被停用时，要求 dmf 的 mod 应报「依赖没启用」
_real_dmf_state = app.dmf_state
app.dmf_state = lambda: {"game_dir_valid": True, "installed": True, "enabled": False,
                         "missing": [], "autopatch_off": False, "payload_version": ""}
write_mod('NeedDmf', packages=[])
write_info('NeedDmf', {"required": ["dmf"]})
(MODS / 'mod_load_order.txt').write_text('NeedDmf\n', encoding='utf-8')
r = app.api_deps_check()
assert any(x['mod'] == 'NeedDmf' and x['needs'].lower() == 'dmf' for x in r['inactive']), \
    f'dmf 停用未报: {r["inactive"]}'

# dmf 没装（或目录无效）时不该在环境检查里报——那是 DMF 横幅的活
app.dmf_state = lambda: {"game_dir_valid": True, "installed": False, "enabled": False,
                         "missing": ["mods/dmf/dmf.mod"], "autopatch_off": False, "payload_version": ""}
r = app.api_deps_check()
assert not any(x['mod'] == 'NeedDmf' for x in r['inactive']), \
    f'dmf 没装时不该报依赖没启用: {r["inactive"]}'
app.dmf_state = _real_dmf_state

# 清理
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)
print('\n===== 依赖检查测试全部通过 =====')