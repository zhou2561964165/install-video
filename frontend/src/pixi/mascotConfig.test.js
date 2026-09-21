import { describe, it, expect } from 'vitest';
import { SCENE_MASCOT, EXPRESSION_NAMES } from './mascotConfig.js';
import { SCENE } from '../state/sceneMachine.js';

describe('mascotConfig', () => {
  it('每个场景都有映射', () => {
    for (const s of Object.values(SCENE)) expect(SCENE_MASCOT[s]).toBeTruthy();
  });
  it('downloading 使用 run（位移+速度线表达奔跑）', () => {
    expect(SCENE_MASCOT[SCENE.DOWNLOADING].run).toBe(true);
  });
  it('expression 名都来自实际存在的文件，且不含水印', () => {
    expect(EXPRESSION_NAMES).not.toContain('水印');
    for (const s of Object.values(SCENE)) {
      const e = SCENE_MASCOT[s].expression;
      if (e) expect(EXPRESSION_NAMES).toContain(e);
    }
  });
});
