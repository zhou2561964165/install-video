import * as PIXI from 'pixi.js';
import { SCENE } from '../state/sceneMachine.js';

// 场景 → 强度档：安静 0 / 活跃 1（spec §6）
export function intensityForScene(scene) {
  switch (scene) {
    case SCENE.PARSING:
    case SCENE.DOWNLOADING:
      return 1;
    default:
      return 0;
  }
}

function makeGradientTexture(w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(2, w);
  canvas.height = Math.max(2, h);
  const ctx = canvas.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, w, h);
  g.addColorStop(0, '#0b0f2a');
  g.addColorStop(0.5, '#3a1c71');
  g.addColorStop(1, '#0f3460');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  return PIXI.Texture.from(canvas);
}

export function createBackground(app, tier = 'high') {
  const low = tier === 'low';

  const gradient = new PIXI.Sprite(makeGradientTexture(app.screen.width, app.screen.height));
  gradient.width = app.screen.width;
  gradient.height = app.screen.height;
  app.stage.addChild(gradient);

  // 色相缓移（ColorMatrixFilter.hue 在 v6 的 pixi.js 中内置）；低档去掉后处理以省 GPU
  let hue = null;
  if (low) {
    gradient.filters = [];
  } else {
    hue = new PIXI.filters.ColorMatrixFilter();
    gradient.filters = [hue];
  }

  // 环境粒子：普通 Container（ParticleContainer 仅支持 Sprite，Graphics 会触发渲染崩溃）
  const particles = new PIXI.Container();
  app.stage.addChild(particles);

  const MAX = low ? 40 : 120;
  const items = [];
  for (let i = 0; i < MAX; i++) {
    const g = new PIXI.Graphics();
    g.beginFill(i % 3 === 0 ? 0xffc9e8 : (i % 3 === 1 ? 0x7ef9ff : 0xffd700), 0.6);
    g.drawCircle(0, 0, 1 + (i % 3));
    g.endFill();
    g.x = Math.random() * app.screen.width;
    g.y = Math.random() * app.screen.height;
    g.vx = (Math.random() - 0.5) * 0.4;
    g.vy = -(0.2 + Math.random() * 0.8);
    items.push(g);
    particles.addChild(g);
  }

  let intensity = 0;
  let hueVal = 0;

  app.ticker.add(() => {
    if (hue) {
      hueVal = (hueVal + 0.02) % 360;
      hue.hue(hueVal, false);
    }
    const speed = 1 + intensity * 2.5;
    for (const p of items) {
      p.y += p.vy * speed;
      p.x += p.vx * speed;
      if (p.y < -5) { p.y = app.screen.height + 5; p.x = Math.random() * app.screen.width; }
      if (p.x < -5) p.x = app.screen.width + 5;
      if (p.x > app.screen.width + 5) p.x = -5;
    }
  });

  return {
    setIntensity(v) { intensity = v; particles.visible = true; },
    resize() {
      gradient.width = app.screen.width;
      gradient.height = app.screen.height;
    },
    destroy() {
      app.ticker.stop();
      app.stage.removeChild(gradient, particles);
    },
  };
}
