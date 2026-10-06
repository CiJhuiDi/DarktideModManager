# -*- coding: utf-8 -*-
"""前端内联 JS 语法校验：抽出 static/index.html 的内联 <script> 块，逐个交给 node --check。

为什么需要：index.html 是单文件（原生 JS 内联），后端测试套件碰不到它——
改完前端只靠肉眼看不出语法错，而语法错会让整页 JS 停摆（表现是界面一直「连接中…」）。
外链脚本（src=…）跳过；只验语法不执行，不依赖浏览器环境。

前置：node 在 PATH 中（本机 C:\\Program Files\\nodejs\\node.exe）。
用法: python tools/check_inline_js.py [index.html 路径]
退出码：0 全部通过 / 1 有语法错误 / 2 环境缺 node 或文件不存在。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
HTML = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'static' / 'index.html'

if not HTML.is_file():
    print(f'找不到文件: {HTML}')
    raise SystemExit(2)
if shutil.which('node') is None:
    print('PATH 里没有 node，无法校验（装 Node.js 后重试；本机在 C:\\Program Files\\nodejs）')
    raise SystemExit(2)

html = HTML.read_text(encoding='utf-8')
blocks = []
for m in re.finditer(r'<script(?P<attr>[^>]*)>(?P<body>.*?)</script>', html, re.S | re.I):
    if re.search(r'\bsrc\s*=', m.group('attr'), re.I):
        continue  # 外链脚本（本地 /vendor 或 CDN）不校验
    start_line = html[: m.start('body')].count('\n') + 1
    blocks.append((start_line, m.group('body')))

print(f'{HTML.name}: 内联 <script> 块 {len(blocks)} 个')
tmp = Path(tempfile.mkdtemp(prefix='dmm_js_check_'))
fail = 0
try:
    for i, (line, body) in enumerate(blocks, 1):
        p = tmp / f'inline_{i}.js'
        p.write_text(body, encoding='utf-8')
        r = subprocess.run(['node', '--check', str(p)], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        if r.returncode == 0:
            print(f'  [OK ] 块{i}（{HTML.name} 第 {line} 行起，{body.count(chr(10))} 行）')
        else:
            fail += 1
            print(f'  [FAIL] 块{i}（{HTML.name} 第 {line} 行起）')
            print((r.stderr or '').strip()[:1500])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('\n结果:', '全部通过' if fail == 0 else f'{fail} 块语法错误')
raise SystemExit(1 if fail else 0)
