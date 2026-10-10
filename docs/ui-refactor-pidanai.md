# UI 风格重构分析报告 · 对齐 pidanai.com

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](design.md)和[需求/实施状态](requirements.md)为准，当前任务与预算见[自适应交接](handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。
> 文档状态（2026-10-03整理）：**历史参考**。历史设计分析，保留观察与当时建议；当前默认深色液态玻璃/樱花粉主题，实施状态看 [handoff.md](handoff.md)，扩展用 [UI指南](ui-extension-guide.md)。
> 工程约定仍适用：UI先用 `ui-ux-pro-max` + `design-system`；skill优先于旧计划；颜色/字体/时长token化、能力数据与配置驱动；yt-dlp仅经 `ytdlp_service.py`，视觉只读scene，不修改下载核心。

> 2026-09-24 · 阶段 1 报告（只分析，未改任何代码）
> 目标：把「樱花粉玻璃拟态」重构为 pidanai.com（PDAim）的「黑白极简 + 折射彩虹 + 超大展示字 + 玻璃拟态」设计语言。
> 铁律：只改视觉层（token/样式/组件外观），功能、路由、数据、API、Live2D、测试全部保持可用。

---

## 1. 当前项目 UI 结构梳理

**技术栈**：React 18.3 + Vite 8 + PIXI 6.5.10 + pixi-live2d-display 0.4.0；StrictMode 已启用；测试 Vitest 44 + pytest 33。

**页面/场景**（单页应用，`App.jsx` 用 `useReducer` 状态机切场景）：

| 场景 | 组件 | 当前外观 |
|---|---|---|
| 入口 | `EntryScene` | 玻璃卡片 + h1「粘贴视频链接」+ 输入框 + 樱花胶囊按钮 |
| 解析中 | `ParsingScene` | 纯文本「正在解析…」 |
| 选清晰度 | `SelectingScene` | 封面卡 + 标题 + 元信息 + 胶囊格式单选 + 下载按钮 |
| 下载中 | `DownloadingScene` | spinner「下载中，请稍候...」+ 能量条 |
| 完成 | `DoneScene` | 气泡卡 + 保存链接 + 继续按钮 |
| 错误 | `ErrorScene` | 气泡卡 + emoji + 标题 + 文案 + 重试（9 种差异化动画） |

**样式方案**：单一 `global.css`，三层 token（primitive 樱花粉阶+灰阶 → semantic → component），玻璃拟态 + 圆角胶囊，三档主题 `[data-theme=light|dark|auto]`。

**现有 token 语义**：`--accent`(深樱 `#d6336c`)、`--accent-hover/soft/lilac/pink`、`--surface/raised/glass`、`--text-primary/secondary/muted`、`--border/strong`、`--on-accent`、`--shadow-sm/md`、`--btn-*`、`--card-radius:14px`、`--pill-radius:999px`、`--font-body`(Alibaba PuHuiTi/Noto Sans SC)、`--font-mono`、`--dur:.25s`、`--ease`。

---

## 2. Live2D 集成情况

- **容器 DOM**：`App.jsx` `<div ref={stageRef} className="stage">`（z-index:0 全屏固定）；UI 层 `<div className="ui">`（z-index:1，`pointer-events:none`，交互控件恢复 auto）。
- **PIXI 初始化**：`stage.js → initStage()` `new PIXI.Application({ resizeTo: window, backgroundAlpha: 0, antialias, autoDensity })`；`destroyStage()` 全量销毁。StrictMode 双挂载已用 `stale` 守卫处理。
- **模型加载**：`mascot.js → Live2DModel.from('/live2d/bai/白.model3.json')`（绝对路径）；Cubism core 由 `index.html` 引入。
- **渲染循环**：`app.ticker`（待机正弦驱动 + 背景粒子层）。
- **受样式影响的 DOM 范围**：仅 `.stage` 与 `.ui` 两个容器类。**重构样式不触碰 `.stage` 结构、PIXI init/resize/destroy、模型加载路径**。

---

## 3. 目标网站设计语言总结（pidanai.com / PDAim）

定位：计算机视觉 FPS 瞄准优化工具官网，**默认浅色主题**。

### 3.1 配色
- 底/字：`--bg:#ffffff` 纯白 · `--fg:#070707` 近黑 · `--muted:rgba(7,7,7,.58)` · `--line:rgba(7,7,7,.08)`
- **「折射」彩虹点缀（核心特色，iridescent refraction）**：cyan `#47a9ff` / violet `#996fff` / pink `#ff6cae` / mint `#53ddb8` / warm `#ffc062`（原值为 15–20% 透明度光斑）
- 玻璃拟态：`--glass-tint`/`--glass-edge-*` 白玻璃 + 上下明暗描边；卡片 `color-mix(in srgb, var(--bg) 84%, transparent)`
- 面板阴影：`0 24px 80px rgba(0,0,0,.08)`

### 3.2 字体/字型
- 主字体 `HYZhengYuan95`（汉仪正圆，圆体）+ Inter；展示字体 + `Arial Black`/`Impact`
- body `14px`；按钮 `12px/900`
- **超大负字距展示字**：h1 `104px/700/letter-spacing:-9.36px`，h2/h3 `82px/700/-5.74px`

### 3.3 组件/交互
- 玻璃胶囊按钮：`linear-gradient(145deg, rgba(255,255,255,.11), transparent 42%)` + `inset` 上下高光描边 + `border-radius:999px`
- 自定义大光标（`--cursor-size:132px` blob）
- canvas 背景特效：网格 `--grid-*` / 线条场 `--line-field-*` / 对角 `--diagonal-*` / 折射 `--refraction-*`

### 3.4 页面结构（区块顺序）
Nav（玻璃固定顶栏）→ Hero（FPS 标签 + 超大标题「HELLO THIS IS PDAIM」+ 副标题 + 滚动提示）→ STABILITY CORE（3 卡）→ CALIBRATION FLOW（3 步）→ Footer。

**一句话**：黑白极简（纯白底 + 近黑字）+ 超大负字距展示字 + 玻璃拟态胶囊按钮 + 折射彩虹点缀 + 大光标 + canvas 网格/折射背景。风格 ≈「Swiss 编辑排版 × 科技游戏」。

---

## 4. 设计 token 对照表（现有 → 目标 → 变更方案）

> 原则：**语义名保持不变**（组件不感知换肤），只改 primitive 映射 + 新增「折射」阶。保留三档主题与主题切换扩展位。

### 4.1 Primitive（新增/替换）

| 现有 | 目标 | 说明 |
|---|---|---|
| `--sakura-700~050`（樱花粉阶） | **删除**，替换为黑白阶 `--ink-*` + 折射阶 `--refract-*` | |
| `--gray-900~100` | **替换**为 `--ink-900:#070707` / `--ink-600:rgba(7,7,7,.58)` / `--ink-300:rgba(7,7,7,.18)` / `--ink-200:rgba(7,7,7,.08)` / `--ink-050:rgba(7,7,7,.045)` | 近黑 + 透明度灰阶 |
| — | 新增 `--refract-cyan:#47a9ff` `--refract-violet:#996fff` `--refract-pink:#ff6cae` `--refract-mint:#53ddb8` `--refract-warm:#ffc062` | 折射彩虹点缀 |

### 4.2 Semantic（名不变，改映射值）

| token | 现有值 | 目标值 | 语义 |
|---|---|---|---|
| `--accent` | `#d6336c` | `var(--ink-900)` | 主强调 = 近黑（主按钮黑底白字） |
| `--accent-hover` | `#bd2a5b` | `#2a2a2a` | hover 稍浅黑 |
| `--accent-soft` | `#f8c3cd` | `rgba(7,7,7,.08)` | 柔和强调底（胶囊/光晕） |
| `--accent-lilac` | `#f5a6b8` | `var(--refract-violet)` | PIXI 二级色（折射紫） |
| `--accent-pink` | `#ffb3c1` | `var(--refract-pink)` | PIXI 点缀（折射粉） |
| `--grad-accent` | 樱花粉渐变 | `linear-gradient(135deg, refract-cyan, refract-violet, refract-pink, refract-mint)` | 折射彩虹渐变（装饰/能量条） |
| `--surface` | `#fcfcfc` | `#ffffff` | 纯白底 |
| `--surface-glass` | `rgba(255,255,255,.72)` | `rgba(255,255,255,.72)`（保持） | 玻璃 |
| `--text-primary` | `#333` | `#070707` | 近黑字 |
| `--text-secondary` | `#666` | `rgba(7,7,7,.58)` | 次字 |
| `--text-muted` | `#999` | `rgba(7,7,7,.42)` | 弱字 |
| `--border` | `#e8e8e8` | `rgba(7,7,7,.08)` | 细线 |
| `--border-strong` | `#d9d9d9` | `rgba(7,7,7,.18)` | 强线 |
| `--overlay` | `rgba(0,0,0,.7)` | `rgba(7,7,7,.7)`（保持） | 封面时长角标 |

### 4.3 Component（名不变 + 新增展示字 token）

| token | 目标 |
|---|---|
| `--btn-bg:var(--accent)` `--btn-fg:var(--on-accent)` | 主按钮黑底白字 |
| `--card-radius:14px` `--pill-radius:999px` | 保持 |
| `--font-body` | 圆体优先：`"Maruko Gothic", "Alibaba PuHuiTi", "Noto Sans SC", "PingFang SC", system-ui` |
| `--font-display`（新增） | `"Arial Black", Impact, "Maruko Gothic", var(--font-body)`（超大展示字） |
| `--fs-display`（新增） | `clamp(48px, 9vw, 104px)`（响应式展示字号） |
| `--ls-display`（新增） | `-0.06em`（负字距，中文比西文收窄） |
| `--font-mono` `--dur` `--ease` | 保持 |

### 4.4 深色主题
`[data-theme=dark]` / `[data-theme=auto]`：`--bg→#0a0a0a`、`--fg→#f5f5f5`、surface/text/border 反转，**折射色恒定**（跨主题不变，同现有 accent 逻辑）。

---

## 5. 组件映射表（现有组件 → 目标风格 → 改动点）

| 现有组件 | 目标风格 | 改动点（只改外观） |
|---|---|---|
| `EntryScene` | 超大展示标题 + 玻璃白卡 + 黑胶囊按钮 | CSS：h1 用 `--font-display`+`--fs-display`+`--ls-display`；输入框玻璃化；按钮黑胶囊 |
| `SelectingScene` | 白玻璃卡 + 黑白信息层级 + 胶囊格式单选（选中黑底白字） | CSS：封面卡/元信息/简介/格式胶囊换色 |
| `DownloadingScene` | spinner 折射色 + 能量条折射渐变 | CSS：`.spinner`/`.energy-bar-fill` 换折射 |
| `DoneScene` / `ErrorScene` | 白玻璃气泡 + 黑白 + 折射错误态 | CSS：`.bubble` 换色；错误动画换折射光晕（保留 `err-*` 类名语义） |
| `ExpressionMenu` | 玻璃面板 + 黑白胶囊 pill（选中黑底） | CSS：`.expression-menu`/`.pill` 换色 |
| `Preloader` | 白底 + 折射光斑（替代花瓣）+ 展示标题 | CSS + `PETALS`→`SPOTS` 数据（改数组不改结构） |
| `pixi/background.js` | 折射光斑/网格（替代樱花花瓣） | `FX` 加折射层 + `palette` 换折射色（数据驱动，不改渲染逻辑） |
| `pixi/theme.js` | fallback 同步折射色 | 改 `palette` fallback 值 |

> 所有改动都落在 CSS token 与数据配置，**不改组件逻辑、状态机、下载编排、Live2D 加载**。

---

## 6. 开源方案调研结果（含 License）

| 用途 | 方案 | License | 说明 |
|---|---|---|---|
| **圆体字体（替代汉仪正圆95，商业字体不可用）** | **马路口圆体 Maruko Gothic** | SIL OFL 1.1（可商用，禁单独卖字体文件） | Zen Maru Gothic 中文补字（约 3 万字），最接近目标站圆体 |
| 备选圆体 | 资源圆体 Resource Han Rounded | OFL（思源黑体二开） | 中宫偏大、笔画转折略糙，备选 |
| 黑体兜底（已有） | Alibaba PuHuiTi / Noto Sans SC | 已在用 | 保留为兜底 |
| 图标库 | Phosphor `@phosphor-icons/react` | MIT | ui-ux-pro-max 默认推荐；当前几乎无图标（preloader 内联 SVG + emoji 错误表情） |
| 动效 | 现有 CSS transition + PIXI ticker | — | 本次不动渲染循环，不引 GSAP |
| 背景粒子 | 现有 `pixi/background.js`（数据驱动） | — | 新增折射层即可，无需第三方 |

> 字体来源：[马路口圆体（Zen 圆体中文补字）](https://www.100font.com/thread-849.htm)、[Resource Han Rounded（思源圆体二开）](https://dieken.github.io/posts/free-chinese-unicode-fonts/)、[List of CJK fonts](https://en.wikipedia.org/wiki/List_of_CJK_fonts)。**汉仪正圆95 为商业字体，不集成**（版权红线，只借鉴「圆体」设计语言）。

---

## 7. 风险清单

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| 1 | **Live2D「白」粉发白裙 vs 黑白科技风风格冲突** | 视觉割裂 | 红线禁二改模型，角色保持原样，仅 UI/背景换肤；需用户接受取舍（可后续用深色主题弱化） |
| 2 | 中文负字距超大展示字易挤压/裁切 | 标题可读性 | 用 `--ls-display:-0.06em`（比西文 -9px 收窄），`clamp()` 响应式缩字号 |
| 3 | 圆体字体文件大（3 万字）拖慢首屏 | 性能 | 保持 Google Fonts 加载现有 Noto Sans SC 兜底；圆体按需 subset 或延迟加载，不强上 |
| 4 | 玻璃拟态 `backdrop-filter` 兼容 | 部分浏览器 | 已有 `-webkit-` 前缀 + `--surface` 兜底 |
| 5 | 折射色偏浅，进度/能量条对比度不足 | 可读性 | 能量条填充用实色折射渐变（非 15% 透明），对比 ≥3:1 |
| 6 | 深色主题 token 需同步重构 | 主题破碎 | 深色用黑白反转 + 折射恒定，与现有三档机制一致 |
| 7 | 测试断言特定颜色/类名 | 测试红 | 现有测试主要断言 data-testid/文案/状态，颜色断言少；实施后全量跑 Vitest 校验 |

---

## 8. 解耦与扩展方案

1. **三层 token 保留**：primitive（黑白阶 `--ink-*` + 折射阶 `--refract-*`）→ semantic（`--accent/--surface/--text-*` 名不变）→ component（`--btn-*`/`--font-*`/`--fs-display`）。换肤/换主题只改 primitive 映射，组件零改动。
2. **主题切换机制保留**：`[data-theme=light|dark|auto]`，深色黑白反转、折射色恒定；未来新增品牌色 = 加一组 primitive 映射。
3. **PIXI 颜色单一来源**：`theme.js` 读 `:root` token（折射色也走 token），`background.js` FX 数据驱动，新增折射层不改渲染逻辑。
4. **展示字型 token 化**：`--font-display`/`--fs-display`/`--ls-display` 集中，换字体/调字号/调字距只改这里。
5. **组件外观走 variant/class**：按钮用 `--btn-bg` 系列 token 区分主/次/胶囊；不复制组件。
6. **扩展点显式标注**：图标库（Phosphor，预留注释）、canvas 背景层（`FX` 配置块）、字体（`--font-*`）、动效（`--dur/--ease` + `prefers-reduced-motion` 保留）。

---

## 9. 分步实施计划（阶段 2，待确认后执行）

1. **重建 token 体系**：`global.css` `:root` 黑白阶 + 折射阶 + semantic 映射 + component + 新增展示字 token；同步深色/auto token。
2. **同步 `theme.js`** fallback 折射色。
3. **改全局样式**：按钮（黑胶囊/玻璃胶囊）、卡片、胶囊选择、气泡、菜单、进度条、spinner、输入框、展示标题。
4. **改组件外观**：仅 className/结构不变，样式对齐（`SelectingScene` 信息层级、`DownloadingScene` 折射、`ErrorScene` 折射错误态）。
5. **改背景层**：`pixi/background.js` FX 加折射光斑层 + palette 换色。
6. **改 Preloader**：花瓣→折射光斑（`PETALS`→`SPOTS` 数据）。
7. **字体**：评估引入马路口圆体 subset（或保留现有 + Arial Black 展示字），先不强上。
8. **响应式 + 状态**：断点 token、移动端 `clamp` 缩字号；补 hover/focus/disabled/loading/empty。
9. **验证**：playwright 截图对比 → 功能回归（Live2D 加载/动效）→ pytest 33 + Vitest 44 → 硬编码/魔法数字扫描 → 扩展指南输出。

---

## 附：需用户确认的关键决策

1. **方向**：接受「黑白科技风 + Live2D 白保持原样」的风格取舍？（红线禁改模型）
2. **字体**：是否引入开源圆体「马路口圆体」（OFL）替换现有方正感字体？还是保留 Noto Sans SC + Arial Black 展示字（零字体成本、更快）？
3. **三档主题**：保留现有「浅/深/自动」三档切换，还是简化为目标站的单一浅色？
