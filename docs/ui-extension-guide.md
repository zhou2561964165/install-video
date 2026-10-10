# UI 主题系统扩展指南（pidanai 深色液态玻璃 + 樱花粉辉光）

> 版本：v2（2026-10-09；依据当前前端源码校订）。视觉方案的历史分析见 `docs/ui-refactor-pidanai.md` 与 `docs/ui-refactor-pidanai-deep.md`；项目当前入口见 `docs/README.md`。
> 本文区分当前实现与扩展约定。模型/语言/主题等已有注册表适合数据驱动；新增渲染、请求或交互行为仍需实现对应代码。接手前遵守根目录 `AGENTS.md` 的工程约定与本文件的模块边界。

---

## 0. 一句话原则

UI改动先用 `ui-ux-pro-max` + `design-system`，skill优先于旧计划；颜色/字体/时长走 token，已有注册表项优先配置化，模块通过窄接口单向通信。当前产品和验收状态以[文档索引](README.md)及其当前入口为准。

**颜色/字体/时长一律走 `:root` token；已有能力优先通过配置表扩展；角色/背景表现读取 `scene` 派生状态，绝不 import 下载核心。** 改任何 UI，先判断「这是不是已有 token 的消费方」，是就直接用 token，不是就加 token 再消费。需要新行为时同步实现该行为，不能把“数据驱动”理解为无需改渲染或交互代码。

---

## 1. 三层 token 体系（primitive → semantic → component）

单一来源 = `frontend/src/styles/global.css` 的 `:root`。组件层**只引用 semantic/component token**，不裸写 primitive 值。

| 层 | 前缀 / 例子 | 职责 | 改哪里 |
| --- | --- | --- | --- |
| L1 primitive | `--sakura-*`、`--ink-*`、`--refract-*`、`--gray-*`、`--cream` | 集中维护基础色板 | `:root` |
| L2 semantic | `--accent` / `--surface*` / `--text-*` / `--border*` / `--scrim` / `--shadow-*` | 表达界面含义；可引用 primitive，也可在 token 层定义透明度或混色 | `:root` + `[data-theme='light']` / `[data-theme='auto']` |
| L3 component | `--btn-*` / `--glass-*` / `--insight-*` / `--refract-ring` / `--font-*` / `--dur*` / `--size-*` / `--*-radius` | 组件外观与动效参数；主题覆盖仍在 token 层维护 | `:root`（必要时在主题块覆盖） |

**加一个 token 的正确顺序**：先判断所属层 → 加到 `:root` 对应段 → 组件通过 `var(--新token)` 消费。颜色、字体和时长不要散落在组件样式里；必要的透明度/混色也应封装为 token。

**PIXI 侧同步（关键坑）**：PIXI 不会自动应用 CSS 样式；`frontend/src/pixi/theme.js` 的 `palette` 通过 `cssVar('--xxx', fallback)` 显式读取 DOM token。无 DOM/CSS 时使用 fallback，改动消费色时应同步两处。**传给 PIXI `hex()` 的颜色必须是 hex**：`rgba()` 和 `color-mix()` 无法解析，会回退成白色。需要 PIXI 消费的颜色 token 应提供 hex 值；纯 CSS 用的玻璃、描边等 token 可以使用透明度和混色。

---

## 2. 加一个主题档

现状三档：`浅色 light` / `深色 dark`（默认）/ `自动 auto`。架构：

- `:root` 即深色默认（`data-theme='dark'` 命中默认值，无需覆盖块）。
- `[data-theme='light']` 小块**只覆盖** `--surface* / --text-* / --border* / --accent-tint / --scrim / --shadow-* / color-scheme`；**accent 与折射五色跨主题恒定，不覆盖**。
- `[data-theme='auto']` + `@media (prefers-color-scheme: light)` 复用浅色 token。
- 切换入口 `frontend/src/App.jsx` 的 `THEMES` 数组（`{ v, label }`）+ `setTheme`，`useEffect` 写 `document.documentElement.dataset.theme`。

**加第四档（如 `sepia`）**：
1. `App.jsx` `THEMES` 加 `{ v: 'sepia', label: '复古' }`（`aria-pressed`/按钮自动生成，无需改渲染）。
2. `global.css` 加 `[data-theme='sepia'] { --surface: …; --text-primary: …; … }` 覆盖块。
3. 若影响 PIXI 底色，`pixi/theme.js` 的 `baseColor` 目前固定 `--ink-900`，需要主题联动时再扩展为运行时读 `--surface`（注意 hex 约束）。

**PIXI 背景色注意**：`pixi/stage.js` 使用 `backgroundColor: hex(baseColor)` 与 `backgroundAlpha: 0`，画布透明，页面底色由 CSS 提供。`baseColor` 当前读 `--ink-900`，用于渲染器底色兜底；若改变画布透明度或让底色参与可见渲染，需重新核对浅色主题表现。

---

## 3. 加一个折射色（玻璃描边 / 光斑 / 背景点缀）

折射五色 `--refract-cyan/violet/pink/mint/warm` 跨主题恒定，用于玻璃 1px 描边环、PIXI 光斑、preloader 光点。

**加第六色（如 `--refract-teal`）**，需三处同步：
1. `global.css` `:root` 加 `--refract-teal: #1fcdb0;`（**hex**）。
2. `pixi/theme.js` `palette` 加 `refractTeal: cssVar('--refract-teal', '#1fcdb0')`（fallback 与 CSS 一致）。
3. 消费处：`pixi/background.js` `createSpots` 的 `colors[]` 数组、`Preloader.jsx` 的 `SPOTS` 数组，各加一条引用即可（数组循环 `% colors.length` 自动轮转，不改循环逻辑）。

**要改渐变**（如加进 `--refract-ring` / `--grad-accent` 的 `linear-gradient` 色阶）：直接在这两个 token 的定义里增删 `color-mix(in srgb, var(--refract-*) 72%, transparent)` 一档即可。

---

## 4. 加背景特效（PIXI 光点 / preloader 光点）

背景光点是**数据驱动**，两处独立：

- **主场景 PIXI 光点**：`pixi/background.js` 的 `FX.spots` 配置（`count/size/drift/sway/alpha`）+ `createSpots()` 生成 + `layers` 数组登记。加新光斑 = 在 `layers` 加一个 `createXxx(root, size, low)` 函数 + 一个 `FX.xxx` 配置对象；`update(delta, intensity)` 里写运动，`resize()` 处理尺寸变化。**删除的 `drawPetal` 是死代码，新特效别复刻**——光晕用 `makeGlowTexture(128, hex(color), alpha)`（径向渐变软光斑），别画硬圆。
- **Preloader 光点**：`components/ui/Preloader.jsx` 的 `SPOTS` 数组提供 `left/size/dur/delay/sway/color`，CSS 由 `.preloader__spot` 与 `@keyframes preloader-drift` 渲染（位移用 `transform: translate3d`，不动画 width/height）。当前 `dur` 是数组中的秒数并写入 inline `animationDuration`；这是现有局部实现。新增通用或复用时长仍遵守工程约定，定义并消费 `:root` 的 `--dur-*` token，不扩散硬编码时长。

**关键约束**：背景层是纯视觉层，`update` 只读 `delta/intensity`，**不感知下载状态**；`intensity` 由 `App.jsx` 的 `intensityForScene(state.scene)` 喂入（场景 → 强度映射）。需要新的粒子行为时要同时更新图层实现和注册数组，单改配置不能生成新行为。

---

## 5. 加表情 / 道具 / 特效

映射与菜单选项在 `frontend/src/pixi/mascotConfig.js` 的 `EXPRESSIONS`；`ExpressionMenu.jsx` 读取这些选项，并实现分组切换、激活态、焦点管理与缩放按钮，再通过回调把参数操作交给 App/mascot。

| 段 | 用途 | 加一个 |
| --- | --- | --- |
| `EXPRESSIONS.stage` | 场景 → 情绪参数（圈圈眼/煎蛋眼/星星眼/生气） | 加 `scene: paramId` 映射 |
| `EXPRESSIONS.random` | 每 ~20s 随机道具（手柄/话筒/戳脸） | 加 `{ paramId, … }` |
| `EXPRESSIONS.menu` | 换装菜单（发型/衣服/配饰/颜色/情绪，single/toggle/multi 分组） | 在对应 `group.options` 加 `{ paramId, name }`，`mode` 决定单选/复选 |
| `EXPRESSIONS.effect` | `edle.motion3.json` 装饰特效（按 `stages` 触发） | 命中 `stages` 的场景列表加场景名 |

- 完整版「白」的表情文件由参数映射驱动，走 `coreModel.setParameterValueById(paramId, 1/0)` 直接写参数（**非** expression manager 单选）；具体可并存关系由 `EXPRESSIONS.menu` 的分组模式控制，并须避免与待机正弦驱动的 `IDLE` 参数冲突。
- 待机动画参数（`ParamAngleX/Y/Z` + `ParamBreath`）在 `mascotConfig.js` 的 `IDLE`（数据驱动，运行时按 `getParameterIndex` 过滤缺失参数）。

新增参数映射可只改配置；新增菜单交互语义或模型控制则要同步实现对应组件/模型代码。

---

## 6. 动画时长 token（`--dur-*`）

`--dur`（通用过渡 `.25s`）之外，循环/反馈类时长单独 token 化，**keyframe 不写死秒数**：

| token | 值 | 用途 |
| --- | --- | --- |
| `--dur-shake` | .35s | 错误抖动 |
| `--dur-breathe` | 2.4s | 错误呼吸 |
| `--dur-dim` | 3s | 错误渐隐 |
| `--dur-progress` | .3s | 进度条宽度过渡 |
| `--dur-spin` | 1s | spinner 旋转 |
| `--dur-spin-fast` | .8s | preloader spinner |
| `--dur-pulse` | 1.8s | preloader mark 脉冲 |
| `--dur-reveal` | .76s | 滚动揭示进场 |
| `--dur-focus` | .5s | 滚动聚焦过渡 |

通用过渡使用 `--dur`（`.25s`）；表格列出其余当前公共 token，值以 `global.css` 为准。新增动画先复用已有 token，否则增加语义化 token（注释用途），不要在 keyframe 中写死时长。CSS 动画须覆盖 `prefers-reduced-motion`；PIXI 动画也要沿用 `background.js` / `mascot.js` 的 reduced-motion 检查方式。

---

## 7. 玻璃 + 折射描边环（复用的坑）

- **玻璃配方**：`--glass-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate))`，所有 `backdrop-filter` 统一引用它（含 `-webkit-` 孪生行）。加新玻璃面直接 `backdrop-filter: var(--glass-filter)`。
- **折射 1px 描边环**：伪元素 `::before` 涂 `--refract-ring` 渐变 + CSS `mask`（`mask-composite: exclude` / `-webkit-mask-composite: xor`）只留 1px 环，不遮玻璃底、不动 backdrop-filter。`@supports (mask-composite: exclude) or (-webkit-mask-composite: xor)` 负责增强环效果。滚动面板（如表情菜单）用**淡描边**替代彩虹环（规避滚动时环错位），见 `.expression-menu` 的 `color-mix(in srgb, var(--refract-violet) 26%, var(--border))`。
- **`backdrop-filter` 祖先链大坑**：祖先元素一旦 `opacity<1` / `transform` / `filter` / `overflow:hidden`，玻璃会**静默失效**。改任何玻璃面，先检查祖先链（详见 `docs/ui-refactor-pidanai.md` 风险清单 + 逐模块截图巡检铁律）。

---

## 8. 解耦与扩展边界

1. **角色/背景根据场景驱动**：`App.jsx` 从 `state.scene` 计算粒子强度并传递阶段状态；`pixi/*` 不读取下载响应，也不 import 下载/API 核心。
2. **PIXI 颜色以 CSS token 为主来源**：`theme.js` 负责运行时桥接；fallback 与 CSS 同步维护。
3. **功能状态通过 hook 和 API 边界流动**：`useDownload` 编排下载、`useVideoInsights` 编排字幕/翻译/总结；`VideoInsights.jsx` 通过 props 接收状态与回调，不能读写下载 reducer。后端 `ytdlp_service.py` 是唯一接触 yt-dlp 的层。
4. **配置适用于已有扩展点**：`THEMES`、`FX`、`SPOTS`、`EXPRESSIONS` 是现存数据入口；新交互、渲染层或请求流程仍需要实现和验证相应代码，不能只添加配置项。

---

## 9. 快速索引（改哪个，看哪里）

| 想改 | 文件 | 入口 |
| --- | --- | --- |
| 配色 / 品牌粉 / 折射色 | `styles/global.css` `:root` | `--sakura-*` / `--refract-*` / `--accent*` |
| 浅/深/自动主题 | `global.css` `[data-theme='light'/'auto']` + `App.jsx` `THEMES` | 覆盖块 / `THEMES` 数组 |
| PIXI 颜色 / 底色 | `pixi/theme.js` `palette` + `baseColor` | `cssVar` 桥接 |
| 背景光点 | `pixi/background.js` `FX` + `createSpots` | `FX.spots` 配置 |
| preloader 光点 | `components/ui/Preloader.jsx` `SPOTS` | `SPOTS` 数组 |
| 表情 / 道具 / 特效 | `pixi/mascotConfig.js` `EXPRESSIONS` + `IDLE` | 配置表 |
| 动画时长 | `global.css` `--dur*` | token 段 |
| 玻璃配方 / 描边环 | `global.css` `--glass-*` / `--refract-ring` | component 段 |
| 场景 → 粒子强度 | `App.jsx` `intensityForScene` | 映射函数 |
| 下载请求/轮询 | `hooks/useDownload.js` + `api.js` | 编排 hook / API 窄接口 |
| 字幕、翻译、总结 | `hooks/useVideoInsights.js` + `api.js` | 独立状态 / API 窄接口 |
| 额度显示 | `components/ui/AuthBar.jsx` | 消费 `quota.unlimited` / `limit` / `remaining` |

## 10. 当前面板、账号额度与登录布局

- 视频智能面板以 AI 内容总结为主，字幕是来源；不扩展未授权的完整时间轴展示/导出。`VideoInsights.jsx` 接收 props，`useVideoInsights` 通过 `api.js` 请求；新操作会取消上一项视频智能请求，URL 改变时会清理旧结果。错误留在面板自己的状态中，下载 reducer 独立。
- 面板当前消费 `--insight-bg`、`--insight-result-bg`、`--insight-border`、`--insight-label-size`、`--insight-body-size`、`--insight-control-radius`。语言清单在 `state/insightConfig.js`；新增输出语言先扩充该注册表，再确认后端 API 接受对应值。
- 账号条的额度对象来自 `/api/auth/me`。只有 `quota.unlimited === true` 才显示“下载额度不限”；有限额度需同时有整数 `limit` 与 `remaining`。`null`、缺失或不完整字段表示前端没有可展示的额度，不应被解释成无限。
- 未登录时显示鉴权页。PIXI/Live2D 只在登录且 WebGL 可用后初始化；否则使用 CSS 背景降级。Preloader 只覆盖已登录后的 Live2D 模型加载期，不遮挡登录表单。
- 模型窄屏布局由 `MODELS[].mobile` 与 `getModelLayout` 配置；账号条、主题开关和选择卡布局由 CSS 负责。改固定控件后要检查重叠、水平溢出和键盘焦点。
- 本节描述源码当前行为，不复用历史浏览器验收结论；各日期、设备和覆盖范围见[文档索引](README.md)列出的报告。
