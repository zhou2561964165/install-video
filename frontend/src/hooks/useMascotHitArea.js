import { useEffect } from 'react';

// Non-overlapping remainder rectangles avoid even-odd holes reappearing when
// a label overlaps its input. This only clips the DOM hit surface, not the model.
export function subtractRectangles(bounds, blockers) {
  let pieces = [bounds];
  for (const block of blockers) {
    pieces = pieces.flatMap(r => {
      const left = Math.max(r.left, block.left), right = Math.min(r.right, block.right);
      const top = Math.max(r.top, block.top), bottom = Math.min(r.bottom, block.bottom);
      if (left >= right || top >= bottom) return [r];
      return [
        { left: r.left, top: r.top, right: r.right, bottom: top },
        { left: r.left, top: bottom, right: r.right, bottom: r.bottom },
        { left: r.left, top, right: left, bottom },
        { left: right, top, right: r.right, bottom },
      ].filter(p => p.left < p.right && p.top < p.bottom);
    });
  }
  return pieces;
}

export function useMascotHitArea({ rootRef, targetRef, enabled }) {
  useEffect(() => {
    const root = rootRef.current, target = targetRef.current;
    if (!enabled || !root || !target) return undefined;
    const originalClip = target.style.clipPath, originalPointer = target.style.pointerEvents;
    const supportsPath = window.CSS?.supports?.('clip-path', 'path("M0 0H1V1H0Z")');
    let controls = [], previousBounds = '', disposed = false;
    const refresh = (force = false) => {
      if (disposed) return;
      const r = target.getBoundingClientRect();
      const key = [r.left, r.top, r.width, r.height].join(',');
      if (!force && key === previousBounds) return;
      previousBounds = key;
      if (r.width <= 0 || r.height <= 0) return;
      const blockers = controls.flatMap(element => {
        if (element.closest('[hidden], [inert]')) return [];
        const box = element.getBoundingClientRect();
        if (!box.width || !box.height || box.right <= r.left || box.left >= r.right || box.bottom <= r.top || box.top >= r.bottom) return [];
        const style = getComputedStyle(element);
        return style.display === 'none' || style.visibility === 'hidden' ? [] : [{
          left: box.left - r.left, right: box.right - r.left,
          top: box.top - r.top, bottom: box.bottom - r.top,
        }];
      });
      let clip = originalClip, pointer = originalPointer;
      if (blockers.length) {
        if (supportsPath) {
          const pieces = subtractRectangles({ left: 0, top: 0, right: r.width, bottom: r.height }, blockers);
          const path = pieces.map(b => `M${b.left} ${b.top}H${b.right}V${b.bottom}H${b.left}Z`).join(' ');
          clip = `path("${path || 'M0 0'}")`;
        } else pointer = 'none'; // Controls remain usable; persistent menu still moves the character.
      }
      if (target.style.clipPath !== clip) target.style.clipPath = clip;
      if (target.style.pointerEvents !== pointer) target.style.pointerEvents = pointer;
    };
    const collect = () => {
      controls = Array.from(root.querySelectorAll('button, input, select, textarea, a, label, [role="button"]'));
      refresh(true);
    };
    const surfaceObserver = new MutationObserver(() => refresh());
    const contentObserver = new MutationObserver(collect);
    const resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(collect) : null;
    surfaceObserver.observe(target, { attributes: true, attributeFilter: ['style', 'hidden'] });
    contentObserver.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'class', 'disabled'] });
    resizeObserver?.observe(root);
    window.addEventListener('scroll', collect, { passive: true });
    window.addEventListener('resize', collect, { passive: true });
    collect();
    return () => {
      disposed = true;
      surfaceObserver.disconnect(); contentObserver.disconnect(); resizeObserver?.disconnect();
      window.removeEventListener('scroll', collect); window.removeEventListener('resize', collect);
      target.style.clipPath = originalClip; target.style.pointerEvents = originalPointer;
    };
  }, [rootRef, targetRef, enabled]);
}
