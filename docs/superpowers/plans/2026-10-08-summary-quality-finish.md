# Summary Quality Finish Implementation Plan

> **历史计划：实施与核查验收已执行，后续产品方向已转为adaptive字幕总结。** 当前状态见[自适应交接](../../handoff-2026-10-09-adaptive.md)：四个phase累计22/26 POST并全部关闭。下列任务和fixed/facts合同仅记录原阶段，不能当作待办重做，也不能恢复已取消的quality-long-final阶段。当前剩余缺陷见最新交接。

> For agentic workers: superpowers:subagent-driven-development、test-driven-development、task review和完成前验证；用户继续及持续授权允许执行，无重复许可停顿。按责任写集并行，不覆盖他人或历史证据。

**Goal:** 长文核查可靠使用有限主题结构，来源姓名与主题归属有程序诊断，真实原14项及精确性/组织验收。

**Architecture:** 复用normalization/references/retry/facts，只新增纯audit协议适配器和纯quality诊断；llm_service保持唯一HTTP，n+2正常/默认n+4不增加阶段。

**Tech Stack:** Python3.12标准库/httpx/pytest，无新依赖/前端改动。

**Spec:** [设计](../specs/2026-10-08-summary-quality-finish-design.md)。

## Global Constraints

技能优先/UI三层token按需；配置化窄接口/单向依赖/LLM与yt-dlp唯一服务层/scene只读。source/core/checks/final7/800/240不放宽，text/hints完整保留、程序不补true/假ID/剪内容。默认legacy，新quality模式默认compat；eval显式compact+default retries1/1/2。原env/db/用户工作/历史资产只读。新组硬26，root唯一真实caller，发前持久预占，失败尝试全计，无无限扩预算。

## Review Focus

- source错误和输出结构同时坏时，来源先拒绝且0额外POST。
- 内嵌bool/外置legacy不混合、不补checks，不把whole paragraph flags当逐句证明。
- ownership只验证确定关系，不能把semantic同主题的新条件删掉。
- 身份检测明确作用域、泛词/副词/原文字面名字不误报，不能宣称普遍NER。
- caller原件/typed ledger/新8模块/helpers完整hash，与default repaired attempts准确映射。

### Task 1: 独立审查边界修复

Owner review actor；llm_service的分类/perform预POST行 + NEW test_summary_runtime_review.py。真实红例先12fail/7pass，修来源、配置分别绿；报告review-boundary-fix。其他llm行root后续owner，互不同时写。

### Task 2: 核查协议纯适配器

Owner audit actor；NEW summary_audit_contract.py、NEW tests/test_summary_audit_contract.py、audit-contract-report。接口read_audit_contract/parse_audit_contract/AuditEnvelope按spec。只生成确定S/P编号与映射，四bool源自模型，不补true。先旧真实失败和新compact红，后实现/隔离旧codecs+新tests。停止后独立task review。

### Task 3: 纯主题/身份诊断

Owner semantic actor；NEW summary_quality.py、NEW tests/test_summary_quality.py、quality-module-report。inspect_quality按spec消费DTO/facts/sources/candidate。只返回问题/可证字面绑定，不改正文或语义。原姓名实际红、副词/generic/原名绿，ownership重复/缺失/未知/跨part保内容案例；语义不由简单相似度证明。禁止改Task2及llm/config/normalizer/ref模块，停止后独立task review。

### Task 4: 集成与模式配置

root owner llm_service prompt/compose/audit编排（等Task1停止）及config、新test_compact_summary_pipeline.py、test_config增mode验证。新增compat|compact默认compat；compact全源计划诊断交原audit，有限槽断言adapter→bank优先→normalize→refs/quality→parse_audit。必须MockTransport核对n+2、格式1、语义1共享2、source/provider/config/capacity0修复。新trace quality/protocol明确，不用改legacy历史checker。

### Task 5: 新冻结验收工具及独立复审

独立worker新quality report/scripts/evaluate/checker/rubric与新offline tests；所有实际8模块/hash完整，不更新旧工具。默认plan零网络；新budget group硬26/首19/normal13，exact ceiling只读关闭与原件核查仍可运行。singlecaller、typed身份、预占失败、raw和反馈、partial fail/full success默认分类重试均离线验证。root集成全量前先全变更独立复审，重要意见红绿解决。

### Task 6: root有限真实验收及文档

新freeze/一致性/默认分类修复后root唯一caller3真实源，所有失败计账。全14essential/精确性/组织按原标准，不能以metadata/true/ID覆盖评分。只在已定位离线修复后有限余量新phase，无自动补跑。更新当前handoff/索引/plan/预算状态；实际未完成必须明确剩余问题。
