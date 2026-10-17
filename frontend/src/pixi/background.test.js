import { afterEach, describe, it, expect, vi } from 'vitest';

const pixiMock = vi.hoisted(() => {
  class Container {
    constructor() {
      this.children = [];
      this.destroyCalls = 0;
    }
    addChild(child) { this.children.push(child); return child; }
    removeChild(child) { this.children = this.children.filter((item) => item !== child); return child; }
    destroy(options) { this.destroyCalls += 1; this.destroyOptions = options; }
  }
  class Graphics {
    beginFill() { return this; }
    drawCircle() { return this; }
    endFill() { return this; }
  }
  class Sprite {
    constructor(texture) { this.texture = texture; this.anchor = { set() {} }; }
  }
  return { Container, Graphics, Sprite, Texture: { from: (canvas) => ({ canvas }) } };
});

vi.mock('pixi.js', () => pixiMock);

import * as background from './background.js';
import { SCENE } from '../state/sceneMachine.js';

const { intensityForScene } = background;

afterEach(() => vi.unstubAllGlobals());

describe('intensityForScene', () => {
  it('解析/下载为活跃档', () => {
    expect(intensityForScene(SCENE.PARSING)).toBe(1);
    expect(intensityForScene(SCENE.DOWNLOADING)).toBe(1);
  });
  it('入口/选择/完成/错误为安静档', () => {
    expect(intensityForScene(SCENE.ENTRY)).toBe(0);
    expect(intensityForScene(SCENE.SELECTING)).toBe(0);
    expect(intensityForScene(SCENE.DONE)).toBe(0);
    expect(intensityForScene(SCENE.ERROR)).toBe(0);
  });
});

describe('background ticker visibility', () => {
  it('pauses background updates while hidden and removes its visibility listener on cleanup', () => {
    const callbacks = new Set();
    const ticker = {
      add: (callback) => callbacks.add(callback),
      remove: (callback) => callbacks.delete(callback),
      tick: (delta) => callbacks.forEach((callback) => callback(delta)),
    };
    const listeners = new Set();
    const page = {
      hidden: false,
      addEventListener: (_type, callback) => listeners.add(callback),
      removeEventListener: (_type, callback) => listeners.delete(callback),
      changeVisibility() { listeners.forEach((listener) => listener()); },
    };
    const update = vi.fn();
    const attach = background.registerBackgroundTicker;

    expect(attach).toBeTypeOf('function');
    const cleanup = attach({ ticker }, update, page);

    ticker.tick(1);
    expect(update).toHaveBeenCalledTimes(1);

    page.hidden = true;
    page.changeVisibility();
    ticker.tick(1);
    expect(update).toHaveBeenCalledTimes(1);

    page.hidden = false;
    page.changeVisibility();
    ticker.tick(1);
    expect(update).toHaveBeenCalledTimes(2);

    cleanup();
    page.changeVisibility();
    ticker.tick(1);
    expect(update).toHaveBeenCalledTimes(2);
    expect(listeners.size).toBe(0);
  });

  it('destroys the background subtree and releases ticker/listener only once', () => {
    const callbacks = new Set();
    const listeners = new Map();
    const ticker = {
      add: vi.fn((callback) => callbacks.add(callback)),
      remove: vi.fn((callback) => callbacks.delete(callback)),
    };
    const gradient = { addColorStop() {} };
    const page = {
      hidden: false,
      createElement: () => ({
        getContext: () => ({
          createRadialGradient: () => gradient,
          fillRect() {},
          set fillStyle(_value) {},
        }),
      }),
      addEventListener: vi.fn((type, listener) => listeners.set(type, listener)),
      removeEventListener: vi.fn((type, listener) => listeners.delete(type, listener)),
    };
    vi.stubGlobal('document', page);
    vi.stubGlobal('window', { matchMedia: () => ({ matches: false }) });

    const stage = new pixiMock.Container();
    const app = { stage, ticker, screen: { width: 800, height: 600 } };
    const result = background.createBackground(app, 'high');
    const root = stage.children[0];

    result.destroy();
    expect(stage.children).toEqual([]);
    expect(root.destroyOptions).toEqual({ children: true, texture: true, baseTexture: true });
    expect(root.destroyCalls).toBe(1);
    expect(callbacks.size).toBe(0);
    expect(page.removeEventListener).toHaveBeenCalledTimes(1);

    result.destroy();
    expect(root.destroyCalls).toBe(1);
    expect(ticker.remove).toHaveBeenCalledTimes(1);
    expect(page.removeEventListener).toHaveBeenCalledTimes(1);
    expect(listeners.size).toBe(0);
  });
});
