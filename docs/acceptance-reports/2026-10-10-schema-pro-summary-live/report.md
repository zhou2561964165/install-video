# 原生 Schema/Pro 在线对照结果（2026-10-10）

工程约定：用户/AGENTS与适用skill优先；UI须ui-ux-pro-max/design-system及三层token；能力配置化、窄接口单向依赖，yt-dlp只经唯一服务层、视觉只读scene。成熟方案优先，保护凭据、本机账号配置及旧验收原件。

## 执行与边界

- 第三phase `source-first-summary-schema-pro-3`：root单caller真实串行6POST，全部HTTP200/completed；format/semantic附加均0，无探针、隐藏fallback或新框架。
- `deepseek-v4-pro`、Responses API、原生`json_schema`、reasoning none；沿用阶段分离生产提示、Pydantic与LCEL。多个配置共同变化，不能单因素归因。
- 短、中、长各points→overview两次；长文复用首phase已付费的两段笔记并结合完整原文，不重复付费提取。
- 本phase25728供应商tokens，父phase5POST/19776及6POST/28851保持原件；同工作组累计**17/17 POST、74355 tokens**，全部closed。没有货币费用推算。旧独立26/26工作组不变。
- 发前16项离线检查、独立代码/guard审查、186资产freeze/check均完成；执行后`--verify`确认闭账、全部响应/结果链及复用父3/4响应。`semantic_quality_verified=false`由内容审查单独处理。

## 实际内容结果

| 样本 | 结构 | 覆盖 | 内容结论 |
| --- | --- | --- | --- |
| zh-short | 5点，通过 | zh1–4 full | **通过**；概览与要点有互补细化 |
| en-medium | 6点，通过 | en1/en2/en4 full，en3 partial | **失败**；概览将通常书面反馈扩大为每节课后；缺账户读取；重复具体评分理由/反馈细节，独立文化表达归因不足 |
| en-long | 14点，通过 | long1–4 full，long5/6 partial | **失败**；缺表达式求值、radius/area具体因果及显式重算、明确下一讲衔接；安全建议及变量影响范围泛化 |

独立审查：[短中篇逐项证据](reviews/short-medium.md)、[长文逐项证据](reviews/long.md)。原完整标准见[验收准则](review-criteria.md)，没有降低必要子句、频率、归因或重复标准。长文概览高层职责与14点上限通过，笔记沿用本身不单独判失败。

本次修复了前两轮长文20点超过14上限的实际结构失败，但**没有解决整体内容质量**。三份已见回归样本不构成通用质量或统计准确率证明。`LLM_SUMMARY_GENERATION_MODE`默认保持`single`，没有更改用户`.env`、升级默认模型或静默增加产品成本。

## 原始证据与发布后的阅读

`results/provenance.json`及186份`snapshots`保存发前资产；`request-ledger.json`、`response-01..06.json`、三份结果/trace、`result-index.json`、`closed-receipt.json`保留执行字节。响应保留安全usage与assistant文本，未持久reasoning/密钥/认证头。

phase闭账之后，发布准备修改了项目当前文档及`backend/tests/test_schema_pro_evaluation.py`可移植夹具。测试从冻结snapshot恢复只读父预算，在tmp重绑定路径/哈希链并调用原完整校验器；37项检查与独立审查通过。原snapshot/调用脚本/raw不改。因当前文档/测试已变化，**不宣称此刻全部live文件仍等于发前冻结版本**；原在线结论绑定冻结候选，生产总结代码未再更改。不要重跑`freeze`/`--run`或删除账本恢复余额。

发布前集成检查另见[当前交接](../../handoff-2026-10-10.md)。语料来自MIT OpenCourseWare / Dr. Haohsiang Liao / Dr. Ana Bell；来源许可与归属见原corpus记录，适用CC BY-NC-SA 4.0。
