# Phase 12：15点完整来源诊断

2026-10-15独立审阅：**整体FAIL；核心5 full / 1 partial / 0 missing；precision FAIL；overview PASS；organization PASS。** 提高要点容量没有达到原覆盖及精度验收要求。

工程约定：成熟组件与窄接口、单向依赖；yt-dlp唯一服务层、视觉只读scene。UI工作遵循ui-ux-pro-max/design-system及三层token。保护账号/env、本地模型、UI及所有封账原件。此内容审阅只读，无新增POST、服务、测试或文件替换；原始输出保留。

## 证据与范围

对象为本报告目录 `results/phase-12/en-long.json` 及 `response-01.json`。来源为本phase `snapshots/0026.bin`，Dr. Ana Bell / Massachusetts Institute of Technology / MIT OpenCourseWare，Lecture 1: What is Computation?，沿冻结manifest保留CC BY-NC-SA 4.0署名许可。

- source SHA：`c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7`
- provenance SHA：`0656638e99b8a64ba7c834e7f92c30bba82c83ae360c8b2d000f427e27babb5c`
- response SHA：`38cabd188295b10ab87c33bb89d518e2fd2bfff93ed9a4dec5d7d0b370019a6b`
- product SHA：`c7a7c173e09a855f9b92cd4994bbb271eeda11f59465fc95a2efec1757e51f97`

配置为同一完整来源direct `merge=False`、Pro/Responses schema、reasoning none、8192输出上限，仅将phase11的14点预算改为15点。真实usage为input9989/output995/total10984，cached0。raw与产品summary、15点逐字符串一致；这只证明传递完整。以下P为要点序号，L为冻结字幕行号。依据原 `review-criteria.md`，不使用Lecture2未见来源的主题标准。

## 六项核心

| 核心 | 对应内容与来源 | 评分 |
| --- | --- | --- |
| long1 | P2计算/存储、P3明确指令；L275–292、319–336 | full |
| long2 | P3事实/配方、P4平方根迭代、P5步骤/控制流/停止；L340–344、373–382、507–588 | full |
| long3 | P6可改变并执行指令、P8/P9测试与跳过/重复；L628–642、700–754 | full |
| long4 | P11/P12语法、静态语义、意图不同及输出不符/崩溃/不停止；L854–943、991–1022。错误示例另扣精度 | full |
| long5 | P13明确类型决定可用操作、标量与非标量；P15求值为值；L1054–1066、1090–1114、1229–1241 | full |
| long6 | P15赋值与具体radius/area未自动重算；缺L1504–1507显式重执行area的正条件及L1511–1515下一讲控制流 | partial |

## 两处明确精度错误

**P11混淆语法与静态语义。** 产品把 `word + 5` 列为“语法上无效”。L848–851的语法错误例是word紧接数字5，没有加号；L877–885另说词与数字相加有合法语法但缺静态意义。产品自行加上符号并合并两例，倒置分类。P12后面的正确意义说明不能消除P11错误。

**P15扩张算术规则的子集。** 产品写“加减乘除中，若两个操作数都是整数则结果为整数”，随后又说除法总是浮点。原L1244–1265明确只对前三种，即加减乘，给出双int结果int/含float结果float；除法单独例外。错误前件把除法也纳入，后句正确不能抵消冲突。phase11曾明确“加减乘”，本次回退。

P15恢复具体radius/area主语，没有phase11“重绑必使旧值失去引用且无法取回”的泛化断言；仍漏显式重执行area条件和下一讲。数值2.2→3.2为可选例子，未写不单独扣分。phase11的静态语义错误捕获条件本次整段省略，不能称已纠正。

## 其余断言与组织

P1三目标/练习及Anaconda课堂尝试建议（L92–175）保持讲师归因与场景；P2估计速度/存储、P3计算指令与知识类型、P4平方根公式/迭代、P5算法组成有源。P6四则计算器作为例子，不把能力限制挂到整个固定程序类别。P7–9架构与控制流分别对应L648–754；P10图灵叙述保留可计算前提与理论模态（L755–789）。P12语义和错误后果、P13类型机制、P14标量值及截断转换有源。P15求值、余数/幂和赋值机制正确，但包含上述算术范围错误。未发现额外明确的时间、数量、人物或安全范围错误。

Overview PASS：摘要提供教学路线，未重复详细运算/数值清单。Organization PASS：顺序清楚，架构/控制流/原语各有新增信息，类型机制与具体类型/转换也互补。P15内容偏集中但概念相连，不以字数或点数直接判失败；可读性仍有压缩空间。

## 与phase11比较

long5由partial变full；long6仍partial但radius/area更具体。新增word+5分类错误，并回退到算术子集范围错误。print可选说明被省略。抽奖时间与评价模态本次没有对应断言，不算纠正旧错误。单次14→15对照只能描述这一实际输出差异，不能将改善或回归归因为点数的必然效果。

本结果未通过，不升级默认、不恢复公开长文；未证明默认Flash分段、未见Lecture2或短中回归。独立Agent审阅非外部人工标注或统计稳定性验证，MIT不背书模型输出。
