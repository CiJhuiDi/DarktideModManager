# -*- coding: utf-8 -*-
"""
构建演示验收环境（demo/）：
- 生成示例 mod（假数据，只含基本信息供读取展示）
- 覆盖场景：中文显示名 / 版本 / 依赖关系 / 顺序扩展 / 缺失 / 禁用
- 初始化 config.json 指向 demo 游戏目录
- 幂等：可反复运行
"""
import json, shutil, re
from datetime import datetime
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
def make_mod(folder, name, version='1.0.0', packages=None, display_name=None, description=None):
    """生成一个假 mod（进游戏不报错）：标准 DMF 结构 .mod + localization + script"""
    d = MODS / folder
    d.mkdir(parents=True, exist_ok=True)
    pkgs = ', '.join(f'"{p}"' for p in (packages or []))
    pkg_line = f'packages = {{{pkgs}}}, ' if pkgs else 'packages = {}, '
    # 标准 .mod：带 mod_script/mod_data/mod_localization 指向实际文件
    mod_body = (
        'return {\n'
        '  run = function()\n'
        f'    new_mod("{name}", {{\n'
        f'      mod_script       = "{folder}/scripts/mods/{folder}/{folder}",\n'
        f'      mod_data         = "{folder}/scripts/mods/{folder}/{folder}_data",\n'
        f'      mod_localization = "{folder}/scripts/mods/{folder}/{folder}_localization",\n'
        '    })\n'
        '  end,\n'
        f'  {pkg_line}version = "{version}"\n'
        '}\n'
    )
    (d / f'{folder}.mod').write_text(mod_body, encoding='utf-8')
    scripts = d / 'scripts' / 'mods' / folder
    scripts.mkdir(parents=True, exist_ok=True)
    # script/data/localization 三个 lua（空实现，加载不报错）
    (scripts / f'{folder}.lua').write_text(
        f'-- demo mod: {name} (fake data, no real function)\nreturn {{}}\n', encoding='utf-8')
    (scripts / f'{folder}_data.lua').write_text('return {}\n', encoding='utf-8')
    (scripts / f'{folder}_localization.lua').write_text('return {}\n', encoding='utf-8')
    # 中文显示名 + 悬停描述（额外 localization 文件，格式: mod_name/mod_description = { ["zh-cn"] = "..." }）
    if display_name or description:
        loc = d / 'localization'
        loc.mkdir(exist_ok=True)
        lines = ['return {']
        if display_name:
            lines.append('  mod_name = {')
            lines.append(f'    ["zh-cn"] = "{display_name}",')
            lines.append('  },')
        if description:
            lines.append('  mod_description = {')
            lines.append(f'    ["zh-cn"] = "{description}",')
            lines.append('  },')
        lines.append('}\n')
        (loc / f'{folder}_localization.lua').write_text('\n'.join(lines), encoding='utf-8')
    return d

# ---------- 场景设计 ----------

# 1. 正常 mod（中文显示名 + 悬停描述）
make_mod('AutoLoot', 'AutoLoot', '2.1.0', display_name='自动拾取',
         description='自动拾取地面战利品：弹药、医疗包、手雷等，可配置拾取范围与优先级过滤。')
make_mod('BetterBots', 'BetterBots', '1.4.2', display_name='智能队友AI',
         description='增强队友 AI：更聪明的走位、集火目标、救援与协作行为。')
make_mod('NumericUI', 'NumericUI', '0.9.5', display_name='数值UI',
         description='在 HUD 显示精确数值：生命、韧性、弹药、闪避充能等。')

# 2. 依赖关系场景
# 本体库（名字避免包含关系，防止顺序启发式误报）
make_mod('sb_core', 'sb_core', '1.0.0', description='计分板核心库：提供统计数据接口供计分板系列 mod 调用。')
make_mod('ui_core', 'ui_core', '2.0.0', description='UI 核心库：统一 HUD 元素布局与主题适配。')
# 依赖正常（依赖 sb_core + ui_core）
make_mod('Scoreboard', 'Scoreboard', '1.2.0', packages=['sb_core', 'ui_core'], display_name='计分板',
         description='任务结束后显示详细战绩统计：击杀、伤害、爆头率、救人与倒地等。')
# 缺依赖（依赖 lib_missing 不存在）
make_mod('MissingDep', 'MissingDep', '1.0.0', packages=['lib_missing'], display_name='缺失依赖示例',
         description='演示缺依赖场景：依赖的 lib_missing 未安装，列表会显示红色缺依赖徽标。')
# 循环依赖
make_mod('CycleA', 'CycleA', '1.0.0', packages=['cycleb'], description='演示循环依赖场景 A：与 CycleB 互相依赖，列表显示循环徽标。')
make_mod('CycleB', 'CycleB', '1.0.0', packages=['cyclea'], description='演示循环依赖场景 B：与 CycleA 互相依赖，列表显示循环徽标。')

# 3. 顺序扩展场景（本体在前，扩展在后）
make_mod('ScoreboardDamage', 'ScoreboardDamage', '1.1.0', display_name='计分板-伤害统计',
         description='计分板插件：展示伤害输出细分（近战/远程/手雷/灵能）。')
make_mod('ScoreboardAbility', 'ScoreboardAbility', '1.0.3', display_name='计分板-技能统计',
         description='计分板插件：展示技能使用次数与命中率。')

# 4. 版本差异场景（演示差异对比用）
make_mod('OldMod', 'OldMod', '0.5.0', display_name='旧版mod',
         description='旧版本示例：导入整合包时用于演示「更新」差异行。')

# 5. 禁用的 mod（清单里 -- 注释）
make_mod('DisabledMod', 'DisabledMod', '1.0.0', display_name='已禁用示例',
         description='已禁用 mod 示例：清单中以 -- 注释，默认灰显不加载。')

# 6. 无版本号 mod
make_mod('NoVersion', 'NoVersion', '', display_name='无版本示例',
         description='无版本号示例：副标题不显示版本，兼容旧格式 mod。')

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

# ---------- 演示预设（三组玩法场景，选自丁香整合包精选 mod） ----------
PROFILES = DEMO / 'profiles'
PROFILES.mkdir(exist_ok=True)

_DEMO_PRESETS = [
    # (文件名, 显示名, mods 清单（框架在前→本体→插件扩展）)
    ('qol', 'QOL · 生活统计', [
        'Power_DI',                 # 数据统计框架（底层）
        'scoreboard',               # 计分板本体：任务结束显示各种统计数据
        'ScoreboardDamage',         # 计分板插件：伤害统计
        'ScoreboardAbilityUsage',   # 计分板插件：技能使用
        'ScoreboardAbilityCounter', # 计分板插件：技能次数
        'ScoreboardExplosive',      # 计分板插件：爆炸伤害
        'ovenproof_scoreboard_plugin',  # OvenProof 自定义记分板
        'uptime',                   # 增益持续时间追踪 + 历史记录
        'CombatStats',              # 战斗统计
        'TeamKills',                # 击杀/连杀统计板
        'kill_tracker',             # HUD 击杀连杀追踪
        'JishuJun',                 # 计数菌（计数统计）
        'true_level',               # 真实等级显示
        'NumericUI',                # 数显界面（血韧闪避弹药数值）
        'minimap',                  # 小地图
        'objective_tracker',        # 任务目标追踪器
        'DamageNumbers',            # 伤害数字
        'show_crit_chance',         # 显示暴击率
        'AccurateCurioNames',       # 饰品名称实际效果
        'ItemSorting',              # 物品排序
        'HazardTimers',             # 危险区域计时
        'GlowCooldown',             # 技能冷却发光
        'OublietteTimer',           # 法庭密牢电梯倒计时
        'Clock',                    # 时钟
        'Mark9',                    # 罗马数字转阿拉伯数字
        'SmoothTide',               # 动态画质调节器（性能）
        'TertiumFixes',             # 特提恩修复（客户端修复合集）
        'StoryReplay',              # 剧情重放
        'ManyMoreTry',              # 再来很多局
    ]),
    ('ob', 'OB · 观赛模式', [
        'AlwaysOutline',            # 敌人轮廓线（核心）
        'GasOutline',               # 毒气中轮廓线修复
        'TraumaOutlines',           # 显示地板杖爆炸范围
        'PlayerOutlines',           # 玩家轮廓线
        'Hound Zero',               # 高亮猎犬引爆范围
        'TargetHunter',             # 精英/首领 HUD 世界标记
        'Spidey Sense',             # 蜘蛛感应（敌人攻击预警）
        'Redshift',                 # 狙击手来袭方向警告
        'Metal Gear Plasma',        # 等离子炮手袭击警告
        'SpecialsTracker',          # 专家追踪器（特殊敌人生成/死亡通知）
        'SpawnFeed',                # 敌人生成通知
        'RitualZones',              # 仪式区（浩劫恶魔宿主仪式计时）
        'danger_zone',              # 危险区域范围显示（火/爆炸）
        'NoCorpses',                # 敌人阵亡立即清除尸体
        'clear_smoke',              # 清除烟雾
        'DisableScreenEffects',     # 禁用屏幕特效
        'FXlimiter',                # 特效限制器
        'vfx_swapper',              # 视觉特效替换器
        'soulblaze_vfx_toggle',     # 灵能火焰特效开关
        'LessDoT',                  # 隐藏异常状态特效
        'NoRottenArmorSFX',         # 去除腐化装甲音效
        'CleanForceBlocking',       # 移除力场剑格挡特效
    ]),
    ('casual', '轻松游戏 · 自动辅助', [
        'AutoLoot',                 # 自动拾取（核心）
        'FullAuto',                 # 全自动开火（核心）
        'AutoSwing',                # 自动连按轻击重击
        'KeepSwinging',             # 自动重复轻攻击
        'UngaBunga',                # 自动近战蓄力攻击
        'AutoPing',                 # 自动标记（带过滤与优先目标）
        'AutoBlitz',                # 自动释放闪击
        'AutoQuell33',              # 灵能者自动散热
        'AutoMedicaeServoSkull',    # 自动医疗伺服头骨
        'BrokerAutoStim',           # 自动注射兴奋剂
        'StickyFingers',            # 自动交互
        'StickySprint',             # 粘滞疾跑
        'helbore_passive_charge',   # 卢修斯自动充能
        'ZealotThrowingKnife',      # 狂信徒自动投掷飞刀
        'RearGuard',                # 脑后有眼（自动格挡背后偷袭）
        'ChatBlock',                # 打开聊天/切窗口自动格挡
        'guarantee_ability_activation',  # 保证技能激活
        'guarantee_special_action',      # 保证特殊动作
        'Skitarius',                # 战斗序列（连招编辑器）
        'NoBrainer',                # 自动化解谜小游戏
        'AutoBruntRoller',          # 自动军备库刷武器
        'CurioHunter',              # 饰品猎手（自动购买/提醒）
        'StimmsPickupIcon',         # 兴奋剂拾取图标
        'whats_in_the_box',         # 兴奋剂箱里装着什么
        'FoundYa',                  # 发现物品（交互图标可视/标记距离）
        'HolyLight',                # 高亮拾取物和箱子
        'Auto-9 Assistive Reticule',# 机械战警目标扫描锁定框
    ]),
]

for fname, disp, mods in _DEMO_PRESETS:
    data = {'name': disp, 'mods': mods, 'created': datetime.now().isoformat(timespec='seconds')}
    (PROFILES / f'{fname}.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

print(f'[OK] 演示环境已构建: {DEMO}')
print(f'   mods 数量: {len([d for d in MODS.iterdir() if d.is_dir()])}')
print(f'   清单: {len(load_order)} 行')
print(f'   预设: {len(_DEMO_PRESETS)} 组（QOL 生活统计 / OB 观赛模式 / 轻松游戏 自动辅助）')
print('   场景覆盖: 中文名 / 依赖正常 / 缺依赖 / 循环依赖 / 顺序扩展 / 版本差异 / 禁用 / 无版本')
