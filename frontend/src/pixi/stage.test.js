import { describe, it, expect, vi, afterEach } from 'vitest';
import { detectTier, initStage } from './stage.js';
import * as PIXI from 'pixi.js';

vi.mock('pixi.js', () => ({ Application: vi.fn(function () {
  this.view = document.createElement('canvas');
  this.renderer = { plugins: { interaction: {} } };
}) }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('detectTier', () => {
  it('无 WebGL 返回 none（模拟）', () => {
    vi.stubGlobal('document', { createElement: () => ({ getContext: () => null }) });
    expect(detectTier()).toBe('none');
  });

  it('有 WebGL 且移动端 UA 返回 low', () => {
    vi.stubGlobal('document', { createElement: () => ({ getContext: () => ({}) }) });
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)',
      hardwareConcurrency: 8,
      deviceMemory: 8,
    });
    expect(detectTier()).toBe('low');
  });

  it('有 WebGL 且桌面高配返回 high', () => {
    vi.stubGlobal('document', { createElement: () => ({ getContext: () => ({}) }) });
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
      hardwareConcurrency: 16,
      deviceMemory: 16,
    });
    expect(detectTier()).toBe('high');
  });
});

it('clears transparent overlay with zero RGB so premultiplied compositing cannot paint white', () => {
  const container = document.createElement('div');
  initStage(container);
  expect(PIXI.Application).toHaveBeenLastCalledWith(expect.objectContaining({ backgroundColor: 0, backgroundAlpha: 0 }));
});
