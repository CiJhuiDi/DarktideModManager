# -*- coding: utf-8 -*-
"""v0.5.1：同步 dmf_payload 到 8/19 master（含合并汉化）+ 更新 VERSION.txt"""
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SRC = Path(r"D:\DeepseekWorkspace\暗潮\99-临时文件\dmf_master_src\Darktide-Mod-Framework-master\dmf")
ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / 'dmf_payload' / 'mods' / 'dmf'
VER = ROOT / 'dmf_payload' / 'VERSION.txt'

# 1. 清空旧 payload dmf 并复制新版
if DST.exists():
    for f in DST.rglob('*'):
        if f.is_file():
            f.unlink()
    for d in sorted([p for p in DST.rglob('*') if p.is_dir()], reverse=True):
        d.rmdir()
shutil.copytree(SRC, DST, dirs_exist_ok=True)
n = len(list(DST.rglob('*')))
print(f"payload mods/dmf 已同步: {n} 个文件")

# 2. 更新 VERSION.txt（保留原结构，更新 DMF 段说明）
old = VER.read_text(encoding='utf-8')
old = old.replace('（2026-08-14 更新为官方原版）', '（2026-09-02 更新为官方 master 2026-08-19 提交，汉化已合并）')
VER.write_text(old, encoding='utf-8')
print("VERSION.txt 已更新")
print(old[:600])
