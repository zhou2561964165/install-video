# 方案设计文档 · 万能视频下载网站

> 版本：v1（2026-09-20）
> 对应需求：见 `docs/requirements.md`
> 本文档是**技术设计基准**。所有「预留扩展点」在实现时通过接口隔离，后续拓展不触碰下载核心。

---

## 0. 工程约定（每次遵守）

> 与根目录 `CLAUDE.md` 一致（最高优先级）。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。

---

## 1. 架构总览

采用 **FastAPI 进程内直接调用 yt-dlp Python API**（方案 A，已选）：

```
[前端 React/Vite]  ⇄ HTTP/JSON  ⇄  [FastAPI 后端]
                                      │
                        ┌─────────────┼─────────────┐
                        │   yt-dlp 服务层          │  线程池 + 并发上限
                        │  extract_info / download │  （任务状态落 SQLite）
                        └─────────────┼─────────────┘
                                      │
                                临时文件目录（TTL 自动清理）
```

**选型理由**：yt-dlp 是 Python，进程内用其官方 API 代码最少、结构化 format 信息直接可用、进度与错误处理干净；下载为阻塞 I/O，用线程池即可支撑 v1 并发。

**备选方案（已否决）**：
- 方案 B：subprocess 调 `yt-dlp` 命令行 —— 与 CLI 解耦但需自解析 JSON/进度/错误，更脆。
- 方案 C：基于现成 yt-dlp-web-ui 改皮肤 —— 技术栈冲突，重写前端反而更费劲。

## 2. 技术选型

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 后端 | Python 3.12 + FastAPI | 与 yt-dlp 同语言 |
| 下载核心 | yt-dlp（Python API） | 进程内调用 |
| 任务存储 | SQLite + SQLModel | 轻量，后续可换 PostgreSQL |
| 前端 | React + Vite | 二次元交互式视觉 |
| 视觉/动效 | CSS + 可选 Three.js / Canvas / Lottie | 二次元场景 |
| 媒体合并 | ffmpeg | 视频流+音频流合并出高清（必需） |

## 3. 目录结构

```
install_video/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 入口、中间件（限流）
│   │   ├── config.py              # ffmpeg 路径、并发数、临时目录、大小上限、TTL
│   │   ├── db.py                  # SQLite / SQLModel 引擎与会话
│   │   ├── models.py              # Job + User + Quota（v2 已建表）
│   │   ├── schemas.py             # Pydantic 请求/响应
│   │   ├── routes/
│   │   │   ├── parse.py           # POST /api/parse
│   │   │   ├── download.py        # POST /api/download, GET /api/job/{id}, GET /api/file/{id}
│   │   └── services/
│   │       ├── ytdlp_service.py   # 封装 yt-dlp（解析/下载/进度/错误分类）
│   │       ├── jobs.py            # 线程池 + 任务生命周期 + 临时文件清理
│   ├── requirements.txt
│   └── scripts/install_ffmpeg.*   # 一键下载 ffmpeg
├── frontend/                      # React + Vite
│   └── src/
│       ├── App.jsx
│       ├── api.js                 # 后端接口封装
│       └── scenes/                # 二次元场景组件（登录页/解析/进度/错误）
├── docs/
│   ├── requirements.md            # 需求文档
│   └── design.md                  # 本文档
└── README.md
```

## 4. 核心数据流

```
1. POST /api/parse {url}
   → ytdlp_service.extract_info(url, download=False)
   → 返回 {title, thumbnail, duration, duration_string, uploader, platform,
           view_count, upload_date, description, subtitles,
           formats:[{format_id, label, height, ext, resolution, filesize,
                     has_audio, vcodec, acodec, direct(是否有直链), note}]}

2. POST /api/download {url, format_id, mode?}
   → 判定下载方式（见 §5）
   → 建 Job（status=queued）→ 线程池执行下载
   → 返回 {mode:"direct", url, headers} 或 {mode:"server", job_id}

3. GET /api/job/{id}（前端轮询进度 / 后续可换 SSE）
   → {status, progress, title, error_type, error}

4. GET /api/file/{job_id}（服务端模式下）
   → 文件流（Content-Disposition 触发浏览器/手机保存）
```

## 5. 下载方式：直链 + 服务端自动切换

- **解析时**：为每个清晰度标记直链是否可用及所需请求头（`format['url']` + `http_headers`）。
- **下载时**：
  1. 直链可用 → 返回 `{mode:"direct", url, headers}`，前端直接浏览器下载；
  2. 直链不可用/过期/需 cookie → 自动落到服务端下载 `{mode:"server", job_id}`；
  3. UI 提供「强制走服务器」开关兜底。
- **服务端下载**：`YoutubeDL.download()` 到临时目录，`progress_hooks` 更新 Job 进度；完成后由 `/api/file/{id}` 流式回传。前端轮询到 `done` 后经 `lib/saveFile.js`（`<a download>`）自动触发浏览器保存，无需手动点链接。
- **ffmpeg 合并阈值（`FFMPEG_MIN_HEIGHT = 1080`）**：音视频分离流需 ffmpeg 合并，仅对 `>= 1080p` 的档位开放；低于 1080p 的档位只用渐进式直链，无直链则跳过该档（不触发 ffmpeg）。

## 6. 数据模型

```
Job:
  id(uuid) · url · title · format_id · status(queued/downloading/merging/done/error)
  progress(0-100) · file_path · file_size · error_type · error
  created_at · updated_at · expires_at
  user_id(可空 FK→User，匿名任务为 null)

【v2 已建表（2026-09-24）】
User:   id(uuid) · email(unique) · password_hash · created_at
Quota:  user_id(FK→User) · date(UTC 日期串) · downloads_used · limit  — (user_id, date) 复合唯一
```

## 7. 临时文件与防滥用

- 临时目录按任务隔离；完成后 **TTL 自动删除**（默认 1 小时），防止磁盘被吃满。
- **并发上限**（默认 3）+ **每 IP 限流** + **文件大小上限**：轻量中间件实现（内存/DB 计数）。
- 接口层隔离，后续接账号额度时不动下载核心。

## 8. 错误处理（统一分类）

yt-dlp 异常 → 结构化错误类型，前端据此渲染对应「二次元错误场景」：

| error_type | 触发 |
| --- | --- |
| invalid_url | 非 URL / 无法识别 |
| unsupported_site | 站点不支持 |
| age_restricted | 年龄限制 |
| geo_blocked | 地区限制 |
| drm | 受保护内容 |
| login_required | 需登录 |
| ffmpeg_missing | 缺少 ffmpeg |
| network | 网络错误 |
| quota | 达到额度/并发上限 |

## 9. 预留扩展点（后续拓展的关键）

| 未来功能 | 现有隔离边界 | 扩展方式（不碰下载核心） |
| --- | --- | --- |
| 账号 / 登录 | ✅ 已实现（v2） | `routes/auth.py` + `services/auth.py`（JWT + `Depends` 注入，匿名可选鉴权） |
| 每用户额度 | ✅ 已实现（v2） | `services/quota.py` `check_and_reserve`，路由层提交即扣（直链/服务端同计） |
| 任务队列扩展 | `jobs.py` 定义 `TaskRunner` 接口 | 换成 Celery/Redis 实现 |
| 视频总结 | `routes/` 独立路由 | 下载完成后调 LLM，独立模块 |
| 字幕翻译 | 同上 | 独立模块 |
| 付费 | Quota 数据模型预留 | 支付回调 → 更新 Quota |

**核心约束**：`ytdlp_service.py` 是唯一接触 yt-dlp 的层；其余模块只依赖它的接口（`extract_info` / `download` / 进度回调）。任何扩展都不得直接 import `yt_dlp`。

## 10. 测试策略

- **单元测试（pytest）**：格式解析与清晰度归并、错误分类（mock yt-dlp）。
- **集成测试**：`/api/parse`、`/api/download`、`/api/job/{id}` 用固定测试 URL 或 mock extractor。
- **手工验收**：本地起服务，粘贴真实链接，验证「解析 → 清晰度 → 下载 → 可播放」，并在手机浏览器验证下载。

## 11. 环境与部署

- 开发机需装：`pip install yt-dlp` + **ffmpeg**（合并视频/音频流必需，提供 `scripts/install_ffmpeg.*` 一键脚本）。
- 生产（Linux VPS）：`apt install ffmpeg`；或 Docker 镜像内置 ffmpeg + yt-dlp。

## 12. 迭代路线图

1. **v1（已完成）**：核心下载闭环（解析/清晰度/下载）+ 二次元前端体验 + 直链/服务端切换 + 防滥用基础。
2. **第二阶段（前端电影感视觉升级，进行中）**：蒙版揭幕/虹膜转场/几何画框/章节台词/自定义光标/分段按钮/缠绕进度，见 §13 与 `docs/superpowers/plans/2026-09-22-phase2-cinematic-visual.md`。
3. **v2（已完成 2026-09-24）**：账号 + 每用户额度（注册/登录 JWT + 每用户每日额度，匿名下载保留）。
4. **v3（候选）**：视频总结、字幕翻译（接入 LLM）。
5. **v4（候选）**：付费能力。

## 13. 第二阶段：前端视觉表现层（fx）架构

> 第二阶段把前端从「炫彩工具页」升级为「可交互的二次元短篇体验」。核心原则：视觉表现层**只读**场景状态，**绝不修改下载状态、绝不 import 下载核心**；下载核心也不依赖视觉层。

### 13.1 分层

沿用 v1 的「单一 PIXI 管线 + DOM UI 叠加」，新增一个 `frontend/src/fx/` 表现层：

```
frontend/src/
├── state/
│   ├── sceneMachine.js         # v1：场景状态机（不动）
│   └── scriptConfig.js         # 新增：章节台词配置（数据驱动）
├── pixi/                       # v1：背景 + Live2D 角色（不动）
├── fx/                         # 新增：电影感表现层（纯配置/纯函数）
│   ├── transitions.js          #   SCENE_TRANSITION + TRANSITION_TYPES + transitionForScene()
│   └── cursor.js               #   SCENE_CURSOR + cursorForScene()
└── components/
    ├── ui/                     # 新增 UI 组件
    │   ├── Subtitle.jsx         #   章节台词字幕条
    │   ├── Frame.jsx            #   几何画框（四角括号）
    │   ├── TransitionOverlay.jsx #  转场覆盖层（按 scene 播动画）
    │   ├── Cursor.jsx           #   自定义动画光标
    │   ├── SegmentedButton.jsx  #   分段分层主按钮
    │   └── PathProgress.jsx     #   缠绕式进度（SVG path）
    └── …（v1 场景组件不变）
```

### 13.2 预留扩展点（第二阶段 → 后续）

| 未来能力 | 本阶段预留的接口 / 配置 | 扩展方式（改配置不改代码） |
| --- | --- | --- |
| 新场景 / 新错误类型 | `scriptConfig.js`（`SCENE_SCRIPT` / `ERROR_SCRIPT`）、`SCENE_TRANSITION`、`SCENE_CURSOR` | 各加一条配置 |
| 视频总结 / 字幕翻译台词注入（v3） | `Subtitle` 只消费 `SCENE_SCRIPT[scene]` | v3 在台词来源前插一层，注入 LLM 文案 |
| 字幕逐字动画 / 多行堆叠 | `Subtitle` 的台词配置 `{ line }` 可演进为 `{ lines[], anim }` | 后续阶段加字段 + CSS，对应参考站 `anim-letter` / `position_N`；本阶段 YAGNI 不实现 |
| 主题切换（多套氛围） | `Frame` 用 CSS 变量驱动；配色集中在 `:root` | 换主题 = 换 CSS 变量表 |
| 队列 / 批量 / 总结进度 | `PathProgress` 通用组件（`path` + `value` props） | 直接复用，业务层只喂 value |
| 更多转场样式 | `transitions.js` 的 `TRANSITION_TYPES` | 新增类型 + 对应 CSS 动画 |

**核心约束（与后端 §9 对齐）**：视觉表现层不得感知下载核心（不 import `api.js` 的下载逻辑、不改 `sceneMachine.reduce` 的下载状态）；下载核心不得依赖视觉层。二者通过「场景状态」单向解耦——视觉层消费 `scene`，仅此而已。

### 13.3 降级策略

- `prefers-reduced-motion`：转场/光标动画关闭，退化为无动画。
- 「轻量模式」/ 低端机（`detectTier() === 'low'`）：跳过 canvas 光标、简化转场；画框/台词（纯 DOM）保留。
- 移动端触摸：无鼠标，光标自动隐藏。
- 任何视觉失效都不影响下载闭环。

## 14. 视觉重设计（lolimeow 主题，Task A/B/C 已完成）

> **⚠️ 已被 pidanai 重构替代（2026-09-24）**：本节记录的是 lolimeow 主题（紫罗兰 `--violet-*` + slate，accent `#8b3dff`）。当前代码已重构为「深色液态玻璃 + 樱花粉辉光」——`--sakura-*` + `--ink-*` + `--refract-*`（五色折射）+ `--gray-*`，accent `#d6336c`，深色默认 + 三档主题（浅/深/自动）。当前主题的分析见 `docs/ui-refactor-pidanai.md`（token 对照/组件映射/解耦/分步），扩展方法见 `docs/ui-extension-guide.md`。§14.6（待机动画 `IDLE`）与 §14.8（表情/道具 `EXPRESSIONS` 数据驱动机制）**未被推翻、仍准确**；§14.1–14.5/14.7 的「紫罗兰配色」描述已被 pidanai 覆盖。

> 用户反馈原「深色霓虹二次元」UI 太差、Live2D 角色不动。按参考站 `baomihuahua/lolimeow`（设计语言）+ `Misaka273/lolimeow-shiroki`（玻璃拟态/粒子打磨）重做视觉。原「霓虹二次元」方向（§12 第二阶段电影感视觉）已被本方案替代。

### 14.1 三层 token（design-system 落地）

- **primitive**：紫罗兰阶 `--violet-*` + slate 灰阶 `--slate-*`（原始值）。
- **semantic**：`--accent`/`--accent-hover`/`--accent-soft`/`--accent-lilac`/`--accent-pink`/`--surface`/`--surface-raised`/`--surface-glass`/`--text-primary|secondary|muted`/`--border`/`--border-strong`/`--shadow-*`。
- **component**：`--btn-*`、`--card-radius`(12px)、`--pill-radius`(999px)、`--font-body`、`--dur`、`--ease`。

配色：强调色紫罗兰 `#8b3dff`（hover `#6f31cc`，高亮 `#d87cff`/`#f59dff`）；文字 slate `#0f172a→#64748b`；边框 `#e2e8f0`；浅色底 `#fff`、深色底 `#0e0e0e`。

### 14.2 浅/深主题

- `document.documentElement.dataset.theme` 切换，CSS `[data-theme='dark']` 小块覆盖 surface/text/border token；**强调色（accent）跨主题恒定**，因此 PIXI 侧调色板跨主题不变。
- 原「轻量模式」按钮（其实是 WebGL 开关）改名为真正的浅/深主题切换；WebGL 兜底回归自动（仅 `!webgl` 走 CSS 渐变）。

### 14.3 视觉语言（替代霓虹 gimmick）

- 移除：`.magic-circle`/`.laser-frame`/`.rainbow-outline`/`.danmaku`/`.burst`/`.speed-lines`/斜切 clip-path/`.float-on-hover` RGB 分离光晕。
- 落地：白色圆角卡片 + 玻璃拟态（`backdrop-filter: blur`）、紫罗兰胶囊主按钮、胶囊单选清晰度（选中紫罗兰填充）、细圆角进度条、图标化完成/错误气泡；错误场景差异化动画收敛为克制的紫罗兰光晕（保留 `err-invalid`/`err-quota`/`err-drm` 类名语义，`data-testid`/`energy-bar` 等类名不破，测试 32/32）。
- 字体：Google Fonts `Noto Sans SC` 400/500/700 + URL 输入等宽 `JetBrains Mono`。

### 14.4 PIXI 侧颜色收敛

- `pixi/theme.js` 的 `palette` 改读语义 token（`--accent` 等），fallback 与当前值一致。
- `pixi/background.js` 粒子/极光/光斑换成紫罗兰/淡紫系，数量/透明度整体下调（参考 shiroki 克制度）；`intensityForScene` 与降级链不变。

### 14.5 主题数据来源（解耦）

CSS 与 PIXI 颜色单一来源 = `global.css` 的 `:root` 语义 token；`theme.js` 仅在无 DOM（jsdom 测试）时用 fallback。视觉表现层仍只读场景状态，不触碰下载核心。

### 14.6 待机动画（Task D，程序化驱动）

「白」的 `model3.json` 的 `Motions` 只挂了 `edle` 装饰特效（单个星光特效，非呼吸/待机动作）、且无 `Breath` 字段，角色本身不会自动呼吸/摆动。因此用 `pixi/mascot.js` 的 `startIdle()`：`app.ticker` 逐帧正弦写 `coreModel.setParameterValueById`，驱动 `ParamAngleX/Y/Z` + `ParamBreath`（均为物理输入），头摆经物理级联出身体/头发摆动。驱动参数名/振幅/频率/相位全部在 `mascotConfig.js` 的 `IDLE` 配置（数据驱动）；运行时按 `coreModel.getParameterIndex` 过滤缺失参数，全缺失时退化为容器级 scale 呼吸。尊重 `prefers-reduced-motion`（完全静止）。

### 14.7 模型升级（完整版「白」）

由免费版升级为作者提供的完整版（`白.moc3` 9.7MB / 46 个表情 / `edle.motion3.json` / 42 组物理）。随之调整：
- `mascotConfig.js`：`url`/`fallback.url` 指向 `白.model3.json` / `白.16384/texture_00.png`。
- 删除 `hideParts`（免费版水印隐藏）——完整版无水印 Part，且配置从未填 `hiddenParts`，属死代码。
- 保留 `startIdle` 待机（完整版仍无呼吸动作）。
- 表情（46 个）与 `edle.motion3.json` 已随模型拷入 `public/live2d/bai/`；表情/道具/装饰特效接入见 §14.8。
- 16K 纹理（16384×16384）在开发机已正常上传（显卡显存充足）；移动端/低端 GPU 的 `MAX_TEXTURE_SIZE` 兼容风险仍保留（见 `frontend/README.md` 已知限制）。

### 14.8 表情 / 道具系统（46 表情接入）

完整版「白」带 46 个 `.exp3.json`，每个 = 单参数 `{Id, Value:1, Blend:'Add'}`。标准 expression manager 是**单选**（一次一个 currentExpression），无法「换发型 + 换衣服 + 戴耳机」并存；因此走**直接写参数** `coreModel.setParameterValueById(paramId, 1/0)`，可任意多选并存，且与待机正弦驱动（`IDLE`）参数不重叠、互不冲突。参数名/分组/节奏全部进 `mascotConfig.js` 的 `EXPRESSIONS`（数据驱动）。

- **阶段映射（`EXPRESSIONS.stage`）**：解析中→圈圈眼(Param40)、选清晰度→煎蛋眼(Param38)、下载中→圈圈眼(Param40)、完成→星星眼(Param41)、出错→生气(Param43)、入口→无。
- **随机道具（`EXPRESSIONS.random`）**：拿手柄(Param35) / 拿话筒(Param32) / 戳脸(Param31)，每 ~20s 随机展示 ~4s 收回。
- **点击换装菜单（`EXPRESSIONS.menu`，6 组 39 项）**：发型(9, single) / 衣服(4, single) / 大小变(1, toggle) / 配饰(16, multi，含创可贴×4) / 颜色(5, multi) / 情绪(4, multi：黑脸/血迹/哭/脸红)，`ExpressionMenu.jsx` 只读配置渲染。**46 个表情已全量暴露，无闲置。**
- **装饰特效（`EXPRESSIONS.effect` → `edle.motion3.json`）**：单个「星光闪烁」循环装饰动作（`Meta.Loop=true`，~11.9s；`白.model3.json` 的 Motions 仅挂这一个文件、且该文件无 Motions 数组，并非多特效）。命中 `stages`（默认 `done`/`error`）时由 `setStageEffect` 调 `model.motion(group, index, MotionPriority.IDLE)` 循环播放，其余场景 `motionManager.stopAllMotions()` 停止。`edle` motion 已注册进 `白.model3.json` 的 `FileReferences.Motions`；motion 文件按需懒加载（首次触发 `motion()` 时才请求）。
- **模型切换已删除**（`cycleModel` / 切换特效 / `useModelSwitcher` / toast）。
