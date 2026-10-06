import hashlib, json, os, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LOCAL_ROOT = r"D:\SteamLibrary\steamapps\common\Warhammer 40,000 Darktide\mods\dmf"
TREE_JSON = r"C:\Users\123\AppData\Local\Temp\dmf_tree.json"

def git_blob_sha(path):
    with open(path, 'rb') as f:
        data = f.read()
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()

tree = json.load(open(TREE_JSON, encoding='utf-8'))
master = {}
for t in tree['tree']:
    if t['type'] == 'blob' and t['path'].startswith('dmf/'):
        master[t['path'][4:]] = t['sha']

# 本地所有文件（相对 dmf/ 根，用正斜杠）
local_files = []
for root, dirs, files in os.walk(LOCAL_ROOT):
    for fn in files:
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, LOCAL_ROOT).replace('\\', '/')
        local_files.append((rel, full))
local_files.sort()

missing = []       # master 有、本地没有
diff = []          # 都有但内容不同
extra = []         # 本地有、master 没有
same = 0

for rel, full in local_files:
    if rel in master:
        if git_blob_sha(full) == master[rel]:
            same += 1
        else:
            diff.append(rel)
    else:
        extra.append(rel)

for rel in master:
    if rel not in dict(local_files):
        missing.append(rel)

print(f"相同: {same} | 内容不同: {len(diff)} | 本地独有: {len(extra)} | 本地缺失: {len(missing)}")
print("\n== 内容不同（本地 vs master）==")
for r in diff: print("  ", r)
print("\n== 本地缺失（master 有本地没有）==")
for r in missing: print("  ", r)
print("\n== 本地独有（master 没有）==")
for r in extra: print("  ", r)
