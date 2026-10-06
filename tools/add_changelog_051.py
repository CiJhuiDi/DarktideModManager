# -*- coding: utf-8 -*-
"""CHANGELOG 插入 v0.5.1 条目（2026-09-02）"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "CHANGELOG.md"
t = p.read_text(encoding='utf-8')

entry = """## v0.5.1（2026-09-02）
**内置组件更新**
- 内置 DMF 组件更新至官方 master（2026-08-19 提交）：新增颜色选择器（color picker）、选项筛选器、数值输入、文本/文本输入控件、tab 指示器等 UI 组件；选项菜单支持滚动位置记忆、mod 加载顺序字段、mod 版本/作者日志、设置重置事件、鼠标按键映射重构等
- 汉化合并完善：以官方全量 93 keys 为基础，保留自译精翻 25 处，补全旧版缺失的 8 处 tooltip 翻译（突变器/难度兼容提示），新增 key（重新加载模组、显示选项 ID、置顶/取消置顶等）汉化齐全
- 同步游戏内已装 DMF（mods/dmf 42 → 58 文件，备份 dmf.bak_20260902_0235）

"""
assert '## v0.5.0' in t, '找不到 v0.5.0 锚点'
t = t.replace('## v0.5.0', entry + '## v0.5.0', 1)
p.write_text(t, encoding='utf-8')
print('CHANGELOG v0.5.1 条目已插入')
print(t[:800])
