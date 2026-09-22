# 扩展计划 · 万能视频下载网站

> 版本：v1（2026-09-21）
> 对应：`docs/requirements.md` §8、`docs/design.md` §9/§12
> 本文档登记 v1 之后的扩展方向、优先级、建议实现方式与风险规避，并说明当前实现已预留的接口/配置/模块边界。任何新功能落地前，先在 `requirements.md` 登记需求，再更新 `design.md`。

---

> **注**：本文档聚焦**后端**功能扩展（v2 账号 / v3 总结·翻译 / v4 付费）。前端「第二阶段：电影感视觉升级」是另一条独立演进线，计划见 `docs/superpowers/plans/2026-09-22-phase2-cinematic-visual.md`，架构见 `docs/design.md §13`。

## 1. 当前实现已预留的扩展点

v1 通过「接口隔离 + 配置外置 + 模块边界」为后续扩展留了余地，核心约束是 **`ytdlp_service.py` 是唯一接触 yt-dlp 的层**，其余模块只依赖它的函数签名，任何扩展都不得直接 `import yt_dlp`。

| 扩展点 | 已预留的接口 / 配置 / 边界 |
| --- | --- |
| 下载核心隔离 | `backend/app/services/ytdlp_service.py` 提供 `extract_info / parse_video / build_format_options / get_direct_url / download / classify_error / is_valid_url`；其余模块（routes/jobs）只依赖这些签名 |
| 任务执行入口 | `backend/app/services/jobs.py` 的 `JobManager.submit_download()` 是唯一提交下载任务的入口——额度检查、队列替换都应加在这里，不碰下载核心 |
| 数据模型扩展 | `backend/app/models.py` 已预留 `User` / `Quota`（见 `design.md` §6，v1 不建表）；`Job` 表字段完整（status/progress/file_path/error_type/error/expires_at） |
| 路由扩展 | `backend/app/routes/` 按资源拆分（`parse.py` / `download.py`）；新功能（总结/翻译/账号）加独立路由文件，不改现有路由 |
| 契约稳定 | `backend/app/schemas.py` 定义请求/响应；新增字段用可选/默认值，避免破坏前端 |
| 参数配置 | `backend/app/config.py` 8 个环境变量（`FFMPEG_PATH / MAX_CONCURRENT / TEMP_DIR / MAX_FILE_SIZE / TTL_SECONDS / DB_URL / RATE_LIMIT / RATE_LIMIT_WINDOW`），默认路径锚定到后端目录 |
| 错误分类 | `classify_error()` 统一映射 9 种 `error_type`；新增错误类型只需在此扩展，前端 `ERROR_SCENES` 同步 |
| 前端状态机 | `frontend/src/state/sceneMachine.js` 6 场景 + `ERROR_SCENES` 9 错误文案；新场景/新错误在此登记 |
| 前端接口封装 | `frontend/src/api.js` 集中 `parseVideo/startDownload/getJob/fileUrl` 与错误归一化 `normalizeError` |
| 角色状态映射 | `frontend/src/pixi/mascotConfig.js` 数据驱动（场景 → 表情/动作），调角色表现不改渲染逻辑 |
| 多模型切换 | `mascotConfig.js` 的 `MODELS` 注册表 + `mascot.js` 的 `switchModel(id)`；新增模型 = 放模型目录 + 加一条注册，渲染/UI 自动感知（`App.jsx` 右上角下拉，`MODELS.length > 1` 时显示） |
| 视觉降级 | `frontend/src/pixi/stage.js` 的 `detectTier()` + `lightMode` 手动开关，下载与视觉解耦 |

---

## 2. 扩展优先级

| 优先级 | 方向 | 阶段 | 依赖 |
| --- | --- | --- | --- |
| P0 | 账号体系 + 每用户额度 | v2 | 无（独立） |
| P1 | 视频总结、字幕抓取+翻译（LLM） | v3 | 账号（用于额度/计费），非硬依赖 |
| P2 | 付费能力（额度/会员/支付） | v4 | 账号 + Quota |
| P3 | 批量下载、任务队列横向扩展、SSE 实时进度、生产部署 | 视需要 | 无/账号 |

> P0 与 P1 相对独立；P2 依赖 P0 的 Quota 数据模型。P3 是横向能力，可随任一阶段插入。

---

## 3. 各扩展点：建议实现方式、风险与规避

### 3.1 账号体系 + 每用户额度（P0 / v2）

**建议实现**
- 建 `User`（id/email/password_hash/created_at）与 `Quota`（user_id/date/downloads_used/limit）表——字段已在 `design.md` §6 预留。
- 新增 `routes/auth.py`（注册/登录，JWT 或 session cookie）；用 FastAPI `Depends` 注入 `current_user`，不影响现有无鉴权路由（v1 公开访问保留）。
- 额度检查放在 `JobManager.submit_download()` 入口（下载前查 Quota，超限返回 `quota` 错误类型——前端已有该错误场景）。

**风险与规避**
- 风险：把鉴权逻辑耦合进下载路由，导致下载核心被污染。规避：鉴权只在路由层做，下载核心不感知用户。
- 风险：限流中间件与额度概念混淆。规避：保留现有「每 IP 限流」为粗粒度防滥用，额度为每用户细粒度，二者分层、互不替换。

### 3.2 视频总结 / 字幕翻译（P1 / v3，LLM）

**建议实现**
- 新增 `services/llm_service.py` 封装 LLM 调用（provider/模型可配置），独立于下载。
- 新增 `routes/summary.py` / `routes/subtitle.py`；下载完成后（`done` 状态）异步触发，或用户显式请求。
- 字幕抓取可直接复用 yt-dlp 的 subtitle 信息（在 `ytdlp_service` 增加只读方法，不扩展下载职责）。

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
- `design.md` §9 已规划：`jobs.py` 定义 `TaskRunner` 接口，`submit(job)` 为其唯一方法；v1 用 `ThreadPoolExecutor` 实现，扩展时新增 `CeleryRunner` 实现并在启动时按配置注入。
- 当前 `JobManager` 已把「提交任务」收敛到 `submit_download()`，改造点集中、范围小。

**风险与规避**
- 风险：进度/状态写入依赖进程内 SQLite，多 worker 后需共享存储。规避：扩展时先切 `DB_URL` 到 PostgreSQL，再上队列——顺序不能反。
- 风险：限流中间件用内存 dict，多进程后失效。规避：限流状态迁到 Redis（或共享存储）与队列扩展一并做。

### 3.5 SSE 实时进度（P3）

**建议实现**
- 现有 `GET /api/job/{id}` 是轮询（前端 `POLL_MS=3000`，受后端 30/60s 限流约束）。扩展时新增 `GET /api/job/{id}/events` 走 SSE，把 `progress_hooks` 的进度推送到订阅者。
- 前端轮询逻辑收敛在 `App.jsx` 的 poll effect，替换为 SSE 不影响场景状态机与 UI 层。

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
- **任务入口唯一**：所有「启动一个下载」都走 `JobManager.submit_download()`；额度、队列替换、审计都挂在这里，未来不需要翻遍下载核心找调用点。
- **错误类型向前兼容**：新错误类型追加到 `classify_error()` 与前端 `ERROR_SCENES`，不改既有 9 类的语义。
- **契约向后兼容**：`schemas.py` 新增字段用可选值，旧前端不会因缺字段报错。
- **配置不硬编码**：任何新引入的阈值/路径/provider 一律进 `config.py` 环境变量，避免后续为改一个数而改代码。
