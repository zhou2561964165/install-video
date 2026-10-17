import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import React from 'react';
import { subtractRectangles, useMascotHitArea } from './useMascotHitArea.js';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe('free mascot control priority', () => {
  it('subtracts overlapping controls as a union without re-exposing their overlap', () => {
    const pieces = subtractRectangles({ left: 0, top: 0, right: 100, bottom: 100 }, [
      { left: 20, top: 20, right: 70, bottom: 70 },
      { left: 40, top: 40, right: 80, bottom: 80 },
    ]);
    const contains = (x, y) => pieces.some(r => x > r.left && x < r.right && y > r.top && y < r.bottom);
    expect(contains(50, 50)).toBe(false);
    expect(contains(25, 25)).toBe(false);
    expect(contains(75, 75)).toBe(false);
    expect(contains(10, 10)).toBe(true);
    expect(pieces.reduce((sum, r) => sum + (r.right - r.left) * (r.bottom - r.top), 0)).toBe(6800);
  });
  it('updates native hit clipping as the model moves and restores after unmount', async () => {
    vi.stubGlobal('CSS', { supports: () => true });
    let modelBox = { left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100 };
    const rootRef = { current: null }, targetRef = { current: null };
    function Fixture() {
      useMascotHitArea({ rootRef, targetRef, enabled: true });
      return <><main ref={e => { rootRef.current = e; }}><button ref={e => {
        if (e) e.getBoundingClientRect = () => ({ left: 20, top: 20, right: 70, bottom: 70, width: 50, height: 50 });
      }}>Parse</button></main><div ref={e => {
        targetRef.current = e;
        if (e) e.getBoundingClientRect = () => modelBox;
      }} data-testid="model" /></>;
    }
    const view = render(<Fixture />);
    const target = view.getByTestId('model');
    expect(target.style.clipPath).toContain('path(');
    const previous = target.style.clipPath;
    await act(async () => {
      modelBox = { left: 200, top: 0, right: 300, bottom: 100, width: 100, height: 100 };
      target.style.left = '200px';
    });
    expect(target.style.clipPath).not.toBe(previous);
    expect(target.style.clipPath).toBe('');
    view.unmount();
    expect(target.style.clipPath).toBe('');
  });
});
