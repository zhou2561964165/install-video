import { useCallback, useEffect, useRef, useState } from 'react';
import { getSubtitle, summarizeVideo, translateSubtitle } from '../api.js';

const emptyState = () => ({
  loading: null,
  error: null,
  active: null,
  subtitle: null,
  translation: null,
  summary: null,
});

export function useVideoInsights(url) {
  const [state, setState] = useState(emptyState);
  const requestId = useRef(0);
  const controller = useRef(null);

  useEffect(() => {
    requestId.current += 1;
    setState(emptyState());
    return () => {
      requestId.current += 1;
      controller.current?.abort();
    };
  }, [url]);

  const run = useCallback(async (kind, operation) => {
    const id = ++requestId.current;
    controller.current?.abort();
    const currentController = new AbortController();
    controller.current = currentController;
    setState((current) => ({
      ...current,
      [kind]: null,
      active: current.active === kind ? null : current.active,
      loading: kind,
      error: null,
    }));
    try {
      const value = await operation(currentController.signal);
      if (id !== requestId.current) return;
      setState((current) => ({ ...current, [kind]: value, active: kind, loading: null }));
    } catch (error) {
      if (id !== requestId.current) return;
      setState((current) => ({ ...current, loading: null, error }));
    }
  }, []);

  const loadSubtitle = useCallback(
    (language) => run('subtitle', (signal) => getSubtitle(url, language, signal)),
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

  return { ...state, loadSubtitle, translate, summarize };
}
