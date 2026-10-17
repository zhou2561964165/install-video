# 独立语义评测工具

## 当前结果与使用边界（2026-10-16）

首轮已经完成并封账：16 POST /34106供应商tokens，八例误放1、误拒0；真实P4实例/类别错误和局部纠正版均获1.0。Faithfulness不能作为生产自动放行门，也未评估coverage。见[实测报告](../../docs/acceptance-reports/2026-10-15-ragas-semantic/report.md)及[独立语义审阅](../../docs/acceptance-reports/2026-10-15-ragas-semantic/semantic-review.md)。

全部后续计划先登记在[统一总表](../../docs/follow-up-plan.md)。本轮仅审查文档；下方命令供工具维护参考，已closed首轮只能verify，不能重复freeze/run。新模型评测须另有用户指示和有限阶段记录。`CASE_NOTES.md`及`review.md`是冻结资产，保留原字节；本README说明当前状态。

工程约定：成熟组件优先、配置化窄接口和单向依赖；生产yt-dlp仍唯一服务边界，UI/scene不变；UI工作须使用ui-ux-pro-max/design-system与三层token。保留账号/env、本地模型及旧冻结证据。

用户批准的Ragas评测对照。此目录为独立uv项目，实际使用`ragas.metrics.collections.Faithfulness`的断言分解、NLI提示和评分；不升级根目录生产依赖，也不导入或修改生产总结模式。Ragas版本固定0.4.3，完整依赖锁在本目录uv.lock。其间接依赖包含LangChain/LangGraph包，不代表产品恢复框架实验。

适配器在首次Ragas导入前禁用遥测，并以`InstructorBaseRagasLLM`窄接口注入受控调用函数。没有使用SDK自动重试、向量检索、模型下载或在线评测平台上传。生成的每条断言、对应verdict/reason保留在评测结果中，格式错误、漏判条目、重复或非法verdict立即失败，不悄悄修复或重试。同一阶段即使失败也不能在该LLM实例上再次调用。

兼容性：Ragas0.4.3仍导入`langchain_community.chat_models.vertexai`，新版langchain-community移除了该模块，因此本工具单独固定0.3.31；这不改变生产依赖。完整锁包含各Python/平台分支，实测环境的已安装版本也写入freeze。

## 安装与离线测试

从仓库根执行：

```powershell
uv sync --project tools/semantic_eval --frozen --default-index https://pypi.org/simple --system-certs --link-mode copy
& 'tools/semantic_eval/.venv/Scripts/python.exe' -B -m pytest --noconftest -p no:cacheprovider tools/semantic_eval/tests -q
```

开发期跨磁盘缓存安装可能显示hardlink回退copy提示，不影响运行；生产.venv未修改。

## 评测含义

`score`是Ragas被支持断言比例；`all_supported`仅表示本次模型给每条断言的verdict都为1。它不是来源忠实证明，也不能证明分解没有删除/修正原摘要中的错误限定。

首轮八样本包括六条合成英中正反例和真实MIT完整字幕+P4错误/局部纠正对照。人工标签不传入judge。合成来源明确给出边界，容易程度高于自然讲座；本轮不是全摘要生成验收或未见来源验收。逐条审阅分解/核验结果，统计错误被放过和正确内容被拒绝，并保留原有独立核心覆盖准则。`core_questions`是人工覆盖检查材料，本轮Faithfulness不自动评分coverage。

## 有限实测机制与首轮历史状态

只有root调用runner的真实run；freeze不读取密钥、不发HTTP。run从现有backend/.env读取凭据到内存，不写回文件。每个样本正常2 POST，总上限16，单次输出上限4096 tokens，完整prompt输入上限60000字符；错误即停并关闭本phase，不重跑旧失败阶段。所有阶段共用现有caller锁、发前持久预占，记录安全公开输出与供应商usage，不保存reasoning、请求header或凭据。

首轮结果保存在`docs/acceptance-reports/2026-10-15-ragas-semantic/results/`。该轮冻结时绑定旧组已有10 POST及当时phase7 frozen/0 POST状态；这是冻结时点的父证据，不是当前计数。随后首轮已完成16 POST并closed，phase7也另有1 POST失败封账。当前持续整改合计39 POST/353577tokens（含Ragas16/34106），旧67另封账，见[统一总表](../../docs/follow-up-plan.md)。实现、离线检查和独立审查通过只证明工具条件，不能将首轮误放结果改称语义通过。

工具入口是`runner.py --freeze`、`runner.py --run --caller root`与`runner.py --verify`。默认phase路径只能创建一次；已关闭phase只能verify，不能重复run或覆盖freeze。新实验须有独立目的、有限上限和路径，不能用新目录抹去既有调用。freeze/verify不读dotenv、不发HTTP；只有run读取现有provider key，raw落盘前检查原文本及JSON转义解码后的凭据回显。

## 来源与许可证

Ragas官方：[Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)、[源码仓库](https://github.com/vibrantlabsai/ragas)。代码许可按锁定包自带LICENSE。

MIT字幕及派生评测样本依CC BY-NC-SA4.0保留署名，详见CASE_NOTES.md及bound_sources.json；软件许可与语料许可分别适用，不将派生课程内容并入软件许可声明。
