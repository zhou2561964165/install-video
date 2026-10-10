# LCEL阶段分离候选实测

2026-10-10。工程约定：用户/AGENTS与skill优先；成熟库复用、窄接口/可配置/单向依赖，yt-dlp唯一层、视觉只读scene；UI需ui-ux-pro-max/design-system三层token。原失败、来源许可、env/db/账号及其它工作保护。MIT OCW/原作者与CC BY-NC-SA4.0沿用语料manifest。

## 已执行与资源

- production相关170项通过，极深JSON/超长整数解码终止分类修复后11项定向通过；独立复审无未关Critical/Important。新caller恢复后真实12 failed/5 passed→compiler dont_inherit修复后17 passed；不把错误cwd导入错误计为行为红测。
- root实际freeze/check与独立81资产/父5核对通过。langchain-core1.6.9、langsmith0.14.7固定，外部追踪禁用；完整原文、两role schema与原leaf关联保留。
- root唯一caller实际6POST：短points+overview、中points+overview、长points+points_format；均HTTP200/stop。格式调用1，原长文leaf3/4复用、没有重付抽取。
- phase已closed，snapshot/payload/raw/trace/双role result/ledger/receipt核验通过；stopped_on_error=true是长文两次仍超主题上限。usage **28851 tokens**；新工作组累计 **11POST/48627tokens**。旧26/26/152726tokens原件保持。

## 独立内容结论

| 样本 | 覆盖 | 总体 |
| --- | --- | --- |
| zh-short | zh1–4全full | fail：概览复述具体起始安排和渠道，P1/P6无新增相关内容重复；完整性不能抵消组织失败 |
| en-medium | en1–4全full；文化P5归因及“有时”通过 | fail：overview丢课后及书面反馈两个usually，且P1/P4与overview实质重复 |
| en-long | 未接受raw：long1–5保留，long6缺下一讲控制流衔接 | 结构fail，overview未生成；raw精度/组织亦有问题，不能冒充产品通过 |

证据：[短中独立审查](reviews/short-medium.md)、[长文诊断](reviews/long-raw-diagnostic.md)。长文raw05与raw06正文逐字一致，20点完全等于首阶段两个leaf数组11+9按序拼接；不是输出token耗尽。单靠分离请求未改善本条概览互补，单靠一次format未使模型实际合并。

## 后续有限对照与发布边界

不降低原标准、不删最后6点、不把主题上限放宽成20来掩盖失败。继续复用已实现框架/codec/完整来源，采用[原生schema及Pro模型有限对照](../../superpowers/specs/2026-10-10-schema-pro-summary-design.md)，供应商官方支持的Responses/json_schema、deepseek-v4-pro(reasoning none)，禁自动format/semantic。

用户自主预算持续有效：父12上限closed/已用11保留，continuation累计上限17、最多新增6；全部已用11绑定计数，不退款/重开/隐藏probe。多配置同时变化，不能独立归因改善于单一因素。新freeze/离线/审查后执行；现defaultsingle仍保留，staged/框架安装不代表质量解决。

用户已授权个人GitHub推送；需真实结果、设计/使用边界同步与集成验证后提交，保留所有原件字节，排除tmp/private环境/账号。此报告不宣称阶段分离候选通过或已有新Pro输出。
