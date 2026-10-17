# 一次原生schema合并对照

> 执行：superpowers:subagent-driven-development；沿既有单caller/冻结/台账，不重复实现HTTP引擎。

工程约定：成熟组件与窄接口/单向依赖；保护旧证据、UI/账号/env/本地模型。UI如改须ui-ux-pro-max/design-system三层token。本轮不改产品默认、生产代码或旧脚本。

## 依据与有限范围

phase8正常Flash/JSON object完整生成已closed3POST：两个成功leaf为11/9点，merge20点超过冻结14而拒绝；完整prompt53416字符可容纳。该具体结构失败说明仅自然语言数量要求不足。已有生产Responses/Pydantic output_schema与显式Pro/schema曾验证14点结构，允许做一次对照，不再付费提取相同leaf。

**新phase9 cap=1**：只复用phase8前两份成功笔记及完整原source，调用既有生产`_summary_merge_contexts`→`_section_notes`→`_summary_request(...merge=True)`；不输入失败raw03或伪造父成功产品。显式候选model=deepseek-v4-pro、response_format=json_schema、thinking=disabled（Responses effort=none），输出上限8192、点上限14不变，format/semantic/extra均0。模型与格式同时变化，不能单独归因schema；更不能写成默认Flash修复或总体语义通过。

用户持续授权任务无总POST/费用上限，此阶段仍有限1。发前历史：原长文组14POST/203348tokens+Ragas16/34106，合计30POST/237454tokens；旧67POST各组另保留。root共享锁串行/持久预占/首错停，新phase独立freeze/ledger/tracker，绝不重开phase8。

## 唯一实现任务

新文件`scripts/native_merge_evaluate.py`（本长文报告目录）及`backend/tests/test_native_merge_evaluation.py`。私有导入复用既有evaluate的run/会计/check/close，不复制HTTP caller。因旧freeze固定三阶段，专项freeze只构建单merge阶段及完整资产绑定；不补写旧冻结原件。

1. TDD验证父失败只允许第三次merge且前两leaf成功/原codec接受，raw01/02及payload01/02/source/manifest/VTT/parent provenance/ledger/receipt/index/tracker/group封账行均绑定。父live漂移在新POST前拒绝；离线verify按本phase保存的父快照重放，不借live父文件掩盖证据。
2. 完整来源、源准备函数、leaf顺序/预算、codec和实际merge输入逐字核对；native请求由生产生成，不手写第二套协议。断言单merge/cap1，超预算、状态/model/结构不符立即停；第二次零发送。
3. Responses证据/内容复用历史schema-Pro的成熟接口，保存安全原生object/status/output/usage并排除reasoning/headers/key。校验原生completed，不制造chat finish_reason代替真实完成状态；最终经冻结JSON/Pydantic与14点规则解析。
4. root双审计和mock system-temp/owned containment保留；help/plan/check/verify零dotenv/零HTTP。资产包含新代码/test/本计划、生产、相关scope回归及独立工具review `reviews/phase-9-native-merge-tool.md`。
5. root执行相关离线复核及独立spec/quality审查后才plan/freeze/check/run。输出完整时独立审P4/原6核心/逐断言精度/组织；结构通过不是语义通过，未见/短中仍须后续实测。

审计适配预期250–350行，不扩为通用框架、不新增公共facts协议、样本答案或删点器，不扩大14/8192。实际状态另记progress/report，冻结后本计划保持不变。没有提交、推送、部署或恢复公开入口。
