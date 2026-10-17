# 万能视频下载网站

> **2026-10-17提交推送：** 用户授权的累积改动已通过隔离模型过滤流程推送至个人私有GitHub，远端产品提交为`7db9ead`，本地模型与原历史保留。尚未部署，F-006仍待用户查验，质量缺口保留；详见[交付记录](docs/implementation-reports/2026-10-17-github-delivery.md)。下文“未提交/推送”仅代表各阶段记录时点。

> **F-003最终交验（2026-10-17）：** 用户已查验通过，包含最新小圈范围与标题倾斜。小圈可在内容列两侧、普通控件和空白处显示，仅避让顶部、模型alpha轮廓及解析表单；模型位置不自动漫游，手动拖动后停在新位置，待机动作继续。257项前端回归/build及本地模型10项浏览器检查的范围见[小圈交验](docs/implementation-reports/2026-10-17-f003-circle-scope.md)和[待机行为交验](docs/implementation-reports/2026-10-17-f003-original-behavior.md)。

> **F-006交验（2026-10-17）：** 实现与验证已完成，等待用户查验。游客/认证恢复中显示首页；顶部登录按钮进入登录/注册页；匿名解析只提示、不发业务API；返回及认证成功保留URL但不自动解析；恢复失败回游客首页。后端鉴权不变。23个前端文件266项、build 300模块、Edge及本地权限检查和独立复核范围见[F-006报告](docs/implementation-reports/2026-10-17-f006.md)。

> **F-003待机行为（2026-10-17）：** 用户已查验通过。自动漫游及新增的位置/暂停菜单已取消；模型保持当前位置，拖动后停在新位置，原待机与小圈alpha联动继续。详情见[交验](docs/implementation-reports/2026-10-17-f003-original-behavior.md)。

> **F-003续调历史：** 两个悬浮按钮和模型方框已取消；小圈按可见alpha轮廓接触隐藏。该阶段的实现和验收数字保留于[续调交验](docs/implementation-reports/2026-10-16-f003-adjustment.md)，顶部登录入口随后在F-006实施。

> **阶段交验历史：** F-001/F-002各自实现完成后曾等待用户查验；F-003初始行为与2026-10-16漫游/暂停验证数字仅属于对应阶段。F-003最终范围已于2026-10-17获用户查验通过；当前行为以本节上方两份交验为准。当前后续任务是F-006，状态见[总表](docs/follow-up-plan.md)。

未登录/认证恢复期间先显示首页，登录/注册由顶部按钮显式打开。游客可填写视频链接；提交解析时会留在首页提示请使用顶部登录按钮，不发送解析请求。认证成功返回首页并保留链接，不自动解析。会话恢复成功直接进入首页，失败回游客首页。登录/会话恢复后，粘贴视频链接 → 解析 → 选择格式 → 下载。有可用字幕的视频可读取字幕、翻译并生成AI总结；前端提供双栏工作台、返回输入、完整文本复制和TXT导出。服务端下载默认按视频原标题保存，取消该选项后使用来源直链，文件名由来源站决定。F-006实现及验证已完成，待用户查验；真实账号登录未测试。

## 当前使用与验收边界（2026-10-17）

- **长文使用与入口：** 用户已确认长文可以上线使用，F-001产品入口已实现。公开总结默认最多接收60000字符；字幕超过20000字符时改走完整来源长文路径，超过公开上限或长文模型输入上限则在模型调用前拒绝。质量整改仍待继续，技术实现不等于已部署或内容质量PASS。
- **模型配置与调用边界：** 短中篇仍用既有`LLM_MODEL`及`legacy/adaptive/single`、`fidelity=off`；长文使用单独配置的`LLM_LONG_SUMMARY_MODEL`（默认`deepseek-v4-pro`），复用运行环境已有的`LLM_BASE_URL`与`LLM_API_KEY`。长文按Responses `text`/`high`/16384输出token/300秒HTTPX timeout调用；timeout是HTTPX各阶段超时配置，不是硬墙钟截止。每进程默认仅接纳1个长文请求，忙时不排队并返回503；不重试、不回退。没有读取或修改本机`.env`，也未部署或复测该路线的模型内容质量。
- **输出形式：** `/api/summary`响应新增`format`。短中篇保持结构化`summary`和`key_points`；长文返回未经Markdown拆分的原样`summary`、空`key_points`及`format="markdown"`，由前端安全渲染。
- **本次第一步已完成：** 仅DeepSeek Pro，两份新来源各一次全文生成，2POST/23275供应商tokens并封账。英文长文7/8项核心完整，仍缺转换前提并有局部退出条件错误；中文短文4/4项完整，未发现确证核心事实错误，但重复扩写明显。这不是优化前后对照或跨模型比较。
- **当前验证：** 本轮前端65项集成检查和build通过，实施者后端236项离线目标通过，root另行复核的93项后端定点通过、独立审查C/I/M=0/0/0。Root浏览器以模拟API、禁用WebGL完成1440/390/320px的parse→长文总结流程，Markdown布局、代码块、无要点栏及无横向溢出通过；这些不验证真实模型输出、Live2D角色或部署。前端65项包含App集成回归。
- **后续边界：** phase15第一步历史实测已封账；F-003已由用户查验通过，F-006实现与验证完成并等待用户查验。F-001/F-002按各自交验记录维护；长文质量整改及产品部署继续按[统一总表](docs/follow-up-plan.md)管理。

[当前完整交接](docs/handoff-2026-10-16-deepseek-step1.md) · [第一步报告](docs/acceptance-reports/2026-10-16-deepseek-source-screen/report.md) · [逐项内容审阅](docs/acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md) · [原样结果下载](exports/deepseek-step1-2026-10-16.zip)

长文工作组phase1–15累计23POST/319471tokens、全部closed；Ragas独立16/34106，持续整改合计39/353577，旧67POST另封账。F-001实施没有发模型POST；旧phase和余额不重开、不借用。整体总结质量尚未全面解决，长文技术接入不构成语义验收或部署证明。

## 界面、字幕与平台现状

浅色默认、深色和自动主题，浮动玻璃导航、淡彩背景与双栏内容工作区已实现。PIXI舞台和本地Live2D角色保留；桌面符合设备与宽度条件时，角色保持当前位置，手动拖动后停留在新位置，呼吸、摆头、换装、表情和道具待机继续。手机UA或≤800px视口不创建角色模型、图片fallback或角色交互面；共享Cubism Core脚本仍由`index.html`加载。F-003已由用户查验通过：小圈随全视口指针显示，可在两侧、普通按钮/链接/菜单和空白处保持，仅避让顶部、模型alpha轮廓与解析表单；标题倾斜随小圈位置变化，模型拖动边界未改。真手机、GPU峰值内存和长时FPS未验证。旧[嵌入报告](docs/acceptance-reports/2026-10-13-embedded-mascot-refinement/report.md)、[全站UI迭代](docs/acceptance-reports/2026-10-13-ui-reference-deep/report.md)和[跟随续测](docs/acceptance-reports/2026-10-13-ui-follow-continuation/report.md)是历史阶段；最新范围见[小圈交验](docs/implementation-reports/2026-10-17-f003-circle-scope.md)和[待机行为交验](docs/implementation-reports/2026-10-17-f003-original-behavior.md)。

指定B站视频`BV1gPH96dEUC`曾实际验证解析和字幕接口成功，见[视频流程报告](docs/acceptance-reports/2026-10-12-reference-video-workflow/report.md)。B站播放响应风险校验已有专属提示，具体诱因和稳定性仍未完全证明；空轨道与结构无效分开处理。`BV1B84y1q7Hr`的字幕结构反馈尚缺该视频上游payload复验。画面文字OCR与音频转写尚未实现，不因候选讨论写为已有功能。

## 工程约定（每次遵守）

> 以最新用户 `AGENTS.md` 和当前有效指令为准。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。
5. **成熟方案优先，避免重复造轮子**：开发前复用已有研究并查找成熟库、框架与官方方案，适用时优先实际采用；自研聚焦业务适配和确实缺失的能力，选型记录来源、版本及采用/不适用原因。详见 [AGENTS.md §10](AGENTS.md) 和 [成熟方案研究](docs/reference-summary-review-2026-10-10.md)。

## 架构

```text
React App / 认证、下载、内容hooks / DOM + PIXI与Live2D
    │ 同源HTTP / Bearer
FastAPI模块化单体
    ├─ 认证与每日额度 → SQLite User / Quota
    ├─ 解析/字幕 → yt-dlp唯一适配层 / 公开平台适配 / 正文HTTP
    ├─ 下载 → 直链返回，或JobManager下载池 → yt-dlp/ffmpeg → 本地文件
    │                                      └─ SQLite Job进度/终态
    ├─ 翻译/短中总结同步请求 → llm_service默认分支 → 配置的模型供应商
    └─ 长文总结同步请求 → summarize_long_text完整来源委托 → 独立DeepSeek Pro配置

独立开发验收：docs/acceptance-reports/.../scripts 与 tools/semantic_eval
```

- 后端只有服务端下载使用专用线程池；解析、字幕、翻译和总结在同步请求链等待外部I/O。SQLite持久化业务状态，执行队列及IP限流属于进程；尚无后端取消或任务重启恢复。成功产物在后续下载提交时懒清理，失败/中断残留不受同一TTL保证。
- 前端由App组装认证、下载reducer及独立内容状态；PIXI背景/角色接收业务只读信号，小圈读取DOM几何并与角色热区避让，角色自身漫游不驱动下载业务。当前桌面默认free视口活动，`embedded`仅保留为显式旧调用兼容；手机UA或≤800px视口在创建角色前关闭模型与fallback。单PIXI舞台不表示所有交互共用一个循环。
- 生产内已有LCEL/Pydantic依赖，独立Ragas另有锁环境；历史Pro全文验收runner仍独立于产品API，F-001另行新增了受限的长文产品服务路径。完整结构、依赖版本、组合规则和运行限制见[架构设计](docs/design.md)，审视发现与后续处理统一见[总表F-005](docs/follow-up-plan.md#9-f-005技术架构审视2026-10-16)。

2026-10-10三轮在线验收属于历史：来源优先5POST、阶段分离6POST、原生Schema/Pro对照6POST，累计17/17 POST、74355供应商tokens并封账。第三轮三源结构均通过（短5/中6/长14点），中长内容未全过，未升级默认或部署；旧26/26组原件保持。该阶段证据见[原生Schema/Pro实测](docs/acceptance-reports/2026-10-10-schema-pro-summary-live/report.md)；当前产品入口和待办见[文档索引](docs/README.md)及[当前交接](docs/handoff-2026-10-16-deepseek-step1.md)。

## 环境要求

当前第一步已完成并停止：长文phase1–15累计23POST/319471tokens，Ragas16/34106，合计39/353577，旧67另封账。整体整改曾获无总费用/POST上限授权，但不覆盖用户本次“后面的听我指示”边界；不自动继续A/B、核查、编辑或新阶段。未来如获新指示，每phase仍先限定有限上限/用途/台账，root共享锁、发前预占、首错停，不重开已closed阶段。见[当前交接](docs/handoff-2026-10-16-deepseek-step1.md)及[路线记录](docs/summary-route-decision-2026-10-15.md)。

成熟方案已实际采用Pydantic严格类型/schema、PydanticOutputParser和langchain-core固定串行编排；langsmith仅用于关闭追踪。F-001后端未新增依赖，前端新增MIT许可的react-markdown 10.1.0；没有第三方评测上传；staged要点→概览、Responses/json_schema和fidelity路径仍为历史/显式候选。短中篇沿用现有分段流程，长文采用独立单次全文路径。旧结果清空修复已完成；成熟组件提供结构与编排能力，内容忠实仍须独立验证。

- [uv](https://docs.astral.sh/uv/)（Python 依赖管理；项目要求 Python ≥3.12，根目录 `uv sync` 准备依赖与 `.venv`）
- Node.js 满足当前 Vite 依赖要求：`^20.19.0 || >=22.12.0`（本机最近验证为24.16.0）
- **ffmpeg**（合并高清视频/音频流必需；缺少时服务端下载会报 `ffmpeg_missing`）

## 快速启动

GitHub版本不包含Live2D模型包及其历史。需要角色时，将已获许可的模型放回本机`frontend/public/live2d/`对应目录；未补齐时使用现有fallback。Cubism Core运行库保留。发布维护见[当前交接](docs/handoff-2026-10-10.md)，本机含模型的原历史不直接推送。

### 1. 后端

```powershell
# 装依赖（uv 依据根目录 pyproject.toml 建/更新 .venv）
uv sync

# 安装 ffmpeg（合并视频/音频流必需）
#   Windows: powershell -ExecutionPolicy Bypass -File backend/scripts/install_ffmpeg.ps1
#   Linux:   bash backend/scripts/install_ffmpeg.sh
#   或系统安装后确保 ffmpeg 在 PATH 上

# 启动（默认 http://127.0.0.1:8000）
Set-Location backend
# 已配置 backend/.env 时载入现有模型endpoint/key，供字幕翻译、短/中总结及长文总结使用
uv run uvicorn app.main:app --reload --port 8000 --env-file .env
# 仅用下载/字幕且没有 .env 时，可省略 --env-file .env
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 由 Vite 代理转发到 8000
```

浏览器打开 `http://localhost:5173`，先注册或登录，再粘贴视频链接走完「解析 → 选清晰度 → 下载」。

## 配置（环境变量）

后端配置主体在 `backend/app/config.py`，通过环境变量覆盖；额度豁免路径由 `services/quota_policy.py` 读取。`.env` 不会由配置类自动加载，使用本地文件启动时需传 `--env-file .env`。LLM地址和模型默认留空，未配置时仍可读取字幕。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg 可执行文件路径 |
| `MAX_CONCURRENT` | `3` | 每个后端进程的下载线程池上限 |
| `TEMP_DIR` | `<backend>/tmp` | 服务端下载临时目录（提交新下载时触发 TTL 清理） |
| `MAX_FILE_SIZE` | `2147483648` | 服务端下载完成后检查文件大小（字节，默认2GB）；直链浏览器下载不经此检查 |
| `TTL_SECONDS` | `3600` | 服务端产物保留时长（秒） |
| `DB_URL` | `sqlite:///<backend>/jobs.db` | 当前按SQLite实现；改用其他数据库需匹配驱动、调整 `db.py` 的SQLite专用连接参数并另行验证 |
| `RATE_LIMIT` | `30` | 每个进程内每 IP 每窗口 `/api/` 请求上限，含鉴权、任务轮询及文件请求 |
| `RATE_LIMIT_WINDOW` | `60` | 限流窗口（秒） |
| `JWT_SECRET` | 开发默认值 | 生产自行设置JWT签名secret |
| `JWT_EXPIRE_MINUTES` | `10080` | 登录token有效期，默认7天 |
| `DEFAULT_QUOTA_LIMIT` | `10` | 每用户每日下载次数，UTC日期粒度 |
| `DEV_QUOTA_POLICY_FILE` | `<backend>/dev-quota-policy.json` | 按请求读取的本地开发额度豁免文件；缺失、不可读或格式非法时保持有限额度 |
| `PASSWORD_ITERATIONS` | `100000` | PBKDF2密码哈希迭代次数 |
| `SUBTITLE_MAX_BYTES` | `5242880` | 单个字幕文件大小上限 |
| `SUBTITLE_TIMEOUT_SECONDS` | `30` | 字幕来源元数据及正文 HTTP 超时 |
| `NETWORK_RETRIES` | `2` | 每个启用重试的请求/yt-dlp重试环节的额外次数（最多3次尝试）；需为非负整数 |
| `NETWORK_RETRY_BACKOFF_SECONDS` | `0.5` | 各次网络重试的初始等待秒数；后续指数递增；需为有限非负数 |
| `LLM_PROVIDER` | `openai-compatible` | 供应商标签；`deepseek`选择摘要专用兼容选项，不会自动配置地址或模型 |
| `LLM_BASE_URL` | 空 | OpenAI-compatible API 根地址，如 `https://api.example.com/v1` |
| `LLM_API_KEY` | 空 | LLM Bearer key；本地免鉴权服务可留空 |
| `LLM_MODEL` | 空 | 总结/翻译使用的模型；为空时返回 `llm_unconfigured` |
| `LLM_TIMEOUT_SECONDS` | `90` | LLM 请求超时 |
| `LLM_MAX_INPUT_CHARS` | `60000` | legacy单次字幕/合并notes及翻译内容上限；来源反馈/修订核完整system+user消息容量，facts核完整序列化请求 |
| `SUMMARY_MAX_SOURCE_CHARS` | `60000` | 公开总结接口的字幕正文字符上限，整数1–1000000；超过时422 `summary_unsupported_length`，不调用模型 |
| `SUMMARY_LONG_THRESHOLD_CHARS` | `20000` | 字幕正文超过此值时走独立长文全文总结路径；不超过时沿用短中篇默认总结 |
| `LLM_LONG_SUMMARY_MODEL` | `deepseek-v4-pro` | 独立长文模型配置；服务要求兼容的DeepSeek Pro模型ID，与短中篇`LLM_MODEL`分开 |
| `LLM_LONG_SUMMARY_MAX_INPUT_CHARS` | `60000` | 长文单次全文输入上限；超过时模型调用前拒绝 |
| `LLM_LONG_SUMMARY_MAX_OUTPUT_TOKENS` | `16384` | 长文单次Responses输出token上限 |
| `LLM_LONG_SUMMARY_TIMEOUT_SECONDS` | `300` | 长文HTTPX timeout配置；连接/读写等阶段受限，不是硬墙钟总时限 |
| `LLM_LONG_SUMMARY_MAX_CONCURRENT` | `1` | 每进程长文请求准入上限；不排队，繁忙请求返回503 `llm_busy` |
| `LLM_SUMMARY_CHUNK_CHARS` | `20000` | 总结分段大小；规范空白、仅折叠相邻相同非空行，再分段归纳合并；保留跨语境重复 |
| `LLM_SUMMARY_MAX_CHUNKS` | `16` | 单次总结最多的原始分段数，限制一次请求的模型调用规模 |
| `LLM_SUMMARY_MAX_OUTPUT_TOKENS` | `4096` | 每次分段或合并总结的基础输出token预算；adaptive可随原字幕规模有限增长 |
| `LLM_SUMMARY_STRATEGY` | `legacy` | `legacy`使用字幕分段归纳/合并；`facts`显式事实实验；`auto`先做facts预检，符合条件才选facts |
| `LLM_SUMMARY_LENGTH_MODE` | `adaptive` | 字幕总结按原内容规模有限拓展，不设固定摘要/要点字数门槛；`fixed`保留旧实验合同 |
| `LLM_SUMMARY_GENERATION_MODE` | `single` | `single`沿用分段/合并；`staged`为显式要点→概览实验，不是当前默认 |
| `LLM_SUMMARY_OUTPUT_TOKEN_CEILING` | `max(8192,基础预算)` | 未设置时保留旧高基础预算；显式值须覆盖基础预算，可配置至65536 |
| `LLM_SUMMARY_POINT_CEILING` | `14` | 内部总结主题数量上限，配置7–32；较大字幕分段能力用于显式实验，公开入口另有正文上限；短文使用更少，不要求填满 |
| `LLM_SUMMARY_RESPONSE_FORMAT` | `auto` | `auto` / `text` / `json_object` / `json_schema` / `strict_tool`；auto对DeepSeek使用JSON模式，对其他供应商不附加输出格式参数；后两项仅legacy显式实验 |
| `LLM_SUMMARY_THINKING_MODE` | `auto` | `auto` / `enabled` / `disabled`；auto仅DeepSeek摘要关闭推理，避免推理消耗正文预算；明确值由操作者确保供应商支持 |
| `LLM_SUMMARY_MAX_POINT_CHARS` | `240` | 仅fixed及事实合同实验使用；默认adaptive无单点固定字数硬拒，不裁切 |
| `LLM_SUMMARY_NOTES_LANGUAGE` | `source` | 多段内部笔记保留源语言；`output`显式兼容旧笔记语言。单段/最终结果仍用请求语言 |
| `LLM_SUMMARY_SOURCE_CONTEXT_MODE` | `auto` | 原文+notes装得下时merge使用完整原文；`boundary`显式只用头尾，auto装不下也回到有省略标记的边界 |
| `LLM_SUMMARY_SOURCE_CONTEXT_CHARS` | `1200` | 边界模式每段头尾各保留至多该字符数；`0`关闭来源上下文（包括auto完整原文） |
| `LLM_SUMMARY_FIDELITY_MODE` | `off` | `off/long/review/checks/subject_checks`；除off外均为legacy/single/adaptive显式候选，不改变独立长文路径 |
| `LLM_SUMMARY_REVIEW_MAX_OUTPUT_TOKENS` | `4096` | review/checks反馈阶段独立输出预算，整数1–65536；修订仍用字幕自适应预算 |
| `LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS` | `8192` | 显式subject_checks候选的独立上限；14点需求7808，整数1–65536 |
| `LLM_SUMMARY_FACTS_MAX_SOURCE_CHARS` | `40000` | facts去重后原字幕字符上限，整数1–1000000 |
| `LLM_SUMMARY_FACTS_CHUNK_CHARS` | `8000` | facts抽取分段字符上限，实际还受legacy分段及单次输入上限约束；整数1–1000000 |
| `LLM_SUMMARY_FACTS_MAX_PER_CHUNK` | `12` | facts每分段抽取事实上限，整数1–48 |
| `LLM_SUMMARY_FACTS_MAX_EVIDENCE_SENTENCES` | `128` | facts单条事实引用的证据句数量上限，整数1–256 |
| `LLM_SUMMARY_FACTS_MAX_SUMMARY_CHARS` | `800` | 显式facts实验的摘要总字符上限，整数1–4000；与默认adaptive字幕总结无关 |
| `LLM_SUMMARY_FACTS_COMPOSE_MAX_OUTPUT_TOKENS` | `0` | facts合成阶段独立输出预算；0沿用基础预算，允许0–65536 |
| `LLM_SUMMARY_FACTS_AUDIT_MAX_OUTPUT_TOKENS` | `0` | facts核查阶段独立输出预算；0沿用基础预算，允许0–65536 |
| `LLM_SUMMARY_FORMAT_RETRIES` | `1` | facts共享格式修复上限，整数 `0–2`；显式legacy/staged也读取此配置，但整次总结至多1次，且受MAX_EXTRA_CALLS约束；`0`关闭 |
| `LLM_SUMMARY_SEMANTIC_RETRIES` | `1` | 事实总结核查发现内容、核心覆盖或引用未决时，最多追加的针对性修订次数；整数 `0–2` |
| `LLM_SUMMARY_MAX_EXTRA_CALLS` | `2` | facts格式/语义修复共享的附加调用上限，整数 `0–2`；也限制显式staged的最多1次格式修复。网络、供应商、来源、容量和配置错误立即停止 |
| `LLM_SUMMARY_QUALITY_CONTRACT` | `compat` | 仅facts实验：`compat`保持原核查合同；`compact`使用有限主题和内嵌四项布尔核查，由程序转换、关联引用并严格验收 |

短中篇默认配置组合为 `legacy/adaptive/single`、fidelity=`off`、notes=`source`、context=`auto`。长文公开上限默认60000字符，超过20000字符时走单次全文Markdown路径；此前分段预算只适用于短中篇路径。短中路径仍仅折叠相邻重复，跨语境重复保留；单段一次POST，多段按leaf与合并次数计费，不适用facts的`n+2`公式。adaptive在每超过8000个清理后源字符的档位增加1024输出tokens和2个可用要点，分别受输出token和主题上限约束；合并按对应源字幕字符总量计算。它不以固定摘要/单点字数拒绝，不裁字删点。

已实现的来源候选默认关闭：完整多段生成时`long`在B之后追加一次完整原文+草稿修订，正常及最坏B+1；`review/checks/subject_checks`走固定LCEL核查→修订两节点，正常及最坏B+2。单段仍1POST，不调用校订；复用已绑定草稿的独立验收long为1 POST，review/checks/subject_checks为2 POST，不重新付费抽取。旧checks预算`128+256×(点数+1)`仍受`LLM_SUMMARY_REVIEW_MAX_OUTPUT_TOKENS=4096`约束。新`subject_checks`按草稿动态生成必需对象字段`target_0…target_N`，值含assessment、`same/draft_broader/draft_narrower/uncertain`范围关系、source/draft主体、最多120字符连续原文引用及最多80字符finding；核查调用用现有Responses `json_schema`，14点预算`128+512×(点数+1)=7808`并受独立`LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS=8192`约束，超限首POST前拒绝。所有候选均无付费重试/hidden fallback，错误或完整source/draft/feedback超容量立即停止；字段、引文归属与assessment不构成语义成功证明，公开响应仍仅summary/key_points。

legacy raw先经过独立`summary_json.py`再入Pydantic/既有预算校验。合法JSON保持旧兼容；只修可证明全部完成字符串及标点结构保留的终端闭合，使用已有Pydantic核心parser，不补默认值、不吞未完成点、不裁字删点，也不额外调用模型。单边Markdown围栏拒绝；strict仍禁围栏/保留严格schema，但也可接受经无损门证明的闭合修复。该格式层不证明来源忠实或内容质量。

显式 `facts` 保留事实抽取→合成→原文核查实验，仍有固定摘要/要点合同，未采用adaptive预算。`auto` 在付费前预检facts协议和容量，仅预检的 `llm_unconfigured` / `llm_input_too_large` 可选择legacy；非法策略、事实字段/重试/质量合同配置先拒绝。facts阶段一旦发出请求，不会因错误切换legacy或隐藏付费fallback。facts仅支持 `auto` / `text` / `json_object`，不支持 `json_schema` / `strict_tool`。

facts模型输出先经过独立规范化层，再由程序根据已验证事实关联引用；完整段落字符串可以直接规范化，不额外调用模型。规范化保留非空内容与原ID提示，不盲挂所有引用；引用匹配提供来源关联建议，最终仍执行原文来源、核心事实覆盖及逐项核查。职责分别位于 `summary_normalization.py`、`summary_references.py`、`summary_retry.py`，HTTP编排保留在 `llm_service.py`。正常调用为facts抽取分段数 `n+2`，默认最多1次格式修复及1次语义修订、共享2次附加调用，因此默认最坏 `n+4`；只重做失败阶段，所有attempt计入trace。网络、供应商、来源安全、容量和配置错误立即停止。默认legacy/single与翻译不自动付费重发；显式legacy/staged整次总结最多追加1次格式修复，受`LLM_SUMMARY_FORMAT_RETRIES`及`LLM_SUMMARY_MAX_EXTRA_CALLS`共同约束，不执行语义重试；`NETWORK_RETRIES`只控制启用它的字幕HTTP和yt-dlp请求，不控制模型POST。

默认路径（`TEMP_DIR` / `DB_URL`）已锚定到后端目录，与启动时的工作目录无关。

### v3 · DeepSeek 本地联调

此前产品链路验收记录使用 `deepseek-flash`，phase15独立profile使用 `deepseek-v4-pro`；代码从 `LLM_MODEL` 读取模型ID，代码默认值为空，不绑定具体模型版本。供应商可用模型以其[模型列表](https://api-docs.deepseek.com/api/list-models/)为准。本地配置可放在被Git忽略的 `backend/.env`；此次文档核对未读取该文件，不将历史配置视为当前实测。

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000 --env-file .env
```

新环境需自行创建被Git忽略的 `.env`。DeepSeek配置示例为 `LLM_PROVIDER=deepseek`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash` 和本机 `LLM_API_KEY`；模型名是示例，不是代码默认值或本轮修改后的环境配置。供应商地址、协议及模型能力需要匹配对应兼容选项，不能仅凭变量名称推断支持。

摘要的默认兼容选项由供应商名驱动：DeepSeek使用`response_format=json_object`及`thinking=disabled`，两项可分别覆盖；其他供应商的auto不附加格式或推理字段，`text`也仍要求模型内容为摘要JSON。翻译请求不携带摘要专用字段。字段缺失、空结果、截断或过滤返回明确错误；模型传输错误不自动重发。facts中可规范化的格式问题及有限修复按上一节处理。相关协议参考[DeepSeek JSON输出](https://api-docs.deepseek.com/guides/json_mode/)及[推理模式](https://api-docs.deepseek.com/guides/thinking_mode/)。

legacy显式`json_schema`走Responses接口，`strict_tool`返回本次预算数量的槽位，未使用的尾部槽位留空，再映射回摘要/要点，不执行工具；fixed预算为7槽位，adaptive随字幕规模增长。DeepSeek官方域名的strict工具请求路由至`/beta/chat/completions`，开启推理时预先拒绝。历史实测供应商仍会违反数量、非空或长度约定，本地验证和失败提示继续生效；[2026-10-04实验报告](docs/acceptance-reports/2026-10-04-schema-summary-quality/report.md)记录的是当时fixed协议，不能视为新adaptive实验协议通过。API根地址应不带query/fragment。原始分段边界用于补充有损notes，不能保证源中所有事实都被保留。

## API、鉴权与实现边界

注册/登录返回 `token` 和 `user`；后续需鉴权的接口携带 `Authorization: Bearer <token>`。接口字段以 `backend/app/schemas.py` 为准，开发时可查看 `/docs`。

| 方法与路径 | 主要请求字段 | 当前行为 |
| --- | --- | --- |
| `POST /api/auth/register` | `email`、`password` | 邮箱规范化为小写；密码至少8位；成功返回登录token |
| `POST /api/auth/login` | `email`、`password` | 成功返回登录token |
| `GET /api/auth/me` | Bearer token | 返回 `user` 和 `quota`，额度字段为 `date`、`limit`、`used`、`remaining`、`unlimited` |
| `POST /api/parse` | `url` | 需登录；返回视频元数据、字幕语言与可选格式，不扣每日下载额度 |
| `POST /api/download` | `url`、`format_id`、可选 `force_server=false` | 需登录；提交前预扣1次额度；返回直链 `url`/`headers` 或服务端 `job_id`。网页默认显式发送 `true` 保留原标题，API缺省值保持兼容 |
| `GET /api/job/{job_id}` | 任务ID、Bearer token | 仅本人任务返回状态及进度；匿名/无效token为401，他人/无主/不存在任务统一404 |
| `GET /api/file/{job_id}` | 任务ID、Bearer token | 仅本人完成且文件仍存在的任务返回文件；匿名401，他人/无主/不存在或本人未完成/文件缺失为404 |
| `POST /api/subtitle` | `url`、可选 `language` | 需登录；返回正文、实际语言、是否自动字幕及可选语言 |
| `POST /api/subtitle/translate` | `url`、可选 `source_language`、`target_language=zh-CN` | 需登录；读取字幕并调用LLM翻译 |
| `POST /api/summary` | `url`、可选 `subtitle_language`、`output_language=zh-CN` | 需登录；返回`summary`、`key_points`、provider/model及`format`。默认正文不超过60000字符；超过20000字符走长文Markdown全文路径，超过上限时422且模型零调用 |

下载直链与服务端模式都计入UTC当日额度，下载失败也不自动退回；字幕读取、翻译和总结不扣这项下载额度，但都受API限流约束。指定用户豁免时 `unlimited=true`、`limit=null`、`remaining=null`，`used`仍累加。豁免按明确用户ID匹配，文件只允许 `unlimited_user_ids` 字段、唯一非空ID，不支持通配符；移除ID或无效文件后恢复原有限额度。

常见错误采用HTTP `detail` 对象承载 `error`，服务错误通常还含 `error_type`：缺失/失效登录token为401 `login_required`；下载额度或IP限流为429 `quota`；无效视频URL为400 `invalid_url`；B站主播放响应有风险校验且没有可用格式时为422 `verification_required`；其他平台提取及字幕读取失败为422；LLM未配置为503 `llm_unconfigured`，模型请求、响应及输入容量等错误为502。Pydantic请求字段校验也可能返回422，但其 `detail` 是字段错误列表。异步下载失败记录在任务响应的 `error_type` / `error`，不是创建任务接口同步报错。

B站播放接口有时HTTP200且`code=0`，却只返回风险校验字段`v_voucher`，没有媒体地址。当前服务复用yt-dlp提取器识别主播放响应中的“非空校验字段且无有效格式”，返回`verification_required`，前端显示“平台安全校验”；解析接口仍为422，下载任务沿用现有错误字段。补查其他清晰度遇到校验时保留已有主格式。请稍后重试。这个提示不会证明代理、请求频率或账号是具体诱因，也不能保证网站恢复提供视频流；缺少主响应风险校验证据的其他无格式错误保持原处理。此次没有接入浏览器Cookie或增加自动重试；显式直链模式失败后尝试服务端下载的既有行为保持，可能再次提取，默认仍为服务端模式。诊断与验证范围见[2026-10-13报告](docs/acceptance-reports/2026-10-13-bilibili-verification/report.md)。

已实现账号登录、每日下载额度、本人任务/文件访问隔离、服务端线程池任务、产物懒清理、平台字幕读取/翻译、默认短中总结及F-001长文总结路径。长文在20000–60000字符区间走独立DeepSeek Pro全文Markdown请求；语义质量尚未复测，浏览器/API模拟和离线检查不替代真实供应商质量验收。前端服务端文件携Bearer获取Blob后保存，取消/退出/换账号阻止过期保存；Blob缓存完整文件，仍有大文件内存边界。当前未实现定时TTL清理、下载失败额度退回、分布式限流/队列或重启后自动恢复下载任务；没有视频音轨转写，也没有画面文字OCR。OCR仅列为后续候选，不在当前使用范围。总结质量边界见当前交接。

## 验证

2026-10-16 F-001实现验证：后端236项实施者离线目标通过，root另做93项定点通过；前端65项与生产build通过。Root浏览器以模拟API、禁用WebGL完成1440/390/320px实际parse→长文总结流程，Markdown标题/代码块显示、无空要点栏及无横向溢出通过。独立审查C/I/M=0/0/0；这些检查未调用真实供应商，未验证长文语义质量或部署。phase15的24项工具和2次模型结果仍是历史证据，不并入本轮。

2026-10-16 F-003角色联动验证：root报告22个前端文件/237项通过，生产build 299个模块通过（仍有大于500kB chunk提示），独立审查C/I/M=0/0/0。Edge加载真实本地16K模型完成7项检查；模拟native/headless再完成7项，包括3种手机UA/尺寸组合未创建模型资源、角色与控件重叠的原生命中、小圈动态碰撞、菜单暂停和resize切到手机卸载角色，无pageerror。后一组是模拟环境，不等于真手机验收；未测GPU峰值内存或长时FPS。模型POST为0，未部署；完整范围见[F-003交验](docs/implementation-reports/2026-10-16-f003.md)。

以下是各日期的历史验证，不合并为本轮测试数量；原报告中的服务状态只表示记录时点，不能当作现在仍在运行。

2026-10-11交互收尾：前端151项测试及build通过，原生Edge/RTX4050共15项桌面及模拟触摸检查通过，包含单指拖动、背景滚动、先落角色再加第二指的原生pinch、焦点位置及原39项菜单。既有开发账号完成3次真实B站解析；前两次截图尚在渐进加载，第三次等待complete/decode后确认约356×200px正常封面。解析预算因该具体缺口2→3并封账；账号/下载统计未变化，LLM调用0。见[本轮报告](docs/acceptance-reports/2026-10-11-ui-interaction-finish/report.md)。真手机未验证，后端1539项为上一轮记录，本轮未重跑。

> 验证范围（2026-10-15）：phase10冻结verify通过仅证结构/账本/原件一致；独立语义评分FAIL（core4/1/1，P2时间回退），详见phase10诊断。目标离线测试56 passed/98.05s、工具审查C/I/M均0。没有重跑生产/前端历史全量、启动服务或部署。该段为phase10历史记录；当前状态见[完整交接](docs/handoff-2026-10-16-deepseek-step1.md)。

2026-10-08前缀实验的历史记录：后端855通过/1既有warning、前端84通过/build成功；当时两phase共3POST/5869报告tokens，未形成final，14项未评，Playwright受限/超时未完整通过。见[当日报告](docs/acceptance-reports/2026-10-08-grounded-summary-prefix/report.md)与[当日交接](docs/handoff-2026-10-08-development.md)。其预算、失败原件及结果作为历史证据保留，不覆盖2026-10-09的自适应phase状态。下方234/73和旧浏览器/构建同样按历史保留。

开发期可在本机 `backend/dev-quota-policy.json` 配置 `{"unlimited_user_ids":["现有用户ID"]}`，或用 `DEV_QUOTA_POLICY_FILE` 指定位置。此前交接记录已对指定现有开发账号启用豁免；此次未读取私有policy、未重新验证账号状态。配置文件已gitignored，额度豁免不改变LLM调用预算。

历史已提交基线验证：后端234/234、前端73/73、生产构建通过。原文证据贯穿摘要合并、实验协议及响应式角色/触摸修复已提交 `be2bdd5`；公开Bilibili适配、inline兼容和yt-dlp回退保持。

本轮证据见[摘要协议与质量](docs/acceptance-reports/2026-10-04-schema-summary-quality/report.md)和[响应式角色](docs/acceptance-reports/2026-10-04-responsive-mascot/report.md)：19次预占、18次HTTP200、1次连接失败；默认三源5/5/7点，结尾事实恢复但12条完整/2条部分保留，长末点365字仍过度打包。实验协议上游仍违约，未切默认；不截断或自动重发。基础GPU布局41项、最终375px真实触摸5项各自通过；焦点几何修复通过但该专测有外部字体错误，未将其混为全浏览器成功。Windows视口和8K模拟不是手机/低GPU真机。

前轮[自然字幕质量](docs/acceptance-reports/2026-10-04-natural-subtitle-quality/report.md)和[公网移动/GPU](docs/acceptance-reports/2026-10-04-public-mobile-gpu/report.md)保留184/66、24次台账、5/6/7点及426字末点，公网保存854×480视频。MIT OCW语料及衍生评测按CC BY-NC-SA4.0非商业再用，与软件许可分开。

前轮[平台扩展](docs/acceptance-reports/2026-10-04-platform-expansion/report.md)、[浏览器闭环](docs/acceptance-reports/2026-10-04-browser-e2e/report.md)与[人工场景总结评测](docs/acceptance-reports/2026-10-04-summary-quality/report.md)保留：当时169/66，本机40项/6下载、公网桌面9项总结，以及独立12次模型台账。各轮范围不混算为全平台或全部质量成功。

此前[平台/TLS报告](docs/acceptance-reports/2026-10-03-platform-quality/report.md)和[AI修复报告](docs/acceptance-reports/2026-10-03-ai-summary-regression/report.md)按原采集时间保留，各轮结果不相互改写。

### 自动化测试（通用命令；长文验收状态见当前交接）

```bash
# 从仓库根目录开始；后端（pytest）
cd backend
uv run python -m pytest

# 在同一终端切换至前端（vitest）
cd ../frontend
npm test
```

### 手工冒烟（端到端主链路）

1. 按「快速启动」起后端与前端，先注册或登录。
2. 前端粘贴 `https://www.youtube.com/watch?v=dQw4w9WgXcQ`，点「解析」→ 应出现标题、时长与多档清晰度。
3. 选一档清晰度点「下载」：默认勾选“按视频标题命名”，走服务端任务，轮询到 `done` 后保存带原标题的文件；取消该选项后优先使用来源直链，失败时按已有逻辑尝试服务端。平台实际提供的格式和可下载性取决于来源，本示例不是平台可用性保证。
4. 后端接口示例（Bash；先用自己的现有账号登录，将响应token放入本地变量 `TOKEN`）：

```bash
curl -X POST http://127.0.0.1:8000/api/parse \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## 署名与授权

Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨。模型遵循作者使用规则：**非商用、不二传二改**（见 `frontend/README.md`）。
