# 原生JSON Schema及模型有限对照

工程约定：当前用户/AGENTS与skill优先；成熟接口实际复用、窄接口/单向依赖/可配置，yt-dlp唯一服务层、视觉只读scene；UI需ui-ux-pro-max/design-system与三层token。保护全部失败原件与其它工作。

## 实测依据与选择

阶段2长文points输出20项与两段笔记按序连接完全一致；一次format输出逐字相同。输入未超限，8192输出预算未耗尽、finish_reason=stop，因此增加重跑次数或简单把点数放宽至20不能纠正全局合并/精度。双角色已实现，但Flash概览仍复述细节且丢限定。

本轮仅作原生协议/模型配置对照，复用已经实现的LCEL/Pydantic和Responses传输，不增加新框架或事实协议：

- 使用供应商文档支持的`text.format=json_schema`，让points-only/overview-only schema随请求传给服务，而非仅json_object/提示中描述约束。
- 选择`deepseek-v4-pro`、reasoning effort none，不使用新账号/新key或修改本地env；root冻结显式配置后调用。两角色正常各1、三源共6，禁format/semantic自动重试。
- 原raw source完整、长文继续复用原2条付费leaf并以完整原文纠正；14主题/原覆盖与限定/重复标准保持。不能把schema或模型名称当作结果保证。
- API/schema模型选择都是现有显式选项；候选通过前默认single/既有模型不静默改变。若通过，只按实测配置发布可用配置说明，不把Flash旧结果转记Pro。

官方依据（2026-10-10查询）：[Models](https://api-docs.deepseek.com/quick_start/pricing/)列deepseek-flash与deepseek-v4-pro及Responses支持；[Responses API](https://api-docs.deepseek.com/api/create-response/)定义json_schema与reasoning.none；[兼容表](https://api-docs.deepseek.com/guides/responses_api/)说明text.format支持、未知参数可能被忽略，故不额外发未列出的strict开关。

## 预算与验收

前阶段累计11（首5+次6）且全部closed。用户持续授权自主预算，本轮从累计12上限调整至17，最多新增6POST；父12/已用11原件封账，新的continuation绑定父hash及全部11请求，不重置。仍单caller、持久预占、错误即停，不以隐藏probe/fallback追加。

新验收入口复用已审预算/冻结/父raw绑定；针对新Responses安全receipt/usage/完成状态、动态模型/endpoint与双role最终对应做新增离线验证及独立审查，然后新freeze/check、root实际6POST。不得原地改旧runner/results。

多项配置同时变化是有目的的候选对照，不能将改善独立归因于schema或模型某一项。最终以原语义准则判断，失败不增加无上限调用；结果文档、可复现配置与未解决边界均准确发布到个人私有GitHub。
