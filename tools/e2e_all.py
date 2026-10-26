# -*- coding: utf-8 -*-
"""一次跑完全部真界面 E2E 剧本并汇总。

为什么需要它：`tools/e2e_ui.py` 一次只跑一个剧本，而它的中文输出经管道时常按 GBK 落盘，
在 PowerShell 里直接拼多个命令容易把"通过/失败"读错（踩过：汇总数字对不上）。
这里统一用 UTF-8 读子进程输出，并把 5 个剧本的结果对齐成一张表。

剧本分两类：
  · 只读剧本（smoke / lists）—— 打真 exe 的真实环境
  · 写盘剧本（lib / mineconflict / dragpack）—— 只打 mock（--source），会改数据，
    真实游戏目录会被 e2e_ui.py 自动跳过（要跑必须显式 --allow-real）

用法：python tools\\e2e_all.py [--exe <路径>]
返回码 0 = 全过；1 = 有剧本失败（便于接进 CI / 收尾清单）。
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
# (剧本名, 额外参数, 说明)
PLAN = [
    ('smoke', [], '真 exe · 只读'),
    ('lists', [], '真 exe · 只读（备份页/预设页）'),
    ('lib', ['--source'], 'mock · 写盘（管理器库）'),
    ('mineconflict', ['--source'], 'mock · 写盘（同名冲突逐个选）'),
    ('dragpack', ['--source'], 'mock · 写盘（拖动导入只解压一次）'),
]
TOTAL_RE = re.compile(r'(\d+)\s*通过\s*/\s*(\d+)\s*失败')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', default='', help='被测 exe（默认 alpha 包；仅用于只读剧本）')
    args = ap.parse_args()

    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}   # 子进程输出可能是 GBK，强制 UTF-8 才读得准
    bad = []
    print('== DMM 真界面 E2E 全套 ==')
    for name, extra, desc in PLAN:
        cmd = [sys.executable, 'tools/e2e_ui.py', '--scenario', name] + extra
        if args.exe and '--source' not in extra:
            cmd += ['--exe', args.exe]
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=env,
                           encoding='utf-8', errors='replace', timeout=900)
        out = (r.stdout or '') + (r.stderr or '')
        m = TOTAL_RE.search(out)
        ok, fail = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)
        good = (r.returncode == 0 and fail == 0 and ok > 0)
        print(f'  [{"OK " if good else "BAD"}] {name:13s} {ok:>3} 通过 / {fail} 失败   {desc}')
        for line in [l.strip() for l in out.splitlines() if '[FAIL]' in l][:6]:
            print(f'          {line[:130]}')
        if not good:
            bad.append(name)
    print('全部通过' if not bad else f'有 {len(bad)} 个剧本失败: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
