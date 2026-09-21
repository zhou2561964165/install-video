import * as PIXI from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display';
import { SCENE_MASCOT } from './mascotConfig.js';
import { SCENE } from '../state/sceneMachine.js';

const MODEL_URL = '/live2d/miku/miku.model3.json';

export async function createMascot(app) {
  window.PIXI = PIXI;                       // 插件依赖 window.PIXI.Ticker
  Live2DModel.registerTicker(PIXI.Ticker);

  let model;
  try {
    model = await Live2DModel.from(MODEL_URL);
  } catch (e) {
    console.warn('[mascot] 模型加载失败，降级为静态占位', e);
    return createFallback(app);
  }

  model.anchor.set(0.5, 0.5);
  model.scale.set(0.28);
  model.x = app.screen.width * 0.82;
  model.y = app.screen.height * 0.62;
  app.stage.addChild(model);

  // 「奔跑」速度线（下载中显示）
  const speedLines = new PIXI.Graphics();
  speedLines.visible = false;
  app.stage.addChild(speedLines);

  let state = { expression: null, motion: 'idle', sway: false, run: false };
  let baseX = model.x;
  let t = 0;

  app.ticker.add(() => {
    t += 1;
    if (state.sway) model.x = baseX + Math.sin(t * 0.05) * 6;
    else if (state.run) {
      model.x = baseX + Math.sin(t * 0.3) * 40;   // 左右位移表达奔跑
      drawSpeedLines(speedLines, model.x, model.y);
    } else {
      model.x = baseX;
      speedLines.visible = false;
    }
  });

  return {
    setScene(scene) {
      const cfg = SCENE_MASCOT[scene] || SCENE_MASCOT[SCENE.ENTRY];
      state = cfg;
      if (cfg.expression) model.expression(cfg.expression);
      // expression: null → 跳过，保持中性（R-F3）
      if (cfg.motion) model.motion(cfg.motion, 0);
    },
    destroy() {
      app.stage.removeChild(model);
      app.stage.removeChild(speedLines);
      model.destroy();
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
  return { setScene() {}, destroy() { app.stage.removeChild(sprite); sprite.destroy(); } };
}
