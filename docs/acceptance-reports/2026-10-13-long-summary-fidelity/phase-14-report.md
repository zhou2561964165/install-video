# Phase14 完整来源＋独立主题规划组合实测

2026-10-16整理。**两次调用成功、封账一致，最终内容仍FAIL。** 完整性改善，准确性与重复仍未通过。[独立内容报告与版本对比](phase-14-content-diagnosis.md)。

工程约定：适用skills、成熟LCEL/Pydantic、窄接口/单向依赖；yt-dlp唯一层、视觉只读scene、UI按设计技能与三层token。保护env/账号/既有UI/本机模型及closed原件，发布继续过滤模型历史。新增内容仅为验收适配器、相关测试和文档；未提交/推送/部署。

## 实际执行

用户要求A/B结合并继续；新独立phase14 cap2，父长文19。两次均完整34894字符MIT Lecture1，没有切段摘要、全局merge或本地模型：

| 调用 | 任务与协议 | input | output | total |
| --- | --- | ---: | ---: | ---: |
| 1 | Pro/Responses json_schema、reasoning none、4096上限，独立列主题 | 8999 | 108 | 9107 |
| 2 | Pro/Responses普通文本、reasoning high、16384上限，全文＋可纠错主题导航自由写作 | 9270 | 7677 | 16947 |
| 合计 | 2/2 POST，无format/semantic/extra/retry/fallback | 18269 | 7785 | **26054** |

规划返回12个标题，严格结构校验后保存accepted-plan。全文写作返回8293字符、15个自然章节，另附十条结论；这些不受14/15点硬合同约束。输出供应商计数包含reasoning，不等于可见回答tokens；reasoning内容未落盘。

参数协议核对[DeepSeek Responses官方文档](https://api-docs.deepseek.com/api/create-response/)：本次使用json_schema/text、none/high与max_output_tokens；没有未列明strict参数或隐式能力探针。temperature沿旧值，官方说明思考模式中它不生效，不将其当写作确定性保证。

## 工具验证与证据

- root新离线套件32 passed/89.08s，独立工具审查C/I/M=0/0/0；[审查文件](reviews/phase-14-planned-direct-tool.md)。没有重跑生产/前端全量。恢复时没有初始RED记录，不追认它。
- root完成plan→freeze→check→run→verify。plan/check无网络与dotenv；run共享锁串行，发前group/ledger/tracker持久预占，首错停止。
- phase14已closed，实际2POST；verify exit0、work_posts21、stopped_on_error=false、semantic_quality_verified=false。后者保留机械验证与内容审阅的区别。
- provenance SHA `81806e353c139fca968cccde2d220f3dc9758157b2061159fbb4de49a572445d`；result SHA `cca6370feb032f9b738896923e47736d445bad239631c172db99d99ac8dd75cb`。
- source SHA `c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7`；answer SHA `71faf1d83e7b98ca635ca2dd116a9ca1050959a6f1b60fc98e4ae64fea04cdc4`；accepted-plan SHA `7283c37ab0a33d8d6e695189494c81ded5a1fece8c112b0c2f5c49988f197f44`。
- 冻结快照内设计/计划保留执行前状态，不为勾完清单而改冻结版本；本报告及当前交接记录实际完成情况。

## 内容与成本结论

三组独立只读审阅后root复核：long1–6全部full，overview PASS，precision FAIL，organization FAIL。原A遗漏的可读/模块化代码和效率比较均恢复；仍把下课前写成课前。末尾新增“类型转换会截断”泛化，并重复正文十条；另有除法/重绑独立结论的限定不足，报告明确记录审阅分歧。没有用删错句或降低标准换取通过。

相对A的phase13，token成本15498→26054，增加约68.1%；可见字符5206→8293，增加约59.3%。完整性改善不等于整体质量按相同比例增长。只有一个已见来源，不能归因成规划引擎普遍提升，不能恢复默认/公开长文。

长文phase1–14共**21 POST /296196供应商tokens**，逐phase响应usage独立求和与台账一致；Ragas独立16/34106，当前持续整改共**37 POST /330302tokens**，旧67另封账。phase14用满、不可重开；本轮后续文档与导出0POST。

## 交付与后续

原样导出在[`exports/planned-pro-direct-2026-10-15/`](../../../exports/planned-pro-direct-2026-10-15/)：完整字幕、原VTT、accepted-plan、Pro回答和README；[zip包](../../../exports/planned-pro-direct-2026-10-15.zip)。导出是原文结果，不是修正后的合格摘要。

下一步先零POST分析新增末尾回顾的压缩与重复、时间关系未解决的原因，再决定独立有限复验；不在本phase自动重写或回退。默认legacy/adaptive/single/fidelityoff、公开20000字符保护和长文暂不支持继续适用。来源及派生材料保留Dr. Ana Bell / MIT OpenCourseWare，CC BY-NC-SA4.0署名，MIT不背书模型回答。
