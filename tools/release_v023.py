# -*- coding: utf-8 -*-
"""创建 v0.2.3 GitHub Release 并上传 zip"""
import subprocess, os

def gh(args):
    r = subprocess.run(['gh'] + args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r

# 获取 token 并设置环境
tok = subprocess.run(
    ['git', 'credential', 'fill'],
    input='protocol=https\nhost=github.com\n',
    capture_output=True, text=True
).stdout
for line in tok.splitlines():
    if line.startswith('password='):
        os.environ['GH_TOKEN'] = line[len('password='):]
        break

body = """## v0.2.3（2026-08-14）

**修复：内置 DMF 组件混入引流广告（因偷懒产生的荒诞错误）**

- 修复：内置组件当初偷懒直接取用整合包，结果把作者植入的引流广告（B站 ID、QQ 群号等私货）一并带进来了——DMF 选项页 mod 名竟显示为别人的广告。现已全部清除，mod 名改为「暗潮模组框架」
- `mods/dmf/` 换为 Darktide Mod Framework 官方 master 原版；`localization/dmf.lua` 为本项目自译汉化（82 条目，无广告、无第三方署名）
- `mods/base/` 换为 Darktide Mod Loader 官方 master 原版（重载快捷键恢复官方 R 键）
- 修复：关于页「🌐 GitHub」按钮点击无反应（事件绑定时机错误，按钮动态生成后未绑定监听）

### 功能
- 一键安装 DMF 框架（加载器 + 中文汉化 + dtkit-patch + 自动装载）
- 整合包一键导入（替换/合并双模式），换包不堆积，旧包自动归档可找回
- Mod 中文显示名、启停/排序/搜索、方案预设
- 右键菜单：打开文件夹 / 复制名 / 备注 / 删除（回收站）/ 清理残留
- 一键启动游戏、补丁自动管理、归档备份恢复页

### 使用
解压后双击 DarktideModManager.exe，首次按顶部提示「一键安装 DMF」，再「导入整合包」即可。
详见包内《使用指南.txt》。
"""

# 创建 release
r = gh(['release', 'create', 'v0.2.3', '-R', 'CiJhuiDi/DarktideModManager',
        '--title', 'v0.2.3 内测版', '--notes', body])
print('create:', r.stdout.strip() or r.stderr.strip()[:300])

# 上传 zip
r = gh(['release', 'upload', 'v0.2.3', r'D:\DeepseekWorkspace\darktide-mod-manager\release\DarktideModManager_v0.2.3.zip',
        '-R', 'CiJhuiDi/DarktideModManager', '--clobber'])
print('upload:', r.stdout.strip() or r.stderr.strip()[:300])

# 查看结果
r = gh(['release', 'view', 'v0.2.3', '-R', 'CiJhuiDi/DarktideModManager'])
print('---')
print(r.stdout)
