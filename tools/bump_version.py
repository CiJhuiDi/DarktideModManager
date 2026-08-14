# -*- coding: utf-8 -*-
"""v0.2.2 -> v0.2.3 全量版本号更新"""
import io, re

FILES = [
    r'D:\DeepseekWorkspace\darktide-mod-manager\version_info.txt',
    r'D:\DeepseekWorkspace\darktide-mod-manager\static\index.html',
    r'D:\DeepseekWorkspace\darktide-mod-manager\README.txt',
    r'D:\DeepseekWorkspace\darktide-mod-manager\使用指南.txt',
]

for p in FILES:
    txt = io.open(p, encoding='utf-8').read()
    new = txt.replace('0.2.2', '0.2.3').replace('v0.2.2', 'v0.2.3')
    # version_info.txt 特殊：filevers/prodvers 是元组
    new = new.replace('(0, 2, 2, 0)', '(0, 2, 3, 0)')
    io.open(p, 'w', encoding='utf-8', newline='\n').write(new)
    print('更新:', p)

# 验证
for p in FILES:
    txt = io.open(p, encoding='utf-8').read()
    left = re.findall(r'0\.2\.2', txt)
    right = re.findall(r'0\.2\.3', txt)
    print(f'  {p.split(chr(92))[-1]}: 剩余0.2.2={len(left)}, 0.2.3={len(right)}')
