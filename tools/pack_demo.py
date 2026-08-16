# -*- coding: utf-8 -*-
"""
把 demo 示例 mod 打包成「管理器可恢复的归档备份」+ 标准整合包 zip：
1. demo/backups/pack_backup_<时间戳>/mods/...   ← 复制到真实管理器 backups/ 即可在备份页看到并恢复
2. demo/演示整合包_v0.4.0.zip                  ← 也可用「导入整合包」导入
用法: python tools/pack_demo.py
"""
import zipfile, shutil, sys, datetime
from pathlib import Path

BASE = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
DEMO = BASE / 'demo'
MODS = DEMO / 'game' / 'mods'

if not MODS.is_dir():
    print('✗ demo 环境不存在，先运行 python tools/reset_demo.py')
    sys.exit(1)

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak_dir = DEMO / 'backups' / f'pack_backup_{ts}' / 'mods'
bak_dir.mkdir(parents=True, exist_ok=True)

# 1. 归档备份结构（含 mods/ 与启停清单）
for d in sorted(MODS.iterdir()):
    if not d.is_dir() or d.name in ('base', 'dmf'):
        continue
    shutil.copytree(d, bak_dir / d.name, dirs_exist_ok=True)
lo = MODS / 'mod_load_order.txt'
if lo.is_file():
    shutil.copy2(lo, bak_dir / 'mod_load_order.txt')

# 2. 标准整合包 zip
out_zip = DEMO / '演示整合包_v0.4.0.zip'
with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as z:
    for d in sorted(MODS.iterdir()):
        if not d.is_dir() or d.name in ('base', 'dmf'):
            continue
        for f in sorted(d.rglob('*')):
            if f.is_file():
                z.write(f, f'mods/{d.name}/{f.relative_to(d)}')
    if lo.is_file():
        z.write(lo, 'mods/mod_load_order.txt')

print(f'✅ 归档备份: {bak_dir.parent.name}（含 {len(list(bak_dir.iterdir()))} 项）')
print(f'✅ 整合包 zip: {out_zip.name}')
print()
print('用法 A（备份页恢复）:')
print('  把 demo\\backups\\pack_backup_<ts> 整个文件夹复制到管理器 exe 旁的 backups\\ 目录，')
print('  打开管理器「备份」页 → 找到「整合包归档」→ 点「恢复此备份」即可在真实环境展示。')
print()
print('用法 B（导入整合包）:')
print('  管理器「＋ 导入」→「导入 Mod/整合包」→ 选 演示整合包_v0.4.0.zip → 替换导入。')
