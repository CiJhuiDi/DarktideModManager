# -*- coding: utf-8 -*-
"""自定义主题端到端测试：上传/读图/移除/非法格式"""
import sys, io, json, urllib.request, urllib.error, os, tempfile
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
from pathlib import Path

sys.path.insert(0, r'D:\DeepseekWorkspace\darktide-mod-manager')
import app
import theme
import state

MOCK = Path(r'D:\DeepseekWorkspace\darktide-mod-manager\mock')
state.CONFIG_FILE = MOCK / 'config_custom_test.json'
theme.CUSTOM_THEME_DIR = MOCK / 'custom_theme_test'
if state.CONFIG_FILE.exists():
    state.CONFIG_FILE.unlink()
import shutil
shutil.rmtree(theme.CUSTOM_THEME_DIR, ignore_errors=True)

# 1x1 红色 PNG
PNG_1PX = bytes.fromhex(
    '89504e470d0a1a0a0000000d494844520000000100000001080600000'
    '01f15c4890000000d4944415478da63fcffff3f030005fe02fea72e'
    'd4940000000049454e44ae426082'
)

checks = []
def test(name, cond, detail=''):
    checks.append((name, cond))
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f'  <- {detail}' if detail else ''))

import asyncio

async def main():
    # 上传（mode=light）
    from starlette.datastructures import UploadFile, Headers
    uf = UploadFile(filename='bg.png', file=io.BytesIO(PNG_1PX), headers=Headers({'content-type': 'image/png'}))
    r = await theme.api_theme_custom_upload(mode='light', file=uf)
    test('上传 ok', r.get('ok'), r)
    img = theme.custom_theme_img()
    test('图片已存', img is not None and img.exists(), img)
    test('扩展名 png', img.suffix == '.png' if img else False, img)
    cfg = json.loads(state.CONFIG_FILE.read_text(encoding='utf-8'))
    test('theme=custom', cfg.get('theme') == 'custom', cfg)
    test('mode=light', cfg.get('custom_theme_mode') == 'light', cfg)

    # state
    st = theme.custom_theme_state()
    test('state exists', st['exists'])
    test('state mode', st['mode'] == 'light', st)

    # 非法格式
    uf2 = UploadFile(filename='bg.txt', file=io.BytesIO(b'hello'), headers=Headers({'content-type': 'text/plain'}))
    r2 = await theme.api_theme_custom_upload(mode='dark', file=uf2)
    test('非法格式拒绝', not r2.get('ok'), r2)

    # 非法 mode
    uf3 = UploadFile(filename='bg.jpg', file=io.BytesIO(PNG_1PX), headers=Headers({'content-type': 'image/jpeg'}))
    r3 = await theme.api_theme_custom_upload(mode='neon', file=uf3)
    test('非法 mode 拒绝', not r3.get('ok'), r3)

    # 覆盖上传（jpg → 应保留唯一 bg.*）
    uf4 = UploadFile(filename='bg.jpg', file=io.BytesIO(PNG_1PX), headers=Headers({'content-type': 'image/jpeg'}))
    r4 = await theme.api_theme_custom_upload(mode='dark', file=uf4)
    test('覆盖上传 ok', r4.get('ok'), r4)
    files = list(theme.CUSTOM_THEME_DIR.glob('bg.*'))
    test('只有一张图', len(files) == 1, files)
    test('新图为 jpg', files[0].suffix == '.jpg' if files else False, files)

    # 移除
    r5 = theme.api_theme_custom_remove()
    test('移除 ok', r5.get('ok') and r5.get('removed'), r5)
    test('图已删', theme.custom_theme_img() is None)
    cfg2 = json.loads(state.CONFIG_FILE.read_text(encoding='utf-8'))
    test('theme 回退 abyss', cfg2.get('theme') == 'abyss', cfg2)
    test('mode 已清', 'custom_theme_mode' not in cfg2, cfg2)

    state.CONFIG_FILE.unlink(missing_ok=True)
    shutil.rmtree(theme.CUSTOM_THEME_DIR, ignore_errors=True)
    failed = [n for n, ok in checks if not ok]
    print(f"\n===== {len(checks)-len(failed)}/{len(checks)} 通过 =====")
    if failed:
        print('失败:', failed)
        raise SystemExit(1)
    print('全部通过 通过')

asyncio.run(main())
