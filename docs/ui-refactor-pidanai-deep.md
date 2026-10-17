# 皮蛋 AI（pidanai.com）深度设计分析报告

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页的“当前/下一步/待实现/等待授权”、预算、测试与服务状态均指记录当时。最新用户决定、活动任务与全部后续计划先读[统一总表](follow-up-plan.md)，phase15证据读[阶段交接](handoff-2026-10-16-deepseek-step1.md)；产品实际实现参照[设计](design.md)、[需求](requirements.md)和[UI指南](ui-extension-guide.md)。长文已获准上线使用但质量仍待整改，现有公开20000字符保护和embedded区域约束尚未在本轮调整。历史候选统一汇入总表，不据旧待办启动开发/服务/模型或重开closed phase；原验收及冻结证据保持原字节。
> 文档状态（2026-10-03整理）：**历史参考**。历史观察记录，不把待确认清单直接当当前需求。当前实现查[前端说明](../frontend/README.md)和[需求](requirements.md)，后续配色、模型及产品计划统一查[总表](follow-up-plan.md)。
> 工程约定仍适用：UI先用 `ui-ux-pro-max` + `design-system`；skill优先于旧计划；颜色/字体/时长token化、能力数据与配置驱动；yt-dlp仅经 `ytdlp_service.py`，视觉只读scene，不修改下载核心。

> 2026-09-24 · 深度观察版（只做分析，未改任何代码）
> 观察对象：https://pidanai.com/#about （PDAim，计算机视觉 FPS 瞄准优化工具官网）
> 目标：把本项目「樱花粉玻璃拟态」重构为 pidanai.com 的「黑白极简 + 折射彩虹 + 超大展示字 + 玻璃拟态」设计语言——**仅改视觉层**。

---

## 数据来源标注约定

每条事实均标注来源，避免混淆「实测」与「推断」：

| 标注 | 含义 | 工具 |
|---|---|---|
| `[chrome-devtools]` | 页面计算样式 / DOM 扫描 / :root 变量实测 | chrome-devtools MCP（evaluate_script + getComputedStyle） |
| `[playwright]` | 桌面 1920×1080 / 平板 768×1024 / 手机 375×812 截图 | playwright MCP |
| `[firecrawl]` | 页面结构 / 导航层级 / 文案 / meta | firecrawl MCP |
| `[liquid-glass.js]` | 站点加载的液态玻璃脚本源码（71KB / 1882 行，已 curl 抓取解析） | 直接读源码 |
| `[context7]` | MDN 现代 CSS 文档（backdrop-filter / color-mix / SVG filter） | context7 MCP |

> **MCP 可用性说明**：4 个 MCP 全部可用。github MCP 中途断连，但本任务不需要。所有结论均基于真实抓取，无推断填充。

---

## 1. 整体设计风格定性

`[firecrawl]` + `[playwright]` + `[chrome-devtools]`

**一句话定性**：**「Swiss 编辑排版 × 科技游戏」的黑白极简，叠加一层「液态玻璃折射彩虹」作为唯一的色彩表达**。默认浅色主题。

- **风格标签**：Swiss/International 排版、极简、玻璃拟态（Glassmorphism）、WebGL 折射、超大负字距展示字、编辑式网格。
- **情绪关键词**：克制、精密、冷静、科技、游戏化点缀。
- **Liquid Glass 相似度评估**：**高度相似，但实现更重**。站点自称「liquid glass」，实测是 **WebGL 逐元素折射**（每块玻璃一个 `<canvas>`，用片元着色器对背后内容做色散折射），而非常见的纯 `backdrop-filter` 毛玻璃。这是它区别于普通 glassmorphism 的核心（详见第 7 节）。

**视觉锚点**：纯白底 `#ffffff` + 近黑字 `#070707`，唯一颜色来自五色「折射彩虹」光斑（青/粉/紫/薄荷/暖橙），以及玻璃边缘的色散虹彩。整体观感是「一张白纸上悬浮着会折射光线的玻璃」。

---

## 2. 色彩体系

`[chrome-devtools]`（:root 全量 223 个 CSS 变量实测 + 关键元素计算色值）+ `[liquid-glass.js]`（orb 颜色常量）

### 2.1 中性色（黑白灰阶，默认浅色主题）

| Token | 实测值 | 用途 |
|---|---|---|
| `--bg` | `#ffffff` | 页面底色 |
| `--fg` | `#070707` | 近黑主字 |
| `--muted` | `rgba(7,7,7,.58)` | 次字/副文案 |
| `--line` | `rgba(7,7,7,.08)` | 细分隔线 |
| `--pill` | `rgba(7,7,7,.045)` | 胶囊底 |
| `--pill-hover` | `rgba(7,7,7,.075)` | 胶囊 hover |
| `--dot` | `rgba(7,7,7,.34)` | 背景网格点 |

### 2.2 「折射」彩虹（核心特色，iridescent refraction）

`:root` 内 `--refraction-*` 五色 + orb 色值常量（`[liquid-glass.js]` 第 1639–1643 行 `defs`）：

| 色名 | :root token | 浅色 orb RGB | 深色 orb RGB |
|---|---|---|---|
| 青 cyan | `--refraction-cyan: rgba(71,169,255,.2)` | `[0.278, 0.663, 1.0]` → `#47a9ff` | `[0.282, 0.698, 1.0]` |
| 粉 pink | `--refraction-pink: rgba(255,108,174,.17)` | `[1.0, 0.424, 0.682]` → `#ff6cae` | `[1.0, 0.455, 0.722]` |
| 紫 violet | `--refraction-violet: rgba(153,111,255,.18)` | `[0.600, 0.435, 1.0]` → `#996fff` | `[0.620, 0.471, 1.0]` |
| 薄荷 mint | `--refraction-mint: rgba(83,221,184,.15)` | `[0.325, 0.867, 0.722]` → `#53ddb8` | `[0.314, 0.878, 0.745]` |
| 暖橙 warm | `--refraction-warm: rgba(255,192,98,.14)` | `[1.0, 0.753, 0.384]` → `#ffc062` | `[1.0, 0.761, 0.412]` |

> 关键发现：**五色在浅/深主题下是两组不同 RGB**（深色版更亮、更饱和），由 `darkAmount = dataset.theme === "dark" ? 1 : 0` 线性插值（`mix(a,b) = a + (b-a)*darkAmount`）。这说明折射色**不是**跨主题恒定的，而是随主题微调亮度。本项目若要复用，建议做两档折射色。

### 2.3 透明度 / 混合模式规律

- 折射光斑透明度统一在 **14%–20%** 区间（`--refraction-opacity: .54` 是整体开关倍率，非单色透明度）。
- 玻璃整体透明度：`--glass-tint: rgba(255,255,255,.018)`（极淡白玻璃）。
- 玻璃边缘高光：`--glass-edge-light: rgba(255,255,255,.95)`、`--glass-edge-dark: rgba(0,0,0,.46)`（上下明暗描边，制造厚度感）。
- 卡片底：`--pdaim-card-bg: color-mix(in srgb, #ffffff 84%, transparent)`（**color-mix 用透明度混色**，等价 `rgba(255,255,255,.84)`）。
- 卡片线：`--pdaim-card-line: color-mix(in srgb, #070707 11%, transparent)`。
- 卡片软影：`--pdaim-panel-shadow: 0 24px 80px rgba(0,0,0,.08)`。

### 2.4 深色主题

`[chrome-devtools]`：`root.dataset.theme` 切 `dark` 时 `--bg→#050505`（orb 读取的深色底）等反转，但本次观察站点默认浅色、未切深色实测（页面脚本可切，但首屏为浅色）。折射色见上表「深色 orb RGB」。

### 2.5 与折射相关的「场景色」

折射不只用于玻璃边缘，还用于两处背景场景（`[liquid-glass.js]`）：
1. **Orb 彩虹光斑**（`uploadOrbTexture`）—— 5 个缓慢漂移的径向渐变光斑，构成页面「呼吸」的背景色。
2. **折射场**（`drawRefractionField`）—— 同样 5 个模糊圆斑，直接画进背景纹理（浅色 15–20% 透明度）。

---

## 3. 排版系统

`[chrome-devtools]`（计算样式实测）

### 3.1 字体

- 主字体 `--font-main: "HYZhengYuan95", Inter, ...`（汉仪正圆 95，**商业字体**）。
- 展示字体 `--font-display: "HYZhengYuan95", Arial Black, Impact, ...`。

### 3.2 字号阶梯（实测关键值）

| 元素 | 字号 | 字重 | 字距 | 行高 | 颜色 | 备注 |
|---|---|---|---|---|---|---|
| **h1（Hero 超大标题）** | `104px` | `700` | `-9.36px` | `89.44px` | `rgb(7,7,7)` | **超大负字距** |
| h2 / h3（区块标题） | `82px` | `700` | `-5.74px` | `73.8px` | `rgb(7,7,7)` | `position:relative; z-index:3` |
| Hero 副文案 | `19px` | `600` | `-0.38px` | — | `rgba(7,7,7,.58)` | `margin:0 0 22px` |
| 导航项 | `14px` | `800` | `0.56px` | — | — | 胶囊内 |
| 按钮 | `12px` | `900` | — | — | — | 全大写感、超重字重 |

### 3.3 排版特征

- **展示字 vs 正文对比极大**：104px 展示标题 vs 14px 正文，比值约 7.4:1。
- **负字距是「视觉签名」**：西文标题 `-9.36px` 制造紧凑、海报感。中文复用需收窄（`-9px` 对汉字会挤压，建议 `-0.06em` 量级）。
- 正文辅助字统一走透明度灰阶（`.58`/`.42`），而非纯灰，保证与白底柔和过渡。

---

## 4. 布局与栅格

`[chrome-devtools]` + `[firecrawl]` + `[playwright]`

### 4.1 区块顺序（firecrawl 抓取）

```
Nav（玻璃固定顶栏，fixed，radius 9999px，z-index 79）
  → Hero（FPS 标签 + 超大标题「HELLO THIS IS PDAIM」+ 副标题 + 滚动提示）
  → STABILITY CORE（3 张卡：Frame Continuity / Confidence Gate / Motion Smoothing）
  → CALIBRATION FLOW（3 步：Collect / Train / Verify）
  → Footer
```

### 4.2 栅格与间距

- 背景网格点距 **38px**（`spacing = 38 * dpr`，点半径 `1.05 * dpr`，`[liquid-glass.js]` 第 1243–1244 行）。
- 网格点带「径向衰减遮罩」`radialGridMask()`，离视口中心越远越淡 → 形成「中心聚焦」的留白节奏。
- Hero 装饰圆斑位置用视口百分比锚定（`0.07/0.22`、`0.9/0.86`），响应式自适应。
- 对角纹理 55°（`drawProductDiagonalTexture`），周期 29px/76px，浅色 alpha `.052`。

### 4.3 响应式断点与行为

- 视口 meta：`width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no` `[firecrawl]`（**禁用缩放**——注意：与无障碍准则「不禁用缩放」冲突，本项目**不应照搬**，见第 8 节）。
- **液态玻璃断点 `max-width:720px` 或 `pointer:coarse`** → 关闭 WebGL 玻璃，退回纯 CSS `[liquid-glass.js]`。
- 手机截图 `[playwright]`：标题字号应通过 `clamp()` 缩小（站内 `--fs-display` 类响应式未见单独值，但 104px 在 375px 屏上靠 `clamp` 机制缩放）。

---

## 5. 组件样式

`[chrome-devtools]`（计算样式实测，含状态）+ `[liquid-glass.js]`

### 5.1 玻璃胶囊按钮 / 导航 pill

`[chrome-devtools]` nav-pill 计算样式实测：

```css
background-color: color(srgb .027 .027 .027 / .02);
background-image: linear-gradient(145deg, color(srgb 1 1 1 / .086), transparent 42%);
border-radius: 13px;
box-shadow:
  color(srgb 1 1 1 / .359) 1px -1px 0.55px -1px inset,   /* 上内高光 */
  color(srgb 1 1 1 / .07) 0.5px 0.5px 0.6px 0px inset,   /* 上内柔光 */
  rgba(0,0,0,.055) 0px 8px 20px 0px;                      /* 底投影 */
filter: drop-shadow(rgba(0,0,0,.08) 5px 23.82px 3px);     /* 外层 drop-shadow */
padding: 12px 19px;
font: 800 14px / .56px 字距;
will-change: filter;
overflow: hidden;
```

**玻璃按钮配方（可移植）**：
1. 底：极淡半透明白 `color(srgb 1 1 1 / .02)`。
2. 高光：`linear-gradient(145deg, 白 8.6% → 透明 42%)` 模拟顶部受光。
3. 描边：多层 `inset` 白色 box-shadow（上亮下暗，制造厚度）。
4. 投影：`drop-shadow`（黑色软影）+ `box-shadow`（黑色近影）。
5. 圆角：胶囊 `999px` 或 13px。

### 5.2 玻璃卡片（内容卡）

`[chrome-devtools]` backdrop-filter 扫描仅 3 处，均为内容卡：

```css
backdrop-filter: blur(18px) saturate(1.16);
/* 用于 .product-copy / .product-window / .config-copy */
```

即：**内容卡用「backdrop-filter 模糊 + 饱和」做简单毛玻璃**，真正的折射在按钮/导航这些「小玻璃」上用 WebGL 做。

### 5.3 状态

`[chrome-devtools]` + `[liquid-glass.js]`

| 状态 | 实现 |
|---|---|
| hover | `--pill-hover: rgba(7,7,7,.075)` 加深底；`will-change: filter` 预先提示合成层 |
| focus | 未见明显 focus ring（**可访问性缺口**，见第 8 节） |
| disabled | 未见单独 disabled 态（站点以营销页为主，表单少） |
| loading | WebGL 纹理上传前 `clearColor(0,0,0,0)` 透明占位，无白闪 |

### 5.4 主题切换按钮

`[chrome-devtools]`：`12px/900`，`border-radius:999px`，`position:absolute; z-index:92`（浮动右上）。

---

## 6. 背景与动效

`[liquid-glass.js]`（Canvas 网格/粒子/线条场参数）+ `[chrome-devtools]`（will-change/filter 扫描）

### 6.1 Canvas 背景层（两层）

| 层 | 元素 | 内容 |
|---|---|---|
| 网格点层 | 背景纹理内 | 38px 间距圆点 + 径向衰减遮罩 |
| 折射场层 | 背景纹理内 | 5 个漂移彩虹光斑（`drawRefractionField`） |
| 线条场层 | `#pdaimLineField` 独立 canvas | 动画流动线条，作 `lineTexture` 上传 |

### 6.2 动效参数

- **漂移节奏**：`performance.now() * 0.00011`（约 9 秒周期），5 个光斑各自相位偏移 `{0, 1.7, 3.1, 0.8, 2.4}` + 不同速度 `{0.62, 0.73, 0.51, 0.68, 0.44}` → 缓慢、错相位、非同步漂移。
- **orb 波动**：`waveA = sin(time*speed+phase)`、`waveB = cos(time*(speed*0.73+0.17)+phase*1.37)`，双波叠加避免周期感。
- **滚动同步**：`renderForScroll()` 挂 `scroll`（passive），仅当 `frameSignature` 变化才重绘（`Math.round(scrollY*2)/2` 半像素粒度）。
- **入场动画**：`filter: blur(10px)` 的 reveal-on-scroll 元素（filter 扫描 15 处中一部分），滚动到视口时去模糊。
- **视差**：`--grid-x/y`、`--tilt-x/y`、`--move-x/y` 等 JS 驱动变量，随滚动/鼠标微移。

### 6.3 渲染循环与性能护栏

- 单一 `requestAnimationFrame(loop)`；桌面无帧间隔限制（逐帧 `render()`），**移动端限 24fps**（`minInterval = 1000/24`）。
- **DPR 上限**：桌面 `1.25`、移动 `0.85`（`GLASS_DPR_LIMIT` / `MOBILE_GLASS_DPR_LIMIT`）——宁可降采样保帧率。
- **输出上限**：桌面最多 64 个玻璃输出，移动 1 个（`MAX_GLASS_OUTPUTS` / `MOBILE_MAX_GLASS_OUTPUTS`）。
- **脏检查**：`frameSignature`（视口尺寸 + scrollY + 各 opacity + 主题 + 缓存脏标记）变化才重绘，静止时零开销。
- **缓存失效**：`MutationObserver` 监听 body `childList/subtree`，DOM 变动置脏。
- **上下文丢失**：`webglcontextlost` → 加 `.liquid-glass-global-failed` 类优雅降级（退回 CSS）。

### 6.4 SVG filter 使用

`[chrome-devtools]` 扫描：**`svgFilters = []`，站点未使用任何 SVG filter**（无 feDisplacementMap / feGaussianBlur / feTurbulence）。折射完全由 WebGL 完成，SVG filter 在此语境是「不可借鉴」的误导项（见第 10 节）。

---

## 7. 液态玻璃特征专项分析（核心）

`[liquid-glass.js]`（完整源码破译）

### 7.1 它是什么，不是什么

| 判断 | 结论 |
|---|---|
| 是否 SVG feDisplacementMap？ | **否**。全站无 SVG filter |
| 是否纯 backdrop-filter？ | **部分**。仅 3 处内容卡用 `blur(18px) saturate(1.16)` |
| 是否 WebGL 折射？ | **是**。11 个 `.liquid-glass-canvas` `<canvas>` 元素，单一 WebGL 上下文逐元素渲染 |

### 7.2 折射机制（片元着色器破译）

`[liquid-glass.js]` 第 50–500 行着色器源码，关键常量：

```glsl
#define disp 6.25   // 色散量（RGB 通道分离强度）
#define Pow 3.0     // 透镜超椭圆的幂
#define A 1.75      // 折射衰减曲线（外层）
#define B 1.25      // 折射衰减曲线（内层）
#define C 2.0       // 边缘深度
#define GRAD 255.0  // 8bit 量化档位
```

**核心机制是「色散（chromatic aberration）采样」**——对背景纹理做 RGB 三通道偏移采样：

```glsl
// 在折射边缘，R/G/B 分别按不同偏移采样，制造虹彩边缘
d = normal * distance;          // 表面法线 × 折射量
dsp = min(1.0, disp / glassRadius * (1.0 - ref));  // 色散偏移
r = texture2D(background, toTex(pixel - d*(1.0-ref) - dsp)).r;
g = texture2D(background, toTex(pixel - d*(1.0-ref))).g;
b = texture2D(background, toTex(pixel - d*(1.0-ref) + dsp)).b;
```

辅助机制：
1. **SDF 圆角框**：`sdRoundBox()` 计算带圆角的形状距离场；`sdfNormal()` 求表面法线。
2. **透镜曲率**：`liquidRel(dst, glassRadius, blurRadius)` 用嵌套 `pow` 模拟「镜片中间平整、边缘折射强」的曲率。
3. **双高光（厚度）**：两个镜面高光 `num1/num2`，光源 `lightPos` **固定 `(width*0.25, height*0.25)`**（左上角），制造玻璃「厚度」的反光。
4. **8×8 Bayer 抖动**：`dither()` 有序抖动，量化到 8bit 前 `floor(clamp(color,0,1)*GRAD + dither)/GRAD`，消除折射渐变的色带。
5. **背景快照**：`drawBackground()` 把「网格点 + 折射场 + 背后 DOM 元素镜像（`drawUnderlyingContent` 把文字/图/盒子用 canvas 重绘）+ 光标层」画进离屏 canvas，作 `backgroundTexture` 上传——这就是「折射看到的是背后真实内容」的原理。

### 7.3 动态响应

- **滚动**：`scroll` 事件触发背景快照重绘，折射内容随滚动实时更新。
- **主题**：`darkAmount` uniform 随 `dataset.theme` 切换，orb 色与背景色联动。
- **鼠标**：**光标层**（`.cursor-reveal`，`--cursor-size: clamp(130px,17vw,245px)` 大光斑）跟随鼠标，但**玻璃高光 `lightPos` 不跟鼠标**（固定左上）。

### 7.4 祖先断裂检查（用户点名关注项）

`[liquid-glass.js]` + `[chrome-devtools]`

JS 侧已有专门补偿函数 `getCompositedOpacity()`（第 ~450 行）——**遍历祖先累乘 opacity**，防止祖先透明度/滤镜破坏折射。实测到两处会「静默破坏折射」的祖先：

1. `.site-header`：`transform: matrix(1,0,0,1,-590,0)`（平移出屏）+ `filter: blur(8px)`——JS 用 `shouldSkipUnderlyingElement` 与 `glassIsolate` 数据集标记隔离处理。
2. `.nav-pill`：`overflow:hidden` + `border-radius:13px` + `filter: drop-shadow(...)`——溢出的折射会被裁剪，故 JS 按 host 单独做 local background。

**对本项目的启示**：若未来引入 WebGL 折射，`.ui` 容器（`pointer-events:none`）与 Live2D `.stage` 的层级/透明度关系是同样隐患，需保证玻璃层的祖先链无 `filter/transform/opacity<1/overflow:hidden`，或显式做 local background。

### 7.5 与普通 glassmorphism 的区别

| 维度 | 普通 glassmorphism | 本站液态玻璃 |
|---|---|---|
| 模糊 | backdrop-filter blur | 背景纹理采样 + WebGL |
| 折射/色散 | 无 | RGB 三通道色散采样（虹彩边缘） |
| 边缘高光 | 1px border | 多段 `num1/num2` 镜面高光 + inset box-shadow |
| 厚度 | 无 | SDF 法线驱动的透镜曲率 |
| 抗色带 | 无 | 8×8 Bayer 抖动 |
| 成本 | 低（GPU 合成） | 高（逐元素离屏渲染 + 纹理上传） |

---

## 8. 可借鉴与不可借鉴清单

### 8.1 可借鉴（低成本、高收益、可移植）

| # | 内容 | 落地方式 |
|---|---|---|
| 1 | **五色折射彩虹调色板**（青/粉/紫/薄荷/暖橙，15–20% 透明） | 纯 CSS token，零成本 |
| 2 | **黑白灰阶 token**（`--ink-*` 近黑 + 透明度灰阶） | 纯 CSS token |
| 3 | **超大负字距展示字**（h1 104px/700/-9.36px） | `--font-display` + `--fs-display` + `--ls-display`（中文收窄到 -0.06em） |
| 4 | **玻璃胶囊按钮配方**（linear-gradient 高光 + 多层 inset box-shadow + drop-shadow） | 纯 CSS，替换现有樱花胶囊 |
| 5 | **内容卡 `backdrop-filter: blur(18px) saturate(1.16)`** | 纯 CSS，`-webkit-` 前缀 + 兜底 |
| 6 | **38px 网格点 + 径向衰减遮罩**的留白节奏 | PIXI background.js 数据驱动新增（已有 ticker） |
| 7 | **错相位缓慢漂移光斑**（多相位 + 双波叠加避免周期感） | PIXI FX 数据驱动 |
| 8 | **性能护栏思路**（DPR 上限、帧间隔、脏检查、上下文丢失降级） | 借鉴到 PIXI 背景层 |

### 8.2 不可借鉴（冲突 / 版权 / 无障碍问题）

| # | 内容 | 原因 |
|---|---|---|
| 1 | **`user-scalable=no` 禁用缩放** | 违反 WCAG，本项目不应照搬 |
| 2 | **汉仪正圆 95 字体** | 商业字体，版权红线 |
| 3 | **WebGL 逐元素折射**（11 个 canvas + 背景快照 + 色散着色器） | 过重、桌面专属、且与本项目 PIXI 单 app 架构冲突（见 8.3） |
| 4 | **无 focus ring** | 可访问性缺口，本项目应补 |
| 5 | **品牌资产**（PDAim 标志、`drawImageFallback` 里的产品截图假图） | 只借鉴语言，不复制 |

### 8.3 需要重新设计再落地（不能直接抄）

1. **液态玻璃核心**：本站 WebGL 折射是「桌面专属 + 逐元素离屏渲染」，直接移植会与 Live2D 的 PIXI app 抢 WebGL 上下文、且移动端不可用。**本项目应降级为「伪折射」**：CSS 侧用「五色 1px 渐变描边环 + inset 高光」模拟色散边缘，`backdrop-filter` 做模糊（见第 9 节）。
2. **折射色深浅两档**：本站折射色随主题切换两套 RGB，本项目若保留三档主题，需设计三套折射色或做 `color-mix` 派生。

---

## 9. 与当前项目的融合建议

`[现状]` React 18.3 + Vite 8 + PIXI v6.5.10 + pixi-live2d-display 0.4.0；粉发 Live2D「白」在 `frontend/public/live2d`；只改 UI/背景层。

### 9.1 方向定调

**「深色液态玻璃基底 + 樱花粉辉光」**（而非照搬纯白黑白）：本站纯白底会与粉发 Live2D 角色冲突，改为**深色底**（黑/近黑）+ 玻璃折射感 + 保留本项目樱花粉作为品牌点缀（与折射粉 `#ff6cae` 天然同族）。这样：① Live2D「白」在深色底上更突出；② 折射五色里的粉/紫与樱花粉不冲突；③ 保留项目既有粉系身份。

### 9.2 Token 映射（现有 → 目标）

| 现有 semantic | 目标值 | 说明 |
|---|---|---|
| `--accent` | `var(--ink-900)` 或深色下 `var(--refract-pink)` | 主强调（黑胶囊 / 粉胶囊二选一，见决策） |
| `--accent-soft` | `rgba(255,255,255,.08)` | 柔和强调底 |
| `--surface` | `#0a0a0a`（深色基底） | 深色液态玻璃底 |
| `--surface-glass` | `color-mix(in srgb, #ffffff 6%, transparent)` | 玻璃底（浅色站点 84%，深色反转） |
| `--text-primary` | `#f5f5f5` | 深色主字 |
| `--text-secondary` | `rgba(255,255,255,.58)` | 次字 |
| `--border` | `rgba(255,255,255,.08)` | 细分隔线 |
| `--grad-accent` | `linear-gradient(135deg, #47a9ff, #996fff, #ff6cae, #53ddb8, #ffc062)` | 折射彩虹渐变（能量条/装饰） |
| 新增 `--refract-*` ×5 | 上表五色 | 折射彩虹 token |
| 新增 `--font-display` | `"Arial Black", Impact, "Maruko Gothic", var(--font-body)` | 超大展示字 |
| 新增 `--fs-display` | `clamp(48px, 9vw, 104px)` | 响应式展示字号 |
| 新增 `--ls-display` | `-0.06em` | 中文负字距 |

### 9.3 液态玻璃在本项目的实现（降级方案）

**不引入 WebGL 折射**（红线：不动 PIXI/Live2D 上下文；成本高、移动端不可用），改用**纯 CSS「伪折射」**：

```css
/* 玻璃胶囊：模糊 + 色散边缘描边 */
.glass {
  backdrop-filter: blur(18px) saturate(1.16);
  -webkit-backdrop-filter: blur(18px) saturate(1.16);
  background: color-mix(in srgb, #ffffff 6%, transparent);
  /* 伪色散边缘：五色细描边环，模拟 RGB 分离虹彩 */
  border: 1px solid transparent;
  box-shadow:
    0 0 0 1px var(--refract-cyan),
    0 0 0 2px var(--refract-violet),
    0 0 0 3px var(--refract-pink),
    0 0 0 4px var(--refract-mint),
    inset 1px -1px 0 0 rgba(255,255,255,.12),      /* 上内高光 */
    inset -1px 1px 0 0 rgba(0,0,0,.46);            /* 下内暗边 */
}
```

（最终样式以 `ui-ux-pro-max` + `ui-styling` 阶段 2 输出为准，此处给方向。）

### 9.4 背景粒子 / 辉光色建议

- **背景层**：深色底上画「38px 网格点 + 径向衰减」+「五色折射光斑错相位漂移」，颜色取折射五色（低透明度）。
- **樱花粉辉光**：用 `--refract-pink #ff6cae` 做 Live2D 周围的粉色光晕，衔接角色与深色玻璃底。
- **能量条/进度**：`--grad-accent` 折射彩虹渐变（实色，非 15% 透明，保证对比度）。

### 9.5 解耦约束（沿用工程约定）

- 视觉层只读 `scene` 状态，绝不 import 下载核心；PIXI 背景层数据驱动（`FX` 配置块新增折射层，不改渲染逻辑）。
- 折射色/字体/时长全部走 `:root` token，不散落硬编码。
- 三档主题 `[data-theme]` 保留；折射色按主题分档（或 `color-mix` 派生）。

---

## 10. 技术实现线索汇总

### 10.1 CSS 变量（本站实测，可参考命名）

`[chrome-devtools]` 全量 223 个，核心命名模式：`--bg/--fg/--muted/--line/--pill/--dot`（中性）、`--refraction-{cyan|violet|pink|mint|warm}`（折射）、`--glass-tint/--glass-edge-{dark|light}`（玻璃）、`--pdaim-card-{bg|line|soft}`（卡片）、`--cursor-*`（光标）、`--grid-*/--line-field-*/--diagonal-*/--tilt-*/--move-*`（JS 驱动动态变量）。

### 10.2 现代 CSS 函数

`[context7]` MDN 文档确认：

- **`color-mix(in srgb, …)`**：本站用 `color-mix(in srgb, #ffffff 84%, transparent)` 做透明度混色；语法 `color-mix( <colorspace>? , [ <color> && <percentage>? ]# )`，默认色彩空间 `oklab`，省略百分比默认 50/50。可用于派生折射色深浅档。
- **`backdrop-filter: blur() saturate()`**：内容卡毛玻璃；需 `-webkit-` 前缀。
- **`color(srgb …)`**：计算样式中出现（如 `color(srgb 1 1 1 / .086)`），广色域写法，本项目可用 `rgba()` 等价替代。
- **`clamp()`**：`--cursor-size: clamp(130px,17vw,245px)`、展示字号缩放。

### 10.3 SVG filter

**本站未用**（`svgFilters = []`）`[chrome-devtools]`。若要实现「液体折射」，SVG `feDisplacementMap` + `feGaussianBlur` 是常见替代（`[context7]` 文档提及），但本站选择 WebGL 说明 SVG filter 在「逐元素动态折射」场景性能不足。**本项目推荐不引入 SVG filter，直接用 backdrop-filter + 伪描边**。

### 10.4 JS 动效库

本站**自研**（`liquid-glass.js` + `pdaim-shell.js`），无 GSAP/Framer Motion 等第三方动效库依赖（`[firecrawl]` 脚本清单确认）。本项目沿用现有 CSS transition + PIXI ticker，不新增动效库。

### 10.5 可复用开源库（本项目可选，非必需）

| 用途 | 库 | License | 说明 |
|---|---|---|---|
| 圆体字体（替代汉仪正圆95） | **马路口圆体 Maruko Gothic** | SIL OFL 1.1 | Zen Maru Gothic 中文补字，最接近目标站圆体 |
| 备选圆体 | Resource Han Rounded | OFL | 思源黑体二开 |
| 图标库 | Phosphor `@phosphor-icons/react` | MIT | 需要图标时引入（当前几乎无图标） |
| 液态玻璃现成实现 | — | — | 无成熟轻量 OSS；本站为闭源自研，不复制 |

### 10.6 液态玻璃实现参考（如需真正 WebGL 折射的进阶路线）

本站架构可作参考（**本项目不实施**）：单一 WebGL 上下文 + 背景快照纹理 + 色散片元着色器 + SDF 圆角 + Bayer 抖动 + 逐元素 2D canvas 输出 + `frameSignature` 脏检查 + DPR/帧率/输出上限 + `webglcontextlost` 降级。详见 `E:\install_video\.planning\liquid-glass.js`（已抓取存档，1882 行）。

---

## 11. 风险与限制

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| 1 | **本站液态玻璃为 WebGL 桌面专属** | 直接移植到本项目会抢 Live2D 的 PIXI WebGL 上下文、移动端不可用 | 降级为 CSS「伪折射」，不引入 WebGL（见 9.3） |
| 2 | **Live2D「白」粉发白裙 vs 深色黑白科技风** | 风格割裂 | 改用「深色液态玻璃 + 樱花粉辉光」调和；角色保持原样（红线禁二改） |
| 3 | **中文负字距超大展示字挤压/裁切** | 标题可读性 | `--ls-display:-0.06em`（比西文 -9px 收窄）+ `clamp()` 缩放 |
| 4 | **backdrop-filter 兼容性**（Safari 需 `-webkit-`，Firefox 已支持但旧版无） | 玻璃失效 | `-webkit-` 前缀 + `--surface-glass` 实色兜底 |
| 5 | **折射色偏浅，进度条对比不足** | 可读性 | 能量条用实色折射渐变（非 15% 透明），对比 ≥3:1 |
| 6 | **三档主题 token 同步重构** | 主题破碎 | 折射色按主题分档 + 深色反转，与现有机制一致 |
| 7 | **headless 渲染退化** | 截图对比失真 | 阶段 3 用 headed playwright 截图 + 真人复核 |
| 8 | **测试断言颜色/类名** | 测试红 | 现有测试主断言 data-testid/文案/状态；实施后全量跑 Vitest 44 + pytest 33 |
| 9 | **圆体字体文件大（3 万字）** | 首屏慢 | 保留现有兜底；圆体按需 subset，不强上 |

---

## 下一步实施建议（Checklist）

> 当前任务为分析阶段（Phase 0/1），**未改任何代码**。以下为阶段 2 实施前需用户确认的决策 + 后续步骤。

**待用户确认（3 个决策）**：

1. **方向**：接受「深色液态玻璃基底 + 樱花粉辉光」（而非照搬纯白黑白）？——这是对「黑白极简 vs 粉发 Live2D」冲突的最优调和。
2. **主按钮色**：主 CTA 用「黑胶囊白字」（贴近本站）还是「粉胶囊白字」（保留项目身份）？
3. **三档主题**：保留现有「浅/深/自动」三档，还是简化？

**确认后执行（阶段 2）**：

1. 重建 token：`global.css` `:root` 加 `--ink-*` 灰阶 + `--refract-*` 五色 + `--font-display/--fs-display/--ls-display` + semantic 映射 + 三档主题。
2. 同步 `pixi/theme.js` fallback 折射色。
3. 改全局样式：玻璃胶囊按钮（伪折射描边）、卡片、胶囊选择、气泡、菜单、进度条、spinner、输入框、展示标题。
4. 改组件外观（仅样式，不动逻辑/状态机/下载编排/Live2D 加载）。
5. 改背景层：`pixi/background.js` FX 加网格点 + 五色折射光斑层（数据驱动）。
6. 改 Preloader：花瓣 → 折射光斑。
7. 字体：评估马路口圆体 subset（或保留现有 + Arial Black 展示字）。
8. 响应式 + 状态：断点 token、移动端 `clamp`、补 focus/disabled/loading/empty。
9. 验证：headed playwright 截图对比 → Live2D 功能回归 → pytest 33 + Vitest 44 → 硬编码扫描 → 扩展指南。
