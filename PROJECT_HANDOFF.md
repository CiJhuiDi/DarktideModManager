# DMM 暗潮 MOD 管理器 · 项目交接摘要

> **给新会话的快速上手文档**：读完这个 + RULES.md（工作条例）+ CHANGELOG.md 即可接手。
> 最后更新：2026-08-18 01:05（补充暗潮 Mod 生态交接段；DMM 本体 v0.4.1）

---

## 一、项目是什么

《战锤40K：暗潮》的 Mod 管理器（pywebview 桌面应用，Python FastAPI 后端 + 原生 JS 前端）。
只做"壳"：管理 mod 启停/顺序/预设/整合包导入，内置 DMF 框架组件，不碰游戏本体。

- **代码位置**：`D:\DeepseekWorkspace\darktide-mod-manager\`
- **当前版本**：v0.4.1（正式版基线，2026-08-17 发布）；工作区当前为**正式态 v0.4.1**，下次内部测试构建前用 `tools/set_alpha_state.py` 切回 Alpha 态（RULES 第 9 条：不带版本号、不打 zip；build_release 发布时自动恢复）
- **测试形态**：Alpha 测试版（`release\DarktideModManager_alpha\`，界面只标 Alpha、不带版本号、不打 zip）；
  正式发布时再 bump 版本 + CHANGELOG 定版 + 打 zip（RULES 第 9 条）
- **GitHub**：https://github.com/CiJhuiDi/DarktideModManager（CiJhuiDi）
- **游戏目录**：用户在真实 Steam 库（D:\SteamLibrary 下能找到，335 mod 大整合包环境）

## 二、核心文件结构

```
app.py               # 入口：FastAPI 路由装配 + mod 管理 API + main（~1050 行）
core/                # 业务模块包（拆分自原 app.py 2400+ 行）
  state.py           #   全局状态/路径常量/游戏目录（⚠️ BASE_DIR = __file__ 的 parent.parent）
  load_order.py      #   清单读写 + set_load_order
  patch.py           #   补丁/守卫/自动装载
  mods.py            #   mod 扫描/显示名/依赖
  imports.py         #   导入/整合包/备份/导出（最大块）
  dmf.py             #   DMF 安装
  crash.py           #   游戏启动/崩溃检测/控制台日志（APIRouter）
  theme.py           #   主题/自定义背景（APIRouter）
  profiles.py        #   方案预设（APIRouter）
static/index.html    # 前端（单文件，原生 JS + SortableJS）
dmf_payload/         # 内置 DMF 组件（官方原版 + 自译汉化）
tools/               # 发布/测试脚本（见下）
test_*.py            # 主测试（根目录）
CHANGELOG.md         # 更新历史（与用户共同维护，以用户手改为准）
RULES.md             # ← 工作条例在 workspace，不在项目里！
```

> 架构拆分（方案 C）已完成：**业务模块已归入 `core/` 包**（state/load_order/patch/mods/imports/dmf/crash/theme/profiles），
> app.py（~1050 行）为入口（路由装配 + mod 管理 API + main）。
> ⚠️ core/state.py 的 BASE_DIR 用 `__file__` 的 parent.parent 定位项目根（core/ 在子目录，
>    不能用 parent——曾导致 config 找不到、数据写到 core/ 的坑）；frozen 模式用 sys.executable 不受影响。
> ⚠️ 测试脚本约定：直接 import app 的测试用 state.XXX = 覆盖全局（不是 app.XXX，值拷贝陷阱）；
>     guard 相关测试需同时覆盖 patch.is_game_running；模块内调用 patch 函数用 patch.xxx() 属性访问；
>     主题相关测试覆盖 theme.CUSTOM_THEME_DIR（模块级常量）；已统一 stdout reconfigure 防 GBK。
> ⚠️ test_pack 的 SAMPLE 留空前置 check 无条件失败是已知历史 bug，可忽略。

## 三、当前功能全景（v0.3.1）

**核心**：一键安装 DMF / 覆盖更新 DMF（force）/ 整合包导入（替换+合并）/ 归档备份找回

**主题系统（v0.3.1 新增）**：
- 7 套主题（abyss 默认深色/dawn 浅色/pleasure 紫/plague 绿/rage 红/mystic 蓝/emperor 金），下拉切换 + config 持久化
- 静态渐变背景（--grad-c1/2/3 三段色）+ 面板微透明毛玻璃（backdrop-filter）；4 种渐变方向（diag/hori/vert/radial，body[data-grad]）
- 🎲 立即随机 + 「每次启动时随机主题」复选框（theme=random 持久化，启动时服务端随机展开不固化）
- 🖼 自定义主题：上传图片（jpg/png/webp/bmp ≤8MB）存 exe 旁 custom_theme/bg.*，暗/亮模式（data-custom-mode）
- 启动零闪烁：后端 GET / 把主题内联进 <body data-theme data-grad>，首帧即正确主题
- 浅色适配：--active-bg/--chosen-bg 等 10+ 硬编码色改为主题变量；关于页布局自适应（卡片全宽、按钮 nowrap）
- API：POST /api/theme（theme+grad）、POST/GET /api/theme/custom(+image/remove)；status 返回 theme/grad/custom_theme

**崩溃检测与控制台日志（工作区未提交，待发布）**：
- 游戏退出后崩溃检测：NTSTATUS 异常退出码（0xC0000005 等）+ crash_dumps 新文件双信号 → 弹窗引导排查
- 崩溃弹窗显示最新控制台日志文件名；「查看控制台日志」打开 console_logs（%APPDATA%\Fatshark\Darktide\console_logs，文本日志）
- 关于页固定按钮「📂 打开控制台日志文件夹」（事件委托 #btnOpenCrashLogs → POST /api/crash_logs/open，优先打开 console_logs）
- API：/api/crash_logs（返回 console + latest）、/api/crash_logs/open、/api/game/launched_exit
- 游戏目录「🔍 自动识别」（detect_game_dir 扫 Steam 库）+ 保存即时生效（apply_game_dir 热更新全局变量，无需重启）
- 搜索框一键清空按钮、showModal 支持 hideActions（崩溃弹窗只用 extra 按钮）、模拟崩溃按钮（测试用）

**日志分析（实验模式，侧边栏动态标签）**：
- 触发：关于页「🔬 实验：日志预览」/ 崩溃弹窗「查看控制台日志」/ 拖拽 .log 文件进窗口（全局拖放，游戏运行中也允许）
- 多标签（最新日志常驻 + 导入旧日志新标签，✕ 独立关闭，全关自动隐藏标签回 mods）
- 三分类过滤（错误/警告/通常按钮互斥）+ 关键词搜索；行色：错误红/警告黄
- 右键菜单：复制选中文本/复制此行/复制选中行；多选模式（点击/拖动批量选、实时预览、反色高亮、提示条）
- 崩溃报告导出：console log + crash_dumps + report_info.json（exports/crash_report_*.zip）
- API：/api/crash_logs/read（尾部+分类）、/api/crash_logs/analyze（导入分析）、/api/crash_logs/export

**横幅显示控制**：
- 按钮伪下拉 + 复选框单独控制三横幅（DMF/补丁/依赖）；一键收起/展开全部（#bannerToggleAll）
- 收起→指示灯行「名称 ●」带 │ 分隔；自动收起正常（绿灯）横幅、自动展开异常（红/橙）横幅（bannerLastColor 状态变化检测）
- 依赖横幅点击：flashDepMod() 逐个跳转闪光问题 mod（missing.mod / cycles / order_hints.ext）

**mod 悬停详细描述**：
- core/mods.py：_read_locale 解析 localization 的 mod_name + mod_description（优先 zh-cn/en，缓存复用）
- 前端 .mod-tip 浮层：显示名/原名/版本/描述/备注/依赖/缺失警告（350ms 延迟，防溢出）

**Mod 管理**：启停/排序/搜索/中文显示名/右键菜单/方案预设/**批量操作（右键多选模式）**
- ⚠️ **清单格式（2026-08-17 变更）**：停用 = 从 mod_load_order.txt 移除（不再写 `--ModName` 注释行），清单只含启用中的 mod 与说明注释；旧式禁用标记在保存/导入时自动清理。代价：停用再启用排到末尾、顺序不保留。改启停相关逻辑先看 core/load_order.py（normalize_entries 丢弃精确禁用行、set_load_order 不生成禁用行）+ app.py 的 api_toggle/api_mods_batch（幂等：enable 追加、disable 移除）。

**导入导出**：
- 「＋ 导入」一个入口 → 自动识别：单 mod / 整合包 / 清单 txt / **文件夹**（pywebview 原生目录选择）
- 整合包识别三态：mod / pack / ambiguous（单 mod 包裹弹窗确认）
- 「📤 导出」三模式：全部 / 按启用 / 仅导出清单（干净 mod_load_order.txt）

**依赖检查**（/api/deps/check）：
- 缺依赖 🔴（packages 短名，过滤 content/wwise 资源路径）
- 循环依赖 🔄
- 顺序建议 📌（mod 名包含关系启发式，本体→扩展）

**差异对比**（/api/pack/preview、/api/backups/{id}/preview、/api/load_order/preview）：
- 导入整合包前 / 恢复备份前 / 恢复清单前 / 应用预设前 → 结构化彩色行预览

**防呆**：游戏运行中 9 个写 API 守卫 + 前端按钮变灰 + **模拟游戏运行**（关于页开关）
- ⚠️ **前端运行状态锁的坑（2026-08-17）**：mod 列表 checkbox 的禁用态在 render() 时写死，轮询（pollStatus 每 10s）更新 gameRunning 后若不重渲染列表，checkbox 永远保持禁用 → 游戏关闭后启动按钮恢复但启停开关仍灰锁。修法：updateEditLocks() 直接同步 `.switch input` 的 disabled + locked class（不依赖重渲染）；拖拽用 Sortable onMove 返回 !gameRunning 拦截。改前端列表类锁定先查这里。

## 四、开发/发布流程（重要！）

**每次开工前**：读 `C:\Users\123\.openclaw\workspace\RULES.md`（工作条例）

**改代码流程**：
1. 改完先跑测试 → 再打包（**改完必构建**，用户明确要求）
2. 测试顺序：`python tools\build_mock.py` 重建 mock → 起服务 `python app.py --port 8317 --browser` → 跑 test_api/test_import/test_formats + tools/test_*.py（14 套件）
3. **测试环境防坑**：先 taskkill 清掉残留 python/exe 进程（僵尸进程抢端口会导致假失败），再跑测试
4. 构建：`python -m PyInstaller --noconfirm --clean --onefile --windowed --name DarktideModManager --icon app.ico --version-file version_info.txt --add-data "static;static" --add-data "dmf_payload;dmf_payload" --collect-all webview app.py`
5. 同步：dist exe → release\DarktideModManager_vX.Y.Z\ → 重打 zip

**发布流程**：
1. `python tools\bump_version.py <新版本>`（版本号全局升级，通用版支持跨 minor）
2. CHANGELOG.md 更新（新功能未定版本先入「待定」条目，定版归入版本段——**以用户手改为准**）
3. 全量测试 → 构建 → 同步 release
4. git add/commit/push + tag
5. `python tools\release.py vX.Y.Z`（从 CHANGELOG 取正文 + 传 zip）
6. **Release 标题格式**：`vX.Y.Z Beta`（不加「版」字）

**仓库上传铁律**：更新后**不要急着 push**，等用户明确说"上传/推送"再动手。

## 五、开源合规（2026-08-16 核实 + 补全）

- **主程序**：MIT（LICENSE 文件，Copyright 2026 DMM contributors）
- **内置组件**（均已核实上游仓库）：DMF=MIT；dtkit-patch=**MIT OR Apache-2.0 双许可**（本项目按 MIT 再分发）；dt-mod-autopatch=MIT
- **xsSplater/Darktide_laucher_bypass（GPL-3.0）仅致谢未分发** → 无 GPL 义务；README 致谢已改指具体仓库并注明
- `THIRD_PARTY_LICENSES.md`（仓库根）列全部组件来源/协议/版权行 + MIT 全文；README 许可证段已更新
- ⚠️ **发新版本打 zip 时必带 `LICENSE` + `THIRD_PARTY_LICENSES.md`**（v0.3.1 zip 已补上这两个文件）

## 六、发布脚本工具链（tools/）

| 脚本 | 用途 |
|---|---|
| `bump_version.py <ver>` | 版本号全局升级（通用版） |
| `release.py <tag>` | 创建/更新 GitHub Release + 传 zip（通用版） |
| `sync_release_notes.py <tag>` | 按 CHANGELOG 同步 Release 说明 |
| `build_mock.py` | 重建测试用 mock 假游戏目录 |
| `start_test_env.py` | 一键测试环境：杀僵尸进程（exe+python）→ 清端口 → 重建 mock → 起服务（前台阻塞，Ctrl+C 停；--skip-build 跳过重建） |
| `test_full.py` | **全量测试一键**：清环境 → tools 套件（17）→ 重建 mock+起服务+HTTP 套件（3）→ 独立目录套件（3，自动清 backups 残留、识别 test_pack SAMPLE 已知 bug 跳过） |
| `smoke_test.py [exe]` | **exe 冒烟测试**：起 exe → 从 app.log 解析端口 → 验证 GET / + /api/status → 自动关闭（会弹窗几秒） |
| `build_alpha.py` | **alpha 构建一键**：检查版本显示（必须 Alpha 态）→ PyInstaller → 同步 release/DarktideModManager_alpha/（不打 zip；--skip-build/--check） |
| `release_pack.py <ver>` | **正式发布打包**：同步 release/DarktideModManager_vX.Y.Z/ + 打 zip（前置：bump 版本 + 构建 exe） |
| `build_release.py <ver>` | **正式发布一键**：恢复版本显示（Alpha→旧版）→ bump → CHANGELOG 定版 → 测试 → 构建 → 打包（--check 只查前置 / --skip-tests） |
| `hanhua_dmf.py` | 重写 DMF localization（自译汉化） |
| test_*.py（11 个） | 专项测试：batch/classify/deps/order_hint/export/preview/backup_preview/load_order/load_order_backup/load_order_preview/folder_import/guard/simulate/dmf_force |

## 七、GitHub 凭据（重要！）

- **gh CLI 未登录**（设备码流程在代理下失败），用 `GH_TOKEN` 环境变量
- 发布脚本自动从 git credential 取 token：`git credential fill` → 设 GH_TOKEN → 调 gh
- **gh 不读 git 代理配置**：跑 gh 前需 `HTTPS_PROXY/HTTP_PROXY=http://127.0.0.1:7890`
- token 在 GCM 里（2026-08-14 换的新令牌，365 天有效）

## 八、踩坑速查（详细见 RULES.md）

- **僵尸进程**：22 个 python/exe 抢 8317 端口 → 测试假失败，先 taskkill
- **装饰器错位**：辅助函数别插到 @app.get 和目标函数之间（备份 422 的根因）
- **秒级时间戳覆盖**：backup_load_order 和 restore 同秒会覆盖目标文件，先读内容再备份
- **DMF packages 两类**：短名=库依赖，含 / 的 content/wwise=资源路径（要过滤）
- **PowerShell 转义地狱**：复杂逻辑写 .py 脚本跑，别内联 python -c
- **pywebview import 名是 webview**，不是 pywebview

## 九、用户偏好速记

- 中文交流，结论先行，报告简短
- 确认框文案精简（后果+补救，不列使用情景）
- CHANGELOG 共同维护（用户手改的优先）
- 临时脚本/下载别堆 D:\DeepseekWorkspace 顶层（放项目 tools/ 或用完删）
- 改完必构建 exe（dist + release + zip 三处）
- 测试先行：改代码先跑测试再打包
- **新项目/新功能先调研**（竞品/生态/现有方案，确认定位再动手；2026-08-15 用户指定，详见 RULES.md 〇节）

## 十、竞品调研结论（2026-08-15，审查时做的）

- 国外主流 = Nexus Mods + Vortex（DMF 官方维护 Vortex 扩展）；DMF 官方无独立 GUI 管理器（只有游戏内 loader + toggle bat）
- GitHub 暗潮专用管理器全是个人小项目（⭐0-9，install/toggle 级别），本项目是唯一中文暗潮专用 GUI
- 细分赛道「暗潮专用+独立GUI+中文+整合包导入」是独苗；护城河=整合包导入/防呆/备份找回；主题美化属于与 Vortex 比弱项
- 功能定位讨论待用户拍板：回归壳（A）/ 转诊断工具（B）/ 维持现状（C）

## 十一、演示验收环境（demo/）

- **位置**：`demo\`（gitignore 不进仓库），用途：拍宣传视频 / 验收新版 exe
- **重置**：`python tools\reset_demo.py`（清空 → 重建示例 mod → 复制最新 exe）
- **真实环境展示**：`python tools\pack_demo.py` 生成两种产物——① `demo\backups\pack_backup_<ts>\`（整个文件夹拷到管理器 backups\ 即可在备份页「恢复此备份」）② `demo\演示整合包_v0.3.0.zip`（「导入整合包」导入）
- **内容**：16 个示例假 mod，覆盖中文名 / 缺依赖 / 循环依赖 / 顺序扩展 / 版本差异 / 禁用 / 无版本
- **以后新版 exe 同步**：构建后运行 reset_demo.py（自动把 dist 的新 exe 复制进 demo）
- release 包照旧在 release\

## 十二·五、暗潮 Mod 生态（2026-08-17/18 工作，非 DMM 本体）

> 四个 mod 项目都在 `D:\DeepseekWorkspace\暗潮\04-Mods\` 下，每个是独立 git 仓库（均已在 GitHub 建仓，CiJhuiDi 账号）。
> 开发规范/游戏源码/参考 mod 见 `D:\DeepseekWorkspace\暗潮\`（01-开发规范 / 02-游戏源码 / 99-临时文件\ref）。

### myhavoc（浩劫任务工具）— v1.1.0 已发布
- 位置：`04-Mods\myhavoc\`；仓库：github.com/CiJhuiDi/darktide-myhavoc（v1.0.0 + v1.1.0 两个 Release）
- `/myhavoc`：发送自己的浩劫任务(层数/地图/词条)到队伍聊天；`/havocstart`：一键开始自己的浩劫任务（v1.1.0，链路同浩劫面板 `havoc_play_view._cb_on_mission_start`：有 ongoing_mission_id 直接复用，否则 `activate_havoc_mission` → `party_immaterium:wanted_mission_selected`；400 already_has_ongoing_mission 特判）
- 数据源：`Managers.data_service.havoc:current_order()` → order.rank / order.blueprint.map / blueprint.flags(词条 `havoc-circ-*`)；词条名 `circumstance_templates[id].ui.display_name` → localize（中文自动）
- 参考实现：Wobin/HavocAuspex + Transmitter（归档 `暗潮\99-临时文件\havoc_auspex_ref\`）

### color_mark（彩色标记）— v1.0.0 已推未实测
- 位置：`04-Mods\color_mark\`；仓库：github.com/CiJhuiDi/darktide-color-mark
- 选人方案定稿：**队伍列表编号**（`/squad` 列当前队伍真名 → `/mark 编号 颜色`），砍掉 friends/recent/players/label_color
- 队伍数据：`social:fetch_party_members()` → PlayerInfo（真名 character_name()，不受 AnonPlayers 隐藏影响）；标记 key=account_id，persistent_table 持久化

### status_wheel（状态轮盘）— v2.0.0 已推未实测（⚠️ 两坑已修）
- 位置：`04-Mods\status_wheel\`；仓库：github.com/CiJhuiDi/darktide-status-wheel
- v2.0.0 整合 For The Emperor（已停更）全量：14 槽可拖拽重排（mod:set wheel_config 持久化）+ 每项独立快捷键(keybind_<key>)+ 求助联动(#need_help 协议:本地语音+聊天,队友响应播语音+头顶10秒标记)+ dibs 禁用 + 报告高压按钮(「高压！！！」)
- ⚠️ **崩溃坑(已修)**：自定义条目必须带 `voice_event_data = {voice_tag_concept, voice_tag_id=""}`，原生 `_on_com_wheel_stop_callback` 会索引它（nil 直接崩游戏，日志 `attempt to index field 'voice_event_data'`）
- ⚠️ **重叠坑(已修)**：14 槽 + 112px 图标必叠（半径 190 固定）；图标尺寸按槽位数动态缩放（≤8:112 / ≤10:100 / ≤12:88 / 14:76）
- 防御式适配：FTE 私有字段全换公开 API（chat:sessions()、player:players_at_peer）；SmartTagSystem/VivoxManager 用 DMF 字符串 hook（自动延迟）
- 参考：FTE 源码归档 `暗潮\99-临时文件\fte_ref\`；游戏 UI 源码在线仓库 Aussiemon/Darktide-Source-Code（本地反编译无 UI 层，在线拉取 smart_tagging/havoc_play_view）

### term_db（暗潮术语库）— 立项 v0.3，待定稿
- 位置：`04-Mods\term_db\`（data/terms.js 63 条 + demo/index.html + docs/术语清单_v0.3.md）；git 已 init 未建远端仓
- 数据来源：`03-技能树\数据\darktide_zh_loc.json`（官方中文 139724 键）+ 官方术语表 loc_glossary_*（22 条）+ 反编译源码验证
- ⚠️ **术语勘误**：撕裂=Rending(破甲/减护甲减伤)，脆弱=Brittleness(每层 2.5% 增伤)；链锯撕裂(Sawing)与两者无关
- 护甲六类：无甲/感染/狂人/防弹/硬壳/不屈（Unarmored/Infested/Berzerker/Armored/Super Armor/Resistant）
- 下一步：用户定稿去留 → 补 glossary 词条 → 关系图谱 → 游戏内 mod 化

## 十二、待办 / 可能的下一步


- 用户反馈测试新功能（主题系统/多选模式/导出/依赖检查/差异对比的实机体验）
- 验证用户实机：① 游戏关闭后 mod 启停开关是否已随轮询解锁；② mod 取消勾选后保存能否真正停用（2026-08-17 两处修复，alpha 构建 release\DarktideModManager_alpha\ 待实机验证）
- 后续功能方向（用户提过但未做）：无（更新检查 Nexus 已砍掉）
- ⚠️ 0.4.1 已发布：清单格式变更为「停用=移除行」（见 Mod 管理段），实机验证待用户反馈
- 注意 release\DarktideModManager_v0.3.1\ 里可能有用户实际运行产生的 backups/config（本地数据）
- test_pack.py 的 SAMPLE 留空时前置 check 无条件失败（历史遗留脚本 bug，与功能无关，跑测试时可忽略或用真实整合包路径）
- 崩溃检测功能（工作区未提交）：console_logs 支持已补完；待用户确认后 → 全量测试 → 构建新 exe（dist+release+zip 带协议文件）→ 提交
