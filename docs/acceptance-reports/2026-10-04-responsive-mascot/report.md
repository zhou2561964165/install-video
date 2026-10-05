# 响应式角色与实际 GPU 验收

## 工程约定

- UI 决策先调用 `ui-ux-pro-max` 和 `design-system`；本轮已检索 focus obscured、touch target、React effect 清理，并按 primitive → semantic → component token 管理新增尺寸。
- Skill 指引优先于计划；每屏动态元素保持受控，保留 reduced-motion。
- 颜色、字体、时长用 `:root` token；模型比例、边距、拖动阈值和纹理能力集中配置，不重做主题或修改模型资产。
- 单向依赖与窄接口：`ytdlp_service.py` 是唯一接触 yt-dlp 的层；角色只读 scene 与 `getRegion` 几何，不导入下载核心、不修改下载状态。

## 已实现与证据

375px 的示例按钮曾盖住角色脸，桌面最大倍率曾截掉鞋。本轮手机把角色放入主要内容之后的独立文档流区域，滚动时角色位置跟随该区，离开视口后隐藏；桌面保留大角色，按视口边界和底部菜单入口预留空间限制尺寸。

菜单增加可见按钮入口、44px 控件、初始焦点、Tab 循环、Escape 和关闭后恢复焦点。React 18 的 `inert` 使用标准空字符串属性。触摸横向拖动保持在角色区，原生纵向滚动保留；桌面拖动限制在视口内。角色轻微动画和表情仍走既有配置。

模型注册表标记 16384 纹理需求。GPU `MAX_TEXTURE_SIZE` 不足时直接跳过模型目录请求，保留背景、结束加载层、禁用角色菜单；没有尝试再上传同一张超限纹理作为兜底。未缩小、替换或删除任何模型资产。

真实 Windows Edge headless、NVIDIA RTX4050、原 16K atlas，基础矩阵共 **41/41** 检查通过，**22 张**当前视口截图见本目录。结果见 [results.json](results.json)，清理见 [service-results.json](service-results.json)。基础矩阵冻结后另补手机原生 focus 保护，追加的 before/after 专测独立保存，不改写这41项。

| 检查 | 结果 |
| --- | --- |
| 320×568、375×812、720×900、1440×900 | 四尺寸均实际注册、加载原模型；RTX4050 renderer 与 16K GPU 驻留证据齐全 |
| 角色与内容 | 窄屏角色区位于 hero 控件之后；真实 PIXI 模型包围盒完全落在分配区；桌面角色包围盒与根层菜单入口不交叠 |
| 真实 tap、换装、菜单与键盘 | 点击模型开菜单，按钮入口可操作，短发和缩放有效，焦点循环与恢复通过 |
| 真实 drag | 窄屏触摸横向拖动、桌面鼠标拖动确实移动模型且保持边界；触摸横拖未滚动文档、未误开菜单 |
| 文档滚动 | 三种窄屏滚动后角色区离开视口时实际模型隐藏；没有文档横向溢出 |
| 实际 HTTP 流程 | 四尺寸均用自制本地 3 秒视频与 HTML，经真实 yt-dlp parse200，并实际选择可下载格式；没有 mock HTTP 或注入 App 状态 |
| 同一 GPU 实例 resize | 1440→375 后 stage 实际宽度375，角色仍在新文档区内，没有模型重载 |
| 模拟 8K 能力 | 明确仅模拟 `getParameter(MAX_TEXTURE_SIZE)=8192`；模型目录请求0、加载层结束、正常 parse200。通用 Cubism runtime 脚本仍可加载 |
| 错误与模型调用 | 最终 run 的 pageerror、console error/warning、失败网络请求均0；AI API 和模型 POST 均0 |

截图通过 CDP `Page.captureScreenshot` 捕获当前真实 GPU 帧；不用 Playwright 对外部字体的等待，也没有改字体 CSS、隐藏元素或替换纹理。模型几何通过 CDP `Runtime.queryObjects` 只读当前已连接 PIXI Application，未改其属性。

## 验收过程保留

[failures](failures/) 保存前五次失败 JSON，未覆盖或重写为成功：

1. 首轮在角色区尚未滚入视口时要求纹理 GPU 驻留；Pixi 当时不绘制不可见模型。改为真实滚动露出角色后检查驻留。同时修正实测 React `inert={true}` warning。
2. 选中“短发”后，菜单选中标识改变 accessible name，原 exact locator 不再命中；修改测试定位，不改产品行为。
3. 模拟 8K 的测试把通用 Cubism runtime 脚本算作模型请求；缩窄为 `/live2d/bai/`，保留原始失败。
4. 四尺寸及 8K 功能检查已通过，但外部资源 `ERR_CONNECTION_CLOSED` 触发严格 console 检查；保留失败，不视作应用/GPU 成功证据。
5. 使用系统代理后，外部 Google 字体等待导致 Playwright screenshot 超时；改为实际当前帧 CDP 截图。最终 run 没有失败网络请求。

另一次人工看图发现 hero 的 `will-change/transform` 会让内部 fixed 菜单入口相对祖先定位，盖住鞋尖；桌面入口移至 App 根层，新增真实包围盒与入口不交叠检查。最终 [桌面完整角色](gpu-1440-whole-character.png)、[375完整角色](gpu-375-whole-character.png)、[菜单](gpu-375-menu.png) 均已人工检查。

## 边界

- 手机尺寸和 touch 输入仍运行在 Windows RTX4050 上，不是手机 GPU、Safari 或真机验收。未在 PATH 找到 adb，也未取得可用 WPD 设备记录；这只说明没有发现可用调试通道，不能推定没有手机。
- 8K 是受控能力模拟，不是实际低规格 GPU。未验证 GPU context loss、Safari 16K 内存、iOS 键盘自动放大或设备 safe-area 行为。
- 短屏先保证输入、示例与解析可达；完整角色区可能需要滚动。本轮证明指定区域内完整模型，不承诺整个角色始终显示在首屏。
- 固定账号栏和主题栏在任意滚动中仍可能覆盖已移到页面顶部的非当前控件；新增下面的 focus 专测只验证指定字幕 select 的聚焦保护，不能当作整页无障碍合规。
- 本轮只做本地 owned 视频的解析和格式选择，没有新增公网下载、AI 请求或媒体质量评测；此前公网手机下载报告仍是独立历史证据。

## 手机原生 focus 补充

人工查看基础矩阵的 resize 截图后，追加可重复的真实浏览器专测：正常滚动使字幕语言 select 位于固定主题栏之后，再通过浏览器 native focus 聚焦该真实控件。不改 App 状态、不改变下载结果。

- [before](native-focus/before/results.json)：控件已聚焦，位置 y109.03125–149.03125；主题栏 y88–124.1875，确实有约15px遮挡。
- 最小修复仅在窄屏 CSS 使用已有140/80px安全间距 token 设置 html `scroll-padding` 和控件 `scroll-margin`，保留原生滚动和焦点。
- [after](native-focus/after/results.json)：同样复现路径下，native focus 将控件移到 y280.03125–320.03125，完整避开账号/主题栏，几何检查通过。[after截图](native-focus/after/native-focus375.png)已人工检查。
- **专测整体脚本仍返回失败**：after run 记录1条外部 `fonts.googleapis.com` stylesheet `ERR_CONNECTION_CLOSED`，原始 console、失败请求和非零结果保留。应用 register/parse200、focus几何均通过，pageerror为0；不能把此专测称为“0console”或整轮全通过。
- 基础41项在补充CSS前完成；补充CSS只影响手机native滚动的安全间距，没有改模型算法、API或下载状态。未因已明确的字体网络问题重复联网刷出成功结果。

## 触摸取消与原生滚动补充

只在375px追加窄专测，没有重跑或覆盖基础41矩阵。

- [取消before](gestures/before/results.json)：真实 `touchStart → touchCancel` 无位移会误开菜单，明确复现。最小修复让 `pointercancel` 调用 `endDrag(false)`，add/remove监听使用同一专用回调；普通 pointerup 的 tap 行为保留。
- 初次取消after已不误开，但真实纵向touch的文档滚动距离0，见 [失败原始记录](failures/gesture-after.json)。已安装 Pixi 初始化会给canvas写 inline `touchAction:none`，覆盖此前CSS；改inline后仍因 normalized TouchEvent 的默认 `preventDefault` 阻断滚动，见 [第二次原始记录](failures/gesture-after-native-scroll.json)。
- 最终 `stage.js` 在初始化后按集中配置写 `touchAction:'pan-y pinch-zoom'`、设置公开 `interaction.autoPreventDefault=false`。不用事件合成来代替浏览器滚动，也没有手工写scrollY满足断言。
- [最终after](gestures/after/results.json) **5/5、0console/pageerror/failed request**：取消不误开；普通touch tap仍开菜单；横向真实touch拖动 x187.5→126.9629167，移动60.5370833px，document181不变、保持区域边界且未误开菜单；纵向finger原生滚动181→366，距离185px且未误开菜单。
- [纵向截图](gestures/after/native-vertical-touch375.png)、[取消截图](gestures/after/touch-cancel375.png)与输入事件trace独立保存。最初的横向专测在菜单恢复focus后的布局/滚动未稳定时读到最终位移0，见 [保留失败](failures/gesture-complete-final.json)；之后等待稳定并重新读取真实可见包围盒中心，诊断与最终核验均通过，未据猜测改生产拖动逻辑。
- [诊断trace](gestures/diagnostic/results.json)仍记录一次横向move之间模型短暂回中心、y变化1px而scrollY不变。异步字体/内容尺寸变化触发ResizeObserver重放置仍可能让正在拖动的角色短暂重新居中；本轮不保证任意异步布局期间拖动完全平滑。

[源码provenance](source-provenance.json)区分两类记录：最终after在运行开始直接读取7个前端源的字节SHA256，归档时再与当前字节核对；历史before没有当时采集哈希，只按本会话唯一源码替换逆向重建对应版本，明确标为事后重建，不能充当独立运行时来源证明。`stage.js` 原始混合换行字节保留，没有为了匹配哈希重写历史证据。

基础41、focused touch5和focus几何1是不同阶段；focus-after仍有外部字体1错误，不能合并描述为“最终47项全部0错误”。物理手机/真实低规格GPU/任意异步字体布局的限制保留。

## 重跑

从仓库根目录运行，参数输出目录必须新建或为空，旧证据会被拒绝覆盖：

```powershell
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-responsive-mascot/acceptance_harness.py --output-dir .planning/responsive-mascot-new/evidence
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-responsive-mascot/acceptance_harness.py --check-output-dir --output-dir .planning/responsive-mascot-new/evidence
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-responsive-mascot/acceptance_harness.py --focus-only --output-dir .planning/responsive-mascot-focus-new/evidence
.venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-responsive-mascot/acceptance_harness.py --gesture-only --output-dir .planning/responsive-mascot-gesture-new/evidence
```

脚本使用已有 Edge、playwright-core、ffmpeg、Python 环境；自行启动8063后端、8064媒体静态服务、5188前端，使用独立临时数据库、随机新测试账号、未配置 LLM，finally 停止全部服务。模型、环境配置、用户数据库和旧报告保持原样。
