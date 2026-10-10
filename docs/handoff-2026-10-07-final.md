# 总结质量收尾交接（2026-10-07 final）

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](design.md)和[需求/实施状态](requirements.md)为准，当前任务与预算见[自适应交接](handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

本文件接续 [refined 交接](handoff-2026-10-07-refined.md)。用户已明确要求多 agent 并行继续，优先收尾总结质量；随后在明确13POST与费用请求后回复“继续”，本轮一次真实验收已执行并按首次错误停止。实际9/13，余4不用；质量尚未收尾。

## 工程约定

技能优先；UI/视觉/交互先 ui-ux-pro-max、design-system 和 primitive → semantic → component 三层 token。颜色／字体／时长走 token，能力配置化、窄接口单向依赖，避免大规模重构。LLM 仅 llm_service.py、yt-dlp 仅 ytdlp_service.py，视觉只读 scene，不修改下载状态或导入下载核心。用户 .env／db／模型资产保持，历史原件与预算不覆盖、不借用、不重置。默认 legacy，正常 n+2，无自动重试或隐藏付费回退。MIT 来源与衍生评测保留署名、CC BY-NC-SA 4.0 非商业和相同方式共享要求。

## 当前实现与验证

- 生产局部修改仅 llm_service.py：通用复合子句完整表达、同主题原则和说明归并、来源→最终文字反向覆盖核查；audit 输入增加程序计算的 missing_core_fact_ids。引用列表为空仍不证明语义完整。
- codec／config 与本轮开始时字节一致；候选最多14条／1600字符，最终最多7条／800字符，points最多7个／每点240字符不变。公开API、默认策略、模型阶段数不变。
- 覆盖定位测试3项有红→绿；真实refined长原件回放6项确认完整55facts／5sources／8候选声明1060字符可以进入第7audit，缺失core为F2_3，失败后无重试。回放不证明模型语义成功。
- 主agent完整后端 `pytest tests -q -p no:cacheprovider`：540 passed／1既有Starlette弃用warning（11.35秒）。裸pytest误收集旧backend/tmp权限目录，已改用完整源码tests目录，无权限调整或删除。
- 生产增量和新入口各自独立复审无Critical／Important／Minor缺陷；新入口52专项、新旧守护组合144专项通过。
- 三个旧台账48/49、12/13、12/13的本轮初始与交付哈希一致。准备阶段POST=0记录保留；本轮真实9/13，工作区尚未新建提交，实测后未再改生产代码。

完整范围见[本轮报告](acceptance-reports/2026-10-07-grounded-summary-final/report.md)。

## 新真实验收结果

新phase为 organization-final，独立目录和13POST上限；final→organization→base有效runner链、检查器、生产模块、配置、提示、codec、原rubric与三源完整冻结。原14essential标准没有更改、没有注入产品提示。主agent已执行零网络freeze，check-only match=true。

主agent沿用前轮已测system-proxy，串行运行一次。9次预占/9HTTP200/32656供应商报告tokens，短3、中3、长3；长第3段extract完整JSON返回13facts超过冻结上限12，invalid_count。前19facts有效，但尚无compose/audit/final。余4不使用、phase不重启。始终n+2正常计划，失败按原件保留。

| 样本 | 最终结果 | 核心事实 | 组织/精度 |
| --- | --- | --- | --- |
| 短 | 4点/239字符摘要 | 4full | partial：原则与准备说明可合并 |
| 中 | 5点/258字符摘要 | 3full/1partial | 录入成绩仍漏；组织partial；汉字姓名缺允许来源支持 |
| 长 | 无最终结果 | 6not_evaluated | precision/organization未评 |

相比refined短中5full/3partial，本轮7full/1partial，改进目的/发音/账户读取恢复；中篇原组织pass退为partial，不能宣称全面改善。短中reviewer参与提示修订已披露，另一未改生产的agent交叉核对同意；不是外部人类盲评或统计准确率。完整14项汇总见[语义审核](acceptance-reports/2026-10-07-grounded-summary-final/results/organization-final-semantic-review.json)，本轮结果见[measurement-delivery](acceptance-reports/2026-10-07-grounded-summary-final/results/measurement-delivery.json)。

本phase只允许以下只读复查，不能再run、freeze或write覆盖原件：

```powershell
# 当前代码仍与本轮freeze匹配；未来增量修改后失配属于预期
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-final/scripts/evaluate.py --check-only
# 核对原件哈希/来源/预算/冻结codec，零网络且不写已有检查文件
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-final/scripts/check_evidence.py
```

单caller串行、每次发送前持久预占，包含所有抽取／组织／核查和失败尝试；证据/台账/阶段与tokens完整对账。caller锁已释放，三个旧账与全部测量hash未变。check-only内部读取本地供应商配置，不打印或保存API key；本轮没有额外模型连通性探针。

## 真正完成条件

新长文必须实际经过audit并获得满足最终合同的输出；独立逐子句核对原14核心事实，另检查出现的可选细节、归因／频率／范围和主题组织。前轮中篇遗漏仍是尚未真实证明修复的问题。HTTP200、fact IDs、checks=true、字数减少和离线测试均不替代语义验收。

没有最终结果记not_evaluated，不补成功，不把旧失败改称成功。当前不推广facts/auto，不计本轮前端或浏览器重新验证，不做支付／队列／ASR等扩展。

连续三轮失败从候选字符→候选声明数→extract事实数迁移，先看[生成合同复审](acceptance-reports/2026-10-07-grounded-summary-final/contract-review.md)，确定有限生成结构与全局主题分配，再局部实施/零网络回归/新phase/明确新预算。不能继续靠放宽上限、删第13条或自动失败重试换通过。本复审仅提出方向，未实施新协议、未发新预算请求、未另建真实phase。
