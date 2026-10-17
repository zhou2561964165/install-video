# Phase 9 原生 schema 单次合并工具独立审查

审查日期：2026-10-15。最终结论：**Critical 0 / Important 0 / Minor 0**。结论仅适用于所列代码版本和有限单次合并工具，不表示最终摘要语义通过。

工程约定：复用成熟组件及已验证接口，保持窄接口、单向依赖、可配置和最小充分修改；yt-dlp 仅经既有 service，视觉层只读 scene。UI 如变更须 ui-ux-pro-max、design-system 及 primitive→semantic→component 三层 token。本次保护现有 UI、账号/env、本地模型、依赖和历史原件；不改生产默认或旧脚本，不提交、推送、部署或恢复公开长文入口。

## 范围与版本

依据 `docs/superpowers/plans/2026-10-15-native-merge-check.md`，独立只读审查新 `scripts/native_merge_evaluate.py`、`backend/tests/test_native_merge_evaluation.py`，沿接口检查复用的本报告 `scripts/evaluate.py`、`normal_evaluate.py`、历史 schema-Pro 工具的 `response_evidence` / `responses_content`，以及生产 merge/request/Responses parser 和冻结 codec 的调用关系。审查者唯一新增文件为本报告，未改实现。

已审 SHA-256：

- `scripts/native_merge_evaluate.py`：`ee0f4150b69c6157b126993b46872fc2db9c44a2997f4a5d0b0f6f78c07eb28d`
- `backend/tests/test_native_merge_evaluation.py`：`4eadd6d3efca31ef5ac947d6decdd1bf08ef3da00928a48e78b1a7df186620b3`
- `docs/superpowers/plans/2026-10-15-native-merge-check.md`：`c732b2f588cf861f5fb7d91a9817589eb122cc58e6f7482467705ffd3e634bb4`
- 复用 `scripts/evaluate.py`：`0dae102010a9f2a91f06b626d6150f9139f38ff3cc4b932b4abe31905aa3b66c`
- 复用 `scripts/normal_evaluate.py`：`b0cfabdce88c37d5851fab7b8b6b1721114c5f0982c4f28cb087baac03144e57`
- 复用 `2026-10-10-schema-pro-summary-live/scripts/evaluate.py`：`73c473cb0dfafa4b112f433f6a093457727c97904597f86c463d17ec51bfbf6f`

## 规范及代码质量审查

- 仅可分配新 phase-9，planned_posts、phase_post_cap、样本 expected_posts 均为1，stage 唯一为 merge；原 engine 发前 arity 和新 expected_payload 同时阻断第二次预占/发送。没有增加 format/semantic/extra 调用，没有自动重试、付费 fallback 或重生成 leaf。
- 显式候选 Pro/Responses json_schema，thinking disabled 对应 effort none；冻结与核验要求输出上限8192、点数上限14及真实 output_schema，不放宽旧结构限制。模型与格式同时变化，只能作为联合候选对照，不归因于 schema 单一因素，更不升级默认 Flash 或宣称总体质量解决。
- 父 phase8 必须已闭账、三次请求且第三次 merge 后失败。专项冻结检查第三条 ledger stage 为 merge、status=response；失败 product 必须 success=false、error_type=llm_invalid_response，ledger 结果 hash、index、receipt、tracker 和 closed group 行互相绑定。没有误要求父整个摘要生成成功。
- 只从父 raw01/raw02 通过父冻结 codec 解码两份成功 leaf，核对 HTTP、model、finish_reason、原 payload、预算及顺序。失败 raw03 不进入新合并输入或专项 leaf 快照绑定；父原 verify 在准备阶段仍只读核验完整旧 phase8 原件，不能将旧失败转记通过。
- 新快照绑定父 provenance/ledger/receipt/index/失败 product/tracker、两 leaf payload/raw，以及父快照内 manifest/source/VTT/准备函数/codec/normalizer。manifest、父 sample 与本 sample 的来源字段三方一致，重新计算完整 cleaned source 和两段 hash。当前生产 source 与父来源也须一致。
- 合并实际调用既有 `_summary_merge_contexts`→`_section_notes`→`_summary_request(...merge=True)`，要求完整 source contexts，使用两份成功 notes 和完整原文，不手写第二套生成协议或样本答案。冻结 payload 与实际发送逐字相等；原 engine 发前还核对运行时、资产、父 live 原件和来源。输入容量继续有限。
- HTTP、共享锁、持久预占、run/check/close 与结果会计复用原引擎；专项 freeze 只为单 merge 构建新冻结资产，不补写旧冻结格式。父 live 证据漂移在新 POST 前拒绝，阶段按错误关闭，旧原件保持。
- Responses evidence 复用已有安全字段白名单，只保留原生 object/status/output/usage 等必要证据，丢弃 reasoning 及任意 header/key 字段。最终独立解码调用冻结生产 `_responses_content`，检查顶层 completed、单个完整 assistant message、output_text、error/incomplete 状态；没有伪造 chat finish_reason=stop。结果再经冻结 JSON/Pydantic codec 与14点规则接受。
- 封账 verify 使用本 phase 已保存的父证据、父准备/codec 快照及新原生响应 parser。对 phase8 的 closed binding 切换为本 phase 快照并比较 group 行，不依赖 live phase8 raw 来掩盖或重解释已保存证据；其他历史会计仍沿原规则检查。
- live root 双声明与 system-temp/owned mock containment 复用已审 guard，且在新阶段 live 状态写入前执行。help/plan/check/verify 不调用读取 dotenv 的 runtime。资产清单含新代码/test/计划/独立审查、生产、scope 回归及所复用工具。

实现者在审查过程中完成父 manifest、失败 product 和第三 stage 状态绑定；审查者在稳定版本中逐项只读复核，没有留下未关闭问题。

## 实际离线验证

审查者仅执行6项必要定点用例，全部使用 pytest 自有 system-temp 目录、合成父来源/响应及 mock transport：

```powershell
.venv/Scripts/python.exe -B -m pytest --noconftest -p no:cacheprovider 'backend/tests/test_native_merge_evaluation.py::test_one_native_merge_preallocated_and_frozen_verify_is_independent_of_live_parent' 'backend/tests/test_native_merge_evaluation.py::test_parent_drift_after_freeze_stops_before_payment_and_closes[response-02.json]' 'backend/tests/test_native_merge_evaluation.py::test_parent_drift_after_freeze_stops_before_payment_and_closes[en-long.json]' 'backend/tests/test_native_merge_evaluation.py::test_bad_provider_response_counts_once_never_retries[incomplete]' 'backend/tests/test_native_merge_evaluation.py::test_true_native_response_shape_is_not_replaced_with_chat_stop[object]' 'backend/tests/test_native_merge_evaluation.py::test_second_stage_refused_before_reservation' -q --tb=short
```

结果：**6 passed in 18.85s**，exit 0。覆盖单次发前预占、原生 payload/schema/完整两叶与 source、旧证据不变、封账后 live 父 raw 漂移不影响新快照 verify、发前父 raw02/失败 product 漂移零付费、原生 incomplete/object 不符拒绝，以及第二次调用零预占/零发送。

实施者另报告扩展27项通过（27 passed / 58.14s）；这是实施者报告，审查者未重复全套或将其记作亲自运行。

本审查没有真实 POST、freeze、读取真实 env/凭据、启动服务或修改旧证据。root 后续仍需独立 plan/freeze/check 核对，才可按已授权 cap1 执行一次对照；实际内容必须另审 P4、原六核心主题、逐断言范围和组织。结构接受不等于语义通过；未见来源及短中回归不在本工具离线证据范围。
