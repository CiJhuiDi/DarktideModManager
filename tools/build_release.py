# -*- coding: utf-8 -*-
"""正式发布一键流程：恢复版本显示 → bump → CHANGELOG 定版 → 测试 → 构建 → 打包。

用法: python tools/build_release.py 0.4.0 [--skip-tests] [--check]
  --check        只检查前置条件（版本显示状态/CHANGELOG/bump OLD），不执行
  --skip-tests   跳过全量测试（发布前不建议）
流程:
  1. 从 CHANGELOG 解析当前正式版本（OLD）
  2. 恢复版本显示（若处于 Alpha 测试态：Alpha 标记 → OLD 版本）
  3. 确保 bump_version.py 的 OLD 正确，bump 到目标版本
  4. CHANGELOG「待定」段定版为 v<目标>（今天日期）
  5. 全量测试（test_full.py）
  6. PyInstaller 构建
  7. release_pack.py 打包（目录 + zip，含 LICENSE/THIRD_PARTY）
  8. 提示后续：tools/release.py v<目标>（GitHub Release，标题 v<目标> Beta）

注意: 打包分发时应跳档（新功能 → minor 升级，如 0.3.1 → 0.4.0），参考 CHANGELOG v0.3.0 跳档说明。
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print('  ✗', ' '.join(cmd), (r.stdout or r.stderr or '')[-300:])
        sys.exit(1)
    return r.stdout or ''


def changelog_old_version() -> str:
    """CHANGELOG 最新正式版本段（## vX.Y.Z（…））"""
    t = open(os.path.join(ROOT, 'CHANGELOG.md'), encoding='utf-8').read()
    m = re.search(r'## v(\d+\.\d+\.\d+)（', t)
    if not m:
        print('CHANGELOG 找不到正式版本段')
        sys.exit(1)
    return m.group(1)


def version_state() -> str:
    """当前版本显示状态（index.html 的 DMM xxx）"""
    idx = os.path.join(ROOT, 'static', 'index.html')
    with open(idx, encoding='utf-8') as f:
        html = f.read()
    m = re.search(r'DMM ([^<]+)', html)
    return m.group(1).strip() if m else '?'


def restore_version_display(old: str):
    """Alpha 测试态 → 正式版本显示（保留功能改动，只还原版本标记）"""
    files = {
        'static/index.html': [
            ('DMM Alpha', 'DMM v' + old),
        ],
        'version_info.txt': [
            ("StringStruct('FileVersion', 'Alpha')", "StringStruct('FileVersion', '%s')" % old),
            ("StringStruct('ProductVersion', 'Alpha')", "StringStruct('ProductVersion', '%s')" % old),
        ],
        'README.txt': [
            ('Alpha 测试版', 'v' + old),
        ],
        '使用指南.txt': [
            ('DarktideModManager_alpha', 'DarktideModManager_v' + old),
        ],
        'README.md': [
            ('当前为 Alpha 测试阶段（内部测试构建，正式版本号待发布时确认）。',
             '当前为 Beta 测试阶段（v' + old + '），欢迎反馈问题与建议。'),
        ],
    }
    changed = False
    for path, pairs in files.items():
        p = os.path.join(ROOT, path)
        t = open(p, encoding='utf-8').read()
        for a, b in pairs:
            if a in t:
                t = t.replace(a, b)
                changed = True
        open(p, 'w', encoding='utf-8', newline='\n').write(t)
    return changed


def main():
    ap = argparse.ArgumentParser(description='正式发布一键流程')
    ap.add_argument('version', help='目标版本号，如 0.4.0')
    ap.add_argument('--skip-tests', action='store_true')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    new = args.version.strip()
    if not re.match(r'^\d+\.\d+\.\d+$', new):
        print('版本号格式应为 X.Y.Z，如 0.4.0')
        sys.exit(1)
    old = changelog_old_version()
    print('当前正式版本:', old, '| 目标版本:', new)
    if old == new:
        print('目标版本与当前相同，无需升级')
        sys.exit(1)

    state = version_state()
    print('当前版本显示:', state)
    if args.check:
        print('--check 模式：')
        print('  CHANGELOG OLD =', old)
        print('  bump_version.py OLD 应为', old, '（脚本会确保）')
        print('  版本显示', '已是正式态' if state == 'v' + old else '是 Alpha 测试态（发布时会自动恢复）')
        return

    # 1. 恢复版本显示（Alpha → old）
    if state != 'v' + old:
        print('[1/7] 恢复版本显示 Alpha → v%s' % old)
        restore_version_display(old)
    else:
        print('[1/7] 版本显示已是正式态 v%s' % old)

    # 2. bump：确保 bump_version OLD 正确，再升级
    print('[2/7] bump 版本 %s → %s' % (old, new))
    bp = os.path.join(ROOT, 'tools', 'bump_version.py')
    t = open(bp, encoding='utf-8').read()
    if ('OLD = "%s"' % old) not in t:
        t = re.sub(r'OLD = "\d+\.\d+\.\d+"', 'OLD = "%s"' % old, t, count=1)
        open(bp, 'w', encoding='utf-8', newline='\n').write(t)
        print('  bump_version.py OLD 已修正为', old)
    run([sys.executable, os.path.join('tools', 'bump_version.py'), new])

    # 3. CHANGELOG 定版
    print('[3/7] CHANGELOG 定版 v%s（%s）' % (new, datetime.date.today().isoformat()))
    chg = os.path.join(ROOT, 'CHANGELOG.md')
    t = open(chg, encoding='utf-8').read()
    old_marker = '## 待定（未发布）'
    if old_marker in t:
        t = t.replace(old_marker, '## v%s（%s）' % (new, datetime.date.today().isoformat()), 1)
        open(chg, 'w', encoding='utf-8', newline='\n').write(t)
    else:
        print('  （无「待定」段，跳过）')

    # 4. 测试
    if not args.skip_tests:
        print('[4/7] 全量测试（test_full.py）')
        run([sys.executable, os.path.join('tools', 'test_full.py')])
    else:
        print('[4/7] 跳过测试（--skip-tests）')

    # 5. 构建
    print('[5/7] PyInstaller 构建')
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
         '--name', 'DarktideModManager', '--icon', 'app.ico', '--version-file', 'version_info.txt',
         '--add-data', 'static;static', '--add-data', 'dmf_payload;dmf_payload',
         '--collect-all', 'webview', 'app.py'])

    # 6. 打包
    print('[6/7] release_pack.py v%s（目录 + zip）' % new)
    run([sys.executable, os.path.join('tools', 'release_pack.py'), new])

    # 7. 提示
    print('[7/7] 完成。后续步骤：')
    print('  1) 检查 git 改动并提交（版本号/CHANGELOG 定版等）')
    print('  2) python tools/release.py v%s   # 创建/更新 GitHub Release（标题 v%s Beta）' % (new, new))
    print('  3) 确认 zip 已上传 Release（含 LICENSE/THIRD_PARTY_LICENSES.md）')


if __name__ == '__main__':
    main()
