# 总结质量受控评测 · 2026-10-04

## 工程约定

- UI/视觉/交互先使用 `ui-ux-pro-max` 与 `design-system`，颜色、字体与时长走三层 token。
- 技能优先于计划；能力数据驱动、可配置，避免大规模重构。
- 核心通过窄接口与单向依赖通信；`ytdlp_service.py` 是唯一接触 yt-dlp 的层；视觉层只读 `scene`，不修改下载状态或 import 下载核心。
- 本轮质量改动限定 `llm_service.py` 的总结提示词；保留摘要与关键要点 API、去重/分段/合并、失败分类和 LLM POST 单次请求行为。

## 结论与实测范围

当前配置的 `deepseek` / `deepseek-flash` 服务对短、中、长三个自编源文本分别进行 before/after 评测，共 **12 次实际 LLM HTTP POST，全部返回 200**。长样本每次使用三个默认 20000 字符分段和一次合并。请求在发送前占用持久化计数，未配置或执行 POST 自动重试。调用时间、序号、状态和供应商返回的 token 用量见 [request-ledger.json](results/request-ledger.json)。没有写出 API key、请求头或完整环境。

测得的主要问题是旧提示词要求最低三条要点，导致只有一件事实的短通知被拆成地点、日期和原因三个片段。中长内容还存在重复批准范围和低价值日志占据输出的情况。更新提示词后短通知变为一条完整要点，长样本将被否决的旧日期与有条件的最终日期合到同一要点，且首部数字、中部发现和末尾决策均保留。长摘要仍包含低价值日志计数、两个要点仍重复“仅批准试点”；没有把部分改善描述为完全去重。

## 独立语料与预期

语料在首次调用前固定；[manifest.json](corpus/manifest.json) 给出所有源文本 SHA-256、独立必需事实和不应虚构的事实。[build_corpus.py](scripts/build_corpus.py) 可重新生成相同文本。文本为本项目自编人工场景，可随项目分发，未读取历史 raw/raw-extra 目录或修改其 ACL。

| 样本 | 原始 / 清理后字符 | 默认分段 | 独立检查内容 | 结果 |
| --- | --- | --- | --- | --- |
| [短通知](corpus/short.txt) | 236 / 58 | 1 | 周一图书馆维护闭馆；不编开馆时间或替代场所；一件事实不拆点凑数 | before 3碎片 → after 1完整点；事实保留 |
| [中等会议](corpus/medium.txt) | 2411 / 2410 | 1 | 2400元上限、18个分12/6、6月17取代6月10、四周、低于22%仅人工检查、连续三天缺读暂停、未批准扩展；不编供应商/单价/节水比例 | before/after均保留7项；显式未批准扩展集中到末条，部分试验范围上下文仍出现 |
| [长压力文本](corpus/long.txt) | 40441 / 40441 | 3 + 合并 | 48000元上限、1200条六周试点、17处不匹配；尾部8月12被否决/9月9有条件、干净审计与成功回滚、Noor可停止发布；不编生产停机/完成/可靠性结果 | before/after均保留6项；7点 → 6点；批准范围仍有语义重复 |

真实服务输出原文分别见 [before.json](results/before.json) 与 [after.json](results/after.json)。[review.json](results/review.json) 是按 manifest 的事实逐项人工对照记录，检查摘要和要点的组合覆盖；这不是独立人工评分，也不是完整精确率或召回率指标。

## 改动与验证

`backend/app/services/llm_service.py` 只调整 `_summary_request` 的系统提示词：**1–7 条**完整、不同的重要事实；短内容不补点；保留准确数字、条件与最终决定并区分已被取代的建议；压缩重复、低优先观察。解析器原本就允许一条非空要点，API 字段不变，没有新增语义过滤算法。

提示词改动通过相同源文本真实 before/after 进行验证，没有写源码字符串或提示词文字镜像测试。`backend/tests/test_llm_service.py` 新增已有行为的保护用例：

- 超过整体 60000 字符的文本分段传送，模拟提供方仅从每段实际内容抽取事实，再从实际段摘要合并；断言首部48000/1200与尾部9月9条件/Noor权限都进入最终结果，且只各出现一次。它证明服务层传递与合并输入完整，不证明模型理解质量。
- 供应商只返回一个完整要点时，服务原样保留而不填充；它保护新提示词允许一条要点时的 API 消费契约，属于既有解析行为，修复前也会通过。

定向运行：`backend` 下 `..\.venv\Scripts\python.exe -m pytest tests/test_llm_service.py -q` → **18 passed**。本分支没有新增产品逻辑修复，所以新增两个测试是已有契约保护，不声称经过失败→修复的逻辑红绿周期。全量验证由主 agent 在其他工作流整合后执行。

## 复现与预算

`--phase` 不是切换旧/新提示词的开关。before 必须使用基线 `b62f7d429becfc00a2db9140be505c9ffeb53a20` 的 `_summary_request` 提示词；after 必须使用本轮修改后的提示词。[provenance.json](results/provenance.json) 在评测结束后通过安全 AST 提取补记两个提示词原文、SHA-256、源码引用与源码哈希，并绑定已有 before/after 结果的原始字节哈希；未重放模型或修改结果/台账。

before 系统提示词 SHA-256：`54b7a814a7c61459ba276f3b5d664a5231096cc81ff43b18f6f869350efed23e`；after：`99e99ec6c9e019e879d38bf0e8cd6bd4a068ece89737b1e45c3646b115db4c2e`。`run_quality.py` 会在读取代理或发送 POST 前核对当前源码中的提示词哈希匹配所选阶段，并在每次 POST 前再次核对实际请求提示词。错误版本不能仅更改标签就冒充 before。

下面是原评测顺序；新评测须先获得调用授权、使用新的证据目录，并携带相应 provenance。不能在当前 after 代码下执行 before 来重现基线：

```powershell
& '.venv\Scripts\python.exe' 'docs\acceptance-reports\2026-10-04-summary-quality\scripts\build_corpus.py'
& '.venv\Scripts\python.exe' 'docs\acceptance-reports\2026-10-04-summary-quality\scripts\run_quality.py' --phase before --system-proxy
# 在获得设计授权并修改提示词之后：
& '.venv\Scripts\python.exe' 'docs\acceptance-reports\2026-10-04-summary-quality\scripts\run_quality.py' --phase after --system-proxy
```

本次已存在 before/after 文件，脚本会拒绝覆写；已耗尽的持久化12次预算也会拒绝继续调用。不要删除现有计数或结果来继续本轮计费调用。未来获得新评测授权时应在新的日期目录复制脚本/语料并使用独立证据和预算。脚本只将被忽略的 `backend/.env` 加载到该评测进程；`--system-proxy` 使用该进程临时 client 代理，不修改环境文件或系统设置。

无需 HTTP 的版本核查：`run_quality.py --phase after --check-provenance-only` 在当前源码通过；`--phase before --check-provenance-only` 在当前源码明确拒绝。该 CLI 核查只是实验溯源保护，不是产品提示词文字镜像测试。

## 限制与下一步

这只是三个人工英语源、中文输出、每个版本各一次实测。长文本的重复演练叙述是分段压力样本，不代表自然对话/各平台字幕分布；真实源没有超过60000字符，超过该长度的证明来自本地 deterministic 测试。未做多轮稳定性、独立人工评估、所有事实的完整精确率、字幕说话人或音画对齐评估。

before 短/中/长耗时约1.59/7.30/15.72秒，after约1.84/12.69/20.83秒；单次网络、缓存和模型输出长度不同，不能据此宣称延迟改善。提示词能缓解凑点，但仍不能保证没有遗漏或语义重复。下一步建议另行授权一组真实自然字幕与独立人工核查，优先评估长内容低价值观察、要点重复与事实条件保留；本轮12次预算已全部使用。
