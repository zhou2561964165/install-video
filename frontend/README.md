# 万能视频下载网站 · 前端

一个「粘贴链接 → 解析 → 选清晰度 → 下载」的全流程视频下载前端，包含 PIXI 舞台背景、Live2D 角色（含程序化待机动画）、「lolimeow」紫罗兰浅/深主题视觉与音频交互。

视觉采用三层设计 token（primitive→semantic→component），浅/深主题由 `document.documentElement.dataset.theme` 切换，CSS 与 PIXI 颜色单一来源为 `src/styles/global.css` 的 `:root` 语义 token。详见根 `docs/design.md` §14。

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
  uvicorn app.main:app --reload --port 8000
  ```

- 前端开发服务器默认 `http://localhost:5173`，通过 Vite 代理转发 `/api` 到后端。

## 测试

```bash
npm test        # vitest run，全量单测
npm run test:watch
```

## Live2D 模型署名与授权

- **Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨（来源：b站工房，完整版）**；遵循作者使用规则：**非商用、不二传二改**。

## 如何新增模型 + 角色换装/表情

角色模型由 `src/pixi/mascotConfig.js` 里的 `MODELS` 注册表驱动（数据驱动，改渲染代码为 0）：

1. 把新模型整套文件放进 `public/live2d/<id>/`（`<id>` 为小写唯一标识，含 `.model3.json` / `.moc3` / 纹理等）。
2. 在 `MODELS` 数组追加一条：`{ id, name, url: '/live2d/<id>/<name>.model3.json', heightRatio, x, y }`。
   - `heightRatio` 为模型占屏幕高度的比例（0~1），渲染时按屏幕高等比缩放，任意尺寸屏幕都看到等比例模型；`x` / `y` 为相对屏幕宽高的占比（0~1）定位角色。
   - 角色随下载阶段切换情绪眼（`EXPRESSIONS.stage`），另有随机道具（`EXPRESSIONS.random`）与点击弹出的换装/表情菜单（`EXPRESSIONS.menu`），均数据驱动。

> 说明：**点击角色会弹出换装/表情菜单**（换发型 / 换衣服 / 大小变 / 配饰），拖动角色仍可任意摆放。表情/道具映射见 `mascotConfig.js` 的 `EXPRESSIONS` 配置（阶段映射、随机节奏、菜单分组），实现见 `docs/design.md` §14.8。

### 已知限制

- **「白」模型纹理为 16384×16384（16K）**：超过多数移动端与部分桌面 GPU 的 WebGL `MAX_TEXTURE_SIZE`（常见 4096/8192，部分桌面 16384），可能在这些设备上渲染失败或黑屏。如需移动端兼容，需征得作者许可后压缩纹理分辨率（改动模型属于「二改」）。

## Cubism Core 说明

本项目的 Live2D 渲染依赖 `pixi-live2d-display`。Cubism Core 运行库（`live2d.min.js` / `*.wasm`）已自托管于项目资源内（不依赖外部 CDN）。请确保按照 Live2D Cubism 官方使用许可与上述模型作者的**非商用、不二传二改**规则使用本项目。

## 已知限制

- **直链模式为 best-effort**：`window.location.assign(d.url)` 无法附带后端返回的 `headers`（如 Referer/Cookie），因此带鉴权头的 CDN 直链可能被拒（403）。对这类链接请使用「强制走服务器」选项，走服务端模式（可带 headers）稳定下载。
- **BGM 为占位**：`public/audio/bgm.mp3` 尚未提供真实音源，BGM 目前静默缺失（Web-Audio SFX 正常）。接入真实音源后自动生效。
