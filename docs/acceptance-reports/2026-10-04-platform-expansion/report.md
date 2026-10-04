# 2026-10-04 真实平台字幕扩展

## 工程约定

UI/视觉/交互先使用 `ui-ux-pro-max` + `design-system`；skill 优先于计划；颜色、字体、时长走三层 token，能力和网络预算可配置；避免大规模重构。后端仅 `ytdlp_service.py` 接触 yt-dlp，平台适配器与字幕服务通过规范化轨道接口通信。前端视觉只读 `scene`，不修改下载状态、不依赖下载核心。

## 结论

增加了独立 Bilibili 匿名字幕适配器。公开 `view → 指定分P的CID → dm/view → 字幕JSON` 路径在真实样本上成功获取正文，补足现有通用路径的字幕可用性；没有复制参考源码、修改参考项目、使用 cookies 或绕过访问限制。平台元数据失败或轨道为空时保留原 yt-dlp 回退。原生轨道选取、正文获取或解析失败时，最多再尝试一次通用字幕入口。

本机已安装的 yt-dlp `2026.8.19` 在 Bilibili 分支将字幕转换为 `{ext: srt, data: ...}`，没有 `url`。原项目仅接收 URL 格式，导致这种通用回退内容被丢弃。本轮补充 inline 字幕规范化与字节上限，在相同正文解析层处理 SRT，仍通过唯一 yt-dlp 接口。

Commons 两个公开元数据探针均为 HTTP 403，证据未显示新增适配器能增加本机可用性，因此本轮保留通用路径。403 是访问限制，不能当作“没有字幕”。YouTube 仅确认页面访问，不能据此宣称字幕提取成功。

## 真实请求证据

采集时区为 UTC。共执行 12 组公开探针：首次 4 组、补充轨道来源记录重跑 4 组、原生路径与其他来源 4 组；不再扩大网络预算。元数据组可能包括关联 CID 的第二个请求。每次请求超时 12 秒，原生复测将本进程重试次数设为 0，以保证探测预算；产品默认配置不变。网络仅使用 Windows 已存在系统代理，环境变量只在测试进程临时设置。

| 来源与公开链接 | UTC | 本轮结果 | 证据范围 |
| --- | --- | --- | --- |
| [Bilibili BV12N4y1M7rh](https://www.bilibili.com/video/BV12N4y1M7rh) | 07:03:07 | 匿名原生字幕正文成功，1,973 字符、136 行；`zh-Hans`，API `type=0` | 仅访问探针；正文、临时签名地址、cookie 均未保存，无 LLM 调用 |
| [Bilibili BV1jL41167ZG](https://www.bilibili.com/video/BV1jL41167ZG) | 07:03:09 | 原生访问/元数据失败，`ValueError` | 记录仅保留异常类别，未确认具体 API code；不能判定无字幕或登录要求 |
| [Archive.org 短片](https://archive.org/details/youtube-6k-kbg3_Drc) | 06:56:13 | 元数据 200，英语、法语 VTT 文件可发现 | CC BY 3.0，许可沿用原验收 manifest；本轮仅读取文件元数据 |
| [Archive.org 长演讲](https://archive.org/details/lca2019-Awesome_Monitoring_Infrastructure_Using_the_Elastic_Stack) | 07:03:10 | 原生元数据成功，`en` 自动字幕轨道 | CC BY 4.0，许可沿用原验收 manifest；未重复下载正文 |
| [Commons 气候短片](https://commons.wikimedia.org/wiki/File:Die_Temperaturkurve_der_Erde_(ZDF,_Terra_X)_720p_HD_50FPS.webm) | 06:56:09 | `videoinfo/timedtext` 403 | 仅元数据访问探针；不能归类为无字幕；没有新增适配器 |
| [Commons Elephants Dream](https://commons.wikimedia.org/wiki/File:Elephants_Dream.ogv) | 06:56:12 | `videoinfo/timedtext` 403 | 仅元数据访问探针；没有保存正文 |
| [YouTube 页面](https://www.youtube.com/watch?v=hVimVzgtD6w) | 07:03:16 | 页面 HTTP 200 | 网页访问成功；没有提取或保存字幕，不作为字幕支持证据 |

Bilibili 正文文本 SHA-256：`56e9cb1efab4fcc0b4756ea413dfdc21482dfb4ee525a8d10d8692de6e65aa8a`。`is_auto` 按平台 `type` 和 `ai-` 语言标记判断，CDN 域名中含 `ai` 不单独决定字幕类型。本轮成功正文使用已获取的原生元数据调用产品正文路径，避免重复外网请求；完整元数据入口、回退和鉴权由确定性回归覆盖。

逐项记录见 [public-probes.json](public-probes.json)、[native-probes.json](native-probes.json)。两份记录只保存最新一轮各组结果；首次相同元数据探针的结果也通过执行日志观察，未复制形成重复报告。每次记录包含公开原始链接/端点、UTC、权限说明、状态以及安全摘要。

## 实现和限制

- 域名精确匹配 `bilibili.com` / `www.bilibili.com`，仅适配普通 BV 视频路径；其他域名、查询字符串中的平台名和短链接保持通用路径。
- 默认第 1 分P；`p=2` 使用 `pages` 对应 CID。非法 `p` 或在完整有效 `pages` 中找不到的分P属于无效输入，直接报 `invalid_url`，防止通用提取器默认为第 1 分P。元数据损坏仍可通用回退。
- 支持 `ai-zh` 等语言规范化、人工字幕优先；保留平台格式来源。字幕 CDN 必须为 `*.hdslb.com/bfs/subtitle/*.json`，HTTP/`//` 升级 HTTPS，拒绝凭据、异常端口与跨来源字幕重定向。
- 原生元数据和正文复用有限 GET 重试及配置化超时/字节上限。JSON 的对象、列表、字符串、类型字段、时间戳有限值和顺序均有验证。
- 未加入 Bilibili 登录、cookies、WBI/风险控制规避、弹幕内容、ASR/OCR 或新页面功能。匿名轨道可能因视频、地区、时间、API 行为而不同，单个成功样本不代表全站可用。
- 通用回退再次失败时保留最初原生正文/选轨道错误，避免报告假“无字幕”；普通通用正文失败不会重复调用提取器。两条路径使用相同字节上限。

## 红绿验证

最初 2 个原生契约用例均失败（尚无原生适配）；扩展平台边界回归后 10 失败 / 15 通过；实现后 25 / 25 通过。之后依次先观察 5 个正文回退/inline 回归失败、3 个 URL/重定向回归失败、4 个无效分P入口回归失败、1 个 API 输入错误类别回归失败、1 个通用 Bilibili AI 字幕语言匹配回归失败，再逐项实现。Bilibili 通用路径中的 `ai-zh` 亦规范化为 `zh` + 自动字幕，避免回退后中文语言选择失败。

最终定向命令：

```powershell
cd E:\install_video\backend
uv run python -m pytest tests/test_platform_bilibili.py tests/test_subtitle_service.py tests/test_ytdlp_service.py tests/test_network_retry.py -q
```

结果 **97 passed in 1.96s**；其中新平台文件 46 个用例。覆盖分P关联、坏元数据、外域来源、JSON 错误、字节上限、瞬时 TLS 恢复、人工优先、inline SRT、最多一次通用回退、原生错误保留及 API 分类。复审补充先红验证了巨大合法 JSON 整数时间戳（例如 `10**400`）会触发 `math.isfinite` 的 `OverflowError`；现在安全数值校验将其归类为 `subtitle_invalid`，维持原生失败后通用回退。同时先红覆盖超过 Python 整数转换上限的 4,301 位分P编号，转换错误明确归类为 `InvalidVideoPartError` / `invalid_url`，不访问平台也不回退默认分P，闭合两项数值边界审查问题。全量集成检查由主 agent 在三个工作流合并后统一执行，此处不把定向结果当作全量结果。

## 复现与原始资料

仓库根目录使用 `.venv/Scripts/python.exe` 执行 [probe_public.py](probe_public.py) 或 [probe_native.py](probe_native.py)。需要本机系统代理时，可用 PowerShell 临时设置子进程代理；不修改用户代理设置。脚本不读取 `.env`，不调用 LLM，不输出或保存字幕正文、cookies 或签名字幕 URL。

设计资料只依赖参考项目、本机真实上游源码与官方文档：[yt-dlp Bilibili 提取器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/bilibili.py)、[yt-dlp Wikimedia 提取器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/wikimedia.py)、[MediaWiki TimedMediaHandler API](https://www.mediawiki.org/wiki/Extension:TimedMediaHandler/API)。MediaWiki 文档公开说明 `videoinfo` 的 `timedtext` 属性，亦提示直接 `action=timedtext` 内容接口属于可能变动的内部模块；本轮未新增该适配器。
