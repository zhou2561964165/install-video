import { vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve as resolvePath } from 'node:path';

const tokensCss = readFileSync(resolvePath(process.cwd(), 'src/styles/tokens.css'), 'utf8');

// JSDOM leaves var() unresolved. Resolve the real stylesheet's token chain at
// the computed-style boundary, as a browser does; tests exercise production
// callers with a simulated clock rather than supplying a duplicated budget.
export function installMascotLoadTokens() {
  const declarations = new Map([...tokensCss.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]));
  const resolve = (name, seen = new Set()) => {
    if (seen.has(name)) throw new Error(`Cyclic CSS token: ${name}`);
    const next = new Set(seen).add(name);
    return (declarations.get(name) ?? '').replace(/var\((--[\w-]+)\)/g, (_match, child) => resolve(child, next));
  };
  const computedStyle = globalThis.getComputedStyle.bind(window);
  vi.stubGlobal('getComputedStyle', (element, pseudo) => {
    const style = computedStyle(element, pseudo);
    if (element !== document.documentElement) return style;
    return new Proxy(style, { get(target, key) {
      if (key === 'getPropertyValue') return (name) => (target.getPropertyValue(name) || resolve(name)).replace(/var\((--[\w-]+)\)/g, (_match, child) => resolve(child));
      const value = Reflect.get(target, key, target);
      return typeof value === 'function' ? value.bind(target) : value;
    } });
  });
}
