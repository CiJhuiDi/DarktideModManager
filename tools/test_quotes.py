# -*- coding: utf-8 -*-
"""语录 API 测试：310 条官方语录 / 无空条 / 编号前缀已去除 / API 可访问"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
from core.quotes import QUOTES
import app

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

print('=== 数据模块 ===')
test('共 310 条', len(QUOTES) == 310, f'实际 {len(QUOTES)}')
test('无空条', all(isinstance(q, str) and q.strip() for q in QUOTES))
test('无残留编号前缀', all(not q.startswith(('001', '002')) or not q[:3].isdigit() for q in QUOTES))
test('中文文本', all(any('\u4e00' <= ch <= '\u9fff' for ch in q) for q in QUOTES))
test('首条=信仰胜过一切', QUOTES[0] == '信仰胜过一切', QUOTES[0])
test('末条存在', len(QUOTES[-1]) > 0, QUOTES[-1])

print('=== API ===')
r = app.api_quotes()
test('返回 quotes 字段', isinstance(r.get('quotes'), list), type(r.get('quotes')))
test('API 条数=310', len(r.get('quotes', [])) == 310, f"实际 {len(r.get('quotes', []))}")
test('与数据模块一致', r.get('quotes') == QUOTES)

failed = [n for n, ok in checks if not ok]
print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
if failed:
    print('失败:', failed)
    raise SystemExit(1)
print('全部通过')
