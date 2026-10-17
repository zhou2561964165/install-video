# 完整来源单次总结的有限点数容量对照

工程约定：技能优先；成熟组件与窄接口优先、单向依赖；保护用户工作、凭据、账号、UI、本地模型和旧原件。UI 改动须使用 ui-ux-pro-max、design-system 与三层 token；yt-dlp 只通过其服务，视觉层只读 scene。本计划仅建立开发验收候选，不改变产品默认或公开入口。

## 问题与单变量

phase11 已完成完整 MIT Lecture 1 来源的单次 Pro/Responses schema 诊断。其 14 点结构通过并不证明全部内容通过。完整规范化字幕为 34,894 字符；现有自适应公式在该长度的自然需求为 15 点，但原候选配置以 14 为 ceiling。phase12 仅把候选配置 `llm_summary_point_ceiling` 从 14 改为 15，检验有限容量是否影响必要条件的保留；不加入样本答案或新的内容删改器。

使用同一 phase10 授权且冻结的 source 身份，同 `deepseek-v4-pro`、Responses `json_schema`、reasoning none、fidelity off、完整 normalized transcript、生产 `_summary_request(merge=False)`、8192 output tokens 和同一通用 prompt 模板。生产 `_summary_budget(len(source))` 必须实际算出 15 点 /8192 tokens；不通过硬填 schema 绕开自适应公式。模板中预算数值由 14 变 15 属于该配置变化。精确比对 phase11 的冻结 payload，除两处生成预算文字和 `maxItems` 外其他字段及全文必须一致。

phase11 产品、raw 和其他封账文件仅用于历史身份、哈希与对照，不输入模型，不生成叶笔记，不重做旧 phase。这个已见来源的一次候选结果不能代表默认 Flash、正常分段路径、未见来源或短中回归全部通过。

## 有限阶段与计数

独立 phase12，cap=1 POST；format/semantic/extra 都为 0，无重试、无隐藏 fallback。开始前长文 phase1–11 累计 17 POST；phase10 和 phase11 都必须 closed 且各 1 POST，旧组原件保留。Ragas 独立 16 POST，合计本次持续整改 33 POST，旧 67 POST 另封账。更换 GPT 账号不清零；用户授权整改无总 POST/费用上限，不改变本 phase 的有限 cap。

发前持久预占、root 单 caller、共享锁串行、首错停。成功或失败都封账，不重开 phase12，不借用旧 phase 余额。任何输入/配置/哈希漂移均拒绝；全文超过 60,000 字符不截断、不自动降级。

## 实施与验收

- 新 `scripts/direct_source_capacity_evaluate.py` 薄适配复用 phase11 direct-source adapter、native freeze、既有 Responses parser、ledger、共享 caller guard 和离线 snapshot replay。旧 runner 与生产代码不修改。原生 freeze 的单个最终 stage 历史标签为 `merge`，样本 `request_path=direct_source` 明确实际 `merge=False`。仅在构造 freeze 时将原始固定 stage 元数据改为实际捕获 schema 的预算，持久化以后校验不修改快照。
- 快照包含新 runner、测试、计划、独立 review 和所有继承的候选资产。phase10、phase11 的 tracker、ledger、receipt、index、provenance、product、payload、raw 均逐字节 hash 绑定，含 source/manifest/VTT/license/title/attribution 身份。不重新运行旧工具。
- TDD 测试先观察缺少 runner 的 RED；离线合成 transport 验证 cap1、预占先于 POST、15 点接受、16 点拒绝、网络/截断首错停、第二次 POST 拒绝、历史漂移拒绝、只在闭账17次基础分配、冻结后不读 env 回放、真实 MIT 34,894 字符的生产预算及完整输入隔离。测试不发 provider 请求、不启动服务。
- 独立工具审查通过后，root 才可 plan/freeze/check/run/verify。原件核验只证明证据一致，内容须独立检查 long1–6、逐断言精度/范围/归因/条件、overview 与组织。不能以 15 点结构或机械回放通过代替语义评分。

默认继续 `legacy/adaptive/single/fidelity=off`，公开 20,000 字符限制和长文暂不支持保持。无提交、推送、部署动作。
