# -*- coding: utf-8 -*-
"""发布 GitHub Release（通用版）。
用法: python tools/release.py v0.3.0
说明: 从 CHANGELOG.md 提取 [tag] 对应版本段作为正文，创建/更新 Release 并上传 zip。
"""
import subprocess, os, sys, argparse, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def gh(args):
    return subprocess.run(['gh'] + args, capture_output=True, text=True, encoding='utf-8', errors='replace')

def get_token():
    tok = subprocess.run(
        ['git', 'credential', 'fill'],
        input='protocol=https\nhost=github.com\n',
        capture_output=True, text=True
    ).stdout
    for line in tok.splitlines():
        if line.startswith('password='):
            os.environ['GH_TOKEN'] = line[len('password='):]
            return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag', help='版本 tag，如 v0.3.0')
    ap.add_argument('--repo', default='CiJhuiDi/DarktideModManager')
    ap.add_argument('--notes-file', default=None,
                    help='面向玩家的 Release 正文（Markdown，如 docs/release_notes/v0.6.0.md）。'
                         '不给则退回「CHANGELOG 版本段 + 固定模板」——那是内部变更记录，玩家看不懂重点')
    ap.add_argument('--skip-upload', action='store_true', help='只改 Release 正文，不上传 zip')
    args = ap.parse_args()

    if args.notes_file:
        body = open(args.notes_file, encoding='utf-8').read().strip()
    else:
        changelog = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'CHANGELOG.md'),
                         encoding='utf-8').read()
        start = changelog.find('## ' + args.tag)
        if start == -1:
            print(f'CHANGELOG 中找不到 ## {args.tag}')
            sys.exit(1)
        nxt = changelog.find('\n## ', start + len(args.tag) + 3)
        section = changelog[start:nxt].strip() if nxt != -1 else changelog[start:].strip()

        body = section + """

### 功能
- 一键安装 DMF 框架（加载器 + 中文汉化 + dtkit-patch + 自动装载）
- 整合包一键导入（替换/合并双模式），换包不堆积，旧包自动归档可找回
- Mod 中文显示名、启停/排序/搜索、方案预设、批量操作
- 依赖检查（缺依赖/循环/顺序）、导入导出（含清单）、差异对比预览
- 一键启动游戏、补丁自动管理、游戏运行防呆、归档备份恢复页

### 使用
解压后双击 DarktideModManager.exe，首次按顶部提示「一键安装 DMF」，再「导入整合包」即可。
详见包内《使用指南.txt》。
"""

    if not get_token():
        print('无法获取 GitHub 凭据')
        sys.exit(1)

    # 正文走 --notes-file：v0.6.0 起 CHANGELOG 版本段超过 Windows 命令行 8191 字符上限，
    # 直接塞 --notes 会报 FileNotFoundError [WinError 206]（2026-11-18 踩到）。
    notes_path = os.path.join(tempfile.gettempdir(), f'dmm_release_{args.tag}.md')
    with open(notes_path, 'w', encoding='utf-8') as f:
        f.write(body)

    try:
        # 先查是否存在，再决定 create / edit。
        # 2026-11-18 踩到：先 create（预期 422 already exists）紧接着 edit，edit 会莫名报
        # "release not found"；换成先 view 判断就正常了。别改回 create→edit 的写法。
        exists = gh(['release', 'view', args.tag, '-R', args.repo]).returncode == 0
        if exists:
            r = gh(['release', 'edit', args.tag, '-R', args.repo, '--title', f'{args.tag} Beta',
                    '--notes-file', notes_path])
            print('edit:', r.stdout.strip() or r.stderr.strip()[:200])
        else:
            r = gh(['release', 'create', args.tag, '-R', args.repo, '--title', f'{args.tag} Beta',
                    '--notes-file', notes_path])
            print('create:', r.stdout.strip() or r.stderr.strip()[:200])
        if r.returncode != 0:
            print('⚠️ 正文更新失败（rc=%d）' % r.returncode)
    finally:
        try:
            os.unlink(notes_path)
        except OSError:
            pass

    # 上传 zip
    if args.skip_upload:
        print('--skip-upload：只更新正文，不动 zip')
    else:
        zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'release',
                                f'DarktideModManager_{args.tag}.zip')
        if os.path.exists(zip_path):
            r = gh(['release', 'upload', args.tag, zip_path, '-R', args.repo, '--clobber'])
            print('upload:', r.stdout.strip() or r.stderr.strip()[:200])
        else:
            print('zip 不存在，跳过上传:', zip_path)

    r = gh(['release', 'view', args.tag, '-R', args.repo])
    print('---')
    print(r.stdout[:600])

if __name__ == '__main__':
    main()
