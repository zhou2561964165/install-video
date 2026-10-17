# 当前交接：核查质量续收尾

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页的“当前/下一步/待实现/等待授权”、预算、测试与服务状态均指记录当时。最新用户决定、活动任务与全部后续计划先读[统一总表](follow-up-plan.md)，phase15证据读[阶段交接](handoff-2026-10-16-deepseek-step1.md)；产品实际实现参照[设计](design.md)、[需求](requirements.md)和[UI指南](ui-extension-guide.md)。长文已获准上线使用但质量仍待整改，现有公开20000字符保护和embedded区域约束尚未在本轮调整。历史候选统一汇入总表，不据旧待办启动开发/服务/模型或重开closed phase；原验收及冻结证据保持原字节。

> **历史阶段，已由[当前adaptive交接](handoff-2026-10-09-adaptive.md)取代。** 本页原17次核查验收已结束，文末quality-long-final准备已取消、未执行，不得恢复为待办。后续两轮adaptive验收及两轮提示修复复验均已执行，当前26/26并停止真实验收；不依本页旧暂停/预算/准备文字重复运行。

> 10月9日后续用户要求已改变实施方向：字数自适应、有限资源、回归字幕交LLM总结。当前入口改为[自适应字幕总结交接](handoff-2026-10-09-adaptive.md)；本页保留此前核查整改与17次实测的状态，原第三phase准备已停止、未freeze/POST。

最新依据为[续验收报告](acceptance-reports/2026-10-09-summary-quality-repaired/report.md)、[短中独立验收](acceptance-reports/2026-10-09-summary-quality-repaired/short-medium-semantic-review.md)及[长文诊断](acceptance-reports/2026-10-09-summary-quality-repaired/long-core-diagnosis.md)。工作记录在`.planning/2026-10-08-summary-quality-finish/`，目录日期为开始日，不代表没有接收10月9日新AGENTS及恢复指令。

工程约定：最新AGENTS/Superpowers优先，UI按需skills/三层token；能力配置化、窄接口单向依赖、唯一LLM/yt-dlp层、scene只读，保留用户env/db/已有账号及旧原件/冻结/预算/未提交代码。实际模型角色SolHigh/LunaMax，不改主模型。掉线任务明确核查未完成后恢复，所有模型POST只由root完成、有限预算、无隐藏fallback。

## 已完成

核查compact协议/真实bool程序映射、质量主题/身份诊断、来源fence绕过与提前paid标记修复、严格HTTP元数据证据、新scalar条件无损转换，独立任务及整合审查完成。最后追加极性保守上下文与missing-core具体反馈已离线红绿和独立审查；root最新完整回归1325 passed、1条既有Starlette/httpx弃用提示、196.66秒，记录在`.planning/2026-10-08-summary-quality-finish/backend-release-final-tests.txt`。

compat质量模式/legacy策略默认保持，真实phase显式compact+defaultformat1/semantic1/共享2。原API返回summary/key_points/provider/model不变，无新依赖或UI/下载核心修改。已有manual-test账号本地不限下载policy、其他账号有限和统计保持，不新建账号或改密码。

## 模型验收

新工作组hard26，目前quality-final3+quality-repaired14=17POST/129204供应商tokens，两个phase均关闭。另旧规范化25组单独保留，不借其余额。首3失败已本地scalar修复；续14短中发布，长文37core引用缺25、semantic修订原文不变，未发布。

原8短中essential全部full、所有输出句精确性通过；中篇原组织rubric通过；短文P2父概览重复仍不通过。长文6essential无final未评；raw诊断4retained/2partial不得冒充final成绩。来源中文别名已消失。整体质量仍未通过，不改默认策略。

## 已定位后续问题

长文既有词项低分/词法假阴性，也有真实缺失子句，不能降低core标准、挂全hint或只重复prompt。最后修复有限词法非否定结构以及specificmissingfeedback后，当前旧raw仍不通过，需要新的实际数据才可发布结论。最后9额度不能自动解锁已关闭phase或被其他组借用；有限后续应有明确必要性和冻结台账，不无限扩预算。

caller当前原件可重复只读checker；原evaluators对已关闭阶段的run和freeze拒绝。当前源修改后check-only mismatch属于正确保护，不修改旧hash。用户恢复额度并要求继续后，已明确准备独立`quality-long-final`：仅原长篇，正常7POST、含默认分类修复最多9POST，与已用17累计最大26；无硬上限扩张，不重启旧阶段。新工具、离线测试、独立审查与完整冻结通过前不发送，所有source/checks/count/length边界保留。
