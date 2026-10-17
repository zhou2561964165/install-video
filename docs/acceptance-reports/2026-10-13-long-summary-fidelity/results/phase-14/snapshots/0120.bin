# 完整来源＋独立主题规划：A/B 组合候选

2026-10-15。用户明确“两方案可以结合起来”并继续，当前采用两次调用的有限验收适配器。此设计替代纯 B 分块/逐主题写作的当前执行入口；A、B 历史设计均保留。

工程约定：适用 skills、成熟组件优先、配置化窄接口/单向依赖；yt-dlp 仅经唯一层，视觉只读 scene，UI 须 ui-ux-pro-max/design-system 和三层 token。保护既有代码、账号/env、UI、本地模型和全部 closed 原件；发布仍过滤 Live2D 历史。

## 目标与已确认范围

A 的 phase13 long1–6 全 full，但时间矛盾、具体计算器实例范围、两项课程路线遗漏和局部重复未过验收。当前并不证明 A 整条路线不可用。按用户要求，保留 A 的完整原文和自由篇幅，用 B 的独立主题规划帮助组织输出。

首轮仅新增验收脚本与其离线测试，不接产品默认/公开 API。已有来源 MIT Lecture1 的原文、标题、署名与许可完全沿 phase13；不会把旧回答或评分、课程参考答案输入模型。

## 固定两次职责

1. **规划**：完整字幕＋通用规划任务 → `{"topics":["主题标题", ...]}`。由 Pro/Responses json_schema 输出；1–12 个非空、各不超过 120 字符且去首尾空白/casefold 后不重复的标题。只作主题导航，不生成事实判决、正文、点数配额或源码块路由。Pydantic strict/extra forbid 校验，重复 JSON 字段拒绝；非法则停止，不发第二次。
2. **全文写作**：完整字幕＋已接受主题标题＋phase13 通用总结任务 → 自由 Markdown 中文概览和详细主题。规划是可纠错的辅助数据，原文优先；模型可补充规划遗漏，标题不替代来源。保留 phase13 普通文本、reasoning high、16384 output tokens；不强制14/15点或字数，不切字删点。

两次均由 DeepSeek Pro API 完成；本地仅做结构校验、传输与会计。LCEL RunnableSequence/RunnableLambda 实际串行执行 plan→generate，构造和调用均在关闭追踪上下文中。无逐块摘要、最终合并或自动语义 judge。

这与历史同响应 theme_plan 不同：规划独立完成并被下一次请求实际携带。但程序仍不能保证模型使用规划或保留全部条件；只按最终真实输出评估，不声称主题标题齐全就等于内容完整。

## 参数、容量与成本

独立 phase14，cap=2 POST，父长文累计19；成功后最多21，含Ragas最多37，旧67另封账。新增阶段用途为同一来源的组合路线验证；format/semantic/extra均0，首错停止，余额不用于重复生成。

- 规划：deepseek-v4-pro、Responses json_schema、reasoning none、max_output_tokens4096。
- 写作：同模型/endpoint、Responses普通文本、reasoning high、max_output_tokens16384。
- 总输出上限20480 tokens（供应商定义，写作包含思考）；每次timeout300秒、HTTP retries0。
- 原文≤60000字符；两种完整请求按确定JSON序列化≤80000字符。先用最大合法规划的保守JSON长度预检写作请求，再在第二POST前检查实际payload，不截断原文。字符边界不是供应商token/window证明。
- 第一规划同样含完整原文，写作原文与phase13输入逐字一致。完整传输、字段类型和HTTP成功只证明机械条件。

写作配置与phase13保持，增加规划阶段及导航上下文。单样本随机生成和规划内容变化仍存在，不宣称严格单因果证明；不把额外规划消耗漏记或改产品下载额度。

## 实施与证据

新增 `scripts/planned_direct_delegate.py` 与 `backend/tests/test_planned_direct_delegation.py`；复用旧脚本的来源身份、现有response白名单/Responses完成解析、持久写入、共享锁与closed会计基础。不修改旧脚本，不读取凭据配置做工具连接。

新脚本提供 plan/freeze/check/run/verify。plan/check/verify纯离线、不加载dotenv、不访问网络；freeze仅冻结公开endpoint/模型/参数与资产，无须凭据。只有run加载已有授权凭据，且root caller/锁/父组与全部hash检查在加载runtime前完成。

freeze保存完整source、两个模板、schema、配置、runner/测试/审查/所用依赖代码资产快照和hash、父phase13 receipt/ledger/provenance/index/result/响应/输入身份及父组hash。旧13个phase全部closed才能新建。

每次发送前：再验证候选资产与既有阶段payload/raw/parsed plan hash→持久保存实际payload→预占group/tracker/ledger→串行POST→白名单raw落盘→解析。第一次成功后保存已接受规划；第二次必须来自该原件，不以任意live规划替代。发生错误立即封账，无第二预占或隐藏重试；未知结果的已预占尝试仍计入。

最终仅在两次都成功后保存原样回答。部分规划/失败raw仅保留诊断，不当产品成功。请求凭据仅header、reasoning文本不落盘；第三方遥测关闭。旧phase和账本原件不改。

## 验证与验收

TDD仅覆盖新适配器：两次完整来源、真实LCEL顺序、规划schema/重复key/类型/重复标题/超限、第一失败零第二POST、第二失败保留第一证据、预占先发、root/锁/cap/父计数、封账不重跑、hash漂移首错停、容量/网络/截断错误、白名单无reasoning和credential、offline路径不读env/不联网。mock仅替换外部transport，隔离到受控临时目录，测试不得写真实group。

独立审查通过后，root先plan/freeze/check，再最多2POST并verify。所有真实尝试均计账。内容独立核对long1–6、课程路线、实例范围/时间/必要条件/模态、概览与重复，来源忠实按完整字幕上下文判断。一次已见来源不代表未见Lecture2、短中回归或产品已解决；新结果记录后再决定后续，不无限追加阶段。
