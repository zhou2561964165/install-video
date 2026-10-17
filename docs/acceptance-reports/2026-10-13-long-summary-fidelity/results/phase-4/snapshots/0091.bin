# 长文独立反馈后修订设计

工程约定：用户/AGENTS/适用skills优先，成熟能力及配置化窄接口/单向依赖，yt-dlp唯一服务层、视觉只读scene；UI用ui-ux-pro-max/design-system及三层token。保护他人工作、账号/env、本地模型和全部历史原字节。

phase-2单次自校订实际1POST/26699tokens，本组累计4POST/78361tokens。新结果恢复末尾衔接，6核心均full，但具体例子范围仍错误；单纯请求模型自校订没有找出该错误，不能再重复同一付费步骤宣称修复。

采用[官方evaluator-optimizer职责分离](https://docs.langchain.com/oss/python/langgraph/workflows-agents#evaluator-optimizer)，实际复用已安装langchain-core的RunnableSequence/RunnableLambda组成固定review→revision，PydanticOutputParser解析简单内部反馈，原httpx承担唯一模型传输。LangSmith仅用于关闭追踪上下文；不用远程评估、SDK、外部遥测或新框架。没有状态图循环、自动重试或事实ID/引用协议。反馈不是语义证明，仍需独立逐源内容评分。

## 配置、接口和成本

- `LLM_SUMMARY_FIDELITY_MODE=off|long|review`。off和旧long单次校订保持显式兼容；新review先为显式候选。只支持legacy/single/adaptive；review不支持strict_tool，发前拒绝，auto/text/json_object/json_schema沿既有传输。
- `LLM_SUMMARY_REVIEW_MAX_OUTPUT_TOKENS=4096`，有限可配置；修订继续沿原来源规模的有限输出预算/14主题上限，不能因独立反馈增加主题或无限输出。
- `review_summary(transcript,draft,*,title,output_language,client,diagnostic)`固定两次：完整原文+草稿→简单`feedback`字符串；完整原文+同草稿+非权威反馈→现有summary/key_points。反馈只报告来源不符或重要遗漏，不返回重写答案、评分合同、推理过程或新facts。第二步由原文判断反馈是否准确。
- 多段正常路径采用该接口；短单段仍一次生成。两叶完整生成3→5POST；复用已付费phase2草稿验证只2POST。坏配置/输入/草稿发前拒绝；完整system+user消息（包括反馈）不能容纳时该阶段0POST且停，不截源/点、不退回草稿、不付费fallback。
- 网络/provider/结构/容量等错误终止，不重跑pipeline。独立反馈即便说无问题也只有一次修订，不增设新的评价循环；最终输出不自动宣称语义通过。

## 验收

先TDD/离线与独立审查，再新phase3 freeze/check/root单caller真实两次。绑定已closed phase2 source/raw/product/receipt和累计4，原phase1/2脚本及原件保持。初候选用正常base4096/ceiling8192、thinking auto（本provider解析disabled）及review4096，避免继续重复高thinking自校订。全部尝试逐次共享uncapped台账预占、错误停，任务仍不设总预算。

phase3要实际检查反馈是否发现来源范围问题，并重新审阅最终全部断言/core6；通过后再在正常profile完整生成已见/未见长文及短中回归。未见准则已在生成前冻结，不能照搬旧source具体答案。公开入口及默认暂不改。
