# 2026-10-11 总结内容验收恢复

工程约定：最新用户/AGENTS/skills优先；UI须专业skills及三层token；成熟能力复用、可配置窄接口和单向依赖，yt-dlp唯一服务层、视觉只读scene。保护凭据、账号、本地模型与旧验收原字节。

## 首阶段实际结果

用户已明确恢复内容验收。新工作组上限10POST，首phase已closed5POST（短1/中1/长两段及合并3）、44968供应商tokens，HTTP均200/stop；--verify确认32冻结资产、raw/result/ledger链及闭账。剩余最多5仅用于已定位并离线验证/独立审查修复后的新phase，见[本地规范化修复复验](../2026-10-11-summary-content-local-repair/report.md)。全部旧26/17/8仍封账，不把结构或旧评分算新内容通过。

| 样本 | 结构 | 覆盖/精度/组织 | 内容结果 |
| --- | --- | --- | --- |
| zh-short | 5点通过 | zh1–4全部full，精度/组织通过 | PASS，限定此冻结输出 |
| en-medium | 4点通过 | en1–4全部full，通常反馈/Engrade完整能力/信念与课堂例子范围保留；精度/组织通过 | PASS，限定此冻结输出 |
| en-long | 原JSON末尾缺数组闭合，14完整点但被拒 | 仅零POST诊断：long1–6full、组织通过；时间锚点、计算器例子类别及运算子集范围精度失败 | 产品FAIL，诊断内容也FAIL，不能转记为通过 |

审查：[短中篇](reviews/short-medium.md)、[长文零POST诊断](reviews/long-diagnostic.md)。诊断只在最后}前插入一个]且全部字符串相同，原failed结果/raw/账本不改；48项成熟Pydantic无损规范化及3项service接线红绿已验证，原真实raw回放一致。JSON格式修复不会自动修正内容。

旧默认single来源提示、输出层、分段与预算通过AST/字符串比对确认与首source-first phase相同；注入可选_request和显式staged分支不会改变当前single。复用旧真实baseline而不再次收费：中篇评分→反馈频率扩大、文化归因/频率问题；长文merge20点等于两段11+9连接、超14，且有安全范围及指代问题。原文完整、raw/result相同及finish_reason/usage证据排除了codec删除和此次容量截断。Pro/schema历史缺陷按Pro候选单列，不能套给默认输出。

## 显式候选与预算

沿用现有legacy/adaptive/single、Pydantic及HTTP接口，deepseek-flash、json_object、thinking enabled。基础8192/ceiling16384输出tokens、最多14主题；正常仍1/1/3，format/semantic额外0，不发送隐式探针/隐藏fallback或恢复框架试验。候选配置改变不能单因素归因；产品默认和本机.env尚未更改。

新入口导入复用成熟source-first runner的冻结/漂移/预占/闭账/raw净化和同一共享caller锁，而不是重写通用执行器。所有历史父文件sha与closed/实际计数绑定：旧独立26，source-first17，归档框架1+7=8；历史总51，其中linked25=17+8不双算，新已用计数独立累计且不抹旧记录。

现有接口支持的协议依据：[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)及[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。显式有限max_tokens保留，不持久reasoning_content/凭据或向第三方发送遥测。

## 内容标准与范围

逐短中长原essential必要子句、全部字段实质断言、频率/模态/主体/条件/作用范围/归因、概览与要点互补/重复判定；详见[本轮准则](review-criteria.md)。真实自然字幕与评分语料复用MIT OCW/原作者及CC BY-NC-SA4.0许可，不增添样本答案、固定字数成功门槛、删点器或facts默认协议。

当前首phase结论已经分别评分，整体未通过，旧26/17/8账本及此phase所有freeze/raw/receipt保持原字节。第二phase不重开这里，不继承旧评分；HTTP200/schema/结构不会自动记为内容通过。思考模式候选暂不提升为产品默认；多个参数共同变化，不作单因素归因。
