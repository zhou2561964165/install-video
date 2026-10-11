import React, { useEffect, useLayoutEffect, useReducer, useCallback, useRef, useState } from 'react';
import { reduce, initialState, SCENE } from './state/sceneMachine.js';
import { parseVideo } from './api.js';
import { useDownload } from './hooks/useDownload.js';
import { useAuth } from './hooks/useAuth.js';
import { useVideoInsights } from './hooks/useVideoInsights.js';
import { normalizeParse } from './lib/videoAdapter.js';
import { initStage, destroyStage, webglSupported, detectTier } from './pixi/stage.js';
import { createBackground, intensityForScene } from './pixi/background.js';
import { createMascot } from './pixi/mascot.js';
import { DEFAULT_MODEL_ID } from './pixi/mascotConfig.js';
import EntryScene from './components/EntryScene.jsx';
import AuthScene from './components/AuthScene.jsx';
import AuthBar from './components/ui/AuthBar.jsx';
import ParsingScene from './components/ParsingScene.jsx';
import SelectingScene from './components/SelectingScene.jsx';
import DownloadingScene from './components/DownloadingScene.jsx';
import DoneScene from './components/DoneScene.jsx';
import ErrorScene from './components/ErrorScene.jsx';
import ExpressionMenu from './components/ui/ExpressionMenu.jsx';
import Preloader from './components/ui/Preloader.jsx';

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
  const mascotRegionRef = useRef(null);
  const uiRef = useRef(null);
  const [mascotAvailable, setMascotAvailable] = useState(false);
  const [webgl] = useState(() => webglSupported());
  const [tier] = useState(() => detectTier());
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'dark');
  const [menuOpen, setMenuOpen] = useState(false);
  const [ready, setReady] = useState(false); // Live2D 模型加载完成才隐藏 preloader

  // 登录态（强制门）：未登录渲染 AuthScene，登录后才启动较重的 PIXI / Live2D 视觉层。
  // 账号入口不依赖 16K 模型资源，慢设备上也能立即操作表单。
  const { status, user, quota, login, register, logout, refreshQuota } = useAuth();
  const sessionKey = status === 'authed' ? user?.id : null;
  const parseRequest = useRef(null);
  const cancelParse = useCallback(() => {
    parseRequest.current?.abort();
    parseRequest.current = null;
  }, []);
  useLayoutEffect(() => cancelParse, [sessionKey, cancelParse]);

  const setThemeTier = useCallback((t) => setTheme(t), []);

  // 主题切换：写 data-theme 属性（light/dark/auto），CSS token 随之切换；
  // auto 由 global.css 的 @media (prefers-color-scheme) 解析，无需 JS 监听系统
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  const handleSubmit = useCallback(async (url) => {
    cancelParse();
    const controller = new AbortController();
    parseRequest.current = controller;
    dispatch({ type: 'SUBMIT_URL', url });
    try {
      const payload = normalizeParse(await parseVideo(url, controller.signal));
      if (controller.signal.aborted || parseRequest.current !== controller) return;
      dispatch({ type: 'PARSE_SUCCESS', payload });
    } catch (e) {
      if (controller.signal.aborted || parseRequest.current !== controller) return;
      dispatch({ type: 'PARSE_FAIL', error: e });
    } finally {
      if (parseRequest.current === controller) parseRequest.current = null;
    }
  }, [cancelParse]);

  // 下载编排（发起 + 服务端轮询）下沉到 useDownload，App 只保留 dispatch 与场景渲染
  const { startDownload: handleDownload, save, saveBusy, saveError, cancel } = useDownload(state, dispatch, sessionKey);
  const handleReset = useCallback(() => {
    cancelParse();
    cancel();
    dispatch({ type: 'RESET' });
  }, [cancelParse, cancel]);
  const handleLogout = useCallback(() => {
    handleReset();
    logout();
  }, [handleReset, logout]);
  const insights = useVideoInsights(status === 'authed' ? state.url : '');

  // 下载提交成功后刷新额度；收到 quota 错误时刷新额度（拿到最新 used/limit）
  useEffect(() => { if (status !== 'authed' || !state.download) return; refreshQuota(); }, [state.download, status, refreshQuota]);
  useEffect(() => { if (status !== 'authed' || state.error?.error_type !== 'quota') return; refreshQuota(); }, [state.error, status, refreshQuota]);

  // 退出时清理上一账号的下载会话，避免重新登录后泄露/恢复旧场景。
  useEffect(() => {
    if (status === 'gate' && state.scene !== SCENE.ENTRY) dispatch({ type: 'RESET' });
  }, [status, state.scene]);

  // PIXI 舞台：WebGL 可用时挂载，否则走 CSS 渐变兜底（global.css 里 .css-fallback）
  useEffect(() => {
    if (!webgl || status !== 'authed') {
      setReady(false);
      setMascotAvailable(false);
      return;
    }
    const app = initStage(stageRef.current);
    const bg = createBackground(app, tier);
    bgRef.current = bg;
    const onResize = () => {
      bg.resize();
      mascotRef.current?.resize();
    };
    const onScroll = () => mascotRef.current?.resize();
    window.addEventListener('resize', onResize);
    window.addEventListener('scroll', onScroll, { passive: true });
    const regionObserver = new ResizeObserver(onScroll);
    if (uiRef.current) regionObserver.observe(uiRef.current);
    let stale = false; // StrictMode 双重挂载：旧挂载的 mascot 结果丢弃，不覆盖 ref / 不提前置 ready
    createMascot(app, DEFAULT_MODEL_ID, { onTap: () => setMenuOpen(true), getRegion: () => mascotRegionRef.current?.getBoundingClientRect() }).then((m) => {
      if (stale) { m.destroy(); return; }
      mascotRef.current = m;
      setMascotAvailable(m.isAvailable());
      m.startRandomProps();
      setReady(true);
    });
    return () => {
      stale = true;
      window.removeEventListener('resize', onResize);
      window.removeEventListener('scroll', onScroll);
      regionObserver.disconnect();
      mascotRef.current?.destroy();
      bg.destroy();
      destroyStage(app);
      mascotRef.current = null;
      bgRef.current = null;
    };
  }, [webgl, tier, status]);

  // 随 scene 切换粒子强度（安静/活跃）
  useEffect(() => {
    bgRef.current?.setIntensity(intensityForScene(state.scene));
  }, [state.scene]);

  // 随 scene 切换角色情绪眼（解析/下载→圈圈眼、选清晰度→煎蛋眼、完成→星星眼、出错→生气）
  useEffect(() => {
    mascotRef.current?.setStageExpression(state.scene);
    mascotRef.current?.resize();
  }, [state.scene, webgl]);

  const mascotSlot = webgl && <div className="mascot-region">
    <div className="mascot-region__viewport" ref={mascotRegionRef} data-mascot-region
      role="button" tabIndex={mascotAvailable ? 0 : -1} aria-label="角色换装（按 Enter 或空格）"
      aria-disabled={!mascotAvailable} aria-haspopup="dialog" aria-expanded={menuOpen}
      onKeyDown={(event) => {
        if (!mascotAvailable || event.repeat || (event.key !== 'Enter' && event.key !== ' ')) return;
        event.preventDefault();
        setMenuOpen(true);
      }} />
  </div>;

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
        insights={insights}
      />
    ); break;
    case SCENE.DOWNLOADING: scene = <DownloadingScene job={state.job} mode={state.download?.mode} />; break;
    case SCENE.DONE: scene = <DoneScene job={state.job} onSave={save} saveBusy={saveBusy} saveError={saveError} onReset={handleReset} />; break;
    case SCENE.ERROR: scene = <ErrorScene error={state.error} onReset={handleReset} />; break;
    case SCENE.ENTRY:
    default: scene = <EntryScene onSubmit={handleSubmit} mascotSlot={mascotSlot} />;
  }

  return (
    <>
      <div ref={stageRef} className={webgl ? 'stage' : 'stage css-fallback'} />
      <div ref={uiRef} className="ui">
        {status === 'authed' ? (
          <>
            {scene}
            {state.scene !== SCENE.ENTRY && mascotSlot}
            <AuthBar user={user} quota={quota} onLogout={handleLogout} />
          </>
        ) : (
          <AuthScene loading={status === 'loading'} onLogin={login} onRegister={register} />
        )}
      </div>
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
      {status === 'authed' && webgl && <Preloader done={ready} />}
    </>
  );
}
