# -*- coding: utf-8 -*-
"""导入清单 API 测试：替换清单、保留注释、防呆"""
import sys, shutil, subprocess
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app
from core import patch
from core import state

MOCK = ROOT / 'mock'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_lo_test.json'
state.BACKUP_DIR = MOCK / 'backups_lo_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}

subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_mock.py')], check=True)

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

lo = MOCK / 'mods' / 'mod_load_order.txt'

print('=== 导入清单 ===')
content = 'TestModC\n--TestModA\nTestModB\n'
r = app.api_load_order_import(app.LoadOrderImportBody(content=content))
test('导入 ok', r.get('ok'), r.get('message'))
lines = lo.read_text(encoding='utf-8').splitlines()
test('清单已替换（旧式禁用标记被清理）', set(lines) == {'TestModC', 'TestModB'}, lines)

print('=== 带空行/CRLF 清洗 ===')
r = app.api_load_order_import(app.LoadOrderImportBody(content='TestModA\r\n\r\n--TestModB\r\n'))
test('CRLF+空行清洗 ok', r.get('ok'))
lines = lo.read_text(encoding='utf-8').splitlines()
test('空行被过滤（旧式禁用标记被清理）', '' not in lines and set(lines) == {'TestModA'}, lines)

print('=== 空内容拒绝 ===')
r = app.api_load_order_import(app.LoadOrderImportBody(content='  \n\n'))
test('空内容拒绝', not r.get('ok'))

print('=== 旧清单已备份 ===')
baks = list((state.BACKUP_DIR).glob('mod_load_order.*.bak'))
test('有备份', len(baks) >= 1, len(baks))

print('=== 游戏运行中拒绝 ===')
app.is_game_running = lambda: True
patch.is_game_running = lambda: True
r = app.api_load_order_import(app.LoadOrderImportBody(content='TestModA'))
test('游戏运行中拒绝', not r.get('ok') and '游戏正在运行' in r.get('error',''), r)
app.is_game_running = lambda: False
patch.is_game_running = lambda: False

print('=== 手动重建当前清单（去掉作者注释） ===')
# 造一份"脏清单"：作者注释 + 已有 mod + 幽灵条目 + 磁盘上新增但没在清单里的 mod
for n in ('RebuildA', 'RebuildB', 'RebuildNew'):
    d = MOCK / 'mods' / n
    d.mkdir(exist_ok=True)
    (d / f'{n}.mod').write_text('return { run = function() new_mod("x", {}) end, packages = {}, version = "1.0" }',
                                encoding='utf-8')
lo.write_text('-- 顶部说明：本包由某某整合\n-- 遇到问题加群 123456\n'
              'RebuildA\n-- === 界面类 ===\nRebuildB\nGhostNotOnDisk\n-- 下面必须在前\n',
              encoding='utf-8')

pv = app.api_rebuild_preview()
test('预览可用', pv.get('ok') is True, str(pv)[:120])
test('预览认出幽灵条目', pv.get('ghosts') == ['GhostNotOnDisk'], str(pv.get('ghosts')))
test('预览统计注释行数', pv.get('comments') == 4, str(pv.get('comments')))
test('预览说明注释会被去掉', pv.get('comments_dropped') == 4 and pv.get('comments_kept') == 0, str(pv)[:90])
test('默认不启用磁盘上原本没启用的 mod（否则会把整个包全开）',
      pv.get('new') == [] and 'RebuildNew' in (pv.get('new_skipped') or []), str(pv.get('new_skipped')))

r = app.api_rebuild_order(app.RebuildOrderBody())      # 默认 strip_comments=True, add_new=False
test('重建 ok', r.get('ok') is True, str(r)[:120])
text = lo.read_text(encoding='utf-8')
lines = text.splitlines()
test('作者注释已去掉', all(not l.startswith('-- 顶部说明') and '界面类' not in l and '下面必须在前' not in l
                          for l in lines), lines)
test('首行是 DMM 自己的来源说明', lines[0].startswith('-- 本清单由 DMM'), lines[0] if lines else '')
test('幽灵条目被移除', 'GhostNotOnDisk' not in text, lines)
test('原有 mod 顺序保留', [l for l in lines if l.startswith('Rebuild')] == ['RebuildA', 'RebuildB'], lines)
test('原本没启用的 mod 仍然没启用', 'RebuildNew' not in (r.get('result') or []), str(r.get('result')))
test('结果统计正确', r.get('removed') == ['GhostNotOnDisk'] and r.get('added') == [], str(r)[:120])

print('=== 重建的选项：保留注释 / 明确要求才启用新增 ===')
lo.write_text('-- 作者说明\nRebuildA\nRebuildB\n', encoding='utf-8')
r2 = app.api_rebuild_order(app.RebuildOrderBody(add_new=False, strip_comments=False))
test('可保留注释', '-- 作者说明' in lo.read_text(encoding='utf-8'), lo.read_text(encoding='utf-8')[:80])
test('不自动启用新增（RebuildNew 不在清单）', 'RebuildNew' not in (r2.get('result') or []), str(r2.get('result')))
r2b = app.api_rebuild_order(app.RebuildOrderBody(add_new=True, strip_comments=False))
test('明确要求时才追加新增', 'RebuildNew' in (r2b.get('result') or []), str(r2b.get('result')))

print('=== 重建也会先备份 ===')
before_baks = len(list((state.BACKUP_DIR).glob('mod_load_order.*.bak')))
app.api_rebuild_order(app.RebuildOrderBody())
after_baks = len(list((state.BACKUP_DIR).glob('mod_load_order.*.bak')))
test('重建前留了备份', after_baks >= before_baks, f'{before_baks} -> {after_baks}')

print('=== 游戏运行中拒绝重建 ===')
patch.is_game_running = lambda: True
r3 = app.api_rebuild_order(app.RebuildOrderBody())
test('游戏运行中拒绝重建', not r3.get('ok') and '游戏正在运行' in (r3.get('error') or ''), str(r3)[:120])
patch.is_game_running = lambda: False

# 清理
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
state.CONFIG_FILE.unlink(missing_ok=True)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 通过')
