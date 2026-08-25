# -*- coding: utf-8 -*-
"""全量版本号升级脚本。
用法: python tools/bump_version.py 0.3.0
替换范围: version_info.txt / static/index.html / README.txt / 使用指南.txt
支持跨 minor 升级（如 0.2.3 -> 0.3.0）。
"""
import io, re, sys

OLD = "0.4.1"  # 当前版本（如升级路径变化需同步改这里）
NEW = sys.argv[1] if len(sys.argv) > 1 else "0.3.0"

FILES = [
    r'D:\DeepseekWorkspace\darktide-mod-manager\version_info.txt',
    r'D:\DeepseekWorkspace\darktide-mod-manager\static\index.html',
    r'D:\DeepseekWorkspace\darktide-mod-manager\README.txt',
    r'D:\DeepseekWorkspace\darktide-mod-manager\使用指南.txt',
]

old_tuple = '(' + ', '.join(OLD.split('.')) + ', 0)'
new_tuple = '(' + ', '.join(NEW.split('.')) + ', 0)'

for p in FILES:
    txt = io.open(p, encoding='utf-8').read()
    new = txt.replace('v' + OLD, 'v' + NEW).replace(OLD, NEW)
    new = new.replace(old_tuple, new_tuple)
    io.open(p, 'w', encoding='utf-8', newline='\n').write(new)
    print('更新:', p)

# 验证
for p in FILES:
    txt = io.open(p, encoding='utf-8').read()
    left = re.findall(re.escape(OLD), txt)
    right = re.findall(re.escape(NEW), txt)
    print(f'  {p.split(chr(92))[-1]}: 剩余{OLD}={len(left)}, {NEW}={len(right)}')
