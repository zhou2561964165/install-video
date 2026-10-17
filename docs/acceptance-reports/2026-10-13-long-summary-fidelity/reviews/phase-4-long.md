# Phase-4 Pro有限对照：独立完整长文语义审阅

工程约定：用户/AGENTS/适用 skills 优先；成熟能力复用、配置化窄接口和单向依赖，yt-dlp 唯一接触层、视觉只读 scene；UI使用 ui-ux-pro-max/design-system 与 primitive→semantic→component token。保护用户工作、账号/env、本地模型和全部历史原件。只创建本review，不改代码、字幕、raw、输出、账本或env；不运行模型、测试、网络或服务，不读取新candidate tests，不构造模型答案。

## 本次结论

**Verdict：FAIL。Coverage：6 full / 0 partial / 0 missing；precision：FAIL；overview / organization：PASS。**

本次全部必要core子句保留，包括赋值与求值、radius重绑、area须显式重新计算以及最后衔接下一讲控制流。精度失败仍来自本次 **P4：把具体旧计算器的四则/不能绘图、邮件、上网限制扩大到固定程序计算机类别**。这是重新核本phase原字幕与实际raw后的结论，未继承旧评分，也未只核P4。summary及全部14点的逐断言记录在下文。

本次文本与phase2的summary/14points逐字符串相等，没有任何实质文本变化；结果model元数据改为Pro。因此没有新增文字回归，也没有实际纠正P4。本次内容评分仍独立以phase4冻结源为准，不以相等比较代替来源审阅。单次模型有限对照不能证明某模型的一般能力、所有长文稳定性或默认产品质量。

## 实际证据与profile

评分对象为 [en-long.json](../results/phase-4/en-long.json) 的result及 [response-02.json](../results/phase-4/response-02.json) 的实际content；[response-01.json](../results/phase-4/response-01.json) 是本轮实际review反馈。P1–P14为本次数组顺序，L指本phase冻结source `snapshots/0030.bin` 的原字幕行号。依据仍是 [review-criteria.md](../review-criteria.md)、原core rubric及原精度/组织准则，讲者教学简化按源忠实度评价。

provenance为work `long-summary-fidelity-20261013` / phase4，冻结时间 `2026-10-14T09:12:08.914043+00:00`。本候选provider `deepseek`、model `deepseek-v4-pro`，explicit comparison；沿正常base4096/ceiling8192、auto response/thinking、review输出预算4096、point ceiling14。实际wire为json_object / thinking disabled，review max_tokens4096，refine自适应max_tokens8192；不是phase2的enabled thinking/base16384候选，也没有升级默认模型。

本phase实际2POST：review和refine各1，供应商tokens分别12882与14620，合计 **27502**；receipt closed、work_posts **8**、parent_posts6。复用phase3精确draft，不重新付费抽取字幕。format/semantic/extra均0，本review增量 **0POST**。机械closed/verify由root完成，`semantic_quality_verified=false`与本报告人工评分分开，不能把closed或结构成功当成内容通过。

两份实际payload的original_transcript均与冻结source全文34894字符逐字符相等；两份draft的summary及全部points均与phase3 product逐字符串相等。refine payload中的review_feedback与实际raw01反馈字符串完全相等。raw02 JSON直接解码后的summary和全部14points与product逐字符串、顺序相等，没有本地删句/截字/修正来制造通过。

| 原件 | 实际 SHA-256 |
| --- | --- |
| en-long.json | `8c013c57882d281817ac017992a1c6fa138705e52b776a674e2dc08c510be616` |
| provenance.json | `d087b2b2d71800c0b67e01a37724239cef6f5c052e7fe3ab5091fcdd0bfb1944` |
| payload-01.json | `b0863a2dfa43a9fecdcf7243c1cbe1cdd8640d7980389c254bb321a59a4f7cbf` |
| payload-02.json | `fe9d7d843414e8a47aff72268d0f6c768983e3df17d85b2bce747cec1e06f951` |
| response-01.json | `a527173a83e2b5bcdd997db5aadf8468fb16518ea180f8878c1960e10cef3cba` |
| response-02.json | `099f662a8e616ce37e075c7d4055eb13ec1862e164461a37cf6e14b27fc4d13c` |
| source snapshots/0030.bin | `c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7` |
| manifest snapshots/0036.bin | `c5426b5d1fb9c5381af2a5e223905f163301be1087167fc5b42ef9f79e6640d3` |

## Core6全部必要子句

| ID | 本次具体内容及必要关系 | 原字幕 | 新评分 |
| --- | --- | --- | --- |
| long1 | P1计算、把结果存内存；P1末段及summary强调只有告知指令才执行。计算与记忆结果、显式指定操作同时具备。 | L275–292、L319–336 | **full** |
| long2 | P2事实陈述与配方/步骤的定义；P3简单四步、判断/重复控制流、接近停止。不能只靠算法名称评分，此处机制齐全。 | L340–344、L373–382、L507–588 | **full** |
| long3 | P4存储并执行序列、更换指令同机换任务；P5测试结果决定下一条/跳转/跳过/重复。具体计算器类别错另记precision。 | L628–642、L700–754 | **full** |
| long4 | P7句法，P8静态语义及单义/可能非意图；语法错捕获、到错分支才能捕获静态语义；非预期输出/崩溃/不停止。 | L854–889、L920–943、L979–1022 | **full** |
| long5 | P10操作有类型对象，类型决定可做操作；标量不可分/非标量有结构；P9/P12表达式求值为一个值。 | L1054–1066、L1090–1114、L1229–1241 | **full** |
| long6 | P13名字绑定值；P14 radius2.2→3.2且area不随之重算，执行显式重算area才变；P14末句和summary末句均预告下一讲控制流，位于最终内存例之后。 | L1307–1336、L1427–1507、L1510–1515 | **full** |

没有必要尾部遗漏。不要将“下一讲”或area显式重算重新报成当前缺陷；P4精度失败仍使整个候选不能通过。

## 本次精度失败：位置与原句

**raw02 `key_points[3]` / product P4：**

> 历史上，固定程序计算机（如计算器）只懂加、减、乘、除，不能绘图、发邮件或上网，要做另一件事就得另造一台固定程序机。

源L596–600引入类别，L609–611明确 `an example of a fixed-program computer is this calculator`；L612–620的限制主语是这台旧计算器。L607–608还说明现在计算器更复杂，L621–626说另造固定程序机器能做另一件事。源没有将全部固定程序机器归成只能四则、不能绘图/邮件/上网。

本句以“固定程序计算机”为类别主语，括号“如计算器”为举例，四则与不能做的能力仍挂在类别上。“历史上”是时代限定，不是将主语变回具体旧计算器。后半同机存储程序机制正确，也不能修复前半范围。因此 **precision FAIL**；评价依据是源自己的指代范围，不是外部理论或理论正确性争议。

## 实际feedback检查

本次raw01 `feedback`开头称“存在以下不匹配”，随后实际上主要列一致项：P1、P2、P3、P5、P6、P7、P8、P10、P11、P12、P13、P14及四条summary概括；P1的轻微措辞差异还明确说不影响核心。它最后写 **“未发现实质性不匹配”**。

公开反馈没有列出P4原断言、没有核L609–611的 `this calculator`，也没有说明四则/不能绘图等应限于该实例。反馈中的summary“固定程序与存储程序架构”话题一致，不能代替P4具体范围的核查。**可确认该公开反馈遗漏了实际存在的P4 mismatch，其“未发现”结论不足以成立**；不能据此推断模型内部完全没读那段或认定所有其他点都已逐句核完。

作为用户允许的对照，读取phase3实际raw01 feedback：同样称未发现实质错误，主要核抽奖、速度估计、四步、英语静态语义/程序单义、Out和area，不包含P4实例类别限制。两模型本次公开反馈都没有报告此目标，Pro并未在这次有限对照修复它。refine实际得到本phase反馈，但输出仍保留P4原句。这些是可观测输入/反馈/结果关系，不是对模型内部推理原因的猜测。

这也说明“反馈列了很多与源一致的条目”不等于识别了所有mismatch。feedback是待核数据，既不是源文，也不是独立语义验收凭据；其结构合法和refine读到了反馈不会提高本报告的precision评分。

## Summary全部实质断言

| 实际分句 | 源与判断 |
| --- | --- |
| MIT6.0001/600第一讲 | L28–30正确，未发明日期/成绩。 |
| 课程目标：概念、编程技能、通过psets解决问题，强调练习 | L147–168三个目标/psets，L172–175练习基础；概括准确，无“一定成功”的强化承诺。 |
| 明确指令下快速计算并存储结果 | L275–292、L319–336，功能与指定关系准确，不把人意图当自动推断。 |
| 陈述/命令知识、平方根、固定/存储程序、图灵原语说明计算原理 | L340–588、L596–789，高层教学路线正确，没有在summary重述P4错误类别规则。 |
| Python对象类型、表达式运算符、print、赋值内存绑定 | L1054–1510内容正确，不新增实现能力或结果。 |
| 程序单义与英语歧义 | L894–943按讲者教学对比正确，单义不保证符合人的意图。 |
| 最后预告下一讲控制流 | L1510–1515相对时间与衔接准确，不误作后续debug课。 |

**Summary自身precision PASS。** 不能抵消P4独立失败。

## 全部14points逐断言

| 点 | 实质断言/限定、原源定位与判定 |
| --- | --- |
| P1 | 计算/内存两功能L275–292；十亿次“可能差不多”及数百GB“不罕见”L282–296；内置加减乘与程序员组合新计算L297–318；讲座反复强调只知/只做告知及无心智L319–336。**PASS**，速度/存储属本讲时代性估计，不作为所有设备实测保证。 |
| P2 | 事实定义L340–344；课结束前获奖/Google Cardboard L350–355/L370–372；平方根y*y=x及单靠陈述不知步骤L493–505；配方定义L373–382；Ana扮机器/Anaconda L362–405；random.randint16–272/75/名单/Lauren Z-O-V L453–469。**PASS**，时间与最终演示数字按源，非最终报名人数断言。 |
| P3 | x16/g3 L507–515；g*g接近x停止返回g L516–521，不接近取g与x/g平均并重来L522–547；四步、判断/重复、停止L554–588；.01/.001为例如L578–584。**PASS**，不把9当足够接近16，不强制唯一容差。 |
| P4 | 类别演变L596–626，具体this calculator能力限制L609–620被写成类别，**FAIL**；存储/执行/改序列、同机不同任务及今天计算机L628–642正确。 |
| P5 | memory/I/O/ALU/control unit四部分L648–669；内存数据与指令L664–667；ALU加减L657–663；计数器首条取指送ALU L670–679；通常递增1 L690–699；测试真/假可能下一条/回起点及可能输出L700–732；解释器下一条/跳过/重复L749–754。**按源PASS**，同点有控制流例外，不绝对线性执行；四部分按讲者简化教学读。 |
| P6 | 加减、逻辑、等于/小于测试、移动存储L735–748；Turing六原语与纸带L755–768，名称和顺序保留；更方便原语L769–776；Python可计算前提、理论上其他语言同算L777–789。**按源PASS**，归因/模态准确，不用外部理论改写“可计算任何东西”的讲者说法。 |
| P7 | 原语组合表达式有值/意义L796–808；float/Boolean/数字/字符串/加减L817–826；英语词L812–815，cat dog boy三名词无效与cat hugs boy名词动词名词有效L834–844；Python word后跟5无效、operator/operand/operator L845–853。**按源PASS**，字幕中的结构顺序未自行纠正，也未加不存在的加号变成另一表达。 |
| P8 | 飞机行为/空中飞机两义和reading lamp双关L894–919；程序单义可能非意图L920–943；语法易捕获/指出行L967–978；静态语义须到错分支L979–986；可能期望0得10/崩溃/不停机L991–1022；后续debug L944–947；I are hungry静态语义差/I am hungry更好L861–869。**按源PASS**，可能性保留，没有把讲者初学者“最挫折”评价加强成确定排序。 |
| P9 | 定义命令序列、表达式求值、命令解释器L1023–1030；shell简单2+4测试与左编辑器多行复杂程序L1031–1053。**PASS（该讲演示布局）**，左侧不是所有IDE通用摆放规范。 |
| P10 | 一切对象/程序操数据/有类型约束操作L1054–1066；标量不可分数字5/非标量有结构列表5,6,7,8 L1090–1114；int/float/bool/NoneType L1115–1134；True/False大写、None单值/类型缺失L1122–1134；type L1137–1148；目标类型置对象前、float(3)3.0、转整数截断非舍入L1149–1167。**按源PASS**，None的说法来自教学原文，不变为理论纠错任务。 |
| P11 | print交互L1177–1186；shell3+2显示5只是查看L1187–1192/L1203–1210；editor3+2不打印L1193–1202；print5到console L1211–1217；该演示Out/无Out辨别L1219–1227。**PASS（连续具体演示语境）**，不外推为所有Python终端规则。 |
| P12 | object/operator/object求值为值L1229–1241；对int/float下+,-,*双int得int、有float得float L1242–1260；除法始终float L1261–1265；%为i除j余数、i**j为i的j次幂L1266–1279；普通优先级/括号改变L1280–1288。**PASS**，first-three子集准确，没有扩到除法/%/**。 |
| P13 | =右值左变量名/绑定内存可以后引用L1307–1342；描述性/可访问L1294–1305、名字复用及代码清楚L1343–1348；圆面积pi/radius L1349–1377；右表达式求值左变量/解x须指定怎么算L1380–1421。**按源PASS**，不是自动解数学方程；前例pi3.14159/pi_approx22/7是省略的可选数值，未错写。 |
| P14 | 新赋值重绑L1422–1426；明确“内存示例中”pi3.14/radius2.2/算area L1427–1459；radius+1从2.2到3.2 L1460–1472；2.2还内存但无句柄、可能GC L1473–1491；area不变因没重算/显式执行才变L1493–1507；最后下一讲控制流分支L1510–1515。**按源PASS**，数值/模态/因果及结尾齐全，不称程序自主新增指令。 |

## 特别边界与可能回归

**不同pi：** L1316–1327前赋值pi3.14159/pi_approx22/7，L1349–1377前面积pi3.14159；L1427–1436后内存例pi3.14。本次P14明确限定后内存例，P13未列前数值，不混两次绑定。不为可选细节省略扣core。

**抽奖范围：** L427–439首端15改16、末端266改271；L453–457最后random.randint说16到272抽75，L463–469确认75找到Lauren。本次P2描述该演示，而非272人最终报名/永久截止；未拿266/271当最终执行范围，时间“下课前”对应L350–353/L370–372。不要求把每次口头修正列进成品。

**Out：** 原句“如果没有显示‘Out,’，就意味着内容被打印到控制台”紧接shell3+2、editor3+2、print5的连续具体示例，源L1219–1227如此解释；按该演示范围接受，不凭空读取“所有Python控制台必然适用”的断言。但它不能脱离语境作通用Out判据，P9左侧编辑器同理。

**安全/可选物流：** L123–136仅Anaconda及简单输入的学习安全建议未进入输出，不扣core，也未出现任意程序绝对安全的新承诺。课程目标/psets/练习有L147–175来源；没有新日期、评分权重、测试分数、固定次数、性能保证或成功承诺。L987–990的“probably/especially初学时”评价未被采用，不用不存在的评价制造新精度错误。

**相较phase2所有实质变化：** 对照结果是summary和全部14点逐字符串全相等，只有provider result中的model元数据由flash变Pro；逐源审阅没有发现新增内容回归。尾部、求值、area显式重算、类型约束、算术子集与时间均保持准确，P4的同一范围错误继续存在。字节相等不是质量保证，只说明本次对照没有产生成品语义变化。

## Overview与组织

**PASS。** Summary是首讲目的、计算指令中心关系与教学路线。没有复述算法步骤、抽奖数值、print显示规则、类型转换、算术结果条件或重绑数值；主题标签与point自然重叠符合原规则。

P1的两功能/原语组合为summary之外的独有解释；P2事实与P3步骤互补；P4机器演变/P5执行机制/P6可计算性不同；P7句法/P8静态语义与含义和错误相关但有独立内容；P9执行/P10对象类型/P11显示与print/P12算术/P13名字绑定/P14重绑后果沿讲座顺序发展。P13没有先重复area不变后果，不与P14重复同一概念数值例。

P1/P8/P14共用计算机按指令执行，分别说明能力、非预期结果及不自动重算，不是只有同义句。P14下一讲属于最后示例的收束，summary高层预告允许与point的分支目的呼应。没有无关尾点清单，不以14点/长度或JSON格式单独判通过。

## 真正剩余问题与实际操作

此Pro对照的覆盖和组织完整，精度仍失败：必须保持P4实例能力的正确指代范围。公开review没有识别它，refine没有改变它；结构化反馈、换模型和两次成功POST不能宣称内容目标已解决。下一讲/求值/显式重算不是当前剩余缺陷，不放宽上限或借外部理论改评分。

实际读取本phaseprovenance/receipt、wire/raw/product、冻结source/manifest及本report准则；为用户允许的反馈对照读取phase3实际raw01，并比对phase2成品文本。进行内存JSON/字符串与SHA核对，逐源核所有断言，只创建本文件。**0模型/新增POST、0网络、0测试、0服务、0env操作**。未读新candidate tests或构造答案；未修改任何旧评语或原件，不重新执行机械verify。

冻结manifest归属：Dr. Ana Bell / Massachusetts Institute of Technology, MIT OpenCourseWare，*Lecture 1: What is Computation?*，[原课程资源页](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-1-what-is-computation/)。source及派生review保留 **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)** 归属与许可，未外网查验；MIT不背书模型或产品。讲者教学简化按来源评价，不扩成独立理论真值。
