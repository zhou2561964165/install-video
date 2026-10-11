const API_BASE = '/api';

let authToken = null;

async function requestResponse(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) throw await normalizeError(res);
  return res;
}

async function request(path, options = {}) {
  return (await requestResponse(path, options)).json();
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

export function parseVideo(url, signal) {
  return request('/parse', { signal, method: 'POST', body: JSON.stringify({ url }) });
}

export function startDownload(url, formatId, forceServer = false, signal) {
  return request('/download', {
    signal,
    method: 'POST',
    body: JSON.stringify({ url, format_id: formatId, force_server: forceServer }),
  });
}

export function getJob(jobId, signal) {
  return request(`/job/${encodeURIComponent(jobId)}`, { signal });
}

export function fileUrl(jobId) {
  return `${API_BASE}/file/${encodeURIComponent(jobId)}`;
}

// Prefer RFC 5987 UTF-8 names; malformed extended values fall back to filename.
function responseFilename(disposition) {
  let name = '';
  const extended = /(?:^|;)\s*filename\*\s*=\s*UTF-8'[^']*'([^;]*)/i.exec(disposition || '');
  if (extended) {
    try { name = decodeURIComponent(extended[1].trim()); } catch { /* use plain filename */ }
  }
  if (!name) {
    const plain = /(?:^|;)\s*filename\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^;]*))/i.exec(disposition || '');
    name = plain ? (plain[1]?.replace(/\\(.)/g, '$1') ?? plain[2].trim()) : '';
  }
  return name.split(/[\\/]/).pop().replace(/[\u0000-\u001f\u007f]/g, '').trim() || 'download';
}

export async function getFile(jobId, signal) {
  const res = await requestResponse(`/file/${encodeURIComponent(jobId)}`, { signal });
  const filename = responseFilename(res.headers.get('Content-Disposition'));
  return { blob: await res.blob(), filename };
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

export function getSubtitle(url, language, signal) {
  return request('/subtitle', {
    signal,
    method: 'POST',
    body: JSON.stringify({ url, language: language || null }),
  });
}

export function translateSubtitle(url, sourceLanguage, targetLanguage = 'zh-CN', signal) {
  return request('/subtitle/translate', {
    signal,
    method: 'POST',
    body: JSON.stringify({
      url,
      source_language: sourceLanguage || null,
      target_language: targetLanguage,
    }),
  });
}

export function summarizeVideo(url, subtitleLanguage, outputLanguage = 'zh-CN', signal) {
  return request('/summary', {
    signal,
    method: 'POST',
    body: JSON.stringify({
      url,
      subtitle_language: subtitleLanguage || null,
      output_language: outputLanguage,
    }),
  });
}
