# 项目剩余工作清单（2026-10-07）

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](design.md)和[需求/实施状态](requirements.md)为准，当前任务与预算见[自适应交接](handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

> **用户2026-10-09要求暂停，新窗口继续。** 最新方向以[自适应字幕总结交接](handoff-2026-10-09-adaptive.md)为准：复用字幕→LLM归纳与合并，字数按任务有限扩展。新代码1342全量通过，新路径模型质量未评；固定800/7/240及逐ID完全覆盖不再作为默认产品成功条件。当前17/26真实POST，旧结果保留；下文是历史快照。

> 最新2026-10-08：规范化、程序引用和格式/语义分类有限重试已实现，后端965项通过，前端本次不改。独立新工作组25/26POST已关闭：短中8项essential完整，长文audit非法JSON、6项未评；中文姓名来源与主题组织仍未通过。默认legacy、现有开发账号不限下载保持。先读[当前交接](handoff-2026-10-08-normalized.md)与[最新报告](acceptance-reports/2026-10-08-grounded-summary-clause/report.md)。下文为历史快照，其无自动重试和预算等待规则已被用户新要求及根AGENTS第6条替代；旧失败原件与余额仍不重用。

本文件补充当前完成状态、未完成事项和后续验收条件，便于后续 Codex 接手。旧设计、计划、报告、冻结快照及预算台账保留原样。本次只更新文档，不调用模型、不开发扩展功能、不提交代码。

阅读顺序：本清单 → [最新交接](handoff-2026-10-07-refined.md) → [refined 实测报告](acceptance-reports/2026-10-07-grounded-summary-refined/report.md) → [逐子句审核清单](acceptance-reports/2026-10-07-grounded-summary-refined/semantic-review-checklist.md)。

## 工程约定

适用技能优先；涉及 UI/视觉/交互时先使用 ui-ux-pro-max 与 design-system，颜色、字体、时长遵循 primitive → semantic → component 三层 token。能力配置化、窄接口单向依赖，避免大规模重构；yt-dlp 仅经 ytdlp_service.py，LLM 仅经 llm_service.py，视觉层只读 scene，不修改下载状态或导入下载核心。用户 .env、数据库、模型资产与历史证据不改。用户明确指令优先；旧计划不构成自动开发、计费或默认策略推广授权。

## 已完成与验证边界

| 项目 | 当前状态 |
| --- | --- |
| Claude 后续代码审查 | 已完成，确认的问题已修复，见[审查报告](acceptance-reports/2026-10-07-grounded-summary-review/report.md) |
| 来源合同 | caller 行号选择、精确来源与归因位置校验已实现；词法可追溯不等于语义正确 |
| 长文组织与预算 | 固定最多 7 个要点槽、阶段输出预算、摘要长度及候选修订余量已实现 |
| 当前候选／最终边界 | 候选摘要最多 14 条声明／1600 字符；最终摘要最多 7 条声明／800 字符；要点始终最多 7 个、每点最多 240 字符 |
| 编排与回归 | 正常 n+2，无自动失败重试或隐藏付费回退；最近记录的后端全量为 479 项通过、1 条既有弃用提示，本次文档更新未重跑测试 |
| 默认策略 | 仍为 legacy；未提升 facts 或 auto 为默认 |
| 代码提交 | 当前代码、测试、新文档与证据均在工作区，尚未新建提交；最近提交基线为 33dc239 |

公开 summary/key_points/provider/model 返回形状保持；本轮不改前端、下载核心、用户配置或模型资产。不能把旧前端测试或浏览器结果算作本轮重新验证。

## 当前核心未完成项

| 优先级 | 未完成项 | 当前阻碍 | 完成条件 |
| --- | --- | --- | --- |
| P1 | 长文完整交付 | 最近真实 phase 完成 5 段抽取与 compose，但 8 条候选摘要声明触发当时 7 条限制，没有 audit 或最终输出 | 当前修订在新独立 phase 真正完成抽取→组织→audit，输出通过最终合同和独立来源／语义审核 |
| P1 | 总结内容补齐 | refined 中篇仍有 en2 改进目的、en3 成绩录入／本人账户读取、en4 发音反馈等缺口；短文部分主题仍重叠 | 依原冻结标准核对全部复合子句，不为精简遗漏必要事实、条件、归因、范围或尾部结论 |
| P1 | 最新修订真实验收 | 候选摘要声明数余量只经过离线回归和原响应回放，没有新的真实 audit | 新建 phase／台账、冻结当前源码及完整配置／提示／codec／runner／rubric 哈希，经明确新预算授权后单 caller 验收 |
| P2 | 集成交付与 Git 提交 | 当前工作区修改尚未提交，不能按旧提交识别当前实现 | 核对本轮改动、证据链接／字节／凭据范围，提交实现及新文档；排除无关 .claude、旧 raw、用户 .env/db/模型资产，不使用无范围 git add -A |

候选摘要声明数已由最多 7 条离线修订为最多 14 条，让原计划 audit 合并；最终 7 条／800 字符约束没有放宽。原失败仍按冻结合同保持失败，不得改称成功。当前 codec 可接纳原候选，但仍缺模型标为 core 的 F2_3 引用；必须由 audit 恢复实际含义并满足覆盖，不能仅挂 ID 宣称恢复。

## 真实测量与质量状态

最近 organization-refined 独立预算为 13 POST，实际 **12 次预占、12 HTTP200、54967 供应商报告 tokens**；剩余 1 次不使用。

| 样本 | 流程结果 | 独立核心事实审核 |
| --- | --- | --- |
| 中文短篇 | 3 POST；5 点，摘要 243 字 | zh1–4 全部完整；主题组织仍部分重叠 |
| 英文中篇 | 3 POST；2 点，摘要 203 字 | 1 完整／3 部分；点数减少不等于事实保留充分 |
| 英文长篇 | 6 POST；55 条事实抽取；7 槽完整；8 条摘要声明／1060 字触发 invalid_count | long1–6 无新最终输出，标 not_evaluated |

已有最终输出的 8 项合计 **5 完整、3 部分、0 缺失**；原定 14 项尚未完成全量最终验收，不能宣称 14/14。long7–11 是可选细节：出现时检查准确性，不把其遗漏额外算作核心覆盖失败。

依据：[独立语义 JSON](acceptance-reports/2026-10-07-grounded-summary-refined/results/organization-refined-semantic-review.json)、[冻结来源检查](acceptance-reports/2026-10-07-grounded-summary-refined/results/organization-refined-offline-check.json)、[失败诊断](acceptance-reports/2026-10-07-grounded-summary-refined/results/organization-refined-failure-diagnosis.json)、[测量后离线回放](acceptance-reports/2026-10-07-grounded-summary-refined/results/post-measurement-offline-replay.json)、[测量／交付源码哈希](acceptance-reports/2026-10-07-grounded-summary-refined/results/code-delivery.json)。

HTTP200、source spans、fact IDs、model checks=true、较短文字及离线测试都不能替代独立语义验收；agent 审阅不是外部人类评分或普适准确率。MIT 来源及衍生评测保留原署名、CC BY-NC-SA 4.0 非商业及相同方式共享要求，完整许可见[原语料许可](acceptance-reports/2026-10-04-natural-subtitle-quality/corpus/LICENSE.md)。

## 下一轮执行顺序

1. 读取上述证据和当前 Git diff，核对交付源码哈希及最近测试记录；保留所有历史原件。
2. 针对当前覆盖缺口与全局重要性取舍制定局部改进；不向产品提示注入评测答案，不持续逐个放宽最终边界。
3. 红绿回归与独立复审后，另建新 phase／台账，冻结当前代码和审核标准；正常三源预计 3＋3＋7＝13 POST。这只是预算估算，尚非新计费授权。
4. 经明确授权后，由一个调用者串行执行；每次发送前持久预占，错误即停，不自动重试、不隐藏付费回退。
5. 独立完成 14 个核心复合事实、可选精度、归因／频率／范围、主题组织与末尾结果审核，记录失败与限制，再决定是否推广默认策略和提交交付。

若再次反复遇到结构或重要性问题，应先复审生成合同与全局组织方式，不以无上限扩预算、删事实、截字或降低冻结标准换取通过。

## 预算与复查注意事项

- 旧 grounded-summary 为 48/49，organization-slots 为 12/13，organization-refined 为 12/13；三个剩余 1 次都不用，不合并、不借用、不重置。
- 失败 phase 不重启；不得覆盖 provenance、trace、payload、response 或账本。
- 当前源码已在测量后修订，旧 evaluate --check-only 预期失配；它比较当前源码与旧快照，不是历史证据损坏的证明。
- 历史原件只读复查：

```powershell
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-refined/scripts/check_evidence.py
```

## 后续扩展候选：不属于当前摘要收尾验收

以下状态来自[需求路线](requirements.md)与[历史交接](handoff.md)。本次没有重新逐项审查或执行，后续需单独确定范围、设计与验收；不能当作自动授权。

| 候选 | 历史记录中的未完成范围 |
| --- | --- |
| 真手机／低 GPU 验证 | 真设备触摸交互、纹理能力及降级；桌面模拟移动视口／模拟 8K 不作为真机证明 |
| 下载失败额度退还 | 失败后的额度补偿及并发一致性 |
| 独立 AI 额度 | AI 总结／翻译的独立计量和限制，现有下载额度不能算作 AI 额度 |
| 会员／积分／支付 | 需求、计费与支付流程尚未实现 |
| 队列扩展 | Celery／Redis 等横向扩展；批量下载仍属可选未定范围 |
| SSE 与生产部署 | 事件推送及部署运行保障，未包含在本轮实现 |

字幕时间轴导出、自动音频转写、问答及思维导图等亦不是当前已授权目标。
