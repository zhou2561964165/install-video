# 容量／逐字段限定候选：短中篇独立内容审查

审查日期：2026-10-12（Asia/Shanghai）。**仅审查本phase新zh-short、en-medium最终JSON及response-01/02，不继承前轮PASS或FAIL。** root通知phase3已closed3POST、工作组累计13/13；本审查不执行新调用，不代替root的闭账／全资产／原始请求与父链核验，不给长文或总体质量结论。旧raw、评分、冻结和账本保持。

工程约定：最新用户／AGENTS及适用skills优先；成熟能力复用，可配置窄接口与单向依赖，避免无关重构；yt-dlp仅由ytdlp_service接触，视觉层只读scene。UI改动先用ui-ux-pro-max/design-system及primitive→semantic→component token；本文无UI改动。保护凭据、env、账号、数据库、本地模型、其他Agent工作及旧证据字节。唯一写入为本review；未调用网络、模型、测试或服务。

## 方法、准则及证据

按[本phase准则](../review-criteria.md)、[原rubric](../../2026-10-09-summary-quality-repaired/rubric.json)、[短中必要子句](../../2026-10-09-adaptive-short-medium/review-criteria.md)、[全句精度／组织](../../2026-10-09-adaptive-summary-final/review-criteria.md)及本phase冻结的前两phase准则，逐必要子句、每个字段全部实质断言与概览／要点关系对照原cleaned TXT。旧文件的固定字数、7点、240字符及历史执行预算不作为本轮门槛。HTTP、JSON、局部规范化、点数或词汇命中均不替代语义评分。未读取其他reviewer对本phase新短中输出的判断。

新provenance有60项资产；实际核对其中8项：两篇cleaned TXT、原rubric、旧短中criteria、旧最终criteria、首phase criteria、phase2 criteria、本phase criteria。各snapshot SHA256与索引相符，当前原件字节亦与snapshot相同；不宣称本审查核验全部60项。两payload的Transcript逐字符等于本phase冻结原文；两raw content均是完整可解析JSON，其summary/key_points逐字段等于最终result。未读取reasoning内容。

| 对象 | SHA256 |
| --- | --- |
| zh-short来源／snapshot0030 | `4e62d9c0f1d25734be1af8dfa7f1328c5f1982590734ca8453b0c2f926e0ae9b` |
| en-medium来源／snapshot0025 | `4b1b09addb5ad3cab6dc885fb4f0a805fede65b2eecc8976b232e180a427edb9` |
| results/zh-short.json | `6d169027ea03c2768197178c37b4bc6ef9aa4d127eb8573bfe19ea69669d553d` |
| results/response-01.json | `a3ca7bad379cd6d241d6404dbfc5963291dfacc95fe41f3aa0c5e08e72a3004f` |
| results/en-medium.json | `534a7caed1ca997796ead4aed55559f52176f0d81cd3f720d5cedbb53ff6dc72` |
| results/response-02.json | `8bd08d117133377577c7a89a58159d2c7276ca877583e63b06a301754ce37136` |

S=result.summary；P1–P5=key_points数组顺序。两输出S均在结果JSON L6，P1–P5均为L8–L12。以下来源L从cleaned TXT第1行开始，不是VTT时间码。

## 判定

| 样本 | 必要子句 | 全部字段精度 | 概览互补／重复 | 本输出 |
| --- | --- | --- | --- | --- |
| zh-short | zh1–4全部full | PASS | PASS | **PASS** |
| en-medium | en1–4全部full | PASS | PASS | **PASS** |

两份已见回归样本未发现阻断内容缺陷。这不是未见语料、统计稳定性、全平台准确率或本工作组长文通过证明。

## zh-short逐必要子句

来源：[zh-short.txt](../../2026-10-04-natural-subtitle-quality/corpus/zh-short.txt)；输出：[zh-short.json](../results/zh-short.json)。

| ID／来源 | 子句、位置与判断 | 整项 |
| --- | --- | --- |
| zh1／L1–4 | MIT中文课full、第二天开始全中文full（S/P1）；第一天准备方式full、大纲full、学生清楚期望full（P1）。 | full |
| zh2／L5–13 | 两关键环节full、学生理解课堂用语full、备课反映课堂练习full、weekly schedule所列每天准备与练习相连full（P2）；每日准备与任务一致full、未准备练习→英文的条件／后果full（P3）。 | full |
| zh3／L14–16 | 用语不能随意改变full；两固定说法在该课堂情境的差别full；老师须注意full（P4）。没有增补字幕未明确的初学者事实。 | full |
| zh4／L17–21 | 有问题／听不懂且需英文问的触发条件full；最后5分钟full；前45分钟中文full；下课与邮件额外渠道full；维持中文气氛目的full（P5）。 | full |

## zh-short全部实质断言与范围

| 位置 | 来源与判断 |
| --- | --- |
| S／JSON L6 | “这段内容说明”是中性来源表述；MIT／第二天中文对应L1–2；维持中文气氛对应L21，沉浸式是该全中文环境的概括，没有新增实验结果或保证。用语理解、准备与课堂练习一致对应L5–13，有限英文提问渠道对应L17–20。S只给中心关系和渠道主题，没有断言任意学生必定用英文、所有提问只准课后或永远禁止英文；“确保一致”保留来源教学要求而非保证学生效果。 |
| P1／L8 | 第二天中文L1–2；第一天准备／大纲／期望L3–4。时间起点正确，没有改第一天全中文。 |
| P2／L9 | 两机制L5／L9；三个用语实例L6–8；weekly schedule与每天准备／课堂练习L10–11。主体仍为学生准备与课堂练习，没有添加时间长度或固定教材。 |
| P3／L10 | “如果”保留未准备到的练习条件，转英文后果L12；每天准备与课堂任务一致L13。因果没有颠倒；和P2机制相关但新增条件与后果。 |
| P4／L11 | “绝对不能出圈”对应L14；两说法与老师注意L15–16。差别被本点课堂用语／例子范围限定，不推广为所有中文语境普遍不等义。 |
| P5／L12 | 条件L17–18；“通常安排”与来源常常一致，“可”保留许可；前45分钟／最后5分钟L19、下课／邮件L20、气氛目的L21。没有把许可改为每课必发生、没有45+15误写或额外限制。 |

S没有复述用语清单、weekly schedule操作、未准备后果、变式例子或具体分钟／渠道清单。P1新增第一天安排，P2新增机制与实例，P3新增未准备的条件／后果，P4新增固定表达约束，P5新增提问条件及时间／渠道。P2/P3共享备课任务一致，但P3确有新增相关后果，不按主题接近判重复；P2也不是空父概览。组织PASS，未发现阻断缺陷。

## en-medium逐必要子句

来源：[en-medium.txt](../../2026-10-04-natural-subtitle-quality/corpus/en-medium.txt)；输出：[en-medium.json](../results/en-medium.json)。

| ID／来源 | 子句、位置与判断 | 整项 |
| --- | --- | --- |
| en1／L7–20 | daily grading full（S/P1）；每次表现即每节课评价full（P1）；持续一致努力修读该课条件full；能力预期保留为说话者“相信”full（P1）。互动印象／受评价理由也完整对应L1–6。 | full |
| en2／L21–29 | 通常课后full（S/P2）；每位学生课堂表现full、语言full、文化行为full、后续改进目的full（P2/S）；通常书面full（P2）。 | full |
| en3／L30–40 | Engrade full、录入成绩full、此外可留言full、每位学生私下评论full、登录自己的账户读取教师评论full（P2）。 | full |
| en4／L41–53、L56–80、L81–95 | 依表现的评论full、简单发音至更深入中文称赞回应full（P3）；中美回应对照维持为说话者文化例子full、两个具体回应有时full（P4）；L1影响课堂表现的条件full、教师鼓励反馈full、课堂教材材料依据full、可努力改进full（P5）。 | full |

## en-medium全部实质断言、限定与归因

| 位置 | 来源与判断 |
| --- | --- |
| S前段／JSON L6 | 一门中文课每日评分及原因／做法框架对应L1–20、L21–40；没有重述两项详细理由，也没有推断额外来源体裁。 |
| S反馈句／L6 | “教师通常如何在课后通过在线平台……提供个性化反馈”在本字段内部以“通常”限定课后反馈过程，L21–22支持；学生课堂表现与语言／文化L23–26、在线网站L30–40、依表现个别反馈L41–43，后续改进目的L27–28及L93–95支持。不是每节课必有反馈。**S没有陈述书面形式，因此无须在此补一个书面通常限定，也没有依赖P2修补本字段。** 这是对反馈流程的有界概览，未列成绩／留言／账户功能清单。 |
| P1／L8 | “说话者提出……并且相信”明确信念主体，覆盖持续一致努力→能力整句；L11–17支持。互动印象／被评价L1–6，评价每次表现即每节课L7–9，采用两理由L18–20。中文能力仍是说话者对本课努力者的相信／预期，不是普遍成功保证。 |
| P2／L9 | 通常课后L21–22；每位学生课堂表现／语言文化L23–26；下一次课改进L27–28；通常书面L29。Engrade L30–31、成绩加私下评论L32–34、本人账户读取L35–40完整。没有新增自动评分、公开评论、固定比重或2026网站推荐。 |
| P3／L10 | 依表现L41–43；简单发音提醒L44–47、可更详细与称赞回应例子L48–53，保留可以／例子范围。“以下发音”呼应来源following pronunciations，没有虚构具体发音列表；措辞可更自然，但不构成精度或覆盖阻断。 |
| P4美国例子／L11 | 本点开头“文化例子”明确教学例子性质，L54–55对应讲者举例；美国自然谢谢与中文／英文很好的两个回应例子L56–64准确。没有改成每位美国人必如此。 |
| P4中国对照／L11 | 中国文化谦逊、不以谢谢接受对应L65–70；两个回应以“有时会说类似”保留L71–76的频率及例子性质，未增加通常不／固定唯一回应。点末“说话者总结”明确谦逊理念归于来源说话者，L77–80支持。结合本点“文化例子”与说话者总结，整段保留讲者例子／观点语境，不把课例当外部已证实的所有中国人的规则；归因判断在本点内，不借另字段修补。 |
| P5／L12 | “如果”保留L81–82课堂表现来自L1条件，母语是本语境解释；教师鼓励与反馈L83–88，课堂所覆盖材料／教材L89–92，可努力改进L93–95。没有将所有学生表现归因于母语、加入测量指标或拓宽到课外统一文化规范。 |

中篇S的“通常”真实存在于其反馈句作用域，不能为完成任务把它视作缺失；相反也没有用来源或P2替摘要补词。S不陈述书面形式，书面通常性在P2自己那句完整保留。文化对照同点开头和结尾构成例子／说话者归属，且有时保留；没有以只出现“中国”“例子”等关键词机械判通过。

## en-medium概览互补与重复

S给评分理由／做法与通常课后反馈帮助改进的高层路线；没有重复具体两评分理由、表现决定评论层级、称赞两种回应、L1处理或Engrade能力清单。P1新增评分理由、逐课粒度及信念条件；P2新增每位学生／通常书面／具体平台／双能力／本人账户；P3新增评论层级；P4新增文化对照／具体例子／频率／说话者理念；P5新增L1条件／鼓励／课堂教材范围／改进后果。平台和语言文化等主题共有，但要点增加相关机制和必要限定，不属于无信息重复。P3–P5都涉及称赞，也分别有层级、例子、触发条件与材料范围，不按同主题判冗余。没有无关最后塞点，5点和篇幅本身不给分。组织PASS，未发现阻断缺陷。

## 来源、实际操作及限制

原作者：Dr. Haohsiang Liao / Massachusetts Institute of Technology, MIT OpenCourseWare；短篇 *Creating an Immersive Classroom Environment (Chinese)*，中篇 *Daily Grading System*。来源／字幕获取／许可见[manifest](../../2026-10-04-natural-subtitle-quality/corpus/manifest.json)。来源、衍生输出及本审查依[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)署名、非商业及相同方式共享；代码不因此重新许可，MIT不为模型输出背书。本次未联网。

完成：本phase两最终结果及raw读取，原文全文阅读，相关8项snapshot／原件字节与SHA核对，两个完整wire的来源一致性，raw／result字段对应，逐必要子句／每字段全部断言／组织来源审查。未做：模型POST、HTTP、测试、服务、env／账号读取、长文评分、整个60项库存或父预算／闭账完整核验。两篇均为已见回归语料，PASS仅绑定上述新结果哈希；不外推未知样本、稳定性或整个总结质量问题已解决。
