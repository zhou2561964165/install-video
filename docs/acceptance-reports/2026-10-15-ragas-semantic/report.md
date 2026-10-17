# Ragas 独立语义评测校准

工程约定：优先成熟组件，通过窄接口单向依赖接入；不修改下载核心、UI、账号/env或本地模型。UI工作须使用ui-ux-pro-max/design-system与三层token；全部历史验收原字节保留。

## 目的与范围

用户批准采用成熟方案检查总结的语义忠实度。本轮真实接入Ragas 0.4.3的`ragas.metrics.collections.Faithfulness`，使用官方断言分解、NLI提示和评分；自定义代码只负责受控LLM适配、严格结果绑定、有限caller及证据保存。独立uv项目见[工具说明](../../../tools/semantic_eval/README.md)，不升级生产依赖。

Ragas先从响应提取断言，再根据完整source逐条判断支持关系。[官方Faithfulness说明](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)支持这一流程，但不能证明跨语言断言分解保留了原错误，也不衡量摘要遗漏的主题。本轮逐条保存原响应、分解断言、verdict/reason并人工比较；`all_supported`只表示模型全部给1。`core_questions`没有传给judge，也没有在本轮自动评分。

八个预先标注样本为4正/4负：实例→类别范围、四周→全年时间范围、不能确定因果→确定否定因果各一对，另有MIT Lecture1 phase4 P4原错误点/局部主体纠正点。合成来源更明确，结果不代表自然长文、完整生成或未见来源通过。标签不进入提示；原MIT来源34894字符完整使用，原坏点与closed phase4产品逐字相同。资料与许可见[标注说明](../../../tools/semantic_eval/CASE_NOTES.md)和[源绑定](../../../tools/semantic_eval/bound_sources.json)。

## 调用边界与历史

新phase最多16 POST（8样本×2），每请求4096输出tokens、60000完整prompt字符；root共享旧caller锁串行、发前持久预占、零重试/零fallback、首执行错误停并封账。用途为上述已定位问题的正反校准，不是无限生成。用户不设整个整改任务的总POST/费用上限，此phase仍有有限上限。

新freeze绑定旧长文组10POST/160808供应商tokens及phase7 frozen/0POST的hash，不修改它们。历史67POST各组也保持封账；更换GPT账号不重置供应商计数。phase7既有生产候选本轮不run、不重freeze，默认legacy/adaptive/single、fidelity=off及公开20000字符限制不变。

## 离线实现与检查

- 独立依赖固定Ragas0.4.3和langchain-community0.3.31：Ragas仍导入新版已移除的vertexai模块，后一固定用于兼容。全部依赖在工具uv.lock，根pyproject/uv.lock未修改。
- 真实Ragas入口、严格0/1类型、逐断言完整唯一绑定、同实例失败锁定、禁止label注入以及fresh-process无外连均有离线验证。Windows asyncio只在封锁网络前预建本地self-pipe；provider/DNS/telemetry没有连接豁免。
- caller在发送前保存预算预占，冻结/旧证据/依赖漂移拒绝；原始及JSON解码后的凭据回显在raw落盘前拒绝，状态/model/重复键/截断等均首错停。
- 初次freeze在创建目录前拒绝环境中两个不在最终lock的遗留包（langchain-classic1.0.8/text-splitters1.1.3）；离线`uv sync --frozen --offline`移除后重新验证。没有绕过依赖门，代码与锁文件未改。
- root精确locked环境完整工具套件：`tools/semantic_eval/.venv/Scripts/python.exe -B -m pytest --noconftest -p no:cacheprovider tools/semantic_eval/tests -q --tb=short`，**78 passed / 17.68s，exit0**。日志`tmp/ragas-locked-offline.log`。没有重跑生产/前端历史全量或启动服务。
- [独立审查](../../../tools/semantic_eval/review.md)最终Critical/Important/Minor均0；审查者定点4项及真实Ragas无外连探针独立通过。review SHA256为`367e67eda7502960494ac571388beb1b9b40d29fa22ad2176fe7c5c1a8c7a680`。
- freeze/check已完成：20项资产、99个已安装包版本匹配，provenance SHA256为`c9f5202007a54bb3dd9bce633fd805cff375e62cb8b09528c92a0a1a08a3d731`。[离线记录](results/phase-1/offline-check.json)明确network=false、dotenv_read=false、cap16。

## 真实结果

phase1已完成并closed：**16/16 POST，34106供应商tokens（input31864、output2242）**，没有格式/语义修复或隐藏重试。root执行`runner.py --verify`返回exit0、closed/completed/16、network=false，逐例重放官方metric并核对冻结提示/schema、raw、评分、账本与closed receipt。原件见[结果](results/phase-1/result.json)、[台账](results/phase-1/request-ledger.json)、[封账收据](results/phase-1/closed-receipt.json)。

| 样本 | 人工supported | score | all_supported | 对照结果 |
| --- | --- | ---: | --- | --- |
| synthetic_scope_supported | true | 1 | true | 正确接受 |
| synthetic_scope_unsupported | false | 0 | false | 正确指出实例→类别扩大 |
| synthetic_time_supported | true | 1 | true | 正确接受 |
| synthetic_time_unsupported | false | 0 | false | 正确指出四周→全年扩大 |
| synthetic_negated_attribution_supported | true | 1 | true | 正确接受 |
| synthetic_negated_attribution_unsupported | false | 0 | false | 正确指出不确定→确定否定 |
| mit_phase4_p4_original | false | 1 | true | **错误放过P4** |
| mit_phase4_p4_scope_corrected | true | 1 | true | 正确接受局部纠正点 |

本次八例有**1次误放、0次误拒**；六个合成例正确不能覆盖真实P4失败。原P4的分解保留了“固定程序计算机只懂四则”和“固定程序计算机不能绘图/邮件/上网”两个类别断言；NLI仍给1，reason仅把具体calculator例子的谓词视为类级证据。因此这次失败发生在NLI主体范围推理，没有发现分解偷偷修正原错误。四则以外的其余存储程序断言均有来源；局部纠正点的主体保持为讲座中的旧计算器。

更细的独立人工对照见[语义审阅](semantic-review.md)；该报告只审本次八例，不证明完整摘要和未见来源。

## 交付边界

工具是开发评测候选，**这轮结果不足以把默认Faithfulness接为生产阻断门**，未增加产品模型步骤或成本。已采用成熟引擎并不消除所用模型的范围推理缺陷；不会以更换框架或调高平均分宣布修复。P4以及完整长文/未见Lecture2/短中回归的产品质量仍未通过；本轮没有提交、推送或部署。
