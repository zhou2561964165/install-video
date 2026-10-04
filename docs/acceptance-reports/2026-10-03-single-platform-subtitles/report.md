# 真实平台字幕样本验收报告

采集时间：2026-10-03 UTC。主 agent 配置保持不变；没有调用 LLM，也没有修改生产代码。5 个字幕文件共 168,559 bytes，来自 3 个 Internet Archive 视频条目。直接取回成功率为 5/5；项目字幕解析器通过 4/5；项目真实平台服务链路通过 0/3 个视频 URL。MNN 的 SRT 与 VTT 内容相同，因此按 5 条格式轨道、4 份独立字幕内容统计。

## 1. 执行摘要

真实样本覆盖了 VTT、SRT、英语、法语、自动生成/ASR 来源和一个长字幕边界。项目解析器完整读取了 4 条轨道。MNN 的 SRT 因时间小数只有两位而返回 `subtitle_invalid`；相同内容的 VTT 通过解析。

主要阻断项在平台集成层：项目的 yt-dlp ArchiveOrg 字幕轨道适配对 3 个视频 URL 均返回空轨道，服务随后返回 `subtitle_unavailable`。项目链路没有发起字幕文件 HTTP 请求。5 个原始附件通过 Internet Archive 公开文件端点独立取回，SHA-256 均与采集回执一致。

## 2. 平台抽取与许可范围

抽取池按固定顺序为 `Internet Archive`、`Wikimedia Commons`。使用 Python `secrets.randbits(128)` 生成 seed `326591177287492597204726524381134284180`，再用 `random.Random(seed).randrange(2)` 抽得下标 0：Internet Archive。Internet Archive 的元数据文档将 `licenseurl` 定义为覆盖该 item 内容的许可链接；每个入选 item 均有明确的 CC BY 或 CC BY-SA 链接，原链接和来源页保存在 `licenses/` 与 [manifest.json](manifest.json) 中。[Internet Archive metadata 文档](https://internetarchive.readthedocs.io/en/stable/metadata.html)

入选条目的许可为 CC BY 4.0、CC BY 3.0、CC BY-SA 4.0。样本权限依据来自 item 级许可元数据，署名来源保留在许可记录中。Wikimedia Commons 只作为抽取池候选，本轮未从该平台采样；其官方说明要求按具体文件页核对许可。[Commons 文件复用说明](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia) TED 未进入抽取池，因为其官方许可说明为 BY-NC-ND，并限制内容改动。[TED 许可说明](https://help.ted.com/hc/en-us/articles/360004233294-How-do-I-license-TED-or-TEDx-content)

所有字幕都来自 Internet Archive item。两个 ID 以 `youtube-` 开头的归档条目仍按 Internet Archive 计数，不代表直接 YouTube 平台验收。采集只访问公开元数据和已列出的字幕附件，没有登录、cookie、风控绕过或付费模型请求。

## 3. 九维扩样覆盖矩阵

| 维度 | 实测数量 | 未测与缺口 |
| --- | --- | --- |
| 平台入口 | Internet Archive 1 个平台、3 个视频 item、5 条轨道；公开元数据 API 与附件 HTTP 均可读 | 手机端 0；其他平台 0；项目服务集成 0/3。不同平台差异未测 |
| 语言 | 源标签 `eng` 1、`en` 1、`fr` 1；轨道级语言未确认 `und` 2 | 中文、混合语、方言/口音 0；未运行自动语言识别，也未做人工语言质量评审 |
| 内容场景 | 会议/技术演讲标题 1；书籍采访/评论标题 1；类型未确认 1。均为 Archive.org 归档视频条目 | 直播、课程、会议录制以外场景、影视等均无足够证据；没有观看媒体 |
| 格式 | VTT 4 条、SRT 1 条 | v3 契约格式 VTT/SRT/JSON3/TTML 测了 2/4（50%）；扩样矩阵格式族 SRT/VTT/ASS/JSON/XML/平台原生测了 2/6（33.3%）。ASS、JSON3、TTML/XML、平台原生均未测 |
| 时间轴 | 5 条轨道共 1,850 个源 cue；有限时间值 1,850/1,850，倒置 0、起始时间回退 0、重叠 0 | 纯文本解析会移除时间轴；不代表输出保留时间。MNN SRT 的 302 个 cue 使用两位小数，解析器无法识别 |
| 编码 | UTF-8 严格解码 5/5；替换字符 0 | GBK、UTF-16、BOM 变体、emoji/特殊符号覆盖没有独立样本 |
| 噪声与说话人 | 无音视频证据 | 音乐、多人串话、同传、自动字幕与音频对齐、说话人识别均未测；本轮没有下载或播放视频/音频 |
| 边界条件 | 一条解析正文 71,658 字符，超过默认 `LLM_MAX_INPUT_CHARS=60,000`；未调用 LLM | 空字幕、单 cue、超高密度、重复、倒置等真实边界样本未测；长字幕只验证了读取解析 |
| 平台兼容与编辑 | 原平台公开字幕附件直取 5/5；真实项目字幕服务 0/3 视频 URL 通过 | 导入、预览、导出、二次编辑、移动端和跨端兼容未测；当前 v3 返回纯文本，不提供时间轴导出验收能力 |

场景分类只依据归档条目标题；没有将标题或报告文字计入字幕正文语言覆盖。来源标记显示自动生成/ASR 3 条，手工字幕已确认 0 条，来源未知 2 条。

## 4. 样本结果与量化口径

解析器通过率分母为 5 个实际取得的字幕文件：4/5 = 80%。项目集成通过率分母为 3 个不同视频 URL：0/3 = 0%。同一视频的英/法轨道和 SRT/VTT 轨道没有增加视频分母。直接附件取回率为 5/5 = 100%。源 cue 时间审计用 1–3 位小数的独立只读规则解析；该审计没有改变应用解析结果。

| 样本 ID | 格式 / 语言证据 | 来源标记 | bytes | cues | 解析结果 |
| --- | --- | --- | ---: | ---: | --- |
| `IA-lca2019-Awesome_Monitoring_Infrastructure_Using_the_Elastic_Stack-eng-vtt` | VTT / `eng` item 元数据 | 自动生成 | 105,766 | 1,230 | 通过，71,658 字符；超 60,000 字符配置边界 |
| `IA-youtube-6k-kbg3_Drc-en-vtt` | VTT / 文件名 `.en` | 未确认手工或自动 | 685 | 8 | 通过，400 字符 |
| `IA-youtube-6k-kbg3_Drc-fr-vtt` | VTT / 文件名 `.fr` | 未确认手工或自动 | 770 | 8 | 通过，478 字符 |
| `IA-mnn_23214_387-en-srt` | SRT / 轨道语言 `und` | 文件名 `.asr.`，自动 ASR | 30,363 | 302 | 失败：`subtitle_invalid` |
| `IA-mnn_23214_387-en-vtt` | VTT / 轨道语言 `und` | 文件名 `.asr.`，自动 ASR | 30,975 | 302 | 通过，20,504 字符 |

MNN SRT/VTT 的源 cue 正文在忽略 cue ID、时间行、标签并归一空白后相同；保留两条格式测试，独立正文计为一份。全部样本的 SHA-256 与捕获回执一致。原始文件、脱敏副本、许可记录、时间、格式与 hash 见 [manifest.json](manifest.json)、[test-results.json](test-results.json) 和 `raw/`、`raw-extra/`。

邮箱/电话规则在 5 份正文中命中 0 次。这不证明内容不存在语义隐私；没有人工复核私密姓名、联系方式或上下文信息。公开署名只作为来源元数据保留，聊天中未复制完整字幕。

## 5. 失败证据

**阻断：ArchiveOrg 项目集成 0/3。** [platform-checks.json](platform-checks.json) 记录三个视频 URL 的 yt-dlp 轨道数均为 0，项目服务返回 `subtitle_unavailable`，应用端字幕 HTTP 未开始。与此同时，平台 metadata 列出的 5 个字幕附件全部可直接下载且 hash 校验成功。这定位为集成适配故障，不是平台无字幕，也没有把直接下载结果计作集成通过。

**一般：MNN SRT 解析 0/1。** 源文件时间行示例为 `00:00:00,49 --> 00:00:05,82`，其小数位是两位；当前应用正则要求三位毫秒，解析器因此找不到 cue 并返回 `subtitle_invalid`。同一正文的 VTT 轨道通过。独立时间审计识别了 SRT 的 302 个 cue，时间均有限、非倒置、按源顺序排列且无重叠；这不改写 SRT 的解析失败结论。

采集辅助脚本还遇到 Python/httpx `ConnectError`、原始目录 ACL 写入拒绝、UTF-8 编码器未初始化以及一次 PowerShell 布尔字面量错误。所有步骤均已解决，错误阶段和重试记录在 [collection-errors.json](collection-errors.json)；它们没有造成最终字幕 HTTP 失败，不进入样本通过率。

## 6. 平台行为与根因

实际探测到的 yt-dlp ArchiveOrg extractor 把 `entries[p['orig']]` 初始化为含空 `subtitles` 字典的对象，随后将字幕轨道写入 `entries[p['orig']][track['label']]` 顶层键。项目适配器只读取 `info['subtitles']` 和 `info['automatic_captions']`，所以三个 Archive.org item 的字幕轨道都未进入项目窄接口。这是依据本机 extractor 源码与 3 个真实 URL 的空轨道结果得出的根因判断。[本机 ArchiveOrg extractor](../../../.venv/Lib/site-packages/yt_dlp/extractor/archiveorg.py:267)、[项目 yt-dlp 适配器](../../../backend/app/services/ytdlp_service.py:54)；上游代码也可在 [yt-dlp ArchiveOrg extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/archiveorg.py) 查阅。

SRT 根因是格式精度兼容：项目 `_TIMESTAMP_RE` 匹配恰好三位毫秒，[subtitle_service.py](../../../backend/app/services/subtitle_service.py:19)；这份源 SRT 使用两位小数。需求文档声明了 SRT 支持，[requirements.md](../../../docs/requirements.md:97)，因此应明确产品要拒绝非典型时间精度还是接受 1–3 位并做规则化。

本轮只选中一个平台，无法比较平台差异；可以比较轨道格式与来源类型。API 元数据中带 `youtube-` 前缀的 item 仍属于 Internet Archive 样本。

## 7. 修复建议与下一轮

1. 在 yt-dlp 上游修正 ArchiveOrg 字幕结构，或在唯一适配层 `ytdlp_service.py` 将 extractor 的轨道结构正规化为应用约定的 `subtitles/automatic_captions` 格式。修复后先用这 3 个 item 重跑真实平台链路，并确认应用自身完成轨道发现、HTTP 取回与解析。
2. 对 SRT 两位小数精度定义明确的解析策略。若支持宽松兼容，须按小数位数补齐毫秒并保留原始文件作为证据；若只接收规范输入，应返回能定位 cue 的错误。不要在验收结果中预先修补源样本。
3. 平台链路恢复后，再补 JSON3、TTML/XML、ASS 和其他平台/来源；新来源继续逐 item 核实许可。没有媒体证据时继续将音画对齐、噪声和说话人准确性标为未测。

本轮没有变更业务实现。独立验收计划、辅助采集脚本和所有产物均位于本报告目录或其独立 planning 目录。

## 8. JSON 结果

完整机器可读结果见 [acceptance-summary.json](acceptance-summary.json)；细项、逐轨道指标和平台检查见 [test-results.json](test-results.json)。本次摘要：5 条轨道、3 个视频、4 份独立正文、168,559 bytes；直接取回 5/5；解析器通过 4/5；项目平台集成通过 0/3。
