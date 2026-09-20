# 方案设计文档 · 万能视频下载网站

> 版本：v1（2026-09-20）
> 对应需求：见 `docs/requirements.md`
> 本文档是**技术设计基准**。所有「预留扩展点」在实现时通过接口隔离，后续拓展不触碰下载核心。

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
│   │   ├── models.py              # Job；预留 User / Quota
│   │   ├── schemas.py             # Pydantic 请求/响应
│   │   ├── routes/
│   │   │   ├── parse.py           # POST /api/parse
│   │   │   └── download.py        # POST /api/download, GET /api/job/{id}, GET /api/file/{id}
│   │   └── services/
│   │       ├── ytdlp_service.py   # 封装 yt-dlp（解析/下载/进度/错误分类）
│   │       └── jobs.py            # 线程池 + 任务生命周期 + 临时文件清理
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
   → 返回 {title, thumbnail, duration,
           formats:[{format_id, note(清晰度), height, ext, filesize,
                     vcodec, acodec, direct(是否有直链)}]}

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
- **服务端下载**：`YoutubeDL.download()` 到临时目录，`progress_hooks` 更新 Job 进度；完成后由 `/api/file/{id}` 流式回传。

## 6. 数据模型

```
Job:
  id(uuid) · url · title · format_id · status(queued/downloading/merging/done/error)
  progress(0-100) · file_path · file_size · error_type · error
  created_at · updated_at · expires_at

【预留，v1 不建表但接口隔离】
User:   id · email · password_hash · created_at
Quota:  user_id · date · downloads_used · limit
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
| 账号 / 登录 | `models.py` 预留 User；限流中间件独立 | 新增 auth 路由 + JWT，注入依赖 |
| 每用户额度 | `jobs.py` 统一任务入口 | 在任务创建前查 Quota 表 |
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

1. **v1**：核心下载闭环（解析/清晰度/下载）+ 二次元前端体验 + 直链/服务端切换 + 防滥用基础。
2. **v2（候选）**：账号 + 每用户额度。
3. **v3（候选）**：视频总结、字幕翻译（接入 LLM）。
4. **v4（候选）**：付费能力。
