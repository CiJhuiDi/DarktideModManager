# -*- coding: utf-8 -*-
"""
DMF localization 汉化脚本 v2
基于官方 master 的 dmf.lua 结构，逐块重建：删除原 zh-cn（含多行拼接），
在 en 行后插入新汉化。整个文件重写，避免正则替换破坏结构。
"""
import re, shutil, os

SRC = r'D:\DeepseekWorkspace\dmf_official2\Darktide-Mod-Framework-master\dmf\localization\dmf.lua'
DST = r'D:\DeepseekWorkspace\darktide-mod-manager\dmf_payload\mods\dmf\localization\dmf.lua'

ZH = {
    "mods_options": "模组选项",
    "open_dmf_options": "打开选项菜单",
    "open_dmf_options_description": "打开或关闭模组选项菜单的按键绑定。",
    "dmf_options_scrolling_speed": "选项菜单滚动速度",
    "dmf_first_run_notification": "欢迎使用 Darktide Mod Framework。模组选项已添加到选项菜单中。",
    "percent": "%%",
    "toggle_mods": "开关模组",
    "toggle_mods_description": "启用或禁用你安装的模组。",
    "ui_scaling": "FHD+ 分辨率下的 UI 缩放",
    "ui_scaling_description": "当分辨率超过 1080p 时自动缩放 UI。",
    "developer_mode": "开发者模式",
    "developer_mode_description": "允许重新加载 DMF 和模组（CTRL+SHIFT+R），并解锁一些调试功能。",
    "show_developer_console": "显示开发者控制台",
    "show_developer_console_description": "打开一个新窗口，实时显示游戏日志。",
    "toggle_developer_console": "开关开发者控制台",
    "show_network_debug_info": "记录网络调用日志",
    "show_network_debug_info_description": "记录所有 DMF 网络调用及随之传输的数据。\n\n日志使用「info」级别记录。",
    "log_ui_renderers_info": "记录 UI 渲染器创建信息",
    "log_ui_renderers_info_description": "记录 UI 渲染器的创建者名称，以及作为参数传入的所有材质。\n\n日志使用「info」级别记录。",
    "logging_mode": "日志设置",
    "settings_default": "默认",
    "settings_custom": "自定义",
    "output_mode_notification": "'Notification' 通知输出",
    "output_mode_echo": "'Echo' 回显输出",
    "output_mode_error": "'Error' 错误输出",
    "output_mode_warning": "'Warning' 警告输出",
    "output_mode_info": "'Info' 信息输出",
    "output_mode_debug": "'Debug' 调试输出",
    "output_disabled": "禁用",
    "output_log": "日志",
    "output_chat": "聊天",
    "output_notification": "通知",
    "output_log_and_chat": "日志与聊天",
    "output_all": "全部",
    "output_log_and_notification": "日志与通知",
    "output_chat_and_notification": "聊天与通知",
    "chat_history_enable": "聊天输入历史",
    "chat_history_enable_description": "保存你在聊天窗口输入过的所有消息和命令。\n\n打开聊天后按「上箭头」和「下箭头」即可浏览输入历史。",
    "chat_history_save": "跨游戏会话保存输入历史",
    "chat_history_save_description": "即使重新加载游戏（或仅重载 DMF），你的聊天输入历史仍会被保存。",
    "chat_history_buffer_size": "输入历史缓冲区大小",
    "chat_history_buffer_size_description": "最多保存的记录条数。\n\n警告：更改此设置会清空你的聊天历史。",
    "chat_history_remove_dups": "删除重复记录",
    "chat_history_remove_dups_mode": "删除模式",
    "chat_history_remove_dups_mode_description": "选择要删除哪些重复记录。\n\n-- 仅上一条 --\n如果上一条与最新一条相同，则删除上一条。\n\n-- 全部 --\n如果记录与最新一条相同，则删除全部相同记录。",
    "settings_last": "仅上一条",
    "settings_all": "全部",
    "chat_history_commands_only": "仅保存已执行的命令",
    "chat_history_commands_only_description": "只有成功执行的命令才会被保存到聊天历史中。\n\n警告：更改此设置会清空你的聊天历史。",
    "chat_command_not_recognized": "无法识别的命令",
    "clean_chat_history": "清除聊天输入历史",
    "clean_chat_notifications": "清除聊天通知提醒",
    "dev_console_opened": "开发者控制台已打开。",
    "dev_console_closed": "开发者控制台已关闭。",
    "dev_console_close_warning": "开发者控制台已禁用，但必须手动关闭。",
    "mutator_no_description_provided": "未提供描述。",
    "lowest": "煽动",
    "low": "暴乱",
    "medium": "憎恶",
    "high": "异端",
    "highest": "诅咒",
    "broadcast_enabled_mutators": "已启用突变器",
    "broadcast_all_disabled": "所有突变器已禁用",
    "broadcast_disabled_mutators": "突变器已禁用",
    "local_disabled_mutators": "突变器已禁用",
    "whisper_enabled_mutators": "[自动消息] 本大厅启用了以下突变器",
    "disabled_reason_not_server": "因为你不再是主机",
    "disabled_reason_difficulty_change": "由于难度发生变化",
    "mutators_title": "突变器",
    "mutators_banner_description": "启用和禁用突变器",
    "no_mutators": "未安装突变器",
    "no_mutators_description": "在创意工坊订阅模组和突变器",
    "tooltip_incompatible_mutators": "\n\n-- 与突变器不兼容 --\n",
    "tooltip_compatible_mutators": "\n\n-- 仅兼容突变器 --\n",
    "tooltip_compatible_with_all_mutators": "\n\n-- 与所有突变器兼容 --",
    "tooltip_incompatible_with_all_mutators": "\n\n-- 与所有突变器不兼容 --",
    "tooltip_incompatible_diffs": "\n\n-- 与难度不兼容 --\n",
    "tooltip_compatible_diffs": "\n\n-- 仅兼容难度 --\n",
    "tooltip_compatible_with_all_diffs": "\n\n-- 与所有难度兼容 --",
    "tooltip_conflicts": "\n\n-- 冲突 --\n",
    "tooltip_append_mutator": "（突变器）",
    "tooltip_append_difficulty": "（难度）",
}

def lua_escape(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')

def zh_lua_lines(text):
    """返回 zh-cn 的 Lua 源码行列表。多行文本用 .. 拼接，格式与官方一致。"""
    if '\n' not in text:
        return [f'    ["zh-cn"] = "{lua_escape(text)}",']
    parts = text.split('\n')
    lines = []
    # 每段一行；除了最后一段，其余以 .. 结尾
    # 官方风格：第一段 "\n\n" .. 后续 "text"（换行转义放在前一段末尾）
    segs = []
    for i, p in enumerate(parts):
        esc = lua_escape(p)
        if i < len(parts) - 1:
            segs.append(f'"{esc}\\n"')
        else:
            segs.append(f'"{esc}"')
    # 拼接成多行：第一行缩进4，续行缩进8
    lines = [f'    ["zh-cn"] = {segs[0]}']
    for s in segs[1:]:
        lines.append(f'        {s}')
    # 在最后一段后加逗号
    lines[-1] = lines[-1] + ','
    # 除最后一行外每行加 ' ..'
    for i in range(len(lines) - 1):
        lines[i] = lines[i] + ' ..'
    return lines

txt = open(SRC, encoding='utf-8').read()
lines = txt.split('\n')

out = []
i = 0
in_block = False
block_key = None
block_start = None
block_lines = []
done = 0

def flush_block():
    global block_lines, block_key, done
    if block_key is None:
        return
    # 删除块内所有 zh-cn 相关行（含多行拼接）
    cleaned = []
    skip = False
    for l in block_lines:
        s = l.strip()
        if s.startswith('["zh-cn"]'):
            skip = True
            # 判断是否有多行拼接：行尾是 .. 则继续跳过下一行
            if not l.rstrip().endswith('..'):
                skip = False
            continue
        if skip:
            # 续行：以 " 开头且行尾 , 或 .. 结尾
            if l.rstrip().endswith('..'):
                continue  # 继续跳过
            else:
                skip = False
                continue  # 跳过最后一段
        cleaned.append(l)
    # 在 en 行（含其多行续行）之后插入新 zh-cn
    zh_lines = zh_lua_lines(ZH[block_key])
    insert_at = None
    for idx, l in enumerate(cleaned):
        if l.strip().startswith('en ='):
            insert_at = idx + 1
            # 跳过 en 的所有续行：从 en 下一行起，直到遇到下一个语言键（如 es/ru/ja/zh）
            j = idx + 1
            while j < len(cleaned):
                s = cleaned[j].strip()
                # 语言键行：es = / ru = / ja = / de = / ["zh-cn"] = 等
                if re.match(r'^(\w+ =|\["[a-z-]+"\] =)', s):
                    break
                j += 1
            insert_at = j
            break
    if insert_at is None:
        insert_at = len(cleaned) - 1  # 在 } 前
    result = cleaned[:insert_at] + zh_lines + cleaned[insert_at:]
    out.extend(result)
    block_lines = []
    block_key = None
    done += 1

for l in lines:
    if not in_block:
        out.append(l)
        m = re.match(r'^  (\w+) = \{', l)
        if m:
            in_block = True
            block_key = m.group(1)
            block_start = len(out) - 1
            block_lines = []  # 起始行已通过 out.append 输出，不再重复
    else:
        block_lines.append(l)
        if l.rstrip().endswith('},'):
            flush_block()
            in_block = False

if in_block:
    flush_block()

new_txt = '\n'.join(out) + '\n'

# 备份原内置文件（若已有备份则不重复）
bak = DST + '.bak_20260814'
if not os.path.exists(bak):
    shutil.copy2(DST, bak)
open(DST, 'w', encoding='utf-8', newline='\n').write(new_txt)

print(f'已重建并汉化 {done} 个条目')
print('输出文件:', DST)
