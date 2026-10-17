# A/B 组合验收适配器实施计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 按任务实施与独立审查。用户已要求结合两方案并继续；本轮只实现有限验收适配器，不迁移产品架构。

**Goal:** 完成独立规划→全文生成的两次Pro调用，并保留完整证据与独立内容结论。

**Architecture:** 新脚本复用现有会计/锁/传输，实际LCEL固定两阶段。Pydantic只校验标题规划，全文生成普通文本沿phase13，无本地删改。

**Tech Stack:** 已有Python/httpx/Pydantic/langchain-core/langsmith禁追踪。

**Spec:** [组合设计](../specs/2026-10-15-planned-direct-summary-design.md)。

## 约束与审查重点

- phase14 cap2，parent19，全文34894字符source SHA沿phase13；规划4096/none/schema，生成16384/high/text，timeout300，retry0；1–12标题/120字，源60000/完整payload80000容量。
- 不修改生产/closed脚本/旧证据/env，不提交推送部署；账户/Live2D保护沿工程约定。
- 关注封账失败和部分持久写入、第二次前首raw/parsed plan漂移、所有来源与父账绑定、纯离线不加载dotenv、mock临时目录和真实group隔离。每项都要有行为测试。

## Task 1：实现和离线行为验证

Files：新增 `docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/planned_direct_delegate.py`；新增 `backend/tests/test_planned_direct_delegation.py`。

- [x] 已保存两次完整source及第二次首规划行为用例；daemon恢复未获取此前RED输出，不虚构其结果。
- [x] 实现纯函数planning schema/parse与两个payload构建、严格容量；固定LCEL串行及禁追踪。
- [x] 实现plan/freeze/check/run/verify和父组/hash/锁/root/cap/预占/封账，复用原会计函数。
- [x] root恢复后运行相关新套件：32 passed/89.08s；无真实HTTP。

## Task 2：独立审查和有限实测

- [x] 独立审查新工具和测试，Critical/Important/Minor均0。
- [ ] 审查报告落盘，纳入freeze资产。root记录预算、完成plan/freeze/check。
- [ ] root共享锁串行run最多2POST；任何错误停止并封账，verify原件。
- [ ] 成功时原样导出规划/全文/回答并做独立逐断言内容审阅；失败时保存失败证据，不把规划当最终产品。

## Task 3：交接同步

- [ ] 当前路线文档/handoff/AGENTS/planning同步，旧纯B标为保留方案而非当前执行入口。
- [ ] 交付真实结果、累计成本和下一动作；不继承旧PASS/FAIL，保留所有封账原件。
