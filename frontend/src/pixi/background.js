import * as PIXI from 'pixi.js';
import { SCENE } from '../state/sceneMachine.js';
import { palette, hex, rgb } from './theme.js';

// 场景 → 强度档：安静 0 / 活跃 1（spec §6）
// 仅 PARSING / DOWNLOADING 激活粒子旋流等「活跃」效果。
export function intensityForScene(scene) {
  switch (scene) {
    case SCENE.PARSING:
    case SCENE.DOWNLOADING:
      return 1;
    default:
      return 0;
  }
}

// —— 背景效果参数（数据驱动，收敛散落的魔法数；H-2）——
// 每个图层一个配置块；调整数量/速度/大小只需改这里，不改渲染逻辑。
// 参考 shiroki 克制度：数量/透明度整体下调，背景更干净。
const FX = {
  aurora: { count: 3, alpha: 0.22, drift: 0.2, size: 1.5 },
  light: { count: 2, alpha: 0.2, drift: 0.12, size: 1.4 },
  stars: { count: 70, rMax: 1.8, alpha: 0.7, twinkle: 0.02 },
  dust: { count: 40, rMax: 1.4, alpha: 0.4, drift: 0.1 },
  spots: { count: 10, size: 16, drift: 0.3, sway: 0.008, alpha: 0.5 },
  bubbles: { count: 12, rMax: 6, rise: 0.35, sway: 0.012 },
  swirl: { count: 70, rMax: 2.6, orbit: 0.02, converge: 0.006 },
};

// 低档减量：粒子数减半（保底 4 个）
const countFor = (n, low) => (low ? Math.max(4, Math.round(n / 2)) : n);

const rand = (min, max) => min + Math.random() * (max - min);

// 柔和径向光晕纹理：中心 rgb 实心 → 边缘全透明（供极光/光斑用）
function makeGlowTexture(size, colorNum, alpha) {
  const s = Math.max(2, Math.floor(size));
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = s;
  const ctx = canvas.getContext('2d');
  const half = s / 2;
  const g = ctx.createRadialGradient(half, half, 0, half, half, half);
  const c = rgb(colorNum);
  g.addColorStop(0, `rgba(${c},${alpha})`);
  g.addColorStop(1, `rgba(${c},0)`);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, s, s);
  return PIXI.Texture.from(canvas);
}

// 极光带：大块柔和紫罗兰光晕，缓慢漂移（普通混合，浅/深底皆可）
function createAurora(root, size, low) {
  const c = new PIXI.Container();
  const colors = [palette.accent, palette.accentSoft, palette.accentLilac, palette.accentHover];
  const sprites = [];
  const n = countFor(FX.aurora.count, low);
  for (let i = 0; i < n; i++) {
    const color = colors[i % colors.length];
    const s = new PIXI.Sprite(makeGlowTexture(512, hex(color), FX.aurora.alpha));
    s.anchor.set(0.5);
    s.factor = FX.aurora.size * rand(0.8, 1.2);
    s.width = size.w * s.factor;
    s.x = rand(0, size.w);
    s.y = rand(0, size.h);
    s.vx = rand(-1, 1) * FX.aurora.drift;
    s.vy = rand(-1, 1) * FX.aurora.drift;
    s.vr = rand(-1, 1) * 0.0004;
    sprites.push(s);
    c.addChild(s);
  }
  root.addChild(c);
  return {
    update(delta) {
      for (const s of sprites) {
        s.x += s.vx * delta;
        s.y += s.vy * delta;
        s.rotation += s.vr * delta;
        const hw = s.width / 2;
        if (s.x < -hw) s.x = size.w + hw;
        else if (s.x > size.w + hw) s.x = -hw;
        if (s.y < -hw) s.y = size.h + hw;
        else if (s.y > size.h + hw) s.y = -hw;
      }
    },
    resize() {
      for (const s of sprites) s.width = size.w * s.factor;
    },
  };
}

// 光斑：更柔和、更慢漂移的紫罗兰光晕（普通混合）
function createLight(root, size, low) {
  const c = new PIXI.Container();
  const colors = [palette.accentLilac, palette.accentSoft];
  const spots = [];
  const n = countFor(FX.light.count, low);
  for (let i = 0; i < n; i++) {
    const s = new PIXI.Sprite(makeGlowTexture(512, hex(colors[i % colors.length]), FX.light.alpha));
    s.anchor.set(0.5);
    s.factor = FX.light.size * rand(0.8, 1.2);
    s.width = size.w * s.factor;
    s.x = rand(0, size.w);
    s.y = rand(0, size.h);
    s.vx = rand(-1, 1) * FX.light.drift;
    s.vy = rand(-1, 1) * FX.light.drift;
    spots.push(s);
    c.addChild(s);
  }
  root.addChild(c);
  return {
    update(delta) {
      for (const s of spots) {
        s.x += s.vx * delta;
        s.y += s.vy * delta;
        const hw = s.width / 2;
        if (s.x < -hw) s.x = size.w + hw;
        else if (s.x > size.w + hw) s.x = -hw;
        if (s.y < -hw) s.y = size.h + hw;
        else if (s.y > size.h + hw) s.y = -hw;
      }
    },
    resize() {
      for (const s of spots) s.width = size.w * s.factor;
    },
  };
}

// 星星：静态分布 + 轻微闪烁（呼吸），淡紫微光
function createStars(root, size, low) {
  const c = new PIXI.Container();
  const stars = [];
  const n = countFor(FX.stars.count, low);
  for (let i = 0; i < n; i++) {
    const s = new PIXI.Graphics();
    const r = rand(0.5, FX.stars.rMax);
    s.beginFill(hex(palette.accentLilac), 1);
    s.drawCircle(0, 0, r);
    s.endFill();
    s.x = rand(0, size.w);
    s.y = rand(0, size.h);
    s.baseAlpha = rand(0.2, 1) * FX.stars.alpha;
    s.phase = rand(0, Math.PI * 2);
    s.speed = rand(0.5, 1.5);
    stars.push(s);
    c.addChild(s);
  }
  root.addChild(c);
  return {
    update(delta) {
      for (const s of stars) {
        s.phase += FX.stars.twinkle * s.speed * delta;
        s.alpha = s.baseAlpha * (0.5 + 0.5 * Math.sin(s.phase));
      }
    },
    resize() {},
  };
}

// 光尘：上浮的细小紫罗兰粒子（活跃态加速）
function createDust(root, size, low) {
  const c = new PIXI.Container();
  const colors = [palette.accentLilac, palette.accentSoft, palette.accentPink];
  const dust = [];
  const n = countFor(FX.dust.count, low);
  for (let i = 0; i < n; i++) {
    const d = new PIXI.Graphics();
    const r = rand(0.4, FX.dust.rMax);
    d.beginFill(hex(colors[i % colors.length]), FX.dust.alpha);
    d.drawCircle(0, 0, r);
    d.endFill();
    d.x = rand(0, size.w);
    d.y = rand(0, size.h);
    d.vx = rand(-1, 1) * FX.dust.drift;
    d.vy = -rand(0.1, 0.4);
    dust.push(d);
    c.addChild(d);
  }
  root.addChild(c);
  return {
    update(delta, intensity) {
      const speed = 1 + intensity * 2;
      for (const d of dust) {
        d.y += d.vy * delta * speed;
        d.x += d.vx * delta * speed;
        if (d.y < -5) { d.y = size.h + 5; d.x = rand(0, size.w); }
        if (d.x < -5) d.x = size.w + 5;
        else if (d.x > size.w + 5) d.x = -5;
      }
    },
    resize() {},
  };
}

// 折射光点：五色折射彩虹的柔和光晕，缓慢上浮 + 左右摇曳（替代樱花花瓣）
function createSpots(root, size, low) {
  const c = new PIXI.Container();
  const colors = [palette.refractCyan, palette.refractViolet, palette.refractPink, palette.refractMint, palette.refractWarm];
  const spots = [];
  const n = countFor(FX.spots.count, low);
  for (let i = 0; i < n; i++) {
    const s = new PIXI.Sprite(makeGlowTexture(128, hex(colors[i % colors.length]), FX.spots.alpha));
    s.anchor.set(0.5);
    const sc = FX.spots.size * rand(0.6, 1.4);
    s.width = sc;
    s.height = sc;
    s.baseX = rand(0, size.w);
    s.x = s.baseX;
    s.y = rand(0, size.h);
    s.phase = rand(0, Math.PI * 2);
    s.swayAmp = rand(8, 22);
    s.drift = FX.spots.drift * rand(0.5, 1.5);
    spots.push(s);
    c.addChild(s);
  }
  root.addChild(c);
  return {
    update(delta, intensity) {
      const speed = 1 + intensity * 0.6;
      for (const s of spots) {
        s.phase += FX.spots.sway * delta * speed;
        s.y -= s.drift * delta * speed;
        s.x = s.baseX + Math.sin(s.phase) * s.swayAmp;
        if (s.y < -20) { s.y = size.h + 20; s.baseX = rand(0, size.w); }
      }
    },
    resize() {},
  };
}

// 气泡：上浮 + 摇曳 + 高光点
function createBubbles(root, size, low) {
  const c = new PIXI.Container();
  const bubbles = [];
  const n = countFor(FX.bubbles.count, low);
  for (let i = 0; i < n; i++) {
    const b = new PIXI.Graphics();
    const r = rand(2, FX.bubbles.rMax);
    b.lineStyle(1, hex(palette.accentLilac), 0.5);
    b.beginFill(0xffffff, 0.05);
    b.drawCircle(0, 0, r);
    b.endFill();
    b.beginFill(0xffffff, 0.35);
    b.drawCircle(-r * 0.3, -r * 0.35, r * 0.25);
    b.endFill();
    b.baseX = rand(0, size.w);
    b.x = b.baseX;
    b.y = rand(0, size.h);
    b.rise = FX.bubbles.rise * rand(0.5, 1.5);
    b.swayAmp = rand(10, 30);
    b.phase = rand(0, Math.PI * 2);
    b.alpha = rand(0.3, 0.7);
    bubbles.push(b);
    c.addChild(b);
  }
  root.addChild(c);
  return {
    update(delta, intensity) {
      const speed = 1 + intensity * 1.2;
      for (const b of bubbles) {
        b.phase += FX.bubbles.sway * delta * speed;
        b.y -= b.rise * delta * speed;
        b.x = b.baseX + Math.sin(b.phase) * b.swayAmp;
        if (b.y < -20) { b.y = size.h + 20; b.baseX = rand(0, size.w); }
      }
    },
    resize() {},
  };
}

// 粒子旋流：活跃态向中心螺旋汇聚（安静态隐没）
function createSwirl(root, size, low) {
  const c = new PIXI.Container();
  const colors = [palette.accent, palette.accentSoft, palette.accentLilac, palette.accentHover];
  const parts = [];
  const n = countFor(FX.swirl.count, low);
  for (let i = 0; i < n; i++) {
    const p = new PIXI.Graphics();
    const r = rand(0.6, FX.swirl.rMax);
    p.beginFill(hex(colors[i % colors.length]), 0.7);
    p.drawCircle(0, 0, r);
    p.endFill();
    p.angle = rand(0, Math.PI * 2);
    p.radius = rand(0, 1) * Math.max(size.w, size.h) * 0.7;
    p.alpha = 0;
    p.cx = size.w * 0.5; // 汇聚目标：默认屏幕中心（可扩展为角色位置）
    p.cy = size.h * 0.5;
    p.x = p.cx + Math.cos(p.angle) * p.radius;
    p.y = p.cy + Math.sin(p.angle) * p.radius;
    parts.push(p);
    c.addChild(p);
  }
  root.addChild(c);
  return {
    update(delta, intensity) {
      for (const p of parts) {
        if (intensity >= 1) {
          p.alpha = Math.min(1, p.alpha + 0.04 * delta);
          p.angle += FX.swirl.orbit * delta;
          p.radius = Math.max(6, p.radius - FX.swirl.converge * p.radius * delta);
          if (p.radius <= 6) {
            p.radius = Math.max(size.w, size.h) * 0.7;
            p.angle = rand(0, Math.PI * 2);
          }
        } else {
          p.alpha = Math.max(0, p.alpha - 0.03 * delta);
        }
        p.x = p.cx + Math.cos(p.angle) * p.radius;
        p.y = p.cy + Math.sin(p.angle) * p.radius;
      }
    },
    resize() {
      for (const p of parts) { p.cx = size.w * 0.5; p.cy = size.h * 0.5; }
    },
  };
}

function prefersReducedMotion() {
  try {
    return typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {
    return false;
  }
}

export function createBackground(app, tier = 'high') {
  const low = tier === 'low';
  const reduceMotion = prefersReducedMotion();
  const size = { w: app.screen.width, h: app.screen.height };
  const root = new PIXI.Container();
  app.stage.addChild(root);

  const layers = [
    createAurora(root, size, low),
    createLight(root, size, low),
    createStars(root, size, low),
    createDust(root, size, low),
    createSpots(root, size, low),
    createBubbles(root, size, low),
    createSwirl(root, size, low),
  ];

  let intensity = 0;
  let tick = null;

  // prefers-reduced-motion：完全静止，只保留静态分层背景（不逐帧驱动）
  if (!reduceMotion) {
    tick = (delta) => {
      for (const layer of layers) layer.update(delta, intensity);
    };
    app.ticker.add(tick);
  }

  return {
    setIntensity(v) { intensity = v; },
    resize() {
      size.w = app.screen.width;
      size.h = app.screen.height;
      for (const layer of layers) layer.resize();
    },
    destroy() {
      if (tick) app.ticker.remove(tick);
      app.stage.removeChild(root);
    },
  };
}
