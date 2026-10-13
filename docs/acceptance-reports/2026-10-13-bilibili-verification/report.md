# B站间歇无格式：网络诊断与安全校验提示整改

日期：2026-10-13。工作区：`E:\install_video`，基线提交`553e126`。本轮改善已捕获响应的识别与说明；没有证明网站持续提供视频流，也没有精确归因代理出口、频率或账号。

## 工程约定

UI先使用`ui-ux-pro-max`与`design-system`，skill优先于旧计划；颜色、字体、时长走`:root`的primitive→semantic→component token。能力通过窄接口接入、保持可配置，避免无关重构。产品仅`ytdlp_service.py`接触yt-dlp，前端视觉层只读scene、不改下载状态、不导入下载核心。保留用户AGENTS、账号/env/模型与历史验收原字节，不重开旧付费phase。

## 用户现象与实际网络样本

用户报告`BV13vpG67ELM`关闭代理后也多数失败、仅一次成功，随后明确**当前代理仍开启**。当前样本全按系统代理开启记录；用户先前关闭代理的现象没有被转记为本轮对照。

当前只读检查：Windows系统HTTP代理开启，指向本地代理服务；WLAN为当前默认路由，未见此前诊断中的Meta/TUN默认路由。yt-dlp实际发现HTTP/HTTPS代理。没有调整代理、DNS、路由、防火墙或服务。

| 样本 | 系统设置 | 诊断进程路径 | 结果 | 播放接口 |
| --- | --- | --- | --- | --- |
| 1–3 | 代理开启 | 继承当前配置 | 连续3次NoFormats | 每次HTTP200/code0，data只有`v_voucher`，DASH/DURL数量均0 |
| 4 | 代理开启 | 显式当前代理 | 提取成功 | 4视频/3音频，quality32，无voucher |
| 5 | 代理开启 | 显式无应用层代理 | 提取成功 | 4视频/3音频，quality32，无voucher |

失败样本均有网页initial state、没有内嵌playinfo。pagelist正常，nav表明匿名；HTTP成功及code0不能代替媒体资源有效性。两条路径随后各成功一次，说明没有足够证据把代理开关判定为直接诱因，也不构成稳定性验收。未记录voucher值、Cookie、WBI密钥或签名媒体地址。

原诊断证据保留并逐字节复制到本报告：[三次失败](capture-result.json)、[有限路径对照](path-compare-result.json)。这些真实样本采自代码整改前；不冒充修复后线上验收。

## 有限资源与成熟方案

旧12次诊断上界记录保持封账。本轮因用户补充持续失败设独立上限：最多3次提取、36次B站metadata GET；捕获失败后为验证代理路径，提取上限明确调整为5，GET硬上限仍36且原13次计入。新增对照9次，最终**22/36 GET、5/5次提取**后停止，剩余不自动使用。模型POST0、完整媒体下载0；官方资料阅读不计入B站metadata预算。

本机及参考项目均安装`yt-dlp==2026.08.19`，提取器源码相同。官方实现已将网页中的风险voucher识别为expected错误，但播放API在code0时直接返回data，未识别此次响应形状。[固定版本B站源码](https://github.com/yt-dlp/yt-dlp/blob/594bd50c2c78ac432f81600d309fdc4e0a92d82c/yt_dlp/extractor/bilibili.py)。源码依据支持“平台风险校验响应”，不支持进一步断言封号或特定网络故障。

实际采用官方提取器与公开`add_info_extractor`注册接口，保留`ie_key`和`IE_NAME`，复用原签名、格式解析及下载链路；没有新依赖、另一套提取引擎、修改installed包或全局monkeypatch。[官方注册入口](https://github.com/yt-dlp/yt-dlp/blob/594bd50c2c78ac432f81600d309fdc4e0a92d82c/yt_dlp/YoutubeDL.py#L908)。额外插件包对此单点响应兼容没有必要。

## 实际整改

- 主播放响应中非空voucher且没有有效格式时，抛固定中文expected错误；真实`DownloadError.exc_info`保留其类型，分类为`verification_required`。
- 解析、取直链、下载均使用适配；解析接口返回422，下载失败沿用Job/JobResponse的错误字段，前端显示“平台安全校验”。异常及界面不包含voucher值，不误标必须登录。
- 正常DASH/DURL、同时有voucher但格式可用、没有主响应风险证据的错误保持原行为。可用主格式的额外qn查询遭校验时沿用上游逻辑，保留主格式。
- 没有增加请求、自动重试或读取浏览器Cookie。显式直链模式失败后尝试服务端下载属于既有行为，可能再次提取；默认服务端模式保持。
- 前端仅补现有场景文案及样式映射，复用已有token/class、返回和手动重试控件，没有修改下载状态逻辑。

## 验证与独立审查

| 检查 | 命令/方式 | 实际结果 |
| --- | --- | --- |
| 主响应回归先红后绿 | 真实yt-dlp离线回放；禁网络 | 初始9项4 failed/5 passed（误标network）→9 passed |
| 补查清晰度兼容 | 有效durl32，补查80仅voucher | 初版1 failed→修复后通过 |
| 平台字段兼容 | 实际extractor与extractor_key | 派生名称断言先失败→显式保留官方IE_NAME后通过 |
| Job错误消费者 | 真实下载错误→内存SQLite→get_job | 通过；先前测试会话过期夹具已更正，没有对应产品补丁 |
| 最终相关后端 | `pytest tests/test_bilibili_verification.py tests/test_ytdlp_service.py tests/test_platform_bilibili.py tests/test_parse_route.py tests/test_jobs.py -q` | 145 passed；新回放文件11项 |
| 前端消费先红后绿 | 专属标题、保留手动重试、无自动第二请求 | 定向2 failed→2 passed，相关35 passed |
| 前端全量 | `npm test` | 19 files/169 passed |
| 前端构建 | `npm run build` | 成功，137 modules；大于500k的bundle警告仍存在 |
| 最终后端完整发现 | `pytest -q --ignore=tmp --durations=8` | 1787 passed/517.58s；最终服务与回放文件哈希核对保持 |

最初`pytest -q`遇到既有`backend/tmp/pytest-quality-final`、`backend/tmp/pytest-quality-local-tests`收集权限错误；没有改ACL或旧产物。完整发现命令仅排除历史临时目录。中间候选曾1785 passed/520.32s，但进程启动后增补了两项边界回归与修复，该数字不是最终版本的全量结论。

独立只读审查发现补查qn会中止已有主格式的Important问题；离线复现并修复后复审无Critical/Important。消费者覆盖建议已补。审查没有重跑测试或真实网络；完整执行结果以上表root实际回收为准。

## 当前限制与使用说明

此修复只识别已捕获的主响应形状，未扩展所有页面风险、非零业务码或其他站点验证码的分类。B站风险校验的具体诱因与长期匿名可用性仍未确定。当前可稍后重试；浏览器登录不会自动传入本程序，也没有验证它能解决这次问题。

当前开发后端原PID1948由本工作区`.venv`启动且未使用reload；重启前再次只读确认活动下载任务0，核验父进程与应用路由后停止该进程，以相同工作目录、`.env`和启动参数加载最终代码，新PID28576。本地OpenAPI检查HTTP200，前端原PID18340保持。没有改用户网络、账号配置或数据库业务记录；这次开发服务重启不作为线上部署。

本轮未进行修复后真实媒体下载、模型质量复验、线上部署或GitHub发布。诊断上限已停用，不以剩余额度继续重复采样。总结长文支持范围与旧内容失败结论不因本轮网络/离线回归而改变。刷新当前网页后可重新解析；若平台仍返回风险校验，新提示不会承诺持续可下载。
