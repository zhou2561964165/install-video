# 万能视频下载网站 · 前端

一个「粘贴链接 → 解析 → 选清晰度 → 下载」的全流程视频下载前端，包含 PIXI 舞台背景、Live2D 角色、二次元视觉与音频交互。

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

- **Live2D 角色「初音未来」—— 人物绘制：玄宝酱 · 建模：怂怂koe**
- 模型遵循作者使用规则：**非商用、不二传二改。**

## 如何新增 / 切换模型

角色模型由 `src/pixi/mascotConfig.js` 里的 `MODELS` 注册表驱动（数据驱动，改渲染代码为 0）：

1. 把新模型整套文件放进 `public/live2d/<id>/`（`<id>` 为小写唯一标识，含 `.model3.json` / `.moc3` / 纹理等）。
2. 在 `MODELS` 数组追加一条：`{ id, name, url: '/live2d/<id>/<name>.model3.json', scale, x, y }`。
   - `scale` 为缩放，`x` / `y` 为相对屏幕宽高的占比（0~1）定位角色。
   - 若该模型的 expression / motion 名与共享默认（`SCENE_MASCOT`）不同，可在条目里加 `scene` 字段按场景覆盖。
3. 前端会自动在右上角显示「模型」下拉框（`MODELS.length > 1` 时出现），选中即切换。

运行时切换走 `mascot.js` 暴露的 `switchModel(id)`（销毁旧模型 → 加载新模型 → 重放当前场景表情）；失败时保留旧模型，不中断。

## Cubism Core 说明

本项目的 Live2D 渲染依赖 `pixi-live2d-display`。Cubism Core 运行库（`live2d.min.js` / `*.wasm`）已自托管于项目资源内（不依赖外部 CDN），渲染水印已关闭。请确保按照 Live2D Cubism 官方使用许可与上述模型作者的**非商用、不二传二改**规则使用本项目。

## 已知限制

- **直链模式为 best-effort**：`window.location.assign(d.url)` 无法附带后端返回的 `headers`（如 Referer/Cookie），因此带鉴权头的 CDN 直链可能被拒（403）。对这类链接请使用「强制走服务器」选项，走服务端模式（可带 headers）稳定下载。
- **BGM 为占位**：`public/audio/bgm.mp3` 尚未提供真实音源，BGM 目前静默缺失（Web-Audio SFX 正常）。接入真实音源后自动生效。
