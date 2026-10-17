# 万能视频下载网站 · 前端

> **F-003最终交验（2026-10-17）：** 用户已查验通过，包含小圈在内容列两侧显示、标题随全视口位置倾斜；仅顶部、模型alpha轮廓和data-follow-exclude=parse表单避让，普通按钮/链接/菜单及空白处保持小圈。模型拖动边界未改。257项/build及本地模型10项浏览器检查范围见[交验](../docs/implementation-reports/2026-10-17-f003-circle-scope.md)。

> **F-006交验（2026-10-17）：** 实现与验证完成，等待用户查验。游客/认证恢复中显示首页；顶部登录按钮显式打开AuthScene；匿名解析提示登录且不发业务API；AuthScene返回和认证成功均保留URL、不自动解析。最终范围见[F-006报告](../docs/implementation-reports/2026-10-17-f006.md)。

> **F-003待机交验（2026-10-17）：** 用户已查验通过。自动漫游及新增位置/暂停菜单已取消；模型保持当前位置、拖动后停留，原待机和小圈alpha联动继续。见[交验](../docs/implementation-reports/2026-10-17-f003-original-behavior.md)。

> **F-003待机行为交验（2026-10-17）：** 自动漫游与应用主动暂停已取消；角色保持当前位置，拖动后停在新位置，原呼吸、摆头、换装、表情和道具继续。页面额外悬浮控制已取消，模型内部菜单按原有行为保留。当前F-003已获用户查验通过，详见[交验](../docs/implementation-reports/2026-10-17-f003-original-behavior.md)。

> **F-003初始交验历史（2026-10-16）：** 当时的自由漫游、暂停与测试数字仅适用于该阶段，已被2026-10-17恢复待机及小圈范围两轮更新覆盖。当前行为以本文件顶部交验和[项目总表](../docs/follow-up-plan.md)为准。

## 实际前端架构（2026-10-16源码审视）

`main.jsx`挂载App；App持有下载reducer并组合useAuth、useDownload、useVideoInsights，解析仍在App直接编排。下载状态与字幕/翻译/总结缓存分别管理；SelectingScene通过VideoInsights的`summarizeCurrent`窄接口触发当前语言的总结。

App仅在认证成功、非手机UA且视口宽于800px时创建Live2D模型。角色从scene接收表情信号，并在同一App ticker上保持待机；用户拖动后位置保持，呼吸、摆头和配置的表情/道具继续。PointerFollower独立读取DOM标记与几何，按最新已验收规则避让顶部、解析表单及模型alpha轮廓，其他按钮、链接、菜单和空白处不隐藏小圈；标题倾斜依据纵向标记及全视口位置。`useMascotHitArea`仅调整DOM交互面的命中范围，不裁切模型画面。视觉模块不导入下载API或修改业务状态，但也并非只读取scene：换装和媒体偏好通过各自窄接口传入。当前没有小圈驱动角色运动的共享事件协议。

CSS按global→reference顺序加载，tokens提供三层变量；PIXI配置和WebAudio仍有JS模块常量。旧Preloader组件文件保留，但App不再挂载加载遮罩或嵌入占位。旧电影感计划中的Subtitle/Frame/PathProgress等未实现，不能当作已有组件。完整依赖图和生命周期边界见[design§13](../docs/design.md#13-当前前端架构业务状态与表现层)，F-003实现与验收边界见[交验](../docs/implementation-reports/2026-10-16-f003.md)。

> F-003当前行为及最新小圈范围已由用户查验通过；F-006实现与验证完成，等待用户查验。F-001长文入口与F-002组件居中状态见各自交验，后续计划状态以[总表](../docs/follow-up-plan.md)为准。F-006测试边界见[实施报告](../docs/implementation-reports/2026-10-17-f006.md)。

## 当前总结状态（2026-10-16）

长文实验组phase1–15已全部封账，23 POST/319471供应商tokens；Ragas独立组16 POST/34106 tokens，持续整改合计39 POST/353577 tokens，旧67 POST另行封账。phase15只完成用户指定的第一步DeepSeek来源筛查：英文长文7/8项核心完整，1项缺转换前提且有局部退出条件错误；中文短文4/4项核心完整，未发现确证核心事实错误，但有重复扩写。第一步已完成，等待用户指示；没有自动进入核查、编辑、新phase、跨模型或产品接入。详见[当前交接](../docs/handoff-2026-10-16-deepseek-step1.md)、[phase15报告](../docs/acceptance-reports/2026-10-16-deepseek-source-screen/report.md)和[独立内容审阅](../docs/acceptance-reports/2026-10-16-deepseek-source-screen/content-review.md)。

phase15是独立API实验，不自动改变网页能力。后续F-001另行实现产品长文路径，响应新增`format=markdown`，全文保存在`summary`且`key_points=[]`；未指定format的旧响应保留原展示。使用MIT许可的react-markdown 10.1.0安全渲染，不启用raw HTML、不加载远程图片，外链仅HTTP(S)并附noopener noreferrer；复制与TXT导出保留原Markdown。短中仍为`legacy / adaptive / single`及`fidelity=off`。本轮65项前端集成与build通过，模拟API浏览器1440/390/320px通过；没有真实模型请求、部署或语义复验，见[交验记录](../docs/implementation-reports/2026-10-16-f001.md)。

F-006已实现并完成验证，等待用户查验：未登录/会话恢复期间显示首页，顶部按钮显式进入登录或注册；游客提交解析时只提示请登录且不发业务API。AuthScene返回及登录/注册成功均返回首页并保留URL，成功后不自动解析。token恢复成功直接进入首页并显示AuthBar，失败回游客首页；后端权限不变。Edge检查使用mock认证API，未进行真实账号登录。登录成功后可粘贴链接、解析视频、选择格式并下载；解析结果页还提供查看字幕、翻译字幕和生成AI总结。页面使用PIXI舞台背景和Live2D角色；没有WebGL时使用CSS背景降级。

主题有浅色、深色和自动三档，浅色默认，由 `document.documentElement.dataset.theme` 驱动。CSS token 单一来源为 `src/styles/tokens.css`：primitive→semantic→component；`global.css`保留基础组件样式，`reference.css`统一全站皮蛋 AI / DeepSeek参考表现。PIXI 通过 `src/pixi/theme.js` 读取 CSS 变量并保留匹配 fallback；折射色跨主题恒定，透明画布底色由CSS响应主题。设计背景见根目录 [设计文档](../docs/design.md)。

产品目前以视频内容总结为主，字幕读取和翻译是辅助功能。视频区保留 `free-video-downloader` 的双栏信息结构，外观已与全站浮动导航、玻璃面板和胶囊页签统一：信息/格式/下载/AI总结与摘要/字幕/翻译页签同屏；返回输入会保留链接、聚焦并取消旧请求，下载不会重挂内容区。完整文本可复制和导出TXT；当前接口没有时间戳段，未提供SRT/VTT、思维导图或问答。项目状态入口见[文档索引](../docs/README.md)和[当前交接](../docs/handoff-2026-10-16-deepseek-step1.md)。

前轮UI验证（2026-10-13，嵌入改造前）：19个测试文件/171项及build通过；Edge headless 1440/768/390/320px布局与交互共17项通过，API全拦截，模型/平台请求0。另一正常动效上下文实际加载本地PIXI/Live2D，验证Enter打开菜单、Escape关闭和390px resize。没有新增运行依赖；系统字体替代外部字体请求。具体截图、检查范围与既有bundle警告见[UI迭代报告](../docs/acceptance-reports/2026-10-13-ui-reference-deep/report.md)。

录像跟随：主视觉装饰小字已移除；`components/ui/PointerFollower.jsx`按`data-ui-follow`区域和`data-follow-plane`标题提供缓动圆形反相与标题倾斜，原生CSS滤镜/混合和transition负责表现。圆形基准直径为`clamp(96px, 13vw, 190px)`，标题倾斜/转角为8deg/3deg；控件接近/退出余量为8px/16px，角色避让以未缩放圆形足迹为基准。定位和缩放/透明度分层处理，参数由`tokens.css`配置。宽度至少801px、细指针/hover且系统动效正常时启用；控件、加载层、菜单、触屏和窄屏使用原生指针。此前22类续测及旧专项仅覆盖嵌入改造前的行为，见[续测报告](../docs/acceptance-reports/2026-10-13-ui-follow-continuation/report.md)和[原录像报告](../docs/acceptance-reports/2026-10-13-ui-follow-video/report.md)，旧结果不代替当前嵌入模式的独立检查。

### 桌面角色活动与小圈避让（F-003）

`PLACEMENT.mode`默认`free`。非手机UA且视口宽度大于800px时，Live2D角色在固定PIXI舞台中缓慢漫游；模型中心保持在视口范围内。拖动和方向键以CSS像素移动，Home及菜单按钮可复位；常驻控制区提供菜单和暂停/恢复，菜单包含移动、缩放、表情/道具和复位。角色进入动态圆形小圈或普通交互控件的避让范围时，小圈隐藏并恢复原生指针。角色DOM交互面会在控件重叠时从命中区域扣除对应矩形，但不会裁掉模型视觉；如浏览器不支持`clip-path:path()`，交互面整体让出命中，原生控件仍可点，小圈可以通过菜单继续操控角色。

键盘聚焦、拖动、菜单打开、用户暂停、`prefers-reduced-motion`、forced-colors和页面隐藏都会暂停角色原生动作、自定义待机、漫游与随机道具。模型使用库支持的`fromSync`入口并关闭自动ticker，交由单PIXI ticker统一更新；App以AbortSignal和token化8秒等待上限清理加载，迟到实例由拥有者销毁。加载失败或设备能力不足使用受控fallback guard；App不再挂载Preloader或嵌入占位。设备门控在创建模型前执行：Android/iPhone/iPod/IEMobile/Windows Phone UA，或视口宽度≤800px，均不加载角色模型或静态fallback、不创建角色交互面和控制区；手机横屏仍由UA挡住。`index.html`的共享Cubism Core脚本仍会加载，所以“手机不加载模型”不代表整个`live2d`目录零请求。

F-003最终验证为前端22个文件/237项通过、生产build 299个模块通过、独立审查C/I/M=0/0/0；build保留大于500kB chunk提示。Edge真实本地16K模型场景7项、模拟native/headless 7项通过，无pageerror。模拟手机组合的模型资源和角色API调用数为0，但未使用真实手机；GPU峰值内存、长时FPS、不同操作系统和LLM内容质量未测。模型POST为0，未部署，详见[本轮交验](../docs/implementation-reports/2026-10-16-f003.md)。2026-10-13的[角色嵌入报告](../docs/acceptance-reports/2026-10-13-embedded-mascot-refinement/report.md)是被F-003替代的历史模式记录。

2026-10-12参考视频工作区验收：指定B站视频的解析与字幕实际API均200；当时后端159相关、前端167项及构建通过。1440/390px浏览器用真实API捕获的解析/字幕数据，模拟模型/翻译/下载，验证完整5809字符字幕、14841字节TXT、原标题文件名、当前语种单次显式总结、同屏下载和返回输入。最后CSS检查确认工具栏不会悬浮盖住卡片，手机语言选择器各316px。该阶段模型0POST，不作为新内容质量评分。见[参考视频工作区报告](../docs/acceptance-reports/2026-10-12-reference-video-workflow/report.md)。

### 字幕空轨道及画面文字识别范围

解析未返回字幕语言时，视频智能面板仍保留显式读取、翻译和总结入口；请求错误就地显示。用户报告B站`BV1B84y1q7Hr`的字幕操作出现“平台字幕轨道结构无效”；本轮只对照后端轨道校验代码，没有重新读取该视频的API响应。当前前端不检测或识别视频画面文字。OCR已登记为后续候选，暂无按钮、自动回退、抽帧流程或OCR依赖；后续实施前需先区分无字幕与真实结构/访问错误。

2026-10-13错误展示更新：B站播放安全校验响应有单独`verification_required`提示；前端全量19个测试文件、169项及生产构建通过，范围见[本轮报告](../docs/acceptance-reports/2026-10-13-bilibili-verification/report.md)。这不代表字幕轨道问题或稳定下载已修复。

此前使用范围提交121bb78的验证：网页默认“按视频标题命名”，复用服务端文件的 `Content-Disposition`；关闭选项可用来源直链，但来源站决定文件名。视频智能面板提示长文暂不支持，超出后端可配置正文上限时模型请求前停止；字幕和视频下载继续可用。该提交的前端155项、构建及1280/390px模拟验证通过，模型0POST；这些数字为当时范围，后续UI验证按上方2026-10-13各阶段报告读取，本轮文档维护没有新增前端验证。

早期四phase内容验收是独立历史候选，16 POST/153697 tokens及其短中/长文结论仍只适用于[当时的长文复验报告](../docs/acceptance-reports/2026-10-12-summary-long-final-check/report.md)。phase15的API实验不改变前端能力；结构校验也不等于内容正确。当前状态与后续边界见上方[当前交接](../docs/handoff-2026-10-16-deepseek-step1.md)。

## 工程约定（每次遵守）

> 遵守仓库根目录 `AGENTS.md` 中的工程约定。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端`ytdlp_service.py`唯一接触yt-dlp）。PIXI背景/角色只读scene派生的业务信号，另经窄接口接收区域几何、菜单操作与媒体偏好，不访问下载API或修改下载状态；下载和视频智能分别由hook编排，经api.js调用后端，视图通过props展示结果。
5. **成熟方案优先，避免重复造轮子**：交互、状态、组件和通用能力开发前，复用已有资料并评估成熟库/官方方案，适用时优先采用；独立实现业务适配，记录采用或不适用原因，执行 [AGENTS.md §10](../AGENTS.md)。

## 启动说明

GitHub排除Live2D模型、纹理、表情及动作资源；Cubism Core运行库保留。角色模型需要在本机补齐，位置由`src/pixi/mascotConfig.js`的registry指定；缺失时`createMascot`使用已有fallback。本机模型仍保留，ignore规则不等于原历史已经删除，发布须按根交接使用隔离过滤副本。

```bash
cd frontend
npm install
npm run dev
```

- 前端开发服务器使用 Vite，默认端口为 `5173`。开发期的 `/api` 请求由 `vite.config.js` 代理到 `http://localhost:8000`；可用进程环境变量 `VITE_PROXY_TARGET` 覆盖代理目标。Vite 代理只适用于开发服务器。
- 后端需另开终端启动（FastAPI + uvicorn；从仓库根目录运行以下命令）：

  ```bash
  cd backend
  uv run uvicorn app.main:app --reload --port 8000 --env-file .env
  ```

前端使用相对路径 `/api`，同源开发请求会经上述代理转发。生产环境的 API 路由由实际部署配置负责，不能依赖 Vite 开发代理。

## 鉴权与额度显示

- F-006已实现并验证：启动/认证恢复期间与游客均显示首页；顶部登录按钮才打开登录/注册页。游客填写的URL在进入和退出AuthScene、认证成功返回首页时保留；匿名提交解析只在首页提示使用顶部登录按钮，不发解析业务API。成功登录/注册后不自动解析。启动时 `useAuth` 从 `localStorage` 读取 `auth_token` 并请求 `/api/auth/me` 校验；恢复成功直接进首页并显示AuthBar，失败回游客首页。登录或注册后token写入`localStorage`，`api.js`后续请求加`Authorization: Bearer ...`；退出/换账号清除token和业务场景状态。后端受保护接口继续要求Bearer token。检查范围及mock限制见[F-006报告](../docs/implementation-reports/2026-10-17-f006.md)。
- 登录/注册响应不包含额度时，前端会再请求 `/api/auth/me` 读取 `quota`。首次补取失败时不显示额度；成功提交下载或收到 `quota` 错误后的刷新失败则保留上次已知额度，不阻断下载流程。
- 账号条只有在 `quota.unlimited === true` 时显示“下载额度不限”。有限额度只在 `limit` 与 `remaining` 都是整数时显示；两者缺失或不完整时不推断为不限，也不显示伪造的数字。

## 下载与视频智能交互

- `useDownload` 先调用 `/api/download`。返回 `mode: direct` 时浏览器跳转到服务端给出的 URL；返回 `mode: server` 时每 3 秒轮询 job，完成后自动触发文件保存。格式卡下方的“按视频标题命名”开关会随请求发送 `force_server`，勾选时使用服务端下载。直链跳转不能附带后端返回的鉴权 headers，因此需要这些 headers 的来源应选服务端模式。
- 服务端job/file请求都携Bearer，只读本人任务。文件通过fetch→Blob→objectURL保存，解析UTF-8 filename*及普通文件名；完成页提供自动保存一次、手动保存/重试、忙态和错误。取消/重置/退出/换账号/卸载阻止过期保存并释放Blob URL；整个文件缓存占内存，尚非流式直通。
- 封面img使用referrerPolicy=no-referrer；不能把图片HTTP加载成功等同于实际显示正常，需同时检查固有尺寸和布局尺寸。
- `useVideoInsights` 与下载 reducer 分开管理字幕、翻译、总结和错误。结果页可以分别调用“查看字幕”“翻译字幕”“生成总结”；输出语言列表由 `state/insightConfig.js` 提供。没有检测到字幕时操作仍可尝试，后端/上游原因显示在视频智能面板，不替换下载场景或下载错误状态。
- 每次视频智能操作会中止上一项视频智能请求；视频 URL 改变或退出登录时也会中止并清空结果。`VideoInsights.jsx` 通过 props 接收状态和回调，不直接导入下载逻辑。

开发期测试命令由 `frontend/package.json` 定义：`npm test` 执行 Vitest，`npm run test:watch` 启动监听模式。文档维护自身不触发测试或生产构建。2026-10-10 [旧结果生命周期整改](../docs/acceptance-reports/2026-10-10-source-first-summary/report.md)已清空新请求对应kind的旧结果，保留其他类型缓存及取消/过期响应保护；4项hook回归及headless Edge真实成功→本地上游503回归通过，失败后旧summary不再显示。此前[HTTP页面补验](../docs/acceptance-reports/2026-10-09-online-formal-flow/report.md)记录的旧结果残留属于修复前版本，证据不改。两轮均未实测密码登录、真实模型质量、下载、移动/GPU或重新构建。以往的浏览器、GPU、布局和测试数字只代表各自报告记录的源码、日期和设备；详见[文档索引](../docs/README.md)及[历史浏览器报告](../docs/acceptance-reports/2026-10-04-browser-e2e/report.md)、[历史移动/GPU报告](../docs/acceptance-reports/2026-10-04-public-mobile-gpu/report.md)、[历史响应式角色报告](../docs/acceptance-reports/2026-10-04-responsive-mascot/report.md)。

## Live2D 模型署名与授权

**历史交互验证（2026-10-11）**：当时角色使用视口自由摆放；点击/Enter/Space打开换装菜单，模型表面支持pinch-zoom，背景canvas保持pan-y/pinch-zoom。151项测试/build及Edge/RTX4050桌面/CDP触摸模拟15项通过，真手机未测，详见[当时报告](../docs/acceptance-reports/2026-10-11-ui-interaction-finish/report.md)。这些结果对应早期实现；当前F-003的行为与独立证据见上方，不把旧触摸模拟当作真机验证。

- **Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨（来源：b站工房，完整版）**；遵循作者使用规则：**非商用、不二传二改**。

## 如何新增模型 + 角色换装/表情

角色模型文件由 `public/live2d/<id>/` 提供，配置入口是 `src/pixi/mascotConfig.js` 的 `MODELS`。当前注册并默认加载 `bai`；`App.jsx` 使用 `DEFAULT_MODEL_ID`，没有运行时模型切换控件。增加注册项本身不会生成切换 UI：

1. 把新模型整套文件放进 `public/live2d/<id>/`（`<id>` 为小写唯一标识，含 `.model3.json` / `.moc3` / 纹理等）。
2. 在 `MODELS` 数组追加配置：`{ id, name, url, textureSize, heightRatio, x, y, mobile?, fallback?, hit? }`；按模型实际情况提供可选字段。
   - `textureSize` 声明模型纹理边长，供 WebGL 最大纹理尺寸预检；`fallback` 可指定加载失败时使用的静态图片，`hit` 可配置点击热区兜底。
   - 默认`free`模式的尺寸和初始位置由`heightRatio`、`x`/`y`及`PLACEMENT`配置决定；`mobile`仅描述一般视口布局参数，不覆盖App的手机门控。`embedded`几何与mask仅供显式旧调用兼容，不是产品界面默认模式。
   - 角色随下载阶段切换情绪眼（`EXPRESSIONS.stage`），另有随机道具（`EXPRESSIONS.random`）与点击弹出的换装/表情菜单（`EXPRESSIONS.menu`），均数据驱动。

当前只显示默认模型「白」。换装、表情和缩放由 `ExpressionMenu` 与 `EXPRESSIONS` 配置支持；角色菜单不负责切换模型。

> 说明：角色点击或键盘Enter/空格会打开换装/表情菜单；方向键移动，Home复位。角色可拖动，点击模型或按Enter/空格打开菜单，菜单内部提供移动、缩放、表情/道具、暂停和复位；页面不再显示两个额外悬浮按钮。默认桌面视口free活动；手机UA或≤800px不创建Live2D模型、fallback或交互DOM。表情/道具映射见`mascotConfig.js`的`EXPRESSIONS`配置，见`docs/design.md` §14.8。46个模型表情已全量暴露。

### 已知限制

- **「白」模型纹理为 16384×16384（16K）**：约1GB GPU纹理。实现按注册表纹理需求和`MAX_TEXTURE_SIZE`预先检查，不足时跳过模型/fallback请求并保留业务流程。F-003 Edge使用真实本地16K模型完成7项检查；模拟native/headless设备测试通过，但不是实际手机GPU内存峰值、长时FPS或context-loss评估。调整模型分辨率仍需作者许可，本轮未改模型资产。

## Cubism Core 说明

本项目的Live2D渲染依赖`pixi-live2d-display`，Cubism Core脚本由`frontend/index.html`从`/live2d/live2dcubismcore.min.js`加载，角色文件由`frontend/public/live2d/`自托管。手机门控不阻止这个共享Core脚本加载，只阻止模型和图片fallback的创建/加载。当前样式使用`tokens.css`中的系统字体栈，不请求Google Fonts；本机系统字体不同可能影响字形外观。请遵循Live2D Cubism官方使用许可与上述模型作者的**非商用、不二传二改**规则。

## 已知限制

- **直链模式为 best-effort**：`window.location.assign(d.url)` 无法附带后端返回的 `headers`（如 Referer/Cookie），因此带鉴权头的 CDN 直链可能被拒（403）。对这类链接勾选“按视频标题命名”，使用可携带headers的服务端下载；实际可下载性仍受来源平台限制。
- **音频现状**：只有WebAudio操作音效；BGM已移除，接入背景音乐需要独立设计与实现。
