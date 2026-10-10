# 霓虹二次元主题 · Token 规范

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。
> 文档状态（2026-10-03整理）：**历史参考**。旧霓虹主题规范；当前主题已替换为深色液态玻璃/樱花粉/折射色token，本文色值不是当前真源。当前状态见 [交接](../../handoff.md)。
> 工程约定仍适用：UI先用 `ui-ux-pro-max` + `design-system`；skill优先于旧计划；颜色/字体/时长token化、能力数据与配置驱动；yt-dlp仅经 `ytdlp_service.py`，视觉只读scene，不修改下载核心。

- 日期：2026-09-22
- 状态：已落地（Task 3）
- 载体：`frontend/src/styles/global.css`（`:root`）+ `frontend/index.html`（Google Fonts）

## 一、设计目标

「霓虹色彩 token 系统 + UI 二次元语言」：把零散写死的色值收敛为三层 token，
统一改名为 `--neon-*` 前缀，并落地二次元 UI 动效语言（彩虹描边 / 光晕 / 流光 / 速度线 / 斜切角 / 全息弹幕）。

## 二、Token 三层结构

### L1 原始色值（primitive）

| 色值 | 名称 | 用途 |
| --- | --- | --- |
| #06060f | 深空黑 | 全局底色 |
| #0d1b3e | 午夜蓝 | 兜底渐变中段 |
| #1a0f3a | 暗紫 | 兜底渐变过渡 |
| #ff2d95 | 霓虹洋红 | 主强调 |
| #2f7bff | 霓虹蓝 | 主强调 |
| #22d3ee | 霓虹青 | 辅助 |
| #a3e635 | 霓虹青柠 | 辅助 |
| #fbbf24 | 霓虹琥珀 | 庆祝/警示 |
| #ff6b4a | 霓虹珊瑚 | 危险/庆祝 |
| #8b5cf6 | 霓虹紫 | 极光渐变 |
| #34d399 | 霓虹薄荷 | 全息渐变 |
| #ff4dd8 | 镭射粉 | 全息渐变端点 |

### L2 语义 token（semantic，`:root` 变量）

| 变量 | 值 | 说明 |
| --- | --- | --- |
| `--bg-deep` | #06060f | 主背景（原 #0b0f2a，已改值） |
| `--bg-midnight` | #0d1b3e | 新增 |
| `--bg-purple` | #1a0f3a | 新增 |
| `--neon-magenta` | #ff2d95 | 由 `--neon-pink` 改名 |
| `--neon-blue` | #2f7bff | 改值（原 #22d3ee，实为青色） |
| `--neon-cyan` | #22d3ee | 新增，承接旧 `--neon-blue` 值 |
| `--neon-lime` | #a3e635 | 不变 |
| `--neon-amber` | #fbbf24 | 由 `--amber` 改名 |
| `--neon-coral` | #ff6b4a | 新增 |
| `--neon-violet` | #8b5cf6 | 新增 |
| `--neon-mint` | #34d399 | 新增 |
| `--laser-pink` | #ff4dd8 | 新增 |
| `--grad-aurora` | linear-gradient(120deg, magenta, violet, blue, cyan, magenta) | 极光带（可复用于弹幕/描边） |
| `--grad-holo` | linear-gradient(90deg, laser-pink, cyan, mint, violet, amber, laser-pink) | 全息（弹幕/彩虹描边） |
| `--font-display` | 'Orbitron', 'JetBrains Mono', system-ui, ... | 数字/HUD 字体（时长、清晰度） |
| `--font-mono` | 'JetBrains Mono', system-ui, ... | 等宽字体（URL 输入） |
| `--font-body` | "PingFang SC", "Microsoft YaHei", system-ui, ... | 正文/标题 |
| `--on-neon` | #06060f | 霓虹底上的文字色（对比度 ≥ 4.5:1） |

### L3 组件映射（component）

| 组件 / 类 | 使用的 token |
| --- | --- |
| `body` | `--bg-deep` + `--font-body` |
| `.css-fallback` | `--bg-deep` / `--bg-purple` / `--bg-midnight` + 紫蓝径向光 |
| `.laser-frame` | `--bg-deep` + `--neon-magenta`/`--neon-blue`/`--neon-lime`（border-box 渐变） |
| `.rainbow-outline` | `--bg-deep` + `--grad-holo`（border-box） |
| `.danmaku` | `--grad-holo` + `--neon-cyan` 光晕 |
| `.energy-bar-fill` | `--neon-magenta`/`--neon-blue`/`--neon-lime` + 流光 `::after` |
| `.magic-circle` | `--neon-blue`（外）/`--neon-magenta`（内） |
| `.model-toast` | `--neon-magenta` 光晕 |
| `button`（通用） | `--neon-magenta`→`--neon-blue` 渐变 + `--on-neon` 文字 |
| `button.laser-frame` | `--on-neon` 例外：深底描边按钮保持白字 |
| `.format-list button` | `--font-display` 字体 |
| `.format-list button.selected` | `--neon-magenta` 光晕 |
| `.badge-switch` | `--neon-blue` 边框 / `--neon-magenta` accent |
| `.done-bubble` | `--neon-amber` + `--neon-coral` 庆祝光晕 |
| `.error-bubble` | 洋红危险光晕（err-* 场景动画覆盖） |
| `.duration` | `--font-display` 字体 |
| `.entry-scene input` | `--font-mono` 字体 / focus `--neon-blue` |

## 三、Token 改名对照表（完整）

| 旧变量 | 新变量 | 值变化 | 状态 |
| --- | --- | --- | --- |
| `--neon-pink` | `--neon-magenta` | #ff2d95（不变） | 改名 |
| `--amber` | `--neon-amber` | #fbbf24（不变） | 改名 |
| `--neon-blue` | `--neon-blue` | #22d3ee → #2f7bff | 改值 |
| （无） | `--neon-cyan` | #22d3ee | 新增（承接旧 blue 值） |
| `--bg-deep` | `--bg-deep` | #0b0f2a → #06060f | 改值 |
| （无） | `--bg-midnight` / `--bg-purple` / `--neon-coral` / `--neon-violet` / `--neon-mint` / `--laser-pink` / `--grad-aurora` / `--grad-holo` | — | 新增 |

> 同步范围：仅 `global.css` 引用这些变量（已 grep 确认）；`background.js` 的粒子/渐变仍用硬编码 hex（属 Task 4 范围，本次未动）。

## 四、字体

| 字体 | 权重 | 用途 | fallback 栈 |
| --- | --- | --- | --- |
| Orbitron | 700;900 | 时长 `.duration`、清晰度 `.format-list button` | `'Orbitron', 'JetBrains Mono', system-ui, -apple-system, sans-serif` |
| JetBrains Mono | 400;500 | URL 输入 `.entry-scene input` | `'JetBrains Mono', system-ui, -apple-system, sans-serif` |
| 中文（系统） | — | 正文/标题 | `"PingFang SC", "Microsoft YaHei", system-ui, -apple-system, "Segoe UI", sans-serif` |

- 加载：`index.html` 中 `preconnect`（googleapis + gstatic crossorigin）+ `display=swap`。
- 离线/被拦截时回落系统字体栈，布局不变。

## 五、动效语言

| 效果 | 实现 |
| --- | --- |
| 彩虹描边 | `.rainbow-outline`（`--grad-holo` border-box） |
| 激光描边（静态） | `.laser-frame`（border-box 渐变，**已移除 hue-rotate 常驻动画**，见「动效克制」） |
| 全息弹幕 | `.danmaku`（`--grad-holo` + 光晕） |
| 能量条流光 | `.energy-bar-fill::after`（shimmer 1.8s） |
| 按钮速度线 | `button:not(.float-on-hover)::before`（hover 斜向扫过 .35s） |
| 清晰度按钮 RGB 分离 | `.float-on-hover:hover`（洋红/蓝/薄荷三色错位光晕） |
| 卡片斜切角 | `.format-card`（clip-path 六边形斜切） |
| 气泡场景配色 | `.done-bubble`（琥珀+珊瑚庆祝光晕）/ `.error-bubble`（洋红危险光晕） |
| 极光兜底 | `.css-fallback`（多 stop 极光 + 径向光斑） |

## 六、无障碍

- 键盘焦点：全局 `:focus-visible { outline: 2px solid var(--neon-cyan); outline-offset: 2px }`。
- 文字对比度：按钮霓虹底改用 `--on-neon`（#06060f，≥ 4.5:1 AA）；深底描边按钮（`.laser-frame`）保持白字。
- `@media (prefers-reduced-motion: reduce)` 关闭：魔法阵呼吸、能量条流光、按钮速度线、错误场景呼吸/灰暗。

## 七、工程约定（每次遵守）

> 与根目录 `CLAUDE.md` 一致，最高优先级。

1. **UI 必须用 skill**：涉及配色/字体/动效/无障碍/组件时，先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准。本 Task 据此把计划里的 `.laser-frame` 常驻 hue-rotate 动画改为静态描边（遵守「每屏最多动 1–2 个关键元素」）。
3. **不写死、保留扩展**：颜色/字体/时长一律走 `:root` token（含 `--font-*`、`--on-neon`），不散落硬编码；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。
