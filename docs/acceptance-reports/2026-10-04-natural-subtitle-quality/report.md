# 真实中英文字幕总结评测与输出契约修复

最终实现提交为 `05753e7`。已完成自然字幕评测、DeepSeek摘要输出兼容和1–7条要点的严格校验；**长课的要点组织与简洁性目标尚未达成**。交付源码恢复到已成功处理全部三个样本的 `bounded` 版本，最后未成功的简洁合并候选及此前失败证据全部保留。

## 工程约定

UI/视觉/交互变更先使用 `ui-ux-pro-max` 与 `design-system`；skill优先于计划；颜色、字体和时长走 primitive → semantic → component token；新增能力可配置，模块通过窄接口单向依赖；只有 `ytdlp_service.py` 接触 yt-dlp；视觉层只读 scene、不改变下载状态。此次未修改UI或下载核心，LLM供应商适配仍只在 `llm_service.py`。

## 来源、固定事实与许可

另一个agent在首次模型调用前独立采集、清洗并冻结三份MIT OCW官方自然字幕，没有拼接、人工扩写或生成字幕。来源和许可详见[采集报告](source-report.md)、[manifest](corpus/manifest.json)。manifest及其中的事实/源锚点SHA256为 `c5426b5d1fb9c5381af2a5e223905f163301be1087167fc5b42ef9f79e6640d3`，评测过程中未按输出修改期待。

| 样本 | 原始清洗文本字符 | 总结服务去重后字符 | 默认分段 | 预先固定主要事实 |
| --- | ---: | ---: | ---: | ---: |
| 中文短课：沉浸式课堂 | 608 | 608 | 1 | 4 |
| 英文中课：每日评分 | 2199 | 2199 | 1 | 4 |
| 英文长课：What is Computation? | 34894 | 34658 | 2 | 6 |

长课另有5条 `detail_if_present`：只有输出提及时才检查准确性，省略这些细节不算主要事实覆盖失败。核心事实按 **summary与key_points整体** 核查，不意味着每个字段各自完整；数字、频率词和示例范围另检查。执行者和独立只读复核者都是agent，未进行外部独立人类评分、全声明精确率或统计稳定性研究。

MIT源字幕、清洗文本、模型生成的改编摘要、源摘录及相应衍生评测内容保留署名和 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 非商业、相同方式共享限制；出处、作者、改动说明见manifest。不能据此宣称这些数据可自由商用。工具脚本与产品代码不由本报告重新指定许可。

## 真实调用与不同实现版本

所有调用使用已有配置的 `deepseek / deepseek-flash`，中文输出。评测受控固定为默认分段配置：chunk 20000、单次输入60000、最多16段、输出4096 tokens；**没有沿用用户 `.env` 对分段参数的覆盖值，也没有修改 `.env`**。源码、system prompt、语料/事实hash在各版本第一次调用前冻结；新兼容版本还冻结配置源码和实际解析后的输出参数。

| 版本 | 实际POST/HTTP响应 | 结果与限制 |
| --- | ---: | --- |
| `before` | 5 / 5 | 三样本正常返回6/7/7点；主要事实覆盖，无纯语义重复，但存在同主题碎片和长末点306字 |
| `after` | 3 / 3 | 组织提示修改后短/中返回5/6点；长第一段缺JSON闭合符，停止 |
| `validation-long` | 3 / 3 | 根明确触发的一次长课验证；合并时4096输出tokens全部用于推理，回答为空，停止 |
| `compatible` | 5 / 5 | 增加JSON输出、关闭摘要推理和JSON示例；长第一段8点、最终12点，旧parser误接受；不能算契约成功 |
| `bounded` | 5 / 5 | 增加严格数量校验及分段/合并数量指导；三个样本返回5/6/7点，选为交付版本 |
| `concise-long` | 3 / 3 | 最后一次只调整合并组织指导；两段各7点，合并11点被严格拒绝；候选回退 |

共 **24个预占尝试、24个确认HTTP响应，均HTTP200；提供商报告合计89567 tokens**。HTTP200不表示摘要契约合格。台账的24上限已耗尽，不允许清空或重置继续调用；没有自动POST重试。上述根明确触发的评测版本均独立命名、冻结和留证，不覆盖失败版本，亦未作为原请求的自动重试。计划中的19或21次预算预测不能替代最终24次实测。

## 实测缺陷与修复

第8响应缺少 `key_points` 的闭合 `]`，既有严格JSON解析正确报 `llm_invalid_response`。第11响应 `finish_reason=length`、content为空，4096 completion tokens全部被报告为reasoning tokens，既有完整性检查正确报 `llm_incomplete_response`。[DeepSeek推理文档](https://api-docs.deepseek.com/guides/thinking_mode/) 说明默认启用推理；[JSON输出文档](https://api-docs.deepseek.com/guides/json_mode/) 支持JSON模式，但仍可能为空，数量和字段契约不能只依赖JSON语法保证。

新增两项启动时校验的配置，保持供应商默认规则数据驱动：

| 配置 | 可选值 | `auto` 行为 |
| --- | --- | --- |
| `LLM_SUMMARY_RESPONSE_FORMAT` | auto / text / json_object | DeepSeek摘要发送json_object；其他供应商不额外发送 |
| `LLM_SUMMARY_THINKING_MODE` | auto / enabled / disabled | DeepSeek摘要发送disabled；其他供应商不额外发送 |

只摘要请求使用这些控制；翻译不接收它们。明确 `text` 不发送response_format；明确设置可覆盖默认，未知兼容服务由操作者按其能力选择。system prompt保留来源仅作数据、安全边界和合法JSON示例，严格parser、输出4096上限及无POST重试保持。

第14/16响应的8/12点暴露旧parser仅检查类型和非空的问题。现对规范空白后的要点数量严格要求1–7；超限报 `llm_invalid_response`，**不截断列表或删除尾部事实**。第24响应虽然JSON有效、finish_reason为stop，11点仍被正确拒绝。仅最后候选合并提示被回退，交付保留JSON/推理兼容、数量校验及分段/合并指导。

## 质量结论与剩余问题

详见[逐事实复核](results/review.json)及[修改前诊断](results/baseline-review.json)。交付版本的14条预先固定主要教学事实在摘要与要点整体中有覆盖，包括45/5分钟、私密反馈、算法终止条件及末尾已计算结果不会自动重算的教学意思。**这不等于14条输出完全精确，也不等于其他声明均准确**：

- 短课6→5点，中课7→6点，只观察到有限合并；同主题原则与支持细节仍分布在多个点，有新事实的支持条件不能算纯语义重复。
- 长课最后一点306→426字，仍把对象、类型、运算、赋值和输出打包，简洁性没有改善。最后候选改成较短句却返回11点，应用拒绝，不能当作成功优化。
- 中课把源字幕的“usually, after class”写成“每节课后都会”，频率限定过强。
- 长课保留不自动重算的意思，但泛化“其他依赖变量”而省略具体标量radius/area示例范围，仍有范围过宽风险；不声称该表述是所有依赖关系的通用规则。
- 中间 `compatible` 版本还曾把约十亿写成“数十亿”、混淆storage与memory；交付 `bounded` 版本恢复十亿和存储数百GB。失败候选对3.2*5的语义解释也不应当作准确交付证据。

最终对照同时改变了组织提示、JSON示例、JSON模式、推理模式及数量验证，不能把观察结果全部归因某一句prompt。只测试了两个MIT课程的三个视频，没有多轮稳定性、其他供应商在线兼容或普遍总结质量保证。

## 验证与证据归档

新增行为测试先失败再实现：输出控制/配置验证9个失败变为通过；数量边界8/12先错误接受，再正确拒绝，1/7保留且只发送一次POST。最终后端 **184项**通过；前端 **66项**和构建通过。已知Starlette/httpx弃用warning单独保留，不是测试失败。提示语不以字符串镜像测试伪装质量验证。

[交付绑定](results/delivery-profile.json) 将最终源码/配置hash、实现提交 `05753e7`、实际输出控制及三个 `bounded` 结果hash绑定；其源码与 `bounded-service.py` 字节完全一致。每个版本的provenance、服务源码副本、phase index、结果及每次响应hash均留存，[request-ledger.json](results/request-ledger.json) 共24条。最初采集时git HEAD为 `47a1ad8`，没有事后改写为新提交。

新报告目录采用 `.gitattributes` 的 `-text` 保存证据原始字节，避免Windows的core.autocrlf改变冻结hash。以下检查只在本地校验，不发提供商请求：

```powershell
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-natural-subtitle-quality/scripts/check_evidence.py
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-natural-subtitle-quality/scripts/check_safety.py
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-natural-subtitle-quality/scripts/evaluate.py --phase bounded --check-only
```

`check_safety.py` 使用临时台账和本地HTTP替身，验证发送前预占、失败占预算、第25次被拦及结果覆盖被拒，不能当作模型质量证据。真实阶段的开始标记与结果不可覆盖；当前预算已封顶，不应删除锁/结果/台账以重新执行。

下一步应解决长课的核心主题选择与支持细节压缩，并单独核查频率词/示例范围；继续保留严格契约和事实完整性，不能用截断或只减少字数代替质量改进。本报告没有把这项未完成目标标为已达成。
