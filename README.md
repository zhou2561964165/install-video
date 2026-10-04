# 万能视频下载网站

注册或登录后，粘贴任意平台视频链接 → 解析 → 选清晰度 → 下载到本地；有字幕的视频还可读取字幕、翻译并生成 AI 总结。依托 yt-dlp 覆盖数千站点，前端采用深色液态玻璃 + 樱花粉辉光主题（PIXI 舞台 + Live2D 白角色，含程序化待机动画），移动端可用。

## 工程约定（每次遵守）

> 与根目录 `CLAUDE.md` 一致（最高优先级）。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。

## 架构

```
[前端 React/Vite + PIXI + Live2D]  ⇄ HTTP/JSON  ⇄  [FastAPI 后端]
                                                       │
                                          yt-dlp 服务层（线程池 + SQLite 任务状态）
```

- 后端：`backend/` — FastAPI + yt-dlp(Python API) + SQLModel/SQLite。JWT 登录后才能解析和下载；直链下载与服务端下载自动切换，服务端产物 TTL 自动清理。
- 前端：`frontend/` — React 18 + Vite + PIXI v6 + pixi-live2d-display。单一 PIXI 管线，场景状态机驱动，WebGL 缺失/低端机自动降级。

当前文档从 [文档索引](docs/README.md) 与 [交接文档](docs/handoff.md) 开始阅读。v3以AI内容总结为主：字幕作为来源，重复内容可去重，长内容分段归纳后合并。电影感/霓虹旧计划是历史参考，不直接作为当前待办。

## 环境要求

- [uv](https://docs.astral.sh/uv/)（Python 依赖管理；`uv sync` 自动准备 Python 3.12 与 `.venv`）
- Node.js 满足当前 Vite 依赖要求：`^20.19.0 || >=22.12.0`（本机最近验证为24.16.0）
- **ffmpeg**（合并高清视频/音频流必需；缺少时服务端下载会报 `ffmpeg_missing`）

## 快速启动

### 1. 后端

```bash
# 装依赖（uv 依据根目录 pyproject.toml 建/更新 .venv）
uv sync

# 安装 ffmpeg（合并视频/音频流必需）
#   Windows: powershell -ExecutionPolicy Bypass -File backend/scripts/install_ffmpeg.ps1
#   Linux:   bash backend/scripts/install_ffmpeg.sh
#   或系统安装后确保 ffmpeg 在 PATH 上

# 启动（默认 http://127.0.0.1:8000）
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 由 Vite 代理转发到 8000
```

浏览器打开 `http://localhost:5173`，先注册或登录，再粘贴视频链接走完「解析 → 选清晰度 → 下载」。

## 配置（环境变量）

后端所有可调参数都在 `backend/app/config.py`，均可通过环境变量覆盖，均有合理默认值：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg 可执行文件路径 |
| `MAX_CONCURRENT` | `3` | 并发下载数上限 |
| `TEMP_DIR` | `<backend>/tmp` | 服务端下载临时目录（TTL 自动清理） |
| `MAX_FILE_SIZE` | `2147483648` | 单文件大小上限（字节，默认 2GB） |
| `TTL_SECONDS` | `3600` | 服务端产物保留时长（秒） |
| `DB_URL` | `sqlite:///<backend>/jobs.db` | SQLite 连接串（可换 PostgreSQL） |
| `RATE_LIMIT` | `30` | 每 IP 每窗口请求上限 |
| `RATE_LIMIT_WINDOW` | `60` | 限流窗口（秒） |
| `JWT_SECRET` | 开发默认值 | 生产自行设置JWT签名secret |
| `JWT_EXPIRE_MINUTES` | `10080` | 登录token有效期，默认7天 |
| `DEFAULT_QUOTA_LIMIT` | `10` | 每用户每日下载次数，UTC日期粒度 |
| `PASSWORD_ITERATIONS` | `100000` | PBKDF2密码哈希迭代次数 |
| `SUBTITLE_MAX_BYTES` | `5242880` | 单个字幕文件大小上限 |
| `SUBTITLE_TIMEOUT_SECONDS` | `30` | 字幕来源元数据及正文 HTTP 超时 |
| `NETWORK_RETRIES` | `2` | 每个启用重试的请求/yt-dlp重试环节的额外次数（最多3次尝试）；需为非负整数 |
| `NETWORK_RETRY_BACKOFF_SECONDS` | `0.5` | 各次网络重试的初始等待秒数；后续指数递增；需为有限非负数 |
| `LLM_PROVIDER` | `openai-compatible` | 前端展示的供应商名称 |
| `LLM_BASE_URL` | 空 | OpenAI-compatible API 根地址，如 `https://api.example.com/v1` |
| `LLM_API_KEY` | 空 | LLM Bearer key；本地免鉴权服务可留空 |
| `LLM_MODEL` | 空 | 总结/翻译使用的模型；为空时返回 `llm_unconfigured` |
| `LLM_TIMEOUT_SECONDS` | `90` | LLM 请求超时 |
| `LLM_MAX_INPUT_CHARS` | `60000` | 单次内容输入上限；总结会分段，翻译超限则明确提示 |
| `LLM_SUMMARY_CHUNK_CHARS` | `20000` | 总结分段大小；先清理重复内容，再分段归纳并合并 |
| `LLM_SUMMARY_MAX_CHUNKS` | `16` | 单次总结最多的原始分段数，限制一次请求的模型调用规模 |
| `LLM_SUMMARY_MAX_OUTPUT_TOKENS` | `4096` | 每次分段或合并总结的最大输出 token 数 |

默认路径（`TEMP_DIR` / `DB_URL`）已锚定到后端目录，与启动时的工作目录无关。

### v3 · DeepSeek 本地联调

当前联调使用 DeepSeek-V4.1-Flash，官方 API 模型 ID 为 `deepseek-flash`（见 [DeepSeek 模型列表](https://api-docs.deepseek.com/api/list-models/)）。本机配置位于被 Git 忽略的 `backend/.env`；API key 只保存在该本地文件中。

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000 --env-file .env
```

新环境需自行创建 `.env`，设置 `LLM_PROVIDER=deepseek`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash` 和 `LLM_API_KEY`。后续兼容供应商只需更改这些环境变量。

## 验证

最近已完成的验证：后端121/121、前端66/66、生产构建通过；原5份已许可文件解析5/5且SHA-256不变。TLS重试修复提交于 `96b0b59`。三平台字幕请求、TLS重试后的真实字幕复测和三次真实 DeepSeek 总结见[平台与总结质量报告](docs/acceptance-reports/2026-10-03-platform-quality/report.md)。上一轮结果见[AI总结修复报告](docs/acceptance-reports/2026-10-03-ai-summary-regression/report.md)，各轮数据分别记录，不推断所有平台均可用。

### 自动化测试

```bash
# 后端（pytest）
cd backend && uv run python -m pytest

# 前端（vitest）
cd frontend && npm test
```

### 手工冒烟（端到端主链路）

1. 按「快速启动」起后端与前端。
2. 前端粘贴 `https://www.youtube.com/watch?v=dQw4w9WgXcQ`，点「解析」→ 应出现标题、时长与多档清晰度。
3. 选一档清晰度点「下载」：
   - 直链可用 → 浏览器直接保存；
   - 否则落到服务端下载（轮询进度到 `done`）→ 点「保存文件」。
4. 后端接口可直接验证（curl）：

```bash
curl -X POST http://127.0.0.1:8000/api/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## 署名与授权

Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨。模型遵循作者使用规则：**非商用、不二传二改**（见 `frontend/README.md`）。
