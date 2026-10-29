// Derived from ant-design/ant-design-pro config/config.ts; see upstream/README.md.
import { defineConfig } from '@umijs/max';
import defaultSettings from './defaultSettings';
import { deployment, developmentProxy, isDevelopmentMock } from './deployment';
import routes from './routes';

export default defineConfig({
  hash: true,
  // Umi's supported scope isolation prevents cross-chunk esbuild helper clashes.
  esbuildMinifyIIFE: true,
  history: { type: 'hash' },
  base: deployment.routeBase,
  publicPath: deployment.publicPath,
  routes,
  proxy: developmentProxy,
  fastRefresh: true,
  ignoreMomentLocale: true,
  model: {},
  initialState: {},
  title: defaultSettings.title,
  layout: { locale: false, logo:false, iconfontUrl:'', ...defaultSettings },
  // Umi emits the official ConfigProvider only when this option is present.
  // The runtime `antd` hook then supplies our shared theme to that provider.
  antd: {configProvider:{}},
  request: {},
  access: {},
  // Never enable mock in production, regardless of caller environment.
  mock: isDevelopmentMock(process.env)
    ? { exclude: ['mock/fixtures.ts','mock/engine.ts'] }
    : false,
  define: {
    ADMIN_API_BASE: deployment.apiBase,
    ADMIN_MOCK_ENABLED: isDevelopmentMock(process.env),
  },
});
