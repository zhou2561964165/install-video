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

- **Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨（来源：b站工房，免费版）**；遵循作者使用规则：**非商用、不二传二改**。

## 如何新增 / 切换模型

角色模型由 `src/pixi/mascotConfig.js` 里的 `MODELS` 注册表驱动（数据驱动，改渲染代码为 0）：

1. 把新模型整套文件放进 `public/live2d/<id>/`（`<id>` 为小写唯一标识，含 `.model3.json` / `.moc3` / 纹理等）。
2. 在 `MODELS` 数组追加一条：`{ id, name, url: '/live2d/<id>/<name>.model3.json', heightRatio, x, y }`。
   - `heightRatio` 为模型占屏幕高度的比例（0~1），渲染时按屏幕高等比缩放，任意尺寸屏幕都看到等比例模型；`x` / `y` 为相对屏幕宽高的占比（0~1）定位角色。
   - 角色不随下载场景切换表情/动作，也不做奔跑/摆动位移；下载各阶段的状态反馈由背景粒子/音频独立承担。

> 说明：当前仅注册「白」一个模型（`MODELS.length === 1`），因此不显示模型切换下拉，点击角色不触发切换（但可拖动角色到任意位置）。新增第二个模型后，`MODELS.length > 1` 会自动恢复「点击角色循环切换」。

### 已知限制

- **「白」模型纹理为 16384×16384（16K）**：超过多数移动端与部分桌面 GPU 的 WebGL `MAX_TEXTURE_SIZE`（常见 4096/8192，部分桌面 16384），可能在这些设备上渲染失败或黑屏。如需移动端兼容，需征得作者许可后压缩纹理分辨率（改动模型属于「二改」）。

## Cubism Core 说明

本项目的 Live2D 渲染依赖 `pixi-live2d-display`。Cubism Core 运行库（`live2d.min.js` / `*.wasm`）已自托管于项目资源内（不依赖外部 CDN）。请确保按照 Live2D Cubism 官方使用许可与上述模型作者的**非商用、不二传二改**规则使用本项目。

## 已知限制

- **直链模式为 best-effort**：`window.location.assign(d.url)` 无法附带后端返回的 `headers`（如 Referer/Cookie），因此带鉴权头的 CDN 直链可能被拒（403）。对这类链接请使用「强制走服务器」选项，走服务端模式（可带 headers）稳定下载。
- **BGM 为占位**：`public/audio/bgm.mp3` 尚未提供真实音源，BGM 目前静默缺失（Web-Audio SFX 正常）。接入真实音源后自动生效。
