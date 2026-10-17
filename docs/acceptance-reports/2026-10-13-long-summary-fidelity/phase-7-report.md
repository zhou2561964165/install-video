# phase7 主体范围核查实测：失败封账

工程约定：成熟组件优先、窄接口/单向依赖；UI如改须ui-ux-pro-max/design-system三层token。本轮不改生产默认、UI、账号/env或本地模型，保留全部历史原件。

2026-10-15恢复执行此前已冻结的subject_checks候选。原plan/freeze/offline-check及独立审查沿用；发前只复核live资产与原check收据，没有重新freeze或重跑旧测试。provenance SHA256为`2551dfb2d8a30c00981d436b32519cb2c432ee2181c1cb1232671fc446754d79`，phase cap2，复用closed phase4的完整来源和旧草稿，原错误phase6不作为修订输入。

## 实际结果

**仅1 POST / 14164供应商tokens（input12708、output1456），随后首错停止并closed。** HTTP完成，15个target字段均返回，但`target_6.source_quote`超过120字符、`target_9.source_subject`超过64字符，动态Pydantic校验失败，产品报`llm_invalid_response`。没有第二次修订、没有新最终产品结果；不能把原raw当通过结果或重开本phase。

root运行`subject_scope_checks_evaluate.py --phase phase-7 --verify`返回exit0、evidence_hashes_verified=true、phase_closed=true、posts=1、work_posts=11、stopped_on_error=true、semantic_quality_verified=false。这是原件一致性验证，不是内容通过。[产品失败](results/phase-7/en-long.json)、[raw](results/phase-7/response-01.json)、[台账](results/phase-7/request-ledger.json)、[封账收据](results/phase-7/closed-receipt.json)保留原字节。

## 原响应中的语义问题

对父phase4草稿的P4，`target_4`仍给`assessment=supported`、`scope_relation=same`，选择`source_subject=fixed-program computers`与`draft_subject=固定程序计算机`，引用只介绍该类别存在的句子。该引文没有包含“只懂四则/不能绘图或上网”的谓词，实际来源把这些限制挂在随后举出的具体旧计算器上。核查只是对齐了相同名词，没有核对同一谓词的主语范围，**P4仍未解决**。

此处是对未接受raw的诊断，不作为最终assessment或修订输入。放宽两个长度限制只会改变机械结果，不能修复该语义漏判，因此不为取得通过而放宽，也不继续增加字段。

同日独立成熟方案[Ragas校准](../2026-10-15-ragas-semantic/report.md)也在保留错误类别主语后误放P4；失败在NLI范围推理，不是换框架即可消除的问题。需要区分尚未实测的最新生成指导与反复核查同一旧草稿，后续正常完整生成按独立有限phase准备。

## 计数与交付边界

原长文组phase1–7现在全部closed，累计**11POST / 174972tokens**；独立Ragas组closed16POST/34106tokens。两项合计本次持续整改27POST/209078tokens，旧67POST各组另外保留，不清零、不借用。用户未设整个任务总费用/POST上限，后续phase仍须先记录有限上限、用途与台账，root共享锁串行、发前持久预占、错误即停。

默认仍legacy/adaptive/single、fidelity=off，公开20000字符限制和长文暂不支持不变。本轮没有提交、推送或部署。
