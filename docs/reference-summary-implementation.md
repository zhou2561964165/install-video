# 参考项目分析与 AI 内容总结改进

## 工程约定

UI 改动先使用 `ui-ux-pro-max` + `design-system`，skill 优先于计划；样式走三层 token，能力通过数据和配置扩展；yt-dlp 仅在 `ytdlp_service.py` 调用，视觉层只读场景状态。

## 参考代码观察

参考项目：`C:/Users/zxk/free-video-downloader`，只读分析，没有修改它的文件。

- `backend/summarizer.py`：平台专用提取（Bilibili）与 yt-dlp 通用路径；手工/自动来源筛选；字幕转换为分段与全文；DeepSeek 总结、问答和思维导图。
- `backend/api_summarize.py`：内容提取在线程执行，AI 输出通过 SSE 事件返回。
- `frontend/src/components/VideoSummary.vue`：字幕分段显示、导出和 AI 结果呈现。
- 参考项目没有 Archive.org 适配，其 VTT 正则也要求三位毫秒。因此上轮两个失败不能靠直接复制参考代码解决。

没有找到独立许可证文件。本轮借鉴组织方式并独立实现，未复制参考源码或迁移其前端框架。

## 按用户目标落地

用户明确以 AI 总结内容为主，允许删除重复片段。当前实现聚焦内容获取与总结，不新增时间轴展示、字幕导出、会员支付或思维导图。

1. 总结层去除重复字幕行，长内容分段总结并分层合并；摘要和关键要点响应契约保持稳定，尾部内容参与总结。
2. 分段大小、数量、模型输出预算均可配置，避免固定截断前若干字符。超出整体容量时明确提示；翻译仍使用独立输入上限。
3. 公开平台适配器由唯一 yt-dlp 服务边界调用。Archive.org 从[官方公开元数据接口](https://archive.org/developers/md-read.html)发现字幕附件，AI 内容获取不依赖视频网页解析；不可用时回退通用提取。
4. 文件级链接按字幕内容名精确关联，区分 `movie` 和 `movie.part2`；多视频内容不静默混合。
5. 元数据类型校验后再读取字段，格式异常不会破坏正常回退；排除弹幕/聊天记录，SRT 支持1–3位小数。

## 验证与边界

2026-10-04增量：在既有注册式接口中独立加入Bilibili公开view/dm字幕适配；同时适配本机yt-dlp返回的inline SRT与AI语言标记，补充原生正文失败后的单次通用恢复。真实匿名正文1973字符与访问限制分开留证，见[平台扩展](acceptance-reports/2026-10-04-platform-expansion/report.md)。完整[浏览器验收](acceptance-reports/2026-10-04-browser-e2e/report.md)和[总结质量评测](acceptance-reports/2026-10-04-summary-quality/report.md)另列证据。实现 `e7c29be`，全量169/66与构建通过。

> 本节下列96/65及3/3数据是本报告对应的上一轮记录。后续101/66回归、三平台字幕样本以及有限TLS重试后的121/66复验，见[平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md)；TLS重试实现提交于 `96b0b59`。

- 后端96项、前端65项通过，生产构建通过。
- 原5份已许可字幕文件解析从4/5到5/5，源文件保持原样。
- 原3个 Internet Archive 视频 URL 的内容获取从0/3到3/3；这验证的是供AI总结使用的公开字幕链路，不代表所有平台或视频下载网页都稳定。
- 真实 DeepSeek 对长演讲测试：原正文71,658字符，清理后71,214字符，分4段归纳再合并；46.62秒返回中文摘要和7条要点。
- 审查发现的“相近文件名选错字幕”和“异常元数据阻断回退”均有失败到通过的回归测试。
- 旧平台验收报告保留为历史基线，修复后结果见 `docs/acceptance-reports/2026-10-03-ai-summary-regression/`。
