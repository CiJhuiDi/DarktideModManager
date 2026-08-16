# 前端 UI 模板（组件库）· DMM

> **使用原则（2026-08-16 用户指定）**：前端 UI 一律复用本模板的组件类，**不新写临时样式**。
> 样式定义集中在 `static/index.html` 的 `<style>` 内；新组件先加进本模板 + 对应 CSS，再在页面使用。
> 目的：统一设计格式、省 token 省算力。

---

## 一、按钮

| 类 | 用途 | 示例 |
|---|---|---|
| `ghost` | 普通操作按钮（工具栏） | `<button class="ghost">🔄 刷新</button>` |
| `ghost danger` | 危险操作（删除/卸载） | `<button class="ghost danger">移除自定义主题</button>` |
| `ghost danger-crash` | 崩溃相关危险（测试用） | `<button class="ghost danger-crash" id="btnSimCrash">💥 模拟崩溃</button>` |
| `chip` + `active` | 筛选/分类标签（互斥选中态） | `<button class="chip active" data-filter="all">全部</button>` |
| `link-btn` | 行内链接按钮（关于页） | `<button class="link-btn" id="btnOpenCrashLogs">📂 打开</button>` |
| `launch-btn` | 大启动按钮（主操作） | 侧边栏「▶ 启动游戏」 |
| `.save`（class="save"） | 保存按钮（状态栏） | 状态栏「保存修改」 |

按钮通用规范：`flex-shrink:0` 防换行；工具栏按钮用 `white-space:nowrap`。

## 二、面板与文本

| 类 | 用途 |
|---|---|
| `card` | 卡片容器（关于页等） |
| `kv`（`.k`/`.v`） | 键值行（关于页路径信息） |
| `tip` | 灰色提示说明文字块 |
| `dim` | 弱化文字（辅助说明/状态） |
| `banner` | 顶部横幅（DMF 安装提示/补丁状态） |
| `dot` | 状态圆点 |
| `icon` | 侧边栏图标 |

## 三、弹窗（showModal）

调用：`showModal({ title, text, lines, html, input, choices, extra, wide, ultra, hideActions })`

| 参数 | 用途 |
|---|---|
| `wide` | 标准宽（520px，确认/选择类） |
| `ultra` | 超宽（920px，长内容如日志/预览） |
| `lines` | 结构化行 `[{text, cls}]`（cls: dim/ml-add/ml-del/ml-upd/ml-info/ml-same） |
| `html` | 原始 HTML 块（高亮内容，如日志行） |
| `extra` | 自定义按钮 `[{text, value}]`（hideActions 时替代底部按钮） |
| `hideActions` | 隐藏底部取消/确定，只用 extra |

示例：
```js
showModal({ title: '确认删除', text: '删除后可从回收站找回。', okText: '删除' });
showModal({ title: '选择模式', choices: [{text:'替换', value:'replace'}, {text:'合并', value:'merge'}] });
showModal({ title: '预览', html: logHtml, ultra: true, extra: [{text:'导出', value:'export'}], hideActions: true });
```

## 四、标签栏（多标签，日志分析用）

| 类 | 用途 |
|---|---|
| `log-tabs` | 标签栏容器 |
| `log-tab` + `active` | 单个标签（可点切换） |
| `log-tab-title` | 标签标题（限宽省略号，长文件名不挤掉 ✕） |
| `log-tab .tab-x` | 标签关闭按钮（✕，hover 变红） |

示例：
```html
<div class="log-tabs">
  <span class="log-tab active">最新日志<span class="tab-x">✕</span></span>
  <span class="log-tab">导入: old.log<span class="tab-x">✕</span></span>
</div>
```

## 五、日志展示

| 类 | 用途 |
|---|---|
| `log-view` | 日志滚动容器（flex:1 + overflow-y:auto；user-select:text） |
| `log-line` | 单行（monospace，pre-wrap 自动换行） |
| `log-line.err` | 错误行（红底） |
| `log-line.warn` | 警告行（黄底） |
| `log-line:hover` | 悬停微亮（brightness 1.18，不破坏行色） |
| `log-line.selected` | 选中态（accent 蓝底白字 !important 反色，彩色行也可见） |
| `mod-row.flash` / `log-line.flash` | 闪光高亮（modflash 动画，定位跳转用） |
| `log-head` | 日志头信息（灰色小字） |

## 六、伪下拉（按钮 + 浮层菜单，替代原生 select）

| 类 | 用途 |
|---|---|
| `banner-drop` | 容器（相对定位） |
| `banner-select` | 触发按钮（当前值 + ▾，hover 边框变亮） |
| `banner-menu` | 浮层菜单（绝对定位，面板样式 + 阴影） |
| `banner-menu-item` | 菜单项（label + checkbox 或 button，hover 高亮） |

## 七、指示灯（横幅收起状态）

| 类 | 用途 |
|---|---|
| `banner-lights` | 指示灯行（flex:1 水平居中，与控件同行） |
| `b-light-item` | 单个灯（名称 + 圆点；`+::before` 自动加 │ 分隔） |
| `b-light` + `green/red/orange/gray` | 圆点颜色（状态） |
| `b-light-text` | 灯名称文字 |

## 八、悬停浮层

| 类 | 用途 |
|---|---|
| `mod-tip` | 通用悬停信息浮层（fixed，面板 + accent 边框，pointer-events:none，防溢出定位） |
| `tip-desc` / `tip-err` | 浮层内描述 / 错误文字 |

## 九、布局规范

- 工具栏：`display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:10px 14px`
- 页面内容区：`padding:14px 18px`
- 面板统一用 `var(--panel)` / `var(--panel2)` 背景、`var(--border)` 边框、圆角 8-12px
- 主题色一律用 CSS 变量（`--text/--dim/--accent/--active-bg/--chosen-bg`），**禁止硬编码色值**（浅色主题会刺眼）

## 十、新组件流程

1. 在 `static/index.html` `<style>` 加 CSS 类（用主题变量）
2. 本文件登记类名 + 用途 + 示例
3. 页面中复用，不再重复写临时样式
