# 有限生成合同 Implementation Plan

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development and test-driven-development. 用户明确要求多agent并行，以隔离写集执行，主agent集成与独立复审。

**Goal:** 将facts私有extract限制为配置化事实槽，在同一次compose响应中输出可核对的全局主题分配。

**Architecture:** summary_facts新增两个严格纯解析接口，旧解析接口保持；llm_service接入新协议并把主题分配传给原audit；评测wrapper独立phase，新增checker验证规划链，不改旧证据。

**Tech Stack:** Python 3.12、dataclasses/JSON、httpx、pytest，无新依赖。

**Spec:** [已选合同设计](../specs/2026-10-07-grounded-summary-contracts-design.md)。

## Global Constraints

技能优先；UI先ui-ux-pro-max/design-system、三层token；配置化/窄接口单向依赖；LLM仅llm_service、yt-dlp仅ytdlp_service、视觉只读scene。用户.env/db/模型资产与历史证据/账本不改；默认legacy、n+2、无自动失败重试或付费回退。默认候选摘要14/1600、final摘要7/800、final points7/240保持；候选point数≤7，长度沿用max(max_claim_chars,max_point_chars)既有修订余量、默认600，不新增放宽。MIT衍生证据保留署名及CC BY-NC-SA4.0许可。开发授权来自用户本次并行继续，新真实计费预算尚未授权。

## Review Focus

- 配置改变槽数时确切键集合随配置变化，不能只写死12/7。
- 新协议非法结构/来源不能被fixture适配或生产旧协议fallback掩盖。
- 缺core候选仍有唯一audit机会；主题规划和引用关系不证明必要子句覆盖。
- 主题/完整来源/facts容量进入实际请求、trace与freeze，超容量不得删内容。
- 新入口有效wrapper/checker全链冻结，旧phase与余额不可续用，新默认命令零网络。

### Task 1: 纯有限合同

**Files:** backend/app/services/summary_facts.py；新增backend/tests/test_grounded_contract_codecs.py。

**Interfaces:** Produces parse_extraction(...) -> tuple[GroundedFact,...]、ThemePlan、PlannedComposition、parse_planned_composition(...) -> PlannedComposition；签名与字段取值逐字遵循Spec。Consumes原parse_facts/parse_composition/FactLimits，不改变这些接口。

- [ ] 写行为红测试：getattr(module,'parse_extraction',None)应callable，随后真实12槽成功/13键拒绝；1/2/12配置槽；首null、间隙、缺键、duplicateJSON、无效来源。
- [ ] 实现新解析接口，使用原来源与字段校验，无截断/丢弃/重试。
- [ ] 写主题分配红测试：跨源相关事实在同theme中完整保存；额外字段/主题间隙/未知refs/point引用不在分配拒绝；缺core允许候选。
- [ ] 红绿后跑新纯测试与test_summary_facts.py；报告精确命令/计数及红记录，不git commit。

### Task 2: 新协议编排及回归迁移

**Files:** backend/app/services/llm_service.py；新增backend/tests/test_grounded_contract_pipeline.py；迁移backend/tests/test_grounded_pipeline.py、test_grounded_organization.py、test_grounded_coverage_revision.py、test_grounded_refined_replay.py中声明为合法的协议fixtures，必要时其他流水线fixtures先报告主agent。

**Interfaces:** Consumes Task1四个接口；Produces trace.theme_plan和auditpayload.theme_plan列表，包含id/topic/principle/conditions/consequences/fact_ids。保持公开result及audit数组输出不变。

- [ ] 先写真实MockTransport红测试：extract新slots、compose带theme_plan，审计请求收到所有来源/facts/candidate/原主题与missingcore；最终仍仅3请求、失败无第四请求。
- [ ] `_grounded_system`由FactLimits动态给出精确槽形状；改extract/compose解析，主题记录传入原audit；preflight含空theme_plan占位，实际容量验证完整计划，不改最终合同。
- [ ] 原合法fixture明确构造新协议；非法payload不能适配后变合法。原saved13事实失败保持拒绝；旧<=12保存数据只做协议容器迁移并标明零网络/非语义证明。
- [ ] 新测试及相关回归通过后停止编辑，报告；主agent统一全量，不重复全量，不git commit。

### Task 3: 独立contracts验收入口

**Files:** docs/acceptance-reports/2026-10-07-grounded-summary-contracts/{scripts/evaluate.py,scripts/check_evidence.py,rubric.json}；backend/tests/test_grounded_contract_evaluation.py。

**Interfaces:** 新phase organization-contracts、独立13POST台账，复用final或org/base有效包装链；显式冻结全部有效wrapper/checker和新入口hash。Consumes冻结codec的新parse_extraction/parse_planned_composition及trace.theme_plan，对原14rubric/source byte-identical。

- [ ] 新入口缺失/具体guard缺失先红，随后默认零网络plan、新phase/整数ceiling13/已用账身份/预占/共享caller锁/失败停止/禁止phase重启等绿。
- [ ] checker零网络核对每个extract原raw到trace事实以及compose原raw到candidate/theme_plan、audit原payload规划与trace一致，使用hash校验过的冻结codec，不能只存在字段就过。
- [ ] 本地替身真实base runner跑3/3/7完整链与错误停；修改任意有效wrapper/checker/codec/prompt后POST拒绝。
- [ ] 只交付代码和本地测试；真实freeze/check由主agent在集成后执行，不读取打印key、发模型请求或写旧目录。

### Task 4: 主agent集成与独立审查

**Files:** 当前文档/新报告；.planning/2026-10-07-grounded-summary-contracts/与本计划SDD ledger。

- [ ] 逐task复审spec/质量，由其他agent交叉核对独立写集；全量 `../.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp <唯一目录>`。
- [ ] Critical/Important先以红绿修复，再最终独立整体审查；保留所有历史phase/hash，核对用户资产和scope。
- [ ] 默认plan、freeze/check-only，准备新模型预算申请；更新报告/入口/交接及测量与交付差别，不能声称语义达标。
- [ ] 明确新预算授权后另续真实测量和14项独立审核；未授权不执行模型POST。
