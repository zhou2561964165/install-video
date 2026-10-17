# Phase 6 Responses/checks验收工具独立审查

审查日期：2026-10-14。审查范围：新phase6专用runner `scripts/structured_checks_evaluate.py`及`backend/tests/test_long_structured_checks_evaluation.py`。审查者独立静态检查，没有修改文件、运行模型、freeze或启动服务。

## 结论

**Critical：0；未解决Important：0。** 可进行离线freeze/check，之后进入最多2 POST的有限phase6；内容是否修复P4仍须真实结果逐点评审。

审查确认：入口只接受`phase-6`，绑定已closed phase4的source/raw02/product/receipt哈希；核查固定走Responses `json_schema`，修订跟随冻结配置。实际每次发送前会重新验证冻结状态、runtime设置、endpoint、当前payload及全部前序payload/raw字节哈希，然后先持久预占group、ledger、tracker再POST。错误或模型漂移停止phase，不自动重试或付费回退。安全Responses收据只保存公开输出文本、完成状态、endpoint、预算及非负数值token usage，不存reasoning内容或未知provider字段。

phase6在计划、provenance与offline-check中显式记录`phase_post_cap=2`；组级总预算仍为用户授权的不设上限。既有`planned_posts=2`与固定stage guard保持一致。收据中的cap严格要求整数；重复check返回同一收据，篡改为浮点`2.0`会在check/run前被拒绝。

审查发现`candidate_assets()`最初遗漏新范围提示/修订回归；现已纳入`test_summary_scope_guidance.py`与`test_summary_source_revision.py`，并增加不替换实际资产清单的测试，防止再漏。phase6冻结资产同时要求设计spec、生产代码审查与本工具审查文件。

## 验证

最终phase cap和receipt类型检查后的工具测试为 **18 passed / 340.70s**，覆盖双endpoint、动态schema、预算、反馈传递、父/前序证据漂移、截断/错误停机、freeze schema、容量和安全receipt。单独新增的candidate_assets回归也先以1个明确失败确认遗漏，再在加入两文件后通过。

Minor：本runner新增回归未重复实现第三次请求、阶段间runtime drift、已占用共享锁及父group累计9次历史失败预占的全部组合；相关执行约束复用已审计的旧engine并在phase6检查中验证。此范围不影响固定两请求的phase6上限及父phase不变。

Runner SHA-256：`2d181d757d52374b054965b1b98bd0c14217e87b24061b3ea9cbcae1e7181c9d`  
Test SHA-256：`d01b1d9b801bcf6422ca5336a982ded92284469bd1ca08b2ce520222d73f9ddf`

本文件与[生产代码审查](phase-6-scope-check-production-final.md)、[整改设计](../../../superpowers/specs/2026-10-14-long-summary-scope-check-hardening.md)是phase6冻结所需的独立审查/设计资产。旧phase1–5脚本、结果、receipt与ledger保持原字节。
