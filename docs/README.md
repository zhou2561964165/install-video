# 项目文档索引

> 更新：2026-10-04。平台扩展、浏览器闭环和总结质量增量已完成；实现提交 `e7c29be`，后端169项、前端66项测试及生产构建通过。当前状态见 [handoff.md](handoff.md)。

## 工程约定

UI先用 `ui-ux-pro-max` + `design-system`，skill优先于旧计划；样式走三层token、能力配置化；yt-dlp仅由 `ytdlp_service.py` 接触，视觉只读场景。以用户当前指令及根工程约定为准。

## 当前维护文档

| 文档 | 用途 |
| --- | --- |
| [handoff.md](handoff.md) | 当前状态、用户决策、子agent停用、启动、验证、边界与剩余事项 |
| [requirements.md](requirements.md) | v1→v3需求与AI内容总结主目标 |
| [design.md](design.md) | 当前架构、接口和配置边界；旧视觉章节已标历史 |
| [v3实现计划](superpowers/plans/2026-10-03-v3-video-intelligence.md) | 当前v3 API、分层和验证范围 |
| [扩展路线](superpowers/plans/2026-09-21-extension-plan.md) | v2/v3已实现状态及后续候选，不作为自动执行授权 |
| [参考实现分析](reference-summary-implementation.md) | 参考项目观察、独立实现选择与已测限制 |
| [本轮增量计划](superpowers/plans/2026-10-04-platform-browser-summary.md) | 用户已授权范围、文件分工与完成结果 |
| [真实平台扩展](acceptance-reports/2026-10-04-platform-expansion/report.md) | Bili匿名正文、inline/native回退、访问限制与确定性回归 |
| [完整浏览器验收](acceptance-reports/2026-10-04-browser-e2e/report.md) | 本机双视口40项/6保存文件，与独立公网Archive桌面9项 |
| [总结质量评测](acceptance-reports/2026-10-04-summary-quality/report.md) | 固定语料、真实模型12次before/after、prompt溯源与残余问题 |
| [平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md) | 此前三平台字幕请求、LLM总结、质量抽查、下载闭环与TLS限制 |
| [UI扩展指南](ui-extension-guide.md) | 当前token、主题、模型配置与v3面板边界 |
| [根README](../README.md) / [前端README](../frontend/README.md) | 安装、运行、配置、模型署名与客户端说明 |

## 证据阅读顺序

- [真实平台扩展](acceptance-reports/2026-10-04-platform-expansion/report.md) → [浏览器闭环](acceptance-reports/2026-10-04-browser-e2e/report.md) → [质量评测](acceptance-reports/2026-10-04-summary-quality/report.md)：本轮结果，169/66及构建通过；单条平台结果不推广为全站支持，模拟LLM页面结果不计模型准确率。
- [平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md)：较早121/66轮结果；保留首轮/限次重试及 TLS 修复后字幕复测。
- [修复后AI总结回归](acceptance-reports/2026-10-03-ai-summary-regression/report.md)：此前结果，后端96/96、前端65/65、Archive.org内容获取3/3、原件解析5/5及真实DeepSeek长文总结。
- [原始平台验收](acceptance-reports/2026-10-03-single-platform-subtitles/report.md)：修复前的0/3、4/5基线，原始文件和许可证据继续保留。

报告数字对应各自采集/测试时间，不相互覆盖；原验收的阻断项不能误当成修复后的状态。

最新平台探针中Commons两项403，仅作为访问限制；YouTube网页200不作为字幕成功。Bili公开正文成功和Archive桌面真实总结有独立证据。所有报告保留请求层级、来源与未覆盖范围。

## 历史参考

`handover-phase1.md`、2026-09-20/21前后端旧实现计划、2026-09-22电影感计划与霓虹规范、pidanai分析报告保留设计过程。它们的任务列表、测试数量和配色描述代表当时状态，接手先读当前交接。

本轮三个实现工作线及独立复审均已交付，沿用主agent模型与推理；旧两个完成会话的历史记录保留。测试服务已停止，主agent规则未修改。
