# -*- coding: utf-8 -*-
"""正式发布打包：同步 release/DarktideModManager_vX.Y.Z/ + 打 zip（含 LICENSE/THIRD_PARTY）。
用法: python tools/release_pack.py v0.4.0
前置: 先 bump 版本（tools/bump_version.py）→ 构建 exe（dist）→ 再跑本脚本。
"""
import argparse
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_FILES = ['DarktideModManager.exe', 'README.txt', '使用指南.txt', 'LICENSE', 'THIRD_PARTY_LICENSES.md']


def main():
    ap = argparse.ArgumentParser(description='正式发布打包（同步目录 + 打 zip）')
    ap.add_argument('version', help='版本号，如 v0.4.0')
    args = ap.parse_args()

    ver = args.version
    if not ver.startswith('v'):
        ver = 'v' + ver
    dirname = 'DarktideModManager_' + ver
    rel_dir = os.path.join(ROOT, 'release', dirname)
    os.makedirs(rel_dir, exist_ok=True)

    missing = []
    for f in RELEASE_FILES:
        src = os.path.join(ROOT, 'dist', 'DarktideModManager.exe') if f == 'DarktideModManager.exe' else os.path.join(ROOT, f)
        if not os.path.isfile(src):
            missing.append(f)
            continue
        shutil.copy2(src, os.path.join(rel_dir, f))
    if missing:
        print('缺失文件（先构建/准备）:', missing)
        sys.exit(1)
    print('已同步:', rel_dir)

    zip_path = rel_dir + '.zip'
    tmp = zip_path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in RELEASE_FILES:
            z.write(os.path.join(rel_dir, f), dirname + '/' + f)
    shutil.move(tmp, zip_path)
    print('zip 完成:', zip_path)


if __name__ == '__main__':
    main()
