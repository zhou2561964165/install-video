import * as PIXI from 'pixi.js';
import { Live2DModel, MotionPriority } from 'pixi-live2d-display/cubism4';
import { MODELS, DEFAULT_MODEL_ID, IDLE, EXPRESSIONS, SCALE, PLACEMENT, getModelPlacement, supportsModelTexture } from './mascotConfig.js';

// 创建 Live2D 角色并接入「拖动角色」+「点击角色 → onTap（React 弹换装菜单）」。
//   modelId   —— 初始模型 id（缺省/未命中回落 DEFAULT_MODEL_ID）
//   { onTap } —— 未位移的点击回调（供 React 打开换装/表情菜单）
// 返回 { getModelId, setExpression, setStageExpression, startRandomProps, resize, destroy }。
// 表情/道具走「直接写参数」（setExpression：paramId 置 1 开 / 0 关），与待机正弦驱动（IDLE）
// 参数不同、互不冲突；角色不随下载场景做奔跑/摆动位移，阶段反馈由表情+背景粒子+音频承担。
export async function createMascot(app, modelId, { onTap, getRegion } = {}) {
  window.PIXI = PIXI;                       // 插件依赖 window.PIXI.Ticker
  Live2DModel.registerTicker(PIXI.Ticker);

  // StrictMode 双重挂载下，第一次挂载的 app 会在 await Live2DModel.from() 返回前
  // 被 destroyStage 销毁，此后 app.stage/app.screen 均为 null。因此：任何 await 之后
  // 都先检查 disposed || !app.stage 守卫，绝不再触碰已销毁的 app。place/resize 只在
  // app.stage 非空的前提下调用，读 app.screen（live）是安全的。
  let disposed = false;
  let detachDrag = null;                    // 当前模型的拖动清理句柄（destroy 时解除 window 监听）
  let idle = { cleanup() {}, refreshBase() {} };  // 待机动画句柄（初始为空，加载后替换）
  let randomPropsCleanup = null;            // 随机道具定时器清理句柄（destroy 时调用）
  let scaleFactor = SCALE.initial;          // 等比缩放倍率（初始值来自 SCALE 配置，跨 resize 持久）

  const current = { model: null, cfg: null };
  const cfg = MODELS.find((m) => m.id === modelId) || MODELS[0];
  const gl = app.renderer.gl;
  if (!supportsModelTexture(cfg, gl.getParameter(gl.MAX_TEXTURE_SIZE))) {
    // 未请求模型/16K atlas，背景保留，避免在 8K GPU 上重复上传同一超限兜底纹理。
    app.view.dataset.mascot = 'unsupported-texture';
    return noopMascot();
  }

  // 响应式摆放：按屏幕高度等比缩放（cfg.heightRatio）+ 相对位置（0~1），
  // 任意尺寸屏幕都看到等比例的完整模型。读 app.screen，窗口 resize 时重放 place 重新适配。
  function place(instance, cfg) {
    instance.anchor.set(0.5, 0.5);
    const p = getModelPlacement(cfg, app.screen, instance.getLocalBounds(), scaleFactor, getRegion?.());
    instance.scale.set(p.scale);
    instance.x = p.x;
    instance.y = p.y;
    instance.visible = p.visible;
  }

  // 交互：可拖动 + 点击（onTap，React 弹换装菜单）。
  //   热区 = 模型自身局部包围盒（不外扩），退化时回落 config.hit 盒 —— 不写死像素。
  //   pointerdown 在模型上起拖；移动/抬起挂在 window 上，拖快时指针移出热区也不丢事件。
  //   位移 < 3px 视为「点击」：未位移的点击触发 onTap，拖动本身不触发。
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
      if (!moved && Math.hypot(p.x - startX, p.y - startY) > PLACEMENT.dragThreshold) moved = true;
      const area = getModelPlacement(cfg, app.screen, instance.getLocalBounds(), scaleFactor, getRegion?.());
      instance.x = Math.min(area.maxX, Math.max(area.minX, p.x + offsetX));
      instance.y = Math.min(area.maxY, Math.max(area.minY, p.y + offsetY));
    }
    function endDrag(triggerTap) {
      if (!dragging) return;
      dragging = false;
      instance.cursor = 'grab';
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
      if (triggerTap && !moved) onTap?.();
    }
    function onUp() { endDrag(true); }
    function onCancel() { endDrag(false); }
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
      window.addEventListener('pointercancel', onCancel);
    }
    instance.on('pointerdown', onDown);

    return () => { endDrag(false); instance.off('pointerdown', onDown); };
  }

  // 程序化待机动画：「白」的 model3.json 无 Motions / Breath 字段，角色本身不会自动呼吸/摆动，
  // 用 ticker 逐帧正弦驱动 coreModel 参数（呼吸 + 头/身轻微摆动）。驱动哪些参数由运行时
  // coreModel.getParameterIndex 判定，振幅/频率/相位来自 mascotConfig.js 的 IDLE 配置（数据驱动）。
  // 返回 { cleanup, refreshBase }。
  //   setParameterValueById 写的是「基础值」——cubism4 的 update() 会 saveParameters/loadParameters，
  //   focus/呼吸/物理在其上叠加并在帧末复原，因此这里每帧写一次即可（至多一帧延迟，肉眼不可感）。
  function startIdle(instance) {
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      return { cleanup() {}, refreshBase() {} };   // 减少动态偏好：完全静止
    }
    const core = instance.internalModel && instance.internalModel.coreModel;
    if (core) {
      const count = core.getParameterCount();
      const exists = (id) => core.getParameterIndex(id) < count;
      const driven = IDLE.params.filter((p) => exists(p.id));
      if (driven.length) {
        const t0 = performance.now();
        const tick = () => {
          if (disposed) { app.ticker.remove(tick); return; }
          const t = (performance.now() - t0) / 1000;
          for (const p of driven) {
            try {
              core.setParameterValueById(p.id, p.base + p.amplitude * Math.sin(t * 2 * Math.PI * p.frequency + p.phase));
            } catch (e) { /* 参数异常：忽略，不阻断其它参数 */ }
          }
        };
        app.ticker.add(tick);
        return { cleanup() { app.ticker.remove(tick); }, refreshBase() {} };
      }
    }
    // 回退：无任何匹配参数 → 容器级 scale 呼吸
    let base = instance.scale.x;
    const t0 = performance.now();
    const tick = () => {
      if (disposed) { app.ticker.remove(tick); return; }
      const t = (performance.now() - t0) / 1000;
      const s = 1 + IDLE.fallback.scale * Math.sin(t * 2 * Math.PI * IDLE.fallback.frequency);
      instance.scale.set(base * s, base * s);
    };
    app.ticker.add(tick);
    return {
      cleanup() { app.ticker.remove(tick); },
      refreshBase() { base = instance.scale.x; },
    };
  }

  async function loadModel(id) {
    const cfg = MODELS.find((m) => m.id === id) || MODELS[0];
    try {
      const instance = await Live2DModel.from(cfg.url);
      if (disposed || !app.stage) { instance.destroy(); return { cfg, instance: null }; } // 已卸载：不触碰已销毁的 app
      place(instance, cfg);
      app.stage.addChild(instance);
      return { cfg, instance };
    } catch (e) {
      console.warn('[mascot] 模型加载失败', cfg.id, e);
      return { cfg, instance: null };
    }
  }

  // 直接写单个参数（1 开 / 0 关）：绕过单选 expression manager，可多选并存。
  //   guard 已销毁 / 无模型 / 参数不存在；异常静默忽略，不阻断其它操作。
  function setExpression(paramId, value) {
    if (disposed || !current.model) return;
    const core = current.model.internalModel && current.model.internalModel.coreModel;
    if (!core) return;
    try {
      if (core.getParameterIndex(paramId) < core.getParameterCount()) {
        core.setParameterValueById(paramId, value);
      }
    } catch (e) { /* 参数异常：忽略 */ }
  }

  // 下载阶段 → 情绪眼（单选）：先清空 stage 全部参数，再置目标为 1；scene 无映射则只清空。
  // 顺带驱动装饰特效（setStageEffect）：完成/出错场景循环播放 edle 特效，其余停止。
  function setStageExpression(scene) {
    const target = EXPRESSIONS.stage[scene];
    Object.keys(EXPRESSIONS.stage).forEach((key) => setExpression(EXPRESSIONS.stage[key].paramId, 0));
    if (target) setExpression(target.paramId, 1);
    setStageEffect(scene);
  }

  // 装饰特效（EXPRESSIONS.effect → edle.motion3.json，Loop=true）：命中 stages 的场景循环播放，
  // 其余 stopAllMotions。motion() 返回 Promise<boolean>（未找到该 motion 时 resolve false），异常静默忽略。
  function setStageEffect(scene) {
    if (disposed || !current.model) return;
    const { motion, stages } = EXPRESSIONS.effect;
    if (stages.includes(scene)) {
      current.model.motion(motion.group, motion.index, MotionPriority.IDLE).catch(() => {});
    } else {
      const mm = current.model.internalModel && current.model.internalModel.motionManager;
      if (mm) mm.stopAllMotions();
    }
  }

  // 随机道具：每 interval 毫秒从 pool 随机取一个展示 duration 毫秒后收回。
  //   recover 未清时跳过本轮（防连发）；重复调用只启动一次，destroy 时统一清理。
  function startRandomProps() {
    if (randomPropsCleanup) return;
    let recover = null;
    const pick = () => {
      if (disposed) return;
      const pool = EXPRESSIONS.random.pool;
      const item = pool[Math.floor(Math.random() * pool.length)];
      setExpression(item.paramId, 1);
      recover = setTimeout(() => {
        recover = null;
        setExpression(item.paramId, 0);
      }, EXPRESSIONS.random.duration);
    };
    const timer = setInterval(() => {
      if (!recover) pick();
    }, EXPRESSIONS.random.interval);
    randomPropsCleanup = () => {
      clearInterval(timer);
      if (recover) clearTimeout(recover);
    };
  }

  // 等比缩放：SCALE.step 累积，clamp 到 [SCALE.min, SCALE.max]，重放 place 保持锚点居中。
  //   direction > 0 放大 / < 0 缩小；倍率持久（跨 resize 生效，place 统一乘 scaleFactor）。
  //   只动模型 transform，不碰表情/下载状态。
  function scaleBy(direction) {
    if (disposed || !current.model || !current.cfg) return;
    const factor = direction > 0 ? SCALE.step : 1 / SCALE.step;
    scaleFactor = Math.min(SCALE.max, Math.max(SCALE.min, scaleFactor * factor));
    place(current.model, current.cfg);
    idle.refreshBase();   // 容器级呼吸回退时重设基准 scale
  }

  // 初始加载；失败则整体降级为静态占位（与旧行为一致）
  const loaded = await loadModel(modelId);
  if (disposed || !app.stage) return noopMascot(); // app 已销毁：返回空句柄，不做任何渲染
  if (!loaded.instance) return createFallback(app, modelId, getRegion);
  current.cfg = loaded.cfg;
  current.model = loaded.instance;
  detachDrag = makeInteractive(loaded.instance, loaded.cfg);
  idle = startIdle(loaded.instance);

  return {
    isAvailable() { return true; },
    getModelId() { return current.cfg.id; },
    setExpression,
    setStageExpression,
    startRandomProps,
    scaleBy,
    resize() {
      if (!disposed && current.model && current.cfg) {
        place(current.model, current.cfg);
        idle.refreshBase();   // 容器级呼吸回退时，重设基准 scale
      }
    },
    destroy() {
      if (disposed) return;
      disposed = true;
      idle.cleanup();
      if (randomPropsCleanup) randomPropsCleanup();
      if (detachDrag) detachDrag();   // 结束未完成的拖动并解除 window 监听
      if (current.model) { app.stage.removeChild(current.model); current.model.destroy(); }
    },
  };
}

// app 已销毁时返回的空句柄：所有方法均 no-op
function noopMascot() {
  return {
    isAvailable() { return false; },
    getModelId() { return DEFAULT_MODEL_ID; },
    setExpression() {},
    setStageExpression() {},
    startRandomProps() {},
    scaleBy() {},
    resize() {},
    destroy() {},
  };
}

async function createFallback(app, modelId, getRegion) {
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
    const p = getModelPlacement(cfg, app.screen, { width: bt.width, height: naturalHeight }, SCALE.initial, getRegion?.());
    sprite.scale.set(p.scale);
    sprite.x = p.x;
    sprite.y = p.y;
    sprite.visible = p.visible;
  };
  lay();
  app.stage.addChild(sprite);
  return {
    isAvailable() { return false; },
    getModelId() { return cfg.id; },
    setExpression() {},
    setStageExpression() {},
    startRandomProps() {},
    scaleBy() {},
    resize() { lay(); },
    destroy() { app.stage.removeChild(sprite); sprite.destroy(); },
  };
}
