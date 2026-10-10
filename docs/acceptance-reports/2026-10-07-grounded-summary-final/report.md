# 总结质量收尾：修订与独立真实验收

本轮按用户要求多 agent 并行继续总结质量收尾。此前 refined 失败、输出、冻结合同和台账保持原样；新 phase 为 `organization-final`。用户在明确最多13模型POST及供应商费用后回复“继续”，授权本轮一次实测；实际9预占/9HTTP200后因长文抽取合同失败停止，余4不使用。短中8项核心事实为7完整/1部分，长6未评；整体质量尚未完成。

## 工程约定

适用技能优先；UI/视觉/交互先 ui-ux-pro-max 与 design-system，颜色、字体和时长采用 primitive → semantic → component 三层 token。能力配置化、窄接口单向依赖，避免大规模重构；yt-dlp 仅经 ytdlp_service.py，LLM 仅经 llm_service.py，视觉层只读 scene，不修改下载状态或导入下载核心。用户 .env、数据库、模型资产与历史证据保持。默认 legacy；正常 n+2，无自动重试或隐藏付费回退。MIT 来源及衍生评测保留署名、CC BY-NC-SA 4.0 非商业与相同方式共享要求，见[原语料许可](../2026-10-04-natural-subtitle-quality/corpus/LICENSE.md)。

## 目标与既有证据

沿用既有抽取 → 全局主题组织 → 来源核查设计，修复已测得的复合事实遗漏和主题重叠，准备一次新的短／中／长最终验收。不向产品提示注入 rubric 答案，不逐次放宽最终边界。

- refined 中篇所缺的改进目的、成绩录入／本人账户读取、发音反馈已经存在于抽取事实；首次丢失发生于 compose，audit 沿用不完整文字。引用完整 fact ID 不代表对应子句完整表达。
- 短篇同一主题的原则和具体条件被分成不同事实、不同要点，audit 未完成要点合并。
- 长篇先前 compose 的 8 条声明／1060 字符触发当时声明数量限制；现有候选 14 条／1600 字符余量已离线修复。缺失 F2_3 引用不会在当前候选阶段阻断 audit，最终 core 引用要求继续保留。

原件及独立语义评分见[refined 报告](../2026-10-07-grounded-summary-refined/report.md)与[逐子句审核标准](../2026-10-07-grounded-summary-refined/semantic-review-checklist.md)。

## 本轮修订范围

生产改动限定 llm_service.py：增强通用复合事实与来源覆盖核查，提示按主题合并相关原则、条件与原因；给原计划 audit 提供 caller 计算的缺失核心引用 ID，作为修复定位信息。该列表只揭示引用缺口，空列表不能证明文字完整或语义正确。

最终 summary 最多 7 条声明／800 字符，key_points 最多 7 个、每点最多 240 字符；候选仍最多 14 条／1600 字符。公开 summary/key_points/provider/model 返回形状保持，codec、默认配置与调用次数不变。

验收入口新增独立目录、phase 与最多 13 POST 的预算边界，复用原冻结 14 essential 标准。实际模型调用仅由主 agent 一个 caller 串行执行，发前持久预占，任何错误即停。旧三份台账剩余额度不使用、不合并、不重置。

## 验证状态

主 agent 集成后的完整后端测试为 **540 passed、1 条既有 Starlette 弃用提示**，11.35 秒：

```powershell
# 在 backend/，全部源码测试；不收集历史运行产物
../.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp E:/install_video/tmp/summary-final-integrated-20261007
```

新覆盖定位测试 3 项有红 → 绿记录；真实 refined 原件回放 6 项首次运行时生产字段已到位，属于补充验证，不伪称前置红记录。新入口 52 项专项通过，新旧预算／checker 守护组合 144 项通过，均为本地替身，不计真实模型质量。

独立生产与新入口复审均无 Critical／Important／Minor 缺陷。默认入口 plan 显示 `network=false`、独立 `organization-final`、预计 13 POST；`git diff --check` 通过，仅既有文件 CRLF 提示。主 agent 核对三个旧台账哈希未变，当前 codec／config 与本轮初始快照字节一致。准备阶段真实POST为0的[code-delivery记录](results/code-delivery.json)保留原样；后续9POST结果单独记录，不覆盖准备快照。

基线 `pytest tests -q` 为 479 passed、1 条既有 Starlette 弃用提示；裸 pytest 误收集 backend/tmp 下两个拒绝访问的历史目录，本轮不更改权限、不删除历史产物。基线记录不能代替修订后的测试。

新入口默认计划与零网络准备命令已执行：

```powershell
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-final/scripts/evaluate.py
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-final/scripts/evaluate.py --freeze
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-final/scripts/evaluate.py --check-only
```

freeze 成功，实测前重新check-only `match=true`。本轮[冻结 provenance](results/organization-final-provenance.json)与三份源码快照保存。`--freeze` 与 `--check-only` 由 runtime 内部读取本地供应商配置，不打印／保存 API key，不发送网络请求；本轮 `.env` 不编辑。实际主agent只执行一次 `--run --system-proxy`，沿用refined三个样本均已使用的代理路径，不额外发模型连通性探针。

## 本轮真实测量结果

[预算授权](results/budget-authorization.json)、[独立台账](results/request-ledger.json)、[来源/合同核对](results/organization-final-offline-check.json)及[证据复核](results/organization-final-evidence-review.json)完整保留。

独立13POST上限实际使用 **9预占、9响应、9HTTP200**，所有finish_reason均为stop；供应商报告 **32656 tokens = 24522 prompt + 8134 completion**。缓存hit/miss为prompt子集，不重复计数、不据此估算费用。剩余4次不使用、不续跑失败phase。

| 样本 | 实际/预计请求 | 流程与最终输出 | 核心事实审核 | 组织 |
| --- | --- | --- | --- | --- |
| 中文短篇 | 3/3 | audit完成；4点、摘要239字符 | 4完整 | partial：原则与备课说明仍可合并 |
| 英文中篇 | 3/3 | audit完成；5点、摘要258字符 | 3完整/1部分 | partial：反馈示例/文化对比/教材反馈仍碎片化 |
| 英文长篇 | 3/7 | 第3段extract失败；前19facts校验通过，无compose/audit/final | 6 not_evaluated | not_evaluated |

长文ordinal9返回完整JSON，但13条事实超过冻结extract上限12，冻结codec回放确认invalid_count；completion1727并未截断。失败发生于part3，不把前19事实或未通过的13事实当最终覆盖，不删第13条、放宽上限、重试或追加请求。[准确诊断](results/organization-final-failure-diagnosis.json)保留原响应hash。

## 语义与精度结果

[短中逐子句审核](results/organization-final-short-medium-semantic-review.json)：已交付8项为 **7完整/1部分/0缺失**，相比refined同8项5完整/3部分，en2改进目的、en4发音反馈恢复，en3本人账户读取恢复但成绩录入仍遗漏。两篇组织均partial，中篇从原pass退为可合并碎片，不能因更多字或更多点宣称全面改善。

确认1项Important精度问题：中篇摘要使用“廖浩翔”，允许的本地材料只提供罗马字姓名，不能唯一支持该汉字写法。未联网断定现实姓名错误；这里判断的是输出缺乏允许来源支持。en1保留“相信”的讲者观点，en4保留讲者课堂示例与“有时”回应范围；full评分不代表所有输出无精度问题。

[长文审核](results/organization-final-long-semantic-review.json)：long1–6全部not_evaluated，可选long7–11、precision、organization同样未评。原分母14不变，只有8项有最终结果，不能宣称14/14。审核是agent基于冻结来源的定性复核，并非外部人类评分或统计准确率；短中reviewer此前参与提示修订，非盲评，这一限制已披露。

## 真实验收与完成条件

本轮预算已执行并停止，不再续跑。当前生产代码、配置、三阶段提示、codec、runner／所有 wrapper、来源和rubric仍与测量freeze一致；默认legacy不推广，代码尚未新建提交。

长文结构失败在连续三轮迁移到不同边界，下一步先复审有限生成结构与全局主题规划，见[合同复审](contract-review.md)。不继续逐个放宽上限或用prompt补丁掩盖未解决的结构与语义问题。任何新协议修订要先零网络回归，再另建独立phase和明确新预算；旧剩余额度不用。

后续完成条件仍是新长文真正获得audit后的有效输出、原14核心复合事实全部核对，以及归因／频率／条件／范围、主题组织和末尾结果审核。HTTP200、引用ID、checks=true、字数减少、离线测试都不能替代该验收。
