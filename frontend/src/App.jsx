import React, { useEffect, useReducer, useCallback, useRef, useState } from 'react';
import { reduce, initialState, SCENE } from './state/sceneMachine.js';
import { parseVideo, startDownload, getJob, fileUrl } from './api.js';
import { initStage, destroyStage, webglSupported, detectTier } from './pixi/stage.js';
import { createBackground, intensityForScene } from './pixi/background.js';
import { createMascot } from './pixi/mascot.js';
import { DEFAULT_MODEL_ID } from './pixi/mascotConfig.js';
import EntryScene from './components/EntryScene.jsx';
import ParsingScene from './components/ParsingScene.jsx';
import SelectingScene from './components/SelectingScene.jsx';
import DownloadingScene from './components/DownloadingScene.jsx';
import DoneScene from './components/DoneScene.jsx';
import ErrorScene from './components/ErrorScene.jsx';
import About from './components/ui/About.jsx';
import ExpressionMenu from './components/ui/ExpressionMenu.jsx';
import Preloader from './components/ui/Preloader.jsx';
import { setScene, setMuted as setAudioMuted } from './audio/audioManager.js';

const POLL_MS = 3000; // 轮询间隔：须 ≥2s，后端 /api 限流 30/60s

// 三档主题开关（数据驱动，加档只改这里）
const THEMES = [
  { v: 'light', label: '浅色' },
  { v: 'dark', label: '深色' },
  { v: 'auto', label: '自动' },
];

export default function App() {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);

  const stageRef = useRef(null);
  const bgRef = useRef(null);
  const mascotRef = useRef(null);
  const [webgl] = useState(() => webglSupported());
  const [tier] = useState(() => detectTier());
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light');
  const [muted, setMuted] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [ready, setReady] = useState(false); // Live2D 模型加载完成才隐藏 preloader

  const setThemeTier = useCallback((t) => setTheme(t), []);
  const toggleMute = useCallback(() => setMuted((m) => !m), []);

  // 主题切换：写 data-theme 属性（light/dark/auto），CSS token 随之切换；
  // auto 由 global.css 的 @media (prefers-color-scheme) 解析，无需 JS 监听系统
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

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

  // PIXI 舞台：WebGL 可用时挂载，否则走 CSS 渐变兜底（global.css 里 .css-fallback）
  useEffect(() => {
    if (!webgl) return;
    const app = initStage(stageRef.current);
    const bg = createBackground(app, tier);
    bgRef.current = bg;
    const onResize = () => {
      bg.resize();
      mascotRef.current?.resize();
    };
    window.addEventListener('resize', onResize);
    let stale = false; // StrictMode 双重挂载：旧挂载的 mascot 结果丢弃，不覆盖 ref / 不提前置 ready
    createMascot(app, DEFAULT_MODEL_ID, { onTap: () => setMenuOpen(true) }).then((m) => {
      if (stale) { m.destroy(); return; }
      mascotRef.current = m;
      m.startRandomProps();
      setReady(true);
    });
    return () => {
      stale = true;
      window.removeEventListener('resize', onResize);
      mascotRef.current?.destroy();
      bg.destroy();
      destroyStage(app);
      mascotRef.current = null;
      bgRef.current = null;
    };
  }, [webgl, tier]);

  // 随 scene 切换粒子强度（安静/活跃）
  useEffect(() => {
    bgRef.current?.setIntensity(intensityForScene(state.scene));
  }, [state.scene]);

  // 随 scene 驱动 BGM/SFX 场景（角色表情/动作已取消，状态反馈由粒子+音频承担）
  useEffect(() => {
    setScene(state.scene);
  }, [state.scene]);

  // 随 scene 切换角色情绪眼（解析→圈圈眼、选清晰度/下载→煎蛋眼、完成→星星眼、出错→生气）
  useEffect(() => {
    mascotRef.current?.setStageExpression(state.scene);
  }, [state.scene, webgl]);

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
      <button type="button" className="mute-toggle" aria-pressed={muted} onClick={toggleMute}>静音</button>
      <div className="theme-switch" role="group" aria-label="主题模式">
        {THEMES.map((t) => (
          <button
            key={t.v}
            type="button"
            className="theme-switch__opt"
            aria-pressed={theme === t.v}
            onClick={() => setThemeTier(t.v)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <ExpressionMenu open={menuOpen} onClose={() => setMenuOpen(false)} onExpression={(pid, v) => mascotRef.current?.setExpression(pid, v)} onScale={(dir) => mascotRef.current?.scaleBy(dir)} />
      <About />
      {webgl && <Preloader done={ready} />}
    </>
  );
}
