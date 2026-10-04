# 公网移动视口下载与 Live2D GPU 验收（2026-10-04）

本轮完成一个公开视频从 375px 浏览器界面提交、服务端下载，到浏览器保存文件的闭环；另用默认 Edge GPU 设置检查桌面和 375px 视口下真实 Live2D 纹理上传与角色画面。没有修改生产代码、模型资产或用户数据库，没有调用字幕翻译/总结 API。

## 结果与证据边界

| 范围 | 实测结果 | 边界 |
| --- | --- | --- |
| 公网移动视口 | 375×812、触摸上下文，9 项记录通过；注册、解析、下载提交、job 轮询和 file 均使用真实 API | Windows Edge headless 模拟视口，不是真 Android/iOS 手机 |
| 保存文件 | 8,854,893 字节；854×480 H.264 视频 + Opus 音频；75.741 秒；Matroska 容器 | 源仅列“最佳”，下载前没有分辨率元数据；没有声称选择了 480p |
| CSS 兜底流程 | 下载流程禁用 WebGL/GPU；入口、选择、完成三个页面 documentWidth=375，无横向页面溢出 | 用于隔离下载验收，不能证明所有控件布局或交互质量 |
| GPU 桌面与 375px | 两个默认 GPU 上下文均为 NVIDIA GeForce RTX 4050 Laptop GPU / ANGLE D3D11；MAX_TEXTURE_SIZE=16384；实际 16384² 纹理 valid 且有 resident GL context | 不是 SwiftShader；仍只覆盖这台 Windows 机器与当前驱动 |
| Live2D 实际画面 | core 已存在、加载层自然消失；两张截图均能看见角色和背景；0 pageerror/console error/warning | 桌面脚部超出屏幕底边；移动示例按钮与角色脸部视觉重叠，不宣称所有部位或所有控件完整无遮挡 |
| AI 调用 | 0 个 summary / translate 请求；后端未配置 LLM | 下载成功不能代替 AI 能力验收 |

原始记录：[results.json](results.json)、独立离线文件复检：[file-inspection.json](file-inspection.json)、服务收尾：[service-results.json](service-results.json)。服务端口 8062 / 5187 的子进程均已停止，现场 TCP 监听复核为空。没有将视频、数据库、运行日志加入版本化报告。

## 公开视频与文件核对

沿用前轮公开样本 [Imagine the Consequences](https://archive.org/details/youtube-6k-kbg3_Drc)，许可 CC BY 3.0，来源约 75.74 秒。真实解析返回英语/法语字幕列表，但本轮不请求字幕或模型。

浏览器手动动作选择 API 实际列出的“最佳”、勾选“强制走服务器”、点击“下载”。下载请求 mode=server，随后真实 job 轮询，最终浏览器接收 `/api/file/...` 下载事件并 `saveAs`。ffprobe 对落盘文件检查视频流、音频流和完整时长，视频 75.741 秒与源元数据相差 0.001 秒。

服务给浏览器的文件名是 `Imagine the Consequences.mkv`，源音频为 Opus，因此本报告按实际 Matroska / H.264 / Opus 记录，不套用旧本地 HLS 的 MP4 / AAC 结论。初版辅助脚本本地保存名写了 `.mp4`，后来仅将相同文件改名为 `.mkv`，SHA-256 不变：`cf2e47033a22c2d5dc50ab27e7f3da0a34b6fb22b95ed36155b7fba8d71dc4d9`。新脚本使用浏览器建议扩展名；离线复检没有再次请求公网或应用。

## GPU 判定依据

GPU 两轮都只使用 `--no-first-run`，没有 `--disable-webgl` / `--disable-gpu`，没有强制 SwiftShader、模型替换、应用路由 mock 或 React 状态注入。只读观察现有 canvas 的 WebGL 参数、PIXI BaseTextureCache、GPU 设备与功能状态、模型资源响应、preloader 以及截图。

两轮加载期间分别约 8.0 / 8.1 秒（具体毫秒见 JSON），preloader 自然卸载；模型纹理 `/live2d/bai/白.16384/texture_00.png` 的宽高均为 16384，尺寸未超出设备上限，PIXI 报告纹理有效且已有 GL context 资源。HTTP 200 只当作资源访问证据；GPU 成功判断同时依赖纹理状态和实际可见角色截图。

图像复核：[桌面真实 GPU](gpu-default-desktop.png)、[375px 真实 GPU](gpu-default-mobile375.png)。主输入与解析按钮可见；375px 的示例 B站按钮与角色脸部有视觉重叠，本轮没有调整布局，也没有测完整角色菜单、拖动、低 GPU 纹理上限或真实手机。GPU 上下文仍使用 Windows UA，375px 视口也不意味着自动触发 Android/iOS 的 low 性能档。

## 辅助脚本修正与可重跑方式

[initial-harness-failure.json](initial-harness-failure.json) 保留初次 `page.goto` 等整页 `load` 超时。改为等待 DOMContentLoaded，再等待真正的应用控件，没有隐藏加载层或跳过应用初始化。

[format-metadata-observation.json](format-metadata-observation.json) 保留第二次脚本要求已知分辨率导致的断言失败；真实 Archive 元数据仅提供“最佳”。最终脚本按实际元数据记录未知分辨率，落盘后 ffprobe 验证，不虚构分辨率选择。这两次属于验收辅助脚本假设修正，不是生产错误修复。

从仓库根目录执行（默认输出到忽略目录 `.planning/2026-10-04-public-mobile-gpu/<timestamp>/evidence`）：

```powershell
.venv\Scripts\python.exe docs\acceptance-reports\2026-10-04-public-mobile-gpu\acceptance_harness.py
```

可用 `--output-dir <新的空目录>` 指定证据目录；harness 将它传给浏览器脚本，`results.json`、截图和 `service-results.json` 都进入该目录。两层脚本在启动服务/浏览器前拒绝非空目标，JSON 写入额外拒绝覆盖。直接跑浏览器脚本时同样支持此参数和安全默认目录，但需先启动应用服务。保存媒体继续留在独立的忽略目录。

仅校验参数与输出路径、不启动服务或联网：

```powershell
.venv\Scripts\python.exe docs\acceptance-reports\2026-10-04-public-mobile-gpu\acceptance_harness.py --output-dir .planning/public-mobile-rerun/evidence --check-output-dir
node docs\acceptance-reports\2026-10-04-public-mobile-gpu\browser_acceptance.mjs --output-dir .planning/public-mobile-rerun/evidence --check-output-dir
.venv\Scripts\python.exe docs\acceptance-reports\2026-10-04-public-mobile-gpu\inspect_saved_file.py .planning\2026-10-04-public-mobile-gpu\saved\archive-mobile375.mkv --output-file .planning\public-mobile-rerun\file-inspection.json --check-output-file
```

离线复检脚本 `inspect_saved_file.py` 读取已有媒体、运行 ffprobe 和 SHA-256，将结果写到指定的新 `--output-file`，不修改输入视频，拒绝覆盖现有 JSON；去掉 `--check-output-file` 才执行复检。它没有应用或网络调用。

使用现有 Edge、缓存中的 playwright-core、ffprobe 与项目虚拟环境，不安装额外依赖。Windows 系统代理只传给本次服务进程；LLM 环境清空，独立 DB / 下载目录位于 `.planning/2026-10-04-public-mobile-gpu`。服务在 `finally` 停止；最长浏览器子进程 600 秒。本轮只有最终成功执行了一次公网下载。

本目录 JSON / PNG 仍是上文原始实际运行的冻结证据。之后仅增加复跑防覆盖和只读离线复检参数，完成脚本语法、空目录接受/非空目录拒绝及离线路径校验；没有再次下载、运行 GPU 或调用模型，不将脚本修正后的检查冒充一次新的实跑验收。

## 后续验收建议

用真 Android / iOS 设备验证浏览器保存、前后台切换、低内存/低纹理上限、角色菜单和触摸拖动；选择提供明确多分辨率元数据的另一公开来源复核分辨率选择。当前移动示例按钮与角色的视觉重叠可作为独立 UI 改进项，在按技能检索制定布局后解决，避免本轮临时硬编码。

## 工程约定

涉及 UI / 视觉 / 交互时先读 `ui-ux-pro-max` 和 `design-system`，技能指导优先于计划；本轮已检索移动布局、性能及 React 指引，仅观察现有 UI。颜色、字体和动画时长走三层 token；新增能力可配置、数据驱动，避免大规模重构。模块通过稳定窄接口单向依赖，后端仅 `ytdlp_service.py` 接触 yt-dlp，视觉层只读 scene 状态，不修改下载核心。验收脚本仅使用公开应用接口与只读渲染观察，不绕过这些边界。
