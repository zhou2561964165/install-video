# 长文来源保真整改设计

日期：2026-10-13。用户已要求解决长文，并明确本次不设预算；旧closed组及原证据不重开。

工程约定：Superpowers/适用skills优先；UI如涉及采用ui-ux-pro-max/design-system与三层token；成熟能力优先，配置化窄接口/单向依赖，yt-dlp唯一服务层/视觉只读scene。保护已有UI改动、账号/env、本地模型与历史证据。

## 问题与验收目标

最后完整长文14点/全部6核心主题/组织通过，但有时间起止、具体计算器范围、算术子集与评价模态失真。前三项局部生成问题之外，本次新定位发现全文seen去重删除原L1245的枚举片段（首次出现L662），确实损坏后文“前三种”的前件。四处原证据都不在最终merge首尾1200窗口，无法纠正错误叶笔记。

目标是保留必要来源上下文，生成来源忠实、完整且互补的概览和要点。按原core6与逐断言标准重新审阅，不继承旧评分、不将结构/schema/HTTP成功视为内容通过，不靠删点/放宽主题上限凑通过。

## 成熟方案与选择

复用现有Pydantic v2严格类型/无损JSON闭合、httpx传输与map-reduce；字幕层已经采用相邻重复折叠，摘要层复用相同语义。框架的tree_summarize/refine会帮助递归打包，却不会恢复预处理已删除的词句，也不会提供输入之外的原文。因此本轮修复业务输入策略和证据装配，不替换已有同类引擎或增加事实协议。

重新核对[LlamaIndex response modes](https://developers.llamaindex.ai/python/framework/module_guides/deploying/query_engine/response_modes/)与[官方长上下文建议](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)。采用原始文档优先、清楚分隔原文与生成笔记；`source_context`在每section的生成summary/points之前。官方Claude效果不是当前供应商保证，实际效果仍须复验。只修改通用生成职责，不给模型样本答案。

## 实施边界

1. `_summary_input`只规范空白并折叠连续相同字幕行；跨语境重复全部保留，与现有字幕解析一致。原字幕文件不改。
2. 多段内部leaf默认保持原文语言，避免提前翻译压缩；单段及最终合并仍按用户指定语言。`LLM_SUMMARY_NOTES_LANGUAGE=source|output`可显式兼容旧笔记语言。
3. `_summary_merge_contexts(results, source_parts)`在原文+笔记JSON能装入现有`llm_max_input_chars`时优先完整原文；装不下则继续有省略标记的有限boundary与既有多层合并。`LLM_SUMMARY_SOURCE_CONTEXT_MODE=auto|boundary`可配置，context chars=0仍禁用上下文。不会强行截原文或偷偷增加阶段。
4. 不改变默认legacy/adaptive/single、模型、thinking或输出上限；首候选沿用最后失败的显式16384/24576/enabled/14 profile，以隔离输入修复。真实内容通过后还须验证合理产品配置，才决定公开长文入口。
5. 当前公开20000字符保护先保留；内部支持范围并非全部已经验证。大于单次原文窗口的来源仍使用边界上下文，必须明确这一限制，不能把完整原文已用的一个样本扩大为所有长文。

## 验收与追踪

新独立uncapped组不设总POST/费用上限，所有尝试仍发前持久预占，root单caller/原共享锁串行、失败保留并停止该phase。具体phase冻结阶段路径与正常调用arity用于审计，不作总预算。禁止隐藏SDK重试、付费fallback和旧组重开。

离线先覆盖跨语境重复、源语言notes/最终语言、完整与有限context、容量和配置；新工具独立覆盖锁/预占/错误/来源与code drift/冻结codec/result-raw绑定。新phase freeze/check及独立审查后才真实调用。初次en-long完整新2leaf+merge，随后独立内容审阅；依据实际缺陷决定后续修复，短中及未见来源作为回归，不写针对样本的答案。

状态与实际结果：[任务记录](../../../.planning/2026-10-13-long-summary-fidelity/task_plan.md)。新报告独立于旧16POST/153697tokens及更早封账组。
