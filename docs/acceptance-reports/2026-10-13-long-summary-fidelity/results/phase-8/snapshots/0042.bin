# Phase 7 主体范围核查生产候选独立审查

审查日期：2026-10-14。最终结论：Critical 0 / Important 0 / Minor 0。

工程约定：复用现有 Pydantic v2、PydanticOutputParser、Responses `json_schema` 与 LCEL 固定串行路径；保持窄接口、单向依赖、可配置和最小充分修改。未新增公共 facts 协议、公共响应字段或依赖。旧验收原始证据、账号/env 和本地模型保持；本报告不改旧结论，也不代表已解决 P4。

## 范围与方法

依据 `docs/superpowers/specs/2026-10-14-subject-scope-relation-checks.md`，只读审查以下生产实现和新测试：

- `backend/app/config.py`
- `backend/app/services/summary_review.py`
- `backend/app/services/llm_service.py`
- `backend/tests/test_summary_subject_checks.py`

同时阅读既有 `summary_pipeline.py` 与 `test_summary_source_review.py`，核对串行错误停止和兼容行为。审查未执行真实模型请求、freeze、服务启动、提交或推送；本报告是唯一新增文件。

## 初始发现、修复与 scoped re-review

初始 Minor：`summary_review.py::parse_subject_checks` 使用 `re.sub(r"\s+", " ", text).strip()`，折叠所有空白，超过设计与提示只允许行分隔规范化的边界。纯内存离线实验中，来源 `This calculator only adds.` 与引文 `This  calculator only adds.`（行内多一个空格）被接受，结果为 `inline_space_rewrite_accepted=True`。影响是新模式可能接受修改了行内空白的引文；该问题没有形成内容语义通过结论。

最小修复建议是为 subject_checks 单独收窄规范化，不修改旧 checks，并补充拒绝行内空白改写的回归。实施者随后报告先得到失败回归，再完成修复。审查者未独立运行修复前的新失败回归，因此该 RED 过程仅作为实施者报告记录。

Scoped re-review 已读取最新 `parse_subject_checks`：专用 `line_breaks_to_space` 仅将行分隔符转换为空格，保留行内空白；主体和引文绑定均使用该规范化。旧 `parse_checks` 未改变。新增 `test_subject_quote_normalizes_line_breaks_but_preserves_inline_whitespace` 覆盖合法行分隔及行内双空格改写拒绝。最新相关测试通过，初始 Minor 已关闭。

后续测试补充复审：在上述复审后，测试文件再新增9个参数化执行用例，覆盖根目标缺失/额外键、拼接引文拒绝、null evidence 保留、布尔/0/65537非法配置、保存14点草稿的7808接受及7807零请求拒绝、重复 JSON target 键导致单次核查后停止。已只读检查这些新增断言：拼接引文没有触发无关字段或长度错误；预算正例核对真实请求体的7808输出上限和15个必需目标，反例核对错误类别及零请求；重复键由原始 JSON 字符串构造，避免先转字典丢失重复键。null 路径只验证字段保留，不宣称语义判断正确。合成14点草稿和模拟 supported 响应用于结构/预算测试，不作为来源忠实性样本。

未发现新增测试误报或共享 fixture 副作用：每次 `subject_checks()` 返回新的嵌套字典，测试不修改全局 SOURCE/DRAFT；请求记录在各测试内部，保存草稿预算正反例之间显式清空。复用的 `configured` fixture 和各测试配置变更均由函数级 monkeypatch 恢复，新 `Settings` 实例不替换全局 settings。行分隔/行内空白回归继续有效。

## 最终生产检查

- 动态根目标和每目标六字段均必需；额外字段禁止。主体/引文使用严格字符串或显式 null，长度有限，空白字符串拒绝。
- supported 要求 same 关系、两主体与来源引文非 null；来源主体绑定其引文，草稿主体绑定实际目标，引文连续归属于来源。反馈保留字段并按目标顺序传给修订，不自动将 uncertain/null 改成 supported。
- subject_checks 强制通过已有 Responses `json_schema` 传输发送动态 schema。LCEL 固定 review→revision，解析或请求错误即停止，无隐藏重试或付费回退。
- 核查输出按 `128 + 512 × (key_points数量 + 1)` 计算，14点为7808 tokens；完整多段生成在首个上游请求前检查预算，保存草稿按实际点数预检。独立 `LLM_SUMMARY_SUBJECT_CHECKS_MAX_OUTPUT_TOKENS` 默认8192，类型和有限范围校验存在。
- 默认 fidelity=off 保持，旧 checks 的4096预算与解析行为隔离；本候选不恢复公开长文，不改变公共输出协议或引入额外依赖。

上述核对未发现未解决的 Critical、Important 或 Minor。

## 实际离线验证

工作目录：`E:\install_video\backend`。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'E:\install_video\.venv\Scripts\python.exe' -B -m pytest --noconftest -p no:cacheprovider tests/test_summary_subject_checks.py tests/test_summary_source_review.py -q
```

修复前相关两文件42 passed；初次修复后实际43 passed in 0.77s。新增9项边界用例后，审查者再次实际执行上述同一命令，最新结果52 passed in 0.80s，exit code 0。最初从仓库根目录运行时因未提供 backend 导入路径而发生 `ModuleNotFoundError: app` 收集失败；切换为上述工作目录后成功，未将该失败写为通过。

Root 提供的当前相关集成结果：调用方为 root 主 Agent，工作目录同为 `E:\install_video\backend`；root 报告实际执行以下相关五文件集合，结果121 passed in 0.58s。此条按 root 提供的执行结果记录，审查者没有独立重跑这五文件集合，不与审查者自身43/52项结果合并计数。

```powershell
& 'E:\install_video\.venv\Scripts\python.exe' -B -m pytest --noconftest -p no:cacheprovider --basetemp E:\install_video\tmp\phase7-production-20261014 tests/test_summary_subject_checks.py tests/test_complete_source_checks.py tests/test_summary_scope_guidance.py tests/test_summary_source_review.py tests/test_summary_source_revision.py -q
```

## 验证边界

MockTransport 和结构回归不能证明供应商遵循 schema、主体关系或谓词判断正确，也不能证明 P4 已解决。程序验证结构、目标位置及子串/连续引用归属，不证明实例是否被泛化成类别；需要新 phase 的实际输出及独立语义审阅。

新增用例补齐了此前指出的重复 JSON target 键、根目标缺失/额外键及保存草稿路径7808/7807预算边界。52项通过仍不是对所有字段组合、所有 Unicode/空白输入或真实供应商行为的穷举，也不能表述为总体内容质量通过。本审查未重新运行后端全量或其他旧验收，不重开任何旧 phase。
