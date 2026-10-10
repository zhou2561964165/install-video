# organization-refined 独立语义验收准备清单（2026-10-07）

当前状态：**准备清单；等待主 agent 通知本轮真实输出，尚未评分。** 主模型及推理设置继承主 agent，不切换模型、不另行调用模型。本清单将冻结标准展开为可审核子句，不修改 rubric，不向产品提示词、抽取器或模型请求注入语料答案。

## 工程约定与独立职责

1. UI/视觉/交互变更先使用 `ui-ux-pro-max`（`--design-system` / `--domain color|typography|ux` / `--stack`）和 `design-system`；设计采用 primitive → semantic → component 三层 token。
2. skill 指引优先于计划；例如每屏最多动 1–2 个关键元素的限制优先于常驻动画清单。用户明确指令优先于技能。本任务不涉及 UI 修改。
3. 颜色、字体、时长一律走 `:root` token；能力数据驱动、可配置、保留扩展，避免硬编码与大规模重构。
4. 模块通过稳定窄接口单向依赖；`ytdlp_service.py` 是唯一接触 yt-dlp 的层；LLM 经 `llm_service.py`；视觉层只读 `scene`，不修改下载状态，不 import 下载核心。新增能力通过接口隔离，不触碰既有核心。
5. 本分工只拥有新建的 `docs/acceptance-reports/2026-10-07-grounded-summary-refined/semantic-review-checklist.md`。不改其他文件，不覆盖旧报告、冻结快照或台账，不提交。
6. 只读本地 handoff、许可语料及评测证据；不联网，不读取 `.env`，不调模型，不启动或重启评测，不借用旧预算。并行协作不接管 producer 或入口 agent 的文件。
7. 准备完成即返回主 agent，等待其通知真实结果；收到通知后可只读独立 review。只有收到新增 JSON 的明确授权通知后，才允许新建本目录 `results/organization-refined-semantic-review.json`；已有同名文件不得覆盖，需返回冲突。本准备阶段不创建该 JSON。

## 已读依据、冻结身份与历史边界

- 最新 [handoff-2026-10-07.md](../../handoff-2026-10-07.md) 优先；旧 [handoff.md](../../handoff.md) 仅作背景，旧暂停和旧测试数字不代表当前任务状态。
- 语义标准：[organization/rubric.json](../2026-10-07-grounded-summary-organization/rubric.json)，冻结于 `2026-10-05T04:52:40.327647+00:00`、新输出出现前；SHA-256 `92418e725678a54aafd51d6c457b1ebd42326f73e1c0b6aa43a86bf147be8d49`。
- 历史独立 [organization-slots-semantic-review.json](../2026-10-07-grounded-summary-organization/results/organization-slots-semantic-review.json)，SHA-256 `66bec7899ef9ed8c48ab01abadfef9c747f4474dea2fe69e994335c420cf99a3`。
- 原语料 [manifest.json](../2026-10-04-natural-subtitle-quality/corpus/manifest.json)，SHA-256 `c5426b5d1fb9c5381af2a5e223905f163301be1087167fc5b42ef9f79e6640d3`，与冻结 rubric 的 manifest 指纹一致。
- 已读许可 [LICENSE.md](../2026-10-04-natural-subtitle-quality/corpus/LICENSE.md)，以及下表三份完整本地 TXT；原始字幕的口误、重复、自我纠正不人工补写。

| 本地原文 | 长度与行数（manifest） | 原始文件 SHA-256 |
| --- | --- | --- |
| [zh-short.txt](../2026-10-04-natural-subtitle-quality/corpus/zh-short.txt) | 608 字符 / 21 行 | `4e62d9c0f1d25734be1af8dfa7f1328c5f1982590734ca8453b0c2f926e0ae9b` |
| [en-medium.txt](../2026-10-04-natural-subtitle-quality/corpus/en-medium.txt) | 2199 字符 / 95 行 | `4b1b09addb5ad3cab6dc885fb4f0a805fede65b2eecc8976b232e180a427edb9` |
| [en-long.txt](../2026-10-04-natural-subtitle-quality/corpus/en-long.txt) | 34894 字符 / 1516 行 | `c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7` |

以上指纹在准备时实测一致。指纹只确认本地材料身份与完整性，**不证明语义覆盖或正确性**。

旧 `organization-slots` 获 13 POST 授权、实际 12 预占 / 12 HTTP 200，报告 tokens 52880，失败后停止，余 1 不用。旧短/中 8 个 essential 为 5 full / 3 partial / 0 missing；长篇 6 个 essential 未在最终输出上评审。旧长篇 compose 有 7 槽、候选摘要 946 字符超过当时 800 合同，未完成 audit，不能当作最终交付或补成 14/14。旧轮记录保持原样。

用户交接的当前 producer 候选为 summary 2 倍候选余量（默认候选上限 1600、final 800）、compose 固定 7 槽，以及频率、观点、姓名的通用提示修订。新真实 profile 预计 13 POST；准备时尚无本轮实测结论。旧 rubric 中历史 `24` ceiling 不作为新轮预算授权，新轮预算和阶段身份由主 agent 提供的独立证据确认。不以离线修订、旧 HTTP 成功或更短文本宣称新修订有效。

## 评分方法与记录单位

- 固定分母 **14 essential = zh1–zh4（4）+ en1–en4（4）+ long1–long6（6）**；不能增加或重划 essential 使候选更容易通过。
- 按最终 `summary` 与最终 `key_points` 的联合语义覆盖判定；可以跨句/跨点支持一个复合事实，但每个必需子句都要定位。允许准确的中英文转述，不要求逐字照抄或关键词命中。
- `full`：全部必需子句、条件、范围、后果和必要归属可由最终文字支持，没有被其他最终文字否定或过强表述破坏。`partial`：仍有准确核心，但有子句缺失或限定/归属不完整。`missing`：没有可支持该核心事实的准确最终表述。矛盾、夸大、无依据新增均另记 precision finding；保留原文与输出证据、解释状态，不能靠一个标签掩盖错误。
- 只在 trace、fact bank、compose 候选、audit 推理或 fact ID 中出现，不算最终覆盖。没有最终结果的样本记 `not_evaluated`，不把它当 missing，也不计入已交付样本的 full/partial/missing 分母。
- 每个 essential 记录：`id`、`status`、各子句的输出位置（summary 句 / P1…P7）、对应原文行/字符范围、缺失或偏差理由、precision findings。字符区间采用 rubric 的清理后文本 0 基、左闭右开；行号从 1 起，不冒充原 VTT 时间轴。
- 同时检查单独展示的 key point：summary 里的讲者归属不能自动补足一个脱离上下文、泛化为普遍规律的 point。联合覆盖与独立点的 precision 分开记录；若同一复合事实被过强 claim 损坏，不能仍判无条件 full。
- 只有三份本轮最终结果均可评，才汇总 `full + partial + missing = 14`。若未齐，报告已交付事实小计及 `not_evaluated` 数，明确不能宣称 14/14。

## 14 个 essential 的逐子句核对

下表每行均需核对全部子句及范围，并为最终评分提供输出位置和理由；这些勾选在真实 review 后才能确认。

| ID | 必需子句与范围 | 原文依据（行；字符区间） | partial / precision 风险 |
| --- | --- | --- | --- |
| zh1 | ① 此 MIT 中文课堂从**第二天**开始全中文；② 第一天说明准备方法；③ 第一天介绍**大纲**；④ 第一天说明对学生的期望。四者同属本课堂安排。 | 1–4；`[0,83)` | 只有准备、期望却漏“大纲”仍为 partial；第一天就全中文与原文冲突。 |
| zh2 | ① 学生听懂固定课堂用语；② 课前准备与课堂练习任务一致；③ 两者作为维持全中文课堂的两个关键环节。 | 5–13；`[84,390)` | “充分备课/提高听力”不能替代任务一致；不能只保留一个环节。未准备的练习使学生转用英语属于可核对的后果，若写出需准确。 |
| zh3 | ① 教师不能随意换课堂用语；② “请你再说一遍”与“请你再说一次”对本教学场景初学者不等同，体现固定表述要求。 | 14–16；`[391,477)` | 只说“课堂用语重要”缺具体语义差别；不能写成教师应多换同义表达，也不能泛化为两句在任何中文语境都不等义。 |
| zh4 | ① 前 **45 分钟**全中文；② 英文问题可在最后 **5 分钟**问；③ 也可下课后问；④ 也可用邮件问。保留课堂时段与课外途径。 | 17–21；`[478,608)` | 少任一途径或时间限定都需说明；不能写成永禁英文、45+15 分钟或课堂内任意英文提问。 |
| en1 | ① 教师采用 daily grading，评估**每堂课表现**；② 学生持续且一贯努力（persistent **and** consistent）；③ 教师**相信/预期**这种投入能体现良好中文能力，是采用制度的理由。 | 7–20；`[143,482)` | “只要坚持就一定学好/保证掌握”把讲者信念变保证，不能判 full；“每日反馈”不能替代每课表现评估。 |
| en2 | ① **通常**课后提供书面反馈（usually after class / usually written）；② 针对学生当堂表现；③ 包含语言表现；④ 包含文化行为；⑤ 帮学生知道下次改进什么。 | 21–29；`[483,715)` | 每课评估与通常课后书面反馈频率不同；不能把 usually 改 always/每堂必写。“个性化反馈”不足以独自覆盖内容与改进目的。 |
| en3 | ① 使用 Engrade；② **录入成绩**；③ 给各学生**私密评论**；④ 学生通过自己的账户访问教师反馈。 | 30–40；`[716,984)` | 只提私密评论与账号、漏成绩录入仍 partial；不能发明自动评分、公开评论或把历史工具说成已核验的 2026 推荐。 |
| en4 | ① 反馈取决于学生表现；② 可涉及发音，也可涉及称赞回应的文化行为；③ **讲者课堂示例**对比美国式致谢与中文语境谦逊；④ 反馈依照本课程/教材所教材料；⑤ 若列具体回应方式，保留 **sometimes** 的有时/举例范围。 | 41–53、56–80、81–95；`[985,1252)`、`[1312,1872)`、`[1873,2199)` | 不能把课堂文化举例改成所有中国人/美国人的普遍规则；sometimes 不变“经常/总是”。“我总爱用这个例子”（54–55 行）修饰教师举例习惯，不提高学生回应频率。教材/课程依据不能只剩笼统“文化适应”。 |
| long1 | ① 计算机进行计算；② 记住/存储结果；③ 程序员必须明确告诉它做哪些运算，属于讲者的计算入门说明。 | 275–292、319–336；`[6352,6768)`、`[7357,7757)` | 只说“服从指令”缺计算与存储；只列硬件性能缺明确指令要求。 |
| long2 | ① declarative knowledge 陈述事实；② imperative knowledge 是方法/步骤序列；③ 算法有步骤；④ 控制流含决定/重复；⑤ **停止条件/停止方式**。 | 340–344、373–382、554–588；`[7807,7926)`、`[8533,8745)`、`[12376,13212)` | “算法是一系列步骤”不能补足控制流、stopping；有迭代却没终止仍 partial。具体容差是 long7 可选精度，不取代这里必需的停止概念。 |
| long3 | ① stored-program 计算机存储指令序列；② 可改变该序列、执行不同任务；③ 执行指令；④ 测试/控制流可继续、跳过或重复指令。 | 628–642、735–754；`[14183,14570)`、`[16692,17206)` | 只列存储程序或 CPU/ALU 不足；不能把执行写成始终线性、不能分支或重复。 |
| long4 | ① 表达式/程序有语法（syntax）；② 静态语义（static semantics）；③ 实际意义可能不同于程序员意图；④ 计算机照所写指令执行；⑤ 后果包括**非预期结果、崩溃、不停止**三类。 | 854–889、920–943、991–1022；`[19546,20426)`、`[21085,21654)`、`[22671,23401)` | “语法正确不保证结果正确”缺静态语义或崩溃/不停仍 partial；不能用泛泛“调试错误”代替三类后果。原文语法口误/自我纠正不变成新语言规范。 |
| long5 | ① Python 操作有类型的数据对象；② 标量不可进一步拆分；③ 非标量有内部结构；④ **对象类型限制/决定可用操作**；⑤ 对象与运算符组成表达式，表达式求值产生值。 | 1054–1066、1090–1114、1229–1241；`[24153,24467)`、`[24960,25552)`、`[28151,28442)` | 只列 int/float/bool、标量/非标量或“表达式有值”不能补足 ops 限制；“数据有类型”不等于明确类型对操作的约束。 |
| long6 | ① 赋值把**名称绑定到值**；② 重新绑定 **radius**；③ **已经计算过的 area 不会因此自动重算**；④ 未给重算指令是原因，重新执行面积计算才会更新；⑤ 这是本讲尾部示例，随后预告**下讲**控制流。 | 1307–1336、1460–1472、1493–1515；`[29977,30664)`、`[33537,33849)`、`[34295,34883)` | 只说变量更新或只出现 radius/area 关键词不能 full；不能泛化成所有依赖对象永不更新。下讲控制流不要误写成该尾部已演示控制流。2.2→3.2 数字是 long11 可选，但 area 未重算是这里 essential。 |

### 姓名与讲者归属专项

- [ ] `en-medium.txt` 第 1 行为 `HAOHSIANG LIAO`，manifest 署名为 `Dr. Haohsiang Liao`；长篇第 13、31–35 行支持 `Ana Bell` 的讲者身份。核对输出姓名与本来源一致，不混入 Eric Grimson 等其他讲者。
- [ ] 如输出出现中文汉字姓名，逐项记录确切汉字及本地证据位置；仅有罗马字音译不唯一支持某组汉字。不联网补姓名，也不根据常识认定旧轮中文姓名正确。
- [ ] 姓名缺省但“讲者/教师认为”仍清楚的，不额外扣 essential；出现无依据汉字或无依据职称时记 precision/attribution finding。署名资料仅支持身份，不替代字幕中具体观点的证据。
- [ ] `en1` 信念与 `en4` 文化示例分别核对 summary 和独立 key point 的归属、频率及适用范围；具名在 quote 中仅证明名称出现，不证明该句归属或蕴含。

## long7–long11：detail_if_present 精度清单

**以下 5 项不是新增 essential，不计入 14 的分母；全未写也不造成 coverage failure。** 仅核对实际写出的细节，不能要求一旦提及某个细节就把整段可选内容全部补齐。写错的可选事实仍计入 precision 问题；它不能靠“可选”豁免。

| ID | 若出现，核对内容与边界 | 原文依据 |
| --- | --- | --- |
| long7 | 平方根示例 `x=16`、初猜 `g=3`；新猜测为 `g` 与 `x/g` 的平均；重复至 `g*g` 足够接近 `x` 才停。`.01` / `.001` 是可选容差，不能声称固定必选 `.001`。 | 507–547、578–584；`[11305,12247)`、`[12963,13115)` |
| long8 | float 转 int 是截断而非四舍五入；`float(3)` 为 `3.0`。不要把“截断”改为向最近整数取整或擅加无来源规则。 | 1149–1167；`[26299,26774)` |
| long9 | Boolean 的两个值是 `True` / `False`；`NoneType` 只有 `None`。若转述原文教学简化，保留讲义范围，不以独立 Python 完备规范宣传。 | 1122–1134；`[25734,25991)` |
| long10 | 在讲者的 **int/float 算术**范围内，前三种 **`+`、`-`、`*`**：两整数得 int，至少一 float 得 float；**`/` 是单独例外，结果为 float**。不能把前三运算的规则推广到所有算术、所有类型，也不能用 `//` 替代 `/`。若只说“整数运算仍为整数”而未排除除法，记录范围风险；不能靠另句提 `/` 自动消除前句无界断言。 | 1242–1265；`[28443,29035)` |
| long11 | 尾部 `radius` 由 `2.2` 经 `radius=radius+1` 到 `3.2`；已计算的 `area` 不变，需显式重算。避免把半径改变和面积不变拆成互不关联的同义复述；注意前面示例 `pi=3.14159` 与尾部 `pi=3.14` 的局部范围。 | 1437–1442、1460–1472、1493–1507；`[33047,33180)`、`[33537,33849)`、`[34295,34677)` |

## 所有最终 claim 的 precision 与证据检查

- [ ] 通读 summary 与所有非空 point，包含 14 essential 之外的新增 claim；逐项记录支持、过强、矛盾或无法支持。保留原始 claim，不能在审核时悄悄替输出补限定词。
- [ ] 数字、单位、频率、否定、条件、例子、课程/讲者范围准确；不发明评分权重、日期、成绩、自动化或实施成果。长篇抽奖范围有 266 / 271 / 272 的自我变更，不伪装成唯一已定范围。
- [ ] 校验本轮最终文件身份与 provenance、source/hash、阶段完成状态；检查 extract/compose/audit 属于同一次新 profile。候选 1600 与 final 800 是不同阶段上限，不把候选充当最终，不改历史合同解释旧失败。
- [ ] 如查看 fact/trace，包括 audit 新增或修复事实，quote、source span、qualifier、归属均需与同一清理后原文核对；白空格规范化或合法位置只证明可追溯，不能证明 claim 被 quote 蕴含。
- [ ] `source_id`、已知 fact ID、真实源 hash、schema 合法、HTTP 200、model `checks/flags=true` 均不证明 full、precision 或组织合格；audit 的自评不能替代独立复核。
- [ ] 原文存在指代幻灯片、口误和教学简化；无法从允许材料判定时标明证据限制，不联网补充，不运行示例或新增实验来为讲者纠错。评的是忠于来源，不能宣称来源所有技术说法独立验证正确。

## organization：按主题合并与因果结构验收

组织是独立维度。冻结限制为最终 1–7 个有效点、每点上限 240 字符；compose 固定 7 槽允许空槽，不要求硬凑 7 个非空点。长度、点数与槽位是合同/测量指标，**不是组织评分本身**。候选更短不自动判改善，每点低于 240 也可能混装失败。

- [ ] 为每个非空 point 标注主题、命题、条件与后果，并给出支持的 essential ID；先判断是否为连贯语义单元。
- [ ] 同主题可合并的内容是否保持了限定/因果，是否把同义句拆成多个点占位；不同事实可在同主题内合理合并，但不是看到共有关键词就合并。
- [ ] 短篇：备课—课堂任务一致的同义表述不另占两点；安排、课堂用语约束与英文求助路径仍需清楚。旧短篇 P1/P2 重叠但有额外后果，不能简单算精确重复；判断是否可合并而不丢事实。
- [ ] 中篇：daily grading 的理由、反馈内容、成绩/私密账号的传递机制有不同事实，不一律算重复；称赞谦逊、课程/教材依据与改进反馈宜形成连贯主题，不能拆成多个同义文化点。旧 P3–P5 的碎片化只作待改善参照。
- [ ] 长篇：计算/存储与显式指令、算法构成、stored-program/control flow、语法/静态语义/意图后果、对象类型/可用操作、赋值/重绑定例子应有可理解的主题归属，不规定唯一正确点序。
- [ ] long1、long4、long6 共有“计算机执行明确指令”主题，但各自的能力、错误后果和不自动重算是不同事实；保留不同后果不算重复。重复泛泛“计算机只做被告知的事”、无新条件或后果才算重复。
- [ ] long6 与 long11 的数值示例支持同一赋值/重绑定主题，可在一个概念点内表达；不能为了合并删 essential area 后果，也不要求可选数字全部出现。
- [ ] 检查最后一点是否把互不相关的类型、运算、赋值、半径面积、错误后果等装成大杂烩；指出具体主题跳跃，而不是只报末点字数。尾部 area 例子必须与重绑定原因衔接。
- [ ] 每样本记录 `organization` 的 `pass / partial / fail / not_evaluated` 和具体 point 证据：pass 表示主题连贯、无无意义重复/碎片/混装；partial 表示可读但仍有可合并碎片或重叠；fail 表示明显混装、重复占位或组织使关键关系难以理解。此为定性报告标签，不增设 rubric 数值权重。
- [ ] 逐样本比较新旧**最终**结果；长篇旧轮没有最终结果，不声称相对旧长篇最终组织改善。可另引用冻结 baseline 的 365 字末点作历史测量，但不把字符减少直接当组织成功。

## 主 agent 通知后：只读复核与返回流程

1. [ ] 接收主 agent 给出的本轮 phase/profile、最终结果路径、阶段 trace/provenance/index、失败情况与预算证据；确认是新的 `organization-refined`，不是 2026-10-05 的旧 `refined` 或旧 `organization-slots`。
2. [ ] 只读核对本轮 rubric 与上述冻结版本、三源身份、结果 hash、完整 audit/final；若材料未齐，报告缺失材料与 `not_evaluated`，不重跑请求、不补造结果。
3. [ ] 独立通读本轮 summary/key_points，按 14 行表逐子句写出结论；不把 producer 自评或旧 review 状态复制成本轮结论。
4. [ ] 单独核对 long7–long11 的已出现细节、姓名、频率、观点、范围；覆盖完整仍可有其他 precision findings，不把 full 等同“全部输出无误”。
5. [ ] 按主题检查重复、碎片化和末点混装，给出 point 定位及理由；报告结构限制测量与语义组织结论的差别。
6. [ ] 返回逐样本及合计 full / partial / missing / not_evaluated，precision 与 organization。记录旧短中 5/3、新短中评分及新长 6 项评分的边界，避免串轮。
7. [ ] 若主 agent 明确通知授权落盘，只新建本目录 `results/organization-refined-semantic-review.json`，含 phase、review method、冻结 rubric/manifest/source/result 指纹、14 项子句证据、可选精度发现、逐样本/合计及组织理由、未评项和方法限制。所有未来分数留待真实结果，不预填成功；不修改本准备清单或任何旧记录。
8. [ ] 落盘后只读核查 JSON 可解析、14 项 ID 无增减、已评/未评数量一致、证据定位真实，并返回文件链接。没有落盘授权时直接返回只读 review 报告，不新建 JSON。

## 来源署名、许可与方法限制

本清单对源事实、例子和冻结标准的展开属于来源衍生评测内容，依 **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)** 提供；保留署名、来源、非商业及相同方式共享要求。这里只引用既有本地许可记录与链接，不声称重新核验当前网页或法律条款。原始 caption URL、采集信息与许可证据见本地 manifest / LICENSE / license-evidence.json。

| 样本 | 原作者 / 机构与标题 | 原始页面（署名链接，未在本轮访问） |
| --- | --- | --- |
| zh-short | Dr. Haohsiang Liao / Massachusetts Institute of Technology, MIT OpenCourseWare；Creating an Immersive Classroom Environment (Chinese) | [MIT OCW 中文沉浸课堂资源](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/mit21g_101f14_immersive_environment_chinese-2/) |
| en-medium | Dr. Haohsiang Liao / Massachusetts Institute of Technology, MIT OpenCourseWare；Daily Grading System | [MIT OCW Daily Grading System](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/daily-grading-system/) |
| en-long | Dr. Ana Bell / Massachusetts Institute of Technology, MIT OpenCourseWare；Lecture 1: What is Computation? | [MIT OCW Lecture 1](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-1-what-is-computation/) |

改动说明：本清单在冻结 rubric 的 14 项复合事实及 5 项可选细节上，以中文展开审核子句、来源范围、定位与判定方法；未修改原文、manifest、冻结标准或旧模型输出。源清洗只删除 VTT 格式/时间戳/标签等以及相邻完全重复行，未补词、改词、拼接、翻译或人为拉长语料。

用途仅为非商业本地推理质量评测；不训练、微调模型，不作为产品提示的答案库。许可范围针对源字幕、摘录、事实及衍生评测，不将产品代码/脚本重新许可，也不表示 MIT 认可本软件或模型输出。

方法限制：仅三份官方自然字幕、两门 MIT 课程；一个候选的一次真实运行不能推断稳定性或总体准确率。本 review 是 agent 独立语义复核，不是外部独立人类评审、穷尽事实真值验证、技术规范认证或统计保证。准备阶段读过旧模型评审，不能宣称审核员对历史输出完全盲评；标准采用输出前冻结的 rubric，新轮评分需有新的最终文字证据。
