# 最新生成指导完整复验计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. 按下列任务逐项实施。

**Goal:** 使用现有生产分段归纳与合并，验证尚未完整生成实测的类别/实例/代词指导。

**Architecture:** 新增很薄的验收入口，复用既有`evaluate.py`的会计、来源、codec、freeze/check、共享锁和真实summarize_text；不重新实现HTTP、产品管线或语义引擎。不再给旧坏草稿叠加核查字段。

**Tech Stack:** 已有Python、Pydantic及受控httpx；不加依赖。

**Spec:** 复用`2026-10-13-long-summary-fidelity-design.md`的来源忠实目标及`2026-10-14-subject-scope-relation-checks.md`中已落地的通用生成指导。用户后续要求优先：产品默认字幕总结、不增无意义协议、逐phase有限。

## Global Constraints

- 工程约定：成熟组件优先、窄接口/单向依赖；保护UI/账号/env/本地模型和历史原件。UI如改须ui-ux-pro-max/design-system及三层token。本次不改生产、UI或旧脚本。
- 用户已持续授权继续整个整改，不设总POST/费用上限；本阶段cap=3，全部真实尝试预占/root共享锁/错误即停，无自动重试或付费fallback。
- 只测已见MIT Lecture1，重新两个leaf+merge，不复用已付费旧错误笔记。尚不发未见源或短中请求；已见通过后再分别登记有限3/2POST。
- 原长文组当前11POST/174972tokens全部closed；Ragas组16POST/34106tokens closed。新phase8承接旧组计数，不重开任何旧phase。
- 明确legacy/adaptive/single/fidelity=off，正常输出base4096/ceiling8192、thinking=auto/response_format=auto；验收format/semantic/extra均0。保留已有source notes/auto完整上下文、chunk/input/point上限。
- provider/model/endpoint沿现有Settings.from_env，不静默切Pro或修改env；freeze记录实际值。不把此前Pro judge对照写成正常默认模型。
- 不提交、推送、部署或恢复公开长文入口。

## Review Focus

- 新入口不能继承旧thinking enabled/16384–24576输出实验，或默默覆盖环境中的model/provider。
- 代码/测试/review/计划及通用scope指导测试均纳入freeze；已消费payload/raw任一漂移必须在下一POST前拒绝。
- mock仅允许system-temp内owned PROJECT/结果/锁，不得触及原工作区或其祖先。
- root caller审计声明在任何live状态写入前检查；help/plan/check/verify不读dotenv、不发HTTP。
- stage arity始终3，两叶原source与merge完整上下文须按实际生产代码生成；程序检查不替代P4/core独立内容评分。

### Task 1: 正常profile薄适配与离线验证

**Files:** Create `docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/normal_evaluate.py`、`backend/tests/test_long_normal_evaluation.py`。其余旧脚本、生产与测试只读。

**Interfaces:** 复用私有导入的`evaluate.py`实例及其`select_phase/plan/freeze/check/run/verify_results`。CLI保留`--phase`及动作，live须`--caller root`和环境审计声明`CODEX_ACCEPTANCE_CALLER=root`。snapshot增加自身、测试、本计划、`backend/tests/test_summary_scope_guidance.py`、phase7生产审查和新的独立工具review。

- [x] 先用有限、隔离的离线测试观察RED：profile不继承旧实验；root/mock guard；包清单覆盖；发前前序原件校验。
- [x] 以最小适配复用旧engine，保留其持久预占、一次phase与phase3阶段边界，不复制freeze/run引擎或新协议。新入口159行，不改旧脚本。
- [x] 新27项+旧engine41项集成由实现者执行68 passed/32.24s；root独立新27 passed/5.30s。没有重跑生产/前端全量。
- [x] 独立review最终C/I/M均0，审查者必要subset9 passed/18 deselected；报告`reviews/phase-8-normal-generation-tool.md`。用户已要求自主继续，不再以计划确认停工。

### Task 2: root有限真实验收与内容审阅

- [ ] phase8 plan/freeze/check，先核对cap3及实际model/provider/output profile。旧父组11与Ragas16保持可追踪。
- [ ] root唯一caller执行最多3POST，首错停并封账，离线verify原件；没有错误才审完整最终结果。
- [ ] 独立审阅新叶笔记及合并中的P4首次范围变化、原6核心、overview/组织和逐断言精度。结构或Ragas高分不作为语义通过。
- [ ] 更新报告/当前文档，准确区分已见、未见与短中范围；本phase失败不得重跑或宣传修复。

冻结后的执行状态在`.planning/2026-10-15-ragas-evaluation/progress.md`和phase8报告更新，本计划作为冻结候选资产保持不变。
