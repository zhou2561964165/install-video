# 主体范围关系核查候选（Phase 7）

工程约定：复用现有Pydantic v2、PydanticOutputParser、Responses `json_schema`与LCEL固定review→revision路径；保持窄接口/单向依赖，不新增facts ID、候选事实合同或公共接口字段。保护phase1–6及旧67 POST证据原字节，账号/env/模型文件不改。

## phase6实测依据

phase6从closed phase4草稿启动，真实只预占并发送1 POST / 13208供应商tokens，Responses完成状态正常，15个目标字段齐全，没有第二次请求。parser因target_11的引文把原文句首小写`if`改成`If`而停止，其他14条source_quote均匹配原文。其target_4仍判断` supported`，仅引用“它只会四则运算”的谓词句，没有把源句实际主体“this calculator”与草稿的类别主体“fixed-program computers”相比较；P4范围泛化仍未修复。phase6已closed/verified，不重开、不把raw转成成功revision输入。

结构化唯一目标和固定字段解决了phase5的重复target及4096-token截断，但不足以引导模型发现subject-scope错配，且逐字引文校验对首字母大小写差异立即失败。

## 新候选设计

保留动态必需根字段`target_0…target_N`，每个目标对象改为：

- `assessment`: `supported`、`needs_correction`或`uncertain`。
- `scope_relation`: `same`、`draft_broader`、`draft_narrower`或`uncertain`，方向始终表示草稿相对来源。
- `source_subject`、`draft_subject`: 严格字符串或`null`，分别绑定对应的source quote与真实草稿字段；单个字符串最多64字符。
- `source_quote`: 严格字符串或`null`，最多120字符，必须为连续原文摘录；只允许把行分隔空白规范成空格，保留大小写、标点与语言。
- `finding`: 1–80字符，指出该目标最重要的范围错配、遗漏或未决原因。

所有键都必须出现；`null`只用于“主体或证据在有限片段中无法可靠呈现”，不能当成缺字段，也不能由程序补造主体/引用。若某个点有多个事实子句，提示要求先看完全部子句，再用字段记录最重要错配；`source_quote`与两主体必须对应同一个谓词，不能选择另一个正确子句来充数。模型标注`uncertain`或引用/主体为null时，不允许parser把该目标转换为“supported”；原文、草稿、主体、quote、relation和finding原样绑定传给修订。

解析只验证结构、目标位置、来源/草稿子串与连续引用归属，不判断谓词等价、实例是否扩为类别或`scope_relation`是否正确。若先行词离quote上限较远，提示要求读完整上下文，但允许主体/quote置null并标不确定；禁止拼接远处句子、改写quote或由程序猜前件。最终P4是否纠正仍由独立语义审阅判断。

## 有限输出与调用路径

按`128 + 512 × (key_points数量 + 1)`预留核查输出tokens：14点需7808。为保持phase6原`checks`模式的4096预算不变，新增独立硬上限配置`LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS`，默认8192；配置上限不足时，多段完整生成在首个leaf POST前拒绝，保存草稿路径按实际点数预拒。超限不裁字段、不降级到json_object、不自动再问一次。Phase7复用phase4已保存draft，固定1次Responses核查+最多1次Chat修订，总cap=2 POST；第一请求失败即关闭phase。

该预算只设每个核查请求的有限输出上限，不改变用户“不设整项任务总POST/费用预算”的授权。组历史累计9 POST/147600tokens + phase6真实1 POST/13208；旧phase1–6全部closed。Phase7按phase_post_cap=2创建独立ledger/tracker，root单caller、共享锁、发前持久预占。

## 兼容与验收

- `fidelity=off`仍是产品默认，公开视频正文20000字符上限不变；此候选不能恢复公开长文。
- 离线覆盖必需/额外/重复JSON字段、subject和quote跨目标误绑定、null路径、source/draft子串、连续/拼接/改写/大小写引文、assessment/relation无效组合、14点7808 token边界及超限零POST。
- 独立代码审查、phase7 runner freeze/check与phase4源/草稿哈希核对全部通过后，才运行最多2 POST复用phase4草稿。失败phase关闭后不重试；若完整结果产出，再重新审阅P4及其他core。
- phase7通过后另行有限phase测试正常完整生成、未见MIT Lecture2及必要短中回归；每个phase各自给出上限。不得将phase6失败或旧phase结论改写、并表或转记通过。

## 成熟方案

采用现有Pydantic严格schema和官方Responses `json_schema`，不引入新SDK/依赖/遥测。Schema保证字段完整和长度限制，不保证生成的主体关系或语义判断正确；产品只在显式checks候选中使用，且错误停机。模型执行范围判断仍需实际语义评分。
