# -*- coding: utf-8 -*-
"""文档体检：篇幅占比 + 跨文档重复段落（交给"文档是不是又胀了"用）。

为什么需要：项目文档会随功能累积只涨不缩（DMM 的 PROJECT_HANDOFF 一度有 38% 篇幅
在"按版本叙事"），而定期的客观体检比肉眼看更可靠——本脚本给出三个可量化信号：
  ① 每份文档的行数/字符数/章节数（谁最胖）
  ② 最大那份文档里各章节的行数占比（胖在哪一节）
  ③ 跨文档**段落级**重复（≥25 字的同一段落同时出现在几份文档里 → 该合并）

只读，不改任何文件。用法:
    python tools/doc_audit.py                 # 扫描本仓全部 .md/.txt
    python tools/doc_audit.py <额外文件...>    # 再纳入指定文件（如 workspace 的 RULES.md）
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent

# 扫描时跳过的目录（构建产物、运行时数据、第三方组件、临时文件）
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', 'build', 'dist', 'release',
             'dmf_payload', 'exports', 'profiles', 'backups', 'custom_theme',
             '99-临时文件', '_archive', '7zbin'}
SKIP_PREFIX = ('mock', 'demo')          # mock*/demo*/mock_fresh…
EXTS = ('.md', '.txt')


def discover():
    out = []
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        parts = set(p.relative_to(ROOT).parts[:-1])
        if parts & SKIP_DIRS or any(part.startswith(SKIP_PREFIX) for part in parts):
            continue
        out.append(p)
    return out


def headings(lines):
    """[(标题, 起始行, 该节行数)]：支持 markdown # / 【小节】 / 一、 三种写法"""
    idx = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if (re.match(r'^#{1,4}\s+\S', s) or re.match(r'^[【\[].+[】\]]$', s)
                or re.match(r'^[一二三四五六七八九十]+、\S', s)):
            idx.append((s.lstrip('# ').strip(), i))
    return [(t, st + 1, (idx[k + 1][1] if k + 1 < len(idx) else len(lines)) - st)
            for k, (t, st) in enumerate(idx)]


def blocks(text):
    """段落级切块（规范化空白），用于跨文档重复检测；太短的丢弃（标题/符号噪声）"""
    out = []
    for b in re.split(r'\n\s*\n', text):
        s = re.sub(r'\s+', ' ', b).strip()
        if len(s) >= 25:
            out.append(s)
    return out


def main():
    files = discover()
    extra = [Path(a) for a in sys.argv[1:]]
    for p in extra:
        if p.is_file() and p not in files:
            files.append(p)

    print('=' * 78)
    print('一、篇幅总览（按体积）')
    print('=' * 78)
    data = {}
    for p in files:
        text = p.read_text(encoding='utf-8', errors='replace')
        lines = text.splitlines()
        data[p] = (text, lines, headings(lines))
    print(f"{'文件':<44}{'行':>5}{'字符':>8}{'KB':>7}  章节")
    for p, (text, lines, hs) in sorted(data.items(), key=lambda kv: -len(kv[1][0])):
        try:
            rel = str(p.relative_to(ROOT))
        except ValueError:
            rel = str(p)
        print(f'{rel:<44}{len(lines):>5}{len(text):>8}{len(text.encode("utf-8")) / 1024:>7.1f}  {len(hs)}')

    if data:
        biggest = max(data.items(), key=lambda kv: len(kv[1][0]))[0]
        text, lines, hs = data[biggest]
        print()
        print('=' * 78)
        print(f'二、最大文档各章节占比：{biggest.name}（{len(lines)} 行）')
        print('=' * 78)
        for title, start, n in sorted(hs, key=lambda x: -x[2])[:14]:
            pct = 100.0 * n / max(1, len(lines))
            print(f'  L{start:<4} {n:>3} 行 {pct:>5.1f}%  {"#" * max(1, round(pct / 2)):<26} {title[:44]}')

    print()
    print('=' * 78)
    print('三、跨文档重复段落（≥25 字的同一段落同时出现在几份文档里）')
    print('=' * 78)
    bmap = {str(p): set(blocks(t)) for p, (t, _, _) in data.items()}
    names = list(bmap)
    found = False
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            inter = bmap[a] & bmap[b]
            if inter:
                found = True
                la = Path(a).name if a.startswith(str(ROOT)) else a
                lb = Path(b).name if b.startswith(str(ROOT)) else b
                print(f'  {la} ↔ {lb}: {len(inter)} 段重复')
                for s in list(inter)[:2]:
                    print(f'      · {s[:88]}…' if len(s) > 88 else f'      · {s}')
    if not found:
        print('  （无：说明冗余是"主题级"而非"文字级"，需要人工看章节结构）')


if __name__ == '__main__':
    main()
