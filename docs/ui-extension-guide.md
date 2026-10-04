# UI 主题系统扩展指南（pidanai 深色液态玻璃 + 樱花粉辉光）

> 版本：v1（2026-09-24）· 对应 `docs/ui-refactor-pidanai.md`（分析）/ `docs/ui-refactor-pidanai-deep.md`（液态玻璃破译）
> 本文档回答「怎么加」，是阶段 3 交付的扩展指南：所有扩展点**数据驱动 / 改配置不改代码**，落地前先看 `docs/handoff.md` §2 解耦边界与工程约定。

---

## 0. 一句话原则

UI改动先用 `ui-ux-pro-max` + `design-system`，skill优先于旧计划；颜色/字体/时长token化，新增能力配置驱动，模块只通过窄接口单向通信。当前决策与状态以 [交接](handoff.md) 为准。

**颜色/字体/时长一律走 `:root` token；新增能力走「配置表」而非改渲染逻辑；视觉层只读 `scene` 状态，绝不 import 下载核心。** 改任何 UI，先判断「这是不是已有 token 的消费方」，是就直接用 token，不是就加 token 再消费。

---

## 1. 三层 token 体系（primitive → semantic → component）

单一来源 = `frontend/src/styles/global.css` 的 `:root`。组件层**只引用 semantic/component token**，不裸写 primitive 值。

| 层 | 前缀 / 例子 | 职责 | 改哪里 |
| --- | --- | --- | --- |
| L1 primitive | `--sakura-*`（7 阶）、`--ink-*`（4 阶）、`--refract-*`（5 色）、`--gray-*`（6 阶）+ `--cream` | 原始色板，只有这里出现 hex | `:root` |
| L2 semantic | `--accent` / `--surface` / `--text-*` / `--border*` / `--scrim` / `--shadow-*` | 语义化，组件只读这层 | `:root` + `[data-theme='light']` / `[data-theme='auto']` |
| L3 component | `--btn-*` / `--glass-*` / `--refract-ring` / `--font-*` / `--dur*` / `--card-radius` / `--pill-radius` | 具体组件的形态，换主题只改这层映射 | `:root`（如需跨主题覆盖再进主题块） |

**加一个 token 的正确顺序**：先想「它属于哪层」→ 加到 `:root` 对应段 → 组件里 `var(--新token, fallback)`。**禁止**在组件 `.jsx`/`.css` 里直接写 hex/rgba/字号/时长。

**PIXI 侧同步（关键坑）**：PIXI 不读 CSS，颜色收敛在 `frontend/src/pixi/theme.js` 的 `palette`（用 `cssVar('--xxx', fallback)` 运行时读 DOM token，jsdom 测试无 DOM 时走 fallback）。**凡 PIXI 要用的颜色必须 hex**（`pixi` 的 `hex()` 解析不了 `rgba()`/`color-mix()`，会静默回退成白色）——所以 `--accent-soft`/`--refract-*` 这类 PIXI 消费色在 CSS 里也保持 hex，不写 `color-mix`。

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

**PIXI 背景色注意**：`pixi/stage.js` 用 `backgroundColor: hex(baseColor)` + `backgroundAlpha: 0`（透明画布，深色底由 body CSS 渐变透出）。浅色主题下 PIXI 底色仍 `--ink-900`，但因 `backgroundAlpha:0` 实际显示的是 body 的浅色渐变——**背景底色以 body CSS 为准，PIXI 那行只是无 WebGL 兜底时的 fallback**。

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
- **Preloader 光点**：`components/ui/Preloader.jsx` 的 `SPOTS` 数组（`left/size/dur/delay/sway/color`，`color` 用 `var(--refract-*)`）。片数/位置/时长/横向幅度/折射色都在数组里调，**不改结构**。CSS 侧 `.preloader__spot` + `@keyframes preloader-drift`（位移用 `transform: translate3d`，不动画 width/height）。

**关键约束**：背景层是纯视觉层，`update` 只读 `delta/intensity`，**不感知下载状态**；`intensity` 由 `App.jsx` 的 `intensityForScene(state.scene)` 喂入（场景 → 强度映射），加场景强度映射改那个函数即可。

---

## 5. 加表情 / 道具 / 特效

全部在 `frontend/src/pixi/mascotConfig.js` 的 `EXPRESSIONS`（数据驱动，`ExpressionMenu.jsx` 只读渲染，不改逻辑）：

| 段 | 用途 | 加一个 |
| --- | --- | --- |
| `EXPRESSIONS.stage` | 场景 → 情绪参数（圈圈眼/煎蛋眼/星星眼/生气） | 加 `scene: paramId` 映射 |
| `EXPRESSIONS.random` | 每 ~20s 随机道具（手柄/话筒/戳脸） | 加 `{ paramId, … }` |
| `EXPRESSIONS.menu` | 换装菜单（发型/衣服/配饰/颜色/情绪，single/toggle/multi 分组） | 在对应 `group.options` 加 `{ paramId, name }`，`mode` 决定单选/复选 |
| `EXPRESSIONS.effect` | `edle.motion3.json` 装饰特效（按 `stages` 触发） | 命中 `stages` 的场景列表加场景名 |

- 完整版「白」46 个表情 = 单参数 `.exp3.json`，走 `coreModel.setParameterValueById(paramId, 1/0)` 直接写参数（**非** expression manager 单选），可任意多选并存，且与待机正弦驱动 `IDLE` 参数不重叠。
- 待机动画参数（`ParamAngleX/Y/Z` + `ParamBreath`）在 `mascotConfig.js` 的 `IDLE`（数据驱动，运行时按 `getParameterIndex` 过滤缺失参数）。

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

新增动画：先看有没有可复用的 `--dur-*`；没有则加一个语义化 token（注释写明用途），**不**在 keyframe 里直接写 `0.8s`。所有动画须尊重 `prefers-reduced-motion`（现有 reduced-motion 块已覆盖，新增动画要同步加禁用分支）。

---

## 7. 玻璃 + 折射描边环（复用的坑）

- **玻璃配方**：`--glass-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate))`，所有 `backdrop-filter` 统一引用它（含 `-webkit-` 孪生行）。加新玻璃面直接 `backdrop-filter: var(--glass-filter)`。
- **折射 1px 描边环**：伪元素 `::before` 涂 `--refract-ring` 渐变 + CSS `mask`（`mask-composite: exclude` / `-webkit-mask-composite: xor`）只留 1px 环，不遮玻璃底、不动 backdrop-filter。`@supports (mask-composite)` 兜底（不支持回退原 `border`）。滚动面板（如表情菜单）用**淡描边**替代彩虹环（规避滚动时环错位），见 `.expression-menu` 的 `color-mix(var(--refract-violet) 26%, var(--border))`。
- **`backdrop-filter` 祖先链大坑**：祖先元素一旦 `opacity<1` / `transform` / `filter` / `overflow:hidden`，玻璃会**静默失效**。改任何玻璃面，先检查祖先链（详见 `docs/ui-refactor-pidanai.md` 风险清单 + 逐模块截图巡检铁律）。

---

## 8. 解耦铁律（违反即破坏扩展性）

1. **视觉表现层只读 `scene`**：`pixi/*`、`components/ui/*`、`Preloader`、`ExpressionMenu` 只消费 `scene` 状态，**绝不修改下载状态、绝不 import 下载核心**（`api.js` 下载逻辑 / `sceneMachine.reduce` 下载状态）。
2. **PIXI 侧颜色单一来源 = CSS token**：`theme.js` 只做运行时桥接（`cssVar` + fallback），不改动 token 语义。
3. **后端 `ytdlp_service.py` 是唯一接触 yt-dlp 的层**；前端视觉层与下载核心通过「场景状态」单向解耦。
4. **改配置不改代码**：新增能力 = 加配置表条目（`THEMES` / `FX` / `SPOTS` / `EXPRESSIONS` / `--dur-*` / `--refract-*`），不推倒渲染逻辑。

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

## 10. 当前v3面板与登录/移动布局

- 视频智能面板的主目标是AI内容总结，字幕作为来源；不要因为辅助字幕读取而扩展未授权的完整时间轴展示/导出。
- `VideoInsights.jsx` 仅消费props；`useVideoInsights` 通过 `api.js` 请求，取消过期请求，下载reducer不变。
- 面板消费 `--insight-bg` / `--insight-result-bg` / `--insight-border` / `--insight-label-size` / `--insight-body-size` / `--insight-control-radius`，新增样式复用或扩展token。
- 登录前不启动PIXI/Live2D重资源；登录后才初始化。预加载层不得遮住登录表单。
- 模型窄屏布局由 `MODELS[].mobile` 与 `getModelLayout` 配置；账号条、主题开关和选择卡有移动端间距，改固定控件后需检查重叠和水平溢出。
