# -*- coding: utf-8 -*-
"""Release 标题统一格式：vX.Y.Z Beta（不加「版」字）

用法: python tools/rename_release_title.py [tag...]  （默认 v0.2.1 v0.2.2 v0.2.3）
"""
import subprocess, os, sys

def gh(args):
    return subprocess.run(['gh'] + args, capture_output=True, text=True, encoding='utf-8', errors='replace')

tok = subprocess.run(
    ['git', 'credential', 'fill'],
    input='protocol=https\nhost=github.com\n',
    capture_output=True, text=True
).stdout
for line in tok.splitlines():
    if line.startswith('password='):
        os.environ['GH_TOKEN'] = line[len('password='):]
        break

tags = sys.argv[1:] or ['v0.2.1', 'v0.2.2', 'v0.2.3']
for tag in tags:
    r = gh(['release', 'edit', tag, '-R', 'CiJhuiDi/DarktideModManager',
            '--title', f'{tag} Beta'])
    print(tag, '->', r.stdout.strip() or r.stderr.strip()[:200])
