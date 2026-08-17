# -*- coding: utf-8 -*-
"""版本显示切换到 Alpha 测试态一键（正式态 vX.Y.Z → Alpha，RULES 第 9 条）。

与 tools/build_release.py 的 restore_version_display（Alpha → 正式）镜像：
内部测试构建前先跑本脚本，界面/exe 版本标识只标 Alpha、不带具体版本号、不打 zip。
用法: python tools/set_alpha_state.py [--check]
  --check  只显示当前状态，不修改
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 镜像 build_release.restore_version_display：正式态标记 → Alpha 态标记
# 每项: (路径, [(正式态正则, 替换为)])
REPLACEMENTS = [
    ('static/index.html', [
        (r'DMM v\d+\.\d+\.\d+', 'DMM Alpha'),
    ]),
    ('version_info.txt', [
        (r"StringStruct\('FileVersion', '\d+\.\d+\.\d+'\)", "StringStruct('FileVersion', 'Alpha')"),
        (r"StringStruct\('ProductVersion', '\d+\.\d+\.\d+'\)", "StringStruct('ProductVersion', 'Alpha')"),
    ]),
    ('README.txt', [
        (r'DarktideModManager v\d+\.\d+\.\d+', 'DarktideModManager Alpha 测试版'),
    ]),
    ('使用指南.txt', [
        (r'DarktideModManager_v\d+\.\d+\.\d+', 'DarktideModManager_alpha'),
    ]),
    ('README.md', [
        (r'当前为 Beta 测试阶段（v\d+\.\d+\.\d+），欢迎反馈问题与建议。',
         '当前为 Alpha 测试阶段（内部测试构建，正式版本号待发布时确认）。'),
    ]),
]


def version_state() -> str:
    """当前版本显示状态（index.html 的 DMM xxx）"""
    idx = os.path.join(ROOT, 'static', 'index.html')
    with open(idx, encoding='utf-8') as f:
        html = f.read()
    m = re.search(r'DMM ([^<]+)', html)
    return m.group(1).strip() if m else '?'


def main():
    ap = argparse.ArgumentParser(description='切换版本显示到 Alpha 测试态')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    state = version_state()
    print('当前版本显示:', state)
    if state == 'Alpha':
        print('已是 Alpha 测试态，无需切换')
        return
    if not re.match(r'^v\d+\.\d+\.\d+$', state):
        print('当前状态异常（%s），不做自动切换，请手动检查' % state)
        sys.exit(1)
    if args.check:
        print('当前为正式态 %s，执行切换将改为：DMM Alpha（界面/exe 只标 Alpha）' % state)
        return

    changed = False
    for path, pairs in REPLACEMENTS:
        p = os.path.join(ROOT, path)
        t = open(p, encoding='utf-8').read()
        for pat, repl in pairs:
            t2, n = re.subn(pat, repl, t)
            if n:
                t = t2
                changed = True
                print('  %-24s %d 处: %s -> %s' % (path, n, pat, repl))
        open(p, 'w', encoding='utf-8', newline='\n').write(t)
    if changed:
        print('已切换到 Alpha 测试态（%s -> DMM Alpha）。正式发布时 build_release.py 会自动恢复。' % state)
    else:
        print('未发现可替换的正式版本标记（可能已是 Alpha 态或格式异常）')


if __name__ == '__main__':
    main()
