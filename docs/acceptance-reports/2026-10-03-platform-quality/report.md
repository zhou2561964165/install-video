# 平台、下载与总结质量验收（2026-10-03）

工程约定：UI 先用 `ui-ux-pro-max` 与 `design-system`；skill 指引优先；token 和能力配置化；`ytdlp_service.py` 是唯一 yt-dlp 边界；insights 请求经 `api.js` / `useVideoInsights`，视觉状态不修改下载状态机。

## 范围和结果

本轮接续 v3 未提交工作，复查全量测试、真实字幕与 AI 总结 API，并验证下载路径和摘要中的代表性事实。所有网络请求使用隔离验收数据库与随机临时账号，AI 密钥保留在被 Git 忽略的本机 `.env`，报告不包含凭据或完整远程字幕正文。

| 验收项 | 结果 | 边界 |
| --- | --- | --- |
| 后端 / 前端 / 生产构建 | 101/101、66/66、通过 | Python 全量测试有现存 Starlette/httpx 弃用提示；Vitest 有既有 jsdom navigation 提示；构建有 bundle 大小提示 |
| 原5份已许可字幕文件离线解析 | 5/5；原件 SHA-256 均未变化 | 基于先前保存的获许可原件 |
| 新增字幕 API 样本首轮 | 8项中3项取得正文：Archive.org 长讲座、Wikimedia Commons 德语短片、YouTube 英文自动字幕 | 其余5项返回 `network`（TLS EOF/握手或读取超时），不据此认定无字幕或不支持 |
| 限次重试 | 对先前失败的5项逐项重试一次，0项成功 | 全部仍为 `network`；保留首轮及重试 JSON，失败没有覆盖原始结果 |
| 真实 DeepSeek 总结 API | 首轮3/3成功：Archive.org 短片、Archive.org 长讲座、Commons 英文短片 | 短片的字幕 API 首轮曾失败；summary 请求重新取内容后独立成功。不能把总结成功回填为此前字幕 API 成功 |
| 长内容尾部与代表性事实 | 71,658字符与先前已许可原件解析结果完全相同；去重后71,214字符、4段，72.67秒返回中文摘要和7要点 | 尾部太阳能监控示例也出现在要点中。人工抽查若干源事实，没有量化整体事实准确率；短片若干要点表达相近 |
| 下载 API 闭环 | 本机生成的3秒 H.264/AAC 视频经本机 HTTP → yt-dlp → 服务端 Job → 文件接口返回；ffprobe 验证3秒、320×240、H.264与AAC；45117字节与原始生成文件哈希相同 | 验证解析/服务端任务/文件交付和格式。公网 Samplelib 探针遇网络 TLS 错误，因此没有宣称公网样本下载通过 |
| 登录、鉴权、额度 | 5个未授权保护接口均401；AI请求前后下载额度一致；实际下载任务额度加1 | 独立数据库和随机测试账号 |

每项响应、耗时及样本定义见 [`results.json`](results.json)、[`results-initial.json`](results-initial.json)、[`results-retry.json`](results-retry.json)、[`samples.json`](samples.json)、[`quality.json`](quality.json)、[`download-local.json`](download-local.json) 与 [`download-smoke.json`](download-smoke.json)。样本许可依据及先前捕获的原件哈希见[初始已许可样本清单](../2026-10-03-single-platform-subtitles/manifest.json)。Commons 英文字幕内容可查[该视频的 en-GB TimedText](https://commons.wikimedia.org/wiki/TimedText:Die_Temperaturkurve_der_Erde_(ZDF,_Terra_X)_720p_HD_50FPS.webm.en-gb.srt)；原始视频页面标示 CC BY 4.0。

YouTube 条目是公开自动字幕读取探针；仅记录正文长度与哈希，没有对其调用 LLM、保存全文或据此确认授权许可。TED、Commons 长片与 Samplelib 只记录访问结果。

## TLS 有限重试复测（2026-10-04）

沿用平台适配优先、yt-dlp回退的提取结构，对 Archive 元数据、字幕正文 GET 与 yt-dlp 请求增加配置化有限重试。默认 `NETWORK_RETRIES=2` 表示每个启用重试的请求/yt-dlp重试环节可额外尝试两次；`NETWORK_RETRY_BACKOFF_SECONDS=0.5` 为初始等待，下一次指数递增。项目自有 httpx GET 重试仅处理超时/网络传输错误、远端EOF及502/503/504；4xx、无字幕、格式错误与 LLM POST不重试。yt-dlp路径使用其原生 `retries` / `extractor_retries` 分类与退避回调。

| 请求 | 修复前记录 | 修复后真实复测 |
| --- | --- | --- |
| Archive.org 已许可短片 `youtube-6k-kbg3_Drc` 英文字幕 | 字幕API 422 `network` | 200，400字符，4.47秒 |
| Wikimedia Commons 气温短片英文字幕 | 字幕API 422 `network` | 200，`en-GB`，480字符，4.75秒 |

结果见 [`retry-live.json`](retry-live.json)。这是修复后的端到端字幕请求复测；该记录未采集每个请求的尝试计数，因此不单独宣称这两次返回200都实际触发过重试。可确定重试行为的证据来自无公网的模拟故障回归：连接/读取超时、远端连接 EOF 与 502/503/504 重试成功；共享 httpx GET 层的4xx、无字幕/格式错误不重试；耗尽后原错误保留且错误响应流在重试前关闭。

本轮全量验证：后端121/121、前端66/66、生产构建通过。Vitest既有jsdom navigation提示、构建的bundle大小提示和Starlette/httpx弃用提示仍存在。

独立代码复审确认关键修复已覆盖：yt-dlp退避函数匹配真实 `n` 关键字；网关错误响应不做无界读取并在重试前关闭；配置拒绝负重试次数和负/非有限退避时间。复审未发现未处理的 Critical 或 Important。

## 修复与前端体验

- 修复 LLM 兼容响应中畸形 `finish_reason` 和非字符串 text block 直接抛 `TypeError` 的情况；现在按契约映射 `llm_invalid_response`。四种畸形字段用例在修复前失败，修复后通过；有效多文本块拼接也有覆盖。
- 下载验收请求改为 `force_server: true`，并检查返回 `mode=server` 与 `job_id`，确保实际走服务端下载分支。
- 当解析阶段返回空字幕语言列表时，视频智能面板仍显示字幕读取、翻译和总结操作，提供“自动选择”语言选项。动作依旧由用户显式触发；失败在面板说明，下载按钮不受影响。没有增加自动字幕请求。
- `ui-ux-pro-max` 的 error recovery / empty state 指引用于保留恢复操作与清晰提示；现有样式继续复用 `design-system` token，没有增加新视觉 token。

独立只读审查没有剩余 Critical / Important；三项原发现（上述两项 Important 与字幕空状态入口 Minor）均已解决。报告只覆盖字幕与总结 API；**不声称每个平台都通过了解析 → 浏览器面板 → 总结的端到端流程**。后续浏览器自动化交互受工具审批阻断，本轮不把 API 结果表述为完整浏览器 E2E。

## 运行状态与后续

验收后端8010、前端5178、本机媒体服务器8021与 TLS 复测后端8011均已停止。TLS重试实现已提交为 `96b0b59`，本报告及复测结果在其后的文档提交中一并收录。根目录的用户 `AGENTS.md` 保持未跟踪；`.env`、隔离 SQLite 数据库、`.planning/` 和本机合成媒体未进入提交。

用户曾在关机前暂停此前的 v3 工作；该部分和 TLS 重试后续现均已本地提交。所有验收服务已停止。后续工作从 [`docs/handoff.md`](../../handoff.md) 和项目文档索引继续。
