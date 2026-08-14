# -*- coding: utf-8 -*-
"""
构建演示验收环境（demo/）：
- 生成示例 mod（假数据，只含基本信息供读取展示）
- 覆盖场景：中文显示名 / 版本 / 依赖关系 / 顺序扩展 / 缺失 / 禁用
- 初始化 config.json 指向 demo 游戏目录
- 幂等：可反复运行
"""
import json, shutil, re
from pathlib import Path

BASE = Path(r'D:\DeepseekWorkspace\darktide-mod-manager')
DEMO = BASE / 'demo'
GAME = DEMO / 'game'
MODS = GAME / 'mods'

# 清除重建
if DEMO.exists():
    shutil.rmtree(DEMO)
MODS.mkdir(parents=True)

# ---------- 系统组件（DMF 框架，真实文件从 dmf_payload 拷） ----------
payload = BASE / 'dmf_payload'
# 完整拷贝：mods/base + mods/dmf + binaries + tools
for sub in ('mods/base', 'mods/dmf', 'binaries', 'tools'):
    src = payload / sub
    if src.is_dir():
        dst = GAME / sub
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
# bundle 目录（patch_999 由 dtkit 打补丁生成，这里先建空目录）
bundle = GAME / 'bundle'
bundle.mkdir(parents=True, exist_ok=True)

# ---------- 示例 mod 生成 ----------
def make_mod(folder, name, version='1.0.0', packages=None, display_name=None):
    """生成一个假 mod：.mod 文件 + localization（中文名）+ 一个脚本文件"""
    d = MODS / folder
    d.mkdir(parents=True, exist_ok=True)
    pkgs = ', '.join(f'"{p}"' for p in (packages or []))
    pkg_line = f'packages = {{{pkgs}}}, ' if pkgs else 'packages = {}, '
    (d / f'{folder}.mod').write_text(
        f'return {{ run = function() new_mod("{name}", {{}}) end, {pkg_line}version = "{version}" }}',
        encoding='utf-8')
    scripts = d / 'scripts' / 'mods' / folder
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / f'{folder}.lua').write_text('-- demo mod (fake data)\n', encoding='utf-8')
    # 中文显示名（localization lua 文件，格式: mod_name = { ["zh-cn"] = "..." }）
    if display_name:
        loc = d / 'localization'
        loc.mkdir(exist_ok=True)
        (loc / f'{folder}_localization.lua').write_text(
            'return {\n  mod_name = {\n    ["zh-cn"] = "' + display_name + '",\n  },\n}\n',
            encoding='utf-8')
    return d

# ---------- 场景设计 ----------

# 1. 正常 mod（中文显示名）
make_mod('AutoLoot', 'AutoLoot', '2.1.0', display_name='自动拾取')
make_mod('BetterBots', 'BetterBots', '1.4.2', display_name='智能队友AI')
make_mod('NumericUI', 'NumericUI', '0.9.5', display_name='数值UI')

# 2. 依赖关系场景
# 本体库（名字避免包含关系，防止顺序启发式误报）
make_mod('sb_core', 'sb_core', '1.0.0')
make_mod('ui_core', 'ui_core', '2.0.0')
# 依赖正常（依赖 sb_core + ui_core）
make_mod('Scoreboard', 'Scoreboard', '1.2.0', packages=['sb_core', 'ui_core'], display_name='计分板')
# 缺依赖（依赖 lib_missing 不存在）
make_mod('MissingDep', 'MissingDep', '1.0.0', packages=['lib_missing'], display_name='缺失依赖示例')
# 循环依赖
make_mod('CycleA', 'CycleA', '1.0.0', packages=['cycleb'])
make_mod('CycleB', 'CycleB', '1.0.0', packages=['cyclea'])

# 3. 顺序扩展场景（本体在前，扩展在后）
make_mod('ScoreboardDamage', 'ScoreboardDamage', '1.1.0', display_name='计分板-伤害统计')
make_mod('ScoreboardAbility', 'ScoreboardAbility', '1.0.3', display_name='计分板-技能统计')

# 4. 版本差异场景（演示差异对比用）
make_mod('OldMod', 'OldMod', '0.5.0', display_name='旧版mod')

# 5. 禁用的 mod（清单里 -- 注释）
make_mod('DisabledMod', 'DisabledMod', '1.0.0', display_name='已禁用示例')

# 6. 无版本号 mod
make_mod('NoVersion', 'NoVersion', '', display_name='无版本示例')

# ---------- 启停清单 ----------
load_order = [
    'sb_core',
    'ui_core',
    'Scoreboard',
    'ScoreboardDamage',
    'ScoreboardAbility',
    'AutoLoot',
    'BetterBots',
    'NumericUI',
    'MissingDep',
    'CycleA',
    'CycleB',
    'NoVersion',
    '--DisabledMod',
]
(MODS / 'mod_load_order.txt').write_text('\n'.join(load_order) + '\n', encoding='utf-8')

# ---------- config.json ----------
(DEMO / 'config.json').write_text(
    json.dumps({'game_dir': str(GAME)}, ensure_ascii=False, indent=2),
    encoding='utf-8')

print(f'✅ 演示环境已构建: {DEMO}')
print(f'   mods 数量: {len([d for d in MODS.iterdir() if d.is_dir()])}')
print(f'   清单: {len(load_order)} 行')
print('   场景覆盖: 中文名 / 依赖正常 / 缺依赖 / 循环依赖 / 顺序扩展 / 版本差异 / 禁用 / 无版本')
