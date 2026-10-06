# -*- coding: utf-8 -*-
"""真实日志回归探针（只读）：拿玩家**真实** console 日志体检 DMM 的日志诊断能力。

为什么需要它：日志分析是 DMM 的定位所在，但它面对的是"玩家的真实日志"——内置
样本测过了不等于真日志上有效。2026-10-06 就是这么发现「MOD 错误排行一个 mod 都
指不出来」的：真实日志里错误行走 `[MOD][名]` 自报标记，而当时代码只认路径式引用
（`scripts/mods/<名>`），8 份真实日志 58 条错误行命中 0 条。

日志目录按**管理器自己的分布解析**取（`core.crash.resolve_crash_root()`），
所以 Steam 版与 Xbox / Game Pass 版都能直接跑。

用法:
    python tools/log_probe.py                 # 概览最新 3 份：诊断条目 / 归属排行 / 标记计数
    python tools/log_probe.py rank [N]        # MOD 错误排行（最新 N 份，默认 5）
    python tools/log_probe.py errs [关键字]    # 打印判为 err 的行 + 后随 3 行（关键字可省，默认最新一份）
    python tools/log_probe.py big             # 最大一份：全文 vs「只取开头 2MB」对照
"""
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import crash  # noqa: E402


def log_dir():
    """当前有效日志根目录（走管理器自己的分布解析），找不到返回 (None, 提示文本)"""
    root, distro = crash.resolve_crash_root()
    if root is None:
        return None, '未找到日志目录，已查：' + crash.crash_root_hint()
    return root, f'日志目录: {root}（{crash.CRASH_DISTRO_LABELS.get(distro, distro)}）'


def all_logs(root):
    d = root / 'console_logs'
    return sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime, reverse=True)


def _diag_kinds(diag):
    k = {}
    for d in diag:
        k[d.get('kind')] = k.get(d.get('kind'), 0) + 1
    return k


def cmd_overview(limit=3):
    root, msg = log_dir()
    print(msg)
    if root is None:
        return 1
    for f in all_logs(root)[:limit]:
        text = f.read_text(encoding='utf-8', errors='replace')
        lines = text.splitlines()
        diag = crash.parse_crash_blocks(text)
        agg = crash.aggregate_mod_errors(lines)
        named = [e for e in agg if e['mod']]
        sig = {}
        for d in diag:
            sig[(d.get('kind'), (d.get('message') or '')[:120], d.get('system') or '')] = \
                sig.get((d.get('kind'), (d.get('message') or '')[:120], d.get('system') or ''), 0) + 1
        dup = sum(1 for v in sig.values() if v > 1)
        print()
        print('=' * 74)
        print(f'{f.name}  ({f.stat().st_size / 1024:.0f} KB / {len(lines)} 行)')
        print('=' * 74)
        print(f"  诊断条目 {len(diag)} {_diag_kinds(diag) or ''}" + (f"  [!] 重复组 {dup}" if dup else ''))
        print(f"  标记: <<Lua Error>> {text.count('<<Lua Error>>')} / <<Script Error>> {text.count('<<Script Error>>')}"
              f" / <<crashify-exception>> {text.count('<<crashify-exception>>')}")
        body = ', '.join(f"{e['mod']}x{e['count']}" + (f"[版本不兼容{e['hook_missing']}]" if e.get('hook_missing') else '')
                         for e in named) or '(无 mod 被归属)'
        unnamed = next((e['count'] for e in agg if not e['mod']), 0)
        print(f'  MOD 错误排行: {body} | 游戏本体 {unnamed} 条')
    return 0


def cmd_rank(limit=5):
    root, msg = log_dir()
    print(msg)
    if root is None:
        return 1
    total = 0
    for f in all_logs(root)[:limit]:
        lines = f.read_text(encoding='utf-8', errors='replace').splitlines()
        agg = crash.aggregate_mod_errors(lines)
        named = [e for e in agg if e['mod']]
        total += len(named)
        body = ', '.join(f"{e['mod']}x{e['count']}" + (f"[版本不兼容{e['hook_missing']}]" if e.get('hook_missing') else '')
                         for e in named) or '(无 mod 被归属)'
        unnamed = next((e['count'] for e in agg if not e['mod']), 0)
        print(f"  {f.name[:46]:<48} mod {len(named)} | {body} | 游戏本体 {unnamed}")
    print(f'\n  合计 {limit} 份日志指出 {total} 个 mod 条目（若为 0，先怀疑归属规则漏了日志里的新标记形态）')
    return 0


def cmd_errs(keyword=''):
    root, msg = log_dir()
    print(msg)
    if root is None:
        return 1
    logs = all_logs(root)
    f = next((x for x in logs if keyword and keyword in x.name), logs[0] if logs else None)
    if f is None:
        print('  没有日志文件')
        return 1
    lines = f.read_text(encoding='utf-8', errors='replace').splitlines()
    errs = [(i, ln) for i, ln in enumerate(lines) if crash.classify_log_line(ln) == 'err']
    print(f'  {f.name}：判为 err 的行 {len(errs)} 条\n')
    for i, ln in errs[:40]:
        t = crash.MOD_TAG_RE.search(ln)
        p = crash.MOD_PATH_RE.search(ln)
        print(f'--- L{i + 1}  路径={p.group(1) if p else None}  标记={t.group(1) if t else None}')
        print(f'    {ln.strip()[:190]}')
        for j in range(i + 1, min(len(lines), i + 4)):
            print(f'    +{j - i} {lines[j].strip()[:150]}')
    if len(errs) > 40:
        print(f'  …还有 {len(errs) - 40} 条')
    return 0


def cmd_big():
    root, msg = log_dir()
    print(msg)
    if root is None:
        return 1
    logs = all_logs(root)
    if not logs:
        print('  没有日志文件')
        return 1
    f = max(logs, key=lambda p: p.stat().st_size)
    text = f.read_text(encoding='utf-8', errors='replace')
    print(f'  {f.name}  {len(text.encode("utf-8", errors="replace")) / 1024 / 1024:.1f} MB / {len(text.splitlines())} 行\n')
    window, dropped, trimmed = crash._tail_window(text, crash.MAX_ANALYZE_CHARS)
    full = crash.parse_crash_blocks(text)
    now = crash.parse_crash_blocks(window)          # 现役：末尾 2MB
    old = crash.parse_crash_blocks(text[:crash.MAX_ANALYZE_CHARS])   # 旧实现：开头 2MB
    e_full = sum(e['count'] for e in crash.aggregate_mod_errors(text.splitlines()))
    e_now = sum(e['count'] for e in crash.aggregate_mod_errors(window.splitlines()))
    e_old = sum(e['count'] for e in crash.aggregate_mod_errors(text[:crash.MAX_ANALYZE_CHARS].splitlines()))
    print(f'  全文          → 诊断 {len(full)} 条 / 错误行 {e_full}')
    print(f'  现役（末尾 2MB）→ 诊断 {len(now)} 条 / 错误行 {e_now}'
          + (f'（丢了最早的 {len(full) - len(now)} 条诊断，前 {dropped} 行未载入）' if trimmed else '（未超限，无截断）'))
    print(f'  旧实现（开头 2MB）→ 诊断 {len(old)} 条 / 错误行 {e_old}  ← 留作回归护栏：修复前就是这个数')
    return 0


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == 'rank':
        return cmd_rank(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
    if arg == 'errs':
        return cmd_errs(sys.argv[2] if len(sys.argv) > 2 else '')
    if arg == 'big':
        return cmd_big()
    return cmd_overview()


if __name__ == '__main__':
    raise SystemExit(main())
