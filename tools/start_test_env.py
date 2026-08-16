# -*- coding: utf-8 -*-
"""一键测试环境：清僵尸进程 → 确认端口清空 → 重建 mock → 起服务（前台阻塞）。

用法:
  python tools/start_test_env.py             # 完整流程（默认端口 8317）
  python tools/start_test_env.py --skip-build  # 已有干净 mock 时跳过重建
  python tools/start_test_env.py --port 9000   # 自定义端口

说明:
  - 自动杀掉 DarktideModManager.exe 和命令行含 app.py 的 python 进程
    （僵尸进程抢 8317 端口是测试假失败的头号原因，RULES 踩坑备忘）
  - 服务以前台方式运行，Ctrl+C 退出时自动终止；下次再跑本脚本会先清残留
  - 不误杀无关 python 进程（只按命令行 app.py 过滤）
"""
import argparse
import subprocess
import sys
import time
import urllib.request
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kill_stale():
    """杀掉 DarktideModManager.exe + 命令行含 app.py 的 python 进程，返回被杀列表"""
    killed = []
    r = subprocess.run(['taskkill', '/F', '/IM', 'DarktideModManager.exe'],
                       capture_output=True, text=True)
    if r.returncode == 0:
        killed.append('DarktideModManager.exe')
    ps = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -match 'app\\.py' } | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True)
    for pid in ps.stdout.split():
        pid = pid.strip()
        if pid:
            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
            killed.append('python(pid=%s)' % pid)
    return killed


def port_owner(port):
    """返回占用端口的 PID，端口空闲返回 None"""
    r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if (':%d' % port) in line and 'LISTENING' in line:
            return line.split()[-1]
    return None


def wait_ready(port, timeout=30):
    """轮询 /api/status 直到服务就绪"""
    for _ in range(timeout):
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=1)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    # 管道/后台运行时也按行输出（否则进度 print 被缓冲看不到）
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description='一键测试环境：清进程 -> 建 mock -> 起服务')
    ap.add_argument('--port', type=int, default=8317)
    ap.add_argument('--skip-build', action='store_true', help='跳过 build_mock')
    args = ap.parse_args()

    # 1. 清僵尸进程
    killed = kill_stale()
    if killed:
        print('[1/4] 已清理残留进程: %s' % ', '.join(killed))
    else:
        print('[1/4] 无残留进程')

    # 2. 确认端口
    time.sleep(1)
    pid = port_owner(args.port)
    if pid:
        print('[2/4] 端口 %d 仍被 PID %s 占用，强杀…' % (args.port, pid))
        subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
        time.sleep(1)
        if port_owner(args.port):
            print('  端口仍被占用，请手动检查（可能有顽固进程）')
            sys.exit(1)
    print('[2/4] 端口 %d 已清空' % args.port)

    # 3. 重建 mock
    if not args.skip_build:
        print('[3/4] 重建 mock…')
        r = subprocess.run([sys.executable, 'tools/build_mock.py'], cwd=ROOT)
        if r.returncode != 0:
            print('  build_mock 失败，中止')
            sys.exit(1)
    else:
        print('[3/4] 跳过 build_mock (--skip-build)')

    # 4. 起服务（前台阻塞，Ctrl+C 停止）
    print('[4/4] 启动服务 http://127.0.0.1:%d … （Ctrl+C 停止）' % args.port)
    proc = subprocess.Popen([sys.executable, 'app.py', '--port', str(args.port)], cwd=ROOT)
    try:
        if wait_ready(args.port):
            print('  服务就绪，可以跑测试了（test_api / test_import / tools/test_*.py）')
        else:
            print('  服务未在 30s 内就绪，请查看 app.log')
        proc.wait()
    except KeyboardInterrupt:
        print('\n停止服务…')
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == '__main__':
    main()
