# -*- coding: utf-8 -*-
"""发布 GitHub Release（通用版）。
用法: python tools/release.py v0.3.0
说明: 从 CHANGELOG.md 提取 [tag] 对应版本段作为正文，创建/更新 Release 并上传 zip。
"""
import subprocess, os, sys, argparse
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
    args = ap.parse_args()

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

    # 创建（已存在则编辑标题+正文，实现幂等）
    r = gh(['release', 'create', args.tag, '-R', args.repo, '--title', f'{args.tag} Beta', '--notes', body])
    if r.returncode != 0:
        # 已存在 → 编辑
        r = gh(['release', 'edit', args.tag, '-R', args.repo, '--title', f'{args.tag} Beta', '--notes', body])
        print('edit:', r.stdout.strip() or r.stderr.strip()[:200])

    # 上传 zip
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
