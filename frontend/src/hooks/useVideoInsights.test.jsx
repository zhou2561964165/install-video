import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useVideoInsights } from './useVideoInsights.js';

afterEach(() => vi.unstubAllGlobals());

describe('useVideoInsights request lifetime', () => {
  it('clears the previous summary while a replacement is pending and keeps it cleared after failure', async () => {
    const previousSubtitle = { text: 'cached transcript' };
    const previousSummary = { text: 'cached summary' };
    const replacementError = new Error('replacement failed');
    let summaryRequests = 0;
    let rejectReplacement;
    vi.stubGlobal('fetch', vi.fn((path) => {
      if (path === '/api/subtitle') {
        return Promise.resolve({ ok: true, json: async () => previousSubtitle });
      }
      summaryRequests += 1;
      if (summaryRequests === 1) {
        return Promise.resolve({ ok: true, json: async () => previousSummary });
      }
      return new Promise((_, reject) => { rejectReplacement = reject; });
    }));

    const { result } = renderHook(() => useVideoInsights('https://example.com/v'));
    await act(async () => result.current.loadSubtitle('en'));
    await act(async () => result.current.summarize('en', 'zh-CN'));
    expect(result.current.summary).toEqual(previousSummary);

    let replacementRequest;
    act(() => {
      replacementRequest = result.current.summarize('en', 'zh-CN');
    });

    expect(result.current.loading).toBe('summary');
    expect(result.current.summary).toBeNull();
    expect(result.current.active).toBeNull();
    expect(result.current.subtitle).toEqual(previousSubtitle);

    await act(async () => {
      rejectReplacement(replacementError);
      await replacementRequest;
    });

    expect(result.current.summary).toBeNull();
    expect(result.current.error).toBe(replacementError);
    expect(result.current.subtitle).toEqual(previousSubtitle);
  });

  it('does not let a superseded summary response replace the latest summary', async () => {
    let resolveFirst;
    let summaryRequests = 0;
    vi.stubGlobal('fetch', vi.fn(() => {
      summaryRequests += 1;
      if (summaryRequests === 1) {
        return new Promise((resolve) => { resolveFirst = resolve; });
      }
      return Promise.resolve({ ok: true, json: async () => ({ text: 'latest summary' }) });
    }));

    const { result } = renderHook(() => useVideoInsights('https://example.com/v'));
    let firstRequest;
    act(() => {
      firstRequest = result.current.summarize('en', 'zh-CN');
    });
    await act(async () => result.current.summarize('en', 'zh-CN'));
    await act(async () => {
      resolveFirst({ ok: true, json: async () => ({ text: 'stale summary' }) });
      await firstRequest;
    });

    expect(result.current.summary).toEqual({ text: 'latest summary' });
  });

  it('a response from the previous video cannot replace current results', async () => {
    let resolveOld;
    vi.stubGlobal('fetch', vi.fn((path, options) => {
      const { url } = JSON.parse(options.body);
      if (url === 'https://example.com/old') {
        return new Promise((resolve) => { resolveOld = resolve; });
      }
      return Promise.resolve({ ok: true, json: async () => ({ text: 'current transcript' }) });
    }));
    const { result, rerender } = renderHook(({ url }) => useVideoInsights(url), {
      initialProps: { url: 'https://example.com/old' },
    });
    let oldRequest;
    act(() => { oldRequest = result.current.loadSubtitle('en'); });
    rerender({ url: 'https://example.com/current' });
    await act(async () => result.current.loadSubtitle('en'));
    await act(async () => {
      resolveOld({ ok: true, json: async () => ({ text: 'old transcript' }) });
      await oldRequest;
    });
    expect(result.current.subtitle.text).toBe('current transcript');
  });

  it('unmount cancels an in-flight request', async () => {
    let signal;
    vi.stubGlobal('fetch', vi.fn((path, options) => {
      signal = options.signal;
      return new Promise(() => {});
    }));
    const { result, unmount } = renderHook(() => useVideoInsights('https://example.com/v'));
    act(() => { result.current.summarize('en', 'zh-CN'); });
    await waitFor(() => expect(result.current.loading).toBe('summary'));
    unmount();
    expect(signal?.aborted).toBe(true);
  });
});
