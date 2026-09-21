import { describe, it, expect, vi } from 'vitest';

vi.mock('pixi.js', () => ({}));

import { intensityForScene } from './background.js';
import { SCENE } from '../state/sceneMachine.js';

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
