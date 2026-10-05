# 摘要结构化输出适配设计

## 工程约定

涉及 UI、视觉或交互时先使用 ui-ux-pro-max 与 design-system，skill 指引优先于计划；颜色、字体、时长通过 token 配置。能力通过配置和窄接口扩展，避免大规模重构；层间保持单向依赖，前端视觉只读 scene。后端仅 ytdlp_service.py 接触 yt-dlp，保留其回退；仅 llm_service.py 接触模型供应商协议。

## 问题与依据

此前 Chat Completions 的 json_object 只要求合法 JSON；本地要点数量校验会拒绝超量，但无法让上游预先保证数量。一次正式长文响应曾把多个主题塞进很长的末点，频率与具体示例范围也出现扩大。增加输入提示和输出预算不能代替结构验证。

[DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/) 宣布 text.format 支持 json_schema/name/schema；[兼容指南](https://api-docs.deepseek.com/guides/responses_api/) 描述 completed、incomplete、failed 及 reasoning.effort。这支持新增显式 json_schema 模式，但没有证明所有 JSON Schema 关键字都能形成供应商硬约束。本轮对抗探针中，第二个 Responses 响应仍返回了 8 条；本地验证正确拒绝。因此它不能作为本轮已验证的要点数量保证。

[DeepSeek strict Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) 明确要求 Beta 路径、function.strict=true、所有对象字段 required 且 additionalProperties=false，并支持 string.pattern；该文档列明 string.minLength/maxLength 及 array.minItems/maxItems 不受支持。这促成独立的 strict_tool 输出路径，用固定字段与正则表达长度，避免把不支持的数组约束视为保证。

## 配置与窄边界

LLM_SUMMARY_RESPONSE_FORMAT 支持 auto、text、json_object、json_schema、strict_tool。text/json_object 保持 Chat Completions；显式 json_schema 使用 Responses API，显式 strict_tool 使用强制命名函数的 Chat Completions。

LLM_SUMMARY_MAX_POINT_CHARS 默认为 240，须为正整数。它只在 json_schema/strict_tool 形成硬性本地长度验证；兼容模式把它作为提示中的精简目标，不新增长度失败阈值。LLM_SUMMARY_MAX_OUTPUT_TOKENS 保持 4096；分段与合并复用同一适配器。LLM_SUMMARY_THINKING_MODE 仍可配置；DeepSeek strict_tool 不接受 enabled，调用前返回 llm_unconfigured，因为强制命名工具与该模式的组合不受支持。未知供应商的显式选项由部署者根据其文档选择。

base URL 或完整 chat/completions、responses URL 都先去除末尾端点再选择目标协议。只有 DeepSeek 官方 api.deepseek.com 的 strict_tool 将根、/v1 或 /beta 转为 /beta/chat/completions；其他路径明确拒绝，其他兼容供应商保留其基础路径。翻译始终使用普通 Chat Completions，不接收摘要 schema、tools 或推理参数。

选择协议发生在 POST 之前。HTTP 错误、连接失败、输出结构错误均不触发第二个付费请求，也不静默回退兼容模式；下载/字幕模块与已有 yt-dlp 回退不受影响。

## strict_tool 数据协议

上游定义 emit_video_summary 函数作为结果容器，不执行该函数，也不提供工具结果继续推理。parameters 对象必需字段为 summary 和 point_1 到 point_7；禁止额外字段。summary 首字符须为非空白；point_1 必须非空白且最长为配置长度，其余槽允许同样受限的字符串或空字符串。unused 槽只能位于末尾，由本地验证连续性。

只接受 finish_reason=tool_calls、assistant 消息、无拒绝标记、恰好一次 function 调用、指定函数名及 JSON 字符串 arguments。本地检查全字段、类型、首字符、长度及槽位；任何异常均返回分类错误。验证后转换为既有 summary/key_points 接口，空的末尾槽剔除，保留 1–7 个完整要点；不截断过长内容，也不任意丢弃多余字段。

提示仍将字幕当作数据，要求按主主题挑选核心事实、保留频率/模态及来源归因、限定具体示例范围。所有模式都优先核心概念及必要条件，省略外围致谢、穷尽的操作符清单和非核心开场日程，避免末点成为剩余细节集合；以物流为核心的内容仍保留相关安排。长度提示与本地验证不能证明取舍准确或消除模型幻觉；人工事实评测仍独立进行，提示不包含评测语料答案。

## Responses 模式的本地验证

只接受 object=response、status=completed、无 error/incomplete_details 的输出；必须恰好一个已完成的 assistant message，内容块只能为 output_text。reasoning 输出项可忽略，tool/refusal 或非文本内容拒绝。incomplete/in_progress 分类为 llm_incomplete_response，failed 分类为 llm_error，异常字段分类为 llm_invalid_response。

正文必须是无代码围栏的 JSON 对象，且只有 summary 和 key_points。summary 非空、数组 1–7 项、每项非空并符合配置长度；本地校验防止供应商忽略约束。普通兼容模式继续接受既有代码围栏解析行为。

## 分段证据保留

第一次 natural-auto 评测显示：长文的部分结尾条件与后果在第二段生成的 notes 中已经消失，原始输入仍完整送达。最终合并只读生成 notes，因而无法从中恢复丢失事实。仅加强合并提示不能修复这条信息损失路径。

LLM_SUMMARY_SOURCE_CONTEXT_CHARS 默认为 1200，须为非负整数，0 关闭。每个原始分段携带最多前后各 1200 字符的原文边界证据；短于两倍该值时保留整段。中间省略标记明确表示没有提供中间原文，避免将不连续内容当成完整字幕。它只改变内部 section notes 的 source_context 字段，公开 LLMSummaryResult、原字幕和翻译接口保持不变。

合并输入同时含生成 notes 和原文证据，提示优先原文证据中的具体条件与结果，并保留段落重要结尾案例。分层合并继续携带这些原始边界证据；分组容量计算包含完整 JSON 和 source_context，超出容量且无法继续合并时明确返回 llm_input_too_large，不静默裁切保留下来的事实。未增加新的推理阶段或额外修复 POST；既有容量分组仍可能决定合并层数。

该证据通道只覆盖段落头尾，不能证明段落中间所有事实均被保留，也不能自动保证模型准确选取或使用证据。配置为 0 时内部 JSON 恢复只有 section/summary/key_points 的旧形状。真实质量评测冻结这一最终源码，在原三样本上进行一次 natural-refine 对照。

## 验证边界

离线 HTTP 边界测试验证请求协议、端点归一、配置长度包含边界、兼容模式、翻译隔离、结构拒绝、异常完成状态、强制工具字段及失败不重试。新增 slot/summary 首字符、槽位间隙和不兼容思考模式测试先复现 4 个失败，再修复为 llm_service/config 合计 87 个通过。原文证据回归故意使分段 provider 返回丢失事实的泛化 notes，然后验证最终 merge 实际收到自编事实的原文，并能恢复；容量与配置测试先复现 3 个失败，再完成修复。关闭配置、分层证据保留与容量错误检查合计定向测试 92 个通过；这些本地 provider 是路由验证，不是模型质量评分。

真实供应商能力与自然字幕质量由独立评测脚本冻结源码与请求台账，详细结果以本目录的 report.md 和 results 为准。一次工具能力请求发生连接失败，只能作为运输失败证据；不能称为供应商拒绝或能力验证成功。恢复网络后第 4 个预占请求获得 Beta HTTP 200 和指定工具字段，但 point_1 为空字符串，违反其非空 pattern；应用正确拒绝，第二个工具数量/长度探针没有发送。因此 json_schema 和 strict_tool 均未通过本轮能力验证，auto 保留此前 json_object；显式实验配置不能宣传为已验证的上游硬保证。
