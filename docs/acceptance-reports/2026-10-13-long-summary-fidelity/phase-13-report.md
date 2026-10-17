# 完整字幕直接委托DeepSeek Pro：用户请求结果

2026-10-15用户要求“本地不跑，把完整信息交给DeepSeek Pro API”。已完成**1次POST，HTTP200/completed，原样保存5206字符可见回答**。本地只传送与保存，没有分段/合并、本地模型、测试套件或语义评分。新文本语义未独立评分，不沿用phase12分数，也不记总体PASS。

工程约定：成熟HTTP/解析/白名单及会计接口复用，窄接口/单向依赖；yt-dlp唯一层、视觉只读scene；UI须设计技能/三层token。保护账号/env、旧phase、本机模型和已有UI。未改产品默认、提交、推送或部署。

## 实际请求与交付

完整MIT Lecture1规范化字幕34894字符一次发送，源SHA `c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7`，与历史冻结原文一致。模型deepseek-v4-pro，Responses普通文本、reasoning high、有限max_output_tokens16384（含思考及可见输出）、timeout300秒。不强制JSON/14或15点/固定字数；通用任务只要求中文概览和完整详细主题，保留来源条件与范围。多个参数变化，不作单因素因果对照。

供应商usage：input9127/output6371/total15498，cached0。output是供应商计数，不等同可见文本tokens；不持久保存reasoning文本。

交付文件：`exports/pro-direct-2026-10-15/full-transcript.txt`、`original-subtitles.vtt`、`pro-summary.md`及来源README；压缩包`exports/pro-direct-2026-10-15.zip`。回答未本地改写，来源与派生材料保留Dr. Ana Bell / Massachusetts Institute of Technology / MIT OpenCourseWare，Lecture 1: What is Computation?，CC BY-NC-SA4.0，MIT不背书输出。

原件在`results/phase-13/`，包含全文、provenance、payload、白名单response、原始可见文本、产品/ledger/index/closed receipt。provenance SHA `3b7dba0e8e483ae5b37cb2f716213f2d3619f17d876b6c2884ccb5194097e9fd`。

## 传送与会计

独立只读静态审查最终Critical/Important 0/0，修复error/incomplete白名单标记适配后复核；依用户要求未跑本地测试/pipeline/judge。原文hash、请求和导出字节核对仅验证传送完整性。

phase13 cap1已closed，root共享锁、发前group/ledger/tracker持久预占，HTTP retries=0，无重试/回退。凭据仅请求头，不写env/headers/日志；响应reasoning排除。旧phase1–12原件不改。

长文累计**19POST/270142tokens**，Ragas另16/34106，持续整改共**35POST/304248tokens**；旧67另封账，不因账号或网络恢复清零。成功仅表示收到Pro文本，默认legacy/adaptive/single/fidelityoff、产品14点与公开20000字符保护未升级。主题写作候选未实施。

协议依据：[DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)，本次已核实text/high/max_output_tokens定义。
