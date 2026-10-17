# 录像参考：UI 跟随与装饰小字精简

日期：2026-10-13。当前代码已落地；用户最新安排为先更新文档，后续测试交给新窗口。

工程约定：UI先使用ui-ux-pro-max/design-system，skill优先于历史计划；颜色、字体、时长走三层token；成熟接口优先、配置化、窄接口和单向依赖。视觉只操作表现，不读取/修改下载核心；仅ytdlp_service.py接触yt-dlp。保护用户修改、账号/env、本地模型和历史验收原字节。

## 用户参考与实现

用户提供`Desktop 2026.10.13 - 14.17.21.03.mp4`，本地离线读取：17.8675秒、2560×1440、约60fps。抽帧确认大圆形光标的缓动、覆盖文字时的黑底白字视觉，以及展示标题随鼠标轻微倾斜/浮动。原录像未改，参考帧仅保存在本机`.planning/ui-follow-video-20261013/`，不复制进报告。

- 精简登录、入口、章节和收尾的装饰小字：功能眉题、介绍副标题、欢迎文案、滚动提示与示例旁“试试”标签已移除。表单标签、错误信息、功能按钮及实际内容说明保留。
- 新`PointerFollower.jsx`只消费`data-ui-follow`/`data-follow-plane`表现标记。标题倾斜和位移、圆形尺寸、缓动时长及801px阈值集中在`tokens.css`。项目自身中文标题由镜片反相呈现。
- 优先复用浏览器原生[backdrop-filter](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter)实现反相/灰度/对比；[mix-blend-mode](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/mix-blend-mode)提供兼容路径。[transform](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/transform)和现有CSS transition承担缓动。没有新动画库、RAF循环、canvas或WebGL舞台。
- 仅桌面精细悬停指针、正常动效且页面可见时启用。触屏/窄窗口、reduced-motion、forced-colors禁用；按钮、输入、链接、导航、加载遮罩和角色菜单使用原生指针，镜片不接收事件。
- 动态布局使用offset布局坐标缓存；刷新时重新命中当前鼠标，避开滚动揭示的transform反馈。修复晚到媒体/尺寸回调清掉跟随、加载遮罩下无光标两类问题。监听器和observer在cleanup释放。

## 用户移交前已经执行的检查

以下记录为本窗口在用户提出“测试交给新窗口”之前实际执行的结果；文档更新不再次运行这些检查。

| 检查 | 已执行结果 |
| --- | --- |
| `npm test` | 最后19文件/171项通过，时间约14:59；未新增镜像实现的单元测试 |
| `npm run build` | 成功，139 modules；既有大bundle提示仍在，主JS约813kB |
| 跟随浏览器专项 | 10项通过：标题/镜片位置、原生控件指针、浅深色、加载遮罩、动态动效偏好、窄窗口、blur、场景替换、coarse-pointer关闭；无pageerror |
| 既有UI浏览器回归 | 17项通过：布局、认证/解析模拟流程、键盘页签、复制/TXT、返回URL/焦点等 |
| 本地PIXI/Live2D | 正常动效上下文实际加载，菜单Enter/Escape及390px resize通过，无pageerror |
| 独立只读复审 | 首审发现加载层排除与变换后矩形问题，已修复。Sol后续复审容量失败，改由现有轻量Agent核对单组件；最终未发现Important遗留。审查方没有运行测试或浏览器 |

专项脚本曾先后暴露媒体恢复和resize后的active被清除，修复后完整通过。与最终代码对应的结果保留为[跟随结果](follow-check-result.json)、[既有UI结果](ui-check-result.json)、[舞台结果](stage-check-result.json)。所有API为模拟响应，本轮模型POST/真实平台提取/媒体下载上限0、实际0；模型内容质量结论与旧预算不变。

## 当前截图

- [浅色入口跟随](entry-follow-light.png)
- [深色入口跟随](entry-follow-dark.png)
- [登录标题跟随](auth-follow-light.png)
- [手机精简入口](entry-mobile-clean.png)

## 新窗口继续测试的入口

先读[当前交接](../../handoff-2026-10-10.md)的“录像跟随续改与测试移交”，再依据新改动范围决定需要补哪些检查；上面的已通过记录可以复用，不能写成新窗口重新执行过。

现有本机脚本：

- `.planning/ui-follow-video-20261013/follow-check.cjs`：本轮10项跟随专项。
- `.planning/ui-reference-deep-20261013/ui-check.cjs`：既有17项UI流程。
- `.planning/ui-reference-deep-20261013/stage-check.cjs`：真实本地舞台/角色检查。

脚本复用本机Playwright和Edge。PowerShell设置`UI_PLAYWRIGHT_PATH`为已安装的`D:\node.js\node_cache\_npx\9833c18b2d85bc59\node_modules\playwright`，再从项目根运行所需脚本；若缓存路径变化，先定位现有安装，不为文档交接自动安装依赖。

后续重点：对照用户视频评估倾斜幅度、回正、圆形大小/延迟和文字反相；补实际快速滚动/连续resize/窗口离开恢复及按需要的真实触屏检查。现有桌面模拟不代表真手机、所有浏览器或FPS性能；兼容blend路径的颜色不保证与滤镜路径逐像素一致。后续测试归新窗口，本窗口按用户指令在文档更新后停止测试。

代码与文档仍在本地工作区，未提交/推送/部署；既有发布过滤模型历史的流程继续适用。
