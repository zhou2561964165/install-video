# Ragas 独立语义评测实施计划

工程约定：成熟组件优先、窄接口/单向依赖；不改yt-dlp层、UI或账号/env；UI如涉及须使用ui-ux-pro-max/design-system及三层token。旧证据原字节保留。

用户已明确按照Ragas独立评测方案继续。范围为评测器实现与有限对照，不将评测分数作为产品成功保证。继续使用原feature工作区；新的工具目录与独立虚拟环境隔离依赖，生产pyproject/uv.lock及phase7冻结资产不改。

## 设计与边界

- `tools/semantic_eval`独立uv项目，锁定Ragas 0.4.3；真实调用其collections.Faithfulness，复用官方分解/NLI提示与评分。不复刻评测引擎。
- 窄LLM适配接口将Ragas的结构化请求交给受控HTTP caller；使用当前已验证的DeepSeek Responses schema协议，串行、零重试/零fallback、显式token和输入上限、关闭遥测。
- 记录原摘要、分解后断言、逐条verdict/reason，校验断言和verdict一一对应。空结果/非0或1 verdict/遗漏/重复拒绝，不能把总平均分当关键断言正确。
- 人工标签与coverage问题仅在离线评测端使用，不加入生成/核查提示；正确/范围扩大/频率/否定/时间/归因合成对照，另复用真实phase4源与摘要作为诊断。
- 先校准真实性；保留现有独立coverage准则，faithfulness不证明摘要覆盖全部核心主题。验证跨语言分解是否保留原错误，不默许翻译修正。
- 独立结果目录、冻结清单及持久账本；共享现有caller锁。当前phase7保持frozen/0POST；新语义对照按独立phase记录且引用原历史组hash/10POST，不抹旧计数。
- 首轮最多16 POST（8样本×2），每请求最多4096输出tokens、60000输入字符；供已定位的范围问题/正反例与真实坏摘要诊断。错误即停并封账；若仍需额外阶段必须明确原因和有限上限，不自动续跑。

## 任务

- [x] A：建立独立依赖锁；审查Ragas公开接口、遥测与调用路径。Ragas0.4.3导入与最新版langchain-community的移除模块不兼容，独立项目固定0.3.31并完成安装；生产依赖文件无diff。
- [x] B：TDD实现真实Faithfulness适配器，暴露逐断言结果及失败语义。root最终工具集成78项离线通过。
- [x] C：建立6条合成对照+2条真实phase4局部对照；独立复核标签、34894字符完整source、7项绑定SHA均匹配。
- [x] D：实现有限caller/冻结/台账与离线测试，验证任何网络请求必须先预占。runner20项包含转义凭据回显拒绝；root最终工具集成78 passed/18.09s，exit0。
- [x] E：独立代码审查、受控离线检查后执行新有限实测；16/16 POST、34106tokens，closed/verify通过。8例误放1、误拒0；真实P4错误被全支持，不能接生产门。报告漏判及分解保真，不因高分宣称解决。
- [x] F：同步当前交接与使用命令、实际结果、未解决边界。当前入口`docs/handoff-2026-10-15-semantic-eval.md`；产品未接Ragas、公开长文未恢复，后续按单独正常生成计划推进。

## 接口与所有权

Adapter worker仅维护`tools/semantic_eval/ragas_adapter.py`与`tools/semantic_eval/tests/test_adapter.py`。样本worker仅维护`tools/semantic_eval/cases.json`和`tools/semantic_eval/CASE_NOTES.md`。caller worker仅维护`runner.py`及其测试；独立reviewer仅写`review.md`。root维护其余文件/依赖/台账/文档并独占真实HTTP执行。输入样本含id、source、response、expected_supported、error_kind、core_questions；标签不传judge。adapter `evaluate(source, response, complete)` 返回可JSON序列化字典；complete为同步`(prompt: str, response_model: type) -> dict`，所有HTTP仅在root caller中。
