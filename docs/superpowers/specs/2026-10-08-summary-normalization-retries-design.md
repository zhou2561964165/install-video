# 摘要规范化、程序引用解析与分类重试

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

用户明确要求先规范化模型summary，不依赖模型硬生成全部引用，区分格式/语义重试，并按真实职责模块化，避免为解耦制造额外层。本轮在当前已验证facts路径上整改；旧失败raw/freeze/ledger保持，不拿原phase续跑。

## 工程约定与授权

技能优先；UI如需修改先ui-ux-pro-max/design-system和三层token，当前不改UI。能力配置化、窄接口单向依赖；LLM仅llm_service、yt-dlp仅ytdlp_service、视觉只读scene，不改下载核心。用户.env/db/模型资产及历史原件保持。主模型不改，轻量真实Luna Max/中高Sol High角色，按实际独立任务决定并行。MIT来源/衍生评测保留署名、CC BY-NC-SA4.0非商业/同方式共享。用户开发/有限计费持续授权；新要求明确覆盖旧“任何错误无重试”规则，重试必须显式分类、有限且纳入账本，禁止隐藏回退/无限扩预算。

## 具体模块边界

1. summary_normalization.py：纯JSON读取与格式转换，返回不可变draft；不访问事实语义、HTTP、数据库或settings。不裁句、删点、补正面checks或猜引用。
2. summary_references.py：纯程序引用解析，消费draft和已验证GroundedFact；按精确文本、主题候选与可解释词法关联产生已知ID和未决状态。模型提供的IDs仅为提示，不是最终依据；不创造新事实/来源。
3. summary_retry.py：纯错误分类/尝试预算，区别格式、语义、来源、安全/容量、provider/network/config；不执行请求。调用策略是实例级，不能跨请求共享可变计数。
4. llm_service.py保留唯一HTTP边界，编排上述三个模块与原source/final codec。没有新的service locator、事件总线或泛化插件框架。

## 规范化输出与稳定接口

不可变DraftItem：id、text、topic（summary为空字符串）、hint_ids（tuple[str,...]）。NormalizedDraft：summary tuple[DraftItem,...]、key_points tuple[DraftItem,...]、theme_hints tuple[ThemeHint,...]、transformations tuple[str,...]。ThemeHint包含point_index、topic、principle、conditions/consequences tuple、hint_ids tuple。ID由caller顺序分配S1…/P1…。

`normalize_composition(payload: dict | str, limits: FactLimits, *, final: bool=False) -> NormalizedDraft`：summary可以是paragraph string、list[str]或list[{text,fact_ids?}]；paragraph保持完整作为一个声明，不靠标点重写/删内容。points可key_points数组或point_N有效前缀，条目string或{topic?,text,fact_ids?}；缺topic用稳定空串/通用主题标签，不能从外部知识填内容。两类point表示同时出现且不一致必须拒绝。theme_plan可缺省，存在时保留已验证形状的提示，不要求为正常paragraph编造计划。

允许本地去除整段外层markdown JSON fence、单ID字符串包装为单元素hint列表、空尾槽规范化；duplicate字段、JSON文本外的杂文、非对象根、未知字段/内空槽、错误text类型、数量/长度超界拒绝，不能挑部分payload隐去错误。保留每个非空text、所有provided IDs（包括无效提示用于诊断），不得无理由丢条目。格式转换先于内部结构校验。

candidate摘要默认14声明/1600总字符、points最多7/既有600候选长度；final摘要7/800、points7/240保持。规范化audit.output也使用同接口final=True；additional_facts和checks保持原校验，缺checks不填true。

## 程序引用解析

`resolve_references(draft: NormalizedDraft, facts: Sequence[GroundedFact]) -> ReferenceResolution`，返回candidate CandidateSummary、bindings tuple[ReferenceBinding,...]、unresolved/ambiguous item IDs及invalid hints。ReferenceBinding记录item_id、fact_ids、method、有限score；来源ID必须来自事实索引，排序确定且去重。

精确文本（规范空白/大小写但不改数字/否定）匹配优先；非精确文本从claim/quote/topic建立可解释词法候选，按相关主题hint限制/加权而非盲从ID。已知模型IDs若与文字不关联，不应直接成为支持；未知ID保存为诊断，无拼写猜改。英文词及中文片段匹配要有最小实质重合，泛泛相似/并列歧义标ambiguous，无候选标unresolved，不无脑挂全部fact IDs。

程序匹配只表示候选来源关联，不证明语义蕴含。未决draft允许进入原计划audit，candidate可含空fact_ids并附每条reference_status/候选提示；不能进入公开最终返回。audit输入包含原文、完整已验证facts、规范化candidate、主题/引用解析记录、缺core诊断，不把IDs或覆盖表当语义正确。

audit后的output再规范化和程序引用解析，复用验证过的完整fact bank（含合法audit additions）。最终必须通过原parse_audit/source/core/checks与原长度/数量边界；无法建立支持或歧义仍未解决属于语义错误，不发布。允许audit明确选择已知候选帮助消歧，但须有文字关联/来源验证，不能因flag=true强挂ID。正常请求不额外保存原文，trace仍仅由显式diagnostic持有。

## 错误分类与有限策略

ErrorCategory：FORMAT、SEMANTIC、SOURCE、CAPACITY、PROVIDER、NETWORK、CONFIG。NormalizationError与ReferenceResolutionError只含bounded reason code，无raw/model/source文本。

默认一次总结format重试≤1、semantic重试≤1、总附加模型调用≤2，可配置0关闭；合法范围0–2，总附加上限硬约束。先本地规范化/引用生成，零额外POST；不可规范化的结构错误才请求同stage格式修复，保留原source与错误reason，不改语义为凑格式。compose缺引用/语义疑点优先交原计划audit，不为此额外compose重试。

audit的missing_core、audit_not_supported、未决引用/限定/归因/范围问题可一次有明确失败项的semantic revision；不再盲重跑整个pipeline。来源/evidence/quote/attribution非法、认证、网络/provider、容量/无效配置错误直接停止，不能凭空造来源或隐藏fallback。最终超限/重复表达要明确归类为需修订的组织/语义约束，不裁字或删事实。

正常n+2；默认最坏n+4。每次attempt trace记录stage/attempt/category/reason/recovery和retry预算used/ceiling，区分本地转换/模型格式修复/语义修订。每次HTTP先实际capacity和持久预算预占；失败尝试同样计数。重试payload完整计入输入容量，不截原响应来凑容量。预算用尽/来源错误不产生下一请求，公开API维持llm_invalid_response等原形状，diagnostic保留明确类别。

## 审计事实窄接口

summary_facts.py可提取现有parse_audit中事实bank构建为 `prepare_audit_facts(additions, sources, facts, limits) -> tuple[GroundedFact,...]`，供audit规范化/程序refs先拿到合法A1…事实。原parse_audit签名与行为保持并调用此helper，不复制来源验证代码；额外事实/evidence/attribution始终校验后使用。

## 验收与预算

先用已存summary字符串失败原件做零网络规范化/引用关联/唯一audit编排回放，保持字面内容及原失败记录。测试格式零调用修复、无法修复时一次format retry、负audit一次semantic revision、错误分类/总附加2/关闭策略/网络不重试/来源不重试/最终不可发布未决引用；真实MockTransport核对每个payload和call count，不通过mock flags宣称内容正确。

新的真实验收另建独立phase，正常三源3/3/7共13，最大5/5/9共19；本次新整改工作组总硬上限26，真实请求由root单caller，并纳入所有格式/语义失败尝试。先完成代码/审查/全量/新freeze和包含所有实际执行模块的hash再执行，不续此前两个失败phase。无自动无上限扩预算，默认legacy不推广，最终14essential/precision/organization仍独立审核。
