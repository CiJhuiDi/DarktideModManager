# -*- coding: utf-8 -*-
"""日志根目录多分布单测：crash.py 的 Steam / MicrosoftStore（Xbox·Game Pass）双候选解析
   + state.detect_game_dir 的 Xbox/Game Pass 常见安装位置兜底。

不碰真实环境：APPDATA 指向临时目录，Xbox 安装根目录用假路径注入，跑完还原。
用法: python tools/test_crash_root.py
"""
import json
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import crash, state  # noqa: E402

checks = []


def check(name, cond, detail=''):
    checks.append((name, bool(cond)))
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + ('' if cond else f'  ← {detail}'))


class _CapHandler(logging.Handler):
    """收集日志记录：验证 app.log 留痕内容（不真写文件）"""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


TMP = Path(tempfile.mkdtemp(prefix='dmm_crash_root_'))
OLD_APPDATA = os.environ.get('APPDATA')
OLD_BASE_DIR = state.BASE_DIR

appdata = TMP / 'AppData'
steam_root = appdata / 'Fatshark' / 'Darktide'
store_root = appdata / 'Fatshark' / 'MicrosoftStore' / 'Darktide'
steam_root.mkdir(parents=True)
store_root.mkdir(parents=True)
os.environ['APPDATA'] = str(appdata)


def clear_logs(root: Path):
    """清掉候选目录下的日志内容（保留目录本身）"""
    shutil.rmtree(root / 'console_logs', ignore_errors=True)
    shutil.rmtree(root / 'crash_dumps', ignore_errors=True)


def write_log(root: Path, name: str) -> Path:
    d = root / 'console_logs'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('[ERROR] boot failed\n', encoding='utf-8')
    return p


def write_dump(root: Path, name: str) -> Path:
    d = root / 'crash_dumps'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b'dmp')
    return p


try:
    print('== 候选路径 ==')
    cands = dict(crash.crash_root_candidates())
    check('Steam 候选 = %APPDATA%\\Fatshark\\Darktide',
          cands.get(crash.CRASH_DISTRO_STEAM) == steam_root, cands)
    check('MicrosoftStore 候选 = %APPDATA%\\Fatshark\\MicrosoftStore\\Darktide',
          cands.get(crash.CRASH_DISTRO_STORE) == store_root, cands)

    print('== 只有 Steam 有日志 ==')
    clear_logs(store_root)
    write_log(steam_root, 'console-2026-09-20-01.log')
    root, distro = crash.resolve_crash_root()
    check('选中 Steam 目录', root == steam_root and distro == crash.CRASH_DISTRO_STEAM, (root, distro))
    r = crash.api_crash_logs()
    check('/api/crash_logs 返回 Steam 控制台日志',
          r.get('ok') and r.get('distro') == 'steam' and r['console']['name'] == 'console-2026-09-20-01.log', r)

    print('== 只有 MicrosoftStore 有日志（Game Pass 分支）==')
    clear_logs(steam_root)
    write_log(store_root, 'console-2026-09-20-02.log')
    root, distro = crash.resolve_crash_root()
    check('选中 MicrosoftStore 目录', root == store_root and distro == crash.CRASH_DISTRO_STORE, (root, distro))
    r = crash.api_crash_logs()
    check('/api/crash_logs 返回商店版日志',
          r.get('ok') and r.get('distro') == 'microsoft_store' and r['console']['name'] == 'console-2026-09-20-02.log', r)
    read = crash._read_latest_console(50)
    check('/api/crash_logs/read 读商店版日志',
          read is not None and read['file'] == 'console-2026-09-20-02.log', read)

    print('== 两分布都有日志：Steam 优先（同分靠前）==')
    write_log(steam_root, 'console-2026-09-20-03.log')
    root, distro = crash.resolve_crash_root()
    check('同分选 Steam', root == steam_root and distro == crash.CRASH_DISTRO_STEAM, (root, distro))

    print('== 有日志 > 仅目录存在 ==')
    clear_logs(steam_root)
    write_log(store_root, 'console-2026-09-20-04.log')
    root, distro = crash.resolve_crash_root()
    check('商店版有日志时压过空 Steam 目录', root == store_root, (root, distro))

    print('== 打开日志目录（用分布名提示）==')
    opened = {}
    orig_startfile = getattr(crash.os, 'startfile', None)
    crash.os.startfile = lambda p: opened.setdefault('path', p)  # type: ignore[attr-defined]
    try:
        r = crash.api_crash_logs_open()
        check('打开的是商店版 console_logs',
              r.get('ok') and Path(opened.get('path', '')) == store_root / 'console_logs', (r, opened))
        check('提示里带分布名', 'Xbox / Game Pass 版' in (r.get('message') or ''), r)
    finally:
        if orig_startfile is None:
            del crash.os.startfile  # type: ignore[attr-defined]
        else:
            crash.os.startfile = orig_startfile  # type: ignore[attr-defined]

    print('== 崩溃报告导出（只放游戏侧材料 + 分布信息）==')
    state.BASE_DIR = TMP / 'base'
    (TMP / 'base').mkdir(parents=True, exist_ok=True)
    (TMP / 'base' / 'app.log').write_text(
        '2026-10-02 01:00:00 INFO 启动 | 游戏目录=X (valid=False)\n',
        encoding='utf-8')
    write_dump(store_root, 'crash-2026-09-20.dmp')
    r = crash.api_crash_logs_export()
    ok_export = r.get('ok') and Path(r['path']).is_file()
    check('导出 zip 成功', ok_export, r)
    if ok_export:
        with zipfile.ZipFile(r['path']) as z:
            names = z.namelist()
            info = json.loads(z.read('report_info.json').decode('utf-8'))
        check('zip 含商店版控制台日志', 'console_logs/console-2026-09-20-04.log' in names, names)
        check('zip 含崩溃转储', 'crash_dumps/crash-2026-09-20.dmp' in names, names)
        check('报告记录分布', info.get('日志目录分布') == 'Xbox / Game Pass 版', info)
        check('报告记录日志目录', info.get('日志目录') == str(store_root), info)
        # 定位：这个 zip 是给「不懂怎么修、要发给懂行人看」的玩家打包游戏侧材料的，
        # 管理器自身诊断（app.log / 候选列表 / APPDATA）不应混进来——那些留在 app.log 里单独发
        check('zip 不夹带 app.log（管理器日志不进给他人看的报告包）',
              not any(n.startswith('app.log') for n in names), names)
        check('report_info 不含管理器内部诊断字段',
              not ({'日志目录候选诊断', '游戏目录自动识别诊断', 'APPDATA', 'app.log 导出行数'} & set(info)),
              sorted(info.keys()))
    state.BASE_DIR = OLD_BASE_DIR

    print('== 两分布都没有：报错列出两条候选路径 ==')
    clear_logs(steam_root)
    clear_logs(store_root)
    shutil.rmtree(steam_root)
    shutil.rmtree(store_root)
    root, distro = crash.resolve_crash_root()
    check('返回 (None, "")', root is None and distro == '', (root, distro))
    r = crash.api_crash_logs()
    check('/api/crash_logs 报错含两种路径',
          r.get('ok') is False and 'MicrosoftStore' in (r.get('error') or '') and 'Fatshark' in (r.get('error') or ''), r)
    check('/api/crash_logs/read 无日志返回失败', crash.api_crash_logs_read(300).get('ok') is False)
    r = crash.api_crash_logs_open()
    check('/api/crash_logs/open 报错含商店版路径', r.get('ok') is False and 'MicrosoftStore' in (r.get('error') or ''), r)

    print('== detect_game_dir：Xbox/Game Pass 兜底 ==')
    xbox_root = TMP / 'XboxGames'
    game_dir = xbox_root / 'Warhammer 40,000 Darktide' / 'Content'
    (game_dir / 'bundle').mkdir(parents=True)
    other = xbox_root / 'SomeOtherGame' / 'Content'
    (other / 'bundle').mkdir(parents=True)
    orig_steam = state._steam_game_candidates
    orig_xbox = state._xbox_games_dirs
    state._steam_game_candidates = lambda: []          # 排除真实 Steam 库干扰
    state._xbox_games_dirs = lambda: [xbox_root]
    try:
        check('XboxGames 下识别到暗潮（Content 层）', state.detect_game_dir() == game_dir, state.detect_game_dir())
        shutil.rmtree(xbox_root / 'Warhammer 40,000 Darktide')
        check('非暗潮目录名不误判（无候选 → None）', state.detect_game_dir() is None, state.detect_game_dir())
    finally:
        state._steam_game_candidates = orig_steam
        state._xbox_games_dirs = orig_xbox

    print('== app.log 诊断留痕（Xbox / Game Pass 用户回报用）==')
    cap = _CapHandler()
    root_logger = logging.getLogger()
    old_level = root_logger.level
    root_logger.addHandler(cap)
    root_logger.setLevel(logging.INFO)
    try:
        write_log(store_root, 'console-2026-09-20-09.log')   # 造出「商店版有日志」的可用环境
        crash._last_probe_sig = None                         # 清去重状态，保证本次一定写
        r, d = crash.resolve_crash_root()
        crash.log_crash_root_probe('单测-命中', r, d)
        check('留痕：命中时写 INFO 且带分布名 + 实际路径',
              any(x.levelno == logging.INFO and '命中=Xbox / Game Pass 版' in x.getMessage()
                  and str(store_root) in x.getMessage() for x in cap.records),
              [x.getMessage() for x in cap.records])
        n_before = len(cap.records)
        crash.log_crash_root_probe('单测-命中', r, d)          # 同环境再触发一次
        check('留痕：相同环境重复触发只记一条（不刷屏）',
              len(cap.records) == n_before, [x.getMessage() for x in cap.records[n_before:]])

        clear_logs(store_root)
        shutil.rmtree(store_root, ignore_errors=True)
        shutil.rmtree(steam_root, ignore_errors=True)   # 前面「两分布都没有」小节可能已删过
        crash._last_probe_sig = None
        r2, d2 = crash.resolve_crash_root()
        crash.log_crash_root_probe('单测-未命中', r2, d2)
        warns = [x for x in cap.records if x.levelno == logging.WARNING]
        check('留痕：未命中时写 WARNING，列出两条候选 + 评分 + APPDATA 实际值',
              bool(warns) and 'MicrosoftStore' in warns[-1].getMessage()
              and '评分=' in warns[-1].getMessage() and 'APPDATA=' in warns[-1].getMessage(),
              [x.getMessage() for x in warns[-1:]])
    finally:
        root_logger.removeHandler(cap)
        root_logger.setLevel(old_level)

    print('== 诊断数据结构（进导出报告用）==')
    rep = crash.crash_root_report()
    check('crash_root_report 两条候选且顺序 = Steam → MicrosoftStore',
          [x['distro'] for x in rep] == [crash.CRASH_DISTRO_STEAM, crash.CRASH_DISTRO_STORE], rep)
    check('crash_root_report 字段齐全（label/path/exists/console/dumps/score）',
          all({'distro', 'label', 'path', 'exists', 'console', 'dumps', 'score'} <= set(x) for x in rep), rep)
    diag = crash.crash_root_diagnosis()
    check('crash_root_diagnosis 含两分布路径 + APPDATA',
          'MicrosoftStore' in diag and 'Fatshark' in diag and 'APPDATA=' in diag, diag)

    xbox2 = TMP / 'XboxGames2'
    (xbox2 / 'Warhammer 40,000 Darktide' / 'Content' / 'bundle').mkdir(parents=True)
    orig_xdirs = state._xbox_games_dirs
    state._xbox_games_dirs = lambda: [xbox2]
    try:
        gd = state.game_dir_diagnosis()
        check('game_dir_diagnosis 含 XboxGames 根目录 + 候选有效性标记',
              str(xbox2) in gd and '/有效' in gd and 'XboxGames 根目录=' in gd, gd)
    finally:
        state._xbox_games_dirs = orig_xdirs
        shutil.rmtree(xbox2, ignore_errors=True)
finally:
    if OLD_APPDATA is None:
        os.environ.pop('APPDATA', None)
    else:
        os.environ['APPDATA'] = OLD_APPDATA
    state.BASE_DIR = OLD_BASE_DIR
    shutil.rmtree(TMP, ignore_errors=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks) - len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过')
