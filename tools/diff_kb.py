# -*- coding: utf-8 -*-
"""对比本地与 master keybindings.lua 的实质差异（忽略纯空白）"""
import sys, difflib
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LOCAL = r"D:\SteamLibrary\steamapps\common\Warhammer 40,000 Darktide\mods\dmf.bak_20260902_0235\scripts\mods\dmf\modules\core\keybindings.lua"
MASTER = r"D:\DeepseekWorkspace\暗潮\99-临时文件\dmf_master_src\Darktide-Mod-Framework-master\dmf\scripts\mods\dmf\modules\core\keybindings.lua"

def norm(path):
    out = []
    for ln in open(path, encoding='utf-8', errors='replace'):
        s = ln.strip()
        if s and not s.startswith('--'):
            out.append(s)
    return out

a = norm(LOCAL)
b = norm(MASTER)
sm = difflib.SequenceMatcher(None, a, b)
print(f"本地有效行 {len(a)} | master 有效行 {len(b)}")
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == 'equal':
        continue
    print(f"\n== {tag} ==")
    for i in range(i1, i2):
        print(f"  local : {a[i][:110]}")
    for j in range(j1, j2):
        print(f"  master: {b[j][:110]}")
