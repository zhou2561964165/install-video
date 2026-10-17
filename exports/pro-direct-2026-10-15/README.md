# 完整字幕与DeepSeek Pro直接结果

用户要求将当前字幕全文交给DeepSeek Pro API；本地只传送并保存，不运行分段摘要、合并、语义核查或本地模型。

- `full-transcript.txt`：完整34,894字符字幕，和历史冻结来源逐字节一致。
- `original-subtitles.vtt`：保存的原始时间轴字幕。
- `pro-summary.md`：供应商成功完成后复制的原始可见文本，不经本地改写。

全文SHA-256：`c53d556b0a0d10504e1acdb9d0645f6573596bac6d110eb610c29fd8bf1ed5b7`。

来源：Dr. Ana Bell / Massachusetts Institute of Technology / MIT OpenCourseWare，*Lecture 1: What is Computation?*，6.0001 Fall 2016。
官方页面：https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-1-what-is-computation/
许可：CC BY-NC-SA 4.0，https://creativecommons.org/licenses/by-nc-sa/4.0/ 。来源及派生材料保留署名/相同许可；MIT不背书模型或产品。

模型：deepseek-v4-pro；Responses普通文本输出、reasoning high、max_output_tokens=16384。单次请求上限1，无自动重试；不固定14/15个要点、不使用JSON合同。模型返回不等于独立内容质量验收，最新实际状态见 `docs/acceptance-reports/2026-10-13-long-summary-fidelity/phase-13-report.md`。

工程约定：成熟接口、窄接口、单向依赖；保护原件、账号/env、UI及本地模型。产品默认和公开20000字符限制未因本次委托更改。
