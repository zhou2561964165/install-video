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

## 修复与前端体验

- 修复 LLM 兼容响应中畸形 `finish_reason` 和非字符串 text block 直接抛 `TypeError` 的情况；现在按契约映射 `llm_invalid_response`。四种畸形字段用例在修复前失败，修复后通过；有效多文本块拼接也有覆盖。
- 下载验收请求改为 `force_server: true`，并检查返回 `mode=server` 与 `job_id`，确保实际走服务端下载分支。
- 当解析阶段返回空字幕语言列表时，视频智能面板仍显示字幕读取、翻译和总结操作，提供“自动选择”语言选项。动作依旧由用户显式触发；失败在面板说明，下载按钮不受影响。没有增加自动字幕请求。
- `ui-ux-pro-max` 的 error recovery / empty state 指引用于保留恢复操作与清晰提示；现有样式继续复用 `design-system` token，没有增加新视觉 token。

独立只读审查没有剩余 Critical / Important；三项原发现（上述两项 Important 与字幕空状态入口 Minor）均已解决。报告只覆盖字幕与总结 API；**不声称每个平台都通过了解析 → 浏览器面板 → 总结的端到端流程**。后续浏览器自动化交互受工具审批阻断，本轮不把 API 结果表述为完整浏览器 E2E。

## 运行状态与后续

验收后端8010、前端5178和本机媒体服务器8021均已停止。实现、报告和交接文档已提交到 `main`（`Complete v3 video intelligence and acceptance`）。根目录的用户 `AGENTS.md` 保持未跟踪；`.env`、隔离 SQLite 数据库、`.planning/` 和本机合成媒体是忽略的本地验收数据，未进入提交。

用户曾在关机前暂停；恢复后已完成复审并提交。后续若开启新工作，从 [`docs/handoff.md`](../../handoff.md) 和项目文档索引继续。
