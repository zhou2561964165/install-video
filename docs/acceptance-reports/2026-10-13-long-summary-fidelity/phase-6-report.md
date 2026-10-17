# Phase 6：Responses checks 真实复验结果

日期：2026-10-14。phase1–5保持closed。本phase cap为2 POST，复用phase4已封账的source/raw02/product/receipt；组级总预算仍按用户授权不设上限。Root单caller、共享锁、发前持久预占。phase6已closed并verify，未重开。

## 执行结果

- 计划上限：2 POST；来源草稿：phase4完整14点摘要；模型：`deepseek-v4-pro`；核查endpoint：DeepSeek Responses；修订endpoint：冻结的Chat Completions。
- 实际：**1 POST / 13208供应商tokens**（12437 input、771 output）。HTTP 200，Responses状态completed，结束标记stop，动态schema返回15个目标字段；没有第二次修订请求。
- 阶段结果：`llm_invalid_response`，原因为一个`source_quote`不是冻结原文的连续子串；首响应后按规则停止，无格式重试、fallback或第二次预占。
- 组总计：原phase1–5为9 POST/147600tokens，加phase6后累计**10 POST/160808tokens**。旧封账计数与phase1–5原件未变。

## 内容核查结论

虽然15个target字段齐全，target 4仍把父草稿中“固定程序计算机（如计算器）”的具体实例限制判成` supported`，source quote只覆盖该例子的四则能力句，没有比较原文“这台计算器”与草稿类别主语的范围差异。由此可见，动态目标和引用来源校验解决了重复字段/格式边界，未能保证模型识别P4范围泛化；即使该响应能通过引用解析，也不能把P4当作已修复。

Target 11引文与来源内容几乎一致，但它把源句开头小写的`if`改成句首大写`If`。当前checker只允许空白规范化，区分大小写，因此将其拒绝为非精确原文引用，没有revision反馈。其余14条引用都能在冻结来源中匹配。这个判断只涉及严格引文归属；不是说摘要另有事实错误。

没有新的最终产品摘要，本phase无语义PASS。P4仍是当前长文实际缺陷；其他前四phase已恢复项目保持原review结论。

## 审计记录

`phase_post_cap=2`已写入冻结provenance及offline-check；该数值必须是严格整数。phase tracker和request ledger显示仅预占并发出POST 1，phase6状态closed，`stopped_on_error=true`，`semantic_quality_verified=false`。闭合验证成功仅证明失败响应、计数与来源链被完整保留。

| 文件 | SHA-256 |
| --- | --- |
| provenance | `0bad0225b80f0750c10c040ae82bd201131227a455ed9d0cffc395697f36ac30` |
| response-01 | `de35ccf67940dea53f4c54fc4185b66d7678f45f5ade3c2d53141d79c0a5b977` |
| error result | `69c9b65866d194d7647992ca1000c859850e40436057fa49d18251d76f7b3231` |
| request ledger | `6d2d4e775618ac9b7754a8b22ee58fd9ee9bdbecfba6446e9a1e92c71661a232` |
| closed receipt | `d5c06eb9e8ecde3c67022bbee10ec1f644f54b8f26a8c098f6c4c0d81f164511` |
| offline check | `a6f254094ba5f9a97412d65d5d697712ebfeb1e4960f9e738802560521f44e49` |

完整冻结snapshot位于`results/phase-6/`。不得修改或重开phase6原件。下一候选拟在新phase中明确绑定source subject、draft subject和范围关系，并保留精确来源引文校验；该设计仍需TDD、独立审查和有限输出预算验证。新phase最多2 POST复用phase4草稿，不把phase6错误raw作为成功输入。MIT字幕来源与CC BY-NC-SA 4.0署名随父冻结manifest保留。
