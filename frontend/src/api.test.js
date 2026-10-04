import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  parseVideo, startDownload, getJob, fileUrl, normalizeError, register, login, getMe,
  getSubtitle, translateSubtitle, summarizeVideo, setAuthToken, clearAuthToken,
} from './api.js';

afterEach(() => { vi.restoreAllMocks(); clearAuthToken(); });

describe('api', () => {
  it('parseVideo POSTs to /api/parse and returns json', async () => {
    const json = { title: 'x', formats: [] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(json) }));
    await expect(parseVideo('https://example.com/v')).resolves.toEqual(json);
    expect(fetch).toHaveBeenCalledWith('/api/parse', expect.objectContaining({ method: 'POST' }));
  });

  it('startDownload sends format_id and force_server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ mode: 'server', job_id: '1' }) }));
    await startDownload('https://example.com/v', 'best', true);
    const [, opts] = fetch.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({ url: 'https://example.com/v', format_id: 'best', force_server: true });
  });

  it('getJob hits /api/job/:id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: '1' }) }));
    await getJob('1');
    expect(fetch).toHaveBeenCalledWith('/api/job/1', expect.anything());
  });

  it('fileUrl builds the file endpoint', () => {
    expect(fileUrl('abc')).toBe('/api/file/abc');
  });

  it('normalizeError extracts error_type from detail', async () => {
    const res = { json: () => Promise.resolve({ detail: { error_type: 'quota', error: '请求过于频繁' } }) };
    await expect(normalizeError(res)).resolves.toEqual({ error_type: 'quota', error: '请求过于频繁' });
  });

  it('normalizeError falls back to network', async () => {
    const res = { json: () => Promise.resolve({ detail: { error: '任务不存在' } }) };
    await expect(normalizeError(res)).resolves.toEqual({ error_type: 'network', error: '任务不存在' });
  });

  it('register POSTs to /api/auth/register', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ token: 't', user: { email: 'a@b.com' } }) }));
    await register('a@b.com', 'password123');
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/api/auth/register');
    expect(JSON.parse(opts.body)).toEqual({ email: 'a@b.com', password: 'password123' });
  });

  it('login POSTs to /api/auth/login', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ token: 't', user: {} }) }));
    await login('a@b.com', 'password123');
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/api/auth/login');
    expect(JSON.parse(opts.body)).toEqual({ email: 'a@b.com', password: 'password123' });
  });

  it('getMe hits /api/auth/me', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ user: {}, quota: {} }) }));
    await getMe();
    expect(fetch).toHaveBeenCalledWith('/api/auth/me', expect.anything());
  });

  it('request attaches Authorization header after setAuthToken', async () => {
    setAuthToken('secret-token');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }));
    await getMe();
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBe('Bearer secret-token');
  });

  it('request omits Authorization header when no token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }));
    await getMe();
    const [, opts] = fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBeUndefined();
  });

  it('getSubtitle sends optional language', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ text: 'x' }) }));
    await getSubtitle('https://example.com/v', 'en');
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/api/subtitle');
    expect(JSON.parse(opts.body)).toEqual({ url: 'https://example.com/v', language: 'en' });
  });

  it('translateSubtitle sends source and target languages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ text: '你好' }) }));
    await translateSubtitle('https://example.com/v', 'en', 'zh-CN');
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/api/subtitle/translate');
    expect(JSON.parse(opts.body)).toEqual({
      url: 'https://example.com/v', source_language: 'en', target_language: 'zh-CN',
    });
  });

  it('summarizeVideo sends subtitle and output languages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ summary: '摘要' }) }));
    await summarizeVideo('https://example.com/v', 'en', 'zh-CN');
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe('/api/summary');
    expect(JSON.parse(opts.body)).toEqual({
      url: 'https://example.com/v', subtitle_language: 'en', output_language: 'zh-CN',
    });
  });
});
