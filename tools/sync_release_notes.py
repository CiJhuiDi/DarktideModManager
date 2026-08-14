# -*- coding: utf-8 -*-
"""
按本地 CHANGELOG.md 的指定版本段，同步更新 GitHub Release 说明。
用法: python tools/sync_release_notes.py v0.2.3 [--repo CiJhuiDi/DarktideModManager]
说明: 从 CHANGELOG.md 提取 [tag] 对应的更新内容，替换 Release 的 notes（保留"功能/使用"附录）。
"""
import subprocess, os, sys, argparse

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
    ap.add_argument('tag', help='版本 tag，如 v0.2.3')
    ap.add_argument('--repo', default='CiJhuiDi/DarktideModManager')
    ap.add_argument('--changelog', default=r'CHANGELOG.md')
    args = ap.parse_args()

    changelog_path = args.changelog
    if not os.path.isabs(changelog_path):
        changelog_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', changelog_path)
    changelog = open(changelog_path, encoding='utf-8').read()

    start = changelog.find('## ' + args.tag)
    if start == -1:
        print(f'CHANGELOG 中找不到 ## {args.tag}')
        sys.exit(1)
    # 找下一个 ## 版本段
    nxt = changelog.find('\n## ', start + len(args.tag) + 3)
    section = changelog[start:nxt].strip() if nxt != -1 else changelog[start:].strip()

    body = section + """

### 功能
- 一键安装 DMF 框架（加载器 + 中文汉化 + dtkit-patch + 自动装载）
- 整合包一键导入（替换/合并双模式），换包不堆积，旧包自动归档可找回
- Mod 中文显示名、启停/排序/搜索、方案预设
- 右键菜单：打开文件夹 / 复制名 / 备注 / 删除（回收站）/ 清理残留
- 一键启动游戏、补丁自动管理、归档备份恢复页

### 使用
解压后双击 DarktideModManager.exe，首次按顶部提示「一键安装 DMF」，再「导入整合包」即可。
详见包内《使用指南.txt》。
"""

    if not get_token():
        print('无法获取 GitHub 凭据')
        sys.exit(1)

    r = gh(['release', 'edit', args.tag, '-R', args.repo, '--notes', body])
    if r.returncode != 0:
        print('失败:', r.stderr.strip()[:300])
        sys.exit(1)
    print(f'OK: Release {args.tag} 说明已按 CHANGELOG 更新')

if __name__ == '__main__':
    main()
