# Grounded summary · 句子ID证据实现计划（evidence-id 轮）

> 新一轮，不覆盖 `2026-10-05-grounded-summary.md`。设计见[同轮 spec](../specs/2026-10-05-grounded-summary-evidence-design.md)。共享 24 POST 硬预算，旧 5 次已用，剩余 19 次；失败即停、不重试、不改旧台账。

## 工程约定

先检查适用技能；本轮不改 UI。只有 `ytdlp_service.py` 接触 yt-dlp，LLM 只经 `llm_service.py`，视觉只读 scene。窄接口单向依赖；配置化。用户 `.env`/db/AGENTS/模型资产与历史台账不改。

## Task 1+2：句子ID证据合同与编排（已完成）

- `summary_facts.py`：`split_sentences`、`Sentence`、`GroundedFact.evidence_indices`（移除 `qualifiers`）、`FactLimits.max_evidence_sentences`。
- `llm_service.py`：抽取/核查提示词改为按 1-based 行号选证据；extract/audit 载荷改为紧凑 `lines` 字符串数组；compose 传 caller 解析后的证据文本。
- `config.py`：`LLM_SUMMARY_FACTS_MAX_EVIDENCE_SENTENCES`。
- 重写 `test_summary_facts.py` / `test_grounded_pipeline.py` / `test_config.py`。后端 347/347 绿。

## Task 3：真实评测（已完成，见本轮报告）

- [x] 新评测脚本（本轮新目录，共享台账续用；最终 ceiling 49）：`evaluate.py`（冻结+预算+真实调用）、`check_evidence.py`（离线行号→span 核查）。
- [x] 复制冻结 rubric.json；`--freeze` 零网络冻结。
- [x] `--system-proxy` 真实跑三源，经 6 个 phase 迭代（evidence-id→lines→chunks→inline→noncontig→wide）逐步消除逐字复制/容量/计数/连续/证据数量五类失败。
- [x] 最终 `evidence-wide`：zh-short ✅、en-medium ✅、en-long 5 段抽取 54 事实全部成功、compose 组织阶段超输出 token。离线核查通过，预算 48/49。

结果与未达项见[本轮报告](../acceptance-reports/2026-10-05-grounded-summary-evidence/report.md)。

## Task 4：集成交付

- [ ] root 独立源码/结果复审；适当全量回归与构建。
- [ ] 实现提交、本轮新文档/证据归档、字节/链接/凭据扫描；停止本轮服务与调用。
- [ ] 报告并等待用户指示（默认仍 `legacy`，不提升）。
