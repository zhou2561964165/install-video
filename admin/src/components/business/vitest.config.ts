import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  resolve: { alias: { '@': fileURLToPath(new URL('../../', import.meta.url)) } },
  test: { include: ['src/components/business/**/*.test.ts', 'src/pages/Support/**/*.test.ts'], environment: 'node', clearMocks: true },
});
