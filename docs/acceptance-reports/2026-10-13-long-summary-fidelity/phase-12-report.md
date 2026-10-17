# Phase 12 有限要点容量对照结果

2026-10-15：**cap1已用完并封账；结构通过，内容FAIL。** 本阶段在phase11完整原文直入路线中只将adaptive要点上限14改为15，检验容量假设。来源、模型、输入路径、提示模板、8192 token上限及其他参数相同；payload比较仅允许两处预算文字和schema maxItems相应变化。

工程约定：复用成熟生成/解析/冻结/台账接口，窄适配与单向依赖；yt-dlp唯一层，视觉只读scene；UI须ui-ux-pro-max/design-system和三层token。保护已有UI、账号/env、本机模型和closed证据。未改产品默认、提交、推送或部署。

## 执行与证据

新工具 `scripts/direct_source_capacity_evaluate.py` 复用phase11 adapter与已有engine；phase10/11的封账数据只作输入身份和会计对照，不输入模型。仅新phase12可分配，source绑定同一34,894字符MIT Lecture1；生产公式计算15点/8192输出。

实施者离线测试：`python -B -m pytest --noconftest -p no:cacheprovider backend/tests/test_direct_source_capacity_evaluation.py -q --maxfail=1`，**42 passed /240.89s**。另真实MIT预算单项通过，属于42项中的同一项，不额外累计。曾观察缺runner的RED及fixture漏bind错误，修正后全套通过。root未重复执行整套；独立只读工具审查C/I/M=0/0/0，见[审查](reviews/phase-12-capacity-tool.md)。

root实际完成plan→freeze→check→run→verify。check记录network=false/dotenv_read=false；run为root单caller、共享锁、发前持久预占，HTTP200/completed，**1 POST、0重试、0 fallback**。返回15点被结构接受。verify确认closed与快照哈希，work_posts=18、semantic_quality_verified=false。

供应商deepseek-v4-pro：input9989/output995/total10984 tokens，cached0。Pro/Responses json_schema、reasoning none、fidelity off。provenance SHA `0656638e99b8a64ba7c834e7f92c30bba82c83ae360c8b2d000f427e27babb5c`；response SHA `38cabd188295b10ab87c33bb89d518e2fd2bfff93ed9a4dec5d7d0b370019a6b`；product SHA `c7a7c173e09a855f9b92cd4994bbb271eeda11f59465fc95a2efec1757e51f97`。

## 内容结论与下一步

[独立内容诊断](phase-12-content-diagnosis.md)：long1–5 full、long6 partial，precision FAIL，overview/organization PASS。类型决定操作恢复，radius/area主体明确；仍漏显式重执行area与下一讲。新错误是P11把word+5判为语法无效，以及P15把加减乘结果类型规则扩到除法。提高一条要点额度没有实现质量目标，不能据此继续机械增加点数或宣称容量是根因。

下一步为零POST方案审计：复用已确认成熟组件研究，评估全局主题组织后按主题写作的独立职责与输入边界，区别于历史同响应theme_plan及points→overview。该方向尚未实施，不新增公开facts协议，不把计划或Ragas高分当语义门。任何后续真实阶段需独立理由、有限cap、离线验证与审查后再分配；phase12不可重开。

长文组phase1–12共**18 POST/254644 tokens**，Ragas另16/34106；持续整改共**34 POST/288750 tokens**，旧67 POST另封账。换账号/网络恢复不清零。默认legacy/adaptive/single/fidelity off、14点和公开20000字符限制保持；默认分段Flash、未见长文与短中回归未由本次验证。

来源Dr. Ana Bell / Massachusetts Institute of Technology / MIT OpenCourseWare，Lecture 1: What is Computation?；来源及派生审阅沿冻结manifest保留CC BY-NC-SA 4.0，MIT不背书输出。此次只评已见来源的单次候选，不是统计质量保证。
