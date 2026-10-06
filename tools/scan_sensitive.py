# -*- coding: utf-8 -*-
"""扫描仓库跟踪文件中的硬编码敏感信息"""
import re, subprocess, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parent.parent

files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8').stdout.splitlines()

patterns = {
    'GitHub token (ghp_/gho_/github_pat_)': re.compile(r'\b(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
    '等号赋值 token/key/secret/password': re.compile(r'(?i)\b(token|api[_-]?key|secret|password|passwd|pwd)\s*=\s*["\'][^"\']{8,}["\']'),
    '私有 IP/本机路径': re.compile(r'[A-Za-z]:\\Users\\(?!Public)'),
    '代理地址': re.compile(r'127\.0\.0\.1:\d{4,5}|http://127\.0\.0\.1'),
    '恢复码/GCM 字样': re.compile(r'(?i)recovery[- ]?code|恢复码'),
}

hits = []
for f in files:
    p = ROOT / f
    try:
        content = p.read_text(encoding='utf-8', errors='replace')
    except Exception:
        continue
    for name, pat in patterns.items():
        for m in pat.finditer(content):
            line_no = content[:m.start()].count('\n') + 1
            line = content.splitlines()[line_no - 1].strip()[:100]
            hits.append((f, line_no, name, line))

for h in hits:
    print(f"{h[0]}:L{h[1]} [{h[2]}] {h[3]}")
if not hits:
    print("未发现硬编码敏感信息（token/key/password/恢复码/本机用户名路径/代理）")
print(f"\n共 {len(hits)} 处")
