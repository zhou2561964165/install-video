# 扩展计划 · 万能视频下载网站

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

> 版本：v3状态同步（2026-10-03；保留初版扩展路线）
> 对应：`docs/requirements.md` §8、`docs/design.md` §9/§12
> 本文档登记 v1 之后的扩展方向、优先级、建议实现方式与风险规避，并说明当前实现已预留的接口/配置/模块边界。任何新功能落地前，先在 `requirements.md` 登记需求，再更新 `design.md`。

---

> **注**：本文档聚焦后端功能扩展。当前v2/v3已实现，v3以AI内容总结为主；电影感前端计划已作历史参考。当前状态见 [交接文档](../../handoff.md)，候选扩展不自动授权下一步开发。

## 工程约定

UI先使用 `ui-ux-pro-max` + `design-system`，skill优先于计划；颜色/字体/时长走token，新能力数据和配置驱动；yt-dlp仅经 `ytdlp_service.py`，视觉只读scene，模块通过窄接口单向依赖。

## 1. 当前实现已预留的扩展点

v1 通过「接口隔离 + 配置外置 + 模块边界」为后续扩展留了余地，核心约束是 **`ytdlp_service.py` 是唯一接触 yt-dlp 的层**，其余模块只依赖它的函数签名，任何扩展都不得直接 `import yt_dlp`。

| 扩展点 | 已预留的接口 / 配置 / 边界 |
| --- | --- |
| 下载核心隔离 | `ytdlp_service.py` 提供下载/解析接口及 `extract_subtitle_tracks`；平台来源适配仅由它调用，不向路由暴露实现细节 |
| 任务执行入口 | `JobManager.submit_download()` 是唯一下载任务入口；鉴权与额度预留在下载路由，线程池不感知用户或LLM |
| 数据模型扩展 | `User` / `Quota` 已实现；Job含user_id，新任务均绑定用户，nullable仅兼容历史 |
| 路由扩展 | `backend/app/routes/` 按资源拆分（`parse.py` / `download.py`）；新功能（总结/翻译/账号）加独立路由文件，不改现有路由 |
| 契约稳定 | `backend/app/schemas.py` 定义请求/响应；新增字段用可选/默认值，避免破坏前端 |
| 参数配置 | `config.py` 包含下载、鉴权、字幕来源、LLM与总结分段预算；完整变量与默认值以根README为准 |
| 错误分类 | `classify_error()` 统一映射 9 种 `error_type`；新增错误类型只需在此扩展，前端 `ERROR_SCENES` 同步 |
| 前端状态机 | `frontend/src/state/sceneMachine.js` 6 场景 + `ERROR_SCENES` 9 错误文案；新场景/新错误在此登记 |
| 前端接口封装 | `api.js` 集中下载/auth/subtitle/translate/summary接口；AI状态由 `useVideoInsights` 隔离 |
| 角色状态映射 | `frontend/src/pixi/mascotConfig.js` 数据驱动（场景 → 表情/动作），调角色表现不改渲染逻辑 |
| 模型配置 | `MODELS` 注册表、默认白模型与 `mobile` 布局；运行时模型切换UI已删除，新增注册不自动生成切换控件 |
| 视觉降级 | `detectTier()` 与WebGL自动检测，三档主题开关不是 `lightMode`；下载与视觉解耦 |

---

## 2. 扩展优先级

| 优先级 | 方向 | 阶段 | 依赖 |
| --- | --- | --- | --- |
| P0 | 账号体系 + 每用户额度 | v2已实现 | 无（独立） |
| P1 | AI内容总结、字幕来源与辅助翻译 | v3已实现 | 必需登录；AI计费暂未实现 |
| P2 | 付费能力（额度/会员/支付） | v4 | 账号 + Quota |
| P3 | 批量下载、任务队列横向扩展、SSE 实时进度、生产部署 | 视需要 | 无/账号 |

> P0 与 P1 相对独立；P2 依赖 P0 的 Quota 数据模型。P3 是横向能力，可随任一阶段插入。

---

## 3. 各扩展点：建议实现方式、风险与规避

### 3.1 账号体系 + 每用户额度（P0 / v2）—— ✅ 已实现并完成强制登录收口（2026-10-03）

> 实现偏差：额度检查放在**路由层**（`routes/download.py` → `services/quota.check_and_reserve`），而非下文建议的 `JobManager.submit_download()` 入口——更严格遵循「鉴权只在路由层、下载核心不感知用户」。密码哈希用 stdlib `pbkdf2_hmac`（零新依赖），JWT 用 `pyjwt`（HS256）。2026-10-03 起 `/api/parse`、`/api/download` 均使用必需鉴权，匿名入口已关闭。

**建议实现**
- 建 `User`（id/email/password_hash/created_at）与 `Quota`（user_id/date/downloads_used/limit）表——字段已在 `design.md` §6 预留。
- 新增 `routes/auth.py`（注册/登录，JWT）；用 FastAPI `Depends(get_current_user)` 保护解析与下载路由。
- 额度检查实际位于 `routes/download.py` → `quota.check_and_reserve`，提交即扣，超限返回 `quota`；不进入线程池。

**风险与规避**
- 风险：把鉴权逻辑耦合进下载路由，导致下载核心被污染。规避：鉴权只在路由层做，下载核心不感知用户。
- 风险：限流中间件与额度概念混淆。规避：保留现有「每 IP 限流」为粗粒度防滥用，登录用户额度为细粒度限制，二者分层、互不替换。

### 3.2 视频总结 / 字幕翻译（P1 / v3，LLM）—— ✅ MVP 已实现（2026-10-03）

> 实际实现：`ytdlp_service.py` 只读暴露字幕轨道；`subtitle_service.py` 负责获取与 VTT/SRT/JSON3/TTML 文本化；`llm_service.py` 封装可配置 OpenAI-compatible 接口；路由为用户显式触发的同步 `def`，由 FastAPI 线程池执行。前端用独立 `useVideoInsights`，不修改下载 reducer。

用户方向已定：AI理解内容优先，允许去掉重复片段；长文分段归纳再合并。用配置模型ID `deepseek-flash`，后续供应商配置切换。96/65、101/66、121/66、169/66、184/66分别属旧轮次；本轮原文证据/实验协议和响应式交互增量234/73及构建通过。新19预占/18HTTP/1连接失败已停止，旧24保留；长365字末点/归因仍待改善，上游schema未证实强制性，auto未切。下一候选是主题/事实层和逐声明校验，再真机；不自动授权新开发。证据见[文档索引](../../README.md)。

**建议实现**
- 新增 `services/llm_service.py` 封装 LLM 调用（provider/模型可配置），独立于下载。✅
- 新增 `routes/summary.py` / `routes/subtitle.py`，由用户在解析结果页显式请求。✅
- 字幕抓取复用 yt-dlp 的 subtitle/automatic_captions 信息（在 `ytdlp_service` 增加只读方法，不扩展下载职责）。✅

**风险与规避**
- 风险：LLM 调用长耗时阻塞事件循环。规避：走 `JobManager` 同款线程池，或独立队列；绝不在 `async def` 里同步阻塞。
- 风险：LLM provider 变更导致大规模重写。规避：`llm_service` 定义统一接口（`summarize(video_meta) -> str`），provider 细节藏在实现里；provider/模型/key 走环境变量配置。

### 3.3 付费能力（P2 / v4）

**建议实现**
- 复用 Quota 表，新增会员/积分字段；支付回调（微信/支付宝）落在 `routes/billing.py`，回调只更新 Quota/会员状态。
- 前端在下载前查剩余额度，超限引导付费——UI 层复用现有 `quota` 错误场景。

**风险与规避**
- 风险：支付回调安全（伪造回调）。规避：回调验签 + 幂等（同一订单号只处理一次）。
- 风险：金额/渠道硬编码。规避：定价与渠道配置化（环境变量或 DB 配置表）。

### 3.4 任务队列横向扩展（P3，Celery/Redis）

**建议实现**
- 当前 `jobs.py` 使用 `ThreadPoolExecutor` 与 `JobManager`；`TaskRunner` / `CeleryRunner` 是未来方案，不是当前已实现接口。扩展时先定义窄协议再接入。
- 当前 `JobManager` 已把「提交任务」收敛到 `submit_download()`，改造点集中、范围小。

**风险与规避**
- 风险：进度/状态写入依赖进程内 SQLite，多 worker 后需共享存储。规避：扩展时先切 `DB_URL` 到 PostgreSQL，再上队列——顺序不能反。
- 风险：限流中间件用内存 dict，多进程后失效。规避：限流状态迁到 Redis（或共享存储）与队列扩展一并做。

### 3.5 SSE 实时进度（P3）

**建议实现**
- 现有 `GET /api/job/{id}` 是轮询（前端 `POLL_MS=3000`，受后端 30/60s 限流约束）。扩展时新增 `GET /api/job/{id}/events` 走 SSE，把 `progress_hooks` 的进度推送到订阅者。
- 前端轮询逻辑已收敛到 `hooks/useDownload.js`，替换为SSE时通过该边界，不让UI依赖下载内部实现。

**风险与规避**
- 风险：SSE 长连接占连接数。规避：仅下载中场景订阅，`done/error` 即关闭；连接数上限配置化。

### 3.6 生产部署（P3，静态托管 + CORS + Docker）

**建议实现**
- 前端 `npm run build` 产物由 FastAPI `StaticFiles` 托管，或反向代理（Nginx）同源部署，消除 dev 期的 Vite 代理依赖。
- 加可配置 CORS 中间件（默认允许本地开发源，生产用环境变量收紧）。
- 提供 Dockerfile：内置 ffmpeg + yt-dlp + 前端构建产物。

**风险与规避**
- 风险：直链模式 `location.assign` 丢 headers（已在 `frontend/README.md`「已知限制」记录）。规避：生产继续以「强制走服务器」为可靠兜底；文档化。
- 风险：CORS 放太宽造成安全面扩大。规避：默认收紧，仅显式配置允许源。

---

## 4. 避免大规模重构的边界清单

- **下载核心永不被扩展逻辑触碰**：总结/翻译/账号/付费都通过新路由 + 新服务接入，`ytdlp_service.py` 仅按需增加只读查询方法（如字幕信息），不新增职责。
- **任务入口唯一**：下载任务统一走 `JobManager.submit_download()`；队列替换集中在任务入口，账号/额度仍保持路由层检查，下载核心不感知扩展职责。
- **错误类型向前兼容**：新错误类型追加到 `classify_error()` 与前端 `ERROR_SCENES`，不改既有 9 类的语义。
- **契约向后兼容**：`schemas.py` 新增字段用可选值，旧前端不会因缺字段报错。
- **配置不硬编码**：任何新引入的阈值/路径/provider 一律进 `config.py` 环境变量，避免后续为改一个数而改代码。
