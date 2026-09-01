# 暗潮（Darktide）Mod 管理器 — 研究报告

> 日期：2026-08-12 ｜ 状态：研究完成，待定技术栈
> 结论先行：DMF 已管加载，第三方管理器只做「壳」——读/写配置 + 调 dtkit-patch + 聚合 Nexus 信息。

---

## 一、现有机制（实证，非猜测）

游戏实际环境（Steam 库，appid 1361210，游戏目录 `Warhammer 40,000 DARKTIDE`）：

```
游戏更新/启动
  └─ dtkit-patch.exe --toggle .\bundle   ← 打/解补丁，注入加载器（游戏更新后必须重跑）
       └─ mods/base/（DMF 加载器本体：mod_manager.lua + function/*.lua）
            └─ 读取 mods/mod_load_order.txt（UTF-8）  ← ★ 启停+顺序的唯一配置源
                 └─ 按顺序加载每个 mod 文件夹的 <Mod名>.mod（Lua manifest）
                      └─ new_mod(...) 注册 → mod 设置存 user_settings.config
```

### 关键文件（壳的全部操作面）

| 文件 | 路径 | 作用 | 格式 |
|---|---|---|---|
| 加载清单 | `…\mods\mod_load_order.txt` | 启停 + 加载顺序 | UTF-8 纯文本；每行一个 mod 文件夹名；`--` 开头 = 注释/禁用；空行忽略 |
| 补丁工具 | `…\tools\dtkit-patch.exe` | `--toggle .\bundle` 打/解补丁 | 命令行，exit code 1 = 失败 |
| mod 清单 | `…\mods\<名>\<名>.mod` | 元数据 | Lua：`return { run=…, packages={}, version="x.y.z" }` |
| 设置 | `%APPDATA%\Fatshark\Darktide\user_settings.config` | 每个 mod 的设置块 | 引擎格式（`ModName = { … }`，**非 JSON**） |
| 日志 | `%APPDATA%\Fatshark\Darktide\console_logs\*.log` | 加载记录/排错 | 文本 |

### 实证结论（来自机器 + console 日志）

1. **DMF 读 `mods\mod_load_order.txt`**（日志：`Loading ./../mods/mod_load_order.txt`）。
   游戏根目录另有一份 48 行的 `mod_load_order.txt` 是整合包留的参考副本，**DMF 不读**，壳不要碰。
2. 当前启用 21 个 mod（psych_ward → PrivateModeBypass），mods/ 目录共存 312 个 mod 文件夹（其余靠不在清单里 = 禁用）。
3. `base` 和 `dmf` 两个基础模块由 DMF 自动插入加载首位，**不需要也不允许写进清单**。
4. 游戏更新后所有 mod 自动失效 → 必须重跑 `dtkit-patch --toggle`。
5. 设置全部在 `user_settings.config`（158KB，含 `mod_manager_settings` 块 + 各 mod 块如 `AutoLoot = {…}`）。更新 mod 时设置保留，因为设置不在 mod 文件夹里。
6. mod 下载源：Nexus Mods（warhammer40kdarktide），Vortex 可用但重且概念绕。

---

## 二、壳的设计结论

### 职责边界

| 模块 | 干 | 不干 |
|---|---|---|
| 数据层 | 扫 `mods\` 解析 `.mod` manifest；读 `mod_load_order.txt` 得状态；读 `user_settings.config` 得设置 | 不碰 mod 文件本体 |
| 操作层 | 写 `mod_load_order.txt`（启停/排序/注释）；调 `dtkit-patch --toggle`；预设 = 清单快照 | 不实现任何加载逻辑 |
| 下载层 | Nexus API：搜索/详情/下载/解压到 `mods\` | 不做订阅管理 |
| UI 层 | 列表、搜索/过滤/排序、开关、预设切换、设置只读展示 | — |

### 核心操作面（就这么点事）

1. **启停/顺序**：编辑 `mods\mod_load_order.txt`（增删行、调序、`--` 注释）
2. **游戏更新后恢复**：检测 → 调 `dtkit-patch.exe --toggle .\bundle`（必须在游戏关闭时）
3. **预设方案**：`mod_load_order.txt` 的保存/恢复/对比
4. **信息聚合**：Nexus API 拉版本/更新/详情，本地对比提示更新

### 风险点（第一版避开）

- `user_settings.config` 是引擎专有格式，写错可能搞坏全部设置 → **第一版只读展示**，写入做成「编辑某一块 + 备份原文件」的高级功能
- 游戏运行时：改清单无害（下次启动生效），但 **dtkit-patch 必须游戏关闭时跑**
- Nexus API 需用户个人 API key；搜索无公开端点 → MVP 用「粘贴 mod 页 URL 导入」

---

## 三、待定项

- [ ] 技术栈：Python+Web（自用）/ Tauri（发布）——等用户拍板
- [ ] Nexus API key 获取（用户 Nexus 账户页生成）
- [ ] `user_settings.config` 完整格式解析（引擎配置语法，需进一步研究）
- [ ] 游戏版本检测方式（判断「更新后需重新打补丁」的触发条件）

## 四、下一步建议

1. 定技术栈 → 搭数据层（扫 mods/ + 解析 load_order）→ 这是全部风险所在，先做
2. UI 壳（列表 + 开关 + 预设）
3. Nexus 下载/更新检测
4. 设置编辑器（只读 → 可写）
