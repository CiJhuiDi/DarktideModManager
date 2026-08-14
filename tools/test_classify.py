# -*- coding: utf-8 -*-
"""压缩包分类测试：单 mod / 完整整合包 / 仅 mods 文件夹整合包 / ambiguous / 非法"""
import sys, io, zipfile, shutil, subprocess
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
app.GAME_DIR = MOCK
app.MODS_DIR = MOCK / 'mods'
app.CONFIG_FILE = MOCK / 'config_cls_test.json'
app.BACKUP_DIR = MOCK / 'backups_cls_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)

def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, content in entries:
            z.writestr(name, content)
    return buf.getvalue()

MOD_BODY = 'return { run = function() new_mod("%s", {}) end, packages = {}, version = "1.0" }'

def classify(data, fname='test.zip'):
    r = app.import_mod_archive(fname, data)
    if r.get('ok'): return 'mod-imported'
    if r.get('ambiguous'): return 'ambiguous'
    if r.get('is_pack'): return 'pack'
    return 'err:' + (r.get('error') or '?')

checks = []
def test(name, got, expect):
    if callable(expect):
        ok = expect(got)
    else:
        ok = got == expect
    checks.append((name, ok))
    print(f"[{'OK ' if ok else 'FAIL'}] {name}: got={got} expect={expect if not callable(expect) else '(条件)'}")

print('=== 单 mod（无 mods/ 包裹）===')
r = classify(make_zip([
    ('CoolMod/CoolMod.mod', MOD_BODY % 'CoolMod'),
    ('CoolMod/scripts/x.lua', '--x'),
]))
test('单 mod → mod', r, 'mod-imported')

print('=== 完整整合包（mods/base + 加载器）===')
r = classify(make_zip([
    ('mods/base/mod_manager.lua', '-- loader'),
    ('mods/CoolMod/CoolMod.mod', MOD_BODY % 'CoolMod'),
    ('binaries/mod_loader', 'bin'),
]))
test('完整整合包 → pack', r, 'pack')

print('=== 仅 mods 文件夹、多 mod ===')
r = classify(make_zip([
    ('mods/ModA/ModA.mod', MOD_BODY % 'ModA'),
    ('mods/ModB/ModB.mod', MOD_BODY % 'ModB'),
]))
test('mods/ 多 mod → pack', r, 'pack')

print('=== 仅 mods 文件夹、单 mod + 清单 ===')
r = classify(make_zip([
    ('mods/ModA/ModA.mod', MOD_BODY % 'ModA'),
    ('mods/mod_load_order.txt', 'ModA\n'),
]))
test('单 mod + 清单 → pack', r, 'pack')

print('=== 仅 mods 文件夹、单 mod、无清单（ambiguous）===')
r = classify(make_zip([
    ('mods/ModA/ModA.mod', MOD_BODY % 'ModA'),
]))
test('单 mod 包裹无清单 → ambiguous', r, 'ambiguous')

print('=== 无 .mod 无整合包结构 ===')
r = classify(make_zip([('readme.txt', 'hello')]))
test('非法包 → 报错', r, lambda x: x.startswith('err:'))

print('=== 外层套目录的单 mod ===')
r = classify(make_zip([
    ('outer/CoolMod/CoolMod.mod', MOD_BODY % 'CoolMod'),
]))
test('嵌套单 mod → mod', r, 'mod-imported')

# 清理
import shutil as sh
sh.rmtree(app.BACKUP_DIR, ignore_errors=True)
app.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 ✔')
