# Phase 10 全局主题合并提示对照：结构通过，内容结论待独立审阅

工程约定：优先复用成熟组件、窄接口与单向依赖，保护用户工作、账号/env、本地模型、UI与历史证据。UI如变更须使用ui-ux-pro-max/design-system及primitive→semantic→component三层token。本phase没有改公共接口、默认模型/策略、UI或旧脚本。

## 验证目标

phase9同样使用Pro/Responses原生json_schema、相同的phase8两份accepted leaves及完整source，并在14点结构上通过，但核心long6尾部机制和下一讲衔接仍缺失，组织/overview FAIL。phase10只改变`merge=True`请求的通用合并指导：跨所有section notes按主题编辑、不把段落顺序当最终point顺序、完整source要复查后段的条件/结论/过渡。模型、Responses/schema、叶notes、输入与输出预算、point上限、retry/fallback配置全部保持phase9相同，作为一个prompt变量的对照。

## 有限phase预算与工具检查

用户已授权整个整改无总POST/费用预算；phase10独立cap=1 POST、8192 output tokens、14点上限，format/semantic/extra=0。root共享锁/单caller/发前持久预占/首错停。起始时长文组15POST/218058tokens，Ragas组16POST/34106tokens，合计31POST/252164tokens；旧67POST组另外封账。

phase10 freeze/check成功，provenance SHA256 `0745cb907d9e40704f65070f77af60d8c70ed15418f6d76f953c540798e45622`，parent_posts=15，planned_posts=1；配置Pro/Responses/json_schema、reasoning none。payload快照含新增merge guidance及phase8两份accepted leaves；不使用phase8失败raw03或phase9输出作为输入。offline receipt记录network=false/dotenv_read=false。

TDD观察两类RED（缺少merge guidance测试1 fail，phase10入口缺失测试1 fail）。实现者阶段18项测试通过/56.98s，scope 11+native回归27共38通过/43.14s；root独立合计目标集**56 passed/98.05s，exit0**。独立工具审查C/I/M均0，审查者8项定点通过/28.23s。审查者两次pytest收集失败因cwd/import与误写node id未执行测试，纠正后报告实际8项，不将未执行用例计为通过。工具报告`reviews/phase-10-global-merge-tool.md`。

## 实际调用

唯一请求已消耗：**1 POST / 14,793供应商tokens**（input13,279、output1,514），Responses HTTP200、status=completed、model=deepseek-v4-pro。原生schema包含`maxItems=14`，输出14个非空点，严格冻结codec接受。root `global_merge_evaluate.py --phase phase-10 --verify`退出码0：evidence_hashes_verified=true、phase_closed=true、posts=1、work_posts=16、stopped_on_error=false、semantic_quality_verified=false。产品结果见[phase10结果](results/phase-10/en-long.json)，raw、wire、账本及receipt同目录，phase10不重开。

## 独立内容审阅

**Phase10整体内容FAIL，long core仍4 full / 1 partial / 1 missing。** long5只提表达式有值/意义，未展开求值过程；long6的名字绑定、radius重绑、area不自动变化及重执行条件、下一讲控制流全部未保留。14点映射与phase9完全相同：A1–A11→P1–P11、B1→P12、B2→P13、B4+B5→P14；B3/B6–B9仍缺失。跨段主题归并/概览组织未改善。

P2抽奖时间从phase9的“课结束前”回退成“课前”，明确精度失败；P13仍丢`probably`评价模态。P5限制在文法上挂到具体计算器，未复现旧P4明确类别泛化，但“不能”仍省略主语，保留实例锚定风险。summary事实精度没有新明确错译，但课程规划清单与P11重复、只覆盖前段。

独立review核对phase9与phase10 wire：除user input新增426字符通用merge指导外，模型、schema、reasoning、temperature、输出预算、section/source_context/summary/key_points都相同；两份section内容逐结构对应phase8已接受leaf。phase10没有按新增指导恢复后段信息。这是一个已见来源、固定leaf上的单次对照，不能推广成该提示对任何输入都无效。[逐点诊断](phase-10-content-diagnosis.md)记录source行及P/A/B映射。14点schema接受不构成语义/coverage结论。

## 当前边界

原长文组phase1–10合计**16 POST / 232,851供应商tokens**；Ragas独立组16 POST / 34,106 tokens；本轮持续整改合计**32 POST / 266,957 tokens**。旧67 POST各组另保留，换GPT账号不清零。phase10 cap已消耗；任何续验需另行记录有限用途/上限并新建phase。

phase10本次通用提示没有改善产物；不继续添加同义merge句子或仅凭结构重复收费。历史审计已确认points-only→overview和同响应theme_plan均试过；新phase11候选是source 34,894<60,000的单次direct summary，cap1，Pro/schema/14/8192，复用现有`_summary_request(merge=False)`不传notes，作为路线诊断。它改变generation path，不能说成正常分段/merge产品通过，也不恢复入口。
