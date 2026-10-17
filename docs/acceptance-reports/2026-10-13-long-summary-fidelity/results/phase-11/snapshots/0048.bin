# Phase 11 完整来源直入工具独立审查

审查日期：2026-10-15。最终结论：**Critical 0 / Important 0 / Minor 0**。审查只确认工具边界与证据绑定，不表示生成内容的语义质量通过。

工程约定：优先复用成熟的生产生成、Responses 解析、冻结、预占、封账和回放接口；保持窄适配，不改产品默认、旧 phase 原件、用户账号/env、本地模型、UI或公开长文入口。此次没有提交、推送或部署。

## 范围与版本

独立只读检查 `scripts/direct_source_evaluate.py`、`backend/tests/test_direct_source_evaluation.py`，并沿用 `native_merge_evaluate.py`、`normal_evaluate.py`、`evaluate.py` 的 freeze/check/run/verify、共享锁、caller guard、发送前持久预占和 Responses codec 调用关系。审查未运行测试、freeze、服务、dotenv/env读取或真实 POST。

最终审查 SHA-256：

- `scripts/direct_source_evaluate.py`：`e080c2b80f5c8564469ed99e4faab0d75e49c8eb3f54ba8343548dd284e2f4f9`
- `backend/tests/test_direct_source_evaluation.py`：`6908f3d95200844aa0a7b171d6fdeb788377e6d3a16193fe211c75f174ae3eb4`

审查期间发现并要求修复一个 Important：开始版本只核对当前语料与当前 manifest，未把二者绑定到 phase10 已冻结的来源。修复后，`source_identity_guard` 在分配前和快照回放时均核对 phase10 唯一 `en-long` 的 `id/file/raw_path/sha256/raw_sha256/title/license/attribution/cleaned_sha256/cleaned_chars`，并核对整个 manifest 文件 SHA。新增同步改字幕/manifest、改字幕元数据、freeze 后漂移及快照重放篡改场景。修复版本哈希稳定后复核通过。

## 审查结论

- 仅允许新 phase11；计划、phase cap、样本期望请求数和实际阶段数均为1。父 phase10 必须 closed，reserved_posts 为1，长文工作组累计数为16；父 receipt、ledger、index、provenance、tracker 和产品哈希相互绑定。新请求不把父产品/notes作为模型输入。
- 输入仅为 phase10 同一 MIT Lecture 1 的完整规范化来源。完整正文、VTT、授权署名字段和整份 manifest 均受父冻结证据及本 phase snapshot 约束；34,894 字符须完整低于60,000上限，超限则在分配前拒绝，不截断或回退。
- 专用 adapter 将生产 `_summary_request` 固定为 `merge=False` 与准确 source_chars；实际 Transcript 必须与冻结 source hash/长度相符。冻结请求继续使用 Pro/Responses `json_schema`、14点及8192输出上限；历史 stage 标签 `merge` 由 `request_path=direct_source` 和实际 `merge=False` 明确区分。
- 复用既有冻结、生产 payload capture、HTTP/Responses parser、共享目录锁、root/mock guard、结果保存、封账和离线 verify。root caller guard 在写入前运行；payload 与 freeze capture 不相等则不发送；预占先持久写入 GROUP、ledger 和 tracker；第二次调用、网络/provider/incomplete/结构错误均不会重试或 fallback。
- phase11 verify 从本 phase 冻结快照重放，明确 `semantic_quality_verified=false`；不依赖后来可能变化的 live 生产文件或父摘要结果来重解释本次响应。审查确认来源漂移在 POST 前拒绝，phase10 历史原件保持独立。

## 实际验证边界

实现者报告离线回归覆盖完整 source/wire、父 phase10 哈希和累计数、同步 source/manifest 漂移、冻结后漂移、快照重放篡改、单 POST cap、schema/预算、caller/mock guard、错误即停与环境隔离。审查者未独立运行这些测试；root应在冻结前记录实际测试命令及结果。

本工具审查不证明供应商会覆盖 long1–6、忠实保留归因/模态、满足逐断言范围或生成良好概览。真实对照仍需独立内容评分；结构合法或快照 verify 通过不能写成长文问题已解决。
