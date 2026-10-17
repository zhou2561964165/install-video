# 第一阶段交接文档（Phase 1 Handover）

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页的“当前/下一步/待实现/等待授权”、预算、测试与服务状态均指记录当时。最新用户决定、活动任务与全部后续计划先读[统一总表](follow-up-plan.md)，phase15证据读[阶段交接](handoff-2026-10-16-deepseek-step1.md)；产品实际实现参照[设计](design.md)、[需求](requirements.md)和[UI指南](ui-extension-guide.md)。长文已获准上线使用但质量仍待整改，现有公开20000字符保护和embedded区域约束尚未在本轮调整。历史候选统一汇入总表，不据旧待办启动开发/服务/模型或重开closed phase；原验收及冻结证据保持原字节。
> 文档状态（2026-10-03整理）：**历史参考**。这是2026-09-22阶段快照，不再作为接手入口。旧Task4–6、测试数量和未提交说明仅代表当时；当前状态看 [handoff.md](handoff.md)。
> 工程约定仍适用：UI先用 `ui-ux-pro-max` + `design-system`；skill优先于旧计划；颜色/字体/时长token化、能力数据与配置驱动；yt-dlp仅经 `ytdlp_service.py`，视觉只读scene，不修改下载核心。

> 本文保留第一阶段的历史交接过程。接手先读 `docs/handoff.md`，不要直接继续旧Task4–6或恢复当时的未提交/测试状态。
>
> 生成时间：2026-09-22
> 最后更新：2026-09-22（Task 3 完成 + 工程约定落地）
> 项目根目录：`E:\install_video`
> 当前分支：`main`

---

## 0. 工程约定（必读，最高优先级）

> 与根目录 `CLAUDE.md` 一致，每次开发必须遵守。

1. **UI 必须用 skill**：涉及配色/字体/动效/无障碍/组件时，先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：计划文档与 skill 冲突时以 skill 为准（例：每屏最多动 1–2 个关键元素 > 计划里的常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。

---

## 目录

1. [项目概览](#1-项目概览)
2. [术语表](#2-术语表)
3. [目录结构与文件清单](#3-目录结构与文件清单)
4. [环境配置与运行](#4-环境配置与运行)
5. [测试方式](#5-测试方式)
6. [已完成事项（Task 1 / 2 / 3）](#6-已完成事项task-1--2--3)
7. [未完成事项（Task 4 / 5 / 6）](#7-未完成事项task-4--5--6)
8. [阻塞项](#8-阻塞项)
9. [待确认项](#9-待确认项)
10. [关键决策及原因](#10-关键决策及原因)
11. [已知问题](#11-已知问题)
12. [技术债](#12-技术债)
13. [风险](#13-风险)
14. [可复用资产](#14-可复用资产)
15. [扩展点](#15-扩展点)
16. [全栈代码审查与重构建议报告（核心）](#16-全栈代码审查与重构建议报告核心)
17. [第二阶段衔接建议](#17-第二阶段衔接建议)
18. [常见问题 FAQ](#18-常见问题-faq)
19. [注意事项](#19-注意事项)

---

## 1. 项目概览

**项目名称**：万能视频下载网站（universal video downloader）

**功能**：粘贴任意平台视频链接 → 解析 → 选清晰度 → 下载到本地。依托 `yt-dlp` 覆盖数千站点；前端是日系二次元沉浸式体验（PIXI 舞台 + Live2D 角色 + 场景状态机）。

**架构**：

```
[前端 React/Vite + PIXI + Live2D]  ⇄ HTTP/JSON  ⇄  [FastAPI 后端]
                                                     │
                                        yt-dlp 服务层（线程池 + SQLite 任务状态）
```

**技术栈**：

| 层 | 技术 |
| --- | --- |
| 后端 | FastAPI + yt-dlp(Python API) + SQLModel/SQLite + uvicorn |
| 前端 | React 18 + Vite 8 + PIXI.js v6.5.10 + pixi-live2d-display 0.4.0 |
| 测试 | 后端 pytest（32 项）；前端 Vitest 5 + @testing-library/react + jsdom（32 项） |
| 语言运行时 | Python 3.12 / Node.js 18+ |
| 外部依赖 | ffmpeg（合并高清音视频流必需） |

**当前进度**：第一阶段（v1 后端 + 前端 + Live2D 基础）已完成并合并 main；第二阶段视觉升级的 Task 1（Live2D 竞态修复）、Task 2（点击角色切换模型）与 Task 3（霓虹色彩 token 系统 + UI 二次元语言）已完成；随后按用户要求简化：删除「初音未来」模型、仅保留「白」，角色改为响应式缩放（按屏幕高度等比）+ 可拖动，取消下载各阶段的场景表情/动作反馈；Task 4–6 未开始。另已建立工程约定（根 `CLAUDE.md` + 各文档「§0 工程约定」，见 §0）。

---

## 2. 术语表

| 术语 / 缩写 | 定义 |
| --- | --- |
| **Scene / SCENE** | 前端场景状态机的 6 个状态：`entry`（入口）、`parsing`（解析中）、`selecting`（选清晰度）、`downloading`（下载中）、`done`（完成）、`error`（出错）。定义于 `frontend/src/state/sceneMachine.js` 的 `SCENE` 常量。 |
| **sceneMachine** | 前端 reducer 状态机（`reduce` + `initialState`），唯一管理下载流程状态；视觉层只读不写。 |
| **PIXI** | `pixi.js` v6 渲染引擎，前端全屏舞台（canvas）。 |
| **Live2D** | 日系二次元可动角色；本项目用 `pixi-live2d-display/cubism4` 入口加载 `.model3.json`。 |
| **MODELS** | Live2D 模型注册表（`frontend/src/pixi/mascotConfig.js`），当前仅含「白」(bai) 一个模型。 |
| **DEFAULT_MODEL_ID** | 默认模型 id，恒等于 `MODELS[0].id`（当前为 `'bai'`），统一供初始加载/兜底/状态初始值使用。 |
| **StrictMode** | React 开发模式的「双重挂载」机制，会 mount → unmount → mount，是 Live2D 竞态 bug 的根因。 |
| **direct / server** | 下载两种模式：`direct` 直链（浏览器直接保存）；`server` 服务端下载（线程池 + 轮询 job 进度）。 |
| **job** | 服务端下载任务（SQLite `Job` 表），状态 `queued → downloading → done/error`。 |
| **error_type** | 后端归一化错误类型，共 9 种：`invalid_url` / `unsupported_site` / `age_restricted` / `geo_blocked` / `drm` / `login_required` / `ffmpeg_missing` / `network` / `quota`。 |
| **tier** | 前端性能分级：`high`（全效果）/ `low`（粒子减半+去滤镜）/ `none`（无 WebGL，CSS 兜底）。 |
| **webglSupported()** | 检测 WebGL 是否可用（决定是否挂 PIXI 舞台）。 |
| **onModelChange** | Live2D 层切换成功后的回调 `(nextId: string) => void`，通知 React 同步状态/弹提示。 |
| **playSfx(name)** | 合成音效播放器（`audioManager.js`），`name ∈ {paste, select, done, error}`。 |
| **ui-ux-pro-max / design-system** | 用户点名的两个设计 skill，用于第二阶段配色/字体方案。 |
| **Vite proxy** | 开发服务器把 `/api` 代理到 `http://localhost:8000`（`frontend/vite.config.js`）。 |

---

## 3. 目录结构与文件清单

### 后端 `backend/`

```
backend/
├── app/
│   ├── main.py               # FastAPI 入口：app 定义 + 限流中间件 + 挂载路由
│   ├── config.py             # Settings 配置（env 覆盖，全部集中于此）
│   ├── db.py                 # SQLModel engine + get_session + init_db
│   ├── models.py             # Job 模型 + JobStatus 枚举
│   ├── schemas.py            # Pydantic 请求/响应模型
│   ├── routes/
│   │   ├── parse.py          # POST /api/parse
│   │   └── download.py       # POST /api/download + GET /api/job/{id} + GET /api/file/{id}
│   └── services/
│       ├── ytdlp_service.py  # yt-dlp 封装：extract/classify_error/build_format_options/get_direct_url/download
│       └── jobs.py           # JobManager 线程池 + 进度 hook + TTL 清理
├── tests/                    # 9 个测试文件 + conftest.py（32 用例）
├── scripts/                  # install_ffmpeg.ps1 / .sh
├── requirements.txt
├── jobs.db                   # SQLite（运行时生成，被 .gitignore 忽略）
└── tmp/                      # 服务端下载产物（TTL 清理，被 .gitignore 忽略）
```

### 前端 `frontend/`

```
frontend/
├── index.html                # 入口，加载 live2dcubismcore.min.js
├── vite.config.js            # Vite 配置 + /api 代理 + Vitest 配置
├── package.json
├── public/live2d/            # Live2D 模型资源（bai/）
└── src/
    ├── main.jsx              # React 入口（<React.StrictMode>）
    ├── App.jsx               # 编排器：状态机 + PIXI 舞台 + 各场景渲染
    ├── api.js                # 前端 API 客户端（4 个接口封装）
    ├── state/sceneMachine.js # SCENE 常量 + reduce + ERROR_SCENES
    ├── pixi/
    │   ├── stage.js          # initStage/destroyStage/webglSupported/detectTier
    │   ├── background.js     # PIXI 背景（渐变 + 粒子）
    │   ├── mascot.js         # Live2D 角色创建/拖动/切换/特效（核心）
    │   └── mascotConfig.js   # MODELS 注册表 + DEFAULT_MODEL_ID
    ├── fx/constants.js       # 动画/交互共享常量（EASE + MODEL_SWITCH_FX）
    ├── hooks/useModelSwitcher.js # 模型切换 React 状态 hook
    ├── audio/audioManager.js # BGM/SFX 合成音效
    ├── components/
    │   ├── EntryScene.jsx / ParsingScene.jsx / SelectingScene.jsx
    │   ├── DownloadingScene.jsx / DoneScene.jsx / ErrorScene.jsx
    │   └── ui/               # Bubble / Danmaku / EnergyBar / About
    ├── styles/global.css     # 全部样式 + 霓虹 token
    └── test/setup.js         # Vitest setup（@testing-library/jest-dom）
```

---

## 4. 环境配置与运行

### 环境要求

- Python 3.12、Node.js 18+、ffmpeg（合并高清音视频流必需，缺失时服务端下载报 `ffmpeg_missing`）。

### 后端配置（环境变量）

全部集中定义于 `backend/app/config.py`，均可通过环境变量覆盖，均有默认值：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg 可执行文件路径（仅非默认值时传给 yt-dlp 的 `ffmpeg_location`） |
| `MAX_CONCURRENT` | `3` | 并发下载数上限 |
| `TEMP_DIR` | `<backend>/tmp` | 服务端下载临时目录（TTL 自动清理） |
| `MAX_FILE_SIZE` | `2147483648`（2GB） | 单文件大小上限（字节） |
| `TTL_SECONDS` | `3600` | 服务端产物保留时长（秒） |
| `DB_URL` | `sqlite:///<backend>/jobs.db` | SQLite 连接串 |
| `RATE_LIMIT` | `30` | 每 IP 每窗口请求上限 |
| `RATE_LIMIT_WINDOW` | `60` | 限流窗口（秒） |

默认路径已锚定到 `backend/` 目录，与启动 CWD 无关。

### 启动命令

**后端（当前已在后台运行）**：

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> ⚠️ **当前后台正在运行**：uvicorn 监听 `http://127.0.0.1:8000`，进程 CWD 为 `backend/`。新窗口无需重复启动，直接复用即可；如需重启，先停掉旧进程。

**前端（当前已在后台运行）**：

```bash
cd frontend
npm install          # 首次
npm run dev          # http://localhost:5173，/api 由 Vite 代理到 8000
```

> ⚠️ **当前后台正在运行**：Vite 监听 `http://localhost:5173`。

浏览器打开 `http://localhost:5173` 即可走完「解析 → 选清晰度 → 下载」。

> 注：仓库根目录存在 `.venv`（`E:\install_video\.venv`，非 `backend/.venv`）。README 快速启动里「`cd backend` 后创建 `backend/.venv`」的描述与实际情况略有出入，但 `python -m pytest` 已在当前环境跑通。

---

## 5. 测试方式

```bash
# 后端（pytest，32 项全绿）
cd backend && python -m pytest

# 前端（Vitest，32 项全绿）
cd frontend && npm test

# 前端 watch 模式
cd frontend && npm run test:watch
```

**测试基线必须保持全绿**：第二阶段每个任务落地后都要重跑两条命令确认 32/32 与 32/32 通过。

**手工冒烟（端到端主链路）**：前端粘贴 `https://www.youtube.com/watch?v=dQw4w9WgXcQ` → 解析 → 选清晰度 → 下载；或 `curl` 直测后端：

```bash
curl -X POST http://127.0.0.1:8000/api/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

---

## 6. 已完成事项（Task 1 / 2 / 3）

### Task 1：修复 Live2D 加载竞态（StrictMode 双重挂载）—— **已完成**

- **目标**：解决「Live2D 模型加载不出来，只看到静态兜底图」的问题。
- **根因**：`main.jsx` 用 `<React.StrictMode>` 双重挂载；`createMascot` 里 `await Live2DModel.from()` 返回时，第一次挂载的 `app` 已被 `destroyStage` 销毁，`app.screen` / `app.stage` 均被置为 `null`，后续 `place()` / `app.stage.addChild()` 抛 `TypeError: Cannot read properties of null`，落到兜底静态图。
- **方案**（三处，最小侵入）：
  1. `createMascot` 顶部在**任何 `await` 之前**同步捕获 `const W = app.screen.width; const H = app.screen.height;`，并声明 `let disposed = false;`。
  2. `place(instance, cfg)` 与 `createFallback` 改用捕获的 `W`/`H`（不再读 `app.screen`）。
  3. 每个 `await` 之后 + ticker 回调里加 `if (disposed || !app.stage) return;` 守卫；`destroy()` 里 `disposed = true`。
- **关键细节**：单用 `disposed` 标志不够——StrictMode 竞态下 pending 的 `Live2DModel.from()` 句柄从不会被 `destroy()` 置位，因此必须加 `!app.stage`（`app.destroy()` 会把 `stage` 置 `null`）作为「app 是否还活着」的可靠信号。
- **产出物**：`frontend/src/pixi/mascot.js` 重写（见 §3）。
- **验证**：浏览器控制台 0 错误、无 `[mascot] 模型加载失败` 警告，「白」Live2D 真正渲染（非兜底图）；`npm test` 32 通过。

### Task 2：点击角色切换模型 + 切换动画 + 指针分层 —— **已完成**

- **目标**：把「右上角 `<select>` 下拉切换」改为「点击 Live2D 角色本身 → 播放切换效果 → 循环切换（多模型间）」，并消除硬编码、解耦点击逻辑、抽象动画常量。（注：后续删除初音、仅保留白，单模型时切换自动禁用、仅保留拖动。）
- **完成内容**（对应 4 项重构要求）：
  1. **消除硬编码**：模型 id 不再写死，统一读 `DEFAULT_MODEL_ID`（`mascotConfig.js`）；切换动画的时长/缓动/粒子参数全部抽到 `fx/constants.js` 的 `MODEL_SWITCH_FX`；点击热区优先取模型局部包围盒（不外扩），退化时回落到 `cfg.hit` 配置盒，不写死像素。
  2. **解耦点击逻辑**：点击切换收敛到 `hooks/useModelSwitcher.js` 的 `useModelSwitcher()`，返回 `{ modelId, toast, onModelChange }`；PIXI 层完成切换动画后通过 `onModelChange(nextId)` 回调同步 React，不在 JSX 内联逻辑。
  3. **动画常量抽象**：`fx/constants.js` 导出 `EASE`（outCubic/inCubic/outQuad）与 `MODEL_SWITCH_FX`（fadeOut 160 / fadeIn 240 / burstCount 22 / burstSpeed 5 / burstDecay 0.92 / burstLife 36 / ringRadius 170）。
  4. **汇报与暂停**：已完成并暂停，未推进 Task 3。
- **关键实现**：
  - 指针分层：`stage.js` 把 `app.view.style.pointerEvents = 'auto'`（原 'none'）；`global.css` 把 `.ui` 设为 `pointer-events: none` 并仅对 `.ui button/input/select/textarea/a/label` 恢复 `auto`，让点击穿透到下方 canvas 角色，同时表单/按钮仍可点。
  - 切换流程 `cycleModel()`：`switching` 防连点 → `spawnSwitchFx`（光环扩散 + 粒子爆散，逐帧）→ 旧模型 `fadeAlpha` 淡出 → `loadModel(next)` → 交换 → 淡入 → `onModelChange(next.id)`。
  - 新增模型 toast（`.model-toast` 漫画气泡风）显示「已切换为「白」」，`useModelSwitcher` 播 `playSfx('select')` + 2.6s 后清除。
  - `About.jsx` 显示每个模型的署名（人物绘制/建模）行 + 授权说明（不再显示切换提示）。
- **产出物**：
  - 新增：`frontend/src/fx/constants.js`、`frontend/src/hooks/useModelSwitcher.js`
  - 修改：`pixi/mascot.js`（重写）、`pixi/stage.js`、`pixi/mascotConfig.js`（新增 fallback/hit/credit 字段 + DEFAULT_MODEL_ID）、`styles/global.css`、`App.jsx`、`components/ui/About.jsx`
- **验证**：浏览器 0 控制台错误；网络日志确认点击后加载了「白」模型文件；toast「已切换为」出现；`npm test` 32 通过（测试中 `webglSupported` mock 为 false，`createMascot` 不执行，删除 `<select>` 不影响用例）。

### 附带修复：PIXI 渲染崩溃（ParticleContainer → Graphics）

- **问题**：`background.js` 用 `new PIXI.ParticleContainer(...)` 装 `Graphics` 子元素（圆形粒子），触发 `TypeError: Cannot read properties of undefined (reading 'baseTexture')`，逐帧崩溃，可能连带阻塞模型渲染。
- **修复**：`ParticleContainer` → 普通 `PIXI.Container`（ParticleContainer 只支持 Sprite，不支持 Graphics）。
- **产出物**：`frontend/src/pixi/background.js`。

### Task 3：霓虹色彩 token 系统 + UI 二次元语言 —— **已完成**

- **目标**：把零散写死的色值收敛为三层 token（primitive→semantic→component），统一 `--neon-*` 前缀，落地二次元 UI 动效语言（彩虹描边/光晕/流光/速度线/斜切角/全息弹幕），并引入 Google Fonts。
- **完成内容**：
  1. **Token 系统**（`global.css` `:root`）：底 `--bg-deep #06060f` / `--bg-midnight #0d1b3e` / `--bg-purple #1a0f3a`；霓虹 `--neon-magenta #ff2d95` / `--neon-blue #2f7bff` / `--neon-cyan #22d3ee` / `--neon-lime` / `--neon-amber` / `--neon-coral` / `--neon-violet` / `--neon-mint` / `--laser-pink`；复合渐变 `--grad-aurora` / `--grad-holo`。改名：`--neon-pink`→`--neon-magenta`、`--amber`→`--neon-amber`；`--neon-blue` 改值（原 #22d3ee 实为青色 → 现 #2f7bff 真蓝，旧值由新 `--neon-cyan` 承接）。
  2. **字体 token**：`--font-display`（Orbitron 数字/HUD）、`--font-mono`（JetBrains Mono 等宽）、`--font-body`（中文系统栈）；替换 3 处硬编码 font-family。
  3. **对比度 token**：`--on-neon #06060f`（霓虹底深字，≥4.5:1 AA）；`button.laser-frame` 深底描边按钮例外保持白字。
  4. **无障碍**：补全局 `:focus-visible`（`outline: 2px solid var(--neon-cyan); outline-offset: 2px`）；`prefers-reduced-motion` 关闭魔法阵呼吸/能量条流光/按钮速度线/错误呼吸与灰暗。
  5. **Google Fonts**：`index.html` preconnect（googleapis + gstatic crossorigin）+ Orbitron 700;900 + JetBrains Mono 400;500（`display=swap`）。
- **skill 合规回改（skill 优先于计划）**：计划原含 `.laser-frame` 常驻 `hue-rotate 6s` 旋转动画，与 ui-ux-pro-max「每屏最多动 1–2 个关键元素」冲突，**已改为静态描边**（删除 `laser-spin` 关键帧）；每屏仅保留 1 个关键动画（入口魔法阵呼吸 / 下载能量条流光 / 错误呼吸或灰暗）。
- **产出物**：Modify `frontend/src/styles/global.css`、`frontend/index.html`；Create `docs/superpowers/specs/2026-09-22-neon-anime-theme.md`（三层 token 表 + 改名对照 + 动效/无障碍 + 工程约定）；Create 根 `CLAUDE.md`（工程约定）；5 个文档补「§0 工程约定」（design / requirements / README / frontend README / handover）。
- **验证**：`npm test` 32/32 通过；grep 确认无残留 `--neon-pink` / `laser-spin` / `hue-rotate`。
- **未覆盖（留 Task 4）**：`background.js` 的 PIXI 颜色仍硬编码（渐变 `#0b0f2a/#3a1c71/#0f3460`、粒子 `0xffc9e8/0x7ef9ff/0xffd700`），H-1 的 PIXI 侧未统一。

---

## 7. 未完成事项（Task 4 / 5 / 6）

> 详细执行计划原文见 `C:\Users\zxk\.claude\plans\immutable-sniffing-lemur.md`（该文件在用户家目录，不在仓库内）。以下为已构思好的完整计划摘录。

### Task 4：PIXI 背景重写 —— 樱花/气泡/星星/光尘/极光/粒子旋流 —— **未开始**

- **目标**：把「单渐变 Sprite + 120 圆点」重写为分层效果系统。
- **涉及文件**：Modify `frontend/src/pixi/background.js`
- **架构**：每个效果一个小函数，`createBackground(app, tier)` 组装；`setIntensity(scene)` 驱动速度/旋流开关。
- **分层（自底向上）**：
  1. 极光带（3-4 个大渐变 Sprite，`BlendMode.ADD`，hue 缓移）
  2. 光斑（2 个大柔和径向光晕）
  3. 星星（alpha 呼吸闪烁）
  4. 光尘（极慢漂移微粒子）
  5. 樱花（花瓣形 Graphics，下落 + 摆动 + 自旋）
  6. 气泡（半透明圆 + 高光，上升）
  7. 粒子旋流（`intensity>=1` 时粒子沿螺旋向中心/角色汇聚，隐喻「粒子汇聚进度」）
- **降级**：`tier='low'` 粒子减半、去滤镜、不卡；`intensityForScene` 保持 `PARSING/DOWNLOADING → 1`，其余 `0`。
- **硬编码隐患**：当前 `background.js` 所有颜色/速度/数量都是写死的（见 §16 报告 H-1）；Task 4 应把颜色收敛到与 Task 3 共享的 token。
- **验证**：`npm test` 通过；各阶段背景动效正常；`tier='low'`（临时改 `detectTier`）粒子减半。

### Task 5：引导角色漫画气泡（每阶段台词） —— **未开始**

- **目标**：角色上方显示每阶段台词漫画气泡。
- **涉及文件**：
  - Create `frontend/src/state/scriptConfig.js`
  - Create `frontend/src/components/ui/MascotBubble.jsx`
  - Modify `frontend/src/App.jsx`（渲染 MascotBubble）
  - Modify `frontend/src/styles/global.css`（气泡定位 + 动画）
  - Test `frontend/src/components/ui/MascotBubble.test.jsx`
- **预期接口**：
  - `scriptConfig.js`：`export const SCENE_SCRIPT = { [SCENE.ENTRY]: '把链接丢进来吧～', [SCENE.PARSING]: '让我想想…', [SCENE.SELECTING]: '选个清晰度嘛', [SCENE.DOWNLOADING]: '跑起来跑起来！', [SCENE.DONE]: '下载完成啦！', [SCENE.ERROR]: '呜…好像出错了' }`
  - `MascotBubble.jsx`：`{ scene }` → 读 `SCENE_SCRIPT[scene]` → 渲染 `.mascot-bubble`（`position:fixed` 指向角色、`pointer-events:none`、`key={scene}` 触发重放进场动画）。
- **测试**：断言 entry 显示「把链接丢进来吧～」、downloading 显示「跑起来跑起来！」。
- **验证**：`npm test`（37 用例）通过。

### Task 6：下载「粒子汇聚」进度 + 完成动画 + 整体验收 —— **未开始**

- **目标**：下载态三层反馈 + 完成爆散 + 端到端视觉验收。
- **涉及文件**：Modify `frontend/src/components/DownloadingScene.jsx`、`DoneScene.jsx`、`pixi/background.js`（确认旋流接入）。
- **内容**：进度层（PIXI 汇聚环，`setIntensity(1)` 已开旋流）+ 氛围层（花瓣/气泡加速）；完成态 `playSfx('done')` + CSS 庆祝爆散 + 「打开/保存文件」/「继续下载」。（角色不再随下载场景做表情/动作/奔跑，状态反馈由背景粒子 + 音频承担。）
- **整体验收**：`npm test` 全绿；playwright 依次走 `入口→解析→选清晰度→下载→完成`，逐阶段截屏，逐条对照用户 spec 核对（多层霓虹渐变/樱花/气泡/星星/光尘/漫画气泡/弹幕/发光能量条/粒子汇聚）；用真实链接验证 33MB mp4 可下。

---

## 8. 阻塞项

**无**。当前无阻塞 Task 4–6 的技术阻塞项。

> 说明：Live2D 竞态（Task 1）与 PIXI 渲染崩溃（附带修复）这两个原本阻塞视觉体验的问题已解决；后续任务纯增量视觉开发，无外部依赖阻塞。

---

## 9. 待确认项

| # | 待确认内容 | 需要的信息 | 由谁确认 |
| --- | --- | --- | --- |
| 1 | **模型切换接口命名与交互细节是否调整**（原文：是否需要调整接口命名或切换交互的细节？） | —— 已在第一步「收尾」中**采用最优方案并答复**：当前接口 `createMascot(app, modelId, { onModelChange })` + `onModelChange(nextId: string)` + `useModelSwitcher()` → `{ modelId, toast, onModelChange }` 命名清晰、配置驱动、已解耦，**保持不变，无需调整**。 | 用户（已答复：不改） |
| 2 | **已解决**：原「白无 expression/motion 文件、其他场景是否补表情/动作映射」的疑问已取消 —— 用户明确要求不做下载各阶段的场景表情/动作反馈，模型无需 expression/motion 文件。 | —— | 已解决 |
| 3 | 第二阶段配色最终是否**完全采用用户霓虹 spec**（已实测 `ui-ux-pro-max --design-system` 返回的 indigo+绿 SaaS 配色与用户 spec 冲突，决策为「用户 spec 覆盖」）。若用户后续想微调具体色值，需再确认。 | 最终色值表 | 用户 |
| 4 | 字体是否引入 Google Fonts（Orbitron + JetBrains Mono）。离线/内网环境无法访问 `fonts.googleapis.com` 时需改本地字体文件。 | 部署环境是否可访问外网 | 用户 / 部署方 |
| 5 | `.venv` 实际位于仓库根目录 `E:\install_video\.venv`（README 描述为 `backend/.venv`），是否更新 README 说明。 | 确认期望的 venv 位置 | 用户 |

---

## 10. 关键决策及原因

| 决策 | 原因 |
| --- | --- |
| **Task 1 用 `disposed || !app.stage` 双守卫，而非仅 `disposed`** | `app.destroy()` 会把 `stage` 置 `null`；StrictMode 竞态下 pending 的 `Live2DModel.from()` 句柄从未被 `destroy()` 置位，单 `disposed` 会漏判。`!app.stage` 是「app 是否还活着」的可靠信号。 |
| **切换动画参数（时长/缓动/粒子）抽到 `fx/constants.js`** | 落实用户「消除硬编码」的明确要求，组件/pixi 层不写死数字。 |
| **点击逻辑抽到 `useModelSwitcher` hook，PIXI 层只发 `onModelChange` 回调** | 落实「解耦点击逻辑」，React 状态与 PIXI 渲染分层。 |
| **模型切换采用「点击角色循环切换」，移除右上角 `<select>`** | 用户明确要求「点击那个 live2d 模型时出现切换这个模型效果展示」。 |
| **设计 skill 结果「用户霓虹 spec 覆盖 `ui-ux-pro-max` 默认配色」，仅采纳其字体配对** | `ui-ux-pro-max --design-system` 实测返回通用 SaaS 配色，与用户霓虹二次元 spec 冲突；用户 spec 为最高权威。 |
| **PIXI 粒子容器 `ParticleContainer → Container`** | ParticleContainer 仅支持 Sprite，装 Graphics 会逐帧崩溃。 |
| **第二阶段顺序：先修 bug/功能（Task 1–2）→ 再视觉系统（Task 3–5）→ 验收（Task 6）** | 先解决「模型不加载/不能点」两个硬伤，再上视觉，每任务独立可提交可验证。 |

---

## 11. 已知问题

| 问题 | 影响 | 状态 |
| --- | --- | --- |
| 前端 `App.jsx:52` `window.location.assign(d.url)`（直链下载）在 jsdom 测试中触发 `Error: Not implemented: navigation` 警告 | 无害（测试仍 32 通过），是直链下载的预期副作用 | 已知，不阻塞 |
| `docs/superpowers/plans/2026-09-22-phase2-cinematic-visual.md` 已被 `immutable-sniffing-lemur.md` 取代，但仍存在且 README 仍引用 | 文档冗余 | 建议删除或标注废弃 |
| 仓库根目录散落 7 张截图（`phase1-*.png` / `phase2-*.png|jpg`）与 `.playwright-mcp/` 未跟踪 | 工作区杂乱 | 建议清理或移入 `docs/` |
| Task 3 改动与工程约定文档**未提交**（`frontend/index.html`、`frontend/src/styles/global.css`、`docs/superpowers/specs/2026-09-22-neon-anime-theme.md`、根 `CLAUDE.md`、5 个含「§0 工程约定」的文档） | 若新窗口在**不同目录/worktree** 工作会丢失这些改动 | 建议先提交形成 Task 3 基线 |

---

## 12. 技术债

- **颜色双源（残留）**：Task 3 已把 CSS 侧收敛为 `:root` token，但 PIXI 渐变颜色（`background.js` `#0b0f2a/#3a1c71/#0f3460`、粒子 `0xffc9e8/0x7ef9ff/0xffd700`）仍硬编码，两处仍不同源，易漂移（Task 4 统一到与 token 共享的颜色模块）。
- **App.jsx 职责偏重**：编排逻辑 + 内联控制按钮视图 + 直链下载副作用混杂。
- **错误映射双份**：`sceneMachine.js` 的 `ERROR_SCENES`（文案）与 `ErrorScene.jsx` 的 `ERR_CLASS`（视觉 class）需手工同步 9 种 error_type。
- 详细清单见 §16 报告。

---

## 13. 风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 未提交的 Task 3 改动在异目录 worktree 丢失 | 高 | 新窗口务必在 `E:\install_video` 原地继续，或先提交 |
| 第二阶段大量视觉改动破坏下载闭环 | 中 | 坚持「只读原则」：视觉层只消费 `scene/job`，不改 `sceneMachine.reduce`，不 import 下载核心；每任务后 `npm test` 全绿 |
| Google Fonts 外网依赖 | 中 | 提供本地字体降级 |
| 低端设备性能（樱花/气泡/粒子叠加） | 中 | `detectTier()==='low'` 减半去滤镜、`prefers-reduced-motion` 关动画 |

---

## 14. 可复用资产

- **`MODELS` 注册表**（`mascotConfig.js`）：新增模型只需放文件到 `public/live2d/<id>/` 并在 `MODELS` 加一条，渲染层/切换 UI 自动感知。
- **`ERROR_SCENES` + `ERR_CLASS`**：9 种错误类型的文案/视觉映射。
- **`EASE` / `MODEL_SWITCH_FX`**（`fx/constants.js`）：可复用的缓动函数与动效参数。
- **`useModelSwitcher`**（`hooks/useModelSwitcher.js`）：模型切换状态管理模式，可复用于未来任何「PIXI 层回传 → React 同步」的场景。
- **`audioManager.js`**：合成音效（paste/select/done/error），无外部音频文件依赖。
- **限流中间件 + TTL 清理 + 线程池下载**（后端）：生产可用。

---

## 15. 扩展点

- **模型扩展**：`MODELS` 注册表（见 §14）。
- **场景扩展**：`SCENE` 增加新状态后，需同步 `SCENE_SCRIPT`（Task 5 将建）、`reduce`。
- **错误类型扩展**：后端 `classify_error` 新增 error_type 时，需同步前端 `ERROR_SCENES` + `ERR_CLASS`（有 `network` 兜底，风险中低）。
- **音效扩展**：`audioManager.js` 的 `SFX` 表新增合成音（如独立的 `switch` 音）。
- **清晰度档扩展**：后端 `HEIGHT_TIERS`（`ytdlp_service.py:62`）。
- **性能档扩展**：`detectTier()` 的 high/low/none 三级。

---

## 16. 全栈代码审查与重构建议报告（核心）

> 本报告基于对 `frontend/` 与 `backend/` 全部源文件的通读，按「写死处 / 耦合模块 / 非可扩展接口」三类，逐文件列出问题类型、严重程度（高/中/低）、具体位置与重构建议。**本报告是新窗口接手后的技术债清单与起跑线。**

### 16.1 硬编码清单（按文件）

| # | 文件:行 | 问题 | 严重度 | 重构建议 |
| --- | --- | --- | --- | --- |
| H-1 | `frontend/src/pixi/background.js:21-23,54` | 渐变三色 `#0b0f2a/#3a1c71/#0f3460`、粒子 `0xffc9e8/0x7ef9ff/0xffd700` 写死，与 `global.css` 的 `:root` token 是**两处不同源**（CSS 侧 Task 3 已 token 化，PIXI 侧仍硬编码） | **高** | Task 4 统一到与 CSS token 共享的颜色模块（JS 常量或读 CSS 变量） |
| H-2 | `frontend/src/pixi/background.js:50,54,58-60,70,75` | 粒子数量 `MAX=low?40:120`、颜色 `0xffc9e8/0x7ef9ff/0xffd700`、alpha `0.6`、速度 `0.4/0.2+rand*0.8/-5`、hue `+0.02`、`speed=1+intensity*2.5` 全部魔法数 | **高** | Task 4 重写时收敛到常量模块 |
| H-3 | `frontend/src/App.jsx:149-160` | 静音/轻量按钮用 inline `style`（`top:16/right:16/zIndex:10` 等），与 `.lightmode-toggle`（CSS 类）风格不一致 | 中 | 抽 `TopControls.jsx`，样式进 CSS 类 |
| H-4 | `frontend/src/App.jsx:18` | `POLL_MS = 3000` 轮询间隔魔法数 | 中 | 提到配置/常量模块（已注释 ≥2s 因限流，但值应命名） |
| H-5 | `frontend/src/styles/global.css:42-43` | `.model-toast` `top:20%/right:10%` 写死，未随 `mascotConfig` 的模型位置 `(0.82,0.62)` 推导 | 中 | toast 定位与模型位置建立关联（或用 CSS 变量） |
| H-6 | `frontend/src/styles/global.css:31-34` | `.lightmode-toggle` `top:56px/right:16px` 依赖静音按钮布局（`top:16px` + 按钮高） | 中 | 抽 `TopControls` 后统一布局 |
| H-7 | `frontend/src/hooks/useModelSwitcher.js:5` | `TOAST_MS = 2600` toast 时长魔法数 | 低 | 移入 `fx/constants.js`（Task 2 自己的「无硬编码」原则未覆盖此值） |
| H-8 | `frontend/src/components/ui/Danmaku.jsx:6,9` | 弹幕时长 `3000ms`、top 偏移 `10+(id*17)%60` 写死 | 低 | 提到常量模块 |
| H-9 | `frontend/src/api.js:1` | `API_BASE = '/api'` 写死（与后端路由前缀 `/api/` 分散在两处） | 低 | 与后端路由前缀建立单一来源说明 |
| H-10 | `backend/app/services/ytdlp_service.py:62` | `HEIGHT_TIERS=[2160,1440,1080,720,480,360]` 写死 | 低 | 若需可配则移入 `config.py`，否则保留（领域常量） |
| H-11 | `backend/app/services/ytdlp_service.py:105,115,157` | format_id 组合串 `bestvideo[height<=...]+bestaudio/...`、`best`、`merge_output_format:"mp4"` 写死 | 低 | 领域专用，保留但注释说明 |
| H-12 | `backend/app/routes/parse.py:9, download.py:16,35,46` | `/api/` 前缀写死在每个 router | 低 | 用 `APIRouter(prefix="/api")` 集中，避免 4 处改 |
| H-13 | `frontend/index.html:7`、`DownloadingScene.jsx:7`、`SelectingScene.jsx:4-9` | `<title>`、`'正在发送…/正在下载…'`、`formatDuration` 内联工具写死/内联 | 低 | 文案可入 `scriptConfig`/常量；工具可抽 util |

### 16.2 逻辑与视图耦合

| # | 模块 | 问题 | 严重度 | 建议 |
| --- | --- | --- | --- | --- |
| C-1 | `frontend/src/App.jsx` | 编排器同时承载：内联控制按钮视图（H-3）、直链下载副作用 `window.location.assign`（:52）、toast JSX、About JSX | **高** | 抽 `TopControls`、`downloadClient` 抽象（直链/服务端二选一），App 只做编排 |
| C-2 | `frontend/src/pixi/mascot.js`（约 300 行） | 混合：生命周期守卫、模型加载、拖动/点击热区、切换粒子特效、兜底 Sprite | 中 | 若继续膨胀，把 `spawnSwitchFx` 拆到 `fx/` 子模块 |
| C-3 | `frontend/src/pixi/background.js` | 渐变 + 单粒子循环混杂 | 中 | Task 4 本就整文件重写，无需单独处理 |

### 16.3 缺乏可扩展性的接口设计

| # | 位置 | 问题 | 严重度 | 建议 |
| --- | --- | --- | --- | --- |
| E-1 | `sceneMachine.js` `ERROR_SCENES` + `ErrorScene.jsx` `ERR_CLASS` | 9 种 error_type 需在**两处**手工同步；后端新增 error_type 时前端若不同步会漏 | 中 | 已确认 `ErrorScene.jsx:21` 有 `|| ERROR_SCENES.network` 兜底、`:26` `ERR_CLASS[...] || ''` 兜底，风险降为中低；建议把文案+视觉 class 合并为单一结构 `{emoji,title,hint,className}` |
| E-2 | `audioManager.js` `SFX` | 只有 4 个合成音，模型切换复用 `select`，无独立 `switch` 音 | 低 | 需要时在 `SFX` 表加 `switch` 项 |
| E-3 | 后端 `/api/` 前缀 + 前端 `API_BASE` | 前缀分散，改前缀需动 4 处 | 低 | 见 H-12 |

### 16.4 其他（文档/仓库卫生）

| # | 位置 | 问题 | 严重度 | 建议 |
| --- | --- | --- | --- | --- |
| O-1 | `docs/superpowers/plans/2026-09-22-phase2-cinematic-visual.md` | 已被取代但仍存在，README 仍引用 | 低 | 删除或标注废弃 |
| O-2 | 仓库根目录 | 7 张截图 + `.playwright-mcp/` 未跟踪 | 低 | 清理或归档到 `docs/` |
| O-3 | git 工作区 | Task 3 改动 + 工程约定文档未提交（Task 1/2 已提交于 `6b22795`） | 中 | 先提交再开工（见 §11） |

---

## 17. 第二阶段衔接建议

### 前置条件

1. 在 `E:\install_video` **原地**继续（或用同一 worktree），确保未提交的 Task 3 改动在（或先提交）。
2. 后端 `uvicorn 127.0.0.1:8000` 与前端 `vite localhost:5173` 已在后台运行（复用，不重复启动）。
3. 确认 `npm test`（32）与 `python -m pytest`（32）基线全绿。
4. 读取计划原文 `C:\Users\zxk\.claude\plans\immutable-sniffing-lemur.md`（Task 4–6 完整步骤；Task 3 已完成，见 §6）。

### 建议优先级

Task 4（PIXI 背景重写）→ Task 5（漫画气泡台词）→ Task 6（粒子汇聚 + 完成动画 + 验收）。
理由：Task 3 已定 token（CSS 侧），Task 4 需复用同一颜色来源（收敛 PIXI 侧，解决 H-1 双源债）；Task 5 数据驱动、独立；Task 6 收口并整体验收。

### 可并行任务

- Task 5（漫画气泡，纯前端数据 + 组件 + 测试）与 Task 4 的**依赖弱**，可与 Task 4 并行。
- Task 4 复用 Task 3 的 CSS token（收敛 PIXI 侧颜色），与 Task 3 的颜色来源依赖已在 Task 3 完成后解除。

### 风险点

- 大量视觉改动破坏下载闭环 → 严守「只读原则」，每任务后跑测试。
- 颜色双源债（H-1）残留：Task 3 已统一 CSS 侧，Task 4 需统一 PIXI 侧，否则持续漂移。
- Google Fonts 外网依赖（待确认项 #4）。

### 建议拆分

按 Task 4–6 逐任务「实现 → `npm test` → 截屏目验 → 提交」；每个任务一个独立 commit，便于回滚。执行方式二选一（推荐 Subagent-Driven：每任务新 subagent + 评审，快速迭代；或 Inline 本会话内推进，便于频繁截屏目验）。

---

## 18. 常见问题 FAQ

| 问题 | 解答 |
| --- | --- |
| 后端起来后 `/api/parse` 返回 429？ | 触发了限流（默认每 IP 每 60s 30 次）。等窗口滑过，或调 `RATE_LIMIT`/`RATE_LIMIT_WINDOW` 环境变量。 |
| 服务端下载报 `ffmpeg_missing`？ | 未装 ffmpeg 或不在 PATH。装 ffmpeg 或设 `FFMPEG_PATH` 环境变量。 |
| Live2D 模型不显示、只有静态图？ | ① 控制台是否还有 `[mascot] 模型加载失败`；② 检查 `public/live2d/<id>/<id>.model3.json` 是否存在；③ `index.html` 是否加载了 `live2dcubismcore.min.js`。Task 1 已修 StrictMode 竞态，若复现属新问题。 |
| 点击角色没反应？ | ① `stage.js` 是否 `app.view.style.pointerEvents='auto'`；② `global.css` 是否 `.ui { pointer-events: none }` 且控件恢复 auto；③ 模型是否加载成功（兜底图无交互）。注：单模型时点击不切换（切换需 ≥2 模型），但可拖动角色。 |
| 前端测试报 `Not implemented: navigation`？ | 无害。是直链下载 `window.location.assign` 在 jsdom 的预期警告，不影响 32 通过。 |
| `npm test` 用了 `webglSupported` mock 为 false？ | 是。`createMascot` 在测试环境不执行，故 Task 2 删除 `<select>`、新增 hook 不影响用例。 |

---

## 19. 注意事项

1. **当前后台运行的服务**：
   - 后端 uvicorn：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`，监听 **`http://127.0.0.1:8000`**。
   - 前端 Vite：`npm run dev`，监听 **`http://localhost:5173`**。
   - 新窗口**复用现有进程，不要重复启动**；如需重启，先停旧进程（避免端口占用）。
2. **测试命令**：后端 `cd backend && python -m pytest`（32）；前端 `cd frontend && npm test`（32）。任何改动后必须重跑确认全绿。
3. **只读原则**（来自计划全局约束）：视觉层只消费 `scene`/`job`，绝不改 `sceneMachine.reduce` 的下载状态、绝不 import 下载核心。任何视觉失效不得影响下载闭环。
4. **降级链**：`prefers-reduced-motion` 关动画；`detectTier()==='low'` 粒子减半、去滤镜；`'none'` 走 `.css-fallback`。
5. **Live2D 入口**：必须继续 `import { Live2DModel } from 'pixi-live2d-display/cubism4'`（`index.html` 只加载了 `live2dcubismcore.min.js`）。
6. **提交前先看 §11 / §16.4-O-3**：Task 3 改动与工程约定文档尚未提交，建议先提交形成干净基线。
7. **禁止编造**：本文所有「待确认」均已标注；未标注的均为已核实事实。

---

*（文档结束）*
