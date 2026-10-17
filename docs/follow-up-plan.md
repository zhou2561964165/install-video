# 项目完成记录与整改计划总表

更新：2026-10-17。本文统一记录**已完成事项、未完成整改及新增计划**。F-004/F-005已结项；F-003恢复原待机行为及最新小圈范围均已由用户查验通过。F-006已按用户指示完成实现、独立复核与验证，现停下等待用户查验。F-001/F-002状态及总结质量整改继续按各自记录管理。

## 1. 最新用户决定与实际状态

| 事项 | 用户已确定的方向 | 当前实际状态 |
| --- | --- | --- |
| 长文使用 | 长文目前可以上线使用；质量问题留待后期继续整改 | F-001产品代码已接入：公开默认60000字符，超过20000走单次全文Pro、完整Markdown；配置化资源上限与离线检查完成，待用户查验。未修改现有env、未部署或真实模型复验；显式较低运维上限仍生效 |
| 长文质量 | 允许使用不代表质量过关，继续保留缺陷与后续整改 | phase15英文长文7 full /1 partial，仍有转换前提遗漏、局部退出条件错误；来源内部range表述张力另列。整体质量未通过 |
| 组件布局 | 组件居中 | F-002阶段入口角色曾保留embedded并后置；后续F-003取消嵌入入口并改为桌面视口角色。六宽36几何、44前端回归及build属于F-002阶段记录，未部署 |
| Live2D与小圈 | 取消自动移动，恢复原待机，手动拖动改变位置，小圈按可见轮廓接触消失；手机不加载模型 | 2026-10-17模型松手停在新位置，原待机/表情/道具继续，无焦点/菜单/系统动态/后台主动暂停；alpha联动/控件点穿透及手机禁用保留。**用户已查验通过**，未部署 |

“长文允许上线使用”是产品决定，不表示质量通过。本轮长文入口实际代码与验证见[F-001交验](implementation-reports/2026-10-16-f001.md)；旧20000字符公开拒绝是接入前状态，当前20000是默认路由分界。角色区域mask仍是当前实现。开发完成、用户查验、部署完成和质量通过分别记录。

仅使用DeepSeek的既有要求继续沿用。phase15已结束且不可重开。本轮按新指示完成F-001后停下；每项等待用户查验，登记事项不自动触发下一项、模型调用或部署。

## 2. 后续整改清单

### 2.1 已完成事项

| 编号 | 事项 | 完成依据 | 状态 |
| --- | --- | --- | --- |
| F-004 | 全项目文档审查与整改 | 审查、文档修正与静态检查见§6，历史原件勘误见§7；两个不可读raw目录作为范围限制记录 | **已完成** |
| F-005 | 实际技术架构审视与文档更新 | 当前源码/锁文件对照、架构图和职责更新、独立复核见§9；发现的A-001至012另列状态 | **已完成** |

以上两项已结项，不作为后续待办；新增修改另记用户依据和范围。

### 2.2 未完成整改

| 编号 | 事项 | 已确认要求与后续范围 | 完成记录依据 | 状态 |
| --- | --- | --- | --- | --- |
| F-001 | 长文上线使用与质量持续整改 | 已接入完整来源单次DeepSeek Pro长文路径与Markdown显示/复制/导出，短中兼容。质量条件遗漏、范围/控制流精度与冗余继续保留；纯B/核查/编辑候选不自动执行 | [本轮交验](implementation-reports/2026-10-16-f001.md)：后端236相关离线、root93定点、前端65/build及三宽模拟API浏览器通过；未部署/真实模型复验 | **产品实现及离线验证完成，待用户查验**；质量持续整改与部署未完成 |
| F-002 | 组件居中 | 以视口可用内容列居中登录整体、入口标题/输入与工作台；入口角色保留embedded并排到内容下方，正文/标签左对齐 | [本轮交验](implementation-reports/2026-10-16-f002.md)：六宽36几何、44前端回归及build通过；独立只读审查无明确C/I/M问题，Git差异核对限制单列；模型/平台请求0 | **实现及验证完成，待用户查验**；F-003未开始 |
| F-003 | Live2D角色与小圈联动（初始阶段） | 2026-10-16桌面漫游/键盘/暂停方案已被后续用户指示调整；该阶段证据只对应当时实现，当前行为见2026-10-17报告 | [历史交验](implementation-reports/2026-10-16-f003.md)：22文件237项/build、初始真实/模拟浏览器范围 | **后续行为已调整；以2026-10-17最终交验为准** |
| F-003续调 | 取消悬浮按钮/模型方框、悬停继续活动、轮廓接触避让 | 两个额外按钮与模型矩形框已移除；小圈alpha接触、位置同步与手机禁用经后续两轮更新细化 | [续调交验](implementation-reports/2026-10-16-f003-adjustment.md)：23文件253项/build及当期浏览器流程 | **已并入最终F-003，用户查验通过** |
| F-003恢复原表现 | 取消自动移动与新加暂停控制，保留手动拖动 | 模型松手停在新位置，原呼吸/摆头/换装/道具继续；应用不因焦点/减少动态/后台主动暂停，手机禁用保持 | [本轮交验](implementation-reports/2026-10-17-f003-original-behavior.md)：23文件254项/build及当期本地模型验证 | **用户查验通过** |
| F-006 | 游客首页与按需登录/注册 | 未登录及认证恢复中显示首页；顶部按钮显式进入AuthScene。匿名提交解析只提示请用顶部登录按钮、不发业务API；从AuthScene返回及认证成功均回首页保留URL，不自动解析。token恢复成功直接首页并显示AuthBar，失败回游客首页；注销/换账号清业务状态。后端权限不变；复用React/useAuth，无新依赖/框架，不改env或模型文件 | [实施报告](implementation-reports/2026-10-17-f006.md)：23文件266项、build、独立复核、Edge及本地权限验证的最终范围 | **实现与验证完成，等待用户查验**；真实账号登录及真实模型未测试 |
| F-003小圈范围 | 取消小圈内容列边界、标题随小圈倾斜 | 两侧限制仅指小圈显示范围，不改模型拖动。仅顶部/模型alpha/解析表单隐藏，其余普通按钮/链接/菜单和两侧空白显示；标题按所在纵向区域、横向全视口位置连续倾斜 | [本轮交验](implementation-reports/2026-10-17-f003-circle-scope.md)：23文件257项/build、本地真实模型10项浏览器检查及独立复核 | **用户查验通过；为当前F-003最终范围** |

以上编号用于持续跟踪，不预设执行顺序。用户新增或调整要求时，在本表更新对应条目；未明确的交互细节在获指示实施后再设计，不在本轮臆定。

## 3. 后续计划统一维护规则

1. **所有后续计划先进入本文。** 新增功能、整改、候选方案、执行顺序和暂停/恢复安排均在此登记，分配稳定编号，写明依据、范围、状态和完成依据。
2. **详细资料通过链接归入对应条目。** 必要的设计、实施清单或验收报告可以另存专门文件，但必须先在本文登记并关联；不能在其他文档中另建一套未汇入本文的活动待办。
3. **当前说明与历史证据各按用途维护。** README、需求、设计和交接引用本文的后续计划；已实现能力仍按代码说明。旧计划、报告和冻结原件保留历史状态，不因本表更新而重开旧phase或改写旧评分。
4. **状态更新要有依据。** 每条记录用户决定、实施状态、相关文件、实际检查/内容审阅和剩余问题；只有实际完成的内容才能标记完成。暂停或调整时在原编号下留记录。
5. **每次交接先读本文。** 后续计划以最新用户指示和本文登记为准；阶段交接负责说明当时进展与证据，不能从历史“下一步”自动恢复工作。

后续条目登记格式：`编号｜日期与用户依据｜目标/范围｜状态｜详细资料｜实际完成与检查｜剩余问题/下一步`。新计划直接追加到本表或对应编号的小节，无需另建平行总表。

### 3.1 历史候选统一归档（均未排期）

以下来自旧需求/交接的未来方向，集中收录以消除游离计划。它们保持“历史候选、未重新确定实施范围”的身份，不因本轮收录就变成已授权开发；已完成的检查也不重做。

| 编号 | 历史候选或未验证范围 | 依据与当前边界 |
| --- | --- | --- |
| H-001 | 平台字幕结构与稳定性复查 | [需求§8.7](requirements.md#87-字幕轨道空结果与画面ocr候选2026-10-13)；`BV1B84y1q7Hr`实际字幕payload仍未核实，不能把结构错误认定为无字幕；B站风险诱因和长期稳定性未证明 |
| H-002 | 画面OCR | [需求§8.7](requirements.md#87-字幕轨道空结果与画面ocr候选2026-10-13)及[综合交接](handoff-2026-10-10.md)；FFmpeg/PaddleOCR仅候选，无入口/锁定依赖/有限资源配置或实测 |
| H-003 | 真机触摸、低GPU、缩放/FPS及实际后台隐藏 | [角色嵌入报告](acceptance-reports/2026-10-13-embedded-mascot-refinement/report.md)、[跟随续测](acceptance-reports/2026-10-13-ui-follow-continuation/report.md)；桌面与模拟结果不代替真机，未来按实际变更与设备条件限定补验 |
| H-004 | 下载失败额度退还与独立AI额度 | [历史剩余工作](remaining-work-2026-10-07.md)；现有下载提交计数、失败不自动退还；AI独立计量/限制未实现 |
| H-005 | 会员、积分与支付 | [需求§7–8](requirements.md#8-扩展状态与后续方向)；尚未实现，范围未定 |
| H-006 | 批量/分布式队列、限流、重启恢复与定时TTL清理 | [当前架构](design.md#7-临时文件与防滥用)及[历史候选](remaining-work-2026-10-07.md)；现有线程池与懒清理不等于这些能力，Celery/Redis仅旧候选 |
| H-007 | SSE与生产部署运行保障 | [历史候选](remaining-work-2026-10-07.md)；现有轮询与本地服务不等于SSE或已部署，后续单独确定目标环境与交付范围 |
| H-008 | 时间轴/SRT/VTT导出、音频转写、问答及思维导图 | [当前需求边界](requirements.md#86-当前实现验收缺口与避免重复工作2026-10-16)；未实现，历史讨论不生成新按钮或自动调用 |
| H-009 | 请求幂等、进行中去重与字幕/总结缓存 | [参考研究](reference-summary-review-2026-10-10.md)；参考项目实例单例不是这些能力，不把已完成的旧结果清空修复重复列为待办 |
| H-010 | `useAuth`额度刷新与会话切换的迟到响应竞态 | F-006独立审查发现既有`getMe`额度刷新可能在退出/切换账号后写入旧会话额度；本轮未修改`useAuth.js`，不扩大F-006范围。后续是否修复另行排期，当前未实现/未验证 |

未来确定实施某项时，在原编号补充用户依据、范围与验收记录，或关联到F项；其他文档中的扩展清单均作为这里的历史依据。

## 4. 工程约定与原件保护

- 适用skill优先；后续涉及UI设计或实现时先使用`ui-ux-pro-max`与`design-system`，颜色/字体/时长通过primitive→semantic→component三层token管理，不散落硬编码。
- 复用既有研究并优先采用成熟组件，通过可配置的窄接口接入，避免无关重构。后端只有`ytdlp_service.py`接触yt-dlp；前端视觉层只读`scene`、不改下载状态、不导入下载核心。
- 保护既有未提交工作、账号/env、数据库及本地Live2D模型；GitHub发布继续采用隔离过滤流程排除Live2D模型与其历史，不直接推送含模型的本机main。
- 历史phase、raw/source/result、snapshot、freeze、ledger、receipt、脚本及冻结审稿保持原字节；模型后续实测沿用有限phase、root共享锁串行、发前持久预占和错误停止规定。
- 先前F-004/F-005文档轮为0模型POST、0产品测试、0服务。本轮F-001有产品实现/离线测试及本地前端Vite和模拟API浏览器检查，真实模型POST仍0；未提交、推送或部署。长文phase1–15仍为23POST/319471供应商tokens，Ragas独立16/34106，持续整改39/353577，旧67POST另封账。

## 5. 现有资料与变更记录

### 本轮实施（2026-10-16，用户要求“根据最新文档进行下一步工作”“按顺序实现”）

执行顺序为F-001→F-002→F-003，各项完成实现及必要验证后推进下一项。F-004/F-005保持结项。[本轮实施计划](superpowers/plans/2026-10-16-product-follow-up.md)记录接口与验收范围。

**用户随后要求“每执行完一个工作后等我查验”。** 本轮先完成F-001并提交查验；F-002/F-003保持未开始，待用户查验后的指示再顺序继续。

以上是前两批交验时点。最新用户在F-002后要求不保留嵌入并禁用手机模型；F-003现已实现和验证，见[F-003交验](implementation-reports/2026-10-16-f003.md)，停下等查验。下面“F-002/F-003未开始”仅保留对应批次历史，不是当前状态。

F-001交付后用户再次“继续”，本轮据此推进F-002，完成后停下等查验。布局沿本轮实施计划§2，以视口扣除滚动条后的内容列为居中基准，正文/标签仍左对齐；不实施F-003活动/小圈联动，不重跑F-001后端或真实模型。

- F-001先落实长文产品入口：完整字幕单次DeepSeek Pro、有限输入/输出/并发和超时，兼容现有短中总结及复制/导出；质量缺陷保留，不在本轮追加核查/改写或付费实验。
- F-002按视口内的内容列居中入口和工作台，保留移动端自然纵向布局，正文左对齐以便阅读。
- F-003实现视口内看板娘活动和指针小圈联动，同时处理坐标、mask、热区、拖动、滚动/resize、菜单焦点、减少动效与清理；保留本地模型。
- 当前F-001/F-002已交付，F-003实现与验证完成并等待查验。本轮真实LLM POST上限0，不重开旧phase、不改原件、不自动部署或推送；浏览器仅模拟业务API和读取本地角色资源。
- 工程约定沿§4：适用skills、三层token、成熟能力优先及窄接口单向依赖。详细执行状态保存在本轮私有规划目录，不另建活动总表。

- [项目文档索引](README.md)：资料导航。
- [phase15阶段交接](handoff-2026-10-16-deepseek-step1.md)、[实测报告](acceptance-reports/2026-10-16-deepseek-source-screen/report.md)、[内容审阅](acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md)：已完成第一步的证据及质量缺口。
- [需求](requirements.md)、[设计](design.md)、[前端说明](../frontend/README.md)：当前实现；后续计划统一引用本文。
- [路线记录](summary-route-decision-2026-10-15.md)：A、B和组合的历史状态，保留候选，不作为自动执行指令。
- [现有角色嵌入报告](acceptance-reports/2026-10-13-embedded-mascot-refinement/report.md)：当前区域限制的历史实现依据；F-003登记后续调整方向。

| 日期 | 变更 | 执行边界 |
| --- | --- | --- |
| 2026-10-16 | 用户确认长文可上线使用但质量仍待整改；登记组件居中、Live2D看板娘活动及小圈联动；建立后续计划统一入口 | 仅文档登记，完成后等待下一步指示 |
| 2026-10-16后续 | 用户要求审查全部文档并整改；F-004执行源码事实核对、历史导航修正、链接审查和后续候选归并 | 仅文档审查，不启动产品/模型后续阶段 |
| 2026-10-16结项 | F-004文档审查与整改、F-005架构审视与文档更新均已完成；按用户要求从待办中移入已完成记录，统一修正入口状态 | 已完成事项不再标作“本轮执行”或后续待办 |
| 2026-10-17 | 用户查验通过F-003最终行为（含小圈全视口范围与标题倾斜），并明确按顺序实施F-006；F-006实现、最终复核与验证已完成 | 真实账号/模型未测、未部署；更新报告后停下等用户查验 |

## 6. F-004文档审查记录（2026-10-16）

**状态：已完成。**

审查使用本地源码、配置和已有封账报告；三名只读审查Agent分别覆盖当前实现说明、历史导航/计划、验收证据，root统一修改维护文档。所有新增计划和审查结果归入本文，未另建活动计划总表。

已确认并整改的类别：

| 类别 | 本轮整改 |
| --- | --- |
| 最新决定与实际实现 | 正文明确长文获准使用、质量未过、现有20000字符保护尚未调整；组件居中与Live2D/小圈联动为后续事项 |
| 计划入口 | 修正requirements要求先在本文登记的旧规则；当前入口统一先读本表，历史handoff/研究/UI分析的阅读提示指向这里；旧未来候选归档为H-001至H-009 |
| 额度行为 | 修正前端说明：登录/注册首次补取失败不显示额度，后续刷新失败保留上次值 |
| 下载交互 | “强制走服务器”改为实际可见的“按视频标题命名”，并保留`force_server`字段含义和来源限制 |
| 格式修复与命令 | README区分默认legacy/single和显式staged最多一次格式修复，并补齐共享上限；修正同一终端后端→前端测试目录切换 |
| UI实现索引 | `intensityForScene`定位到background.js；普通玻璃/镜片分别消费token；移除祖先属性必然使滤镜失效的过强说法；embedded缺参数时静止、free才scale回退 |
| 日期与测量范围 | UI的193项/build等明确属于2026-10-13阶段；旧迁回目录/PID/服务/待同步提示不作为当前命令；历史深色主题说明与当前浅色默认分开 |
| Ragas工具 | 可变README记录已closed16 POST、误放实例/类别错误及coverage未评；旧冻结时父计数明确为历史，不再声称尚待实测 |
| 研究与路径 | 已完成的旧结果清空修复不再列为待办；实现功能不宣称质量优胜；本机外部参考链接改为历史代码定位，本项目链接改相对路径 |
| 原始证据 | 不改原报告/快照/冻结计划；历史错误与链接问题在下节外部勘误，补齐阶段报告及独立评分入口 |

覆盖与实际检查：

| 范围 | 本次结果 |
| --- | --- |
| 可读文本清点 | 233份：213个Markdown、20个TXT；覆盖根说明、全部docs、工具说明和原样导出中的文本文档；排除依赖目录、运行产物、本机模型和私有规划草稿 |
| 文档分组 | 29份维护文档、3份评测工具文档、48份历史冻结plans/specs、139份验收文本、3份快照内Markdown、11份原样导出文本；后三类中的字幕/模型回答只核对身份及结构，不借此重做语义评分 |
| 内容核对 | 完整核对当前主说明及所需源码；历史导航/计划逐组审查，验收报告和评审文档扫描并重点对照后续勘误、phase13–15及Ragas结论。并行审查实际执行，后续定点只读复核确认事实整改，无遗留重要问题 |
| 实际修订 | 30份可变维护文档，包含旧handoff的当前阅读提示；冻结plans/specs、验收原件、快照、导出、工具冻结CASE_NOTES/review及产品源码均保持原字节 |
| 静态检查 | 对全部可读Markdown的1192个本地链接检查目标与标题锚点，并检查编码及差异空白；维护文档未发现未处理的失效目标/锚点。2个冻结原件缺失目标保留原字节，已在§7提供正确入口/解释；编辑器`:行号`链接按文件定位处理 |
| 保护核对 | 3738个可读文件建立基线；本轮写入30份维护Markdown，产品源码、配置、验收、冻结plans/specs及导出字节均未变。另观察到本地`.idea/workspace.xml`在对照期间变化，本轮未写入或还原该IDE状态，单独记录；不将它算作产品改动或宣称所有工作区文件均未变 |
| 未覆盖范围 | `docs/acceptance-reports/2026-10-03-single-platform-subtitles/raw/`与`raw-extra/`拒绝访问，未改ACL或绕过；外网链接未联网核验，本机外部参考代码定位不作为可移植链接保证 |
| 执行边界 | 0产品测试、0模型POST、0服务启动；未改产品配置、入口或模型，未提交、推送或部署。文档审查完成不表示长文质量通过，F-001～003仍待下一步指示 |

## 7. 历史原件勘误与阅读指引

本节解释已证实的历史问题，**不改原件、不重开phase、不转记新候选通过**。

| 原记录 | 应如何阅读/定位 |
| --- | --- |
| [2026-10-05 evidence报告](acceptance-reports/2026-10-05-grounded-summary-evidence/report.md)的短中统计及“唯一剩余compose超token” | 该报告串用了前轮短6点/396字、中6点/424字；[2026-10-07复审§3](acceptance-reports/2026-10-07-grounded-summary-review/report.md)更正为短5点/270字、中7点/405字。长文截断前已有18完整点及第19文本，另有数量/组织违约，不能只归为token不足或声称语义通过 |
| 同一evidence报告里的代码格式设计/计划路径 | 正确目标是[设计](superpowers/specs/2026-10-05-grounded-summary-evidence-design.md)和[计划](superpowers/plans/2026-10-05-grounded-summary-evidence.md)；从原报告位置计算需`../../superpowers/...`，原文少一层目录 |
| [evidence冻结计划](superpowers/plans/2026-10-05-grounded-summary-evidence.md)中的报告链接 | 正确报告是[2026-10-05 evidence报告](acceptance-reports/2026-10-05-grounded-summary-evidence/report.md)；从原计划需`../../acceptance-reports/...`，原文少一层目录 |
| [phase10报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-10-report.md)标题“内容结论待独立审阅” | 标题保留早期状态；正文及[独立诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-10-content-diagnosis.md)已有最终FAIL：4 full/1 partial/1 missing，不按标题推定仍未评分 |
| [phase13执行报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md)“未独立评分” | 只描述调用交付时点；此后[独立评分](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-content-diagnosis.md)和[phase14比较](acceptance-reports/2026-10-13-long-summary-fidelity/phase-14-content-diagnosis.md)已经指出精度/重复及课程路线缺口 |
| [纯B候选计划](superpowers/plans/2026-10-15-topic-writing-candidate.md)称组合计划为“当前执行”；早期计划指10月9日交接为“当前任务与预算” | 均按冻结时点阅读。纯B未实现/未实测，组合phase14已执行、质量未过；phase15也已closed。后续是否采用、如何实施只在本表F-001登记 |
| Ragas phase1快照内课程LICENSE链接同层manifest | 快照只冻结部分来源文件，该相对目标未随LICENSE复制；身份/许可应结合快照provenance与[原语料manifest](acceptance-reports/2026-10-04-natural-subtitle-quality/corpus/manifest.json)、[LICENSE](acceptance-reports/2026-10-04-natural-subtitle-quality/corpus/LICENSE.md)阅读，原快照不补文件、不改哈希 |
| 2026-10-03报告的编辑器`:行号`链接和`.venv`依赖路径 | 行号不是文件名组成部分；仓库源码可去掉后缀定位，`.venv`链接只适用于当时本机安装，不作为发布副本内的依赖源码入口或当前版本证明 |

## 8. 已封账阶段的证据入口

下表是历史导航，不包含待执行命令。长文phase1–15共23 POST/319471tokens，Ragas独立16/34106，持续整改39/353577，旧67另封账。

| 阶段 | 执行与内容依据 |
| --- | --- |
| phase1–5 | [综合报告](acceptance-reports/2026-10-13-long-summary-fidelity/report.md)、[phase1细项](acceptance-reports/2026-10-13-long-summary-fidelity/phase-1-report.md)；旧9POST/147600，P4问题未解决，phase5截断后停止 |
| phase6 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-6-report.md)；1POST后引用不匹配停止，无修订产品 |
| phase7 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-7-report.md)；1POST字段超限停止，语义问题仍在 |
| phase8 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-8-report.md)、[内容诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-8-content-diagnosis.md)；3POST，merge20点被拒，无最终产品 |
| phase9 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-9-report.md)、[内容诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-9-content-diagnosis.md)；1POST结构接受、内容FAIL |
| phase10 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-10-report.md)、[内容诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-10-content-diagnosis.md)；1POST结构接受、内容FAIL |
| phase11 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-11-report.md)、[内容诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-11-content-diagnosis.md)；1POST完整source/schema，精度FAIL |
| phase12 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-12-report.md)、[内容诊断](acceptance-reports/2026-10-13-long-summary-fidelity/phase-12-content-diagnosis.md)；1POST，15点诊断不改变产品14点，精度FAIL |
| phase13 | [执行报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md)、[后续独立评分](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-content-diagnosis.md)；1POST原样交付，后续确认精度/组织仍有缺口 |
| phase14 | [报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-14-report.md)、[逐项比较](acceptance-reports/2026-10-13-long-summary-fidelity/phase-14-content-diagnosis.md)；2POST，覆盖改善但精度/重复FAIL |
| phase15 | [报告](acceptance-reports/2026-10-16-deepseek-source-screen/report.md)、[内容审阅](acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md)；2POST同模型新来源观察，不是优化或跨模型对照 |
| 独立Ragas | [报告](acceptance-reports/2026-10-15-ragas-semantic/report.md)、[语义审阅](acceptance-reports/2026-10-15-ragas-semantic/semantic-review.md)；16POST，真实错误误放，不能当生产放行门 |

## 9. F-005技术架构审视（2026-10-16）

**状态：已完成。** 完成范围为架构审视与文档同步；§9.2中结构整改项分别保留其未实施状态。

用户要求对照原有与现有技术架构并更新。三条只读源码审查分别覆盖后端运行/存储、前端状态/表现和LLM/评估工具，root更新现有[design](design.md)，同步README、需求、前端与交接入口。基础技术栈仍为React + FastAPI + yt-dlp，但早期v1下载图已无法表达当前职责。

### 9.1 已更新的架构说明

- design§1–11重新描述模块化单体、同步请求与下载线程池、认证/额度、字幕来源及正文处理、持久数据和进程内执行状态、取消/清理/部署边界；不再把SQLite与执行恢复画等号。
- 目录树纠正不存在的根scripts目录，phase13–15 runner实际位于长文验收目录；生产锁与独立Ragas锁分别记录，不冒充当前已安装版本。
- design§12.7明确strategy/generation/fidelity/length/format组合、分支解析和付费修复边界；summary_pipeline只有两种固定LCEL序列，不是所有请求的统一引擎，summary_json也不是所有分支的统一规范化层。
- design§13用真实前端模块图替换未实现的电影感组件图。下载reducer、认证/视频内容状态、PIXI句柄、DOM几何与小圈分别说明；当前角色与小圈关系是避让，主动联动未实现。
- 旧设计/验收原件继续保留，具体实现/风险与计划状态分开。以下架构整改项只完成静态识别与登记，尚未实施或做运行复现。

### 9.2 结构风险与后续整改登记

优先级表示后续处理建议，非已获代码修改授权或已证明故障概率。每项直接关联源码及已有F/H任务；实施前结合明确场景确定方案与必要验证。

| 编号 / 关联 | 源码证据与当前边界 | 后续处理范围 | 建议时机 / 状态 |
| --- | --- | --- | --- |
| A-001 / H-004 | [quota.py](../backend/app/services/quota.py)先读/判断/Python递增/commit；每日唯一约束不保证既有行原子扣减，首次并发建行冲突未统一处理 | 明确额度事务、原子条件扣减及冲突处理；用并发场景核对超额受理/计数覆盖，保留指定账号策略 | 多用户并发使用前优先核验；待实施 |
| A-002 / H-006、009 | [download路由](../backend/app/routes/download.py)分步扣额度、建Job、提交内存线程池；[jobs.py](../backend/app/services/jobs.py)没有可恢复队列/后端cancel，进程故障可能留下queued/downloading | 定义提交失败、幂等、取消/重启恢复和优雅停止语义；不是直接增加Uvicorn worker或替换队列库 | 扩展任务能力前；待实施 |
| A-003 / H-006 | jobs仅成功设置expires_at，cleanup仅删除过期产物和Job；失败/中断/partial/侧文件及目录未统一回收，大小上限下载后才查 | 明确失败任务和目录的回收、磁盘资源限制及清理失败处理；不能宣称现TTL覆盖所有临时数据 | 持续下载运行前优先核验；待实施 |
| A-004 / F-001、H-007 | [main.py](../backend/app/main.py)限流和JobManager均进程本地；同步字幕/LLM不受下载worker上限；[llm_service](../backend/app/services/llm_service.py)无验收root锁或生产持久调用账本 | 长文产品接入时明确请求时长、并发/资源与前端取消边界；多进程部署时确定全局限制，复用成熟能力但不照搬验收账本为产品逻辑 | 长文接入与部署设计时；待实施 |
| A-005 / F-001 | [summary路由](../backend/app/routes/summary.py)仍有默认20000 gate；[独立runner](acceptance-reports/2026-10-13-long-summary-fidelity/scripts/)返回自由文本，产品返回summary/key_points | 确认长文实际产品路径、输入输出契约与有限资源；提高gate不会自动接入Pro全文路线，允许使用与质量验收分别记录 | F-001落地时；待指示 |
| A-006 / F-001 | llm_service约1802行，集传输、预算、提示、编排与诊断；多组合预检和不同解析器交叉；每次默认HTTP请求建立客户端 | 随具体修改评估传输/预算窄接口和连接生命周期，避免一次性大重构；兼容矩阵作为现状依据 | 按后续变化触发；待评估 |
| A-007 / H-007 | [db.py](../backend/app/db.py)固定SQLite参数/create_all；API未托管dist，仓库无生产反代/容器部署资产 | 数据库适配/迁移、静态托管、TLS、可信代理IP和持久目录需按目标环境设计；DB_URL可配不等于已支持任意数据库 | 生产部署设计时；待确定环境 |
| A-008 / H-001、007 | [ytdlp_service](../backend/app/services/ytdlp_service.py)一般URL预检仅HTTP(S)+netloc，下载路由不走同一预检；B站host/path白名单仅局部；通用提取/Job仍存或回传异常字符串 | 公开部署场景评估统一目的地控制和错误公开字段；不能把局部字幕约束当全站保证。本次未执行访问攻击或泄露复现 | 公开部署前审查；待实施 |
| A-009 / H-001 | B站校验适配覆写yt-dlp内部_download_playinfo；[验收runner](acceptance-reports/2026-10-13-long-summary-fidelity/scripts/)动态加载旧阶段辅助和修改模块全局 | yt-dlp升级关注内部契约；未来新验收工具可抽稳定辅助接口，冻结脚本不回写 | 依赖升级/新工具开发时；待评估 |
| A-010 / F-002、003 | [App](../frontend/src/App.jsx)、[mascot](../frontend/src/pixi/mascot.js)、[PointerFollower](../frontend/src/components/ui/PointerFollower.jsx)通过区域getter、热区和DOM标记耦合；当前小圈避让角色 | 居中先确定参照容器；自由活动/联动同时处理区域坐标、mask、热区、捕获、滚动/resize、菜单焦点和排除标记，不能仅去mask/切free | F-002/003实施时；待指示 |
| A-011 / F-003、H-003 | App等待createMascot后解除Preloader，模型/fallback路径未见统一应用级超时/取消；加载遮罩期间可能影响交互 | 明确视觉加载超时、失败/挂起与业务可用性的隔离；核对cleanup，静态风险尚未复现 | 视觉生命周期整改时优先核验；待实施 |
| A-012 / F-002、003 | [main.jsx](../frontend/src/main.jsx)按global→reference加载；[tokens](../frontend/src/styles/tokens.css)与JS配置分担参数，仍有模块常量/多个监听与计时器 | 核对最终级联和DOM/PIXI几何；新通用样式/时长继续token化，不声称全前端单循环或所有参数已token化 | 随UI改动处理；待实施 |

以上是源码支持的结构风险，不代替真实并发、故障、性能和设备检查。产品源码、依赖及配置本轮不变；长文已获使用决定不变、质量未过结论不变。

### 9.3 复核与交付边界

本轮只进行源码/锁文件/文档静态核对，不导入运行应用、不读env/数据库/账号、不发POST、不启动服务或浏览器。三名只读审查者完成定点复核，发现的字幕函数名、直链探测图边及若干表述已修正；F-005完成表示架构审视和文档已同步，不表示A-001至012已经修复。

静态AST分析解析34个backend/app Python模块：yt_dlp导入仅位于ytdlp_service.py，在本次收集的包内相对导入图中未发现环；这不覆盖动态导入、运行时行为或跨目录验收工具。根/评估uv.lock及前端package-lock已用标准解析器核对版本。收尾扫描233文本文档、1246个本地链接，维护文档未发现未处理的目标/锚点问题；diff空白检查通过，3738文件基线的源码/配置/原件保护核对通过（IDE元数据变化仍单列）。旧2个冻结缺链接及2个不可读raw目录限制沿§6–7保留。两幅Mermaid为文本架构图，代码围栏已静态核对，未启动浏览器渲染验证。

本轮修改10份既有维护文档：design、总表、根README、需求、文档索引、前端README、UI扩展指南、AGENTS、CLAUDE和phase15交接。未更改产品代码/锁依赖或历史原件，未提交、推送或部署；实际模型累计计数保持39 POST/353577tokens，旧67另封账。
