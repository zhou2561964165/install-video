import { describe, it, expect } from 'vitest';
import { MODELS, DEFAULT_MODEL_ID, EXPRESSIONS, SCALE, getModelLayout, getModelPlacement, supportsModelTexture } from './mascotConfig.js';

describe('角色完整摆放与能力降级', () => {
  const bounds = { width: 1400, height: 2000 };
  it('桌面最大倍率仍完整落在视口内', () => {
    const p = getModelPlacement(MODELS[0], { width: 1440, height: 900 }, bounds, SCALE.max);
    expect(p.x - bounds.width * p.scale / 2).toBeGreaterThanOrEqual(0);
    expect(p.x + bounds.width * p.scale / 2).toBeLessThanOrEqual(1440);
    expect(p.y - bounds.height * p.scale / 2).toBeGreaterThanOrEqual(0);
    expect(p.y + bounds.height * p.scale / 2).toBeLessThanOrEqual(900);
  });
  it.each([320, 375, 720])('窄屏 %i 仅在内容之后的装饰区摆放', (width) => {
    const region = { left: 20, top: 590, width: width - 40, height: 300 };
    const p = getModelPlacement(MODELS[0], { width, height: 812 }, bounds, SCALE.initial, region);
    expect(p.y - bounds.height * p.scale / 2).toBeGreaterThanOrEqual(region.top);
    expect(p.y + bounds.height * p.scale / 2).toBeLessThanOrEqual(region.top + region.height);
    expect(p.x - bounds.width * p.scale / 2).toBeGreaterThanOrEqual(region.left);
    expect(p.x + bounds.width * p.scale / 2).toBeLessThanOrEqual(region.left + region.width);
  });
  it('窄屏装饰区离开视口时隐藏角色', () => {
    expect(getModelPlacement(MODELS[0], { width: 375, height: 812 }, bounds, 2,
      { left: 20, top: -400, width: 335, height: 300 }).visible).toBe(false);
  });
  it('8K GPU 不会请求 16K 模型，16K GPU 保持可用', () => {
    expect(supportsModelTexture(MODELS[0], 8192)).toBe(false);
    expect(supportsModelTexture(MODELS[0], 16384)).toBe(true);
  });
});

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
  it('窄屏使用配置化布局，角色高度小于桌面布局', () => {
    const m = MODELS[0];
    expect(getModelLayout(m, 375)).toBe(m.mobile);
    expect(getModelLayout(m, 1440)).toBe(m);
    expect(m.mobile.heightRatio).toBeLessThan(m.heightRatio);
  });
});

describe('SCALE 等比缩放配置', () => {
  it('step/min/max 合法（step>1 可放大、min>0、max>min）', () => {
    expect(SCALE.step).toBeGreaterThan(1);
    expect(SCALE.min).toBeGreaterThan(0);
    expect(SCALE.max).toBeGreaterThan(SCALE.min);
  });
  it('initial 落在 [min, max] 区间内', () => {
    expect(SCALE.initial).toBeGreaterThanOrEqual(SCALE.min);
    expect(SCALE.initial).toBeLessThanOrEqual(SCALE.max);
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
