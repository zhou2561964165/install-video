import * as PIXI from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display/cubism4';
import { MODELS, DEFAULT_MODEL_ID } from './mascotConfig.js';
import { EASE, MODEL_SWITCH_FX } from '../fx/constants.js';

// 创建 Live2D 角色并接入「拖动角色」+「点击角色 → 循环切换模型」（仅 ≥2 模型时点击才切换）。
//   modelId             —— 初始模型 id（缺省/未命中回落 DEFAULT_MODEL_ID）
//   { onModelChange }   —— 切换成功后的回调 (nextId)，供 React 侧同步状态 / 提示
// 返回 { getModelId, cycleModel, resize, destroy }。
// 注意：角色不随下载场景切换表情/动作，也不做奔跑/摆动位移；下载各阶段的状态
// 反馈由背景粒子/音频独立承担。单模型时仍可拖动，但不设切换点击。
export async function createMascot(app, modelId, { onModelChange } = {}) {
  window.PIXI = PIXI;                       // 插件依赖 window.PIXI.Ticker
  Live2DModel.registerTicker(PIXI.Ticker);

  // StrictMode 双重挂载下，第一次挂载的 app 会在 await Live2DModel.from() 返回前
  // 被 destroyStage 销毁，此后 app.stage/app.screen 均为 null。因此：任何 await 之后
  // 都先检查 disposed || !app.stage 守卫，绝不再触碰已销毁的 app。place/resize 只在
  // app.stage 非空的前提下调用，读 app.screen（live）是安全的。
  let disposed = false;
  let switching = false;                    // 切换动画进行中，防连点
  let detachDrag = null;                    // 当前模型的拖动清理句柄（destroy 时解除 window 监听）

  const current = { model: null, cfg: null };

  // 响应式摆放：按屏幕高度等比缩放（cfg.heightRatio）+ 相对位置（0~1），
  // 任意尺寸屏幕都看到等比例的完整模型。读 app.screen，窗口 resize 时重放 place 重新适配。
  function place(instance, cfg) {
    const w = app.screen.width;
    const h = app.screen.height;
    instance.anchor.set(0.5, 0.5);
    instance.scale.set((h * cfg.heightRatio) / instance.getLocalBounds().height);
    instance.x = w * cfg.x;
    instance.y = h * cfg.y;
  }

  // 交互：可拖动 + 点击切换（仅 ≥2 模型时点击才切换）。
  //   热区 = 模型自身局部包围盒（不外扩），退化时回落 config.hit 盒 —— 不写死像素。
  //   pointerdown 在模型上起拖；移动/抬起挂在 window 上，拖快时指针移出热区也不丢事件。
  //   位移 < 3px 视为「点击」：未位移的点击才切换模型，拖动本身不触发切换。
  function makeInteractive(instance, cfg) {
    instance.interactive = true;
    instance.cursor = 'grab';
    const b = instance.getLocalBounds();
    const box = (b.width > 1 && b.height > 1)
      ? new PIXI.Rectangle(b.x, b.y, b.width, b.height)
      : new PIXI.Rectangle(-cfg.hit.width / 2, -cfg.hit.height / 2, cfg.hit.width, cfg.hit.height);
    instance.hitArea = box;

    let dragging = false;
    let moved = false;
    let startX = 0;
    let startY = 0;
    let offsetX = 0;
    let offsetY = 0;

    function toStage(cx, cy) {
      const r = app.view.getBoundingClientRect();
      return { x: ((cx - r.left) * app.screen.width) / r.width, y: ((cy - r.top) * app.screen.height) / r.height };
    }
    function onMove(e) {
      if (!dragging || disposed) return;
      const p = toStage(e.clientX, e.clientY);
      if (!moved && Math.hypot(p.x - startX, p.y - startY) > 3) moved = true;
      instance.x = p.x + offsetX;
      instance.y = p.y + offsetY;
    }
    function endDrag(triggerTap) {
      if (!dragging) return;
      dragging = false;
      instance.cursor = 'grab';
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      if (triggerTap && !moved && MODELS.length >= 2) cycleModel();
    }
    function onUp() { endDrag(true); }
    function onDown(e) {
      if (disposed) return;
      const p = e.data.global;   // 舞台逻辑坐标，与 toStage 一致
      offsetX = instance.x - p.x;
      offsetY = instance.y - p.y;
      startX = p.x;
      startY = p.y;
      dragging = true;
      moved = false;
      instance.cursor = 'grabbing';
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onUp);
    }
    instance.on('pointerdown', onDown);

    return () => { endDrag(false); instance.off('pointerdown', onDown); };
  }

  // 隐藏模型内置的「免费版水印」Part：水印是 moc3 里的 Part（非 expression），
  // 无法通过删除 exp3.json 去除，只能通过 coreModel 把对应 Part 不透明度置 0。
  // 哪些 Part 需要隐藏由 config.hiddenParts 指定，渲染层不写死任何 Part id。
  function hideParts(instance, cfg) {
    if (!cfg.hiddenParts || !cfg.hiddenParts.length) return;
    const core = instance.internalModel && instance.internalModel.coreModel;
    if (!core) return;
    for (const partId of cfg.hiddenParts) {
      try {
        core.setPartOpacityById(partId, 0);
      } catch (e) {
        console.warn('[mascot] 隐藏部件失败', cfg.id, partId, e);
      }
    }
  }

  async function loadModel(id) {
    const cfg = MODELS.find((m) => m.id === id) || MODELS[0];
    try {
      const instance = await Live2DModel.from(cfg.url);
      if (disposed || !app.stage) { instance.destroy(); return { cfg, instance: null }; } // 已卸载：不触碰已销毁的 app
      place(instance, cfg);
      hideParts(instance, cfg);
      app.stage.addChild(instance);
      return { cfg, instance };
    } catch (e) {
      console.warn('[mascot] 模型加载失败', cfg.id, e);
      return { cfg, instance: null };
    }
  }

  // —— 切换特效：光环扩散 + 粒子爆散（逐帧，参数取自 MODEL_SWITCH_FX） ——
  function spawnSwitchFx(cx, cy) {
    const g = new PIXI.Graphics();
    app.stage.addChild(g);
    const pts = [];
    for (let i = 0; i < MODEL_SWITCH_FX.burstCount; i++) {
      const ang = (Math.PI * 2 * i) / MODEL_SWITCH_FX.burstCount;
      pts.push({
        x: cx, y: cy,
        vx: Math.cos(ang) * MODEL_SWITCH_FX.burstSpeed,
        vy: Math.sin(ang) * MODEL_SWITCH_FX.burstSpeed,
        life: 0,
      });
    }
    let frame = 0;
    const tick = () => {
      if (disposed) { app.ticker.remove(tick); return; }
      frame += 1;
      const p = Math.min(1, frame / MODEL_SWITCH_FX.burstLife);
      g.clear();
      g.lineStyle(2, 0xffffff, 0.8 * (1 - p));
      g.drawCircle(cx, cy, MODEL_SWITCH_FX.ringRadius * EASE.outCubic(p));
      for (const pt of pts) {
        pt.life += 1;
        pt.x += pt.vx; pt.y += pt.vy;
        pt.vx *= MODEL_SWITCH_FX.burstDecay;
        pt.vy *= MODEL_SWITCH_FX.burstDecay;
        g.beginFill(0xffffff, Math.max(0, 0.9 - pt.life / MODEL_SWITCH_FX.burstLife));
        g.drawCircle(pt.x, pt.y, 2);
        g.endFill();
      }
      if (frame >= MODEL_SWITCH_FX.burstLife) {
        app.ticker.remove(tick);
        app.stage.removeChild(g);
        g.destroy();
      }
    };
    app.ticker.add(tick);
  }

  // alpha 补间：from → to，时长 duration（ms），缓动 ease，结束回调 done
  function fadeAlpha(target, from, to, duration, ease, done) {
    const start = performance.now();
    const tick = () => {
      if (disposed) { app.ticker.remove(tick); return; }
      const p = Math.min(1, (performance.now() - start) / duration);
      target.alpha = from + (to - from) * ease(p);
      if (p >= 1) { app.ticker.remove(tick); if (done) done(); }
    };
    app.ticker.add(tick);
  }

  // 循环切换到下一个模型：爆散 + 旧模型淡出 → 加载新模型 → 淡入
  function cycleModel() {
    if (switching || disposed || !current.model || MODELS.length < 2) return;
    switching = true;
    const idx = MODELS.findIndex((m) => m.id === current.cfg.id);
    const nextCfg = MODELS[(idx + 1) % MODELS.length];
    const cur = current.model;

    spawnSwitchFx(cur.x, cur.y);
    fadeAlpha(cur, 1, 0, MODEL_SWITCH_FX.fadeOut, EASE.inCubic, async () => {
      const next = await loadModel(nextCfg.id);
      if (disposed || !next.instance) {   // 卸载或加载失败：旧模型淡回，保持原状
        fadeAlpha(cur, 0, 1, MODEL_SWITCH_FX.fadeIn, EASE.outCubic, () => { switching = false; });
        return;
      }
      app.stage.removeChild(cur);
      cur.destroy();
      current.model = next.instance;
      current.cfg = next.cfg;
      detachDrag = makeInteractive(next.instance, next.cfg);
      next.instance.alpha = 0;
      fadeAlpha(next.instance, 0, 1, MODEL_SWITCH_FX.fadeIn, EASE.outCubic, () => {
        switching = false;
        if (onModelChange) onModelChange(next.cfg.id);
      });
    });
  }

  // 初始加载；失败则整体降级为静态占位（与旧行为一致）
  const loaded = await loadModel(modelId);
  if (disposed || !app.stage) return noopMascot(); // app 已销毁：返回空句柄，不做任何渲染
  if (!loaded.instance) return createFallback(app, modelId);
  current.cfg = loaded.cfg;
  current.model = loaded.instance;
  detachDrag = makeInteractive(loaded.instance, loaded.cfg);

  return {
    getModelId() { return current.cfg.id; },
    cycleModel,
    resize() { if (!disposed && current.model && current.cfg) place(current.model, current.cfg); },
    destroy() {
      if (disposed) return;
      disposed = true;
      if (detachDrag) detachDrag();   // 结束未完成的拖动并解除 window 监听
      if (current.model) { app.stage.removeChild(current.model); current.model.destroy(); }
    },
  };
}

// app 已销毁时返回的空句柄：所有方法均 no-op
function noopMascot() {
  return {
    getModelId() { return DEFAULT_MODEL_ID; },
    cycleModel() {},
    resize() {},
    destroy() {},
  };
}

async function createFallback(app, modelId) {
  const cfg = MODELS.find((m) => m.id === modelId) || MODELS[0];
  const sprite = PIXI.Sprite.from(cfg.fallback.url);
  sprite.anchor.set(0.5, 0.5);
  // 16K 纹理异步加载：等 baseTexture 就绪后再按自然高缩放，否则读到的是占位 1×1
  const bt = sprite.texture.baseTexture;
  if (!bt.valid) {
    await new Promise((res) => {
      bt.once('loaded', res);
      bt.once('error', res);
    });
  }
  if (!app.stage) return noopMascot(); // await 期间 app 已销毁
  const naturalHeight = sprite.height;   // 纹理自然高（scale 仍为 1）
  const lay = () => {
    sprite.scale.set((app.screen.height * cfg.heightRatio) / naturalHeight);
    sprite.x = app.screen.width * cfg.x;
    sprite.y = app.screen.height * cfg.y;
  };
  lay();
  app.stage.addChild(sprite);
  return {
    getModelId() { return cfg.id; },
    cycleModel() {},
    resize() { lay(); },
    destroy() { app.stage.removeChild(sprite); sprite.destroy(); },
  };
}
