# 首轮长文来源保真验收

工程约定：Superpowers及适用skills优先；成熟能力、配置化窄接口/单向依赖，yt-dlp唯一层/视觉只读scene；UI采用ui-ux-pro-max/design-system及三层token。保护已有工作、账号/env、模型资源及历史原字节。

2026-10-14记录，phase-1于UTC 2026-10-13结束。结论：结构与证据链通过，内容仍失败，长文公开入口尚未恢复。

## 实际执行

用户明确本任务不设总POST/费用预算；逐次预占、共享caller锁、root串行、错误停止仍生效。旧67POST各组封账不变，本组phase-1共3POST、供应商51662tokens，全部HTTP200/stop，format/semantic额外0。正常两叶+合并，没有隐藏fallback。Provider/model为deepseek/deepseek-flash，显式thinking enabled，输出base16384/ceiling24576、主题上限14；不是产品默认profile。

相邻重复折叠后的来源34894字符，两段各8点源语言笔记；合并source_context分别20000/14893字符，原文及全部笔记均实际进入请求，无middle省略。最终14点。原文进入模型不是语义保证。

freeze/check/run/verify完成。provenance SHA-256 `bc41c59218b321dee28781af5154db660b4b8f1d38b6f4355bfd89027d991f5d`，最终result SHA-256 `f851d818b0d85bc059bef47d74eb18ab61272f4b8d74c10b3c9db1d130ea5765`。全部snapshot、payload、raw、result、ledger与closed receipt保持原字节。机械verify明确`semantic_quality_verified=false`。

## 内容审阅

独立[逐源审阅](reviews/phase-1-long.md)：coverage **5full/1partial/0missing**，precision **FAIL**，overview/organization **PASS**。

- P4将具体旧计算器的限制推广为固定程序计算机类别，仍失败。
- long6只缺下一讲控制流衔接，末尾重绑定/area不自动重算与显式重算已经准确。
- 时间锚点、实际抽奖演示、算术前三种子集、求值及不同pi示例重新核对通过。旧错误标签不能继承。

新证据支持单独来源校订候选，见[后续设计](../../superpowers/specs/2026-10-14-long-summary-revision-design.md)。后续另建phase复用精确草稿，不重开本phase，结果必须重新全内容评分。

## 离线验证与范围

输入修复及历史测试fixture隔离后，后端明确tests目录全量**1847 passed / 424.56s**。随后新增单次校订不属于这次全量记录；其验证另记。不把离线通过写成内容质量通过，不把显式高预算候选写成默认已升级。

来源归属：Dr. Ana Bell / MIT OpenCourseWare，*Lecture 1: What is Computation?*，来源与派生审阅沿冻结manifest的CC BY-NC-SA4.0，保留归属及相同许可。完整来源/许可详情见本phase manifest和独立审阅，MIT不背书模型或产品。
