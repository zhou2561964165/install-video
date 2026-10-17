# 角色嵌入与跟随细化开发验收

日期：2026-10-13。用户已授权按最新设计开发；本报告记录新实现，原“仅方案”阶段及此前跟随报告保留历史适用范围。

工程约定：UI使用ui-ux-pro-max/design-system；skill优先于计划；primitive→semantic→component三层token；成熟PIXI/CSS能力优先，配置化、窄接口、单向依赖。视觉只消费scene/DOM几何，不操作下载状态；仅ytdlp_service.py接触yt-dlp。保护已有未提交修改、账号/env、本地模型及历史原件；Live2D模型/截图不上传。本轮无新依赖。

## 实际交付

- 默认`embedded`，全部宽度按文档区域contain；模型local bounds/pivot参与限位，父Container的Graphics mask约束真实渲染与canvas命中，DOM热区取模型/区域/视口交集。复用同一舞台/ticker。
- ≥1180px角色位于主内容旁独立列；较窄屏置于示例网站下方，视频工作台下方保留区域。拖动保存区域内相对位置；滚动随区域，resize/scene/区域失效终止旧拖动和捕获。`free`仅为显式兼容配置，无新增产品入口。
- 只恢复示例网站前的“试试”。镜片`clamp(96px,13vw,190px)`，标题倾斜8deg/转角3deg，位移12px；定位与缩放/透明度分层，隐藏140ms、恢复180ms，控件进入8px/退出16px。角色避让依据未缩放圆形足迹。
- 控件排除几何按相关布局/边界变化缓存；镜片自己的style不触发观察循环。非活动dialog/inert内容立即退出排除；恢复镜片时先保留原生指针。原焦点隐藏时菜单回焦主区域可见控件。
- 白模型保留参数待机；无匹配IDLE参数的embedded模型静止降级，避免容器缩放逐帧写DOM/触发避让扫描。显式free保留历史缩放呼吸。

## 本轮检查

| 检查 | 实际结果与范围 |
| --- | --- |
| Vitest全套 | 20个文件、193项通过；`npm test`，不是旧171项或后端历史计数 |
| 生产构建 | `npm run build`退出0；仍有既有>500kB bundle提示，未为本次功能做无关拆包 |
| 实质审查修复 | 独立Agent发现3个Important，全部接受；4个失败回归实际RED→GREEN，相关4文件/63项通过，无遗留Important/Minor |
| 主要浏览器检查 | Headless Edge 12/12：本地Live2D、1440/1024/390/320布局、菜单/Enter/Space/回焦/尺寸、区域内拖动和滚动、工作台后置、镜片参数/标题/控件与角色避让、淡出中间态/恢复定位、暗色/断点恢复、reduced-motion、网络审计 |
| 新边界浏览器检查 | 6/6：mix-blend兼容、forced-colors、无WebGL/无虚假区域、无效区域菜单后备回焦与恢复、关闭菜单后原覆盖处不再排除（不借滚动刷新）、网络审计 |
| 视觉核对 | 本机桌面/320px与mix-blend截图已实际查看；模型完整在区域内，输入/示例网站与角色分开。模型截图只保留`.planning`，不进入本报告目录 |

最终主要检查：`.planning/ui-embedded-implementation-20261013/runs/2026-10-13T11-03-30-382Z/result.json`。最终边界检查：`.planning/ui-embedded-implementation-20261013/edge-runs/2026-10-13T11-08-10-304Z/result.json`。两份JSON按原字节复制到本目录`evidence/`；原运行脚本、日志、快照和截图保留在本机任务目录，脚本及来源文件哈希见`evidence/manifest.json`。

最初浏览器脚本曾使用错误的假token键，未发送API；后续定位点两次落在新header接近带或尚在进入动画中的菜单坐标，属于验收脚本问题。对应失败JSON/日志原件仍在本机，不转记为产品通过。独立审查发现的三个产品问题另有失败回归和修复证据。

## 网络与资源边界

本轮开始前记录预算：真实LLM POST=0、平台提取=0、媒体下载=0。所有浏览器使用独立context、阻断service worker、拦截全部API并阻断外部请求；本地模型/字体/程序资源走同源静态文件。

最终主要检查记录11次浏览器mock API，边界检查10次；仅`auth/me`和mock`parse`，无外部请求、download事件或真实供应商请求。主要检查page/console errors均0；边界page errors为0。实际模型生成、平台提取、媒体下载均为0。没有新付费phase、账号额度或运行时模型预算调整，旧封账工作组不重开。

## 适用范围与交接

上述结果属于本机Headless Edge（155.0.4283.45）和MAX_TEXTURE_SIZE16384环境；不证明实体手机pinch/FPS/低GPU性能、真实后台标签页隐藏、逐像素/录像帧率一致或真实平台稳定下载。无WebGL降级已验收，8K GPU原能力判断的已有用例继续保留。本轮不重跑无变化后端测试，也不改变总结内容质量结论或默认总结配置。

当前代码/文档已落地，已有未提交UI改动继续保留；没有提交、推送、部署或清理原分支。前端验收服务为127.0.0.1:5173，本轮未启动后端。后续发布仍须使用过滤Live2D历史的隔离副本。

依据：[设计方案](../../superpowers/specs/2026-10-13-embedded-mascot-follow-refinement-design.md)、[实施计划](../../superpowers/plans/2026-10-13-embedded-mascot-follow-refinement.md)、[当前交接](../../handoff-2026-10-10.md)。
