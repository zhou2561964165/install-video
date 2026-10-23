// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { build } from 'vite';
import { resolve } from 'node:path';

describe('production pointer filter', () => {
  it('retains the standard backdrop filter in the minified lens rule', async () => {
    const result = await build({
      root: process.cwd(), configFile: resolve(process.cwd(), 'vite.config.js'),
      envDir: false, publicDir: false, base: '/demo/', logLevel: 'silent',
      build: { write: false, emptyOutDir: false, sourcemap: false },
    });
    const outputs = (Array.isArray(result) ? result : [result]).flatMap((bundle) => bundle.output);
    const css = outputs.filter((asset) => asset.type === 'asset' && asset.fileName.endsWith('.css')).map((asset) => String(asset.source)).join('\n');
    const rule = css.match(/\.cursor-lens\[data-rendering=["']?filter["']?\]\s+\.cursor-lens__surface\s*\{([^}]+)\}/)?.[1];
    expect(rule).toBeTruthy();
    // Prefixed-only CSS leaves modern Chrome's transparent surface invisible.
    expect(rule).toMatch(/(?:^|;)backdrop-filter:var\(--cursor-lens-filter\)/);
    expect(rule).toMatch(/(?:^|;)-webkit-backdrop-filter:var\(--cursor-lens-filter\)/);
  }, 20000);
});
