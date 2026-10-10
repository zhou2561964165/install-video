# 开发账号与有限自主验收 Implementation Plan

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](../../design.md)和[需求/实施状态](../../requirements.md)为准，当前任务与预算见[自适应交接](../../handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

**Goal:** 开放一个已有开发账号的下载额度，直接继续已冻结的总结质量验收，有限扩预算无需再确认。

**Architecture:** 独立本地quota policy文件按现有user ID配置不限下载额度，不改账户/历史quota数据结构或LLM config模块；quota服务保留计数，me API明确unlimited及null上限。AuthBar用既有token样式显示语义明确的状态。root唯一caller执行现有contracts phase，worker隔离实现额度与UI。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system与primitive → semantic → component三层token；颜色/字体/时长不硬编码。能力配置化、窄接口单向依赖，避免大规模重构；LLM仅llm_service，yt-dlp仅ytdlp_service，视觉只读scene。不编辑.env/模型资产/历史原件；用户明确允许现有账号不限额度。默认legacy，正常n+2，无失败自动重试/隐藏付费回退。MIT来源/衍生评测保留署名与CC BY-NC-SA4.0非商业/同方式共享。用户已持续授权，无需重复审批；有限预算每轮独立记录。

## Task 1: 后端账号额度政策

写集：新backend/app/services/quota_policy.py、现quota.py/schemas.py/routes/auth.py、新backend/tests/test_dev_quota_policy.py。不改app/config.py、User/Quota表、LLM三模块或旧评测文件。

- 本地backend/dev-quota-policy.json默认不存在即无豁免，可通过DEV_QUOTA_POLICY_FILE环境变量指定路径；root配置已有manual-test@example.com的user ID，不新建账号或改密码。
- policy顶层仅unlimited_user_ids字符串数组，显式ID匹配；无全局*语义。缺失/非法/重复字段/错误类型等配置fail closed为无豁免，不报出配置内容；每次读取支持配置热更新，撤销立即恢复原有限额度。
- get_quota_info保留used/date，不限时limit=None；QuotaInfo.limit/remaining可null并含unlimited布尔标志。普通用户继续原整数limit/remaining。
- check_and_reserve豁免只跳过额度耗尽检查，原usage计数及认证/每IP限流/下载核心保持。不限账号当日已有耗尽行也可继续，不重置行；撤销后继续按原行/default限制。
- TDD真实API/临时DB验证超过有限阈值仍成功、me不限且used准确、其他账号429不变、撤销/坏配置failclosed、明日继续适用；全量root统一。

## Task 2: 额度状态展示

写集：frontend/src/components/ui/AuthBar.jsx及新增对应测试。先读ui-ux-pro-max/design-system并检索ux；root已查Contextual Live Badge Updates。使用原auth-bar token/class，显示“下载额度不限”，不渲染null比例或错误耗尽；正常/耗尽保留。一个role=status完整语义、必要atomic更新，不增加动画和新配色。仅接收props，不修改下载/scene。真实组件红绿验证不限/null、普通整数及退出按钮，再frontend全量/build。

## Task 3: root有限真实验收与独立审核

- 新授权记录本次组预算上限26，首phase organization-contracts上限13。当前冻结3源正常3/3/7，用户已明确准许直接使用且有限必要扩预算。
- 先check-only并落独立授权/组计数；root串行一次run --system-proxy，包含每段/compose/audit/失败，错误即停，不复用旧余额。
- 独立核对新raw/ledger/hash/codec和14essential/precision/organization。错误/质量缺口先离线诊断；确有验证过的修复才另建最多13POST扩展phase，本次总26不得超过。
- 原预算请求废止等待状态，新用户指令优先。授权更新进当前文档和AGENTS，旧快照“未授权”是当时记录，不改历史原件。

## Task 4: 集成交付

后端/UI独立复审，主agent全量与构建；配置已有账号、本机验证me API，保留默认legacy直到真实证据支持决策。记录当前额度账号、已用/上限/余量与必要扩展原因，完整更新报告/交接。拒绝新账号绕quota、全站不限或无穷循环计费。
