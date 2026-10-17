import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Container, Point, Rectangle, Ticker, InteractionManager, Sprite, Texture, utils } from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display/cubism4';
import { createMascot as createActualMascot } from './mascot.js';
import { getMascotSilhouette } from './mascotSilhouette.js';

// 默认视口手动定位，原生动作与参数待机持续；embedded保留显式兼容回归。
const createMascot = createActualMascot;

// Loading a Cubism model requires external assets and WebGL. Keep PIXI's real
// transforms, event emitter and stage; replace only that external loading boundary.
vi.mock('pixi-live2d-display/cubism4', () => ({
  Live2DModel: { registerTicker: vi.fn(), from: vi.fn(), fromSync: vi.fn() },
  MotionPriority: { IDLE: 1 },
}));

let handles;
let tickers;
let surfaces;

beforeEach(() => {
  handles = [];
  tickers = [];
  surfaces = [];
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
});

afterEach(() => {
  handles.forEach((mascot) => mascot.destroy());
  tickers.forEach((ticker) => ticker.destroy());
  surfaces.forEach((surface) => surface.remove());
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.documentElement.style.removeProperty('--mascot-load-timeout');
  vi.useRealTimers();
});

async function setup({ width = 1440, height = 900, region, embedded = false, liveBounds = false, core = false } = {}) {
  const model = new Container();
  model.anchor = liveBounds ? { set: (x, y) => model.pivot.set(x * 1400, y * 2000) } : new Point();
  model.getLocalBounds = () => liveBounds ? new Rectangle(0, 0, 1400, 2000) : new Rectangle(-700, -1000, 1400, 2000);
  if (core) model.internalModel = { coreModel: { getParameterCount: () => 1, getParameterIndex: () => 0, setParameterValueById: vi.fn() } };
  mockModelLoad(model);
  const screen = { width, height };
  const view = document.createElement('canvas');
  view.getBoundingClientRect = () => ({ left: 0, top: 0, width: screen.width, height: screen.height });
  const ticker = new Ticker();
  tickers.push(ticker);
  const app = {
    screen, view, ticker, stage: new Container(),
    renderer: { gl: { MAX_TEXTURE_SIZE: 0x0d33, getParameter: () => 16384 } },
  };
  let currentRegion = region;
  const onTap = vi.fn();
  const interactionTarget = document.createElement('div');
  document.body.append(view, interactionTarget);
  surfaces.push(view, interactionTarget);
  const mascot = await createMascot(app, 'bai', { onTap, interactionTarget, getRegion: () => currentRegion, ...(embedded && { placementMode: 'embedded' }) });
  handles.push(mascot);
  return { app, model, mascot, onTap, interactionTarget, setRegion: (next) => { currentRegion = next; } };
}

function motionPreferences(reduce = false) {
  const queries = new Map();
  vi.stubGlobal('matchMedia', (query) => {
    if (!queries.has(query)) {
      const media = new EventTarget();
      media.matches = query.includes('reduced-motion') && reduce;
      queries.set(query, media);
    }
    return queries.get(query);
  });
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  return (query, matches) => {
    const media = [...queries].find(([key]) => key.includes(query))?.[1] ?? window.matchMedia(query);
    media.matches = matches; media.dispatchEvent(new Event('change'));
  };
}
function advance(app, ticks = 1) {
  for (let i = 0; i < ticks; i += 1) {
    app.testTime = (app.testTime ?? performance.now()) + 100;
    app.ticker.update(app.testTime);
  }
}

function loadingScene() {
  const screen = { width: 1440, height: 900 };
  const view = document.createElement('canvas');
  view.getBoundingClientRect = () => ({ left: 0, top: 0, ...screen });
  const ticker = new Ticker(); tickers.push(ticker);
  const app = { screen, view, ticker, stage: new Container(), renderer: { gl: { MAX_TEXTURE_SIZE: 0x0d33, getParameter: () => 16384 } } };
  const interactionTarget = document.createElement('div');
  document.body.append(view, interactionTarget); surfaces.push(view, interactionTarget);
  return { app, interactionTarget };
}
function fallbackSprite(valid = true) {
  const sprite = new Container(); sprite.anchor = new Point();
  sprite.getLocalBounds = () => new Rectangle(-700, -1000, 1400, 2000);
  const texture = new Container(); texture.valid = valid;
  sprite.texture = { baseTexture: texture };
  vi.spyOn(Sprite, 'from').mockReturnValue(sprite);
  return { sprite, texture };
}
async function flushLoad() { for (let i = 0; i < 8; i += 1) await Promise.resolve(); }
function mockModelLoad(model, error) {
  model.internalModel ??= { destroy() {} };
  const destroy = model.destroy.bind(model);
  model.destroy = (options) => {
    if (options?.texture) model.textures?.forEach((texture) => texture.destroy?.(options.baseTexture));
    model.internalModel?.destroy?.();
    destroy(options);
  };
  Live2DModel.fromSync.mockImplementationOnce((url, options) => {
    queueMicrotask(() => { if (error) options.onError(error); else options.onLoad(); });
    return model;
  });
}

describe('bounded mascot loading', () => {
  it('publishes the model alpha provider only during the mascot lifetime', async () => {
    const { interactionTarget, mascot } = await setup();
    expect(getMascotSilhouette(interactionTarget)?.overlapsCircle).toBeTypeOf('function');
    mascot.destroy(); expect(getMascotSilhouette(interactionTarget)).toBeUndefined();
  });
  it.each(['abort', 'stage disposal'])('releases a loaded model when %s lands between the two async continuations', async (action) => {
    const { app, interactionTarget } = loadingScene(); const controller = new AbortController();
    const { sprite: model } = fallbackSprite();
    const texture = Texture.fromBuffer(new Uint8Array(4), 1, 1); model.textures = [texture];
    const base = texture.baseTexture;
    let queued = false;
    Object.defineProperty(model, 'autoUpdate', { configurable: true, set() {
      if (!queued) {
        queued = true;
        queueMicrotask(() => { if (action === 'abort') controller.abort(); else app.stage = null; });
      }
    } });
    mockModelLoad(model);
    const handle = await createMascot(app, 'bai', { interactionTarget, signal: controller.signal }); handles.push(handle);
    expect(handle.hasVisual()).toBe(false); expect(model.destroyed).toBe(true); expect(base.destroyed).toBe(true);
  });
  it('fallback safely accepts done/error scenes without Live2D motion methods', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { app, interactionTarget } = loadingScene(); fallbackSprite();
    mockModelLoad(new Container(), new Error('model missing'));
    const handle = await createMascot(app, 'bai', { interactionTarget }); handles.push(handle);
    expect(() => { handle.setStageExpression('done'); handle.setStageExpression('error'); }).not.toThrow();
  });

  it('retains a shared atlas until both overlapping live and fallback owners release it', async () => {
    const texture = Texture.fromBuffer(new Uint8Array(4), 1, 1);
    Texture.addToCache(texture, '/live2d/bai/shared-atlas.png');
    const native = new Container(); native.anchor = new Point(); native.textures = [texture];
    native.getLocalBounds = () => new Rectangle(-700, -1000, 1400, 2000);
    mockModelLoad(native);
    const first = loadingScene();
    const live = await createMascot(first.app, 'bai', { interactionTarget: first.interactionTarget }); handles.push(live);
    const fallback = fallbackSprite().sprite; fallback.texture = texture;
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockModelLoad(new Container(), new Error('model unavailable'));
    const second = loadingScene();
    const staticHandle = await createMascot(second.app, 'bai', { interactionTarget: second.interactionTarget }); handles.push(staticHandle);
    const base = texture.baseTexture; const destroy = vi.spyOn(texture, 'destroy');
    live.destroy(); expect(destroy).not.toHaveBeenCalled(); expect(base.destroyed).toBe(false);
    staticHandle.destroy(); expect(destroy).toHaveBeenCalledTimes(1); expect(base.destroyed).toBe(true);
    expect(utils.TextureCache['/live2d/bai/shared-atlas.png']).toBeUndefined();
  });

  it('releases an internal model created after an aborted partial load', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { app, interactionTarget } = loadingScene(); const controller = new AbortController();
    const model = new Container(); model.update = vi.fn(); let onLoad;
    Live2DModel.fromSync.mockImplementationOnce((url, options) => { onLoad = options.onLoad; return model; });
    const pending = createMascot(app, 'bai', { interactionTarget, signal: controller.signal });
    await flushLoad(); controller.abort(); const handle = await pending; handles.push(handle);
    const internal = { destroy: vi.fn() }; model.internalModel = internal;
    model.emit('modelLoaded', internal); onLoad(); await flushLoad();
    expect(internal.destroy).toHaveBeenCalledTimes(1);
  });

  it('releases cached textures on setup failure before the factory assigns textures', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { app, interactionTarget } = loadingScene(); fallbackSprite();
    const model = new Container(); model.textures = [];
    const texture = Texture.fromBuffer(new Uint8Array(4), 1, 1);
    const url = '/live2d/bai/partial-atlas.png'; Texture.addToCache(texture, url);
    const destroyTexture = vi.spyOn(texture, 'destroy');
    Live2DModel.fromSync.mockImplementationOnce((source, options) => {
      queueMicrotask(() => {
        model.emit('settingsLoaded', { textures: ['atlas'], resolveURL: () => url });
        options.onError(new Error('second atlas failed'));
      });
      return model;
    });
    const handle = await createMascot(app, 'bai', { interactionTarget }); handles.push(handle);
    expect(handle.isAvailable()).toBe(false);
    expect(destroyTexture).toHaveBeenCalledOnce(); expect(utils.TextureCache[url]).toBeUndefined();
    expect(model.destroyed).toBe(true);
  });
  it('abort releases a late model without reading the destroyed app', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { app, interactionTarget } = loadingScene();
    const controller = new AbortController(); let resolve;
    const late = new Container(); late.internalModel = { destroy() {} }; const destroy = vi.spyOn(late, 'destroy');
    Live2DModel.fromSync.mockImplementationOnce((url, options) => { resolve = options.onLoad; return late; });
    const pending = createMascot(app, 'bai', { interactionTarget, signal: controller.signal });
    await flushLoad(); controller.abort();
    const handle = await pending; handles.push(handle);
    expect(handle.hasVisual()).toBe(false);
    app.stage = null; app.ticker = null;
    resolve(); await flushLoad();
    expect(destroy).toHaveBeenCalledTimes(1);
    expect(() => { handle.moveBy(1, 1); handle.resetPosition(); handle.setMotionEnabled(true); handle.destroy(); }).not.toThrow();
  });

  it('bounds model waiting, publishes fallback geometry, and destroys a late model', async () => {
    vi.useFakeTimers(); vi.spyOn(console, 'warn').mockImplementation(() => {});
    document.documentElement.style.setProperty('--mascot-load-timeout', '10ms');
    const { app, interactionTarget } = loadingScene(); const { sprite } = fallbackSprite();
    let resolve; const late = new Container();
    Live2DModel.fromSync.mockImplementationOnce((url, options) => { resolve = options.onLoad; return late; });
    const pending = createMascot(app, 'bai', { interactionTarget });
    await flushLoad(); await vi.advanceTimersByTimeAsync(10);
    const handle = await pending; handles.push(handle);
    expect(handle.isAvailable()).toBe(false); expect(handle.hasVisual()).toBe(true);
    expect(app.view.dataset.mascot).toBe('fallback');
    expect(interactionTarget.style.visibility).toBe('visible');
    expect(parseFloat(interactionTarget.style.width)).toBeGreaterThan(0);
    const position = sprite.x; handle.moveBy(-20, 0); expect(sprite.x).toBeLessThan(position);
    handle.resetPosition(); expect(sprite.x).toBe(position);
    resolve(); await flushLoad();
    expect(late.destroyed).toBe(true); expect(app.stage.children).toEqual([sprite]);
    handle.destroy(); expect(interactionTarget.style.visibility).toBe('hidden');
  });

  it.each(['abort', 'timeout'])('cleans fallback texture listeners after %s', async (end) => {
    vi.useFakeTimers(); vi.spyOn(console, 'warn').mockImplementation(() => {});
    document.documentElement.style.setProperty('--mascot-load-timeout', '10ms');
    const { app, interactionTarget } = loadingScene(); const { sprite, texture } = fallbackSprite(false);
    const controller = new AbortController();
    mockModelLoad(new Container(), new Error('missing local model'));
    const pending = createMascot(app, 'bai', { interactionTarget, signal: controller.signal });
    await flushLoad(); expect(texture.listenerCount('loaded')).toBe(1);
    if (end === 'abort') controller.abort(); else await vi.advanceTimersByTimeAsync(10);
    const handle = await pending; handles.push(handle);
    expect(handle.hasVisual()).toBe(false); expect(sprite.destroyed).toBe(true);
    expect(texture.listenerCount('loaded')).toBe(0); expect(texture.listenerCount('error')).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
    texture.emit('loaded'); expect(app.stage.children).toHaveLength(0);
    expect(interactionTarget.style.visibility).toBe('hidden');
  });

  it('destroy is idempotent when abort and owner cleanup both release the live handle', async () => {
    const { app, interactionTarget } = loadingScene(); const { sprite: model } = fallbackSprite();
    const controller = new AbortController(); mockModelLoad(model);
    const handle = await createMascot(app, 'bai', { interactionTarget, signal: controller.signal }); handles.push(handle);
    const destroy = vi.spyOn(model, 'destroy');
    controller.abort(); handle.destroy();
    expect(destroy).toHaveBeenCalledTimes(1); expect(app.ticker.count).toBe(0);
    expect(handle.hasVisual()).toBe(false); expect(handle.isAvailable()).toBe(false);
    expect(interactionTarget.style.visibility).toBe('hidden');
  });

  it('does not expose a stale DOM surface on an unsupported texture device', async () => {
    const { app, interactionTarget } = loadingScene();
    interactionTarget.style.visibility = 'visible';
    app.renderer.gl.getParameter = () => 8192;
    const handle = await createMascot(app, 'bai', { interactionTarget }); handles.push(handle);
    expect(handle.hasVisual()).toBe(false);
    expect(interactionTarget.style.visibility).toBe('hidden');
    expect(app.view.dataset.mascot).toBe('unsupported-texture');
  });
});

describe('viewport motion lifecycle', () => {
  it('keeps stationary circle notifications, native updates and idle running with system preferences and background state', async () => {
    const preference = motionPreferences(); let clock = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => clock);
    const { app, model, mascot, interactionTarget } = await setup({ core: true }); model.update = vi.fn();
    const write = model.internalModel.coreModel.setParameterValueById;
    const position = [model.x, model.y];
    const changed = vi.fn(() => expect(model.update).toHaveBeenCalled());
    interactionTarget.addEventListener('mascot-silhouette-change', changed);
    advance(app); expect(changed).toHaveBeenCalledTimes(1); expect([model.x, model.y]).toEqual(position);
    let calls = 1;
    for (const query of ['reduced-motion', 'forced-colors']) {
      preference(query, true); clock += 200; advance(app); expect(changed).toHaveBeenCalledTimes(++calls);
      preference(query, false); clock += 200; advance(app); expect(changed).toHaveBeenCalledTimes(++calls);
    }
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true); clock += 200; advance(app);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(changed).toHaveBeenCalledTimes(++calls);
    expect(model.update).toHaveBeenCalledTimes(calls);
    expect(write.mock.calls.length).toBeGreaterThanOrEqual(calls);
    expect([model.x, model.y]).toEqual(position);
    mascot.destroy(); clock += 200; advance(app); expect(changed).toHaveBeenCalledTimes(calls);
  });
  it('controls native updates and resumes the latest stage loop once after pause', async () => {
    motionPreferences();
    const { app, interactionTarget } = loadingScene(); const { sprite: model } = fallbackSprite();
    model.update = vi.fn(); model.motion = vi.fn().mockResolvedValue(true);
    model.internalModel = { motionManager: { stopAllMotions: vi.fn() } };
    mockModelLoad(model);
    const handle = await createMascot(app, 'bai', { interactionTarget }); handles.push(handle);
    expect(Live2DModel.fromSync).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ autoUpdate: false, autoInteract: false }));
    handle.startRandomProps(); handle.setStageExpression('done'); advance(app);
    expect(model.update).toHaveBeenCalledTimes(1); expect(model.autoUpdate).toBe(false);
    handle.setMotionEnabled(false); model.update.mockClear(); model.motion.mockClear();
    handle.setStageExpression('error'); advance(app, 3);
    expect(model.update).not.toHaveBeenCalled(); expect(model.motion).not.toHaveBeenCalled();
    handle.setMotionEnabled(true); advance(app, 3);
    expect(model.update).toHaveBeenCalledTimes(3); expect(model.motion).toHaveBeenCalledTimes(1);
  });

  it('stops random prop timers while motion is paused and restarts only when enabled', async () => {
    vi.useFakeTimers(); motionPreferences();
    const { mascot } = await setup({ core: true });
    mascot.startRandomProps(); expect(vi.getTimerCount()).toBe(1);
    mascot.setMotionEnabled(false); expect(vi.getTimerCount()).toBe(0);
    mascot.setMotionEnabled(true); expect(vi.getTimerCount()).toBe(1);
    mascot.destroy(); expect(vi.getTimerCount()).toBe(0);
  });
  it('starts parameter idle even when the system requests reduced motion', async () => {
    const preference = motionPreferences(true);
    const { model, app } = await setup({ core: true });
    advance(app);
    const write = model.internalModel.coreModel.setParameterValueById;
    expect(write).toHaveBeenCalled();
    write.mockClear();
    preference('reduced-motion', false); advance(app);
    expect(write).toHaveBeenCalled();
  });

  it('keeps its position and DOM hit surface fixed through sustained native and parameter idle updates', async () => {
    motionPreferences();
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const { app, model, interactionTarget } = await setup({ liveBounds: true, core: true });
    model.update = vi.fn();
    const write = model.internalModel.coreModel.setParameterValueById;
    const start = [model.x, model.y];
    const bounds = interactionTarget.style.cssText;
    advance(app, 150);
    expect([model.x, model.y]).toEqual(start);
    expect(interactionTarget.style.cssText).toBe(bounds);
    expect(model.update).toHaveBeenCalledTimes(150);
    expect(write.mock.calls.length).toBeGreaterThanOrEqual(150);
    expect(parseFloat(interactionTarget.style.left)).toBeCloseTo(model.x - 700 * model.scale.x);
  });

  it('keeps native and parameter idle running at a fixed position while the pointer rests over the model', async () => {
    motionPreferences();
    const { app, model, interactionTarget } = await setup({ core: true });
    model.update = vi.fn();
    const write = model.internalModel.coreModel.setParameterValueById;
    const before = [model.x, model.y];
    interactionTarget.dispatchEvent(new Event('pointerenter'));
    advance(app, 3);
    expect([model.x, model.y]).toEqual(before);
    expect(model.update).toHaveBeenCalledTimes(3);
    expect(write.mock.calls.length).toBeGreaterThanOrEqual(3);
    interactionTarget.dispatchEvent(new Event('pointerleave'));
    advance(app);
    expect([model.x, model.y]).toEqual(before);
    expect(model.update).toHaveBeenCalledTimes(4);
  });

  it('keeps native idle and random props running during focus and drag and after focus restoration', async () => {
    vi.useFakeTimers(); motionPreferences();
    const { app, model, mascot, interactionTarget } = await setup({ core: true });
    model.update = vi.fn();
    const write = model.internalModel.coreModel.setParameterValueById;
    mascot.startRandomProps();
    interactionTarget.dispatchEvent(new Event('focusin'));
    down(model); advance(app, 3);
    expect(model.update).toHaveBeenCalledTimes(3);
    expect(write.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(vi.getTimerCount()).toBe(1);
    pointer('pointermove', 350, 400);
    pointer('pointerup', 350, 400);
    advance(app, 3);
    expect(model.update).toHaveBeenCalledTimes(6);
    // The menu can return focus to the interaction surface without a focusout.
    interactionTarget.dispatchEvent(new Event('focusin')); advance(app, 3);
    expect(model.update).toHaveBeenCalledTimes(9);
    interactionTarget.dispatchEvent(new Event('focusout')); advance(app, 3);
    expect(model.update).toHaveBeenCalledTimes(12);
    expect([model.x, model.y]).toEqual([350, 400]);
    expect(write.mock.calls.length).toBeGreaterThanOrEqual(12);
    expect(vi.getTimerCount()).toBe(1);
    mascot.destroy(); expect(vi.getTimerCount()).toBe(0);
  });

  it('supports the explicit motion compatibility API and removes ticker work on destroy', async () => {
    motionPreferences();
    const { app, model, mascot } = await setup({ core: true });
    model.update = vi.fn();
    const write = model.internalModel.coreModel.setParameterValueById;
    const assertPaused = () => {
      model.update.mockClear(); write.mockClear(); advance(app, 3);
      expect(model.update).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled();
    };
    const assertResumed = () => {
      advance(app, 3); expect(model.update).toHaveBeenCalledTimes(3);
      expect(write.mock.calls.length).toBeGreaterThanOrEqual(3);
    };
    mascot.setMotionEnabled(false);
    assertPaused();
    const position = [model.x, model.y];
    mascot.moveBy(-10, -10);
    expect([model.x, model.y]).not.toEqual(position);
    mascot.setMotionEnabled(true); assertResumed();
    mascot.destroy(); assertPaused();
    expect(app.ticker.count).toBe(0);
    document.dispatchEvent(new Event('visibilitychange')); advance(app);
    expect(model.update).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled();
  });

  it('keeps stationary bounds and does not rewrite identical DOM bounds on resize', async () => {
    motionPreferences();
    const { app, model, mascot, interactionTarget } = await setup();
    const position = [model.x, model.y]; advance(app, 10);
    expect([model.x, model.y]).toEqual(position);
    const changed = vi.fn(); const observer = new MutationObserver(changed);
    observer.observe(interactionTarget, { attributes: true, attributeFilter: ['style'] });
    mascot.resize(); await Promise.resolve();
    expect(changed).not.toHaveBeenCalled(); observer.disconnect();
    mascot.destroy(); expect(app.ticker.count).toBe(0);
  });
});

function pointer(type, x, y, pointerType = 'mouse', pointerId = 1) {
  const event = new MouseEvent(type, { clientX: x, clientY: y });
  Object.defineProperty(event, 'pointerType', { value: pointerType });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  window.dispatchEvent(event);
}

function down(model, pointerType = 'mouse', pointerId = 1) {
  model.emit('pointerdown', {
    data: { global: new Point(model.x, model.y), originalEvent: { pointerType, pointerId } },
  });
}

function drag(model, x, y, pointerType = 'mouse') {
  down(model, pointerType);
  pointer('pointermove', x, y, pointerType);
  pointer('pointerup', x, y, pointerType);
}

function touchStart(view, touches) {
  const event = new Event('touchstart', { cancelable: true, bubbles: true });
  Object.defineProperty(event, 'touches', { value: touches });
  view.dispatchEvent(event);
  return event;
}

function nativeDown(target, model, pointerId, pointerType = 'touch', button = 0) {
  const event = new MouseEvent('pointerdown', { bubbles: true, clientX: model.x, clientY: model.y, button });
  Object.defineProperties(event, { pointerId: { value: pointerId }, pointerType: { value: pointerType } });
  target.dispatchEvent(event);
}

describe('createMascot free viewport dragging', () => {
  it('默认free真实pivot在无文档区域时可见，键盘移动按CSS像素并保持完整bounds', async () => {
    const result = await setup({ width: 390, liveBounds: true });
    expect(result.model.visible).toBe(true);
    result.app.view.getBoundingClientRect = () => ({ left: 0, top: 0, width: 780, height: 1800 });
    const x = result.model.x;
    result.mascot.moveBy(20, 0);
    expect(result.model.x).toBeCloseTo(x + 10);
    result.mascot.moveBy(-10000, 10000);
    const b = result.model.getLocalBounds();
    const first = result.model.toGlobal(new Point(b.x, b.y));
    const last = result.model.toGlobal(new Point(b.x + b.width, b.y + b.height));
    expect(first.x).toBeGreaterThanOrEqual(0);
    expect(last.y).toBeLessThanOrEqual(900);
    result.mascot.resetPosition();
    expect(result.model.x).toBeCloseTo(x);
  });
  it('cancels lost native pointer capture without tapping and allows the next drag', async () => {
    const { model, interactionTarget, onTap } = await setup();
    nativeDown(interactionTarget, model, 11, 'mouse');
    const lost = new Event('lostpointercapture');
    Object.defineProperty(lost, 'pointerId', { value: 11 });
    interactionTarget.dispatchEvent(lost);
    const position = [model.x, model.y];
    pointer('pointermove', 100, 120, 'mouse', 11);
    pointer('pointerup', 100, 120, 'mouse', 11);
    expect([model.x, model.y]).toEqual(position);
    expect(onTap).not.toHaveBeenCalled();
    nativeDown(interactionTarget, model, 12, 'mouse');
    pointer('pointermove', 350, 400, 'mouse', 12);
    pointer('pointerup', 350, 400, 'mouse', 12);
    expect([model.x, model.y]).toEqual([350, 400]);
  });

  it.each(['pointerup', 'pointercancel'])('accepts a new drag after a PointerEvents-only two-finger %s', async (end) => {
    const { model, interactionTarget, onTap } = await setup();
    nativeDown(interactionTarget, model, 11);
    nativeDown(document.body, model, 22);
    pointer(end, model.x, model.y, 'touch', 11);
    pointer(end, model.x, model.y, 'touch', 22);
    nativeDown(interactionTarget, model, 33);
    pointer('pointermove', 350, 400, 'touch', 33);
    pointer('pointerup', 350, 400, 'touch', 33);
    expect([model.x, model.y]).toEqual([350, 400]);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('restores native drag after window blur during a multi-touch gesture', async () => {
    const { model, interactionTarget, onTap } = await setup();
    nativeDown(interactionTarget, model, 11);
    nativeDown(document.body, model, 22);
    window.dispatchEvent(new Event('blur'));
    nativeDown(interactionTarget, model, 33);
    pointer('pointermove', 350, 400, 'touch', 33);
    pointer('pointerup', 350, 400, 'touch', 33);
    expect([model.x, model.y]).toEqual([350, 400]);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('ignores another pointer move, release and cancellation throughout a drag', async () => {
    const { model, onTap } = await setup();
    const position = [model.x, model.y];
    down(model, 'touch', 11);
    pointer('pointermove', 100, 120, 'touch', 22);
    pointer('pointerup', 100, 120, 'touch', 22);
    pointer('pointercancel', 100, 120, 'touch', 22);
    expect([model.x, model.y]).toEqual(position);
    expect(onTap).not.toHaveBeenCalled();
    pointer('pointermove', 350, 400, 'touch', 11);
    pointer('pointerup', 350, 400, 'touch', 11);
    expect([model.x, model.y]).toEqual([350, 400]);
  });

  it('cancels a single-finger gesture when a second finger lands outside the model', async () => {
    const { model, app, onTap } = await setup();
    down(model, 'touch', 11);
    pointer('pointermove', 350, 400, 'touch', 11);
    const position = [model.x, model.y];
    touchStart(app.view, [{ clientX: 150, clientY: 180 }, { clientX: 400, clientY: 600 }]);
    pointer('pointermove', 250, 280, 'touch', 11);
    pointer('pointerup', 250, 280, 'touch', 11);
    expect([model.x, model.y]).toEqual(position);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('does not let a second model pointer reset an already moved gesture into a tap', async () => {
    const { model, onTap } = await setup();
    down(model, 'touch', 11);
    pointer('pointermove', 350, 400, 'touch', 11);
    down(model, 'touch', 22);
    pointer('pointerup', 350, 400, 'touch', 22);
    pointer('pointerup', 350, 400, 'touch', 11);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('keeps a clipped DOM interaction and focus surface aligned after drag, scale and resize', async () => {
    const { model, mascot, interactionTarget, app } = await setup();
    drag(model, 350, 400);
    const assertBounds = () => {
      const b = model.getLocalBounds();
      const topLeft = model.toGlobal(new Point(b.x, b.y));
      const bottomRight = model.toGlobal(new Point(b.x + b.width, b.y + b.height));
      const left = Math.max(0, topLeft.x), top = Math.max(0, topLeft.y);
      expect(parseFloat(interactionTarget.style.left)).toBeCloseTo(left);
      expect(parseFloat(interactionTarget.style.top)).toBeCloseTo(top);
      expect(parseFloat(interactionTarget.style.width)).toBeCloseTo(Math.min(app.screen.width, bottomRight.x) - left);
      expect(parseFloat(interactionTarget.style.height)).toBeCloseTo(Math.min(app.screen.height, bottomRight.y) - top);
    };
    assertBounds();
    mascot.scaleBy(-1); assertBounds();
    app.screen.width = 375; app.screen.height = 812;
    mascot.resize(); assertBounds();
    expect(interactionTarget.style.touchAction).toBe('pinch-zoom');
  });

  it('moves a large desktop model across its initial placement zone on both axes', async () => {
    const { model, onTap } = await setup();
    drag(model, 350, 400);
    expect(model.x).toBe(350);
    expect(model.y).toBe(400);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('moves a touch-driven mobile model outside the document-flow region', async () => {
    const { model } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    drag(model, 100, 120, 'touch');
    expect(model.x).toBe(100);
    expect(model.y).toBe(120);
  });

  it('keeps the complete model inside every viewport edge', async () => {
    const { model } = await setup();
    drag(model, -1000, -1000);
    expect(model.x).toBeGreaterThan(0);
    expect(model.x - model.getLocalBounds().width * model.scale.x / 2).toBeGreaterThanOrEqual(0);
    expect(model.y).toBeGreaterThan(0);
    expect(model.y - model.getLocalBounds().height * model.scale.y / 2).toBeGreaterThanOrEqual(0);
    drag(model, 3000, 3000);
    expect(model.x).toBeLessThan(1440);
    expect(model.x + model.getLocalBounds().width * model.scale.x / 2).toBeLessThanOrEqual(1440);
    expect(model.y).toBeLessThan(900);
    expect(model.y + model.getLocalBounds().height * model.scale.y / 2).toBeLessThanOrEqual(900);
  });

  it('keeps the chosen position and scale visible when its mobile region scrolls away', async () => {
    const { model, mascot, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    drag(model, 100, 120, 'touch');
    const scale = model.scale.x;
    setRegion({ left: 20, top: -400, width: 335, height: 300 });
    mascot.resize();
    expect([model.x, model.y, model.visible, model.scale.x]).toEqual([100, 120, true, scale]);
  });

  it('keeps a manual placement when a scene region shrinks or disappears', async () => {
    const { model, mascot, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    drag(model, 100, 120);
    const scale = model.scale.x;
    setRegion({ left: 20, top: 700, width: 335, height: 0 });
    mascot.resize();
    expect([model.x, model.y, model.visible, model.scale.x]).toEqual([100, 120, true, scale]);
    setRegion(undefined);
    mascot.resize();
    expect([model.x, model.y, model.visible, model.scale.x]).toEqual([100, 120, true, scale]);
  });

  it('scales around the manual center instead of returning to the initial anchor', async () => {
    const { model, mascot } = await setup();
    drag(model, 350, 400);
    const before = model.scale.x;
    mascot.scaleBy(-1);
    expect([model.x, model.y]).toEqual([350, 400]);
    expect(model.scale.x).toBeLessThan(before);
    mascot.scaleBy(1);
    expect([model.x, model.y]).toEqual([350, 400]);
  });

  it('constrains the manual center on window resize without resetting to the adaptive anchor', async () => {
    const { app, model, mascot } = await setup();
    drag(model, 1300, 850);
    app.screen.width = 800;
    app.screen.height = 600;
    mascot.resize();
    expect(model.x).toBeGreaterThan(600);
    expect(model.x).toBeLessThan(800);
    expect(model.y).toBeGreaterThan(400);
    expect(model.y).toBeLessThan(600);
    const position = [model.x, model.y];
    mascot.resize();
    expect([model.x, model.y]).toEqual(position);
  });

  it('preserves mobile viewport placement independently of the document region', async () => {
    const { model, mascot, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    expect([model.x, model.y, model.visible]).toEqual([187.5, 406, true]);
    setRegion({ left: 20, top: 500, width: 335, height: 300 });
    mascot.resize();
    expect([model.x, model.y, model.visible]).toEqual([187.5, 406, true]);
    setRegion({ left: 20, top: -400, width: 335, height: 300 });
    mascot.resize();
    expect(model.visible).toBe(true);
  });

  it('retains the model hit area and only opens the menu for a click below the drag threshold', async () => {
    const { model, mascot, onTap } = await setup();
    expect(model.hitArea.contains(0, 0)).toBe(true);
    expect(model.hitArea.contains(701, 0)).toBe(false);
    const start = [model.x, model.y];
    down(model);
    pointer('pointermove', model.x + 1, model.y + 1);
    pointer('pointerup', model.x, model.y);
    expect(onTap).toHaveBeenCalledTimes(1);
    mascot.resize();
    expect([model.x, model.y]).toEqual(start);
    drag(model, 350, 400);
    expect(onTap).toHaveBeenCalledTimes(1);
  });

  it('stops on pointercancel without triggering the menu or accepting later moves', async () => {
    const { model, onTap } = await setup();
    down(model, 'touch');
    pointer('pointercancel', model.x, model.y, 'touch');
    const position = [model.x, model.y];
    pointer('pointermove', 350, 400, 'touch');
    pointer('pointerup', 350, 400, 'touch');
    expect([model.x, model.y, model.cursor]).toEqual([...position, 'grab']);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('preserves native pinch and background scrolling without cancelling touchstart', async () => {
    const { app, model, interactionTarget } = await setup();
    app.view.getBoundingClientRect = () => ({ left: 100, top: 50, width: 2880, height: 1800 });
    const center = { clientX: 100 + model.x * 2, clientY: 50 + model.y * 2 };
    expect(touchStart(app.view, [center]).defaultPrevented).toBe(false);
    expect(interactionTarget.style.touchAction).toBe('pinch-zoom');
    expect(touchStart(app.view, [{ clientX: 100, clientY: 50 }]).defaultPrevented).toBe(false);
    expect(touchStart(app.view, [center, { clientX: 110, clientY: 60 }]).defaultPrevented).toBe(false);
    app.view.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1440, height: 900 });
    drag(model, 350, 400, 'touch');
    expect(touchStart(app.view, [{ clientX: 120, clientY: 150 }]).defaultPrevented).toBe(false);
  });

  it('allows scrolling outside the independent mobile model and releases its touch listener on destroy', async () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');
    const { app, model, mascot, interactionTarget, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    const visibleCenter = { clientX: model.x, clientY: model.y };
    expect(touchStart(app.view, [visibleCenter]).defaultPrevented).toBe(false);
    setRegion({ left: 20, top: -400, width: 335, height: 300 });
    mascot.resize();
    expect(interactionTarget.style.visibility).toBe('visible');
    expect(touchStart(app.view, [{ clientX: model.x, clientY: model.y }]).defaultPrevented).toBe(false);
    mascot.destroy();
    expect(touchStart(app.view, [visibleCenter]).defaultPrevented).toBe(false);
    const registrations = add.mock.calls.filter(([type]) => type === 'touchstart');
    expect(registrations).toHaveLength(1);
    expect(registrations[0][2]).toEqual({ passive: true, capture: true });
    expect(remove.mock.calls.filter(([type]) => type === 'touchstart'))
      .toEqual([['touchstart', registrations[0][1], true]]);
  });

  it('removes every active window drag listener after release, cancel, and destroy', async () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');
    const { model, mascot, onTap } = await setup();
    for (const end of ['pointerup', 'pointercancel', 'destroy']) {
      down(model);
      if (end === 'destroy') mascot.destroy();
      else pointer(end, model.x, model.y);
    }
    for (const type of ['pointermove', 'pointerup', 'pointercancel']) {
      const registered = add.mock.calls.filter(([name, , capture]) => name === type && !capture).map(([, fn]) => fn);
      const removed = remove.mock.calls.filter(([name, , capture]) => name === type && !capture).map(([, fn]) => fn);
      expect(registered).toHaveLength(3);
      expect(removed).toEqual(registered);
    }
    const taps = onTap.mock.calls.length;
    pointer('pointermove', 350, 400);
    pointer('pointerup', 350, 400);
    expect(onTap).toHaveBeenCalledTimes(taps);
    expect(model.destroyed).toBe(true);
    expect(model.listenerCount('pointerdown')).toBe(0);
  });
});

describe('createMascot 显式嵌入兼容', () => {
  beforeEach(() => {
    // PIXI Graphics 的默认白纹理需要canvas；jsdom没有栅格实现，保留真实PIXI几何/树/变换。
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ fillRect() {}, fillStyle: '' });
  });
  const region = { left: 900, top: 180, width: 280, height: 300 };
  const assertContained = ({ model, interactionTarget }, area) => {
    const bounds = model.getLocalBounds();
    const first = model.toGlobal(new Point(bounds.x, bounds.y));
    const last = model.toGlobal(new Point(bounds.x + bounds.width, bounds.y + bounds.height));
    expect(first.x).toBeGreaterThanOrEqual(area.left);
    expect(first.y).toBeGreaterThanOrEqual(area.top);
    expect(last.x).toBeLessThanOrEqual(area.left + area.width);
    expect(last.y).toBeLessThanOrEqual(area.top + area.height);
    expect(parseFloat(interactionTarget.style.left)).toBeGreaterThanOrEqual(Math.max(0, area.left));
    expect(parseFloat(interactionTarget.style.top)).toBeGreaterThanOrEqual(Math.max(0, area.top));
    expect(parseFloat(interactionTarget.style.left) + parseFloat(interactionTarget.style.width)).toBeLessThanOrEqual(area.left + area.width);
  };
  it('真实anchor/pivot语义下contain模型，独立mask不改变模型bounds', async () => {
    const result = await setup({ embedded: true, liveBounds: true, region });
    assertContained(result, region);
    expect(result.model.parent).not.toBe(result.app.stage);
    expect(result.model.parent.mask).toBeTruthy();
    expect(result.model.getLocalBounds()).toEqual(new Rectangle(0, 0, 1400, 2000));
    expect(result.model.parent.mask.containsPoint(new Point(10, 10))).toBe(false);
    expect(result.model.parent.mask.containsPoint(new Point(1000, 300))).toBe(true);
    // 真实PIXI交互树：父级mask限制canvas命中，不仅是DOM占位裁切。
    const interaction = new InteractionManager({ view: result.app.view, resolution: 1 });
    expect(interaction.hitTest(new Point(10, 10), result.app.stage)).toBeNull();
    expect(interaction.hitTest(new Point(result.model.x, result.model.y), result.app.stage)).toBe(result.model);
    interaction.destroy();
  });
  it('拖动不越区，滚动后跟随自己的文档区域', async () => {
    const result = await setup({ embedded: true, liveBounds: true, region });
    result.mascot.scaleBy(-1);
    drag(result.model, -1000, -1000);
    assertContained(result, region);
    const before = result.model.y;
    const shifted = { ...region, top: region.top - 100 };
    result.setRegion(shifted); result.mascot.resize();
    expect(result.model.y).toBeCloseTo(before - 100);
    assertContained(result, shifted);
    result.setRegion(undefined); result.mascot.resize();
    expect(result.model.visible).toBe(false);
    expect(result.interactionTarget.style.visibility).toBe('hidden');
  });
  it('resize保持区域内相对意图，缩放后仍可容纳', async () => {
    const result = await setup({ embedded: true, liveBounds: true, region });
    result.mascot.scaleBy(-1);
    drag(result.model, 1020, 330);
    const ratio = [(result.model.x - region.left) / region.width, (result.model.y - region.top) / region.height];
    const next = { left: 20, top: 400, width: 320, height: 300 };
    result.app.screen.width = 390; result.setRegion(next); result.mascot.resize();
    expect(result.model.x).toBeCloseTo(next.left + next.width * ratio[0]);
    result.mascot.scaleBy(1); assertContained(result, next);
  });
  it('场景变化取消旧拖动和捕获，不触发菜单', async () => {
    const result = await setup({ embedded: true, liveBounds: true, region });
    result.interactionTarget.hasPointerCapture = () => true;
    result.interactionTarget.releasePointerCapture = vi.fn();
    down(result.model, 'mouse', 9);
    result.mascot.setStageExpression('parsing');
    const pos = [result.model.x, result.model.y];
    pointer('pointermove', 50, 50, 'mouse', 9); pointer('pointerup', 50, 50, 'mouse', 9);
    expect([result.model.x, result.model.y]).toEqual(pos);
    expect(result.interactionTarget.releasePointerCapture).toHaveBeenCalledWith(9);
    expect(result.onTap).not.toHaveBeenCalled();
  });
  it('转换偏移/缩放canvas坐标，热区仍是CSS文档区域', async () => {
    const result = await setup({ embedded: true, liveBounds: true, region });
    result.app.view.getBoundingClientRect = () => ({ left: 100, top: 50, width: 2880, height: 1800 });
    result.mascot.resize();
    expect(parseFloat(result.interactionTarget.style.left)).toBeGreaterThanOrEqual(region.left);
    expect(parseFloat(result.interactionTarget.style.left) + parseFloat(result.interactionTarget.style.width)).toBeLessThanOrEqual(region.left + region.width);
    expect(parseFloat(result.interactionTarget.style.top)).toBeGreaterThanOrEqual(region.top);
  });
  it('destroy释放mask/container且不动背景', async () => {
    const result = await setup({ embedded: true, liveBounds: true, region });
    const background = new Container(); result.app.stage.addChild(background);
    const host = result.model.parent, mask = host.mask;
    result.mascot.destroy(); result.mascot.destroy();
    expect(host.destroyed).toBe(true); expect(mask.destroyed).toBe(true);
    expect(result.app.stage.children).toEqual([background]);
  });
  it('无待机参数的嵌入回退不逐帧发布DOM几何', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const result = await setup({ embedded: true, liveBounds: true, region });
    const changed = vi.fn(); const observer = new MutationObserver(changed);
    observer.observe(result.interactionTarget, { attributes: true, attributeFilter: ['style'] });
    result.app.ticker.update(performance.now() + 1000);
    await Promise.resolve();
    expect(changed).not.toHaveBeenCalled(); observer.disconnect();
  });
});
