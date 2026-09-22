import { describe, it, expect } from 'vitest';
import { MODELS, DEFAULT_MODEL_ID } from './mascotConfig.js';

describe('MODELS 模型注册表', () => {
  it('仅注册「白」一个模型', () => {
    expect(MODELS).toHaveLength(1);
    expect(MODELS[0].id).toBe('bai');
  });
  it('模型有合法入口、响应式高度比例与相对位置', () => {
    const m = MODELS[0];
    expect(m.url).toMatch(/\.model3\.json$/);
    expect(m.heightRatio).toBeGreaterThan(0);
    expect(m.heightRatio).toBeLessThan(1);
    expect(m.x).toBeGreaterThan(0);
    expect(m.x).toBeLessThanOrEqual(1);
    expect(m.y).toBeGreaterThan(0);
    expect(m.y).toBeLessThanOrEqual(1);
  });
  it('DEFAULT_MODEL_ID 指向唯一模型', () => {
    expect(DEFAULT_MODEL_ID).toBe('bai');
  });
});
