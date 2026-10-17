# 长文主体范围与来源核查加固

工程约定：复用成熟组件，保持可配置窄接口/单向依赖，`ytdlp_service.py`仍是唯一yt-dlp接入层；不触碰UI、账号/env/本地模型及任何closed验收原件。

## 状态与证据

用户于2026-10-14明确恢复长文整改。旧phase1–5维持closed，累计9 POST / 147600供应商tokens。本设计只针对新代码与新phase，不重开或改写旧记录。

phase1英文叶笔记已经把一个具体实例的限制泛化至类别，后续merge和phase2/4沿用；因此只改merge或多给原文不足以覆盖根因。phase2/4独立逐源审阅均发现P4范围错误。phase5的反馈响应产生重复target并以`finish_reason=length`截断；其`json_object`请求没有把Pydantic checks schema传给供应商。

## 设计

1. 在生成、核查和修订指导中明确跟踪类别切换到实例后的语法主体：示例后的指示词/代词继续指向该实例，直到原文明确切回类别；能力谓词不能仅因共享主题词就上升为类别结论。若一个草稿点包含多个断言，核查先检查整个点，选择最需要纠正的范围或遗漏，而不是列出多条重复target。措辞保持跨主题通用，不加入课程、计算器或样本答案。
2. 核查schema依据实际summary与key_points数量动态生成固定对象字段`target_0`…`target_N`。每个字段只含枚举`assessment`、最多120字符的连续原文`source_quote`和最多80字符的简短`finding`；不让模型重复生成target编号或草稿引文。程序按对象字段绑定原草稿位置、验证严格类型/额外字段/引用来源/字段长度，并把通过结构检查的反馈依位置传给唯一修订。
3. 核查专用schema沿现有Pydantic v2与Responses `json_schema`传输发出，不新增SDK或provider探针；产品其余生成格式仍沿配置。核查token预算固定为`128 + 256 × (要点数 + 1)`，受现有`LLM_SUMMARY_REVIEW_MAX_OUTPUT_TOKENS`硬上限约束；14要点需3968 tokens。多段完整生成按源规模可用点数在第一片叶模型POST前检查此上限；单段流程不调用核查，因此不要求核查预算。复用草稿路径按草稿实际点数检查。配置不足则发前拒绝，不先付费生成叶笔记再失败。任何不完整/非法/超长响应错误即停，不裁字、不增重试。
4. 使用原文优先的固定review→revision两阶段。核查的assessment和反馈都只是易错提示，不构成事实证明。引用子串、schema覆盖和结构通过不等于语义通过；新结果仍需独立逐断言内容审阅。

## 已有成熟能力与选型

- Pydantic v2（现有依赖）生成动态严格schema；现有`PydanticOutputParser`验证核查结构。无需再造结构化输出框架。
- [DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)当前文档支持`text.format`下的`json_schema`；项目已有Responses传输和接收解析，因此checks候选只复用该通道。调用仍固定两次，不做能力探针、隐藏fallback或新SDK请求。
- DeepSeek [Chat JSON Output](https://api-docs.deepseek.com/guides/json_mode/)只保证JSON可解析，不保证符合应用字段结构；现有phase5请求未传schema，故不再用于checks。函数工具需Beta端点及专用解码分支，未选用。
- 实际收益是每个草稿位置只有一个必需schema字段、引用及finding长度有上限；它降低重复目标与截断风险，不建立语义保证。没有新依赖；潜在成本仅固定两次核查/修订POST，核查输出随目标数配置并受上限约束。
- phase6把`phase_post_cap=2`写入计划、provenance和offline-check；组级总预算仍按用户授权不设上限。发送器在每次POST前同时核验该phase cap和固定两阶段来源链，第三次请求无法进入发送。

## 验收

- 离线回归用不同主题的“类别→具名实例→指示词→能力限定”合成输入，验证生成、核查、修订消息保留主体范围关系且不含旧样本专属措辞。
- Pydantic schema对1、14、32个key_points各自产生固定N+1字段；未知/缺失字段、重复JSON键、虚假或过长原文引用均拒绝。
- Mock HTTP确认checks使用Responses `json_schema`和按目标数计算的有限预算，核查成功后恰好一个修订请求；长度/HTTP/JSON/schema/容量错误只发一次。
- 独立生产与验收工具审查、全新增模块freeze/check完成后，新phase复用phase4精确源/完整草稿，phase预算最多2 POST，首错即停。通过后再分别冻结完整长文、未见长文及短中回归的有限phase；整体任务没有总POST/费用上限，旧67 POST不借用或重置。
- phase1–5快照、payload、raw、result、ledger、receipt、脚本和冻结审查原文保持逐字节不变。默认fidelity仍off、公开20000字符入口保持未恢复，直到新的完整实测和质量审阅支持调整。
