# 全局主题合并提示与单次长文复验

工程约定：优先复用成熟组件，保持窄接口、单向依赖和最小充分修改；保护用户工作、UI/账号/env/本地模型及旧验收原件。UI变更须使用ui-ux-pro-max/design-system和primitive→semantic→component三层token。本任务不改UI、默认模型/模式或公开长度入口。

## 根因和目标

phase9 Pro/Responses/json_schema单次合并确实把输出限制在14点内，但独立评分仍FAIL：14点大体按原序保留leaf1的A1–A11，仅追加leaf2少量内容；B3/B6–B9和long6完全漏失，P13评价概率限定仍被强化，概览职责与组织FAIL。phase8/9的完整source均可见，因此剩余根因是跨段notes没有真正全局编辑和尾部对照；不能放宽14、截断点或更换judge称为修复。

## 单phase预算与输入

新的phase10最多**1 POST**，用途只检验一条通用merge指导是否促成主题级归并及保留完整来源尾部必要信息。实际供应商model/protocol不变为`deepseek-v4-pro`、Responses原生`json_schema`、reasoning none；8192 output tokens、14点、format/semantic/extra均0。仅修改本方案merge提示，为phase9同模型/格式/来源/leaf的单变量对照。

复用phase8已接受raw01/raw02（11/9点）及完整source；不使用phase8失败raw03或phase9失败内容作为输入。不重做leaf，不新增样本答案、逐点facts协议或本地删点器。若仍FAIL，阶段首错停并封账。

发起本阶段之前长文组15POST/218058供应商tokens，Ragas组16POST/34106 tokens，合计本轮31POST/252164tokens；旧67POST各组另封账。换GPT账号不重置。采用root共享锁/唯一caller/发前持久预占，cap=1；执行不得超出此数。

## 改动边界

- 修改`backend/app/services/llm_service.py`中仅`merge=True`生效的通用`request_guidance`：明确跨所有notes主题归并、段落顺序不决定最终point顺序、不要照搬首段再追加少量后段、用完整source在有限point内复查后段核心条件/结论/过渡，同时保留“合并去重但不丢独立内容”的自适应目标。
- `backend/tests/test_summary_scope_guidance.py`先RED后GREEN：从现有请求捕获行为验证这些通用要求只进入final merge guidance，不改变leaf prompt、schema、max_points、retry或调用数。
- 新增专项薄runner `scripts/global_merge_evaluate.py`及测试`backend/tests/test_global_merge_evaluation.py`，通过窄wrapper复用phase9的HTTP/accounting/Responses证据/父phase8 leaf校验，不改phase8/9 runner。新冻结绑定更新的生产service、需求测试、新计划、新runner/测试、phase8/9结果报告及独立工具review。
- phase10父证据仍只读核验phase8成功leaf，与phase9结果不混用。新的输出raw/content必须原生completed、model/profile、schema与14点都匹配，之后Pydantic strict codec接受；旧原件字节保护。

## 步骤和验证

1. 对merge提示先新增失败测试并观察RED；实现最小通用说明后确认新测试GREEN及相关scope/summary路径。
2. wrapper离线测试覆盖cap1、严格phase8 leaf来源、freeze/check/verify、父raw漂移零预占、caller/mock隔离和第二请求零发送。保护已冻结phase9脚本、结果、ledger、review和本计划。
3. 独立代码审查Critical/Important为0，修复后重新检查受影响测试。root plan/freeze/check确认父15、cap1、同Pro/schema profile、payload新merge指导。
4. root唯一caller最多1 POST；实际结果另做核心long1–6、逐断言精度、概览/组织独立内容审阅。schema接受不等于内容通过。

只有通过phase10且独立内容审阅认可，才考虑新的Flash正常profile对照；该后续阶段仍需单独有限预算。无论phase10结果如何，默认`legacy/adaptive/single/fidelity=off`和公开20000字符长文限制不自动变更。
