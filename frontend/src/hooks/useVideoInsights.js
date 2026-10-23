import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { exportSubtitle, exportTranscription, generateMindmap, getSubtitle, getTranscriptionCapabilities, summarizeVideo, transcribeVideo, translateSubtitle } from '../api.js';

const emptyState = () => ({
  loading: null,
  error: null,
  active: null,
  subtitle: null,
  translation: null,
  summary: null,
  transcription: null,
  mindmapResult: null,
  subtitleLanguage: null,
  transcriptionLanguage: null,
  errorKind: null,
});

export function useVideoInsights(url, sessionKey) {
  const [state, setState] = useState(emptyState);
  const requestId = useRef(0);
  const controller = useRef(null);

  useLayoutEffect(() => {
    requestId.current += 1;
    setState(emptyState());
    return () => {
      requestId.current += 1;
      controller.current?.abort();
    };
  }, [url, sessionKey]);

  const run = useCallback(async (kind, operation, metadata = {}) => {
    const id = ++requestId.current;
    controller.current?.abort();
    const currentController = new AbortController();
    controller.current = currentController;
    const resultKey = kind === 'mindmap' ? 'mindmapResult' : kind;
    const isExport = kind.endsWith('-export');
    setState((current) => ({
      ...current,
      ...(!isExport ? { [resultKey]: null, active: current.active === kind ? null : current.active } : {}),
      loading: kind,
      error: null,
      errorKind: null,
    }));
    try {
      const value = await operation(currentController.signal);
      if (id !== requestId.current) return;
      setState((current) => ({ ...current, ...(!isExport ? { [resultKey]: value, active: kind, ...metadata } : {}), loading: null }));
      return value;
    } catch (error) {
      if (id !== requestId.current) return;
      setState((current) => ({ ...current, loading: null, error, errorKind: kind.replace('-export', '') }));
    }
  }, []);

  const loadSubtitle = useCallback(
    (language) => run('subtitle', (signal) => getSubtitle(url, language, signal), { subtitleLanguage: language }),
    [run, url],
  );
  const translate = useCallback(
    (sourceLanguage, targetLanguage) => run(
      'translation',
      (signal) => translateSubtitle(url, sourceLanguage, targetLanguage, signal),
    ),
    [run, url],
  );
  const summarize = useCallback(
    (subtitleLanguage, outputLanguage) => run(
      'summary',
      (signal) => summarizeVideo(url, subtitleLanguage, outputLanguage, signal),
    ),
    [run, url],
  );

  const transcribe = useCallback((language) => run('transcription', async (signal) => {
    const capability = await getTranscriptionCapabilities(signal);
    // A superseded capability response must never launch the expensive second request.
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    if (!capability.available) throw { error_type: 'transcription_unavailable', error: capability.reason || '本地音频转写暂不可用。' };
    return transcribeVideo(url, language, signal);
  }, { transcriptionLanguage: language }), [run, url]);

  const mindmap = useCallback((subtitleLanguage, outputLanguage) => run('mindmap', (signal) => generateMindmap(url, subtitleLanguage, outputLanguage, signal)), [run, url]);
  const exportTimedSubtitle = useCallback((format, kind = 'subtitle') => run(`${kind}-export`, (signal) => kind === 'transcription'
    ? exportTranscription(url, state.transcriptionLanguage, format, signal)
    : exportSubtitle(url, state.subtitleLanguage, format, signal)), [run, url, state.transcriptionLanguage, state.subtitleLanguage]);
  const cancel = useCallback(() => {
    requestId.current += 1;
    controller.current?.abort();
    setState((current) => ({ ...current, loading: null, error: null, errorKind: null }));
  }, []);

  return { ...state, loadSubtitle, translate, summarize, transcribe, mindmap, exportTimedSubtitle, cancel };
}
