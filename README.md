# DMM 暗潮 MOD 管理器

> **多种需求，一站搞定** —— 装框架、导整合包、管启停、存预设、防崩备份，全在一个窗口里。

一款为《战锤40K：暗潮》(Warhammer 40,000: Darktide) 设计的轻量 Mod 管理器。

基于 [Darktide Mod Framework (DMF)](https://www.nexusmods.com/warhammer40kdarktide/mods/8) 的加载机制，只做"壳"：管理 mod 启停、加载顺序、方案预设与整合包导入，不干预游戏本体文件。**内置 DMF 全套组件，新玩家下载后即可一键安装框架开玩。**

> 独立窗口应用（pywebview），Windows 10/11，**Steam 版**完整支持。
> 🔬 **Xbox app / PC Game Pass 版为实验功能**：游戏目录自动识别与商店版日志目录（`%APPDATA%\Fatshark\MicrosoftStore\Darktide`）已实现，但**仅经单元测试，未在真机 Game Pass 环境验证**；`WindowsApps` 下的 MSIX 安装无法枚举，需「选择文件夹」手动指定游戏目录。
> 当前为 Alpha 测试阶段（内部测试构建，正式版本号待发布时确认）。

## ✨ 功能特性

**开箱即用**
- **一键安装 DMF**：内置加载器 base + DMF（含中文汉化）+ dtkit-patch + 自动装载插件，检测缺失自动提示，一键释放并打补丁
- **覆盖更新 DMF**：DMF 已装也随时可点「🔄 重新安装框架」，强制用内置组件覆盖（旧文件自动备份可找回），用于更新版本或清除旧整合包中的残留组件
- **整合包一键导入**：zip / 7z / rar / tar.gz，自动识别结构（兼容外层套目录），两种模式：
  - **替换导入**（推荐）：旧 mods 整体归档到 backups，mods 始终保持当前一套；根目录旧残留文件自动收走
  - **合并叠加**：包内 mod 加进现有 mods（同名覆盖）
- **归档备份找回**：所有替换/恢复操作自动归档，备份页**表格**列出每次换包/恢复的归档（时间线分组 + 搜索 + 排序），顶部显示**占用与上限**、保留策略可自己调、清理前先列出将删的。
  - **🔍 详情**可看备份里有哪些 mod（大小 / 是否已在游戏目录 / 备份里是否启用）
  - **⤓ 恢复选中**：只把丢掉的**单个 mod** 找回来（默认只勾选"游戏目录里没有"的），其他 mod 不受影响；同名旧版先移进 `backups\partial_*\` 可回滚
  - **↺ 整包恢复**：整个换回某次换包前的状态（仍带差异预览）
- **⭐ 「我的 mod」管理器库**：自己设计/私装的 mod 整合包里没有，换包时最容易被连带清掉。在列表里右键「标记为我的 mod」，它就会被收进管理器自己的**管理器库**（`my_mods\`）：换包时**原地保留 + 按你换包前的开关状态保持启用**，游戏目录被清空/误删时还能**一键从库部署回来**。包里有同名时保留你的版本、不覆盖。

**Mod 管理**
- 启停开关、拖拽排序、搜索筛选（中英文名均可搜）
- **中文显示名**：自动读取 mod 本地化文件，列表显示中文名（如「自动拾取」「智能队友AI」），英文原名作副标题
- 版本号解析、缺失（残留）检测
- **右键菜单**：打开文件夹 / 复制 mod 名 / 备注（显示为 `Mod名(备注)`）/ 删除 mod 文件（进回收站可找回）/ 清理清单残留 / **多选模式**（批量启用/禁用/删除，**拖动任一已选行可整组排序**）
- **方案预设**：启停+顺序一键切换（打宝流 / 拍照流 / 纯净流…），应用前预览启停变化
- **依赖检查**：缺依赖 / 循环依赖 / 加载顺序建议徽标提示
- **导入增强**：自动识别单 mod / 整合包 / 清单 txt / 文件夹，导入前差异预览（新增/更新/移除）
- **导出**：全部导出 / 按启用导出 / 仅导出清单（干净的 mod_load_order.txt），导出包可直接再导入

**补丁与启动**
- 补丁状态检测、一键安装/卸载（dtkit-patch）、启动游戏前自动补打
- 一键启动游戏（绕过启动器，带 Steam 登录/运行状态保护；**仅 Steam 版**，Xbox / Game Pass 版请用 Xbox app 启动）
- 防崩溃设计：绝不动 patch_999 / mod_loader 文件，卸载走"禁用自动装载 + 还原数据库"路线
- **游戏运行防呆**：游戏运行时自动锁定 mod 增删改（按钮变灰禁用 + 后端双重拦截），防止游戏运行中动 mods 目录导致崩溃/丢 mod
- **崩溃检测与日志**：游戏退出后自动检测异常退出（崩溃码 / 新崩溃转储），弹窗引导排查；关于页一键打开控制台日志文件夹——Steam 版 `%APPDATA%\Fatshark\Darktide\console_logs`，🔬 Xbox / PC Game Pass 版 `%APPDATA%\Fatshark\MicrosoftStore\Darktide\console_logs`（**两处互不通用**，按实际存在的自动定位并提示所属版本），文本日志可直接查看 mod 报错
- **排错留痕（反馈问题时附上 app.log 即可）**：exe 同目录 `app.log` 会记录启动环境诊断——游戏目录自动识别的全部候选（Steam 库 / `<盘>:\XboxGames`，逐个标存在·有效）、日志目录探测结果（命中哪个版本 + 实际路径，未命中则列出候选的存在性/日志数与 `APPDATA` 实际值）
- **崩溃报告导出（发群里/发作者用）**：把最新控制台日志 + 崩溃转储 + 报告信息打成一个 zip，**只含游戏侧材料**，方便不懂怎么修的玩家直接丢给有经验的人看；管理器自己的日志与诊断不在其中（在 `app.log` 里）
- **日志分析（实验）**：日志页多标签（最新/导入文件）、错误/警告/通常三分类过滤 + 关键词搜索、行颜色标识、多选/拖选/右键复制、旧日志拖拽导入、崩溃报告一键导出（含环境信息）。**大日志自动只分析末尾**（2MB 窗口，从行边界开始，信息栏会写明「前 N 行未载入」）——玩家要看的崩溃与报错都在最后，早期版本取开头会丢掉最近的整段
  - **crashify 异常诊断**：自动解析游戏内异常块，诊断卡展示异常系统/信息 + **调用链逐帧归属**（涉及 mod 橙色高亮 + 源码行号，可点击定位；游戏/框架帧灰显），提示最内层 mod 帧优先排查——玩家拖入日志即可看出是哪个 mod 出问题
  - **MOD 错误排行**：自动统计日志里各 mod 的报错次数并降序排列（带错误样例），点一条立刻筛出该 mod 的日志行——**谁在刷屏、谁崩的，一眼定位，据此更新或停用它**。归属同时认 mod 日志里的 `[MOD][名]` 自报标记与 `scripts/mods/<名>` 路径；其中 hook 目标失效（`trying to hook … doesn't exist`）的会标「⚠ 版本不兼容」并提示更新该作者的 mod 或暂时停用
  - **被吞掉的引擎错误也可见**：有些 mod 会把引擎报错「吞掉」（压成 INFO 级），排行里自然看不到它、但排查时可能正是它在掩盖问题——日志页会单列一组「🩹 被 mod 吞掉的引擎错误」（哪个 mod、吞了几条、样例）
  - **崩溃同样能解析**：游戏原生致命崩溃（`<<Script Error>>` + 调用链）也识别，不再只认异常块；崩溃报告导出前自动抹掉机器码 / Steam ID 等隐私字段
- **mod 悬停详细描述**：悬停 mod 行显示本地化描述（中文优先，含版本/备注/依赖/缺失警告）
- **横幅显示控制**：顶部横幅（DMF/补丁/依赖）按钮伪下拉 + 复选框单独控制显隐、一键收起/展开全部；收起后显示指示灯（颜色=状态）；正常状态自动收起、异常自动展开；依赖横幅点击逐个跳转并闪光定位问题 mod（缺依赖/循环/顺序）

**语录显示（暗潮风味）**
- 底部**状态栏内嵌语录胶囊**（不再单开栏位，绝对定位水平居中浮于状态栏中部）：每进行一次**有效操作**（点按钮 / 启停 mod / 拖拽排序等）自动换一条暗潮加载画面官方语录（310 条，取自游戏 `loading_view_settings.lua`），一轮播完重新洗牌不重复；点空白/装饰区等**空操作不换**（200ms 内同元素重复点击去重）
- 点击语录胶囊可手动换一条；超长语录自动省略，悬停看全文

**工程细节**：单实例保护（多开自动聚焦现有窗口）、窗口位置记忆（含屏幕外修复）、每次写入自动备份、游戏目录自动识别与即时切换（Steam 库 + 🔬 Xbox / Game Pass 默认安装位置 `<盘>:\XboxGames`，实验）、运行日志

## 🚀 快速开始

### 直接使用

从 [Releases](https://github.com/CiJhuiDi/DarktideModManager/releases) 下载最新 `DarktideModManager_vX.Y.Z.zip`，解压后得到一个文件夹：

```
DarktideModManager_vX.Y.Z/
├── DarktideModManager.exe   ← 双击运行
├── README.txt               ← 完整使用说明
└── 使用指南.txt             ← 新手快速上手
```

程序自动搜索游戏目录——Steam 版扫常见 Steam 库（`libraryfolders.vdf`），🔬 Xbox / PC Game Pass 版扫各盘符默认安装位置 `<盘>:\XboxGames`（实验功能）；自动识别不到时到「关于」页点「🔍 自动识别」或「📂 选择文件夹」手动指定（选含 `bundle` 或 `mods` 的那一层），保存后立即生效。首次使用按顶部红色横幅提示点「⚡ 一键安装 DMF」即可；想一步到位直接点「📦 导入整合包」导入整合包压缩包。

### 从源码运行

```bash
pip install fastapi uvicorn pywebview py7zr
python app.py --browser   # 浏览器模式（开发用，跳过单实例锁）
```

## 🔨 构建 exe

```bash
pip install pyinstaller
build.bat   # 或手动执行：
# python -m PyInstaller --noconfirm --clean --onefile --windowed \
#   --name DarktideModManager --icon app.ico --version-file version_info.txt \
#   --add-data "static;static" --add-data "dmf_payload;dmf_payload" \
#   --collect-all webview app.py
```

输出：`dist\DarktideModManager.exe`

## 🧪 测试

测试脚本使用 mock 假游戏目录（`mock/` 需自行构建，见脚本注释）：

```bash
python tools/test_full.py   # 全量测试（22 个直接套件 + 3 个 HTTP 套件 + 3 个独立目录套件 = 28 项，改代码后/发布前必跑）
python tools/smoke_test.py  # 构建后 exe 冒烟测试
python app.py --port 8317 --browser   # 起测试服务（另开终端）
python tools/build_mock.py  # 构建干净 mock（每次跑测试前执行，防残留污染）
python test_api.py      # API 全流程（需干净 mock，先跑）
python test_import.py   # mod 导入
python test_formats.py  # 多格式导入（rar 用例需系统安装 WinRAR）
python test_dmf.py      # DMF 一键安装（自建 mock_fresh）
python test_backups.py  # 归档备份管理（自建 mock_bak）
python test_pack.py     # 整合包导入（真实整合包场景可选，需自备样例包）
python tools/test_guard.py     # 游戏运行时防呆（9 项）
python tools/test_simulate.py  # 模拟游戏运行环境（6 项）
python tools/test_dmf_force.py # DMF 覆盖更新
python tools/test_crash_diag.py   # crashify 异常诊断
python tools/test_crash_native.py # 原生崩溃解析 + MOD 错误排行 + 导出脱敏
python tools/test_crash_root.py   # 日志根目录双分布 + app.log 诊断留痕（Steam / Xbox·Game Pass，🔬 实验功能，31 项）
```

## 📁 目录结构

```
├── app.py                 # FastAPI 后端（核心业务在 core/ 包）
├── core/                  # 业务模块：state/load_order/patch/mods/imports/dmf/crash/theme/profiles
├── static/index.html      # 前端（原生 JS + SortableJS）；**界面文案全部内联在这个文件里**
├── dmf_payload/           # 内置 DMF 组件（一键安装用）
├── build.bat              # PyInstaller 打包脚本
├── tools/                 # 工程脚本：test_full/smoke_test/build_alpha/build_release/release_pack/start_test_env 等
├── version_info.txt       # exe 版本信息
├── CHANGELOG.md           # 更新历史
├── test_*.py              # 测试脚本（旧，逐步并入 tools/）
├── README.txt             # 随包分发的使用说明（中文）
└── 使用指南.txt           # 新手快速上手指南
```

> 想改界面文字？全部在 `static/index.html`（旧版整理出的「文案清单」已过时并撤下，直接改代码即可）。

## 🛠 技术栈

Python · FastAPI · pywebview（Edge WebView2）· 原生 JS · PyInstaller

## 📦 内置 DMF 组件说明

`dmf_payload/` 内置以下组件（一键安装时释放到游戏目录，已有文件自动备份）：

| 组件 | 来源 |
|---|---|
| mods/base/ | DMF 加载器（读取 mod_load_order.txt 按序加载 mod） |
| mods/dmf/ | [Darktide Mod Framework](https://github.com/Darktide-Mod-Framework/Darktide-Mod-Framework)（mod 形态，含中文汉化） |
| tools/dtkit-patch.exe | [dtkit-patch](https://github.com/ManShanko/dtkit-patch) 0.1.8 |
| binaries/plugins/_dt_mod_autopatch.dll | [dt-mod-autopatch](https://github.com/manshanko/dt-mod-autopatch) 1.0.1（自动装载，游戏更新后自动重新打补丁） |

组件核心为官方 master 原版，localization 为本项目自译汉化。更新方式：覆盖 `dmf_payload/` 对应路径后重新打包。

## ⚠️ 免责声明

本工具仅读写配置文件，不修改游戏本体。使用 mod 可能导致游戏报错或封号风险，请自行斟酌。官方对 mod 持开放态度，但使用须遵守 [Fatshark 官方 modding 政策](https://forums.fatsharkgames.com/t/darktide-modding-policy/75407)——该政策涵盖对其它玩家的影响、服务稳定性与性能、以及绕过进度或付费内容等限制。作者不对使用后果负责。

## ❓ 常见问题（高频）

**Q: 游戏崩溃/闪退，是管理器导致的吗？**
A: 不是。管理器只读写 mods 配置文件和打补丁，不修改游戏本体。崩溃绝大多数由 mod 冲突、mod 与游戏版本不兼容或游戏自身问题引起。排查：① 游戏更新后先点「安装补丁」；② 逐个禁用 mod 定位冲突源；③ 必要时校验游戏文件。管理器的安装/卸载操作都有自动备份，可随时恢复。

**Q: 游戏更新后 mod 全部失效？**
A: 这是 DMF 官方机制（游戏更新会重置 mod 加载），mod 文件都还在。打开管理器点「安装补丁」即可恢复。

**Q: 在管理器里启用了 mod，进游戏却没效果？**
A: 管理器的「启用/停用」管的是**加载**：它把 mod 写进游戏目录的加载清单（`mods\mod_load_order.txt`），决定游戏要不要加载这个 mod。DMF 框架内部还有一层自己的开关，决定加载后**是否生效**——在游戏里按 **F4** 打开 DMF 的 mod 选项菜单，就能看到哪些 mod 被关闭，也可以直接切换。两层互相独立：管理器里显示「已启用」只代表它会被加载。

**Q: 杀毒软件报毒 / 被拦截？**
A: PyInstaller 打包程序的常见误报，源码全开源可自查，添加信任/白名单即可。

**Q: 用了 mod 会不会被封？**
A: 官方对 mod 持开放态度，但须遵守 [Fatshark modding 政策](https://forums.fatsharkgames.com/t/darktide-modding-policy/75407)（含对其它玩家影响、服务稳定性、绕过进度/付费内容等限制），联机使用第三方 mod 尤其要注意，后果自负。

## 🙏 致谢

- [Darktide Mod Framework 社区](https://github.com/Darktide-Mod-Framework)
- [dtkit-patch](https://github.com/ManShanko/dtkit-patch)（[ManShanko](https://github.com/manshanko)）
- [dt-mod-autopatch](https://github.com/manshanko/dt-mod-autopatch)（ManShanko，自动装载插件）
- [xsSplater](https://github.com/xsSplater/Darktide_laucher_bypass)（绕过游戏启动器启动脚本，GPL 3.0，仅致谢参考，未随本软件分发）
- mod 整合包作者们（测试环境参考）

## 📄 许可证

主程序以 [MIT](LICENSE) 协议发布；内置第三方组件按各自协议分发，详见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
