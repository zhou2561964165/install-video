# Phase 7 主体范围核查验收工具独立审查

审查日期：2026-10-14。最终结论：Critical 0 / Important 0 / Minor 0。

工程约定：技能优先；UI 使用 primitive→semantic→component 三层 token；保持可配置、窄接口与单向依赖，yt-dlp 仅由 ytdlp_service 接触，视觉层只读 scene。本审查不新增产品协议、不改变默认配置，保护旧验收证据、账号/env 和本地模型。

## 审查范围与方法

依据 `docs/superpowers/specs/2026-10-14-subject-scope-relation-checks.md`，独立只读审查新 `scripts/subject_scope_checks_evaluate.py` 和 `backend/tests/test_long_subject_scope_checks_evaluation.py`；对照 phase6 的 `structured_checks_evaluate.py`、原工具审查、复用的 `pro_review_evaluate.py` / `evaluate.py` 及 fixture 链。

审查者没有运行完整 runner、真实 provider POST、任何 phase 的 freeze/check/run、服务启动或后端全量测试。独立执行的运行时验证仅通过 AST 提取 `caller_guard` 到内存并传入合成路径，未导入完整 runner、创建目录或访问真实账本。此报告为审查者唯一新增文件；phase1–6 原件未修改。

## 初始发现与 scoped re-review

初始 Important（已关闭）：原 `subject_scope_checks_evaluate.py::caller_guard` 只拒绝真实 PROJECT 自身及其子目录，未拒绝祖先。审查版本 SHA-256 为 `F58780BE6D5E387FC079B0D0ED36E44FD9A0D5BBB52C8E6D1D6F35BE1561793A`。将 PROJECT 设为 `E:/`、所有 owned paths 保留在真实 `E:/install_video`，纯 AST 内存实验输出 `ancestor_project_with_live_owned_paths=ACCEPTED`。影响是 injected mock transport 可越过隔离门禁，存在写入真实 phase 账本或结果的风险；建议增加反向祖先关系拒绝和相应零状态访问回归。

实施者报告新增回归先得到 `DID NOT RAISE` 的 RED；审查者未独立重跑该 pytest RED，原缺陷由上述独立内存实验确认。最终修复位于 `scripts/subject_scope_checks_evaluate.py:430`：拒绝真实 PROJECT 自身、子目录及祖先，mock PROJECT 必须为系统 tempfile 的严格子目录，REPORT/CORPUS/GROUP/SHARED_LOCK/RESULTS/TRACKER 全部必须解析到该 PROJECT 内；guard 在 `run:451` 中先于 bind 和任何账本读写。新增回归位于 `backend/tests/test_long_subject_scope_checks_evaluation.py:224`，仅调用 guard，避免 RED 时触碰真实共享锁。

对最终补丁完成 scoped 静态复审及独立 AST 内存实验：ancestor、real、descendant、temp_root、escaped_owned 均 REFUSED，仅 isolated_temp 正例 ACCEPTED。真实调用声明 `(caller, CODEX_ACCEPTANCE_CALLER)` 的 `(None,None)`、`(root,None)`、`(worker,root)`、`(root,worker)` 均 REFUSED，仅 `(root,root)` ACCEPTED。这些检查证明操作声明门禁行为；两处 root 声明是审计与误触发保护，不是不可伪造的身份认证。初始 Important 已关闭，未发现其他未解决 C/I/M。

## 最终路径核对

- `select_phase:61` 只允许 phase-7；不分配或重开 phase1–6。计划、provenance、offline-check 明确记录整数 `phase_post_cap=2`，冻结验证拒绝 bool/float 或其他上限；实际 ordinal guard 不允许第三次 POST。
- `parent_evidence:93` 与 `frozen_sources:242` 固定绑定 closed phase4 的 source、原字幕、response-02、product、provenance、ledger、index、receipt、tracker 与原 codec/normalizer/preparation 快照，逐字节哈希及 receipt 所有权交叉核对。raw02 经原冻结解析器恢复的 public draft 必须等于绑定草稿；phase6 失败 raw/checks 不作为核查或修订输入。
- `candidate_assets:129` 包含生产 schema/config/services、subject 与已有 scope/revision 回归、本工具测试、新 spec、production-final 和本 tool-final 报告。冻结保存报告原字节，后续 live 验证检查资产哈希及清单；本审查稿与测试须稳定后才由 root 执行独立 freeze/check。
- `frozen_sources:303` 以冻结生产 helper 重新构造 prompt、动态 schema 和输出预算；核查为 Responses json_schema，无未声明 strict 参数，14 点预算为 7808、独立上限 8192，旧 review 上限 4096 保持。修订采用声明的 Chat 配置，endpoint、model、source、draft、容量及预算须与 freeze 一致。
- `expected_payload:365` 与 `feedback_from_raw:339` 验证本 phase 的前序 payload/raw 字节及成功核查收据，解析真实 subject feedback 替换 freeze-only 占位；修订只接收这一次成功核查反馈，错误不执行第二次调用。
- `caller_guard:430` 要求真实 `--caller root` 与 `CODEX_ACCEPTANCE_CALLER=root` 同时满足；CLI 暴露该声明。mock 仅允许上述隔离目录，不能触碰真实工作区 owned paths。
- `run:451` 持有共享锁完成整段串行执行，每次发送前重验 freeze、runtime、source/payload/前序 raw。GROUP 累计数、phase ledger 和 tracker 持久预占成功后才 POST；组预算仍 uncapped、累计不清零、不退款、不改旧 closed 账。首错关闭，无自动重试、隐藏 fallback 或新增付费步骤。
- Responses 收据只保存公开 output_text、分类完成状态和非负数值 usage；不保存 reasoning 内容或未知 provider 字段。verify 使用冻结代码/配置/原件哈希，明确 `semantic_quality_verified=False`。运行时显式读取 env 的既有路径不写 `.env`，plan/check/closed verify 不加载 env。

## 实际离线验证及归属

实施者提供的最终稳定版本完整工具套件结果：backend cwd，以下命令 exit code 0，**26 passed in 381.37s (0:06:21)**，无 warnings。审查者读取了对应断言并核对最终文件哈希，但没有独立重跑该套件；这不是审查者自身测试结果，也不与旧 phase 的测试数字合并。

```powershell
& '..\.venv\Scripts\python.exe' -B -m pytest --noconftest -p no:cacheprovider tests/test_long_subject_scope_checks_evaluation.py -q --tb=short
```

实施者另报告修复后 guard 局部 4 passed / 22 deselected in 30.57s。修复前 24 passed 属于初始版本，不作为最终完整通过结果。最终套件覆盖 phase 限制、清单、父字节绑定、原生 schema/反馈、预算不足零分配、篡改拒绝、首请求失败停止、root 声明及 mock 路径隔离；全部模拟调用只在 owned pytest temp 中执行。

最终 Runner SHA-256：`797F512176CDB4F649EAF8C8E1B6F33FD9F0C91A0491F8A049D5B23E17901A2A`。

最终 Test SHA-256：`3D14060885E2A412B40F5D420321ED8BBA8B47F58DDB39CEFFADE88D73D24AF1`。

## 验证边界

可由 root 按独立 plan/freeze/check 后进入 cap=2 的新 phase7；本报告没有实际 freeze 或模型调用。原 closed phase1–6、失败 raw 与账本不重开。结构、连续引用和主体字面归属不证明语义关系正确，模拟套件不证明供应商执行行为，也不证明 P4 或长文整体内容质量已解决；完整实测产出仍需独立内容审阅。默认 legacy/adaptive/single、fidelity=off 和公开 20000 字符入口限制保持。

上述 hash 绑定本次审过的 runner/test；其后若变化，必须对变化完成 scoped re-review，并使本工具审查资产稳定后再 freeze。

临时目录与 injected transport 限制也只是操作约束，不是网络沙箱：任意传入的 Python transport 对象本身仍可执行其自定义行为，门禁不认证调用者、不证明该对象没有网络能力。实际离线套件使用合成 post 函数并将所有 owned 路径隔离；不得据此声称 runner 提供不可绕过的身份或网络安全隔离。
