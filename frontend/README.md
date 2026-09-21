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

## Cubism Core 说明

本项目的 Live2D 渲染依赖 `pixi-live2d-display`。Cubism Core 运行库（`live2d.min.js` / `*.wasm`）已自托管于项目资源内（不依赖外部 CDN），渲染水印已关闭。请确保按照 Live2D Cubism 官方使用许可与上述模型作者的**非商用、不二传二改**规则使用本项目。
