# -*- coding: utf-8 -*-
"""alpha 测试版构建一键：PyInstaller → 同步 release/DarktideModManager_alpha/（不打 zip）。
规则（RULES 第 9 条）：alpha 不带版本号只标 Alpha、不打 zip、不对外发布。
用法: python tools/build_alpha.py [--skip-build] [--check]
  --check       只检查当前版本显示状态（是否 Alpha 测试态），不构建
  --skip-build  跳过构建，只同步 release 目录
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALPHA_DIR = os.path.join(ROOT, 'release', 'DarktideModManager_alpha')
RELEASE_FILES = ['DarktideModManager.exe', 'README.txt', '使用指南.txt', 'LICENSE', 'THIRD_PARTY_LICENSES.md']

BUILD_CMD = [
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
    '--name', 'DarktideModManager', '--icon', 'app.ico', '--version-file', 'version_info.txt',
    '--add-data', 'static;static', '--add-data', 'dmf_payload;dmf_payload',
    '--collect-all', 'webview', 'app.py',
]


def version_state():
    """返回当前版本显示状态: 'alpha'（DMM Alpha）或版本号字符串"""
    idx = os.path.join(ROOT, 'static', 'index.html')
    with open(idx, encoding='utf-8') as f:
        html = f.read()
    import re
    m = re.search(r'DMM ([^<]+)', html)
    return m.group(1).strip() if m else '?'


def main():
    ap = argparse.ArgumentParser(description='alpha 构建一键（不带版本号、不打 zip）')
    ap.add_argument('--skip-build', action='store_true')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    state = version_state()
    print('当前版本显示:', state)
    if args.check:
        print('期望: DMM Alpha（alpha 测试态）；若显示 vX.Y.Z 说明非测试态，构建产物会带正式版本号')
        return
    if state != 'Alpha':
        print('⚠️  当前不是 Alpha 测试态（显示 %s）。alpha 构建应只标 Alpha（RULES 第 9 条）。' % state)
        print('   继续构建将产出带正式版本号的 exe——确认继续请输入 y:')
        if input().strip().lower() != 'y':
            print('已取消')
            return

    if not args.skip_build:
        print('构建中…')
        r = subprocess.run(BUILD_CMD, cwd=ROOT)
        if r.returncode != 0:
            print('构建失败')
            sys.exit(1)
        print('构建完成')

    os.makedirs(ALPHA_DIR, exist_ok=True)
    for f in RELEASE_FILES:
        src = os.path.join(ROOT, 'dist', 'DarktideModManager.exe') if f == 'DarktideModManager.exe' else os.path.join(ROOT, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(ALPHA_DIR, f))
    print('已同步:', ALPHA_DIR)
    print('（alpha 不打 zip、不对外发布）')


if __name__ == '__main__':
    main()
