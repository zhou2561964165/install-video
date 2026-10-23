import React, { StrictMode } from 'react';
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearAuthToken, getAuthToken } from '../api.js';
import { useAuth } from './useAuth.js';

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve: (body) => resolve({ ok: true, json: async () => body }), reject };
}

const userA = { id: 'a', email: 'a@example.com' };
const userB = { id: 'b', email: 'b@example.com' };
const quotaA = { limit: 10, used: 2, remaining: 8 };
const quotaB = { limit: 20, used: 1, remaining: 19 };

beforeEach(() => { localStorage.clear(); clearAuthToken(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); clearAuthToken(); });

function restoredHook() {
  const pending = [];
  localStorage.setItem('auth_token', 'token-a');
  vi.stubGlobal('fetch', vi.fn((path, options) => {
    const request = deferred();
    pending.push({ ...request, path, options });
    return request.promise;
  }));
  return { ...renderHook(() => useAuth()), pending };
}

async function restore(hook) {
  await act(async () => hook.pending[0].resolve({ user: userA, quota: quotaA }));
  expect(hook.result.current.status).toBe('authed');
}

describe('useAuth session lifetime', () => {
  it('keeps a guest signed out and skips quota refresh without a session', async () => {
    vi.stubGlobal('fetch', vi.fn());
    const { result } = renderHook(() => useAuth());
    expect(result.current.status).toBe('gate');
    await act(async () => result.current.refreshQuota());
    expect(fetch).not.toHaveBeenCalled();
  });

  it('ignores a quota refresh that finishes after logout', async () => {
    const hook = restoredHook();
    await restore(hook);
    let refresh;
    act(() => { refresh = hook.result.current.refreshQuota(); });
    expect(hook.pending[1].options.headers.Authorization).toBe('Bearer token-a');
    act(() => hook.result.current.logout());
    await act(async () => { hook.pending[1].resolve({ quota: quotaA }); await refresh; });
    expect(hook.result.current).toMatchObject({ status: 'gate', user: null, quota: null });
    expect(getAuthToken()).toBeNull();
    expect(localStorage.getItem('auth_token')).toBeNull();
  });

  it('clears the previous quota immediately on account change and rejects its late refresh', async () => {
    const hook = restoredHook();
    await restore(hook);
    let refresh, login;
    act(() => { refresh = hook.result.current.refreshQuota(); });
    act(() => { login = hook.result.current.login('b@example.com', 'password'); });
    await act(async () => hook.pending[2].resolve({ token: 'token-b', user: userB }));
    expect(hook.result.current.user).toEqual(userB);
    expect(hook.result.current.quota).toBeNull();
    expect(hook.pending[3].options.headers.Authorization).toBe('Bearer token-b');
    await act(async () => { hook.pending[3].resolve({ quota: quotaB }); await login; });
    await act(async () => { hook.pending[1].resolve({ quota: quotaA }); await refresh; });
    expect(hook.result.current).toMatchObject({ user: userB, quota: quotaB });
    expect(getAuthToken()).toBe('token-b');
  });

  it.each(['resolve', 'reject'])('ignores an old login quota %s after a newer login', async (outcome) => {
    const hook = restoredHook();
    await restore(hook);
    let first, second;
    act(() => { first = hook.result.current.login('a@example.com', 'password'); });
    await act(async () => hook.pending[1].resolve({ token: 'token-a2', user: userA }));
    act(() => { second = hook.result.current.login('b@example.com', 'password'); });
    await act(async () => hook.pending[3].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[4].resolve({ quota: quotaB }); await second; });
    await act(async () => {
      if (outcome === 'resolve') hook.pending[2].resolve({ quota: quotaA });
      else hook.pending[2].reject(new Error('old quota failed'));
      await first;
    });
    expect(hook.result.current).toMatchObject({ user: userB, quota: quotaB });
  });

  it.each(['resolve', 'reject'])('ignores startup recovery %s after a new login', async (outcome) => {
    const hook = restoredHook();
    let login;
    act(() => { login = hook.result.current.login('b@example.com', 'password'); });
    await act(async () => hook.pending[1].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[2].resolve({ quota: quotaB }); await login; });
    await act(async () => {
      if (outcome === 'resolve') hook.pending[0].resolve({ user: userA, quota: quotaA });
      else hook.pending[0].reject(new Error('old token rejected'));
    });
    expect(hook.result.current).toMatchObject({ status: 'authed', user: userB, quota: quotaB });
    expect(getAuthToken()).toBe('token-b');
    expect(localStorage.getItem('auth_token')).toBe('token-b');
  });

  it.each(['login', 'register'])('does not restore authentication when pending %s finishes after logout', async (method) => {
    const hook = restoredHook();
    await restore(hook);
    let auth;
    act(() => { auth = hook.result.current[method]('b@example.com', 'password'); });
    expect(hook.pending[1].path).toBe(`/api/auth/${method}`);
    act(() => hook.result.current.logout());
    await act(async () => hook.pending[1].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[2]?.resolve({ quota: quotaB }); await auth; });
    expect(hook.result.current).toMatchObject({ status: 'gate', user: null, quota: null });
    expect(getAuthToken()).toBeNull();
    expect(localStorage.getItem('auth_token')).toBeNull();
    expect(hook.pending).toHaveLength(2);
  });

  it('does not let an older authentication attempt replace the latest one', async () => {
    const hook = restoredHook();
    await restore(hook);
    let first, second;
    act(() => { first = hook.result.current.login('a@example.com', 'password'); });
    act(() => { second = hook.result.current.register('b@example.com', 'password'); });
    await act(async () => hook.pending[2].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[3].resolve({ quota: quotaB }); await second; });
    await act(async () => hook.pending[1].resolve({ token: 'token-a2', user: userA }));
    await act(async () => { hook.pending[4]?.resolve({ quota: quotaA }); await first; });
    expect(hook.result.current).toMatchObject({ user: userB, quota: quotaB });
    expect(getAuthToken()).toBe('token-b');
    expect(hook.pending).toHaveLength(4);
  });

  it('uses the latest quota request when responses finish in reverse order', async () => {
    const hook = restoredHook();
    await restore(hook);
    let first, second;
    act(() => { first = hook.result.current.refreshQuota(); });
    act(() => { second = hook.result.current.refreshQuota(); });
    const latest = { ...quotaA, used: 3, remaining: 7 };
    await act(async () => { hook.pending[2].resolve({ quota: latest }); await second; });
    await act(async () => { hook.pending[1].resolve({ quota: quotaA }); await first; });
    expect(hook.result.current.quota).toEqual(latest);
  });

  it('preserves the current quota if its refresh fails', async () => {
    const hook = restoredHook();
    await restore(hook);
    let refresh;
    act(() => { refresh = hook.result.current.refreshQuota(); });
    await act(async () => { hook.pending[1].reject(new Error('offline')); await refresh; });
    expect(hook.result.current.quota).toEqual(quotaA);
  });

  it('rejects an old-token refresh started while the next login is pending', async () => {
    const hook = restoredHook();
    await restore(hook);
    let login, refresh;
    act(() => { login = hook.result.current.login('b@example.com', 'password'); });
    act(() => { refresh = hook.result.current.refreshQuota(); });
    expect(hook.pending[2].options.headers.Authorization).toBe('Bearer token-a');
    await act(async () => hook.pending[1].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[3].resolve({ quota: quotaB }); await login; });
    await act(async () => { hook.pending[2].resolve({ quota: quotaA }); await refresh; });
    expect(hook.result.current).toMatchObject({ user: userB, quota: quotaB });
  });

  it('ignores the login quota response after logout', async () => {
    const hook = restoredHook();
    await restore(hook);
    let login;
    act(() => { login = hook.result.current.login('b@example.com', 'password'); });
    await act(async () => hook.pending[1].resolve({ token: 'token-b', user: userB }));
    act(() => hook.result.current.logout());
    await act(async () => { hook.pending[2].resolve({ quota: quotaB }); await login; });
    expect(hook.result.current).toMatchObject({ status: 'gate', user: null, quota: null });
    expect(getAuthToken()).toBeNull();
    expect(localStorage.getItem('auth_token')).toBeNull();
  });

  it('restores the original session if authentication fails during startup recovery', async () => {
    const hook = restoredHook();
    let failure;
    act(() => { failure = hook.result.current.login('b@example.com', 'password').catch((error) => error); });
    const denied = new Error('login denied');
    await act(async () => { hook.pending[1].reject(denied); expect(await failure).toBe(denied); });
    await restore(hook);
    expect(hook.result.current).toMatchObject({ user: userA, quota: quotaA });
    expect(getAuthToken()).toBe('token-a');
  });

  it('does not cancel a pending login when startup restoration succeeds', async () => {
    const hook = restoredHook();
    let login;
    act(() => { login = hook.result.current.login('b@example.com', 'password'); });
    await restore(hook);
    await act(async () => hook.pending[1].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[2].resolve({ quota: quotaB }); await login; });
    expect(hook.result.current).toMatchObject({ status: 'authed', user: userB, quota: quotaB });
  });

  it('applies registration and its own quota normally', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: 'token-b', user: userB }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ quota: quotaB }) }));
    const { result } = renderHook(() => useAuth());
    await act(async () => result.current.register('b@example.com', 'password'));
    expect(result.current).toMatchObject({ status: 'authed', user: userB, quota: quotaB });
    expect(getAuthToken()).toBe('token-b');
    expect(localStorage.getItem('auth_token')).toBe('token-b');
  });

  it('keeps a login successful with unknown quota if the initial quota fetch fails', async () => {
    const hook = restoredHook();
    await restore(hook);
    let login;
    act(() => { login = hook.result.current.login('b@example.com', 'password'); });
    await act(async () => hook.pending[1].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[2].reject(new Error('quota offline')); await login; });
    expect(hook.result.current).toMatchObject({ status: 'authed', user: userB, quota: null });
  });

  it('clears an invalid startup token', async () => {
    const hook = restoredHook();
    await act(async () => hook.pending[0].reject(new Error('unauthorized')));
    expect(hook.result.current).toMatchObject({ status: 'gate', user: null, quota: null });
    expect(getAuthToken()).toBeNull();
    expect(localStorage.getItem('auth_token')).toBeNull();
  });

  it('ignores startup failure from the discarded StrictMode effect', async () => {
    const pending = [];
    localStorage.setItem('auth_token', 'token-a');
    vi.stubGlobal('fetch', vi.fn(() => { const request = deferred(); pending.push(request); return request.promise; }));
    const { result } = renderHook(() => useAuth(), { wrapper: ({ children }) => <StrictMode>{children}</StrictMode> });
    expect(pending).toHaveLength(2);
    await act(async () => pending[1].resolve({ user: userA, quota: quotaA }));
    await act(async () => pending[0].reject(new Error('discarded request')));
    expect(result.current).toMatchObject({ status: 'authed', user: userA, quota: quotaA });
    expect(getAuthToken()).toBe('token-a');
    expect(localStorage.getItem('auth_token')).toBe('token-a');
  });

  it('ignores pending authentication after hook unmount', async () => {
    const hook = restoredHook();
    await restore(hook);
    let login;
    act(() => { login = hook.result.current.login('b@example.com', 'password'); });
    hook.unmount();
    await act(async () => hook.pending[1].resolve({ token: 'token-b', user: userB }));
    await act(async () => { hook.pending[2]?.resolve({ quota: quotaB }); await login; });
    expect(getAuthToken()).toBe('token-a');
    expect(localStorage.getItem('auth_token')).toBe('token-a');
    expect(hook.pending).toHaveLength(2);
  });
});
