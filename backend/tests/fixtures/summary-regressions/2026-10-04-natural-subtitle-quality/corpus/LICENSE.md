# 自然字幕语料许可与署名

## 工程约定

UI、视觉与交互变更先使用 `ui-ux-pro-max` 和 `design-system`；skill 指引优先于计划；颜色、字体和时长遵循 primitive → semantic → component token；新增能力可配置、模块通过窄接口单向依赖；只有 `ytdlp_service.py` 接触 yt-dlp；视觉层只读 scene，不改变下载状态。

本目录三份原始 VTT、清洗文本和其中保留的摘录属于 **MIT OpenCourseWare / 各授课者的 CC BY-NC-SA 4.0 内容**，不是本项目软件许可下的代码。许可：[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)。署名、课程原始页面和字幕 URL 逐份见 [manifest.json](manifest.json)。

| 文件 | 标题与原作者 | 官方来源 |
| --- | --- | --- |
| zh-short.vtt / zh-short.txt | Creating an Immersive Classroom Environment (Chinese)，Dr. Haohsiang Liao / MIT OpenCourseWare | [中文字幕资源](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/mit21g_101f14_immersive_environment_chinese-2/) |
| en-medium.vtt / en-medium.txt | Daily Grading System，Dr. Haohsiang Liao / MIT OpenCourseWare | [课程视频及字幕](https://ocw.mit.edu/courses/21g-101-chinese-i-regular-fall-2014/resources/daily-grading-system/) |
| en-long.vtt / en-long.txt | Lecture 1: What is Computation?，Dr. Ana Bell / MIT OpenCourseWare | [课程视频及字幕](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-1-what-is-computation/) |

清洗仅去除 VTT 头、时间戳、cue ID、标签、相邻完全重复行并规范空白；没有补写、更正讲话、翻译、拼接或重复扩充。原始字幕字节及 SHA-256 保留，清洗版同样按 CC BY-NC-SA 4.0 再分发。本目录源事实摘录及其改编也按同一许可提供。

本次用途仅为非商业本地推理质量评测，**没有训练或微调模型**。再使用这些字幕、摘录或改编时，必须保留署名、来源、许可及改动说明，并遵守非商业及相同方式共享要求；不得据此推定 MIT 认可本软件或模型输出。商业产品不能把这些文件直接当作可无限制复用的产品数据。

[MIT 当前官方条款](https://ocw.mit.edu/pages/privacy-and-terms-of-use/)的 AI 条款明确允许按适用许可开发和改进 AI，同时要求署名、非商业及 ShareAlike；本轮没有把普通 CC 标识当作绕过来源 AI 条款的依据。采集时刻、政策页面 hash 与条款标题见 [license-evidence.json](license-evidence.json)。
