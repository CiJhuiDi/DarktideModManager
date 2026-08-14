# -*- coding: utf-8 -*-
"""导出整合包 API 测试 v2：all / enabled 两种模式 + 可再导入闭环 + 防呆"""
import sys, json, zipfile, shutil, subprocess
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
app.GAME_DIR = MOCK
app.MODS_DIR = MOCK / 'mods'
app.CONFIG_FILE = MOCK / 'config_export_test.json'
app.BACKUP_DIR = MOCK / 'backups_export_test'
app.BASE_DIR = MOCK
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

# 重建干净 mock（TestModA/B/C 启用，DisabledMod 禁用）
subprocess.run([sys.executable, r'D:\DeepseekWorkspace\darktide-mod-manager\tools\build_mock.py'], check=True)

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

def zip_mods(path):
    z = zipfile.ZipFile(path)
    return set(n.split('/')[1] for n in z.namelist() if n.startswith('mods/') and '/' in n[5:])

print('=== 全部导出 mode=all ===')
r = app.api_export(app.ExportBody(name='全量包', mode='all'))
test('all 导出 ok', r.get('ok'), r.get('message'))
out = Path(r['path'])
mods = zip_mods(out)
test('all 包含全部 4 个 mod', mods == {'TestModA','TestModB','TestModC','DisabledMod'}, mods)
z = zipfile.ZipFile(out)
lo = z.read('mods/mod_load_order.txt').decode('utf-8').splitlines()
test('all 清单含全部 4 个', set(lo) == {'TestModA','TestModB','TestModC','DisabledMod'}, lo)
test('all 不含系统组件', not any(m in ('base','dmf') for m in mods))

print('=== 按启用导出 mode=enabled ===')
r2 = app.api_export(app.ExportBody(name='启用包', mode='enabled'))
test('enabled 导出 ok', r2.get('ok'), r2.get('message'))
out2 = Path(r2['path'])
mods2 = zip_mods(out2)
test('enabled 只含 3 个启用 mod', mods2 == {'TestModA','TestModB','TestModC'}, mods2)
z2 = zipfile.ZipFile(out2)
lo2 = z2.read('mods/mod_load_order.txt').decode('utf-8').splitlines()
test('enabled 清单只含启用的', set(lo2) == {'TestModA','TestModB','TestModC'}, lo2)

print('=== 全部禁用时 enabled 导出拒绝 ===')
# 全禁用
r = app.api_mods_batch(app.BatchBody(names=['TestModA','TestModB','TestModC'], action='disable'))
r3 = app.api_export(app.ExportBody(name='x', mode='enabled'))
test('无启用 mod 时 enabled 拒绝', not r3.get('ok') and '没有启用' in r3.get('error',''), r3)
# 恢复
app.api_mods_batch(app.BatchBody(names=['TestModA','TestModB','TestModC'], action='enable'))

print('=== 仅导出清单 mode=load_order ===')
r_lo = app.api_export(app.ExportBody(name='', mode='load_order'))
test('load_order 导出 ok', r_lo.get('ok'), r_lo.get('message'))
lo_path = Path(r_lo['path'])
test('导出为 .txt 文件', lo_path.suffix == '.txt', lo_path.name)
txt = lo_path.read_text(encoding='utf-8').splitlines()
test('清单只含启用 mod', set(txt) == {'TestModA','TestModB','TestModC'}, txt)
test('无注释/禁用行', all(not l.startswith('--') and l.strip() for l in txt))

print('=== 全部禁用时 load_order 拒绝 ===')
r = app.api_mods_batch(app.BatchBody(names=['TestModA','TestModB','TestModC'], action='disable'))
r_lo2 = app.api_export(app.ExportBody(name='', mode='load_order'))
test('无启用时 load_order 拒绝', not r_lo2.get('ok') and '没有启用' in r_lo2.get('error',''), r_lo2)
app.api_mods_batch(app.BatchBody(names=['TestModA','TestModB','TestModC'], action='enable'))

print('=== 可再导入闭环（enabled 包）===')
# 先测默认模式（趁 mods 还是 4 个）
r5 = app.api_export(app.ExportBody(name='默认包'))
test('默认 mode=all', r5.get('mode') == 'all' and r5.get('count') == 4, r5)
data = Path(r2['path']).read_bytes()
for d in list((MOCK / 'mods').iterdir()):
    if d.name not in app.SYSTEM_MODS:
        shutil.rmtree(d, ignore_errors=True)
(MOCK / 'mods' / 'mod_load_order.txt').unlink(missing_ok=True)
rr = app.import_pack_archive('启用包.zip', data, 'replace')
test('enabled 包再导入 ok', rr.get('ok'), rr.get('message'))
test('再导入还原 3 个启用 mod', (MOCK/'mods'/'TestModA').is_dir() and not (MOCK/'mods'/'DisabledMod').exists())

print('=== 游戏运行中拒绝 ===')
app.is_game_running = lambda: True
r = app.api_export(app.ExportBody(name='y'))
test('游戏运行中拒绝', not r.get('ok') and '游戏正在运行' in r.get('error',''), r)
app.is_game_running = lambda: False

# 清理
shutil.rmtree(MOCK / 'exports', ignore_errors=True)
shutil.rmtree(app.BACKUP_DIR, ignore_errors=True)
app.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 ✔')
