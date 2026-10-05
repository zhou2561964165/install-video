# 严格结构化输出与真实字幕重点组织评测

## 工程约定

UI/视觉/交互修改先使用 `ui-ux-pro-max` 与 `design-system`；skill 优先于计划；颜色、字体、时长使用 primitive → semantic → component token；新增能力可配置；模块通过窄接口单向依赖；只有 `ytdlp_service.py` 接触 yt-dlp；视觉层只读 scene，不改变下载状态；LLM 提供商细节保留在 `llm_service.py`。本评测脚本不修改产品模块或 UI。

## 预先固定的评价方法

复用[此前冻结的 MIT 自然语料与 14 条主要事实](../2026-10-04-natural-subtitle-quality/corpus/manifest.json)，不重新获取、生成或修改字幕。不重新付费运行旧 baseline：绑定 `05753e7` 的 `bounded` 源码与 5/6/7 点结果 hash。新增问题标准在任何本轮输出前保存在 [rubric.json](rubric.json)。

事实覆盖按 summary 与 key_points 整体进行语义核验；数字、频率、归因和例子范围另外检查。只出现关键词不算正确；同一主题增加新条件或后果不算纯重复。目标是减少旧长文末点 426 字符的混装，保留主要事实、停止条件与结尾已计算面积不自动重算的具体例子；字符变少本身不能证明质量提高。

## 预算与能力探针

本轮独立持久台账最多 20 次真实 POST，包含能力探针、分段、合并以及失败。每次发送前在跨进程锁内先 fsync 预占，失败仍计入；无自动 POST 重试，无失败后付费格式降级。旧 24 次台账完全只读。

能力探针是自行编写的测试内容，使用产品 schema 和实际模型选项，但独立冻结 system/user 指令。一个要求空 summary 和零要点，另一个要求八个超过 350 字符的要点，用于分别挑战 minLength/minItems 与 maxItems/maxLength。它们不属于 MIT 自然字幕质量样本。HTTP 成功、JSON 有效、字段完整、数量与长度合格分别统计；本轮遵守约束不代表服务器绝对保证，也不代表内容事实正确。

原计划仅在两个探针均成功后才选择生产 auto 的严格模式。实测失败后保持已工作的 json_object 默认，把协议实验与自然质量实验分开；自然实验先冻结最终生产源码，再运行短/中各一次、长两段与一次合并，共五次 POST。若测量确实需要一次修正，先冻结另一个 profile 后重新评测，不覆盖失败证据。

## 许可与归因

MIT OpenCourseWare 字幕、清洗文本以及模型生成摘要和相关衍生复核继续按 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 署名、非商业、相同方式共享。出处、作者、改动说明详见原 manifest 与[来源报告](../2026-10-04-natural-subtitle-quality/source-report.md)；课程作者为 Dr. Haohsiang Liao / MIT 与 MIT 6.0001 教师团队。MIT 不为本产品或模型输出背书。评测工具脚本及产品代码不由本报告重新指定许可。

## 已实测的协议限制

| profile | 预占 POST | 确认 HTTP | 本轮实际结果 |
| --- | ---: | ---: | --- |
| `capability` | 2 | 2（200） | Responses 空值探针返回非空摘要与一个点；过量探针仍返回八点，应用正确拒绝 |
| `tool-capability` | 1 | 0 | `ConnectError`，无法据此判断 Beta 协议支持与否 |
| `tool-capability-verified` | 1 | 1（200） | Beta strict 工具正确返回指定工具及所有必需字段，但第一点空字符串违反非空 pattern，应用正确拒绝并停止 |

协议能力阶段共四次预占、三个 HTTP 响应，不可把传输失败计为已收到响应。失败 profile 不重置、不覆盖；也没有自动模式降级后追加 POST。工具参数仅作为结构化输出读取，从未执行工具或发起第二轮工具对话。

官方 [strict 工具能力说明](https://api-docs.deepseek.com/guides/tool_calls/)不支持数组 minItems/maxItems 和字符串 minLength/maxLength；因此另用七个必需点槽和支持的 pattern 表达边界。但本轮真实请求仍违反第一点非空 pattern，不能把 strict:true 接受、正确字段或工具结束标记等同于完整约束执行。本轮证据不足以切换生产 auto 到严格协议默认，也不能声称已验证最大长度的服务器保证。

第一次工具探针的网络错误后，另作两个系统代理下的无凭据只读 GET，官方根路径和模型路径均到达 TLS/HTTP 并返回 401。这仅说明当时网络可达，不算付费 POST，也不证明请求会成功。结果见 [network-get-probe.json](results/network-get-probe.json)。

## 自然字幕质量：首次 profile

`natural-auto` 冻结生产字节并使用实际 auto → json_object/关闭推理运行，三样本共五次 POST，全部 HTTP 200 且应用成功。单点 240 字符在兼容模式为组织提示的软目标，不是服务器或本地硬保证。短/中/长分别返回 6/5/7 点，旧 `bounded` 对照为 5/6/7 点。

[逐事实复核](results/natural-auto-review.json)显示原 14 条复合主要事实中 11 条完整、3 条部分保留：中课漏明确录入成绩；长课漏程序崩溃/不停的结果；长课虽在总述中保留抽象赋值绑定，但丢失 radius 重绑定后已计算 area 不自动重算的具体结尾后果。此结尾在第二段输入完整存在，却在第二段输出已经消失，不能只修合并阶段。

中课现保留 usually-after-class，文化对比仍未明确归于教师观点；持续努力与技能之间也有保证式措辞风险。短课主题组织未改善，相关准备条件仍拆开；这些条件包含不同事实，因此没有据此伪报“纯语义重复”。长末点从 426 降到 304 字符，却继续混装对象、转换、输出与运算符并失去重要结尾事实，不能把字符下降当成精简成功。

首次自然质量 profile **未达到本轮组织和事实完整目标**。随后只实施一次测量驱动修正，另冻结 `natural-refined`，保留首次失败证据；它与严格协议约束实验分别记录。

## 最终默认 profile 与剩余质量问题

`natural-refined` 保持 auto → json_object，增加一般性全段与结尾条件/结果指导，并把每段原字幕头尾证据传到合并输入。新增 `LLM_SUMMARY_SOURCE_CONTEXT_CHARS` 默认 1200：每段头尾各至多 1200 字符，中间有明确省略标记；设 0 保持旧 notes 格式。容量计算包括证据，分层合并保留已携带内容；它不能恢复未携带的中间事实，也不代表完整原文都穿过每层。

该 profile 三样本五次 POST 全部 HTTP 200、应用成功，返回 5/5/7 点。重要结尾 radius 改变后已计算 area 不自动重算、程序错误输出/崩溃/不停止恢复。第二段输出已保住这些内容，合并还收到原字幕证据；因此只能说联合修正后恢复，不能把结果单独归因于证据携带机制。

[最终逐事实复核](results/natural-refined-review.json)保守评为原 14 条复合主要事实 **12 条完整、2 条部分保留**：Engrade 录入成绩能力仍缺；类型限制可用操作的原原则未明确保留，只给数字运算结果类型例子。文化对比仍无教师归因，泛化“其他变量不自动重算”及原 +/−/* 运算范围也有风险。长末点 **365 字符**，仍混装多个主题并超过 240 软目标。因此 **长文组织与完整精确性目标仍未达标**，不以点数、字符数或核心主题出现替代逐声明准确性。

最终生产选择该兼容默认 profile，保留获得的重要结尾修复；不把显式严格协议设为默认。

[交付绑定](results/delivery-profile.json)绑定当前源代码/config 字节、实际 auto 控制与安全端点元数据、1200 证据参数、全部六阶段 index 和三个逐事实 review、原始 baseline 与最后台账 hash。分段/输入/输出限制按此前固定默认值在评测进程中设置，没有改 `.env`。实际默认仍 json_object/关闭摘要推理。

## 显式 strict_tool 正常输入烟测

为避免只凭离线测试交付新显式模式，最后另冻结 `natural-tool`：相同生产源码、配置、原字幕、1200 证据与模型，仅改为显式 strict_tool，实际请求路径为 `api.deepseek.com /beta/chat/completions`。这不是第二次提示优化，也不是把对抗失败的模式提升为默认。

该阶段五次 POST 全部 HTTP 200。短课返回七点、中课六点，均通过本地字段、连续槽位、1–7 数量和 240 长度校验；两段长课中间结果也通过。但是最后合并的第七点 **294 字符**，违反最大 240 的 pattern，本地正确报 `llm_invalid_response`。长课没有成功应用结果，原失败参数仍留证，不能拿它评分为完整有效总结。参见[显式模式复核](results/natural-tool-review.json)。

短/中课八条主要事实保留，中课成绩录入能力这次明确出现，usually 也正确，但教师文化观点归因仍有问题。短课用满七点更碎，数量结构合法也不能证明组织质量。工具从未执行，没有追加工具回复 POST，没有付费降级或重试。

## 最终台账与只读复核

| 阶段 | 预占尝试 | 确认 HTTP 响应 |
| --- | ---: | ---: |
| Responses 对抗能力 | 2 | 2 |
| 最初工具能力（传输错误） | 1 | 0 |
| 网络验证后的工具对抗能力 | 1 | 1 |
| 首次自然默认 profile | 5 | 5 |
| 唯一默认 refinement | 5 | 5 |
| 显式工具正常输入烟测 | 5 | 5 |
| **合计** | **19 / 20** | **18（全部 HTTP 200）** |

提供商报告累计 **52062 tokens**。一次 ConnectError 没收到 HTTP 响应，仍占预算；两个无凭据 GET 不占 POST 预算。保留六个冻结 profile，旧 24 次台账、语料、事实和 05753e7 结果未改。**付费调用已停止，不为剩余一个名额继续尝试，也不自动补失败请求。**

以下只校验本地文件、原始 hash、预占行为或指标，不发送模型请求：

```powershell
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-schema-summary-quality/scripts/check_evidence.py
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-schema-summary-quality/scripts/check_safety.py
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-schema-summary-quality/scripts/metrics.py
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-schema-summary-quality/scripts/evaluate.py --phase natural-tool --format strict_tool --check-only
```

`check_safety` 只使用临时本地替身，证明发送前 fsync 预占、传输失败计预算、第 21 次拒绝、互斥及证据不可覆盖；它不是上游 schema 或模型质量证据。真实阶段不可清空开始标记/台账或覆盖结果重跑。Markdown/代码/结果需保持报告目录的原始字节，避免换行转换破坏冻结 hash。

此评测只有两门 MIT 课程的三份样本、每个 profile 各一次推理，复核者是 agent；没有外部独立人工评分、完整逐声明精确率或多轮稳定性结论。下一步应处理主要主题预算、观点归因与具体范围，严格模式则先解决实际供应商约束遵守，不能靠继续堆提示或截断结果宣称达标。
