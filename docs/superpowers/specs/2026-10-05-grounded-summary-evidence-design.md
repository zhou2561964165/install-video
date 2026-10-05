# 可追溯事实摘要 · 句子ID证据设计（evidence-id 轮）

> 上一轮（`2026-10-05-grounded-summary`）的「逐字复制 quote/qualifiers」合同在真实评测中两次失败：quote 超上限、限定词/归因不在 quote 内。本文件是**新一轮**设计，不覆盖旧设计/旧证据；实现与旧报告保持分离，便于后续 Codex 审查。

## 目标与边界

在不改变公开 API、n+2 阶段、legacy 路径与默认策略的前提下，消除「模型逐字复制子串」的脆弱性，保留 caller 侧的精确可追溯。来源匹配只证明引用可追溯，不证明语义蕴含或外部世界事实正确。

## 合同变更（相对上一轮）

1. **句子切分**：`split_sentences(part)` 把每个清理后分段按行切成句子（句文本=原文精确切片，`start/end` 相对 part）。纯函数、确定性、可重建，是唯一来源；与 rubric 的行级证据对齐。
2. **事实字段**：模型输出 `topic`、`claim`、`evidence`（非空、1-based 行号列表，升序去重、**可非连续**，因复合事实天然跨多行）、`attribution`、`importance`。源以内联编号文本 `[1] 行1\n[2] 行2…` 呈现（附 `line_count`），模型照抄所见行号、无需数数组位置，也避免逐行 JSON 元数据超 60K。**不再要求模型逐字复制 quote 或 qualifiers**。
3. **caller 计算**：由选中行号计算 `quote`（=选中行原文按序以 `\n` 连接）、`start/end`（首行 start 到末行 end 的覆盖区间），存入 `GroundedFact.evidence_indices`。`qualifiers` 字段整体移除——频率/模态/范围保留改由 `claim` 措辞 + 核查 `qualifiers_preserved` 语义标志 + 独立评审承担；句子级证据天然保证限定词来自原文。
4. **归因**：仍为 `source` 或该 part 内逐字出现的名字（名字短、非本次失败主因），caller 计算 attribution span。
5. **限制**：`FactLimits` 去掉 `max_quote_chars/max_qualifiers/max_qualifier_chars`，新增 `max_evidence_sentences`（默认 128、上限 256）；config 用 `LLM_SUMMARY_FACTS_MAX_EVIDENCE_SENTENCES` 替代 `LLM_SUMMARY_FACTS_MAX_QUOTE_CHARS`。facts 策略用 `llm_summary_facts_chunk_chars`（默认 8000）细分段。

## 语义/取舍/蕴含核查（不变）

句子选择不放宽为模糊匹配；`flags=true`、有效 source/ID 不证明 claim 被蕴含、核心事实齐全、核查为真或外部事实正确。逐项 checks 与最终事实覆盖独立核查。

## 验收

- 纯 codec/流程红绿测试（`test_summary_facts.py` / `test_grounded_pipeline.py`）：证据 span 映射、未知/重复/非连续证据、越权归因/伪 span、长单行证据无长度上限、legacy 与格式兼容、容量、API 形状。
- 真实评测复用冻结 MIT 源与 14 条复合事实，新 phase `evidence-wide` 继续共享台账（最终 ceiling 49，三次用户授权追加；全部正常阶段+失败计入，不重试）。失败原件保留、不覆盖旧 phase。
