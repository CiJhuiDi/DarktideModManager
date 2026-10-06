# -*- coding: utf-8 -*-
"""构建「换包保留我的启用 mod」demo 环境
产物：
  demo_keep/game/          = 当前游戏目录（含启用 mod + 私有 MyPriv v2.1 + base 框架文件）
  demo_keep/新整合包_纯净.zip   = 场景1：不含 MyPriv（验证自动补回）
  demo_keep/新整合包_冲突.zip   = 场景2：MyPriv v3.0（验证冲突弹窗）
用法：把 demo_keep/game 设为 DMM 游戏目录（关于页选择文件夹），导入两个 zip 各测一次
"""
import io, os, shutil, sys, zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'demo_keep'
GAME = OUT / 'game'

# 重建
if OUT.exists():
    shutil.rmtree(OUT)
(GAME / 'mods').mkdir(parents=True)
(GAME / 'binaries').mkdir(parents=True)
(GAME / 'bundle').mkdir(parents=True)

MOD_BODY = 'return { run = function() new_mod("%s", {}) end, packages = {}, version = "%s" }'


def write_mod(name, ver):
    d = GAME / 'mods' / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{name}.mod').write_text(MOD_BODY % (name, ver), encoding='utf-8')
    (d / 'scripts').mkdir(exist_ok=True)
    (d / 'scripts' / f'{name}.lua').write_text(f'-- {name} v{ver} (demo)', encoding='utf-8')


# 当前环境：整合包常见 mod + 我的私有 MyPriv
for n, v in [('ScoreboardFix', '1.0'), ('BetterHud', '2.3'), ('AutoLoot', '1.1'), ('MyPriv', '2.1')]:
    write_mod(n, v)
# base 框架（系统组件，demo 简化版）
b = GAME / 'mods' / 'base'
b.mkdir(exist_ok=True)
(b / 'mod_manager.lua').write_text('-- base', encoding='utf-8')
# 清单（MyPriv 启用 = 我的私有）
(GAME / 'mods' / 'mod_load_order.txt').write_text(
    'ScoreboardFix\nBetterHud\nAutoLoot\nMyPriv\n', encoding='utf-8')
# 补丁相关（避免导入报错“未找到 dtkit-patch”只属提示，不影响演示）
(GAME / 'bundle' / 'bundle_database.data').write_bytes(b'FAKE')

# base/dmf 组件在新包里也带（简化：只带 base）
def pack_zip(name, mods: dict, lo: list):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for mn, mv in mods.items():
            z.writestr(f'mods/{mn}/{mn}.mod', MOD_BODY % (mn, mv))
            z.writestr(f'mods/{mn}/scripts/{mn}.lua', f'-- {mn}')
        z.writestr('mods/mod_load_order.txt', '\n'.join(lo) + '\n')
        z.writestr('mods/base/mod_manager.lua', '-- base')
        z.writestr('bundle/bundle_database.data', b'FAKE')
    p = OUT / name
    p.write_bytes(buf.getvalue())
    print('生成:', p, f'({p.stat().st_size/1024:.1f} KB)')


# 场景1：新整合包不含 MyPriv → 自动补回
pack_zip('场景1_纯净新包.zip',
         {'ScoreboardFix': '1.0', 'BetterHud': '2.3', 'AutoLoot': '1.1', 'NewMod': '0.8'},
         ['ScoreboardFix', 'BetterHud', 'AutoLoot', 'NewMod'])
# 场景2：新整合包 MyPriv v3.0 → 版本冲突弹窗
pack_zip('场景2_冲突新包.zip',
         {'ScoreboardFix': '1.0', 'BetterHud': '2.3', 'AutoLoot': '1.1', 'MyPriv': '3.0'},
         ['ScoreboardFix', 'BetterHud', 'AutoLoot', 'MyPriv'])

print('\n=== demo 环境就绪 ===')
print('游戏目录: ', GAME)
print('当前启用: ScoreboardFix, BetterHud, AutoLoot, MyPriv(v2.1 私有)')
print('\n测试步骤：')
print('1. DMM 关于页 → 游戏目录选', GAME)
print('2. 导入 场景1_纯净新包.zip → 提示「已保留 1 个 mod 文件(MyPriv)，未自动启用」')
print('   MyPriv 文件在 mods/ 里但不在清单（作者清单全权），列表里手动开启它')
print('3. 重置后再导入 场景2_冲突新包.zip → 应弹版本冲突框（MyPriv 2.1 vs 3.0）')
print('   选「全部用新包」= 保持 3.0；选「补回我的版本」= 恢复 2.1（文件级）')
