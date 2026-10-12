# 万能视频下载网站

> 新窗口先读[当前交接](docs/handoff-2026-10-10.md)。开发统一在 `E:\install_video`；分支`feature/summary-content-resume-20261011`。恢复总结验收及用户指定的[完整长文复验](docs/acceptance-reports/2026-10-12-summary-long-final-check/report.md)已完成，四phase16/16POST、153697tokens封账：短中通过，长文14点/6项核心覆盖通过但精度仍失败。默认/env未升级，本地Live2D保留，发布仍须过滤模型历史。

注册或登录后，粘贴任意平台视频链接 → 解析 → 选清晰度 → 下载到本地；有字幕的视频还可读取字幕、翻译并生成 AI 总结。依托 yt-dlp 覆盖数千站点，前端采用深色液态玻璃 + 樱花粉辉光主题（PIXI 舞台 + Live2D 白角色，含程序化待机动画），移动端可用。

## 工程约定（每次遵守）

> 以最新用户 `AGENTS.md` 和当前有效指令为准。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。
5. **成熟方案优先，避免重复造轮子**：开发前复用已有研究并查找成熟库、框架与官方方案，适用时优先实际采用；自研聚焦业务适配和确实缺失的能力，选型记录来源、版本及采用/不适用原因。详见 [AGENTS.md §10](AGENTS.md) 和 [成熟方案研究](docs/reference-summary-review-2026-10-10.md)。

## 架构

```
[前端 React/Vite + PIXI + Live2D]  ⇄ HTTP/JSON  ⇄  [FastAPI 后端]
                                                       │
                                          yt-dlp 服务层（线程池 + SQLite 任务状态）
```

- 后端：`backend/` — FastAPI + yt-dlp(Python API) + SQLModel/SQLite。JWT 登录后才能解析、发起下载及使用字幕/AI接口；直链下载与服务端下载自动切换。服务端产物记录 TTL，下次提交下载时清理已过期产物。
- 前端：`frontend/` — React 18 + Vite + PIXI v6 + pixi-live2d-display。单一 PIXI 管线，场景状态机驱动，WebGL 缺失/低端机自动降级。

2026-10-10三轮在线验收已完成并封账：来源优先5POST、阶段分离6POST、原生Schema/Pro对照6POST，累计17/17 POST、74355供应商tokens。第三轮三源结构均通过（短5/中6/长14点），但中篇频率/账户读取/概览重复和长文覆盖/安全范围仍失败；不提升候选为默认，不宣称总体质量解决。默认仍为legacy/adaptive/single。旧26/26工作组原件保持；没有部署。最新证据见[原生Schema/Pro实测](docs/acceptance-reports/2026-10-10-schema-pro-summary-live/report.md)。 从[文档索引](docs/README.md)及[当前交接](docs/handoff-2026-10-10.md)开始。

## 环境要求

开发验收预算持续自主授权；新组已按10→12→17有限调整并全部封账，失败与父账本不覆盖。预算不写入产品下载额度或LLM运行代码。

成熟方案已实际采用Pydantic严格类型/schema、langchain-core 1.6.9串行两角色编排与供应商原生Responses/json_schema对照；langsmith 0.14.7仅用于关闭追踪。候选正常短文2POST、多段n+2POST，默认single未增加成本。旧结果清空修复已完成。成熟方案提供结构及编排能力，内容忠实仍须独立验证。

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
uv run uvicorn app.main:app --reload --port 8000
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
| `LLM_MAX_INPUT_CHARS` | `60000` | legacy单次字幕/合并notes及翻译内容上限；facts按完整序列化请求计算容量 |
| `LLM_SUMMARY_CHUNK_CHARS` | `20000` | 总结分段大小；先清理重复内容，再分段归纳并合并 |
| `LLM_SUMMARY_MAX_CHUNKS` | `16` | 单次总结最多的原始分段数，限制一次请求的模型调用规模 |
| `LLM_SUMMARY_MAX_OUTPUT_TOKENS` | `4096` | 每次分段或合并总结的基础输出token预算；adaptive可随原字幕规模有限增长 |
| `LLM_SUMMARY_STRATEGY` | `legacy` | `legacy`使用字幕分段归纳/合并；`facts`显式事实实验；`auto`先做facts预检，符合条件才选facts |
| `LLM_SUMMARY_LENGTH_MODE` | `adaptive` | 字幕总结按原内容规模有限拓展，不设固定摘要/要点字数门槛；`fixed`保留旧实验合同 |
| `LLM_SUMMARY_OUTPUT_TOKEN_CEILING` | `max(8192,基础预算)` | 未设置时保留旧高基础预算；显式值须覆盖基础预算，可配置至65536 |
| `LLM_SUMMARY_POINT_CEILING` | `14` | 长文可用主题数量上限，配置7–32；短文使用更少，不要求填满 |
| `LLM_SUMMARY_RESPONSE_FORMAT` | `auto` | `auto` / `text` / `json_object` / `json_schema` / `strict_tool`；auto对DeepSeek使用JSON模式，对其他供应商不附加输出格式参数；后两项仅legacy显式实验 |
| `LLM_SUMMARY_THINKING_MODE` | `auto` | `auto` / `enabled` / `disabled`；auto仅DeepSeek摘要关闭推理，避免推理消耗正文预算；明确值由操作者确保供应商支持 |
| `LLM_SUMMARY_MAX_POINT_CHARS` | `240` | 仅fixed及事实合同实验使用；默认adaptive无单点固定字数硬拒，不裁切 |
| `LLM_SUMMARY_SOURCE_CONTEXT_CHARS` | `1200` | 每分段原文头尾各保留至多该字符数随notes合并；跨层保留，容量计算包含证据；`0`关闭 |
| `LLM_SUMMARY_FACTS_MAX_SOURCE_CHARS` | `40000` | facts去重后原字幕字符上限，整数1–1000000 |
| `LLM_SUMMARY_FACTS_CHUNK_CHARS` | `8000` | facts抽取分段字符上限，实际还受legacy分段及单次输入上限约束；整数1–1000000 |
| `LLM_SUMMARY_FACTS_MAX_PER_CHUNK` | `12` | facts每分段抽取事实上限，整数1–48 |
| `LLM_SUMMARY_FACTS_MAX_EVIDENCE_SENTENCES` | `128` | facts单条事实引用的证据句数量上限，整数1–256 |
| `LLM_SUMMARY_FACTS_MAX_SUMMARY_CHARS` | `800` | 显式facts实验的摘要总字符上限，整数1–4000；与默认adaptive字幕总结无关 |
| `LLM_SUMMARY_FACTS_COMPOSE_MAX_OUTPUT_TOKENS` | `0` | facts合成阶段独立输出预算；0沿用基础预算，允许0–65536 |
| `LLM_SUMMARY_FACTS_AUDIT_MAX_OUTPUT_TOKENS` | `0` | facts核查阶段独立输出预算；0沿用基础预算，允许0–65536 |
| `LLM_SUMMARY_FORMAT_RETRIES` | `1` | 每次facts总结共享的格式修复次数上限，只修复失败阶段；整数 `0–2`，`0`关闭 |
| `LLM_SUMMARY_SEMANTIC_RETRIES` | `1` | 事实总结核查发现内容、核心覆盖或引用未决时，最多追加的针对性修订次数；整数 `0–2` |
| `LLM_SUMMARY_MAX_EXTRA_CALLS` | `2` | 每次事实总结两类修复共享的附加模型调用上限；整数 `0–2`。网络、供应商、来源、容量和配置错误立即停止 |
| `LLM_SUMMARY_QUALITY_CONTRACT` | `compat` | 仅facts实验：`compat`保持原核查合同；`compact`使用有限主题和内嵌四项布尔核查，由程序转换、关联引用并严格验收 |

默认配置组合为 `LLM_SUMMARY_STRATEGY=legacy`、`LLM_SUMMARY_LENGTH_MODE=adaptive`。legacy先去除重复字幕行，再逐段归纳；多段以生成notes和原文边界证据分组、必要时多层合并。单段为1次POST，多段调用数取决于合并层数，不适用facts的 `n+2` 公式。adaptive在每超过8000个清理后源字符的档位增加1024输出tokens和2个可用要点，分别受输出token和主题上限约束；合并按对应源字幕字符总量计算。它保留有限点数和输入/输出容量校验，不以固定摘要或单点字数拒绝，不裁字删点。

legacy raw先经过独立`summary_json.py`再入Pydantic/既有预算校验。合法JSON保持旧兼容；只修可证明全部完成字符串及标点结构保留的终端闭合，使用已有Pydantic核心parser，不补默认值、不吞未完成点、不裁字删点，也不额外调用模型。单边Markdown围栏拒绝；strict仍禁围栏/保留严格schema，但也可接受经无损门证明的闭合修复。该格式层不证明来源忠实或内容质量。

显式 `facts` 保留事实抽取→合成→原文核查实验，仍有固定摘要/要点合同，未采用adaptive预算。`auto` 在付费前预检facts协议和容量，仅预检的 `llm_unconfigured` / `llm_input_too_large` 可选择legacy；非法策略、事实字段/重试/质量合同配置先拒绝。facts阶段一旦发出请求，不会因错误切换legacy或隐藏付费fallback。facts仅支持 `auto` / `text` / `json_object`，不支持 `json_schema` / `strict_tool`。

facts模型输出先经过独立规范化层，再由程序根据已验证事实关联引用；完整段落字符串可以直接规范化，不额外调用模型。规范化保留非空内容与原ID提示，不盲挂所有引用；引用匹配提供来源关联建议，最终仍执行原文来源、核心事实覆盖及逐项核查。职责分别位于 `summary_normalization.py`、`summary_references.py`、`summary_retry.py`，HTTP编排保留在 `llm_service.py`。正常调用为facts抽取分段数 `n+2`，默认最多1次格式修复及1次语义修订、共享2次附加调用，因此默认最坏 `n+4`；只重做失败阶段，所有attempt计入trace。网络、供应商、来源安全、容量和配置错误立即停止。legacy与翻译没有模型自动重发；`NETWORK_RETRIES`只控制启用它的字幕HTTP和yt-dlp请求，不控制模型POST。

默认路径（`TEMP_DIR` / `DB_URL`）已锚定到后端目录，与启动时的工作目录无关。

### v3 · DeepSeek 本地联调

此前验收记录使用 `deepseek-flash`；代码从 `LLM_MODEL` 读取模型ID，不绑定具体模型版本。供应商可用模型以其[模型列表](https://api-docs.deepseek.com/api/list-models/)为准。本地配置可放在被Git忽略的 `backend/.env`；此次文档核对未读取该文件，不将历史配置视为当前实测。

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000 --env-file .env
```

新环境需自行创建 `.env`，设置 `LLM_PROVIDER=deepseek`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash` 和 `LLM_API_KEY`。后续兼容供应商只需更改这些环境变量。

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
| `POST /api/download` | `url`、`format_id`、可选 `force_server=false` | 需登录；提交前预扣1次额度；返回直链 `url`/`headers` 或服务端 `job_id` |
| `GET /api/job/{job_id}` | 任务ID、Bearer token | 仅本人任务返回状态及进度；匿名/无效token为401，他人/无主/不存在任务统一404 |
| `GET /api/file/{job_id}` | 任务ID、Bearer token | 仅本人完成且文件仍存在的任务返回文件；匿名401，他人/无主/不存在或本人未完成/文件缺失为404 |
| `POST /api/subtitle` | `url`、可选 `language` | 需登录；返回正文、实际语言、是否自动字幕及可选语言 |
| `POST /api/subtitle/translate` | `url`、可选 `source_language`、`target_language=zh-CN` | 需登录；读取字幕并调用LLM翻译 |
| `POST /api/summary` | `url`、可选 `subtitle_language`、`output_language=zh-CN` | 需登录；读取字幕并返回 `summary`、`key_points`、供应商与模型标签 |

下载直链与服务端模式都计入UTC当日额度，下载失败也不自动退回；字幕读取、翻译和总结不扣这项下载额度，但都受API限流约束。指定用户豁免时 `unlimited=true`、`limit=null`、`remaining=null`，`used`仍累加。豁免按明确用户ID匹配，文件只允许 `unlimited_user_ids` 字段、唯一非空ID，不支持通配符；移除ID或无效文件后恢复原有限额度。

常见错误采用HTTP `detail` 对象承载 `error`，服务错误通常还含 `error_type`：缺失/失效登录token为401 `login_required`；下载额度或IP限流为429 `quota`；无效视频URL为400 `invalid_url`；平台提取及字幕读取失败为422；LLM未配置为503 `llm_unconfigured`，模型请求、响应及输入容量等错误为502。Pydantic请求字段校验也可能返回422，但其 `detail` 是字段错误列表。异步下载失败记录在任务响应的 `error_type` / `error`，不是创建任务接口同步报错。

已实现账号登录、每日下载额度、本人任务/文件访问隔离、服务端线程池任务、产物懒清理、字幕读取/翻译、有限字幕分段总结，以及显式facts实验。前端服务端文件携Bearer获取Blob后保存，取消/退出/换账号阻止过期保存；Blob缓存完整文件，仍有大文件内存边界。当前未实现定时TTL清理、下载失败额度退回、分布式限流/队列或重启后自动恢复下载任务；视频无字幕时也没有音轨转写路径。总结的已知质量缺陷见当前交接。

## 验证

2026-10-11交互收尾：前端151项测试及build通过，原生Edge/RTX4050共15项桌面及模拟触摸检查通过，包含单指拖动、背景滚动、先落角色再加第二指的原生pinch、焦点位置及原39项菜单。既有开发账号完成3次真实B站解析；前两次截图尚在渐进加载，第三次等待complete/decode后确认约356×200px正常封面。解析预算因该具体缺口2→3并封账；账号/下载统计未变化，LLM调用0。见[本轮报告](docs/acceptance-reports/2026-10-11-ui-interaction-finish/report.md)。真手机未验证，后端1539项为上一轮记录，本轮未重跑。

> 文档实现核对（2026-10-09）：本次仅读取代码并更新说明，未重跑测试、启动服务或追加模型调用。最新状态与续作入口见上方当前交接段及[文档索引](docs/README.md)；后端1342 passed/1既有警告为历史全量记录，当前自适应验收仍有短篇重复、中篇必要子句遗漏及重复。

2026-10-08前缀实验的历史记录：后端855通过/1既有warning、前端84通过/build成功；当时两phase共3POST/5869报告tokens，未形成final，14项未评，Playwright受限/超时未完整通过。见[当日报告](docs/acceptance-reports/2026-10-08-grounded-summary-prefix/report.md)与[当日交接](docs/handoff-2026-10-08-development.md)。其预算、失败原件及结果作为历史证据保留，不覆盖2026-10-09的自适应phase状态。下方234/73和旧浏览器/构建同样按历史保留。

开发期可在本机 `backend/dev-quota-policy.json` 配置 `{"unlimited_user_ids":["现有用户ID"]}`，或用 `DEV_QUOTA_POLICY_FILE` 指定位置。此前交接记录已对指定现有开发账号启用豁免；此次未读取私有policy、未重新验证账号状态。配置文件已gitignored，额度豁免不改变LLM调用预算。

历史已提交基线验证：后端234/234、前端73/73、生产构建通过。原文证据贯穿摘要合并、实验协议及响应式角色/触摸修复已提交 `be2bdd5`；公开Bilibili适配、inline兼容和yt-dlp回退保持。

本轮证据见[摘要协议与质量](docs/acceptance-reports/2026-10-04-schema-summary-quality/report.md)和[响应式角色](docs/acceptance-reports/2026-10-04-responsive-mascot/report.md)：19次预占、18次HTTP200、1次连接失败；默认三源5/5/7点，结尾事实恢复但12条完整/2条部分保留，长末点365字仍过度打包。实验协议上游仍违约，未切默认；不截断或自动重发。基础GPU布局41项、最终375px真实触摸5项各自通过；焦点几何修复通过但该专测有外部字体错误，未将其混为全浏览器成功。Windows视口和8K模拟不是手机/低GPU真机。

前轮[自然字幕质量](docs/acceptance-reports/2026-10-04-natural-subtitle-quality/report.md)和[公网移动/GPU](docs/acceptance-reports/2026-10-04-public-mobile-gpu/report.md)保留184/66、24次台账、5/6/7点及426字末点，公网保存854×480视频。MIT OCW语料及衍生评测按CC BY-NC-SA4.0非商业再用，与软件许可分开。

前轮[平台扩展](docs/acceptance-reports/2026-10-04-platform-expansion/report.md)、[浏览器闭环](docs/acceptance-reports/2026-10-04-browser-e2e/report.md)与[人工场景总结评测](docs/acceptance-reports/2026-10-04-summary-quality/report.md)保留：当时169/66，本机40项/6下载、公网桌面9项总结，以及独立12次模型台账。各轮范围不混算为全平台或全部质量成功。

此前[平台/TLS报告](docs/acceptance-reports/2026-10-03-platform-quality/report.md)和[AI修复报告](docs/acceptance-reports/2026-10-03-ai-summary-regression/report.md)按原采集时间保留，各轮结果不相互改写。

### 自动化测试（按需执行，以下命令不是本次运行结果）

```bash
# 后端（pytest）
cd backend
uv run python -m pytest

# 前端（vitest）
cd frontend
npm test
```

### 手工冒烟（端到端主链路）

1. 按「快速启动」起后端与前端，先注册或登录。
2. 前端粘贴 `https://www.youtube.com/watch?v=dQw4w9WgXcQ`，点「解析」→ 应出现标题、时长与多档清晰度。
3. 选一档清晰度点「下载」：
   - 直链可用 → 浏览器直接保存；
   - 否则落到服务端下载（轮询进度到 `done`）→ 点「保存文件」。
4. 后端接口示例（Bash；先用自己的现有账号登录，将响应token放入本地变量 `TOKEN`）：

```bash
curl -X POST http://127.0.0.1:8000/api/parse \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## 署名与授权

Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨。模型遵循作者使用规则：**非商用、不二传二改**（见 `frontend/README.md`）。
