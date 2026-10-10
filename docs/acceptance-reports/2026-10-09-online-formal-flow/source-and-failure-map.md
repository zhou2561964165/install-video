# 正式在线流程：来源与失败映射

2026-10-09。本记录只完成来源核对、最多 3 次公开产品来源探针，以及已有离线失败的分层映射。未启动 app.main、读取 .env、访问数据库、注册账号、调用 LLM 或执行历史 evaluator/freeze/run。旧工作组已耗尽 26 POST；本记录不分配新模型预算。新收费验收必须使用另外明确授权的有限预算及独立台账，不能重开旧阶段。

工程约定：适用 skill 优先；UI 工作须先使用 ui-ux-pro-max 和 design-system，采用 primitive→semantic→component 三层 token；颜色、字体、时长走 token。保持可配置窄接口、单向依赖、最小充分改动；yt-dlp 仅由 ytdlp_service 接触，LLM 仅由 llm_service 接触，视觉层只读 scene。保护用户未提交工作、env/db/账号、全部历史证据及原始来源。本任务只新增本文件，没有修改产品或原始字幕。MIT OCW 来源及派生材料保留原 manifest 的作者归属与 CC BY-NC-SA 4.0 条款。

## 1. 原始 VTT → 当前产品 parser → 总结输入

实际用项目 `.venv/Scripts/python.exe -B -` 执行内存核对：导入当前 `subtitle_service`、`llm_service`，以进程内临时 `app.config` 模块提供公开探针所需的非敏感常量，避免导入真实 config/settings、读取环境配置或启动应用。调用的是产品原函数 `parse_subtitle_text(raw, "vtt")` 和 `_summary_input(text)`，未替换解析或归一化函数。此项不是正式 API/认证/UI 验收。

三份 raw VTT 和 TXT 的原字节 SHA-256 均匹配原 [manifest](../2026-10-04-natural-subtitle-quality/corpus/manifest.json)。三份 VTT 解析出的字符串均与既有 TXT **逐字符完全一致**；两条入口再经 `_summary_input` 后也完全一致。

| 样本 | 原 VTT 字节 | TXT 字节 / 字符 | parser 字符 | summary_input 字符 / 行 | 相等性 |
| --- | ---: | ---: | ---: | ---: | --- |
| zh-short | 2238 | 1704 / 608 | 608 | 608 / 21 | parser=TXT；两条归一化路径一致 |
| en-medium | 3849 | 2199 / 2199 | 2199 | 2199 / 95 | parser=TXT；两条归一化路径一致 |
| en-long | 62402 | 34894 / 34894 | 34894 | 34658 / 1494 | parser=TXT；两条归一化路径一致 |

长文的 236 字符差异来自现有 `_summary_input` 对规范化后完整字幕行的全局精确去重；VTT parser 只消除相邻精确重复行。没有改写原始 TXT/VTT，也没有截断、纠词或增加内容。后续模型 payload 应核对 **34658 字符的归一化输入**，不能要求它仍等于原始 34894 字符 TXT。

| 样本 | 原 VTT SHA-256 | TXT SHA-256（亦为 parser UTF-8 SHA-256） | summary_input UTF-8 SHA-256 |
| --- | --- | --- | --- |
| zh-short | `27c9f20e7174f5a4c24175da802069d53184ec5f7469f2515ef5a1f4426206f8` | `4e62d9c0f1d25734be1af8dfa7f1328c5f1982590734ca8453b0c2f926e0ae9b` | `4e62d9c0f1d25734be1af8dfa7f1328c5f1982590734ca8453b0c2f926e0ae9b` |
| en-medium | `cbd05069baa999d80750c6e18786a7dd10d47dd2eb45fac623e355089a7c97c5` | `4b1b09addb5ad3cab6dc885fb4f0a805fede65b2eecc8976b232e180a427edb9` | `4b1b09addb5ad3cab6dc885fb4f0a805fede65b2eecc8976b232e180a427edb9` |
| en-long | `404eb34eff454f97932952f677ce4bec0457488616dc5548ed8be81f70210a9f` | `c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7` | `3faeca5fe447959fce73ff9491413a52916b5f628cf00e2cd88c8bbad9f6cbd4` |

核对时产品源码 SHA-256：

- `backend/app/services/subtitle_service.py`: `9b18dfadbb3a356322ff633026f18692cfa71761e47235c70a90762eb1dcc571`
- `backend/app/services/llm_service.py`: `9cd3176f62e42839cca47bda1e263b79a4c18565ebb5167ffa9a8164ec125664`
- `backend/app/services/ytdlp_service.py`: `fd7f7ddba51e1118d1db4662b5dd22656b160fad42946ffab35daa81ef3eb08b`
- `backend/app/services/subtitle_sources.py`: `6416ed93734b42c6a0f3fcdfa0d45ec04be6b356033cd076be2af192b48571c8`

## 2. 公开视频页产品来源探针

当前 `subtitle_sources._ADAPTERS` 只注册 Archive.org 和 Bilibili，未注册 MIT OCW。`ytdlp_service.extract_subtitle_tracks` 对这些 OCW 页先得到空 public-adapter tracks，再调用其唯一 yt-dlp 层的通用提取。因此不应把这三页称为已有 OCW 原生适配器支持。

实际串行执行了 **3 次** `subtitle_service.fetch_subtitle_document(manifest.page, manifest.language)`，一次一个样本。未读取 .env、Cookie、账号、数据库或模型配置。为保证探针有限，进程内仅将网络重试设为 0，并给 `YoutubeDL` 初始化选项添加 8 秒 socket timeout、关闭 retry、静默 logger；未替换来源 URL、提取函数、字幕选择或解析逻辑。没有额外直连 caption 或浏览器探针。stdout 只输出以下非敏感统计，没有输出内部媒体地址、签名 URL、异常全文或凭据。

| 样本与原始公开页 | 实际结果 | 产品错误分类 | 用时 |
| --- | --- | --- | ---: |
| [zh-short](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/mit21g_101f14_immersive_environment_chinese-2/) | `DownloadError` | `network` | 1.80 秒 |
| [en-medium](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/daily-grading-system/) | `DownloadError` | `network` | 0.92 秒 |
| [en-long](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-1-what-is-computation/) | `DownloadError` | `network` | 0.86 秒 |

这只说明当前环境与本次有限探针未完成公开页字幕提取；不能推断 OCW 字幕不存在、永久不可用、视频不支持，或定位具体 TLS/代理/远端故障。未保留异常全文，因而不声称已查明网络根因。

代码映射：`routes/insight_common.py:17` 会将这种 yt-dlp 异常转为 HTTP 422、`error_type=network`；`/api/subtitle` 和 `/api/summary` 都先经过该入口。**此处 HTTP 状态是代码推断，本任务没有启动正式 API 进行实测。** 来源失败在 `summarize_text` 之前发生，应为 0 模型 POST；后续正式 HTTP 验收仍须实际核对 caller 台账。

### loopback 原始 VTT 的范围

loopback 可以公开服务上述原始 VTT，验证真实 HTTP 获取、产品字幕解析、归一化及后续 API/UI/LLM 路径；它不能证明外网 OCW 页、YouTube 或原生字幕提取成功。

`/api/summary` 接受视频 `url`，并非任意 VTT 文件上传或原文输入接口。直接把 `.vtt` URL 传给产品，不等于已经实现字幕导入。可选择真正能被当前 yt-dlp 提取字幕轨道的 loopback HTML5 视频页；须先核验实际返回的语言/track，不能仅依 HTML 标签断言成功。如果 harness 在 `ytdlp_service.extract_subtitle_tracks` 窄接口提供固定 loopback track 元数据，再让真实 `subtitle_service` HTTP 获取 VTT，应明确标为 **来源元数据测试接口**：HTTP/解析链路是真实的，视频元数据提取被替代。不要替换 `fetch_subtitle_document`、`summarize_text` 或最终 API 结果后宣称完整产品链路。

## 3. 已有离线失败属于哪一层

记录来源是不可改写的 [repair offline-validation](../2026-10-09-adaptive-summary-repair/scripts/offline-validation.json)、[final offline-validation](../2026-10-09-adaptive-summary-final/scripts/offline-validation.json) 和相应测试源码。repair 记录有初始 3 个 red、KeyboardInterrupt 1 个 red、审查修复 2 个 red；final 记录有 7 个新阶段 red。它们的修复结论限于验收工具，不能变成产品 API 能力说明。

| 已实际观察的 red | 层级 | 可复用验证方式 | 不能宣称 |
| --- | --- | --- | --- |
| durable tracker reservation 写入失败后 ledger 留在 reserved | 验收工具预算/持久化 | 独立新 harness 的 ledger/transport 保护；发前预占失败不能触发供应商调用 | 产品 API 已实现模型预算账本或相同故障恢复 |
| transport 期间 model 被修改，raw 与 result 模型失配 | 验收工具运行时冻结 | 新 caller 的 runtime/model/endpoint drift 防护及证据比对 | 产品自带运行时冻结、防人为改配置或最终来源语义审计 |
| index 将全部成功结果伪标为停止失败 | 验收工具证据一致性 | 新索引/台账 verifier 的矛盾状态负例 | 产品 HTTP/业务结果校验能力 |
| KeyboardInterrupt 后 attempt 留在 reserved | 验收工具中断闭环 | caller 层中断持久化、关闭阶段、禁重开 | 中断供应商之后可保证产品 API 的跨进程恢复 |
| HTTP Client 构造失败后 phase 留在 running | 验收工具初始化/收尾 | 新 harness 的 0 POST 初始化失败收尾 | 产品服务的 Client 构造异常已被相同修复覆盖 |
| 成功 samples 没有 request，而 tracker/index 同步伪造计数 | 验收工具证据绑定 | 成功结果→唯一 request/hash→raw 的反向校验 | 产品结果自带请求原件证明 |
| final plan 仍为旧 phase；预占仍为 23/24；第三请求边界仍用旧偏移 | 验收工具阶段身份/预算 | 新阶段身份、有限预算、第三请求发前拒绝 | 产品默认账号/下载额度、LLM 功能或 API 错误处理 |
| prior repair tracker 被打开或指向另一个 ledger | 验收工具历史身份 | 新阶段分配前只读核验历史 closed/identity/path | 产品业务接口的账号权限或资源鉴权 |
| prior snapshot 被篡改或旧 runner bytes 被改变 | 验收工具 freeze/历史完整性 | 新 freeze/verifier 的快照 hash 与代码 hash | 产品字幕来源安全已由这些测试证明 |

### 产品 API 可以在线观察，但并非上述真实 red 的产品修复

repair 测试中 `network/non_json/http/invalid_summary` 是 **故障注入的保护测试**；保存记录未将这四项列为实际失败后修复的 red。它们调用了测试 `Service` 和 transport，没有跑正式 API、字幕提取或 UI。可以在另外的新在线 harness 中使用受控 loopback provider 响应，保留真正 `llm_service` 的请求、完成状态和 JSON 解析路径，再通过真实 HTTP API 观察以下产品结果；不要直接返回伪造 `LLMSummaryResult`。

| 可测条件 | 当前产品代码对应 | 新在线验收需要的边界 |
| --- | --- | --- |
| 字幕网络/提取失败、无字幕/语言不可用、空坏字幕、字幕超大 | `insight_common.load_subtitle`: 422；非法 URL 为 400；模型尚未开始 | 实际 subtitle HTTP/metadata seam；核对 0 paid POST，不只看页面 toast |
| LLM HTTP 503/连接失败/外层非 JSON | `_complete` 捕获 HTTPError/ValueError 为 `llm_error`；summary route 为 502 | loopback provider 真正 HTTP 故障响应；无付费 fallback/retry；不使用真实供应商制造故障 |
| 模型 content 非总结 JSON、空/错误字段、超过有限 point budget | `_parse_summary_json` 等为 `llm_invalid_response`；summary route 为 502 | 固定错误 raw response，真实产品 parser/API；每次受控本地 POST 单独记为 local，不计入供应商 paid POST |
| finish_reason=length/content_filter 或不完整结构化完成状态 | 服务层 `llm_incomplete_response`；summary route 为 502 | 可复用已有服务测试的 envelope 构造，但须真的经过 HTTP/service/API |
| 未配置 LLM | `llm_unconfigured`；summary route 为 503 | 独立 test session 配置；不改用户 .env；先确保字幕阶段成功 |
| 摘要/要点详细重复、遗漏每节评价、量词/提问条件放宽 | 模型内容质量；有效 JSON 通常仍返回 HTTP 200 | 原 rubric 逐断言来源复核；HTTP 200/JSON 成功不能代替语义通过，也不能借改评分把失败变通过 |

API 状态以上均来自代码阅读，不是本任务已执行的 HTTP 结果。UI 是否展示准确提示、恢复控件或错误状态须由 root 的实际浏览器验收另行记录。即使同样叫 Client 初始化失败，针对 product 的另一次注入必须独立记实际行为；不能用 evaluator 的已修复 red 推断 product 的异常类型或 HTTP 状态。

## 4. 原 harness 可复用的位置与限制

- 可复用旧 evaluator 的 `digest`、`exclusive`、`durable`、共享 `directory_guard`、raw/result/hash 绑定、发前持久预占和失败停止设计；引用时保留旧脚本原字节，新的 phase/group/ledger/freeze 配置放到新文件。旧 26 组不复位、不改上限、不重开，不以替换全局常量来启动旧 runner。
- repair/final evaluator 的 `run` 直接对 TXT 调 `summarize_text`，没有正式登录、视频 URL、字幕 HTTP 获取、API server 或 UI。它的成功记录不能充当正式在线流程结果。
- 已有 `backend/tests/test_insight_routes.py` 可参考 request/response/error 形状；它使用 `TestClient`、直接 stub subtitle/summary，并注册随机新账号。**不要直接运行它代替新正式验收**：本轮沿既有 manual 账号，不注册新账号；需真实 HTTP API、真正字幕/service 路径和浏览器状态证据。
- 字幕 parser/格式/语言/大小测试可参考 `test_subtitle_service.py`；provider envelope 与解析边界可参考已有 LLM 服务测试。但只移植有必要的受控故障数据，不能重跑旧验收原件、把 mock 成功称为真实供应商语义成功，或把验收工具 tamper 测试塞入产品界面宣称产品能力。
- 新 session 可将受控 loopback 故障与 real-provider paid 正常案例分开台账。`local HTTP`、`供应商 paid POST`、`供应商 tokens` 应独立标记；任何真实供应商尝试，包括失败，都计入新明确授权的 cap。此文档不执行、不默认分配这些调用。

## 5. 本任务的结论和未验证范围

已验证：三份原 VTT/TXT hash、产品 parser 与既有 TXT 的完全一致性、当前总结归一化路径一致性；3 个公开产品来源探针均失败；已有 red 的工具层归属与产品 API 可观察错误边界已明确。

未验证：正式 HTTP API、既有账号登录、UI、loopback HTML5 track 提取、loopback VTT HTTP 获取、真实供应商新调用及本轮语义质量。没有重新运行后端全量/旧模型验收/旧 evaluator。公开来源探针的网络分类不能取代网络根因定位。下一步由 root 在独立 session 和明确模型 cap 下执行，保留外网来源失败与 loopback 链路成功/失败各自的范围。
