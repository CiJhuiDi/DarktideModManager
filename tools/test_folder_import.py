# -*- coding: utf-8 -*-
"""文件夹导入测试：单 mod 文件夹 / mods/ModA 结构 / ambiguous / force_mod"""
import sys, shutil, subprocess
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
app.GAME_DIR = MOCK
app.MODS_DIR = MOCK / 'mods'
app.CONFIG_FILE = MOCK / 'config_fdir_test.json'
app.BACKUP_DIR = MOCK / 'backups_fdir_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)

MOD_BODY = 'return { run = function() new_mod("%s", {}) end, packages = {}, version = "1.0" }'
checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

# 构造测试文件夹
TD = MOCK / 'fdir_test'
shutil.rmtree(TD, ignore_errors=True)

print('=== 单 mod 文件夹（CoolMod/）===')
d = TD / 'CoolMod'
d.mkdir(parents=True)
(d / 'CoolMod.mod').write_text(MOD_BODY % 'CoolMod', encoding='utf-8')
(d / 'scripts').mkdir()
(d / 'scripts' / 'x.lua').write_text('--x', encoding='utf-8')
r = app.import_mod_from_dir(d, 'CoolMod')
test('单 mod 文件夹导入 ok', r.get('ok'), r)
test('已拷入 mods/CoolMod', (MOCK / 'mods' / 'CoolMod' / 'CoolMod.mod').is_file())

print('=== mods/ModA 包裹结构（ambiguous）===')
d2 = TD / 'Wrapped'
d2.mkdir(parents=True)
(d2 / 'mods').mkdir()
(d2 / 'mods' / 'ModA').mkdir()
(d2 / 'mods' / 'ModA' / 'ModA.mod').write_text(MOD_BODY % 'ModA', encoding='utf-8')
r = app.import_mod_from_dir(d2, 'Wrapped')
test('单 mod 包裹 → ambiguous', r.get('ambiguous') is True, r)

print('=== ambiguous + force_mod 强制按 mod ===')
r = app.import_mod_from_dir(d2, 'Wrapped', force_mod=True)
test('force_mod 导入 ok', r.get('ok'), r)
test('已拷入 mods/ModA', (MOCK / 'mods' / 'ModA' / 'ModA.mod').is_file())

print('=== 整合包文件夹（mods/ 多 mod）===')
d3 = TD / 'PackDir'
d3.mkdir(parents=True)
(d3 / 'mods').mkdir()
for n in ['PA', 'PB']:
    (d3 / 'mods' / n).mkdir()
    (d3 / 'mods' / n / f'{n}.mod').write_text(MOD_BODY % n, encoding='utf-8')
r = app.import_mod_from_dir(d3, 'PackDir')
test('多 mod 文件夹 → is_pack', r.get('is_pack') is True, r)

print('=== 空文件夹 ===')
d4 = TD / 'Empty'
d4.mkdir(parents=True)
r = app.import_mod_from_dir(d4, 'Empty')
test('空文件夹报错', not r.get('ok'), r)

print('=== 游戏运行中拒绝 ===')
app.is_game_running = lambda: True
r = app.api_import_folder(app.ImportFolderBody(path=str(d)))
test('游戏运行中拒绝', not r.get('ok') and '游戏正在运行' in r.get('error', ''), r)
app.is_game_running = lambda: False

# 清理
shutil.rmtree(TD, ignore_errors=True)
shutil.rmtree(app.BACKUP_DIR, ignore_errors=True)
app.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 ✔')
