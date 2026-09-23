import { describe, it, expect } from 'vitest';
import { MODELS, DEFAULT_MODEL_ID, EXPRESSIONS } from './mascotConfig.js';

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

describe('EXPRESSIONS 表情/道具配置', () => {
  it('stage 覆盖五个下载阶段，且映射到参数', () => {
    const keys = ['parsing', 'selecting', 'downloading', 'done', 'error'];
    expect(Object.keys(EXPRESSIONS.stage).sort()).toEqual(keys.slice().sort());
    keys.forEach((k) => {
      expect(EXPRESSIONS.stage[k].paramId).toMatch(/^Param\d+$/);
      expect(EXPRESSIONS.stage[k].name).toBeTruthy();
    });
  });

  it('random 道具池非空且节奏参数合法', () => {
    expect(EXPRESSIONS.random.pool.length).toBeGreaterThan(0);
    EXPRESSIONS.random.pool.forEach((p) => {
      expect(p.paramId).toMatch(/^Param\d+$/);
      expect(p.name).toBeTruthy();
    });
    expect(EXPRESSIONS.random.interval).toBeGreaterThan(0);
    expect(EXPRESSIONS.random.duration).toBeGreaterThan(0);
  });

  it('menu 分组 mode 合法、选项齐全、single 组内 paramId 无重复', () => {
    expect(EXPRESSIONS.menu.length).toBeGreaterThan(0);
    EXPRESSIONS.menu.forEach((g) => {
      expect(['single', 'toggle', 'multi']).toContain(g.mode);
      expect(g.label).toBeTruthy();
      expect(g.options.length).toBeGreaterThan(0);
      const ids = g.options.map((o) => {
        expect(o.paramId).toMatch(/^Param\d+$/);
        expect(o.name).toBeTruthy();
        return o.paramId;
      });
      if (g.mode === 'single') {
        expect(new Set(ids).size).toBe(ids.length);
      }
    });
  });

  it('effect 装饰特效：motion 定位合法且 stages 均为有效场景', () => {
    const { motion, stages } = EXPRESSIONS.effect;
    expect(motion.group).toBeTruthy();
    expect(typeof motion.index).toBe('number');
    expect(stages.length).toBeGreaterThan(0);
    stages.forEach((s) => expect(EXPRESSIONS.stage[s]).toBeTruthy());
  });

  it('menu 覆盖 6 个分组，且全表 paramId 无重复（可多选并存）', () => {
    const labels = EXPRESSIONS.menu.map((g) => g.label);
    expect(labels).toEqual(expect.arrayContaining(['发型', '衣服', '大小变', '配饰', '颜色', '情绪']));
    const all = EXPRESSIONS.menu.flatMap((g) => g.options.map((o) => o.paramId));
    expect(new Set(all).size).toBe(all.length);
  });
});
