import * as PIXI from 'pixi.js';
import { hex, baseColor } from './theme.js';
import { PLACEMENT } from './mascotConfig.js';

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
    backgroundColor: hex(baseColor), // 底色对齐深色底（--ink-900），配合 backgroundAlpha:0 兜底
    backgroundAlpha: 0,      // 背景透明，深色底渐变由 body CSS 提供（透过画布）
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  });
  container.appendChild(app.view);
  app.view.style.position = 'absolute';
  app.view.style.inset = '0';
  app.view.style.pointerEvents = 'auto'; // 角色点击切换需要 canvas 接收事件；UI 层通过 CSS 穿透（.ui pointer-events:none）
  // PIXI 初始化会写 inline touchAction:none；在此按配置恢复原生纵向滚动。
  app.view.style.touchAction = PLACEMENT.touchAction;
  // TouchEvent 被 PIXI 归一化后默认 preventDefault；关闭它让允许的手势交给浏览器。
  app.renderer.plugins.interaction.autoPreventDefault = PLACEMENT.autoPreventDefault;
  return app;
}

export function destroyStage(app) {
  app.destroy(true, { children: true, texture: true, baseTexture: true });
}
