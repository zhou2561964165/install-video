// Vite supplies the build base, keeping subpath deployments on their own routes.
export const APP_BASE = import.meta.env.BASE_URL;

export function appPath(path) {
  return `${APP_BASE}${path.replace(/^\/+/, '')}`;
}

// Root deployments retain their existing sessions; demos never read or clear them.
export const AUTH_TOKEN_KEY = APP_BASE === '/' ? 'auth_token' : `video-downloader:${APP_BASE}:auth_token`;
