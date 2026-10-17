# 当前交接：摘要模块化与有限验收

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页的“当前/下一步/待实现/等待授权”、预算、测试与服务状态均指记录当时。最新用户决定、活动任务与全部后续计划先读[统一总表](follow-up-plan.md)，phase15证据读[阶段交接](handoff-2026-10-16-deepseek-step1.md)；产品实际实现参照[设计](design.md)、[需求](requirements.md)和[UI指南](ui-extension-guide.md)。长文已获准上线使用但质量仍待整改，现有公开20000字符保护和embedded区域约束尚未在本轮调整。历史候选统一汇入总表，不据旧待办启动开发/服务/模型或重开closed phase；原验收及冻结证据保持原字节。

当前以 [对应子句修复报告](acceptance-reports/2026-10-08-grounded-summary-clause/report.md) 为准。用户要求的规范化、程序引用、格式/语义分类有限重试已落地，后端最终 965 passed；实际总结质量仍未收尾，默认 legacy。

工程约定：以最新用户 AGENTS 和有效指令为准，Superpowers 管理流程；UI 按需 ui-ux-pro-max/design-system 与三层 token，能力配置化、窄接口单向依赖；HTTP/yt-dlp 各自唯一服务层，scene 只读。原 env、数据库、已有账号、用户工作和历史原件/冻结/台账保持。按注册 Luna Max/Sol High 实际并行；后续子 Agent 被平台额度拒绝，root 接手，无虚构独立审查。

## 已完成

- 新 summary_normalization/summary_references/summary_retry 三个纯模块，运行时不再直接拒绝 raw summary 字符串。
- 引用从已验证事实程序关联，保留依据/冲突/歧义；最终仍严格核查，不补造 true 或来源。
- 默认格式 1、语义 1、共享额外 2，可关闭；网络/供应商/来源/容量/配置不重试。优化模式预算副作用已红绿修复。
- exact json_object 提取 marker 与双方对应子句作用域的两个真实问题已离线红绿修复。
- 最新后端全量 965 passed、1 条既有弃用提示；先前一次 964 pass/1 error 为旧测试临时文件 atomic replace 的 Windows WinError 5，保留该日志，再完整复跑 965 通过。未修改历史 runner 来隐藏文件系统错误。
- 新三个独立评测 phase 与 hash/原始请求/trace/public 重放，MockTransport 完整三源测试、typed ledger、篡改/反馈伪造、预占失败、共享 caller 锁验证。
- 前端本次不改；此前 84 项/build 验证仍有效，未冒称新增浏览器验证。

## 当前模型预算与质量

新工作组上限 26，三阶段分别 8、4、13，共 25 POST / 135,175 供应商 tokens；各阶段已关闭，旧余额不续跑。本轮最后 phase 仅评测 extra=0，产品默认 extra=2 保持。旧开发账号工作组的 3 POST/5869 tokens 单独保存。

最新短中有 final，8 个可评 essential 完整；长文最终 audit 非法 JSON且出现28个点检查编号，无 final，6 个 essential 未评。中篇中文别名未由来源确认，短中主题仍可合并；不宣布质量完成或改变默认策略。下一步先离线整改 audit 输出格式、主题合并和姓名来源边界，再按持续授权建立明确的新有限工作范围；不能突破已冻结工作组硬上限。

只读检查三个新阶段的 `scripts/check_evidence.py`；关闭阶段不使用 `--run`。源改动后的 evaluate `--check-only` 失配是正常保护，不修改历史 provenance。计划和日志在 `.planning/2026-10-08-summary-normalization-retries/`。

已有 manual-test 开发账号不限下载的本地 policy 保持，其他账号仍有限，统计保持；本次不新建账号、不改密码或数据库。
