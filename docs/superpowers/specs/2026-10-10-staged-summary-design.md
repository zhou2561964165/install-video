# 成熟串行编排：主题要点与概览分离

用户已授权成熟方案整改及按任务自主预算。依据首轮[实测失败](../../acceptance-reports/2026-10-10-source-first-summary-live/report.md)，本轮是现有总结链路的局部替换；公开API仍summary/key_points，不增加facts协议。

工程约定：skill优先，UI需ui-ux-pro-max/design-system与三层token；成熟能力实际复用、可配置窄接口、单向依赖；yt-dlp唯一服务边界、视觉只读scene。保护env/db/账号、原证据及其他修改。

## 技术与收益

采用`langchain-core`的RunnableSequence/RunnableLambda进行真实串行步骤及异常传播：最终主题要点生成→独立概览生成→组合为原响应。供应商HTTP仍只在llm_service，显式传入受账本保护的client；不引入模型SDK、并行批量、retry/fallback或额外推理引擎。

必要收益是把本轮模型未遵循的同响应分工变为实际两个调用边界：概览请求不能生成/覆盖要点，先成功的主题内容再生成概览。Pydantic分别验证points-only和overview-only，复用现有类型/schema能力。成熟编排不证明内容准确，仍逐断言人工复核。

LangSmith等传递依赖仅由解析库带入，禁止外部遥测：每次串行invoke必须使用tracing_context(enabled=False)，不读取/发送用户源码、字幕或APIkey给第三方追踪服务。保留锁定版本、许可证与实际依赖记录。

## 生成与容量

- 单段：points-only→overview-only，正常2POST。
- 多段：既有分段笔记→结合完整来源的全局points-only→overview-only；两段正常4POST。复用旧笔记是内部窄接口，必须绑定原source/分段hash和原raw，不把笔记当权威。
- 模型输出先本地处理兼容围栏/空白，所有非空主题内容不裁字删点；超过主题预算时最多1次独立format修复，要求合并相关主题而不删除非空内容，所有attempt计数。网络/provider/来源安全/容量/配置错误不重试，修复失败停止。
- 概览只表达高层主旨/关系，保留其自己涉及的主体/频率/归因；不能用要点中的正确限定修补概览。文化/行为比较作为来源讲者的情境或例子，不推广为普遍规则；指代必须清晰。
- 固定/strict_tool/facts显式兼容路径保留single模式，新增generation mode配置，候选通过前不静默替换这些路径。

## 验收与预算

新修复phase复验短/中各2、长文复用两段笔记后2+最多1format，最多7POST；已用首轮5，新累计硬上限12。用独立预算continuation绑定父5次和原phase/hash，不重开旧失败。单caller串行、持久预占、失败即停。

先TDD验证串行角色隔离、类型/预算/失败终止、一次format上限、原输入不裁剪、外部追踪禁用、旧路径兼容；再独立审查/新freeze，真实内容按原标准评审。不能按HTTP/schema或框架名称宣称质量解决；也不写样本答案。
