# 万能视频下载网站 · 前端

一个「注册/登录 → 粘贴链接 → 解析 → 选清晰度 → 下载」的全流程视频下载前端，并在解析结果页提供字幕读取、字幕翻译与 AI 总结。包含 PIXI 舞台背景、Live2D 角色（含程序化待机动画）、深色液态玻璃 + 樱花粉辉光主题视觉与音频交互。

视觉采用三层设计 token（primitive→semantic→component），浅/深主题由 `document.documentElement.dataset.theme` 切换，CSS 与 PIXI 颜色单一来源为 `src/styles/global.css` 的 `:root` 语义 token。详见根 `docs/design.md` §14。

当前方向以AI理解和总结内容为主；字幕读取/翻译是辅助能力，完整时间轴展示与导出不属于本轮交付。当前文档入口见 [交接文档](../docs/handoff.md) 和 [文档索引](../docs/README.md)。

## 工程约定（每次遵守）

> 与根目录 `CLAUDE.md` 一致（最高优先级）。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。

## 启动说明

```bash
npm install
npm run dev
```

- 后端需先启动（FastAPI + uvicorn，默认 `http://localhost:8000`）：

  ```bash
  # 在仓库根目录另开终端；本机 .env 含被 Git 忽略的 DeepSeek 配置
  cd backend
  uv run uvicorn app.main:app --reload --port 8000 --env-file .env
  ```

- 前端开发服务器默认 `http://localhost:5173`，通过 Vite 代理转发 `/api` 到后端。

## 测试

```bash
npm test        # vitest run，全量单测
npm run test:watch
```

最近实测前端66/66，生产构建通过。回归覆盖解析阶段未发现字幕时，用户仍可显式尝试总结；错误保留在视频智能面板，下载操作仍可用。v3实现和文档已提交到 `main`，当前验收边界见 [`docs/handoff.md`](../docs/handoff.md)。

2026-10-04增量验收已补齐桌面与375px的真实应用API浏览器流程：40项检查、6个保存文件，720p/360p选择与ffprobe高度匹配；无字幕和LLM模拟upstream503均只影响AI面板。独立公网Archive桌面解析→真实模型总结另有9项通过。详见[浏览器报告](../docs/acceptance-reports/2026-10-04-browser-e2e/report.md)。本轮使用既有无WebGL的CSS降级，未验证16K角色的GPU或手机硬件兼容。

后续[公网移动/GPU报告](../docs/acceptance-reports/2026-10-04-public-mobile-gpu/report.md)补齐375px页面真实下载保存：9项检查、一个854×480 H.264/Opus、75.741秒Matroska文件，来源仅列“最佳”，并非用户选择480p。独立默认Edge桌面/375px均使用RTX4050/ANGLE D3D11，MAX_TEXTURE_SIZE=16384、16K纹理已上传、截图角色可见。仅覆盖当前Windows设备，不证明真手机或低档GPU兼容；移动示例按钮与角色脸部有视觉重叠、桌面脚部超出屏幕底边，完整角色菜单/触摸交互未测。生产前端未改。

最新[响应式角色报告](../docs/acceptance-reports/2026-10-04-responsive-mascot/report.md)修复手机控件遮角色、桌面脚部裁切、取消触摸误开菜单与原生纵向滚动；模型资产不改。基础320/375/720/1440真实RTX4050布局/GPU41项，最终375px触摸5项分别通过，横拖60.54px且页面不滚、原生纵滚185px；菜单按钮44px、焦点循环/恢复。焦点控件避开固定栏的几何通过，但该专测有Google字体网络错误，不能说全部浏览器检查成功。8K仅受控模拟，未真机；异步字体/尺寸变化可能使拖动短暂重新居中。全量73项与构建通过。

## 当前交互与数据边界

- 登录后进入五屏滚动落地页；首页不移动到登录前。
- 重型PIXI/Live2D在登录后初始化，登录表单立即可操作；退出会清理旧下载场景和AI请求。
- `useVideoInsights` 通过 `api.js` 调用，结果组件只接收props；AI失败在面板就地展示，不替换下载状态机。
- 移动端模型位置/高度由 `mascotConfig.js` 的 `mobile` 配置控制；账号条、主题开关与选择卡的安全间距已做375px验证。
- `--insight-*` 样式token定义在 `global.css`；目标语言注册表位于 `state/insightConfig.js`。

## Live2D 模型署名与授权

- **Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨（来源：b站工房，完整版）**；遵循作者使用规则：**非商用、不二传二改**。

## 如何新增模型 + 角色换装/表情

角色模型由 `src/pixi/mascotConfig.js` 里的 `MODELS` 注册表驱动（数据驱动，改渲染代码为 0）：

1. 把新模型整套文件放进 `public/live2d/<id>/`（`<id>` 为小写唯一标识，含 `.model3.json` / `.moc3` / 纹理等）。
2. 在 `MODELS` 数组追加一条：`{ id, name, url: '/live2d/<id>/<name>.model3.json', heightRatio, x, y }`。
   - `heightRatio` 为模型占屏幕高度的比例（0~1），渲染时按屏幕高等比缩放，任意尺寸屏幕都看到等比例模型；`x` / `y` 为相对屏幕宽高的占比（0~1）定位角色。
   - 角色随下载阶段切换情绪眼（`EXPRESSIONS.stage`），另有随机道具（`EXPRESSIONS.random`）与点击弹出的换装/表情菜单（`EXPRESSIONS.menu`），均数据驱动。

当前只显示默认模型「白」，运行时模型切换UI已删除。追加注册项不会自动生成模型切换控件；新增模型若需默认使用，应同步调整默认注册/ID。换装、表情和缩放交互仍可用。

> 说明：**点击角色会弹出换装/表情菜单**（换发型 / 换衣服 / 大小变 / 配饰 / 颜色 / 情绪），拖动角色仍可任意摆放。表情/道具映射见 `mascotConfig.js` 的 `EXPRESSIONS` 配置（阶段映射、随机节奏、菜单分组、装饰特效 `edle.motion3.json`），实现见 `docs/design.md` §14.8。46 个表情已全量暴露。

### 已知限制

- **「白」模型纹理为 16384×16384（16K）**：约 1GB GPU 纹理。新实现按注册表纹理需求和 `MAX_TEXTURE_SIZE` 预先检查，不足时跳过模型目录请求、禁用角色交互并保留解析，避免重复上传同一超限纹理作兜底；受控8K模拟已测，未证明真实手机内存/context loss兼容。调整模型分辨率仍需作者许可，本轮未改模型资产。

## Cubism Core 说明

本项目的 Live2D 渲染依赖 `pixi-live2d-display`。Cubism Core 运行库（`live2d.min.js` / `*.wasm`）已自托管于项目资源内（不依赖外部 CDN）。请确保按照 Live2D Cubism 官方使用许可与上述模型作者的**非商用、不二传二改**规则使用本项目。

## 已知限制

- **直链模式为 best-effort**：`window.location.assign(d.url)` 无法附带后端返回的 `headers`（如 Referer/Cookie），因此带鉴权头的 CDN 直链可能被拒（403）。对这类链接请使用「强制走服务器」选项，走服务端模式（可带 headers）稳定下载。
- **音频现状**：只有WebAudio操作音效；BGM已移除，接入背景音乐需要独立设计与实现。
