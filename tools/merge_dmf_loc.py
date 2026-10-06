# -*- coding: utf-8 -*-
"""合并 master 原版与本地汉化版 localization/dmf.lua
规则：
- 基底 = master（93 keys，含新增 key 的 zh-cn）
- zh-cn 覆盖：本地有 zh-cn 且非残缺（tooltip_* 本地只有 \\n 的用 master）→ 用本地措辞
- en 覆盖：developer_mode_description 用本地（带 CTRL+SHIFT+R 说明）
"""
import re, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MASTER = r"D:\DeepseekWorkspace\暗潮\99-临时文件\dmf_master_src\Darktide-Mod-Framework-master\dmf\localization\dmf.lua"
LOCAL = r"D:\SteamLibrary\steamapps\common\Warhammer 40,000 Darktide\mods\dmf.bak_20260902_0235\localization\dmf.lua"
OUT = r"D:\DeepseekWorkspace\暗潮\99-临时文件\dmf_master_src\Darktide-Mod-Framework-master\dmf\localization\dmf.lua"

def parse_blocks(path):
    """返回 {key: (start_line_idx, end_line_idx, block_text)}，行号 0 基"""
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    blocks = {}
    n = len(lines)
    for idx, line in enumerate(lines):
        m = re.match(r'^  ([a-zA-Z0-9_]+) = \{', line)
        if m:
            key = m.group(1)
            depth = 0
            j = idx
            while j < n:
                depth += lines[j].count('{') - lines[j].count('}')
                if depth <= 0:
                    break
                j += 1
            blocks[key] = (idx, j)
    return lines, blocks

def get_lang_val(block_lines, lang):
    """取 block 内某语言的值（含转义原文）。返回 (line_idx, value) 或 None"""
    pat = re.compile(r'^(\s*)(\["%s"\]|%s)\s*=\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$' % (re.escape(lang), re.escape(lang)))
    for i, ln in enumerate(block_lines):
        m = pat.match(ln)
        if m:
            return i, m.group(3)
    return None

def replace_lang_val(lines, block_range, lang, new_val):
    """在 block 范围内替换某语言行的值；没有该语言行则跳过（不新增）"""
    s, e = block_range
    pat = re.compile(r'^(\s*)(\["%s"\]|%s)\s*=\s*"((?:[^"\\]|\\.)*)"(\s*,?\s*)$' % (re.escape(lang), re.escape(lang)))
    for i in range(s, e + 1):
        m = pat.match(lines[i])
        if m:
            lines[i] = '%s%s = "%s"%s' % (m.group(1), m.group(2), new_val, m.group(4))
            return True
    return False

master_lines, master_blocks = parse_blocks(MASTER)
local_lines, local_blocks = parse_blocks(LOCAL)

# 1. zh-cn 覆盖（本地优先，tooltip 残缺除外）
def is_degenerate_zh(val):
    # 本地残缺：只有换行符没有实际中文
    return val is not None and not re.search(r'[\u4e00-\u9fff]', val)

zh_overridden = []
for key, (ms, me) in master_blocks.items():
    if key not in local_blocks:
        continue
    ls, le = local_blocks[key]
    local_zh = get_lang_val(local_lines[ls:le + 1], 'zh-cn')
    master_zh = get_lang_val(master_lines[ms:me + 1], 'zh-cn')
    if local_zh is None:
        continue
    if is_degenerate_zh(local_zh[1]):
        continue  # 本地残缺 → 保留 master
    if master_zh is not None and master_zh[1] == local_zh[1]:
        continue  # 相同
    ok = replace_lang_val(master_lines, (ms, me), 'zh-cn', local_zh[1])
    if ok:
        zh_overridden.append(key)

# 2. en 覆盖：developer_mode_description
key = 'developer_mode_description'
if key in master_blocks and key in local_blocks:
    ms, me = master_blocks[key]
    ls, le = local_blocks[key]
    local_en = get_lang_val(local_lines[ls:le + 1], 'en')
    if local_en:
        replace_lang_val(master_lines, (ms, me), 'en', local_en[1])
        print(f"[en 覆盖] {key}")

out = '\n'.join(master_lines) + '\n'
open(OUT, 'w', encoding='utf-8', newline='\n').write(out)
print(f"zh-cn 覆盖 {len(zh_overridden)} 个 key")
print("覆盖列表:", ', '.join(zh_overridden))
print("输出:", OUT)
