# 来源优先总结与结果状态整改

用户已要求现在采用有帮助的成熟方案解决现有问题，并同步设计。此次为现有LLM及前端请求链路的局部整改，公开接口和技术栈保持。

工程约定：适用skill优先；UI使用ui-ux-pro-max/design-system与三层token；数据驱动、窄接口、单向依赖；yt-dlp唯一服务边界，视觉只读scene。复用既有研究与已完成验证，不修改原验收证据。

## 问题与成熟方案选型

- 中篇单块输出遗漏频率、摘要/要点重复及归因弱，框架换分段不能直接解决；LlamaIndex TreeSummarize单块仍一次生成，Refine的默认错误处理/调用模式需额外适配。此时增加大型依赖没有已证实收益，记录此具体不采用理由。
- 借鉴并适配 [Anthropic来源优先建议](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)：生成前从原文定位中心内容及其条件/归因，先完成详细要点，再写高层概览；在同一次生成中完成，不输出新facts合同/引句协议，也不声称完整实现独立引句提取。
- 实际采用已有Pydantic v2的严格类型校验及JSON Schema生成，取代summary/key_points的手写结构检查/手写schema。Pydantic负责格式，内容是否忠实仍单独评审。
- 参考UI及既有AbortController请求生命周期：新请求清空该类旧结果；loading/error不把旧结果当作当前成功，保留其他类型缓存、取消与请求编号保护。

## 实现边界

`summary_output.py`仅负责原始字段严格类型和结构schema；`llm_service.py`继续负责本地规范化、预算与最终结构规则、HTTP和LLM错误映射。JSON示例/schema呈现key_points在前、summary在后；顺序为生成指导，不能保证供应商实际按此输出。strict_tool兼容路径保留现有槽协议。

兼容模式仍先拒绝非字符串point，再strip/drop空项后计数；strict保留extra拒绝、空point及原字符串长度边界。所有非空内容不截字删点。分段、合并、默认adaptive预算和1块1POST保持；没有额外模型评估/自动付费fallback。

前端hook清除本次kind缓存，若active等于kind同时取消显示；其他类型结果保留。失败时错误反馈与按钮恢复沿用现有组件，UI样式/token不新增值。

## 验证和完成边界

新增结构/序列化边界、现有LLM/adaptive针对性回归，以及前端成功→重做→失败/过期响应回归。离线验证不计算为模型内容通过，不重跑未变全量测试或旧在线phase。旧工作组26/26封账，此次无真实模型POST；中篇语义修复效果和新版长文必须获得新有限预算后实测。
