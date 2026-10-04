# v3 视频智能 · 实现计划

> 日期：2026-10-03
> 状态：MVP 已完成
> 基线：v2 强制登录 + 每用户下载额度

> 用户已确认：AI内容总结为主，重复内容可以清理，长内容分段归纳再合并；首页保留登录后。当前状态、子agent停用与测试范围见 [交接](../../handoff.md)。

## 工程约定（每次遵守）

1. UI/视觉/交互先调用 `ui-ux-pro-max` + `design-system`，skill 指引优先于本计划。
2. 颜色、字体、时长走三层 token；新能力数据驱动、可配置。
3. `ytdlp_service.py` 是唯一接触 yt-dlp 的层；LLM 只由 `llm_service.py` 接触。
4. 前端 insights 层不修改下载 reducer；通过 `api.js` 和独立 hook 通信。

## MVP 范围

- 登录用户读取手工字幕或自动字幕正文。
- 将选定字幕翻译为目标语言。
- 基于字幕生成摘要与关键要点。
- LLM 通过 OpenAI-compatible HTTP 接口调用，base URL、model、key、超时和最大输入长度均由环境变量配置。
- 未配置 LLM 时字幕读取仍可用，翻译/总结返回明确配置错误。

## API 契约

| 接口 | 请求 | 响应 |
| --- | --- | --- |
| `POST /api/subtitle` | `url`, `language?` | 标题、语言、是否自动字幕、可用语言、正文 |
| `POST /api/subtitle/translate` | `url`, `source_language?`, `target_language` | 源/目标语言、译文、provider/model |
| `POST /api/summary` | `url`, `subtitle_language?`, `output_language` | 标题、字幕语言、摘要、关键要点、provider/model |

## 分层

```text
routes/summary.py ─┐
                   ├─ subtitle_service.py ── ytdlp_service.py（轨道元数据）
routes/subtitle.py ┘          │
                              └─ httpx（字幕正文）

routes ── llm_service.py ── OpenAI-compatible endpoint

App ── useVideoInsights ── api.js
  └─ SelectingScene ── VideoInsights（纯 props）
```

## 验收

- 无 token 的三个 v3 接口返回 `401 login_required`。
- 有手工字幕时优先手工字幕，无手工字幕时可回退自动字幕。
- VTT/SRT/JSON3/TTML 正确去时间轴、标签与重复行。
- 未配置 LLM 返回 `llm_unconfigured`，页面给出就地提示且下载仍可继续。
- 前后端全量测试、生产构建和浏览器主链路通过。

## 实际验证与限制

- 后端 96/96，前端 65/65，生产构建与 diff check 通过。
- 后续交接前回归：后端101/101、前端66/66、生产构建通过；追加provider畸形响应错误分类与解析空字幕列表下的显式总结前端集成回归，详见[平台与总结质量报告](../../acceptance-reports/2026-10-03-platform-quality/report.md)。
- 本地模拟外部轨道元数据与 LLM 服务的浏览器联调已验证真实应用 API、HTTP 字幕正文获取、正文解析和三种结果展示；未配置 LLM 的错误在面板就地展示，下载仍可操作。
- samplelib 无字幕视频的真实网络降级已验证。用户指定的 DeepSeek-V4.1-Flash 已完成真实服务调用与浏览器样例验收，API ID 为 `deepseek-flash`；更多平台字幕与长视频样本待扩大验收。
- 根据用户纠正，总结以内容理解为主：去除重复行后分段归纳并合并，不因超过单段输入上限而直接拒绝。翻译仍保留输入上限；总结分段数和输出预算均可配置。
- 参考项目的“平台专用提取 + 通用回退”已独立实现于 Archive.org 内容适配，原3个URL内容获取3/3成功、原5份文件解析5/5成功。约7.2万字符真实演讲已通过 DeepSeek 4段归纳后合并为中文摘要和7条要点，46.62秒。
- 独立代码审查发现的聊天轨道、请求头丢失、输出截断和缓冲式大小检查问题均已修复并复审。
- 后续参考适配审查的相近文件名选错字幕、元数据类型异常已通过失败→修复→通过的回归验证。
- 跨平台补验分别记录字幕API和总结API：YouTube、Archive.org、Wikimedia Commons均获得真实字幕成功样本；首轮8项字幕请求通过3项、真实总结3/3；公网请求发生间歇TLS/超时，限次重试5项均因网络失败，不代表站点不支持。详见平台与总结质量报告。
- 约7.2万字符演讲的本轮真实总结用时72.67秒，四段归纳后保留摘要与7要点；尾部家用太阳能指标案例仍出现在总结。只核查代表性事实，完整语义准确率没有量化。工作区另经本机生成媒体验证yt-dlp解析、服务端Job、文件响应与H.264/AAC播放属性。
- 本轮只读审查的两项Important与一项Minor均已修复；浏览器自动化后续交互受工具审批限制，报告不声称本轮完整浏览器E2E通过。v3实现、测试与报告已提交到 `main`；最终状态见交接文档。
- 2026-10-04 TLS follow-up：HTTP字幕元数据/正文GET和yt-dlp读取加入配置化有限重试（提交 `96b0b59`），平台专用适配优先与通用回退不变；全量后端121/121、前端66/66、build通过。之前失败的Archive短字幕与Commons英文字幕真实复测2/2返回正文，见[平台与总结质量报告](../../acceptance-reports/2026-10-03-platform-quality/report.md)。
