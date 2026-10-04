# 方案设计文档 · 万能视频下载网站

> 版本：v3（2026-10-03；历史视觉方案另作标记）
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
| 视觉/动效 | CSS + PIXI v6 + pixi-live2d-display | 单一PIXI管线与Live2D；未引入Three.js/Lottie |
| 媒体合并 | ffmpeg | 视频流+音频流合并出高清（必需） |

## 3. 目录结构

```
install_video/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 入口、中间件（限流）
│   │   ├── config.py              # 下载/鉴权/字幕来源/LLM配置
│   │   ├── db.py                  # SQLite / SQLModel 引擎与会话
│   │   ├── models.py              # Job + User + Quota（v2 已建表）
│   │   ├── schemas.py             # Pydantic 请求/响应
│   │   ├── routes/
│   │   │   ├── parse.py           # POST /api/parse
│   │   │   ├── download.py        # POST /api/download, GET /api/job/{id}, GET /api/file/{id}
│   │   │   ├── auth.py            # JWT注册/登录/me
│   │   │   ├── subtitle.py        # 字幕内容读取/翻译
│   │   │   └── summary.py         # AI内容总结
│   │   └── services/
│   │       ├── ytdlp_service.py   # 封装 yt-dlp（解析/下载/进度/错误分类）
│   │       ├── jobs.py            # 线程池 + 任务生命周期 + 临时文件清理
│   │       ├── auth.py / quota.py  # 鉴权与路由层每日额度
│   │       ├── subtitle_sources.py # 公开平台来源适配，由ytdlp_service调用
│   │       ├── bilibili_subtitle_source.py # 匿名BV/分P字幕元数据，可信来源与输入校验
│   │       ├── subtitle_service.py # 正文HTTP与文本化
│   │       └── llm_service.py      # 去重、分段归纳、分层合并与兼容传输
│   └── scripts/install_ffmpeg.*   # 一键下载 ffmpeg
├── frontend/                      # React + Vite
│   └── src/
│       ├── App.jsx
│       ├── api.js                 # 后端接口封装
│       ├── components/            # 登录/解析/选择/进度/错误与视频智能面板
│       ├── hooks/                 # useAuth / useDownload / useVideoInsights
│       ├── state/                 # 下载状态机与语言配置
│       └── pixi/                  # 舞台、角色与背景纯表现层
├── docs/
│   ├── requirements.md            # 需求文档
│   └── design.md                  # 本文档
├── pyproject.toml            # Python 依赖声明（uv 管理）
├── uv.lock                   # 锁文件（纳入版本库）
└── README.md
```

## 4. 核心数据流

```
1. POST /api/parse {url}（Authorization: Bearer <token> 必需）
   → ytdlp_service.extract_info(url, download=False)
   → 返回 {title, thumbnail, duration, duration_string, uploader, platform,
           view_count, upload_date, description, subtitles,
           formats:[{format_id, label, height, ext, resolution, filesize,
                     has_audio, vcodec, acodec, direct(是否有直链), note}]}

2. POST /api/download {url, format_id, mode?}（Authorization: Bearer <token> 必需）
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
  user_id(可空 FK→User；新任务必填，nullable 仅兼容 v1 历史数据)

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
| 账号 / 登录 | ✅ 已实现（v2） | `routes/auth.py` + `services/auth.py`（JWT + `Depends(get_current_user)`；解析/下载必须登录） |
| 每用户额度 | ✅ 已实现（v2） | `services/quota.py` `check_and_reserve`，路由层提交即扣（直链/服务端同计） |
| 任务队列扩展 | 当前 `JobManager.submit_download` + `ThreadPoolExecutor` | 未来先定义TaskRunner窄协议，再接Celery/Redis；当前未实现这些类 |
| 视频总结 | ✅ v3 MVP | `routes/summary.py` → `llm_service.py`，显式请求、独立于下载任务 |
| 字幕翻译 | ✅ v3 MVP | `routes/subtitle.py` → `subtitle_service.py` / `llm_service.py` |
| 付费 | Quota 数据模型预留 | 支付回调 → 更新 Quota |

**核心约束**：`ytdlp_service.py` 是唯一接触 yt-dlp 的层；其余模块只依赖它的接口（`extract_info` / `download` / 进度回调）。任何扩展都不得直接 import `yt_dlp`。

## 10. 测试策略

- **单元测试（pytest）**：格式解析与清晰度归并、错误分类（mock yt-dlp）。
- **集成测试**：`/api/parse`、`/api/download`、`/api/job/{id}` 用固定测试 URL 或 mock extractor。
- **手工验收**：本地起服务，粘贴真实链接，验证「解析 → 清晰度 → 下载 → 可播放」，并在手机浏览器验证下载。

## 11. 环境与部署

- 开发机需装：[uv](https://docs.astral.sh/uv/)（`uv sync` 依 `pyproject.toml` 装依赖）+ **ffmpeg**（合并视频/音频流必需，提供 `backend/scripts/install_ffmpeg.*` 一键脚本）。
- 生产（Linux VPS）：`apt install ffmpeg`；或 Docker 镜像内置 ffmpeg + yt-dlp。

## 12. 迭代路线图

1. **v1（已完成）**：核心下载闭环（解析/清晰度/下载）+ 二次元前端体验 + 直链/服务端切换 + 防滥用基础。
2. **第二阶段（历史视觉计划）**：电影感手法见§13与旧计划；当前UI已改为深色液态玻璃/樱花粉主题，不把旧电影感清单自动列为未完成任务。
3. **v2（已完成，2026-10-03 收口）**：账号 + 每用户额度（注册/登录 JWT + 每用户每日额度；解析/下载强制登录）。
4. **v3（MVP 已完成，2026-10-03）**：字幕抓取、字幕翻译、视频总结；见 `docs/superpowers/plans/2026-10-03-v3-video-intelligence.md`。
5. **v4（候选）**：付费能力。

### 12.1 v3 视频智能架构

- `ytdlp_service.py` 新增只读字幕轨道查询接口，仍是唯一 import `yt_dlp` 的模块。
- `subtitle_service.py` 负责轨道选择、HTTP 获取和 VTT/SRT/JSON3/TTML 文本化，不感知下载任务。
- `llm_service.py` 定义总结/翻译窄接口，OpenAI-compatible 传输细节封装在内部；配置缺失返回 `llm_unconfigured`。
- AI 总结先清理重复行，再按 `LLM_SUMMARY_CHUNK_CHARS` 分段归纳；超长结果分层合并，保持全局输出为现有摘要与要点结构。字幕源文件和翻译流程不做全局去重。
- `subtitle_sources.py` 提供注册式公开平台适配器，由 `ytdlp_service.py` 唯一调用。Archive.org 总结内容优先从官方字幕附件元数据获取，无需先解析视频下载信息；不可用时回退 yt-dlp。文件级字幕使用去除已识别后缀后的精确内容关联，避免混入其他视频。
- `routes/subtitle.py` 与 `routes/summary.py` 使用 `Depends(get_current_user)`，同步路由交由 FastAPI 线程池执行。
- 前端通过 `api.js` + `useVideoInsights` 调用，`VideoInsights` 只接收 props；现有下载 reducer 和 `useDownload` 不变。
- 解析阶段的字幕发现可能是可选查询，空语言列表不会隐藏视频智能动作：面板提供自动选源语言和显式用户触发；请求失败就地展示，下载状态和额度互相隔离。

### 12.2 增量平台与验收边界

新增公开字幕元数据适配器继续返回既有标题与轨道格式，通过 `subtitle_sources.py` 注册，再由 `ytdlp_service.py` 统一调用；适配器无轨道或失败时保留通用提取。需要新字幕正文格式时只扩展 `subtitle_service.py` 的格式解析入口，不让路由接触平台JSON。

当前注册Archive与Bilibili。原生payload由唯一入口附内部来源标记；选轨道/正文获取/解析失败时，字幕服务最多一次调用 `use_public_sources=False` 的通用路径，通用仍失败则保留原生错误。上游inline `data` 字幕也经同一格式解析和字节上限。明确非法分P映射 `invalid_url`，不借回退静默选择另一段内容。

浏览器验收使用隔离账户/数据库和可控外部HTTP服务；应用API及其真实请求编排参与运行。本机LLM协议夹具用于稳定验证页面行为，实际配置模型用于独立内容质量评测；两类报告提供各自的数据与限制。平台、浏览器和LLM实现工作线分配不同文件，主agent集中整合与复审。

### 12.3 自然字幕评测与摘要输出控制

自然语料和事实清单由独立采集agent在模型输出前冻结，模型实现与独立复审分工，源码、提示词、模型、配置和请求台账可核对。原始字幕清洗保持来源与许可，本轮MIT OCW语料单独遵守CC BY-NC-SA4.0，不并入无约束软件许可。

本轮真实HTTP200出现两类失败：正文JSON漏闭合符号；合并请求4096输出token全部用于推理，finish_reason=length而content为空。仍按`llm_invalid_response`或`llm_incomplete_response`拒绝，不增加自动POST重试或修复残缺JSON。

`llm_service.py`在摘要请求内部按配置生成输出选项：`LLM_SUMMARY_RESPONSE_FORMAT=auto|text|json_object`与`LLM_SUMMARY_THINKING_MODE=auto|enabled|disabled`。auto读取供应商能力表，DeepSeek摘要使用json_object与disabled；其他供应商的auto不加专有字段，翻译不继承摘要选项。明确覆盖由使用者依据供应商协议选择。配置启动时验证，接口及分段上限不变，两个控制均作用于分段与合并。模型内容仍作为不可信结构经原解析器校验；JSON模式不保证非空或完整，见[官方说明](https://api-docs.deepseek.com/guides/json_mode/)。

JSON模式也不保证要点数量。实测完整JSON包含12条要点，原解析器只验证类型与非空；本轮补齐1–7条数量约束，超过上限返回`llm_invalid_response`，不截断删除尾部。最终合并请求明确按最多7个主题归纳，原因、条件和具体例子归入相关主题；字段与数量验证都由服务承担，不能仅相信提示词。

兼容模式与原默认推理模式分别留证；它同时改变了提示词和输出控制，不能将其结果全部归因于提示词。公网375px下载、默认GPU纹理驻留与角色截图各自验证；Windows移动视口与真手机兼容范围分开，详情见[公网移动/GPU报告](acceptance-reports/2026-10-04-public-mobile-gpu/report.md)。

## 13. 第二阶段：前端视觉表现层（fx）架构

> 本节为历史方案，所列 `Subtitle` / `Frame` / `TransitionOverlay` / `Cursor` / `PathProgress` 不代表当前组件已实现。当前实际文件见§3、交接文件地图与v3计划；本轮不扩展这条视觉演进线。

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
