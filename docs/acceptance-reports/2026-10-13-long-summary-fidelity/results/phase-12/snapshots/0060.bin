# Phase 12 adaptive 要点容量对照工具独立审查

审查日期：2026-10-15。结论：**Critical 0 / Important 0 / Minor 0**。本次只审工具边界及冻结输入差异，不表示15点候选语义质量通过。

工程约定：优先复用已验证的生产摘要请求、Responses/schema、冻结、预占、封账与snapshot replay接口；不改生产代码、默认配置、用户账号/env、UI、本地模型或既有closed phase。没有提交、推送、部署。

## 范围及版本

只读检查 `scripts/direct_source_capacity_evaluate.py`、`backend/tests/test_direct_source_capacity_evaluation.py`、`docs/superpowers/plans/2026-10-15-direct-source-capacity-check.md`，并沿phase11 direct adapter/native freeze和通用engine的freeze/check/run/close/verify、shared lock、root/mock guard及Responses parser调用关系复核。审查前后哈希一致：

- runner：`8f3c666ac945c61628cb6e50bd624964828632b2a9f3d4544ce8731bedec902c`
- tests：`b720ba0419a663d0b4e3280f048bb69d9c69f01c6184bc3d13fe3f082a8a0d35`
- plan：`16201861bd9ced64c48477280386da1fb51972ca2664a7fefd35db19ed25a2f1`

审查者未修改文件、运行测试、freeze/check/run、读取env或发送POST。实现者报告42项离线测试通过；reviewer未重复运行。

## 审查结论

- 新入口仅能分配phase12、cap=1 POST，要求phase10/11均closed且工作组累计17；旧阶段不能通过CLI或目录名重新分配。source identity仍绑定phase10唯一MIT来源。
- Phase11完整响应只用于历史封账/对照。新请求payload投影必须逐字段等于phase11冻结payload，唯一允许变化是自适应预算中的14→15文字以及`key_points.maxItems`；source全文、prompt其余内容、模型、provider、Responses格式、reasoning、8192输出上限、语言、输入路径和额外调用数保持一致。生产`_summary_budget(34894)`需真实计算15点/8192，而非手填schema绕过公式。
- phase10和phase11的tracker、ledger、receipt、index、provenance、product、payload、raw逐字节hash绑定到phase12快照，并验证closed receipt链和请求结果hash；父product/raw仅作对照，不放入本次模型输入。完整MIT source/VTT/manifest/许可归属保持绑定；身份或历史证据漂移在分配/POST前拒绝。
- native freeze的历史stage标签仍为`merge`，样本`request_path=direct_source`及`merge=False`识别真实路径。freeze hook仅在新冻结内存对象构造时将stage max_points投影为捕获schema值；后续check/run/verify只校验已冻结snapshot，不再改stage元数据。单请求、cap1和相同payload条件相互校验。
- run先执行root caller/mock guard，随后使用共享锁；成熟engine先确认snapshot/runtime/payload与冻结一致，再持久预占group、ledger、tracker后发送。网络/provider/incomplete/点数越界错误首错停、不重试、不fallback；第二次POST在第二次预占前拒绝。verify基于新快照回放phase10/11历史证据，不依赖live历史响应变化来改写本次证据。
- 测试清单覆盖容量公式、payload差异投影、完整source、历史漂移、累计17/cap1、预占先于发送、错误封账、第二次调用拒绝、caller/mock路径隔离及offline verify。以上边界通过仍只证明验收工具完整，不能证明模型会保留long1–6必要子句或实现精度/组织目标。

## 验收边界

phase12尚待root复核计划、freeze、offline check及最多一次真实请求。无论结构是否接受，raw必须另由独立内容审阅依据冻结字幕评分；`semantic_quality_verified=false`、合法15点schema或逐字段snapshot replay通过都不能写成长文质量解决。默认继续legacy/adaptive/single/fidelity=off、14点上限和公开20,000字符保护。
