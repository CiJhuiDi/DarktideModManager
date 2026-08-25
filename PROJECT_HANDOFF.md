# DMM 暗潮 MOD 管理器 · 项目交接摘要

> **给新会话的快速上手文档**：读完这个 + RULES.md（工作条例）+ CHANGELOG.md 即可接手。
> 最后更新：2026-08-25（**v0.5.0 已发布**；含语录内嵌状态栏 / 单实例聚焦修复 / 性能批次 / CDN 本地化）

---

## 一、项目是什么

《战锤40K：暗潮》的 Mod 管理器（pywebview 桌面应用，Python FastAPI 后端 + 原生 JS 前端）。
只做"壳"：管理 mod 启停/顺序/预设/整合包导入，内置 DMF 框架组件，不碰游戏本体。

- **代码位置**：`D:\DeepseekWorkspace\darktide-mod-manager\`
- **当前版本**：**v0.5.0（2026-08-25 发布，正式版）**；工作区为正式态（发布后如需继续 alpha 测试，用 `tools/set_alpha_state.py` 切换）
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

**语录显示（内嵌状态栏，2026-08-25 调整，待实机验证）**：
- 底部**状态栏内嵌语录胶囊**（绝对定位水平居中，statusbar 需 position:relative；不再单开栏位）：暗潮加载画面官方语录（310 条），点击胶囊手动换；超长省略 + 悬停 title 看全文
- **有效操作才换**：点击可交互元素才换（前端 `QUOTE_INTERACTIVE` 选择器：button/a/input/select/label/[role]/[data-action]/[onclick]/.switch/.chip/.nav-item/.quote-bar/.banner/.mod-row/.ctx-menu/.log-fbtn/.log-view/.tab，200ms 同元素去重）+ Sortable onEnd 拖拽换；**点空白/装饰区（空操作）不换**
- 数据：core/quotes.py（310 条，2026-08-19 从游戏 loading_view_settings.lua 导出；官方文本含 4 条重复文案，如实保留）；API GET /api/quotes 返回全部，前端本地洗牌轮换
- 触发：全局捕获 click 过滤 QUOTE_INTERACTIVE + Sortable onEnd；CSS 类 .quote-bar/.q-ico/.q-text（已登记 docs/UI_TEMPLATE.md 八·五节）
- 工具：tools/test_quotes.py（已入 test_full Phase A，共 18 套件）

**性能与稳定性优化（2026-08-21，工作区未提交，待实机验证）**：
- **列表加载**：scan_mods 元数据缓存（30s TTL + MODS_DIR mtime 签名自动失效 + 写操作显式失效 invalidate_scan_cache：导入/删除/恢复备份/改备注），冷扫 434ms→缓存命中 0ms；localization 搜索深度受限（4 层 os.walk 剪枝替代 rglob 全树）+ 文件列表缓存；.mod 单次读取（version+packages 共用）
- **status 接口**：去掉 `len(scan_mods())`（改轻量目录计数）+ 进程检测换 CreateToolhelp32Snapshot 快照 API（<5ms，异常回退 tasklist），511ms→60ms
- **首屏**：骨架屏（.boot-loading，登记 UI_TEMPLATE 八·六）+ /api/mods 去 description（85KB→55KB）+ /api/mods/{name}/detail 悬停懒加载（descCache + 防重入；无描述显示“（无描述）”）
- **前端渲染**：DocumentFragment 批量插入 + 依赖徽标预构建索引（depIndex，render 时 O(1) 查询）
- **单实例**：窗口关闭后主动释放互斥体 + 清理 WebView2 子进程（psutil，加速用户数据锁释放，快速重启不再 47s 干等）+ acquire 时先聚焦旧窗口、失败短暂重试（真多开才拦截）
- **日志**：app.log 轮转（2MB×4 份封顶 8MB）；/api/perf 前端启动耗时上报（首次 load 后写 app.log，排查慢直接看“前端启动耗时”行）

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

- **前端卡「连接中…」= CDN 外链脚本超时中断 JS（2026-08-23）**：SortableJS 曾走 `cdn.jsdelivr.net` 同步 `<script src>`，CDN 不可达时 WebView2 等 ~20s 超时后继续执行内联 JS，跑到 `new Sortable(...)` 时 `Sortable` 未定义抛错 → 后续 `load()`（脚本最后一行）永不执行 → 前端永远「连接中…」（`/api/status` 轮询正常、`/api/mods` 请求缺失——uvicorn access log 响应完成才写，所以日志里看不到）。已修：Sortable.min.js 本地化到 `static/vendor/sortablejs/`，后端 `app.mount("/vendor", StaticFiles(...))`；**以后前端禁引外网 CDN 脚本**，静态资源一律走 `/vendor`

- **status 轮询别塞重活（2026-08-21）**：前端每 10s 轮询 /api/status，里面曾有 `len(scan_mods())`（每 10s 全量扫 300+ mod）和 tasklist 子进程（每次 ~350ms）。已改：轻量目录计数 + CreateToolhelp32Snapshot 进程快照（<5ms，异常回退 tasklist）。教训：轮询接口只放轻量计算；进程检测用快照 API 别起子进程；前端渲染用 DocumentFragment + 预构建索引
- **单实例互斥体不释放 → 关窗后立刻重启被误拦（2026-08-21）**：CreateMutexW 句柄只在进程退出时由 OS 释放，而窗口关闭到进程退出有延迟（WebView2 子进程收尾），期间重启会被判多开。修法：窗口关闭后主动 CloseHandle + acquire 时先聚焦旧窗口、失败则短暂重试（真多开才拦截）。注意同进程内重复 CreateMutexW 同名互斥体会返回同一 handle 且不报 183，等待重试前必须先 CloseHandle。**行为变更（2026-08-25）**：多开不再弹「已经在运行中」提示框——已有实例时聚焦现有窗口后静默退出（app.py main 里去掉 MessageBoxW，只留日志）
- **聚焦现有窗口失效 = tasklist bytes/str 比较坑（2026-08-25 破案）**：`focus_existing_window` 用 `'DarktideModManager.exe' not in (out or b'')`——out 是 bytes，str in bytes 抛 TypeError 被外层 except 吞成 False，SetForegroundWindow 从未执行。修法：`b'DarktideModManager.exe' not in out`。**另：PyInstaller 6.x onefile 是父子双进程**（bootloader 父 + 实际代码子，父子同名），进程列表里两个 DarktideModManager.exe 是**同一实例**，别误判成双开；互斥体在子进程创建
- **聚焦唤起最小化窗口白屏 = WebView2 合成器未唤醒（2026-08-25 破案，用户实机必现）**：最小化状态下被聚焦唤起 → 窗口持续白屏无法交互。三重修复（app.py）：① 弃用 keybd_event 模拟 Alt（按键注入可能干扰 WebView2），改 **AttachThreadInput**（当前线程 attach 到目标窗口线程+前台线程，SetForegroundWindow 不再被前台锁拦，零按键注入）；② SW_RESTORE 仅 IsIconic 时才调（无条件还原会把最大化窗口打回普通大小）；③ 还原后 **RedrawWindow(RDW_INVALIDATE|ALLCHILDREN|UPDATENOW) 强制重绘** + 窗口侧 `win.events.restored` 里做 **+1/-1px resize 往返**强制合成器重新唤醒。注意：ImageGrab 截屏在窗口不在前台时截到遮挡内容（97% 白假象），抓窗口内容要用 **PrintWindow(PW_RENDERFULLCONTENT=2)**；build_alpha 曾静默失败（exe 停在旧版），构建后务必核对 release exe 时间戳
- **装饰器丢失致路由 404（2026-08-21）**：架构拆分/重构时装饰器可能被吞——`api_set_game_dir` 曾裸奔（无 `@app.post("/api/game_dir")`），前端调 `/api/settings/game_dir` 与后端路径不一致，玩家点「选择文件夹」报 Not Found。教训：路由函数前必须紧贴装饰器；前端 API 路径与后端路由要保持同一常量源；路由改动后全量搜前端/测试/文档引用
- **启动慢 = scan_mods 的 rglob 全树遍历（2026-08-21）**：启动时 /api/mods + /api/deps/check 连续两次 scan_mods，每个 mod 都 rglob 全树找 localization（缓存检查在搜索后，第二遍白跑）。已改为深度受限搜索（4 层）+ 完整缓存（文件列表缓存，命中只 stat 几个文件）+ .mod 单次读取（version+packages 共用）。教训：扫描类接口在 SSD 上测不出问题，机械盘 + 300+ mod 才会暴露；改 IO 密集路径先想想缓存放哪
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

## 十二、待办 / 可能的下一步

- **v0.5.0 已发布（2026-08-25）**：Alpha 批次（语录内嵌状态栏 / 性能优化 / CDN 本地化 / 单实例聚焦修复含白屏三重修复）全部定版发布；Release v0.5.0 Beta + zip（含 LICENSE/THIRD_PARTY）已上传。后续待办：
- 玩家反馈新版本实机体验（语录/聚焦/性能）
- 后续功能方向（用户提过但未做）：无（更新检查 Nexus 已砍掉）
