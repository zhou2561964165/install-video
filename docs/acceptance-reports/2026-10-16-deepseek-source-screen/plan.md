# 第一步：固定DeepSeek Pro的未见来源验证

2026-10-16。用户最新限定“不用改变模型，只使用DeepSeek”，仅完成第一步，后续核查/校订听用户指示。故本轮由跨模型选型收窄为同模型跨来源能力观察；不能得出不同模型孰优结论。

工程约定：适用skills、成熟能力与窄接口优先、单向依赖；yt-dlp唯一层/视觉只读scene，UI用设计技能与三层token；保护已有UI/代码/env/账号/本地模型及全部closed原件。不修改产品、不提交/推送/部署。

## 固定矩阵与预算

| 来源 | 角色 | 请求 |
| --- | --- | --- |
| MIT Lecture1 | 已见开发基线，仅参考phase13单次全文输出 | 复用旧结果，0新增 |
| MIT Lecture2 Branching and Iteration | 之前准备但未在本组真实生成，英文长字幕33710字符（含末尾LF） | 1次 |
| Listening for Success: The Importance of Audio Files (Chinese) | 新获取中文教学访谈，402字符 | 1次 |

新phase15，复用原长文work组/共享锁，parent_posts=21、phase_post_cap=2、planned_posts=2；总任务授权无总上限不影响本phase限额。所有尝试/失败预占计入；错误立即停、零retry/fallback/format/semantic/extra，不为未执行样本借余额重试。顺序英文长→中文短。旧37POST/330302tokens（含Ragas）和旧67另封账不重置。

固定deepseek-v4-pro、官方Responses、普通text、reasoning high、max_output_tokens16384、timeout300s、temperature0.2（思考模式不生效），与phase13同档；全文一次输入，不使用phase14规划或任何修订/自动judge。通用SYSTEM和TASK正文原样复用phase13，只替换来源标题/署名/许可元数据。两source输入各≤60000字符，完整payload≤80000字符，不裁剪。

旧基线只有一次历史结果，不补跑以控制预算；不可拿不同来源的得分变化宣称质量提升比例或统计可靠性。“未见”仅指未在本项目用作模型输出开发，不代表供应商预训练未见；同MIT来源体系的局限须披露。

## 实施边界

新增 `docs/acceptance-reports/2026-10-13-long-summary-fidelity/scripts/deepseek_source_screen.py` 与 `backend/tests/test_deepseek_source_screen.py`。复用旧runner的io/engine/白名单与生产Responses解析，不改旧模块文件。可借phase14纯snapshot helpers，但不得靠修改其全局硬编码绕过parent/cap。

CLI plan/freeze/check/run/verify；plan/check/verify离线不读dotenv/不网络，freeze也无需凭据；run经root双声明+共享锁+hash检查才加载已有DeepSeek凭据。旧phase1–14全closed且累计21才允许分配。

freeze包含本plan、独立工具review、review-criteria.md、manifest/两个source/raw、脚本/测试/实际复用本地依赖资产、库版本、父phase closed metadata及group hash；source和许可元数据均绑定冻结字节。每个source的payload在freeze确定并存档；发前持久预占group/ledger/tracker，任何前面payload/raw/result或冻结资产漂移拒绝下一POST；原始公开文本无改写保存，reasoning/header/凭据不持久化。

每个样本独立成功/错误结果；若第二个失败保留第一份已完成输出但整个phase不称全部完成；未执行样本明确skipped。封账后verify只验证证据与计数、原始响应/结果字节一致，semantic_quality_verified仍false。允许后续doc编辑，但不改旧snapshot/script原件。

## 验证与交付

- 新工具先写最小行为测试并观察缺实现失败；覆盖两个source全文传输、参数、parent21/cap2、预占、root/mock临时隔离、首错停、第二次前首结果漂移、离线不读env/不网络、closed拒重跑/verify、输出白名单。
- 独立代码审查与相关离线测试完成后才root freeze/check/run/verify。无需生产/前端全量。
- 两来源的必要内容与评审标准在模型生成前固定；真实输出只给匿名样本标签供只读审阅，模型身份不用于打分（单模型条件下不能声称模型盲测）。区分确证错误、源内冲突/歧义、可接受教学抽象，允许同段/标题继承明确语境，不临时扩评分要求。
- 记录coverage、核心/次要错误、冗余、实际usage/请求耗时；费用仅按已核实计价做估算，不能把tokens冒充人民币。
- 完成后给两份原样总结、报告和能力边界，停在第一步。绝不自动进入校订、换模型或新phase。

准备记录：中文公开VTT首次httpx TLS连接超时，尚无model POST；随后curl公开GET成功。只用现有字幕解析函数去头/时间戳/标签和相邻重复行，未改写文字；原始VTT保留。未用其他供应商凭据，不再等待额外API配置。
