# 有限生成合同交接（2026-10-08）

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](design.md)和[需求/实施状态](requirements.md)为准，当前任务与预算见[自适应交接](handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

用户要求多agent并行继续后的本轮开发与离线验收准备已完成，当前新真实13POST预算确认已提出，尚未获答复。项目总结质量目标仍未完成，不能把706测试或结构计划当语义质量通过。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system和primitive → semantic → component三层token，颜色/字体/时长走token。能力配置化、窄接口单向依赖，避免大规模重构；LLM仅llm_service.py、yt-dlp仅ytdlp_service.py、视觉只读scene，不改下载状态或import核心。用户.env/db/模型资产和历史证据/台账保持。默认legacy、正常n+2、无自动失败重试/隐藏付费回退。MIT来源和衍生评测保留署名与CC BY-NC-SA4.0非商业/相同方式共享要求。

## 当前改动

- 新parse_extraction要求默认12个配置化fact槽，至少第一槽有效，闲置只能尾部null，未知/缺失/间隙/重复字段/嵌套对象字符串拒绝；保留所有来源校验，不删第13事实挽救历史失败。
- 新parse_planned_composition要求同一次compose返回默认7主题槽，含原则/条件/后果与fact IDs；对应point引用属于主题。ThemePlan/PlannedComposition不可变，新trace/audit输入带完整主题计划。
- 旧纯parser、公开summary/key_points/provider/model、原audit输出合同及legacy/translation行为保持；模型阶段仍n+2。
- 默认候选摘要14条/1600字符，最终7条/800；candidate point≤7、沿用既有max(claim,point)默认600修订余量；final point≤7/240不放宽。主题计划和引用关系不证明最终必要含义已表达。
- 新独立organization-contracts入口绑定final/org/base及checker全链hash；strict artifact JSON、精确int身份/计数、类型敏感raw→trace→audit绑定，发前预占/共享单caller锁/首次错误停止及phase排重保持。旧代码与余额不改。

## 验证与源状态

主agent完整后端706 passed、1既有Starlette弃用提示（20.34秒）；最终整体审查和fix scoped复审通过，无剩余C/I/M。曾检出嵌套string、非法fixture尾None、JSON重复字段、bool/float身份及嵌套整数别名，均真实红→绿并独立复审，具体见[本轮报告](acceptance-reports/2026-10-07-grounded-summary-contracts/report.md)。

351历史文件与用户.env/db本轮初始哈希保持；用户资产未编辑。工作区尚未新建提交，不使用无范围git add -A。原git基线33dc239不能代表本轮未提交实现，准确模块/源码hash见[code-delivery](acceptance-reports/2026-10-07-grounded-summary-contracts/results/code-delivery.json)。前端/UI未改，本轮不声明重新跑过浏览器或前端全量。

## 新phase与预算边界

新organization-contracts已零网络freeze，check-only match=true；目前只有provenance、三源码快照及准备阶段code-delivery，无started/ledger/真实结果。新预算预计短3/中3/长7共13POST，尚未授权。

```powershell
# 当前入口默认只打印零网络计划
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-contracts/scripts/evaluate.py
# 恢复时先确认当前代码与freeze一致
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-contracts/scripts/evaluate.py --check-only
```

明确新预算后才由root唯一caller串行 `--run --system-proxy`，沿用前轮已测代理，不额外发模型探针；发送前持久预占，包含所有阶段/失败，错误即停，不继续失败phase。旧台账48/49、organization12/13、refined12/13、final9/13均保持，所有余量不借用、不合并、不重置。真实测量后checker只读复查，首次检查结果可独占写新文件，不能覆盖历史原件。

## 质量完成条件

前轮final短中7full/1partial、长6not_evaluated仍是最近真实评分；成绩录入遗漏、主题碎片和汉字姓名无允许来源支持的问题尚未被新模型结果证明解决。新协议固定槽也不能保证供应商始终遵守合同。

新长文真正完成audit并输出满足最终合同的结果后，独立按原14essential逐子句、可选精度、归因/频率/条件/范围、主题合并和尾部后果审核。不是模型checks/IDs、HTTP200或离线结构测试替代语义审核。结果齐全后再决定默认推广及提交范围；不自动增预算或放宽边界，不扩展ASR/支付/队列等范围。
