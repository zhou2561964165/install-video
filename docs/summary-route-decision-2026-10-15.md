# 总结路线记录与当前执行边界

> 最新用户决定与后续计划统一见[后续整改与计划总表](follow-up-plan.md)：长文可以上线使用，质量仍待后期整改；组件居中、Live2D看板娘活动及小圈联动已登记。后续计划继续写入总表，本文保留路线历史；本轮仅文档，完成后等待下一步指示。

更新：2026-10-16。最新接手先读[统一总表](follow-up-plan.md)，phase15证据读[阶段交接](handoff-2026-10-16-deepseek-step1.md)。用户先后保留A/B、结合两方案、限定DeepSeek完成第一步，随后确认长文可上线使用但质量仍待整改，并要求统一后续计划、全面审查文档。这些决定按时间演进，历史路线不是同时执行的待办。

工程约定：适用skills、成熟组件优先、配置化窄接口和单向依赖；yt-dlp唯一层、视觉只读scene，UI使用设计技能及三层token。保护env/账号/已有UI/本机模型和全部历史原件，发布继续过滤Live2D模型历史。

## 1. phase15第一步已完成，当前后续安排以总表为准

用户明确“先完成第一步，后面的听我指示”“不用改变模型，只使用DeepSeek”。跨模型筛选因此收窄为固定Pro/high的两来源单次全文观察。phase15已closed，实际2POST/23275tokens，没有规划、自动核查、修订或再生成。

| 来源 | 本次结果 |
| --- | --- |
| MIT Lecture2英文长字幕 | 7full/1partial；缺可转换输入前提，局部退出示例条件错误；range总括与step实例的源内张力单列。概览/组织PASS |
| 中文Listening访谈 | 4full、未发现确证核心事实错误；开头口语含糊不硬判错误，重复扩写使组织未通过 |

[报告](acceptance-reports/2026-10-16-deepseek-source-screen/report.md)、[内容审阅](acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md)、[原样结果](../exports/deepseek-step1-2026-10-16/)。这是单模型、每源一次的能力观察，不能换算优化百分比、可靠错误率或模型优劣。用户后续指示前，不自动推进任何下一阶段。

## 2. A：完整字幕直接委托Pro（历史已执行）

流程：完整字幕＋明确总结任务一次发送→保存供应商回答。本地负责获取、传输、结构/完成状态检查与会计，不使用本地模型、分段摘要或自动语义judge。

phase13参考profile：DeepSeek Pro、Responses普通text、reasoning high、16384 output token上限、timeout300秒；不强制14/15点或摘要字数。全文34894字符，1POST/15498tokens，返回5206字符，已closed并原样导出。

[执行报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md)在调用时没有语义评分；随后[独立审阅](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-content-diagnosis.md)为六项核心full，precision FAIL、overview PASS、organization局部FAIL，另漏两项课程路线。此区别通过当前索引解释，旧执行报告原字节不改。一次结果失败不证明A整条路线永久不可用。

## 3. B：独立规划→逐主题写作→概览（保留设计）

这是助手提出的后备，程序分配原文和写作预算，按主题执行，最后单独生成概览；区别于同响应theme_plan或一次全局points→overview。已有[候选计划](superpowers/plans/2026-10-15-topic-writing-candidate.md)及[设计](superpowers/specs/2026-10-15-topic-writing-design.md)，**未实现、未实测**。

旧设计中的T+2、14点、8192写作预算是纯B候选取舍，不是A、组合、phase15或当前产品新增合同。保留设计不构成继续开发授权，不依据旧“下一步”提前执行。

## 4. A/B组合：独立标题规划→全文写作（历史已执行）

按用户“两方案可以结合起来”，phase14两次均输入完整字幕。规划只列可纠错主题标题，第二次用原文＋规划自由写作，原文优先，不按14/15点硬限、不分块归纳。实际采用已有LCEL/Pydantic与传输/会计；它只在独立验收脚本中运行。

cap2实际2POST/26054tokens，返回8293字符，已closed；[报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-14-report.md)、[逐项对比](acceptance-reports/2026-10-13-long-summary-fidelity/phase-14-content-diagnosis.md)。六项核心仍full，补齐A漏的可读/模块化代码及算法效率主题，但时间错误未解决、末尾回顾增加重复和转换范围错误。除法/重绑等部分判断有语境分歧，报告保留了分歧。

相较phase13，供应商tokens增加约68.1%、可见字符增加约59.3%；不能把篇幅/成本增长当质量增长。此实验未证明组合普遍优于直接生成，也未接入产品默认。[冻结设计](superpowers/specs/2026-10-15-planned-direct-summary-design.md)和[实施计划](superpowers/plans/2026-10-15-planned-direct-summary.md)保留执行前状态，实际完成以报告为准。

## 5. 核查/编辑建议的状态

此前完整source核查、revision、checks/subject_checks及Ragas已有各自历史实现和失败证据；Ragas对已知P4实例/类别错误曾误放，不能作为生产自动放行门。有关“先证明核查者能辨错，再作有界局部修订”的新建议只讨论过，用户没有指示进入该后续步骤；不把它更名为已完成能力，也不重复旧付费路径。

内容评价继续区分：确证错误、来源冲突/歧义、合理抽象、必要遗漏和重复；允许明确段落语境继承，不以字段齐全、标题出现或多个judge一致认证语义。不能用删错句或改原文换取通过。

## 6. 计数和后续门槛

长文工作组phase1–15全部closed，23POST/319471tokens；Ragas独立16/34106，持续整改39POST/353577tokens，旧67POST各组另封账。旧原件、脚本、台账与freeze保持；phase15用满不能重开，网络恢复或换账号不清零。

整体整改曾获无总费用/POST上限授权，每个未来phase仍须有限cap/用途/台账、root共享锁、串行、发前预占及首错停止。该授权不覆盖用户当前“第一步完成后听指示”的停止边界。文档更新也不触发测试、服务、freeze或模型调用。

产品仍为`legacy/adaptive/single/fidelity=off`、公开20000字符保护；供应商/模型由部署配置决定，代码默认模型为空。任何profile通过都不自动恢复公开长文，不自动升级默认或部署。
