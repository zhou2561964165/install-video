# 长文来源保真整改：暂停报告

2026-10-14用户指令：「先暂停，然后更新文档等下一次测试」。当前仅文档维护，模型验收与开发暂停。**长文精度仍失败，公开入口未恢复；没有新的总体质量PASS。**

工程约定：用户/AGENTS/适用skills优先，成熟能力、配置化窄接口/单向依赖，yt-dlp唯一层/视觉只读scene；UI采用ui-ux-pro-max/design-system三层token。保护已有工作、账号/env、本地模型及历史原证据；原freeze/script/raw/ledger/receipt/result不改。

## 累计及phase实际结果

本任务没有总POST/费用预算，仍逐次持久预占/root共享锁串行/错误停止。旧26+17+8+16=67POST各历史组仍closed，不借用、不重置。本组五phase全部closed，**9POST/147600供应商tokens**。

| Phase | POST / tokens | Provenance SHA-256 | 结构/内容或错误 |
| --- | --- | --- | --- |
| 1 | 3 / 51662 | bc41c59218b321dee28781af5154db660b4b8f1d38b6f4355bfd89027d991f5d | 源语言两叶各8点，完整source_context20000/14893；最终14点。5full/1partial，精度FAIL |
| 2 | 1 / 26699 | 78cb03aec395a466a52d1f41918c308f4457c81b987d7b9bbb0cb054e524b149 | 复用1草稿自校订，6full，P4范围FAIL |
| 3 | 2 / 25830 | e75b00fd1d1a243909052f383642c44c974d7276a15ef023a7c216aa74ed43fa | Flash反馈→修订，最终文件与2完全等SHA，P4仍FAIL |
| 4 | 2 / 27502 | d087b2b2d71800c0b67e01a37724239cef6f5c052e7fe3ab5091fcdd0bfb1944 | Pro显式对照，6full/精度FAIL，业务文字与2完全相同 |
| 5 | 1 / 15907 | 599688f5eca51d001910b064d7760e5cd4ddc36a38a2b0e45d2fcefb1ce539b1 | checks输出4096 completion，length截断、llm_incomplete_response，停止未修订 |

独立内容依据：[phase1](reviews/phase-1-long.md)、[phase2](reviews/phase-2-long.md)、[phase4](reviews/phase-4-long.md)，同[评分准则](review-criteria.md)。phase3源/result业务全同phase2，机械file SHA相等；此处明确以字节/来源相等解释失败，不伪称新独立审阅通过。最后完整有效产品为phase4，result SHA `8c013c57882d281817ac017992a1c6fa138705e52b776a674e2dc08c510be616`。

## 已完成实现及真实缺陷

字幕摘要输入现在只折叠相邻重复，修复跨语境枚举被删除；内部叶笔记默认source，最终按用户语言；完整原文可装下时优先传给merge。这些实际进入phase1请求，不能单凭更多原文保证质量。

自校订及LCEL独立反馈→修订、PydanticOutputParser完整checks均已实现为显式off默认候选，无新SDK/第三方追踪或付费retry/fallback。公有summary/key_points保持，基础4096/ceiling8192、14主题及20000公开正文上限保持。真实阶段profile/config按自身冻结阅读，Pro候选不等于默认模型升级。

**仍有两个具体阻断：**

- 旧计算器实例范围被推广至固定程序类别。phase2/4所有6核心、概览与组织通过，只有这个已确认内容精度错误仍在；时间/算术子集/求值/area重算/下一讲衔接已恢复，不重报旧错误。
- phase5虽要求概览+14点各一次，raw实际上target0五次、1三次等，按子断言扩写并含拼接/ellipsis。生成达到4096 token而截断。只发1POST，第二次未预占/发送；错误/原raw及receipt保留，没有可交付的新结果，局部检查片段不转记语义PASS。完整json_object成功、目标覆盖和quote归属仍不等于范围准确。

## 证据与验证解释

五phase各自freeze/check/run/verify均已执行；失败phase5亦核原件/计数/关闭，其`semantic_quality_verified=false`，`stopped_on_error=true`。这表示失败被准确保留，不表示模型内容通过。phase5错误result SHA `c7e3c46d1d9386e9c59ee3c22d6b9166196d903aa60ef1ae6e0987c9712440fb`，closed receipt SHA `4ff6ebe143811b4d536fc000286b122a39ed0362f4d3306581a571b91dff4056`。

离线输入修复阶段全量1847passed/424.56s在新校订之前；最新相关7文件197passed/0.84s，非当前全量。checks生产76项相关通过；工具28项通过后，新增target-count及超容量各一项分别验证，不写成最后30项全跑。完整生成工具统一packet SHA gate修复有2项RED→27pass，后补锁/orphan3项单独通过，总29未重跑全29。独立生产/工具审查的覆盖Minor已补，未重新执行真实模型或扩大质量结论。

未见MIT Lecture2只准备官方字幕与独立[8核心准则](unseen-review-criteria.md)，0POST。正常完整新流程和短中回归尚未实测；本报告不能恢复长文入口。暂停后的文档维护没有触发新tests/service/freeze/模型调用。

来源及派生审阅归属Dr. Ana Bell / Massachusetts Institute of Technology / MIT OpenCourseWare，CC BY-NC-SA4.0，沿各冻结manifest保留署名与许可，MIT不背书此模型或产品。

下一次执行前读取[当前交接](../../handoff-2026-10-14-long-summary.md)，先离线处理已定位缺陷、独立审查再新phase；原阶段不重开、计数不清零。任务暂停只记录在当前文档/计划，不改任何closed台账。全部代码及既有UI仍未提交/推送/部署。
