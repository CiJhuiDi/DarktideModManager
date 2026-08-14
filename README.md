# DMM 暗潮 MOD 管理器

一款为《战锤40K：暗潮》(Warhammer 40,000: Darktide) 设计的轻量 Mod 管理器。

基于 [Darktide Mod Framework (DMF)](https://www.nexusmods.com/warhammer40kdarktide/mods/8) 的加载机制，只做"壳"：管理 mod 启停、加载顺序、方案预设与整合包导入，不干预游戏本体文件。**内置 DMF 全套组件，新玩家下载后即可一键安装框架开玩。**

> 独立窗口应用（pywebview），Windows 10/11，Steam 版 / Xbox 版均可。
> 当前为 Beta 测试阶段（v0.2.x），欢迎反馈问题与建议。

## ✨ 功能特性

**开箱即用**
- **一键安装 DMF**：内置加载器 base + DMF（含中文汉化）+ dtkit-patch + 自动装载插件，检测缺失自动提示，一键释放并打补丁
- **整合包一键导入**：zip / 7z / rar / tar.gz，自动识别结构（兼容外层套目录），两种模式：
  - **替换导入**（推荐）：旧 mods 整体归档到 backups，mods 始终保持当前一套；根目录旧残留文件自动收走
  - **合并叠加**：包内 mod 加进现有 mods（同名覆盖）
- **归档备份找回**：所有替换/恢复操作自动归档，备份页一键换回任意历史整合包

**Mod 管理**
- 启停开关、拖拽排序、搜索筛选（中英文名均可搜）
- **中文显示名**：自动读取 mod 本地化文件，列表显示中文名（如「自动拾取」「智能队友AI」），英文原名作副标题
- 版本号解析、缺失（残留）检测
- **右键菜单**：打开文件夹 / 复制 mod 名 / 备注（显示为 `Mod名(备注)`）/ 删除 mod 文件（进回收站可找回）/ 清理清单残留
- **方案预设**：启停+顺序一键切换（打宝流 / 拍照流 / 纯净流…）

**补丁与启动**
- 补丁状态检测、一键安装/卸载（dtkit-patch）、启动游戏前自动补打
- 一键启动游戏（绕过启动器，带 Steam 登录/运行状态保护）
- 防崩溃设计：绝不动 patch_999 / mod_loader 文件，卸载走"禁用自动装载 + 还原数据库"路线

**工程细节**：单实例保护、窗口位置记忆、每次写入自动备份、运行日志

## 🚀 快速开始

### 直接使用

从 [Releases](https://github.com/CiJhuiDi/DarktideModManager/releases) 下载最新 `DarktideModManager_vX.Y.Z.zip`，解压后得到一个文件夹：

```
DarktideModManager_vX.Y.Z/
├── DarktideModManager.exe   ← 双击运行
├── README.txt               ← 完整使用说明
└── 使用指南.txt             ← 新手快速上手
```

程序自动搜索 Steam 库定位游戏目录；首次使用按顶部红色横幅提示点「⚡ 一键安装 DMF」即可；想一步到位直接点「📦 导入整合包」导入整合包压缩包。

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
python app.py --port 8317 --browser   # 起测试服务（另开终端）
python test_api.py      # API 全流程（需干净 mock，先跑）
python test_import.py   # mod 导入
python test_formats.py  # 多格式导入（rar 用例需系统安装 WinRAR）
python test_dmf.py      # DMF 一键安装（自建 mock_fresh）
python test_backups.py  # 归档备份管理（自建 mock_bak）
python test_pack.py     # 整合包导入（真实整合包场景可选，需自备样例包）
```

## 📁 目录结构

```
├── app.py                 # FastAPI 后端（全部逻辑）
├── static/index.html      # 前端（原生 JS + SortableJS）
├── dmf_payload/           # 内置 DMF 组件（一键安装用）
├── build.bat              # PyInstaller 打包脚本
├── version_info.txt       # exe 版本信息
├── CHANGELOG.md           # 更新历史
├── test_*.py              # 测试脚本
├── README.txt             # 随包分发的使用说明（中文）
└── 使用指南.txt           # 新手快速上手指南
```

## 🛠 技术栈

Python · FastAPI · pywebview（Edge WebView2）· 原生 JS · PyInstaller

## 📦 内置 DMF 组件说明

`dmf_payload/` 内置以下组件（一键安装时释放到游戏目录，已有文件自动备份）：

| 组件 | 来源 |
|---|---|
| mods/base/ | DMF 加载器（读取 mod_load_order.txt 按序加载 mod） |
| mods/dmf/ | [Darktide Mod Framework](https://github.com/Darktide-Mod-Framework/Darktide-Mod-Framework)（mod 形态，含中文汉化） |
| tools/dtkit-patch.exe | [dtkit-patch](https://github.com/ManShanko/dtkit-patch) 0.1.8 |
| binaries/plugins/_dt_mod_autopatch.dll | 自动装载插件（游戏启动时自动补打补丁） |

组件核心与官方 master 一致（localization 为中文汉化版，来自实测可用的整合包环境）。更新方式：覆盖 `dmf_payload/` 对应路径后重新打包。

## ⚠️ 免责声明

本工具仅读写配置文件，不修改游戏本体。使用 mod 可能导致游戏报错或封号风险，请自行斟酌（官方对 mod 持开放态度，但联机使用第三方 mod 需遵守游戏规则）。作者不对使用后果负责。

## 🙏 致谢

- [Darktide Mod Framework 社区](https://github.com/Darktide-Mod-Framework)
- [dtkit-patch](https://github.com/ManShanko/dtkit-patch)
- mod 整合包作者们（测试环境参考）

## 📄 许可证

[MIT](LICENSE)
