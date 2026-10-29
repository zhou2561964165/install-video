import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  parseVideo, startDownload, getJob, fileUrl, normalizeError, register, login, getMe,
  getSubtitle, translateSubtitle, summarizeVideo, setAuthToken, clearAuthToken, getFile,
  exportSubtitle, getTranscriptionCapabilities, transcribeVideo, exportTranscription, generateMindmap,
  getMembershipPlans, getMembership, createCheckout, createBillingPortal,
  getSupportMeta, submitSupportTicket, listSupportTickets,
} from './api.js';

afterEach(() => { vi.restoreAllMocks(); clearAuthToken(); });

describe('api', () => {
  it('uses account authorization and abort signals without accepting client prices or identities for billing', async () => {
    const signal = new AbortController().signal;
    setAuthToken('billing-owner'); vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    await getMembershipPlans(signal); await getMembership(signal); await createCheckout(signal); await createBillingPortal(signal);
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(['/api/membership/plans', '/api/membership', '/api/billing/checkout', '/api/billing/portal']);
    for (const [, options] of fetch.mock.calls) { expect(options.headers.Authorization).toBe('Bearer billing-owner'); expect(options.signal).toBe(signal); expect(options.body).toBeUndefined(); }
    expect(fetch.mock.calls.slice(2).every(([, options]) => options.method === 'POST')).toBe(true);
  });
  it('support calls carry the account bearer and send only category, note and checkout', async () => {
    setAuthToken('support-owner'); vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    await getSupportMeta(); await listSupportTickets();
    await submitSupportTicket({ category: 'other', note: '你好', checkout_id: null, user_id: 'spoofed' });
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(['/api/support/meta', '/api/support/tickets', '/api/support/tickets']);
    expect(fetch.mock.calls[2][1].method).toBe('POST');
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ category: 'other', note: '你好', checkout_id: null });
    for (const [, options] of fetch.mock.calls) expect(options.headers.Authorization).toBe('Bearer support-owner');
  });
  it.each([['zh-TW', 'zh'], ['EN_us', 'en'], ['auto', null], [undefined, null]])('normalizes ASR language %s consistently for generate and cached export', async (input, language) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    await transcribeVideo('https://example.com/v', input);
    await exportTranscription('https://example.com/v', input, 'srt');
    for (const [, options] of fetch.mock.calls) expect(JSON.parse(options.body).language).toBe(language);
  });
  it('content tools preserve bearer, cancellation and their distinct contracts', async () => {
    setAuthToken('content-owner');
    const signal = new AbortController().signal;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    await exportSubtitle('https://example.com/v', 'en', 'vtt', signal);
    await getTranscriptionCapabilities(signal);
    await transcribeVideo('https://example.com/v', 'zh-CN', signal);
    await exportTranscription('https://example.com/v', '', 'srt', signal);
    await generateMindmap('https://example.com/v', 'en', 'ja', signal);
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(['/api/subtitle/export', '/api/transcribe/capabilities', '/api/transcribe', '/api/transcribe/export', '/api/mindmap']);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ url: 'https://example.com/v', language: 'en', format: 'vtt' });
    expect(JSON.parse(fetch.mock.calls[2][1].body).language).toBe('zh');
    expect(JSON.parse(fetch.mock.calls[3][1].body).language).toBeNull();
    expect(JSON.parse(fetch.mock.calls[4][1].body)).toEqual({ url: 'https://example.com/v', subtitle_language: 'en', output_language: 'ja' });
    for (const [, options] of fetch.mock.calls) {
      expect(options.signal).toBe(signal);
      expect(options.headers.Authorization).toBe('Bearer content-owner');
    }
  });
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

  it('startDownload adds an optional idempotency header without changing the body, bearer or signal', async () => {
    const controller = new AbortController();
    setAuthToken('owner-token');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ mode: 'server', job_id: '1' }) }));
    await startDownload('https://example.com/v', 'best', true, controller.signal, 'submission-key');
    expect(fetch).toHaveBeenCalledWith('/api/download', expect.objectContaining({
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer owner-token', 'Idempotency-Key': 'submission-key' },
      body: JSON.stringify({ url: 'https://example.com/v', format_id: 'best', force_server: true }),
    }));
  });

  it.each([undefined, null, ''])('startDownload omits an empty optional key (%s) for older callers', async (key) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    await startDownload('https://example.com/v', 'best', false, undefined, key);
    expect(fetch.mock.calls[0][1].headers).not.toHaveProperty('Idempotency-Key');
  });

  it('getJob hits /api/job/:id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: '1' }) }));
    await getJob('1');
    expect(fetch).toHaveBeenCalledWith('/api/job/1', expect.anything());
  });

  it('getJob forwards cancellation while preserving the bearer header', async () => {
    const controller = new AbortController();
    setAuthToken('owner-token');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 'j' }) }));
    await getJob('j', controller.signal);
    expect(fetch).toHaveBeenCalledWith('/api/job/j', expect.objectContaining({
      signal: controller.signal, headers: expect.objectContaining({ Authorization: 'Bearer owner-token' }),
    }));
  });

  it.each([
    ['attachment; filename="fallback.mp4"; filename*=UTF-8\'\'%E6%B5%8B%E8%AF%95.mp4', '测试.mp4'],
    ['attachment; filename="a clip.mp4"', 'a clip.mp4'],
    ['attachment; filename="fallback.mp4"; filename*=UTF-8\'\'%invalid', 'fallback.mp4'],
    [null, 'download'],
    ['attachment; filename="../unsafe.mp4"', 'unsafe.mp4'],
  ])('fetches the protected file with a safe response filename: %s', async (disposition, filename) => {
    const blob = new Blob(['video']);
    const controller = new AbortController();
    setAuthToken('secret-token');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => blob, headers: new Headers(disposition ? { 'Content-Disposition': disposition } : {}) }));
    await expect(getFile('abc', controller.signal)).resolves.toEqual({ blob, filename });
    expect(fetch).toHaveBeenCalledWith('/api/file/abc', expect.objectContaining({
      signal: controller.signal, headers: expect.objectContaining({ Authorization: 'Bearer secret-token' }),
    }));
    expect(fetch.mock.calls[0][0]).not.toContain('secret-token');
  });

  it.each([401, 404])('surfaces a file HTTP %s through normalizeError without reading a blob', async (status) => {
    const blob = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({ detail: { error: '无权访问文件', error_type: 'login_required' } }), blob }));
    await expect(getFile('hidden')).rejects.toEqual({ error_type: 'login_required', error: '无权访问文件' });
    expect(blob).not.toHaveBeenCalled();
  });

  it('fileUrl builds the file endpoint', () => {
    expect(fileUrl('abc')).toBe('/api/file/abc');
  });

  it('normalizeError extracts error_type from detail', async () => {
    const res = { json: () => Promise.resolve({ detail: { error_type: 'quota', error: '请求过于频繁' } }) };
    await expect(normalizeError(res)).resolves.toEqual({ error_type: 'quota', error: '请求过于频繁' });
  });

  it.each(['complete', null, 'uncertain'])('normalizeError recognizes only the complete idempotency receipt (%s)', async (receipt) => {
    const res = {
      headers: new Headers(receipt ? { 'Idempotency-Status': receipt } : {}),
      json: async () => ({ detail: { error_type: 'quota', error: '请求过于频繁' } }),
    };
    const expected = { error_type: 'quota', error: '请求过于频繁' };
    if (receipt === 'complete') expected.idempotency_complete = true;
    await expect(normalizeError(res)).resolves.toEqual(expected);
  });

  it('normalizeError keeps a complete receipt when the response error body cannot be parsed', async () => {
    const res = { headers: new Headers({ 'Idempotency-Status': 'complete' }), json: async () => { throw new SyntaxError('invalid JSON'); } };
    await expect(normalizeError(res)).resolves.toEqual({ error_type: 'network', error: '请求失败', idempotency_complete: true });
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
