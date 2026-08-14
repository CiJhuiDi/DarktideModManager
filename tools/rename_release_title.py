# -*- coding: utf-8 -*-
"""Release 标题 内测版 -> Beta 版"""
import subprocess, os

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

for tag in ['v0.2.3', 'v0.2.2', 'v0.2.1']:
    r = gh(['release', 'edit', tag, '-R', 'CiJhuiDi/DarktideModManager',
            '--title', f'{tag} Beta 版'])
    print(tag, '->', r.stdout.strip() or r.stderr.strip()[:200])
