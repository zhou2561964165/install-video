import * as PIXI from 'pixi.js';
import { SCENE } from '../state/sceneMachine.js';
import { palette, hex, rgb } from './theme.js';

// 场景强度仍由 App 按 scene 注入；解析/下载只轻微提速，不切换成另一套强装饰。
export function intensityForScene(scene) {
  switch (scene) {
    case SCENE.PARSING:
    case SCENE.DOWNLOADING:
      return 1;
    default:
      return 0;
  }
}

// 背景只保留柔和折射光斑与少量光尘。参数集中，避免视觉值散落在更新逻辑中。
const FX = {
  spots: {
    count: 5,
    alpha: 0.14,
    textureSize: 128,
    size: { min: 76, max: 128 },
    drift: { min: 0.08, max: 0.16 },
    swayRate: 0.0035,
    swayAmplitude: { min: 12, max: 26 },
    speed: { min: 0.75, max: 1.25 },
    activeBoost: 0.15,
    edgePadding: 24,
  },
  dust: {
    count: 6,
    radius: { min: 0.45, max: 0.9 },
    alpha: 0.11,
    drift: 0.025,
    rise: { min: 0.035, max: 0.075 },
    activeBoost: 0.2,
    edgePadding: 5,
  },
  lowTierMinimumCount: 4,
};

// 低档保留少量装饰；光斑和光尘都遵循同一个像素预算。
const countFor = (count, low) => (low ? Math.max(FX.lowTierMinimumCount, Math.round(count / 2)) : count);
const rand = (min, max) => min + Math.random() * (max - min);

// 柔和径向光晕纹理：中心低 alpha，边缘透明。颜色来自 CSS 主题 token。
function makeGlowTexture(size, colorNum, alpha) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const half = size / 2;
  const gradient = ctx.createRadialGradient(half, half, 0, half, half, half);
  const color = rgb(colorNum);
  gradient.addColorStop(0, `rgba(${color},${alpha})`);
  gradient.addColorStop(1, `rgba(${color},0)`);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  return PIXI.Texture.from(canvas);
}

function createSpots(root, size, low) {
  const container = new PIXI.Container();
  const colors = [
    palette.refractCyan,
    palette.refractViolet,
    palette.refractPink,
    palette.refractMint,
    palette.refractWarm,
  ];
  const textures = new Map();
  const spots = [];

  for (let i = 0; i < countFor(FX.spots.count, low); i++) {
    const color = hex(colors[i % colors.length]);
    if (!textures.has(color)) textures.set(color, makeGlowTexture(FX.spots.textureSize, color, FX.spots.alpha));
    const spot = new PIXI.Sprite(textures.get(color));
    spot.anchor.set(0.5);
    spot.diameter = rand(FX.spots.size.min, FX.spots.size.max);
    spot.width = spot.height = spot.diameter;
    spot.u = rand(0, 1);
    spot.v = rand(0, 1);
    spot.baseX = spot.u * size.w;
    spot.x = spot.baseX;
    spot.y = spot.v * size.h;
    spot.phase = rand(0, Math.PI * 2);
    spot.swayAmplitude = rand(FX.spots.swayAmplitude.min, FX.spots.swayAmplitude.max);
    spot.drift = rand(FX.spots.drift.min, FX.spots.drift.max);
    spot.speed = rand(FX.spots.speed.min, FX.spots.speed.max);
    spots.push(spot);
    container.addChild(spot);
  }

  root.addChild(container);
  return {
    update(delta, intensity) {
      for (const spot of spots) {
        const speed = spot.speed * (1 + intensity * FX.spots.activeBoost);
        spot.phase += FX.spots.swayRate * speed * delta;
        spot.y -= spot.drift * speed * delta;
        spot.x = spot.baseX + Math.sin(spot.phase) * spot.swayAmplitude;
        if (spot.y < -spot.diameter / 2 - FX.spots.edgePadding) {
          spot.v = 1 + (spot.diameter / 2 + FX.spots.edgePadding) / size.h;
          spot.y = spot.v * size.h;
          spot.u = rand(0, 1);
          spot.baseX = spot.u * size.w;
        }
        spot.v = spot.y / size.h;
      }
    },
    resize() {
      for (const spot of spots) {
        spot.baseX = spot.u * size.w;
        spot.x = spot.baseX + Math.sin(spot.phase) * spot.swayAmplitude;
        spot.y = spot.v * size.h;
      }
    },
  };
}

function createDust(root, size, low) {
  const container = new PIXI.Container();
  const colors = [palette.refractCyan, palette.refractViolet, palette.refractPink];
  const dust = [];

  for (let i = 0; i < countFor(FX.dust.count, low); i++) {
    const particle = new PIXI.Graphics();
    const radius = rand(FX.dust.radius.min, FX.dust.radius.max);
    particle.beginFill(hex(colors[i % colors.length]), FX.dust.alpha);
    particle.drawCircle(0, 0, radius);
    particle.endFill();
    particle.u = rand(0, 1);
    particle.v = rand(0, 1);
    particle.x = particle.u * size.w;
    particle.y = particle.v * size.h;
    particle.vx = rand(-FX.dust.drift, FX.dust.drift);
    particle.vy = -rand(FX.dust.rise.min, FX.dust.rise.max);
    dust.push(particle);
    container.addChild(particle);
  }

  root.addChild(container);
  return {
    update(delta, intensity) {
      const speed = 1 + intensity * FX.dust.activeBoost;
      for (const particle of dust) {
        particle.x += particle.vx * delta * speed;
        particle.y += particle.vy * delta * speed;
        if (particle.y < -FX.dust.edgePadding) {
          particle.v = 1 + FX.dust.edgePadding / size.h;
          particle.y = particle.v * size.h;
          particle.u = rand(0, 1);
          particle.x = particle.u * size.w;
        }
        if (particle.x < -FX.dust.edgePadding) particle.x = size.w + FX.dust.edgePadding;
        else if (particle.x > size.w + FX.dust.edgePadding) particle.x = -FX.dust.edgePadding;
        particle.u = particle.x / size.w;
        particle.v = particle.y / size.h;
      }
    },
    resize() {
      for (const particle of dust) {
        particle.x = particle.u * size.w;
        particle.y = particle.v * size.h;
      }
    },
  };
}

// 同一背景回调在页面可见时挂到 PIXI ticker；隐藏时摘除，销毁时清理监听和回调。
export function registerBackgroundTicker(app, tick, page = typeof document === 'undefined' ? null : document) {
  let attached = false;
  let disposed = false;
  const syncVisibility = () => {
    const shouldRun = !disposed && (!page || !page.hidden);
    if (shouldRun && !attached) {
      app.ticker.add(tick);
      attached = true;
    } else if (!shouldRun && attached) {
      app.ticker.remove(tick);
      attached = false;
    }
  };

  page?.addEventListener?.('visibilitychange', syncVisibility);
  syncVisibility();

  return () => {
    if (disposed) return;
    disposed = true;
    page?.removeEventListener?.('visibilitychange', syncVisibility);
    if (attached) app.ticker.remove(tick);
    attached = false;
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

  // 网格点由 CSS 负责；PIXI 只渲染少量虹彩光斑和光尘，避免背景形成灰雾。
  const layers = [createSpots(root, size, low), createDust(root, size, low)];
  let intensity = 0;
  let cleanupTicker = null;
  let destroyed = false;

  if (!reduceMotion) {
    const tick = (delta) => {
      for (const layer of layers) layer.update(delta, intensity);
    };
    cleanupTicker = registerBackgroundTicker(app, tick);
  }

  return {
    setIntensity(value) { intensity = value; },
    resize() {
      size.w = app.screen.width;
      size.h = app.screen.height;
      for (const layer of layers) layer.resize();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      cleanupTicker?.();
      app.stage.removeChild(root);
      root.destroy({ children: true, texture: true, baseTexture: true });
    },
  };
}
