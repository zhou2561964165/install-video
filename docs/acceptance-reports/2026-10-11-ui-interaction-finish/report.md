# 2026-10-11 角色交互与解析展示收尾

工程约定：当前用户/AGENTS和skills优先；UI使用ui-ux-pro-max/design-system与三层token；成熟浏览器/PIXI接口优先，配置化窄接口、视觉只读scene、yt-dlp唯一服务层。保护账号、凭据、本地模型、旧验收原件及用户未提交改动。

## 修改与原因

基线f35755e，原目录分支feature/ui-interaction-finish-20261011。访问隔离已在ebc1554提交、封面no-referrer已在f35755e提交。本轮补拖动/触摸/焦点真实验证，不重复这两项开发。

初审定位错指接管拖动/误开菜单，以及桌面角色键盘区域height0、移动后焦点停在原占位。用失败回归与实际GPU页面确认后，绑定起拖pointerId，并把原DOM键盘入口作为跟随模型边界的局部触控表面。首touchstart不再取消，局部pinch-zoom允许浏览器接管双指，背景pan-y仍可滚动。保留布局占位/既有39项菜单，移除旧按钮44px留白。复审追加仅PointerEvents环境多指结束后无法再拖的3项失败回归，改由pointer集合及blur恢复；补lost capture恢复检查。

App仅传interactionTarget/getRegion和回调，视觉层维护自己的几何/手势，不导入下载核心。焦点颜色/宽度走primitive→semantic→component token，没有新产品依赖、模型资源改动或后端代码变化。

采用现有PIXI6.5、浏览器PointerEvent及pointer capture；依据[MDN touch-action](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/touch-action)与[Pointer events](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events)。局部手势策略在开始前设置，避免动态改变整canvas的手势策略或取消首触点后试图恢复原生pinch。

## 验证

| 检查 | 结果 | 实际范围 |
| --- | --- | --- |
| TDD复现 | 先5项失败，再3项多指恢复失败；修复后相关用例通过 | 非测试报错，分别复现错指坐标/tap、空几何、touch默认取消及多指释放/blur后不能再拖 |
| npm test | 151 passed / 19 files | 原目录前端完整Vitest，含本轮回归 |
| npm run build | 通过，136模块，805.79KB JS | 既有大于500KB chunk警告保留，未做无关拆包 |
| 原生Edge桌面及模拟触摸 | 15项通过，pageerrors0 | RTX4050/MAX_TEXTURE_SIZE16384；桌面拖动、scroll/scene/scale/resize位置保持、原39项菜单、焦点恢复；CDP单指纵向拖动无pointercancel、背景真实touch滚动、第一指先落模型后第二指pinch，visualViewport.scale约1.97；退出禁用表面/销毁舞台 |
| 独立审查 | 最后无Critical/Important阻断 | 2项初审及1项复审Important均已修复；只读审查没有冒充测试/真机 |
| 真实账号/平台 | 两条B站视频共3次解析均200；metadata/格式显示 | 复用本机指定既有开发账号，短期JWT仅在内存/临时浏览器上下文，不记录token/邮箱/密码；账号/下载统计核对保持 |
| 封面可见性 | 第三次完整解码后正常 | BV1GJ411x7h7固有1920×1080，实际约356×200px，complete/decode完成、截图确认，referrerPolicy=no-referrer；前两次只等naturalWidth，截图仍在渐进加载，不拿它们证明完整显示，原记录未改 |
| 模型调用/预算 | LLM0 POST；真实parse3/3 | 初始parse上限2，截图暴露未等完整解码的缺口，发前提高至有限总上限3、仅补1次complete/decode核查并绑定两父账本hash；三份分别预占/closed，无重开、隐藏重试或模型调用 |

浏览器交互页使用明确的auth/scene HTTP fixture，真实本地模型及渲染/输入事件；真实解析页另通过既有账号及原后端执行、关闭WebGL以聚焦metadata。这两类证据不等同于真手机、真实平台下载或密码登录实测。

本机原件位于`E:\install_video\tmp\ui-interaction-finish-20261011\`：`browser-result.json`、`frontend-final-tests.log`、`real-parse-result.json`、`real-parse-cover-followup-result.json`、`real-parse-cover-decoded-result.json`、三份parse ledger及截图。截图/临时凭据/用户配置不进入GitHub。原开发环境没有安装浏览器测试依赖，uv提供独立临时Playwright工具环境。

## 限制与交付

物理手机及其他浏览器/低GPU未复验；前述“小窗口”暂按原解析信息卡检查，其它含义仍待用户说明。完整Blob文件缓存及中长篇总结内容缺陷仍在；没有提升默认模型、调用翻译/总结或恢复回滚框架实验。

后端未修改且本轮未重跑，1539 passed是上轮历史结果。开发服务来自原目录127.0.0.1:5173/8000；没有合并/远程推送/部署。本地模型保留，后续GitHub发布必须使用既有隔离过滤流程，不直接推含模型历史的main/开发分支。
