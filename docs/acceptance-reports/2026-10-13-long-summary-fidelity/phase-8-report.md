# phase8 最新指导的正常完整生成：合并超限，失败封账

工程约定：成熟组件优先、窄接口与单向依赖，保护既有UI/账号/env/本地模型和历史证据。UI如改须ui-ux-pro-max/design-system三层token。本轮不改生产默认、旧脚本或公开入口，没有提交/推送/部署。

## 目的与冻结

此前phase6/7核查的草稿来自尚无最新类别/实例/代词指导的phase1生成。为区分旧草稿漏判与最新生成效果，本phase重新生成完整已见Lecture1的两段笔记并合并，不复用旧错误笔记，不追加judge或修订。

本phase有限cap3、format/semantic/extra均0；用户仍授权整个整改无总POST/费用上限，root共享锁串行、发前持久预占、首错停。新`normal_evaluate.py`只适配旧会计/来源/freeze/实际summarize_text，不复制HTTP引擎；代码159行，独立工具审查C/I/M均0。实现者新27+旧41集成68 passed/32.24s；root独立27 passed/5.30s，审查者subset9 passed/18 deselected。没有重跑生产或前端历史全量。

profile为legacy/adaptive/single/fidelityoff，thinking/response auto，输出4096/有限ceiling8192；provider/model沿当前配置，实际`deepseek-flash`与Chat Completions，不静默升级Pro。完整source文件34894字符、清理后34893字符，两leaf、最终最多14点。freeze/check通过，provenance SHA256 `ec24e6c826261a9ec573678210684611cd8de268c354dea80d44e1af2002c3cf`，parent_posts11，phase planned_posts3，offline-check network=false/dotenv_read=false。

工具review里的计划hash是四项Task1完成状态勾选前版本；freeze绑定勾选后状态版。root只读逆向恢复这四处状态/验证记录及追加进度说明，SHA精确恢复为review中`8853eeaad0964759dc59b821c5fc3f15cde1c9cda4516e38cee3cfe35f3e4f4c`，确认要求/设计/代码无改动；没有重写冻结原件。

## 实际结果

**3/3 POST、28376供应商tokens，closed失败。** 两个leaf分别返回11点和9点且被生产路径接受；merge返回完整JSON，但有20点，超过冻结14点，触发`llm_invalid_response`。这不是网络/截断错误；system实际要求1–14及combine/deduplicate，JSON object仅要求语法，不约束数组数量。没有自动修复、额外调用或最终产品结果。

| POST | 阶段 | raw点数 | 供应商tokens |
| --- | --- | ---: | ---: |
| 1 | extract | 11 | 7424 |
| 2 | extract | 9 | 5947 |
| 3 | merge | 20（拒绝） | 15005 |

root `normal_evaluate.py --phase phase-8 --verify`返回exit0、evidence_hashes_verified=true、phase_closed=true、posts3、work_posts14、stopped_on_error=true、semantic_quality_verified=false。验证证明原件一致，不能写成总结通过。[失败结果](results/phase-8/en-long.json)、[raw merge](results/phase-8/response-03.json)、[台账](results/phase-8/request-ledger.json)与[closed receipt](results/phase-8/closed-receipt.json)保持原字节。

## 内容诊断与后续边界

第一leaf把四则/不能绘图等限制写在`a calculator that ...`的例子中，与旧类别主语不同；raw merge的中文仍须独立检查。20点未接受，不能作为产品改善或P4通过。独立范围、覆盖、精度及是否逐条串接笔记的诊断见[内容诊断](phase-8-content-diagnosis.md)。

不为取得通过放宽14或删除raw要点。若下一步采用原生schema/明确模型候选，仅可另建有限phase，并优先复用本轮已成功笔记，避免再付费提取；不能使用失败raw merge冒充接受草稿。来源/候选/成本差异和语义结果必须分别记录，不升级默认或重开本phase。

## 计数

原长文组phase1–8均closed，累计**14POST/203348tokens**；Ragas独立closed16POST/34106tokens，持续整改合计30POST/237454tokens，旧67POST各组另保留。当前整体质量仍未解决；未见Lecture2和短中回归仍未实测，默认与公开20000字符限制保持。
