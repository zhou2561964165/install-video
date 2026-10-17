import * as PIXI from 'pixi.js';
import { Live2DModel, MotionPriority } from 'pixi-live2d-display/cubism4';
import { MODELS, DEFAULT_MODEL_ID, IDLE, EXPRESSIONS, SCALE, PLACEMENT, getModelPlacement, getDraggedModelPosition, supportsModelTexture } from './mascotConfig.js';
import { createMascotResources } from './mascotResources.js';
import { registerMascotSilhouette } from './mascotSilhouette.js';

// 创建 Live2D 角色并接入「拖动角色」+「点击角色 → onTap（React 弹换装菜单）」。
//   modelId   —— 初始模型 id（缺省/未命中回落 DEFAULT_MODEL_ID）
//   { onTap } —— 未位移的点击回调（供 React 打开换装/表情菜单）
// moveBy使用CSS像素；resetPosition复位；setMotionEnabled保留显式调用兼容接口。
// signal只取消本层等待/资源持有；底层模型加载晚到时释放实例。
// 表情/道具走「直接写参数」（setExpression：paramId 置 1 开 / 0 关），与待机正弦驱动（IDLE）
// 参数不同、互不冲突；角色不随下载场景做奔跑/摆动位移，阶段反馈由表情+背景粒子+音频承担。
export async function createMascot(app, modelId, { onTap, getRegion, interactionTarget, placementMode = PLACEMENT.mode, signal } = {}) {
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
  let randomPropsRequested = false;
  let scaleFactor = SCALE.initial;          // 等比缩放倍率（初始值来自 SCALE 配置，跨 resize 持久）
  let manualPosition = null;                // free兼容的视口中心；embedded另保存区域内相对意图
  let relativePosition = null;
  let placement = null;
  let visibleBounds = null;
  let cancelDrag = () => {};
  let host = null;
  let mask = null;
  const embedded = placementMode === 'embedded';
  let available = true;
  let resources = createMascotResources();
  let nativeMotionActive = null;
  let currentScene = null;
  let syncMotionState = () => {};
  let motionEnabled = true;
  let motionCleanup = () => {};
  let publishedStyle = '';
  let silhouette = null;
  const canAnimate = () => !disposed && Boolean(app.stage) && motionEnabled;
  const alive = () => !disposed && !signal?.aborted && Boolean(app.stage);

  const current = { model: null, cfg: null };
  if (interactionTarget) interactionTarget.style.visibility = 'hidden';

  const regionInStage = () => embedded ? toStageRegion(app, getRegion?.()) : null;

  // 现有 DOM 键盘入口同时承担模型的局部触控表面。只发布视口几何，不接触业务状态。
  function syncInteraction(instance) {
    const b = instance.getLocalBounds();
    const first = instance.toGlobal(new PIXI.Point(b.x, b.y));
    const last = instance.toGlobal(new PIXI.Point(b.x + b.width, b.y + b.height));
    const r = app.view.getBoundingClientRect();
    const area = embedded ? regionInStage() : null;
    const left = Math.max(0, first.x, area?.left ?? 0), top = Math.max(0, first.y, area?.top ?? 0);
    const right = Math.min(app.screen.width, last.x, area ? area.left + area.width : app.screen.width);
    const bottom = Math.min(app.screen.height, last.y, area ? area.top + area.height : app.screen.height);
    const width = Math.max(0, right - left), height = Math.max(0, bottom - top);
    visibleBounds = instance.visible && (!embedded || area) && width > 0 && height > 0 ? { left, top, right, bottom } : null;
    if (!interactionTarget) return;
    const styles = {
      left: `${r.left + left * r.width / app.screen.width}px`,
      top: `${r.top + top * r.height / app.screen.height}px`,
      width: `${width * r.width / app.screen.width}px`,
      height: `${height * r.height / app.screen.height}px`,
      visibility: visibleBounds ? 'visible' : 'hidden',
      touchAction: PLACEMENT.modelTouchAction,
    };
    const key = JSON.stringify(styles);
    if (key !== publishedStyle) { Object.assign(interactionTarget.style, styles); publishedStyle = key; }
  }
  const cfg = MODELS.find((m) => m.id === modelId) || MODELS[0];
  const gl = app.renderer.gl;
  if (!supportsModelTexture(cfg, gl.getParameter(gl.MAX_TEXTURE_SIZE))) {
    // 未请求模型/16K atlas，背景保留，避免在 8K GPU 上重复上传同一超限兜底纹理。
    app.view.dataset.mascot = 'unsupported-texture';
    return noopMascot();
  }

  // embedded兼容文档区域contain；free完全独立于文档，约束模型全部bounds。
  function place(instance, cfg) {
    instance.anchor.set(0.5, 0.5);
    const region = regionInStage();
    const p = getModelPlacement(cfg, app.screen, instance.getLocalBounds(), scaleFactor, region, { mode: placementMode, pivot: instance.pivot });
    placement = p;
    instance.scale.set(p.scale);
    if (embedded) {
      const pos = relativePosition && region ? getDraggedModelPosition({ x: region.left + relativePosition.x * region.width, y: region.top + relativePosition.y * region.height }, app.screen, p) : p;
      instance.x = pos.x; instance.y = pos.y; instance.visible = p.visible;
      if (!p.visible) cancelDrag();
      if (mask) { mask.clear(); if (region) mask.beginFill().drawRect(region.left, region.top, region.width, region.height).endFill(); }
    } else {
      if (manualPosition) manualPosition = getDraggedModelPosition(manualPosition, app.screen, p);
      instance.x = manualPosition ? manualPosition.x : p.x;
      instance.y = manualPosition ? manualPosition.y : p.y;
      instance.visible = p.visible;
      manualPosition = { x: instance.x, y: instance.y };
    }
    syncInteraction(instance);
  }

  // Public movement is expressed in CSS pixels; PIXI coordinates may differ under
  // a scaled canvas. Both pointer and keyboard paths use the same bounds clamp.
  function moveBy(dx, dy) {
    if (!alive() || !current.model || !placement || ![dx, dy].every(Number.isFinite)) return;
    cancelDrag();
    const r = app.view.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    const instance = current.model;
    manualPosition = getDraggedModelPosition({ x: instance.x + dx * app.screen.width / r.width, y: instance.y + dy * app.screen.height / r.height }, app.screen, placement);
    instance.x = manualPosition.x; instance.y = manualPosition.y;
    if (embedded) {
      const area = regionInStage();
      if (area) relativePosition = { x: (instance.x - area.left) / area.width, y: (instance.y - area.top) / area.height };
    }
    syncInteraction(instance);
  }
  function resetPosition() {
    if (!alive() || !current.model) return;
    cancelDrag(); manualPosition = null; relativePosition = null;
    place(current.model, current.cfg);
  }
  function startMotion(instance) {
    const ticker = app.ticker;
    syncMotionState = () => {
      const active = canAnimate();
      if (active === nativeMotionActive) return;
      nativeMotionActive = active;
      if (!active) {
        instance.internalModel?.motionManager?.stopAllMotions?.();
        if (randomPropsCleanup) { randomPropsCleanup(); randomPropsCleanup = null; }
      } else {
        setStageEffect(currentScene);
        if (randomPropsRequested) startRandomProps();
      }
    };
    const tick = () => {
      syncMotionState();
      if (!canAnimate()) return;
      if (available) instance.update?.(Math.min(100, Math.max(0, ticker.deltaMS)));
      silhouette?.tick();
    };
    ticker.add(tick);
    syncMotionState();
    return () => {
      ticker.remove(tick);
    };
  }

  // 交互：可拖动 + 点击（onTap，React 弹换装菜单）。
  //   热区 = 模型自身局部包围盒（不外扩），退化时回落 config.hit 盒 —— 不写死像素。
  //   pointerdown 在模型上起拖；移动/抬起挂在 window 上，拖快时指针移出热区也不丢事件。
  //   位移未超过配置阈值视为「点击」：点击触发 onTap，实际拖动不触发。
  function makeInteractive(instance, cfg) {
    instance.interactive = true;
    instance.cursor = 'grab';
    const b = instance.getLocalBounds();
    const box = (b.width > 1 && b.height > 1)
      ? new PIXI.Rectangle(b.x, b.y, b.width, b.height)
      : new PIXI.Rectangle(-cfg.hit.width / 2, -cfg.hit.height / 2, cfg.hit.width, cfg.hit.height);
    instance.hitArea = box;

    let dragging = false;
    let activePointer = null;
    let activePointerType = null;
    let multipleTouches = false;
    const touchPointers = new Set();
    let moved = false;
    let startX = 0;
    let startY = 0;
    let offsetX = 0;
    let offsetY = 0;

    function toStage(cx, cy) {
      const r = app.view.getBoundingClientRect();
      return { x: ((cx - r.left) * app.screen.width) / r.width, y: ((cy - r.top) * app.screen.height) / r.height };
    }
    // touch-action 在手势开始前确定：模型表面允许 pinch，背景仍允许 pan-y。
    // 不取消首个 touchstart，否则随后加入第二指也无法恢复原生 pinch。
    function onTouchStart(e) {
      if (e.touches.length > 1) { multipleTouches = true; endDrag(false); }
    }
    function onTouchEnd(e) { if (e.touches.length === 0) multipleTouches = false; }
    function onAdditionalPointer(e) {
      if (e.pointerType !== 'touch') return;
      touchPointers.add(e.pointerId);
      if (touchPointers.size > 1 || (dragging && activePointerType === 'touch' && e.pointerId !== activePointer)) {
        multipleTouches = true;
        endDrag(false);
      }
    }
    function onPointerEnd(e) {
      touchPointers.delete(e.pointerId);
      if (touchPointers.size === 0) multipleTouches = false;
    }
    window.addEventListener('touchstart', onTouchStart, { passive: true, capture: true });
    window.addEventListener('touchend', onTouchEnd, { passive: true, capture: true });
    window.addEventListener('touchcancel', onTouchEnd, { passive: true, capture: true });
    window.addEventListener('pointerdown', onAdditionalPointer, true);
    window.addEventListener('pointerup', onPointerEnd, true);
    window.addEventListener('pointercancel', onPointerEnd, true);
    window.addEventListener('blur', onBlur);
    function onMove(e) {
      if (!dragging || disposed || (e.pointerId ?? 1) !== activePointer) return;
      const p = toStage(e.clientX, e.clientY);
      if (!moved && Math.hypot(p.x - startX, p.y - startY) > PLACEMENT.dragThreshold) moved = true;
      if (!moved) return;
      const area = embedded ? regionInStage() : null;
      if (embedded && (!area || !instance.visible)) { endDrag(false); return; }
      manualPosition = getDraggedModelPosition({ x: p.x + offsetX, y: p.y + offsetY }, app.screen, placement);
      if (embedded) relativePosition = { x: (manualPosition.x - area.left) / area.width, y: (manualPosition.y - area.top) / area.height };
      instance.x = manualPosition.x;
      instance.y = manualPosition.y;
      instance.visible = true;
      syncInteraction(instance);
    }
    function endDrag(triggerTap) {
      if (!dragging) return;
      dragging = false;
      const pointerId = activePointer;
      activePointer = null;
      activePointerType = null;
      instance.cursor = 'grab';
      if (interactionTarget) {
        interactionTarget.style.cursor = 'grab';
        if (interactionTarget.hasPointerCapture?.(pointerId)) interactionTarget.releasePointerCapture(pointerId);
      }
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
      if (triggerTap && !moved) onTap?.();
    }
    function onUp(e) { if ((e.pointerId ?? 1) === activePointer) endDrag(true); }
    function onCancel(e) { if ((e.pointerId ?? 1) === activePointer) endDrag(false); }
    function onBlur() { touchPointers.clear(); multipleTouches = false; endDrag(false); }
    function onDown(e) {
      const original = e.data?.originalEvent || e;
      if (disposed || dragging || multipleTouches || original.isPrimary === false || (original.button ?? 0) !== 0) return;
      const p = e.data?.global || toStage(original.clientX, original.clientY);
      if (embedded && (!visibleBounds || p.x < visibleBounds.left || p.x > visibleBounds.right || p.y < visibleBounds.top || p.y > visibleBounds.bottom)) return;
      activePointer = original.pointerId ?? e.data?.pointerId ?? 1;
      activePointerType = original.pointerType || e.data?.pointerType;
      offsetX = instance.x - p.x;
      offsetY = instance.y - p.y;
      startX = p.x;
      startY = p.y;
      dragging = true;
      moved = false;
      instance.cursor = 'grabbing';
      if (interactionTarget) {
        interactionTarget.style.cursor = 'grabbing';
        interactionTarget.setPointerCapture?.(activePointer);
      }
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
      window.addEventListener('pointercancel', onCancel);
    }
    instance.on('pointerdown', onDown);
    interactionTarget?.addEventListener('pointerdown', onDown);
    interactionTarget?.addEventListener('lostpointercapture', onCancel);
    cancelDrag = () => endDrag(false);

    return () => {
      endDrag(false);
      window.removeEventListener('touchstart', onTouchStart, true);
      window.removeEventListener('touchend', onTouchEnd, true);
      window.removeEventListener('touchcancel', onTouchEnd, true);
      window.removeEventListener('pointerdown', onAdditionalPointer, true);
      window.removeEventListener('pointerup', onPointerEnd, true);
      window.removeEventListener('pointercancel', onPointerEnd, true);
      window.removeEventListener('blur', onBlur);
      interactionTarget?.removeEventListener('pointerdown', onDown);
      interactionTarget?.removeEventListener('lostpointercapture', onCancel);
      instance.off('pointerdown', onDown);
    };
  }

  // 程序化待机动画：「白」的 model3.json 无 Motions / Breath 字段，角色本身不会自动呼吸/摆动，
  // 用 ticker 逐帧正弦驱动 coreModel 参数（呼吸 + 头/身轻微摆动）。驱动哪些参数由运行时
  // coreModel.getParameterIndex 判定，振幅/频率/相位来自 mascotConfig.js 的 IDLE 配置（数据驱动）。
  // 返回 { cleanup, refreshBase }。
  //   setParameterValueById 写的是「基础值」——cubism4 的 update() 会 saveParameters/loadParameters，
  //   focus/呼吸/物理在其上叠加并在帧末复原，因此这里每帧写一次即可（至多一帧延迟，肉眼不可感）。
  function startIdle(instance) {
    const ticker = app.ticker;
    const core = instance.internalModel && instance.internalModel.coreModel;
    if (core) {
      const count = core.getParameterCount();
      const exists = (id) => core.getParameterIndex(id) < count;
      const driven = IDLE.params.filter((p) => exists(p.id));
      if (driven.length) {
        const t0 = performance.now();
        const tick = () => {
          if (!canAnimate()) return;
          const t = (performance.now() - t0) / 1000;
          for (const p of driven) {
            try {
              core.setParameterValueById(p.id, p.base + p.amplitude * Math.sin(t * 2 * Math.PI * p.frequency + p.phase));
            } catch (e) { /* 参数异常：忽略，不阻断其它参数 */ }
          }
        };
        ticker.add(tick);
        return { cleanup() { ticker.remove(tick); }, refreshBase() {} };
      }
    }
    // No container-scale breathing: it would drift outside the clamped bounds
    // and move the DOM hit surface independently of the visual.
    return { cleanup() {}, refreshBase() {} };
  }

  async function loadModel(id) {
    const cfg = MODELS.find((m) => m.id === id) || MODELS[0];
    const modelResources = resources;
    let retired = false;
    let instance;
    try {
      await boundedLoad(() => new Promise((resolve, reject) => {
        // fromSync is the installed library's supported ownership entry point.
        // autoUpdate=false keeps native motion on our controlled application ticker.
        instance = Live2DModel.fromSync(cfg.url, { autoUpdate: false, autoInteract: false,
          onLoad: () => { if (retired) modelResources.release(instance, true); resolve(instance); },
          onError: (error) => { if (retired) modelResources.release(instance, true); reject(error); } });
        instance.on('settingsLoaded', (settings) => settings.textures.forEach((url) => modelResources.addUrl(settings.resolveURL(url))));
      }), signal);
      if (!alive()) { retired = true; modelResources.release(instance, true); return { cfg, instance: null }; }
      instance.autoUpdate = false;
      instance.textures?.forEach((texture) => modelResources.addTexture(texture));
      return { cfg, instance };
    } catch (e) {
      retired = true;
      if (instance) modelResources.release(instance, true);
      console.warn('[mascot] 模型加载失败', cfg.id, e);
      return { cfg, instance: null };
    }
  }

  async function loadFallback(cfg) {
    if (!alive()) return null;
    const sprite = PIXI.Sprite.from(cfg.fallback.url);
    resources = createMascotResources();
    resources.addUrl(cfg.fallback.url); resources.addTexture(sprite.texture);
    const bt = sprite.texture.baseTexture;
    let removeTextureListeners = () => {};
    try {
      if (!bt.valid) await boundedLoad(() => new Promise((resolve, reject) => {
        const loaded = () => resolve(sprite);
        const failed = () => reject(new Error('Fallback texture unavailable'));
        bt.once('loaded', loaded); bt.once('error', failed);
        removeTextureListeners = () => { bt.off('loaded', loaded); bt.off('error', failed); };
      }), signal);
      if (!alive() || !bt.valid) { resources.release(sprite, false); return null; }
      return sprite;
    } catch { resources.release(sprite, false); return null; }
    finally { removeTextureListeners(); }
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
        silhouette?.invalidate();
      }
    } catch (e) { /* 参数异常：忽略 */ }
  }

  // 下载阶段 → 情绪眼（单选）：先清空 stage 全部参数，再置目标为 1；scene 无映射则只清空。
  // 顺带驱动装饰特效（setStageEffect）：完成/出错场景循环播放 edle 特效，其余停止。
  function setStageExpression(scene) {
    currentScene = scene;
    if (embedded) cancelDrag();
    const target = EXPRESSIONS.stage[scene];
    Object.keys(EXPRESSIONS.stage).forEach((key) => setExpression(EXPRESSIONS.stage[key].paramId, 0));
    if (target) setExpression(target.paramId, 1);
    setStageEffect(scene);
  }

  // 装饰特效（EXPRESSIONS.effect → edle.motion3.json，Loop=true）：命中 stages 的场景循环播放，
  // 其余 stopAllMotions。motion() 返回 Promise<boolean>（未找到该 motion 时 resolve false），异常静默忽略。
  function setStageEffect(scene) {
    if (disposed || !available || !current.model || typeof current.model.motion !== 'function') return;
    const { motion, stages } = EXPRESSIONS.effect;
    if (canAnimate() && stages.includes(scene)) {
      Promise.resolve(current.model.motion(motion.group, motion.index, MotionPriority.IDLE)).catch(() => {});
    } else {
      const mm = current.model.internalModel && current.model.internalModel.motionManager;
      if (mm) mm.stopAllMotions();
    }
  }

  // 随机道具：每 interval 毫秒从 pool 随机取一个展示 duration 毫秒后收回。
  //   recover 未清时跳过本轮（防连发）；重复调用只启动一次，destroy 时统一清理。
  function startRandomProps() {
    randomPropsRequested = true;
    if (randomPropsCleanup || !canAnimate() || !available) return;
    let recover = null;
    let activeParam = null;
    const pick = () => {
      if (!canAnimate() || !available) return;
      const pool = EXPRESSIONS.random.pool;
      const item = pool[Math.floor(Math.random() * pool.length)];
      activeParam = item.paramId;
      setExpression(item.paramId, 1);
      recover = setTimeout(() => {
        recover = null;
        setExpression(item.paramId, 0);
        activeParam = null;
      }, EXPRESSIONS.random.duration);
    };
    const timer = setInterval(() => {
      if (!recover) pick();
    }, EXPRESSIONS.random.interval);
    randomPropsCleanup = () => {
      clearInterval(timer);
      if (recover) clearTimeout(recover);
      if (activeParam) setExpression(activeParam, 0);
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
    idle.refreshBase();
  }

  // 初始加载；失败使用静态纹理，保留统一的活动/移动和DOM热区发布接口。
  const loaded = await loadModel(modelId);
  if (!alive()) {
    if (loaded.instance) resources.release(loaded.instance, true);
    return noopMascot();
  }
  if (!loaded.instance) { available = false; loaded.instance = await loadFallback(loaded.cfg); }
  if (!alive() || !loaded.instance) {
    if (loaded.instance) resources.release(loaded.instance, available);
    if (interactionTarget) interactionTarget.style.visibility = 'hidden';
    return noopMascot();
  }
  current.cfg = loaded.cfg;
  current.model = loaded.instance;
  app.view.dataset.mascot = available ? 'live' : 'fallback';
  if (embedded) {
    host = new PIXI.Container(); mask = new PIXI.Graphics();
    app.stage.addChild(host, mask); host.addChild(current.model); host.mask = mask;
  } else app.stage.addChild(current.model);
  place(current.model, current.cfg);
  silhouette = registerMascotSilhouette(interactionTarget, { app, model: current.model, cacheMs: readToken('--mascot-silhouette-cache', 0.15, true) * 1000 });
  detachDrag = makeInteractive(loaded.instance, loaded.cfg);
  idle = startIdle(loaded.instance);
  motionCleanup = startMotion(loaded.instance);

  const handle = {
    isAvailable() { return !disposed && available; },
    hasVisual() { return !disposed; },
    getModelId() { return current.cfg.id; },
    setExpression,
    setStageExpression,
    startRandomProps,
    scaleBy,
    moveBy,
    resetPosition,
    setMotionEnabled(enabled) { motionEnabled = Boolean(enabled); syncMotionState(); },
    resize() {
      if (!disposed && current.model && current.cfg) {
        if (embedded) cancelDrag();
        place(current.model, current.cfg);
        idle.refreshBase();
      }
    },
    destroy() {
      if (disposed) return;
      disposed = true;
      signal?.removeEventListener('abort', handle.destroy);
      motionCleanup();
      silhouette?.destroy();
      idle.cleanup();
      if (randomPropsCleanup) randomPropsCleanup();
      if (detachDrag) detachDrag();   // 结束未完成的拖动并解除 window 监听
      if (interactionTarget) interactionTarget.style.visibility = 'hidden';
      if (host) { host.mask = null; host.removeChild(current.model); app.stage?.removeChild(host); host.destroy({ children: true }); }
      else if (current.model) app.stage?.removeChild(current.model);
      if (current.model) resources.release(current.model, available);
      if (mask) { app.stage?.removeChild(mask); mask.destroy(); }
    },
  };
  signal?.addEventListener('abort', handle.destroy, { once: true });
  if (signal?.aborted) handle.destroy();
  return handle;
}

// app 已销毁时返回的空句柄：所有方法均 no-op
function noopMascot() {
  return {
    isAvailable() { return false; },
    hasVisual() { return false; },
    getModelId() { return DEFAULT_MODEL_ID; },
    setExpression() {},
    setStageExpression() {},
    startRandomProps() {},
    scaleBy() {},
    moveBy() {},
    resetPosition() {},
    setMotionEnabled() {},
    resize() {},
    destroy() {},
  };
}

function toStageRegion(app, region) {
  const rect = app.view.getBoundingClientRect();
  if (!region || ![region.left, region.top, region.width, region.height, rect.width, rect.height].every(Number.isFinite) || region.width <= 0 || region.height <= 0 || rect.width <= 0 || rect.height <= 0) return null;
  return { left: (region.left - rect.left) * app.screen.width / rect.width, top: (region.top - rect.top) * app.screen.height / rect.height,
    width: region.width * app.screen.width / rect.width, height: region.height * app.screen.height / rect.height };
}

// Component tokens are resolved by CSS; defaults also support a headless caller.
function readToken(name, fallback, duration = false) {
  const value = typeof getComputedStyle === 'function' ? getComputedStyle(document.documentElement).getPropertyValue(name).trim() : '';
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return duration && value.endsWith('ms') ? parsed / 1000 : parsed;
}

// The provider loader has no abort API. Bound our wait and dispose late instances
// without touching the application that may already have been destroyed.
function boundedLoad(load, signal, releaseLate = () => {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new Error('Mascot load aborted')); return; }
    let settled = false;
    const finish = (value, error) => {
      if (settled) { if (!error) releaseLate(value); return; }
      settled = true; clearTimeout(timer); signal?.removeEventListener('abort', abort);
      if (error) reject(error); else resolve(value);
    };
    const abort = () => finish(null, new Error('Mascot load aborted'));
    const timer = setTimeout(() => finish(null, new Error('Mascot load timed out')), readToken('--mascot-load-timeout', 8, true) * 1000);
    signal?.addEventListener('abort', abort, { once: true });
    Promise.resolve().then(load).then((value) => finish(value), (error) => finish(null, error));
  });
}
