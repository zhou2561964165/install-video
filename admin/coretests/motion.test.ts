import { readFileSync } from 'node:fs';
import postcss from 'postcss';
import { describe, expect, it } from 'vitest';

// Inspect the actual stylesheet: event-driven rc-motion must retain its names
// while reduced-motion shortens the animation to one imperceptible iteration.
const css = postcss.parse(readFileSync(new URL('../src/global.less', import.meta.url), 'utf8'));
const tokens = new Map<string, string>();
css.walkRules(':root', rule => { rule.walkDecls(declaration => { tokens.set(declaration.prop, declaration.value); }); });
const reduced = new Map<string, string>();
css.walkAtRules('media', media => {
  if (media.params === '(prefers-reduced-motion: reduce)') {
    media.walkDecls(declaration => { reduced.set(declaration.prop, declaration.value); });
  }
});
const resolve = (value: string | undefined, seen = new Set<string>()): string | undefined => {
  const name = value?.match(/^var\((--[\w-]+)\)$/)?.[1];
  if (!name) return value;
  if (seen.has(name)) throw new Error('Cyclic motion token');
  seen.add(name);
  return resolve(tokens.get(name), seen);
};

describe('actual reduced-motion stylesheet lifecycle', () => {
  it('preserves component animation and transition names so end events can fire', () => {
    expect(reduced.size).toBeGreaterThan(0);
    for (const property of ['animation', 'animation-name', 'transition', 'transition-property']) {
      expect(reduced.has(property)).toBe(false);
    }
    expect(resolve(reduced.get('animation-iteration-count'))).toBe('1');
  });
  it('uses positive minimal duration and zero delay via root motion tokens', () => {
    for (const kind of ['animation', 'transition']) {
      expect(reduced.get(`${kind}-duration`)).toMatch(/^var\(--/);
      const duration = resolve(reduced.get(`${kind}-duration`));
      expect(duration).toMatch(/^\d*\.?\d+ms$/);
      expect(Number.parseFloat(duration!)).toBeGreaterThan(0);
      expect(Number.parseFloat(duration!)).toBeLessThanOrEqual(1);
      expect(resolve(reduced.get(`${kind}-delay`))).toBe('0ms');
    }
  });
});

it('resets the actual body margin so measured banner height matches fixed offsets', () => {
  let margin: string | undefined;
  css.walkRules('body', rule => { rule.walkDecls('margin', declaration => { margin = declaration.value; }); });
  expect(resolve(margin)).toBe('0');
});
