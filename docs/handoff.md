# 交接文档 · 万能视频下载网站（当前：pidanai UI 风格重构）

> 交接时间：2026-09-24 · HEAD `f177a23` · **活跃任务：pidanai UI 风格重构（阶段 2 进行中）**
> 本文写给**下一位接手者**（人或 AI）。所有命令、数字、结论均来自**本次实测**，如实标注验证程度，不夸大、不隐瞒。

---

## 0. 30 秒上手

**这是什么**：一个「粘贴链接 → 解析 → 选清晰度 → 下载」的全流程视频下载网站。
- 后端：FastAPI + yt-dlp + SQLite（进程内直接调 yt-dlp Python API）。
- 前端：React 18.3 + Vite 8 + PIXI 6.5.10 + pixi-live2d-display 0.4.0，Live2D 角色「白」。

**跑起来（3 条命令）**：

```bash
# 后端（端口 8000；venv 在仓库根目录，不是 backend/ 下）
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# 前端（端口 5173；dev server 已配 Vite 代理 /api → localhost:8000）
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`（若端口被占，Vite 自动 +1，看终端实际地址；本次实测落在 `:5175`）。

**验证跑通（2 条命令，均全绿——本次实测）**：

```bash
cd frontend && npm test                                   # 45/45 通过（10 个文件）
cd backend && ../.venv/Scripts/python -m pytest -q        # 33/33 通过
```

> 首次换机器需：`python -m venv .venv`（**仓库根目录**）→ `.venv/Scripts/pip install -r backend/requirements.txt`；前端 `cd frontend && npm install`。

---

## 1. 当前活跃任务（先读这个）

**任务**：把 UI 从「樱花粉玻璃拟态」重构为 **pidanai.com 的「深色液态玻璃 + 樱花粉辉光」**设计语言。**只改视觉层**。

- **计划文件**：`.planning/2026-09-24-ui-pidanai/`（`task_plan.md` 阶段+决策 / `progress.md` 会话日志 / `findings.md` 侦察 / `verify/` 截图）。
- **分析报告**：`docs/ui-refactor-pidanai.md`（阶段 1 报告）、`docs/ui-refactor-pidanai-deep.md`（深度分析，含 liquid-glass.js 破译）。

### 1.1 阶段进度（如实）

| 阶段 | 状态 |
| --- | --- |
| 阶段 0 侦察 | ✅ complete |
| 阶段 1 分析报告 | ✅ complete |
| 阶段 2 实施：① 重建 token 体系 | ✅ **完成并验证**（Vitest 45 + 双工具截图） |
| 阶段 2 实施：② 改全局样式 | ✅ **完成并验证**（玻璃 token + 折射背景 + 双工具复查） |
| 阶段 2 实施：③ 改组件外观 | ✅ **完成并验证**（玻璃卡折射描边环 + Arial Black 超大展示字 + token 化两处硬编码；Vitest 45 + 双工具截图） |
| 阶段 2 实施：④ 调细节/背景层 | ✅ **完成并验证**（花瓣→折射光点、PIXI 底色对齐深色底、主题化滚动条；Vitest 45 + playwright 截图） |
| 阶段 3 验证与交付 | ✅ **完成并验证**（全量 playwright 截图对比 深浅两档 + Live2D 功能回归 + pytest 33/Vitest 45 + 硬编码扫描 + `docs/ui-extension-guide.md` 扩展指南） |

**节奏铁律**：每改完一个模块**立即截图对比一次**，不等到全改完再统一验证。每次完成后用 **chrome-devtools + playwright 双工具**查看。

### 1.2 约束红线（不可破，来自用户提示词）

1. 不升/降 PIXI（v6.5.10）、pixi-live2d-display（0.4.0）。
2. 不改后端 FastAPI 接口/路由/数据模型/表结构；不改 yt-dlp/ffmpeg。
3. 不删/改写现有测试；pytest 33 + Vitest 45 全绿。
4. 不改 Live2D 容器 DOM 层级、尺寸计算、生命周期挂载；模型路径 `/live2d/` 绝对路径。
5. 只借鉴设计语言，不复制目标站代码/品牌资产/受版权字体（汉仪正圆95 商业字体不可用）。
6. 不写死、解耦、token 语义化、保留主题切换扩展位。

### 1.3 已定设计决策（AskUserQuestion 确认，勿再问）

- 方向：**深色液态玻璃基底 + 樱花粉辉光**（非纯黑白）。
- 主 CTA：**粉胶囊白字**。
- 主题：**保留三档**（浅/深/自动），**深色为默认**。

---

## 2. 架构与解耦铁律

### 2.1 数据流

```
[前端 React/Vite :5173]  ⇄ /api（Vite 代理） ⇄  [FastAPI :8000]
                                                    │
                          ┌─────────────────────────┼──────────────────┐
                          │ ytdlp_service.py        │  线程池 + 并发上限  │
                          │ extract_info / download │  任务状态落 SQLite │
                          └─────────────────────────┼──────────────────┘
                                                    │
                                              临时目录 TTL 自动清理
```

### 2.2 解耦边界（单向依赖，改动隔离——违反会破坏扩展性）

- **后端**：`backend/app/services/ytdlp_service.py` 是**唯一**接触 `yt_dlp` 的层；其余模块只依赖它的接口（`extract_info` / `download` / 进度回调），**不得直接 import `yt_dlp`**。
- **前端**：视觉表现层（`pixi/`、`components/`）**只读** `scene` 状态，**绝不修改下载状态、绝不 import 下载核心**；下载核心也不依赖视觉层。
- **数据驱动、不写死**：颜色/字体/时长走 `:root` token；模型/表情/道具/特效走 `frontend/src/pixi/mascotConfig.js`。

### 2.3 工程约定（最高优先级，与根 CLAUDE.md 一致）

1. UI 必用 skill（`ui-ux-pro-max` 主 + `design-system`）；涉及 UI 前**先调 skill，再写代码**。
2. skill 优先于计划（冲突以 skill 为准）。
3. 不写死、保留扩展，避免大规模重构。
4. 解耦（见 2.2）。
5. 每完成一个 Task **停下等用户指示**，不自动推进下一个 Task。

---

## 3. 前端 token 体系（阶段 2 ① 成果）

三层 token：primitive → semantic → component，单一切换开关 `[data-theme]`（写在 `<html>` 上）。

**深色为默认**（`:root` = 深色签名）；`[data-theme='light']` 为显式浅色覆盖块；`[data-theme='dark']` 继承默认；`[data-theme='auto']` 由 `@media (prefers-color-scheme)` 解析。`App.jsx` 的 `useState` 默认 `'dark'`，三档数组 `THEMES = [{v:'light'},{v:'dark'},{v:'auto'}]`。

### 3.1 关键 token 值（本次 evaluate_script 实测读数）

| token | 深色 | 说明 |
| --- | --- | --- |
| `--surface` | `#0a0a0f`（ink-900） | 基底 |
| `--surface-glass` | `color-mix(in srgb, #fff 6%, transparent)` | 玻璃面（浅色档为 72% 白） |
| `--accent` | `#d6336c` | 品牌樱花粉·主按钮（白字 4.6:1） |
| `--accent-hover` | `#bd2a5b` | 深一档 |
| `--accent-soft` | `#f8c3cd` | 浅粉 |
| `--accent-pink` | `#ff6cae` | 折射粉（辉光/PIXI 粒子） |
| `--accent-lilac` | `#996fff` | 折射紫 |
| `--refract-cyan` | `#47a9ff` | 折射青 |
| `--refract-violet` | `#996fff` | 折射紫 |
| `--refract-pink` | `#ff6cae` | 折射粉 |
| `--refract-mint` | `#53ddb8` | 折射薄荷 |
| `--refract-warm` | `#ffc062` | 折射暖橙 |
| `--fs-display` | `clamp(40px, 8vw, 104px)` | 超大展示字号 |
| `--font-display` | `"Arial Black", Impact, "Alibaba PuHuiTi", "Alimama ShuHeiTi", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, ...` | 展示字栈（均为免费可商用字体） |

折射五色**跨主题恒定**（hex，不随浅/深变化）；品牌粉 `--accent` 也跨主题恒定。

### 3.2 PIXI `hex()` 约束（重要坑）

`pixi/theme.js` 的 `hex()` 用 `parseInt(hex,16)`，非 hex 输入回退**白色**。因此 `--accent` / `--accent-hover` / `--accent-soft` / `--accent-lilac` / `--accent-pink` **必须解析为 hex**，**不能**是 `rgba()`/`color-mix()`。PIXI 消费的 token 与 CSS 消费的 token 分属两条线，改值时两侧要同步（theme.js fallback 与 global.css `:root` 保持一致）。

---

## 4. 玻璃系统（阶段 2 ② 成果）

- 玻璃配方统一 token：`--glass-blur:18px` / `--glass-saturate:1.16` / `--glass-filter: blur(18px) saturate(1.16)`。
- 6 处 `backdrop-filter`（静音 8px、主题 8px、光环 12px、卡片 12px、气泡 12px、表情菜单 14px，含 `-webkit-` 孪生行）全部改用 `var(--glass-filter)`。
- `body` 与 `.css-fallback` 背景 = 深色底 + 折射双光斑（青 `12% 6%`、紫 `88% 94%`，`color-mix` 从 `--refract-*` 派生）+ 樱花粉辉光（`72% 58%` 角色身后）。

### 4.1 backdrop-filter 祖先破坏（必须逐模块巡检）

`opacity<1` / `transform` / `filter` / `overflow:hidden` 任一出现在玻璃元素**祖先**上，会**静默破坏** `backdrop-filter`（变不透明、糊掉）。目标站用 WebGL 逐元素折射 + `getCompositedOpacity()` 补偿；我们用 CSS「伪折射」，靠**每改一个模块就截图对比**早发现早修。实测巡检法（chrome-devtools evaluate_script）：读 `getComputedStyle(el).backdropFilter` + 逐祖先查这四项。

---

## 5. 文件地图（改哪，看哪）

### 前端 `frontend/src/`

| 文件 | 职责 | 改它注意 |
| --- | --- | --- |
| `App.jsx` | 场景装配：三档主题、角色点击开菜单、scene→表情/特效、preloader 就绪态、菜单 `onScale` | 视觉层只读 `scene`，不碰下载；主题默认 `'dark'` |
| `styles/global.css` | **三层 token + 全部组件样式（视觉层唯一真源）** | 颜色一律 `var(--*)`，勿散落硬编码 |
| `pixi/theme.js` | PIXI 颜色读 `:root` 语义 token | 无 DOM 时 fallback；`hex()` 只吃 hex（见 §3.2） |
| `pixi/mascotConfig.js` | **数据单一来源**：`MODELS`/`IDLE`/`EXPRESSIONS`/`SCALE` | 加表情/道具/特效/缩放都改这里 |
| `pixi/mascot.js` | Live2D 创建/待机/`setExpression`/`setStageExpression`/`scaleBy` | 特效走 `model.motion()`；缩放走 `place()` |
| `pixi/background.js` | 粒子/极光背景 | 颜色读 `pixi/theme.js` |
| `components/ui/ExpressionMenu.jsx` | 换装菜单（表情 + 尺寸缩放区） | 常驻挂载，`open` 只切 CSS 类 |
| `components/ui/Preloader.jsx` | 加载层（Live2D 加载期） | 仅 `webgl && !ready` 时渲染 |
| `components/SelectingScene.jsx` | 解析结果展示 | 字段来自 `normalizeParse` 派生值 |
| `components/DownloadingScene.jsx` | 下载中 spinner + 能量条 | — |
| `api.js` | 后端接口封装 | 前端唯一接后端的边界 |
| `lib/videoAdapter.js` | parse 归一化 + 派生字段 | 纯函数 |
| `lib/saveFile.js` | 浏览器原生保存（`<a download>`） | 服务端完成后自动保存入口 |
| `hooks/useDownload.js` | 下载编排：发起 + 轮询 + 自动保存 | 直链走 `window.location.assign` |
| `state/downloadConfig.js` | 下载配置（`POLL_MS`） | 数据驱动 |
| ~~`components/ui/About.jsx`~~ | **已删除**（页脚署名，已获作者授权） | 不要再引用 |

### 后端 `backend/app/`

| 文件 | 职责 |
| --- | --- |
| `services/ytdlp_service.py` | **唯一**接触 yt-dlp 的层 |
| `services/jobs.py` | 线程池 + 任务生命周期 + 临时文件清理 |
| `config.py` | 全部配置（env 覆盖） |
| `routes/parse.py` / `download.py` | HTTP 路由 |
| `models.py` | SQLModel `Job` |
| `db.py` | SQLite 引擎/会话 |

---

## 6. 如何验证改动

```bash
cd frontend && npm test                                   # 前端必跑（45/45）
cd backend && ../.venv/Scripts/python -m pytest -q        # 后端必跑（33/33）
```

**视觉验证（改 UI 必做，双工具）**：
1. chrome-devtools：reload → `take_screenshot` + `evaluate_script`（读 token / backdrop-filter / body 背景）。
2. playwright：`browser_navigate` → `take_screenshot` + `browser_console_messages`（确认 0 error）。
3. 截图存 `.planning/2026-09-24-ui-pidanai/verify/` 便于对比。

**手工验收清单**（动到以下任一项就跑）：
1. 起前后端 → 打开 `:5173` → 模型正常显示（非黑屏）。
2. 点角色 → 弹菜单 → 点「变大/变小」等比缩放、点表情变 `is-active`。
3. 主题三档切换（浅/深/自动）→ 玻璃卡、token、文字色随档切换，折射青紫光斑恒定。
4. 粘贴真实链接跑「解析 → 选清晰度 → 下载」→ 眼睛 圈圈眼→煎蛋眼→星星眼；下载中 spinner + 能量条；无效链接→生气 + edle 特效。

---

## 7. 坑（务必先读，别再踩）

1. **venv 在仓库根目录** `E:/install_video/.venv`，**不是** `backend/.venv`。后端命令必须 `cd backend && ../.venv/Scripts/python ...`。
2. **ffmpeg**：默认 `ffmpeg_path="ffmpeg"`（走 PATH）；本机靠环境变量 `FFMPEG_PATH` 指定。换机器报 `ffmpeg_missing` 先设 `FFMPEG_PATH`。可 env 覆盖：`MAX_CONCURRENT`(3)、`TEMP_DIR`(backend/tmp)、`MAX_FILE_SIZE`(2GB)、`TTL_SECONDS`(3600)、`RATE_LIMIT`(30)。`ytdlp_service.py` 有 `FFMPEG_MIN_HEIGHT=1080` 阈值：仅 ≥1080p 提供 ffmpeg 合并，低清档只用渐进式直链、无直链跳过该档（720/480/360 可能不出现属预期）。
3. **16K 纹理**：`白.16384/texture_00.png` 是 16384×16384（约 1GB GPU 纹理），超过多数移动端/部分桌面 GPU 的 `MAX_TEXTURE_SIZE`（常见 4096/8192）会黑屏。开发机显存充足已实测可加载；移动端兼容需征得作者许可压缩（属「二改」）。
4. **待机动画已逐帧实锤（2026-09-23）**：ticker 正弦驱动确实逐帧在动（角色区逐帧变化 3.7%~10.75%，背景噪声地板 0.23%~0.46%）。验证方法见 progress.md。
5. **浏览器自动化被 BFCache 冻结**：页面后台化后 `rAF`/`setTimeout` 冻结，采样挂起。验证时保持页面前台，或真机手动。
6. **参考截图勿提交**（`git status` 里的 `??`）：根目录 `blog-home.png` / `ui-1280.png` / `ui-entry-light.png` / `pidanai-*.png`（5 张）；`.planning/` 下的 `verify/*.png` 也属临时验证产物。
7. **授权状态**：Live2D「白」已获作者授权，页脚署名已去除（`About` 已删）。「二改」（纹理压缩/模型改动）是否在授权范围内仍建议确认后再动。
8. **WebGL canvas 读不到像素**：PIXI 默认 `preserveDrawingBuffer:false`，`getImageData()` 返回全透明。测模型尺寸用临时 `window.__mascot` 钩子读 `instance.scale`，实测后删。
9. **edle 只有单个特效**：`edle.motion3.json` 是单个「星光闪烁」循环，非旧注释所写 5 个。
10. **YouTube 间歇性风控**：部分视频报 `Sign in to confirm you're not a bot`（`login_required`/网络错误），属风控非 bug。真实链路验证应预期偶发失败，勿误判为回归。
11. **backdrop-filter 祖先破坏**：`opacity<1`/`transform`/`filter`/`overflow:hidden` 出现在祖先会静默破坏玻璃效果（§4.1）。每改一个模块就巡检。
12. **PIXI `hex()` 只吃 hex**：`--accent*` 系列 token 必须 hex，不能 `rgba`/`color-mix`，否则 PIXI 侧回退白色（§3.2）。
13. **Vitest 两条「Not implemented: navigation」告警是既有的**：来自 `useDownload.js` 的 `window.location.assign` 在 jsdom 不支持，**非测试失败**（45/45 仍全绿）。

---

## 8. Git 状态（如实）

- **HEAD `f177a23`**（樱花粉主题重设计 + 三档主题 + 樱花 preloader + 缩放菜单）。
- **工作区未提交**（`git status` 可见，两块内容叠加）：
  1. **后端解析/下载结构对齐**（前序任务，代码已改未提交）：`backend/app/routes/parse.py`、`schemas.py`、`services/ytdlp_service.py`、`tests/test_formats.py`、`tests/test_parse_route.py`；前端 `components/SelectingScene.jsx`、`DownloadingScene.jsx`、`lib/videoAdapter.js`、`lib/saveFile.js`、`hooks/useDownload.js`、`state/downloadConfig.js`。
  2. **pidanai UI 风格重构（活跃任务）**：`styles/global.css`（token 重建 + 玻璃 + 背景）、`App.jsx`（主题默认 dark）、`pixi/theme.js`（palette 同步）、`components/ui/About.jsx`（删除）、`docs/*`、`.planning/`。
- **`??` 勿提交**：参考截图（见坑 #6）、`docs/package-lock.json`、`uv.lock`、`.planning/`（计划文件属工作记忆，是否入库由你定）。

---

## 9. 下一步

阶段 2 ①②③④ 与阶段 3 最终回归**全部完成**（视觉重构落地并验证；Vitest 45 / pytest 33 全绿；扩展指南 `docs/ui-extension-guide.md` 已交付）。**当前无待做 Task，停下等用户指示。**

## 10. 更多设计细节

- 表情/道具/特效参数映射、阶段映射 → `docs/design.md` §14.8。
- 主题/token/待机动画 → `docs/design.md` §14.1–14.6（⚠️ §14 配色描述已由 pidanai 重构替代，**当前** token/主题见 `docs/ui-refactor-pidanai.md` 与 `docs/ui-extension-guide.md`；§14.6 待机/§14.8 表情机制仍准）。
- 后端架构/数据模型/错误分类/扩展点 → `docs/design.md` §1–§9。
- pidanai 风格分析（token 对照/组件映射/风险/解耦/分步）→ `docs/ui-refactor-pidanai.md`。
- pidanai 深度分析（liquid-glass.js 破译/SVG filter/移动端退回）→ `docs/ui-refactor-pidanai-deep.md`。
