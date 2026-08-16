# -*- coding: utf-8 -*-
"""备份清理策略测试：数量上限（各10份）+ 体积上限（5GB 从旧删起）"""
import sys, shutil, os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
from core import state

MOCK = Path(r'D:\DeepseekWorkspace\darktide-mod-manager\mock')
state.BACKUP_DIR = MOCK / 'backups_prune_test'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_prune_test.json'

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

BK = state.BACKUP_DIR
if BK.exists():
    shutil.rmtree(BK)

print('=== 数量上限（pack 保留 10 份）===')
# 造 15 个 pack_backup
for i in range(15):
    d = BK / f'pack_backup_20260815_{i:06d}' / 'mods'
    d.mkdir(parents=True)
    (d / 'XMod').mkdir()
    (d / 'XMod' / 'XMod.mod').write_text('x', encoding='utf-8')
    (d / 'mod_load_order.txt').write_text('XMod\n', encoding='utf-8')

r = app.prune_backups()
kept = sorted(d.name for d in BK.iterdir() if d.is_dir())
test('pack 保留 10 份', len(kept) == 10, len(kept))
test('保留的是最新的 10 个', kept == [f'pack_backup_20260815_{i:06d}' for i in range(5, 15)], kept[:2])

print('=== 数量上限（dmf 保留 10 份）===')
for i in range(12):
    d = BK / f'dmf_backup_20260815_{i:06d}'
    d.mkdir(parents=True)
    (d / 'x.lua').write_text('x', encoding='utf-8')
r = app.prune_backups()
dmf_kept = sorted(d.name for d in BK.iterdir() if d.name.startswith('dmf_'))
test('dmf 保留 10 份', len(dmf_kept) == 10, len(dmf_kept))

print('=== 体积上限（临时调小阈值模拟 5GB）===')
# 重置目录
shutil.rmtree(BK)
BK.mkdir(parents=True)
# 造 3 个 2GB 的备份（总 6GB > 阈值）——用假大小文件（稀疏）
app.BACKUP_MAX_TOTAL_BYTES = 5 * 1024 * 1024 * 1024
for i in range(3):
    d = BK / f'pack_backup_20260815_{i:06d}' / 'mods'
    d.mkdir(parents=True)
    big = d / 'big.bin'
    with open(big, 'wb') as f:
        f.seek(2 * 1024 * 1024 * 1024)  # 2GB 空洞文件（不占实际空间但 stat 报 2GB）
        f.write(b'\0')
# 直接调清理
r = app.prune_backups()
left = sorted(d.name for d in BK.iterdir() if d.is_dir())
test('体积超限后只留最新的', len(left) <= 2, left)
# 最旧的 0 应该被删
test('最旧的被删', 'pack_backup_20260815_000000' not in left, left)

print('=== 空目录/不存在 ===')
shutil.rmtree(BK)
r = app.prune_backups()
test('无备份不报错', r == [])

# 恢复默认
app.BACKUP_MAX_TOTAL_BYTES = 5 * 1024 * 1024 * 1024
shutil.rmtree(BK, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 通过')
