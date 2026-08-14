# -*- coding: utf-8 -*-
"""构建 test_api 需要的 mock 假游戏目录"""
import os, json
from pathlib import Path

BASE = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
MOCK = BASE / 'mock'
MODS = MOCK / 'mods'

# 重建
import shutil
if MOCK.exists():
    shutil.rmtree(MOCK)
MODS.mkdir(parents=True)

MOD_BODY = 'return { run = function() new_mod("%s", {}) end, packages = {}, version = "%s" }'

# TestModA v1.2.0
d = MODS / 'TestModA'
d.mkdir()
(d / 'TestModA.mod').write_text(MOD_BODY % ('TestModA', '1.2.0'), encoding='utf-8')
(d / 'scripts').mkdir()
(d / 'scripts' / 'x.lua').write_text('-- a', encoding='utf-8')

# TestModB v0.5
d = MODS / 'TestModB'
d.mkdir()
(d / 'TestModB.mod').write_text(MOD_BODY % ('TestModB', '0.5'), encoding='utf-8')

# TestModC 无版本
d = MODS / 'TestModC'
d.mkdir()
(d / 'TestModC.mod').write_text(MOD_BODY % ('TestModC', ''), encoding='utf-8')

# DisabledMod（清单里禁用）
d = MODS / 'DisabledMod'
d.mkdir()
(d / 'DisabledMod.mod').write_text(MOD_BODY % ('DisabledMod', '1.0'), encoding='utf-8')

# base 系统组件（应被排除）
d = MODS / 'base'
d.mkdir()
(d / 'mod_manager.lua').write_text('-- base loader', encoding='utf-8')

# 加载清单
load_order = [
    '-- 测试注释行',
    '--disabled_by_comment',
    'TestModA',
    'TestModB',
    'TestModC',
    '--DisabledMod',
    '--GhostMod',
]
(MODS / 'mod_load_order.txt').write_text('\n'.join(load_order) + '\n', encoding='utf-8')

# config 指向 mock
cfg = {"game_dir": str(MOCK)}
(BASE / 'config.json').write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')

print('mock 构建完成:', MODS)
for p in sorted(MODS.iterdir()):
    print(' ', p.name)
