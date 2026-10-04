# 交接文档 · 万能视频下载与 AI 内容总结

> 更新：2026-10-04 · v3实现、验收与文档已提交在 `main`。
> 当前入口见 [文档索引](README.md)。最后一次交接前验收结果见[平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md)。

## 0. 当前结论与用户已定方向

- v2：注册/登录、JWT、每用户每日下载额度；解析、下载和 v3 API 必须登录。
- v3：AI 内容总结为主，字幕只是内容来源；允许清理重复片段，长内容分段归纳后合并。字幕读取/翻译保留为辅助能力。
- 滚动落地页保留在登录后，用户已确认；本轮不扩展完整字幕展示、时间轴导出、思维导图、问答或支付。
- 当前测试供应商为 DeepSeek-V4.1-Flash，API 模型 ID `deepseek-flash`；供应商地址、模型和 key 走配置。
- 已只读分析 `C:/Users/zxk/free-video-downloader`，借鉴平台专用提取与通用回退思想并独立实现，未修改参考项目或复制其源码。

## 1. 子agent与本轮交接状态

| 子agent | 处理结果 | 后续使用 |
| --- | --- | --- |
| `real_platform_subtitle_acceptance` | 已完成，已执行停止操作，无运行任务 | 本轮停用，不自动重启或复用 |
| `v3_review` | 已完成，已执行停止操作，无运行任务 | 本轮停用，不自动重启或复用 |

当前运行中的子agent为 **0**；主agent设定未修改。现有管理工具无法删除已完成的历史会话记录，界面仍可能显示这两个完成记录。审查记录中的两项 Important 是修复前发现，现已通过回归测试修复，不代表仍未处理。

## 2. 启动与验证

仓库根目录执行 `uv sync` 安装 Python 依赖；前端首次安装执行 `cd frontend && npm install`。虚拟环境位于仓库根 `.venv`，不是 `backend/.venv`。

本机已配置被 Git 忽略的 `backend/.env`，启动 DeepSeek 联调环境：

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000 --env-file .env
```

另开终端：

```bash
cd frontend
npm run dev
```

新机器先创建自己的 `.env`。不启用 LLM 时，可不加 `--env-file .env`；模型未配置会在功能面板就地提示。文档和源码不保存 key。访问 Vite 输出的实际端口，`/api` 默认代理到 8000。

环境要求：Python 3.12（uv）、Node 满足当前 Vite 的 `^20.19.0 || >=22.12.0`、ffmpeg；最近验证本机 Node 为24.16.0。

```bash
cd backend && uv run python -m pytest -q
cd frontend && npm test
cd frontend && npm run build
```

| 最近验证 | 结果 | 证据范围 |
| --- | --- | --- |
| 后端全量 | 121/121通过 | 包含provider格式回归、有限网络重试、yt-dlp真实退避调用、错误流及时关闭和配置边界测试 |
| 前端全量 | 66/66通过 | 包含解析阶段未发现字幕时仍可显式尝试 AI 的集成回归 |
| 生产构建 / diff check | 通过 | build 有 bundle 大小提示；diff check 只有 Windows 行尾提示 |
| 原5份已许可文件 | 5/5解析通过，原件哈希不变 | 原始验收时为4/5 |
| 新增已许可平台样本字幕API | 首轮 Archive.org、Wikimedia Commons、YouTube 三平台都有成功样本；8项中3项成功 | 单条字幕请求受间歇 TLS/超时影响。限次重试5项为0项成功；失败表示网络错误，不代表无字幕或平台不支持 |
| 真实DeepSeek总结 | 首轮3/3成功，含 Archive.org 约7.2万字符演讲、Archive.org 短片和 Commons 短片 | 长文71,658字符，清理后71,214字符，4段归纳合并，72.67秒返回中文摘要与7要点；只抽查代表性事实和尾部内容，不代表完整语义准确率已测 |
| 下载闭环 | 本机生成3秒 H.264/AAC 样本，经本机 HTTP、yt-dlp、下载任务和文件接口成功；ffprobe确认音视频轨、时长及分辨率 | 验证服务端核心闭环；公网 Samplelib 请求遇TLS错误，不能据此声称该公网样本下载通过 |
| 鉴权/额度 | 5个未授权受保护API均返回401；AI总结前后下载额度不变 | 下载验收用独立临时用户和隔离数据库 |
| TLS重试后真实字幕复测 | 此前失败的 Archive.org 短字幕与 Wikimedia Commons 英文字幕均返回200（2/2） | 是修复后的真实请求成功结果；没有记录每次请求内部实际重试次数。逐项结果见 `retry-live.json` |

逐项平台请求、重试、总结响应与质量核查见[平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md)及其 JSON 证据。此前桌面/375px浏览器验证覆盖注册、登录、刷新、退出、额度、落地页与视频智能面板；本轮补充了真实 insights hook 的前端集成回归。浏览器自动化的后续交互受工具审批阻断，因此不能宣称本轮完整浏览器 E2E 通过。

## 3. 工程约定与隔离边界

1. UI/视觉/交互先用 `ui-ux-pro-max` + `design-system`；不因更换AI工具而跳过已有技能。
2. 用户指令与工程约定优先；skill指引优先于旧计划，历史文档不是新的执行授权。
3. 颜色、字体、时长走三层token；阈值、模型、来源适配、目标语言数据驱动、可配置，避免大规模重构。
4. `ytdlp_service.py` 是唯一接触yt-dlp的层；公开来源适配由它调用。下载线程池不感知账号、LLM或视觉。视觉只读场景状态，不修改下载reducer、不import下载核心。

前端接口只走 `api.js`；`useVideoInsights` 独立管理AI请求和结果，不污染下载状态机。额外工作是否继续以用户当前指令为准；本次停止了子agent，但没有给主agent设定增加规则。

## 4. 实现与文件地图

| 文件/模块 | 当前职责 |
| --- | --- |
| `backend/app/config.py` | 环境变量配置；完整变量列表见根README |
| `services/ytdlp_service.py` | 解析/下载窄接口与字幕来源入口，过滤聊天/弹幕 |
| `services/subtitle_sources.py` | 注册式公开平台适配；Archive元数据优先，文件名精确关联，校验异常结构 |
| `services/subtitle_service.py` | 字幕正文HTTP、字节上限与SRT/VTT/JSON3/TTML文本化 |
| `services/llm_service.py` | 兼容HTTP适配，总结去重、分段/分层合并、输出完整性检查；翻译仍有输入上限 |
| `services/auth.py` / `quota.py` | JWT、密码哈希、每日下载额度；额度在下载路由提交时预留 |
| `services/jobs.py` | 下载线程池、SQLite任务与产物TTL |
| `routes/auth.py` / `parse.py` / `download.py` | 认证、解析、下载/任务状态/文件响应 |
| `routes/insight_common.py` / `subtitle.py` / `summary.py` | v3错误映射、正文、翻译和摘要API |
| `frontend/src/App.jsx` | 登录门、下载场景、主题、独立insights hook与视觉装配；登录后加载重资源 |
| `api.js` / `hooks/useAuth.js` / `hooks/useDownload.js` / `hooks/useVideoInsights.js` | 唯一后端边界与各职责请求编排 |
| `components/ui/VideoInsights.jsx` | 只通过props触发动作和展示结果，下载与AI错误互不替换 |
| `state/sceneMachine.js` / `state/insightConfig.js` | 下载reducer、错误文案与目标语言配置 |
| `styles/global.css` / `pixi/theme.js` | 三层CSS token与PIXI颜色桥接 |
| `pixi/mascotConfig.js` / `mascot.js` | 单模型白、待机/表情/缩放、移动布局；目前没有模型切换UI |

API：`POST /api/subtitle`、`POST /api/subtitle/translate`、`POST /api/summary`；请求与响应详见v3计划。总结返回摘要、关键要点、provider/model。AI请求当前不扣下载额度，AI计费未实现。

## 5. 配置、已修复项与限制

- 当前默认：每用户每天下载10次（UTC日期），提交即扣；失败退款未实现。每IP限流独立保留。
- AI：`LLM_MAX_INPUT_CHARS=60000`；总结分段默认20000字符、最多16段、每次输出最多4096 tokens；可通过 `LLM_SUMMARY_*` 配置调整。
- 字幕/yt-dlp读取：`NETWORK_RETRIES=2`（每个启用重试的请求/yt-dlp重试环节可额外尝试2次）与 `NETWORK_RETRY_BACKOFF_SECONDS=0.5`（各次等待基数，指数递增），两者需为非负有效数。项目自有 httpx GET 重试仅处理超时/网络异常、远端EOF及502/503/504，不重试4xx、无字幕或格式错误；LLM POST不接入该重试器。yt-dlp同时使用其原生有限 `retries` / `extractor_retries`，重试按其错误分类在各环节内生效。
- Archive内容获取不再先依赖视频网页；专用路径不可用时回退yt-dlp。多视频条目没有明确内容关联时要求具体视频文件链接。
- 审查修复：`movie`不会混入`movie.part2`字幕；异常metadata/files/title不会绕过回退；SRT小数精度容错1–3位。
- 本轮审查修复：LLM provider 的 `finish_reason` 与文本块字段格式异常时统一映射为 `llm_invalid_response`；解析阶段暂未发现字幕时，视频智能面板仍开放显式请求并使用“自动选择”语言来源。
- TLS稳定性修复：字幕元数据和正文 GET、以及 `ytdlp_service.py` 内 yt-dlp 读取都使用有界重试；平台专用适配优先与yt-dlp通用回退顺序保持不变。设置见根README，真实字幕复测见 `retry-live.json`。
- 服务端产物TTL清理、ffmpeg合并、直链HTTP请求头限制仍沿用既有下载契约。
- 16K角色纹理的GPU兼容与原作者非商用/不二改限制仍存在；代码只调整布局，没有压缩原模型。
- 原始字幕完整性、音画对齐、说话人、所有语言/编码/平台尚未全面验收；AI主目标不等于已经覆盖这些能力。
- 长模型输出如果被截断会明确报错；超过整体分段预算会提示调整容量，不无限调用模型。
- 已有SQLite表不会被 `create_all` 自动修改；使用旧库前检查schema并备份/迁移，不直接删用户数据库。

## 6. Git、产物与下一步

- v3实现、验收和交接文档已提交；TLS重试后续已在 `96b0b59`（`Add bounded retries for transient subtitle network failures`）提交。原有根目录 `AGENTS.md` 保持未跟踪且未纳入提交；没有改主agent规则或参考项目。
- 最新全量验证：后端121/121、前端66/66、生产构建通过；Archive.org与Commons字幕真实复测2/2。独立复审未发现Critical/Important。
- 原验收 [report.md](acceptance-reports/2026-10-03-single-platform-subtitles/report.md) 保留0/3与4/5历史结果；当前状态以修复后报告为准。
- 原始来源、UTC采集时间、许可、哈希、脱敏副本与去重关联继续保留；历史证据不因修复而改写。
- 验收期间临时服务已全部停止：后端8010、前端5178、本机媒体HTTP 8021均无监听。测试用户库 `backend/quality-online-acceptance.db`、本机生成媒体、pytest临时文件和工作计划均是 Git 忽略的本地验收产物；原 `backend/.env` 仍是被忽略的本地配置，没有复制进代码或报告。
- 用户曾在关机前暂停此前的 v3 工作，恢复后该部分与 TLS 重试后续均已本地提交。验收服务已停止；未跟踪的 `AGENTS.md` 和忽略的 `.env`、SQLite 数据库均未提交。

下一步仅为候选，不自动推进：按用户指令继续扩平台与AI总结质量样本；再考虑流式体验、AI独立额度或v4付费。滚动首页位置已定，不再反复询问。

## 7. 文档入口与阅读顺序

1. [文档索引](README.md) → 本交接 → [需求](requirements.md) / [设计](design.md)。
2. [v3实现计划](superpowers/plans/2026-10-03-v3-video-intelligence.md) → [参考实现分析](reference-summary-implementation.md) → [AI总结修复报告](acceptance-reports/2026-10-03-ai-summary-regression/report.md) → [平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md)。
3. [扩展路线](superpowers/plans/2026-09-21-extension-plan.md) 与 [UI扩展指南](ui-extension-guide.md)。

旧Phase1、霓虹规范与电影感实现计划均为历史参考，不能直接把旧未勾选项当作当前待办。
