# 长文摘要组织后续开发（2026-10-07）

本轮接续[审查结论](../2026-10-07-grounded-summary-review/report.md)，新建文档与证据目录，不覆盖旧报告或冻结结果。长文旧响应在截断前包含18个完整点及第19个点的完整文本；本轮针对主题组织失控与预算/容量边界进行开发。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system、三层token；配置化、窄接口单向依赖；yt-dlp仅ytdlp_service，LLM仅llm_service，视觉只读scene。不改UI、.env、用户db、模型资产、旧台账。默认legacy，正常n+2，无自动付费重试/回退。MIT源与衍生内容保留原署名和CC BY-NC-SA4.0非商业许可。

## 实现

- compose 私有输出固定 point_1…point_7；第一槽必须有效，闲置槽仅允许末尾null。纯codec严格解析并转换为旧CandidateSummary，不删点、不截字、不接受第8槽、缺槽、间隙、重复字段、无效引用。audit与公开API保持原形状。
- compose提示先把全局事实归并为主题，再填写槽；同主题的原则、条件、例子可引用多个fact ID，不能按事实或分段逐项输出。
- 最终摘要硬上限可配，默认800字符；compose/audit各有独立输出预算，默认0继承全局4096。显式覆盖只影响指定阶段，extract与legacy保留全局值。容量检查和HTTP发送同预算。
- 首次测量后增加有限候选摘要余量：compose候选最多2倍最终上限（默认1600），交给原计划audit精简；最终仍800，1601候选或946字最终输出拒绝，不截字、不增阶段。初次模型profile并不包含此改动，原失败仍失败。

| 新环境变量 | 产品默认 | 范围/含义 |
| --- | --- | --- |
| LLM_SUMMARY_FACTS_MAX_SUMMARY_CHARS | 800 | 1–4000，总摘要字符上限 |
| LLM_SUMMARY_FACTS_COMPOSE_MAX_OUTPUT_TOKENS | 0 | 0继承全局，正值1–65536 |
| LLM_SUMMARY_FACTS_AUDIT_MAX_OUTPUT_TOKENS | 0 | 0继承全局，正值1–65536 |

## 当前验证

- codec/配置首轮15项失败后修复通过；pipeline阶段预算/槽合同3项失败后通过；摘要长度在正确槽协议生效后单独复现失败并修复。
- Task1后端全量399通过；完成评测入口及集成修复后434通过。测量后的候选余量与提示修订交付代码最终437通过，保留1条既有Starlette/httpx弃用提示。git diff --check通过。
- `test_grounded_organization.py`：4项零网络回放通过。原54事实经真实codec/编排校验，5extract+compose+audit=7调用；第8槽、非法预算及容量不足有明确停止行为。

回放的compose/audit响应由测试合成，**不计为真实模型生成、语义准确、主题质量或14条复合事实覆盖验收**。挂fact IDs及mock flags=true不是语义正确证明。

## 新发现的输入容量限制

保留全部原文和54事实后，最小audit载荷约71138字符；产品默认LLM_MAX_INPUT_CHARS=60000不足。测试确认在实际audit发送前明确报llm_input_too_large，前6个正常阶段仍计成本，54事实不丢弃。

本轮拟测profile显式使用：facts策略、8000字符分段、100000输入字符、summary800字符、extract4096及compose/audit8192输出tokens。没有修改用户.env或产品全局输入默认。

## 真实测量（单次已授权13POST）

独立 `organization-slots` phase 的13POST新台账入口已完成，预计中文短3＋英文中3＋英文长7。默认只打印计划；freeze/check/run互斥，只有明确run才发送。freeze/check/run在导入配置前以override=False读取同一环境配置；import/默认计划不读取.env。配置顺序回归修复前失败、修复后通过。

31项新入口测试＋13项旧预算测试合计44通过；独立reviewer复审产品与入口，未发现其他重要缺陷。

初次测量前已冻结源码/提示/config/codec/rubric、entrypoint/base runner哈希及阶段预算，check-only match=true；经用户审批运行一次。新独立台账**12/13预占、12HTTP200、52880供应商报告tokens**，剩1不使用。旧台账仍48/49，未借用或修改。

| 样本 | 请求 | 最终输出 | 来源核查 |
| --- | --- | --- | --- |
| zh-short | 3 | 3点，摘要117字，点长75/38/54 | 12事实；audit合同完整 |
| en-medium | 3 | 5点，摘要164字，点长41/54/30/52/52 | 11具名事实；来源位置与audit合同完整 |
| en-long | 6：5extract+compose | 无最终结果，无audit请求 | 48事实抽取；compose因summary_too_long拒绝 |

长文compose完整JSON、7槽、点长110/79/118/137/144/166/138，finish_reason=stop、1747输出tokens。7条摘要声明合计946字，超过冻结版本的800硬上限；没有重现19点或输出截断，但没有最终核查结果。只报告此样本所见行为，不能宣称模型普遍遵守槽合同或长文已交付。

冻结codec诊断见 [failure-diagnosis](results/organization-slots-failure-diagnosis.json)；加强后的冻结版本离线检查见 [offline-check](results/organization-slots-offline-check.json)，事实位置12/11/48全部成立，但语义正确未由此证明。

## 独立语义审阅及测量后修订

对照未改的原rubric，仅在已有最终输出的8个复合核心事实上：**5完整、3部分、0缺失；长文6个核心事实未在新最终输出上评分**。逐项见 [semantic-review](results/organization-slots-semantic-review.json)。

- zh1部分：第一天准备与期望保留，但大纲遗漏。zh2/3/4完整。
- en1部分：持续一致努力保留，但讲者信念/预期加强为“即可”。en2/3完整。
- en4部分：文化回应与教材例子保留，但讲者示例范围弱化、sometimes加强为“常说”；中篇汉字姓名也不是来源英文拼写可唯一推出的依据。
- 短P1/P2局部重叠备课一致性，中P3–P5仍碎分文化反馈主题；有新增信息，不判为全纯同义重复。更短的文字不等于完整或准确。

审阅是独立agent对真实输出和已许可来源的核对，不是外部人工评分或普适准确率。根据实际失败/precision问题，当前代码在离线修订后给候选摘要2倍有界余量，并加强通用提示：观点/文化示例保持讲者或课程范围、sometimes不加强为often、专名保留来源写法或泛称、不逆推汉字姓名，audit明确修订过长摘要。未注入语料答案。

候选余量回归红→绿，最终800上限及1601候选拒绝仍通过，134专项通过；当前codec对同一旧3087字符响应离线解析可接纳946字候选、7点和全部core IDs，见 [post-measurement replay](results/post-measurement-offline-replay.json)。该回放**没有执行真实audit，不是新的模型成功结果**。437全量及独立增量复审通过。

```powershell
# 项目根：默认计划、冻结历史原件复查（只读，不重写原结果）
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-organization/scripts/evaluate.py
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-organization/scripts/check_evidence.py

# 当前源码已在首次测量后修订，evaluate --check-only预期失配。
# 不能再run或重启organization-slots，不能覆盖其冻结文件/台账。
```

## 后续交接

本轮实现与测量已归档；当前修订需要另一独立phase与明确新预算，再做三源（预计13POST）及原14条复合事实的完整语义/主题验收。不得用剩余1次续跑已失败phase，也不能把旧槽候选或离线回放当作长文已验收。

默认legacy不提升；.env/db/下载/UI/模型资产未改。当前代码与本轮证据保留在工作区，未新建提交。

设计：[2026-10-07设计](../../superpowers/specs/2026-10-07-grounded-summary-organization-design.md)；计划：[实现计划](../../superpowers/plans/2026-10-07-grounded-summary-organization.md)。
