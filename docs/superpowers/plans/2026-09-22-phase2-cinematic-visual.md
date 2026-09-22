# 第二阶段：电影感视觉升级 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把前端从「炫彩工具页」升级为「可交互的二次元短篇体验」——对照参考站 2019.makemepulse.com 补齐 6 项「电影感」手法（蒙版揭幕 + 虹膜转场、几何画框、章节台词、自定义光标、分段分层按钮、缠绕式进度），全部映射到二次元风格，且**不触碰下载核心**。

**Architecture:** 在既有「单一 PIXI 管线 + DOM UI 叠加」上新增一个视觉表现层 `frontend/src/fx/`（转场/光标纯配置）与 `frontend/src/components/ui/`（字幕/画框/转场覆盖层/光标/分段按钮/缠绕进度）。所有 fx 模块**只读**场景状态（`scene`），绝不修改 `sceneMachine.reduce` 的下载状态、绝不 import `api.js` 的下载逻辑。台词/转场/光标/进度全部配置外置、数据驱动——后续扩展（新场景、新错误、v3 总结台词注入、主题切换）改配置不改代码。

**Tech Stack:** React 18 + Vite 8 + CSS（clip-path / transform / SVG）+ 现有 PIXI v6（仅复用，不新增渲染库）。**不引入任何新依赖**。

**Spec:** `docs/requirements.md §9`（第二阶段需求基准）；`docs/design.md §13`（视觉表现层架构 + 扩展点）。
**契约基准 / 基线:** `docs/superpowers/specs/2026-09-20-frontend-experience-design.md`（v1 视觉基准）；`frontend/src/state/sceneMachine.js`（`SCENE` / `ERROR_SCENES`）；`docs/superpowers/plans/2026-09-21-frontend-experience.md`（v1 已实现，本计划在其之上叠加）。

---

## Global Constraints

1. **核心流程优先（端到端可运行、可验证）**：每个 Task 落地后都必须保持「解析 → 选清晰度 → 下载」主链路完整可用；任何视觉/动效卡顿或失效都**不得阻塞下载**。每个 Task 结束都要 `npm test` 全绿 + 手工冒烟主链路（见 Task 7 验收清单）。
2. **视觉层与下载核心单向解耦**：视觉表现层只读 `scene`，不得 import `api.js` 的下载逻辑、不得改 `sceneMachine.reduce` 的下载状态；下载核心不得依赖视觉层。二者通过「场景状态」解耦。
3. **数据驱动、配置外置（不写死核心逻辑）**：台词/转场/光标/进度全部抽成注册表或 props；新增场景/错误/转场 = 加一条配置，不改渲染逻辑。
4. **避免过度设计（YAGNI）**：不为 v1 用不到的抽象建层；能用 DOM/CSS 做的（转场/光标/字幕/画框）不引入 PIXI 或新库；每个组件只有一个职责。
5. **降级策略**：`prefers-reduced-motion` 关闭转场/光标动画；「轻量模式」/ 低端机（`detectTier()==='low'`）跳过 canvas 光标、简化转场；移动端触摸隐藏光标。纯 DOM 的字幕/画框始终保留。
6. **继承 v1 约束**：PIXI v6 锁版 + `pixi-live2d-display@0.4`；单一 PIXI 管线；角色非商用不二传二改；`ERROR_SCENES` 9 类错误不增删语义。
7. 提交信息沿用约定：`feat(frontend):` / `fix(frontend):` / `test(frontend):` / `chore(frontend):`。

### 关键裁决（记录）

- **P2-1（不新增渲染库）**：6 项手法全部用 DOM/CSS/SVG + 复用现有 PIXI 实现。转场用「React 覆盖层 + CSS 动画」而非 PIXI 内实现——转场属 DOM 层职责，与场景组件同层、简单可测；自定义光标用 DOM 元素跟随 `pointermove`（等价于参考站的 canvas 光标，但更省、可测），低端机/触摸直接不启用。
- **P2-2（台词 vs 错误文案）**：`scriptConfig.js` 的台词是「底部叙事字幕」（电影感），与 `sceneMachine.ERROR_SCENES`（气泡标题/提示）是**两层互补**，不重复、不替换。
- **P2-3（进度组件）**：`PathProgress` 用 SVG `pathLength="1"` 归一化，`stroke-dashoffset` 直接 0..1，免去路径长度计算。
- **P2-4（转场语义）**：转场是「覆盖层遮住 → 揭开」的进场效果：新场景先渲染在底层，覆盖层在其上播放揭开动画后卸载。`iris` = 中心圆扩张 + 淡出；`maskReveal` = 深色幕布右移擦除。
- **P2-5（扩展锚点）**：`SCENE_SCRIPT` / `SCENE_TRANSITION` / `SCENE_CURSOR` 三个注册表 + `PathProgress` 通用组件是第二阶段的扩展锚点，供 v3（总结/翻译台词注入、更多进度）与主题切换复用。

### 参考站实测细节（2026-09-22 playwright 复核）

> 用 Playwright 走通参考站 2019.makemepulse.com 的「Start → 章节」交互，运行时实测比纯 DOM 抓取多出以下细节，供实现时对照。**仅作参考，不照搬**：我们是 React 状态机 + DOM/CSS/SVG，参考站是 WebGL 全 canvas。

| 参考站实测 | 记录 | 本计划处置 |
| --- | --- | --- |
| 章节台词 | 首章原文「Today is a big day for our tribe. The year ends… It is time to leave the island.」；`.subtitles` 带 `anim-letter`（**逐字揭示**）+ `position_0`/`position_1`（**多行堆叠**），`hidden` 控制每行显隐 | 台词风格已对齐（短句叙事）；逐字动画/多行堆叠本阶段 **YAGNI 不做**，登记为后续扩展点（见 design §13.2） |
| 字体 | `Noto Sans SC`（CJK 无衬线，参考站即便英文内容也加载了 CJK 字体） | 我方中文/二次元已自带字体栈，不新增 |
| 光标 | 150×150 canvas 元素 | 我方改用 DOM glyph 光标（更省、可测），尺寸按需 CSS 调 |
| 进度 | `.loader` > `.loader__bar` > `.loader__bar__inner` > `{ .loader__bar__background, .loader__bar__foreground }`（垂直缠绕条，bg/fg 两层） | 已映射为 `PathProgress` 的 `track`/`fill` 两条 path，建模一致 |
| 按钮 | `.button-xp`（`--top` 位置变体）+ `is-hidden` 显隐态，左/中/右三段 bg+fg | 已映射为 `SegmentedButton` 三段 `.seg` + `__label` |
| 场景状态 | 用 body class（`body-landing` 等）驱动场景显隐 | 我方用 React 场景状态机（`sceneMachine`）等价，不照搬 |

---

## 文件结构

```
frontend/src/
├── state/
│   ├── sceneMachine.js          # v1：不动
│   └── scriptConfig.js          # 新增：章节台词配置（SCENE_SCRIPT + ERROR_SCRIPT）
├── fx/                          # 新增：电影感表现层（纯配置/纯函数）
│   ├── transitions.js           #   SCENE_TRANSITION + TRANSITION_TYPES + transitionForScene()
│   └── cursor.js                #   SCENE_CURSOR + cursorForScene()
├── components/ui/               # 新增 UI 组件
│   ├── Subtitle.jsx             #   章节台词字幕条
│   ├── Frame.jsx                #   几何画框（四角括号）
│   ├── TransitionOverlay.jsx    #   转场覆盖层（按 scene 播动画）
│   ├── Cursor.jsx               #   自定义动画光标（DOM，跟随 pointermove）
│   ├── SegmentedButton.jsx      #   分段分层主按钮
│   └── PathProgress.jsx         #   缠绕式进度（SVG path）
├── components/                  # v1 场景组件：EntryScene 换用 SegmentedButton、DownloadingScene 换用 PathProgress
└── App.jsx                      # 挂载字幕/画框/转场/光标（与既有 stage/mascot 并列）
```

---

## Task 1: 章节台词系统（scriptConfig + 字幕条）

> 数据驱动的「章节台词」：每个场景/错误类型一句台词，底部字幕条展示。这是叙事感的骨架，纯数据 + 纯 DOM，风险最低，先落地。

**Files:**
- Create: `frontend/src/state/scriptConfig.js`, `frontend/src/components/ui/Subtitle.jsx`
- Modify: `frontend/src/App.jsx`（渲染 `<Subtitle>`）
- Test: `frontend/src/state/scriptConfig.test.js`

**Interfaces:**
- Consumes: `sceneMachine.js` 的 `SCENE`、`ERROR_SCENES`（键集合）。
- Produces: `scriptConfig.js` 的 `SCENE_SCRIPT`、`ERROR_SCRIPT`；`Subtitle.jsx` 的 props `{ scene, errorType }`。

- [ ] **Step 1: 写 scriptConfig.js（数据驱动，核心扩展点）**

`frontend/src/state/scriptConfig.js`:
```js
import { SCENE } from './sceneMachine.js';

// 章节台词（底部叙事字幕）：新增场景 = 加一条，不改渲染。
// 与 sceneMachine.ERROR_SCENES（气泡标题/提示）是两层互补，不重复。
export const SCENE_SCRIPT = {
  [SCENE.ENTRY]:       { line: '把链接交给魔法阵，开启旅程吧。' },
  [SCENE.PARSING]:     { line: '正在聆听链接的低语…' },
  [SCENE.SELECTING]:   { line: '选一档你想要的清晰度。' },
  [SCENE.DOWNLOADING]: { line: '精灵正努力搬运视频中…' },
  [SCENE.DONE]:        { line: '完成啦，收好你的视频！' },
  [SCENE.ERROR]:       { line: '唔…好像遇到了一点麻烦。' },
};

// 错误类型 → 字幕台词（键与 ERROR_SCENES 一致，覆盖 design §8 的 9 种）
export const ERROR_SCRIPT = {
  invalid_url:      '这条链接看起来不太对呢。',
  unsupported_site: '这个站点我还不会。',
  age_restricted:   '这里需要成年认证。',
  geo_blocked:      '你所在的地区暂时打不开。',
  drm:              '这段内容被保护起来了。',
  login_required:   '需要先登录才能下载。',
  ffmpeg_missing:   '服务器缺了点零件。',
  network:          '网络好像断了。',
  quota:            '今天搬得太多了，歇一歇吧。',
};
```

- [ ] **Step 2: 写测试，验证覆盖全场景 + 全错误类型**

`frontend/src/state/scriptConfig.test.js`:
```js
import { describe, it, expect } from 'vitest';
import { SCENE_SCRIPT, ERROR_SCRIPT } from './scriptConfig.js';
import { SCENE, ERROR_SCENES } from './sceneMachine.js';

describe('scriptConfig 章节台词', () => {
  it('每个场景都有台词', () => {
    for (const s of Object.values(SCENE)) expect(SCENE_SCRIPT[s]).toBeTruthy();
  });
  it('每种错误类型都有台词，且与 ERROR_SCENES 键一致', () => {
    for (const k of Object.keys(ERROR_SCENES)) expect(ERROR_SCRIPT[k]).toBeTruthy();
    // 不多不少：不引入 ERROR_SCENES 之外的错误键
    expect(Object.keys(ERROR_SCRIPT).sort()).toEqual(Object.keys(ERROR_SCENES).sort());
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/state/scriptConfig.test.js`
Expected: FAIL（`scriptConfig.js` 尚不存在）。

- [ ] **Step 4: 写 Subtitle.jsx**

`frontend/src/components/ui/Subtitle.jsx`:
```jsx
import React from 'react';
import { SCENE_SCRIPT, ERROR_SCRIPT } from '../../state/scriptConfig.js';
import { SCENE } from '../../state/sceneMachine.js';

// 底部叙事字幕条：只读 scene/errorType，不感知下载。
export default function Subtitle({ scene, errorType }) {
  const line = scene === SCENE.ERROR
    ? (ERROR_SCRIPT[errorType] || ERROR_SCRIPT.network)
    : (SCENE_SCRIPT[scene] || SCENE_SCRIPT[SCENE.ENTRY]).line;
  return <div className="subtitle" data-testid="subtitle" aria-live="polite">{line}</div>;
}
```

在 `global.css` 增加（纯装饰，`pointer-events:none`）：
```css
.subtitle {
  position: fixed; left: 50%; bottom: 56px; transform: translateX(-50%);
  z-index: 5; max-width: 80vw; padding: 8px 20px;
  font-size: 14px; color: rgba(245,246,255,.85);
  background: rgba(11,15,42,.55); border: 1px solid rgba(255,255,255,.14);
  border-radius: 999px; backdrop-filter: blur(4px);
  text-align: center; pointer-events: none;
  transition: opacity .3s ease;
}
```

- [ ] **Step 5: 在 App 挂载字幕**

在 `App.jsx` 的根节点（`.ui` 之后）加：
```jsx
<Subtitle scene={state.scene} errorType={state.error?.error_type} />
```
并在文件顶部 `import Subtitle from './components/ui/Subtitle.jsx';`

- [ ] **Step 6: 跑全部测试 + 提交**

Run: `cd frontend && npm test`
```bash
git add frontend/src/state/scriptConfig.js frontend/src/state/scriptConfig.test.js frontend/src/components/ui/Subtitle.jsx frontend/src/App.jsx frontend/src/styles/global.css
git commit -m "feat(frontend): 章节台词系统（scriptConfig + 底部字幕条）"
```

---

## Task 2: 几何画框（Frame）

> 四角括号 + 边缘渐变构成的「漫画分格」画框，纯装饰、不拦截交互。为后续「主题切换」预留：配色走 CSS 变量。

**Files:**
- Create: `frontend/src/components/ui/Frame.jsx`
- Modify: `frontend/src/App.jsx`（渲染 `<Frame />`）、`frontend/src/styles/global.css`
- Test: `frontend/src/components/ui/Frame.test.jsx`

**Interfaces:**
- Produces: `Frame.jsx`（无 props，纯装饰组件，`aria-hidden`）。

- [ ] **Step 1: 写 Frame.jsx**

`frontend/src/components/ui/Frame.jsx`:
```jsx
import React from 'react';

// 几何画框：四角括号 + 边缘，纯装饰（aria-hidden + pointer-events:none）。
// 配色集中在 :root 变量（--frame-edge），后续主题切换只换变量。
export default function Frame() {
  return (
    <div className="frame" aria-hidden="true">
      <span className="frame__corner frame__corner--tl" />
      <span className="frame__corner frame__corner--tr" />
      <span className="frame__corner frame__corner--bl" />
      <span className="frame__corner frame__corner--br" />
    </div>
  );
}
```

在 `global.css` 增加：
```css
:root { --frame-edge: rgba(34,211,238,.5); }
.frame { position: fixed; inset: 12px; z-index: 3; pointer-events: none; }
.frame__corner { position: absolute; width: 28px; height: 28px; border: 2px solid var(--frame-edge); }
.frame__corner--tl { top: 0; left: 0; border-right: none; border-bottom: none; }
.frame__corner--tr { top: 0; right: 0; border-left: none; border-bottom: none; }
.frame__corner--bl { bottom: 0; left: 0; border-right: none; border-top: none; }
.frame__corner--br { bottom: 0; right: 0; border-left: none; border-top: none; }
```

- [ ] **Step 2: 写测试**

`frontend/src/components/ui/Frame.test.jsx`:
```jsx
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import Frame from './Frame.jsx';

describe('Frame 几何画框', () => {
  it('渲染 4 个角，且对辅助技术隐藏', () => {
    const { container } = render(<Frame />);
    expect(container.querySelectorAll('.frame__corner')).toHaveLength(4);
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true');
  });
});
```

- [ ] **Step 3: 在 App 挂载画框 + 跑测试 + 提交**

在 `App.jsx` 根节点加 `<Frame />`（在 `.stage` 之后、`.ui` 之前或之后均可，z-index 决定层级）。

Run: `cd frontend && npm test`
```bash
git add frontend/src/components/ui/Frame.jsx frontend/src/components/ui/Frame.test.jsx frontend/src/App.jsx frontend/src/styles/global.css
git commit -m "feat(frontend): 几何画框（四角括号，主题变量预留）"
```

---

## Task 3: 转场系统（蒙版揭幕 + 虹膜转场）

> 场景切换的「电影感」核心：一个覆盖层在新场景之上播放揭开动画。纯函数 `transitionForScene` 是唯一逻辑核心，可单测；视觉是 CSS 动画。

**Files:**
- Create: `frontend/src/fx/transitions.js`, `frontend/src/components/ui/TransitionOverlay.jsx`
- Modify: `frontend/src/App.jsx`（渲染 `<TransitionOverlay scene={state.scene} />`）、`frontend/src/styles/global.css`
- Test: `frontend/src/fx/transitions.test.js`

**Interfaces:**
- Consumes: `sceneMachine.SCENE`。
- Produces: `transitions.js` 的 `SCENE_TRANSITION`、`TRANSITION_TYPES`、`transitionForScene(scene, { reduceMotion }) → { type, duration }`。

- [ ] **Step 1: 写 transitions.js（注册表 + 纯函数，核心扩展点）**

`frontend/src/fx/transitions.js`:
```js
import { SCENE } from '../state/sceneMachine.js';

// 转场注册表：scene → 转场效果（数据驱动；新增转场样式加 CSS，新增场景加条目）
export const SCENE_TRANSITION = {
  [SCENE.ENTRY]:       { type: 'maskReveal', duration: 900 },
  [SCENE.PARSING]:     { type: 'iris',       duration: 700 },
  [SCENE.SELECTING]:   { type: 'iris',       duration: 700 },
  [SCENE.DOWNLOADING]: { type: 'iris',       duration: 700 },
  [SCENE.DONE]:        { type: 'iris',       duration: 900 },
  [SCENE.ERROR]:       { type: 'iris',       duration: 900 },
};

// 可用转场类型（新增转场 = 加类型 + 对应 CSS 动画）
export const TRANSITION_TYPES = ['maskReveal', 'iris', 'none'];

// 纯函数：根据 scene 与 reduceMotion 决定转场；降级时返回 none
export function transitionForScene(scene, opts = {}) {
  if (opts.reduceMotion) return { type: 'none', duration: 0 };
  return SCENE_TRANSITION[scene] || { type: 'none', duration: 0 };
}
```

- [ ] **Step 2: 写测试**

`frontend/src/fx/transitions.test.js`:
```js
import { describe, it, expect } from 'vitest';
import { SCENE_TRANSITION, TRANSITION_TYPES, transitionForScene } from './transitions.js';
import { SCENE } from '../state/sceneMachine.js';

describe('transitions 转场系统', () => {
  it('每个场景都有转场映射，且类型合法', () => {
    for (const s of Object.values(SCENE)) {
      const t = SCENE_TRANSITION[s];
      expect(t).toBeTruthy();
      expect(TRANSITION_TYPES).toContain(t.type);
    }
  });
  it('TRANSITION_TYPES 无重复', () => {
    expect(new Set(TRANSITION_TYPES).size).toBe(TRANSITION_TYPES.length);
  });
  it('reduceMotion 时退化为 none', () => {
    expect(transitionForScene(SCENE.PARSING, { reduceMotion: true }).type).toBe('none');
  });
  it('未知场景回退 none', () => {
    expect(transitionForScene('__unknown__').type).toBe('none');
  });
});
```

- [ ] **Step 3: 写 TransitionOverlay.jsx**

`frontend/src/components/ui/TransitionOverlay.jsx`:
```jsx
import React, { useMemo } from 'react';
import { transitionForScene } from '../../fx/transitions.js';

// 转场覆盖层：场景切换时在新场景之上播一次揭开动画，动画结束由 CSS forwards 定格（不可见）。
// 用 key={scene} 让 React 在场景变化时重挂载，重放动画。
const reduceMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export default function TransitionOverlay({ scene }) {
  const { type } = useMemo(() => transitionForScene(scene, { reduceMotion: reduceMotion() }), [scene]);
  if (type === 'none') return null;
  return (
    <div key={scene} className={`transition-overlay ${type}`} aria-hidden="true">
      {type === 'iris' && <span className="transition-iris" />}
    </div>
  );
}
```

在 `global.css` 增加：
```css
.transition-overlay {
  position: fixed; inset: 0; z-index: 20; display: grid; place-items: center;
  pointer-events: none; background: var(--bg-deep);
}
/* iris：中心圆从 0 扩张到覆盖，再淡出 */
.transition-iris {
  width: 70vmax; height: 70vmax; border-radius: 50%;
  background: var(--bg-deep); transform: scale(0);
}
.transition-overlay.iris { background: transparent; animation: iris-fade 700ms ease-out forwards; }
.transition-overlay.iris .transition-iris { animation: iris-grow 700ms ease-out forwards; }
@keyframes iris-grow { to { transform: scale(1); } }
@keyframes iris-fade { 0%,80% { opacity: 1; } 100% { opacity: 0; } }
/* maskReveal：深色幕布右移擦除 */
.transition-overlay.maskReveal { animation: mask-wipe 900ms ease-out forwards; }
@keyframes mask-wipe { from { transform: translateX(0); } to { transform: translateX(100%); } }
```

> 注意：`iris` 覆盖层为透明背景 + 中心深色圆扩张，动画结束后 `iris-fade` 把整层淡出；`maskReveal` 整层右移擦除。两者都让底层已渲染好的新场景「揭开」。

- [ ] **Step 4: 在 App 挂载转场覆盖层 + 跑测试 + 提交**

在 `App.jsx` 根节点加 `<TransitionOverlay scene={state.scene} />`，并 `import TransitionOverlay from './components/ui/TransitionOverlay.jsx';`

Run: `cd frontend && npm test`
```bash
git add frontend/src/fx/transitions.js frontend/src/fx/transitions.test.js frontend/src/components/ui/TransitionOverlay.jsx frontend/src/App.jsx frontend/src/styles/global.css
git commit -m "feat(frontend): 转场系统（蒙版揭幕 + 虹膜转场，reduceMotion 降级）"
```

---

## Task 4: 自定义动画光标（Cursor）

> 光标随场景变样（解析=圈圈、完成=比心…），强化「进入世界」感。DOM 元素跟随 `pointermove`，纯函数 `cursorForScene` 可单测；触摸/低端机不启用。

**Files:**
- Create: `frontend/src/fx/cursor.js`, `frontend/src/components/ui/Cursor.jsx`
- Modify: `frontend/src/App.jsx`（条件渲染 `<Cursor scene={state.scene} enabled={…} />`）、`frontend/src/styles/global.css`
- Test: `frontend/src/fx/cursor.test.js`

**Interfaces:**
- Consumes: `sceneMachine.SCENE`。
- Produces: `cursor.js` 的 `SCENE_CURSOR`、`cursorForScene(scene) → { glyph, color }`。

- [ ] **Step 1: 写 cursor.js（配置 + 纯函数）**

`frontend/src/fx/cursor.js`:
```js
import { SCENE } from '../state/sceneMachine.js';

// 光标形态配置：scene → 字形 + 颜色（数据驱动；新增场景加条目）
export const SCENE_CURSOR = {
  [SCENE.ENTRY]:       { glyph: '✦', color: '#22d3ee' },
  [SCENE.PARSING]:     { glyph: '◌', color: '#a3e635' },
  [SCENE.SELECTING]:   { glyph: '✧', color: '#ff2d95' },
  [SCENE.DOWNLOADING]: { glyph: '➤', color: '#22d3ee' },
  [SCENE.DONE]:        { glyph: '♥', color: '#ff2d95' },
  [SCENE.ERROR]:       { glyph: '✖', color: '#fbbf24' },
};

export function cursorForScene(scene) {
  return SCENE_CURSOR[scene] || SCENE_CURSOR[SCENE.ENTRY];
}
```

- [ ] **Step 2: 写测试**

`frontend/src/fx/cursor.test.js`:
```js
import { describe, it, expect } from 'vitest';
import { SCENE_CURSOR, cursorForScene } from './cursor.js';
import { SCENE } from '../state/sceneMachine.js';

describe('cursor 自定义光标', () => {
  it('每个场景都有光标形态', () => {
    for (const s of Object.values(SCENE)) expect(SCENE_CURSOR[s]).toBeTruthy();
  });
  it('未知场景回退 entry', () => {
    expect(cursorForScene('__unknown__')).toEqual(SCENE_CURSOR[SCENE.ENTRY]);
  });
});
```

- [ ] **Step 3: 写 Cursor.jsx**

`frontend/src/components/ui/Cursor.jsx`:
```jsx
import React, { useEffect, useRef } from 'react';
import { cursorForScene } from '../../fx/cursor.js';

// 自定义光标：DOM 元素跟随 pointermove；移动端无鼠标时系统光标即可（enabled=false 不渲染）。
export default function Cursor({ scene, enabled }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    const move = (e) => {
      el.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0)`;
    };
    window.addEventListener('pointermove', move);
    return () => window.removeEventListener('pointermove', move);
  }, [enabled]);

  if (!enabled) return null;
  const { glyph, color } = cursorForScene(scene);
  return (
    <div ref={ref} className="custom-cursor" aria-hidden="true" style={{ color }}>
      {glyph}
    </div>
  );
}
```

在 `global.css` 增加：
```css
.custom-cursor {
  position: fixed; left: 0; top: 0; z-index: 30; pointer-events: none;
  font-size: 20px; line-height: 1; transform: translate3d(-100px,-100px,0);
  transition: color .3s ease; will-change: transform;
}
/* 隐藏系统光标，让自定义光标独占 */
body.custom-cursor-on, body.custom-cursor-on * { cursor: none; }
```

- [ ] **Step 4: 在 App 条件挂载光标 + 跑测试 + 提交**

在 `App.jsx` 加（`tier` 已存在；移动端由 `detectTier` 归入 `low`）：
```jsx
const isTouch = typeof window !== 'undefined' && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
<Cursor scene={state.scene} enabled={!isTouch && tier !== 'low' && !lightMode} />
```
并在 `useEffect` 里按 `enabled` 给 `document.body` 加/去 `custom-cursor-on` 类。

Run: `cd frontend && npm test`
```bash
git add frontend/src/fx/cursor.js frontend/src/fx/cursor.test.js frontend/src/components/ui/Cursor.jsx frontend/src/App.jsx frontend/src/styles/global.css
git commit -m "feat(frontend): 自定义动画光标（场景驱动，触摸/低端机禁用）"
```

---

## Task 5: 分段分层按钮（SegmentedButton）

> 参考站「Start」按钮：左/中/右三段、每段 bg+fg 双层，hover 逐段点亮。做成通用组件，替换主按钮（解析/下载/重试）。

**Files:**
- Create: `frontend/src/components/ui/SegmentedButton.jsx`
- Modify: `frontend/src/components/EntryScene.jsx`（「解析」换用）、`frontend/src/styles/global.css`
- Test: `frontend/src/components/ui/SegmentedButton.test.jsx`

**Interfaces:**
- Produces: `SegmentedButton` 的 props `{ children, onClick, disabled?, className? }`（与原生 `<button>` 对齐，语义为按钮）。

- [ ] **Step 1: 写 SegmentedButton.jsx**

`frontend/src/components/ui/SegmentedButton.jsx`:
```jsx
import React from 'react';

// 分段分层主按钮：三段 bg+fg，hover 逐段点亮；语义仍是原生 button，可无障碍访问。
export default function SegmentedButton({ children, onClick, disabled, className = '' }) {
  return (
    <button type="button" className={`segmented-btn ${className}`} onClick={onClick} disabled={disabled}>
      <span className="seg seg--left"><i /><i /></span>
      <span className="seg seg--mid"><i /><i /></span>
      <span className="seg seg--right"><i /><i /></span>
      <span className="segmented-btn__label">{children}</span>
    </button>
  );
}
```

在 `global.css` 增加：
```css
.segmented-btn {
  position: relative; display: inline-grid; grid-auto-flow: column; gap: 2px;
  padding: 0; border: none; background: transparent; cursor: pointer;
}
.segmented-btn .seg { position: relative; width: 22px; height: 40px; display: block; }
.segmented-btn .seg i {
  position: absolute; inset: 0; border-radius: 6px; transition: box-shadow .2s, transform .2s;
}
.segmented-btn .seg i:first-child { background: linear-gradient(180deg, var(--neon-pink), var(--neon-blue)); opacity: .75; }
.segmented-btn .seg i:last-child { background: rgba(255,255,255,.12); }
.segmented-btn:hover .seg i:last-child { box-shadow: 0 0 12px var(--neon-blue); transform: translateY(-2px); }
.segmented-btn__label {
  grid-column: 1 / -1; padding: 10px 18px; border-radius: 999px; font-weight: 600;
  color: #f5f6ff; background: linear-gradient(90deg, var(--neon-pink), var(--neon-blue));
}
.segmented-btn:disabled { opacity: .45; cursor: not-allowed; }
```

> 说明：三段 `.seg` 作为装饰层垫在文字下方，`__label` 为可读文本承载交互与点击区域；hover 时三段逐一点亮。此为参考站「分段 bg+fg」的二次元简化版。

- [ ] **Step 2: 写测试**

`frontend/src/components/ui/SegmentedButton.test.jsx`:
```jsx
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SegmentedButton from './SegmentedButton.jsx';

describe('SegmentedButton 分段分层按钮', () => {
  it('渲染三段 + 标签，点击触发 onClick', async () => {
    const onClick = vi.fn();
    render(<SegmentedButton onClick={onClick}>解析</SegmentedButton>);
    const btn = screen.getByRole('button', { name: '解析' });
    expect(btn.querySelectorAll('.seg')).toHaveLength(3);
    await userEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
  it('disabled 时不触发', async () => {
    const onClick = vi.fn();
    render(<SegmentedButton onClick={onClick} disabled>下载</SegmentedButton>);
    await userEvent.click(screen.getByRole('button', { name: '下载' }));
    expect(onClick).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: EntryScene 换用 + 跑测试 + 提交**

在 `EntryScene.jsx` 里把「解析」的 `<button type="submit">` 换成 `SegmentedButton`（注意 `SegmentedButton` 是 `type="button"`，需在 `onClick` 里手动调 `submit(e)`，或给组件加 `type` 透传）。**优先方案**：给 `SegmentedButton` 增加 `type` prop 透传（`type="submit"` 时表单内可直接提交）。

调整 `SegmentedButton` 签名为 `{ children, onClick, disabled, className, type = 'button' }`，`<button type={type} …>`。EntryScene 用 `<SegmentedButton type="submit">解析</SegmentedButton>`。

Run: `cd frontend && npm test`
```bash
git add frontend/src/components/ui/SegmentedButton.jsx frontend/src/components/ui/SegmentedButton.test.jsx frontend/src/components/EntryScene.jsx frontend/src/styles/global.css
git commit -m "feat(frontend): 分段分层按钮（SegmentedButton，替换解析主按钮）"
```

---

## Task 6: 缠绕式进度（PathProgress）

> 把下载的横条能量条升级为「魔法符文/星光轨迹」SVG 缠绕进度。通用组件：业务层只喂 `value`，`path` 可换，供后续队列/批量/总结进度复用。

**Files:**
- Create: `frontend/src/components/ui/PathProgress.jsx`
- Modify: `frontend/src/components/DownloadingScene.jsx`（换用 PathProgress，保留 EnergyBar 作 lightMode 兜底）、`frontend/src/styles/global.css`
- Test: `frontend/src/components/ui/PathProgress.test.jsx`

**Interfaces:**
- Produces: `PathProgress` 的 props `{ value, path? }`；`value` 0–100。
- 复用既有：`EnergyBar` 保留（Task 7 用于 lightMode / 低端机兜底）。

- [ ] **Step 1: 写 PathProgress.jsx**

`frontend/src/components/ui/PathProgress.jsx`:
```jsx
import React from 'react';

// 缠绕式进度：SVG path 用 stroke-dashoffset 表达进度（pathLength=1 归一化）。
// path 可换（默认一段星光轨迹）；业务层只关心 value。
const DEFAULT_PATH = 'M0,60 C90,0 180,120 270,60 C360,0 450,120 540,60';

export default function PathProgress({ value, path = DEFAULT_PATH }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <svg
      className="path-progress"
      viewBox="0 0 540 120"
      preserveAspectRatio="none"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <path className="path-progress__track" d={path} pathLength="1" />
      <path
        className="path-progress__fill"
        d={path}
        pathLength="1"
        style={{ strokeDasharray: 1, strokeDashoffset: 1 - pct / 100 }}
      />
    </svg>
  );
}
```

在 `global.css` 增加：
```css
.path-progress { width: 100%; max-width: 480px; height: 60px; overflow: visible; }
.path-progress__track, .path-progress__fill {
  fill: none; stroke-linecap: round; stroke-width: 6;
}
.path-progress__track { stroke: rgba(255,255,255,.1); }
.path-progress__fill {
  stroke: url(#pgrad);
  stroke: linear-gradient(90deg, var(--neon-pink), var(--neon-blue), var(--neon-lime));
  filter: drop-shadow(0 0 6px var(--neon-blue));
  transition: stroke-dashoffset .3s ease;
}
```

- [ ] **Step 2: 写测试**

`frontend/src/components/ui/PathProgress.test.jsx`:
```jsx
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import PathProgress from './PathProgress.jsx';

describe('PathProgress 缠绕式进度', () => {
  it('clamps value 到 0..100 并设置 aria', () => {
    const { rerender } = render(<PathProgress value={150} />);
    expect(document.querySelector('[role="progressbar"]')).toHaveAttribute('aria-valuenow', '100');
    rerender(<PathProgress value={-5} />);
    expect(document.querySelector('[role="progressbar"]')).toHaveAttribute('aria-valuenow', '0');
  });
  it('渲染 track 与 fill 两条 path', () => {
    const { container } = render(<PathProgress value={50} />);
    expect(container.querySelectorAll('path')).toHaveLength(2);
  });
});
```

- [ ] **Step 3: DownloadingScene 换用 + 跑测试 + 提交**

在 `DownloadingScene.jsx`：服务端模式用 `<PathProgress value={job?.progress} />`；lightMode / 低端机（可用 props 传入 `simplified`）回退 `<EnergyBar value={job?.progress} />`（`EnergyBar` 保留）。直链模式文案不变。

Run: `cd frontend && npm test`
```bash
git add frontend/src/components/ui/PathProgress.jsx frontend/src/components/ui/PathProgress.test.jsx frontend/src/components/DownloadingScene.jsx frontend/src/styles/global.css
git commit -m "feat(frontend): 缠绕式进度（PathProgress，替换横条能量条）"
```

---

## Task 7: 收尾 —— 端到端验收 + 降级复核 + 文档

> 确认 6 项手法叠加后，核心下载主链路仍完整可运行、可验证；降级路径（reduced-motion / lightMode / low-tier / 移动端）全部生效；文档补齐。

**Files:**
- Modify: `frontend/src/App.jsx`（若有遗漏的挂载/降级分支）、`frontend/README.md`（已知限制与降级说明）
- 无新测试（或补一条 `App.test.jsx` 断言字幕/画框随 scene 出现）

**Interfaces:**
- 依赖 Task 1–6 的全部产物；无新接口。

- [ ] **Step 1: 补一条 App 集成断言（可选，防回归）**

`frontend/src/App.test.jsx` 增加：
```jsx
it('渲染章节字幕与几何画框', () => {
  render(<App />);
  expect(screen.getByTestId('subtitle')).toBeInTheDocument();
});
```
> 若 `App.test.jsx` 已 mock 掉部分模块，把字幕/画框断言并入既有「入口场景」用例即可。

- [ ] **Step 2: 全量测试 + 手工冒烟（端到端主链路，Global Constraint 1）**

Run: `cd frontend && npm test`（全绿；后端 `pytest` 亦全绿）。

手工冒烟（对照 `docs/requirements.md` R1–R6）：
- [ ] 入口：魔法阵 + 蒙版揭幕转场进入，字幕「把链接交给魔法阵…」
- [ ] 解析：虹膜转场，字幕「正在聆听链接的低语…」，光标变 ◌
- [ ] 选择：卡片入场，光标 ✧，选清晰度
- [ ] 下载：缠绕进度推进，角色奔跑，光标 ➤
- [ ] 完成：比心，字幕「完成啦…」，可保存文件
- [ ] 错误：错误场景 + 对应错误台词
- [ ] 直链与服务端两模式都走通
- [ ] 手机浏览器：主链路可跑，光标隐藏、转场降级、下载不受影响
- [ ] 打开系统「减少动态效果」：转场/光标退化为 none，功能不变

- [ ] **Step 3: 更新 frontend/README.md 的「已知限制」**

补充：第二阶段新增的转场/光标在 `prefers-reduced-motion` 与「轻量模式」下自动降级；自定义光标在移动端（无鼠标）隐藏。

- [ ] **Step 4: 提交**

```bash
git add frontend/src frontend/README.md
git commit -m "feat(frontend): 第二阶段电影感视觉收尾（验收 + 降级复核 + 文档）"
```

---

## 自检（writing-plans self-review）

- **Spec 覆盖**：requirements §9 的 V1（转场/揭幕）→ Task 3；V2（画框）→ Task 2；V3（台词）→ Task 1；V4（光标）→ Task 4；V5（分段按钮）→ Task 5；V6（缠绕进度）→ Task 6；端到端 + 降级 → Task 7。
- **字段一致性**：`SCENE_SCRIPT`/`SCENE_TRANSITION`/`SCENE_CURSOR` 均以 `sceneMachine.SCENE` 为键；`ERROR_SCRIPT` 键与 `ERROR_SCENES` 逐字对齐。
- **无占位**：所有配置、纯函数、组件、测试均有具体代码；仅 CSS 动画的逐帧手感需实现时微调（已给具体 keyframes）。
- **扩展点落位**：三个注册表 + `PathProgress` 通用组件即「预留接口」，对应 design §13.2 的扩展清单。
- **不碰核心**：全部 fx 只读 `scene`，未 import `api.js` 下载逻辑、未改 `sceneMachine.reduce`。
