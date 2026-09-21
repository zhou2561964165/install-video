import * as PIXI from 'pixi.js';

export function webglSupported() {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl') || c.getContext('experimental-webgl'));
  } catch {
    return false;
  }
}

// 性能分级：'high' 全效果 / 'low' 降档（粒子减半 + 去后处理）/ 'none' 无 WebGL（CSS 兜底）
export function detectTier() {
  if (!webglSupported()) return 'none';
  const nav = navigator;
  const isMobile = /Android|iPhone|iPad|iPod/i.test(nav.userAgent);
  const lowCores = nav.hardwareConcurrency && nav.hardwareConcurrency <= 4;
  const lowMem = nav.deviceMemory && nav.deviceMemory <= 4;
  if (isMobile || lowCores || lowMem) return 'low';
  return 'high';
}

export function initStage(container) {
  const app = new PIXI.Application({
    resizeTo: window,
    backgroundAlpha: 0,      // 背景透明，渐变由 background.js 的 Sprite 提供
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  });
  container.appendChild(app.view);
  app.view.style.position = 'absolute';
  app.view.style.inset = '0';
  app.view.style.pointerEvents = 'none'; // UI 层在上方接收交互
  return app;
}

export function destroyStage(app) {
  app.destroy(true, { children: true, texture: true, baseTexture: true });
}
