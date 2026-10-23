import { describe, it, expect } from 'vitest';
import { MODELS, DEFAULT_MODEL_ID, EXPRESSIONS, SCALE, PLACEMENT, getModelLayout, getModelPlacement, supportsModelTexture } from './mascotConfig.js';

describe('角色完整摆放与能力降级', () => {
  const bounds = { width: 1400, height: 2000 };
  it('默认free在所有宽度不依赖文档区域，并正确处理非中心pivot', () => {
    expect(PLACEMENT.mode).toBe('free');
    expect(SCALE.initial).toBe(1);
    for (const width of [320, 390, 1440]) {
      const b = { x: 100, y: -50, width: 1000, height: 1600 };
      const pivot = { x: 400, y: 900 };
      const p = getModelPlacement(MODELS[0], { width, height: 812 }, b, SCALE.initial, undefined, { pivot });
      expect(p.visible).toBe(true);
      expect(p.x + (b.x - pivot.x) * p.scale).toBeGreaterThanOrEqual(0);
      expect(p.x + (b.x + b.width - pivot.x) * p.scale).toBeLessThanOrEqual(width);
      expect(p.y + (b.y - pivot.y) * p.scale).toBeGreaterThanOrEqual(0);
      expect(p.y + (b.y + b.height - pivot.y) * p.scale).toBeLessThanOrEqual(812);
    }
  });
  it('桌面最大倍率仍完整落在视口内', () => {
    const p = getModelPlacement(MODELS[0], { width: 1440, height: 900 }, bounds, SCALE.max, undefined, { mode: 'free' });
    expect(p.x - bounds.width * p.scale / 2).toBeGreaterThanOrEqual(0);
    expect(p.x + bounds.width * p.scale / 2).toBeLessThanOrEqual(1440);
    expect(p.y - bounds.height * p.scale / 2).toBeGreaterThanOrEqual(0);
    expect(p.y + bounds.height * p.scale / 2).toBeLessThanOrEqual(900);
  });
  it.each([320, 375, 720])('窄屏 %i 仅在内容之后的装饰区摆放', (width) => {
    const region = { left: 20, top: 590, width: width - 40, height: 300 };
    const p = getModelPlacement(MODELS[0], { width, height: 812 }, bounds, SCALE.initial, region, { mode: 'embedded' });
    expect(p.y - bounds.height * p.scale / 2).toBeGreaterThanOrEqual(region.top);
    expect(p.y + bounds.height * p.scale / 2).toBeLessThanOrEqual(region.top + region.height);
    expect(p.x - bounds.width * p.scale / 2).toBeGreaterThanOrEqual(region.left);
    expect(p.x + bounds.width * p.scale / 2).toBeLessThanOrEqual(region.left + region.width);
  });
  it('窄屏装饰区离开视口时隐藏角色', () => {
    expect(getModelPlacement(MODELS[0], { width: 375, height: 812 }, bounds, 2,
      { left: 20, top: -400, width: 335, height: 300 }, { mode: 'embedded' }).visible).toBe(false);
  });
  it('8K GPU 不会请求 16K 模型，16K GPU 保持可用', () => {
    expect(supportsModelTexture(MODELS[0], 8192)).toBe(false);
    expect(supportsModelTexture(MODELS[0], 16384)).toBe(true);
  });
});

describe('显式嵌入兼容布局', () => {
  it('显式embedded在所有宽度都contain到专属区域', () => {
    for (const width of [1440, 1024, 390, 320]) {
      const region = { left: 16, top: 180, width: Math.min(280, width - 32), height: 240 };
      const bounds = { x: 0, y: 0, width: 1400, height: 2000 };
      const pivot = { x: 700, y: 1000 };
      const p = getModelPlacement(MODELS[0], { width, height: 900 }, bounds, SCALE.max, region, { pivot, mode: 'embedded' });
      expect(p.visible).toBe(true);
      expect(p.x + (bounds.x - pivot.x) * p.scale).toBeGreaterThanOrEqual(region.left);
      expect(p.x + (bounds.x + bounds.width - pivot.x) * p.scale).toBeLessThanOrEqual(region.left + region.width);
      expect(p.y + (bounds.y - pivot.y) * p.scale).toBeGreaterThanOrEqual(region.top);
      expect(p.y + (bounds.y + bounds.height - pivot.y) * p.scale).toBeLessThanOrEqual(region.top + region.height);
    }
  });
  it('非中心bounds和pivot仍完整可见', () => {
    const region = { left: 800, top: 180, width: 260, height: 300 };
    const bounds = { x: 100, y: -50, width: 1000, height: 1600 };
    const pivot = { x: 400, y: 900 };
    const p = getModelPlacement(MODELS[0], { width: 1440, height: 900 }, bounds, SCALE.max, region, { pivot, mode: 'embedded' });
    expect(p.x + (bounds.x - pivot.x) * p.scale).toBeGreaterThanOrEqual(region.left);
    expect(p.x + (bounds.x + bounds.width - pivot.x) * p.scale).toBeLessThanOrEqual(region.left + region.width);
    expect(p.y + (bounds.y - pivot.y) * p.scale).toBeGreaterThanOrEqual(region.top);
    expect(p.y + (bounds.y + bounds.height - pivot.y) * p.scale).toBeLessThanOrEqual(region.top + region.height);
  });
  it.each([undefined, { left: 0, top: 0, width: 0, height: 240 }, { left: NaN, top: 0, width: 260, height: 240 }, { left: 1450, top: 100, width: 260, height: 240 }])('无有效可见区域时隐藏，不漂回视口中央：%j', (region) => {
    const p = getModelPlacement(MODELS[0], { width: 1440, height: 900 }, { x: -700, y: -1000, width: 1400, height: 2000 }, SCALE.initial, region, { mode: 'embedded' });
    expect(p.visible).toBe(false);
    expect(Number.isFinite(p.scale)).toBe(true);
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
  it('资源目录版本不改变模型标识，并让入口、相对资源和兜底共同绕过旧缓存', () => {
    const model = MODELS[0];
    expect(model.id).toBe('bai');
    expect(model.assetPath).toBe('live2d/bai-v1');
    expect(model.url).toBe('/live2d/bai-v1/白.model3.json');
    expect(model.fallback.url).toBe('/live2d/bai-v1/白.16384/texture_00.png');
    const entry = new URL(model.url, 'https://example.test');
    for (const resource of ['白.moc3', '白.physics3.json', '白.16384/texture_00.png']) {
      expect(new URL(resource, entry).pathname).toMatch(/^\/live2d\/bai-v1\//);
    }
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
