# Phase 2 长文 raw 只读诊断

日期：2026-10-10。执行者：`/root/staged_phase2_long_diagnostic`，sol_specialist。按 systematic-debugging 先追踪已保存输入、raw 和错误边界；using-superpowers 的 subagent-stop 适用。本任务只新增本文，没有修改产品、source、rubric、payload、response、freeze、ledger、tracker 或旧报告；没有模型请求、联网、测试、服务启动、env/账号/数据库/Git 操作。

工程约定：最新用户/AGENTS 与适用 skill 优先；UI 如涉及须先 ui-ux-pro-max/design-system，primitive→semantic→component token；能力配置化、成熟方案复用、窄接口、单向依赖，yt-dlp 唯一服务层，视觉只读 scene，避免无关重构。共享目录中其他 Agent 的修改不覆盖。本诊断不拥有 supplier 调用权限；父 Agent 记录的同工作组累计 11/12，不因诊断新增额度、不重开 closed phase，后续真实调用由 root 单 caller 持久预占并记录有限新预算。

## 结论及适用边界

`response-05.json` 和 `response-06.json` 的 **content 完全相同**，都是 20 点；每一点又与 `payload-05.json` 两段 section notes 按原顺序连接的结果完全相同：第一段 11 点，第二段 9 点。供应商此次表现是直接保留段落列表，没有执行全局主题合并或根据全文恢复遗漏。外层响应文件不同，不应称两个文件完全相同。

初次 points 和唯一 points_format 均被 `invalid_count` 拒绝，最终 `en-long.json` 为 `success:false/error_type:llm_invalid_response`。trace 中没有 overview 阶段。因此下面的覆盖与精度判读仅是**未接受 raw 的人工诊断**，不能转记产品成功、已交付结果或整个长文验收通过。

将 theme cap 从 14 改为 20，只能移除本次计数拒绝，不能修复 next-lecture 子句缺失、简单命令安全范围泛化、“前三种”指代不明或重复组织。现有证据不足以把“必须允许 20 个独立主题”作为这份来源的需求。可配置有限自适应 cap 仍合理，但应依据独立主题与必要条件的密度确定，不能按一次违规返回的长度倒推上限。

## 输入、raw 与失败边界

读取 [payload-05](../results/payload-05.json)、[payload-06](../results/payload-06.json)、[response-05](../results/response-05.json)、[response-06](../results/response-06.json)、[trace-en-long](../results/trace-en-long.json) 与 [en-long](../results/en-long.json)。使用 PowerShell 解析本地 JSON 并逐条比较，没有运行验收脚本或调用产品。

| 证据 | 实际观察 |
| --- | --- |
| raw05/raw06 正文 | `content -ceq` 为 True；解析后的 key_points 均 20 |
| raw05 与两段笔记 | 11+9=20，按顺序连接后每条字符串均完全相同，没有 mismatch |
| points 系统指令 | 明确 1–14 个不同主题；全文优先；段落笔记可错；合并相关细节；检查有限点数 |
| format 用户指令 | 明确 14 点、invalid_count，保留全部非空断言/条件/归因/例子；多点时合并，不删文字、不语义重写 |
| provider 输出方式 | `response_format={"type":"json_object"}`，没有本次请求的原生 strict JSON Schema/maxItems 约束 |
| 输出容量 | 请求 max_tokens=8192；两次 completion_tokens 均 1152，finish_reason 均 stop，没有截断证据 |
| 错误类别 | points 和 points_format 都是 format/invalid_count；未进入 overview |

14 点与保留所有必要内容并无逻辑冲突：可以在同主题内组合原断言而不删内容。此次格式修复却原样回显；这证明本轮指令没有有效执行，不能证明所有模型都无法合并。`Repair only the structure` 与 `Do not ... perform a semantic rewrite` 可能使模型偏向保守复制，这是尚未独立验证的机制假设；它不是已经证实的供应商内部原因。原 JSON 已合法，变化目标实为数组层级的主题重组；单纯 JSON mode 无法保证计数或组织效果。

format 的职责边界也使其不能修复原错误断言或恢复 next-lecture：这两者属于依据原文的内容修订，需要不同职责的生成候选；不能把 format 原样重试当作内容修复。

用于确认所读来源/原件的 SHA256：

- 原 `corpus/en-long.txt`：`c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7`，与结果来源 hash 一致。
- response-05 文件：`80f8317f33d4752513639e5feb7e9b584dc6f68784c117f29c0edff339f71a52`。
- response-06 文件：`7fd4bacaa8e2ef03cb71d88fbd356959ea6aa7c8ec220779553d3868b9a29d51`。

这只是本任务所读文件 hash 与本地逐条比较，没有宣称重新完成全套 freeze/ledger 证据核验。

## 原 long1–6：未接受 raw 的必要子句观察

沿用 [本 phase 准则](../review-criteria.md)、[首 phase 准则](../../2026-10-10-source-first-summary-live/review-criteria.md)及[原 rubric](../../2026-10-09-summary-quality-repaired/rubric.json)。原 rubric 的历史 7 点/240 字限额已被后续自适应规定覆盖；全部 essential 子句、来源精度与重复定义继续适用。P1–P20 是 raw 数组索引，不是新答案模板。

| 原项 | raw 覆盖观察 | 原字幕依据与实际保留/遗漏 |
| --- | --- | --- |
| long1 | retained | P2 计算与存储结果；P3 明确告知操作、无心智。对应原字幕 275–292、319–336。|
| long2 | retained | P4 声明性事实/命令性步骤；P5 具体 g*g 检验、足够接近则答 g、否则平均 g 与 x/g 并重复；P6 步骤、决策/重复控制流和停止方式。对应 340–344、373–382、507–588。|
| long3 | retained | P7 可存储/执行/更换指令；P8 真/假测试及跳过/回开头；P9 解释器决定下一条/跳过/重复。对应 628–642、648–754。|
| long4 | retained | P11 语法与静态语义；P12 程序执行写下的内容；P13 非预期结果、崩溃与不停止，以及静态语义错误走到对应分支才捕获。对应 854–943、975–1022。|
| long5 | retained | P15 类型决定可执行操作、标量不可分/非标量有结构；P18 表达式求值得到值。对应 1054–1114、1229–1241。P18 另有精度问题，见下文。|
| long6 | partial | P19 赋值绑定；P20 radius=radius+1，2.2→3.2，已有 area 不变，因为没有要求重算，显式再执行才变。**缺少本例为最终例子及下节课添加控制流的收束预告**。原 essential claim 与 1493–1515 包含此子句；P6/P8/P9 的一般控制流不能替代 next-lecture 事件关系。|

诊断计数为 5 retained、1 partial；无 overview，不能用未来 overview 或旧输出补当前 raw。后六点 P15–P20 携带 long5/long6 的关键内容，绝不可为从20降14直接截掉。long7/8/9/11 为 detail_if_present：平方根数值/容差不必全部出现，已写的更新公式与停止条件正确；float(3)=3.0、截断非四舍五入、True/False、None 与 radius 数值例均在来源中。long10 的运算范围实际不合格，详见 P18。

## 精度与组织

| raw 点/主题 | 判读及原文依据 |
| --- | --- |
| P1 学习建议 | “不必害怕运行代码会弄坏电脑”移除了原 123–136 的 Anaconda/输入简单命令情境。这是从入门课堂练习安全鼓励推广为一般运行代码安全；与本 phase 明确回归项不符。|
| P18 运算类型 | 原 1242–1265 先枚举加、减、乘、除，再限定“前三种”即 +、-、*；raw 只说“乘除等运算”就引用“前三种”，没有可识别的三项。其余“两 int→int、含 float→float”的作用范围因此不明；后句 / 总 float 正确也不能修补前句。需在断言本身恢复具体操作集合，不能靠模型常识推断。|
| P6 停止条件措辞 | 原 570–577 是课程算法的停止需求和“不想”程序一直运行；raw “不能有无休止运行的程序或配方”语气更绝对。核心停止条件已保，但后续候选应保持教学情境，避免扩成所有程序的普遍不可能性。|
| P10/P16 讲座简化 | 图灵六原语、任意语言理论可计算性、float“所有实数”、None“类型缺失”均源自讲座。原 rubric 明确按来源忠实而非现代技术教材独立审校；不因外部常识给新扣分，也不把这些讲座简化宣称为经独立科学证明。|
| P8/P9 架构控制流 | 二者都列原始加减操作、逐条解释与跳过/重复；P8 新增部件、计数器、真/假，P9 新增逻辑/测试/移动数据，但共有流程又被完整复述。该具体重叠可在同主题内组织；不应把20条全看成20个独立中央主题。|
| P3/P12/P13/P20 指令执行 | “只执行写下内容”反复出现；原 rubric 允许 P13 非预期结果和 P20 area 不自动重算这类不同后果共享主干，不能一概算重复。P3 独立抽出泛化主干则增加展开粒度。|
| P19/P20 赋值 | 一般名字绑定、左右侧结构与具体重绑后果不同，P20 新增数值、旧引用与 area 因果，不应裁去或直接判重复。可作为相邻概念及其例子组织。|
| P4/P5/P6、P11/P12/P13、P15/P16 | 分别形成知识→算法例与停止规则、语言含义→错误后果、对象类型→具体取值与转换的同主题链；保留全部必要断言与相关例子时仍有主题聚合空间。这是粒度观察，没有提供固定课程的重写答案或要求一定合成某个点数。|

其余 substantive 断言已对照原字幕相关行：课程目标/练习（63–177）、计算类别与速度/存储（275–318）、知识/平方根（339–590）、固定/存储程序与部件/解释器（596–754）、语言原语与含义（755–943）、错误与 shell/editor（944–1053）、对象/转换/print/表达式（1054–1288）、绑定与重绑（1294–1515）。本报告未发现额外阻碍性的数字或公式篡改；这不等于独立真值保证或所有供应商输出普遍可靠。

## 通用候选建议与待验证问题

1. 保留现有成熟串行编排与 Pydantic 窄接口。在全局 points 生成中把 section notes 定位为辅助证据，让组织职责明确区分“段落笔记的数组”与“全篇独立主题”，要求全文核对条件、指代及收束。只给通用规则，不附本课程答案或预设分组列表。
2. root 可评估当前 provider/模型实际支持的原生 strict schema，并把有限数组上限交给供应商可验证的约束能力。当前请求只有 json_object，原生 maxItems 是否支持、组合条件是否兼容、是否增加调用必须另核实。即使计数合法，来源/精度/遗漏/重复仍独立核查。更适合模型的通用长文组织能力也只是待验证候选，不能靠型号宣传确认。
3. 单纯提高 cap 缺少此次证据支持；若未来来源有更多独立主题，允许在配置的硬上限内按来源规模及信息密度自适应。需同时明确单点容量和完整内容约束，避免把所有内容塞进少量无关长点。不能静默接纳旧 raw 或用新 cap 重评旧 closed phase 成功。
4. count repair 要保留原始全部断言时，明确允许组合同主题字符串并调整组织，避免角色暗示必须逐条复制。内容纠错/补原文必要子句则由具有来源核对职责的生成完成，仍计入有限预算、按独立新 phase/freeze/ledger 执行。不能无上限重试同一提示，也不能本地按样本裁删六点凑数。

成熟方案依据复用 [已有官方资料研究](../../../reference-summary-review-2026-10-10.md)：DeepSeek JSON Output 的作用限于格式，LlamaIndex response synthesizer/树形总结与 LangGraph 固定工作流可提供组织/编排组件，但均不保证语义；当前已采用 LangChain 串行节点，新增框架不是此次段落列表拼接的必要结论。本任务没有重新联网或声称核实当前所有模型 API。

来源与派生诊断保留原归属：Dr. Ana Bell / Massachusetts Institute of Technology, MIT OpenCourseWare，Lecture 1: What is Computation?；原链接与字幕详见 corpus/manifest.json，CC BY-NC-SA 4.0。MIT 未为本软件或模型背书。本诊断结论只适用于本次已保存的回归 raw，不是 holdout 或总体质量评分。
