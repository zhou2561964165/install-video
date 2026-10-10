# 规范化与引用解析分类重试 Implementation Plan

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

> For agentic workers: 使用superpowers:subagent-driven-development、test-driven-development与独立task review；用户已明确整改及持续授权，不重复审批。按确切接口划定写集。

**Goal:** 原始模型输出经本地规范化/程序引用关联后再校验，格式与语义修复分开且有限。

**Architecture:** 三具体纯模块负责normalization/reference/retry，HTTP仍仅llm_service；小窄接口prepare_audit_facts复用旧来源验证；新独立真实评测capture所有attempt和模块hash。

**Tech Stack:** Python3.12、dataclasses/json/stdlib、httpx、pytest，无新依赖/前端改动。

**Spec:** [设计](../specs/2026-10-08-summary-normalization-retries-design.md)。

**当前执行结果：** 三模块、运行时和独立冻结/重放工具已落地，最终后端965 passed。平台子 Agent usage 限制使 root 接手后续检查和工具工作；不宣称未发生的独立审查。实际三phase为8+4+13=25/26POST，均关闭。最新短中8essential完整，长6未评，audit JSON/来源别名/主题组织仍未通过，默认legacy。下面为实施任务依据；最新状态见[交接](../../handoff-2026-10-08-normalized.md)。

## 工程约定与Global Constraints

技能优先/UI三层token/配置化窄接口单向依赖/LLM唯一HTTP层/yt-dlp唯一服务层/scene只读。用户.env/db/模型/旧raw/freeze/ledger不改；默认legacy，公开返回形状/translation保持。重试新要求覆盖旧no-retry指引，分类可配置且默认1format/1semantic/extra2，总预算有限纳入ledger；正常n+2/最坏n+4。最终7/800/7point240不放宽，不自动补true、不瞎挂全部ID/未知源、不截字删点。注册轻量LunaMax、中高SolHigh，主模型不改。

## Review Focus

- 规范化保留原段落/条目/数字/否定/条件，拒绝duplicate与杂文而非贪心提取JSON。
- 引用相似度是来源关联建议，不是语义证明；英文/中文、泛词/歧义/错误提示不能假成功。
- 缺ref draft可进原计划audit，最终空ref/未知source/negativecheck不能发布。
- format/semantic计数分开但总extra≤2，实例隔离，所有attempt真实payload容量计入且无网络retry。
- 新评测frozen解析须hash验证全部新执行模块；旧phase证据仍只读，可录新规范化过程不改旧失败。

### Task 1: 纯规范化

Files: NEW backend/app/services/summary_normalization.py、NEW backend/tests/test_summary_normalization.py。

接口按spec提供DraftItem/ThemeHint/NormalizedDraft/NormalizationError、normalize_composition(payload,limits,final=False)，codecs dataclass依赖允许、禁止HTTP/settings/DB。仅本写集，无跨role覆盖。

- [ ] 真实已存summary str红→完整oneclaim规范化绿；array字符串/对象、slot/list points、theme hints、outer fence。
- [ ] raw未知/duplicate/nestedstr对象/内洞/超量/超长不可截，final limits先后明确。
- [ ] 新纯测试及报告 .planning/2026-10-08-summary-normalization-retries/normalization-report.md；停止编辑，root独立review。

### Task 2: 程序引用解析

Files: NEW backend/app/services/summary_references.py、NEW backend/tests/test_summary_references.py。

Consumes Task1 DTO、既有GroundedFact。Produces ReferenceResolution/ReferenceBinding/ReferenceResolutionError及resolve_references(draft,facts)；保留candidate与bindings/unresolved/ambiguous/invalid提示，不能newraw事实。

- [ ] 手工事实夹具精确/跨句/主题hint关联红绿，错误/未知IDs无强挂，空匹配/同分歧义可审核。
- [ ] bilingual/token/数字否定边界、确定性排序、原内容/源属性不变；已存str输出零网络只证明关联不证明质量。
- [ ] 新纯测试及reference-report.md，禁止改normalizer/旧codec/HTTP模块，停止编辑。

### Task 3: 分类重试与HTTP编排

Files: NEW backend/app/services/summary_retry.py、MOD backend/app/services/llm_service.py/config.py/summary_facts.py（only审计bank小helper）、NEW tests/test_summary_retry.py/test_normalized_pipeline.py；必要旧流水线测试由此owner明确报告迁移。

Consumes Task1/2，调用先normalize→resolve→draftAudit，audit.output重复normalize/resolve→prepare_audit_facts+parse_audit。原strict最终codec保持。

- [ ] Format原rawstr成功零extra；不可规范化一次格式修复；composeref缺口进入原audit。
- [ ] audit negative/core/未决一次semantic revision；source/network/config/capacity不重试，预算关闭/耗尽/请求实例隔离。
- [ ] config可选默认1/1/2，严格0–2类型范围；trace尝试/类别/原数据映射，max n+4真实MockTransport。
- [ ] 旧失败保留，不能通过改trace为validated包装成功；相关tests报告runtime-report.md，root统一全量/最后review。

### Task 4: 集成、独立评测与文档

主agentowner当前plan、whole delta、API形状/源资产核对；另立新phase/context正常13/最大19且组总26，frozen额外normalizer/references/retry所有source与配置hash。新checker只执行hash验证模块并重建norm→refs→audit pipeline，明确分类attempt和used budgets，不套旧严格raw==candidate假规则。旧checker/phase原件不改。

- [ ] 各task spec/quality独立审查，重要问题红绿、root后端全量/旧history只读检查。
- [ ] 新phase默认no network/共享caller/预占/分类budgetguards完整离线通过后freeze/check，root唯一caller有限实测。
- [ ] 14essential/precision/organization独立审核并更新当前entrypoints/handoff，不能把匹配ID/checks=true或测试成功当准确率。
