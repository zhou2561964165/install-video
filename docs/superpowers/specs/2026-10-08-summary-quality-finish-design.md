# 摘要核查协议与质量约束续收尾

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

## 用户目标与工程约定

沿已授权原步骤恢复真实多 Agent，优先收尾总结质量。复用已有规范化、程序引用与分类预算，解决长文核查结构负担、主题前部占满、未确认姓名和独立审查发现。技能优先；UI 按需 ui-ux-pro-max/design-system 三层 token，本次仅后端。配置化窄接口单向依赖，LLM/yt-dlp 唯一服务边界，scene 只读。已有工作区/用户 env/db/账号/旧 raw/freeze/ledger 保持；不重构下载/前端、不提交推送。

用户持续授权和本次继续指令优先于技能的重复审批停顿，完成具体设计与独立审查后直接执行。新预算独立硬26，首三源正常13、默认格式1/语义1/共享2最坏19；后续phase仅在定位且离线验证后以明确剩余额度分配，不突破26、不续旧25组。

## 已确认根因

长文49事实（38core/11support），候选7摘要共1332字、7点，但实际引用只覆盖13core，缺25，theme_plan为空，前部占满主题。核查以追加点补覆盖，实际27正文点、P1–P28检查编号；raw有34处坏fact_ids键，5183/8192tokens、finish stop，非截断。姓名在compose引入，提取 attribution 正确，现模型alltrue不拦自由文本别名。

独立审查两个明确bug：fence让原raw重新json.loads失败，非法provenance误归FORMAT；endpoint尚未验证就计paid_calls。边界修复先做，按规范化对象分类、配置预检后才付费标记。

## 职责与接口

只新增两个实际职责模块，无新HTTP阶段、NER依赖、事件框架：

1. `summary_audit_contract.py`：纯读取核查协议与真实模型断言映射，不验证来源或语义。
   - `read_audit_contract(payload: dict | str) -> dict`：完整JSON对象/完整外fence、重复键拒绝；字段保留，让调用层先验证additional_facts。
   - `parse_audit_contract(payload: dict | str, limits: FactLimits) -> AuditEnvelope`。
   - `AuditEnvelope(protocol, additional_facts, composition, checks)`：保留所有文本、模型提示与bool值；程序生成S1/Pn与checks对应关系，不生成true、不截字删点。
2. `summary_quality.py`：纯可确定主题/身份诊断，不改正文、事实和引用，不做普遍NER或语义证明。
   - `inspect_quality(draft: NormalizedDraft, facts: Sequence[GroundedFact], sources: Sequence[SourcePart], *, require_theme_plan: bool=False, candidate: CandidateSummary | None=None) -> QualityReport`。
   - `QualityIssue(reason,item_id,fact_ids=(),...)` 与 `QualityReport(issues, identities, ...)` 不可变；能直接反馈具体失败条目，详细字段由实施报告固定，不向公开API扩展。

原 normalizer/references/summary_facts/RetryPolicy 接口保持。llm_service 唯一编排层；模型断言与关联ID不是来源蕴含保证。

## 核查 compact 协议

精确顶层 `{additional_facts, output}`。output一个summary对象 `{text, assertions, fact_ids?}` 和 `point_1…point_max_items` 连续非空前缀，每点 `{topic,text,assertions,fact_ids?}`。至少1点；空尾可省或null，洞/未知字段/第8槽不忽略。summary只一段，不拆句。assertions精确四个实际bool：supported、qualifiers_preserved、attribution_preserved、scope_preserved。

false可进入结构映射，原parse_audit随后拒绝并走semantic修订；字符串true、数字1、缺/多flag为FORMAT。程序分配S1/Pn并生成逐项checks，把真实模型四flag原值转置；不要求模型再生成check item_id或最终引用。

精确顶层 `{additional_facts, output, checks}` 为legacy兼容路由；不因解析失败猜协议，不把缺旧checks补true，不允许混合内嵌和外置断言。兼容原件只读可重放，不把旧失败改成功。

读取完整对象后 **先** prepare_audit_facts 验证源银行/additions，再适配contract和normalize(final=True)，再程序refs/quality/原parse_audit。source错误不被输出格式错误掩盖而重试。summary最终800/配置限值，点7/240/配置限值，core/source/新增事实/全部逐项检查保持。

## 主题与身份

新增 `LLM_SUMMARY_QUALITY_CONTRACT=compat|compact`，默认compat保存当前事实协议，策略默认legacy不改。新真实验收显式compact，并使用原default retry 1/1/2。compact compose要求完整全源theme_plan：1–7主题，每主题具体原则、条件/后果和主要事实归属；先读所有part及结尾再分配点，不能一fact一点、核心遗漏通过追加尾目录补齐。缺计划的draft仅诊断并交原audit，不为此额外compose POST。

compact audit的point topic+text+模型fact_ids归属可构成最终主题记录；程序最终refs仍由文本关联生成。主题诊断检查计数、明确主要ownership重复、未知ID和相同主题标签等确定性不变量；summary已实际关联的core可由摘要承载，不逼概览单独占点。非同义词检测/ID覆盖不证明组织质量，最终原评分仍人工审核。

身份允许信息仅来自原SourcePart和经过验证的fact.attribution/span；输入显式提供原拼写/一般讲者策略。程序能发现的原字面姓名自己产生output/source span记录，避免模型再次硬算offset。独立诊断仅针对明确角色绑定专名结构或模型显式身份表达，覆盖已存“讲者〔未确认中文姓名〕介绍”且不硬编码姓名；“讲者明确指出”等绿例不可误判。不能任意2–4汉字当人名，不能盲replace或依据外部知识补别名。检测边界及未覆盖隐式姓名明确记录。

最终未确认身份/确定主题冲突是候选语义错误，可原有semantic一次修订；原事实source/span/attribution非法继续SOURCE立即停。原文和flag不由程序改写。

## 验证与发布

旧非法JSON原件持续失败、旧短中legacy形状等值；新compact全字段/真实false/slot/混合/超限；来源错误优先；原姓名新增片段与副词绿例；跨part主题含独立条件/后果及尾部；真实MockTransport正常n+2和默认修复n+4，所有attempt原件/反馈/计数可重放。

分任务规范与质量审查，root全量；新工具必须冻结新增两个模块及现有六个和所有实际helper，默认零网络、独立组/phase、发送前预占/单caller/typed ledger，预算达到上限仍能只读关闭/报告但不能POST。14essential、precision、organization标准不改；三方面实际通过才宣布质量收尾或考虑启用默认compact事实协议。默认legacy不提前推广。
