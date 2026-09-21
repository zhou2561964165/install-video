import * as PIXI from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display';
import { SCENE_MASCOT, MODELS } from './mascotConfig.js';
import { SCENE } from '../state/sceneMachine.js';

// 创建 Live2D 角色。modelId 对应 MODELS 里的 id（缺省/未命中回落到 MODELS[0]）。
// 返回 { getModelId, switchModel, setScene, destroy }。
export async function createMascot(app, modelId) {
  window.PIXI = PIXI;                       // 插件依赖 window.PIXI.Ticker
  Live2DModel.registerTicker(PIXI.Ticker);

  // 运行时态：ticker / setScene / switchModel 共享的可变引用
  const current = { model: null, cfg: null, scene: SCENE.ENTRY, state: null };
  let baseX = 0;

  // 「奔跑」速度线（下载中显示），独立于模型，切换模型时保留
  const speedLines = new PIXI.Graphics();
  speedLines.visible = false;
  app.stage.addChild(speedLines);

  // 解析某模型 + 场景的表情/动作配置：模型可选覆盖（cfg.scene）→ 共享默认 SCENE_MASCOT
  function resolveCfg(cfg, scene) {
    const fallback = SCENE_MASCOT[SCENE.ENTRY];
    const base = SCENE_MASCOT[scene] || fallback;
    const ov = cfg.scene && (cfg.scene[scene] || cfg.scene[SCENE.ENTRY]);
    return ov ? { ...base, ...ov } : base;
  }

  function place(instance, cfg) {
    instance.anchor.set(0.5, 0.5);
    instance.scale.set(cfg.scale);
    instance.x = app.screen.width * cfg.x;
    instance.y = app.screen.height * cfg.y;
    baseX = instance.x;
  }

  async function loadModel(id) {
    const cfg = MODELS.find((m) => m.id === id) || MODELS[0];
    try {
      const instance = await Live2DModel.from(cfg.url);
      place(instance, cfg);
      app.stage.addChild(instance);
      return { cfg, instance };
    } catch (e) {
      console.warn('[mascot] 模型加载失败', cfg.id, e);
      return { cfg, instance: null };
    }
  }

  // 初始加载；失败则整体降级为静态占位（与旧行为一致）
  const loaded = await loadModel(modelId);
  if (!loaded.instance) return createFallback(app);
  current.cfg = loaded.cfg;
  current.model = loaded.instance;

  let t = 0;
  app.ticker.add(() => {
    if (!current.model) return;
    t += 1;
    const s = current.state;
    if (s.sway) current.model.x = baseX + Math.sin(t * 0.05) * 6;
    else if (s.run) {
      current.model.x = baseX + Math.sin(t * 0.3) * 40;   // 左右位移表达奔跑
      drawSpeedLines(speedLines, current.model.x, current.model.y);
    } else {
      current.model.x = baseX;
      speedLines.visible = false;
    }
  });

  function applyScene(scene) {
    current.scene = scene;
    const cfg = resolveCfg(current.cfg, scene);
    current.state = cfg;
    if (cfg.expression) current.model.expression(cfg.expression);
    // expression: null → 跳过，保持中性（R-F3）
    if (cfg.motion) current.model.motion(cfg.motion, 0);
  }
  applyScene(SCENE.ENTRY);

  return {
    getModelId() { return current.cfg.id; },
    async switchModel(id) {
      if (id === current.cfg.id) return;
      const next = await loadModel(id);
      if (!next.instance) return;           // 新模型加载失败：保留旧模型，不做任何改动
      if (current.model) { app.stage.removeChild(current.model); current.model.destroy(); }
      current.model = next.instance;
      current.cfg = next.cfg;
      applyScene(current.scene);            // 重放当前场景的表情/动作
    },
    setScene(scene) { applyScene(scene); },
    destroy() {
      if (current.model) { app.stage.removeChild(current.model); current.model.destroy(); }
      app.stage.removeChild(speedLines);
    },
  };
}

function drawSpeedLines(g, cx, cy) {
  g.clear();
  g.lineStyle(2, 0xffffff, 0.5);
  for (let i = 0; i < 5; i++) {
    const y = cy - 120 + i * 40;
    const len = 30 + Math.sin(i) * 20;
    g.moveTo(cx - 180, y).lineTo(cx - 180 + len, y);
  }
  g.visible = true;
}

function createFallback(app) {
  const sprite = PIXI.Sprite.from('/live2d/miku/miku.4096/texture_00.png');
  sprite.anchor.set(0.5, 0.5);
  sprite.scale.set(0.2);
  sprite.x = app.screen.width * 0.82;
  sprite.y = app.screen.height * 0.62;
  app.stage.addChild(sprite);
  return {
    getModelId() { return 'miku'; },
    async switchModel() {},
    setScene() {},
    destroy() { app.stage.removeChild(sprite); sprite.destroy(); },
  };
}
