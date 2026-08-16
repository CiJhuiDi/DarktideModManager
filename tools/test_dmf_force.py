# -*- coding: utf-8 -*-
"""验证 force 覆盖更新功能：直接调用 api_dmf_install(force)"""
import sys, shutil
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
import state

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
FRESH = ROOT / 'mock_fresh'

# 重建 mock
if FRESH.exists():
    shutil.rmtree(FRESH)
FRESH.mkdir(parents=True)
(FRESH / 'bundle').mkdir()
state.GAME_DIR = FRESH
state.CONFIG_FILE = FRESH / 'config_test.json'
state.BACKUP_DIR = FRESH / 'backups'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

# 1. 首次安装
r = app.api_dmf_install()
print('1. 首次安装:', r.get('ok'), '|', r.get('message'))
assert r.get('ok')

# 2. 篡改一个组件（模拟旧版/广告版）
target = FRESH / 'mods' / 'dmf' / 'scripts' / 'mods' / 'dmf' / 'modules' / 'dmf_options.lua'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text('dmf_mod_data.name = "带广告的旧版"', encoding='utf-8')
print('2. 篡改组件为: 带广告的旧版')

# 3. 普通安装（无 force）也应覆盖（原逻辑就覆盖）
r = app.api_dmf_install()
print('3. 普通安装 ok:', r.get('ok'))
txt = target.read_text(encoding='utf-8')
print('   组件内容恢复:', '暗潮模组框架' in txt)

# 4. force 安装：返回 force 语义
r = app.api_dmf_install(body=type('B', (), {'force': True})())
print('4. force 安装:', r.get('ok'), '|', r.get('message'))
assert '覆盖更新' in r.get('message', '')
print('   force 语义 OK: 消息含「覆盖更新」')

# 5. 备份存在（秒级时间戳可能合并同名目录，只要>=1 即可）
baks = list((FRESH / 'backups').glob('dmf_backup_*'))
print('5. 备份目录数:', len(baks), '(应>=1)')
assert len(baks) >= 1

print('\n===== force 覆盖功能验证通过 =====')
