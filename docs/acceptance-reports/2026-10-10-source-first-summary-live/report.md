# 来源优先新候选首轮实测

2026-10-10。工程约定：当前用户/AGENTS优先，成熟能力复用、可配置窄接口与单向依赖；yt-dlp唯一服务边界、视觉只读scene；UI需ui-ux-pro-max/design-system与三层token。保护用户工作、env/db/账号及全部历史原件。MIT OCW语料/衍生审查按原作者及CC BY-NC-SA4.0归属。

## 实际执行及证据

新source-first-summary-20261010工作组首phase上限5、冻结时group硬上限10。新增工具初始21项、版本定向2项、真实落盘错误定向7项离线通过（重叠不相加），独立审查关闭env/owned写入保护问题。实际freeze/check及独立只读32资产核对通过，新summary_output与实际依赖版本在清单。

root唯一caller串行实际5POST：短1、中1、长分段2+合并1；全部HTTP200/finish_reason=stop，供应商deepseek/modeldeepseek-flash，累计usage **19776 tokens**，没有隐藏重试或付费fallback。phase已closed，snapshot/payload/raw/result/账本/关闭receipt核验通过；stopped_on_error=true是长文最终结构拒绝，不代表HTTP失败。旧26/26、152726 tokens工作组未改。

## 内容与结构结果

| 样本 | 内容/结构结论 | 证据 |
| --- | --- | --- |
| zh-short | zh1–4 full、精度/组织通过本条回归；不是通用准确率 | [短中审查](reviews/short-medium.md) |
| en-medium | en1–3 full，恢复每课评价、持续努力信念与Engrade双能力；en4 partial。summary将通常反馈扩大为每课反馈，文化示例归因/频率仍不足；组织通过 | [短中审查](reviews/short-medium.md) |
| en-long | 最终raw为合法JSON/20点，超过本次14点预算，产品以llm_invalid_response拒绝，success=false。两段分别11/9点符合本段预算；不得将20点raw直接冒充成功结果 | [失败结果](results/en-long.json) |

长文raw作为未接受候选独立阅读：原essential long1–5 full，long6 partial（赋值/area不自动重算核心完整，课程衔接缺少）；P01泛化运行代码安全、P18“前三种”指代不明确、P08/P09控制流重复。相邻主题可以合并并保留全部内容，不能简单删除末6点。详见[长文raw审查](reviews/long-raw-candidate.md)。两段笔记有损且存在精度风险，后续复用时须以完整原字幕校正，不能视为语义已验证。

## 定位与后续修复

同一响应内指导要点→概览和schema顺序不能保证模型实际分工；中篇仍出现跨字段频率泛化。长文合并把11/9段主题生成20点，缺乏充分全局合并。Pydantic结构拒绝与内容评分分开，失败原件不改。

后续选择成熟串行编排，分离最终主题要点和概览生成；长文优先复用已付费的两个分段raw笔记并结合完整原文重新合并，避免重复付费抽取。格式修复最多一次并计账，不删非空内容或自动重跑整pipeline；网络/provider/容量错误仍终止。

用户已授权按任务自主调整有限预算。为覆盖短/中各2个生成步骤及长文2步骤+最多1格式修复，新累计硬上限从10调整为12，修复phase最多7；与首轮5累计最多12。调整原因、父预算及计数在独立continuation台账记录，首phase及10上限原件封账保留，不以新组抹除旧5次。

本页记录的是首轮失败和已定位修复方向，不表示新修复已实施或内容通过。下一phase仍需新代码/离线/独立审查及独立freeze/check；旧首phase不重开，不重新解释原失败为通过。代码未提交/推送/部署。
