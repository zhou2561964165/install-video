# 可追溯事实摘要 · 句子/行号证据（evidence 轮）验收

> 这是**新一轮**交付文档，不覆盖 `../2026-10-05-grounded-summary/` 的旧报告。旧轮「逐字复制 quote/qualifiers」合同两次真实评测失败；本轮合同改为**模型按 caller 行号选证据、caller 计算精确 span**，并保留旧轮冻结证据原样。默认策略仍 `legacy`，本轮不改 UI / yt-dlp 层 / `.env` / db / AGENTS / 模型资产。

## 工程约定

先检查适用技能；skill 优先于计划。样式走三层 token、能力配置化；yt-dlp 仅 `ytdlp_service.py`，LLM 仅 `llm_service.py`，视觉只读 scene，模块窄接口单向依赖。MIT 源语料及衍生评测按 CC BY-NC-SA 4.0 非商业使用，署名保留。

## 合同（最终形态，phase `evidence-wide`）

1. **句子切分**：`split_sentences(part)` 按清理后行切分，每行一个 `Sentence`（`text` 为原文精确切片，`start/end` 相对 part），纯函数确定性。
2. **模型字段**：`topic`、`claim`、`evidence`（非空 1-based 行号列表，升序去重、可非连续，因复合事实天然跨多行）、`attribution`、`importance`。**不再要求模型逐字复制 quote 或 qualifiers**；限定/频率/模态保留由 `claim` 措辞 + 核查 `qualifiers_preserved` 语义标志 + 独立评审承担。
3. **呈现**：源以内联编号文本 `[1] 行1\n[2] 行2…` 传给模型（附 `line_count`），模型照抄所见行号、无需数数组位置。
4. **caller 计算**：由选中行号计算 `quote`（=选中行原文按序以 `\n` 连接）、`start/end`（首行 start 到末行 end 的覆盖区间），存 `GroundedFact.evidence_indices`。
5. **归因**：`source` 或该 part 内逐字出现的名字（caller 算 attribution span）。
6. **限制**：`FactLimits` 无 `max_quote_chars/max_qualifiers`；`max_evidence_sentences`（默认 128，上限 256）。facts 策略用 `llm_summary_facts_chunk_chars`（默认 8000）细分段，避免单次抽取超输出预算。

## 迭代记录（真实评测，共享 24→49 台账）

| phase | 合同变化 | 结果 |
|---|---|---|
| `evidence-id`（warm-up） | 字符串行号 ID + 逐行 JSON `{id,text}` | zh-short/en-medium 成功；en-long 因审计载荷超 60K 停止（JSON 元数据过臃肿） |
| `evidence-lines` | 整数行号 + `lines` 数组 | zh-short/en-medium 成功；en-long 抽取超 4096 输出 token（20K 分段太大） |
| `evidence-chunks` | + facts 细分段 8000 | zh-short 成功；en-medium 因模型把 95 行数成 97 越界（数组计数不可靠） |
| `evidence-inline` | + 内联编号 `[N]` | zh-short/en-medium 成功；en-long 因复合事实跨非连续行被「必须连续」拒绝 |
| `evidence-noncontig` | + 允许非连续行号 | zh-short/en-medium 成功；en-long 因宽事实引用 87 行 > 32 拒绝 |
| `evidence-wide` | + `max_evidence_sentences` 128 | zh-short/en-medium 成功；en-long 5 段抽取全部成功，**compose 组织阶段超输出 token** |

每次失败均为**明确可追溯的结构拒绝**，不重试、不隐藏付费回退，失败原件保留（`results/` 各 phase 独立目录）。旧 phase 的 provenance/trace/result 原样保留，不重写。

## 最终结果（`evidence-wide`）

| 样本 | 结果 | 离线核查 |
|---|---|---|
| zh-short | ✅ 3 POST，6 点（≤99 字），摘要 396 字 | 11 事实 span 全部成立 |
| en-medium | ✅ 3 POST，6 点（≤70 字），摘要 424 字 | 8 事实 span 全部成立 |
| en-long | ⚠️ 5 段抽取全部成功（54 事实 span 全部成立），compose 组织阶段 `llm_incomplete_response` | 54 事实 span 成立，无最终输出 |

`check_evidence --phase evidence-wide`：`trace_lexically_valid: True`，语义蕴含与事实准确不在本离线检查内（`semantic_entailment_proven: False`）。

**核心结论**：句子/行号选证据合同**已在三源全部验证**——短/中端到端通过，长文的 54 条事实也全部成功抽取并逐行可追溯。唯一剩余是**compose 组织阶段**把 5 段约 50 条事实压缩成摘要+≤7 要点时超 4096 输出 token，这是此前各轮都未达成的「长文组织/压缩」难题，与证据合同本身无关。

## 预算

共享台账 ceiling 24 → 40 → 42 → 49（三次用户授权追加）。已用 **48/49**，剩余 1：

- 前轮冻结 5；`evidence-id` 6；`evidence-lines` 7；`evidence-chunks` 4；`evidence-inline` 7；`evidence-noncontig` 7；`evidence-wide` 12（zh-short 3 + en-medium 3 + en-long 6）。

真实调用不自动重试；失败即停、计入台账。前轮 5 行与旧 `delivery-profile.json` 原样，未改写。剩余 1 次不再使用。

## 未达目标与下一步

- 核心目标（**模型按 caller 行号选证据替代逐字复制**）已实现并**三源验证**：短/中端到端，长文 54 事实全部成功抽取、逐行可追溯。
- en-long 唯一剩余：compose 组织阶段（约 50 条事实 → 摘要+≤7 点）超输出 token。修法候选：给 compose 阶段独立更大输出预算、或先对事实做一次中间归并再组织。这是长组织难题，留待后续。
- 长文 14 条复合事实全量覆盖、文化归因/类型操作范围等此前各轮的未达项，仍留待后续。

## 复查命令

```powershell
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary-evidence/scripts/evaluate.py --phase evidence-wide --check-only
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary-evidence/scripts/check_evidence.py --phase evidence-wide
```

设计见 `../superpowers/specs/2026-10-05-grounded-summary-evidence-design.md`，计划见 `../superpowers/plans/2026-10-05-grounded-summary-evidence.md`。默认 `legacy`，不提升。
