# DMM 暗潮 MOD 管理器 · 项目交接摘要

> **给新会话的快速上手文档**：读完这个 + RULES.md（工作条例）+ CHANGELOG.md 即可接手。
> 最后更新：2026-08-15 01:00（v0.3.0 发布后）

---

## 一、项目是什么

《战锤40K：暗潮》的 Mod 管理器（pywebview 桌面应用，Python FastAPI 后端 + 原生 JS 前端）。
只做"壳"：管理 mod 启停/顺序/预设/整合包导入，内置 DMF 框架组件，不碰游戏本体。

- **代码位置**：`D:\DeepseekWorkspace\darktide-mod-manager\`
- **当前版本**：v0.3.0 Beta（2026-08-15 发布，Latest）
- **GitHub**：https://github.com/CiJhuiDi/DarktideModManager（CiJhuiDi）
- **游戏目录**：用户在真实 Steam 库（D:\SteamLibrary 下能找到，335 mod 大整合包环境）

## 二、核心文件结构

```
app.py               # FastAPI 后端（全部逻辑，~2000 行）
static/index.html    # 前端（单文件，原生 JS + SortableJS）
dmf_payload/         # 内置 DMF 组件（官方原版 + 自译汉化）
tools/               # 发布/测试脚本（见下）
test_*.py            # 主测试（根目录）
CHANGELOG.md         # 更新历史（与用户共同维护，以用户手改为准）
RULES.md             # ← 工作条例在 workspace，不在项目里！
```

## 三、当前功能全景（v0.3.0）

**核心**：一键安装 DMF / 覆盖更新 DMF（force）/ 整合包导入（替换+合并）/ 归档备份找回

**Mod 管理**：启停/排序/搜索/中文显示名/右键菜单/方案预设/**批量操作（右键多选模式）**

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

## 五、发布脚本工具链（tools/）

| 脚本 | 用途 |
|---|---|
| `bump_version.py <ver>` | 版本号全局升级（通用版） |
| `release.py <tag>` | 创建/更新 GitHub Release + 传 zip（通用版） |
| `sync_release_notes.py <tag>` | 按 CHANGELOG 同步 Release 说明 |
| `build_mock.py` | 重建测试用 mock 假游戏目录 |
| `hanhua_dmf.py` | 重写 DMF localization（自译汉化） |
| test_*.py（11 个） | 专项测试：batch/classify/deps/order_hint/export/preview/backup_preview/load_order/load_order_backup/load_order_preview/folder_import/guard/simulate/dmf_force |

## 六、GitHub 凭据（重要！）

- **gh CLI 未登录**（设备码流程在代理下失败），用 `GH_TOKEN` 环境变量
- 发布脚本自动从 git credential 取 token：`git credential fill` → 设 GH_TOKEN → 调 gh
- **gh 不读 git 代理配置**：跑 gh 前需 `HTTPS_PROXY/HTTP_PROXY=http://127.0.0.1:7890`
- token 在 GCM 里（2026-08-14 换的新令牌，365 天有效）

## 七、踩坑速查（详细见 RULES.md）

- **僵尸进程**：22 个 python/exe 抢 8317 端口 → 测试假失败，先 taskkill
- **装饰器错位**：辅助函数别插到 @app.get 和目标函数之间（备份 422 的根因）
- **秒级时间戳覆盖**：backup_load_order 和 restore 同秒会覆盖目标文件，先读内容再备份
- **DMF packages 两类**：短名=库依赖，含 / 的 content/wwise=资源路径（要过滤）
- **PowerShell 转义地狱**：复杂逻辑写 .py 脚本跑，别内联 python -c
- **pywebview import 名是 webview**，不是 pywebview

## 八、用户偏好速记

- 中文交流，结论先行，报告简短
- 确认框文案精简（后果+补救，不列使用情景）
- CHANGELOG 共同维护（用户手改的优先）
- 临时脚本/下载别堆 D:\DeepseekWorkspace 顶层（放项目 tools/ 或用完删）
- 改完必构建 exe（dist + release + zip 三处）
- 测试先行：改代码先跑测试再打包

## 九、演示验收环境（demo/）

- **位置**：`demo\`（gitignore 不进仓库），用途：拍宣传视频 / 验收新版 exe
- **重置**：`python tools\reset_demo.py`（清空 → 重建示例 mod → 复制最新 exe）
- **内容**：16 个示例假 mod，覆盖中文名 / 缺依赖 / 循环依赖 / 顺序扩展 / 版本差异 / 禁用 / 无版本
- **以后新版 exe 同步**：构建后运行 reset_demo.py（自动把 dist 的新 exe 复制进 demo）
- release 包照旧在 release\

## 十、待办 / 可能的下一步

- 用户反馈测试新功能（多选模式/导出/依赖检查/差异对比的实机体验）
- 后续功能方向（用户提过但未做）：无（更新检查 Nexus 已砍掉）
- 注意 release\DarktideModManager_v0.3.0\ 里可能有用户实际运行产生的 backups/config（本地数据）
