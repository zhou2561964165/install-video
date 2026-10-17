import { describe, expect, it, vi } from 'vitest';
import { Container, Rectangle } from 'pixi.js';
import { registerMascotSilhouette, getMascotSilhouette } from './mascotSilhouette.js';

function setup({ pivot = false, fails = false } = {}) {
  let time = 0;
  const model = new Container(); const stage = new Container(); stage.addChild(model);
  model.getLocalBounds = () => new Rectangle(0, 0, 100, 100);
  model.position.set(50, 30); model.scale.set(2);
  if (pivot) model.pivot.set(50, 50);
  const priorTarget = { label: 'main' }; const frame = new Rectangle(1, 2, 400, 300);
  const textures = [];
  const renderer = {
    renderingToScreen: true, projection: { transform: null },
    renderTexture: { current: priorTarget, sourceFrame: frame, destinationFrame: frame, viewportFrame: frame, bind: vi.fn() },
    generateTexture: vi.fn((object, options) => {
      expect(object.worldTransform.a).toBe(1); expect(object.worldTransform.tx).toBe(0);
      const resolution = options.resolution;
      const texture = { width: 100, height: 100, baseTexture: { resolution }, destroy: vi.fn() };
      textures.push(texture); return texture;
    }),
    extract: { pixels: vi.fn((texture) => {
      if (fails) throw new Error('read failed');
      const w = Math.round(texture.width * texture.baseTexture.resolution);
      const pixels = new Uint8Array(w * w * 4);
      // Only the central 20% is opaque: the large transparent corner stays passable.
      for (let y = w * .4; y < w * .6; y++) for (let x = w * .4; x < w * .6; x++) pixels[(y * w + x) * 4 + 3] = 255;
      return pixels;
    }) },
  };
  const view = { getBoundingClientRect: () => ({ left: 10, top: 20, width: 400, height: 300 }) };
  const app = { renderer, view, screen: { width: 400, height: 300 } };
  const element = document.createElement('div');
  const provider = registerMascotSilhouette(element, { app, model, now: () => time });
  return { model, app, renderer, provider, element, textures, priorTarget, time: (next) => { time = next; } };
}

describe('mascot alpha silhouette', () => {
  it('notifies stationary pointers on a separate bounded clock without pre-sampling', () => {
    const s = setup(); const changed = vi.fn(); s.element.addEventListener('mascot-silhouette-change', changed);
    s.provider.tick();
    for (const time of [1, 50, 100, 149]) { s.time(time); s.provider.tick(); }
    expect(changed).toHaveBeenCalledTimes(1);
    s.time(150); s.provider.tick(); expect(changed).toHaveBeenCalledTimes(2);
    expect(changed.mock.lastCall[0].bubbles).toBe(true);
    expect(s.renderer.generateTexture).not.toHaveBeenCalled(); s.provider.destroy();
  });
  it('coalesces explicit pose invalidations and suppresses stale queued or ticker notifications', async () => {
    const s = setup(); const changed = vi.fn(); s.element.addEventListener('mascot-silhouette-change', changed);
    s.provider.invalidate(); s.provider.invalidate(); s.provider.tick();
    expect(changed).not.toHaveBeenCalled(); await Promise.resolve();
    expect(changed).toHaveBeenCalledTimes(1); expect(s.renderer.generateTexture).not.toHaveBeenCalled();
    const replacement = registerMascotSilhouette(s.element, { app: s.app, model: s.model });
    s.time(1000); s.provider.tick(); s.provider.invalidate(); await Promise.resolve();
    expect(changed).toHaveBeenCalledTimes(1);
    replacement.invalidate(); replacement.destroy(); await Promise.resolve();
    replacement.tick(); expect(changed).toHaveBeenCalledTimes(1); s.provider.destroy();
  });
  it('publishes a provider and does not sample an out of bounds circle', () => {
    const s = setup(); expect(getMascotSilhouette(s.element)).toBe(s.provider);
    expect(s.provider.overlapsCircle(0, 0, 5)).toBe(false);
    expect(s.renderer.generateTexture).not.toHaveBeenCalled(); s.provider.destroy();
  });
  it('keeps transparent corners visible and detects center and circle edge contact with zero margin', () => {
    const s = setup();
    expect(s.provider.overlapsCircle(65, 55, 3)).toBe(false);
    expect(s.provider.overlapsCircle(160, 150, 3)).toBe(true);
    expect(s.provider.overlapsCircle(135, 150, 5)).toBe(true);
    expect(s.provider.overlapsCircle(134.9, 150, 5)).toBe(false);
    expect(s.renderer.generateTexture).toHaveBeenCalledTimes(1); s.provider.destroy();
  });
  it('maps offset, pivot, scale and canvas CSS coordinates', () => {
    const s = setup({ pivot: true });
    s.app.view.getBoundingClientRect = () => ({ left: 100, top: 200, width: 800, height: 600 });
    expect(s.provider.overlapsCircle(200, 260, 3)).toBe(true);
    expect(s.provider.overlapsCircle(50, 110, 3)).toBe(false); s.provider.destroy();
  });
  it('reuses alpha after translation, refreshes on expiry and explicit invalidation', () => {
    const s = setup(); s.provider.overlapsCircle(160, 150, 2);
    s.model.x += 20; expect(s.provider.overlapsCircle(180, 150, 2)).toBe(true);
    expect(s.renderer.generateTexture).toHaveBeenCalledTimes(1);
    s.time(151); s.provider.overlapsCircle(180, 150, 2);
    expect(s.renderer.generateTexture).toHaveBeenCalledTimes(2);
    s.provider.invalidate(); s.provider.overlapsCircle(180, 150, 2);
    expect(s.renderer.generateTexture).toHaveBeenCalledTimes(3); s.provider.destroy();
  });
  it('maps a rotated and nonuniformly scaled pixel silhouette without a bbox approximation', () => {
    const s = setup({ pivot: true }); s.model.rotation = Math.PI / 4; s.model.scale.set(2, 1);
    expect(s.provider.overlapsCircle(60, 50, 1)).toBe(true);
    expect(s.provider.overlapsCircle(60, 100, 1)).toBe(false); s.provider.destroy();
  });
  it('refreshes on scale changes and caps huge model bounds at 256 rather than reading its atlas', () => {
    const s = setup(); s.provider.overlapsCircle(160, 150, 1);
    s.model.scale.set(0.5); s.provider.overlapsCircle(85, 75, 1);
    expect(s.renderer.generateTexture).toHaveBeenCalledTimes(2);
    const large = new Rectangle(0, 0, 16000, 16000); s.model.getLocalBounds = () => large;
    s.model.scale.set(0.01); s.provider.overlapsCircle(140, 130, 1);
    const options = s.renderer.generateTexture.mock.lastCall[1];
    expect(options.resolution * large.width).toBeLessThanOrEqual(256);
    expect(options.resolution * large.width).toBeLessThanOrEqual(160); s.provider.destroy();
  });
  it('keeps a replacement registry owner when an old provider is destroyed', () => {
    const s = setup(); const replacement = registerMascotSilhouette(s.element, { app: s.app, model: s.model });
    s.provider.destroy(); expect(getMascotSilhouette(s.element)).toBe(replacement);
    replacement.destroy(); expect(getMascotSilhouette(s.element)).toBeUndefined();
  });
  it('restores transform and renderer target and always destroys temporary textures', () => {
    const s = setup(); s.provider.overlapsCircle(160, 150, 2);
    expect(s.model.worldTransform.a).toBe(2); expect(s.model.worldTransform.tx).toBe(50);
    expect(s.renderer.renderTexture.bind).toHaveBeenLastCalledWith(s.priorTarget, expect.any(Rectangle), expect.any(Rectangle));
    expect(s.textures[0].destroy).toHaveBeenCalledWith(true);
    s.provider.destroy(); expect(getMascotSilhouette(s.element)).toBeUndefined();
    expect(s.provider.overlapsCircle(160, 150, 2)).toBe(false);
  });
  it('fails open without bbox hiding, restores state, releases textures, and throttles retry', () => {
    const s = setup({ fails: true });
    expect(s.provider.overlapsCircle(160, 150, 2)).toBe(false);
    expect(s.provider.overlapsCircle(160, 150, 2)).toBe(false);
    expect(s.renderer.extract.pixels).toHaveBeenCalledTimes(1);
    expect(s.textures[0].destroy).toHaveBeenCalledWith(true);
    expect(s.model.worldTransform.a).toBe(2); s.provider.destroy();
  });
});
