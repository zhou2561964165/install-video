import React, { useEffect, useReducer, useCallback } from 'react';
import { reduce, initialState, SCENE } from './state/sceneMachine.js';
import { parseVideo, startDownload, getJob, fileUrl } from './api.js';
import EntryScene from './components/EntryScene.jsx';
import ParsingScene from './components/ParsingScene.jsx';
import SelectingScene from './components/SelectingScene.jsx';
import DownloadingScene from './components/DownloadingScene.jsx';
import DoneScene from './components/DoneScene.jsx';
import ErrorScene from './components/ErrorScene.jsx';

const POLL_MS = 3000; // 轮询间隔：须 ≥2s，后端 /api 限流 30/60s

export default function App() {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);

  const handleSubmit = useCallback(async (url) => {
    dispatch({ type: 'SUBMIT_URL', url });
    try {
      const payload = await parseVideo(url);
      dispatch({ type: 'PARSE_SUCCESS', payload });
    } catch (e) {
      dispatch({ type: 'PARSE_FAIL', error: e });
    }
  }, []);

  const handleDownload = useCallback(async () => {
    const { url, selectedFormat, forceServer } = state;
    try {
      const d = await startDownload(url, selectedFormat.format_id, forceServer);
      dispatch({ type: 'START_DOWNLOAD', download: d });
      if (d.mode === 'direct' && d.url) {
        // 直链：直接触发浏览器下载（新窗口/隐藏 iframe）
        window.location.assign(d.url);
      }
    } catch (e) {
      dispatch({ type: 'DOWNLOAD_FAIL', error: e });
    }
  }, [state]);

  // 服务端模式：轮询 job
  useEffect(() => {
    if (state.scene !== SCENE.DOWNLOADING || !state.download || state.download.mode !== 'server') return;
    let timer;
    const tick = async () => {
      try {
        const job = await getJob(state.download.job_id);
        dispatch({ type: 'DOWNLOAD_PROGRESS', job });
        if (job.status === 'done' || job.status === 'error') return;
        timer = setTimeout(tick, POLL_MS);
      } catch (e) {
        dispatch({ type: 'DOWNLOAD_FAIL', error: e });
      }
    };
    timer = setTimeout(tick, POLL_MS);
    return () => clearTimeout(timer);
  }, [state.scene, state.download]);

  switch (state.scene) {
    case SCENE.PARSING: return <ParsingScene />;
    case SCENE.SELECTING: return (
      <SelectingScene
        parseResult={state.parseResult}
        selectedFormat={state.selectedFormat}
        forceServer={state.forceServer}
        onSelect={(format, forceServer) => dispatch({ type: 'SELECT_FORMAT', format, forceServer })}
        onDownload={handleDownload}
      />
    );
    case SCENE.DOWNLOADING: return <DownloadingScene job={state.job} mode={state.download?.mode} />;
    case SCENE.DONE: return <DoneScene job={state.job} fileUrl={state.job && fileUrl(state.job.id)} onReset={() => dispatch({ type: 'RESET' })} />;
    case SCENE.ERROR: return <ErrorScene error={state.error} onReset={() => dispatch({ type: 'RESET' })} />;
    case SCENE.ENTRY:
    default: return <EntryScene onSubmit={handleSubmit} />;
  }
}
