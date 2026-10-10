# 有限事实槽与全局主题分配

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

接续用户已要求多agent并行继续的[合同复审](../../acceptance-reports/2026-10-07-grounded-summary-final/contract-review.md)。本设计限定既有facts路径私有生成协议，公开API和服务依赖保持；先离线交付，再申请新真实验收预算。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system与primitive → semantic → component三层token。能力配置化、窄接口单向依赖，避免大规模重构；LLM仅llm_service.py、yt-dlp仅ytdlp_service.py、视觉只读scene，不改下载状态或导入下载核心。用户.env/db/模型资产、历史报告/冻结快照/台账保持。默认legacy、正常n+2、无自动失败重试或付费回退。MIT来源和衍生评测保留署名、CC BY-NC-SA4.0非商业和相同方式共享要求。

## 固定抽取形状

新增纯函数 `parse_extraction(payload: dict | str, source: SourcePart, limits: FactLimits, id_prefix: str) -> tuple[GroundedFact, ...]`。顶层恰有fact_1…fact_N，N为limits.max_facts_per_chunk，默认12。各有效槽采用原topic/claim/evidence/attribution/importance五字段；至少首槽有效，所有null只能连续位于尾部。额外/缺失槽、重复JSON字段、空首槽、空槽后重启、未知来源、无效行号和归因均拒绝。有效事实按槽顺序生成原F索引和精确来源，不截断、删事实或扩大数量上限。

旧parse_facts数组合同保持为已有纯接口/历史兼容用途；新生产extract仅用parse_extraction，不静默回退旧协议。相关理由/条件可合并为完整命题，不能只留主题词；有限结构本身不证明语义完整，也不保证供应商遵守协议。

## 同一次compose内的全局主题分配

新增不可变 `ThemePlan(id, topic, principle, conditions, consequences, fact_ids)` 与 `PlannedComposition(candidate, themes)`，前者字符串/tuple、后者原CandidateSummary与tuple[ThemePlan,...]。新增纯函数 `parse_planned_composition(payload: dict | str, facts: Sequence[GroundedFact], limits: FactLimits) -> PlannedComposition`。

顶层恰有summary、point_1…point_M和theme_plan（M=limits.max_items，默认7）。theme_plan恰有theme_1…theme_M；非空主题和point同序对应，有效前缀长度一致，闲置只能尾部null。主题对象恰有topic/principle/conditions/consequences/fact_ids：topic≤max_topic_chars，principle≤max_claim_chars；conditions、consequences各0…max_items项，每项非空、≤max_point_chars；fact_ids为非空已知唯一引用。caller给主题ID T1…，模型不生成ID。对应point的引用必须属于该主题分配；允许共享上下文，但point继续遵循原新增事实引用约束。summary仍只引用已知事实。

解析器先检查完整新顶层与主题，再经原parse_composition验证候选，不悄悄丢弃未知字段。旧parse_composition与parse_candidate接口不变。缺少core引用的合法候选仍可进入原计划audit，不能将分配表视为已覆盖含义；未知引用、错误结构和容量违约仍立即停止。

compose在同一次模型响应内形成至多7个全局主题，包含原则、必要条件、后果和事实归属，按主题生成point及综合摘要。不得按分段或逐事实占点，不重标已验证core，不写rubric答案。

## audit与诊断

生产extract切换新槽解析；compose切换PlannedComposition并将主题分配作为trace.theme_plan与audit输入theme_plan保存。主题记录是带caller T索引的列表，含原六字段，不含源全文副本。原candidate、完整sources/facts和missing_core_fact_ids保持；容量检查包含完整新字段。audit根据原文核对最终文字的必要子句、姓名来源拼写/泛称、讲者观点、频率和范围，能修正主题/补充来源事实；最终输出合同仍是additional_facts/output/checks，不要求模型再次生成主题分配或追加阶段。

候选摘要默认≤14条/1600字符；最终摘要默认≤7条/800字符。候选与最终point数量都≤7；最终point默认≤240字符，候选沿用既有有限修订余量max(max_claim_chars,max_point_chars)，默认600字符，以供唯一既定audit修订。它不是本轮新放宽，也不改变最终硬上限；原配置和字段限制保持。有限主题规划也只是模型计划，不能代替原14essential/precision/organization独立评测。raw、trace只在评测中落盘，正常请求不额外持久化用户字幕。

## 隔离与验收

三个独立写集：纯codec+新纯测试；llm编排/提示+流水线测试迁移；独立organization-contracts评测wrapper+checker+新守护测试。主agent持有计划、集成及当前文档；用户明确要求并行，写集隔离后并行执行。当前未提交工作是已测交付基础，继续原工作区，不reset/clean/覆盖旧证据；不自动提交或改用户资产。

新评测仅默认plan/本地替身/freeze/check，独立phase及13POST计划，四个旧phase余额均不使用。完整冻结runner/checker链、codec/模块/配置/提示/rubric与三源；默认无网络，真实请求必须新预算明确授权，由root单caller串行、发前预占、失败即停。新checker同时检查主题trace/auditpayload一致和对应原raw新codec，不把规划存在当语义正确。

离线要求：12有效槽和13额外槽、空槽/缺槽/重复字段、来源/归因错误；全局主题跨来源、关系引用、缺失core进入唯一audit；最终所有原硬边界、阶段输入完整容量、错误不重试/不付费回退；legacy/translation/公开API保持。历史原件回放仅在测试中明确迁移合法协议形状，保留所有事实和来源；原13事实失败直接保持拒绝，不能截成12充当成功。
