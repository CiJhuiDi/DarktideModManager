# -*- coding: utf-8 -*-
"""前后端路由对账（只读）：查「前端在调、后端没有」的断链，以及「后端有、前端从没调」的死路由。

为什么需要它：DMM 的后端路由散在 app.py + core/*.py（APIRouter），前端是单文件内联 JS，
两边靠字符串约定对齐——**这条约定已经断过一次**：`api_set_game_dir` 重构时装饰器被吞，
函数裸奔，前端点「选择文件夹」直接 404（HANDOFF 第八节有记录）。
改路由/改前端 API 调用后跑一遍，比等着用户报 404 便宜。

判据：
  - 「断链」必须是**空**——非空就是真 bug（前端会拿到 404）。
  - 「死路由」允许存在：白名单外多出来的，逐个确认是给测试/外部用的还是真没人用。
用法: python tools/route_audit.py
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
# 前端不调用、但确实存在的路由（页面本身 / 测试或外部工具用）
# · /api/pack/preview 是旧版"base64 上传预览"，现前端改走 /api/pack/stage（一次上传一次解压），
#   该接口保留给脚本与测试（tools/test_preview.py 直接用）
# · /api/test/* 是 --e2e 专属钩子，由 tools/e2e_ui.py 的剧本用 fetch 调，静态页里搜不到
# · /api/order/rebuild 与 rebuild_preview 是"手动重建清单"的后端实现。前端按钮已按用户要求撤掉
#   （2026-10-10），但接口与 core/load_order.py 的重建逻辑保留给脚本与测试
#   （tools/test_load_order.py 直接调用它们），所以这里登记为"前端不调用但确实存在"
DEAD_OK = {'/', '/api/test/state', '/api/test/reset', '/api/test/import_pack',
           '/api/test/extract_reset', '/api/pack/preview',
           '/api/order/rebuild', '/api/order/rebuild_preview'}


def backend_routes():
    routes = []
    for f in [ROOT / 'app.py'] + sorted((ROOT / 'core').glob('*.py')):
        txt = f.read_text(encoding='utf-8', errors='replace')
        for m in re.finditer(r'@(?:app|router)\.(get|post|put|delete)\(\s*[\'"]([^\'"]+)', txt):
            routes.append((m.group(2), m.group(1).upper(), f.name))
    return routes


def frontend_calls():
    html = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8', errors='replace')
    calls = set()
    for m in re.finditer(r"""(?:api|fetch)\(\s*['"`]([^'"`]+)""", html):
        p = m.group(1)
        if not p.startswith('/'):
            continue
        p = p.split('?')[0]                              # 去查询串
        p = re.sub(r'\$\{[^}]+\}', '\x00', p)            # 模板串插值 → 单段占位
        calls.add(p.rstrip('/') or '/')
    return calls


def route_re(p: str):
    """路由 → 正则：`{param}` 与模板占位都匹配单段路径"""
    return re.compile('^' + re.escape(re.sub(r'\{[^}]+\}', '\x00', p)).replace('\x00', '[^/]+') + '$')


def main():
    routes, calls = backend_routes(), frontend_calls()
    matched, broken = set(), []
    for c in sorted(calls):
        ok = False
        for p, _verb, _src in routes:
            # 直接匹配；或前端用拼接（api('/api/backups/' + bid + '/preview')）只捕获到前缀
            if route_re(p).match(c) or route_re(p).match(c + '\x00') or p.startswith(c.replace('\x00', '')):
                ok = True
                break
        (matched.add(c) if ok else broken.append(c))

    print(f'后端路由 {len(routes)} 条 | 前端 API 调用 {len(calls)} 个 | 命中 {len(matched)}')
    print('\n== 断链（前端在调、后端没有）==')
    print('  ' + ('\n  '.join(broken) if broken else '（无）'))

    unused = [f'{v:<6} {p:<42} ({s})' for p, v, s in sorted(routes)
              if p not in DEAD_OK and not any(route_re(p).match(c) or route_re(p).match(c + '\x00')
                                              or p.startswith(c.replace('\x00', '')) for c in calls)]
    print('\n== 死路由（后端有、前端从没调）==')
    print('  ' + ('\n  '.join(unused) if unused else '（无）'))
    return 1 if broken else 0


if __name__ == '__main__':
    raise SystemExit(main())
