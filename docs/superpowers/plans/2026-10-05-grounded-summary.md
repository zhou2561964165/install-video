# Grounded summary Implementation Plan

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

> **已暂停：2026-10-05用户明确要求。** 代码/测试/证据已保存但未提交；默认legacy。实际5POST/5HTTP200/11426tokens，两个候选失败原件保留，新中/长结果未完成；剩余19次不使用。后续仅按用户指示继续，先读[交接](../../handoff.md)，不能把本计划当作自动恢复授权。

> **For agentic workers:** Use applicable superpowers:test-driven-development and verification-before-completion; root coordinates independent file ownership and final review.

**Goal:** 在现有摘要链路加入来源绑定事实、主题组织和逐声明核查，保持API与yt-dlp回退。

**Architecture:** summary_facts提供纯数据合同和校验；llm_service通过现有单POST传输编排抽取/组织/核查，策略在请求前选择。独立评测读取冻结的MIT源，不写产品模块。

**Tech Stack:** Python3.12、dataclasses/JSON、现有httpx/FastAPI/pytest，无新依赖。

**Spec:** [设计](../specs/2026-10-05-grounded-summary-design.md)。

## 工程约定与全局约束

适用Superpowers技能优先检查；UI先ui-ux-pro-max/design-system，本轮不改UI；三层token和配置、窄接口单向依赖。只有ytdlp_service接触yt-dlp，LLM只llm_service，视觉只读scene。保持.env/db/用户AGENTS/模型资产、旧源码基线和台账原样，无自动计费POST重试/降级，正常核查阶段明确计入预算。

## Review Focus

- 引用规范空白后仍能回到真实清理文本位置，不能把模型claim当作原文。
- 有效来源quote不等于claim蕴含；逐项checks和最终事实覆盖独立核查。
- 核查新增事实必须有来源和已知ID，不能通过新增ID绕过来源验证。
- 最终1–7点/长度/非空与审查清单完整，不截断或静默删无效记录。
- auto选择、容量、配置组合在计费前决定，legacy长文/实验格式兼容保留。

### Task 1: Pure fact/claim contracts

**Files:** new backend/app/services/summary_facts.py, backend/tests/test_summary_facts.py。

**Interfaces:** SourcePart/FactLimits/GroundedFact/CandidateSummary/AuditResult dataclasses；parse_facts(payload, source, limits, id_prefix)、parse_candidate(payload, facts, limits)、parse_audit(payload, sources, facts, limits)；FactValidationError不依赖llm_service或HTTP。两实现者先确认精确JSON、签名和trace字段再并行编码。

- [ ] 写原文映射、无效quote/限定/归因、未知引用/重复点、核查完整与新增事实来源红测试。
- [ ] 实现最小纯校验并运行红绿，记录含义边界。

### Task 2: Configurable stage orchestration

**Files:** backend/app/services/llm_service.py、app/config.py、tests/test_llm_service.py/test_config.py及必要新pipeline tests。

- [ ] 策略/容量/格式组合与旧API行为红测试；完整计划阶段抽取n次、组织1次、核查1次。
- [ ] 使用Task1窄接口、现有_complete传输；私有trace回调、错误分类、无自动失败回退。
- [ ] 校验所有输入/输出、重要结尾与限定/归因信息，匹配现有summary响应。

### Task 3: Independent real evaluation

**Files:** docs/acceptance-reports/2026-10-05-grounded-summary/（脚本/新台账/结果/评审）。

- [ ] 新24POST硬预算、发前预占、源码/配置/prompt/事实/语料/trace哈希，历史19/24不改。
- [ ] 未付费前冻结评价规则与预计10POST；仅必要测量驱动修复后新profile，失败保留。
- [ ] 独立审核每条引用/输出与原文，保守统计完整/部分和主题组织；新阶段调用成本明确。

### Task 4: Integration and delivery

- [ ] root独立源码/结果复审，解决确定缺陷，运行适当全量测试/构建。
- [ ] 实现提交、主文档/证据归档、字节/链接/凭据扫描；停止本轮服务和调用。
- [ ] 报告达成/未达目标与下一项建议，等待用户指示。
