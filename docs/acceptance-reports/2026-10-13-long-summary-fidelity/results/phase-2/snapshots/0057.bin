# 长文单次来源校订设计

日期：2026-10-14。延续用户已授权的长文整改，不设任务总POST/费用预算；实际调用继续逐次记账，旧phase不重开。

工程约定：Superpowers与适用skills优先，成熟组件优先；配置化窄接口、单向依赖，yt-dlp唯一接入/视觉只读scene；UI采用ui-ux-pro-max、design-system及三层token。保护已有工作、账号/env、本地模型及所有历史证据原字节。

## 新证据与目标

phase-1已closed，3POST、51662供应商tokens。相邻字幕去重、源语言笔记、完整原文合并均实际生效，输入/结构/账本核验通过；独立内容审阅仍FAIL：5full/1partial，具体实例限制被推广到类别，重要末尾衔接遗漏。算术子集、相对时间、求值和显式重算已通过新审阅，不能沿用旧失败标签。

在完整原文和草稿已可装入同一次请求的范围内，单独执行一次来源校订，使模型专注逐断言范围与重要遗漏。它不是语义保证；仍由独立源文审阅验收。

## 成熟模式与选择

复用已核对的LlamaIndex refine与现有生成/校验组件。LlamaIndex逐chunk refine可能重新拆分并发出多次调用，官方evaluator-optimizer模式也可能循环评估/重生成，均不直接满足本项目严格一次及既有输出接口。采用明确结束的单次校订职责，实际执行继续复用httpx、Pydantic、无损JSON规范化和现有分段合并；不新增供应商SDK、框架或事实协议。具体官方来源与取舍追加在本轮pipeline分析中。

## 接口与有限资源

- `LLM_SUMMARY_FIDELITY_MODE=off|long`，初期默认off；候选必须显式long。仅支持legacy/single/adaptive，其他组合在任何模型请求前拒绝。
- `refine_summary(transcript, draft, *, title, output_language, client, diagnostic)`：完整原文优先，草稿标为非权威；一次输出仍是现有summary/key_points。坏配置、空源、坏草稿和完整消息超容量均发前拒绝，不截源/截点、不降级。
- `summarize_text`仅多段且显式long在原合并后调用一次校订。短单段成本不变；两叶正常3→4POST，多层树原调用数+1。任何provider、容量、结构等错误直接返回失败，格式/语义重试均0，没有付费fallback。
- 沿用配置的模型、thinking、有限自适应输出预算及主题上限。任务不设总预算不影响产品每次请求的输入、输出与调用上限。不能靠提高14点上限通过。
- 校订完整system+user消息包含指导、来源、草稿及title/lang，都按现有输入容量校验。多段开启时先检查完整来源及最小消息可容纳，实际草稿生成后再检查最终消息，超限不能偷偷改用边界证据。

## 验收顺序

先失败回归、最小实现、相关测试及独立代码/工具审查，再新phase freeze/check。phase-2通过新入口绑定已closed phase-1的精确源文、raw03和产品草稿，仅一次校订POST，不重复付费抽取。共享uncapped台账累计，不抹旧失败；root单caller串行、共享锁、发前持久预占、错误停。旧脚本/freeze/raw/ledger/review保持字节，新的复用脚本和审查另存。

校订结果逐断言/core6审阅；通过后再验证正常产品profile的完整生成和未见长文/短中回归，才决定默认及公开入口。当前20000字符入口限制仍保留；单例或机械测试通过不能证明所有长文已解决。
