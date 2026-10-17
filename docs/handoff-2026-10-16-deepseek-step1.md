# 阶段交接：DeepSeek第一步结果（phase15）

> **F-003待机行为更新（2026-10-17）：** 用户要求恢复原待机表现，已取消自动漫游及新增的位置/暂停菜单。模型保持当前位置，手动拖动后停在新位置，呼吸、摆头、换装、表情与道具继续；小圈alpha轮廓联动和手机不加载模型保持。当前F-003已由用户查验通过，见[交验](implementation-reports/2026-10-17-f003-original-behavior.md)。下文10月16日漫游/暂停描述按当时阶段阅读。

> **2026-10-17最新交接：** F-003当前行为与最新小圈范围已由用户查验通过，见[待机交验](implementation-reports/2026-10-17-f003-original-behavior.md)和[小圈范围交验](implementation-reports/2026-10-17-f003-circle-scope.md)。F-006按用户指示实施完成：访客/认证恢复中显示首页，顶部按钮显式进入登录/注册；匿名解析仅提示、不发送业务API；返回及认证成功保留URL但不自动解析；会话恢复失败回游客首页；后端权限不变。最终独立复核和验证完成，等待用户查验，见[F-006报告](implementation-reports/2026-10-17-f006.md)。本页以下phase15及F-001至F-003早期描述均按各自记录时点阅读。

> **项目最新交接（2026-10-16）：** F-001长文入口与F-002组件居中已各自完成实现/验证，F-003桌面Live2D自由活动、小圈避让及手机模型资源门控也已完成，均等待用户逐项查验。F-003桌面非手机且视口>800px启用漫游；手机UA或≤800px不创建模型、图片fallback或角色交互面，`index.html`共享Cubism Core脚本仍加载。前端22文件/237项、build299模块通过，独立审查C/I/M=0/0/0；Edge真实本地16K模型7项及模拟native/headless7项通过，无pageerror。真实手机、GPU峰值内存、长时FPS未验证；build仍有大于500kB chunk提示。0模型POST、未部署/提交/推送。详见[F-003交验](implementation-reports/2026-10-16-f003.md)及[统一总表](follow-up-plan.md)。本页phase15记录按当时状态阅读。

更新日期：2026-10-17。本页主体是phase15历史交接。最新用户决定、活动文档任务与全部后续计划先读[统一总表](follow-up-plan.md)；产品实际实现同时参照[需求](requirements.md)、[设计](design.md)，UI与发布历史参照[综合交接](handoff-2026-10-10.md)。

**F-004文档审查与整改、F-005架构审视与文档更新均已完成。** 当前运行架构见[design§1–11](design.md#1-架构总览)，LLM配置组合见§12.7，前端实际职责见§13；两项已结项，发现的结构整改项在总表单独跟踪。

## 1. 用户最新决定与phase15范围

用户明确“先完成第一步，后面的听我指示”，随后限定“不用改变模型，只使用DeepSeek”。第一步已收窄为**固定DeepSeek Pro单次全文的两来源能力观察**，不是跨模型选型，也不是提示优化。phase15已完成，后续核查、校订、规划、默认推广、新模型阶段均未获本次继续指示。

用户随后确认长文可以上线使用但质量未过，要求按F-001→F-002→F-003实现，并要求每项完成先等查验。**本段保留当时F-001完成、F-002/F-003尚未开始的阶段状态**；后续F-002/F-003进度见页首当前交接与各自交验。phase15记录不因后续工作改写，也不据此继续新的模型phase。

工程约定：适用skills、成熟能力优先、配置化窄接口和单向依赖；yt-dlp只经`ytdlp_service.py`，视觉只读scene，UI设计须`ui-ux-pro-max`/`design-system`及primitive→semantic→component token。保护既有代码/UI、账号/env、数据库、本地模型和全部历史原件。个人GitHub发布继续过滤Live2D模型历史；不直接推送含模型的本机main。

## 2. 第一步实际结果

[完整报告](acceptance-reports/2026-10-16-deepseek-source-screen/report.md)、[内容审阅](acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md)、[原样结果目录](../exports/deepseek-step1-2026-10-16/)、[zip下载](../exports/deepseek-step1-2026-10-16.zip)。

| 项目 | 英文长字幕 | 中文短访谈 |
| --- | --- | --- |
| 来源 | MIT Lecture2: Branching and Iteration | Listening for Success: The Importance of Audio Files (Chinese) |
| 原文 / 回答 | 33710 / 4888字符 | 402 / 1112字符 |
| 核心覆盖 | 7 full /1 partial /0 missing | 4 full /0 partial /0 missing |
| 忠实度 | 缺少输入须可转换的前提；局部示例将非right退出收窄成left才退出 | 未发现确证核心事实错误；开头口语释义存疑单列 |
| 来源歧义 | range的stop−1口语总括与step示例张力没有消解，不算凭空捏造 | 源字幕“不是不容易/不太清楚”的自我修正含糊，不强迫单一解释 |
| 概览 / 组织 | PASS / PASS，少量有用途的重复 | PASS / FAIL，末尾分类回顾和多个解释重复正文 |
| 当轮供应商tokens | 19791 | 3484 |
| 预占至响应 | 113.037秒 | 37.926秒 |

这两次显示模型能提炼主线，但长文条件完整性仍有缺口，短文不够简练。它们不是一次优化前后对照，不能换算“提升X%”；各来源仅一次、两份均来自MIT教学材料，且语言/长度/体裁同时不同，不能据此估计稳定性、模型优劣或跨平台准确率。“未见”只指未在本项目用新输出调试，不代表供应商预训练未见。

旧MIT Lecture1仅复用phase13已保存结果作开发锚点，没有追加生成。所有新回答保留原样，没有删错句或局部校正；截至本页，没有进入第二步核查或第三步编辑。

## 3. phase15结束时的产品实现与实验区别（历史时点）

本节20000公开保护及未接Markdown描述phase15结束时状态；后续F-001已另行接入长文产品服务，默认60000公开上限、20000路由阈值及format字段，见页首交验记录。不改原phase报告或计数。

| 边界 | 当前实现 / 适用范围 |
| --- | --- |
| 对外总结接口 | 仍返回`summary/key_points/provider/model`；没有把实验Markdown或主题规划字段接到公开API |
| 默认生成 | `legacy/adaptive/single`、`fidelity=off`；模型与endpoint来自部署配置，没有把Pro验收profile升为默认 |
| 公开长度保护 | `summary_max_source_chars=20000`；超出在模型调用前拒绝，长文暂不支持 |
| 内部输入/输出 | 代码内部默认输入上限60000字符，adaptive基础4096、输出ceiling8192、最多14点；这些不是公开长文已可用的证据 |
| 已实现输入/来源处理 | 相邻重复字幕行折叠、source-language notes、可容纳时完整来源merge；跨语境重复不被盲删 |
| 兼容候选 | facts/auto、staged、long/review/checks/subject_checks等显式路径保留；结构/引用匹配不认证语义 |
| 成熟组件 | 已有Pydantic及LCEL窄编排、关闭外部追踪；独立Ragas工具不充当生产放行门 |
| phase13–15 | 独立验收脚本；phase15显式Pro/Responses/text/high/16384，和产品8192/14点默认不混用 |

新phase15只新增验收runner与相关离线测试，没有修改产品代码。与代码默认值有关的完整配置、支持格式和路径限制以[设计](design.md)及[需求](requirements.md)对应章节为准。

其他产品与UI能力见当前源码及既有综合交接：下载、字幕、翻译和短中总结保留已有流程；本页phase15时点记录的玻璃工作台与角色嵌入已由F-002/F-003后续实现更新。B站空字幕/轨道结构、OCR未实现、真实手机及平台稳定性等各自证据见需求和对应报告；本页的phase15数字不转记为后续验证。

## 4. 调用预算与封账

phase15 cap2、parent21；两次各单来源全文、相同Pro/high/text配置、HTTP重试0，format/semantic/extra均0。root共享锁串行，发前持久预占，首错停。实际2POST/23275tokens，HTTP200/completed，closed/verify一致，`semantic_quality_verified=false`保留机械核验和内容评分的区别。

| 计数范围 | POST | 供应商tokens | 状态 |
| --- | ---: | ---: | --- |
| 长文工作组phase1–15 | 23 | 319471 | 全部closed |
| 独立Ragas | 16 | 34106 | closed；曾误放已知实例/类别错误 |
| 当前持续整改合计 | **39** | **353577** | 不含下行旧历史组 |
| 更早各历史组 | 67 | 不在本页重新汇总 | 原封账保留，不借余额 |

用户曾持续授权整个整改无总费用/POST上限，但每个新phase仍须明确有限cap、用途、台账和首错停；**这不覆盖当前“第一步完成后等待指示”的边界**。网络恢复、切换账号或文档更新均不重置计数。phase15用满，不能重开或以新组抹去旧尝试。

费用说明仅为报告中的当日官网费率估算，非账户实扣证明；预占至响应耗时包含持久化开销，不冒充纯推理延迟。文档维护不读取余额或凭据。

## 5. 已做验证与本轮未做事项

- phase15新工具24项离线通过，独立工具审查最终C/I/M=0/0/0；初始live父证据/snapshot损坏阻断封账的实际失败和修复日志保留。见[工具审查](acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-15-deepseek-source-tool.md)。
- 当轮root已完成plan/freeze/check/run/verify，两个payload包含完整source；provenance SHA `3160b10297b28602f108c4a101fde759f7092c8224244751018345974801bfe1`。
- 原样导出8文件zip逐成员字节/CRC已核对，SHA `c444865cbb091f96c3da604a640aaacf591b825e95a8e6306e0aea9153a0994f`；此前核对160份旧父资产与新freeze一致。当前文档维护不重新执行这些runner。
- 24项只验证工具行为，不是后端/前端全量，也不证明语义质量；历史1847、1494/86、UI/build等数字只对应各原阶段，不转记本轮通过。

本页较早写入的文档静态检查/原件保护说明属于phase15与F-001阶段。F-003产品验证和边界见页首及[交验记录](implementation-reports/2026-10-16-f003.md)；本次文档同步未重跑产品测试、启动服务或调用模型。未提交、推送或部署。

## 6. 保留的方案与不再执行的旧待办

| 路线/工具 | 当前状态 | 证据 |
| --- | --- | --- |
| A：完整字幕直接交Pro | phase13已运行并导出；六项核心完整，但精度/局部重复未通过 | [phase13](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md)、[独立审阅](acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-content-diagnosis.md) |
| B：独立主题规划→逐主题写作→概览 | 保留设计，未实现/未实测；不是当前待开发任务 | [候选计划](superpowers/plans/2026-10-15-topic-writing-candidate.md) |
| A/B组合：独立标题规划→完整原文写作 | phase14已完成2POST；补齐课程路线两主题，但时间/范围与重复仍FAIL | [phase14](acceptance-reports/2026-10-13-long-summary-fidelity/phase-14-report.md) |
| 同DeepSeek两来源能力观察 | phase15已完成本次第一步；不是A/B改良或跨模型优胜结论 | [phase15报告](acceptance-reports/2026-10-16-deepseek-source-screen/report.md) |
| Ragas Faithfulness | 独立诊断工具；真实错误与纠正例曾同获1.0，不能作为自动放行门 | [Ragas报告](acceptance-reports/2026-10-15-ragas-semantic/report.md) |
| 独立核查/局部编辑的新建议 | 仅讨论，未实现、未运行；用户保留后续决定 | 当前用户边界见§1 |

历史阶段的“待freeze/run”“下一步A/B”“等待新预算”等文字按当时记录阅读。phase1–15已经closed，不能依据旧文档重开；旧报告/脚本/快照/ledger/receipt/冻结审稿保留原字节。文档索引和当前交接负责解释时间，不修改原始结果。

## 7. 下一次接手

1. 先读[统一总表](follow-up-plan.md)，再按需读取本页phase15历史报告和内容审阅；不要把本页早期F-001/F-002/F-003状态当作当前状态。
2. F-004、F-005已结项；F-003当前行为及最新小圈范围已获用户查验通过。F-006已按明确指示实施，当前最终复核与验证状态见[F-006报告](implementation-reports/2026-10-17-f006.md)。
3. 后续工作依据总表和用户最新指示安排；不从phase15历史候选或旧“下一步”文字自动推导模型实验。保留全部closed计数，不把两来源观察说成所有长文已解决。

来源及派生评测继续保留Dr. Ana Bell / Dr. Haohsiang Liao / Massachusetts Institute of Technology / MIT OpenCourseWare署名和CC BY-NC-SA4.0要求；MIT不背书模型输出。Live2D本机资源与含模型历史继续保留，发布按既有隔离过滤流程处理。
