# -*- coding: utf-8 -*-
"""exe 冒烟测试：起 exe → 从 app.log 解析端口 → 验证 GET / 与 /api/status → 关闭。
用法: python tools/smoke_test.py [exe路径]
默认: release/DarktideModManager_alpha/DarktideModManager.exe
注意: 会短暂弹出应用窗口（几秒后自动关闭）。
"""
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXE = os.path.join(ROOT, 'release', 'DarktideModManager_alpha', 'DarktideModManager.exe')


def find_port_from_log(exe_dir, timeout=30):
    """读 exe 旁 app.log 的 Uvicorn 端口（取最新一条）"""
    log = os.path.join(exe_dir, 'app.log')
    for _ in range(timeout * 2):
        try:
            with open(log, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            matches = re.findall(r'Uvicorn running on http://127\.0\.0\.1:(\d+)', content)
            if matches:
                return int(matches[-1])
        except Exception:
            pass
        time.sleep(0.5)
    return None


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXE
    if not os.path.isfile(exe):
        print('exe 不存在:', exe)
        sys.exit(1)
    exe_dir = os.path.dirname(exe)
    print('冒烟测试:', exe)

    subprocess.run(['taskkill', '/F', '/IM', 'DarktideModManager.exe'], capture_output=True)
    time.sleep(1)

    proc = subprocess.Popen([exe], cwd=exe_dir)
    try:
        port = find_port_from_log(exe_dir)
        if port is None:
            print('FAIL 未在 app.log 找到服务端口（exe 可能启动失败）')
            sys.exit(1)
        print('  服务端口:', port)

        base = 'http://127.0.0.1:%d' % port
        page_ok = False
        has_title = False
        # 服务启动有间隙（日志先于监听就绪），GET / 失败时重试几次再判失败
        for attempt in range(5):
            try:
                r = urllib.request.urlopen(base + '/', timeout=5)
                page_ok = r.status == 200
                body = r.read().decode('utf-8', errors='ignore')
                has_title = '暗潮 Mod 管理器' in body or 'mods' in body.lower()
                print('  GET /:', r.status, '| 页面含内容:', has_title)
                break
            except Exception as e:
                if attempt < 4:
                    time.sleep(1)
                    continue
                print('  GET / 失败:', e)
                page_ok = False

        try:
            import json
            st = json.load(urllib.request.urlopen(base + '/api/status', timeout=5))
            status_ok = st.get('ok') is None or st.get('game_dir_valid') is not None or 'theme' in st
            print('  /api/status ok:', status_ok, '| theme:', st.get('theme'), '| game_dir_valid:', st.get('game_dir_valid'))
        except Exception as e:
            print('  /api/status 失败:', e)
            status_ok = False

        if page_ok and status_ok:
            print('冒烟通过')
            code = 0
        else:
            print('冒烟失败')
            code = 1
    finally:
        subprocess.run(['taskkill', '/F', '/IM', 'DarktideModManager.exe'], capture_output=True)
    sys.exit(code)


if __name__ == '__main__':
    main()
