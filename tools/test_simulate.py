# -*- coding: utf-8 -*-
"""模拟环境端到端测试：开关模拟 -> is_game_running 生效 -> 防呆拦截"""
import sys, json, asyncio
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
from core import state

ROOT = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = ROOT / 'mock'
state.GAME_DIR = MOCK
state.MODS_DIR = MOCK / 'mods'
state.CONFIG_FILE = MOCK / 'config_sim_test.json'
state.BACKUP_DIR = MOCK / 'backups_sim_test'
app._run_patch = lambda action: {"ok": True, "patched": True, "output": "mock"}
# 清掉可能的模拟残留
if state.CONFIG_FILE.exists():
    state.CONFIG_FILE.unlink()

print('=== 模拟环境测试 ===')

# 1. 初始：无模拟 -> is_game_running 应为 False（真实环境无 Darktide）
state.CONFIG_FILE.unlink(missing_ok=True)
print(f'1. 初始未模拟: is_game_running={app.is_game_running()} (期望 False)')
assert app.is_game_running() is False

# 2. 开启模拟
r = app.api_simulate_game(app.SimulateGameBody(running=True))
print(f'2. 开启模拟: ok={r.get("ok")}, running={r.get("running")}')
assert r.get('ok') and r.get('running')
print(f'   is_game_running={app.is_game_running()} (期望 True)')
assert app.is_game_running() is True

# 3. 模拟运行中 -> 防呆拦截
r = asyncio.run(app.api_import_mods(files=[]))
print(f'3. 模拟运行时导入 mod 被拦: {r.get("error")}')
assert not r.get('ok') and '游戏正在运行' in r.get('error', '')
r = app.api_toggle('TestModA')
print(f'   toggle 被拦: {r.get("error")}')
assert not r.get('ok')

# 4. status 接口暴露模拟标记
import json as _json
# 直接构造 status 检查
st = app.api_status()
print(f'4. status.game_running={st["game_running"]}, simulated={st.get("simulated_game_running")}')
assert st['game_running'] is True and st['simulated_game_running'] is True

# 5. 关闭模拟
r = app.api_simulate_game(app.SimulateGameBody(running=False))
print(f'5. 关闭模拟: ok={r.get("ok")}, is_game_running={app.is_game_running()} (期望 False)')
assert r.get('ok') and app.is_game_running() is False

# 6. 模拟关闭后操作恢复
r = app.api_toggle('TestModA')
print(f'6. 停止模拟后 toggle 恢复: ok={r.get("ok")}')
assert r.get('ok')

# 清理
state.CONFIG_FILE.unlink(missing_ok=True)
import shutil
shutil.rmtree(state.BACKUP_DIR, ignore_errors=True)
print('\n===== 模拟环境测试全部通过 =====')
