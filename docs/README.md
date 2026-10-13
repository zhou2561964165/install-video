# 项目文档索引

> **当前接手入口：[完整交接](handoff-2026-10-10.md)。** 原目录`E:\install_video`、分支`feature/summary-content-resume-20261011`；恢复验收及指定完整long复验共四phase16POST/153697tokens封账。短中PASS；最新完整long14点结构/6项核心覆盖通过，但精度仍FAIL。默认/env未升级，旧phase/回滚按历史阅读，本地Live2D保留，发布过滤模型历史。

> 下方验收表和旧计划按各自历史阶段阅读；不能据此重开closed phase、重复已完成开发，或把结构/单测通过转记真实内容与触摸交互通过。框架实验已回滚，证据在实验分支和本机精确归档，位置见交接。

## 工程约定

UI先用 `ui-ux-pro-max` + `design-system`，skill优先于旧计划；样式走三层token、能力配置化；yt-dlp仅由 `ytdlp_service.py` 接触，视觉只读场景。以用户当前指令及根工程约定为准。

**2026-10-10追加：成熟方案优先，避免重复造轮子。** 后续开发先复用已有研究并查找成熟库、框架与官方方案，适用时优先实际采用；自研聚焦业务适配与缺失能力，选型记录依据及不适用原因。长期执行规则见 [AGENTS.md §10](../AGENTS.md)，现有资料见 [成熟方案研究](reference-summary-review-2026-10-10.md)；旧自研建议不能覆盖该要求。

## 当前维护文档

最新视频功能已按用户提供参考项目适配：白蓝双栏、同屏下载/内容页签、返回输入与TXT导出；指定B站AI字幕路径修复后实际API成功。当前范围见[本轮报告](acceptance-reports/2026-10-12-reference-video-workflow/report.md)，新模型0POST，旧内容评分不改。

2026-10-12使用范围更新：网页默认按视频原标题保存，保留可选来源直链；短中总结开放，长文正文超过配置上限时提示暂不支持并阻止模型调用。实现与真实验证范围见[当前交接](handoff-2026-10-10.md)，模型0POST；下列冻结报告及失败评分保持原件。

| 文档 | 用途 |
| --- | --- |
| [用户指定完整长文复验](acceptance-reports/2026-10-12-summary-long-final-check/report.md) | closed3POST/32432tokens；累计16/153697，新完整long14点结构/6项full，精度FAIL，原件不改 |
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
| [正式 HTTP 流程补验](acceptance-reports/2026-10-09-online-formal-flow/report.md) | 2026-10-10：API20/20、页面4/4、旧工具故障10/10；零付费，真实模型阶段待明确新预算 |
| [参考代码与成熟方案复核](reference-summary-review-2026-10-10.md) | 当前只读代码对照及官方资料：15,000字符截断限制、旧结果处理借鉴、已实现能力复用与候选方案 |
| [自适应字幕总结](handoff-2026-10-09-adaptive.md) | 历史交接：旧候选结论；当前见2026-10-10交接 |
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

下表的“当前/最新”、测试数量、授权等待和待办均指各自记录当时。旧任务列表不作为新的执行入口；旧组余额不与当前已耗尽26/26组合并。保留原证据，复用已经完成且仍有效的实现与检查。

| 文档 | 历史用途 |
| --- | --- |
| [核查质量续验收](acceptance-reports/2026-10-09-summary-quality-repaired/report.md) | 原17POST阶段的输出、失败和离线修复，不是当前总账 |
| [当前摘要交接](handoff-2026-10-09-quality.md) | 最新模块、1325全量验证、有限复验边界与未解决事项 |
| [核查质量收尾计划](superpowers/plans/2026-10-08-summary-quality-finish.md) | 纯模块职责、独立审查与当前有限验收工作范围 |
| [摘要模块化与对应子句复验](acceptance-reports/2026-10-08-grounded-summary-clause/report.md) | 当前三模块/965回归、25有限调用、最新质量缺口与预算停止 |
| [最新摘要交接](handoff-2026-10-08-normalized.md) | 当前代码、分类策略、实际模型计数、只读复查及后续离线事项 |
| [规范化与引用实施计划](superpowers/plans/2026-10-08-summary-normalization-retries.md) | 模块边界、并行写集、分类修复与冻结验收要求 |
| [规范化首轮](acceptance-reports/2026-10-08-grounded-summary-normalized/report.md) / [marker复验](acceptance-reports/2026-10-08-grounded-summary-marker/report.md) | 独立8与4POST、两个已定位并离线修复的故障，保持旧失败原件 |
| [开发账号与前缀续验收](acceptance-reports/2026-10-08-grounded-summary-prefix/report.md) | 当前不限下载账号/855与84回归、3次有限实测失败及未达质量目标 |
| [最新开发交接](handoff-2026-10-08-development.md) | 新全局模型路由/持续授权、额度配置、关闭phase只读命令与后续边界 |
| [开发账号实施计划](superpowers/plans/2026-10-08-development-quota-validation.md) | 配置化现有账号豁免、UI状态与有限模型组预算 |
| [有限合同与全局主题](acceptance-reports/2026-10-07-grounded-summary-contracts/report.md) | 当前代码/706全量、独立新phase冻结与预算待确认；无新模型质量结果 |
| [最新contracts交接](handoff-2026-10-08-contracts.md) | 新纯接口/编排/checker、旧资产保持、恢复命令与真实预算边界 |
| [合同设计/计划](superpowers/specs/2026-10-07-grounded-summary-contracts-design.md) / [实施计划](superpowers/plans/2026-10-07-grounded-summary-contracts.md) | 用户已继续的有限槽与主题分配私有协议，公开API/n+2不变 |
| [总结质量收尾](acceptance-reports/2026-10-07-grounded-summary-final/report.md) | 当前修订、540项回归、独立9/13实测与未达质量目标 |
| [前轮final交接](handoff-2026-10-07-final.md) | 前轮冻结与实测状态、预算停止、只读复查命令与完成条件 |
| [生成合同复审](acceptance-reports/2026-10-07-grounded-summary-final/contract-review.md) | 连续三轮不同结构边界失败、有限生成结构与全局主题规划建议，未实施 |
| [剩余工作](remaining-work-2026-10-07.md) | 本轮开始前的质量缺口、完成条件和后续候选范围 |
| [refined 交接](handoff-2026-10-07-refined.md) | 前轮 12/13 实测、5 完整／3 部分／长文 6 未评及离线候选修订 |
| [handoff.md](handoff.md) | 历史交接：当时状态和用户决策；当前支持范围、并行工作与启动以[当前交接](handoff-2026-10-10.md)为准 |
| [v3实现计划](superpowers/plans/2026-10-03-v3-video-intelligence.md) | 当前v3 API、分层和验证范围 |
| [扩展路线](superpowers/plans/2026-09-21-extension-plan.md) | v2/v3已实现状态及后续候选，不作为自动执行授权 |
| [参考实现分析](reference-summary-implementation.md) | 参考项目观察、独立实现选择与已测限制 |
| [暂停中的事实/主题设计](superpowers/specs/2026-10-05-grounded-summary-design.md) | 来源位置、私有事实/声明/核查合同及语义限制，尚未交付 |
| [暂停中的实现计划](superpowers/plans/2026-10-05-grounded-summary.md) | 纯合同、编排和评测分工，后续仅听用户指示 |
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

- [摘要协议/质量](acceptance-reports/2026-10-04-schema-summary-quality/report.md) → [响应式角色](acceptance-reports/2026-10-04-responsive-mascot/report.md)：最新234/73和构建通过。默认5/5/7点、尾部事实恢复与365字末点；上游schema违约使默认保持兼容。19预占不是19有效总结，41/5/焦点不同源码/阶段各自说明，不假称真机。
- [自然字幕实测](acceptance-reports/2026-10-04-natural-subtitle-quality/report.md) → [来源与冻结事实](acceptance-reports/2026-10-04-natural-subtitle-quality/source-report.md) → [公网移动/GPU](acceptance-reports/2026-10-04-public-mobile-gpu/report.md)：前轮184/66。24个HTTP200不等于有效总结；当时5/6/7点与426字末点对应旧源码，证据保持原样。
- [真实平台扩展](acceptance-reports/2026-10-04-platform-expansion/report.md) → [浏览器闭环](acceptance-reports/2026-10-04-browser-e2e/report.md) → [质量评测](acceptance-reports/2026-10-04-summary-quality/report.md)：前轮169/66及构建通过；单条平台结果不推广为全站支持，模拟LLM页面结果不计模型准确率。
- [平台与总结质量报告](acceptance-reports/2026-10-03-platform-quality/report.md)：较早121/66轮结果；保留首轮/限次重试及 TLS 修复后字幕复测。
- [修复后AI总结回归](acceptance-reports/2026-10-03-ai-summary-regression/report.md)：此前结果，后端96/96、前端65/65、Archive.org内容获取3/3、原件解析5/5及真实DeepSeek长文总结。
- [原始平台验收](acceptance-reports/2026-10-03-single-platform-subtitles/report.md)：修复前的0/3、4/5基线，原始文件和许可证据继续保留。

报告数字对应各自采集/测试时间，不相互覆盖；原验收的阻断项不能误当成修复后的状态。

最新平台探针中Commons两项403，仅作为访问限制；YouTube网页200不作为字幕成功。Bili公开正文成功和Archive桌面真实总结有独立证据。所有报告保留请求层级、来源与未覆盖范围。

## 历史参考

`handover-phase1.md`、2026-09-20/21前后端旧实现计划、2026-09-22电影感计划与霓虹规范、pidanai分析报告保留设计过程。它们的任务列表、测试数量和配色描述代表当时状态，接手先读当前交接。

历史记录：此前供应商/质量/UI复审及20次预算中19次预占属于相应旧阶段，不是当前26/26工作组。历史原件和测试服务状态按各报告时间理解，不重复运行这些阶段。
