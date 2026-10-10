# 长文摘要组织与阶段预算

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

本轮继续 evidence 设计的主题合并、1–7 要点与逐项核查目标；保留 2026-10-05 文档和证据。审查确认旧长文 compose 不仅截断，还产生 18 个完整要点对象及第 19 条文本。

## 工程约定

技能优先；UI 使用 ui-ux-pro-max/design-system 与三层 token；能力配置化、窄接口单向依赖；yt-dlp 仅 ytdlp_service，LLM 仅 llm_service，视觉只读 scene。本轮不改 UI、.env、数据库和模型资产，正常 n+2 调用、无失败重试或隐藏付费回退，legacy 默认保持。MIT 评测源与衍生内容继续原署名及 CC BY-NC-SA 4.0 非商业许可。

## 范围

- compose 输出私有固定槽合同：summary 声明数组以及 point_1…point_7。槽值为 {topic,text,fact_ids} 或 null；第一槽必须有效、闲置槽只允许在末尾。不接受未知字段、缺槽、重复 JSON 字段或空槽后重启。
- 纯 codec 将槽合同转换成现有 CandidateSummary，audit 输入/输出及公开 summary/key_points/provider/model 不变。正常过程仍分段抽取 n 次、compose 一次、audit 一次。
- 提示词先归并全局主题再填写槽；允许多个相关 core fact IDs 共用一个点，避免逐事实列点或末点杂物清单。来源、条件、归因与范围不能为压缩而删去；源引用与 flags 不证明语义正确。
- LLM_SUMMARY_FACTS_MAX_SUMMARY_CHARS 默认800（1–4000），用于最终摘要硬上限。point 上限仍来自 LLM_SUMMARY_MAX_POINT_CHARS，compose 候选允许有限超长以便一次正常 audit 修订。
- 首次真实profile是 compose/audit 摘要同一800硬上限版本；长文候选946字触发summary_too_long，已停在12/13且原件保留。根据测量做离线修订：compose候选摘要最多2倍最终上限（默认1600），audit最终仍800；不截字、丢声明或增设修复POST。修订尚无新真实profile，不重启原phase。
- 首次短/中输出的独立审阅为5完整/3部分：大纲遗漏、预期/文化观点范围及频率仍不足，存在无来源支持的汉字姓名。根据实际precision问题增强通用提示：每个独立观点明确保持讲者/课程视角，sometimes不得加强为often，专名保留来源写法或用泛称，不逆推汉字姓名；不加入语料答案。该提示修订尚未真实验证。
- LLM_SUMMARY_FACTS_COMPOSE_MAX_OUTPUT_TOKENS 与 LLM_SUMMARY_FACTS_AUDIT_MAX_OUTPUT_TOKENS 默认0（0–65536）；0继承 LLM_SUMMARY_MAX_OUTPUT_TOKENS，明确正值按阶段应用，extract/legacy 不变。请求前容量校验与实际发送使用同一预算。
- 54事实回放暴露实际 audit 输入约71K字符，原60K输入默认不足。产品输入默认保持不变；本轮独立评测profile显式用 LLM_MAX_INPUT_CHARS=100000、compose/audit=8192。容量不足明确拒绝，不删原文/事实、不截断或隐藏回退。

## 验收与限制

先红绿测试固定槽、输入容量、按阶段预算、错误不重试、旧API/legacy，再用保存的长文54事实做零网络编排回放。回放仅证明真实 codec/编排/预算行为，不计作模型语义验收。新真实评测必须独立 phase、独立台账、源码/提示/config/rubric哈希冻结，短/中/长预计3+3+7=13 POST，未获新预算前不调用。
