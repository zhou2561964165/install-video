import { describe, it, expect } from 'vitest';
import { SCENE_MASCOT, EXPRESSION_NAMES, MODELS } from './mascotConfig.js';
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

describe('MODELS 模型注册表', () => {
  it('至少注册一个模型，且 id 唯一', () => {
    expect(MODELS.length).toBeGreaterThan(0);
    const ids = MODELS.map((m) => m.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
  it('每个模型都有合法入口与缩放', () => {
    for (const m of MODELS) {
      expect(m.url).toMatch(/\.model3\.json$/);
      expect(m.scale).toBeGreaterThan(0);
      expect(m.x).toBeGreaterThan(0);
      expect(m.x).toBeLessThanOrEqual(1);
      expect(m.y).toBeGreaterThan(0);
      expect(m.y).toBeLessThanOrEqual(1);
    }
  });
  it('首模型是 miku（默认角色）', () => {
    expect(MODELS[0].id).toBe('miku');
  });
  it('无 expression/motion 的模型用 scene 覆盖关闭表情动作，避免调用缺失资源', () => {
    const bai = MODELS.find((m) => m.id === 'bai');
    expect(bai).toBeTruthy();
    expect(bai.scene[SCENE.ENTRY].expression).toBeNull();
    expect(bai.scene[SCENE.ENTRY].motion).toBeNull();
  });
});
