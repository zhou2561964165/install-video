import * as PIXI from 'pixi.js';

export function webglSupported() {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl') || c.getContext('experimental-webgl'));
  } catch {
    return false;
  }
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
