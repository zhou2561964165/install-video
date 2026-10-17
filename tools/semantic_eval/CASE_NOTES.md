# 人工标注说明

工程约定：成熟组件优先、窄接口/单向依赖；保留旧原件/账号/env，本评测不修改生产代码或UI。若涉及UI，须使用ui-ux-pro-max/design-system三层token。

这六条是用于评估 Faithfulness 的合成英文来源与中文响应，不使用 MIT 样本答案。每两条共用完全相同的 source；响应只改变一个关键范围或判断表达。`expected_supported` 是人工逐条判断，不提供给 judge。`error_kind` 标记该对照所针对的错误类型，正例也保留同一类型，便于成对分析。

| 对照 | 人工判断依据 |
| --- | --- |
| `synthetic_scope_*` | 来源只测试了 M 系列中的 A17，并明确没有其他设备的结果。A17 在传感器达到 82°C 时关机一次，因此正例有直接依据；“每台 M 系列设备”把单台观察扩大到整个类别，无法由来源推出。 |
| `synthetic_time_*` | 完整记录只覆盖 7 月 6 日至 8 月 2 日的四周试点，且该期间每周一恰有一次会议。正例保留了时间范围和频率；负例把该规律扩展到全年，而来源没有其余年度记录，故不能推出全年规律。 |
| `synthetic_negated_attribution_*` | 来源引用高说他无法从记录判断提醒是否导致增长，并说明没有因果结论。正例复述这种不确定性；负例把它改成“提醒没有导致增长”的确定性否定。来源既没有这个归因，也没有作出提醒无效的结论，因此负例不受支持。该标签只表示缺少蕴含依据，不把它标成真实因果关系的反命题。 |

响应和标签是英文来源到中文输出的跨语言对照。它们检验评测分解能否保留设备范围、时间限定、说话人归属和不确定性；若 judge 在翻译或断言切分时丢失限定，自动分数可能失真。人工标签用于检查这种误差，不保证跨语言评测本身可靠。

每项的 `core_questions` 只供后续独立 coverage 标注使用，不会传给 Faithfulness judge，也不等同于实际 coverage 测量或本轮实测结论。Faithfulness 标签只判断响应断言能否由对应 source 支持，不要求响应覆盖来源的全部信息。

## 真实来源的局部对照

root新增`mit_phase4_p4_original`与`mit_phase4_p4_scope_corrected`：两者均使用phase4的完整34894字符英文字幕快照，前者response逐字等于原产品key_points[3]，后者仅重写首句开头的主体/范围框架；其余响应逐字相同。原文先介绍fixed-program computers，再说“an example ... is this calculator”，四则/不能绘图上网的谓词挂在这一例子上。因此原点不受支持；人工纠正点保留其余关于存储程序可改变指令序列的内容。

这仅是对P4的定点诊断，不是完整摘要生成或未见讲座验收。合成来源明确说明边界，通常比自然讲座容易；六条通过不足以证明一般化。保留全部分解断言并独立检查是否把错误主体偷偷修正；labels/core_questions不进入模型提示。核验遗漏继续使用既有独立core准则，本轮Faithfulness只衡量断言支持。

MIT字幕及其派生对照按CC BY-NC-SA 4.0保留：Dr. Ana Bell / Massachusetts Institute of Technology, MIT OpenCourseWare，Lecture 1: What is Computation?；https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-1-what-is-computation/ 。原始来源、产品、响应及许可证的SHA256见bound_sources.json；旧文件原字节不改。
