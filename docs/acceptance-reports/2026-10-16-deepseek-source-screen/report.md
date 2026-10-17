# 第一步完成：仅DeepSeek的未见来源单次全文验证

2026-10-16。用户要求只用DeepSeek、先完成第一步、后续听指示。本轮实际**2/2 POST、23275供应商tokens**，已closed且verify一致。没有进入规划、核查、局部修订、跨模型或产品接入。[内容结论](content-review.md)：英文长7/8核心完整、1项缺转换前提并有局部退出条件错误；中文短4/4核心完整、未发现确证核心事实错误，但重复扩写明显。

工程约定：适用skills、成熟io/engine/Responses白名单/共享锁复用，窄接口/单向依赖；yt-dlp唯一层/scene只读，UI须设计技能及三层token；保护env/账号/本机模型、既有代码/UI与closed原件。只新增验收工具/测试/新样本与报告；未修改产品默认或公开20000字符保护，未提交/推送/部署。

## 范围、来源与固定配置

[执行计划](plan.md)和[生成前准则](review-criteria.md)在freeze中绑定。基线复用phase13已封账的MIT Lecture1单次全文原结果，0追加调用。两新来源见[manifest](corpus/manifest.json)：

| 来源 | 输入 | 输出 | 身份SHA256 |
| --- | ---: | ---: | --- |
| Lecture2: Branching and Iteration | 33710字符，含末尾LF | 4888字符 | source `4e8a1ba805030af1a1d61fad202ce4661d8009cca324b5bd2280ae3ccc11a128`；answer `8a1b1517abb09da638cc8fd689df70876f7396af4f57a6b6a71145bc9744523f` |
| Listening for Success (Chinese) | 402字符 | 1112字符 | source `90acdee254a5293b6f1def16f0d0bc90f4941fe1a5b516df91a36d2269a7f1b4`；answer `736b06a22806c5b3c32ab21b3960aecfa236431740e4823e2a40cda338cbe53a` |

只用已授权DeepSeek凭据；deepseek-v4-pro，官方Responses普通text，reasoning high，max_output_tokens16384，timeout300s，HTTP retries0，format/semantic/extra均0。通用SYSTEM/TASK正文沿phase13，只替换来源标题/署名/许可；不发评审准则或参考答案，全文不截断。输出可见字符不是供应商output tokens，后者包含思考；reasoning内容未持久化。[协议依据](https://api-docs.deepseek.com/api/create-response/)。

## 实际调用、耗时与成本

phase15 cap2、parent21、共享caller锁、root双声明、发前持久预占，依英文长→中文短串行。两次HTTP200/completed，各样本只生成一次；没有失败重试、隐藏fallback或后续校订。

| 样本 | input tokens | output tokens | total | cached input | 预占至响应 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 英文长 | 9139 | 10652 | 19791 | 0 | 113.037秒 |
| 中文短 | 538 | 2946 | 3484 | 256 | 37.926秒 |
| 合计 | 9677 | 13598 | **23275** | 256 | 约151秒 |

耗时取ledger reserved_utc至response received_utc，含持久化等开销，不冒充纯网络推理计时。两次均在2026-10-16 05:22–05:25 UTC，按当日[官网价格](https://api-docs.deepseek.com/quick_start/pricing/)非高峰USD档估算：9421未缓存输入×$0.66/M＋256缓存输入×$0.022/M＋13598输出×$1.98/M≈**$0.03315**。这是公开费率估计，不是账户实扣账单，也不换算人民币或查询余额。

长文工作组phase1–15全部closed，**23 POST/319471tokens**；Ragas独立16/34106，持续整改合计**39 POST/353577tokens**，旧67另封账。换账号/本次收窄任务不清零历史。

## 离线验证与审查

新runner `scripts/deepseek_source_screen.py`、新测试`backend/tests/test_deepseek_source_screen.py`。实施初期缺runner是1failed/23errors；实际封账路径两次23passed/1failed先后暴露live父证据和snapshot损坏时阻断close，均保留日志。最终**24 passed/56.72s**，独立工具局部复核C/I/M=0/0/0。[冻结审查](../2026-10-13-long-summary-fidelity/reviews/phase-15-deepseek-source-tool.md)。没有重跑生产/前端全量。

独立来源审阅在生成前修正中文口语歧义、允许语境继承和相邻主题合并，未降低必要机制标准；细节见审查记录。模型输出后没有修改冻结准则。

root完成plan/freeze/check/run/verify：provenance SHA `3160b10297b28602f108c4a101fde759f7092c8224244751018345974801bfe1`，实际posts2、work_posts23、stopped_on_error=false。verify的semantic_quality_verified=false保留，内容审阅独立记录，机械核验不替代语义。

## 交付与停止边界

原样回答、source、原VTT与manifest在[导出目录](../../../exports/deepseek-step1-2026-10-16/)，[压缩包](../../../exports/deepseek-step1-2026-10-16.zip)。没有本地改写、删错句或修复输出。两来源内容结论与产品可用性分开；单次每来源、小样本、同MIT体系、语言/长度/体裁混杂均限制泛化。

**第一步已完成，停在这里。** 不自动开启第二步核查、第三步编辑、新phase、提示优化或部署。phase15用满封账，不重开、不借余额。后续由用户指示。

来源与派生材料保留Dr. Ana Bell / Dr. Haohsiang Liao / Massachusetts Institute of Technology / MIT OpenCourseWare及CC BY-NC-SA4.0署名与相同方式共享；MIT不背书模型总结。
