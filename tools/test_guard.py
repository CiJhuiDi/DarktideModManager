# -*- coding: utf-8 -*-
"""验证防呆：游戏运行时所有写操作被拒绝"""
import sys, json
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
from core import profiles
from core import state

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'

# 指向 mock 并模拟游戏运行中
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_test.json'
state.BACKUP_DIR = MOCK / 'backups_test'
from core import patch
app.is_game_running = lambda: True
patch.is_game_running = lambda: True  # guard 在 patch 模块内调用  # 强制"游戏运行中"
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

# 备份原始清单
lo = MOCK / 'mods' / 'mod_load_order.txt'
orig = lo.read_text(encoding='utf-8')

checks = []

def test(name, r, expect_block=True):
    blocked = (not r.get('ok')) and ('游戏正在运行' in (r.get('error') or ''))
    ok = blocked == expect_block
    checks.append((name, ok, r.get('error') or r.get('message') or r.get('results')))
    print(f"[{'OK ' if ok else 'FAIL'}] {name}: {r.get('error') or r.get('message')}")

print('=== 游戏运行时防呆测试 ===')
# 1. 导入 mod
class FakeUpload:
    filename = 'TestX.zip'
    async def read(self):
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('TestX/TestX.mod', 'return { run = function() new_mod("TestX", {}) end }')
            z.writestr('TestX/scripts/x.lua', '--x')
        return buf.getvalue()
import asyncio
r = asyncio.run(app.api_import_mods(files=[FakeUpload()]))
test('导入 mod', r)

# 2. 删除 mod
r = app.api_delete_mod('TestModA')
test('删除 mod', r)

# 3. 清残留
r = app.api_remove_from_load_order('GhostMod')
test('从清单移除', r)

# 4. toggle
r = app.api_toggle('TestModB')
test('切换启停', r)

# 5. 保存顺序
r = app.api_set_order(app.OrderBody(mods=['TestModA']))
test('保存顺序', r)

# 6. 整合包导入
r = asyncio.run(app.api_pack_import(files=[], mode='replace'))
test('导入整合包', r)

# 7. DMF 安装
r = app.api_dmf_install()
test('DMF 安装', r)

# 8. 备份恢复（用存在的备份目录验证守卫在恢复前拦截）
import shutil
bak_src = state.BACKUP_DIR / 'pack_backup_test' / 'mods'
bak_src.mkdir(parents=True, exist_ok=True)
(bak_src / 'XMod').mkdir(exist_ok=True)
r = app.api_backup_restore('pack_backup_test')
test('备份恢复', r)

# 9. 预设应用（走 order 守卫；先建一个真实预设验证被拦）
state.PROFILES_DIR = MOCK / 'profiles_test'
state.PROFILES_DIR.mkdir(exist_ok=True)
(state.PROFILES_DIR / 'test.json').write_text(json.dumps({"mods": ["TestModA"]}), encoding='utf-8')
r = profiles.api_profile_apply('test')
test('预设应用', r)

# 清单未被修改
after = lo.read_text(encoding='utf-8')
print(f"\n清单未被修改: {orig == after}")

failed = [n for n, ok, _ in checks if not ok]
print(f"\n===== {len(checks) - len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败项:', failed)
    raise SystemExit(1)
print('全部通过')
