# 正式 HTTP 流程与既有失败用例补验

执行日期：2026-10-09 开始，2026-10-10 完成零付费部分；目录沿用任务开始日期。

**范围结论：实际产品 API 20/20、页面交互 4/4、既有工具故障 10/10 通过。真实供应商调用 0 次。真实模型内容复验尚未执行，因此不能宣称正式模型流程或总结质量全面通过。**

工程约定：适用 skill 优先；UI 设计须用 `ui-ux-pro-max` + `design-system`，样式采用 primitive→semantic→component token；能力数据驱动、可配置，避免无关重构。保持窄接口及单向依赖：产品 yt-dlp 仅由 `ytdlp_service.py` 接触，视觉层只读 scene。此次仅新增验证工具、证据和说明，产品代码、原字幕、历史账本、账号与配置不改。

## 1. 实际链路与测试边界

使用独立临时 SQLite、真实 JWT 鉴权、Uvicorn 实际 TCP 服务和当前产品路由。既有指定账号仅以只读查询复制 id/email/创建时间；不读取密码、不注册新账号、不改线上数据库。临时 JWT 不写入文件或工具输出；**没有验证密码登录表单**。

链路为：视频 URL → 原生 yt-dlp HTML5/HLS 提取 → 原始 VTT 的本地 HTTP 获取 → 当前字幕 parser → 当前 legacy/adaptive 分段、总结与合并 → 实际 HTTP 响应 → React 页面。

本地视频页复用既有媒体夹具、原样提供三份验收 VTT；没有替换字幕提取、parser、summarize_text 或最终响应。供应商端是受控 loopback HTTP fixture，其固定文本只用于传输和渲染验证，**不参与语义评分**。这也不是公网 MIT 提取成功证明。原来源归属及许可见 [corpus manifest](../2026-10-04-natural-subtitle-quality/corpus/manifest.json)。

三次有限公网 MIT 来源探针均为 network 失败，见 [来源与失败映射](source-and-failure-map.md)；该探针直接调用来源服务，未测量其产品 API HTTP 状态。本轮没有重复探针，未声称公网问题已解决。

## 2. API 20 项

| 范围 | 实测结果 |
| --- | --- |
| 未登录总结 | 401 / login_required，0 供应商 POST |
| 既有账号临时会话 /auth/me | 200 |
| 无效 URL、无字幕 | 400 / invalid_url；422 / subtitle_unavailable，均 0 POST |
| zh-short / en-medium / en-long 解析 | 三次 200 |
| 三份字幕读取 | 三次 200；逐字符等于原 TXT，进入总结前归一化结果也相等 |
| 三份总结传输夹具 | 三次 200；短/中各 1，本地长文分段合并 3 POST |
| 上游 503、非 JSON、结构无效、连接中断、超时、finish_reason=length | 六次 502，分别保持 llm_error / llm_invalid_response / llm_incomplete_response 分类 |
| 未配置模型 | 503 / llm_unconfigured，0 POST |

总计本地供应商 **11/20 POST**，包含受控错误尝试；无隐藏重试或真实供应商访问。未测量生产环境默认限流，临时服务使用独立的 300 请求限额。

原报告：[api-http-report.json](evidence/api-http-report.json)；核对清单及哈希：[summary.json](evidence/summary.json)。

## 3. 页面补验

服务器重启中断第一次浏览器工具调用。原 API 报告已完整保留，原临时服务在 600 秒等待期后自动关闭。恢复后使用 `--browser-only`，跳过所有已完成 API 用例。

使用本机缓存 Playwright 与 headless Edge 的新隔离 context；浏览器只允许本轮两个 owned origin。实际操作：输入中篇 URL、解析、查看字幕、生成总结、注入上游 503、再次生成总结。

- 四项通过：解析后的操作区出现；中篇字幕逐字显示；总结/要点夹具显示；错误 alert 出现且总结按钮恢复可用。
- 浏览器实际响应为 parse 200、subtitle 200、summary 200、summary 502；pageerror 为 0，本地供应商 2 POST。
- 发现现有体验问题：**再次总结失败时，上一次结果仍显示，未明确标为旧结果**。错误同时可见，不能把旧结果视作本次成功。
- 此次没有执行下载、翻译、移动端、GPU 性能、全量构建或密码登录测试。

证据：[browser-evidence.json](evidence/browser-evidence.json)、[browser-api-report.json](evidence/browser-api-report.json)、[成功截图](evidence/browser-summary.png)、[失败截图](evidence/browser-upstream-error.png)。

## 4. 包含既有离线失败的工具用例

独立 synthetic 临时工作区与真实 localhost HTTP，复用已有 guard 实现，不改原 phase/账本。十项全部通过，合计 **16/20 本地 POST**（含必要的模拟前阶段脚手架）；付费调用 0。

覆盖：持久预占写失败、模型运行时漂移、索引伪报失败、中断、Client 初始化失败、没有请求证据却报成功、前阶段身份变化、冻结快照篡改、runner 变化、第三次请求超上限。此处检验的是验收工具保护，不意味着产品 API 实现了相同的预算账本或冻结协议。

新增边界测试各只运行一次：guard HTTP 工具 **8 passed**；产品 HTTP 工具 **4 passed in 2.02s**。后者实际验证代理污染不能改变目的地、多个 client 共享 20 次上限且第 21 次发前拒绝、非 owned URL 拒绝、初始化异常后两个监听器关闭。没有重复运行此前 19/7、91 或历史全量测试。

证据：[guard-http-report.json](evidence/guard-http-report.json)。工具静态审查发现的初始化清理、环境代理、发送后计数问题均已修正并有边界测试；恢复后独立审查未发现当前浏览器补验的付费外逃或计数并发阻断。

## 5. 异常、收尾及保护

首次工具初始化时，当前 ORM 的 timezone bind 拒绝原 SQLite 无时区时间值，实际 0 POST；通过在隔离 DB 原样复制创建时间解决，不改产品模型或 live DB。保留 [首次失败报告](evidence/initialization-failure-report.json)。

正式 API 和页面补验报告的服务主线程均停止，live DB 哈希保持。后续 TCP 探测确认两轮各自 API、来源、Vite 共六个端口关闭；Vite 子进程通过 terminate/wait 收尾。主线程字段不代表跨进程崩溃恢复或任意活跃 handler 终止保证。

旧证据基线 **118 文件哈希全部不变**，本轮记录见 [protected-hashes.json](evidence/protected-hashes.json)。这是先前 repair 的跨阶段基线；guard 自身的 468 项 before/after 是另一保护范围，两者不累加成文件总量。旧工作组仍为 **26/26 POST、152726 供应商 tokens，六个 phase closed**，未借用或重开。无提交、推送、部署或付费 fallback。

## 6. 尚未完成

用户要求的真实供应商正式总结流程，包括此前未通过的中篇内容，需要新的明确有限预算；异步预算问题尚无提交答复，故此次没有创建付费 phase。预选项或 Agent 额度恢复均不当作授权。

已有中篇缺陷仍是：每节课评价遗漏、评分理由重复、努力→技能的信念归属较弱；新版提示长文真实质量也仍未复验。Engrade 两种能力的旧修复结论保持。后续获得明确预算后只执行尚未完成的真实模型阶段，复用本报告有效的来源、路由与故障证据，不重跑这 20/4/10 项。
