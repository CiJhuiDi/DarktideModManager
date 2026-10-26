# -*- coding: utf-8 -*-
"""着色器缓存功能：复刻原版启动器"启动前跑缓存构建器"这一步。

关键断言：
  · 参数与原版启动器一致（-i bundled / -o APPDATA 里那份 / -device-index 0）
  · 双发行版路径解析（Steam 与 Xbox/Game Pass）
  · 输出分类：校验通过 / 重建 / 失败 / 缺构建器 / 超时
  · **失败绝不影响启动**（prepare_for_launch 不抛；api_launch_game 照样起游戏）
"""
import io
import os
import shutil
import sys
import types
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import state          # noqa: E402
from core import crash          # noqa: E402
from core import shader         # noqa: E402
from core import patch          # noqa: E402

MOCK = ROOT / 'mock_shader'
FAILED = []


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f"  <- {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


class CP:
    """假 CompletedProcess"""

    def __init__(self, rc=0, out=b""):
        self.returncode = rc
        self.stdout = out
        self.stderr = b""


def make_env(appdata: Path, distro_dir: str = "Darktide"):
    """造一个假环境：游戏目录 + 构建器 + 输入缓存 + Fatshark 数据目录"""
    if MOCK.exists():
        state.safe_rmtree(MOCK, ignore_errors=True)
    game = MOCK / 'game'
    (game / 'shader_cache').mkdir(parents=True)
    (game / 'mods').mkdir(parents=True)          # is_valid_game_dir 要求 mods/ 或 bundle/ 存在
    (game / shader.SHADER_SUBDIR / shader.BUILDER_NAME).write_bytes(b"MZ fake builder")
    (game / shader.SHADER_SUBDIR / shader.BUNDLED_NAME).write_bytes(b"X" * 1024)
    data = appdata / "Fatshark" / distro_dir
    data.mkdir(parents=True, exist_ok=True)
    (data / "console_logs").mkdir(exist_ok=True)
    (data / "console_logs" / "console-x.log").write_text("x", encoding='utf-8')
    state.GAME_DIR = game
    os.environ["APPDATA"] = str(appdata)
    return game, data


print("===== 1. 路径解析（沿用崩溃日志那套双发行版逻辑）=====")
ap = MOCK / 'appdata_steam'
game, data = make_env(ap, "Darktide")
check("Steam：输出缓存落在 %APPDATA%\\Fatshark\\Darktide", shader.output_path() == data / shader.OUTPUT_NAME,
      str(shader.output_path()))
check("构建器路径正确", shader.builder_path() == game / 'shader_cache' / shader.BUILDER_NAME,
      str(shader.builder_path()))
st = shader.status()
check("状态里能看出可跑", st.get('ready') is True, str(st)[:120])
check("状态带发行版与缓存大小", st.get('distro') == 'steam' and st['bundled']['size'] == 1024,
      str({k: st[k] for k in ('distro',)}))
shutil.rmtree(MOCK, ignore_errors=True)

ap2 = MOCK / 'appdata_store'
game2, data2 = make_env(ap2, os.path.join("MicrosoftStore", "Darktide"))
check("Xbox/Game Pass：输出缓存落在 MicrosoftStore\\Darktide",
      shader.output_path() == data2 / shader.OUTPUT_NAME, str(shader.output_path()))
check("Xbox 发行版识别为 microsoft_store", shader.data_dir()[1] == crash.CRASH_DISTRO_STORE,
      shader.data_dir()[1])
shutil.rmtree(MOCK, ignore_errors=True)

print("\n===== 2. 调用参数必须与原版启动器一致 =====")
ap3 = MOCK / 'appdata3'
game3, data3 = make_env(ap3)
calls = []
# "缓存有效"的前提是输出文件本来就在（构建器只是校验它），先造出来
(data3 / shader.OUTPUT_NAME).write_bytes(b"Y" * 4096)


def runner(argv, cwd, timeout):
    calls.append({'argv': argv, 'cwd': cwd, 'timeout': timeout})
    return CP(0, b"[ShaderCacheBuilder] Data from Shader Cache Process: Cache is valid")


r = shader.build(runner=runner)
a = calls[0]['argv']
check("参数顺序与内容：-i 输入 -o 输出 -device-index 0",
      a[0] == str(game3 / 'shader_cache' / shader.BUILDER_NAME)
      and a[1] == '-i' and a[2] == str(game3 / 'shader_cache' / shader.BUNDLED_NAME)
      and a[3] == '-o' and a[4] == str(data3 / shader.OUTPUT_NAME)
      and a[5] == '-device-index' and a[6] == '0', str(a))
check("工作目录 = 构建器所在目录", calls[0]['cwd'] == str((game3 / 'shader_cache').resolve()),
      calls[0]['cwd'])
check("给了超时上限", calls[0]['timeout'] == shader.DEFAULT_TIMEOUT, str(calls[0]['timeout']))
check("『Cache is valid』→ 判为校验通过", r['ok'] and r['kind'] == 'valid', str(r)[:140])

print("\n===== 3. 三种结果分类 =====")
# 重建：输出里带压缩信息，且文件确实变了
out_file = data3 / shader.OUTPUT_NAME
out_file.write_bytes(b"Y" * 2048)


def runner_rebuild(argv, cwd, timeout):
    return CP(0, b"Choosing adapter: NVIDIA GeForce RTX 3060 Laptop GPU\n"
                 b"Validating Cache\nCompressing cache\n"
                 b"original size 132711922 new size 34083112\n")


r2 = shader.build(runner=runner_rebuild)
check("压缩输出 → 判为已重建", r2['ok'] and r2['kind'] == 'rebuilt', str(r2)[:160])
check("解析出显卡名", r2['adapter'] == 'NVIDIA GeForce RTX 3060 Laptop GPU', r2['adapter'])
check("解析出压缩前后字节数", r2['compressed'] == {'original': 132711922, 'new': 34083112},
      str(r2['compressed']))
check("记下耗时", isinstance(r2['seconds'], float), str(r2['seconds']))

r3 = shader.build(runner=lambda *a: CP(3, b"boom"))
check("非 0 退出码 → 判为失败且不抛", (not r3['ok']) and r3['kind'] == 'failed', str(r3)[:140])
check("失败信息里带退出码", '3' in (r3['error'] or ''), r3['error'])

r4 = shader.build(runner=lambda *a: CP(0, b""), out=MOCK / 'nonexistent' / 'x.hans')
check("没有产出文件 → 判为失败", (not r4['ok']) and '没有产出' in (r4['error'] or ''), str(r4)[:140])

print("\n===== 4. 缺构建器 / 缺输入 / 超时：都不抛异常 =====")
r5 = shader.build(builder=MOCK / 'no-such-builder.exe')
check("缺构建器 → no_builder，不抛", r5['kind'] == 'no_builder', str(r5)[:120])
r6 = shader.build(bundled=MOCK / 'no-such-bundled.hans')
check("缺输入缓存 → no_input，不抛", r6['kind'] == 'no_input', str(r6)[:120])


def runner_timeout(argv, cwd, timeout):
    raise shader.subprocess.TimeoutExpired(cmd=argv, timeout=timeout)


r7 = shader.build(runner=runner_timeout)
check("超时 → kind=timeout，不抛", r7['kind'] == 'timeout', str(r7)[:120])


def runner_boom(argv, cwd, timeout):
    raise OSError("文件被占用")


check("任意异常 → failed，不抛", shader.build(runner=runner_boom)['kind'] == 'failed')

print("\n===== 5. prepare_for_launch 绝不阻断启动 =====")
p1 = shader.prepare_for_launch()
check("prepare_for_launch 返回字典且不抛", isinstance(p1, dict) and 'kind' in p1, str(p1)[:120])
orig_build = shader.build
shader.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("炸了"))
try:
    p2 = shader.prepare_for_launch()
    check("build 抛异常时 prepare 仍返回", isinstance(p2, dict) and p2.get('ok') is False, str(p2)[:120])
finally:
    shader.build = orig_build

print("\n===== 6. 启动接口：着色器步骤失败也要照常起游戏 =====")
# 造一个可执行文件占位 + 拦掉 Steam 检查与 Popen
fake_exe = game3 / 'binaries' / 'Darktide.exe'
fake_exe.parent.mkdir(parents=True, exist_ok=True)
fake_exe.write_bytes(b"MZ")
launched = {}
orig_pop, orig_run, orig_running = crash.subprocess.Popen, crash.subprocess.run, patch.is_game_running
orig_prep = shader.prepare_for_launch
orig_auto = patch.auto_patch_if_needed
crash.subprocess.Popen = lambda argv, **kw: (launched.update({'argv': argv, 'kw': kw}) or types.SimpleNamespace(pid=4321))
crash.subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="steam.exe", stderr="")
patch.is_game_running = lambda *a, **k: False
patch.auto_patch_if_needed = lambda *a, **k: None
try:
    shader.prepare_for_launch = lambda: {'ok': False, 'kind': 'failed', 'error': '故意失败', 'seconds': 0.0}
    res = crash.api_launch_game()
    check("着色器步骤失败时游戏仍被启动", res.get('ok') is True and launched.get('argv'), str(res)[:140])
    check("返回里带上着色器结果供界面提示", 'shader' in res and res['shader'].get('kind') == 'failed',
          str(res.get('shader')))
    shader.prepare_for_launch = lambda: {'ok': True, 'kind': 'valid', 'seconds': 2.1, 'out_size': 34083112}
    res2 = crash.api_launch_game()
    check("着色器成功时消息里说明用了多久", '2.1' in (res2.get('message') or ''), res2.get('message'))
    shader.prepare_for_launch = lambda: (_ for _ in ()).throw(RuntimeError("崩了"))
    res3 = crash.api_launch_game()
    check("着色器步骤抛异常时也不阻断启动", res3.get('ok') is True, str(res3)[:140])
finally:
    crash.subprocess.Popen, crash.subprocess.run = orig_pop, orig_run
    patch.is_game_running = orig_running
    shader.prepare_for_launch = orig_prep
    patch.auto_patch_if_needed = orig_auto

print("\n===== 7. 界面文案 =====")
check("校验通过的说法不含括号堆叠", shader.summary_text({'ok': True, 'kind': 'valid', 'seconds': 2.1})
      == '着色器缓存已校验，用时 2.1 秒', shader.summary_text({'ok': True, 'kind': 'valid', 'seconds': 2.1}))
check("重建的说法", shader.summary_text({'ok': True, 'kind': 'rebuilt', 'seconds': 13.6})
      == '着色器缓存已重建，用时 13.6 秒', shader.summary_text({'ok': True, 'kind': 'rebuilt', 'seconds': 13.6}))
check("失败时给一句跳过说明", '跳过' in shader.summary_text({'ok': False, 'kind': 'failed'}),
      shader.summary_text({'ok': False, 'kind': 'failed'}))

state.safe_rmtree(MOCK, ignore_errors=True)
print("\n===== 结果 =====")
if FAILED:
    print(f"失败 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过 通过")
