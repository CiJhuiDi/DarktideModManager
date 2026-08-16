# -*- coding: utf-8 -*-
"""主题设置 API 测试：保存/读取/非法值"""
import sys, shutil
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
import theme
import state

MOCK = Path(r'D:\DeepseekWorkspace\darktide-mod-manager\mock')
state.CONFIG_FILE = MOCK / 'config_theme_test.json'
if state.CONFIG_FILE.exists():
    state.CONFIG_FILE.unlink()

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

print('=== 保存主题 ===')
r = theme.api_theme(theme.ThemeBody(theme='pleasure', grad='radial'))
test('保存 ok', r.get('ok'), r)
test('主题已存', r.get('theme') == 'pleasure', r)
test('方向已存', r.get('grad') == 'radial', r)

print('=== 只改方向 ===')
r = theme.api_theme(theme.ThemeBody(grad='hori'))
test('只改方向 ok', r.get('ok'))
test('主题不变', r.get('theme') == 'pleasure', r)
test('方向=hori', r.get('grad') == 'hori', r)

print('=== 非法值忽略 ===')
r = theme.api_theme(theme.ThemeBody(theme='hacker', grad='spin'))
test('非法主题忽略', r.get('theme') == 'pleasure', r)
test('非法方向忽略', r.get('grad') == 'hori', r)

print('=== random 可保存 ===')
r = theme.api_theme(theme.ThemeBody(theme='random'))
test('random 可存', r.get('theme') == 'random', r)

print('=== status 返回主题 ===')
import json
cfg = json.loads(state.CONFIG_FILE.read_text(encoding='utf-8'))
test('config 里有 theme', 'theme' in cfg, cfg)
test('config 里有 grad', 'grad' in cfg, cfg)

state.CONFIG_FILE.unlink(missing_ok=True)
failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过 通过')
