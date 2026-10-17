# 长文修复真实调用前审查记录

工程约定：用户/AGENTS/适用skills优先；成熟能力、窄接口/单向依赖，yt-dlp唯一层、视觉只读scene；UI用专业skills/三层token。保护已有工作、账号/env、本地模型及历史原件。

本记录在phase-1 freeze前生成；freeze之后保持原字节，后续测试/内容评分另存报告，不修改此资产。用户本轮不设总预算，但逐次预占、root串行/shared lock、错误即停、旧closed不可重开仍执行。

## 生产审查与处理

独立Sol审查确认跨语境重复保留、相邻字幕复制折叠、源语言多段笔记/用户语言最终输出、完整来源容量选择和大源有限边界符合设计。无新框架/facts协议/样本答案或付费步骤，默认legacy/adaptive/single、provider/thinking/token配置不变，公开20000保护尚未调整。

原Important为`summarize_sections`可变配置遗漏新增策略校验。root新增两项失败回归，实测非法配置已经发送请求并落到invalid_response；随后提取共用`_validate_summary_source_policy`供默认入口与staged预检查，相关160项通过，错误现在在POST前返回llm_unconfigured。原Minor完整来源所有section覆盖已增加从输入独立推导的断言；没有修改旧评分或删模型文本。

原独立稿见本机`.planning/2026-10-13-long-summary-fidelity/production-review.md`；修复证据为policy-review-red.log/green.log。生产真实内容尚未通过，本记录不声称语义正确。

## 验收工具审查与处理

新入口使用uncapped/null总预算标志；phase的planned_posts只审核生产arity，不作长期额度。旧历史26+17+8+16=67由原closed元数据hash完整绑定，不双计、不重写。共享caller锁沿用旧路径；Agent身份为协作纪律，不伪称工具认证。

独立初审Critical0/Important2；作者TDD修复后scoped独立复审Spec/Quality PASS，两项均ADDRESSED：

- 分配inventory识别phase目录/文件、tracker与writing残件，任何未登记或未closed分配在新runtime/freeze前拒绝；保留allocation原件，不自动清理/重开/伪造closed。
- closed验证从source/codec/helper快照重建，不强制当前profile/一般版本字符串/准备函数；live仍严格拒绝漂移，结果与最后raw逐字符串绑定。冻结Python/Pydantic源码仍需兼容执行环境，不能保证任意未来库ABI。

首个raw后notes/context/format/semantic/max_extra五字段漂移，在第二leaf预占和发送前拒绝。新入口源码审查hash为`0dae102010a9f2a91f06b626d6150f9139f38ff3cc4b932b4abe31905aa3b66c`；稳定稿纳入freeze inventory。原审查及作者RED→GREEN/60项synthetic结果见本机harness-review.md、harness-implementation.md；审查员未重跑测试或调用模型。

## 执行前门槛

root仍须核对全部相关检查、phase-1 plan、实际freeze/check，再root单caller进行完整2leaf+merge。任何新失败保留原件、暂停该phase；不能把本审查或机械verify的semantic_quality_verified=false当内容PASS。当前测试/来源/候选与后续真实评分分开记录。
