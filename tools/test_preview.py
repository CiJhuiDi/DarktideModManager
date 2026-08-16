# -*- coding: utf-8 -*-
"""差异预览测试：新增/移除/更新/相同 + 防呆"""
import sys, io, zipfile, shutil, subprocess, base64
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
state.CONFIG_FILE = MOCK / 'config_preview_test.json'
state.BACKUP_DIR = MOCK / 'backups_preview_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)
MODS = MOCK / 'mods'

def wm(name, ver):
    d = MODS / name
    d.mkdir(exist_ok=True)
    (d / f'{name}.mod').write_text(
        f'return {{ run = function() new_mod("{name}", {{}}) end, packages = {{}}, version = "{ver}" }}',
        encoding='utf-8')

# 当前 mods: TestModA(1.2.0) TestModB(0.5) TestModC(无版本)
# 包内: TestModA(2.0 更新) TestModB(0.5 相同) NewMod(新增) + 清单
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('mods/TestModA/TestModA.mod', 'return { run = function() new_mod("TestModA", {}) end, packages = {}, version = "2.0" }')
    z.writestr('mods/TestModB/TestModB.mod', 'return { run = function() new_mod("TestModB", {}) end, packages = {}, version = "0.5" }')
    z.writestr('mods/NewMod/NewMod.mod', 'return { run = function() new_mod("NewMod", {}) end, packages = {}, version = "1.0" }')
    z.writestr('mods/mod_load_order.txt', 'TestModA\nTestModB\nNewMod\n')
data = buf.getvalue()

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

print('=== 差异预览 ===')
r = app.preview_pack_archive('test_pack.zip', data)
test('预览 ok', r.get('ok'), r.get('error'))
test('新增 NewMod', r['added'] == ['NewMod'], r['added'])
test('更新 TestModA', r['updated'] == ['TestModA'], r['updated'])
test('相同 TestModB', r['same'] == ['TestModB'], r['same'])
test('移除含 TestModC', 'TestModC' in r['removed'], r['removed'])
test('包计数', r['pack_count'] == 3 and r['cur_count'] == 4, (r['pack_count'], r['cur_count']))
test('含清单', r['has_load_order'] and r['pack_lo_count'] == 3, r)

print('=== 不写文件（只读）===')
test('mock 未被修改', (MODS / 'TestModA' / 'TestModA.mod').exists() and not (MODS / 'NewMod').exists())

print('=== API 入口（base64）===')
b64 = base64.b64encode(data).decode()
r = app.api_pack_preview(app.PackPreviewBody(filename='t.zip', data_b64=b64))
test('API ok', r.get('ok'), r.get('error'))
test('API added', r['added'] == ['NewMod'], r['added'])

print('=== 防呆 ===')
r = app.api_pack_preview(app.PackPreviewBody(filename='', data_b64=''))
test('空数据拒绝', not r.get('ok'))
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r = app.api_pack_preview(app.PackPreviewBody(filename='t.zip', data_b64=b64))
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
