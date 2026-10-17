# 完整来源单次总结诊断

工程约定：成熟组件与窄接口优先、单向依赖，保护用户工作/凭据/账号/UI/本地模型及旧原件。UI如改须ui-ux-pro-max/design-system与三层token。本计划只建开发验收候选，不改变默认产品入口。

## 证据与目标

phase9/10都在 Pro/Responses schema下接受14点结构，但合并仍保留第一leaf的11点，遗漏第二leaf多主题。`_section_notes`及source preparation检查表明两叶notes完整序列化、source_context完整，未发现本地截断或有序重排；phase10仅加426字符通用提示无效。当前cleaned transcript为34894字符，低于生产输入上限60000。

做一次直接来源诊断：用已有`_summary_request(full_source, merge=False)`，只输入完整source，不用section notes，测试现有生成服务能否在一次请求内覆盖完整long core。固定deepseek-v4-pro、Responses `json_schema`、reasoning none、max_output_tokens=8192、maxItems=14、fidelity off、无format/semantic/extra。相较phase10，实验变量是whole-source direct request path（prompt职责与notes/source packaging随路径变化）；不能把结果单独归因“去掉notes”，也不能视作默认Flash或分段产品修复。

## 有限phase边界

新phase11 cap=1 POST。历史开始累计：长文组phase1–10为16 POST/232851tokens，Ragas独立组16/34106，合计32 POST/266957tokens；旧67 POST另封账。换GPT账号不重置。root唯一caller/共享锁/发前持久预占/错误即停，无重试/fallback；不复用phase9/10失败输出作输入。本阶段source只来自原授权MIT Lecture1，完整norm/text SHA绑定，模型/数据无其他样本。

## 实施范围

- 新`direct_source_evaluate.py`薄runner和`backend/tests/test_direct_source_evaluation.py`。优先复用现有生产`_summary_request(...merge=False,source_chars=len(text))`及HTTP/schema/codec/accounting engine，不复制HTTP、预算或Responses解析层，不增加依赖。若要适配旧runner，使用私有窄adapter，不改phase8–10冻结脚本。
- TDD测试完整normalized source等于冻结原文，wire没有生成notes或前序草稿，仍有14/8192和Responses schema；预留只允许1 POST，完整原文超60000则发前拒绝，无截断/fallback。绑定phase10 closed计数16及其receipt用于历史完整性，不把phase10产品放入本请求。
- 调用与响应、parent/candidate assets、freeze/check/verify、caller/mock guard、必要的独立工具review纳入完整hash；phase11结果能从本phasesnapshot离线重放。source、许可manifest及全部历史父证据不改。
- 独立审查后root plan/freeze/check；仅1 POST。对core long1–6、逐断言精度、范围、summary/组织独立评分；完整来源直入模型只证明这个已见direct候选，不替代之后的正常分段Flash或未见/短中回归。

先完成代码/离线审查再run，禁止把本计划或fixture伪造结果称为模型通过。无论本轮结果如何，默认`legacy/adaptive/single/fidelity=off`、公开20000字符上限及长文暂不支持不改变。没有发布、提交或部署授权动作。
