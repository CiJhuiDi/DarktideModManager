# -*- coding: utf-8 -*-
"""
一键重置演示验收环境（demo/）：
1. 删除 demo 目录所有内容（含运行产生的 backups/profiles/config 改动）
2. 重新构建示例 mod + 清单 + config
3. 复制最新 exe 到 demo
用法：python tools/reset_demo.py
"""
import shutil, sys
from pathlib import Path

BASE = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
DEMO = BASE / 'demo'

# 1. 清空 demo（保留目录本身）
if DEMO.exists():
    for item in DEMO.iterdir():
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)
    print('✓ demo 已清空')
else:
    DEMO.mkdir(parents=True)

# 2. 重建示例环境
import subprocess
env = dict(__import__('os').environ)
env['PYTHONIOENCODING'] = 'utf-8'
r = subprocess.run([sys.executable, str(BASE / 'tools' / 'build_demo.py')], capture_output=True, env=env)
out = r.stdout.decode('utf-8', errors='replace').strip()
if out:
    print(out)
if r.returncode != 0:
    err = r.stderr.decode('utf-8', errors='replace')[-500:]
    print('✗ 构建失败:', err)
    sys.exit(1)

# 3. 复制最新 exe
exe = BASE / 'dist' / 'DarktideModManager.exe'
if exe.is_file():
    shutil.copy2(exe, DEMO / 'DarktideModManager.exe')
    print(f'✓ exe 已复制: {exe.name}')

print('\n✅ 演示环境已重置，可直接打开 demo\\DarktideModManager.exe 验收/拍摄')
