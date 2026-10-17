# 长文整改交接：phase6失败，phase7审查已过待冻结

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页的“当前/下一步/待实现/等待授权”、预算、测试与服务状态均指记录当时。最新用户决定、活动任务与全部后续计划先读[统一总表](follow-up-plan.md)，phase15证据读[阶段交接](handoff-2026-10-16-deepseek-step1.md)；产品实际实现参照[设计](design.md)、[需求](requirements.md)和[UI指南](ui-extension-guide.md)。长文已获准上线使用但质量仍待整改，现有公开20000字符保护和embedded区域约束尚未在本轮调整。历史候选统一汇入总表，不据旧待办启动开发/服务/模型或重开closed phase；原验收及冻结证据保持原字节。

> 本页为2026-10-14恢复阶段历史。phase7现已1POST失败封账，Ragas另16POST仍误放P4；当前状态以[2026-10-15交接](handoff-2026-10-15-semantic-eval.md)为准，不执行下文旧待冻结步骤。

更新：2026-10-14。用户曾要求暂停并更新文档，随后明确「继续」恢复整改。**phase6已closed/failed：仅1 POST / 13208供应商tokens；target_11因引文大小写变化未匹配而立即停止，target_4的实例→类别范围错误仍未被核查发现。新`subject_checks`候选生产相关集121项通过，独立生产审查C/I/M均0；phase7 runner离线测试26项通过，独立工具审查C/I/M均0。phase7尚未plan/freeze/check或发POST；长文质量没有解决。**

工程约定：Superpowers/适用skills优先，成熟组件优先、配置化窄接口及单向依赖；`ytdlp_service.py`唯一接触yt-dlp，前端视觉只读scene。UI使用ui-ux-pro-max/design-system与primitive→semantic→component token。保护既有UI、账号/env、本地模型、用户工作与全部历史证据原字节。GitHub发布仍须过滤Live2D模型历史，不能直接推送本机含模型main。

## 当前实现与默认

公开接口仍返回summary/key_points/provider/model，默认legacy/adaptive/single；`LLM_SUMMARY_FIDELITY_MODE=off`，没有升级默认模型。公开正文上限仍20000字符，超过时422 `summary_unsupported_length`，模型调用前停止；长文入口未恢复。

已实际实现的输入修复：只折叠相邻重复字幕行，跨语境重复保留；多段叶笔记默认源语言，最终仍按请求语言；原文和笔记能装入60000字符容量时合并使用完整原文，装不下则显式有限boundary，不偷偷截源或增阶段。

| 配置 | 当前默认/能力 | 适用范围 |
| --- | --- | --- |
| LLM_SUMMARY_NOTES_LANGUAGE | source；可选output | 内部叶笔记，单段/最终按用户语言 |
| LLM_SUMMARY_SOURCE_CONTEXT_MODE | auto；可选boundary | 完整来源可容纳时优先；context chars=0仍禁用 |
| LLM_SUMMARY_FIDELITY_MODE | off；可选long/review/checks/subject_checks | legacy/single/adaptive显式候选，不是默认质量保证 |
| LLM_SUMMARY_REVIEW_MAX_OUTPUT_TOKENS | 4096 | review/checks核查输出硬上限；最终修订沿来源自适应预算 |
| LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS | 8192 | 新subject_checks候选独立硬上限；14点需7808，避免改变旧checks预算 |
| 总结输出/主题上限 | base4096、ceiling8192、最多14 | 未放宽以取得通过；adaptive无固定800/240字拒绝 |

`long`在多段合并后正常多一次来源自校订；`review`和`checks`正常多两次（独立反馈→修订），短单段不增调用。两叶路径分别3/4/5POST；没有付费重试或隐藏fallback。PydanticOutputParser与LCEL RunnableSequence/RunnableLambda已真实接入，HTTP仍走原服务；LangSmith仅禁用追踪，无新SDK/框架/第三方遥测。

phase6 `checks`模式沿用原有动态必需对象字段`target_0…target_N`，每项含assessment、连续原文引用和简短finding；其`128 + 256 × (要点数 + 1)`预算仍受4096旧配置约束。新`subject_checks`是另一个显式候选，动态字段增加`scope_relation`、`source_subject`、`draft_subject`，并允许必要证据字段为null；source/draft主体按所在目标和连续来源引用做字面绑定，只转换行分隔空白，不改写大小写或行内空白。14点核查预算`128 + 512 × (要点数 + 1)=7808`，由独立8192硬上限配置控制，避免改变phase6原checks设置。两个候选都固定走Responses `json_schema`，incomplete、容量不足或结构错误立即停止；字段结构、引用出处和assessment不是语义证明。

## 真正剩余问题

1. **P4范围泛化尚未解决**：phase6 target_4仍把具体计算器限制判断为supported，没有核对源主体`this calculator`和草稿主体`fixed-program computers`是否对应同一谓词。不能把新提示/schema/离线测试通过写成内容通过。
2. **phase6保留为失败原件**：target_11把原文句首小写`if`改为大写`If`，连续引文校验立即失败；没有进入revision，没有phase6产品结果。phase6不重开、不把raw转为修订输入。
3. **phase7还未实测**：新候选目前只有离线实现及测试，独立审查修复和phase7 runner完成后才可独立冻结并最多2 POST复用phase4草稿。完整正常长文、未见Lecture2及新流程短中回归仍待后续phase；公开入口保持未恢复。

phase2/4公开feedback没有提及P4，不能据此推断模型内部没读。此次改动先解决核查结果不能按目标唯一约束的问题，并加强跨类别/实例的主体范围表达；最终仍以实际内容审阅判断。

## 本组实测与封账

用户本轮「不设置预算」授权只表示本任务没有总POST/费用上限；产品每请求资源仍有限。以下每次尝试均持久预占、root单caller共享锁串行，旧67POST各组保持封账不重开。

| Phase | 实际POST | 供应商tokens | 本轮结果 |
| --- | ---: | ---: | --- |
| 1 来源保真输入修复 | 3 | 51662 | 14点结构通过；5full/1partial，精度FAIL |
| 2 一次自校订，复用phase1草稿 | 1 | 26699 | 6full，精度FAIL；恢复下一讲衔接 |
| 3 Flash反馈→修订，复用phase2 | 2 | 25830 | 最终product SHA完全等phase2，P4未修 |
| 4 Pro显式对照，复用phase3 | 2 | 27502 | 6full，精度FAIL；全部业务文字等phase2，仅model meta变Pro |
| 5 完整checks，复用phase4 | 1 | 15907 | 输出length截断，停止；未修订，无新最终结果 |
| phase1–5历史小计 | **9** | **147600** | 原件全部closed，长文质量未通过 |
| 6 完整checks，复用phase4 | 1 | 13208 | quote大小写不匹配，首请求后关闭；P4范围错误仍在，无结果 |
| phase1–6累计 | **10** | **160808** | 全部closed；P4未解决，phase7未实测 |

详细证据与每phase哈希见[phase1–5报告](acceptance-reports/2026-10-13-long-summary-fidelity/report.md)和[phase6报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-6-report.md)。原snapshot/payload/raw/result/ledger/receipt、旧脚本及冻结设计/审查稿保持原字节；docs更新不替换其结论。内部call-group状态active只代表累计登记，不重开已closed phase。

## 验证范围

- 2026-10-14续行当前代码相关5文件：**105 passed/0.93s**，含新主体范围提示、新动态checks schema、Responses预算/单段边界及旧来源校订回归。它证明离线逻辑和报文形状，不证明provider遵循schema或P4语义已修复。
- phase6工具runner及其离线测试：**18 passed/340.70s**；含父phase绑定、candidate_assets完整性检查、plan/provenance/offline-check严格整数`phase_post_cap=2`、重复check与float cap拒绝。phase6实际已closed并失败，真实1 POST / 13208 tokens，详情以[phase6原报告](acceptance-reports/2026-10-13-long-summary-fidelity/phase-6-report.md)为准。
- phase7生产候选：subject专测35 passed，与旧checks/review/revision相关路径集成为121 passed/0.58s；production审查Critical/Important/Minor均0，见[生产审查](acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-7-subject-checks-production-final.md)。新runner/测试最终SHA分别为`797F512176CDB4F649EAF8C8E1B6F33FD9F0C91A0491F8A049D5B23E17901A2A`和`3D14060885E2A412B40F5D420321ED8BBA8B47F58DDB39CEFFADE88D73D24AF1`，离线26 passed/381.37s；runner工具审查C/I/M均0，见[工具审查](acceptance-reports/2026-10-13-long-summary-fidelity/reviews/phase-7-subject-checks-tool-final.md)。初始mock祖先目录Important已RED复现、修复并独立验证；审计双声明不是身份认证。所有离线结果只证明代码/runner结构和路径行为，不证明真实模型遵循或P4语义已修复。
- 输入修复与历史fixture兼容后的后端全量：1847 passed/424.56s，发生在随后校订模块之前，不能写为当前全部代码新全量。
- 最新checks/旧legacy-staged等相关7文件：197 passed/0.84s；新18+旧58为76 passed/0.43s。机械通过不代表内容通过。
- phase5工具28项先通过528.20s；新增target_count/冻结纯prompt回归单独1passed，容量回归单独1passed。共30case，未重新跑最后全30。
- 完整生成工具原件消费前统一packet SHA保护27passed/84.21s；后来孤儿/锁3项单独9.22s。总29case未重跑最后全29，工具未真实run完整生成。
- 本会话UI交付193前端项/build/18本机模拟接口浏览器检查属于已有UI阶段，暂停时未重跑。见[角色嵌入报告](acceptance-reports/2026-10-13-embedded-mascot-refinement/report.md)。

## phase7真实复验前的待办

1. 生产/runner的离线实现及独立审查已完成；执行plan/freeze/check前复核当前候选清单及哈希，冻结subject schema/预算配置/prompt、相关测试和两份phase7 review。
2. 离线plan/freeze/check只绑定closed phase4 source/raw02/product/receipt hashes及其已保存草稿，phase7 cap=2；phase6失败原件不进入revision输入。
3. 离线check后由root唯一串行执行最多2 POST；每次发前持久预占、共享锁，错误即停，历史10次及旧67次不重置。
4. 若phase7产出完整结果，独立逐点审阅P4范围及其他core；结构、quote与assessment通过不视作内容通过。
5. 之后分别制定有限phase并测试正常完整长文、未见Lecture2及必要短中回归；依真实结果决定是否调整默认/公开容量。

未见来源已从官方MIT OCW Lecture2准备VTT/txt/manifest，33709正文字符/1467行，预先8核心准则，**0POST**；source与派生审阅按Dr. Ana Bell/MIT OpenCourseWare署名和CC BY-NC-SA4.0保留。准则、源/raw hash见[未见准则](acceptance-reports/2026-10-13-long-summary-fidelity/unseen-review-criteria.md)。没有提交、推送或部署；本机现有模型与未提交UI改动保留。
