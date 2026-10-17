# Ragas 独立评测实现审查

审查日期：2026-10-15。最终未解决问题：**Critical 0 / Important 0 / Minor 0**。此结论覆盖下述实现与离线边界，允许主 Agent 继续执行其有限冻结和实测流程；不表示供应商分解、NLI 或总结内容已通过语义验收。

工程约定：成熟组件优先、窄接口和单向依赖；本工具隔离生产依赖，不修改 yt-dlp、UI、账号或 env。UI 如涉及须使用 ui-ux-pro-max/design-system 与三层 token。旧冻结证据保持原字节。

## 范围与证据

- 阅读实施计划、adapter、runner、两个测试文件、样本及说明、依赖锁，并交叉检查独立环境内 Ragas 0.4.3 的实际 Faithfulness/base/util 源码。
- `ragas_adapter.py:28`、`:142` 起直接实例化 `ragas.metrics.collections.Faithfulness` 并调用其官方 `score`，继承真实 `InstructorBaseRagasLLM`；没有复制评分引擎或用 mock metric 替代。脚本化 completion 仅用于离线边界验证。
- `ragas_adapter.py:77` 起在 completion 前锁定两阶段尝试；`:91` 起验证非空、有界、无重复分解；`:103` 起要求原始 verdict 严格为整数 0/1，并要求逐字断言一一匹配。runner 直接返回原始解析 dict，不先做 Pydantic 类型强转。
- `ragas_adapter.py:17` 起在首次 Ragas 导入前禁用 Ragas/LangSmith/LangChain/Hugging Face 遥测及在线下载设置。受控适配器没有 provider SDK、重试、缓存或 fallback 层。
- `runner.py:67` 起校验独立虚拟环境、Ragas 版本和安装包版本与锁；`:108` 起绑定新资产、父组 10 POST、phase7 frozen/0 POST 及旧来源哈希；`:142` 起检查 snapshot/live 漂移。历史文件只读，不重开旧 phase。
- `runner.py:235` 起要求 root caller、持有既有共享目录锁并拒绝重开；`:255` 起在每次请求前复核冻结和已消费证据，限制 phase 16 POST、样本 2 POST、输出 4096 tokens、完整 prompt 60000 字符；`:270` 起持久预占后才写 payload 和发送。HTTPX 串行、无重试、无重定向、无环境代理；模型响应名、状态、HTTP 状态及 JSON 均须通过，首错封账。
- `runner.py:175` 起仅提取公开 assistant output_text、有限 usage 和白名单元数据；对原始文本及 JSON 解码后全部对象键值扫描凭据。命中则整段 redacted 并终止。请求 header、reasoning、任意 provider 字段和异常消息不持久化。测试 transport 被限制在 system-temp 内的独立 PROJECT/输出/锁路径。
- 8 个样本为 4 对相同 source 的英源中答对照，4 正/4 负；标签与 core_questions 只在离线统计/人工审阅使用，adapter 窄接口只接收 source/response/complete。实际官方提示不接收人工标签或覆盖问题。
- 独立只读核验 7 个 bound source SHA 全部匹配；两个 MIT source 均逐字等于 34894 字符快照；原例 response 逐字等于 phase4 `result.key_points[3]`。合成范围/时间/否定归因标签合理。MIT 原文将限制挂在具体 calculator 示例上，原中文将其扩到类别，局部纠正例恢复实例主体；该标签只用于定点诊断。

## 本次发现及关闭

1. **Important，已关闭：JSON 转义凭据回显。** 原 runner 只在原始 output_text 中查密钥，合法 JSON 的 Unicode 转义可在解码后进入保存结果。已改为保存 raw 之前扫描解码后的每个对象键和值，保留重复键以免覆盖绕过；命中统一 redacted 并首错停。最终定点回归与额外重复键探针通过。
2. **Minor，已关闭：adapter 失败后可再次进入 completion。** 原状态仅记录成功输出，失败后同实例可重发。现用 extraction/nli attempted 标志在调用前预占状态。独立 provider 异常探针确认第二次调用不再进入 completion；真实 runner 本身的首错停与 2 POST 门同时保留。

Windows 新鲜进程网络阻断检查曾被 asyncio 的本地 socketpair 自管道触发；最终检查预创建有限本地 IPC pair，随后继续阻断全部 connect/connect_ex/create_connection/getaddrinfo，未放行 provider 或 telemetry 路径。

## 审查者实际执行

- 独立环境 Python `-B` 只读样本/哈希核验：7 项哈希、MIT 来源/原响应逐字绑定、4 对来源相同、8 项/4 正例，均符合上述结果。
- 新鲜 Python 进程真实 Ragas 定点探针：网络连接/DNS 全阻断（事件循环仅使用预创建本地 IPC pair）；官方两阶段返回负例 score=0；`do_not_track()` 为 true；布尔 verdict 拒绝；异常后同实例再次 generate 不调用 completion。最终进程 exit 0。
- `tools/semantic_eval/.venv/Scripts/python.exe -B -m pytest --noconftest -p no:cacheprovider --basetemp <独立 system-temp 路径> tools/semantic_eval/tests/test_runner.py -k 'decoded_credential_echo or invalid_output_json' -q`：**4 passed，16 deselected**。仅 mock transport/临时 PROJECT；未触碰真实 phase。
- 额外只读假密钥探针：重复 JSON 键中被覆盖的 Unicode 转义凭据仍被 redacted，进程 exit 0。
- 未重跑全套 pytest；不将其他 Agent 的测试数字记为本人执行。未安装依赖、读取真实凭据、真实 freeze、发送 POST、启服务或修改旧证据。

## 最终代码绑定

以下 SHA256 为审查完成时的实际文件字节；后续 freeze 应另绑定全部 ASSETS 与本文件。

| 文件 | SHA256 |
| --- | --- |
| ragas_adapter.py | `3cb0ca411c3137eb642f783a94a163a0031f05b274bc8816de879a0c45911e1f` |
| runner.py | `1c1de0e84202ffc2afd2cba1842d5aecd707df960db7a3ab786e4ba92c466643` |
| cases.json | `e4ab4a2b2c30fa4609eefec3572e62e92d2d76ba4f5feffd53cef264fcd3b851` |
| bound_sources.json | `75a7f067ce4a4a4e2d3821cc7e61452402c788f22966c8f7097494b3aace8c5a` |
| pyproject.toml | `0dd6f25b28d99b623f0da6cb15dbbd61743d4ae87600232d7bdc2816d98edc4f` |
| uv.lock | `17f7ef68034e67dbd5b2e2d1565bf2970b4ae187b07a41a95f6d54b9dfe75f09` |

## 保留边界

官方分解可能遗漏限定或将错误主体翻译修正，NLI 也可能误判；结构门和断言绑定不证明语义。adapter 明确保留原响应与逐条结果，并标注 decomposition/source-scope 未自动核实、coverage 未测量。真实英中分解必须由人工与原响应对照，分别报告漏判/误拒和分解失真；合成正反例或高分不能替代原有 core 覆盖准则、完整摘要生成与未见来源验收。
