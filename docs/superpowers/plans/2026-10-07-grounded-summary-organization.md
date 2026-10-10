# 长文摘要组织 Implementation Plan

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

> For agentic workers: 使用 superpowers:executing-plans 与 test-driven-development；reviewer 独立复查合同和预算边界。

**Goal:** 在既有 n+2 事实摘要路径中限制 compose 的要点结构，并配置摘要长度与阶段输出预算。

**Architecture:** summary_facts 纯槽解析转换为既有候选；llm_service 调用前按阶段取预算并生成固定槽提示；评测复用预算工具，新目录独立冻结与台账。

**Tech Stack:** Python 3.12、dataclasses/JSON、httpx、pytest，无新增依赖。

**Spec:** [设计](../specs/2026-10-07-grounded-summary-organization-design.md)。

## Global Constraints

技能优先；UI 先 ui-ux-pro-max/design-system、三层 token；窄接口和配置化；yt-dlp 仅 ytdlp_service，LLM 仅 llm_service，视觉只读 scene；不改用户 .env/db/模型资产/历史原件；默认legacy，n+2、无自动付费重试。

## Review Focus

- 固定槽不得靠删点/截字得到合法结果，缺槽、重复字段、间隙必须拒绝。
- core 事实引用可跨多个主题合并，但不能只挂 ID 而省语义；mock不能证明真实质量。
- 阶段预算必须同时体现在容量检查、实际请求与冻结评测 payload。
- 新评测不得重置/借用旧49预算，默认命令不发送请求。
- 旧回放由真实codec校验，历史失败原件不改写成成功。

### Task 1：槽合同与阶段预算

Files: backend/app/services/summary_facts.py、llm_service.py、backend/app/config.py、对应tests。

- [x] 写槽缺失/未知/间隙/duplicate/引用/覆盖红测试；新增parse_composition转换为CandidateSummary。
- [x] 配置summary800、compose/audit预算0继承或显式覆盖，运行配置与真实MockTransport红测试。
- [x] 发送与容量检查使用同一stage预算；更新compose提示固定7槽、audit保持数组合同。
- [x] Task1 全量后端399通过；后续回放又增加4项。

### Task 2：离线回放与可审查评测准备

Files: backend/tests/test_grounded_organization.py、新docs/acceptance-reports/2026-10-07-grounded-summary-organization/。

- [x] 使用原长文54事实验证5抽取+compose+audit=7调用、公开形状与严格失败停；4项通过。真实audit完整输入>71K，本轮profile显式100000。
- [x] 新目录评测入口复用现有BudgetClient，独立台账/phase，默认零网络；已冻结新配置/提示词/源码并check-only match=true。
- [x] 独立复审、首次全量434通过；获13POST授权后单次实测12/13，短/中有效，长compose946摘要超800被拒；初测8事实5完整3部分，长6未评分。
- [x] 按测量离线修订：候选摘要2倍余量、final上限不变、通用归因/频率/姓名提示强化；红绿测试、437全量与增量复审通过，新报告原件归档。
- [ ] 后续另建phase与明确新预算验证当前修订；不重启本轮phase或使用剩余1次。
