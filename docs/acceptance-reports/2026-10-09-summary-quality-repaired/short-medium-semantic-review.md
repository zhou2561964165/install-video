# quality-repaired 短、中篇独立语义验收（2026-10-09）

本报告只读验收已保存的 public final；唯一新增文件为本报告。未调用模型、未访问网络、未运行 phase、未修改产品、原文、raw response、trace、freeze、账本、环境或数据库；本审查新增 POST 为 0，新增模型费用为 0。正在协作的其他 Agent 的修改不归本报告所有。

## 实际判定

| 样本 | 原 compound essential 逐子句覆盖 | 全句来源精确性、条件与归属 | 原 rubric 组织/重复 | 结论 |
| --- | --- | --- | --- | --- |
| zh-short | zh1–zh4 均 full；4 full / 0 partial / 0 missing | 通过；未发现源外人名、错数字或反转条件 | 不通过：P2 重复 P3/P4 的父概览，无新增实质条件或后果 | 内容合格，但组织尚未完全达标 |
| en-medium | en1–en4 均 full；4 full / 0 partial / 0 missing | 通过；通常、讲者信念、文化例子、L1/教材范围均保留 | 按冻结原 rubric 通过；仍存在可整合的同主题分散，不能把新增条件/后果误判为重复 | 原语义及组织 rubric 合格，主题融合仍可改善 |

这是独立 Agent 阅读判定，不是外部人工评分或统计稳定性结论。未因 `checks=true`、fact ID 已覆盖、primary owner 唯一或点数不超过 7 判定语义/组织通过。中篇没有仅因文化点共享主题而被加码判失败：冻结 rubric 明确允许同主题的不同相关条件/后果。

## 依据与索引

标准为本目录 `rubric.json` 的原 14 compound essential、precision、organization，短中取其中原 8 项；原始策划与内容来自 `../2026-10-04-natural-subtitle-quality/corpus/manifest.json`、`zh-short.txt`、`en-medium.txt`。行号为上述 cleaned TXT 的 1-based 行号，不是 VTT 时间码。

S1 是 public final 唯一 summary 段；为精确定位，按该段中文句号依次标作 S1.a、S1.b 等。P1…Pk 是 public `key_points` 的 1-based 数组索引，与 raw audit `point_1`…一致。分号内所有必要子句也逐一核查。

| 文件 | SHA-256（验收前读取） |
| --- | --- |
| corpus/zh-short.txt | `4e62d9c0f1d25734be1af8dfa7f1328c5f1982590734ca8453b0c2f926e0ae9b` |
| corpus/en-medium.txt | `4b1b09addb5ad3cab6dc885fb4f0a805fede65b2eecc8976b232e180a427edb9` |
| results/quality-repaired-zh-short.json | `164b6d559b5fd7807cafd927d7b1f17fd2b6671beff139568a9caf309d4841b0` |
| results/quality-repaired-en-medium.json | `3e7cf46bcc9c87ce017c6598b21182aef2c26e1656bed8e56461180bc3796ea2` |
| results/quality-repaired-zh-short-trace.json | `a16c9a4ddaac915ce3a0072ed0817fc65f511b08131a7a09fdfcb682a6902a36` |
| results/quality-repaired-en-medium-trace.json | `802110c9d30f621cdbc7c57b97245894c6173b61f4251b62584ed26cceea8117` |

源文件 hash 与原 manifest/rubric 一致；public final hash 与本 phase index 一致，trace hash 与 public final 的 trace_sha256 一致。

## 原 8 项逐必要子句核对

| 原 ID | 必要子句及实际输出位置 | 原 source 行 span 与依据 | 判定 |
| --- | --- | --- | --- |
| zh1 | MIT 中文课（S1.a/P1）；第二天起全中文（S1.a/P1）；第一天说明准备、大纲、期望（S1.a/P1） | L1–4：`从第二天开始`；`第一天…怎么样准备…大纲…期望` | 每一子句 full；整项 full |
| zh2 | 两个关键环节（S1.b/P2）；学生听懂课堂用语（S1.b/c、P2/P3）；固定用语约束（S1.c/P3）；课前准备与每日课堂练习任务一致（S1.b/d、P2/P4）；练未准备内容会转用英文的条件/后果（S1.d/P4） | L5–9：两个环节及用语理解；L9–13：weekly schedule、课堂练习、未准备就跑出英文、每日任务一致；L14–16：用语不可随意改变 | 每一子句 full；整项 full |
| zh3 | 课堂用语不得随意变换（S1.c/P3 的“不能出圈”及例子）；“请你再说一遍”与“请你再说一次”不同（S1.c/P3）；老师应注意（S1.c/P3） | L14–16 原话逐项对应。输出保持在本 MIT 中文课堂教学情境内，没有将区别另释为通用词义规则 | full。“初学者”不是源 L14–16 明写字样，不能要求模型新增该标签；课堂用语学习情境与限制实际保留 |
| zh4 | 前 45 分钟中文（S1.e/P5）；学生真的不懂、需英文问的触发条件（S1.e/P5）；最后 5 分钟、下课后、邮件三个渠道（S1.e/P5）；保持课堂中文气氛的目的（S1.e/P5） | L17–19：不懂需英文问、最后五分钟/前四十五分钟；L20：下课/电子邮件；L21：维持中文气氛 | 每一子句 full；整项 full |
| en1 | 采用日常评分（S1.a/P1）；每次表现即每节课评价（S1.a/P1）；坚持且持续努力修读该课程（S1.a/P1）；能展现很好的中文技能是讲者“相信”，不是普遍保证（S1.a/P1） | L7–9：each performance/each class；L10–17：we are convinced、persistent and consistent efforts、good skills；L18–20：adopt daily grading | 每一子句 full；整项 full |
| en2 | 通常课后（S1.b/P2）；针对每位学生课堂表现（S1.b/P2）；语言及文化行为两类内容（S1.b/P2）；让学生知道后续课次改进事项（S1.b/P2）；通常书面（S1.c/P3） | L21–28：usually、each student's performance、language/cultural behavior、next sessions；L29：usually written feedback | 每一子句 full；整项 full；没有把 usually 改成每节课必定 |
| en3 | 网站名 Engrade（S1.c/P3）；录入成绩（P3，S1.c 未列但整项不要求 summary 独立穷尽）；私下给每位学生留言（S1.c/P3）；通过自己的账户读取教师评论（S1.c/P3） | L30–34：Engrade、besides entering grades、privately；L35–40：their account、comments from instructor | 每一子句 full；整项 full；未宣传它是 2026 年已核实的新推荐 |
| en4 | 评论依学生表现（S1.d/P4）；发音或更深入的中文赞美回应（S1.d/P4）；讲者的美国谢谢/中国谦逊对比（P5）；L1 导致的课堂表现时鼓励并反馈（P6）；依课堂所涵盖教材内容（P6）；学生知道可努力改进的方向（P6） | L41–53：performance、pronunciations、compliments；L56–64：美国谢谢；L65–80：中国谦逊与 sometimes 例子；L81–95：if L1、encourage/feedback、textbook/course materials、work on | 每一子句 full；整项 full。S1.d 没独自包括对比/教材，P5/P6 完整补足，符合跨 summary/key_points 原标准 |

## 全输出句的精确性复核

以下覆盖两个 summary 的每一句及所有 key point 的全部陈述。每格“通过”是将文字与原文独立比较的结果，不采用模型 assertions 代替判定。

| 输出位置 | 源行 span | 全句检查 |
| --- | --- | --- |
| zh S1.a；P1 | L1–4 | MIT、第二天、第一天准备/大纲/期望准确；没有提前为第一天全中文。通过 |
| zh S1.b；P2 | L5–9，并结合 L13 | 两环节是理解用语和备课对应练习；“最重要”来自讲者原话。通过 |
| zh S1.c；P3 | L6–8、L14–16 | 三个用语例子、不可“出圈”、“一遍/一次”、老师注意均有原话；未鼓励随意改说法。通过 |
| zh S1.d；P4 | L9–13 | weekly schedule 名称保持；“会收到”是原“课前…会有”的自然概括；每日准备与练习一致、未准备转英文的条件及后果都在。通过 |
| zh S1.e；P5 | L17–21 | 真实问题/不懂/需英文问、前45/末5、课后/邮件、维持中文气氛均准确；“可”没有变成必须或永远禁止。通过 |
| en S1.a；P1 | L1–20 | 与人互动留下印象受评价是讲者论据；两个采用理由、每节评价、持续努力的课程内条件及“相信”归属均保留。通过 |
| en S1.b；P2 | L21–28 | 通常、课后、每个学生表现、语言与文化、改善后续课次均一致；中文“下节课”概括 next sessions，没有改成固定考核时间或结果保证。通过 |
| en S1.c；P3 | L29–40 | 通常书面、Engrade、私下、个人账号、教师评论均准确；P3 另明确“除录入成绩外”保证 en3 完整。没有自动评分、公开评论或额外权重。通过 |
| en S1.d；P4 | L41–53 | 随表现而定，可能简单至发音提醒，也可能深入至赞美回应；“可”与原 can 一致。通过 |
| en P5 分号前/后全部子句 | L54–80 | “讲者以…为例”统摄整段中美对比；美方自然谢谢，中方谦逊、不以谢谢接受、两种有时的回应、谦逊观点均与原一致。“有时”没有扩大成经常/所有人。通过 |
| en P6 条件/动作/依据/目的 | L81–95 | “若…L1”条件没有删除；鼓励及反馈的动作、赞美情境、课堂涵盖的教材、可努力方向均保留。“母语（L1）”是原术语释义，没有引入其他人物或课堂成绩指标。通过 |

当前短篇没有任何讲者中文姓名；中篇仅在 S1.a 使用源 L1 明写的 `HAOHSIANG LIAO`，其余用“讲者”。因此旧问题所指的源外中文姓名在这两份当前 final 中已消失，且未发现新中文/英文别名。`MIT`、`weekly schedule`、`Engrade`、`L1` 均能直接回到各自源文字，不来自无关 metadata 的猜测。

文化判断只承认本视频讲者/课程的教学例子忠实性，不将其认定为所有中国人或美国人的规则。P5 前缀“讲者以…为例”保留陈述归属，P6 明确教材及课程材料范围。日常努力的学习预期在 S1.a/P1 由“讲者…相信”约束，不能读成评审替其保证学成。

## 组织判定：实质命题，而非 ID/长度

zh P1（课程安排）、P3（固定/可理解用语与变式例子）、P4（备课任务一致的机制与未准备后果）、P5（英文问题分流）各有独立内容，末点没有无关内容拼箱。P2 只是将 P3 的“听懂课堂用语”和 P4 的“准备反映练习”再列一次。P3/P4 相比 P2 加入条件、例子、后果，不能把 P3/P4 自身判成无用；但 P2 相比这些点没有新增实质限定。“两个”只是父级计数，不是第三个教学原则。因此父概览应由 S1.b 承担，P2 不需再次占 key point；当前存在冗余，按原 duplicate criterion 组织不通过。删除/合并父概览若实施，必须保留 P3/P4 原有用语限制及未备课后果；本次没有实施。

en P1/P2/P3 分别有评分理由、反馈内容目的、书面私密交付细节，原 `en-feedback` rubric 明确这些不同细节不能一概算重复。P4 加入“取决于表现”与发音/文化反馈层级，P5 给完整中美赞美对比，P6 给 L1 触发条件、鼓励、教材依据与改进目的。因此三个点共享“文化反馈”母主题，但不只是反复说“保持谦逊”：P5 是文化例子，P6 有新的课程实践条件与后果，符合原 rubric “distinct implications sharing a theme are not” 的豁免。中美两侧已经合在 P5，且比较没有损坏。

从本轮 compose/audit prompt 的“principle and examples 合并、一主题一实践”目标看，en P4–P6 仍可融为更连贯的反馈主题；这是独立的可读性/主题融合改进项，不能改写成原 rubric 的“无新增命题重复”失败。若后续融合，应同时保留依学生表现、发音或文化反馈、讲者中美对比、有时、L1、教材及改进目的。不得用点数目标或仅保留一侧文化例子压缩它们。

机械边界实测：zh summary 332 字符，5 点分别 47/53/80/86/81；en summary 208 字符，6 点分别 81/51/66/49/72/75。两者都在本轮 800/240/1–7 边界内，这只证明容量，不改变上述组织判定，也不提出人为固定点数。

## raw/trace 核验及实际验证

已读 `results/responses/03.json`（zh audit）和 `06.json`（en audit）正文，以及各 trace 最后事件的 source、stage、audit.output 必要字段。raw audit summary 与对应 public summary 精确字符串相等；全部 raw `point_k.text` 与 public `key_points` 对应一致；trace audit.output 的 summary/points 同样匹配。未将模型四个 true assertions 视为语义证据。

对应 trace 完成事件均记录 extract/compose/audit 各 1 次，`paid_calls=3`、`retry_budget.used=0`。本文仅报告已保存 trace，不另审计整个工作组账本，也不把这 6 次既有调用计成本审查新增费用。本审查新增调用为 0。

实际执行了原文逐行阅读、原 8 项逐子句矩阵、全部输出句对照、raw/trace/public 字符串一致性与 SHA-256 核查。本审查未运行产品测试，报告不声明产品构建/自动测试已通过。写入后再次核对源、public 和 trace 的上述六个 byte hash，内容保持。

## 署名、许可与范围

两份原素材及本文相关摘录/派生审查来自 Dr. Haohsiang Liao / Massachusetts Institute of Technology, MIT OpenCourseWare。

- 短篇：[Creating an Immersive Classroom Environment (Chinese)](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/mit21g_101f14_immersive_environment_chinese-2/)。原 caption：[MIT21G_101F14_Immersive_Environment_Chinese.vtt](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/50e5414eeb1e526bbb94593453e9c84a_MIT21G_101F14_Immersive_Environment_Chinese.vtt)。
- 中篇：[Daily Grading System](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/daily-grading-system/)。原 caption：[hNUoYTJl3j4.vtt](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/e9d389e4d81e5391b948a1981fc7ef4c_hNUoYTJl3j4.vtt)。

原文、相关摘录、派生总结与本审查按 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 署名、非商业及相同方式共享。变化是加入独立语义定位、评审表和组织判断；未修改原字幕。MIT 不为该软件或模型输出背书。产品与脚本不因本报告重新许可。上述链接来自已冻结素材，本审查未联网。

## 工程约定（本次读取的 AGENTS.md 原文）

### 1. UI 设计必须用 skill

涉及 UI/视觉/交互（配色、字体、动效、无障碍、组件）时，先调用：
- `ui-ux-pro-max`（设计决策检索：`--design-system` / `--domain color|typography|ux` / `--stack`）
- `design-system`（三层 token：primitive→semantic→component）

### 2. skill 优先于计划

计划文档与 skill 指引冲突时，**以 skill 为准**。
例：ui-ux-pro-max「每屏最多动 1–2 个关键元素」> 计划里的常驻动画清单。

### 3. 代码不写死、保留扩展、避免大规模重构

- 颜色/字体/时长一律走 `:root` token，不散落硬编码。
- 新增能力数据驱动、可配置，不做写死导致后续要推倒重来的实现。

### 4. 解耦（单向依赖，改动隔离）

- 核心模块对外只暴露窄接口：后端 `ytdlp_service.py` 是唯一接触 yt-dlp 的层；前端视觉表现层只读 `scene` 状态，绝不修改下载状态、绝不 import 下载核心。
- 层与层、模块与模块通过稳定接口通信，禁止绕过接口直接依赖内部实现。
- 新增能力走接口隔离，扩展不触碰既有核心。

以上约定需写进所有文档（含现有文档），并每次照做。

### 5. 开发期账号与模型验收授权（用户2026-10-08更新）

- 开发期沿用现有账号，允许给指定账号配置不限下载额度，不为绕过额度新建账号；其他账号额度和使用统计保持。
- 开发、模型验收及必要的有限扩预算已获持续授权，不再逐轮询问许可。每轮开始前记录明确上限、原因和台账；禁止无上限扩预算。
- 本次总结质量工作先13模型POST，最多因已定位且离线验证的修复追加一轮13，总硬上限26。包含所有阶段及失败尝试；达到上限后停止真实调用。
- 每个phase仍独立冻结和台账、单caller串行、发前持久预占、错误即停；修复后另建phase，旧失败原件/预算不覆盖、不借用、不自动重试或隐藏付费回退。
- 本条优先于旧文档里的“等待新的授权”。账号不限下载额度不表示模型调用/服务器资源无限；用户后续可撤销或修改授权。

### 6. 规范化与分类重试整改（用户后续指令优先）

- 模型raw summary必须先经独立规范化层，再进入内部结构/最终语义校验；引用由程序结合已验证事实与主题关联提供，不完全依赖模型生成。
- 规范化保留所有非空内容/原ID提示，不裁字删点、不盲挂全部引用。关联ID不是语义证明，未决候选交核查，最终来源/核心事实/检查/长度边界仍必须满足。
- 格式错优先本地零POST修复；确需模型格式修复与语义修订分别计数，默认每次总结最多1次format、1次semantic且总附加最多2，可配置关闭。网络/provider/来源安全/容量/配置错误不重试，不盲重跑整个pipeline。
- 所有attempt计入真实调用预算与trace，正常n+2/默认最坏n+4；禁止隐藏付费fallback和无限扩预算。本条覆盖旧phase“任何错误无重试”，旧失败原件与账本不改。
- 本次新整改正常三源13POST、含最多6附加调用最大19，工作组总硬上限26；真实验收须先代码/离线/审查/包含新模块的freeze验证，单caller执行，无需重复问许可。
