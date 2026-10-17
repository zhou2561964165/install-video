# 来源核查模型显式对照

工程约定：用户/AGENTS/适用skills优先，成熟能力、配置化窄接口/单向依赖，yt-dlp唯一层/视觉只读scene；UI采用ui-ux-pro-max/design-system及三层token。保护已有工作、账号/env、模型资源和所有历史原字节。

phase3已closed，2POST/25830供应商tokens，本组累计6POST/104191tokens。Flash核查未指出类别范围错误，最终product与phase2原件SHA完全相同，P4也未变；结构/证据通过不意味着内容通过。此次不继续加提示、token或新facts协议，而隔离模型能力做明确对照。

使用已支持的`deepseek-v4-pro`执行同一固定review→revision，仍base4096/ceiling8192、review4096、thinking auto（当前deepseek provider默认disabled）、JSON模式；不改默认模型、env、提示、主题14上限或评分。复用精确phase3草稿与完整源，仅2POST，不重付抽取。累计父6保持，所有实际尝试计账，错误停，不重开旧阶段。

[官方Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)列明该模型与thinking disabled；[JSON输出指南](https://api-docs.deepseek.com/guides/json_mode/)说明json_object。本次重新核对官方文档，不发能力探针或未列明strict参数，不保存reasoning。现有传输/格式接口足够，无新SDK或框架。

新`pro_review_evaluate.py`明确固定phase4及候选模型，freeze记录真实父模型与显式候选模型，不伪造父身份；同provider/endpoint、精确草稿及源文、共享caller锁、root串行、发前持久预占、冻结codec/raw绑定和失败封账复用。代码/离线/独立审查完成后才freeze/run；结果需独立源文评分。若模型对照通过，正常完整生成与未见来源仍待实测，不立即宣布产品解决或静默升级模型。
