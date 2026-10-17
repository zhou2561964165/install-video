# Phase 6 生产代码独立审查

审查日期：2026-10-14。范围：`backend/app/services/llm_service.py`、`backend/app/services/summary_review.py`及其scope/checks/revision回归。审查者独立静态检查；没有修改代码、调用模型或启动服务。

## 结论

**Critical：0；未解决Important：0。** 可进入phase6工具整合与有限真实复验；本审查不表示P4内容已修复，也不证明DeepSeek实际遵循Responses schema。

独立审查先指出多段完整生成若只在`review_summary`检查核查预算，会在已付费生成叶/合并后才因输出上限不足而失败。生产代码已将检查移至`summarize_text`首个叶请求前，并只对会走校订的多段路径执行；单段继续1次生成，不受review token额度影响。复用保存草稿则按实际要点数预检。14点核查额度为`128 + 256×15 = 3968`，默认4096可容纳。

独立审查确认动态schema具有所有必需target槽位、禁止额外字段、限制引用和finding长度；重复JSON键、错误反馈和不属于原文的连续引文会阻止修订。checks固定走现有Responses `json_schema`，一次核查接一次修订；没有新增重试或付费fallback。范围提示面向一般主体和指代关系，没有加入计算器、课程或样本答案。

## 主Agent补充的离线验证

审查后由主Agent增加边界回归并执行相关5文件：**105 passed / 0.93s**。覆盖完整多段14点模拟的3968-token核查额度、单段低review额度仍只发1次请求、Responses incomplete/provider failed/refusal均1请求后停止，以及嵌套字段重复JSON key。测试结果只证明本地逻辑、报文和错误处理，不代表真实模型语义。

Phase 6工具代码的独立审查另存于[工具审查](phase-6-structured-checks-tool-final.md)。两份审查文件及新设计应在freeze时一起hash绑定。phase1–5全部snapshot/raw/result/ledger/receipt和原冻结稿不属于本次修改范围。
