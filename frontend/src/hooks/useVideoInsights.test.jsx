import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useVideoInsights } from './useVideoInsights.js';

afterEach(() => vi.unstubAllGlobals());

describe('useVideoInsights request lifetime', () => {
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
