import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Container, Point, Rectangle, Ticker } from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display/cubism4';
import { createMascot } from './mascot.js';

// Loading a Cubism model requires external assets and WebGL. Keep PIXI's real
// transforms, event emitter and stage; replace only that external loading boundary.
vi.mock('pixi-live2d-display/cubism4', () => ({
  Live2DModel: { registerTicker: vi.fn(), from: vi.fn() },
  MotionPriority: { IDLE: 1 },
}));

let handles;
let tickers;

beforeEach(() => {
  handles = [];
  tickers = [];
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
});

afterEach(() => {
  handles.forEach((mascot) => mascot.destroy());
  tickers.forEach((ticker) => ticker.destroy());
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function setup({ width = 1440, height = 900, region } = {}) {
  const model = new Container();
  model.anchor = new Point();
  model.getLocalBounds = () => new Rectangle(-700, -1000, 1400, 2000);
  Live2DModel.from.mockResolvedValueOnce(model);
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
  const mascot = await createMascot(app, 'bai', { onTap, getRegion: () => currentRegion });
  handles.push(mascot);
  return { app, model, mascot, onTap, setRegion: (next) => { currentRegion = next; } };
}

function pointer(type, x, y, pointerType = 'mouse') {
  const event = new MouseEvent(type, { clientX: x, clientY: y });
  Object.defineProperty(event, 'pointerType', { value: pointerType });
  window.dispatchEvent(event);
}

function down(model, pointerType = 'mouse') {
  model.emit('pointerdown', {
    data: { global: new Point(model.x, model.y), originalEvent: { pointerType } },
  });
}

function drag(model, x, y, pointerType = 'mouse') {
  down(model, pointerType);
  pointer('pointermove', x, y, pointerType);
  pointer('pointerup', x, y, pointerType);
}

function touchStart(view, touches) {
  const event = new Event('touchstart', { cancelable: true });
  Object.defineProperty(event, 'touches', { value: touches });
  view.dispatchEvent(event);
  return event;
}

describe('createMascot free viewport dragging', () => {
  it('moves a large desktop model across its initial placement zone on both axes', async () => {
    const { model, onTap } = await setup();
    drag(model, 120, 150);
    expect(model.x).toBe(120);
    expect(model.y).toBe(150);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('moves a touch-driven mobile model outside the document-flow region', async () => {
    const { model } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    drag(model, 60, 120, 'touch');
    expect(model.x).toBe(60);
    expect(model.y).toBe(120);
  });

  it('keeps a dragged center recoverable at every viewport edge while allowing clipping', async () => {
    const { model } = await setup();
    drag(model, -1000, -1000);
    expect(model.x).toBeGreaterThan(0);
    expect(model.x).toBeLessThan(120);
    expect(model.y).toBeGreaterThan(0);
    expect(model.y).toBeLessThan(150);
    drag(model, 3000, 3000);
    expect(model.x).toBeLessThan(1440);
    expect(model.x).toBeGreaterThan(1320);
    expect(model.y).toBeLessThan(900);
    expect(model.y).toBeGreaterThan(750);
  });

  it('keeps the chosen position and scale visible when its mobile region scrolls away', async () => {
    const { model, mascot, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    drag(model, 60, 120, 'touch');
    const scale = model.scale.x;
    setRegion({ left: 20, top: -400, width: 335, height: 300 });
    mascot.resize();
    expect([model.x, model.y, model.visible, model.scale.x]).toEqual([60, 120, true, scale]);
  });

  it('keeps a manual placement when a scene region shrinks or disappears', async () => {
    const { model, mascot, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    drag(model, 60, 120);
    const scale = model.scale.x;
    setRegion({ left: 20, top: 700, width: 335, height: 0 });
    mascot.resize();
    expect([model.x, model.y, model.visible, model.scale.x]).toEqual([60, 120, true, scale]);
    setRegion(undefined);
    mascot.resize();
    expect([model.x, model.y, model.visible, model.scale.x]).toEqual([60, 120, true, scale]);
  });

  it('scales around the manual center instead of returning to the initial anchor', async () => {
    const { model, mascot } = await setup();
    drag(model, 120, 150);
    const before = model.scale.x;
    mascot.scaleBy(-1);
    expect([model.x, model.y]).toEqual([120, 150]);
    expect(model.scale.x).toBeLessThan(before);
    mascot.scaleBy(1);
    expect([model.x, model.y]).toEqual([120, 150]);
  });

  it('constrains the manual center on window resize without resetting to the adaptive anchor', async () => {
    const { app, model, mascot } = await setup();
    drag(model, 1300, 850);
    app.screen.width = 800;
    app.screen.height = 600;
    mascot.resize();
    expect(model.x).toBeGreaterThan(700);
    expect(model.x).toBeLessThan(800);
    expect(model.y).toBeGreaterThan(500);
    expect(model.y).toBeLessThan(600);
    const position = [model.x, model.y];
    mascot.resize();
    expect([model.x, model.y]).toEqual(position);
  });

  it('preserves adaptive mobile placement before the first actual drag', async () => {
    const { model, mascot, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    expect([model.x, model.y, model.visible]).toEqual([187.5, 740, true]);
    setRegion({ left: 20, top: 500, width: 335, height: 300 });
    mascot.resize();
    expect([model.x, model.y, model.visible]).toEqual([187.5, 650, true]);
    setRegion({ left: 20, top: -400, width: 335, height: 300 });
    mascot.resize();
    expect(model.visible).toBe(false);
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
    drag(model, 120, 150);
    expect(onTap).toHaveBeenCalledTimes(1);
  });

  it('stops on pointercancel without triggering the menu or accepting later moves', async () => {
    const { model, onTap } = await setup();
    down(model, 'touch');
    pointer('pointercancel', model.x, model.y, 'touch');
    const position = [model.x, model.y];
    pointer('pointermove', 120, 150, 'touch');
    pointer('pointerup', 120, 150, 'touch');
    expect([model.x, model.y, model.cursor]).toEqual([...position, 'grab']);
    expect(onTap).not.toHaveBeenCalled();
  });

  it('reserves only a single-finger start inside the transformed model for dragging', async () => {
    const { app, model } = await setup();
    app.view.getBoundingClientRect = () => ({ left: 100, top: 50, width: 2880, height: 1800 });
    const center = { clientX: 100 + model.x * 2, clientY: 50 + model.y * 2 };
    expect(touchStart(app.view, [center]).defaultPrevented).toBe(true);
    expect(touchStart(app.view, [{ clientX: 100, clientY: 50 }]).defaultPrevented).toBe(false);
    expect(touchStart(app.view, [center, { clientX: 110, clientY: 60 }]).defaultPrevented).toBe(false);
    app.view.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1440, height: 900 });
    drag(model, 120, 150, 'touch');
    expect(touchStart(app.view, [{ clientX: 120, clientY: 150 }]).defaultPrevented).toBe(true);
  });

  it('allows scrolling over an invisible model and releases its touch listener on destroy', async () => {
    const add = vi.spyOn(HTMLCanvasElement.prototype, 'addEventListener');
    const remove = vi.spyOn(HTMLCanvasElement.prototype, 'removeEventListener');
    const { app, model, mascot, setRegion } = await setup({ width: 375, height: 812,
      region: { left: 20, top: 590, width: 335, height: 300 } });
    const visibleCenter = { clientX: model.x, clientY: model.y };
    expect(touchStart(app.view, [visibleCenter]).defaultPrevented).toBe(true);
    setRegion({ left: 20, top: -400, width: 335, height: 300 });
    mascot.resize();
    expect(touchStart(app.view, [{ clientX: model.x, clientY: model.y }]).defaultPrevented).toBe(false);
    mascot.destroy();
    expect(touchStart(app.view, [visibleCenter]).defaultPrevented).toBe(false);
    const registrations = add.mock.calls.filter(([type]) => type === 'touchstart');
    expect(registrations).toHaveLength(1);
    expect(registrations[0][2]).toEqual({ passive: false });
    expect(remove.mock.calls.filter(([type]) => type === 'touchstart'))
      .toEqual([['touchstart', registrations[0][1]]]);
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
      const registered = add.mock.calls.filter(([name]) => name === type).map(([, fn]) => fn);
      const removed = remove.mock.calls.filter(([name]) => name === type).map(([, fn]) => fn);
      expect(registered).toHaveLength(3);
      expect(removed).toEqual(registered);
    }
    const taps = onTap.mock.calls.length;
    pointer('pointermove', 120, 150);
    pointer('pointerup', 120, 150);
    expect(onTap).toHaveBeenCalledTimes(taps);
    expect(model.destroyed).toBe(true);
    expect(model.listenerCount('pointerdown')).toBe(0);
  });
});
