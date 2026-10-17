# 工程约定（每次必须遵守）

> **2026-10-17 GitHub交付：** 用户授权提交推送后，开发提交`690adb1`经隔离clone过滤模型历史发布为`7db9ead`，已快进推送并核对远端main；本地模型与原历史保留，尚未部署。详见[交付记录](docs/implementation-reports/2026-10-17-github-delivery.md)。下文旧“未提交/推送”按各自时点阅读，后续仍须过滤模型，不能直接推开发分支。

> **2026-10-17 F-003最终交验：** 用户已查验通过，包含小圈全视口范围和标题倾斜。小圈在两侧及普通按钮/链接/菜单上显示，仅顶部、模型alpha轮廓和解析表单避让；模型拖动边界未改。证据见[交验](docs/implementation-reports/2026-10-17-f003-circle-scope.md)。F-006按用户指示完成实现和验证，现等待用户查验，见[报告](docs/implementation-reports/2026-10-17-f006.md)。

> **2026-10-17 F-003待机行为：** 用户已查验通过。模型位置不自动变化，拖动松手后停在新位置，呼吸/摆头/换装/表情/道具和小圈alpha联动继续；无新增应用暂停开关，手机禁用保持。该阶段23文件254项/build及本地模型验证范围见[交验](docs/implementation-reports/2026-10-17-f003-original-behavior.md)。

> **F-003续调历史记录：** 当时实现取消额外悬浮按钮、hover暂停和模型方框，并登记顶部登录入口为F-006。F-006现已按用户后续指示实施；当前状态见[总表](docs/follow-up-plan.md)和[实施报告](docs/implementation-reports/2026-10-17-f006.md)。

> **F-003初始交验历史（2026-10-16）：** 当时实现桌面漫游/拖动/暂停及手机加载门控；后续用户要求已取消漫游和应用主动暂停，并更新小圈范围。该阶段237项/build等数字不代表当前行为的重新验证，当前以本文件顶部2026-10-17交验为准。

> **F-002最新状态（2026-10-16）：** F-001交付后用户要求继续，现已完成组件居中及验证，等待用户查验；F-003未开始。入口各屏宽改为居中单列、embedded角色后置，正文/标签左对齐；登录整体和工作台标题居中。六宽36项几何、44项前端回归及build通过，见[本轮交验](docs/implementation-reports/2026-10-16-f002.md)。本轮0真实模型POST、未部署；下方F-001交验和角色旁栏记录按之前阶段阅读。

> **当前接手入口（2026-10-17）：** 先读[完成记录与整改计划总表](docs/follow-up-plan.md)，实际架构读[design](docs/design.md)，phase15证据读[阶段交接](docs/handoff-2026-10-16-deepseek-step1.md)。**F-004文档审查与整改、F-005技术架构审视与文档更新均已完成并结项；F-003当前范围已由用户查验通过。** F-006实现、独立复核与验证完成，等待用户查验。旧阶段与原件保护按§34–38，不重开closed phase。

> **F-001实现更新：** 用户要求按顺序实施后，又要求每项完成先等查验。本轮仅实现F-001长文产品入口，代码/离线检查已完成，部署与真实质量复验未执行；F-002/F-003未开始。公开默认60000字符、超过20000走单次全文Pro/Markdown，短中旧流程保留。详见[本轮交验](docs/implementation-reports/2026-10-16-f001.md)。交验后停下，不自动进入下一项或新的模型phase。

## 1. UI 设计必须用 skill
涉及 UI/视觉/交互（配色、字体、动效、无障碍、组件）时，先调用：
- `ui-ux-pro-max`（设计决策检索：`--design-system` / `--domain color|typography|ux` / `--stack`）
- `design-system`（三层 token：primitive→semantic→component）

## 2. skill 优先于计划
计划文档与 skill 指引冲突时，**以 skill 为准**。
例：ui-ux-pro-max「每屏最多动 1–2 个关键元素」> 计划里的常驻动画清单。

## 3. 代码不写死、保留扩展、避免大规模重构
- 颜色/字体/时长一律走 `:root` token，不散落硬编码。
- 新增能力数据驱动、可配置，不做写死导致后续要推倒重来的实现。

## 4. 解耦（单向依赖，改动隔离）
- 核心模块对外只暴露窄接口：后端 `ytdlp_service.py` 是唯一接触 yt-dlp 的层；前端视觉表现层只读 `scene` 状态，绝不修改下载状态、绝不 import 下载核心。
- 层与层、模块与模块通过稳定接口通信，禁止绕过接口直接依赖内部实现。
- 新增能力走接口隔离，扩展不触碰既有核心。

以上约定需写进所有文档（含现有文档），并每次照做。

## 5. 开发期账号与模型验收授权（用户2026-10-08更新）

- 开发期沿用现有账号，允许给指定账号配置不限下载额度，不为绕过额度新建账号；其他账号额度和使用统计保持。
- 开发、模型验收及必要的有限扩预算已获持续授权，不再逐轮询问许可。每轮开始前记录明确上限、原因和台账；禁止无上限扩预算。
- 本次总结质量工作先13模型POST，最多因已定位且离线验证的修复追加一轮13，总硬上限26。包含所有阶段及失败尝试；达到上限后停止真实调用。
- 每个phase仍独立冻结和台账、单caller串行、发前持久预占、错误即停；修复后另建phase，旧失败原件/预算不覆盖、不借用、不自动重试或隐藏付费回退。
- 本条优先于旧文档里的“等待新的授权”。账号不限下载额度不表示模型调用/服务器资源无限；用户后续可撤销或修改授权。

## 6. 规范化与分类重试整改（用户后续指令优先）

- 模型raw summary必须先经独立规范化层，再进入内部结构/最终语义校验；引用由程序结合已验证事实与主题关联提供，不完全依赖模型生成。
- 规范化保留所有非空内容/原ID提示，不裁字删点、不盲挂全部引用。关联ID不是语义证明，未决候选交核查，最终来源/核心事实/检查/长度边界仍必须满足。
- 格式错优先本地零POST修复；确需模型格式修复与语义修订分别计数，默认每次总结最多1次format、1次semantic且总附加最多2，可配置关闭。网络/provider/来源安全/容量/配置错误不重试，不盲重跑整个pipeline。
- 所有attempt计入真实调用预算与trace，正常n+2/默认最坏n+4；禁止隐藏付费fallback和无限扩预算。本条覆盖旧phase“任何错误无重试”，旧失败原件与账本不改。
- 本次新整改正常三源13POST、含最多6附加调用最大19，工作组总硬上限26；真实验收须先代码/离线/审查/包含新模块的freeze验证，单caller执行，无需重复问许可。

## 7. 回归字幕总结与有限自适应输出（用户2026-10-09后续更新）

- 产品目标是 yt-dlp 提取字幕后交给 LLM 总结优化，复用已有分段归纳与合并，不继续为了事实合同验收新增无意义协议。
- 摘要和要点不按固定字数硬拒；允许按字幕规模、主题和必要条件有限拓展。长文可使用更多主题和更完整说明，不凑点、不截字、不无限增加调用或输出预算。
- 默认字幕总结采用自适应输出预算，基础及有限 token/主题数量上限可配置；旧 fixed/facts 合同只保留为显式兼容实验及历史证据，不作为用户默认总结的成功条件。
- 本条覆盖旧计划中的固定800字、7点、240字产品目标。来源忠实、关键条件、范围、归因、可读性及有限资源控制仍须验证；现有工作组26POST硬上限不变。

## 8. 当前交接与有限后续验证

- 当前验收工作组已达26/26 POST、152726供应商tokens，六个phase全部closed。最后adaptive-transcript-repair-final实际2 POST，snapshot/raw/result核验通过；报告 `docs/acceptance-reports/2026-10-09-adaptive-summary-final/report.md`。旧phase、账本与失败原件保持不变，不可重开。
- 此旧工作组已耗尽预算并封账，不重开、不借用或重跑；平台Agent额度恢复不重置其硬26。后续新任务预算按第12条用户更新自主设定有限上限并记账；该上限属于开发验收，不写入产品下载额度或LLM运行代码。
- 最后短篇zh1–zh4覆盖、精度及组织通过本条回归；中篇en2/en3/en4 full，Engrade成绩录入+私下留言已恢复，但en1仍缺每节课评价、评分理由重复且摘要信念归属较弱，整体仍未通过。新版提示的长文实际质量未复验，旧长文审查只适用旧冻结提示。不得宣称总体总结质量已全面解决。
- 当前代码1342 passed/1既有警告是历史全量记录；新phase只核验内容质量与自己的证据，不代表本轮重新跑过后端全量测试。
- 本轮只修订legacy通用生成指导，明确高层概览/完整要点、互补能力、来源体裁与逐断言限定/粒度；没有样本答案、文本删除器、新facts协议或新付费阶段。相关91项机械回归、两个工具19/7项离线测试及独立审查完成；机械通过不能代替内容评分。全部改动仍未提交/推送/部署。

## 9. 文档与当前实现同步（用户后续追加）

- 依据项目当前代码、配置和已有实测结果维护现有文档。过时的接口、默认值、功能状态、验证范围和执行建议须更正并解释适用阶段。
- README、design/requirements、前端说明与当前交接描述实际已实现能力；候选功能、未完成能力和未验证范围明确标注，不把设计目标写成已实现。
- 当前交接列出已完成工作和真正剩余缺陷；历史计划、旧待办与旧“等待授权”说明标为历史，不因接手或文档更新重复已完成开发、测试、freeze或模型验收。
- 原始验收结果、freeze、脚本、台账与报告保留原字节；对历史记录的解释通过文档索引、当前说明或阅读提示提供，不改原证据。
- 文档维护不自动触发测试、服务启动或模型调用；新增实现或具体风险需要验证时，仅执行与变化相关且未完成的检查。

## 10. 成熟方案优先，避免重复造轮子（用户2026-10-10追加）

- 后续新增功能、问题整改和通用能力设计前，先复用已经确认的研究，再查找适用的成熟开源库、框架和官方方案；已有资料仍有效时不重复调研。
- 存在适用的成熟方案时，优先学习并实际采用其组件、接口和最佳实践。不要闭门造车，也不要因为已有自研实现或熟悉现状就跳过成熟方案评估。
- 自研聚焦项目业务差异、接口适配和成熟方案确实缺失的能力；避免重新实现已有成熟的通用引擎、编排、解析或协议。通过窄接口接入，保持可配置、可维护及现有数据/行为兼容。
- 选型记录候选来源、适用版本、采用方式和实际收益；结合维护情况、许可证、兼容性与资源成本判断。确需自研时写明成熟方案不适用的具体原因，不能只以“自己实现更方便”为依据。
- LlamaIndex、LangGraph等已研究的方案允许纳入后续实际选型；先复用 `docs/reference-summary-review-2026-10-10.md` 的资料，依据任务选择合适模块并验证集成效果。文档中的历史自研建议不覆盖本条新要求。

## 11. 当前成熟方案整改状态（2026-10-10）

- 已复用现有Pydantic v2严格类型/schema能力，新增`summary_output.py`，适配官方来源优先建议并指导同一次生成先完整要点、后高层概览；未新增依赖或模型调用步骤。设计见`docs/superpowers/specs/2026-10-10-source-first-summary-design.md`。
- 前端新请求清空该类旧结果，保留其他类型缓存、取消与请求编号保护。后端相关108项、前端hook4项离线通过；旧全量数字不重复计入本轮。
- 生成指导/schema顺序不是语义或供应商执行顺序保证。当前新候选中篇/长文真实质量仍未实测，第8条旧输出结论只适用于旧冻结候选；26/26封账、原证据及第12条有限自主预算规定保持。

## 12. 后续验收预算自主设定（用户2026-10-10后续更新）

- 用户已明确“预算可以不用问我，可以根据任务要求自行提升”。后续开发验收由主Agent按任务自主设定/必要时提高有限预算，不再请求逐轮预算许可；此条覆盖旧“须用户另给数值授权/等待确认”说明。
- 每轮开始前必须记录明确上限、用途与台账；所有实际尝试及失败预占计入预算，禁止无限调用、隐藏付费fallback或通过新组抹去旧计数。增加预算须有具体任务或已定位修复依据，并记录调整前后数值。
- 旧26/26工作组及六个closed phase保持封账和原字节；后续新任务使用独立freeze/ledger/tracker，仍共享caller锁、root单caller串行、发前持久预占、错误即停。修复先离线验证和独立审查，再另建新phase，不重开旧失败phase。
- 本次来源优先新候选工作组总硬上限10POST：首phase最多5POST，短/中各1、长预计3；剩余最多5仅用于已定位且离线验证修复后的独立复验。不能把首轮预留余额当作可随意重复生成的额度。

## 13. 实测后的有限阶段分离修复（2026-10-10）

- 首phase已closed5POST、19776供应商tokens：短篇通过本条回归；中篇summary反馈频率/文化归因仍失败；长文合并raw20点超过冻结14上限，被拒，原失败不改。
- 同响应顺序提示不足，现按实际缺陷采用langchain-core成熟串行编排（已安装1.6.9）及已有Pydantic，最终points-only→overview-only；LangSmith0.14.7只用于关闭追踪上下文，禁止第三方遥测和隐藏SDK请求。设计见`docs/superpowers/specs/2026-10-10-staged-summary-design.md`。
- 本轮累计上限自主从10调整到12，父10上限预算closed/已用5原件保留；continuation绑定父hash及5次，不重置计数。修复phase最多7：短/中各2，长复用已付费两段笔记后正常2+最多1格式修复；因此避免重复付费长文抽取。全phase最多1format，各摘要仍有限，网络/provider/容量错误终止。
- 新代码/离线/独立审查及新freeze/check后root单caller执行；旧phase不重开，不能把raw未接受或旧评分转记新候选通过。新增依赖与实际正常/最坏调用规模同步设计和交接，默认是否启用须依据实际验证，不静默扩成本。

## 14. 原生schema/模型有限对照及个人GitHub交付（2026-10-10后续）

- 阶段2已closed6POST/28851tokens，累计11POST/48627tokens；长文points及format均20且完全等于11+9笔记按序连接，产品再次拒绝。旧失败/台账/评分不改，defaultsingle仍保留。
- 基于实际不遵循数量/概览职责问题，采用已有Responses传输与原生json_schema、官方支持的deepseek-v4-pro(reasoning none)作一次有限对照，不加新框架或样本答案，不放宽14上限/原覆盖精度/重复标准。官方协议已核实；不发送未列明strict参数或隐式能力探针，不持久reasoning内容。
- 用户持续授权自主预算：累计上限12→17，父12上限closed11原件保留；新continuation绑定父hash及全部11次，phase3最多6（短中长各2，复用原两个longleaf）。format/semantic额外均0，错误即停/root串行/发前持久预占，禁止无限扩预算或重开旧phase。
- 用户已授权完成当前任务后推送个人GitHub。目标已连接个人账号zhou2561964165；本地无remote/匹配仓库，拟private install-video。明确文件清单，不上传env/db/本机账号配置/tmp/.planning草稿，不重写原证据；原始验收字节通过gitattributes保护。实际结果/未解决范围、验证与依赖设计同步后再提交推送，不把失败候选宣称完成质量目标。

## 15. 当前实际交付状态（2026-10-10在线对照后）

- 第三phase已closed6POST/25728供应商tokens，累计17/17 POST、74355tokens；全部调用成功、format/semantic额外0。短5/中6/长14点结构通过，短篇内容通过，中篇与长文内容失败；完整证据见`docs/acceptance-reports/2026-10-10-schema-pro-summary-live/report.md`。不能把结构通过写为整体质量通过。
- 默认legacy/adaptive/single保持，staged与Pro/schema仍为显式候选；没有部署或升级默认模型。中篇频率/账户读取/概览重复与文化归因、长文求值/重算/安全范围等真正缺陷见`docs/handoff-2026-10-10.md`。
- 三个新phase与旧26/26均封账，不再freeze/run；原snapshot/raw/ledger/receipt保持。发布后的当前文档及可移植测试可以更新，但旧验收结论只绑定冻结候选，不宣称当前全部live文件哈希仍匹配。
- 用户已授权个人GitHub推送；已创建private `zhou2561964165/install-video`并配置origin。发布前集成验证、凭据扫描、明确路径stage及原始验收blob字节核对后提交；本机Git登录尚须用户完成，不能从MCP配置提取令牌或上传本机env/账号策略。

## 16. GitHub排除Live2D模型（用户2026-10-10后续更新）

- 用户明确“live2d模型不上传”。排除模型包、纹理、moc3、model3/physics/表情/动作文件及历史记录；Cubism Core运行库是程序依赖，可保留，模型由用户本地补齐，缺失时走已有fallback。
- 本机原始main和模型文件保留，不在原工作区重写历史或删除资源。发布通过隔离新clone及成熟git-filter-repo过滤模型历史；仅推送已核验无模型的发布副本，不直接推送本机含模型的原始main。
- `.gitignore`不能清除已有追踪/历史；后续发布继续复用此过滤方式并检查全部可达历史对象。此工具仅为Git发布维护，不是产品新技术栈，不改运行依赖或模型调用预算。

## 17. 发布核验与后续操作（2026-10-10）

- GitHub设备登录已完成；无模型内容版本`678f874`已成功推送个人private `zhou2561964165/install-video`并通过远端main提交号核对，后续仅补交付说明。当前52模型文件/78历史路径与全部模型blob排除，运行库保留；其余HEAD文件blob与本机原提交一致。
- 本机main保留原历史/模型；`github-main`用于跟踪过滤发布历史，origin默认push仅发送该发布分支。新开发提交后须重新生成隔离过滤副本、核验及更新github-main，再发布；不得把含模型的本机main直接推送，也不force覆盖已发布历史。
- 当前验证1494后端/86前端、build及导出6项通过；中长总结内容缺陷仍在，默认single不改。三个新phase17/17及旧26/26原件封账；发布不重跑模型/测试或改验收原始字节。

## 18. 长文整改暂停交接（用户2026-10-14最新）

- 用户明确「先暂停，然后更新文档等下一次测试」：长文开发与真实模型验收暂停，仅维护当前文档。未收到继续指令前不发POST、freeze、重跑测试或启动验收服务；旧计划/预算授权不撤销此暂停。
- 本任务用户已明确不设总POST/费用预算，仍逐次预占记账/root共享锁串行/错误停，不取消产品每请求有限输入、输出和调用次数。旧26/17/8/16组封账原件不改。
- 新long-summary-fidelity组phase1–5全closed，共9POST/147600供应商tokens。phase2/4独立内容审阅core6全full、overview/organization通过，但P4具体旧计算器限制→固定程序类别泛化仍FAIL；已修时间、算术子集、求值、area显式重算和下一讲衔接不重报旧缺陷。
- phase5 checks仅1POST：json_object响应重复target、按子断言扩写并含拼接引用，4096 completion达到length而截断，llm_incomplete_response后立即停止；没有第二修订或新最终结果。旧raw/snapshot/result/ledger/receipt/script/冻结审查稿原字节保持，不重开失败phase。
- 当前代码已采用相邻重复折叠、源语言notes、可容纳时完整source merge；新增fidelity off/long/review/checks候选及有限review预算，真实LCEL/PydanticOutputParser固定职责。coverage/quote归属只证明机械条件，非语义证明，无新公共facts协议或输出删除器。
- 默认仍legacy/adaptive/single、fidelity off；模型/env未升级，公有20000字符限制及长文暂不支持保留。新正常完整生成、未见MIT Lecture2和新流程短中回归未实测；不把代码或工具tests通过写为整体质量解决。
- 当前交接`docs/handoff-2026-10-14-long-summary.md`和本轮`docs/acceptance-reports/2026-10-13-long-summary-fidelity/report.md`。输入修复全量1847仅此前阶段；最新相关197等按各阶段记录，暂停后没有重跑。未提交/推送/部署，既有UI与本地模型保留，发布继续过滤模型历史。

## 19. 长文整改恢复记录（用户2026-10-14后续“继续”）

- 用户已明确恢复前述长文整改。第18条作为暂停时点的历史记录保留；继续指令不重开phase1–5，原9POST/147600tokens、快照、响应、结果、ledger、receipt、runner与冻结审阅稿均保持原字节。
- 新根因已定位：范围泛化首次出现在英文叶笔记，核查请求此前使用json_object且没有把动态schema发给供应商。当前候选方向是增强通用主语/指代范围指导，核查使用Pydantic动态必需字段和Responses json_schema，按目标数计算有限输出，固定核查→修订调用并首错停止；默认fidelity仍off。
- 第一恢复验收phase如能通过离线验证、独立审查与冻结，最多2POST，仅复用phase4已保存草稿验证核查与修订；预算仅限制该phase，用户仍授权整个整改不设总POST/费用预算。各后续phase开始前另定有限上限、用途与台账，单caller/root串行/共享锁/发前持久预占继续。
- 截至本条更新时，新设计、通用提示与Pydantic动态checks schema已经实现，生产相关离线回归105项通过；phase6 Responses runner最终18项通过。独立生产与工具审查Critical/Important均0；工具freeze资产清单包含本轮设计、代码、回归与两个review文件。phase6在plan/provenance/offline-check都严格记录`phase_post_cap=2`，组级预算仍无总上限；下一步执行离线plan/freeze/check，尚未freeze新phase、发新POST或启服务。禁止写成P4已解决；公开20000字符限制不恢复。未提交/推送/部署。

## 20. Phase 6 验收结果与新续行边界（2026-10-14）

- phase6已freeze/check/run/verify并closed；phase cap=2，实际仅预占/发送1 POST、13208供应商tokens，phase6 group reserved_posts累计10。Responses返回完整15个目标字段，但`target_11.source_quote`为原文转述，不是连续原文片段，触发`llm_invalid_response`；错误即停，无第二次修订/POST、无最终产品结果。不能重开phase6或把partial checks/raw转记通过。
- 对父phase4草稿逐点只读检查发现`target_4`的assessment仍为supported，source quote只覆盖四则能力句，未识别具体实例限制被推广成类别，P4仍未解决。完整原始记录留在closed phase6结果，不改phase6冻结/台账/receipt。
- 下一修复候选要明确核查字段呈现`source_subject`、`draft_subject`及主体范围关系，并保留连续原文引用；字段/引用/assessment仍不自动证明语义。TDD/独立审查/new runner完成后建立phase7，复用phase4草稿、有限cap最多2 POST，root单caller共享锁和持久预占。整个工作仍无总POST/费用预算；旧phase1–5的9POST/147600及phase6的1POST都保持封账。
- 默认仍`legacy/adaptive/single`与`fidelity=off`，公开20000字符入口未恢复。未提交/推送/部署。

## 21. Phase 7 主体范围核查候选（2026-10-14继续）

- phase6失败根因已证实：引文首字母大小写不同导致机械拒绝；更重要的是核查结果没有把同一谓词的source subject与draft subject并列比较，具体计算器限制仍泛化为类别结论。phase6保持closed，不改其脚本、raw、结果、台账与receipt。
- 新增显式`subject_checks`候选模式，默认`off`不变。动态必需字段含assessment、scope_relation、source_subject、draft_subject、连续source_quote与finding；程序只验证结构、目标位置和引用/主体字面归属，不认证语义；不新增公开facts协议或API字段。
- 为避免改变phase6原`checks`的4096输出行为，新增独立有限配置`LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS`，默认8192；14点预算7808，超限多段任务在首个leaf POST前拒绝。错误即停，不自动重试或降级格式。
- TDD新增subject测试初始RED 25后继续扩展，当前新测试35 passed；与旧checks/review/revision相关路径合计121 passed。生产审查Critical/Important/Minor均0；runner最终26项离线测试通过，工具独立审查Critical/Important/Minor均0。工具审查修复了mock PROJECT祖先路径逃逸并限定到system temp及owned path containment。以上均不证明provider语义正确。
- phase7已完成独立plan/freeze/check，cap=2，父phase4 source/raw02/product/receipt hashes及全部候选资产核对通过，provenance SHA `2551dfb2d8a30c00981d436b32519cb2c432ee2181c1cb1232671fc446754d79`，offline receipt记录network=false、dotenv_read=false。下一步仅由root单caller共享锁串行实测最多2POST，首错停止；phase6原失败原件不进入revision。整个整改无总POST/费用预算但phase cap有限；默认off和公开20000字符限制不变，未完成语义验收前不得写成长文/P4问题已解决。

## 22. Ragas实测与phase7封账（2026-10-15）

- 用户已恢复子Agent额度并要求继续。已真正接入独立`tools/semantic_eval`uv项目：Ragas0.4.3官方Faithfulness两阶段，兼容固定langchain-community0.3.31；生产依赖、默认与UI没改。精确locked环境root78passed，独立实现审查C/I/M均0。遥测关闭，窄LLM接口无SDK重试/回退，root共享caller锁及发前预占。
- 新Ragas phase1 cap16已closed/completed16POST/34106tokens，freeze/离线重放/hash核验通过。六个合成例判断正确，真实原P4与纠正例同为1.0；八例误放1、误拒0。独立人工审阅确认错误主语保留在断言中，NLI将具体计算器谓词错误支持整类。Faithfulness不能接生产放行门，也未测coverage；不把高分、结构或案例局部通过说成质量解决。报告`docs/acceptance-reports/2026-10-15-ragas-semantic/report.md`，旧原件不改。
- 第21条是实测前记录：phase7现已真实1POST/14164tokens后closed失败；target6引用超120、target9主体超64触发llm_invalid_response，没发第二修订、无新产品。target4仍supported/same且quote只介绍类别存在，P4未解决。verify通过仅指hash/封账，不是语义。报告`docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-7-report.md`。phase7与Ragas首轮不可重开。
- 原长文组累计11POST/174972tokens全部closed；Ragas独立16POST/34106tokens，当前合计本次持续整改27POST/209078tokens，旧67POST各组另保留。更换GPT账号不清零，整个整改无总费用/POST上限，每新phase仍须有限上限/用途/台账。
- 最新通用类别/实例/代词生成指导在phase6才加入，而phase6/7复用phase4旧草稿，因此当前完整生成尚未实测。正常profile薄适配复用旧engine，已见源新phase8 cap3（两leaf+merge），先离线/独立审查/freeze/check；不重做产品管线、不增judge协议或把同NLI的FactualCorrectness改名当独立核查。新计划`docs/superpowers/plans/2026-10-15-normal-long-generation.md`，当前交接`docs/handoff-2026-10-15-semantic-eval.md`。默认legacy/adaptive/single/fidelityoff、公开20000字符和长文暂不支持不变，未提交/推送/部署。

## 23. 最新正常生成实测与单次合并候选（2026-10-15）

- phase8已按正常deepseek-flash/auto/4096–8192/fidelityoff完整实测3POST/28376tokens并closed。两leaf11/9点接受；merge20超冻14而llm_invalid_response，无最终产品，无自动重试。原件verify通过只证明封账一致。新normal入口root27项通过，实施者新旧相关集成68项通过，独立工具审查C/I/M均0；旧脚本/生产不改。
- 独立raw诊断：新leaf已用具体calculator实例，merge中文主体比旧P4收窄但有省略歧义；合并同序翻译11+9点而非跨段归并，把before class ended译成课前，缺显式重执行area条件与下一讲。raw core5full/1partial、精度/组织失败，不把未接受raw转记产品/P4通过。
- 原长文组现在14POST/203348tokens，Ragas16POST/34106tokens，各phase全closed，当前持续整改合计30POST/237454tokens，旧67另保留。phase8不重开，raw03不作为修订草稿，14/8192不为通过放宽。
- phase9已按显式Pro/Responses `json_schema`完成1POST/14710供应商tokens；复用phase8两份accepted leaves，不含失败raw03。返回14点、结构通过，phase9 verify exit0，但独立内容FAIL：仍近似逐点拼接，后段Python错误/对象/类型转换/表达式/赋值重绑/area重算/下一讲均有缺漏；计算器限制收窄至实例但“不能”主语仍有歧义。报告`docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-9-report.md`及独立诊断。原长文组phase1–9共15POST/218058tokens，Ragas16POST/34106，总31/252164，旧67另封账。Phase9与旧phase不可重开。下一步重新设计一个有限阶段，在14点内显式保留long1–6必要信息、按主题合并两leaf，而不使用文本删除器/截断；先离线及独立审查，再决定新的有限模型对照。当前默认/公开限制不变，未提交/推送/部署。


## 25. 跨分段全局归并提示复验（2026-10-15）

> 本节记录phase10实际freeze/run之前的启动状态；最终结论见§26及最新交接。

- phase9独立审阅确认14点结构通过但内容FAIL：4full/1partial/1missing；遗漏long6赋值、重绑、area重算条件和下一讲；P13模态精度、概览/组织FAIL。phase9摘要可读但仍保留首leaf A1–A11并遗漏第二leaf多条内容。phase9及phase8旧原件保持closed、不得重开。
- 当前实施phase10只修正通用`merge=True`指导并用同Pro/schema、相同phase8 accepted raw01/02和完整source作单变量对照，cap1、8192输出/14点、0 format/semantic/extra。目标为按主题跨段合并并检查source尾部，不新增facts协议/样本答案/删除器、不放宽点数、不触碰默认模型；phase10尚未freeze/POST。
- phase10开始时旧组15POST/218058tokens，Ragas16POST/34106，累计31POST/252164，旧67另封账，换账号不清零。TDD、离线审查、独立工具review和phase-specific snapshot完毕后才root单caller freeze/check/run；失败即停。默认仍legacy/adaptive/single/fidelityoff、公开20000字符限制和长文暂不支持不变。


## 26. Phase 10 merge提示

- phase10已freeze/check/run/verify并closed，cap1实际1 POST/14793tokens；仅改merge指导，Pro/Responses schema和phase8成功leaf保持。结构14点接受但独立内容FAIL：4full/1partial/1missing，long6全缺，P13模态失败、组织FAIL，P2时间回退“课前”；新增426字符提示未改变A1–A11/B1/B2/B4+B5→14点映射。详情`phase-10-report.md`与`phase-10-content-diagnosis.md`。
- TDD观察prompt与runner两个RED；root合并target tests56 passed/98.05s、独立工具审查C/I/M均0、必要8项复核通过。旧phase8/9文件和台账不改。当前phase组phase1–10累计16POST/232851tokens，Ragas组16/34106，合计32/266957；旧67另封账，换账号不清零。phase10不可重开。
- 用户持续授权任务无整体预算上限；每个新phase仍须cap、用途/台账、root共享锁、发前预占和首错停。下一步依据phase10独立内容审阅，phase10提示单变量复验失败（4full/1partial/1missing，P2时间回退、尾部遗漏），不再追加同类提示句付费重试；先只读梳理phase1–10旧分段/points-only/overview结果及现有分配机制，再确定是否有实质性不同且单phase有限的方案。phase10 cap用完不可重开，默认legacy/adaptive/single/fidelityoff、公开20000字符限制和长文暂不支持不变，未部署/提交/推送。


## 27. 单次完整来源诊断候选（2026-10-15）

- Phase10 merge提示单变量未改变14点映射/coverage，P2时间回退。历史审计确认Flash与Pro/schema的points→overview、同响应theme_plan均已实测且有缺口；LlamaIndex/LangGraph仅研究、未实际作为引擎运行。phase10及旧账全部closed不重开。
- 现先实现一次cap1 direct-source诊断：规范化完整MIT source 34,894字符（低于现有60,000输入边界），使用生产`_summary_request(merge=False)`，同deepseek-v4-pro/Responses/json_schema/14点/8192，不传segmented notes，只评估这一不同输入路线是否更完整。它不是产品已决定的路由，也不符合用它证明正常分段流程通过；若继续后续产品集成须另审决策。
- 长文组phase1–10已16POST/232851tokens，Ragas16POST/34106，总32POST/266957，旧67另封账；换账号不清零，整体总预算授权不改变phase cap1。未实现、独立审查、冻结/离线检查前0POST，旧phase raw/result/ledger保持字节原样。
- 计划`docs/superpowers/plans/2026-10-15-full-source-direct-diagnostic.md`记录范围和限额。默认legacy/adaptive/single/fidelityoff、公开20000字符入口关闭，未部署/提交/推送。

> §27为phase11执行前的计划状态；实际结果按本节记录。后续有限候选的当前计划见`docs/superpowers/plans/2026-10-15-direct-source-capacity-check.md`。

## 28. Phase 11 完整来源直入实测与下一候选（2026-10-15）

- phase11 cap=1已freeze/check/run/verify并closed，实际1 POST/10809供应商tokens；Pro/Responses `json_schema`、reasoning none、14点/8192、`fidelity=off`，完整MIT Lecture1规范化原文34894字符直走生产`merge=False`，不带notes。phase11 group总reserved_posts从16到17；原phase10及phase11 raw/source/result/provenance/ledger/receipt/hash保持封账。
- 新增runner只复用既有freeze、HTTP/Responses解析、共享锁、root caller guard、持久预占、封账和快照回放。独立source身份检查在修复前曾观察到source与manifest同步漂移漏过；现sample分配前/冻结回放均绑定phase10唯一来源的file/raw路径与哈希、清理后source哈希/长度、标题、许可、署名和manifest整体SHA，漂移零POST拒绝。测试34 passed/143.25s；工具独立审查Critical/Important/Minor 0/0/0。
- HTTP/completed、14点schema解码及`semantic_quality_verified=false`只证明请求/结构与证据封账。独立内容审查**FAIL**：long1–4 full、long5/6 partial、precision FAIL、overview/organization PASS。P11缺对象类型决定操作关系；P10遗漏静态语义错误需到达相应分支的前提；P14泛化radius旧值/area具体示例并漏显式重算条件与下一讲衔接。P2时间、旧计算器类别、P13模态本次未输出对应断言，不能称其修复。详情`docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-11-report.md`与`phase-11-content-diagnosis.md`。
- 长文组phase1–11累计17 POST/243660tokens；Ragas独立组16/34106；本次持续整改33 POST/277766，旧67 POST另封账。用户允许无整体预算上限；后续每phase仍有限cap/用途/台账、root共享锁、发前持久预占、错误即停，换账号不重置。默认仍legacy/adaptive/single/fidelityoff、14点产品上限及公开20000字符保护；正常分段Flash、未见MIT Lecture2和短中回归未通过本phase验证。
- §28记录了phase12开始前的候选和限额；实测结果见§29。phase11不重开、不修改。

## 29. Phase 12容量对照与零POST下一步（2026-10-15）

> 本节“下一步B”是phase12完成后的历史计划；phase13后用户确定先A、确认不能满足要求后再切B，当前顺序见§31。

- phase12 cap=1已freeze/check/run/verify并closed，实际1 POST/10984供应商tokens；仅将同一34,894字符MIT Lecture1完整来源direct `merge=False` 路径的adaptive要点上限14提高到15，Pro/Responses schema、prompt、8192输出与其余参数不变。HTTP/completed、15点schema和hash verify只证明请求/结构/封账，不代表内容质量通过。详情`docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-12-report.md`。
- 独立内容评分5 full /1 partial /0 missing，precision FAIL，overview/organization PASS。long5“类型决定可用操作”的关系恢复；long6仍漏显式重新执行area及下一讲衔接；P11把`word + 5`误判成语法错误，P15把加减乘规则泛化到除法。不得降低既定coverage precision要求或宣称长文已解决。逐项依据`docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-12-content-diagnosis.md`。
- 长文组phase1–12累计18 POST/254644 tokens；Ragas独立组16/34106；本次持续整改共34 POST/288750，旧67 POST另封账。42项离线runner测试通过，工具review C/I/M=0/0/0；这些是工具证据，不替代语义评分。网络恢复或换GPT账号不清零，phase12不可重开。
- phase12结束时曾建议立即设计B；这是phase13之前的历史建议。用户随后决定A先、确认不足再B，当前次序见§31及docs/summary-route-decision-2026-10-15.md。候选B未实现，phase13已用于A；不按此历史待办提前开发B。
- 默认仍`legacy/adaptive/single/fidelity=off`，产品14点上限与公开20000字符限制不变；phase11/12 direct对照未验证正常分段Flash、MIT Lecture2或短中回归。未部署/提交/推送。

## 30. 用户指定完整字幕直接交给DeepSeek Pro（2026-10-15）

> 本节记录phase13开始前的候选边界；用户phase13完成后的最终决定是两方案均保留，先A后B，详见§31。

- 用户最新要求“本地不跑，完整信息交给Pro”，并明确DeepSeek Pro API；本次优先按该直接委托执行，暂不开发主题规划候选。本地仅传送/保存，不运行本地模型、分段归纳、合并、语义judge或测试套件。
- 新phase13 cap1，全文34894字符源SHA绑定，普通文本输出、reasoning high、有限16384 tokens、timeout300秒；无14/15点和JSON合同，旧phase1–12仍closed。root共享锁、发前持久预占、错误停/无retry。相对phase12多因素变化，不宣称单因素证明。
- 直接委托脚本复用已有transport依赖、完成状态解析、响应白名单、共享锁和封账写入；凭据仅HTTP头、reasoning文本不落盘。发前独立只读审查Critical/Important最终0/0，完成状态标记适配Important已修复并复核；依用户要求未运行本地测试/pipeline。
- 执行开始时长文累计18POST/254644tokens，Ragas16/34106；合计34POST/288750，旧67另封账。当前一次请求已持久预占，结果与封账数字以新phase13报告为准；旧账不清零。
- 全文及原VTT导出`exports/pro-direct-2026-10-15/`，结果成功后原样保存。成功只表示收到Pro文本，语义未独立评分；默认/公开入口/部署状态不因此升级。

### Phase13实际交付

- 已实际1POST/15498供应商tokens并closed（input9127/output6371）；Pro返回5206字符可见文本，保存并导出`pro-summary.md`。没有本地改写或语义评分，不是整体质量PASS，不把phase12评分套到此输出。
- 长文累计19POST/270142tokens，加Ragas后35POST/304248，旧67另封账。phase13 cap用完，不重开/重发。当前结果见`docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md`，默认和公开入口未升级。

## 31. 两方案保留、优先用户全文Pro方案（用户最新决定）

> 本节记录此前决定；用户后续选择A/B组合，当前执行边界见§32。

- 用户明确“两方案都保留，目前先更新文档；后续先使用我提出的方案，不可以解决就换成你的方案”。本轮只维护文档，不发POST、不启动服务、不跑测试或改产品代码。
- A为优先方案：完整字幕连同明确总结任务一次交给DeepSeek Pro，本地仅获取/传送/保存，不运行分段/合并/主题编排或本地模型。phase13已实际完成，全文与输出保留；初步发现时间矛盾，尚无全面独立评分，既不记总体PASS，也不因此立即切换。
- B为保留后备：独立全局主题规划→逐主题写作→概览，见既有候选计划，未实现/未实测。不要因为旧计划“下一步”而提前实施B或删除任一方案。
- 下次先验证A；若有具体来源证据确认A在关键完整性、忠实度或有限资源下无法满足要求，记录限制和切换依据后按本授权推进B。不得降低原内容标准、无限重复A或在单请求中隐藏付费fallback。网络/provider错误先记录停止，不自动转B。
- 当前顺序及边界以`docs/summary-route-decision-2026-10-15.md`和最新交接为准。旧phase和账本封账，不重发phase13；默认/公开入口及35POST/304248持续整改计数均不因文档更新改变。

## 32. 完整原文＋独立主题规划组合（2026-10-15继续）

> 本节为phase14启动状态；最终结果见§33，不重复freeze/run。

- 用户明确“两方案可以结合起来”并继续。当前组合为独立规划→全文写作两次Pro调用；两次均完整原文，规划仅可纠错导航，第二次保留A自由篇幅，不用纯B逐块写作/14点合同。设计与计划为`docs/superpowers/{specs,plans}/2026-10-15-planned-direct-summary*.md`。
- phase13零POST独立审阅：long1–6 full，precision FAIL（时间矛盾、实例范围），overview PASS、organization局部FAIL，另有两项课程路线遗漏；详见phase-13-content-diagnosis.md。当前回答失败不证明A永久不可用；原件不改。
- 新phase14 cap2，父组19；规划Pro/schema/none/4096，生成Pro/text/high/16384，timeout300、0retry/format/semantic/extra，root共享锁/串行/发前预占/首错停。先新工具离线测试与独立审查，后freeze/check/run/verify；当前恢复点尚未freeze/POST，group仍19，含Ragas35/304248、旧67另封账。
- 只新增验收runner和相关离线测试，不升级默认legacy/adaptive/single/fidelityoff或公开20000字符保护。实际内容仍须独立评分，不用schema或主题规划证明语义；未提交/推送/部署。

## 33. 组合phase14实际封账与内容结论（2026-10-16）

> 后续用户仅要求固定DeepSeek完成第一步，当前结果与停止边界见§34。

- 已实际完成独立规划→全文写作2POST/26054tokens并closed，verify成功，cap2用满不可重开。provenance `81806e353c139fca968cccde2d220f3dc9758157b2061159fbb4de49a572445d`；新runner32项离线通过、工具审查C/I/M0/0/0。恢复没有此前RED日志，不虚构TDD过程。
- phase14回答8293字符、原样导出`exports/planned-pro-direct-2026-10-15/`。独立内容6full/0partial/0missing、overview PASS、precision与organization FAIL：补齐phase13遗漏课程路线两主题；下课前仍成课前，末尾“类型转换会截断”泛化、十条回顾重复；除法/重绑限定争议按原准则在报告单列，不夸为全部一致确证。完整性改善不能换算整体质量提升百分比。
- 长文组phase1–14全closed，21POST/296196tokens；Ragas16/34106；持续整改37/330302，旧67另封账。真实调用前预占/root串行/共享锁保留。下一步先零POST分析末尾再压缩与时间表达，不重复本phase或自动扩阶段；全任务无总预算授权不等于无限重跑。
- 见`phase-14-report.md`、`phase-14-content-diagnosis.md`与当前handoff。默认legacy/adaptive/single/fidelityoff、公开20000字符和长文暂不支持未升级；未见Lecture2/短中/普通Flash流程未由本phase验证，未提交/推送/部署。旧raw/snapshot/账本/receipt/script/review字节不改；冻结设计/计划仍留执行前状态，实际进度写当前报告。

## 34. 仅DeepSeek第一步完成，等待后续指示（2026-10-16）

- 用户明确“不用改变模型，只使用DeepSeek”“先完成第一步，后面的听我指示”。跨模型筛选已收窄为固定Pro/high/单次全文的两个未见来源观察，不再等待其他供应商凭据；不允许自动进入核查、编辑、改提示或下一phase。
- phase15 cap2/parent21，Lecture2英文33710字符和新中文Listening访谈402字符各1次，沿phase13 text/high/16384通用任务只换元数据。已freeze/check/run/verify并closed，实际2POST/23275tokens，0retry/format/semantic/extra。provenance `3160b10297b28602f108c4a101fde759f7092c8224244751018345974801bfe1`。
- 新工具24项离线通过，独立C/I/M0/0/0；父原件/snapshot漂移封账问题曾真实失败并修复，旧失败日志原样保留。仅新增验收工具与测试，不改产品代码/模型/env/default或公开20000字符保护，不跑无关全量。
- 内容：英文7full/1partial（缺可转换前提），局部Zelda退出条件错误；range总括与step例为源内张力未消解；概览/组织PASS。中文4full、未发现确证核心错误，口语释义存疑单列，重复扩写FAIL。源/篇幅/语言不同、单样本各1次，不称优化百分比或统计可靠性。
- 长文phase1–15全部closed，23POST/319471tokens；Ragas16/34106，持续整改39/353577，旧67另封账。报告`docs/acceptance-reports/2026-10-16-deepseek-source-screen/report.md`及content-review.md，原样导出`exports/deepseek-step1-2026-10-16/`。第一步结束，后续等待用户指示；不重开phase15，不借余额，无提交/推送/部署。

## 35. 当前文档入口与维护边界（2026-10-16）

- 用户本轮要求“更新完整文档”，仅同步文档，不构成恢复产品开发、提示优化、模型测试或后续核查/编辑的指令。§34第一步已完成后的停止边界继续生效。
- 当前规范交接是`docs/handoff-2026-10-16-deepseek-step1.md`，总索引`docs/README.md`；README、design/requirements、前端说明与综合交接反映当前代码/phase15实测。旧10-15交接整理为阶段回顾，早期handoff/剩余工作通过历史通知指向新入口，不能把其中待办当现行动作。
- 纯B逐主题写作仅保留设计、未实现/未实测；phase14标题规划→全文写作已在独立验收工具实测，两者区分。phase15仅同模型新来源观察，不是跨模型或优化优胜结论；代码默认模型为空，不把Pro验收profile写成生产默认。
- 旧报告、raw/source/result、snapshot、freeze、ledger/receipt、脚本与冻结审稿原字节保留，通过当前索引解释阶段差异；旧计划/specs不为勾完成而改写。文档维护只做静态链接、配置/状态与原件哈希核对，0测试/0服务/0模型POST，无提交/推送/部署。

## 36. 后续计划统一登记与长文使用决定（用户2026-10-16后续更新）

- 用户明确长文目前可以上线使用，但不代表质量过关；后期继续整改。本轮只记录决定，不将已有20000字符保护写成已解除，不将文档更新写成已部署。
- 后续整改包含组件居中、Live2D像看板娘一样不再局限于一个地方并与小圈联动；本轮不实施，文档完成后等待下一步指示。
- `docs/follow-up-plan.md`是全部后续整改和新增计划的统一入口。以后新增/调整/暂停/完成的计划必须先在该文档登记，详细设计/计划/报告如另存文件，须归入对应条目并建立链接；其他文档仅引用，不维护互相冲突的活动待办。
- §34–35及旧交接中的产品限制描述其记录时点；最新产品决定和后续安排先读总表，实际实现状态仍以代码和实施记录为准。历史封账计数、原件保护、DeepSeek要求及本轮仅文档/等待指示边界继续。

## 37. 全项目文档审查与历史勘误（2026-10-16后续）

- 用户已指示审查全部文档并整改，本轮文档任务不再等待确认；产品开发、模型调用与部署仍待下一步指示。总表F-004记录范围、修订和检查结果。
- 当前README、需求、设计、前端说明及工具README按实际源码修正；总表统一收录历史候选、阶段证据和原件勘误。旧报告/冻结plans/specs的错误不直接改字节，按总表§7正确路径/后续评分阅读。
- 文档静态检查不等于产品测试或语义复验；不可读历史raw目录、外部本机依赖路径和未联网核验范围须实事求是记录，不改ACL绕过、不虚构通过。

## 38. 当前技术架构审视（2026-10-16后续）

- 用户要求审视原有与现有架构并更新。本轮F-005按源码/锁文件更新design和入口说明；结构整改项统一登记在总表§9，不自动实施代码重构或新增模型阶段。
- 当前后端是同步业务请求与专用下载池并存的模块化单体；SQLite业务记录不等于持久执行队列、取消或重启恢复，限流/下载池属进程。生产LLM与独立Pro验收/Ragas隔离，根scripts目录不存在，runner在验收目录。
- 视觉只读业务信号、不修改下载状态及不导入下载核心的约定继续。实际表现还通过窄接口接收DOM几何、菜单操作和媒体偏好；小圈读DOM并避让角色，不能把所有视觉模块写成只接收scene或已实现主动联动。
- 设计说明与代码风险分开；额度并发、提交一致性、失败残留、LLM资源与取消、视觉加载和部署边界仅静态发现，未做运行复现。本轮0产品测试/0模型POST/0服务，源码/依赖/配置和历史原件保持。
