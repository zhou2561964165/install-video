# 历史阶段交接：长文整改与语义评测（2026-10-15）

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页的“当前/下一步/待实现/等待授权”、预算、测试与服务状态均指记录当时。最新用户决定、活动任务与全部后续计划先读[统一总表](follow-up-plan.md)，phase15证据读[阶段交接](handoff-2026-10-16-deepseek-step1.md)；产品实际实现参照[设计](design.md)、[需求](requirements.md)和[UI指南](ui-extension-guide.md)。长文已获准上线使用但质量仍待整改，现有公开20000字符保护和embedded区域约束尚未在本轮调整。历史候选统一汇入总表，不据旧待办启动开发/服务/模型或重开closed phase；原验收及冻结证据保持原字节。

> **本页为阶段回顾。** 当前状态以[2026-10-16完整交接](handoff-2026-10-16-deepseek-step1.md)为准：phase15已完成固定DeepSeek的第一步，后续等待用户指示。本页的设计、调用和评分按各自冻结候选解释，不重开phase、不执行旧待办。

工程约定：适用skills、成熟组件优先、配置化窄接口/单向依赖；yt-dlp唯一层、视觉只读scene；UI使用设计技能和三层token。保护账号/env、已有UI、本地模型和历史原件；发布按既有隔离过滤流程排除Live2D模型历史。

## 阶段演进与真实结论

| 阶段 | 当时实际调用 | 真实结论与原始证据 |
| --- | --- | --- |
| phase1–5 | 9POST/147600tokens | 实例范围泛化未解决；phase5响应截断、无第二修订。见[原报告](acceptance-reports/2026-10-13-long-summary-fidelity/report.md) |
| phase6 | 1/13208 | checks引用大小写不匹配后首错停止，旧P4仍漏判；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-6-report.md) |
| phase7 | 1/14164 | subject字段/引文超长后停止，无修订结果；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-7-report.md) |
| phase8正常Flash | 3/28376 | 两叶11/9点，merge20超14拒绝；未接受raw不能转记产品通过；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-8-report.md) |
| phase9 Pro/schema merge | 1/14710 | 14点结构通过，内容4full/1partial/1missing，尾部缺失与精度/组织FAIL；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-9-report.md) |
| phase10 merge提示对照 | 1/14793 | 新提示未改变要点映射/遗漏，时间回退，不能反复同义提醒付费；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-10-report.md) |
| phase11完整来源直入/schema | 1/10809 | 4full/2partial，precision FAIL、overview/organization PASS；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-11-report.md) |
| phase12仅14→15点 | 1/10984 | 5full/1partial，precision仍FAIL；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-12-report.md) |
| phase13用户直接委托 | 1/15498 | 全文34894字符、自由text/high、输出5206字符。调用时未评分，后续审阅六core full但精度/局部重复FAIL；[执行报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md)、[后续审阅](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-content-diagnosis.md) |
| phase14 A/B组合 | 2/26054 | 输出8293字符，补齐两项课程路线，六core full；时间/末尾范围和重复仍FAIL；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-14-report.md) |
| Ragas独立工具 | 16/34106 | 八例误放1/误拒0，真实P4与纠正版同获1.0；不能作放行门；[报告](acceptance-reports/2026-10-15-ragas-semantic/report.md)、[语义审阅](acceptance-reports/2026-10-15-ragas-semantic/semantic-review.md) |

本页截至phase14：长文21POST/296196tokens，加Ragas后37/330302；**这是历史累计**。phase15后当前累计为长文23/319471，含Ragas39/353577，旧67另封账。全部phase已closed，不能从本页阶段预算推导剩余额度。

## 方案与实现适用时点

- 相邻重复折叠、source-language notes、可容纳时完整来源merge和显式保真候选已在代码中实现；默认仍legacy/adaptive/single/fidelityoff。输入处理与动态schema都不是语义证明。
- 普通分段Flash、Pro/schema、全文直入、自由输出和组合规划是不同冻结候选，不能互相继承质量成绩或混为默认产品路径。
- 纯B的独立主题规划→逐主题写作→概览仅保留设计，未实现/实测。phase14的组合是标题规划后全文生成，区别于纯B；见[路线记录](summary-route-decision-2026-10-15.md)。
- Ragas只在隔离的`tools/semantic_eval`中采用已有成熟Faithfulness，不在生产依赖或放行流程中；无需因框架名称更换重做已经失败的语义判断。
- 旧“先A后B”“下一步freeze/check/run”是当时决策；后来用户要求结合，并最终限定只DeepSeek完成第一步。现在等待后续指示。

## 历史验证与证据边界

Ragas78项、subject相关121项、phase7工具26项、normal入口27项、phase11工具34项、phase12工具42项、phase14工具32项分别对应原阶段的离线结果。它们不代表本轮重新全量测试，也不代替逐断言内容评分。phase15的新24项与两来源结果见[当前报告](acceptance-reports/2026-10-16-deepseek-source-screen/report.md)。

冻结源码、prompt/config、raw、ledger、receipt、review和失败原件保留原字节。原执行报告中的“未评分”保留调用时点事实，后续审阅通过当前索引链接解释；不回写历史PASS/FAIL，不要求当前所有live文档哈希仍等于旧freeze。

公开20000字符长度保护没有恢复；Pro实验未升级默认/env，未提交/推送/部署。UI、本地模型与既有功能保留，相关状态按[综合交接](handoff-2026-10-10.md)及当前设计/需求阅读。
