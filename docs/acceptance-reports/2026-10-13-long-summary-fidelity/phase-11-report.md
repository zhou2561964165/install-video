# Phase 11 完整来源直入诊断报告

日期：2026-10-15。phase11以单次完整来源请求检验：此前的long core遗漏是否与叶笔记/分段合并输入有关。结论：**工具边界与封账通过；内容仍FAIL，不是长文问题已解决。**

工程约定：复用既有生成、Responses、freeze/check/run/verify和持久预占层；窄适配、单向依赖，不更改默认产品、生产代码、公开API、既有phase原件、用户账号/env、本地模型或UI。UI工作另需 `ui-ux-pro-max`、`design-system`和primitive→semantic→component tokens。MIT来源保留署名和CC BY-NC-SA 4.0。本阶段没有提交、推送或部署。

## 冻结设计与执行

- 本phase冻结单一已见MIT Lecture1来源：完整规范化文本34,894字符，绑定phase10的来源/VTT/manifest和许可证署名哈希。超60,000字符会在请求前拒绝，不截断。
- 与phase10相比采用独立direct-source路径：生产 `_summary_request(..., merge=False, source_chars=len(source))`，不传叶notes或旧summary；其余保持DeepSeek Pro、Responses `json_schema`、reasoning none、maxItems14、8192 max output tokens、`fidelity=off`。这次配置不能单独归因“去掉notes”，也不代表默认分段Flash产品路径。
- phase cap=1 POST；freeze/check完成后root以唯一caller执行一次，无format/semantic/extra、retry或fallback。冻结prompt与实际wire一致；全量source原样进入Transcript。供应商返回HTTP200/completed，input 9,989、output 820、total 10,809 tokens（cached input 768）。
- 实际 POST：**1/1**；长文工作组累计由16变17。请求成功，14点通过结构解码。闭账verify确认全部phase快照/ledger/receipt哈希，`stopped_on_error=false`、`semantic_quality_verified=false`；verify是证据一致性，不是内容通过。

## 离线开发与审查

先按TDD复现source及manifest同步漂移会在旧实现漏过，再补充phase10 source身份绑定与拒绝回归。候选runner与测试最终SHA-256：

- `scripts/direct_source_evaluate.py`：`e080c2b80f5c8564469ed99e4faab0d75e49c8eb3f54ba8343548dd284e2f4f9`
- `backend/tests/test_direct_source_evaluation.py`：`6908f3d95200844aa0a7b171d6fdeb788377e6d3a16193fe211c75f174ae3eb4`
- provenance：`fc5e0501c48bfb6a096d1d9d6fbb418296c7125c1cbbb46dec51ffefabd0190e`

实现者执行：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'E:/install_video/.venv/Scripts/python.exe' -B -m pytest --noconftest -p no:cacheprovider backend/tests/test_direct_source_evaluation.py -x -q
```

结果 **34 passed in 143.25s，exit 0**。覆盖真实冻结MIT来源payload capture（无网络）、全source/尾部/schema/14-8192、phase10/累计16绑定、manifest/source/metadata同步漂移拒绝、cap1与发前预占、root/mock guard、首错停止、离线check与冻结快照回放。此前观察到来源同步漂移测试RED；修复后全部通过。

独立工具审查：最终C/I/M **0/0/0**，初审发现的source身份Important在最终哈希版本复核已解决。审查只读，未运行测试、freeze、env、服务或POST。独立内容审阅另见[phase11内容诊断](phase-11-content-diagnosis.md)。

root实际运行 `--plan` 得 `phase_post_cap=1`、parent count16、network/dotenv=false；`--freeze`成功；`--check`返回freeze_valid=true、network/dotenv=false；唯一一次 `--run` 后立即 `--verify`，结果哈希全部核实，phase closed。

## 内容结论

[独立逐项内容诊断](phase-11-content-diagnosis.md)：long1–4 full，long5/6 partial，0 missing；precision FAIL；overview/organization PASS。P11缺“对象类型决定可用操作”；P10静态语义错误被Python捕获的断言遗漏“执行到出错分支”条件；P14把具体radius旧值失去句柄及area未自动更新推广成一般规则，且缺显式重算area的条件与下一讲控制流。核心尾部内容从phase9/10的多项遗漏改善，但仍不满足全部核心/精度门。

phase9/10的P2“课结束前→课前”、计算器类别范围和P13 `probably`问题本次未再输出对应事实，属于未覆盖，不是这些错误已被纠正。**本phase不是整体内容PASS，不恢复默认、不取消公开20,000字符入口限制、不声明正常Flash分段路径或未见长文已解决。**

## 总账与后续

长文工作组phase1–11累计 **17 POST / 243,660 supplier tokens**；独立Ragas组16 POST / 34,106 tokens。当前持续整改合计 **33 POST / 277,766 tokens**；此前67 POST历史组独立封账。换GPT账号不清零；后续每phase仍独立设置有限cap、原因与台账，root共享锁串行、发前持久预占、首错停。

下一候选只检验一个资源假设：本source按adaptive公式的可用要点数为15，当前冻结candidate上限14且实际返回14点。新phase拟只把候选点上限14→15，其余来源、模型、输入路线、提示与8192输出不变，cap=1；用来判断14点上限是否挤掉必要条件。它不改默认、不预设通过，也不扩展总预算。本phase1POST和全部失败评分保持closed；phase11的source/raw/product、freeze、ledger、receipt及旧phase均不改。
