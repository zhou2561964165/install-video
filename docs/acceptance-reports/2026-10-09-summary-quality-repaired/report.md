# 核查质量续验收与独立复核

> 后续用户已要求回归字幕→LLM总结，字数按任务有限拓展，并于2026-10-09暂停工作。当前见[自适应交接](../../handoff-2026-10-09-adaptive.md)。本报告保留两个关闭phase累计17次的真实结果；此前准备的fixed长文第三phase已取消，后续adaptive最多3次脚本未run，不得把准备状态算成新实测。

## 工程约定

以最新用户 AGENTS 和有效指令为准，Superpowers 调试、TDD、实际并行与独立审查。UI 按需 ui-ux-pro-max/design-system 三层 token，本轮仅后端。配置化窄接口单向依赖、LLM/yt-dlp 唯一服务层、scene只读；用户 env/db/已有账号/未提交工作和历史原件/冻结/账本保留。root 唯一真实调用者，发送前持久预占，所有失败与分类修复计数，新工作组硬26不增加。

**协议与多项代码边界已修复，整体总结质量尚未通过。** 本阶段已关闭，默认策略保持legacy，质量协议默认compat；本次实测显式compact，格式1/语义1/共享最多2次的产品默认修复策略保持开启。

## 实际调用

| 阶段 | POST | 供应商报告tokens | 状态 |
| --- | ---: | ---: | --- |
| quality-final | 3 | 7,840 | extract有效，compose标量主题字段两次格式失败，无final，关闭 |
| quality-repaired | 14 | 121,364 | 短中final；长文核查和一次semantic修订均缺核心引用，关闭 |
| 当前工作组合计 | **17 / 硬26** | **129,204** | 没有隐藏请求，旧phase不续跑 |

第二阶段正常13、最大19，原始3计入同组、预分配最大工作22≤26；未动硬上限，也没有借上一25POST工作组的余额。只在已定位且离线验证的scalar修复和新独立freeze/check后执行。token数据直接来自供应商，不推算货币费用。

短文、中篇各3POST无附加修复；长文5次extract、一次compose和两次audit共8POST，semantic_used=1、format_used=0。两次audit都是合法compact JSON，程序仍严格拒绝缺core，原输出没有被伪装成final。

独立checker已核对全部真实payload、原响应、修复反馈、规范化、程序引用、主题/身份诊断、真实bool映射、trace、公开结果，8模块及5文件helper链、原语料/rubric/旧基准及整个父结果树均绑定。全部hash在任何模型POST和归档产品执行之前校验；当前受信任helper自身的顶层初始化不提供另外的独立bootstrap保护，不声称更强保证。证据一致不等于语义正确。

## 当前工程成果

- 核查由compact一个摘要及有限主题点、内嵌实际四bool转成原严格audit格式，程序编号和引用，不造true，不剪字删点。
- 主题conditions/consequences标量完整包成tuple，精确空串有明确转换记录，空白-only/非法类型/超限仍拒，原数组不改变。实际scalar原件保留。
- 来源姓名原拼写策略、限定命名结构、primary/context主题关系诊断；姓名前缀、命名构式贪心、后副词和普通谓词句误报已红绿处理并独立复核，不宣称通用NER/身份归属证明。
- provenance分类消费已规范化对象，fence/marker不能绕过来源停止；配置检查先于paid标记，错误quality模式不能auto触发付费legacy fallback。
- strict ledger/HTTP实际int/usage/tz时间与响应原件一致，未完成/缺证据不标成功；fsync预占、单caller、关闭与重复启动拒绝。

进入本阶段的root全量为1292 passed。最后离线修复后，root最新全量为1325 passed、1条既有Starlette/httpx提示、196.66秒。独立工具审查未发现Critical/Important，曾见旧helper临时WinError5，受影响用例新路径单独复跑通过，失败日志保留，不修改已冻结父helper掩盖。

## 独立内容验收

[短中篇独立报告](short-medium-semantic-review.md)逐必要子句和全部输出句对照原字幕：

- zh1–zh4、en1–en4：**8项全部full**，无partial/missing。
- 短中所有已发布输出句精确性通过；无源外中文姓名，中篇使用原文HAOHSIANG LIAO、信念与文化例子显式归讲者。
- 短文组织不通过：P2仅父概览，没有新的实质条件，重复P3/P4两个展开。
- 中篇按原rubric组织通过：P4/P5/P6各有新条件/后果，不能只因同主题判重复；P5已合并中美两侧。更强的“一主题融合”仍可改进，但不擅自升级原评分门槛。
- 长文无可发布final，long1–long6 **6项仍未评**。原14项完成条件未达。

## 长文真实根因

[长文逐ID诊断](long-core-diagnosis.md)确认当前49事实为37core/12support。实际refs覆盖12core，缺25；其中21个低于词项阈值、4个负向冲突，不应把25都说成真实全文遗漏或selection删除。

raw13/raw14 content完全相同。正文实际保留许多主干，却仍丢失必要公式、停止条件、静态语义的分支限定、print/shell/editor、精确求解机制等。原始四flags全true也不能救回这些缺口。人工容量草案说明摘要247字/7点最大204字可以容纳关键内容，但它不是final或37core验证成功，不作为固定答案喂给模型。

## 后续离线修复与界限

在保持关闭阶段原件后，已修复“不同/无论”的词法误判，并保守恢复不同意/不同步/不同于、无论据/无论证以及显式差异反转护栏；混合主体同关系头不交叉误杀。真正让步结构采用明确条件和结果标记。独立[最后审查](../../../.planning/2026-10-08-summary-quality-finish/last-offline-fixes-review.md)在限定覆盖中无已证Critical/Important，不是通用语义证明。

missing_core_fact修订反馈现提供实际程序输出引用及具体缺失事实原claim/evidence/attribution；完整之前响应及来源保持，输入容量全量计算，超限发送前停止、不提前扣附加次数。真实红测先确认缺失反馈字段，修复后绿色；不会仅让模型再贴ID，不降低core阈值/selection/来源/长度/检查。

这些最后修改 **尚未真实重新验收长文**。只读当前原件重放仍不满足全core，部分新候选出现歧义，保守拒绝保持。当前17次之后没有再新增付费请求。用户恢复额度并要求继续后，明确准备独立`quality-long-final`，原因是已离线验证的极性修复和具体缺失事实反馈：只验原长篇，正常7、含默认分类修复最多9，累计最大26。新工具独立测试、审查及冻结通过前不发送；不改旧关闭工具/原件/台账、不另造预算、不提高总硬上限；默认legacy不提前推广。

只读命令：`.venv/Scripts/python.exe -B docs/acceptance-reports/2026-10-09-summary-quality-repaired/scripts/check_evidence.py`。关闭阶段不run，不修改provenance。
