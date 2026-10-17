import React, { useEffect, useRef } from 'react';
import { getMascotSilhouette } from '../../pixi/mascotSilhouette.js';

// 只读表现标记与缓存几何；不依赖业务状态，不增加RAF或渲染舞台。
export default function PointerFollower({ rootRef, enabled = true }) {
  const lensRef = useRef(null);
  useEffect(() => {
    const root = rootRef.current, lens = lensRef.current;
    if (!enabled || !root || !lens || !window.matchMedia) return undefined;
    const backdrop = window.CSS?.supports?.('backdrop-filter', 'invert(1)') || window.CSS?.supports?.('-webkit-backdrop-filter', 'invert(1)');
    if (!backdrop && !window.CSS?.supports?.('mix-blend-mode', 'difference')) return undefined;
    lens.dataset.rendering = backdrop ? 'filter' : 'blend';
    const style = getComputedStyle(document.documentElement);
    const minWidth = style.getPropertyValue('--follow-min-width').trim() || '801px';
    const pointer = window.matchMedia('(hover: hover) and (pointer: fine) and (min-width: ' + minWidth + ')');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const forcedColors = window.matchMedia('(forced-colors: active)');
    // Only these product regions suppress the circle. Normal links, buttons and
    // content outside the central column remain part of the visible cursor area.
    const controls = '.site-header, [data-follow-exclude="parse"]';
    const inactive = (element) => element?.closest?.('[inert], [role="dialog"][aria-hidden="true"]');
    let targets = [], exclusions = [], boundaryElements = [];
    let active = null, lastPointer = null, disposed = false, avoiding = false;
    let radius = 0, enterGap = 0, exitGap = 0, cursorTimer = null;
    const allowed = () => pointer.matches && !reduced.matches && !forcedColors.matches && !document.hidden;
    const clearPlane = () => {
      if (!active) return;
      active.element.removeAttribute('data-follow-active');
      active.element.style.removeProperty('--follow-x'); active.element.style.removeProperty('--follow-y');
      active = null;
    };
    const hide = () => {
      clearPlane(); lens.dataset.active = 'false';
      clearTimeout(cursorTimer); cursorTimer = null;
      document.documentElement.classList.remove('has-pointer-follow');
    };
    const suspend = () => { lastPointer = null; avoiding = false; hide(); };
    const distance = (x, y, rect) => Math.hypot(Math.max(rect.left - x, 0, x - rect.right), Math.max(rect.top - y, 0, y - rect.bottom));
    const move = (event) => {
      lastPointer = { clientX: event.clientX, clientY: event.clientY, pointerType: event.pointerType, buttons: event.buttons };
      if (!allowed() || event.buttons || (event.pointerType && event.pointerType !== 'mouse')) { avoiding = false; hide(); return; }
      const { clientX: x, clientY: y } = event;
      // Position follows the collision circle immediately, including the frame
      // where contact hides it; no old visible circle lingers at a stale point.
      lens.style.setProperty('--cursor-x', x + 'px'); lens.style.setProperty('--cursor-y', y + 'px');
      const gap = avoiding ? exitGap : enterGap;
      const control = event.target?.closest?.(controls);
      const ordinaryControl = control && control.dataset.followExclude !== 'mascot';
      avoiding = Boolean(ordinaryControl && !inactive(control)) || exclusions.some(({ rect, mascot, element }) => {
        if (!mascot) return distance(x, y, rect) <= gap;
        if (distance(x, y, rect) > radius) return false;
        const silhouette = getMascotSilhouette(element);
        return silhouette ? silhouette.overlapsCircle(x, y, radius) : distance(x, y, rect) <= radius;
      });
      // A section's title responds across the full viewport width, including
      // its side gutters; cursor visibility itself has no section boundary.
      const target = targets.find(({ rect }) => y >= rect.top && y <= rect.bottom);
      if (avoiding) { hide(); return; }
      if (active !== target) { clearPlane(); active = target; }
      if (target) {
        const { rect, element } = target;
        const normalize = (value, start, size) => Math.max(-1, Math.min(1, (value - start - size / 2) / Math.max(1, size / 2)));
        const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
        element.style.setProperty('--follow-x', normalize(x, 0, viewportWidth).toFixed(4));
        element.style.setProperty('--follow-y', normalize(y, rect.top, rect.height).toFixed(4));
        element.dataset.followActive = 'true';
      }
      const restoring = lens.dataset.active !== 'true';
      if (restoring) lens.style.transition = 'none';
      if (restoring) {
        void getComputedStyle(lens).transform;
        lens.style.removeProperty('transition'); lens.dataset.active = 'true';
        // 淡入过程中保留原生指针，避免镜片仍透明时两者都不可见。
        const duration = style.getPropertyValue('--cursor-lens-show-duration').trim();
        const delay = (parseFloat(duration) || 0) * (duration.endsWith('ms') ? 1 : 1000);
        cursorTimer = setTimeout(() => {
          cursorTimer = null;
          if (lens.dataset.active === 'true' && allowed()) document.documentElement.classList.add('has-pointer-follow');
        }, delay);
      }
    };
    const refreshBoundaries = () => {
      if (disposed) return;
      exclusions = boundaryElements.flatMap((element) => {
        const computed = getComputedStyle(element), rect = element.getBoundingClientRect();
        if (inactive(element) || computed.display === 'none' || computed.visibility === 'hidden' || !rect.width || !rect.height) return [];
        return [{ element, rect, mascot: element.dataset.followExclude === 'mascot' }];
      });
      if (lastPointer && allowed()) move({ ...lastPointer, target: document.elementFromPoint?.(lastPointer.clientX, lastPointer.clientY) });
      else hide();
    };
    const refresh = () => {
      if (disposed) return;
      clearPlane();
      targets = Array.from(root.querySelectorAll('[data-ui-follow]')).map((element) => {
        let left = 0, top = 0;
        for (let node = element; node; node = node.offsetParent) { left += node.offsetLeft; top += node.offsetTop; }
        left -= window.scrollX; top -= window.scrollY;
        return { element, rect: { left, top, right: left + element.offsetWidth, bottom: top + element.offsetHeight, width: element.offsetWidth, height: element.offsetHeight } };
      });
      const currentStyle = getComputedStyle(document.documentElement);
      enterGap = parseFloat(currentStyle.getPropertyValue('--cursor-lens-enter-gap')) || 0;
      exitGap = parseFloat(currentStyle.getPropertyValue('--cursor-lens-exit-gap')) || enterGap;
      // 未缩放圆形足迹参与碰撞，模型移动只更新排除几何，不重扫标题布局。
      radius = lens.offsetWidth / 2;
      boundaryElements = Array.from(document.querySelectorAll(controls + ', [data-follow-exclude="mascot"]'));
      refreshBoundaries();
    };
    const resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(refresh) : null;
    const boundaryObserver = new MutationObserver(refreshBoundaries);
    const observeTargets = () => {
      if (disposed) return;
      refresh(); resizeObserver?.disconnect(); boundaryObserver.disconnect();
      for (const element of new Set([...targets.map((target) => target.element), ...boundaryElements])) {
        resizeObserver?.observe(element);
        // 仅观察控件/角色属性；镜片与倾斜写style不会反馈成刷新循环。
        if (boundaryElements.includes(element)) boundaryObserver.observe(element, { attributes: true, attributeFilter: ['style', 'hidden', 'class', 'inert', 'aria-hidden', 'data-follow-exclude'] });
      }
      // Responsive mounts insert the model inside the persistent stage, rather
      // than as a direct sibling of the UI root. Observe structure, never its
      // per-frame styles, so newly available silhouettes are included at once.
      for (const stage of root.parentElement?.querySelectorAll('.stage') || []) {
        mutationObserver.observe(stage, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'data-follow-exclude'] });
      }
    };
    const mutationObserver = new MutationObserver(observeTargets);
    mutationObserver.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'data-follow-exclude'] });
    // 舞台和常驻菜单位于uiRef之外；只观察兄弟挂载，不观察全document style。
    if (root.parentElement) mutationObserver.observe(root.parentElement, { childList: true });
    observeTargets();
    const focus = (event) => { if (event.target?.closest?.(controls)) suspend(); };
    const mediaChanged = () => { if (!allowed()) suspend(); };
    const silhouetteChanged = () => {
      if (lastPointer && allowed()) move({ ...lastPointer, target: document.elementFromPoint?.(lastPointer.clientX, lastPointer.clientY) });
    };
    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('pointerdown', suspend, { passive: true });
    window.addEventListener('scroll', refresh, { passive: true });
    window.addEventListener('resize', observeTargets, { passive: true });
    window.addEventListener('blur', suspend);
    document.documentElement.addEventListener('pointerleave', suspend);
    document.addEventListener('focusin', focus); document.addEventListener('visibilitychange', mediaChanged);
    document.addEventListener('mascot-silhouette-change', silhouetteChanged);
    const media = [pointer, reduced, forcedColors];
    for (const query of media) query.addEventListener('change', mediaChanged);
    return () => {
      disposed = true; suspend(); mutationObserver.disconnect(); boundaryObserver.disconnect(); resizeObserver?.disconnect();
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerdown', suspend);
      window.removeEventListener('scroll', refresh); window.removeEventListener('resize', observeTargets); window.removeEventListener('blur', suspend);
      document.documentElement.removeEventListener('pointerleave', suspend);
      document.removeEventListener('focusin', focus); document.removeEventListener('visibilitychange', mediaChanged);
      document.removeEventListener('mascot-silhouette-change', silhouetteChanged);
      for (const query of media) query.removeEventListener('change', mediaChanged);
    };
  }, [enabled, rootRef]);
  return <div ref={lensRef} className="cursor-lens" data-active="false" aria-hidden="true"><div className="cursor-lens__surface" /></div>;
}
