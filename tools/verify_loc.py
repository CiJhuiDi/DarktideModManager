# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from luaparser import ast

path = r"D:\DeepseekWorkspace\暗潮\99-临时文件\dmf_master_src\Darktide-Mod-Framework-master\dmf\localization\dmf.lua"
src = open(path, encoding='utf-8').read()
tree = ast.parse(src)
print('语法 OK, 行数 =', src.count('\n') + 1)

for k in ['dmf_mod_name', 'tooltip_incompatible_mutators', 'developer_mode_description',
          'chat_history_enable', 'toggle_mods', 'reload_mods', 'show_network_debug_info_description']:
    m = re.search(r'^  %s = \{(.*?)^  \},?$' % re.escape(k), src, re.S | re.M)
    if m:
        zh = re.search(r'\["zh-cn"\]\s*=\s*"((?:[^"\\]|\\.)*)"', m.group(1))
        en = re.search(r'\ben\s*=\s*"((?:[^"\\]|\\.)*)"', m.group(1))
        print(k)
        print('   zh-cn:', zh.group(1) if zh else None)
        print('   en   :', en.group(1) if en else None)
