# 多agent并行续验收（2026-10-07）

接续[上一轮报告](../2026-10-07-grounded-summary-organization/report.md)。本轮只测量当前候选摘要余量与通用范围提示修订，另建 organization-refined phase，不重启organization-slots或借用其剩余1次。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system与三层token；能力配置化、窄接口单向依赖；LLM仅llm_service、yt-dlp仅ytdlp_service、视觉只读scene。用户.env/db/下载/UI/模型资产不改；默认legacy，正常n+2，无自动重试/隐藏付费回退。MIT源及衍生评测保持原署名与CC BY-NC-SA4.0非商业许可。

## 并行分工

- Agent A：新独立入口与账本、冻结和安全回归测试。
- Agent B：产品代码/合同/预算边界只读复审。
- Agent C：独立14核心事实审核清单及真实结果语义评分。
- 主agent：集成、全量回归、冻结、预算申请、唯一串行模型调用者与文档归档。

## 测量合同

复用原冻结rubric及三源。输入100000字符、facts分段8000；extract4096、compose/audit8192输出token；候选摘要最多1600、最终800字符，1–7槽/最终点≤240。独立13POST上限，短3/中3/长7；失败停止、发前持久预占。不把HTTP200、fact IDs或checks=true当准确率。

## 当前进度

新入口39项专项通过；主agent全量476通过，保留既有Starlette/httpx弃用提示；git diff --check通过。产品和入口独立复审无Important/Critical缺陷，临时替身验证完整3/3/7调用链、发前预占、锁释放、绑定还原。14事实语义审核清单已冻结，尚未预填成功。

refined测量前零网络freeze完成、check-only match=true，覆盖新入口、org入口、base runner及生产模块/配置/提示/codec/rubric预算。经用户审批独立13POST后只运行一次，实际12预占/12HTTP200/54967供应商报告tokens，剩1不使用。旧台账48/49与organization-slots12/13保持原样。

## 本轮真实结果

| 样本 | 请求数 | 最终输出 | 冻结来源/合同核对 |
| --- | --- | --- | --- |
| zh-short | 3 | 5点，摘要243字；点长48/49/81/50/73 | 6事实，audit完整 |
| en-medium | 3 | 2点，摘要203字；点长81/74 | 7事实，audit完整 |
| en-long | 6（5extract+compose） | 无audit或最终输出 | 55事实可追溯，compose invalid_count |

长文完整JSON、7槽、点长128/72/72/112/136/146/194，finish_reason=stop，1869输出tokens。摘要1060字符在候选1600容量内，但8条摘要声明超过冻结codec当时的7条限制，因此整批拒绝；没有重试、截字或删声明挽救。

[冻结词法/合同核对](results/organization-refined-offline-check.json)确认6/7/55事实来源成立；[冻结codec失败诊断](results/organization-refined-failure-diagnosis.json)始终按当时合同保留invalid_count，不能改称成功。

## 独立语义审核

[本轮逐子句审阅](results/organization-refined-semantic-review.json)：已交付8个essential复合事实中5完整、3部分、0缺失；long1–6没有最终输出，标not_evaluated，不能声称14/14。

- 短篇4项完整，大纲恢复；P2/P3仍有可合并局部重叠，组织partial。
- 中篇1完整/3部分：en2改进目的不完整；en3遗漏成绩录入及个人账户读取；en4遗漏发音反馈。仅两点并不证明关键信息足够，组织pass与覆盖partial分别记录。
- 未发现明确来源外新增；该审阅属于独立agent核对，非外部人类评分或普适准确率。只依赖真实输出/source/rubric，不用model flags或挂ID替代语义。

## 测量后离线增量与边界

针对8条候选摘要声明，新增红→绿回归：允许候选summary最多2倍声明数（默认14），保留全文交给原计划一次audit合并；final仍最多7条声明/800字符、points始终最多7。15条候选、8条final仍拒绝，无丢弃/额外阶段/失败重试。audit提示明确合并多余草稿声明。

137相关测试及最终后端479全量通过；独立增量复审确认最终合同未放松。当前codec可离线解析同一原响应8条summary/7points，但缺core ID F2_3（抽签演示被抽取模型标core），还需audit恢复真实含义；[新codec离线回放](results/post-measurement-offline-replay.json)不是最终输出或新模型成功。

## 交接与复查

```powershell
# 项目根，默认不调用模型；历史原件按冻结codec复查
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-refined/scripts/evaluate.py
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-refined/scripts/check_evidence.py
```

当前源码经过上述测量后增量，evaluate --check-only预期失配；不要覆盖provenance、重新run该phase、重置账本或使用剩1。当前增量尚无新真实audit，下一次须独立phase与新预算，完成长文最终14事实覆盖、范围与主题验收后才决定默认策略。默认legacy保持。
