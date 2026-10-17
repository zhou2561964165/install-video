# UI 主题系统扩展指南（皮蛋 AI / DeepSeek 全站参考风格）

> **F-003小圈范围（2026-10-17，用户已查验）：** 使用data-follow-exclude=parse明确解析组件，顶部.site-header与模型alpha是另外两类避让对象；普通按钮/链接/菜单不再自动纳入。内容列之外仍显示小圈，data-ui-follow只负责标题倾斜，不改变模型拖动边界。见[交验](implementation-reports/2026-10-17-f003-circle-scope.md)。

> **F-003待机行为（2026-10-17，用户已查验）：** 自动漫游及新加的位置/暂停菜单已取消。模型保持当前位置，手动拖动后停在新位置，原呼吸、摆头、换装、表情与道具继续；焦点、系统减少动态及后台状态不触发应用主动暂停。见[交验](implementation-reports/2026-10-17-f003-original-behavior.md)。F-006实现与验证已完成，等待用户查验，见[实施报告](implementation-reports/2026-10-17-f006.md)。

> **F-003续调历史记录：** 页面角色菜单/暂停活动额外按钮已取消；该阶段顶部登录按钮还只是F-006候选。当前F-006状态见[总表](follow-up-plan.md)。

> **F-003初始交验历史（2026-10-16）：** 当时记录自由活动、暂停与早期小圈范围；这些行为已被后续更新覆盖。最新用户已接受行为见顶部2026-10-17交验。

> **F-006交验（2026-10-17）：** 游客首页、顶部显式登录/注册、匿名解析本地提示且不请求API、URL保留与认证成功不自动解析均已实现并验证。Edge认证API使用mock；真实账号登录未测。最终范围见[实施报告](implementation-reports/2026-10-17-f006.md)。

> 版本：v3（2026-10-13；统一浅色默认/三档主题与全站玻璃UI）。视觉方案的历史分析见 `docs/ui-refactor-pidanai.md` 与 `docs/ui-refactor-pidanai-deep.md`；项目当前入口见 `docs/README.md`。
> 本文区分当前实现与扩展约定。模型/语言/主题等已有注册表适合数据驱动；新增渲染、请求或交互行为仍需实现对应代码。接手前遵守根目录 `AGENTS.md` 的工程约定与本文件的模块边界。

> **当前维护边界（2026-10-17）：** 标题中的DeepSeek是视觉参考，不指定模型供应商或模型默认值。F-003已获用户查验通过；F-006实现与验证已完成，等待用户查验。见[统一总表](follow-up-plan.md)及[F-006报告](implementation-reports/2026-10-17-f006.md)。

---

## 0. 一句话原则

UI改动先用 `ui-ux-pro-max` + `design-system`，skill优先于旧计划；颜色/字体/时长走 token，已有注册表项优先配置化，模块通过窄接口单向通信。当前产品和验收状态以[文档索引](README.md)及其当前入口为准。

**颜色/字体/时长一律走 `:root` token；已有能力优先通过配置表扩展；角色/背景表现读取 `scene` 派生状态，绝不 import 下载核心。** 改任何 UI，先判断「这是不是已有 token 的消费方」，是就直接用 token，不是就加 token 再消费。需要新行为时同步实现该行为，不能把“数据驱动”理解为无需改渲染或交互代码。

---

## 1. 三层 token 体系（primitive → semantic → component）

单一来源 = `frontend/src/styles/tokens.css` 的 `:root`。`global.css`保留基础组件，`reference.css`在其后统一参考视觉；组件层**只引用semantic/component token**，不裸写primitive值。

| 层 | 前缀 / 例子 | 职责 | 改哪里 |
| --- | --- | --- | --- |
| L1 primitive | `--sakura-*`、`--ink-*`、`--refract-*`、`--gray-*`、`--cream` | 集中维护基础色板 | `:root` |
| L2 semantic | `--accent` / `--surface*` / `--text-*` / `--border*` / `--scrim` / `--shadow-*` | 表达界面含义；可引用 primitive，也可在 token 层定义透明度或混色 | `:root` + `[data-theme='dark']` / `[data-theme='auto']` |
| L3 component | `--btn-*` / `--glass-*` / `--insight-*` / `--refract-ring` / `--font-*` / `--dur*` / `--size-*` / `--*-radius` | 组件外观与动效参数；主题覆盖仍在 token 层维护 | `:root`（必要时在主题块覆盖） |

**加一个 token 的正确顺序**：先判断所属层 → 加到 `:root` 对应段 → 组件通过 `var(--新token)` 消费。颜色、字体和时长不要散落在组件样式里；必要的透明度/混色也应封装为 token。

**PIXI 侧同步（关键坑）**：PIXI 不会自动应用 CSS 样式；`frontend/src/pixi/theme.js` 的 `palette` 通过 `cssVar('--xxx', fallback)` 显式读取 DOM token。无 DOM/CSS 时使用 fallback，改动消费色时应同步两处。**传给 PIXI `hex()` 的颜色必须是 hex**：`rgba()` 和 `color-mix()` 无法解析，会回退成白色。需要 PIXI 消费的颜色 token 应提供 hex 值；纯 CSS 用的玻璃、描边等 token 可以使用透明度和混色。

---

## 2. 加一个主题档

现状三档：`浅色 light`（默认）/ `深色 dark` / `自动 auto`。架构：

- `:root` 是浅色默认；`index.html` 初始`data-theme='light'`避免首屏主题闪变。
- `[data-theme='dark']` 覆盖语义色（包括accent/on-accent），组件与视频区自动继承；折射五色跨主题恒定。
- `[data-theme='auto']` + `@media (prefers-color-scheme: dark)`复用深色语义。
- 切换入口 `frontend/src/App.jsx` 的 `THEMES` 数组（`{ v, label }`）+ `setTheme`，`useEffect` 写 `document.documentElement.dataset.theme`。

**加第四档（如 `sepia`）**：
1. `App.jsx` `THEMES` 加 `{ v: 'sepia', label: '复古' }`（`aria-pressed`/按钮自动生成，无需改渲染）。
2. `tokens.css` 加 `[data-theme='sepia'] { --surface: …; --text-primary: …; … }` 覆盖块。
3. `pixi/theme.js` 的 `baseColor`初始化读取`--surface`（注意hex约束）；动态更新可见画布底色时需要额外的运行时同步接口。

**PIXI 背景色注意**：`pixi/stage.js`使用`backgroundAlpha:0`，画布透明，当前主题切换由CSS提供底色；palette/baseColor在模块初始化时读取，不宣称会逐帧重新读取。若使画布底色可见或动态改折射色，需要实现显式同步接口并核对各主题。

---

## 3. 加一个折射色（玻璃描边 / 光斑 / 背景点缀）

折射五色 `--refract-cyan/violet/pink/mint/warm` 跨主题恒定，用于玻璃1px描边环与PIXI光斑；Preloader光点样式/资源仍保留，但App已不再挂载该加载层。

**加第六色（如 `--refract-teal`）**，需三处同步：
1. `tokens.css` `:root` 加 `--refract-teal: #1fcdb0;`（**hex**）。
2. `pixi/theme.js` `palette` 加 `refractTeal: cssVar('--refract-teal', '#1fcdb0')`（fallback 与 CSS 一致）。
3. 消费处：`pixi/background.js` `createSpots` 的`colors[]`数组。`Preloader.jsx`的`SPOTS`属于未挂载的旧加载层代码，不是当前产品展示路径。

**要改渐变**（如加进 `--refract-ring` / `--grad-accent` 的 `linear-gradient` 色阶）：直接在这两个 token 的定义里增删 `color-mix(in srgb, var(--refract-*) 25%, transparent)` 一档即可。

---

## 4. 加背景特效（PIXI 光点 / preloader 光点）

背景光点是**数据驱动**，两处独立：

- **主场景 PIXI 光点**：`pixi/background.js` 的 `FX.spots` 配置（`count/size/drift/sway/alpha`）+ `createSpots()` 生成 + `layers` 数组登记。加新光斑 = 在 `layers` 加一个 `createXxx(root, size, low)` 函数 + 一个 `FX.xxx` 配置对象；`update(delta, intensity)` 里写运动，`resize()` 处理尺寸变化。**删除的 `drawPetal` 是死代码，新特效别复刻**——光晕用 `makeGlowTexture(128, hex(color), alpha)`（径向渐变软光斑），别画硬圆。
- **旧Preloader光点代码**：`components/ui/Preloader.jsx`的`SPOTS`数组提供`left/size/dur/delay/sway/color`，CSS由`.preloader__spot`与`@keyframes preloader-drift`渲染。文件仍存在，但App不挂载它；若未来重新使用，新增通用时长仍须走`:root`的`--dur-*` token。

**关键约束**：背景层是纯视觉层，`update`只读`delta/intensity`，**不感知下载状态**；`App.jsx`调用`pixi/background.js`导出的`intensityForScene(state.scene)`映射后传入强度。需要新的粒子行为时要同时更新图层实现和注册数组，单改配置不能生成新行为。

当前主背景只保留`spots`与`dust`两种柔和装饰，静态38px点阵由`reference.css`消费`--grid-spacing`/`--grid-color`。复用同一个PIXI ticker；隐藏文档时摘除背景更新，reduced-motion关闭，销毁时释放监听、容器子树和纹理。`App` resize先更新舞台尺寸再更新背景/角色，勿另建循环或把旧星点/气泡清单恢复成默认。

---

## 5. 加表情 / 道具 / 特效

映射与菜单选项在 `frontend/src/pixi/mascotConfig.js` 的 `EXPRESSIONS`；`ExpressionMenu.jsx` 读取这些选项，并实现分组切换、激活态、焦点管理与缩放按钮，再通过回调把参数操作交给 App/mascot。

| 段 | 用途 | 加一个 |
| --- | --- | --- |
| `EXPRESSIONS.stage` | 场景 → 情绪参数（圈圈眼/煎蛋眼/星星眼/生气） | 加 `scene: paramId` 映射 |
| `EXPRESSIONS.random` | 每 ~20s 随机道具（手柄/话筒/戳脸） | 加 `{ paramId, … }` |
| `EXPRESSIONS.menu` | 换装菜单（发型/衣服/配饰/颜色/情绪，single/toggle/multi 分组） | 在对应 `group.options` 加 `{ paramId, name }`，`mode` 决定单选/复选 |
| `EXPRESSIONS.effect` | `edle.motion3.json` 装饰特效（按 `stages` 触发） | 命中 `stages` 的场景列表加场景名 |

- 完整版「白」的表情文件由参数映射驱动，走 `coreModel.setParameterValueById(paramId, 1/0)` 直接写参数（**非** expression manager 单选）；具体可并存关系由 `EXPRESSIONS.menu` 的分组模式控制，并须避免与待机正弦驱动的 `IDLE` 参数冲突。
- 待机参数（`ParamAngleX/Y/Z` + `ParamBreath`）在`mascotConfig.js`的`IDLE`，运行时按`getParameterIndex`过滤缺失参数。产品默认free模式在单PIXI ticker上驱动待机；角色不自动漫游，用户拖动后位置保持。显式embedded兼容调用仍按区域约束，缺参不启动容器scale呼吸或逐帧DOM热区更新。

新增参数映射可只改配置；新增菜单交互语义或模型控制则要同步实现对应组件/模型代码。

---

## 6. 动画时长 token（`--dur-*`）

`--dur`（通用过渡 `.22s`）之外，循环/反馈类时长单独 token 化，**keyframe 不写死秒数**：

| token | 值 | 用途 |
| --- | --- | --- |
| `--dur-shake` | .35s | 错误抖动 |
| `--dur-breathe` | 2.4s | 错误呼吸 |
| `--dur-dim` | 3s | 错误渐隐 |
| `--dur-progress` | .3s | 进度条宽度过渡 |
| `--dur-spin` | 1s | spinner 旋转 |
| `--dur-spin-fast` | .8s | preloader spinner |
| `--dur-pulse` | 1.8s | preloader mark 脉冲 |
| `--dur-reveal` | .5s | 滚动揭示进场 |
| `--dur-focus` | .4s | 滚动聚焦过渡 |

通用过渡使用 `--dur`（`.22s`）；表格列出其余当前公共 token，值以 `tokens.css` 为准。新增动画先复用已有 token，否则增加语义化 token（注释用途），不要在 keyframe 中写死时长。CSS 动画须覆盖 `prefers-reduced-motion`；PIXI 动画也要沿用 `background.js` / `mascot.js` 的 reduced-motion 检查方式。

---

## 7. 玻璃 + 折射描边环（复用的坑）

- **玻璃配方**：普通玻璃面使用`--glass-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate))`，`backdrop-filter`及`-webkit-`声明消费该token。跟随镜片使用专门的`--cursor-lens-filter`，按各自组件用途维护。
- **折射 1px 描边环**：伪元素 `::before` 涂 `--refract-ring` 渐变 + CSS `mask`（`mask-composite: exclude` / `-webkit-mask-composite: xor`）只留 1px 环，不遮玻璃底、不动 backdrop-filter。`@supports (mask-composite: exclude) or (-webkit-mask-composite: xor)` 负责增强环效果。滚动面板（如表情菜单）用**淡描边**替代彩虹环（规避滚动时环错位），见 `.expression-menu` 的 `color-mix(in srgb, var(--refract-violet) 26%, var(--border))`。
- **`backdrop-filter` 祖先链检查**：修改玻璃面时检查祖先的`opacity`、`transform`、`filter`与裁切设置，结合目标浏览器中的实际效果定位问题；不能仅凭出现某个属性就断言滤镜必然失效。历史风险观察见`docs/ui-refactor-pidanai.md`。

---

## 8. 解耦与扩展边界

源码架构详见[design§13](design.md#13-当前前端架构业务状态与表现层)。“只读scene”约定用于阻止视觉修改下载业务；当前小圈实际读取DOM几何，菜单还持有表现状态，均通过窄接口工作。旧电影感fx组件不作为现有依赖，后续联动与布局风险登记在[总表F-005](follow-up-plan.md#9-f-005技术架构审视2026-10-16)。

1. **角色/背景根据场景驱动**：`App.jsx`调用`pixi/background.js`导出的`intensityForScene(state.scene)`计算粒子强度并传递阶段状态；`pixi/*` 不读取下载响应，也不 import 下载/API 核心。
2. **PIXI 颜色以 CSS token 为主来源**：`theme.js` 负责运行时桥接；fallback 与 CSS 同步维护。
3. **功能状态通过 hook 和 API 边界流动**：`useDownload` 编排下载、`useVideoInsights` 编排字幕/翻译/总结；`VideoInsights.jsx` 通过 props 接收状态与回调，不能读写下载 reducer。后端 `ytdlp_service.py` 是唯一接触 yt-dlp 的层。
4. **配置适用于已有扩展点**：`THEMES`、`FX`、`SPOTS`、`EXPRESSIONS` 是现存数据入口；新交互、渲染层或请求流程仍需要实现和验证相应代码，不能只添加配置项。

---

## 9. 快速索引（改哪个，看哪里）

| 想改 | 文件 | 入口 |
| --- | --- | --- |
| 配色 / 品牌蓝 / 折射色 | `styles/tokens.css` `:root` | `--sakura-*` / `--refract-*` / `--accent*` |
| 浅/深/自动主题 | `tokens.css` `[data-theme='dark'/'auto']` + `App.jsx` `THEMES` | 覆盖块 / `THEMES` 数组 |
| PIXI 颜色 / 底色 | `pixi/theme.js` `palette` + `baseColor` | `cssVar` 桥接 |
| 背景光点 | `pixi/background.js` `FX` + `createSpots` | `FX.spots` 配置 |
| 旧Preloader光点（App未挂载） | `components/ui/Preloader.jsx` `SPOTS` | `SPOTS` 数组 |
| 角色待机与手动拖动 | `App.jsx`、`pixi/mascot.js`、`pixi/mascotConfig.js` | 视口`PLACEMENT`、窄句柄与App ticker；不自动漫游 |
| 角色DOM命中与控件穿透 | `hooks/useMascotHitArea.js`、`PointerFollower.jsx` | 动态DOM热区和几何避让 |
| 表情 / 道具 / 特效 | `pixi/mascotConfig.js` `EXPRESSIONS` + `IDLE` | 配置表 |
| 动画时长 | `tokens.css` `--dur*` | token 段 |
| 玻璃配方 / 描边环 | `tokens.css` `--glass-*` / `--refract-ring` | component 段 |
| 场景 → 粒子强度 | `pixi/background.js`的`intensityForScene`；`App.jsx`导入调用 | 映射函数 / 调用方 |
| 下载请求/轮询 | `hooks/useDownload.js` + `api.js` | 编排 hook / API 窄接口 |
| 字幕、翻译、总结 | `hooks/useVideoInsights.js` + `api.js` | 独立状态 / API 窄接口 |
| 额度显示 | `components/ui/AuthBar.jsx` | 消费 `quota.unlimited` / `limit` / `remaining` |

## 10. 当前面板、账号额度与登录布局

2026-10-13录像续改移除了主视觉装饰小字，标题/输入及功能信息承担层级；示例网站前仅保留一次“试试”。当前入口各宽度均为居中单列（F-002），角色行为见F-003；早期[跟随续测](acceptance-reports/2026-10-13-ui-follow-continuation/report.md)和[录像报告](acceptance-reports/2026-10-13-ui-follow-video/report.md)只对其采集时的实现有效。

### 10.1 圆形跟随与标题视差

- `components/ui/PointerFollower.jsx`由`App.jsx`传入`uiRef`，只消费DOM标记与矩形几何、写CSS表现变量，不读取下载/认证/视频智能状态。`data-ui-follow`标记标题展示区，`data-follow-plane`只变换当前展示标题；角色、表单、视频卡和按钮不随标题倾斜。
- 圆形基准尺寸为`clamp(96px, 13vw, 190px)`，`--follow-tilt: 8deg`、`--follow-roll: 3deg`，指针位移仍为12px。接近状态从当前圆径缩至18%并淡出，隐藏140ms、恢复180ms；所有尺寸/角度/时长/间距通过`tokens.css`的primitive→semantic→component token传递。
- 角色避让使用镜片基准圆与角色可见alpha边界的接触判断。只有顶部、显式解析表单和模型轮廓属于避让目标；普通按钮、链接、菜单及内容列两侧不隐藏小圈。标题倾斜使用全视口指针位置，纵向标题标记只决定作用的标题区域；模型拖动范围不由这些标记改变。
- 镜片外层只负责固定定位与位置缓动；内层负责`transform: scale()`和透明度过渡，不动画宽高。标题变换独立使用CSS transform transition；没有新增RAF、第二canvas、逐帧碰撞或GPU像素读取。
- F-003报告中的移动设备和窄视口门控仍适用于模型；小圈的当前可见范围以2026-10-17交验为准。其余设备/系统动效及指针恢复细节保留token与组件实现约束，不能用早期报告替代本轮范围。
- 避让边界包括普通控件及`data-follow-exclude="mascot"`角色区域/交互面。位于`inert`子树或`[role="dialog"][aria-hidden="true"]`内的元素及控件会被忽略；因此菜单关闭时即使CSS仍在淡出，也不会留下旧排除矩形。`ResizeObserver`和滚动/resize刷新目标及边界几何；`MutationObserver`跟踪`uiRef`子树增删、hidden/排除标记，并只在相关边界上观察style/class/inert/aria-hidden等变化。舞台和模型菜单在`uiRef`外，另观察其父节点挂载；不观察全document的style变化，避免镜片自身写样式引起刷新循环。卸载时断开观察器和事件监听。

- 视频智能面板以 AI 内容总结为主，字幕是来源；不扩展未授权的完整时间轴展示/导出。`VideoInsights.jsx` 接收 props，`useVideoInsights` 通过 `api.js` 请求；新操作会取消上一项视频智能请求，URL 改变时会清理旧结果。错误留在面板自己的状态中，下载 reducer 独立。
- 面板当前消费 `--insight-bg`、`--insight-result-bg`、`--insight-border`、`--insight-label-size`、`--insight-body-size`、`--insight-control-radius`。语言清单在 `state/insightConfig.js`；新增输出语言先扩充该注册表，再确认后端 API 接受对应值。
- 账号条的额度对象来自 `/api/auth/me`。只有 `quota.unlimited === true` 才显示“下载额度不限”；有限额度需同时有整数 `limit` 与 `remaining`。`null`、缺失或不完整字段表示前端没有可展示的额度，不应被解释成无限。
- **F-006已实现：** 未登录/认证恢复期间显示首页；顶部登录按钮显式打开鉴权页。首页保留游客输入的URL；匿名提交只显示请使用顶部登录按钮的本地提示，不发送解析API。鉴权页可返回首页并保留URL；登录/注册成功后回首页、保留URL但不自动解析。认证恢复成功直接进入首页并显示AuthBar，失败回游客首页。PIXI/Live2D角色只在认证成功、WebGL可用、UA非手机且视口宽度>800px时创建；后端Bearer/JWT权限不变。Edge认证API使用mock，真实账号登录未测。
- 默认free模式尺寸/初始位置来自`MODELS`和`PLACEMENT`配置。Android/iPhone/iPod/IEMobile/Windows Phone UA或≤800px（含手机横屏）不创建角色模型/图片fallback、角色交互DOM及控制区；共享Cubism Core脚本仍由`index.html`加载。`embedded`只给显式旧调用兼容。固定控件仍须检查重叠、水平溢出和键盘焦点。
- 本节描述源码当前行为，不复用历史浏览器验收结论；各日期、设备和覆盖范围见[文档索引](README.md)列出的报告。

## 11. Live2D待机与小圈避让（F-003，用户已查验）

默认`PLACEMENT.mode=free`，只在登录、WebGL可用、UA非手机且视口宽度>800px时创建角色。Android/iPhone/iPod/IEMobile/Windows Phone UA或宽度≤800px在模型创建前退出，不创建模型、静态fallback、角色交互面或常驻控制区；手机横屏仍由UA门控。共享Cubism Core脚本仍从`index.html`加载，不能将设备门控解释为`live2d`目录零请求。显式`embedded`只服务旧调用兼容。

角色由App ticker维持待机，不自动漫游；手动拖动后停留在新位置，呼吸、摆头和表情/道具继续。F-003取消页面额外悬浮控制和应用主动暂停。`fromSync`加载实例关闭库autoUpdate，并受AbortSignal与token化8秒等待上限管理；迟到实例由owner释放。fallback另有能力检查。

PointerFollower按F-003最新验收范围处理：小圈在全视口跟随指针，仅顶部、解析表单及模型alpha轮廓避让；普通按钮/链接/菜单和页面空白处保持显示。标题倾斜依据纵向标记与横向全视口位置变化。`useMascotHitArea`只调整DOM命中面，不裁切Live2D画面；模型和页面拖动范围保持既有行为。

用户已查验F-003最终范围。待机报告记录23文件/254项/build及本地模型验证；小圈范围报告记录23文件/257项/build、本地模型10项浏览器检查及独立复核。真手机、GPU峰值内存与长时FPS仍未验证；真实LLM POST为0，未部署。2026-10-16及更早报告仅对应当时实现，具体见[待机交验](implementation-reports/2026-10-17-f003-original-behavior.md)和[小圈范围交验](implementation-reports/2026-10-17-f003-circle-scope.md)。
