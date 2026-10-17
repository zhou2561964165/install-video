# Phase 8 正常长文生成工具独立审查

审查日期：2026-10-15。最终结论：Critical 0 / Important 0 / Minor 0。仅适用于下列已审代码和本次正常生成验收入口，不是总结内容通过结论。

工程约定：复用成熟组件和已有验收引擎，保持窄接口、单向依赖及最小充分修改。yt-dlp 仅经既有 service，视觉层只读 scene；UI 如变更须 ui-ux-pro-max、design-system 与 primitive→semantic→component 三层 token。本次未修改生产、UI、账号/env、本地模型、依赖或历史原始证据，未提交、推送或部署。

## 范围与依据

依据 `docs/superpowers/plans/2026-10-15-normal-long-generation.md`，独立只读审查新 `scripts/normal_evaluate.py`、`backend/tests/test_long_normal_evaluation.py`，并沿复用接口检查本报告目录的 `scripts/evaluate.py`、来源优先验收引擎的 runtime/config/durable 接口，以及生产准备/请求选项和既有离线 fixture。审查者唯一新增文件为本报告。

已审文件 SHA-256：

- `scripts/normal_evaluate.py`：`b0cfabdce88c37d5851fab7b8b6b1721114c5f0982c4f28cb087baac03144e57`
- `backend/tests/test_long_normal_evaluation.py`：`65738f4ae77b92b0153a0e8024cfb9f8cc2e849a95f046789cedfcad89b6c5a7`
- `docs/superpowers/plans/2026-10-15-normal-long-generation.md`：`8853eeaad0964759dc59b821c5fc3f15cde1c9cda4516e38cee3cfe35f3e4f4c`
- 复用 `scripts/evaluate.py`：`0dae102010a9f2a91f06b626d6150f9139f38ff3cc4b932b4abe31905aa3b66c`

## 规范符合性与代码质量

- 正常 profile 明确为 legacy/adaptive/single/fidelity off；thinking/response_format 为 auto，输出基础4096、有限上限8192，format/semantic/extra 均0。保留 source notes 和 auto source context。配置不覆盖 provider/model，真实 freeze/run 通过原 runtime 读取 Settings.from_env 并绑定实际 provider/model/endpoint；不会继承旧 enabled/16384–24576 实验输出 profile。
- 仅允许 en-long：离线计划要求恰好两段及预计3 POST，冻结源校验再次要求 planned_posts=3、单一 en-long、两次 extract 后一次 merge。实际请求须逐包等于冻结生产请求，原引擎在第四阶段预占和发送之前拒绝。phase_post_cap 是薄入口返回说明；冻结原件中的 planned_posts、样本及 stage 序列承担实际不可绕过的3阶段边界，无需重写旧 freeze 格式。
- 新入口先执行 caller_guard 再 bind/run。真实 run 同时要求 caller=root 和 CODEX_ACCEPTANCE_CALLER=root，失败发生在共享锁、tracker、group 等 live 状态写入前；这是操作审计声明，不被表述为不可伪造的身份认证。
- mock 仅允许 system-temp 内隔离 PROJECT，排除真实工作区、其子目录及祖先；REPORT/CORPUS/GROUP/SHARED_LOCK/RESULTS/TRACKER 均解析后受 PROJECT 归属约束。原引擎的原子 durable 写入仍限制为本阶段自有文件。
- candidate_assets 包含新代码、新测试、计划、本审查、通用 scope 指导回归及 phase7 生产审查，另复用生产文件、codec、来源与历史会计绑定资产。冻结与发前检查继续验证快照/当前资产清单及 hash；不会只凭空 asset 清单绕过 live 校验。
- 新 expected_payload 在每次下一 POST 预占前核对全部已消费 payload 和已有 response hash，覆盖第二个独立 leaf 之前的漂移；merge 仍从新叶响应及冻结完整 source parts 生成，不复用旧付费笔记。原 codec、来源重新构建、阶段顺序、runtime matching 及单 caller 共享锁继续生效。
- 复用原引擎的一次阶段、持久预占、首错停止及 closed receipt，不复制 HTTP/会计引擎，不新增重试或隐藏付费 fallback。旧 closed 记录仅被读取和绑定；新阶段仅分配自己的结果/tracker，并累计原组计数，不重开旧阶段。
- help/plan/check/verify 路径不调用 runtime，故不读 dotenv；freeze 明确需要 runtime 但不发 HTTP。最终 verify 继续验证 frozen codec、原件、结果和 closed receipt；semantic_quality_verified 明确为 false。

未发现新入口的规范偏差、重要质量缺陷或需要代码修正的问题。

## 审查者实际执行

仅执行以下必要的离线定点验证，使用 pytest 自有临时目录、合成来源/响应和 mock transport：

```powershell
.venv/Scripts/python.exe -B -m pytest --noconftest -p no:cacheprovider backend/tests/test_long_normal_evaluation.py -q -k 'prior_packet_drift or live_caller_rejected or three_posts_preallocated or fourth_stage_rejected or mock_guard_rejects' --tb=short
```

实际结果：**9 passed, 18 deselected in 3.93s**，exit 0。覆盖两叶+merge 的发前预占/完整来源上下文与正常离线模型、前序 payload/raw 漂移在下一次付费前拒绝、双 caller 声明缺失/不匹配时零状态写入、第四次调用零发送及 mock 工作区/祖先隔离。

实施者另报告新27项及旧41项集成共68 passed，root 另报告独立新27 passed；这些属于他人报告，本审查未重复全套，未将其计作审查者亲自运行。

本审查未执行真实 POST、freeze、读取真实 env/凭据或启动服务，没有修改旧脚本/旧 phase 原件。通过上述审查只允许 root 在独立 plan/freeze/check 核对后进行最多3 POST 的正常生成复验；P4、六个核心主题、逐断言范围及 overview/组织仍须按真实新叶笔记和最终结果独立内容评分。未见来源及短中回归不在本次实际验证范围。
