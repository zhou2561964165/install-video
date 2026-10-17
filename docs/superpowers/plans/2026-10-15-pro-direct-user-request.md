# 用户委托完整字幕给DeepSeek Pro API

用户2026-10-15明确“本地不跑，完整信息交给Pro”，并确认DeepSeek Pro API。phase13执行已完成。本计划是方案A的历史执行记录；最新决定是方案A优先、确认无法满足要求后再切换方案B，见`docs/summary-route-decision-2026-10-15.md`。本次执行没有运行分段/合并/语义核查或本地模型推理。

工程约定：成熟接口优先、窄接口、单向依赖；保护UI、账号/env、模型与closed证据。UI依旧须ui-ux-pro-max/design-system及三层token；yt-dlp唯一服务层、视觉只读scene。

phase13有限上限1 POST，用途为将现存MIT Lecture1完整字幕34,894字符一次交给deepseek-v4-pro。开始累计长文18POST/254644tokens；Ragas16/34106，合计34/288750，旧67另封账。root唯一caller/共享锁/发前持久预占/首错停，零retry/fallback。旧phase1–12不可重开。

使用官方Responses文本输出、reasoning high、max_output_tokens=16384（含供应商思考及可见输出），timeout300秒。与phase11/12不同，本次不走生产摘要提示/JSON合同/14或15条限制；仅传通用忠实总结任务与全文，条数由Pro决定，有限token预算保持。来源/模型/格式/思考/提示多因素变化，不作单因素因果对照。

本地只传输并保存原文、payload、供应商公开响应、最终文本和账本。复用既有HTTP库、生产Responses完成状态解析、已有安全响应白名单、共享锁及封账写入，不启动服务、不运行本地summary pipeline或语义评分器。凭据只读配置并放请求头，不进入payload/快照/日志；供应商reasoning内容不持久保存。

独立只读审查后freeze，原文字节/尾部与冻结哈希核对后单次run。成功仅记“Pro已返回文本”，不宣称其内容经过独立语义验收；若失败记录原件并封账，不自动补发。结果以独立文件交付；不改产品默认或公开20,000字符入口。

协议依据：https://api-docs.deepseek.com/api/create-response/ ，本次已打开核实text类型、high和包含思考的max_output_tokens。软件不新增依赖。
