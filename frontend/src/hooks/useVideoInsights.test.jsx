import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useVideoInsights } from './useVideoInsights.js';

afterEach(() => vi.unstubAllGlobals());

describe('useVideoInsights request lifetime', () => {
  it('switching accounts clears cached content and rejects the old in-flight response at the same URL', async () => {
    let resolve;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ summary: '旧账号内容' }) }).mockImplementationOnce(() => new Promise((done) => { resolve = done; })));
    const view = renderHook(({ session }) => useVideoInsights('https://example.com/same', session), { initialProps: { session: 'a' } });
    await act(async () => view.result.current.summarize());
    expect(view.result.current.summary.summary).toBe('旧账号内容');
    let pending; act(() => { pending = view.result.current.loadSubtitle(); });
    const signal = fetch.mock.calls[1][1].signal;
    view.rerender({ session: 'b' });
    expect(view.result.current.summary).toBeNull(); expect(signal.aborted).toBe(true);
    await act(async () => { resolve({ ok: true, json: async () => ({ text: '迟到字幕' }) }); await pending; });
    expect(view.result.current.subtitle).toBeNull();
  });
  it('exports the generated language cache without changing results or launching transcription', async () => {
    const subtitle = { text: '字幕', language: 'en', segments: [{ start: 0, end: 1, text: '字幕' }] };
    const transcription = { text: '转写', language: 'zh', segments: [{ start: 0, end: 1, text: '转写' }] };
    vi.stubGlobal('fetch', vi.fn((path) => Promise.resolve({ ok: true, json: async () => {
      if (path.endsWith('/capabilities')) return { available: true };
      if (path === '/api/subtitle') return subtitle;
      if (path === '/api/transcribe') return transcription;
      return { filename: '字幕.vtt', format: 'vtt', content: 'WEBVTT' };
    } })));
    const { result } = renderHook(() => useVideoInsights('https://example.com/v'));
    await act(async () => result.current.loadSubtitle('en'));
    await act(async () => result.current.transcribe('zh-CN'));
    fetch.mockClear();
    await act(async () => result.current.exportTimedSubtitle('vtt', 'subtitle'));
    await act(async () => result.current.exportTimedSubtitle('srt', 'transcription'));
    expect(fetch.mock.calls.map(([path]) => path)).toEqual(['/api/subtitle/export', '/api/transcribe/export']);
    expect(JSON.parse(fetch.mock.calls[0][1].body).language).toBe('en');
    expect(JSON.parse(fetch.mock.calls[1][1].body).language).toBe('zh');
    expect(result.current.subtitle).toEqual(subtitle);
    expect(result.current.transcription).toEqual(transcription);
    expect(result.current.active).toBe('transcription');
  });

  it('cancelling the capability check prevents even an abort-ignoring response from starting ASR', async () => {
    let resolveCapabilities;
    let signal;
    vi.stubGlobal('fetch', vi.fn((_, options) => { signal = options.signal; return new Promise((resolve) => { resolveCapabilities = resolve; }); }));
    const { result } = renderHook(() => useVideoInsights('https://example.com/v'));
    let pending;
    act(() => { pending = result.current.transcribe('en'); });
    act(() => result.current.cancel());
    expect(signal.aborted).toBe(true);
    await act(async () => { resolveCapabilities({ ok: true, json: async () => ({ available: true }) }); await pending; });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(result.current.loading).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.transcription).toBeNull();
  });

  it('suppresses a stale export return value and errors after URL changes', async () => {
    let resolveExport;
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { resolveExport = resolve; })));
    const { result, rerender } = renderHook(({ url }) => useVideoInsights(url), { initialProps: { url: 'https://example.com/old' } });
    let pending;
    act(() => { pending = result.current.exportTimedSubtitle('srt'); });
    rerender({ url: 'https://example.com/new' });
    let file;
    await act(async () => { resolveExport({ ok: true, json: async () => ({ content: '旧字幕' }) }); file = await pending; });
    expect(file).toBeUndefined();
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBeNull();
  });

  it('routes failed cached transcription export to transcription while preserving the text', async () => {
    vi.stubGlobal('fetch', vi.fn((path) => Promise.resolve(path.endsWith('/export')
      ? { ok: false, json: async () => ({ detail: { error_type: 'transcription_unavailable', error: '转写缓存已过期' } }) }
      : { ok: true, json: async () => path.endsWith('/capabilities') ? { available: true } : { text: '已有转写' } })));
    const { result } = renderHook(() => useVideoInsights('https://example.com/v'));
    await act(async () => result.current.transcribe(''));
    await act(async () => result.current.exportTimedSubtitle('srt', 'transcription'));
    expect(result.current.transcription.text).toBe('已有转写');
    expect(result.current.errorKind).toBe('transcription');
    expect(result.current.error.error).toBe('转写缓存已过期');
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('checks ASR availability only on explicit transcription and never silently falls back', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ available: false, reason: '本地转写未启用' }) }));
    const { result } = renderHook(() => useVideoInsights('https://example.com/v'));
    expect(fetch).not.toHaveBeenCalled();
    await act(async () => result.current.transcribe('zh-CN'));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(result.current.transcription).toBeNull();
    expect(result.current.error.error).toBe('本地转写未启用');
  });

  it('preserves subtitle cache during mindmap generation and cancels late transcription after URL change', async () => {
    let resolveCapabilities;
    vi.stubGlobal('fetch', vi.fn((path) => {
      if (path.endsWith('/capabilities')) return new Promise((resolve) => { resolveCapabilities = resolve; });
      return Promise.resolve({ ok: true, json: async () => path === '/api/subtitle' ? { text: '字幕' } : { root: { label: '导图', children: [] } } });
    }));
    const { result, rerender } = renderHook(({ url }) => useVideoInsights(url), { initialProps: { url: 'https://example.com/old' } });
    await act(async () => result.current.loadSubtitle('en'));
    await act(async () => result.current.mindmap('en', 'zh-CN'));
    expect(result.current.subtitle.text).toBe('字幕');
    expect(result.current.mindmapResult.root.label).toBe('导图');
    let pending;
    act(() => { pending = result.current.transcribe('en'); });
    rerender({ url: 'https://example.com/new' });
    await act(async () => { resolveCapabilities({ ok: true, json: async () => ({ available: true }) }); await pending; });
    expect(fetch.mock.calls.map(([path]) => path)).not.toContain('/api/transcribe');
    expect(result.current.transcription).toBeNull();
    expect(result.current.mindmapResult).toBeNull();
  });
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
