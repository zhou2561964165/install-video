# 历史交接（2026-10-09至来源优先首轮准备）

> 以下状态按记录当时阅读，不作为待办或可用预算。当前三轮已完成、17/17封账及实际缺陷见[2026-10-10交接](handoff-2026-10-10.md)。旧26/26和全部原证据保持，不重新执行。

# 当前交接：回归字幕总结

> **首轮已实测，修复候选准备中：** [首轮报告](acceptance-reports/2026-10-10-source-first-summary-live/report.md)5POST/19776tokens已closed；短pass，中反馈频率/文化归因fail，长raw20超14结构fail。已引入[LCEL阶段分离候选](superpowers/specs/2026-10-10-staged-summary-design.md)，170相关离线通过后补解码容量边界，默认single尚保留；新continuation父5、累计上限自主10→12，修复phase最多7（复用两已付费leaf，不重复抽取），待代码/保护工具审查与freeze后root实测。首轮失败和10上限父预算保持closed原字节，不改评分。

> **下一步（2026-10-10后续更新）：** 用户已允许按任务自主提升预算，无需再询问。新工作组总硬上限10POST，首phase最多5（三源），剩余最多5仅用于已定位/离线验证修复后的新phase；旧26/26封账保持。[新候选内容验收](superpowers/plans/2026-10-10-source-first-summary-acceptance.md)正在准备新增工具/离线审查和独立freeze/check，尚无真实调用。实现/108后端/4hook/旧结果浏览器验证复用，不重复；freeze包含summary_output.py和现有依赖版本。

> **2026-10-10成熟方案整改：** [来源优先局部设计](superpowers/specs/2026-10-10-source-first-summary-design.md)已实现：已有Pydantic接管summary/key_points严格类型/schema；生成指导先要点后概览，接口/预算/调用次数保持；hook清空重做时的旧结果。108后端及4hook离线回归通过。此次没有真实模型POST，新候选中篇语义与长文质量未验证；下文短/中结果仅对应旧冻结提示，不能转记给新候选。旧在线报告保留原字节，其旧结果残留现象属于修复前版本。

> **后续开发必须遵守（用户2026-10-10追加）：成熟方案优先，避免重复造轮子。** 先复用[已有成熟方案研究](reference-summary-review-2026-10-10.md)，按任务核实官方资料与兼容性，适用时实际采用LlamaIndex、LangGraph等成熟组件；自研聚焦业务适配与缺失能力。开发计划记录采用方案或确需自研的具体原因，执行[AGENTS.md §10](../AGENTS.md)。不能以已有自研分段/合并为由直接跳过成熟方案选型；已有有效开发、验证和证据仍复用。

> **2026-10-10 在线补验更新：** [正式 HTTP 流程报告](acceptance-reports/2026-10-09-online-formal-flow/report.md)新增真实 TCP API20/20、页面4/4、旧工具故障10/10。三份原字幕传输/解析一致；LLM使用本地夹具，真实模型0POST，旧26/26不变。公网来源仍有network失败；再次总结失败时旧结果仍显示。下文提示质量结论及原阶段测试范围保持，不能用此次传输通过替代内容评分。已完成在线检查不重复，真正剩余的真实模型阶段待明确新预算。

**当前状态：来源优先新候选实现/离线/UI修复完成；用户授权自主预算的新组上限10、首phase5进入真实验收准备。旧工作组六phase仍closed，26/26 POST、152726供应商tokens保持。旧最后短篇回归通过、中篇未通过仅对应旧候选，新候选内容未实测，不标为已解决。**

工程约定：最新用户指令/AGENTS优先，适用Superpowers流程；新增能力配置化、窄接口单向依赖、避免无关重构。LLM/yt-dlp各经唯一服务层，视觉只读scene。UI变化须ui-ux-pro-max/design-system与primitive→semantic→component tokens；本轮无UI变化。保护用户工作、env/db/账号及原始失败、freeze、脚本和账本。

整体实现与配置见[设计](design.md)、[需求状态](requirements.md)和[根README](../README.md)。本页只负责当前总结任务、实际完成清单、质量缺口与预算，历史计划不自动恢复成待办。

## 已执行的开发与验证

| 工作 | 实际状态/证据 | 后续处理 |
| --- | --- | --- |
| legacy字幕分段归纳/有限合并、adaptive输出预算 | 已有实现；原字幕规模贯穿合并，配置保持 | 直接复用，不重建总结引擎 |
| adaptive配置兼容修复、多层规模传递 | 历史针对性125及全量1342 passed/1既有警告；原120000字符内存合并实验 | 未变部分不重复验证；不是内容评分 |
| 第一版通用提示 | 概览/细节互补、并列能力、来源体裁；[首修复报告](acceptance-reports/2026-10-09-adaptive-summary-repair/report.md) | 实际2POST、closed24，部分改善未通过，原件保留 |
| 第二版用户请求指导 | 高层概览、完整条件、频率/对象/事件/单位、每处断言限定 | 最新相关91 passed in0.32s；独立产品审查通过 |
| 两个独立验收工具 | 真实保护红测后19/7项离线通过，审查发现的重要问题已修复并复核关闭 | freeze/check与共享锁、发前持久预占、快照/raw/result闭环已执行 |
| 最后短中篇复验 | [最终报告](acceptance-reports/2026-10-09-adaptive-summary-final/report.md)及results；2POST均HTTP200/stop | closed26，snapshot核验通过；内容结论如下 |

2026-10-09两轮复验对应的产品变化仅为llm_service.py的共用system/user提示；2026-10-10新增codec及结果状态整改见页首新报告。公开字段、解析、输入/输出预算、分段/合并调用规模保持；无样本答案注入、文本删除器、新facts协议或额外付费核查。提示是生成指导，不是确定性语义保证。

1342项全量、前端84/build及旧浏览器报告仍是各自历史记录，本轮未重跑全量/前端/浏览器。旧长文已执行3POST，旧短中篇已执行2POST；本轮没有重开它们。

## 最新内容结果与真正剩余缺陷

- **zh-short通过本条回归：** zh1–zh4均full，精度及组织通过。概览不再复制具体时段/渠道/话术。P2/P3仍有备课概念重叠，但各自补充不同例子、机制和后果，按原标准不是纯重复。不是“完全无词项重叠”或通用质量证明。
- **en-medium仍未通过：** en2/en3/en4 full，Engrade成绩录入+私下留言已恢复；en1仍缺“每次课堂表现，即每节课评价”。摘要完整两理由与P1复述；摘要努力→技能的信念归属比原讲者相信弱，不能用P1的相信修补。当前摘要的高层“课后反馈”不直接当作always，通常课后/书面在P2/P3保留。
- **新版长文质量未实测：** 旧en-long单样本无关键阻断的结论仅属于旧冻结提示。不能把旧14点内容评分或机械合并验证转记为新提示通过。

后续复用已有原字幕、失败输出与审查调查中篇问题；不要重跑已关闭验证、降低原必要子句/精度/重复标准，或恢复固定800/7/240与37core-ID合同。旧组没有余额；用户后续自主预算授权见AGENTS第12条，当前新组独立上限10/首phase5并记账，不再请求数值许可。两个短中样本已见，是回归样本，不是holdout或统计准确率。

## 预算原件与停止边界

| phase | POST | 状态 |
| --- | ---: | --- |
| quality-final | 3 | closed |
| quality-repaired | 14 | closed |
| adaptive-transcript-long | 3 | closed |
| adaptive-transcript-short-medium | 2 | closed |
| adaptive-transcript-repair | 2 | closed |
| adaptive-transcript-repair-final | 2 | closed |
| 合计 | **26/26** | 无剩余额度 |

原budget-group.json仍是前两阶段17次快照，不改原件。应按对应phase ledger逐一核算17+3+2+2+2=26，**不能把各tracker的累计reserved_posts相加**。原件在.planning/2026-10-08-summary-quality-finish/：

- budget-group.json
- budget-continuation.json
- budget-continuation-short-medium.json
- budget-continuation-repair.json
- budget-continuation-repair-final.json

最后phase2390 prompt+497 completion=2887 tokens；供应商原始usage逐响应合计152726 tokens、无缺失usage。不推算货币费用。平台Agent额度恢复不重置本工作组上限；测试预算不变成产品下载额度或生产LLM代码中的限制。

四个adaptive一次性脚本均禁止再次freeze/run，不删除results/tracker/锁以重开。已取消quality-long-final及归档草稿不执行，旧组25/26等余额不借用。

## 配置与证据边界

默认legacy/adaptive沿用普通字幕一次总结、长字幕分段及有限合并。默认基础4096 tokens，上限max(8192,base)，主题基础7/默认最多14（可配置7–32），随清理后原规模有限增长；没有固定摘要/单点字数硬拒，不裁字、不凑点。fixed/facts仅显式实验，详见根README；输入、分段数、完成状态和字段类型校验仍保留。

早期long/short工具的live-asset比较可能因之后AGENTS/交接更新而拒绝；不要改旧hash或重跑模型来“修复”历史检查。新repair/final的只读--verify使用冻结快照及raw/result/hash闭环，文档收尾不会破坏检证。所有旧报告和原始结果保持原字节，当前文档对阶段差异作说明。

## 工作区与交接

当前候选提示、工具、测试和文档都在未提交工作区，未推送/部署。环境、数据库、账号和下载核心未改，旧ACL受限raw目录不清理。本轮机械/有限验收步骤结束，但中篇质量及新版长文质量验证仍未解决；以[修复计划](superpowers/plans/2026-10-09-adaptive-summary-repair.md)及最终报告的实际范围为准，不重复历史工作。
