# 本地规范化／通用限定修复候选：短中篇独立内容审查

审查日期：2026-10-12（Asia/Shanghai）。开始审查时phase2仍进行中，**结论仅绑定本phase已完成的zh-short、en-medium最终JSON与response-01/02**；不判长文或phase整体，root另行核验闭账、全部冻结资产及证据链。没有继承首phase PASS，也没有更改首phase审查或原件。

工程约定：最新用户／AGENTS及适用skills优先；可配置窄接口、单向依赖、成熟能力复用，避免无关重构；yt-dlp只由ytdlp_service接触，视觉层只读scene。UI改动须先用ui-ux-pro-max/design-system及primitive→semantic→component token；本审查无UI改动。保护凭据、env、数据库、账号、模型、其他Agent工作及全部freeze/raw/ledger历史字节。仅创建本指定review，未调用网络、模型、服务或测试。

## 方法与证据绑定

采用[本phase准则](../review-criteria.md)、[首phase准则](../../2026-10-11-summary-content-resume/review-criteria.md)、[原rubric](../../2026-10-09-summary-quality-repaired/rubric.json)、[短中必要子句](../../2026-10-09-adaptive-short-medium/review-criteria.md)、[全句精度／组织准则](../../2026-10-09-adaptive-summary-final/review-criteria.md)。旧文件的执行预算、固定字数／7点／240字符与旧候选结论不作为本phase评分要求。每个实质断言按自己的频率、主体、条件与作用范围审阅；别处正确不能修补该句限定缺失。

provenance列41项冻结资产；本次核对其中7项：两篇cleaned TXT、原rubric、短中旧criteria、最终精度旧criteria、首phase criteria及本phase criteria。各snapshot SHA256正确，当前原件字节均与本phase snapshot一致。本次不宣称核验全部41项。两请求的Transcript均逐字符等于对应冻结原文；两raw content均可正常JSON解析，summary/key_points与最终result逐字段相同，没有本地修复改变语义。本次不读取reasoning内容。

| 对象 | SHA256 |
| --- | --- |
| zh-short来源／snapshot0024 | `4e62d9c0f1d25734be1af8dfa7f1328c5f1982590734ca8453b0c2f926e0ae9b` |
| en-medium来源／snapshot0019 | `4b1b09addb5ad3cab6dc885fb4f0a805fede65b2eecc8976b232e180a427edb9` |
| results/zh-short.json | `853601e901e0e29ce6f839c00d39422c79c6ff818061752ef1ff9c51ac627ecc` |
| results/response-01.json | `371ed658f7cf6f6e7920c58185e58f9c97016326d4388dca4d044c6e650e5f27` |
| results/en-medium.json | `f0219d29d0cbf2eff6078789f98485a6a2bdb69a4455df0899d4c5c293c15c0c` |
| results/response-02.json | `2bb054561af29382e37dd8826e3b27d4e40cd10bb4e4d261a54c3d4fed02d813` |

S为result.summary；P编号按key_points顺序；L为原cleaned TXT一基行号，不是VTT时间。两结果S均在JSON L6，短P1–5在L8–12，中P1–4在L8–11。

## 结论

| 样本 | 必要内容 | 每字段精度 | 概览互补／重复 | 本样本 |
| --- | --- | --- | --- | --- |
| zh-short | zh1–4全部full | PASS | PASS | **PASS** |
| en-medium | en1–4全部full | **FAIL：S具体课后书面交付缺通常限定** | PASS | **FAIL** |

中篇失败不表示必要项完全遗漏：通常性完整存在于P2，但按冻结逐句要求，它不能修补S。HTTP、JSON结构、本地规范化及点数合法均不代替内容判断。

## zh-short逐必要子句

来源：[zh-short.txt](../../2026-10-04-natural-subtitle-quality/corpus/zh-short.txt)，输出：[zh-short.json](../results/zh-short.json)。

| ID／来源 | 逐子句与输出 | 整项 |
| --- | --- | --- |
| zh1／L1–4 | MIT中文课full、第二天起全中文full（S/P1）；第一天说明准备方式full、大纲full、学生清楚期望full（P1）。 | full |
| zh2／L5–13 | 两个重要环节full、用语听懂full、备课反映在练习full（P2/S）；每天准备与任务一致full、没准备的练习→转英文的条件后果full（P3）。 | full |
| zh3／L14–16 | 用语不能随意变式full、两说法在该教学情境的差别full、教师须注意full（P4）。 | full |
| zh4／L17–21 | 真有问题且不懂、需用英文问的触发条件full；最后5分钟full、前45分钟中文full、下课／邮件渠道full、维持气氛full（P5）。 | full |

## zh-short全部实质断言

| 位置 | 来源与精度判断 |
| --- | --- |
| S／JSON L6 | MIT／第二天中文对应L1–2；讲者归属及两个关键机制对应L5–13；英文提问时段与课堂中文气氛对应L17–21。“限制英文提问时段”处于维持课堂环境的语境，概括课堂最后5分钟安排，未说禁止课外／邮件提问或永远禁止英文。没有数字错置或提前到第一天。 |
| P1／L8 | 第二天中文L1–2；第一天准备方式、大纲、期望L3–4，顺序与主体准确。 |
| P2／L9 | 两机制L5／L9；听懂要求与三用语例子L6–8。“必须”保留教学要求，不是新增效果保证。 |
| P3／L10 | weekly schedule及每天准备、课堂练习L10–11；“若”保留没准备的条件，转英文后果L12；每日任务一致L13。未增加课前时长或反转因果。 |
| P4／L11 | “不能出圈”L14；两用语和教师注意L15–16。由本点课堂用语例子限定“完全不同”，没有转成汉语普遍不等义或新增初学者事实。 |
| P5／L12 | 有问题／不懂／需英文L17–18；“常做”“可”对应来源常常和许可，未改成每课必有英文问答；45／5分钟L19、下课／邮件L20、目的L21，数字及条件完整。 |

概览没有列具体用语、weekly schedule、未准备后果、用语变式或45／5分钟与三渠道清单。P1新增第一天安排，P2新增可理解用语实例，P3新增准备机制／未准备后果，P4新增变式约束，P5新增条件／时间／渠道。P2、P3共享备课主旨但有相关机制和后果增量，不判同义重复；P2也不是空父概览。没有阻断缺陷。

## en-medium逐必要子句

来源：[en-medium.txt](../../2026-10-04-natural-subtitle-quality/corpus/en-medium.txt)，输出：[en-medium.json](../results/en-medium.json)。

| ID／来源 | 逐子句与输出 | 整项 |
| --- | --- | --- |
| en1／L7–20 | daily grading full（S/P1）；每次表现即每堂课评价full；持续努力修读本课条件full；能力预期归于讲者“并相信”full（P1）。两理由的互动／印象／评价也完整对应L1–6。 | full |
| en2／L21–29 | 通常课后full、每位学生课堂表现full、语言full、文化行为full、后续改进目的full、通常书面full（P2）。S精度问题独立计入，不用coverage抵消。 | full |
| en3／L30–40 | Engrade full、录入成绩full、此外留言full、每位学生私下评论full、学生有账户访问即可阅读教师评论的机制full（P2）。 | full |
| en4／L41–53、L56–80、L81–95 | 依表现的反馈full、发音到详细赞美回应full；中美文化对照在反馈举例范围full、两个具体回应有时full（P3）；L1课堂条件full、讲者／教师鼓励反馈full、所学课堂教材范围full、可改进方向full（P4）。 | full |

P2的“学生只要有账号访问权限即可阅读”在同一句每位学生私下评论及Engrade网站的上下文中保留个人账户读取机制，没有宣称公开全班或通过任意他人账户；不机械要求原字面“登录自己的账户”才记full。

## en-medium全部实质断言

| 位置 | 来源与精度判断 |
| --- | --- |
| S前段／JSON L6 | 一门中文课每日评分L15–20；“讲者说明……原因”L1–20。中性“这份内容”不捏造来源体裁；没有复述两理由清单。 |
| **S中段／JSON L6** | **FAIL：“课后向每位学生提供关于语言与文化表现的个性化书面反馈”**。每位学生／课堂表现／语言文化L23–26有支持，个性化由依表现L41–43支持；但L21–22为“usually, after class”，L29为“We usually do written feedback”。此处列出具体课后书面交付方式，却没有在这项断言内保留通常性，成为无条件的方式陈述。摘要没有字面说“每节课”或“全部都是书面”，不把那些字面词算作新增；失败依据是具体交付断言比来源少了必要频率限定，不是主题名重合。P2两个“通常”不能修补S。 |
| S末段／L6 | “讲者……描述……如何结合文化规范帮助……改进”受本句讲者与中文课语境限定，属于文化行为反馈主题概括，L25–28、L50–80、L81–95支持。未展开具体文化规则或宣称当前独立验证的普遍准则，不另判文化泛化。 |
| P1／L8 | 讲者主体及“并相信”作用域覆盖努力→能力句，L11–17；互动／印象／评价L1–6、每次／每堂课L7–9、两理由采用每日评分L18–20。没有把来源信念写成普遍成功保证。 |
| P2／L9 | “课后通常”L21–22、“通常书面”L29，限定保留；每位学生表现和语言／文化L23–26；“下节课”概括next sessions（L27–28）的后续改进用途，没有新增具体课次／持续时间，不据单复数译法机械判错。Engrade和成绩／私下留言L30–34，账户访问读取L35–40；未添自动评分、公开评论、成绩权重或2026推荐。 |
| P3前段／L10 | 依表现L41–43；简单发音L44–47、详细思考称赞应对L48–53，保留“可以”，没有将所有反馈固定为一种内容。 |
| P3例子／L10 | 文化对照由本点反馈内容与“例如”连续引出，是课程评语的例子，不是独立另起普遍文化结论；美国自然谢谢及两赞美对象L56–64，中国谦虚／不以谢谢接受L65–70，两个回应及“有时”L71–76，基本观念L77–80。没有增添“才是唯一”或有源之外的通常频率；不依赖另字段归因来修补。 |
| P4／L11 | “讲者以称赞为例”与L50–55归属一致；“如果”保留L81–82的L1／课堂表现条件，教师鼓励反馈L83–88，教材／课堂涉及材料L89–92，可改进方向L93–95。教材表达紧贴原“according to a textbook where everything is based on the materials we cover in class”，未新增书名、课外标准或所有学生的普遍因果。 |

## en-medium概览与组织

S提供系统原因、反馈和改进的高层路线，没有复述具体两理由、Engrade双能力、评论层级、中美回应实例或L1／教材条件。P1增加评分理由／逐课粒度／讲者信念，P2增加两处通常性及私密账户交付，P3增加反馈层级与文化例子，P4增加L1条件、教师鼓励与课程材料范围。各点共享评价／称赞主题但有新的条件、例子、能力或后果，符合原重复定义。未发现无增量重复、空父概览或无关最后塞点，组织PASS。

中篇唯一确定阻断是S的具体课后书面反馈通常性缺失；不是4点、篇幅、原文关键词或结构合规问题。不能以P2的限定或首phase PASS改记本输出通过，也不建议删除必要内容凑通过。

## 来源、操作与限制

作者：Dr. Haohsiang Liao / Massachusetts Institute of Technology, MIT OpenCourseWare；短篇 *Creating an Immersive Classroom Environment (Chinese)*，中篇 *Daily Grading System*。原始来源／获取／许可见[manifest](../../2026-10-04-natural-subtitle-quality/corpus/manifest.json)。字幕、衍生总结和本审查依[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)署名、非商业及相同方式共享；代码不因此重新许可，MIT不为输出背书。本次未联网核实链接。

实际完成：本phase两raw及最终结果读取、完整冻结源文阅读、相关7项冻结资产哈希／原字节比对、请求全文与冻结源一致性、raw与result字段一致性、逐必要子句／全部断言／组织来源对照。未做：测试、网络、模型、服务、env／账号访问、长文审查、phase闭账和全部41资产核验。两篇均为已见回归语料；本结论不证明未见样本表现、稳定性或总体质量。
