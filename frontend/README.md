# 万能视频下载网站 · 前端

登录后可以粘贴链接、解析视频、选择格式并下载。解析结果页还提供查看字幕、翻译字幕和生成 AI 总结。页面使用 PIXI 舞台背景和 Live2D 角色；没有 WebGL 时使用 CSS 背景降级。

主题有浅色、深色和自动三档，由 `document.documentElement.dataset.theme` 驱动。CSS token 的主定义在 `src/styles/global.css` 的 `:root`；PIXI 通过 `src/pixi/theme.js` 读取 CSS 变量，并为 DOM/CSS 不可用的环境保留匹配的 fallback。设计背景见根目录 [设计文档](../docs/design.md)。

产品目前以视频内容总结为主，字幕读取和翻译是辅助功能；完整字幕时间轴和导出不在当前交付范围。项目状态入口见[文档索引](../docs/README.md)，当前总结验收交接见[当前总结交接](../docs/handoff-2026-10-10.md)。

## 工程约定（每次遵守）

> 遵守仓库根目录 `AGENTS.md` 中的工程约定。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp）。PIXI 背景/角色只消费由 `scene` 派生的表现状态；下载和视频智能分别由 hook 编排，经 `api.js` 调用后端，视图组件通过 props 展示结果，不绕过接口读写另一功能的状态。
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

- 未登录时显示登录/注册页。启动时 `useAuth` 从 `localStorage` 读取 `auth_token` 并请求 `/api/auth/me` 校验；登录或注册后也会把 token 写入 `localStorage`，`api.js` 在后续 API 请求中加 `Authorization: Bearer ...`。退出时清除 token 和当前下载场景。
- 登录/注册响应不包含额度时，前端会再请求 `/api/auth/me` 读取 `quota`。成功提交下载或收到 `quota` 错误后也会刷新额度；刷新失败时隐藏未知额度，不阻断下载流程。
- 账号条只有在 `quota.unlimited === true` 时显示“下载额度不限”。有限额度只在 `limit` 与 `remaining` 都是整数时显示；两者缺失或不完整时不推断为不限，也不显示伪造的数字。

## 下载与视频智能交互

- `useDownload` 先调用 `/api/download`。返回 `mode: direct` 时浏览器跳转到服务端给出的 URL；返回 `mode: server` 时每 3 秒轮询 job，完成后自动触发文件保存。格式卡下方的“强制走服务器”开关会随请求发送 `force_server`。直链跳转不能附带后端返回的鉴权 headers，因此需要这些 headers 的来源应选服务端模式。
- `useVideoInsights` 与下载 reducer 分开管理字幕、翻译、总结和错误。结果页可以分别调用“查看字幕”“翻译字幕”“生成总结”；输出语言列表由 `state/insightConfig.js` 提供。没有检测到字幕时操作仍可尝试，后端/上游原因显示在视频智能面板，不替换下载场景或下载错误状态。
- 每次视频智能操作会中止上一项视频智能请求；视频 URL 改变或退出登录时也会中止并清空结果。`VideoInsights.jsx` 通过 props 接收状态和回调，不直接导入下载逻辑。

开发期测试命令由 `frontend/package.json` 定义：`npm test` 执行 Vitest，`npm run test:watch` 启动监听模式。文档维护自身不触发测试或生产构建。2026-10-10 [旧结果生命周期整改](../docs/acceptance-reports/2026-10-10-source-first-summary/report.md)已清空新请求对应kind的旧结果，保留其他类型缓存及取消/过期响应保护；4项hook回归及headless Edge真实成功→本地上游503回归通过，失败后旧summary不再显示。此前[HTTP页面补验](../docs/acceptance-reports/2026-10-09-online-formal-flow/report.md)记录的旧结果残留属于修复前版本，证据不改。两轮均未实测密码登录、真实模型质量、下载、移动/GPU或重新构建。以往的浏览器、GPU、布局和测试数字只代表各自报告记录的源码、日期和设备；详见[文档索引](../docs/README.md)及[历史浏览器报告](../docs/acceptance-reports/2026-10-04-browser-e2e/report.md)、[历史移动/GPU报告](../docs/acceptance-reports/2026-10-04-public-mobile-gpu/report.md)、[历史响应式角色报告](../docs/acceptance-reports/2026-10-04-responsive-mascot/report.md)。

## Live2D 模型署名与授权

- **Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨（来源：b站工房，完整版）**；遵循作者使用规则：**非商用、不二传二改**。

## 如何新增模型 + 角色换装/表情

角色模型文件由 `public/live2d/<id>/` 提供，配置入口是 `src/pixi/mascotConfig.js` 的 `MODELS`。当前注册并默认加载 `bai`；`App.jsx` 使用 `DEFAULT_MODEL_ID`，没有运行时模型切换控件。增加注册项本身不会生成切换 UI：

1. 把新模型整套文件放进 `public/live2d/<id>/`（`<id>` 为小写唯一标识，含 `.model3.json` / `.moc3` / 纹理等）。
2. 在 `MODELS` 数组追加配置：`{ id, name, url, textureSize, heightRatio, x, y, mobile?, fallback?, hit? }`；按模型实际情况提供可选字段。
   - `textureSize` 声明模型纹理边长，供 WebGL 最大纹理尺寸预检；`fallback` 可指定加载失败时使用的静态图片，`hit` 可配置点击热区兜底。
   - `heightRatio` 为目标模型高度相对视口高度的比例（0~1）；`x` / `y` 为定位占比。桌面使用视口作为定位区域，窄屏可用 `mobile` 配置阈值、目标高度与区域内位置，实际布局还会受模型边界和安全留白约束。
   - 角色随下载阶段切换情绪眼（`EXPRESSIONS.stage`），另有随机道具（`EXPRESSIONS.random`）与点击弹出的换装/表情菜单（`EXPRESSIONS.menu`），均数据驱动。

当前只显示默认模型「白」。换装、表情和缩放由 `ExpressionMenu` 与 `EXPRESSIONS` 配置支持；角色菜单不负责切换模型。

> 说明：**点击角色会弹出换装/表情菜单**（换发型 / 换衣服 / 大小变 / 配饰 / 颜色 / 情绪），拖动位置受视口和窄屏预留区域的边界约束。表情/道具映射见 `mascotConfig.js` 的 `EXPRESSIONS` 配置（阶段映射、随机节奏、菜单分组、装饰特效 `edle.motion3.json`），实现见 `docs/design.md` §14.8。46 个表情已全量暴露。

### 已知限制

- **「白」模型纹理为 16384×16384（16K）**：约 1GB GPU 纹理。新实现按注册表纹理需求和 `MAX_TEXTURE_SIZE` 预先检查，不足时跳过模型目录请求、禁用角色交互并保留解析，避免重复上传同一超限纹理作兜底；受控8K模拟已测，未证明真实手机内存/context loss兼容。调整模型分辨率仍需作者许可，本轮未改模型资产。

## Cubism Core 说明

本项目的 Live2D 渲染依赖 `pixi-live2d-display`，Cubism Core 脚本由 `frontend/index.html` 从 `/live2d/live2dcubismcore.min.js` 加载，角色文件由 `frontend/public/live2d/` 自托管。字体仍通过 Google Fonts 请求，系统字体栈提供回退；因此不能把整个前端描述为完全离线。请遵循 Live2D Cubism 官方使用许可与上述模型作者的**非商用、不二传二改**规则。

## 已知限制

- **直链模式为 best-effort**：`window.location.assign(d.url)` 无法附带后端返回的 `headers`（如 Referer/Cookie），因此带鉴权头的 CDN 直链可能被拒（403）。对这类链接请使用「强制走服务器」选项，走服务端模式（可带 headers）稳定下载。
- **音频现状**：只有WebAudio操作音效；BGM已移除，接入背景音乐需要独立设计与实现。
