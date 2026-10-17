# Phase 10 全局归并提示与单次合并工具独立审查

审查日期：2026-10-15。结论：**Critical 0 / Important 0 / Minor 0**。允许 root 按既定计划继续独立 plan/freeze/check；本报告不证明供应商执行提示、摘要内容或 P4 已通过。

工程约定：优先复用成熟组件和已验证接口，保持窄接口、单向依赖、可配置及最小充分修改；yt-dlp 仅经既有 service，视觉层只读 scene。UI 如变更须使用 ui-ux-pro-max、design-system 和 primitive→semantic→component 三层 token。本次不改 UI、账号/env、本地模型、产品默认、公开长度入口或旧验收原件；不提交、推送或部署。

## 范围与版本

依据 `docs/superpowers/plans/2026-10-15-global-merge-prompt.md`，只读审查本报告目录的 `scripts/global_merge_evaluate.py`、`backend/tests/test_global_merge_evaluation.py`、生产 `_summary_request` 合并指导及 `test_summary_scope_guidance.py`，沿接口检查复用的 native/normal/evaluate runner、schema-Pro Responses 证据与解析、会计/冻结/关闭及 mock containment。审查者唯一新增文件为本报告。

已审 SHA-256：

- `scripts/global_merge_evaluate.py`：`d65a9f9a594910dac2424d995f2d088d29ef41f634782497c5254cf92f2ca00e`
- `backend/tests/test_global_merge_evaluation.py`：`bbcdc69d254123b5eb6f7c3df931ed9dee4c3c9979596be6cd58731b254be4a2`
- `backend/app/services/llm_service.py`：`9d142603911e6a8a58d023e2b1492c358ef762232f4d7d00567de48771054b8b`
- `backend/tests/test_summary_scope_guidance.py`：`6cb223d473c93bc51ed9378a87c4bc3d19e430be9ec5cbd920a3c81b76070e2f`
- 本次计划：`fc312831d1a0d3faff59f69a7ffc7affbda34d8a3b6757d193e04dbb5a3601d4`

另外将当前 `native_merge_evaluate.py`、长文 `evaluate.py`、`normal_evaluate.py` 和历史 schema-Pro `evaluate.py` 的 SHA-256 与 phase9 provenance 中相应冻结资产记录逐项比较，四项均相同。没有修改这些旧 runner。生产 service 与 phase9 冻结 service 的行级比较只有本次五条 merge 指导新增，未混入此前未提交改动作为本次变量。

## 规范及代码质量

- 新指导位于 `merge=True` 的 request guidance 分支，要求跨全部 notes 按主题编辑、摆脱分段列表顺序、保留独立内容并核对完整 source 后段条件/结论/过渡。没有样本答案、事实协议、删点器或截断器；leaf/system/schema/输出预算均不因这五条指导改变。
- wrapper 只允许 phase-10，通过窄绑定复用 phase9 的生产合并 adapter、HTTP、Responses、codec、共享锁、持久预占、错误停止和封账。单样本、单 merge、cap1、8192 output、14 点、Pro/json_schema/effort none 均继续受冻结检查；format/semantic/extra 均0。第二请求在预占和发送前拒绝，没有自动重试或付费回退。
- `prior_closed_guard` 调用已有 group_state 检查各 closed metadata 的 receipt/ledger/provenance 绑定，再要求唯一 closed phase9、其 reserved_posts=1，以及总计等于此前15加本 phase 预占数。plan/freeze 均先 guard；run 在 inherited engine 写 running 状态前完成 root/mock guard 和共享锁内 prior guard。phase9 ledger/receipt 漂移在 phase10 状态写入前拒绝。
- phase8 raw01/raw02 的来源、预算、原 payload、父 codec 与闭账关系继续受原生工具严格校验。仅两份已接受 leaf 和完整原文进入 notes；phase8 raw03、phase9 product 不进入生成输入。phase8 raw 漂移经 inherited live check 零预占拒绝并 proper close，旧失败不会转记为新成功。
- candidate_assets 包含基础 engine/helper/生产/schema/来源资产、原 native/normal/schema-Pro 工具、scope 回归、新 wrapper/测试/计划、本报告，以及 phase8/9 report 和 content-diagnosis。基础资产由原 asset_paths 枚举；check 和发前 frozen_state 对全部快照逐个核对 live 字节，并比较完整资产清单，基础 helper 漂移也受检。报告自身在 root freeze 前落盘。
- caller guard 复用已审成熟实现：真实执行需要 root 双声明；mock 只允许 system-temp 下独立项目，拒绝真实工作区、自身祖先及 owned 路径逃逸。guard 位于新 phase 状态写入之前；离线 plan/check/verify 不需要 live runtime 或 dotenv。
- 封账内容回放使用本 phase 快照中的 phase8 来源、两份成功 leaf、父准备函数/codec/normalizer，以及当前冻结 codec/Responses parser，不用 live phase8 raw 替换证据。当前 live 生产文件漂移后仍可 verify；发前则必须严格匹配。

### 历史依赖的精确边界

phase9 只作为此前已用一次 POST 的总账历史，不参与生成。它的 closed tracker/ledger/receipt/index/provenance 仍由原 closed_binding 读取 live 文件并验证相互 hash 绑定；phase10 不为这些 metadata 建立独立快照。freeze 保存完整 group_at_freeze（含 phase9 row 的 receipt/provenance hash），但这不等于已克隆 phase9 全部原件。

这是既有 closed group 的 fail-closed 完整性约束，与本计划要求的 phase8 生成证据快照及 phase8/9 诊断报告绑定一致，不构成本次阻断问题。历史 metadata 须继续保留且一致；不能笼统声称 phase10 verify 完全不依赖任何 live 历史文件。若以后要求移除全部旧 metadata 后仍能独立回放，应另行设计、测试和冻结。

## 审查者实际离线验证

从 `E:/install_video/backend` 执行以下8项，合成父证据位于 pytest system-temp，网络使用 mock transport：

```powershell
../.venv/Scripts/python.exe -B -m pytest --noconftest -p no:cacheprovider 'tests/test_global_merge_evaluation.py::test_plan_is_new_cap1_only_phase8_leaves_and_offline' 'tests/test_global_merge_evaluation.py::test_single_merge_preserves_old_bytes_preallocates_and_replays' 'tests/test_global_merge_evaluation.py::test_parent_drift_is_refused_before_any_reservation[leaf-response-02.json]' 'tests/test_global_merge_evaluation.py::test_parent_drift_is_refused_before_any_reservation[contrast-request-ledger.json]' 'tests/test_global_merge_evaluation.py::test_missing_closed_phase9_or_wrong_cumulative_count_cannot_allocate' 'tests/test_global_merge_evaluation.py::test_second_request_refused_without_another_send' 'tests/test_global_merge_evaluation.py::test_root_audit_is_required_and_ancestor_mock_project_rejected' 'tests/test_summary_scope_guidance.py::test_global_theme_editing_guidance_is_only_sent_to_final_merge' -q --tb=short
```

结果：**8 passed in 28.23s，exit 0**。覆盖离线计划、实际请求新指导/完整来源/两叶/Pro schema、发前预占、旧字节保护、phase8/phase9 漂移零发送、父15约束、第二请求拒绝、root/mock 隔离及指导仅进入 merge。首次两次收集尝试因工作目录导致的 `ModuleNotFoundError: app` 和误写用例名未运行测试；纠正目录和真实 node ID 后得到上述结果，未改实现以消除失败。

root 另报告新旧目标集合56 passed/98.05s；这是 root 的集成结果，审查者未将其计为亲自执行。

本审查真实 POST 增量 **0**；未运行真实 plan/freeze/run、读取真实 env/凭据、启动服务或修改旧 phase。root 后续最多按 cap1 执行，实际内容仍须独立审阅核心 long1–6、逐断言精度、范围、概览和组织；结构与证据 hash 通过不能代替语义验收，默认与公开长文限制不自动改变。
