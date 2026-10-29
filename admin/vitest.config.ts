import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)), '@umijs/max': fileURLToPath(new URL('./coretests/umi.ts', import.meta.url)) } },
  test: { include: ['coretests/**/*.test.ts'], environment: 'node', clearMocks: true },
  define: { ADMIN_API_BASE: JSON.stringify('/demo/api/admin/v1'), ADMIN_MOCK_ENABLED: 'false' },
});
