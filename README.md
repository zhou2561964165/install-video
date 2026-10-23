# 视频下载与智能内容处理系统

基于 React 和 FastAPI 的视频处理工作台。用户提交单个视频链接后，可以查看来源信息、选择格式并下载视频；也可以提取平台字幕、独立运行本地语音转写，以及使用翻译、总结和思维导图整理内容。

## 主要功能

| 功能 | 说明 |
| --- | --- |
| 视频解析 | 获取标题、封面、时长、字幕语言及来源实际提供的格式 |
| 视频下载 | 浏览器直链或服务端任务；需要时由 FFmpeg 合并音视频 |
| 任务进度 | 前端每 3 秒查询单个任务，完成后领取文件 |
| 平台字幕 | 查看文本和时间轴，按可用时码导出 SRT、VTT |
| 本地转写 | 使用 faster-whisper 识别音轨，查看并导出文本或时码字幕 |
| 文本整理 | 根据平台字幕生成翻译、分层总结和导图，支持复制与导出 |
| 账号与会员 | JWT 登录、任务与文件归属校验、会员权限及可选 Stripe 支付 |
| 请求复用 | 下载幂等回执、进行中去重和按账号隔离的有界结果缓存 |

平台字幕与本地转写是独立来源。当前翻译、总结和导图读取平台字幕，本地转写结果尚未接入这三项功能。系统以单链接操作为主，暂未提供批量下载、下载历史页面或 WebSocket 推送。

## 技术栈

- 前端：React 18、JavaScript / JSX、Vite、CSS；可选 PIXI / Live2D 装饰层。
- 后端：Python、FastAPI、Pydantic、SQLModel / SQLAlchemy、SQLite。
- 媒体：yt-dlp、FFmpeg / ffprobe。
- 本地语音识别：faster-whisper、CTranslate2，可选安装。
- 内容生成：服务端配置的兼容模型接口。
- 支付：Stripe Checkout 与签名 Webhook，可选启用。

## 环境要求

- Python 3.12+；Node.js 20.19+（20.x）或 22.12+，以及 npm。
- [uv](https://docs.astral.sh/uv/) 用于安装锁定的 Python 依赖。
- FFmpeg 与 ffprobe 已安装并加入 `PATH`；FFmpeg 也可用 `FFMPEG_PATH` 指定。
- 可以访问目标视频来源；使用模型服务或支付时需另行配置相应服务。

## 本地启动

以下命令适用于 PowerShell。前后端分别使用一个终端。

### 1. 安装依赖并准备配置

```powershell
git clone https://github.com/zhou2561964165/install-video.git
cd install-video
uv sync --frozen
Copy-Item backend/.env.example backend/.env
```

编辑 `backend/.env`，先替换 `JWT_SECRET`。模型与支付配置可暂时留空，解析和下载不依赖这两项服务。数据库默认位于 `backend/jobs.db`，临时媒体位于 `backend/tmp/`。

### 2. 启动后端

在项目根目录执行：

```powershell
uv run --env-file backend/.env uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

接口文档：<http://127.0.0.1:8000/docs>。

### 3. 启动前端

在另一个终端进入项目目录后执行：

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 <http://127.0.0.1:5173>，注册或登录后提交视频链接。Vite 默认将 `/api` 转发到后端 8000 端口；后端地址变化时，可在启动前设置 `VITE_PROXY_TARGET`。

### 4. 可选安装语音转写

在项目根目录执行：

```powershell
uv sync --frozen --extra asr
```

默认模型为 `tiny`，使用 CPU 和 `int8`。首次主动转写时可能下载模型，也可用 `ASR_MODEL_PATH` 指定已有模型目录。默认单个音轨最多 30 分钟、128 MiB；时长未知、直播或不符合音轨下载条件的来源会被拒绝。

## 常用配置

示例见 [backend/.env.example](backend/.env.example)，完整变量和校验规则见 [backend/app/config.py](backend/app/config.py)。实际 `.env`、Cookie 和密钥文件不应提交到仓库。

| 变量 | 用途与默认行为 |
| --- | --- |
| `JWT_SECRET` | 登录签名密钥；部署时替换开发默认值 |
| `DB_URL` / `TEMP_DIR` | 数据库与媒体目录，默认 `backend/jobs.db` / `backend/tmp/` |
| `FFMPEG_PATH` | FFmpeg 可执行文件，默认 `ffmpeg` |
| `MEMBERSHIP_UNLIMITED_DOWNLOADS` | 默认 `true`，免费和会员均不限每日下载次数，仍保留统计 |
| `MEMBERSHIP_FREE_MAX_HEIGHT` | 免费下载画质上限，默认 720 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 翻译、短中篇总结和导图的模型接口 |
| `SUMMARY_MAX_SOURCE_CHARS` | 总结的字幕正文输入上限，默认 60,000 字符 |
| `SUMMARY_LONG_THRESHOLD_CHARS` | 默认超过 20,000 字符进入独立长文路径 |
| `LLM_LONG_SUMMARY_MODEL` | 长文专用 DeepSeek Pro 模型，默认 `deepseek-v4-pro`，需匹配模型校验和 Responses 接口能力 |
| `ASR_MODEL` / `ASR_MODEL_PATH` | 本地转写模型名称或已有模型目录 |
| `BILIBILI_COOKIE_FILE` | 可选 Netscape Cookie 文件路径，仅用于 B 站请求，默认空 |
| `BILIBILI_API_ENABLED` | 可选 B 站专用 API 路径，默认 `false` |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe 服务端密钥及通知验签密钥 |
| `STRIPE_PRICE_ID` / `STRIPE_BILLING_MODE` | 商品价格 ID 与支付模式；配置不完整时不开放购买 |
| `STRIPE_PRICE_LABEL` / `STRIPE_PUBLIC_ORIGIN` | 价格说明和允许的站点来源 |
| `STRIPE_VIP_DURATION_DAYS` | 一次性购买的有效天数，默认 30 |

字幕长度限制不等于视频时长限制。超过总结输入上限会在模型调用前拒绝；生成内容仍需对照字幕核实。

## 使用流程与权限

1. 登录后提交一个可访问的视频链接。
2. 核对视频信息，选择来源返回的格式。
3. 发起下载，服务端任务完成后领取文件。
4. 根据需要查看平台字幕、独立转写，或分别发起翻译、总结及导图。

| 用户 | 默认可用能力 |
| --- | --- |
| 访客 | 首页、会员方案、注册及登录 |
| 普通登录用户 | 解析、最高 720p 下载、本地转写、导图；后两项需配置相应依赖 |
| 有效会员 | 普通用户能力、平台字幕与导出、翻译、总结，以及来源提供的更高清晰度 |

身份、会员和资源归属均由后端校验。会员不能取得来源未提供的画质，系统也不会将低清视频升频为高清。

### 可选会员支付

示例采用 `STRIPE_BILLING_MODE=payment`：人民币 9.9 元一次购买 30 天，到期手动续费。部署者需创建对应的 Stripe Price，并配置价格标签、站点来源及 Webhook。权益由验签通过的服务端通知更新，浏览器回跳不直接授予会员。测试和正式环境使用各自的密钥与通知配置。

## 构建与部署

```powershell
cd frontend
npm run build
```

产物位于 `frontend/dist/`。生产服务器提供静态文件，并将同源 `/api` 转发到后端。`npm run preview` 只预览静态产物，不能代替完整后端部署。子路径构建可使用 `npm run build -- --base=/demo/`，服务器需配置匹配的静态路径和 API 转发。

- 后台执行池、缓存和并发槽属于进程内资源，当前按单实例运行方式部署；任务记录持久化不表示重启后自动恢复下载队列。
- 为媒体目录设置空间与清理策略，限制资源使用，并通过 HTTPS 提供公开访问。
- 通用 URL 校验主要检查协议和地址格式。公网部署还需限制私网及云元数据访问，并检查 DNS 和重定向目标，现有校验不构成完整 SSRF 防护。
- B 站等来源可能要求有效会话或触发平台校验；格式和可用性取决于来源及网络条件。
- `tools/`、`deployment/` 含可选 Linux 会话维护脚本和模板，需按自己的目录、服务名及浏览器环境配置，不随本地启动自动运行。
- 仓库保留装饰层源码和 Cubism Core 运行库，Live2D 模型包与语音模型权重不随仓库发布；缺少装饰模型不影响核心功能。

## 目录结构

```text
backend/
  app/          接口、业务服务、配置和数据模型
  scripts/      FFmpeg 安装辅助脚本
  tests/        后端检查与回归用例
frontend/
  src/          页面、组件、业务 Hook、状态与样式
  public/       公共静态资源
tools/          可选维护脚本及独立工具
deployment/     可选部署与会话维护模板
pyproject.toml  Python 依赖与可选组件
uv.lock         Python 依赖锁文件
```

媒体来源统一由 `ytdlp_service.py` 封装；界面表现与下载业务通过窄接口和单向依赖隔离。颜色、字体及交互时长集中使用样式 token 管理。

请仅处理本人拥有或获准使用的内容，并遵守来源平台及内容许可要求。
