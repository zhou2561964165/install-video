# 方案设计文档 · 万能视频下载网站

> 版本：v3（2026-10-11 任务访问隔离与角色交互同步；历史视觉与模型实验另作标记）
> 对应需求：见 `docs/requirements.md`
> 本文档是**技术设计基准**。当前实现见 §1–12，§13–14 保留历史视觉决策；模型历史阶段见 §12.3–12.4，当前默认与验收状态见 §12.6。所有「预留扩展点」在实现时通过接口隔离，后续拓展不触碰下载核心。

---

## 0. 工程约定（每次遵守）

> 遵循当前 `AGENTS.md`、有效用户指令及上级指令。`CLAUDE.md` 是项目补充说明，不具有最高优先级；历史计划不能覆盖后续用户要求。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。
5. **成熟方案优先，避免重复造轮子**：设计前复用已确认资料、调研成熟库/框架/官方方案，适用时优先集成；自研聚焦业务差异与适配。选型记录来源、版本、兼容性、维护/许可证/资源成本及不适用的具体原因。执行 [AGENTS.md §10](../AGENTS.md)，既有自研实现不构成跳过成熟方案评估的理由。

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
                                临时文件目录（下载提交时懒触发 TTL 清理）
```

**选型理由**：yt-dlp 是 Python，进程内用其官方 API 代码最少、结构化 format 信息直接可用、进度与错误处理干净；下载为阻塞 I/O，用线程池即可支撑 v1 并发。

**备选方案（已否决）**：
- 方案 B：subprocess 调 `yt-dlp` 命令行 —— 与 CLI 解耦但需自解析 JSON/进度/错误，更脆。
- 方案 C：基于现成 yt-dlp-web-ui 改皮肤 —— 技术栈冲突，重写前端反而更费劲。

## 2. 技术选型

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 后端 | Python >=3.12 + FastAPI | `pyproject.toml`声明最低版本，与yt-dlp同语言 |
| 下载核心 | yt-dlp（Python API） | 进程内调用 |
| 任务存储 | SQLite + SQLModel | 轻量，后续可换 PostgreSQL |
| 总结结构校验 | Pydantic v2（已有依赖；本机2.13.5） | `summary_output.py`统一严格字段类型与JSON Schema生成；生成组织采用来源优先、要点先写/概览后写的指导，内容质量另行验收 |
| 候选总结串行编排 | langchain-core 1.6.9（锁定，约束>=1,<2） | staged候选使用实际RunnableSequence/RunnableLambda两步骤，供应商HTTP仍在llm_service；默认single保留至候选验证 |
| 追踪上下文控制 | langsmith 0.14.7（直接依赖，约束>=0.3,<1） | 仅用tracing_context(enabled=False)禁用整个管线外部追踪；不启用LangSmith服务、账号或数据上传 |
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
│   │       ├── quota_policy.py    # 指定用户开发豁免窄接口；保留计数、无效策略恢复有限额度
│   │       ├── subtitle_sources.py # 公开平台来源适配，由ytdlp_service调用
│   │       ├── bilibili_subtitle_source.py # 匿名BV/分P字幕元数据，可信来源与输入校验
│   │       ├── subtitle_service.py # 正文HTTP与文本化
│   │       ├── llm_service.py      # 默认legacy字幕分段/合并、自适应预算；facts实验编排与传输
│   │       ├── summary_output.py   # 已有Pydantic严格字段类型与JSON Schema；无配置/HTTP依赖
│   │       ├── summary_pipeline.py # 候选LCEL points→overview串行角色边界，关闭外部追踪
│   │       ├── summary_facts.py    # facts实验的来源/事实/候选结果严格合同
│   │       ├── summary_normalization.py # facts raw输出独立规范化，保留内容与ID提示
│   │       ├── summary_references.py # facts程序关联引用，未决候选交核查
│   │       ├── summary_quality.py  # facts主题/重复/关键事实/归因检查
│   │       ├── summary_audit_contract.py # facts compat/compact核查包解析
│   │       ├── summary_retry.py    # facts分类修复预算；格式/语义分别计数
│   │       └── network_retry.py    # 下载/字幕网络策略，与LLM分类修复分离
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
   → ytdlp_service.parse_video(url)（内部extract_info只读提取）
   → 返回 {title, thumbnail, duration, duration_string, uploader, platform,
           view_count, upload_date, description, subtitles,
           formats:[{format_id, label, height, ext, resolution, filesize,
                     has_audio, vcodec, acodec, direct(是否有直链), note}]}

2. POST /api/download {url, format_id, force_server:false}（Authorization: Bearer <token> 必需）
   → 判定下载方式（见 §5）
   → 服务端模式建 Job（status=queued）→ 线程池执行下载
   → 返回 {mode:"direct", url, headers} 或 {mode:"server", job_id}

3. GET /api/job/{id}（Bearer token必需；查询id+user_id；前端轮询进度 / 后续可换 SSE）
   → {id, status, progress, title, error_type, error}

4. GET /api/file/{job_id}（Bearer token必需；仅本人完成且文件仍存在的任务）
   → FileResponse；前端携Bearer取Blob、解析Content-Disposition文件名后保存
```

**鉴权边界（按当前路由）**：注册/登录无需已有 token；`/api/auth/me`、解析、下载、字幕、翻译、总结及job/file读取要求Bearer token。job/file同时按id和user_id查询；匿名/无效token为401，他人/无主/不存在统一404。本人文件仍需完成且存在，未新增即时TTL拒绝或迁移。前端退出清除token并取消当前解析/下载，换账号或迟到响应不能继续保存旧文件；没有服务端logout/refresh API。文件先完整缓存Blob再保存，不是流式直通下载。

**视频智能 API**：`POST /api/subtitle {url, language?}` 返回标题、语言、自动字幕标记、可选语言和正文；`POST /api/subtitle/translate {url, source_language?, target_language:"zh-CN"}` 返回译文及 provider/model；`POST /api/summary {url, subtitle_language?, output_language:"zh-CN"}` 返回标题、源语言、`summary`、`key_points`、provider/model。公开总结响应不包含 facts、trace 或模型修复计数；这些仅在显式诊断中使用。

## 5. 下载方式：直链 + 服务端自动切换

- **解析时**：返回清晰度与 `direct` 标记；公开格式列表不返回直链 URL 或请求头。下载提交时由 `get_direct_url` 重新提取该格式的 URL 和请求头。
- **下载时**：
  1. 直链可用 → 返回 `{mode:"direct", url, headers}`，前端直接浏览器下载；
  2. 直链探测无结果或抛错 → 自动落到服务端下载 `{mode:"server", job_id}`；
  3. UI 提供「强制走服务器」开关兜底。
- **服务端下载**：`ytdlp_service.download()` 内用 `YoutubeDL.extract_info(download=True)` 下载到任务临时目录，`progress_hooks` 更新 Job 进度；完成后由 `/api/file/{id}` 流式回传。前端轮询到 `done` 后经 `lib/saveFile.js`（`<a download>`）自动触发浏览器保存，无需手动点链接。
- **现有直链边界**：前端用 `window.location.assign(url)`，不附服务端返回的 `headers`；浏览器侧过期、请求头限制或保存失败不会自动重新提交服务端任务，需要用户使用强制服务器选项。下载路由会在探测前扣额度，失败不自动返还。
- **ffmpeg 合并阈值（`FFMPEG_MIN_HEIGHT = 1080`）**：有分辨率的清晰度档位优先使用渐进式直链；无直链时，仅对 `>= 1080p` 的档位生成音视频合并格式，低于1080p跳过该档。若最终没有候选，仍提供无指定分辨率的 `best` 兜底；阈值是格式列表策略，不是下载路由对任意format_id的硬限制。

## 6. 数据模型

```
Job:
  id(uuid) · url · title · format_id · status(queued/downloading/merging/done/error)
  progress(0-100) · file_path · file_size · error_type · error
  created_at · updated_at · expires_at
  user_id(可空 FK→User；新任务必填，nullable 仅兼容 v1 历史数据)

【v2 已建表（2026-09-24）】
User:   id(uuid) · email(unique) · password_hash · created_at
Quota:  id(uuid) · user_id(FK→User) · date(UTC 日期串) · downloads_used · limit  — (user_id, date) 复合唯一
```

## 7. 临时文件与防滥用

- 临时目录按任务隔离；完成后设置过期时间（默认 1 小时），下一次下载提交调用 `cleanup_expired()` 删除过期文件与任务行。当前无定时清理任务，不能承诺 TTL 到点即删。
- **并发执行上限**默认 3，由 `ThreadPoolExecutor` 控制；超出的任务排队，当前没有队列长度拒绝机制。**每 IP 限流**是 `/api/` 内存窗口，默认 60 秒 30 次；多进程不共享计数。**文件大小上限**默认 2 GiB，在服务端下载完成后检查，并非下载前磁盘预留。
- **账号额度已实现**：`quota.py` 按 UTC 日统计，默认每用户每日 10 次，`check_and_reserve` 在下载探测/创建任务前提交计数，直链与服务端同计。解析、字幕、翻译、总结不扣下载额度。
- **开发指定账号豁免已实现**：`quota_policy.is_unlimited_user(user_id)` 每次按显式 ID 读取本地策略；缺失、不可读或无效策略恢复有限额度。豁免只绕过耗尽判断，仍累计 `downloads_used`，不改其他用户的额度行；`/api/auth/me` 对豁免用户返回 `unlimited=true`、`limit/remaining=null`。下载豁免不解除 IP 限流、并发、磁盘或模型预算。

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
| quota | 每日额度耗尽、IP请求限流或完成文件超出大小上限 |

## 9. 预留扩展点（后续拓展的关键）

| 未来功能 | 现有隔离边界 | 扩展方式（不碰下载核心） |
| --- | --- | --- |
| 账号 / 登录 | ✅ 已实现（v2） | `routes/auth.py` + `services/auth.py`（JWT + `Depends(get_current_user)`；解析/下载必须登录） |
| 每用户额度 | ✅ 已实现（v2，含开发豁免） | `services/quota.py` `check_and_reserve`，路由层提交即扣（直链/服务端同计）；`quota_policy.is_unlimited_user`隔离豁免策略 |
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
- legacy共用请求提示已修订：summary提供高层主题/关系概览，要点展开完整机制、条件、互补能力与例子；每处断言保留限定和频率/对象/事件/单位。该提示同样用于单段与合并，属于生成指导而非确定性语义验证，不新增调用、输出删除器或API字段。
- `subtitle_sources.py` 提供注册式公开平台适配器，由 `ytdlp_service.py` 唯一调用。Archive.org 总结内容优先从官方字幕附件元数据获取，无需先解析视频下载信息；不可用时回退 yt-dlp。文件级字幕使用去除已识别后缀后的精确内容关联，避免混入其他视频。
- `routes/subtitle.py` 与 `routes/summary.py` 使用 `Depends(get_current_user)`，同步路由交由 FastAPI 线程池执行。
- 前端通过 `api.js` + `useVideoInsights` 调用，`VideoInsights` 只接收 props；现有下载 reducer 和 `useDownload` 不变。
- 解析阶段的字幕发现可能是可选查询，空语言列表不会隐藏视频智能动作：面板提供自动选源语言和显式用户触发；请求失败就地展示，下载状态和额度互相隔离。

### 12.2 增量平台与验收边界

新增公开字幕元数据适配器继续返回既有标题与轨道格式，通过 `subtitle_sources.py` 注册，再由 `ytdlp_service.py` 统一调用；适配器无轨道或失败时保留通用提取。需要新字幕正文格式时只扩展 `subtitle_service.py` 的格式解析入口，不让路由接触平台JSON。

当前注册Archive与Bilibili。原生payload由唯一入口附内部来源标记；选轨道/正文获取/解析失败时，字幕服务最多一次调用 `use_public_sources=False` 的通用路径，通用仍失败则保留原生错误。上游inline `data` 字幕也经同一格式解析和字节上限。明确非法分P映射 `invalid_url`，不借回退静默选择另一段内容。

浏览器验收使用隔离账户/数据库和可控外部HTTP服务；应用API及其真实请求编排参与运行。本机LLM协议夹具用于稳定验证页面行为，实际配置模型用于独立内容质量评测；两类报告提供各自的数据与限制。平台、浏览器和LLM实现工作线分配不同文件，主agent集中整合与复审。

### 12.3 自然字幕评测与摘要输出控制

> 历史阶段：记录 2026-10-04 的失败与当时修复决策，不是当前待办或默认长度合同。后续规范化/分类修复与自适应输出已覆盖下述「不修复格式」「最多7点」结论；当前行为见 §12.6。历史请求与失败原件保留。

自然语料和事实清单由独立采集agent在模型输出前冻结，模型实现与独立复审分工，源码、提示词、模型、配置和请求台账可核对。原始字幕清洗保持来源与许可，本轮MIT OCW语料单独遵守CC BY-NC-SA4.0，不并入无约束软件许可。

当时真实HTTP200出现两类失败：正文JSON漏闭合符号；合并请求4096输出token全部用于推理，finish_reason=length而content为空。当时按`llm_invalid_response`或`llm_incomplete_response`拒绝；当前默认legacy路径仍不自动追加付费请求，facts实验路径已增加独立规范化与有限分类修复（§12.6），不能将历史禁止所有修复当作当前统一规则。

`llm_service.py`在摘要请求内部按配置生成输出选项：`LLM_SUMMARY_RESPONSE_FORMAT=auto|text|json_object`与`LLM_SUMMARY_THINKING_MODE=auto|enabled|disabled`。auto读取供应商能力表，DeepSeek摘要使用json_object与disabled；其他供应商的auto不加专有字段，翻译不继承摘要选项。明确覆盖由使用者依据供应商协议选择。配置启动时验证，接口及分段上限不变，两个控制均作用于分段与合并。模型内容仍作为不可信结构经原解析器校验；JSON模式不保证非空或完整，见[官方说明](https://api-docs.deepseek.com/guides/json_mode/)。

JSON模式也不保证要点数量。当时实测完整JSON包含12条要点，原解析器只验证类型与非空；当时补齐1–7条数量约束，不截断删除尾部。当前默认adaptive按字幕规模计算有限主题上限，旧7点约束仅适用于fixed或facts显式实验；字段与本次预算仍由服务校验，不能仅相信提示词。

兼容模式与原默认推理模式分别留证；它同时改变了提示词和输出控制，不能将其结果全部归因于提示词。公网375px下载、默认GPU纹理驻留与角色截图各自验证；Windows移动视口与真手机兼容范围分开，详情见[公网移动/GPU报告](acceptance-reports/2026-10-04-public-mobile-gpu/report.md)。

### 12.4 实验schema协议与原文证据贯穿

> 历史协议验收：以下「七槽」「240字符」描述针对当时fixed预算。接口仍保留显式实验选项；当前legacy-adaptive的schema/工具槽数跟随本次主题预算，默认不按点长硬拒。facts保留自己的固定合同，不能作为默认总结质量门槛。

`json_schema`显式选择Responses的text.format，检查response/message完成状态、字段、数量；`strict_tool`显式选择Beta chat严格工具，用summary及本次预算数量的必需字符串槽位表示结果，空尾槽表示未用，再转换为原API，不执行工具或发工具结果第二轮。fixed模式额外校验配置点长；历史七槽实测Responses仍返回8点，Beta仍可返回空首槽/294字点，因此当时DeepSeek auto继续json_object，本地拒绝而不是静默降级重发；协议名不等于上游保证。

段摘要是有损中间件，实测重要结尾事实在进入merge前已丢失。每原分段通过`LLM_SUMMARY_SOURCE_CONTEXT_CHARS`保留原文头尾边界，在notes中标记source_context；分层合并将这些原始证据继续携带，组大小计入JSON及证据，无进展时明确报容量错误，不删证据来凑预算。`0`恢复旧notes形状。源事实与提示联合作用的结果只由实测评价，不将恢复单独归因某一项。

当时fixed兼容模式240字符是提示目标，fixed实验协议为本地校验；当前adaptive不按该字符数硬拒。频率、模态、讲者观点归因与案例范围仍要独立检查，schema只能校验结构。边界片段不是全文备份，遗漏中部事实仍可能发生。

### 12.5 响应式角色的几何接口

App通过getRegion提供初始视觉占位，通过interactionTarget提供已有DOM角色入口。手机初始布局使用文档流区域；首次拖动后保留视口中心及尺寸比例，跨滚动/场景/缩放持久，resize只约束可恢复中心。视觉层把模型实际边界同步到局部DOM表面，焦点随角色移动；布局占位不再额外保留已删除按钮的44px空白。模型资源未改，纹理不足仍跳过模型请求，视觉失败不阻塞解析。

点击角色或聚焦已有入口按Enter/Space打开原39项菜单，不额外添加可见换装按钮；菜单保留焦点循环/恢复和inert。canvas通过已有公共配置允许pan-y/pinch-zoom，模型局部表面在手势开始前设置pinch-zoom；首touchstart不preventDefault。拖动绑定pointerId，第二指加入取消单指拖动而不触发tap；全部释放/cancel/blur后恢复，销毁清理监听。采用现有PIXI6.5/浏览器PointerEvent、CSS touch-action及pointer capture，不加产品依赖。依据[MDN touch-action](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/touch-action)与[Pointer events](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events)；同手势开始后改变touch-action不能修复原生冲突。当前Edge/CDP模拟检查见[本轮报告](acceptance-reports/2026-10-11-ui-interaction-finish/report.md)，不等于真手机通过。

### 12.6 字幕总结、实验模块与交付边界

**2026-10-12当前更新：** 已恢复内容验收，四独立phase16POST/153697供应商tokens全部closed。短中在第三phase内容通过，长结构14点成功但仍有时间/例子范围/运算子集精度缺陷；用户指定的第四完整long使用两次新提取和新merge，不是复用第三phase笔记。实际评分及冻结范围见[最新长文报告](acceptance-reports/2026-10-12-summary-long-final-check/report.md)，旧输出不转记新通过，默认/env未升级。

新增独立`summary_json.py`在legacy raw与原字段/预算校验之间，用现有Pydantic核心JSON parser生成有限partial候选，再以完整字符串序列与标点骨架证明无损；只补终端闭合，不吞未完成值/默认补点/裁字、不新增POST。标准合法JSON沿用旧兼容，单边围栏拒绝；strict继续禁止围栏/严格schema，也允许有无损证明的闭合修复。依据[Pydantic部分JSON解析](https://docs.pydantic.dev/latest/concepts/json/#partial-json-parsing)，其默认partial行为可能丢未完值，故项目增加上述保留门；实际第四leaf末]缺失后完整9点恢复，原raw保留。

通用来源指导增加局部枚举前件、具体例子主语、相对时间锚点、符号顺序及各字段断言独立保留限定，不含样本答案/删点器/新facts协议。无新产品依赖，HTTP仍原受控client/root开发验收单caller；显式thinking候选及8192/16384→16384/24576只用于有限对照，不能单因素归因或静默改默认成本。

**实测及阶段分离候选（后续更新）：** 首来源优先phase已5POST/19776tokens并closed；短篇内容通过，中篇summary频率/文化归因未通过，长文raw20点超14结构失败，详见[首轮实测](acceptance-reports/2026-10-10-source-first-summary-live/report.md)。所以进一步采用[阶段分离设计](superpowers/specs/2026-10-10-staged-summary-design.md)，实际引入langchain-core/RunnableSequence两生成边界，Pydantic验证points-only与overview-only；LangSmith依赖仅用于禁用追踪，所有HTTP仍通过原服务受控client，不启用模型SDK、批量、外部上传或fallback。

新增`LLM_SUMMARY_GENERATION_MODE=single|staged`，当前默认single。staged仅legacy/adaptive候选：单段正常2POST，多段原leaf笔记后最终全局要点+概览正常n+2；整摘要最多一次format额外调用，网络/provider/来源安全/容量错误终止。内部`summarize_sections`以原source_parts逐项匹配本次原文分段，支持绑定旧raw的笔记续处理，不能将笔记当权威；最终要点使用完整原文纠正损失。复验使用已付费两段笔记，正常长文2而非重复4，全部原件/哈希保留。

2026-10-10三轮在线验收已完成并封账：来源优先5POST、阶段分离6POST、原生Schema/Pro对照6POST，累计17/17 POST、74355供应商tokens。第三轮三源结构均通过（短5/中6/长14点），但中篇频率/账户读取/概览重复和长文覆盖/安全范围仍失败；不提升候选为默认，不宣称总体质量解决。默认仍为legacy/adaptive/single。旧26/26工作组原件保持；没有部署。最新证据见[原生Schema/Pro实测](acceptance-reports/2026-10-10-schema-pro-summary-live/report.md)。 采用方案与成本见[阶段分离设计](superpowers/specs/2026-10-10-staged-summary-design.md)和[原生Schema/Pro设计](superpowers/specs/2026-10-10-schema-pro-summary-design.md)。多项配置同时改变，不将改善归因于单一参数。

**成熟方案增量（2026-10-10）：** [局部设计](superpowers/specs/2026-10-10-source-first-summary-design.md)已落地。复用已有Pydantic v2严格类型和动态JSON Schema，`summary_output.py`无配置/HTTP依赖，`llm_service`继续执行空白规范化、数量/长度预算和错误映射。兼容模式允许额外字段、先拒绝非字符串再清理空白点；strict保留extra/空项/原字符串长度拒绝。JSON示例与schema先列key_points后列summary；strict_tool槽适配保留。公开API字段、单块1POST、分段合并及adaptive预算保持，没有新增依赖、框架、重试或付费fallback。

借鉴并适配官方来源优先建议，要求先定位原文主张及频率/主体/条件/归因，形成完整要点后写高层概览；这是同一响应内的生成指导，不能保证供应商输出顺序，也不代表独立引句提取或语义质量已通过。LlamaIndex单块路径及新splitter不能直接解决本轮中篇组织缺陷，Refine默认错误模式需额外适配，故此次未引入大框架；实际采用的库与方法、理由见局部设计。

前端`useVideoInsights`新操作清空该kind旧结果、active匹配时清空显示，保留其他kind缓存和AbortController/请求编号；失败后旧总结不再作为当前结果显示。相关后端108项、前端hook4项离线回归通过；这是针对当前变化的新验证，不重算历史全量或原内容评分。

**默认产品路径**是 `LLM_SUMMARY_STRATEGY=legacy` 与 `LLM_SUMMARY_LENGTH_MODE=adaptive`。这里legacy指已有字幕清理、分段归纳、分层合并流程，不表示旧固定长度。`summarize_text` 接收字幕文本，不增加ASR、事实合同或字幕导出；单段一次请求，多段逐段归纳后分层合并，原文头尾证据随notes传递，无法缩减组数时明确报容量错误。

`_summary_budget` 按清理后来源字符数增长输出许可：基础4096 tokens，默认有限上限8192；每新增约8000来源字符增加1024 tokens和2个主题，主题从7增长至默认最多14。分段默认20000字符、最多16段，单次输入默认60000字符；均通过配置调整。合并按对应原来源长度计算预算，不能误用中间notes长度。adaptive不按摘要800字或单点240字硬拒，保留非空、字段/类型、完成状态及本次主题数量边界；预算是资源上限，不要求模型凑满主题。

**facts是显式兼容实验**：`strategy=facts`启用来源/事实提取、compose、audit，`auto`仅在发送前判断能力/容量并可选择legacy；已发送facts失败不自动切换另一条付费pipeline。`summary_facts`负责来源位置/哈希、事实与最终引用合同；`summary_normalization`先保留非空内容与原ID提示再规范结构；`summary_references`结合已验证事实与主题关联引用，关联不是语义证明，未决候选交audit；`summary_quality`检查关键事实、主题、重复和归因；`summary_audit_contract`解析compat/compact核查包。默认 `quality_contract=compat`，compact、fixed长度及schema/strict-tool保留作显式实验，未成为产品默认成功条件。

**分类修复仅已接入facts编排**：优先本地零POST规范化；确需模型修复时 `summary_retry.RetryBudget` 默认每次总结最多1次format、1次semantic，总附加最多2，可配置为0关闭。来源安全、网络/provider、容量、配置错误不重试；每个付费attempt和修复预算记入诊断trace，不盲重跑整个pipeline。facts正常n次提取+compose+audit为n+2，默认最坏n+4。默认legacy的请求/解析错误仍直接返回，不宣称其已接入这些分类修复模块。

2026-10-10三轮在线验收已完成并封账：来源优先5POST、阶段分离6POST、原生Schema/Pro对照6POST，累计17/17 POST、74355供应商tokens。第三轮三源结构均通过（短5/中6/长14点），但中篇频率/账户读取/概览重复和长文覆盖/安全范围仍失败；不提升候选为默认，不宣称总体质量解决。默认仍为legacy/adaptive/single。旧26/26工作组原件保持；没有部署。最新证据见[原生Schema/Pro实测](acceptance-reports/2026-10-10-schema-pro-summary-live/report.md)。

最新提示变化后的相关LLM/adaptive机械回归91 passed；两个新工具离线保护测试19/7 passed。`1342 passed / 1既有警告`是此前记录，GitHub交付前新增集成验证单独记录，不重算旧结果。证据入口为[自适应交接](handoff-2026-10-09-adaptive.md)、[最终有限复验](acceptance-reports/2026-10-09-adaptive-summary-final/report.md)和[首修复未通过记录](acceptance-reports/2026-10-09-adaptive-summary-repair/report.md)。原始失败、请求、响应、freeze和账本保留，不改旧成功状态。

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
- 16K 纹理（16384×16384）已有当前Windows GPU上传历史证据；当前代码先按 `mascotConfig.textureSize` 与 `MAX_TEXTURE_SIZE` 检查，不支持时跳过模型加载，见 §12.5。移动端/低GPU降级与真手机兼容仍分别验收，不能把Windows GPU成功当作所有设备支持。

### 14.8 表情 / 道具系统（46 表情接入）

完整版「白」带 46 个 `.exp3.json`，每个 = 单参数 `{Id, Value:1, Blend:'Add'}`。标准 expression manager 是**单选**（一次一个 currentExpression），无法「换发型 + 换衣服 + 戴耳机」并存；因此走**直接写参数** `coreModel.setParameterValueById(paramId, 1/0)`，可任意多选并存，且与待机正弦驱动（`IDLE`）参数不重叠、互不冲突。参数名/分组/节奏全部进 `mascotConfig.js` 的 `EXPRESSIONS`（数据驱动）。

- **阶段映射（`EXPRESSIONS.stage`）**：解析中→圈圈眼(Param40)、选清晰度→煎蛋眼(Param38)、下载中→圈圈眼(Param40)、完成→星星眼(Param41)、出错→生气(Param43)、入口→无。
- **随机道具（`EXPRESSIONS.random`）**：拿手柄(Param35) / 拿话筒(Param32) / 戳脸(Param31)，每 ~20s 随机展示 ~4s 收回。
- **点击换装菜单（`EXPRESSIONS.menu`，6 组 39 项）**：发型(9, single) / 衣服(4, single) / 大小变(1, toggle) / 配饰(16, multi，含创可贴×4) / 颜色(5, multi) / 情绪(4, multi：黑脸/血迹/哭/脸红)，`ExpressionMenu.jsx` 只读配置渲染。46份表情资源另包含阶段/随机能力，不能等同于46个手动菜单项；尺寸另有2个按钮。
- **装饰特效（`EXPRESSIONS.effect` → `edle.motion3.json`）**：单个「星光闪烁」循环装饰动作（`Meta.Loop=true`，~11.9s；`白.model3.json` 的 Motions 仅挂这一个文件、且该文件无 Motions 数组，并非多特效）。命中 `stages`（默认 `done`/`error`）时由 `setStageEffect` 调 `model.motion(group, index, MotionPriority.IDLE)` 循环播放，其余场景 `motionManager.stopAllMotions()` 停止。`edle` motion 已注册进 `白.model3.json` 的 `FileReferences.Motions`；motion 文件按需懒加载（首次触发 `motion()` 时才请求）。
- **模型切换已删除**（`cycleModel` / 切换特效 / `useModelSwitcher` / toast）。
