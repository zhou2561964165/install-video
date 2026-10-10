# 参考项目复核与成熟方案选择

日期：2026-10-10。参考目录 `C:/Users/zxk/free-video-downloader`。此次两 Agent 分别只读分析后端总结和前端状态，主 Agent 核对当前实现及官方资料；不运行项目、测试或模型，不读取凭据，不改参考源码或产品代码。旧真实验收仍26/26，未新增付费阶段。

> **用户后续明确要求：成熟方案可以使用，后续开发必须优先调研并采用适用方案，避免重复造轮子。** 本文“已有同类能力”用于识别可复用现状，不能作为跳过成熟方案选型的理由。后续先评估成熟组件接入，自研集中在业务适配及明确缺失的能力；长期规则见 [AGENTS.md §10](../AGENTS.md)。

> **后续实施更新：** 已采用现有Pydantic严格字段类型/schema与适配来源优先建议的要点→概览指导，旧结果状态已修复；见[实际整改与验证](acceptance-reports/2026-10-10-source-first-summary/report.md)。本文余下“建议/尚未实施”指本次分析当时，后续实际状态以新报告为准；新候选语义质量仍未实测。

工程约定：适用 skill 优先；UI设计先用 ui-ux-pro-max/design-system、primitive→semantic→component token；能力配置化、窄接口与单向依赖，yt-dlp仅由唯一服务边界接触，视觉只读scene；避免无关重构及重复已完成工作。

## 结论

**参考项目可以借鉴结果生命周期和内容组织，但它没有已证明解决遗漏、重复、限定与归因问题的总结机制。当前项目的长文覆盖及资源边界更完整。** 以下是静态代码事实，不是参考项目在线质量评分；也没有历史源码快照证明其近期发生了变化。

## 1. 它实际上怎么总结

流程：Bilibili专用/yt-dlp字幕提取 → 带时间的字幕片段和全文 → 全文前15,000字符 → 一次流式Markdown总结 → 额外生成思维导图 → SSE事件到前端。

| 项目 | 代码证据 | 可借鉴程度 |
| --- | --- | --- |
| 提示组织 | [summarizer.py:345](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:345)要求概述、逻辑大纲、知识要点、整体总结 | 可参考来源逻辑顺序；概述/整体总结也可能重复，不能证明内容正确 |
| 长文 | [summarizer.py:346](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:346)固定text[:15000]；segments是字幕时间片段 | 不采用；没有AI分段归纳/合并，尾部可能直接丢失 |
| 生成配置 | [summarizer.py:293](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:293)固定模型、temperature0.7、输出4096、stream=True | 固定值不构成质量方案；不要移植成不可配置默认 |
| 原文清理 | [summarizer.py:238](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:238)去标签及完全相同字幕块 | 当前已有去重，不重复实现；部分重叠字幕不因此解决 |
| 输出处理 | [summarizer.py:306](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:306)直接转发模型文本 | 没有独立模型输出规范化、频率/范围/归属检查或语义质量评分 |
| 附加调用 | [api_summarize.py:101](/C:/Users/zxk/free-video-downloader/backend/api_summarize.py:101)总结之后无条件另生成mindmap | 当前目标不需要，增加调用及失败耦合；不采用 |
| 错误终态 | [api_summarize.py:120](/C:/Users/zxk/free-video-downloader/backend/api_summarize.py:120)统一SSE error；mindmap失败可发生在summary已流出之后 | 不采用其终态语义；summary阶段成功和附加阶段失败应明确区分 |

没有应用层分类重试；[SDK构造器](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:287)未显式设置重试参数。两次顶层生成不能等同于严格两次真实HTTP POST。

字幕路径额外限制：语言排序实际为首选人工→首选自动→其他人工→其他自动（[170行](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:170)）；下载阶段重新运行yt-dlp并强制VTT，正则要求完整HH:MM:SS.mmm（[211行](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:211)）。没有文件可能返回空片段，而外层仍标has_subtitle=True（[59行](/C:/Users/zxk/free-video-downloader/backend/summarizer.py:59)）。它也没有为本轮公网MIT network失败提供特定解决方案。

## 2. 页面失败处理：有一个明确可借鉴点

参考项目在开始新总结时清空旧摘要：[VideoSummary.vue:649](/C:/Users/zxk/free-video-downloader/frontend/src/components/VideoSummary.vue:649)。当前 [useVideoInsights.js:32](/E:/install_video/frontend/src/hooks/useVideoInsights.js:32)开始/失败分支保留原状态，[VideoInsights.jsx:57](/E:/install_video/frontend/src/components/ui/VideoInsights.jsx:57)继续显示旧summary；与[本轮HTTP页面实测](acceptance-reports/2026-10-09-online-formal-flow/report.md)一致。

后续可在新总结开始时清空该结果，或明确把旧结果标为上一轮；这属于结果状态语义，分析本身不实施修改。参考流式请求若已收到部分文字再失败，仍可能保留部分本次内容，因此不能把它整体当作正确的失败展示方案。

当前已有AbortController和请求编号保护，参考fetch未传signal、卸载不取消流（[summarize.js:67](/C:/Users/zxk/free-video-downloader/frontend/src/api/summarize.js:67)、[组件767行](/C:/Users/zxk/free-video-downloader/frontend/src/components/VideoSummary.vue:767)），不应倒退移植。浏览器abort能中断fetch和响应体消费，但不证明上游已停止推理或计费；见 [MDN AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort)。

参考后端直接把str(e)送到UI，没有解决错误文本内的上游endpoint问题。它的实例单例也不是结果缓存；没有可直接借鉴的请求幂等、进行中请求去重或字幕结果缓存机制。

## 3. 对应的成熟方案

| 方案/资料 | 已核实能力 | 本项目适用范围 |
| --- | --- | --- |
| [LlamaIndex Response Modes](https://developers.llamaindex.ai/python/framework/module_guides/deploying/query_engine/response_modes/) | tree_summarize全片段递归归纳；refine依次更新答案；按token及上下文窗口打包、必要时重叠拆分 | 优先评估采用其response synthesizer与拆分组件，通过窄接口兼容当前字段和预算；复用已有输入/内容评测。递归压缩仍需内容评分 |
| [LangGraph Workflows](https://docs.langchain.com/oss/python/langgraph/workflows-agents) | 固定工作流、分步生成、条件门与生成后评估/优化模式 | 后续编排优先评估采用成熟节点、状态及恢复机制，保持有限调用与明确终态；采用后验证实际效果，不增加无限修订环 |
| [Anthropic长上下文建议](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) | 对长文先定位相关原文引句再完成任务，分隔文档与指令 | 可作为来源优先的候选生成策略。官方建议针对Claude；转用于当前模型是否有效须另验证，不当作跨模型保证 |
| [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) | 合法JSON、明确格式示例、合理max_tokens；官方也列出空content可能性 | 管格式，不证明必要信息覆盖、频率、归因与无重复；不能用JSON/schema通过替代原内容评审 |

以上官方资料于本日查询。LlamaIndex文档明确simple_summarize会截断并可能丢细节，故参考项目的首15,000字符路径不能当成长文成熟解法。没有安装、迁移或运行这些框架。

## 4. 后续优先级与避免重复

1. **明确的局部缺陷：**先处理新总结失败仍显示旧结果；复用现有取消/请求编号保护。此建议不需要模型调用。
2. **中篇总结候选：**先评估成熟summarizer/工作流可配置的生成与组织能力，通过适配保持当前API字段及有限调用。可比较“先完成具体主题要点，再生成高层概览”的生成顺序；这是顺序候选，不能宣称能解决重复。不要加入样本答案或删除必要条件来凑通过。
3. **复用已有内容准则：**每节课评价、评分理由、努力→技能归属等缺陷仍按原标准审查；没有新实测证明解决。中篇原文仅2,199字符并走单次生成，参考项目的截断或新分段框架不是针对该缺陷的修复证据。
4. **仅在长文边界实际出现风险时**研究按自然段/主题和token预算切块；当前全文覆盖、原文头尾证据、有限合并、自适应输出预算均已存在，不再开发一遍。

不建议直接复制参考源码、切换Vue、增加思维导图、将完整总结改成top-k片段检索、自动扩预算或恢复facts作为默认成功条件。参考项目先前未找到独立许可证，借鉴思想与独立实现即可，不推断复制授权。

以上为分析建议，尚未实施或模型验收。旧26/26组继续封账，新真实对照需要明确有限预算。零付费静态研究与文档维护不触发重跑旧20API/4页面/10guard、91项回归或旧phase。
