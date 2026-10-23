import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => vi.stubEnv('BASE_URL', '/demo/'));

import { clearAuthToken, fileUrl, getFile, getJob, getMe, parseVideo, setAuthToken } from './api.js';
import { useAuth } from './hooks/useAuth.js';
import { APP_BASE, AUTH_TOKEN_KEY } from './lib/appBase.js';
import { MODELS } from './pixi/mascotConfig.js';

const json = (body) => ({ ok: true, json: async () => body });

beforeEach(() => {
  localStorage.clear();
  clearAuthToken();
  localStorage.setItem('auth_token', 'hermes-session');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  clearAuthToken();
});

describe('/demo deployment boundaries', () => {
  it('keeps API and authenticated downloads under /demo with encoded identifiers', async () => {
    const blob = new Blob(['video']);
    vi.stubGlobal('fetch', vi.fn(async (path) => path.includes('/file/')
      ? { ok: true, headers: new Headers({ 'Content-Disposition': 'attachment; filename="clip.mp4"' }), blob: async () => blob }
      : json({})));
    const signal = new AbortController().signal;
    setAuthToken('demo-token');
    await parseVideo('https://example.com/video', signal);
    await getMe();
    await getJob('id/with spaces', signal);
    expect(fileUrl('id/with spaces')).toBe('/demo/api/file/id%2Fwith%20spaces');
    await expect(getFile('id/with spaces', signal)).resolves.toEqual({ blob, filename: 'clip.mp4' });
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      '/demo/api/parse', '/demo/api/auth/me', '/demo/api/job/id%2Fwith%20spaces', '/demo/api/file/id%2Fwith%20spaces',
    ]);
    for (const [, options] of fetch.mock.calls) expect(options.headers.Authorization).toBe('Bearer demo-token');
    expect(fetch.mock.calls[3][1].signal).toBe(signal);
  });

  it('prefixes model and fallback paths without changing their relative asset locations', () => {
    expect(APP_BASE).toBe('/demo/');
    expect(AUTH_TOKEN_KEY).not.toBe('auth_token');
    expect(MODELS[0].assetPath).toBe('live2d/bai-v1');
    expect(MODELS[0].url).toBe('/demo/live2d/bai-v1/白.model3.json');
    expect(MODELS[0].fallback.url).toBe('/demo/live2d/bai-v1/白.16384/texture_00.png');
  });

  it('ignores a root session when the demo has no saved token', () => {
    vi.stubGlobal('fetch', vi.fn());
    const { result } = renderHook(() => useAuth());
    expect(result.current.status).toBe('gate');
    expect(fetch).not.toHaveBeenCalled();
    expect(localStorage.getItem('auth_token')).toBe('hermes-session');
  });

  it('clears only the demo token after failed startup recovery', async () => {
    localStorage.setItem(AUTH_TOKEN_KEY, 'expired-demo');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('expired')));
    const { result } = renderHook(() => useAuth());
    await act(async () => {});
    expect(result.current.status).toBe('gate');
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem('auth_token')).toBe('hermes-session');
    expect(fetch).toHaveBeenCalledWith('/demo/api/auth/me', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer expired-demo' }),
    }));
  });

  it('stores and removes only the demo session on login and logout', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(json({ token: 'demo-token', user: { id: 'demo' } }))
      .mockResolvedValueOnce(json({ quota: { remaining: 1 } })));
    const { result } = renderHook(() => useAuth());
    await act(async () => result.current.login('demo@example.com', 'test-password'));
    expect(result.current.status).toBe('authed');
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBe('demo-token');
    expect(localStorage.getItem('auth_token')).toBe('hermes-session');
    act(() => result.current.logout());
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem('auth_token')).toBe('hermes-session');
  });
});
