# 本地规范化与通用来源限定修复（已闭账，未整体通过）

工程约定：用户/AGENTS/skills优先；UI专业skills及三层token；成熟Pydantic复用、窄接口/单向依赖，yt-dlp唯一层/视觉只读scene；保护原证据、凭据、账号及本地模型。

首phase已closed5POST/44968tokens，short/medium独立内容PASS；long14完整字符串但缺末尾数组]，产品拒绝。零POST诊断保留全部内容后发现时间、例子/枚举范围失真，不能当内容通过；原证据见[首phase](../2026-10-11-summary-content-resume/report.md)。

修复复用已安装Pydantic核心parser：独立summary_json.py严解析优先，只修可证明全部字符串和标点结构保留的末尾闭合，不为未完成值补默认，不丢点/裁字；原类型、数量及容量校验仍执行。现有service接线3项TDD先2失败后通过，新层48项通过。另补通用来源前件/示例主语/时间锚点/符号顺序指导，没有样本答案、依赖安装或新增付费步骤。

复验候选仍legacy/adaptive/single及显式thinking enabled，8192基础/16384 ceiling、14主题上限。新phase实际closed5POST/52139供应商tokens，HTTP均200，long最后finish_reason=length且content空；工作组累计10/10、97107tokens封账，旧51不重开。1668后端完整回归及129项相关集成、两个独立审查无阻断、41资产freeze/check均已通过；两phase --verify确认冻结/raw/result/账本闭账链。

| 样本 | 结构 | 内容结果 |
| --- | --- | --- |
| zh-short | 5点通过 | zh1–4full，精度/组织PASS |
| en-medium | 4点通过 | en1–4full、组织PASS；summary具体课后/书面反馈方式遗漏两个通常限定，precision FAIL；正确要点不能修补摘要 |
| en-long | 两leaf成功；最终合并无正文，产品拒绝 | final max12288全部reasoning、finishlength，不评分空内容，不按旧14点转记通过 |

独立审查：[短中篇](reviews/short-medium.md)。首阶段及本阶段原raw、失败结果、冻结和账本不改；源/网络/供应商与容量错误不自动重试。基于该具体容量及限定缺陷，后续仅用[10→13有限continuation](../2026-10-12-summary-content-capacity-repair/report.md)复验short1/medium1/long复用已付费两leaf只merge1，不重复提取。

准则见[review-criteria.md](review-criteria.md)。同组预算/请求原件按phase绑定，不把离线或旧phase结论当新内容通过；自然字幕及衍生审查依原MIT OCW/作者/CC BY-NC-SA4.0许可。
