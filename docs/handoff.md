# 交接 · 视频下载、平台字幕与AI总结

> 更新：2026-10-05（关机后恢复，完成文档归档）。实验协议、原文证据贯穿合并、响应式角色/触摸修复已提交：`be2bdd5`。前轮实现/文档 `05753e7` / `8713862`；此前Bilibili/inline `e7c29be`、TLS重试 `96b0b59`。验收数据仍为2026-10-04采集，恢复后没有重跑模型。

## 工程约定

1. UI/视觉/交互先用 `ui-ux-pro-max` + `design-system`，skill优先于计划。
2. 颜色、字体、时长走三层token；来源、阈值和模型配置化，避免大规模重构。
3. `ytdlp_service.py` 是唯一接触yt-dlp的层；字幕平台适配不依赖下载任务，LLM仅经 `llm_service.py`。
4. 前端请求通过 `api.js` 和独立hook；视觉只读scene，AI错误不替换下载状态机。

## 已定方向与本轮交付

- 解析、下载、字幕与AI接口要求登录；每日下载额度默认10次，UTC粒度。AI操作不扣下载额度，AI独立计费未实现。
- AI内容总结是主目标；字幕是内容来源，可清理重复内容，长内容分段归纳再合并，保留尾部结论。
- 滚动首页保留在登录后。没有新增时间轴导出、音频转写、问答、思维导图、支付或批量下载。
- 用户授权多agent逐步完成平台覆盖、完整浏览器流程与总结质量。所有agent继承主agent的模型与推理设置。
- 当前已完成实验协议/源证据、独立质量评测、响应式布局与手势，并交叉复审。默认保持json_object；供应商严格约束、长文组织与部分归因仍未达标。旧 `real_platform_subtitle_acceptance` / `v3_review` 历史会话继续停用。

## 最新验证与证据

| 项目 | 结果 | 范围与限制 |
| --- | --- | --- |
| 后端 / 前端 / 构建 | 234/234、73/73、通过 | 新协议/状态/槽位/容量/证据贯穿与既有平台认证下载；布局/菜单回归。已知弃用/navigation/大chunk提示保留 |
| 新模型台账 | 19次预占，18次HTTP200，1次ConnectError；52062报告tokens | 六profile；剩余1次不用。HTTP成功不等于契约或质量成功，没有自动付费重试/降级 |
| 选定默认 | natural-refined，5/5/7点，12条完整/2条部分保留 | 原文边界和提示联合恢复首轮遗漏的末尾radius/area、崩溃/不停后果；长末点365字仍混装，文化归因和范围/成绩录入等仍有不足 |
| 实验协议 | Responses可返回8点，Beta可返回空首槽和294字末点；本地严格拒绝 | json_schema/strict_tool仅显式可选，auto未切。工具只序列化参数不执行、无第二轮POST；240在默认模式只是softtarget |
| 基础角色矩阵 | 320/375/720/1440真实RTX4050布局/GPU41项、22截图 | 较早源码阶段，各尺寸16K驻留、实际控件/角色交互/尺寸调整；Windows视口不是真机 |
| 最终375触摸 | 5项通过，0pageerror/console/failedRequest | 取消不误开、tap菜单、横拖60.54px且文档不滚、原生竖滚185px；七源hash在该run开始直接采集 |
| 焦点修复 | select y109..149→280..320，几何1项通过 | 该专测整体仍有Google字体网络1错误，不算全clean，不与41/5混为47全成功 |
| 降级与已知限制 | 8K模拟跳过16K模型目录/parse可用；原模型未改 | 没有真手机调试通道证明，未真机/低GPU实测。异步字体/UI尺寸变化可能使拖动短暂重新居中 |

优先读[本轮摘要协议与质量](acceptance-reports/2026-10-04-schema-summary-quality/report.md)、[协议设计](acceptance-reports/2026-10-04-schema-summary-quality/provider-design.md)与[响应式角色](acceptance-reports/2026-10-04-responsive-mascot/report.md)。UI历史源码hash是事后逆向重建，最终触摸源码hash才在运行开始直接捕获，两者明确区分。MIT原语料/事实及衍生评测继续按NC/SA，旧证据未改。

## 前轮验证（184/66）

| 项目 | 结果 | 范围与限制 |
| --- | --- | --- |
| 后端全量 | 184/184通过 | 新增15项输出控制/配置/数量边界用例，含红→绿；原有平台、认证、下载和TLS测试保留 |
| 前端全量 / 构建 | 66/66 / 通过 | 生产前端未改；已知jsdom navigation、Starlette弃用及大chunk提示仍存在 |
| 自然字幕 | MIT OCW原生中文608、英文2199、英文长课34894字符 | 三份独立自然字幕，预先冻结4/4/6个主事实；未覆盖中文长课/六种语言×长度组合。CC BY-NC-SA4.0，仅非商业评测 |
| 模型实测 | 六个profile共24次POST，HTTP均200；89567个供应商报告token | HTTP200不等于有效总结：漏JSON闭合、推理耗尽空正文、超限8/12/11点均保留。预算已耗尽，不重置或自动重试 |
| 当时最终选择 | bounded版本三源返回5/6/7点；当时service/config字节与冻结快照一致 | 14个主事实概念语义覆盖不等于每个claim准确；中篇usually→always过强，长篇依赖变量例泛化有范围风险，末条426字比基线306更大。最后concise候选失败已回退，长组织/压缩未达标 |
| 公网375px下载 | 9项检查、1个实际浏览器保存文件 | 854×480 H.264/Opus、75.741秒、Matroska、8854893字节；源仅提供“最佳”，不声称选择480p |
| 默认GPU | Windows Edge桌面和375px均RTX4050/ANGLE D3D11，16K纹理驻留、角色可见 | 只覆盖当前硬件；移动示例按钮遮角色脸、桌面脚部出底边，真手机、低档GPU与完整角色交互未测 |

优先读取[自然字幕与输出修复报告](acceptance-reports/2026-10-04-natural-subtitle-quality/report.md)、[独立来源/事实清单](acceptance-reports/2026-10-04-natural-subtitle-quality/source-report.md)及[公网移动/GPU报告](acceptance-reports/2026-10-04-public-mobile-gpu/report.md)。最后候选失败、回退原因与当前快照绑定见质量报告的delivery profile，不能拿失败候选的短句当作已交付改善。

## 前轮验证与证据（历史）

| 项目 | 结果 | 范围与限制 |
| --- | --- | --- |
| 后端全量 | 169/169通过 | Bili平台46新增用例、inline/正文失败回退、错误分类、源数据上限及既有下载/认证/TLS逻辑 |
| 前端全量 / 生产构建 | 66/66 / 通过 | 既有jsdom navigation及Starlette/httpx弃用提示仍存在；不将提示当成测试失败 |
| 本机浏览器 | 桌面和375px共40项检查通过；6次保存文件 | 应用API、yt-dlp、字幕HTTP、HLS下载均真实运行；仅LLM upstream模拟。ffprobe核对所选360p/720p和音视频，18个布局状态无水平溢出 |
| 公网浏览器追加 | Archive.org已许可短片桌面9项通过 | 实际HTTPS视频解析→页面总结，响应为deepseek/deepseek-flash；未测试公网下载或公网375px。总结API次数不等于供应商POST计数 |
| Bilibili公开字幕 | 一条匿名样本正文成功：1973字符、136行 | 专用view→分P CID→dm/view→JSON路径；仅访问探针，不保存未许可正文/签名地址，不对该来源调用LLM |
| 其他平台探针 | Archive元数据/轨道成功；Commons两项403；YouTube网页200 | 访问限制不当作无字幕；网页可访问不当作字幕成功。12组公开探针已用完 |
| 总结受控质量 | 短/中/长before+after，共12次真实POST，全200 | 三个自编英语源→中文输出；提示词允许1–7个独立完整事实。短3碎片→1点，中重复改善，长7→6且尾部条件/数字保留；长内容日志计数和批准范围仍有冗余 |
| 提示词/数据溯源 | before/after源码、prompt、语料和结果哈希已核对 | before基线b62f7d4；脚本发请求前校验对应prompt。真实质量不是完整准确率指标，mock仅证明数据路由与API消费契约 |

读取前轮三个报告：

- [平台扩展](acceptance-reports/2026-10-04-platform-expansion/report.md)：公开请求、许可/访问范围、源数据处理和红绿回归。
- [浏览器完整流程](acceptance-reports/2026-10-04-browser-e2e/report.md)：本机40项、6下载和独立公网Archive桌面9项。
- [总结质量](acceptance-reports/2026-10-04-summary-quality/report.md)：固定语料、真实before/after、12次预算、逐事实核查与残余缺陷。

旧 [TLS/平台验收](acceptance-reports/2026-10-03-platform-quality/report.md)、[AI总结修复](acceptance-reports/2026-10-03-ai-summary-regression/report.md) 和 [原始字幕验收](acceptance-reports/2026-10-03-single-platform-subtitles/report.md) 保持历史证据。旧121/66、3/8及0/5等数字对应各自测试时间；旧浏览器审批阻断说明不作为本轮未完成项。

## 实现与窄接口

| 模块 | 职责 |
| --- | --- |
| `services/ytdlp_service.py` | 唯一yt-dlp入口，平台native优先；`use_public_sources=False`提供一次明确通用回退；规范化URL和inline轨道 |
| `services/subtitle_sources.py` | exact-host注册式平台分发：Archive.org与Bilibili |
| `services/bilibili_subtitle_source.py` | 匿名元数据、BV/分P/CID关联、可信HTTPS字幕来源、语言/类型校验 |
| `services/subtitle_service.py` | 轨道选择、HTTP或inline正文、字节上限，SRT/VTT/JSON3/TTML/Bilibili JSON解析；native正文失败最多generic一次 |
| `services/network_retry.py` | 只包裹幂等GET的有限瞬时网络/EOF/502/503/504重试，指数退避 |
| `services/llm_service.py` | 摘要/翻译窄接口；显式实验协议、严格本地状态/槽/数量/长度校验，原文边界贯穿分层merge；不执行工具、不截断、不自动POST重试 |
| `routes/subtitle.py` / `summary.py` | 登录鉴权、请求响应与局部错误映射；不依赖平台JSON |
| `api.js` / `useAuth` / `useDownload` / `useVideoInsights` | 前端请求边界与分别独立的状态/请求生命周期 |
| `VideoInsights.jsx` | 纯props展示；解析语言列表为空仍提供自动选源语言和显式操作 |
| `styles/global.css` / `pixi/theme.js` | 三层样式token与PIXI颜色桥接 |
| `pixi/mascotConfig.js` / `mascot.js` / `stage.js` | 区域几何、纹理能力、触控默认配置；角色只读矩形/scene，取消非点击，浏览器原生滚动保留，模型资源不改 |

### 平台回退边界

- 支持普通 `bilibili.com` / `www.bilibili.com` BV路径；短链接、AV形式和其他host仍交通用路径。
- `p=2`查正确CID。明确非法/不存在分P映射 `invalid_url`，不让通用提取器误用默认分P；元数据损坏或访问失败仍可回退。
- Bili正文JSON验证字段、数值与字节上限；CDN为限定来源，拒绝跨来源redirect。通用Bili inline SRT及 `ai-zh` 字幕兼容。
- native选轨道/正文获取/解析失败最多通用尝试一次；通用仍失败时保留原生错误。普通generic正文失败不重复提取。
- 没有加入登录cookies、风险控制规避、ASR/OCR；单条匿名成功不代表全站可用。

## 配置与启动

完整环境变量表见根README。主要值：

- `SUBTITLE_MAX_BYTES=5242880`，`SUBTITLE_TIMEOUT_SECONDS=30`。
- `NETWORK_RETRIES=2`为每个受控请求/yt-dlp重试环节的额外次数；`NETWORK_RETRY_BACKOFF_SECONDS=0.5`为指数退避基数，配置必须非负且有限。
- httpx GET处理瞬时传输/超时、远端EOF及502/503/504；4xx、无字幕、格式错误不进入该重试器。yt-dlp按原生错误分类使用有限retries；LLM POST不自动重试。
- `LLM_MAX_INPUT_CHARS=60000`；分段默认20000字符、最多16段、每次最大输出4096 tokens。翻译仍有独立输入上限。
- 配置供应商为deepseek、API模型ID `deepseek-flash`；凭据只在Git忽略的 `backend/.env`。
- `LLM_SUMMARY_RESPONSE_FORMAT=auto|text|json_object|json_schema|strict_tool`、`LLM_SUMMARY_THINKING_MODE=auto|enabled|disabled`。auto继续DeepSeek json_object+disabled；后两格式显式实验、本地拒绝违约，不设为默认；DeepSeek strict_tool不能enabled推理。通用auto和翻译不加摘要专用控制，用户`.env`未改。
- `LLM_SUMMARY_MAX_POINT_CHARS=240`：兼容模式精简目标、实验模式本地硬校验。`LLM_SUMMARY_SOURCE_CONTEXT_CHARS=1200`：每原分段头尾证据穿层保留，组大小包含JSON/context；`0`恢复旧notes形状，无容量时明确失败而非删证据。原文中部仍可能有未被notes/边界保留的事实。

```powershell
# 在项目根首次准备依赖
uv sync
cd frontend
npm install

# 后端另开终端，8000端口
cd E:\install_video\backend
uv run uvicorn app.main:app --reload --port 8000 --env-file .env

# 前端另开终端
cd E:\install_video\frontend
npm run dev
```

本机Python虚拟环境在根 `.venv`；ffmpeg/ffprobe必需；Node应满足 `^20.19.0 || >=22.12.0`。若开发机需要已有系统proxy，可仅在验收/启动进程设置HTTP(S)_PROXY，不改用户系统配置或绕过平台访问限制。

```powershell
cd E:\install_video\backend
..\.venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend
npm test
npm run build
```

完整本机浏览器复跑命令见对应报告，新输出必须独立且不能覆盖。历史12/24台账耗尽且不改；本轮20上限使用19预占后停止，剩余1次不继续调用或重置。各profile须对应源码/config/hash，不能仅改标签冒充复现；只读check_evidence命令见质量报告。

## 状态与下一步

- 实现已本地提交 `be2bdd5`，文档与本轮证据已归档提交。用户`AGENTS.md`仍未跟踪，未提交.env/db/.planning/临时媒体。`.gitattributes`保留新证据及被实时捕获源码字节；stage.js混合EOL按原字节保存，不规范化后假称当时源码。
- 历史8051/8052/8053/5185、8061/5186、8062/5187及本轮8063/8064/5188测试服务均已停止；用户jobs.db与原模型资源未改。
- 源样本许可、SHA-256、历史原件和失败记录保持原样；新脚本不依赖ACL受限的旧raw目录，不更改其权限。
- 当前Windows硬件GPU/16K角色及模拟视口触摸菜单已补实测；真手机触摸菜单、真实低GPU纹理上限仍未证明，模型资源未改。
- 下载失败额度退还、独立AI额度、支付、SSE、队列横向扩展和生产部署仍未实现。

建议下一项：**事实/主题层与逐声明校验**。先用可追溯原文建立带限定与归因的主题/事实中间结构，再选择重点，避免段摘要过度省略和最后一点收纳剩余内容；不能靠字符串截断或继续声称供应商schema保证。随后在可用真机通道上验键盘/触摸/低内存，并按授权许可考虑轻量模型和字体本地化。端点query/fragment配置未支持、异步布局拖动重居中列已知Minor。当前调用停止，等待用户指示。
