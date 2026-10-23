import React, { useReducer } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useDownload } from './useDownload.js';
import { initialState, reduce, SCENE } from '../state/sceneMachine.js';
import { POLL_MS } from '../state/downloadConfig.js';
import { clearAuthToken, setAuthToken } from '../api.js';

const selected = () => ({ ...initialState(), scene: SCENE.SELECTING, url: 'https://example.com/v', selectedFormat: { format_id: 'best' } });
const server = () => ({ ...selected(), scene: SCENE.DOWNLOADING, download: { mode: 'server', job_id: 'j1' } });
const done = () => ({ ...server(), scene: SCENE.DONE, job: { id: 'j1', status: 'done' } });
const json = (value) => ({ ok: true, json: async () => value });
const file = () => ({ ok: true, blob: async () => new Blob(['video']), headers: new Headers({ 'Content-Disposition': 'attachment; filename*=UTF-8\'\'%E6%B5%8B%E8%AF%95.mp4' }) });
const deferred = () => { let resolve; let reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
let clicks;

function mount(seed = server(), session = 'u1') {
  return renderHook(({ identity }) => {
    const [state, dispatch] = useReducer(reduce, seed);
    return { ...useDownload(state, dispatch, identity), state, dispatch };
  }, { initialProps: { identity: session } });
}

// App's error recovery cancels, resets, parses again, then selects a format.
function selectAgain(view, { url = selected().url, formatId = 'best', forceServer = selected().forceServer } = {}) {
  act(() => { view.result.current.cancel(); view.result.current.dispatch({ type: 'RESET' }); });
  act(() => view.result.current.dispatch({ type: 'SUBMIT_URL', url }));
  act(() => {
    view.result.current.dispatch({ type: 'PARSE_SUCCESS', payload: { formats: [{ format_id: formatId }] } });
    view.result.current.dispatch({ type: 'SELECT_FORMAT', format: { format_id: formatId }, forceServer });
  });
}

const submissionKey = (index = 0) => fetch.mock.calls[index][1].headers['Idempotency-Key'];

beforeEach(() => {
  vi.useFakeTimers();
  setAuthToken('owner-token');
  clicks = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { clicks.push({ url: this.href, filename: this.download }); });
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:saved-video'), revokeObjectURL: vi.fn() }));
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); clearAuthToken(); });

describe('useDownload submission idempotency', () => {
  it('reuses the uncertain submission key through App cancel/RESET/reparse without automatically retrying', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('connection lost')).mockResolvedValue(json({ mode: 'server', job_id: 'j1' })));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    expect(key).toEqual(expect.any(String));
    expect(key.length).toBeGreaterThan(0);
    expect(view.result.current.state.scene).toBe(SCENE.ERROR);
    selectAgain(view);
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS * 2));
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).toBe(key);
    expect(view.result.current.state.download.job_id).toBe('j1');
  });

  it.each(['network', 'idempotency_in_progress', 'idempotency_uncertain'])('retains the same key after an uncertain %s response', async (errorType) => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: { error_type: errorType, error: 'try later' } }) })
      .mockResolvedValue(json({ mode: 'server', job_id: 'j1' })));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    expect(key).toEqual(expect.any(String));
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).toBe(key);
  });

  it.each([
    ['network', 'quota', 429],
    ['network', 'idempotency_unavailable', 503],
    ['abort', 'quota', 429],
    ['abort', 'idempotency_unavailable', 503],
  ])('keeps the %s submission key through a later pre-receipt %s rejection', async (initialFailure, errorType, status) => {
    const pending = deferred();
    const network = vi.fn();
    if (initialFailure === 'abort') network.mockReturnValueOnce(pending.promise);
    else network.mockRejectedValueOnce(new TypeError('response lost after dispatch'));
    network.mockResolvedValueOnce({ ok: false, status, json: async () => ({ detail: { error_type: errorType, error: 'rejected before receipt lookup' } }) });
    network.mockResolvedValue(json({ mode: 'server', job_id: 'original-job' }));
    vi.stubGlobal('fetch', network);
    const view = mount(selected());
    let first;
    if (initialFailure === 'abort') act(() => { first = view.result.current.startDownload(); });
    else await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(view.result.current.state.error.error_type).toBe(errorType);
    expect(submissionKey(1)).toBe(key);
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(2)).toBe(key);
    expect(view.result.current.state.download.job_id).toBe('original-job');
    if (initialFailure === 'abort') {
      await act(async () => { pending.resolve(json({ mode: 'server', job_id: 'stale' })); await first; });
      expect(view.result.current.state.download.job_id).toBe('original-job');
    }
  });

  it.each(['idempotency_conflict', 'idempotency_expired'])('releases an uncertain key after an authoritative %s response', async (errorType) => {
    vi.stubGlobal('fetch', vi.fn()
      .mockRejectedValueOnce(new TypeError('response lost after dispatch'))
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: { error_type: errorType, error: 'receipt cannot be replayed' } }) })
      .mockResolvedValue(json({ mode: 'server', job_id: 'new-job' })));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).toBe(key);
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(2)).not.toBe(key);
    expect(view.result.current.state.download.job_id).toBe('new-job');
  });

  it('releases an uncertain key when a retried quota failure has a complete receipt', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockRejectedValueOnce(new TypeError('response lost after dispatch'))
      .mockResolvedValueOnce({
        ok: false, status: 429, headers: new Headers({ 'Idempotency-Status': 'complete' }),
        json: async () => ({ detail: { error_type: 'quota', error: 'persisted quota rejection' } }),
      })
      .mockResolvedValue(json({ mode: 'server', job_id: 'new-job' })));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).toBe(key);
    expect(view.result.current.state.error.error_type).toBe('quota');
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(2)).not.toBe(key);
    expect(view.result.current.state.download.job_id).toBe('new-job');
  });

  it.each([
    ['url', { url: 'https://example.com/other' }],
    ['format', { formatId: '720p' }],
    ['forceServer', { forceServer: !selected().forceServer }],
  ])('uses a new key when the submission %s changes', async (_name, change) => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('connection lost')));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    expect(key).toEqual(expect.any(String));
    selectAgain(view, change);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).toEqual(expect.any(String));
    expect(submissionKey(1)).not.toBe(key);
  });

  it.each(['quota', 'idempotency_conflict', 'idempotency_expired', 'idempotency_unavailable'])('starts a new submission after a definite %s failure', async (errorType) => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: { error_type: errorType, error: 'rejected' } }) })
      .mockResolvedValue(json({ mode: 'server', job_id: 'j1' })));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    expect(key).toEqual(expect.any(String));
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).not.toBe(key);
  });

  it('uses a new key for an explicit new download after a known successful submission', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ mode: 'server', job_id: 'j1' })));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    expect(key).toEqual(expect.any(String));
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).not.toBe(key);
  });

  it('clears an uncertain submission on account change even when returning to the old account', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('connection lost')));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    const key = submissionKey();
    expect(key).toEqual(expect.any(String));
    view.rerender({ identity: 'u2' });
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(1)).not.toBe(key);
    view.rerender({ identity: 'u1' });
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(submissionKey(2)).not.toBe(key);
    expect(submissionKey(2)).not.toBe(submissionKey(1));
  });

  it('keeps an aborted submission key and ignores its late response after a new retry has started', async () => {
    const stale = deferred();
    const retry = deferred();
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(stale.promise).mockReturnValueOnce(retry.promise));
    const view = mount(selected());
    let first;
    act(() => { first = view.result.current.startDownload(); });
    const key = submissionKey();
    expect(key).toEqual(expect.any(String));
    const signal = fetch.mock.calls[0][1].signal;
    selectAgain(view);
    let second;
    act(() => { second = view.result.current.startDownload(); view.result.current.startDownload(); });
    expect(signal.aborted).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(submissionKey(1)).toBe(key);
    await act(async () => { stale.resolve(json({ mode: 'server', job_id: 'stale' })); await first; });
    expect(view.result.current.state.download).toBeNull();
    await act(async () => { retry.resolve(json({ mode: 'server', job_id: 'current' })); await second; });
    expect(view.result.current.state.download.job_id).toBe('current');
  });

  it('prefers Web Crypto randomUUID for keys and falls back to getRandomValues without it', async () => {
    const randomUUID = vi.fn(() => '12345678-1234-4123-8123-123456789abc');
    vi.stubGlobal('crypto', { randomUUID });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ mode: 'server', job_id: 'j1' })));
    const view = mount(selected());
    await act(async () => view.result.current.startDownload());
    expect(submissionKey()).toBe('12345678-1234-4123-8123-123456789abc');
    expect(randomUUID).toHaveBeenCalledTimes(1);
    const getRandomValues = vi.fn((bytes) => bytes.fill(17));
    vi.stubGlobal('crypto', { getRandomValues });
    selectAgain(view);
    await act(async () => view.result.current.startDownload());
    expect(getRandomValues).toHaveBeenCalledTimes(1);
    expect(submissionKey(1)).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(submissionKey(1)).not.toBe(submissionKey());
  });
});

describe('useDownload authenticated saves and request lifetime', () => {
  it('polls with bearer, enters DONE and automatically saves once; manual save reuses the owned Blob URL', async () => {
    vi.stubGlobal('fetch', vi.fn((path) => Promise.resolve(path.startsWith('/api/job/') ? json({ id: 'j1', status: 'done' }) : file())));
    const { result, rerender, unmount } = mount();
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(result.current.state.scene).toBe(SCENE.DONE);
    expect(clicks).toEqual([{ url: 'blob:saved-video', filename: '测试.mp4' }]);
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(['/api/job/j1', '/api/file/j1']);
    expect(fetch.mock.calls.every(([, opts]) => opts.headers.Authorization === 'Bearer owner-token')).toBe(true);
    rerender({ identity: 'u1' });
    expect(clicks).toHaveLength(1);
    await act(async () => result.current.save());
    expect(clicks).toHaveLength(2);
    expect(fetch).toHaveBeenCalledTimes(2);
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:saved-video');
  });

  it('reports failed auto-save without changing DONE and allows a deliberate retry', async () => {
    let requests = 0;
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(++requests === 1
      ? { ok: false, status: 404, json: async () => ({ detail: { error: '文件不存在' } }) }
      : file())));
    const { result } = mount(done());
    await act(async () => {});
    expect(result.current.state.scene).toBe(SCENE.DONE);
    expect(result.current.saveError?.error).toBe('文件不存在');
    expect(clicks).toHaveLength(0);
    await act(async () => result.current.save());
    expect(result.current.saveError).toBeNull();
    expect(clicks).toHaveLength(1);
    expect(requests).toBe(2);
  });

  it('deduplicates concurrent automatic/manual saves and exposes busy state', async () => {
    const pending = deferred();
    vi.stubGlobal('fetch', vi.fn(() => pending.promise));
    const { result } = mount(done());
    expect(result.current.saveBusy).toBe(true);
    await act(async () => { result.current.save(); result.current.save(); });
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve(file()));
    expect(result.current.saveBusy).toBe(false);
    expect(clicks).toHaveLength(1);
  });

  it.each(['cancel', 'RESET', 'account', 'unmount'])('ignores a pending file response after %s and aborts its request', async (kind) => {
    const pending = deferred();
    vi.stubGlobal('fetch', vi.fn(() => pending.promise));
    const view = mount(done());
    const signal = fetch.mock.calls[0][1].signal;
    if (kind === 'cancel') act(() => view.result.current.cancel());
    if (kind === 'RESET') act(() => view.result.current.dispatch({ type: 'RESET' }));
    if (kind === 'account') view.rerender({ identity: 'u2' });
    if (kind === 'unmount') view.unmount();
    await act(async () => pending.resolve(file()));
    expect(signal.aborted).toBe(true);
    expect(clicks).toHaveLength(0);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('ignores a Blob body that completes after the account changes', async () => {
    const body = deferred();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ...file(), blob: () => body.promise }));
    const view = mount(done());
    await act(async () => {});
    view.rerender({ identity: 'u2' });
    await act(async () => body.resolve(new Blob(['stale'])));
    expect(clicks).toHaveLength(0);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it.each(['RESET', 'account', 'unmount'])('does not dispatch a late poll or save after %s', async (kind) => {
    const pending = deferred();
    vi.stubGlobal('fetch', vi.fn(() => pending.promise));
    const view = mount();
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    const signal = fetch.mock.calls[0][1].signal;
    if (kind === 'RESET') act(() => view.result.current.dispatch({ type: 'RESET' }));
    if (kind === 'account') view.rerender({ identity: 'u2' });
    if (kind === 'unmount') view.unmount();
    await act(async () => pending.resolve(json({ id: 'j1', status: 'done' })));
    expect(signal.aborted).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(clicks).toHaveLength(0);
    if (kind !== 'unmount') expect(view.result.current.state.job).toBeNull();
  });

  it('surfaces unauthorized polling through the error scene', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: { error_type: 'login_required', error: '请登录' } }) }));
    const { result } = mount();
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(result.current.state.scene).toBe(SCENE.ERROR);
    expect(result.current.state.error.error).toBe('请登录');
  });

  it.each(['cancel', 'RESET', 'account', 'unmount'])('ignores a late download start after %s', async (kind) => {
    const pending = deferred();
    vi.stubGlobal('fetch', vi.fn(() => pending.promise));
    const view = mount(selected());
    let request;
    act(() => { request = view.result.current.startDownload(); });
    const signal = fetch.mock.calls[0][1].signal;
    if (kind === 'cancel') act(() => view.result.current.cancel());
    if (kind === 'RESET') act(() => view.result.current.dispatch({ type: 'RESET' }));
    if (kind === 'account') view.rerender({ identity: 'u2' });
    if (kind === 'unmount') view.unmount();
    await act(async () => { pending.resolve(json({ mode: 'server', job_id: 'old' })); await request; });
    expect(signal.aborted).toBe(true);
    if (kind !== 'unmount') expect(view.result.current.state.download).toBeNull();
  });

  it('deduplicates repeated starts before the first response', async () => {
    const pending = deferred();
    vi.stubGlobal('fetch', vi.fn(() => pending.promise));
    const { result } = mount(selected());
    let request;
    act(() => { request = result.current.startDownload(); result.current.startDownload(); });
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => { pending.resolve(json({ mode: 'server', job_id: 'j1' })); await request; });
    expect(result.current.state.download.job_id).toBe('j1');
  });

  it('releases the cached URL on RESET', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(file()));
    const { result } = mount(done());
    await act(async () => {});
    act(() => result.current.dispatch({ type: 'RESET' }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:saved-video');
  });

  it('cancel before the poll timer fires makes no network request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ id: 'j1', status: 'done' })));
    const { result } = mount();
    act(() => result.current.cancel());
    await act(async () => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(fetch).not.toHaveBeenCalled();
  });

  it('StrictMode disposes its aborted first attempt and saves the current job only once', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(file()));
    const { unmount } = renderHook(() => {
      const [state, dispatch] = useReducer(reduce, done());
      return useDownload(state, dispatch, 'u1');
    }, { wrapper: React.StrictMode });
    await act(async () => {});
    expect(clicks).toEqual([{ url: 'blob:saved-video', filename: '测试.mp4' }]);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  });

  it('a browser save exception is visible and manual retry uses the existing Blob', async () => {
    let fail = true;
    HTMLAnchorElement.prototype.click.mockImplementation(function () {
      if (fail) throw new Error('browser save blocked');
      clicks.push({ url: this.href, filename: this.download });
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(file()));
    const { result } = mount(done());
    await act(async () => {});
    expect(result.current.saveError.error).toBe('browser save blocked');
    expect(result.current.state.scene).toBe(SCENE.DONE);
    fail = false;
    await act(async () => result.current.save());
    expect(result.current.saveError).toBeNull();
    expect(clicks).toHaveLength(1);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('releases a saved Blob when changing the account', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(file()));
    const view = mount(done());
    await act(async () => {});
    view.rerender({ identity: 'u2' });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:saved-video');
    expect(view.result.current.state.scene).toBe(SCENE.ENTRY);
    expect(clicks).toHaveLength(1);
  });
});
