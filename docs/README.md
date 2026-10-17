# 项目文档索引

> **F-003最终交验（2026-10-17）：** 用户已查验通过，含最新小圈显示范围与标题倾斜。角色不自动漫游，手动拖动后保持新位置，原待机动作继续；小圈两侧和普通按钮/链接/菜单/空白处均可见，仅顶部、模型alpha轮廓和解析表单避让。详情见[待机行为交验](implementation-reports/2026-10-17-f003-original-behavior.md)和[小圈范围交验](implementation-reports/2026-10-17-f003-circle-scope.md)。

> **F-006交验（2026-10-17）：** 实现与验证完成，等待用户查验。游客/认证恢复中显示首页，顶部登录按钮显式进入AuthScene；匿名解析提示登录、不发业务API；返回及认证成功回首页保留URL但不自动解析。认证后端授权不变。Edge认证API使用mock，真实账号登录未测，完整范围见[F-006报告](implementation-reports/2026-10-17-f006.md)。

> **2026-10-16交验记录为历史阶段：** 当时的自由漫游和暂停功能已按后续用户要求撤销；原测试数字只适用于当时实现。当前F-003行为与验收范围见本页顶部的2026-10-17交验链接。

更新：2026-10-17。当前先读[后续整改与计划总表](follow-up-plan.md)，再读[phase15完整交接](handoff-2026-10-16-deepseek-step1.md)；产品能力查[需求](requirements.md)、[设计](design.md)和[根README](../README.md)。[综合UI/发布交接](handoff-2026-10-10.md)保留其他模块的历史状态。

最新状态：F-003已由用户查验通过（包含最新小圈范围）；F-006实现与验证完成，等待用户查验。F-001长文质量问题保留，所有后续计划统一进入[总表](follow-up-plan.md)。F-001结果见[长文交验](implementation-reports/2026-10-16-f001.md)，F-002见[居中交验](implementation-reports/2026-10-16-f002.md)，F-003最新证据见顶部链接，F-006报告见[实施报告](implementation-reports/2026-10-17-f006.md)。

## 当前任务与结果

**F-004全项目文档审查与整改：已完成。** 修订和静态核验见[完成记录](follow-up-plan.md#6-f-004文档审查记录2026-10-16)。下段phase15来源结果属于既有实测。

**F-005实际技术架构审视与文档更新：已完成。** 当前运行拓扑、状态/并发、LLM组合及DOM/PIXI边界已更新到[design](design.md#1-架构总览)，[完成记录](follow-up-plan.md#9-f-005技术架构审视2026-10-16)保留依据和独立复核。发现的结构整改项另有状态，不将已完成审视重新列为待办。

用户限定只用DeepSeek、先完成第一步，后续听指示。phase15固定Pro/high单次全文，两份新来源各1次，2POST/23275tokens并closed。英文7/8项核心完整，存在转换前提遗漏和局部退出条件错误；中文4/4项完整、无确证核心事实错误，但重复扩写明显。没有跨模型对照或后续核查/修订，不能称总体质量通过。

| 当前资料 | 用途 |
| --- | --- |
| [后续整改与计划总表](follow-up-plan.md) | 所有后续计划统一登记；最新用户决定、待办和状态 |
| [实际架构设计](design.md#1-架构总览) | 当前运行图、锁版本、模块/数据流、LLM组合和前端依赖；历史方案明确标注 |
| [2026-10-16完整交接](handoff-2026-10-16-deepseek-step1.md) | phase15阶段入口：已完成工作、当时产品边界、计数与证据；最新安排见总表 |
| [第一步实测报告](acceptance-reports/2026-10-16-deepseek-source-screen/report.md) | phase15配置、2次调用、耗时、费用估算和工具验证 |
| [第一步内容审阅](acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md) | 两来源覆盖、确证错误、源内歧义、重复和实用性 |
| [原样回答与字幕](../exports/deepseek-step1-2026-10-16/) / [zip](../exports/deepseek-step1-2026-10-16.zip) | 原回答、正文、VTT与manifest，未校订输出 |
| [phase15工具审查](acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-15-deepseek-source-tool.md) | 新24项离线与独立审查边界，不等于生产全量或语义通过 |
| [路线与当前停止边界](summary-route-decision-2026-10-15.md) | A、B、组合实验和同模型来源观察的区别 |
| [前端说明](../frontend/README.md) / [UI扩展指南](ui-extension-guide.md) | 已实现界面、token/scene边界与历史UI验证范围 |

长文组phase1–15全部closed：23POST/319471tokens；Ragas独立16/34106；持续整改合计**39POST/353577tokens**。旧67POST各组原封账，不借余额、不重开。F-001新增0模型POST；短中仍`legacy/adaptive/single/fidelity=off`，公开长文另用独立Pro配置，不直接导入历史runner。

## 工程约定

适用skills优先；UI先用`ui-ux-pro-max`+`design-system`及primitive→semantic→component token；颜色/字体/时长集中配置，能力数据驱动，窄接口与单向依赖，yt-dlp仅经`ytdlp_service.py`，视觉只读scene。新能力优先复用成熟方案，已有研究见[选型资料](reference-summary-review-2026-10-10.md)，有效规则见[AGENTS](../AGENTS.md)。

历史报告、raw、snapshot、ledger、receipt、scripts和冻结审稿保留原字节。当前说明与旧阶段有差异时，按其采集时点解释，不改旧评分。旧“下一步/等待授权”均属历史，不触发后续开发、测试、freeze或模型调用。F-003已有验证仅见本节与交验报告；本次文档同步没有追加产品测试、启动服务或调用模型。

## 历史维护资料与验收索引

历史原件的已知错误路径、过强结论及最终评分说明统一见[总表§7勘误](follow-up-plan.md#7-历史原件勘误与阅读指引)；phase1–15和Ragas的报告/独立内容审阅连续入口见[总表§8](follow-up-plan.md#8-已封账阶段的证据入口)。下列旧计划/specs和报告中的“当前/下一步”按记录时点阅读，原字节不改。

**当前角色行为（F-003，已查验）**：非手机且宽度>800px时加载角色；角色保持当前位置，手动拖动后停在新位置，原待机、换装、表情和道具行为继续。手机UA或≤800px不创建模型、图片fallback或角色交互面。小圈按可见alpha轮廓接触避让，顶部及显式解析表单也避让；内容列两侧、普通按钮/链接/菜单和空白处显示小圈，标题倾斜随全视口位置变化。模型拖动边界未改。当前证据见[待机行为交验](implementation-reports/2026-10-17-f003-original-behavior.md)与[小圈范围交验](implementation-reports/2026-10-17-f003-circle-scope.md)；2026-10-13嵌入、跟随报告均为历史阶段。

**最新续测**：新窗口已补快速滚动/连续resize、恢复/媒体设置、兼容降级及本地角色拖动/触摸模拟；22类检查有通过证据。Headless Edge没有实际触发后台hidden，原生pinch在最小对照页面也未放大，真实窗口/真机缩放仍未证明。产品源码不变、模型/平台/媒体0，见[续测报告](acceptance-reports/2026-10-13-ui-follow-continuation/report.md)。此前171前端/build、10专项+17UI等仍按原报告的历史范围阅读。

2026-10-13全站UI继续深入参考皮蛋 AI / DeepSeek：浅色默认、三档主题、浮动玻璃导航、圆润标题/宽输入框/胶囊页签与淡彩点阵背景，PIXI装饰收敛为光斑和光尘。前端171项及build、17项模拟接口浏览器检查和实际本地Live2D菜单/resize通过；后端仅按用户要求启动，旧模型质量结论不变。见[全站UI深度迭代](acceptance-reports/2026-10-13-ui-reference-deep/report.md)。

2026-10-13捕获B站间歇风险校验响应：当前代理开启下3次失败，随后显式代理/直连各一次成功，22/36 metadata GET后停止，未改系统网络。主播放响应识别与专属提示已整改；具体诱因和稳定下载仍未证明。范围与最终检查见[网络诊断及校验提示](acceptance-reports/2026-10-13-bilibili-verification/report.md)，模型/完整媒体0。

2026-10-13字幕轨道反馈：用户报告B站`BV1B84y1q7Hr`获取字幕时显示“平台字幕轨道结构无效”。当前代码对空列表按无字幕处理，对`null`/非列表轨道报结构错误；本轮未重新请求该视频核对实际payload。画面文字OCR方案已登记为后续候选，暂不启用/实现。当前状态见[需求§8.7](requirements.md)与[设计§4/§9](design.md#4-核心数据流)。

最新视频功能已按用户提供参考项目适配：白蓝双栏、同屏下载/内容页签、返回输入与TXT导出；指定B站AI字幕路径修复后实际API成功。当前范围见[本轮报告](acceptance-reports/2026-10-12-reference-video-workflow/report.md)，新模型0POST，旧内容评分不改。

2026-10-12使用范围记录（历史）：网页默认按视频原标题保存，保留可选来源直链；当时短中总结开放、长文超上限拒绝。最新用户已允许长文上线使用但质量继续整改，入口代码尚未在本轮调整；当前任务与后续边界以[统一总表](follow-up-plan.md)为准，下列冻结报告及失败评分保留原件。

| 文档 | 用途 |
| --- | --- |
| [两方案执行决策](summary-route-decision-2026-10-15.md) | 路线历史与当前停止边界；A/B/组合各自状态，第一步已完成后听指示 |
| [phase13直接委托报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md) | 完整字幕直送Pro并导出的执行时点记录；后续独立评分见phase13-content-diagnosis，原报告不回写 |
| [语义评测与长文交接（2026-10-15）](handoff-2026-10-15-semantic-eval.md) | phase1–14阶段回顾，已归档；当前任务先读[统一总表](follow-up-plan.md)，phase15证据读阶段交接 |
| [phase12容量对照报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-12-report.md) | cap1已closed；返回15点但precision仍失败 |
| [phase12逐项内容诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-12-content-diagnosis.md) | coverage、precision、概览与组织评分及原文依据 |
| [主题规划与逐主题写作候选](superpowers/plans/2026-10-15-topic-writing-candidate.md) | 纯B保留设计，未实现/实测；phase13实际用于A，不按旧计划分配或执行 |
| [phase11完整来源诊断报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-11-report.md) | cap1已closed、34离线测试、独立工具审查及实际内容分数 |
| [phase11逐项内容诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-11-content-diagnosis.md) | long1–6 coverage、精度、概览和组织的独立评分及source行号 |
| [Ragas实测与独立语义审阅](acceptance-reports/2026-10-15-ragas-semantic/report.md) | 独立成熟Faithfulness，16POST/8例，真实P4误放；未接生产门 |
| [phase7实测失败](acceptance-reports/2026-10-13-long-summary-fidelity/phase-7-report.md) | 1POST后字段超长停止，P4仍漏判，无修订结果 |
| [长文总结phase 1–5验收报告](acceptance-reports/2026-10-13-long-summary-fidelity/report.md) | 9POST/147600 tokens，全部phase closed；P4范围错误未解决，phase 5 checks响应截断且未进入revision |
| [长文总结phase 6报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-6-report.md) | 1POST/13208 tokens；quote大小写差异后首错停止，P4仍失败 |
| [主体范围核查候选设计](superpowers/specs/2026-10-14-subject-scope-relation-checks.md) | phase7 schema/提示/有限预算方案；不构成语义验收或默认配置 |
| [phase7生产独立审查](acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-7-subject-checks-production-final.md) | subject schema/请求路径及121项相关测试的代码审查；C/I/M均0，不能证明语义修复 |
| [phase7 runner独立审查](acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-7-subject-checks-tool-final.md) | 历史26项离线/C/I/M均0；后续真实1POST失败，不构成内容通过 |
| [角色嵌入开发验收（历史阶段）](acceptance-reports/2026-10-13-embedded-mascot-refinement/report.md) | 2026-10-13 embedded/mask/相对拖动实现及当期验证；当前桌面行为见F-003交验 |
| [F-003待机行为交验](implementation-reports/2026-10-17-f003-original-behavior.md) | 当前用户已接受的待机、拖动、手机资源门控与小圈联动 |
| [F-003小圈范围交验](implementation-reports/2026-10-17-f003-circle-scope.md) | 当前用户已接受的小圈全视口显示、避让范围与标题倾斜 |
| [F-006交验报告](implementation-reports/2026-10-17-f006.md) | 登录入口实现、最终复核、mock浏览器与本地权限验证边界 |
| [F-003初始交验（历史阶段）](implementation-reports/2026-10-16-f003.md) | 视口漫游/暂停阶段的验证范围；行为已由后续更新覆盖 |
| [角色嵌入与跟随细节方案](superpowers/specs/2026-10-13-embedded-mascot-follow-refinement-design.md) | 新录像布局、单处“试试”、token与避让依据；最初仅方案阶段已转入实施 |
| [录像跟随新窗口续测](acceptance-reports/2026-10-13-ui-follow-continuation/report.md) | 新增行为检查/本地角色，22类通过证据；真实后台及真机pinch未证明，源码/选定原件哈希不变，模型0 |
| [录像跟随与小字精简](acceptance-reports/2026-10-13-ui-follow-video/report.md) | 当前实现、已有检查及新窗口测试移交；10项跟随专项，原录像仅本机，模型0 |
| [全站UI深度迭代](acceptance-reports/2026-10-13-ui-reference-deep/report.md) | 统一token/导航/登录/入口/工作台与粒子；171前端、build、响应式/交互和本地舞台验证，模型0 |
| [较早完整长文复验（2026-10-12）](acceptance-reports/2026-10-12-summary-long-final-check/report.md) | 旧组closed3POST/32432tokens；累计16/153697，新完整long14点结构/6项full，精度FAIL，原件不改；当前结论见2026-10-16交接及phase15报告 |
| [有限容量/限定复验](acceptance-reports/2026-10-12-summary-content-capacity-repair/report.md) | closed3POST；累计13/121265tokens，短中PASS、长14点结构通过但内容FAIL |
| [本地无损规范化复验](acceptance-reports/2026-10-11-summary-content-local-repair/report.md) | closed5POST/52139tokens，短PASS、中summary限定FAIL、长reasoning耗尽输出容量 |
| [总结内容验收恢复](acceptance-reports/2026-10-11-summary-content-resume/report.md) | closed5POST/44968tokens，short/mediumPASS、long缺JSON闭合且诊断精度FAIL；原件不改 |
| [角色交互收尾](acceptance-reports/2026-10-11-ui-interaction-finish/report.md) | pointerId/多指恢复/局部pinch与焦点；前端151项/build、Edge15项、真实parse3次（预算2→3，仅补完整封面解码），模型0，真手机未验证 |
| [阶段分离实测](acceptance-reports/2026-10-10-staged-summary-live/report.md) | closed6POST/28851tokens；累计11，两role实现但短中仍fail、长20点回显fail |
| [原生Schema/Pro实测](acceptance-reports/2026-10-10-schema-pro-summary-live/report.md) | closed6POST/25728tokens，累计17；三源结构通过，内容未全过，候选不推广 |
| [原生schema/Pro对照设计](superpowers/specs/2026-10-10-schema-pro-summary-design.md) | 实测后的协议/模型有限对照，父11/新phase最多6/累计17，已实测并封账 |
| [来源优先首轮实测](acceptance-reports/2026-10-10-source-first-summary-live/report.md) | closed5POST/19776tokens；短pass、中限定fail、长20点超14结构fail，原件保持 |
| [串行阶段分离设计](superpowers/specs/2026-10-10-staged-summary-design.md) | 实际LangChainCore编排/禁追踪、双角色与有限format；复用leaf的修复phase≤7，累计≤12 |
| [来源优先成熟方案整改](acceptance-reports/2026-10-10-source-first-summary/report.md) | Pydantic实际复用、要点先写指导、旧结果修复；108后端/4hook与局部浏览器通过，真实模型质量未验证 |
| [来源优先局部设计](superpowers/specs/2026-10-10-source-first-summary-design.md) | 实际采用方案、未引入大框架的具体理由、兼容性与调用预算边界 |
| [新候选内容验收](superpowers/plans/2026-10-10-source-first-summary-acceptance.md) | 首phase5及后续6+6已完成；10→12→17有限调整，所有phase封账 |
| [正式 HTTP 流程补验](acceptance-reports/2026-10-09-online-formal-flow/report.md) | 2026-10-10：API20/20、页面4/4、旧工具故障10/10；该次零付费，“模型待预算”为当时状态，此后有限实测已执行封账，见总表阶段索引 |
| [参考代码与成熟方案复核](reference-summary-review-2026-10-10.md) | 2026-10-10静态代码及当时官方资料：15,000字符限制、旧结果处理借鉴与候选方案；后续实际状态由总表解释 |
| [自适应字幕总结](handoff-2026-10-09-adaptive.md) | 历史交接：旧候选结论；当前先读[统一总表](follow-up-plan.md)，phase15证据读2026-10-16交接 |
| [有限总结修复计划](superpowers/plans/2026-10-09-adaptive-summary-repair.md) | 两版通用提示已实施/有限复验已执行；验收预算耗尽，内容质量仍未全过 |
| [最终有限复验](acceptance-reports/2026-10-09-adaptive-summary-final/report.md) | closed2POST；短篇通过，中篇逐课评价/重复/归属缺陷未通过 |
| [首修复复验](acceptance-reports/2026-10-09-adaptive-summary-repair/report.md) | closed2POST；互补能力恢复与残余错误，保留未通过候选 |
| [设计文档](design.md) | 当前代码对应的架构、接口、鉴权、额度、总结分层与实现边界 |
| [需求/实施状态](requirements.md) | 已实现能力、候选功能、未解决质量问题与未验证范围 |
| [根README](../README.md) / [前端README](../frontend/README.md) | 当前安装、启动、环境配置及前端交互说明 |
| [UI扩展指南](ui-extension-guide.md) | 当前token、主题、模块职责及扩展方式边界 |
| [长文验收](acceptance-reports/2026-10-09-adaptive-summary/report.md) | 已关闭3POST阶段；长文实际输出与内容复核 |
| [修复前短中篇验收](acceptance-reports/2026-10-09-adaptive-short-medium/report.md) | 已关闭2POST历史候选；其缺陷不能覆盖最终新结果 |
| [短中篇验收准则](acceptance-reports/2026-10-09-adaptive-short-medium/review-criteria.md) | 已用于本轮审查的覆盖、条件、归因和组织标准 |
| 本机历史执行草稿（不入库） | 四个验证步骤均完成；公开证据以上述验收报告及snapshot为准 |

## 历史工程与验收档案

下表的测试数量、授权等待和待办均指各自记录当时。旧任务列表不作为新入口；旧26/26等各组与后续39POST持续整改计数分别封账，不合并余额、不重置旧尝试。保留原证据，复用已经完成且仍有效的实现与检查。

| 文档 | 历史用途 |
| --- | --- |
| [核查质量续验收](acceptance-reports/2026-10-09-summary-quality-repaired/report.md) | 原17POST阶段的输出、失败和离线修复，不是当前总账 |
| [摘要质量历史交接（2026-10-09）](handoff-2026-10-09-quality.md) | 当时模块、1325全量验证、有限复验边界；不作为当前摘要质量入口 |
| [核查质量收尾计划](superpowers/plans/2026-10-08-summary-quality-finish.md) | 当时模块职责、独立审查与有限验收范围；非当前执行计划 |
| [摘要模块化与对应子句复验](acceptance-reports/2026-10-08-grounded-summary-clause/report.md) | 当时三模块/965回归、25有限调用及封账时质量缺口 |
| [摘要质量历史交接（2026-10-08）](handoff-2026-10-08-normalized.md) | 当时代码、分类策略、模型计数与离线事项；当前状态见2026-10-16完整交接 |
| [规范化与引用实施计划](superpowers/plans/2026-10-08-summary-normalization-retries.md) | 模块边界、并行写集、分类修复与冻结验收要求 |
| [规范化首轮](acceptance-reports/2026-10-08-grounded-summary-normalized/report.md) / [marker复验](acceptance-reports/2026-10-08-grounded-summary-marker/report.md) | 独立8与4POST、两个已定位并离线修复的故障，保持旧失败原件 |
| [开发账号与前缀续验收](acceptance-reports/2026-10-08-grounded-summary-prefix/report.md) | 当时不限下载账号/855与84回归、3次有限实测失败及质量缺口；不代表此次重新核对账号 |
| [开发授权历史交接（2026-10-08）](handoff-2026-10-08-development.md) | 当时模型路由/持续授权与额度配置；本索引顶部交接反映当前有限续行状态 |
| [开发账号实施计划](superpowers/plans/2026-10-08-development-quota-validation.md) | 配置化现有账号豁免、UI状态与有限模型组预算 |
| [有限合同与全局主题](acceptance-reports/2026-10-07-grounded-summary-contracts/report.md) | 当时代码/706全量、冻结与待预算状态；该报告没有新增模型质量结果 |
| [contracts历史交接](handoff-2026-10-08-contracts.md) | 当时接口/编排/checker、资产与预算；旧恢复命令不自动执行 |
| [合同设计/计划](superpowers/specs/2026-10-07-grounded-summary-contracts-design.md) / [实施计划](superpowers/plans/2026-10-07-grounded-summary-contracts.md) | 用户已继续的有限槽与主题分配私有协议，公开API/n+2不变 |
| [总结质量收尾](acceptance-reports/2026-10-07-grounded-summary-final/report.md) | 当时修订、540项回归、独立9/13实测与质量缺口 |
| [前轮final交接](handoff-2026-10-07-final.md) | 前轮冻结与实测状态、预算停止、只读复查命令与完成条件 |
| [生成合同复审](acceptance-reports/2026-10-07-grounded-summary-final/contract-review.md) | 连续三轮不同结构边界失败、有限生成结构与全局主题规划建议，未实施 |
| [剩余工作](remaining-work-2026-10-07.md) | 本轮开始前的质量缺口、完成条件和后续候选范围 |
| [refined 交接](handoff-2026-10-07-refined.md) | 前轮 12/13 实测、5 完整／3 部分／长文 6 未评及离线候选修订 |
| [handoff.md](handoff.md) | 历史交接：当时状态和用户决策；当前先读[统一总表](follow-up-plan.md)，阶段证据/UI/发布再读对应交接 |
| [v3实现计划](superpowers/plans/2026-10-03-v3-video-intelligence.md) | v3早期API、分层与当时验证范围；当前实现见design/requirements |
| [扩展路线](superpowers/plans/2026-09-21-extension-plan.md) | v2/v3已实现状态及后续候选，不作为自动执行授权 |
| [参考实现分析](reference-summary-implementation.md) | 参考项目观察、独立实现选择与已测限制 |
| [历史事实/主题设计](superpowers/specs/2026-10-05-grounded-summary-design.md) | 当时来源/事实/声明/核查设计；facts及后续规范化已成为显式兼容实验，整体质量未通过，不能将“暂停/未交付”套作当前全部实现状态 |
| [历史事实/主题实现计划](superpowers/plans/2026-10-05-grounded-summary.md) | 当时合同、编排和评测分工；旧计划不再作为活动执行清单 |
| [事实/主题本轮实测](acceptance-reports/2026-10-05-grounded-summary/report.md) | 新5预占/5HTTP，短篇首轮成功、中/长未完成、默认未推广 |
| [本轮schema/布局计划](superpowers/plans/2026-10-04-schema-quality-responsive-layout.md) | 协议实测、原始证据贯穿、角色布局/触摸和未达目标 |
| [摘要协议与质量](acceptance-reports/2026-10-04-schema-summary-quality/report.md) | 19预占/18HTTP/1连接失败，默认与实验模式各自质量/契约边界 |
| [响应式角色/手势](acceptance-reports/2026-10-04-responsive-mascot/report.md) | 基础41项、最终触摸5项、焦点局部成功/字体网络失败、GPU与模拟范围 |
| [前轮自然质量计划](superpowers/plans/2026-10-04-natural-quality-mobile-gpu.md) | 前轮自然字幕、输出控制/数量修复、公网移动/GPU与未达质量目标 |
| [自然字幕实测与输出修复](acceptance-reports/2026-10-04-natural-subtitle-quality/report.md) | 新24次POST，6个profile/失败原件/选定bounded源码，质量残余 |
| [独立自然字幕来源](acceptance-reports/2026-10-04-natural-subtitle-quality/source-report.md) | 原生中英文608/2199/34894字符，许可、hash与预先事实锚点 |
| [公网移动与GPU](acceptance-reports/2026-10-04-public-mobile-gpu/report.md) | 375px 9项/1保存文件；RTX4050 16K纹理/角色，真手机与布局限制 |
| [前轮增量计划](superpowers/plans/2026-10-04-platform-browser-summary.md) | 前轮已授权范围、文件分工与完成结果 |
| [真实平台扩展](acceptance-reports/2026-10-04-platform-expansion/report.md) | Bili匿名正文、inline/native回退、访问限制与确定性回归 |
| [完整浏览器验收](acceptance-reports/2026-10-04-browser-e2e/report.md) | 本机双视口40项/6保存文件，与独立公网Archive桌面9项 |
| [总结质量评测](acceptance-reports/2026-10-04-summary-quality/report.md) | 固定语料、真实模型12次before/after、prompt溯源与残余问题 |
| [平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md) | 此前三平台字幕请求、LLM总结、质量抽查、下载闭环与TLS限制 |

## 历史证据阅读顺序

- [摘要协议/质量](acceptance-reports/2026-10-04-schema-summary-quality/report.md) → [响应式角色](acceptance-reports/2026-10-04-responsive-mascot/report.md)：当时234/73和构建通过。默认5/5/7点、尾部事实恢复与365字末点；上游schema违约使默认保持兼容。19预占不是19有效总结，41/5/焦点不同源码/阶段各自说明，不假称真机。
- [自然字幕实测](acceptance-reports/2026-10-04-natural-subtitle-quality/report.md) → [来源与冻结事实](acceptance-reports/2026-10-04-natural-subtitle-quality/source-report.md) → [公网移动/GPU](acceptance-reports/2026-10-04-public-mobile-gpu/report.md)：前轮184/66。24个HTTP200不等于有效总结；当时5/6/7点与426字末点对应旧源码，证据保持原样。
- [真实平台扩展](acceptance-reports/2026-10-04-platform-expansion/report.md) → [浏览器闭环](acceptance-reports/2026-10-04-browser-e2e/report.md) → [质量评测](acceptance-reports/2026-10-04-summary-quality/report.md)：前轮169/66及构建通过；单条平台结果不推广为全站支持，模拟LLM页面结果不计模型准确率。
- [平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md)：较早121/66轮结果；保留首轮/限次重试及 TLS 修复后字幕复测。
- [修复后AI总结回归](acceptance-reports/2026-10-03-ai-summary-regression/report.md)：此前结果，后端96/96、前端65/65、Archive.org内容获取3/3、原件解析5/5及真实DeepSeek长文总结。
- [原始平台验收](acceptance-reports/2026-10-03-single-platform-subtitles/report.md)：修复前的0/3、4/5基线，原始文件和许可证据继续保留。

报告数字对应各自采集/测试时间，不相互覆盖；原验收的阻断项不能误当成修复后的状态。

最新平台探针中Commons两项403，仅作为访问限制；YouTube网页200不作为字幕成功。Bili公开正文成功和Archive桌面真实总结有独立证据。所有报告保留请求层级、来源与未覆盖范围。

## 历史参考

`handover-phase1.md`、2026-09-20/21前后端旧实现计划、2026-09-22电影感计划与霓虹规范、pidanai分析报告保留设计过程。它们的任务列表、测试数量和配色描述代表当时状态，接手先读当前交接。

历史记录：此前供应商/质量/UI复审及20次预算中19次预占属于相应旧阶段，不是phase15或当前39POST累计工作范围。历史原件和测试服务状态按各报告时间理解，不重复运行这些阶段。
