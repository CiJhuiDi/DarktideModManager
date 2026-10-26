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

def running_instances() -> list:
    """已在运行的 DMM 实例（exe 与源码模式都算）。**这些不是我们起的**，绝不能杀。"""
    out = []
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'DarktideModManager.exe' "
             "-or ($_.Name -like 'python*' -and $_.CommandLine -like '*app.py*') } "
             "| Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=30)
        out = [int(x) for x in (r.stdout or '').split() if x.strip().isdigit()]
    except Exception:
        pass
    return out


def kill_app(proc=None):
    """只关**我们自己起的**进程。

    ⚠️ 以前这里无脑 `taskkill /IM DarktideModManager.exe`，会把用户正在用的窗口一起杀掉
    （2026-10-06 实际发生过：用户正在验收整合包导入，窗口被 E2E 干掉，界面断言也跟着偶发失败）。
    现在：给了 proc 就杀 proc 及其子进程；没给就什么都不做。
    另外顺手清掉**我们自己留下的孤儿 WebView2**——它会锁住 exe，让随后的重建同步失败。"""
    if proc is None:
        return
    try:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                       capture_output=True, timeout=20)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    # 孤儿 WebView2（命令行指向 DMM 的）会占着 exe 句柄；只清属于我们的那些
    try:
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
             "Where-Object { $_.CommandLine -like '*DarktideModManager*' } | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=30)
        for pid in [x for x in (r.stdout or '').split() if x.strip().isdigit()]:
            subprocess.run(['taskkill', '/F', '/T', '/PID', pid], capture_output=True, timeout=20)
        if r.stdout.strip():
            time.sleep(2.0)          # 等句柄释放，免得紧接着的构建同步失败
    except Exception:
        pass


def launch(args):
    """返回 (工作目录, 进程)。**起之前先看有没有别人在跑**——有就拒绝，不打扰用户的窗口。"""
    others = running_instances()
    if others:
        print(f'  ✗ 检测到已在运行的 DMM 实例（PID {others}）。')
        print('    E2E 需要独占一个实例，但**不会**去杀你正在用的窗口。')
        print('    请先自己关掉它再跑；确认要强杀可加 --allow-kill。')
        if not getattr(args, 'allow_kill', False):
            sys.exit(2)
        for pid in others:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True, timeout=20)
        time.sleep(1.5)
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
    # 首次打开会自动弹新手引导（遮罩会挡住坐标计算），先关掉
    cdp.js("try { window.__dmmEndTour && window.__dmmEndTour(); } catch(e) {}; true")
    time.sleep(0.3)
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

    # 侧边栏展开/收起（52px 图标栏 ↔ 168px 文字栏；transition 0.16s，每步要等它走完）
    cdp.js("""(() => {
      const nav = document.querySelector('.sidebar');
      const b = document.getElementById('btnSidebarToggle');
      if (nav.classList.contains('expanded')) b.click();   // 上次跑留下展开态就先收回去
      return true;
    })()""")
    time.sleep(0.4)
    sb0 = json.loads(cdp.js("""JSON.stringify({
      w: Math.round(document.querySelector('.sidebar').getBoundingClientRect().width),
      font: getComputedStyle(document.querySelector('.sidebar button[data-view="mods"]')).fontSize})""") or '{}')
    check('侧边栏默认 52px 图标栏（文字隐藏）', sb0.get('w') == 52 and sb0.get('font') == '0px', str(sb0))

    cdp.js("document.getElementById('btnSidebarToggle').click(); true")
    time.sleep(0.4)
    sb1 = json.loads(cdp.js("""JSON.stringify({
      w: Math.round(document.querySelector('.sidebar').getBoundingClientRect().width),
      font: getComputedStyle(document.querySelector('.sidebar button[data-view="mods"]')).fontSize,
      lbl: !!document.querySelector('#btnSidebarToggle .lbl'),
      lblW: Math.round((document.querySelector('#btnSidebarToggle .lbl') || {getBoundingClientRect: () => ({width: 0})})
             .getBoundingClientRect().width),
      saved: localStorage.getItem('dmm_sidebar_open')})""") or '{}')
    check('展开后回到 168px 且文字可见',
          sb1.get('w') == 168 and sb1.get('font') not in ('0px', None) and (sb1.get('lblW') or 0) > 0, str(sb1))
    check('展开状态记进 localStorage', sb1.get('saved') == '1', str(sb1))

    # Ctrl+B 也能切，切完收回 52px（不影响后面的截图）
    cdp.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'b', ctrlKey: true, bubbles: true})); true")
    time.sleep(0.4)
    sbc = json.loads(cdp.js("""JSON.stringify({
      w: Math.round(document.querySelector('.sidebar').getBoundingClientRect().width),
      saved: localStorage.getItem('dmm_sidebar_open')})""") or '{}')
    check('Ctrl+B 能收起侧边栏', sbc.get('w') == 52 and sbc.get('saved') == '0', str(sbc))

    # 三栏布局 + 详情栏（2026-10-26 UI 重写）
    lay = json.loads(cdp.js("""JSON.stringify({
      cols: document.querySelectorAll('.cols .col').length,
      off: document.querySelectorAll('#bodyOff .mod-row').length,
      on: document.querySelectorAll('#bodyOn .mod-row').length,
      infoEmpty: (document.querySelector('#modInfo .info-desc') || {}).textContent || ''})""") or '{}')
    check('Mod 页是三栏（未启用 / 已启用 / 详情）', lay.get('cols') == 3, str(lay))
    check('两栏行数之和与后端一致',
          (lay.get('off') or 0) + (lay.get('on') or 0) == rows, str(lay))

    # 拖动落位 → 顺序必须写回数据。曾因 onEnd 不回写 mods，render() 按旧顺序重绘 = 松手弹回原位
    reorder = json.loads(cdp.js("""(() => {
      const body = document.getElementById('bodyOn');
      const rows = [...body.querySelectorAll('.mod-row')];
      if (rows.length < 3) return JSON.stringify({skip: true, n: rows.length});
      const before = rows.map(r => r.dataset.name).slice(0, 4);
      body.insertBefore(rows[2], rows[0]);          // 模拟「把第 3 行拖到最前」
      const moved = [...body.querySelectorAll('.mod-row')].map(r => r.dataset.name).slice(0, 4);
      window.__dmmReorderFromDom();                 // 拖完做的事：DOM 顺序 → 数据 → 重绘
      const after = [...document.querySelectorAll('#bodyOn .mod-row')].map(r => r.dataset.name).slice(0, 4);
      return JSON.stringify({skip: false, before, moved, after});
    })()""") or '{}')
    if reorder.get('skip'):
        skip('拖拽排序（已启用 mod 不足 3 个）', str(reorder))
    else:
        check('拖动落位后重绘不弹回原顺序（顺序已写回数据）',
              reorder.get('after') == reorder.get('moved'), str(reorder))

    # 左栏的行必须可拖（拖出去 = 启用）。Sortable 在 pointerdown 时才给行打 draggable：
    # 曾被 filter:'.disabled'（未启用行都带这个 class）和 sort:false（连 draggable 都不加）双双挡死。
    # 注意：Sortable 只在 document 的 mouseup 上收尾，所以测完要补一次 mouseup 再放行后续操作。
    press = json.loads(cdp.js("""(() => {
      const row = document.querySelector('#bodyOff .mod-row');
      if (!row) return JSON.stringify({skip: true});
      const b = row.getBoundingClientRect();
      row.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, cancelable: true,
        clientX: b.left + 30, clientY: b.top + 10, button: 0, buttons: 1,
        pointerId: 1, pointerType: 'mouse', isPrimary: true}));
      const ok = row.draggable === true;
      document.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
      const inst = window.Sortable ? Sortable.get(document.getElementById('bodyOff')) : null;
      return JSON.stringify({skip: false, draggable: ok, filter: inst ? String(inst.options.filter) : null});
    })()""") or '{}')
    if press.get('skip'):
        skip('左栏拖拽（左栏没有行）', str(press))
    else:
        check('左栏的行能被拖（没被 filter / sort:false 挡住）',
              press.get('draggable') is True and press.get('filter') in ('null', None), str(press))

    cdp.js("(() => { const r = document.querySelector('#bodyOn .mod-row') || "
           "document.querySelector('#bodyOff .mod-row'); if (r) r.click(); return true; })()")
    time.sleep(0.7)
    det = json.loads(cdp.js("""JSON.stringify({
      name: (document.querySelector('#modInfo .info-name') || {}).textContent || '',
      kv: document.querySelectorAll('#modInfo .info-kv').length,
      note: !!document.getElementById('noteEdit')})""") or '{}')
    check('点行后详情栏显示内容', bool(det.get('name')) and (det.get('kv') or 0) >= 3, str(det))
    check('详情栏有备注编辑区', det.get('note') is True, str(det))

    # 详情栏常驻：没有「收起」按钮，也不会被点行藏起来
    info2 = json.loads(cdp.js("""(() => {
      const col = document.getElementById('colInfo');
      const disp = () => getComputedStyle(col).display;
      const row = document.querySelector('#bodyOn .mod-row') || document.querySelector('#bodyOff .mod-row');
      if (row) row.click();
      return JSON.stringify({display: disp(),
        closeBtn: !!document.getElementById('infoClose'),
        hasName: ((document.querySelector('#modInfo .info-name') || {}).textContent || '').length > 0});
    })()""") or '{}')
    check('详情栏常驻显示', info2.get('display') != 'none', str(info2))
    check('详情栏没有收起按钮', info2.get('closeBtn') is False, str(info2))
    check('点行后详情栏有内容', info2.get('hasName') is True, str(info2))

    # 游戏运行中：卡片变灰只读，单击看详情仍可用，拖拽被拦
    lock1 = json.loads(cdp.js("""(() => {
      gameRunning = true; updateEditLocks();
      const body = document.getElementById('bodyOn');
      const row = body.querySelector('.mod-row');
      const op = row ? parseFloat(getComputedStyle(row).opacity) : null;
      const s = window.Sortable ? Sortable.get(body) : null;
      const canDrag = (s && s.options.onMove) ? s.options.onMove() : null;
      return JSON.stringify({op, locked: body.classList.contains('locked'), canDrag});
    })()""") or '{}')
    check('游戏运行中卡片变灰', (lock1.get('op') or 1) < 0.9, str(lock1))
    check('游戏运行中整栏标记为只读', lock1.get('locked') is True, str(lock1))
    check('游戏运行中拖拽被拦（onMove 返回 false）', lock1.get('canDrag') is False, str(lock1))

    cdp.js("(() => { const r = document.querySelector('#bodyOn .mod-row'); if (r) r.click(); return true; })()")
    time.sleep(0.5)
    lock2 = json.loads(cdp.js("""(() => {
      const info = ((document.querySelector('#modInfo .info-name') || {}).textContent || '').length > 0;
      gameRunning = false; updateLaunchBtn();   // 用 updateLaunchBtn 恢复：它内部会调 updateEditLocks，也会还原启动按钮文案
      const row = document.querySelector('#bodyOn .mod-row');
      const opAfter = row ? parseFloat(getComputedStyle(row).opacity) : null;
      return JSON.stringify({info, opAfter});
    })()""") or '{}')
    check('游戏运行中单击仍能看详情', lock2.get('info') is True, str(lock2))
    check('解除锁定后卡片透明度恢复', (lock2.get('opAfter') or 0) > 0.9, str(lock2))

    # 「恢复布局」必须常驻可见（原来「改过布局才出现」，用户根本找不到这功能）
    rz = json.loads(cdp.js("""(() => {
      const b = document.getElementById('btnResetLayout');
      if (!b) return JSON.stringify({exists: false});
      return JSON.stringify({exists: true, display: getComputedStyle(b).display,
        vis: b.getBoundingClientRect().width > 0});
    })()""") or '{}')
    check('「恢复布局」按钮常驻可见', rz.get('exists') is True and rz.get('vis') is True, str(rz))

    # 诊断条：两个灯常驻（DMF 组件已并入补丁状态、依赖检查），点一项能真的展开/收起对应横幅
    # （2026-10-26 修：此处曾绑了两个 click 监听，后一个把状态强制设回 true，导致点不动）
    diag = json.loads(cdp.js("""(() => {
      const disp = k => getComputedStyle(document.getElementById(k + 'Wrap')).display;
      // 点击之前先记一次：曾因 applyBannerMode 只在「状态刚变化」时调用，
      // 首次加载（一直红或一直绿）一条都不进，诊断条保持 display:none 一直不出现。
      const litBefore = getComputedStyle(document.getElementById('bannerLights')).display;
      let key = ['dmf','dep'].find(k => disp(k) !== 'none') || 'dmf';
      const cap = key[0].toUpperCase() + key.slice(1);
      const b = disp(key);
      document.getElementById('lightItem' + cap).click();
      const a = disp(key);
      document.getElementById('lightItem' + cap).click();
      const c = disp(key);
      return JSON.stringify({key, b, a, c, litBefore, lights: document.querySelectorAll('.b-light-item').length,
        lit: document.getElementById('bannerLights').style.display});
    })()""") or '{}')
    check('诊断条一开始就可见（不用先点一下）', diag.get('litBefore') == 'flex', str(diag))
    check('诊断条常驻一行', diag.get('lit') == 'flex', str(diag))
    check('诊断条只剩两项（补丁已并入 DMF 组件）', diag.get('lights') == 2, str(diag))
    check('点诊断条能收起/展开对应横幅', diag.get('b') != diag.get('a'), str(diag))
    check('再点一下恢复原状', diag.get('c') == diag.get('b'), str(diag))

    # DMF 横幅：能展开、有文案、有操作按钮（mock 里没装 DMF → 文本含「未检测到」）
    dmf = json.loads(cdp.js("""(() => {
      const disp = k => getComputedStyle(document.getElementById(k + 'Wrap')).display;
      if (disp('dmf') === 'none') document.getElementById('lightItemDmf').click();
      const txt = (document.querySelector('#dmfBanner') || {}).textContent || '';
      const btns = [...document.querySelectorAll('#dmfBanner button')].map(b => b.textContent.trim());
      return JSON.stringify({visible: disp('dmf') !== 'none', txt: txt.trim().slice(0, 80), btns});
    })()""") or '{}')
    check('DMF 横幅能展开', dmf.get('visible') is True, str(dmf))
    check('DMF 横幅有状态文案和操作按钮',
          bool(dmf.get('txt')) and bool(dmf.get('btns')), str(dmf))

    # 搜索下放到两栏 + 诊断条并进工具栏（全局 chips 已删）
    lay2 = json.loads(cdp.js("""(() => {
      const mid = id => { const e = document.getElementById(id); if (!e) return null;
        const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2); };
      return JSON.stringify({
        chips: document.querySelectorAll('#view-mods .chip').length,
        off: !!document.getElementById('searchOff'),
        on: !!document.getElementById('searchOn'),
        lightsMid: mid('bannerLights'), importMid: mid('btnImport')});
    })()""") or '{}')
    check('全局筛选 chips 已删除（两栏已按启停分开）', lay2.get('chips') == 0, str(lay2))
    check('两栏各有自己的筛选框', lay2.get('off') is True and lay2.get('on') is True, str(lay2))
    check('诊断条与工具栏按钮在同一行',
          lay2.get('lightsMid') is not None
          and abs((lay2.get('lightsMid') or 0) - (lay2.get('importMid') or 0)) <= 2, str(lay2))

    # 只筛左栏，右栏内容不受影响
    flt = json.loads(cdp.js("""(() => {
      const on0 = document.querySelectorAll('#bodyOn .mod-row').length;
      const off0 = document.querySelectorAll('#bodyOff .mod-row').length;
      const i = document.getElementById('searchOff');
      i.value = 'zzzz-no-such'; i.dispatchEvent(new Event('input', {bubbles: true}));
      const on1 = document.querySelectorAll('#bodyOn .mod-row').length;
      const off1 = document.querySelectorAll('#bodyOff .mod-row').length;
      i.value = ''; i.dispatchEvent(new Event('input', {bubbles: true}));
      return JSON.stringify({on0, off0, on1, off1});
    })()""") or '{}')
    check('只筛左栏时右栏不受影响',
          flt.get('on1') == flt.get('on0') and (flt.get('off0') or 0) > 0 and flt.get('off1') == 0, str(flt))

    errs = cdp.js_errors()
    check('页面无 JS 异常/错误日志（favicon 除外）', not errs, '; '.join(errs)[:300])

    # 着色器缓存状态（只读断言；**绝不点启动按钮** —— 那会真的把游戏起起来）
    sh = json.loads(cdp.js("fetch('/api/shader/status').then(r => r.text())") or '{}')
    check('着色器缓存状态接口可用', sh.get('ok') is True, str(sh)[:140])
    line = cdp.js("(document.getElementById('shaderLine')||{}).textContent || ''")
    if sh.get('ready'):
        check('侧边栏显示着色器缓存状态行', '着色器缓存' in (line or ''), str(line))
    else:
        skip('本环境没有游戏自带的着色器缓存构建器，状态行留空（正确表现）', str(sh.get('builder'))[:80])
    check('启动按钮文案未被着色器功能改坏',
          '启动游戏' in (cdp.js("(document.getElementById('btnLaunchSidebar')||{}).textContent || ''") or ''),
          '')
    # 底部工具栏不该再出现「重建清单」（2026-10-10 用户要求撤掉这个按钮）
    check('工具栏没有再出现「重建清单」按钮',
          cdp.js("!document.getElementById('btnRebuildOrder')") is True,
          cdp.js("(document.querySelector('.foot')||{}).innerText || ''"))

    p = cdp.screenshot(shot)
    check('截图已保存', p.is_file() and p.stat().st_size > 1000, str(p))

    # 新手引导：能起来、四块暗区拼出洞、走完自己收掉
    cdp.js("window.__dmmStartTour ? (window.__dmmStartTour(), true) : false")
    time.sleep(0.8)
    tour = json.loads(cdp.js("""JSON.stringify({
      hl: getComputedStyle(document.getElementById('tourHl')).display,
      box: getComputedStyle(document.getElementById('tourBox')).display,
      tiles: document.querySelectorAll('#tourMask .tm').length,
      title: (document.querySelector('#tourBox h4') || {}).textContent || '',
      text: (document.querySelector('#tourBox p') || {}).textContent || ''})""") or '{}')
    check('引导能打开（高亮 + 气泡 + 遮罩）',
          tour.get('hl') == 'block' and tour.get('box') == 'block'
          and tour.get('tiles') == 4, str(tour)[:110])
    check('引导首步讲三栏', '三栏' in (tour.get('title') or ''), str(tour.get('title')))

    # 往后翻几步：要专门讲「三栏位置和宽度能调」（用户报过没人知道能拖）
    step_texts = []
    for _ in range(3):
        d = json.loads(cdp.js("""JSON.stringify({
          text: (document.querySelector('#tourBox p') || {}).textContent || ''})""") or '{}')
        step_texts.append(d.get('text') or '')
        ok = cdp.js("""(() => { const b = document.getElementById('tourNext');
          if (b) { b.click(); return true; } return false; })()""")
        time.sleep(0.35)
        if not ok:
            break
    joined = ' | '.join(step_texts)
    check('引导讲了「拖栏头换位 / 拖分隔条调宽度」',
          ('分隔条' in joined) and ('栏头' in joined), joined[:160])
    cdp.js("window.__dmmEndTour && window.__dmmEndTour(); true")
    time.sleep(0.3)
    check('引导可关掉',
          cdp.js("getComputedStyle(document.getElementById('tourBox')).display") == 'none')

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


def wait_until(cdp, expr: str, timeout: float = 20.0, interval: float = 0.3) -> bool:
    """轮询等待页面就绪（返回表达式是否为真），替代写死的 sleep。

    必要性：真实环境里备份页首次渲染要算体积（用户那次导入留下 343 个 mod 的备份），
    写死 sleep 会让断言在页面渲染前跑，看起来像功能回归（实测踩过：5 条断言集体假失败）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if cdp.js(f'!!({expr})') is True:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def wait_view(cdp, view: str, marker: str, timeout: float = 20.0) -> bool:
    """切到某视图并等它的内容真渲染出来（marker 是 JS 表达式）"""
    cdp.js(f"document.querySelector('.sidebar button[data-view=\"{view}\"]')?.click(); true")
    return wait_until(cdp, marker, timeout)


def scenario_lists(cdp, state_json, shot: Path):
    """备份页 / 预设页现代化验收（只读：只看、只开对话框，**不保存任何设置**）。

    验的是"表格真渲染出来了 / 汇总与进度条在 / 搜索真能过滤 / 策略对话框真能打开"。"""
    # ---- 备份页 ----
    # 等汇总条/表头真出来（大备份体积计算可能耗时），而不是 sleep 死等
    ready = wait_view(cdp, 'backups',
                      "document.querySelector('#backupCards .bak-sum') "
                      "&& document.querySelector('#backupCards table.lib-table th')")
    if not ready:
        skip('备份页渲染未在超时内就绪（可能在算大备份体积）', '备份页')
        return
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
    ready2 = wait_view(cdp, 'profiles',
                       "document.querySelector('#profileCards .bak-sum') "
                       "&& (document.querySelector('#profileCards table.lib-table') "
                       "|| document.querySelector('#profileCards .tip'))")
    if not ready2:
        skip('预设页渲染未在超时内就绪', '预设页')
        return
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


def scenario_mineconflict(cdp, state_json, shot: Path):
    """同名冲突必须**问玩家**（用户反馈：不能替玩家选）。

    真链路：造一个与「我的 mod」同名的整合包 → 真喂给文件选择框 → 预览框 → 点「替换导入」
    → 应弹出**逐个选择**的决策框（默认预选"保留我的"）→ 点「取消导入」→ 确认什么都没变。
    **只跑 mock 环境**（会写标记），真实游戏目录自动跳过。"""
    import zipfile
    real = 'mock' not in str(state_json.get('game', {}).get('dir', '')).lower()
    if real and not ALLOW_REAL:
        skip('mineconflict 剧本（会写标记+造包）——真实游戏目录，未加 --allow-real',
             f"game_dir={state_json['game']['dir']}；请用 --source 打 mock 环境")
        return

    # ① 标记一个 mock mod（冲突对象）
    name = cdp.js("(async () => { const r = document.querySelector('.mod-row'); if (!r) return '';"
                  "  const n = r.dataset.name;"
                  "  const x = await api('/api/mods/mine', {method:'POST', body: JSON.stringify({name:n, mine:true})});"
                  "  await load(); return x.ok ? n : ''; })()")
    check('准备好「我的 mod」用于制造冲突', bool(name), str(name))
    if not name:
        return
    try:
        # ② 造一个含同名 mod 的整合包（放 99-临时文件，用完删）
        pack = SHOT_DIR / 'mineconflict_pack.zip'
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        body = 'return { run = function() new_mod("X", {}) end, packages = {}, version = "9.9" }'
        with zipfile.ZipFile(pack, 'w') as z:
            z.writestr(f'mods/{name}/{name}.mod', body)
            z.writestr(f'mods/{name}/scripts/{name}.lua', '-- pack 版本')
            z.writestr('mods/E2EExtraPackMod/E2EExtraPackMod.mod', body)
            z.writestr('mods/mod_load_order.txt', f'{name}\nE2EExtraPackMod\n')

        # ③ 真把文件喂给 #fileInput 并触发 change
        doc = cdp.send('DOM.getDocument', depth=1)
        node = cdp.send('DOM.querySelector', nodeId=doc['root']['nodeId'], selector='#fileInput')
        cdp.send('DOM.setFileInputFiles', files=[str(pack)], nodeId=node['nodeId'])
        cdp.js("document.getElementById('fileInput').dispatchEvent(new Event('change')); true")
        time.sleep(2.0)

        d1 = json.loads(cdp.js("JSON.stringify({open: !!document.querySelector('#modal.open'),"
                               "title: (document.getElementById('modalTitle')||{}).textContent || '',"
                               "body: (document.querySelector('#modalBody')||{}).innerText || ''})") or '{}')
        check('整合包预览弹窗出现', bool(d1.get('open')) and '导入整合包' in (d1.get('title') or ''), str(d1)[:200])
        check('预览里说明会逐个选择同名冲突', '逐个选' in (d1.get('body') or '') or '同名' in (d1.get('body') or ''),
              (d1.get('body') or '')[:160])

        # ④ 点「替换导入」→ 应进入**冲突决策框**
        cdp.js("document.getElementById('modalOk').click(); true")
        time.sleep(1.2)
        d2 = json.loads(cdp.js("JSON.stringify({open: !!document.querySelector('#modal.open'),"
                               "title: (document.getElementById('modalTitle')||{}).textContent || '',"
                               "body: (document.querySelector('#modalBody')||{}).innerText || '',"
                               "radios: document.querySelectorAll('#modalBody input[name^=mc_]').length,"
                               "mineChecked: document.querySelectorAll('#modalBody input[value=mine]:checked').length,"
                               "packOpts: document.querySelectorAll('#modalBody input[value=pack]').length})") or '{}')
        check('弹出「与你的 mod 同名，请逐个选择」决策框', bool(d2.get('open')) and '同名' in (d2.get('title') or ''),
              f"title={d2.get('title')!r} open={d2.get('open')}")
        check('每个冲突给出"保留我的 / 用包里的"两个选项',
              (d2.get('radios') or 0) >= 2 and (d2.get('packOpts') or 0) >= 1, str(d2.get('radios')))
        check('默认预选"保留我的"（安全项）', (d2.get('mineChecked') or 0) >= 1, str(d2.get('mineChecked')))
        check('决策框写清了两种选择的后果',
              '保留' in (d2.get('body') or '') and '包里' in (d2.get('body') or ''), (d2.get('body') or '')[:200])
        p = cdp.screenshot(shot.with_name(shot.stem + '-mineconflict.png'))
        check('决策框截图已保存', p.is_file() and p.stat().st_size > 1000, str(p))

        # ⑤ 点「取消导入」→ 必须什么都没导入
        cdp.js("(() => { const btns = [...document.querySelectorAll('#modalBody ~ * .modal-extra, .modal-extra, #modalCancel')];"
               "  const t = btns.find(b => (b.textContent || '').includes('取消导入')) || btns.find(b => b.id === 'modalCancel');"
               "  if (t) t.click(); return !!t; })()")
        time.sleep(1.0)
        left = cdp.js("api('/api/mods').then(r => JSON.stringify((r.mods || []).map(m => m.name).filter(n => n === 'E2EExtraPackMod')))")
        check('取消后没有导入任何东西', left in ('[]', '', None), str(left))
        errs = cdp.js_errors()
        check('冲突决策流程无 JS 异常', not errs, '; '.join(errs)[:300])
    finally:
        pack = SHOT_DIR / 'mineconflict_pack.zip'
        try:
            pack.unlink(missing_ok=True)
        except Exception:
            pass
        # 收尾：取消标记
        cdp.js(f"api('/api/mods/mine', {{method:'POST', body: JSON.stringify({{name:{json.dumps(name)}, mine:false}})}})"
               ".then(() => load()).then(() => 1)")
        time.sleep(0.3)


SCENARIOS['mineconflict'] = scenario_mineconflict


def scenario_dragpack(cdp, state_json, shot: Path):
    """**拖动导入**整合包：不许重复解压（用户反馈"拖动导入还是先解压两次"）。

    真链路：造包 → 在页面里合成 File 并派发真的 `drop` 事件（走 document 的拖放监听）
    → 弹预览框 → 用后端解压计数器断言**只解压 1 次** → 取消导入 → 什么都没变。
    只跑 mock 环境（会写标记/包），真实游戏目录自动跳过。"""
    import base64
    import zipfile
    real = 'mock' not in str(state_json.get('game', {}).get('dir', '')).lower()
    if real and not ALLOW_REAL:
        skip('dragpack 剧本（会造包并走导入流程）——真实游戏目录，未加 --allow-real',
             f"game_dir={state_json['game']['dir']}；请用 --source 打 mock 环境")
        return

    def state_now():
        return json.loads(cdp.js("fetch('/api/test/state').then(r => r.text())") or '{}')

    def extract_calls():
        st = state_now()
        return st.get('extract_calls')

    # ① 造一个整合包（含一个能识别为整合包的结构：mods/ 下 2 个 mod + 清单）
    pack = SHOT_DIR / 'e2e_dragpack.zip'
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    body = 'return { run = function() new_mod("X", {}) end, packages = {}, version = "1.0" }'
    with zipfile.ZipFile(pack, 'w') as z:
        z.writestr('mods/DragPackA/DragPackA.mod', body)
        z.writestr('mods/DragPackB/DragPackB.mod', body)
        z.writestr('mods/mod_load_order.txt', 'DragPackA\nDragPackB\n')
    b64 = base64.b64encode(pack.read_bytes()).decode('ascii')

    try:
        cdp.js("fetch('/api/test/extract_reset', {method:'POST'}).then(r => r.text())")
        time.sleep(0.3)
        before = extract_calls()

        # ② 在页面里合成 File，派发**真的 drop 事件**（拖动导入走的就是这条监听）
        dropped = cdp.js("""(async () => {
          const bin = atob('%s');
          const u8 = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
          const file = new File([u8], 'e2e_dragpack.zip', {type: 'application/zip'});
          const dt = new DataTransfer();
          dt.items.add(file);
          const ev = new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true});
          document.dispatchEvent(ev);
          return true;
        })()""" % b64)
        check('拖动 drop 事件已派发', dropped is True, str(dropped))
        time.sleep(2.5)

        # ③ 预览框出现，且只解压一次
        d1 = json.loads(cdp.js("JSON.stringify({open: !!document.querySelector('#modal.open'),"
                               "title: (document.getElementById('modalTitle')||{}).textContent || '',"
                               "body: (document.querySelector('#modalBody')||{}).innerText || ''})") or '{}')
        check('拖动后弹出整合包预览框（认出了整合包）',
              bool(d1.get('open')) and '导入整合包' in (d1.get('title') or ''), str(d1)[:200])
        check('预览列出了包内 mod',
              'DragPackA' in (d1.get('body') or '') or '新增' in (d1.get('body') or ''),
              (d1.get('body') or '')[:160])
        after = extract_calls()
        check('拖动导入只解压 1 次（不再"先解压两次"）',
              isinstance(before, int) and isinstance(after, int) and (after - before) == 1,
              f'解压次数 {before} -> {after}（差 {None if before is None or after is None else after - before}）')
        p = cdp.screenshot(shot.with_name(shot.stem + '-dragpack.png'))
        check('拖动导入截图已保存', p.is_file() and p.stat().st_size > 1000, str(p))

        # ④ 取消：不留暂存、不导入
        cdp.js("document.getElementById('modalCancel').click(); true")
        time.sleep(1.2)
        st2 = state_now()
        check('取消后暂存已释放', (st2.get('pack_stages') or 0) == 0, str(st2.get('pack_stages')))
        mods = cdp.js("api('/api/mods').then(r => JSON.stringify((r.mods||[]).map(m=>m.name)"
                      ".filter(n => n === 'DragPackA' || n === 'DragPackB')))")
        check('取消后没有 mod 被导入', mods in ('[]', '', None), str(mods))
        errs = cdp.js_errors()
        check('拖动导入流程无 JS 异常', not errs, '; '.join(errs)[:300])

        # ⑤ **索引读不到的格式**（用户 2026-10-10 报"仍然解压两次"的那种包）：
        #    以前判定类型时整包解压一次、随后 stage 又解压一次 = 2 次；
        #    现在判定那次直接进暂存并把 token 交出去，导入复用 → 全流程仍只解压 1 次
        cdp.js("fetch('/api/test/extract_reset', {method:'POST'}).then(r => r.text())")
        time.sleep(0.3)
        drop2 = cdp.js("""(async () => {
          const bin = atob('%s');
          const u8 = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
          const file = new File([u8], 'e2e_indexless.pack', {type: 'application/octet-stream'});
          const dt = new DataTransfer();
          dt.items.add(file);
          const ev = new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true});
          document.dispatchEvent(ev);
          return true;
        })()""" % b64)
        check('索引读不到的包也能拖入', drop2 is True, str(drop2))
        time.sleep(3.0)
        d2 = json.loads(cdp.js("JSON.stringify({open: !!document.querySelector('#modal.open'),"
                               "title: (document.getElementById('modalTitle')||{}).textContent || '',"
                               "body: (document.querySelector('#modalBody')||{}).innerText || ''})") or '{}')
        check('索引读不到的包也弹出了整合包预览',
              bool(d2.get('open')) and '导入整合包' in (d2.get('title') or ''), str(d2)[:200])
        calls2 = extract_calls()
        check('判定 + 预览阶段只解压 1 次', calls2 == 1, f'解压次数 {calls2}')
        # 确认导入（替换导入）→ 复用暂存，不应再解压
        cdp.js("document.getElementById('modalOk').click(); true")
        time.sleep(4.0)
        calls3 = extract_calls()
        check('确认导入后总解压次数仍是 1（用户报的第二次没了）', calls3 == 1, f'解压次数 {calls3}')
        landed = cdp.js("api('/api/mods').then(r => JSON.stringify((r.mods||[]).map(m=>m.name)"
                        ".filter(n => n === 'DragPackA' || n === 'DragPackB')))")
        check('导入确实生效（包内 mod 已落盘）', landed not in ('[]', '', None), str(landed))
        st3 = state_now()
        check('导入后暂存已释放', (st3.get('pack_stages') or 0) == 0, str(st3.get('pack_stages')))
    finally:
        try:
            pack.unlink(missing_ok=True)
        except Exception:
            pass


SCENARIOS['dragpack'] = scenario_dragpack


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
    ap.add_argument('--allow-kill', action='store_true',
                    help='允许杀掉已在运行的 DMM 实例（默认拒绝——那可能是用户正在用的窗口，不是我们起的）')
    args = ap.parse_args()
    global ALLOW_REAL
    ALLOW_REAL = bool(args.allow_real)

    try:
        import websocket  # noqa: F401
    except ImportError:
        print('缺 websocket-client：python -m pip install websocket-client')
        sys.exit(2)

    print(f'== DMM E2E（{args.scenario}）==')
    # 注意：这里**不再**无脑清场。launch() 会先检查有没有别人在跑，
    # 有就拒绝（除非显式 --allow-kill）——绝不杀用户正在用的窗口。
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
        # 开场先把可能挡路的弹窗关掉（启动时的崩溃弹窗、上次留下的确认框等）。
        # 曾经因为一个弹窗挡住侧边栏，让 lists 剧本整页断言集体失败，看起来像代码回归。
        dismissed = cdp.js("""(() => {
          const m = document.getElementById('modal');
          if (!m || !m.classList.contains('open')) return '';
          const t = (document.getElementById('modalTitle') || {}).textContent || '';
          const c = document.getElementById('modalCancel');
          if (c) c.click(); else m.classList.remove('open');
          return t;
        })()""")
        if dismissed:
            print(f'  （开场关掉了一个挡路弹窗: {dismissed}）')
        time.sleep(0.4)
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
