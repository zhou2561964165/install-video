const API_BASE = '/api';

let authToken = null;

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) throw await normalizeError(res);
  return res.json();
}

export function setAuthToken(token) { authToken = token; }
export function clearAuthToken() { authToken = null; }
export function getAuthToken() { return authToken; }

// 后端错误体：{ detail: { error_type, error } } 或 { detail: { error } } 或 { detail: "..." }
export async function normalizeError(res) {
  try {
    const body = await res.json();
    const d = body && body.detail;
    if (d && typeof d === 'object') {
      return { error_type: d.error_type || 'network', error: d.error || String(d) };
    }
    return { error_type: 'network', error: typeof d === 'string' ? d : '请求失败' };
  } catch {
    return { error_type: 'network', error: '请求失败' };
  }
}

export function parseVideo(url) {
  return request('/parse', { method: 'POST', body: JSON.stringify({ url }) });
}

export function startDownload(url, formatId, forceServer = false) {
  return request('/download', {
    method: 'POST',
    body: JSON.stringify({ url, format_id: formatId, force_server: forceServer }),
  });
}

export function getJob(jobId) {
  return request(`/job/${jobId}`);
}

export function fileUrl(jobId) {
  return `${API_BASE}/file/${jobId}`;
}

export function register(email, password) {
  return request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) });
}

export function login(email, password) {
  return request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

export function getMe() {
  return request('/auth/me');
}
