# 来源优先总结与旧结果生命周期整改

2026-10-10。用户授权实际采用有帮助的成熟方案，要求选型有依据并同步设计。设计：[来源优先局部设计](../../superpowers/specs/2026-10-10-source-first-summary-design.md)。

工程约定：skill优先；UI使用ui-ux-pro-max/design-system、三层token；数据驱动、窄接口、单向依赖；yt-dlp唯一服务边界、视觉只读scene。复用已有资料与有效验证，不修改参考源码、env/db/账号、历史账本与原始证据。

## 采用的成熟能力及实际收益

1. **Pydantic v2已有依赖**：新增独立`summary_output.py`，由库接管summary/key_points的严格类型及JSON Schema生成。移除服务内重复手写类型与schema定义；不新增依赖，不导入配置、HTTP、SDK或远程遥测。实际本机/锁定版本2.13.5。
2. **借鉴并适配官方来源优先建议**：请求指导模型先定位原文主张及主体/频率/条件/归因，再写完整主题要点，最后写高层概览。JSON示例及schema属性key_points在前、summary在后；所有公开字段、单块1POST、原文分段/有限合并与adaptive预算保持。
3. **成熟异步结果生命周期**：新操作清空该kind旧结果；active匹配时清空显示，保留其他kind缓存、AbortController与请求编号保护。根因是原hook开始/失败时保留旧summary，组件继续按active显示，与此前浏览器结果一致。

选型已核对LlamaIndex TreeSummarize单块仍只生成一次，新splitter也不能直接解决2,199字符中篇组织问题；Refine默认处理结构异常后继续的模式需额外适配。此次实际采用已有库与适用方法，未因名称成熟而增加没有明确收益的引擎。官方依据：[Pydantic strict](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/)、[JSON Schema](https://pydantic.dev/docs/validation/latest/concepts/json_schema/)、[Anthropic提示建议](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)。

## TDD与针对性回归

| 验证 | 实际结果与范围 |
| --- | --- |
| 后端初次测试配置 | 缺PYTHONPATH导致collection错误；修正后才执行有效RED，不将此环境错误计为语义失败 |
| 后端新增RED | 13 failed / 4 passed：两项schema/JSON例子顺序失败，11项新codec尚未实现；全部是机械行为，不是模型质量红测 |
| 后端GREEN及相关回归 | **108 passed in 0.48s**；新17项+既有LLM/adaptive91项，非历史全量重跑 |
| 前端RED | hook4项，1 failed / 3 passed，重做summary仍残留旧结果按预期失败 |
| 前端GREEN | hook **4/4 passed**；重做时立即清空、失败后不恢复、其他类型缓存保留、过期响应不覆盖 |
| 独立静态审查 | 无Critical/Important；库确实接管结构能力、compat/strict预算边界保持、无隐藏调用/重试、错误不暴露raw |

compat仍先拒绝非字符串point，再strip/drop空白项后计数；8项含1空项预算7可接受。strict保留extra、空项及原字符串长度边界；adaptive不增加固定字符硬拒。非空内容不截点裁字，strict_tool供应商槽转换保持。异常映射为原LLM错误类别，Pydantic验证详情不直接显示到UI。

后端命令：`PYTHONPATH=backend`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，项目Python `-B -m pytest --noconftest -p no:cacheprovider backend/tests/test_summary_output.py backend/tests/test_llm_service.py backend/tests/test_adaptive_summary.py -q`。

前端命令：在frontend执行`npm exec -- vitest run src/hooks/useVideoInsights.test.jsx`。没有构建或全量测试。

## 真实浏览器针对性回归

复用上一轮owned HTTP工具，以browser_only启动当前代码；没有修改或重跑旧20API/4页面/10guard的脚本/原证据。新隔离headless Edge与既有账号临时JWT，仅实际操作中篇解析→生成总结成功→注入本地上游503→再次总结。

- API实际响应200解析、200总结、502再次总结。
- 成功结果可见；失败后旧summary节点不存在，错误alert可见且按钮恢复；pageerror0。
- 本地供应商 **2/20 HTTP POST**，真实供应商 **0 POST**。固定输出为传输夹具，不用于语义评分。
- 临时API/source/Vite三个端口实际关闭，服务主线程停止，live DB哈希不变。原118个跨阶段证据基线哈希不变。未执行密码登录、下载、翻译、移动/GPU或新收费phase。

证据：[ui-regression.json](evidence/ui-regression.json)、[临时API报告](evidence/report.json)、[错误后的页面截图](evidence/summary-after-failure.png)、[本轮验证汇总](evidence/validation.json)。

## 当前完成与剩余边界

**已完成实现及离线/局部浏览器验证**：成熟结构组件复用、来源优先/要点先写指导、旧结果生命周期修复与设计同步。

**未证明解决**：中篇每节课评价遗漏、评分理由重复、信念归属弱及新版长文真实质量。Pydantic保证结构，schema顺序与提示只表达生成要求；不能保证供应商实际生成顺序，也不代表完整独立quote extraction或LangGraph多调用链。

旧组仍26/26 POST、152726供应商tokens、六phase closed。新代码没有调用真实模型、另建付费组/phase或自动回退；真实内容验收需明确新有限预算、独立freeze/ledger/tracker及单caller持久预占。原短/中内容评分只对应旧冻结提示，不能转记到此新候选。所有修改未提交、推送或部署。
