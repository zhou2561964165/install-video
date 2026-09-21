import React, { useEffect, useReducer, useCallback, useRef, useState } from 'react';
import { reduce, initialState, SCENE } from './state/sceneMachine.js';
import { parseVideo, startDownload, getJob, fileUrl } from './api.js';
import { initStage, destroyStage, webglSupported } from './pixi/stage.js';
import { createBackground, intensityForScene } from './pixi/background.js';
import { createMascot } from './pixi/mascot.js';
import EntryScene from './components/EntryScene.jsx';
import ParsingScene from './components/ParsingScene.jsx';
import SelectingScene from './components/SelectingScene.jsx';
import DownloadingScene from './components/DownloadingScene.jsx';
import DoneScene from './components/DoneScene.jsx';
import ErrorScene from './components/ErrorScene.jsx';
import { setScene, setMuted as setAudioMuted } from './audio/audioManager.js';

const POLL_MS = 3000; // 轮询间隔：须 ≥2s，后端 /api 限流 30/60s

export default function App() {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);

  const stageRef = useRef(null);
  const bgRef = useRef(null);
  const mascotRef = useRef(null);
  const [webgl] = useState(() => webglSupported());
  const [muted, setMuted] = useState(false);

  const toggleMute = useCallback(() => setMuted((m) => !m), []);

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

  // PIXI 舞台：WebGL 可用时挂载，缺失时走 CSS 渐变兜底
  useEffect(() => {
    if (!webgl) return;             // 无 WebGL → CSS 渐变兜底（global.css 里加 .css-fallback）
    const app = initStage(stageRef.current);
    const bg = createBackground(app);
    bgRef.current = bg;
    createMascot(app).then((m) => {
      mascotRef.current = m;
      m.setScene(state.scene);
    });
    return () => { mascotRef.current?.destroy(); bg.destroy(); destroyStage(app); };
  }, [webgl]);

  // 随 scene 切换粒子强度（安静/活跃）
  useEffect(() => {
    bgRef.current?.setIntensity(intensityForScene(state.scene));
  }, [state.scene]);

  // 随 scene 驱动 mascot 表情/动作
  useEffect(() => {
    mascotRef.current?.setScene(state.scene);
  }, [state.scene]);

  // 随 scene 驱动 BGM/SFX 场景
  useEffect(() => {
    setScene(state.scene);
  }, [state.scene]);

  // 静音状态同步到音频管理器
  useEffect(() => {
    setAudioMuted(muted);
  }, [muted]);

  let scene;
  switch (state.scene) {
    case SCENE.PARSING: scene = <ParsingScene />; break;
    case SCENE.SELECTING: scene = (
      <SelectingScene
        parseResult={state.parseResult}
        selectedFormat={state.selectedFormat}
        forceServer={state.forceServer}
        onSelect={(format, forceServer) => dispatch({ type: 'SELECT_FORMAT', format, forceServer })}
        onDownload={handleDownload}
      />
    ); break;
    case SCENE.DOWNLOADING: scene = <DownloadingScene job={state.job} mode={state.download?.mode} />; break;
    case SCENE.DONE: scene = <DoneScene job={state.job} fileUrl={state.job && fileUrl(state.job.id)} onReset={() => dispatch({ type: 'RESET' })} />; break;
    case SCENE.ERROR: scene = <ErrorScene error={state.error} onReset={() => dispatch({ type: 'RESET' })} />; break;
    case SCENE.ENTRY:
    default: scene = <EntryScene onSubmit={handleSubmit} />;
  }

  return (
    <>
      <div ref={stageRef} className={webgl ? 'stage' : 'stage css-fallback'} />
      <div className="ui">{scene}</div>
      <button
        type="button"
        className="mute-toggle"
        aria-pressed={muted}
        onClick={toggleMute}
        style={{ position: 'fixed', top: 16, right: 16, zIndex: 10, ...(muted ? { opacity: 0.6 } : {}) }}
      >
        静音
      </button>
    </>
  );
}
