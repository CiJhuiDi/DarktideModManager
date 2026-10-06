# -*- coding: utf-8 -*-
"""DMM 真界面 E2E 驱动（AI 自动化验收）——用 CDP 驱动**真实 WebView2 界面**。

为什么有它：DMM 有一堆功能只能"真机点"才知道对不对（多选拖动、弹窗文案、日志页渲染…），
以前只能靠人点。实测发现 WebView2 支持 CDP：给 exe 加
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222`（`--e2e` 开关会自己加）
就能连上真界面读 DOM / 点按钮 / 截图。于是：
    起应用 → 连 CDP → 跑剧本 → 断言 → **截图** → 退出码

前置：`pip install websocket-client`（仅测试用，不进 exe）；目标默认是 alpha exe。
用法:
    python tools/e2e_ui.py                  # 驱动 release\\DarktideModManager_alpha 的 exe（冒烟剧本）
    python tools/e2e_ui.py --source         # 驱动源码 python app.py --e2e（改完代码免打包）
    python tools/e2e_ui.py --scenario smoke --keep-open   # 跑完不关窗口（肉眼看）
退出码：0 全过 / 1 有断言失败 / 2 环境不可用（缺依赖、起不来）。
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
EXE_DEFAULT = ROOT / 'release' / 'DarktideModManager_alpha' / 'DarktideModManager.exe'
SHOT_DIR = ROOT / '99-临时文件' / 'e2e'

FAILED, PASSED, SKIPPED = [], [], []
ALLOW_REAL = False       # --allow-real：允许写真实游戏环境的剧本（默认只读脚本可跑真实环境）


def skip(name, detail=''):
    """环境不满足 → 明确跳过（不算失败，但必须显眼）"""
    SKIPPED.append(name)
    print(f"  [SKIP] {name}" + (f"  <- {detail}" if detail else ""))


def check(name, cond, detail=''):
    (PASSED if cond else FAILED).append(name)
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + ('' if cond else f"  <- {detail}"))


# ---------------------------------------------------------------- CDP 客户端

class CDP:
    """最小 CDP 客户端：发命令 + 收事件（够用：evaluate / screenshot / 监听 JS 异常）"""

    def __init__(self, ws_url, timeout=15):
        import websocket  # websocket-client
        # suppress_origin：Chromium 默认拒绝带 Origin 头的 CDP 连接
        # （否则要额外给浏览器加 --remote-allow-origins=*）
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self._id = 0
        self.events = []

    def send(self, method, **params):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        deadline = time.time() + 20
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method} 失败: {msg['error']}")
                return msg.get("result", {})
            self.events.append(msg)
        raise TimeoutError(f"{method} 超时")

    def js(self, expression):
        """在页面里执行 JS 并取值（awaitPromise 支持 async 表达式）"""
        r = self.send("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        res = r.get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(f"JS 求值出错: {res}")
        return res.get("value")

    def screenshot(self, path: Path):
        r = self.send("Page.captureScreenshot", format="png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(r["data"]))
        return path

    def js_errors(self, ignore=('favicon.ico',)):
        """页面里的 JS 异常 + 浏览器级 error 日志（带 URL）；ignore 里的资源 404 视为无害"""
        out = []
        for e in self.events:
            m = e.get("method")
            if m == "Runtime.exceptionThrown":
                d = e["params"].get("exceptionDetails", {})
                out.append("exception: " + str(d.get("text") or d.get("exception", {}).get("description", ""))[:200])
            elif m == "Log.entryAdded":
                p = e["params"].get("entry", {})
                if p.get("level") != "error":
                    continue
                url = str(p.get("url") or "")
                if any(k in url for k in ignore):
                    continue
                out.append(f"log: {str(p.get('text'))[:160]}  url={url[:120]}")
        return out

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------- 起停应用

def kill_app(proc=None):
    """关掉被测应用：先杀我们起的进程（源码模式是 python），再清同名 exe（防残留抢端口）"""
    if proc is not None:
        try:
            proc.kill()
        except Exception:
            pass
    subprocess.run(['taskkill', '/F', '/IM', 'DarktideModManager.exe'],
                   capture_output=True, timeout=20)


def launch(args):
    """返回 (工作目录, 进程, 期望的 app.log 路径)"""
    if args.source:
        workdir = ROOT
        proc = subprocess.Popen([sys.executable, 'app.py', '--e2e', '--port', str(args.port)],
                                cwd=str(workdir), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        exe = Path(args.exe)
        if not exe.is_file():
            print(f'exe 不存在: {exe}（先构建，或用 --source）')
            sys.exit(2)
        workdir = exe.parent
        proc = subprocess.Popen([str(exe), '--e2e'], cwd=str(workdir))
    return workdir, proc


def log_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def read_log(path, pattern, timeout, offset=0):
    """等 app.log **在 offset 之后**出现并匹配 pattern，返回 re.Match 或 None。

    ⚠️ 必须带 offset：app.log 是跨次运行追加的，全局取"最后一条"会被上一次运行的
    端口行误导（2026-10-06 实际踩到：手动跑的 --port 8319 旧行把冒烟/E2E 引到死端口）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(offset)
                text = f.read()
            hits = list(re.finditer(pattern, text))
            if hits:
                return hits[-1]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def wait_http(url, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception:
            time.sleep(0.5)
    return None


def cdp_target(cdp_port, app_port, timeout=30):
    """拿页面的 webSocketDebuggerUrl。

    ⚠️ 实测：exe 刚起来时可能先看到一个 about:blank 目标（WebView2 初始化顺序），
    所以要**优先挑 URL 指向本应用端口**的 page 目标，挑不到再退回任意 page。
    """
    deadline = time.time() + timeout
    fallback = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{cdp_port}/json/list', timeout=3) as r:
                targets = json.loads(r.read().decode('utf-8'))
            pages = [t for t in targets if t.get('type') == 'page' and t.get('webSocketDebuggerUrl')]
            for t in pages:
                if f':{app_port}' in str(t.get('url') or ''):
                    return t
            if pages and fallback is None:
                fallback = pages[0]
        except Exception:
            pass
        time.sleep(0.5)
    return fallback


# ---------------------------------------------------------------- 剧本

def scenario_smoke(cdp, state_json, shot: Path):
    """冒烟：页面真的渲染出来了 + 无 JS 异常 + 前后端数据一致 + 截图"""
    info = cdp.js("JSON.stringify({title: document.title, rows: document.querySelectorAll('.mod-row').length,"
                  "stats: (document.querySelector('#stats')||{}).textContent || '',"
                  "loading: !!document.querySelector('.boot-loading'),"
                  "sidebar: document.querySelectorAll('.sidebar button[data-view]').length})")
    d = json.loads(info or '{}')
    check('页面标题正确', d.get('title') == '暗潮 Mod 管理器', str(d.get('title')))
    check('侧边栏导航已渲染', (d.get('sidebar') or 0) >= 5, str(d.get('sidebar')))
    rows = d.get('rows') or 0
    check('mod 列表已渲染（不是"连接中…"）', rows > 0, f'rows={rows}')
    # 前端渲染的行数应与后端扫描数一致（骨架 mock 环境里相等）
    check('前后端 mod 数一致', rows == int(state_json['game']['mods']),
          f"前端 {rows} vs 后端 {state_json['game']['mods']}")
    check('状态栏有文案', '共' in (d.get('stats') or ''), str(d.get('stats')))
    errs = cdp.js_errors()
    check('页面无 JS 异常/错误日志（favicon 除外）', not errs, '; '.join(errs)[:300])
    p = cdp.screenshot(shot)
    check('截图已保存', p.is_file() and p.stat().st_size > 1000, str(p))

    # 关于页：切过去读一遍（顺带跑到 loadAbout 里的模板代码 —— 历史上模板字符串写坏会让整页 JS 停摆）
    cdp.js("document.querySelector('.sidebar button[data-view=\"about\"]')?.click(); true")
    time.sleep(0.8)
    ab = json.loads(cdp.js("JSON.stringify({lib: document.body.innerText.indexOf('管理器库') >= 0,"
                           "kv: document.querySelectorAll('#aboutPaths .k').length,"
                           "view: !!document.querySelector('#view-about.active')})") or '{}')
    check('关于页可切换', bool(ab.get('view')), str(ab))
    check('关于页含「管理器库」行', bool(ab.get('lib')), str(ab))
    errs2 = cdp.js_errors()
    check('关于页无 JS 异常', not errs2, '; '.join(errs2)[:300])
    p2 = cdp.screenshot(shot.with_name(shot.stem + '-about.png'))
    check('关于页截图已保存', p2.is_file() and p2.stat().st_size > 1000, str(p2))


SCENARIOS = {'smoke': scenario_smoke}


def scenario_lib(cdp, state_json, shot: Path):
    """管理器库剧本：真点标记 → 收进库 → 管理器库表出现该行 → 恢复现场

    走的是页面自己的 api()/loadMyLib()，等于验证"标记即收库 + 表格渲染"这条真链路。

    ⚠️ 安全：本剧本会**写标记 + 往管理器库拷一份**，所以
      ① 只允许跑在 mock/测试环境（真实游戏目录会被拒绝，除非 --allow-real）
      ② 先行保存用户原有标记，收尾恢复（双重保险：绝不动用户的真实数据）"""
    orig = cdp.js("api('/api/mods/mine/library').then(r => JSON.stringify((r.items||[]).map(x => x.name)))")
    try:
        orig_names = json.loads(orig or '[]')
    except Exception:
        orig_names = []
    real = 'mock' not in str(state_json.get('game', {}).get('dir', '')).lower()
    if real and not ALLOW_REAL:
        skip('lib 剧本（会写标记+收库副本）——真实游戏目录，未加 --allow-real',
             f"game_dir={state_json['game']['dir']}；请用 --source 打 mock 环境")
        return
    print(f"  （原有「我的 mod」标记 {len(orig_names)} 个，收尾会恢复）")
    if orig_names:
        print("  （库里已有内容：本次只挑**不在库里的** mod 做测试，不碰你已有的）")

    # 挑几个未被标记的 mod 标记上（够把表撑长，用于验证滚动）
    picked_raw = cdp.js("(async () => {"
                        f"  const skip = new Set({json.dumps(orig_names)});"
                        "  const rows = [...document.querySelectorAll('.mod-row')].filter(r => !skip.has(r.dataset.name));"
                        "  if (!rows.length) return '[]';"
                        "  const picked = rows.slice(0, 6).map(r => r.dataset.name);"
                        "  for (const n of picked) {"
                        "    await api('/api/mods/mine', {method:'POST', body: JSON.stringify({name:n, mine:true})});"
                        "  }"
                        "  await load(); await loadMyLib();"
                        "  return JSON.stringify(picked);"
                        "})()")
    try:
        picked = json.loads(picked_raw or '[]')
    except Exception:
        picked = []
    check('标记成功（至少 1 个）', bool(picked), str(picked_raw))
    if not picked:
        return

    # 切到管理器库页看表格
    cdp.js("document.querySelector('.sidebar button[data-view=\"mylib\"]')?.click(); true")
    time.sleep(0.8)
    exp_rows = len(orig_names) + len(picked)
    info = cdp.js("JSON.stringify({"
                  "rows: document.querySelectorAll('#mylibWrap .lib-table tbody tr').length,"
                  "names: [...document.querySelectorAll('#mylibWrap .lib-name')].map(x => x.textContent),"
                  "lib: (document.querySelector('#mylibWrap tbody tr td:nth-child(3)')||{}).innerText || '',"
                  "deployed: (document.querySelector('#mylibWrap tbody tr td:nth-child(4)')||{}).innerText || '',"
                  "btns: document.querySelectorAll('#mylibWrap tbody tr:first-child .lib-btn').length,"
                  "summary: (document.querySelector('#mylibWrap div')||{}).textContent || '',"
                  "overflow: getComputedStyle(document.getElementById('mylibWrap')).overflowY,"
                  "h: document.getElementById('mylibWrap').clientHeight,"
                  "win: window.innerHeight})")
    d = json.loads(info or '{}')
    check(f'库里出现 {exp_rows} 行（原有 {len(orig_names)} + 本次 {len(picked)}）',
          d.get('rows') == exp_rows, str(d.get('rows')))
    check('表格含刚标记的 mod', all(n in (d.get('names') or []) for n in picked), f"{picked} vs {d.get('names')}")
    check('库内列显示体积（KB）', 'KB' in (d.get('lib') or ''), str(d.get('lib')))
    check('游戏目录列显示已部署', '✓' in (d.get('deployed') or ''), str(d.get('deployed')))
    check('每行 4 个操作按钮', d.get('btns') == 4, f"首行 {d.get('btns')} 个")
    check('汇总行有"共 N 个"', f"共 {exp_rows} 个" in (d.get('summary') or ''), str(d.get('summary'))[:140])
    check('容器是滚动容器（overflow-y: auto）', d.get('overflow') == 'auto', str(d.get('overflow')))
    check('容器高度受窗口约束（不顶出窗口）', (d.get('h') or 0) < (d.get('win') or 0), f"{d.get('h')} vs {d.get('win')}")
    errs = cdp.js_errors()
    check('管理器库页无 JS 异常', not errs, '; '.join(errs)[:300])
    p = cdp.screenshot(shot)
    check('管理器库表格截图已保存', p.is_file() and p.stat().st_size > 1000, str(p))

    # 真溢出验证：把视口压矮 → 必须能滚动（scrollHeight > clientHeight），而不是被 body 裁掉
    cdp.send('Emulation.setDeviceMetricsOverride', width=1004, height=300, deviceScaleFactor=1, mobile=False)
    time.sleep(0.6)
    sc = cdp.js("JSON.stringify({sh: document.getElementById('mylibWrap').scrollHeight,"
                "ch: document.getElementById('mylibWrap').clientHeight})")
    s = json.loads(sc or '{}')
    check('视口压矮后可滚动（内容没被裁掉）', (s.get('sh') or 0) > (s.get('ch') or 0), str(s))

    # 吸顶表头必须**完全**遮住滚过的行（曾漏缝：容器 padding-top 让表头停在裁剪边界内侧，
    # 滚过的行从那 4px 缝里露出来 → 用户报"表头的元素没遮好"）
    cdp.js("(() => { const w = document.getElementById('mylibWrap'); w.scrollTop = 150; return true; })()")
    time.sleep(0.4)
    stick = cdp.js("""JSON.stringify((() => {
      const w = document.getElementById('mylibWrap');
      const th = w.querySelector('thead th');
      const thRect = th.getBoundingClientRect();
      const wr = w.getBoundingClientRect();
      const bad = [];
      for (let y = Math.round(wr.top); y < Math.round(thRect.top); y += 2) {
        const el = document.elementFromPoint(300, y);
        if (el && el.closest && el.closest('tbody')) bad.push(y + ':' + el.tagName);
      }
      const bg = getComputedStyle(th).backgroundColor;
      const m = /rgba?\\(([^)]+)\\)/.exec(bg);
      const alpha = m && m[1].split(',').length === 4 ? parseFloat(m[1].split(',')[3]) : 1;
      return {thTop: Math.round(thRect.top), wrapTop: Math.round(wr.top), bg, alpha, bad,
              padTop: getComputedStyle(w).paddingTop};
    })())""")
    k = json.loads(stick or '{}')
    check('吸顶表头上方没有滚过的行（无漏缝）', not k.get('bad'), f"漏出: {k.get('bad')} ({k})")
    check('吸顶表头背景不透明（行不会透出来）', (k.get('alpha') or 0) >= 0.99, str(k.get('bg')))
    check('表格滚动容器顶部无 padding（表头能贴住裁剪边界）', (k.get('padTop') in ('0px', '0')), str(k.get('padTop')))
    p2 = cdp.screenshot(shot.with_name(shot.stem + '-scroll.png'))
    check('滚动状态截图已保存', p2.is_file() and p2.stat().st_size > 1000, str(p2))
    cdp.send('Emulation.clearDeviceMetricsOverride')
    time.sleep(0.4)

    # 收尾：取消本次标记 + 恢复原有标记
    for n in picked:
        cdp.js(f"api('/api/mods/mine', {{method:'POST', body: JSON.stringify({{name:{json.dumps(n)}, mine:false}})}})")
        time.sleep(0.15)
    for n in orig_names:
        cdp.js(f"api('/api/mods/mine', {{method:'POST', body: JSON.stringify({{name:{json.dumps(n)}, mine:true}})}})")
        time.sleep(0.15)
    cdp.js("load()")
    time.sleep(0.4)
    left = cdp.js("api('/api/mods/mine/library').then(r => JSON.stringify((r.items||[]).map(x => x.name)))")
    try:
        left_names = json.loads(left or '[]')
    except Exception:
        left_names = []
    check('跑完现场已恢复（标记与原来一致）', left_names == orig_names, f"原 {orig_names} → 现 {left_names}")


SCENARIOS['lib'] = scenario_lib


def scenario_lists(cdp, state_json, shot: Path):
    """备份页 / 预设页现代化验收（只读：只看、只开对话框，**不保存任何设置**）。

    验的是"表格真渲染出来了 / 汇总与进度条在 / 搜索真能过滤 / 策略对话框真能打开"。"""
    # ---- 备份页 ----
    cdp.js("document.querySelector('.sidebar button[data-view=\"backups\"]')?.click(); true")
    time.sleep(0.9)
    raw = cdp.js("JSON.stringify({"
                 "summary: !!document.querySelector('#backupCards .bak-sum'),"
                 "bar: !!document.querySelector('#backupCards .bak-bar'),"
                 "rows: document.querySelectorAll('#backupCards table.lib-table tbody tr').length,"
                 "groups: [...document.querySelectorAll('#backupCards .bak-group')].map(x => x.textContent),"
                 "empty: !!document.querySelector('#backupCards .tip'),"
                 "headers: [...document.querySelectorAll('#backupCards table.lib-table th')].map(x => x.textContent),"
                 "search: !!document.getElementById('bakSearch'), sort: !!document.getElementById('bakSort'),"
                 "policy: !!document.getElementById('btnBakPolicy'), prune: !!document.getElementById('btnBakPrune'),"
                 "sumText: (document.querySelector('#backupCards .bak-sum')||{}).textContent || ''})")
    b = json.loads(raw or '{}')
    check('备份页有汇总条（占用/上限可见）', bool(b.get('summary')), str(b.get('sumText'))[:120])
    check('备份页有占用进度条', bool(b.get('bar')), str(b.get('bar')))
    check('备份页表头齐全', b.get('headers') == ['时间', '类型', '内容', '启用', '大小', '操作'], str(b.get('headers')))
    check('备份页有搜索框/排序/保留策略/清理按钮',
          all(b.get(k) for k in ('search', 'sort', 'policy', 'prune')), str(b)[:150])
    check('备份页有行或明确的空态', (b.get('rows') or 0) > 0 or bool(b.get('empty')),
          f"rows={b.get('rows')} empty={b.get('empty')}")
    check('汇总里写了"占用"和"上限"', '占用' in (b.get('sumText') or '') and '上限' in (b.get('sumText') or ''),
          str(b.get('sumText'))[:140])
    if b.get('groups'):
        check('备份页有时间线分组（今天/本周/更早）',
              all(g.split('（')[0] in ('今天', '本周', '更早') for g in b['groups']), str(b.get('groups')))

    # 搜索真能过滤（输入不可能匹配的关键词 → 0 行 + 提示）
    cdp.js("(() => { const e = document.getElementById('bakSearch'); e.value = 'zzzz-no-such';"
           " e.dispatchEvent(new Event('input')); return true; })()")
    time.sleep(0.4)
    f = json.loads(cdp.js("JSON.stringify({rows: document.querySelectorAll('#backupCards table.lib-table tbody tr').length,"
                          "tip: !!document.querySelector('#backupCards .tip')})") or '{}')
    check('备份页搜索能过滤（无匹配 → 0 行 + 提示）', (f.get('rows') or 0) == 0 and f.get('tip'), str(f))
    cdp.js("(() => { const e = document.getElementById('bakSearch'); e.value = '';"
           " e.dispatchEvent(new Event('input')); return true; })()")
    time.sleep(0.4)

    # 排序切换不报错且仍有内容
    cdp.js("(() => { const e = document.getElementById('bakSort'); e.value = 'size_desc';"
           " e.dispatchEvent(new Event('change')); return true; })()")
    time.sleep(0.4)
    check('备份页排序切换后仍有汇总条',
          bool(cdp.js("!!document.querySelector('#backupCards .bak-sum')")), '切换 size_desc 后汇总条没了')

    # 保留策略对话框（只读打开 + 关闭，不保存）
    cdp.js("document.getElementById('btnBakPolicy')?.click(); true")
    time.sleep(0.7)
    p = json.loads(cdp.js("JSON.stringify({open: !!document.querySelector('#modal.open'),"
                          "per: (document.getElementById('polPer')||{}).value || '',"
                          "mb: (document.getElementById('polMb')||{}).value || ''})") or '{}')
    check('保留策略对话框能打开', bool(p.get('open')), str(p))
    check('策略对话框带"每类保留数"和"总量上限"两个输入',
          bool(p.get('per')) and bool(p.get('mb')), str(p))
    cdp.js("document.getElementById('modalCancel')?.click(); true")
    time.sleep(0.4)

    errs = cdp.js_errors()
    check('备份页无 JS 异常', not errs, '; '.join(errs)[:300])
    p1 = cdp.screenshot(shot.with_name(shot.stem + '-backups.png'))
    check('备份页截图已保存', p1.is_file() and p1.stat().st_size > 1000, str(p1))

    # ---- 预设页 ----
    cdp.js("document.querySelector('.sidebar button[data-view=\"profiles\"]')?.click(); true")
    time.sleep(0.8)
    q = json.loads(cdp.js("JSON.stringify({"
                          "headers: [...document.querySelectorAll('#profileCards table.lib-table th')].map(x => x.textContent),"
                          "summary: !!document.querySelector('#profileCards .bak-sum'),"
                          "rows: document.querySelectorAll('#profileCards table.lib-table tbody tr').length,"
                          "empty: !!document.querySelector('#profileCards .tip'),"
                          "search: !!document.getElementById('profSearch'), sort: !!document.getElementById('profSort'),"
                          "newBtn: !!document.getElementById('btnNewProfile')})") or '{}')
    check('预设页有汇总条', bool(q.get('summary')), str(q)[:120])
    check('预设页有搜索/排序/新建按钮', all(q.get(k) for k in ('search', 'sort', 'newBtn')), str(q)[:120])
    check('预设页有行或明确的空态', (q.get('rows') or 0) > 0 or bool(q.get('empty')),
          f"rows={q.get('rows')} empty={q.get('empty')}")
    # 有预设时必须是表格（列名齐全）；没有预设时空态是正确表现
    if (q.get('rows') or 0) > 0:
        check('预设页表头齐全（有预设时）', q.get('headers') == ['预设名', 'mod 数', '创建时间', '操作'],
              str(q.get('headers')))
    cdp.js("(() => { const e = document.getElementById('profSearch'); e.value = 'zzzz-no-such';"
           " e.dispatchEvent(new Event('input')); return true; })()")
    time.sleep(0.4)
    z = json.loads(cdp.js("JSON.stringify({rows: document.querySelectorAll('#profileCards table.lib-table tbody tr').length,"
                          "tip: !!document.querySelector('#profileCards .tip')})") or '{}')
    check('预设页搜索能过滤（无匹配 → 0 行 + 提示）', (z.get('rows') or 0) == 0 and z.get('tip'), str(z))
    cdp.js("(() => { const e = document.getElementById('profSearch'); e.value = '';"
           " e.dispatchEvent(new Event('input')); return true; })()")
    time.sleep(0.4)
    errs2 = cdp.js_errors()
    check('预设页无 JS 异常', not errs2, '; '.join(errs2)[:300])
    p2 = cdp.screenshot(shot.with_name(shot.stem + '-profiles.png'))
    check('预设页截图已保存', p2.is_file() and p2.stat().st_size > 1000, str(p2))


SCENARIOS['lists'] = scenario_lists


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', default=str(EXE_DEFAULT), help='被测 exe（默认 alpha 包）')
    ap.add_argument('--source', action='store_true', help='改为驱动源码 python app.py --e2e')
    ap.add_argument('--port', type=int, default=8317, help='源码模式的 HTTP 端口')
    ap.add_argument('--scenario', default='smoke', choices=sorted(SCENARIOS))
    ap.add_argument('--keep-open', action='store_true', help='跑完不关应用（肉眼看）')
    ap.add_argument('--allow-real', action='store_true',
                    help='允许会写盘的剧本跑在真实游戏目录上（默认拒绝；写盘剧本请优先用 --source 打 mock）')
    ap.add_argument('--timeout', type=int, default=60, help='等应用起来的总超时（秒）')
    args = ap.parse_args()
    global ALLOW_REAL
    ALLOW_REAL = bool(args.allow_real)

    try:
        import websocket  # noqa: F401
    except ImportError:
        print('缺 websocket-client：python -m pip install websocket-client')
        sys.exit(2)

    print(f'== DMM E2E（{args.scenario}）==')
    kill_app()
    workdir, proc = launch(args)
    log_offset = log_size(workdir / 'app.log')      # 只看本次启动后新增的日志
    cdp = None
    try:
        log = workdir / 'app.log'
        print(f'  启动: {"源码" if args.source else args.exe}  (工作目录 {workdir})')

        m = read_log(log, r'E2E ready app=(\d+) cdp=(\d+)', args.timeout, offset=log_offset)
        if not m:
            print('  ✗ 未在 app.log 找到 "E2E ready"（应用没起来？或不是 --e2e 模式）')
            sys.exit(2)
        app_port, cdp_port = int(m.group(1)), int(m.group(2))
        print(f'  E2E ready: app={app_port} cdp={cdp_port}')

        state_json = wait_http(f'http://127.0.0.1:{app_port}/api/test/state', args.timeout)
        if not state_json:
            print('  ✗ /api/test/state 无响应（钩子没注册？）')
            sys.exit(2)
        print(f"  环境: 游戏目录={state_json['game']['dir']} valid={state_json['game']['valid']} "
              f"mods={state_json['game']['mods']} enabled={state_json['game']['enabled']}")

        t = cdp_target(cdp_port, app_port, args.timeout)
        if not t:
            print('  ✗ 连不上 CDP 目标（CDP 端口没开？）')
            sys.exit(2)
        print(f"  CDP 目标: {t.get('title')} @ {t.get('url')}")

        cdp = CDP(t['webSocketDebuggerUrl'])
        cdp.send('Runtime.enable')
        cdp.send('Log.enable')
        cdp.send('Page.enable')
        time.sleep(1.0)                       # 给前端 load() 一点时间
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        shot = SHOT_DIR / f'{ts}-{args.scenario}.png'
        print(f'-- 剧本 {args.scenario} --')
        SCENARIOS[args.scenario](cdp, state_json, shot)
        print(f'\n  截图: {shot}')
    finally:
        if cdp is not None:
            cdp.close()
        if not args.keep_open:
            kill_app(proc)
        else:
            print('  （--keep-open：应用保持运行）')

    print(f'\n结果: {len(PASSED)} 通过 / {len(FAILED)} 失败'
          + (f' / {len(SKIPPED)} 跳过' if SKIPPED else '')
          + (f'  失败项: {FAILED}' if FAILED else ''))
    if SKIPPED:
        print(f'  跳过项: {SKIPPED}')
    sys.exit(1 if FAILED else 0)


if __name__ == '__main__':
    main()
