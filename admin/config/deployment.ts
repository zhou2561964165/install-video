/** Build-time boundaries; no implicit backend target or rewrite. */
function localPath(value: string, name: string, trailingSlash: boolean): string {
  if (!value.startsWith('/') || value.startsWith('//') || /[?#\\\s\x00-\x1f%]/.test(value) || value.split('/').some(part=>part==='.'||part==='..')) {
    throw new Error(`${name} must be an absolute same-origin path`);
  }
  const normalized = value.replace(/\/+$/, '') || '/';
  return trailingSlash && normalized !== '/' ? `${normalized}/` : normalized;
}

export const isDevelopmentMock=(env:Record<string,string|undefined>)=>env.NODE_ENV==='development'&&env.ADMIN_MOCK==='true';
export function resolveDeployment(env:Record<string,string|undefined>) {
const deployment = {
  // Hash routes remain /users inside the fragment.
  routeBase: localPath(env.ADMIN_ROUTE_BASE || '/', 'ADMIN_ROUTE_BASE', false),
  publicPath: localPath(env.ADMIN_PUBLIC_PATH || '/admin/', 'ADMIN_PUBLIC_PATH', true),
  apiBase: localPath(env.ADMIN_API_BASE || '/api/admin/v1', 'ADMIN_API_BASE', false),
};
const target = env.ADMIN_DEV_PROXY_TARGET;
if (target && !/^https?:\/\/[^/]+\/?$/.test(target)) {
  throw new Error('ADMIN_DEV_PROXY_TARGET must be an explicit HTTP(S) origin');
}
const developmentProxy = env.NODE_ENV === 'development' && target
  ? { [deployment.apiBase]: { target, changeOrigin: false } }
  : undefined;
return {deployment,developmentProxy};
}
export const {deployment,developmentProxy}=resolveDeployment(process.env);
