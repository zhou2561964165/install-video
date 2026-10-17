# 仅DeepSeek：第一步两来源原样结果

两个新来源各用DeepSeek Pro/high进行一次完整输入总结，未做规划、核查或修订。原样回答：

- `en-long-unseen.md`：英文Lecture2的中文总结；源33710字符、输出4888字符，7/8核心完整，仍有转换前提遗漏和局部退出条件错误。
- `zh-listening-unseen.md`：中文听力教学访谈总结；源402字符、输出1112字符，4/4核心完整，未发现确证核心事实错误，但有重复扩写。
- 同名txt或`zh-listening.txt`为输入正文，vtt为原字幕；`manifest.json`保存来源/许可/hash。

本轮2POST/23275供应商tokens，phase15已closed。内容说明见`docs/acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md`，不是修正后答案。只完成用户要求的第一步，后续未执行。

来源：Dr. Ana Bell，Lecture2 Branching and Iteration；Dr. Haohsiang Liao，Listening for Success: The Importance of Audio Files (Chinese)；Massachusetts Institute of Technology / MIT OpenCourseWare。网页与caption地址见manifest。原文和派生材料遵循CC BY-NC-SA4.0，保留署名、非商业与相同方式共享；MIT不背书模型输出。

工程约定：适用skills、成熟组件/窄接口/单向依赖，yt-dlp唯一层、scene只读，UI设计技能及三层token；保护账号/env、UI、本机模型及旧封账证据。本目录不包含凭据或reasoning文本，不改产品默认。
