# 浏览器完整流程验收（2026-10-04）

## 工程约定

UI/视觉/交互变更先使用 `ui-ux-pro-max` 和 `design-system`；skill 指引优先于计划；颜色、字体和时长使用 primitive → semantic → component 三层 token，新增能力保持可配置；`ytdlp_service.py` 是唯一接触 yt-dlp 的生产层；视觉层只读 scene，下载与 AI 状态独立，模块通过窄接口通信。本次只增加验收脚本、结果和文档，未改生产 UI、模型资源、配置或用户数据库。

## 验收方法与证据范围

`local_harness.py` 在 `.planning/2026-10-04-platform-browser-summary/browser/` 生成自有的 3 秒 H.264/AAC 视频、360p/720p 双变体 HLS、标准 HTML video 和 WebVTT track。独立静态 HTTP 服务提供内容，运行原 FastAPI 应用和 Vite 前端，使用每轮新建的隔离 SQLite 数据库及下载目录。浏览器通过页面按钮和表单完成操作。

应用的认证、解析、字幕、翻译、总结、下载、job 和文件 API 均真实调用，没有 Playwright route 拦截、应用 API mock、extract_info 替换或 JS 状态注入。yt-dlp 真实读取 HTML、HLS 和 track，并下载本机 HTTP 分片；字幕服务真实请求 WebVTT 并转换文本。

本机夹具这一轮唯一模拟的是独立 OpenAI-compatible **LLM upstream**：返回可重复的翻译/总结，或按控制请求返回 503。这验证页面、业务服务和 HTTP 错误传播，不能据此判断真实模型质量或公网平台支持。本机夹具脚本不读取 `.env`，没有调用付费模型。后面的公网追加流程由主agent另行执行，范围单列。

使用本机已安装 Edge headless 和 npm 缓存中的 playwright-core。以 `--disable-webgl --disable-gpu` 验证项目已有 CSS fallback，因此本报告不证明 Live2D / 16K 纹理在 GPU 下可用。

## 当前结果

结果见 [results.json](results.json)，LLM 模拟调用记录见 [upstream-results.json](upstream-results.json)。桌面视口为 **1440 × 900**，窄屏视口为 **375 × 812**，各完成以下操作：

| 流程 | 检查内容 |
| --- | --- |
| 注册、退出、登录、刷新、最终退出再刷新 | 原 auth API 与 JWT 恢复真实运行，退出后回到登录门 |
| 解析和选清晰度 | 原 yt-dlp 解析 HTML/HLS，页面有 720p / 360p 两档并显式选中 |
| 字幕、翻译、总结 | 英文 WebVTT 尾句进入正文；译文/摘要显示；AI 操作不扣下载额度 |
| 正常字幕来源下载 | 强制走服务器，下载 job 完成，浏览器收到并保存文件 |
| 无字幕时手动总结 | 返回 422 / `subtitle_unavailable`，错误局限在 AI 面板；下载保持可用，并切到 360p 保存 |
| 模拟 LLM upstream 503 | 应用返回 502 / `llm_error`，AI 面板显示原因；720p 下载仍成功 |
| 文件校验 | 六个浏览器保存产物均由 ffprobe 核对 H.264、AAC、至少 3 秒；高度匹配所选 360p 或 720p |
| 布局 | 认证、入口、选格式、摘要、AI 错误、下载完成均核对 document.scrollWidth；页面无水平溢出 |

每个视口有 3 个下载成功，合计 6 个。两视口合计 40 项记录，最终 `pass: true`，未发现应用 JavaScript pageerror 或非预期 console error。预期错误的 HTTP 状态保存在请求记录中，不被当作正常请求成功。18 张截图保存在本目录，例如 [桌面摘要](desktop-summary.png)、[375px 摘要](mobile375-summary.png)、[375px 无字幕提示](mobile375-no-caption.png) 和 [375px AI 错误](mobile375-ai-error.png)。

HLS remux 可能改变字节，因此 SHA-256 仅标识本次浏览器产物；通过条件是音视频、时长和所选高度，不要求与输入 MP4 字节一致。隐藏的角色菜单可在视口外，未造成文档横向滚动；本次未检验 GPU 下的角色菜单交互。

## 已测失败和修正

首轮验收脚本错误地把无字幕 error_type 写成 `no_subtitles`，应用实际契约为 `subtitle_unavailable`。首轮原始失败保留在 [initial-harness-failure.json](initial-harness-failure.json)。修正的是脚本断言，无生产 bug 修复。

最初直接 MP4 HTML source 可成功下载，但 Generic HTML5 extractor 的 source `vcodec` 为 None，项目只能展示“最佳”。为覆盖真实清晰度选择，fixture 改成声明 CODECS / RESOLUTION 的双变体 HLS；没有模拟应用提取结果。最终脚本显式切换 360p，并验证保存高度，避免仅检验按钮切换。

## 公网 Archive.org 桌面追加流程

主agent另用真实后端既有模型配置，对 [已许可短片](https://archive.org/details/youtube-6k-kbg3_Drc) 执行 `--summary-only --viewport desktop`。结果见 [live-archive/results.json](live-archive/results.json) 与 [公网页面摘要截图](live-archive/desktop-summary.png)：真实注册/退出/登录/刷新、HTTPS视频解析、页面触发总结和显示共 **9项检查通过、0脚本错误**。解析与总结API均200；响应标示 `deepseek` / `deepseek-flash`。来源许可为CC BY3.0，沿用[初始样本清单](../2026-10-03-single-platform-subtitles/manifest.json)。

这条追加记录没有模拟应用API或LLM upstream，补齐一条公网“解析→页面总结”证据。仅验证桌面；未执行公网下载、字幕翻译或公网页面375px流程。一次总结API调用不等于供应商POST统计，该记录没有计数内部模型请求；不混入独立质量语料的12次调用台账。API结果显示5条相关要点，仅作为页面结果展示证据，不将其计为自然字幕的独立质量评分。

追加时后端8061与前端5186使用独立验收数据库；完成后均已停止。本机夹具40项及公网追加9项各自留证，不合并为多平台成功率。

## 重跑命令

仓库根目录执行：

```powershell
& '.venv\Scripts\python.exe' 'docs/acceptance-reports/2026-10-04-browser-e2e/local_harness.py'
```

要求项目 Python 依赖、前端 node_modules、ffmpeg/ffprobe、系统 Edge 和 playwright-core 已存在。本机已满足。脚本默认从 `npm config get cache` 的 `_npx` 子目录寻找 playwright-core，也可用 `PLAYWRIGHT_CORE_PATH` 指定已安装的包目录。应用端口为 backend **8051**、静态媒体 **8052**、LLM upstream **8053**、Vite **5185**。服务进程隐藏启动，finally 中结束；数据库和媒体保留为 Git 忽略的本机证据，不触碰 `backend/jobs.db`。

公网 UI 验收可复用浏览器脚本，对一个已启动且使用隔离数据库的应用服务执行：

```powershell
node 'docs/acceptance-reports/2026-10-04-browser-e2e/browser_flow.mjs' --base-url 'http://127.0.0.1:5186' --video-url '<实际公开视频页面>' --summary-only --viewport desktop --output-dir 'docs/acceptance-reports/2026-10-04-browser-e2e/live-platform'
```

该模式注册独立验收账号并完成页面解析/摘要，使用目标后端既有真实模型配置；单桌面模式会调用一次总结。不执行本机 fixture 控制和下载。省略 `--viewport desktop` 会跑两种视口并调用两次总结。使用 `--browser-executable` 可以指定其他已安装 Chromium/Edge，`--output-dir` 隔离证据，避免覆盖本机全流程结果。真实公网的结果应另列在其输出目录，不能把本机 HTTP 验收计入公网支持成功率。
