# 录像跟随：新窗口补充浏览器测试

日期：2026-10-13。范围为交接中的后续 UI 行为检查，未改产品代码，未提交、推送或部署。

工程约定：UI先使用ui-ux-pro-max/design-system，skill优先于历史计划；颜色、字体、时长走primitive→semantic→component三层token；成熟接口优先、配置化、窄接口和单向依赖。视觉只消费表现/scene，不修改下载核心；仅ytdlp_service.py接触yt-dlp。保护用户修改、账号/env、本地模型和历史验收原字节。

## 本轮范围与资源

- 读取当前交接、旧专项脚本、原录像抽帧，沿用原目录Vite 5173服务；进程命令行指向E:\install_video\frontend\node_modules\vite。后端不重启，账号与额度配置不读取/修改。
- 本轮开始前记录并执行上限：真实模型POST=0、平台提取=0、媒体下载=0。隔离浏览器context拦截全部API，阻断外站请求，禁用service worker；模拟用户仅在context内。Live2D为本机已存在的角色资源，不是LLM调用。
- 复用已安装Playwright和Headless Edge 155.0.4283.45，无新增依赖。ui-ux-pro-max的UX检索采用reduced-motion、excessive-motion与cancellable-state-transitions建议，design-system用于核对既有三层token；未重新设计主题。
- 独立只读Agent核对未覆盖的测试路径，主Agent执行实际浏览器测试。未因换窗口重复此前无变化的171项单元测试/build、17项旧UI流程或任何模型内容验收。

## 结果与证据

新增跟随脚本包含16类检查，新增本地舞台脚本包含8类检查。按实际覆盖归类：**22类检查已获得通过证据，2类真实行为尚未证明**，逐项归类及原始断言状态见[coverage.json](evidence/coverage.json)。这不是24类全部通过，也不代表真手机、全部浏览器或FPS性能通过。

| 范围 | 本轮实际观察 |
| --- | --- |
| 指针快速变化、缓动、回正 | 35次交替移动后正确收敛；移动中观察到缓动，离开页面后标题恢复；镜片pointer-events:none |
| 快速滚动与静止指针重命中 | 多章节正反向wheel；滚动后目标重新命中，最多一个活动标题，没有水平溢出 |
| 连续resize与断点 | 1365/1024/850/801/800/768/390/320/802/1100/1440连续切换；800及以下清除跟随，恢复宽度后重新移动可激活 |
| 离开与事件恢复 | 真实pointerleave/reenter立即定位；合成blur/visibilitychange清除后通过真实pointermove恢复 |
| 控件、键盘与场景 | 输入、主题按钮维持原生指针；返回顶部后链接输入获得焦点；入口/解析工作区往返4轮且仅一个镜片 |
| 系统动效设置 | reduced-motion反复切换3轮，以及forced-colors启停，均清除不允许的跟随并可恢复 |
| CSS兼容与触屏模拟 | 实际filter、强制blend、两者都不支持的原生降级；390/844横竖屏及1024触屏模拟禁用跟随，背景单指可滚动 |
| 实际本地角色 | WebGL MAX_TEXTURE_SIZE=16384，模型确实加载；键盘Enter/Space打开菜单、Escape回焦及可见焦点通过 |
| 角色鼠标拖动 | 两轴跨原区域拖动，不误开菜单；滚动保留位置，1024×768 resize后仍在视口内；合成blur终止拖动 |
| 角色触摸模拟 | 单指纵向拖动未触发pointercancel且不滚页面；touchCancel后新手势可用；背景单指仍可滚动 |
| Console/Network | 跟随及角色context无pageerror/console error，无外站请求；所有API响应均由测试夹具提供 |

首次跟随运行原件见[follow-first.json](evidence/follow-first.json)：15个脚本断言通过，1个因新测试误写返回按钮名称超时。代码及旧脚本实际名称为“返回输入”；仅修正新脚本定位器后，四轮场景往返和控制台检查[2/2通过](evidence/follow-scene-rerun.json)。原失败结果保留，产品没有因此修改。

[最终完整性核对](evidence/final-integrity.json)将重跑记录中的scriptSha256与当前新脚本字节核对，并保存成功重跑所用的“返回输入”定位器原文。独立只读Agent复核了原始断言、22/2归类、60/19哈希及零调用隔离边界；其指出的交接旧“最新安排”措辞已改为历史安排。

首次舞台运行原件见[stage-first.json](evidence/stage-first.json)：7/8脚本断言通过；未通过项是两指手势后的visualViewport.scale仍为1。不能据部分通过把这次舞台运行写成全通过。

### 两项尚未证明的真实行为

1. **真实窗口/标签页隐藏与恢复。** Headless Edge中新开标签并bringToFront仍令原页面document.hidden=false；脚本里的该探测虽未抛异常，只证明了返回后可恢复跟随，未证明真实后台隐藏。覆盖计数将这一项归为未验证。合成blur/visibilitychange和真实pointerleave路径有独立通过证据。
2. **实际两指缩放。** 模型上的第二指确实到达、两条pointer被取消、默认触摸事件未preventDefault、角色回到grab且没有误开菜单，但缩放比例未增大。用完全无应用代码/账号/模型的最小页面对照，两种CDP方法（dispatchTouchEvent、synthesizePinchGesture）及默认/2触点四组均为scale 1→1，见[pinch-controls.json](evidence/pinch-controls.json)。当前环境不能证明原生pinch可用，不能将其当成已定位的应用Bug，也不能宣称真机缩放通过。

## 视觉对照

实际查看原录像接触表和本轮浅色、深色、blend兼容、390px截图。filter路径可见黑底白字/白底黑字反相，标题轻倾斜并回正，窄屏没有镜片。blend路径文字略偏米色，与filter路径不保证逐像素相同。

测得当前token：圆径clamp(130px,17vw,245px)，镜片缓动0.16s，标题缓动0.3s、倾斜上限4deg、位移上限12px。录像包含浏览器外框和可能的显示缩放，未获得其CSS viewport/devicePixelRatio；对照证明效果类型可见，不宣称像素尺寸、原录制帧率或延迟完全一致。原录像、抽帧与带角色截图仅留本机，不复制入报告。

## 代码与原件保护

[audit.json](evidence/audit.json)及[前置基线](evidence/provenance-before.json)核对本轮前后60份前端源码/配置哈希一致，选定19份旧UI报告、图片/JSON及原专项脚本哈希一致。这里的19份是本轮明确核对范围，不表示重验了全部历史raw/freeze。新结果复制件与本机原件字节一致，失败原件未覆盖。

当前产品、原账号/env、默认总结配置和封账模型验收组均未更改；本轮不复评总结内容或B站长期下载稳定性。历史171/build等结果仍只属于各自原报告，本轮不将其计入新测试数量。

## 本机复用入口

新脚本在`.planning/ui-follow-video-20261013/continuation/`：`check.cjs`、`stage-check.cjs`、`pinch-diagnostic.cjs`。每次运行生成新的时间戳目录，保留先前结果；`UI_CHECKS`可选择指定跟随检查。

```powershell
$env:UI_PLAYWRIGHT_PATH='D:\node.js\node_cache\_npx\9833c18b2d85bc59\node_modules\playwright'
# 仅在需要补验或出现相关代码修改后运行；沿用已确认来源的5173服务。
node .planning/ui-follow-video-20261013/continuation/check.cjs
node .planning/ui-follow-video-20261013/continuation/stage-check.cjs
```

接下来需要具备真实前台/后台状态的桌面浏览器检查，以及实际触屏设备上的第一指落模型后第二指pinch。当前环境内新增行为检查已执行并留下结果；这些实际设备验证和低GPU/FPS覆盖仍未完成。
