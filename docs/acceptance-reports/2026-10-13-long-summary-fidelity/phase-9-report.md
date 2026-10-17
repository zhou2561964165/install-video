# Phase 9 原生 schema 合并对照：结构通过，内容未通过

工程约定：成熟组件优先、以窄接口和单向依赖接入，保护用户工作、env、UI、本地模型及全部旧原件。UI如有变动须使用ui-ux-pro-max/design-system并遵循primitive→semantic→component token。本phase未改生产代码/默认配置/旧脚本，未提交、推送或部署。

## 目的与限制

phase8正常模型deepseek-flash用JSON object完整生成，两份已接受leaf为11点和9点；合并响应20点超过14点冻结上限后被拒。phase9只做一次Pro＋Responses原生json_schema合并对照，复用phase8已接受raw01/raw02和完整来源，不重复提取；phase8失败raw03只按父封账验证，不进入新摘要输入。

用户允许整个整改无总POST/费用上限；phase9独立cap=1，输出上限8192tokens、14点上限、format/semantic/extra附加调用均0。root共享锁单caller，发前持久预占，错误即停、无重试/fallback。模型与协议同时改变，结果不能单独归因为schema，也不表示默认Flash已修复。

phase9 provenance SHA256为`29dd7f6407f727a8e553d938cc61c558bfa05c146153ded898192062c20eeeb6`，绑定phase8已closed父组14POST、父失败状态及前两leaf的payload/raw/source/codec/manifest。freeze/check成功且注明network=false、dotenv_read=false。root独立完整离线套件27项通过/60.74s；工具独立审查Critical/Important/Minor均0，必要子集6项通过/18.85s。该证据证明工具和资产边界，不代表内容通过。

## 实际调用与结构结果

**1 POST / 14,710供应商tokens**（input 13,207、output 1,503）。Responses返回HTTP200、status=completed、model=deepseek-v4-pro。raw经完整冻结Responses/Pydantic codec解析，最终输出14个非空要点，结构符合冻结限制。root运行`native_merge_evaluate.py --phase phase-9 --verify`退出码0：evidence_hashes_verified=true、phase_closed=true、posts=1、work_posts=15、stopped_on_error=false、semantic_quality_verified=false。

产品候选保存为[phase9结果](results/phase-9/en-long.json)，wire/raw/父证据与账本见同目录。阶段证据与父长文组计数完整保留；没有将Ragas得分或旧phase状态混入本次结果。

## 独立内容结论

**完整长文内容FAIL。** 独立逐点审阅给出core为4 full / 1 partial / 1 missing；long5只提到表达式有值和意义，没有展开表达式如何求值，按复合准则为partial；long6的赋值绑定、radius重绑、area不自动变化/重执行条件及下一讲控制流全部缺失。14点映射保留phase8第一leaf A1–A11原序，第二leaf仅B1、B2与合并B4+B5；B3、B6–B9未进入成品。报告P2抽奖为“课结束前”，时间锚点正确；P5把四则计算定在计算器实例上，没有复现旧P4明确的类别泛化，但零主语“不能……”仍有歧义。P13仍把原字幕`probably ... most frustrating ...`写成确定判断，精度FAIL。summary事实本身未发现明确错译，但与P11重复课程规划清单、没有覆盖尾部收束，概览职责及全局组织FAIL。详见[逐点内容诊断](phase-9-content-diagnosis.md)。结构通过仅说明本次模型返回了符合14点schema的JSON，不证明语义或coverage通过。

## 当前边界与继续方向

原长文phase1–9累计**15 POST / 218,058供应商tokens**；Ragas独立phase累计16 POST / 34,106 tokens；本次持续整改合计**31 POST / 252,164 tokens**。用户未设整改整体预算上限，但新phase仍须有限POST上限、用途、独立冻结/台账、root共享锁、发前预占及首错停。旧67 POST各组另行封账，账号更换不重置计数。

phase9证明Pro/schema候选处理了phase8的20点结构拒绝，却仍把大部分首leaf列表保留、漏掉重要尾部。不能把结果归因到schema单一因素，不能宣称正常Flash或产品默认已解决。下一轮先只调整通用merge提示：按主题全局合并leaf，不让段落边界决定优先级，检查完整来源尾部，并在有限14点内保存必要条件与结尾关系；保持相同Pro/schema、已付款leaf和容量上限，以单一变量、cap1对照。开发改动须先离线测试/独立审查/freeze/check，结果仍需独立语义审阅。不得重开phase9、用文本删除器裁点、放宽14点或复用失败raw03当草稿。默认仍legacy/adaptive/single、fidelity=off，公开20000字符限制及长文暂不支持保持。
