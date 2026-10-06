# -*- coding: utf-8 -*-
"""对比 master 原版与本地汉化版 localization/dmf.lua 的差异"""
import re, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MASTER = r"D:\DeepseekWorkspace\暗潮\99-临时文件\dmf_master_src\Darktide-Mod-Framework-master\dmf\localization\dmf.lua"
LOCAL = r"D:\SteamLibrary\steamapps\common\Warhammer 40,000 Darktide\mods\dmf.bak_20260902_0235\localization\dmf.lua"

def parse_keys(path):
    """提取顶层 key 及其条目文本（key = { ... } 到匹配的 }）"""
    src = open(path, encoding='utf-8', errors='replace').read()
    # 顶层条目：行首 key = { 开始，缩进 2 空格
    keys = {}
    # 用简单状态机：找到 "  key = {" 后数大括号配对
    i = 0
    lines = src.splitlines()
    n = len(lines)
    for idx, line in enumerate(lines):
        m = re.match(r'^  ([a-zA-Z0-9_]+) = \{', line)
        if m:
            key = m.group(1)
            # 收集到配对的 }
            depth = 0
            j = idx
            while j < n:
                depth += lines[j].count('{') - lines[j].count('}')
                if depth <= 0:
                    break
                j += 1
            block = '\n'.join(lines[idx:j+1])
            keys[key] = block
    return keys, src

mk, msrc = parse_keys(MASTER)
lk, lsrc = parse_keys(LOCAL)

print(f"master keys: {len(mk)} | local keys: {len(lk)}")

def extract_lang(block, lang):
    m = re.search(r'\["%s"\]\s*=\s*"((?:[^"\\]|\\.)*)"' % lang, block)
    if m:
        return m.group(1)
    m2 = re.search(r'%s\s*=\s*"((?:[^"\\]|\\.)*)"' % lang, block)
    if m2:
        return m2.group(1)
    return None

# 1. key 差异
only_master = [k for k in mk if k not in lk]
only_local = [k for k in lk if k not in mk]
print(f"\n== 仅 master 有的 key（本地缺）: {len(only_master)} ==")
for k in only_master:
    zh = extract_lang(mk[k], 'zh-cn')
    print(f"  {k}: zh-cn={zh!r}" if zh is not None else f"  {k}: (无 zh-cn)")

print(f"\n== 仅本地有的 key（master 缺）: {len(only_local)} ==")
for k in only_local:
    print(f"  {k}")

# 2. 共同 key 的 zh-cn 差异
print("\n== 共同 key 中 zh-cn 不同 ==")
diff_zh = 0
for k in mk:
    if k in lk:
        mzh = extract_lang(mk[k], 'zh-cn')
        lzh = extract_lang(lk[k], 'zh-cn')
        if mzh != lzh:
            diff_zh += 1
            print(f"  {k}:\n    master: {mzh!r}\n    local : {lzh!r}")
print(f"zh-cn 不同总数: {diff_zh}")

# 3. 共同 key 中 en 不同
print("\n== 共同 key 中 en 不同（前 10）==")
diff_en = 0
for k in mk:
    if k in lk:
        men = extract_lang(mk[k], 'en')
        len_ = extract_lang(lk[k], 'en')
        if men != len_:
            diff_en += 1
            if diff_en <= 10:
                print(f"  {k}:\n    master: {men!r}\n    local : {len_!r}")
print(f"en 不同总数: {diff_en}")
