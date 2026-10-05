# 可追溯事实/主题与逐声明核查验收

## 工程约定

先检查适用 Superpowers 技能；skill 指引优先于计划。UI/视觉/交互先用 `ui-ux-pro-max` 和 `design-system`，颜色/字体/时长遵循三层 token；本轮不修改 UI。能力和容量配置化，模块经窄接口单向依赖；只有 `ytdlp_service.py` 接触 yt-dlp，LLM 只经 `llm_service.py`，视觉层只读 scene。保留 yt-dlp 回退、用户 `.env`/数据库/AGENTS/模型资产和历史证据，不自动重试或降级付费 POST。

## 评价范围与许可

复用[原独立语料 manifest](../2026-10-04-natural-subtitle-quality/corpus/manifest.json)中的三份自然字幕和原有 14 条复合核心事实，未新增采集、拼接、重复扩充或注入人工答案到产品提示词。中文短/英文中由 Dr. Haohsiang Liao 授课，英文长课由 Dr. Ana Bell 授课，来源 MIT OpenCourseWare；原始页面、字幕 URL、署名及改动说明见 manifest 与[原许可说明](../2026-10-04-natural-subtitle-quality/corpus/LICENSE.md)。

本轮源摘录、模型衍生摘要和事实评审遵循 **CC BY-NC-SA 4.0**，仅非商业本地推理评测，相同方式共享并保留署名；未训练/微调模型，MIT 不背书本软件或模型输出。产品代码与评测脚本不因此重新许可。

新输出前冻结[rubric.json](rubric.json)：原 14 条事实不变；以前默认 `natural-refined` 的三个结果按 SHA-256 只读复用，基线为 **12 条完整、2 条部分保留，长末点 365 字**。覆盖按复合事实各子句语义检查，非关键词命中；限定词、文化/教学观点归因、成绩录入功能、对象类型约束操作、算术操作范围、radius/area 与崩溃/不停后果单独审核。

## 预算与可追溯性

新台账上限 **24 次 POST**，与已停止的旧 24/19 次台账独立，不改旧结果或重置额度。正常流程每段抽取一次，全部事实组织一次，原文核查/修订一次；三个源计划为 3 + 3 + 4 = 10 次。核查是显式预定阶段，包含在预算中，不是隐藏重试；结构/来源/核查失败立即结束该 profile。没有付费能力探针、自动重发、模型工具执行或故障后的付费回退。

评测器仅进程加载被忽略的 `backend/.env`，不保存密钥、headers、完整环境变量或 reasoning。每次请求前锁定全局唯一调用者，独占创建 payload，fsync 并原子替换台账以预占次数，再发送 HTTP；源码、配置、阶段 system prompt、输出协议、语料与 rubric 在 POST 前复核。真实响应仅保存正文/结束标志/usage；caller 私有诊断 trace 保存来源分段、清理文本跨度、caller ID、事实、候选和核查输出；公开 HTTP 响应仍只有 summary/key_points/provider/model。

有效 quote/span/ID 只证明词法来源可追溯，**不证明 claim 被引用蕴含、核心事实齐全、模型核查为真或外部世界事实正确**。脚本独立核对 source/hash/span/quote/限定字段，人工式 agent 审阅另核对语义及主题组织，不声称独立外部人类评分或普适准确率。[零网络预算安全测试](results/budget-safety.json)使用隔离临时台账，证实实际发送前预占、错误消耗额度、25次拒绝、隐藏阶段重试/配置变化/第二调用者锁拒绝；模拟请求没有污染真实台账。

## 结果

首次 `initial` 离线冻结后发现核查提示错误地描述“原有+新增事实每源≤12”。root 决定与 codec 已有合同对齐：每段抽取≤12，核查新增事实全局≤12，可以补回已满段的漏项。只修正提示，不改容量算法；原 `initial` 冻结保持为**未发请求的历史快照**，新 `initial-contract` 才执行真实评测。

`initial-contract` 在中篇抽取首次失败时停止：**4 次 POST 预占，4 次 HTTP200，9702 个供应商报告 tokens**。短篇正常抽取/组织/核查共3次，中篇仅抽取1次；没有中篇组织/核查或长篇请求。HTTP200 不等于可交付总结。

| 样本 | 结果 | 独立评价 |
| --- | --- | --- |
| 中文短 | 7 点，字数38/26/51/59/40/47/55；摘要382字；7条有效 quote/spans，0新增事实 | 原4条复合事实完整保留，但单独“两个重要环节”元描述占一点，准备/后果分散到两点；比基线5点更碎，摘要接近复述，组织未改善 |
| 英文中 | 抽取 HTTP200，随后本地 `llm_invalid_response` | 首条 quote466字超过400，codec 原因为 `invalid_text`；归因名称不在该 quote 内也违反合同。整批拒绝，没有部分挽救或隐藏重试 |
| 英文长 | 未调用 | 失败立即停止，不能把旧结果或未核查 raw fact 当作本候选成功；14条总体覆盖、类型/范围、长末点和文化归因目标未验证 |

详见[独立评审](results/initial-contract-review.json)、[失败诊断](results/initial-contract-failure-diagnosis.json)与[离线跨度/哈希核对](results/initial-contract-offline-check.json)。短篇所有模型核查 flags 都为 true，独立审阅仍指出组织缺陷；flags/source refs 不是质量评分。该候选不建议提升为默认。

root 根据首轮实际失败批准唯一一次通用修订：quote 上限400→600，不截字；名称允许来自同一 SourcePart 的精确原文位置，caller 另外计算 `attribution_start/end` 并绑定同一来源 hash，任意名称、不同分段或改大小写仍拒绝。提示明确排除只报数量的空纲目、超上限则选完整较窄证据、合并主题并精简概述；未写入数据集答案。正常流程仍 n+2，点长240且无自动重试。

新 `refined` 按最终源码/配置/提示重新冻结后调用，**首条中文短篇抽取就失败**：1次POST、HTTP200、1724报告tokens；第3条 fact 的限定字段 `第一个` 不在其实际 quote（只有 `一个就是…`）内，冻结 codec 原因为 `qualifier_not_found`。原文语义近似不能满足逐字字段合同，整个 payload 拒绝，没有删掉坏字段、部分挽救、修复请求或继续中/长篇；空元描述事实也仍存在。详见[第二候选评审](results/refined-review.json)、[冻结 codec 失败诊断](results/refined-failure-diagnosis.json)与[离线核对](results/refined-offline-check.json)。旧466字失败始终按旧400合同保留，没有用新600合同改称首轮成功。

两次测量累计 **5/24 次预占、5 次HTTP200、11426报告tokens，只有首轮短篇1个可交付结果**。中/长篇没有新可交付结果，原14条复合事实中仅短篇4条在新最终输出上核对；不能声称14/14、长末点改善、文化归因/类型操作范围改进或模型检查准确率。新同分段名称跨度只是已通过离线行为测试的能力，没有这轮真实成功输出证据。

**保持代码默认 `legacy`，不提升 `auto` 或事实策略为默认。** 新能力是显式可选的、失败明确且可追溯的管线；尚未达到质量和实际稳定性目标。本轮付费调用已停止，不使用剩余19次，不复跑失败 phase、不新增测量候选或重置台账。下一步建议优先减少模型逐字复制字段的脆弱性：给原文段落/句子 caller ID，让模型选择已存在证据并由 caller 计算片段/限定位置；仍独立校验语义和取舍，不能放宽为模糊匹配或把 flags 当蕴含证明。

## 复查命令

```powershell
# 零网络预算安全检查
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary/scripts/check_safety.py
# 独占冻结当前实现（已有 phase 文件时拒绝覆盖）
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary/scripts/evaluate.py --phase initial-contract --freeze
# 仅验证源码/配置/阶段提示词/语料与冻结值，不调用模型
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary/scripts/evaluate.py --phase initial-contract --check-only
# 真实评测需该 phase 尚未 started；调用失败仍计数且停止
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary/scripts/evaluate.py --phase initial-contract --system-proxy
# 独立离线证据审核，不调用模型
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary/scripts/check_evidence.py --phase initial-contract
```

同一 phase 不复写、不重新运行；源码变化只能在剩余额度内创建已批准的新 profile。原文跨度对应 `_summary_input` 清理后的输入字符位置，不是 VTT 时间轴。三个源与单次推理不证明跨平台/语言普适表现或供应商严格 schema 保证。
