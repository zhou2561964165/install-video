# 有限事实槽与全局主题分配：离线交付准备

用户要求多agent并行继续[前轮合同复审](../2026-10-07-grounded-summary-final/contract-review.md)后，本轮在既有n+2流程内实施有限事实槽、全局主题分配和独立验收入口。当前真实新预算尚未授权，不调用模型，不将离线结构回归称为总结质量通过。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system与primitive → semantic → component三层token，颜色/字体/时长走token。能力配置化、窄接口单向依赖，避免大规模重构；LLM仅llm_service.py、yt-dlp仅ytdlp_service.py，视觉只读scene，不修改下载状态或导入核心。用户.env/db/模型资产、历史报告/源码快照/台账保持。默认legacy、正常n+2，无自动失败重试或隐藏付费回退。MIT来源和衍生评测保留署名、CC BY-NC-SA4.0非商业和相同方式共享要求，见[原许可](../2026-10-04-natural-subtitle-quality/corpus/LICENSE.md)。

## 本轮变化

详细接口与限制见[设计](../../superpowers/specs/2026-10-07-grounded-summary-contracts-design.md)和[计划](../../superpowers/plans/2026-10-07-grounded-summary-contracts.md)。三个独立写集并行：纯codec，LLM编排/合法fixture迁移，新phase/checker。

- extract改为配置化fact_1…fact_N固定槽，默认12，闲置只能尾部null；新纯parse_extraction使用原来源/归因/字段校验。额外第13槽、缺槽、间隙等拒绝，不丢事实或静默接受旧数组。
- 同一次compose响应包含至多7个主题槽的theme_plan。每主题明确principle、conditions、consequences与已知fact_ids；纯parse_planned_composition校验主题和point的对应引用，产出原CandidateSummary与不可变主题计划。
- caller给主题ID，原候选、完整source/facts、missing_core诊断和主题计划传给唯一既定audit。audit仍返回原additional_facts/output/checks，公开API和正常请求的隐私边界保持。
- 旧parse_facts/parse_composition/parse_candidate/parse_audit纯接口保持，历史原件仍按冻结codec检查。有限槽和规划只是生成/结构合同，不证明源含义完整或供应商不会违约。

## 保持的边界

extract事实数仍默认12；候选摘要默认≤14条/1600字符，最终摘要默认≤7条/800字符，最终要点≤7个/每点240字符。候选要点数也≤7，长度沿用既有max(max_claim_chars,max_point_chars)修订余量、默认600字符，唯一audit可修订，最终仍严格240；本轮没有新增放宽。阶段预算/默认配置保持；实际输入容量计入完整主题计划，超容量不删原文、事实或计划。旧已验证core不重标降级，模型阶段不增加、失败不重试或付费回退。

前轮organization-final9/13、长无最终结果和短中7full/1partial保持原样；新协议尚无真实最终输出，不能声称解决成绩录入遗漏、主题碎片或汉字姓名来源支持问题。原14essential/rubric和三源不改，也不作为产品提示的答案。

## 验证与实测准备

截至2026-10-08，三个任务及最终整体修复的独立复审全部通过，当前修订的主agent后端全量为 **706 passed、1条既有Starlette弃用提示，20.34秒**。首次701/24.52秒属于最终checker修复前的阶段记录，不替代本次706验证。

```powershell
# backend目录，完整源码tests，不收集旧tmp权限目录
../.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp E:/install_video/tmp/contracts-final-20261008
```

独立审查和红绿修复记录：

- Task1：新接口原先会自动解码嵌套JSON字符串；修复仅新入口的对象类型guard，顶层rawJSON和旧parser兼容保留。10例真实红→绿，相关183项通过，独立scoped复审通过。
- Task2：合法fixture容器迁移原先把非法尾部None转成合法空槽；现在非法None/非dict/缺字段/引用类型保持非法，13事实与8要点也不裁剪。真实pipeline红→绿，相关69项通过，独立复审通过。
- Task3：新wrapper/checker原先接受重复JSON字段及bool/float序号。新层严格读取artifact、精确整数身份/计数guard，旧代码不改；23例红→绿，新55专项/129组合通过，独立复审通过。
- 最终整体审查发现checker普通容器等值比较会把audit事实行号true/1.0与int1视为相等。4个重哈希真实check_phase回归先红→绿，新增类型敏感JSON比较覆盖新合同绑定，保留对象键无序、数组有序和tuple到JSON数组规范化；原60专项/134组合通过，整体scoped复审关闭唯一Important。生产代码和旧模块没有因这次checker修复而修改。

最终审查无未解决Critical/Important/Minor。legacy/translation及公开结果形状的原回归继续包含在706全量中；本轮未改UI，不以历史前端/浏览器结果称重新验证。

新默认plan已由主agent执行，显示独立organization-contracts、13POST、network=false。稳定代码已实际零网络freeze，随后check-only `match=true`；完整[module/config/codec/prompt/source/rubric及有效runner/checker链provenance](results/organization-contracts-provenance.json)、三源码快照和[当前交付记录](results/code-delivery.json)已保存。尚无started/ledger/真实结果，模型请求为0。

```powershell
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-contracts/scripts/evaluate.py
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-contracts/scripts/evaluate.py --freeze
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-07-grounded-summary-contracts/scripts/evaluate.py --check-only
```

上述准备不发送模型请求；runtime内部读取本地供应商配置，不打印/保存API key、不修改.env。全部351历史材料和用户.env/db哈希与本轮初始一致。当前实现、新测试与证据尚未新建提交。

主agent本轮开始固定351份历史报告/脚本/源码/JSON证据身份以及本地.env和用户数据库哈希，提交前/交付前复核；仅在本机记录身份，不打印凭据。现有未提交工作保留，工作区不reset/clean、worker不git commit。

新organization-contracts必须使用独立phase和13POST预计预算（短3/中3/长7），旧四轮余额均不借用、不重置、不续跑失败phase。新默认plan零网络，freeze/check仅本地配置读取；真实预算明确授权后root单caller串行、发前持久预占、错误即停。

新checker除原来源/哈希/预算/最终audit合同检查外，核对已验证raw extract/compose与trace的事实、候选和主题计划，以及audit输入规划与trace一致；received失败阶段不能算已验证结果。离线替身与协议容器迁移不作为模型质量成功。

本轮已提出最多13模型POST的新预算确认，等待用户明确答复；先前开发中的“继续”仅承接实现，不自动视为新phase计费授权。获授权后单次运行、失败原件保留，再独立审核原14复合事实、可选细节精度、归因/频率/范围和主题组织。默认legacy不推广，不能宣称已修复前轮全部语义缺口。
