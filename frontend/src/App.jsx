import React, { useEffect, useLayoutEffect, useReducer, useCallback, useRef, useState } from 'react';
import { reduce, initialState, SCENE } from './state/sceneMachine.js';
import { parseVideo } from './api.js';
import { useDownload } from './hooks/useDownload.js';
import { useAuth } from './hooks/useAuth.js';
import { useVideoInsights } from './hooks/useVideoInsights.js';
import { useMascotHitArea } from './hooks/useMascotHitArea.js';
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
import VideoIcon from './components/ui/VideoIcon.jsx';
import PointerFollower from './components/ui/PointerFollower.jsx';

// 三档主题开关（数据驱动，加档只改这里）
const THEMES = [
  { v: 'light', label: '浅色' },
  { v: 'dark', label: '深色' },
  { v: 'auto', label: '自动' },
];

function mascotToken(name, fallback, time = false) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value) || value <= 0) return fallback;
  return time && !raw.endsWith('ms') ? value * 1000 : value;
}

const PHONE_VIEWPORT = '(max-width: 800px)';
const PHONE_USER_AGENT = /Android|iPhone|iPod|IEMobile|Windows Phone/i;

function useMascotEligible() {
  const isPhone = () => PHONE_USER_AGENT.test(navigator.userAgent);
  const [eligible, setEligible] = useState(() => !isPhone() && !(window.matchMedia?.(PHONE_VIEWPORT)?.matches ?? window.innerWidth <= 800));
  useEffect(() => {
    const phone = isPhone();
    const media = window.matchMedia?.(PHONE_VIEWPORT);
    const update = () => setEligible(!phone && !(media?.matches ?? window.innerWidth <= 800));
    update();
    if (media) {
      media.addEventListener('change', update);
      return () => media.removeEventListener('change', update);
    }
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  return eligible;
}

export default function App() {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);
  const sceneRef = useRef(state.scene);
  sceneRef.current = state.scene;

  const stageRef = useRef(null);
  const bgRef = useRef(null);
  const mascotRef = useRef(null);
  const mascotInteractionRef = useRef(null);
  const uiRef = useRef(null);
  const [mascotAvailable, setMascotAvailable] = useState(false);
  const [mascotVisual, setMascotVisual] = useState(false);
  const mascotEligible = useMascotEligible();
  useMascotHitArea({ rootRef: uiRef, targetRef: mascotInteractionRef, enabled: mascotVisual && mascotEligible });
  const [webgl] = useState(() => webglSupported());
  const [tier] = useState(() => detectTier());
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'light');
  const [menuOpen, setMenuOpen] = useState(false);
  const [inputDraft, setInputDraft] = useState('');
  const [focusInput, setFocusInput] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [authBlocked, setAuthBlocked] = useState(false);

  // 首页向访客开放；只有显式点击顶部登录才显示账号页，业务请求仍需认证。
  // 较重的 PIXI / Live2D 视觉层继续仅在登录后启动。
  const { status, user, quota, login, register, logout, refreshQuota } = useAuth();
  const authNotice = authBlocked && status !== 'authed'
    ? (status === 'loading' ? '正在验证登录状态，请稍后再解析' : '请先点击顶部登录按钮登录后再解析')
    : '';
  const sessionKey = status === 'authed' ? user?.id : null;
  const parseRequest = useRef(null);
  const cancelParse = useCallback(() => {
    parseRequest.current?.abort();
    parseRequest.current = null;
  }, []);
  useLayoutEffect(() => cancelParse, [sessionKey, cancelParse]);

  const setThemeTier = useCallback((t) => setTheme(t), []);
  const focusMainControl = useCallback(() => {
    const controls = uiRef.current?.querySelectorAll('input:not(:disabled), button:not(:disabled), a[href]') || [];
    const target = Array.from(controls).find((element) => {
      const style = getComputedStyle(element);
      return style.display !== 'none' && style.visibility !== 'hidden' && !element.closest('[hidden], [inert]');
    });
    target?.focus();
  }, []);

  // 主题切换：写 data-theme 属性（light/dark/auto），CSS token 随之切换；
  // auto 由 global.css 的 @media (prefers-color-scheme) 解析，无需 JS 监听系统
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  const handleSubmit = useCallback(async (url) => {
    setInputDraft(url);
    setFocusInput(false);
    cancelParse();
    if (status !== 'authed') {
      setAuthBlocked(true);
      return;
    }
    setAuthBlocked(false);
    const controller = new AbortController();
    parseRequest.current = controller;
    dispatch({ type: 'SUBMIT_URL', url });
    try {
      const payload = normalizeParse(await parseVideo(url, controller.signal));
      if (controller.signal.aborted || parseRequest.current !== controller) return;
      dispatch({ type: 'PARSE_SUCCESS', payload });
      const firstFormat = payload.formats.find((format) => format?.format_id);
      if (firstFormat) dispatch({ type: 'SELECT_FORMAT', format: firstFormat });
    } catch (e) {
      if (controller.signal.aborted || parseRequest.current !== controller) return;
      dispatch({ type: 'PARSE_FAIL', error: e });
    } finally {
      if (parseRequest.current === controller) parseRequest.current = null;
    }
  }, [cancelParse, status]);

  // 下载编排（发起 + 服务端轮询）下沉到 useDownload，App 只保留 dispatch 与场景渲染
  const { startDownload: handleDownload, save, saveBusy, saveError, cancel } = useDownload(state, dispatch, sessionKey);
  const handleReset = useCallback(() => {
    cancelParse();
    cancel();
    dispatch({ type: 'RESET' });
    setAuthBlocked(false);
    setFocusInput(true);
  }, [cancelParse, cancel]);
  const handleLogout = useCallback(() => {
    handleReset();
    setInputDraft('');
    setAuthOpen(false);
    logout();
  }, [handleReset, logout]);
  const insights = useVideoInsights(status === 'authed' ? state.url : '');
  const previousSession = useRef(sessionKey);
  useLayoutEffect(() => {
    const previous = previousSession.current;
    previousSession.current = sessionKey;
    if (previous === sessionKey) return;
    setAuthOpen(false);
    setAuthBlocked(false);
    // 访客 → 登录保留草稿；退出或账号切换清空上一账号的输入。
    if (previous != null) {
      setInputDraft('');
      setFocusInput(false);
    } else if (sessionKey != null) setFocusInput(true);
  }, [sessionKey]);
  const handleAuthBack = useCallback(() => {
    setAuthOpen(false);
    setFocusInput(true);
  }, []);
  const showAuth = authOpen && status !== 'authed';

  // 下载提交成功后刷新额度；收到 quota 错误时刷新额度（拿到最新 used/limit）
  useEffect(() => { if (status !== 'authed' || !state.download) return; refreshQuota(); }, [state.download, status, refreshQuota]);
  useEffect(() => { if (status !== 'authed' || state.error?.error_type !== 'quota') return; refreshQuota(); }, [state.error, status, refreshQuota]);

  // 退出时清理上一账号的下载会话，避免重新登录后泄露/恢复旧场景。
  useEffect(() => {
    if (status === 'gate' && state.scene !== SCENE.ENTRY) dispatch({ type: 'RESET' });
  }, [status, state.scene]);

  // PIXI 舞台：WebGL 可用时挂载，否则走 CSS 渐变兜底（global.css 里 .css-fallback）
  useEffect(() => {
    setMascotAvailable(false);
    setMascotVisual(false);
    setMenuOpen(false);
    if (!webgl || status !== 'authed') {
      return;
    }
    const app = initStage(stageRef.current);
    const bg = createBackground(app, tier);
    bgRef.current = bg;
    const onResize = () => {
      app.resize?.();
      bg.resize();
      mascotRef.current?.resize();
    };
    window.addEventListener('resize', onResize);
    const controller = new AbortController();
    let stale = false;
    let ownedMascot = null;
    let timeout;
    // Phone and small-screen gates run before createMascot, preventing model and fallback requests.
    if (mascotEligible) {
      timeout = window.setTimeout(() => controller.abort(), mascotToken('--mascot-load-timeout', 8000, true));
      createMascot(app, DEFAULT_MODEL_ID, {
        placementMode: 'free', signal: controller.signal,
        onTap: () => { if (mascotRef.current?.isAvailable()) setMenuOpen(true); }, interactionTarget: mascotInteractionRef.current,
      }).then((m) => {
        window.clearTimeout(timeout);
        if (stale || controller.signal.aborted) { m.destroy(); return; }
        ownedMascot = m;
        mascotRef.current = m;
        setMascotAvailable(m.isAvailable());
        setMascotVisual(m.hasVisual?.() ?? m.isAvailable());
        m.startRandomProps();
        m.setStageExpression(sceneRef.current);
      }).catch(() => {
        window.clearTimeout(timeout);
        if (stale) return;
        setMascotAvailable(false);
        setMascotVisual(false);
      });
    }
    return () => {
      stale = true;
      window.clearTimeout(timeout);
      window.removeEventListener('resize', onResize);
      ownedMascot?.destroy();
      controller.abort();
      bg.destroy();
      destroyStage(app);
      if (mascotRef.current === ownedMascot) mascotRef.current = null;
      if (bgRef.current === bg) bgRef.current = null;
    };
  }, [webgl, tier, status, mascotEligible]);

  const moveMascot = useCallback((dx, dy) => {
    const step = mascotToken('--mascot-keyboard-step', 24);
    mascotRef.current?.moveBy(dx * step, dy * step);
  }, []);

  // 随 scene 切换粒子强度（安静/活跃）
  useEffect(() => {
    bgRef.current?.setIntensity(intensityForScene(state.scene));
  }, [state.scene]);

  // 随 scene 切换角色情绪眼（解析/下载→圈圈眼、选清晰度→煎蛋眼、完成→星星眼、出错→生气）
  useLayoutEffect(() => {
    mascotRef.current?.setStageExpression(state.scene);
    mascotRef.current?.resize();
  }, [state.scene, mascotVisual]);

  const mascotInteraction = webgl && mascotEligible && <div className="mascot-interaction" ref={mascotInteractionRef} data-mascot-interaction data-follow-exclude="mascot"
      role={mascotAvailable ? 'button' : 'img'} tabIndex={mascotAvailable ? 0 : -1}
      aria-label={mascotAvailable ? '角色换装（按 Enter 或空格打开菜单）' : '角色动画'}
      hidden={!mascotVisual}
      aria-disabled={!mascotAvailable || !mascotVisual}
      aria-haspopup={mascotAvailable ? 'dialog' : undefined} aria-expanded={mascotAvailable ? menuOpen : undefined}
      onKeyDown={(event) => {
        if (!mascotAvailable || !mascotVisual) return;
        const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        if (directions[event.key]) {
          event.preventDefault();
          moveMascot(...directions[event.key]);
          return;
        }
        if (event.key === 'Home') { event.preventDefault(); mascotRef.current?.resetPosition(); return; }
        if (event.repeat || (event.key !== 'Enter' && event.key !== ' ')) return;
        event.preventDefault();
        setMenuOpen(true);
      }} />;

  let scene;
  switch (state.scene) {
    case SCENE.PARSING: scene = <ParsingScene />; break;
    case SCENE.SELECTING: scene = null; break;
    case SCENE.DOWNLOADING: scene = <DownloadingScene job={state.job} mode={state.download?.mode} />; break;
    case SCENE.DONE: scene = <DoneScene job={state.job} onSave={save} saveBusy={saveBusy} saveError={saveError} onReset={handleReset} />; break;
    case SCENE.ERROR: scene = <ErrorScene error={state.error} onReset={handleReset} />; break;
    case SCENE.ENTRY:
    default: scene = <EntryScene onSubmit={handleSubmit} initialUrl={inputDraft} onUrlChange={setInputDraft} focusInput={focusInput} notice={authNotice} />;
  }

  // 同一个展示组件贯穿格式选择、下载、保存和下载失败，右侧页签不因下载换页而重挂载。
  if (state.parseResult) {
    const downloadContent = state.scene === SCENE.SELECTING ? null : scene;
    scene = <SelectingScene parseResult={state.parseResult} selectedFormat={state.selectedFormat}
      forceServer={state.forceServer} onSelect={(format, forceServer) => dispatch({ type: 'SELECT_FORMAT', format, forceServer })}
      onDownload={handleDownload} insights={insights} downloadContent={downloadContent} sourceUrl={state.url}
      locked={state.scene !== SCENE.SELECTING} />;
  }

  return (
    <>
      <header className="site-header">
        <a className="site-brand" href="#top" aria-label="万能视频下载，回到页首">
          <span className="site-brand__mark" aria-hidden="true"><VideoIcon name="download" /></span>
          <span>万能视频下载</span>
        </a>
        {!showAuth && state.scene === SCENE.ENTRY && (
          <nav className="site-nav" aria-label="页面导航">
            <a href="#features">功能</a>
            <a href="#how-it-works">如何使用</a>
          </nav>
        )}
        <div className="site-header__utilities">
          {status === 'authed' && <AuthBar user={user} quota={quota} onLogout={handleLogout} />}
          {status !== 'authed' && <button type="button" className="site-login" aria-expanded={showAuth}
            onClick={() => { setAuthOpen(true); setFocusInput(false); }}>登录</button>}
          <div className="theme-switch" role="group" aria-label="主题模式">
            {THEMES.map((t) => (
              <button key={t.v} type="button" className="theme-switch__opt"
                aria-pressed={theme === t.v} onClick={() => setThemeTier(t.v)}>{t.label}</button>
            ))}
          </div>
        </div>
      </header>
      <div ref={stageRef} className={webgl ? 'stage stage--floating' : 'stage css-fallback'}>{mascotInteraction}</div>
      <div id="top" ref={uiRef} className="ui">
        {showAuth ? (
          <AuthScene loading={status === 'loading'} onLogin={login} onRegister={register} onBack={handleAuthBack} />
        ) : (
          <>
            {state.scene === SCENE.ENTRY ? scene : <main className="video-workflow">
              <div className="video-workflow__heading" data-ui-follow>
                <h1 data-follow-plane>从链接，到你的收藏。</h1>
              </div>
              <div className="video-workflow__toolbar">
                <button type="button" className="video-back" onClick={handleReset}><span aria-hidden="true">←</span> 返回输入</button>
                <p className="video-workflow__url" title={state.url}>{state.url}</p>
              </div>
              {scene}
            </main>}
          </>
        )}
      </div>
      {mascotEligible && mascotAvailable && <ExpressionMenu open={menuOpen && mascotVisual && status === 'authed'} onClose={() => setMenuOpen(false)}
        canCustomize={mascotAvailable}
        onExpression={(pid, v) => mascotRef.current?.setExpression(pid, v)} onScale={(dir) => mascotRef.current?.scaleBy(dir)} onFocusFallback={focusMainControl} />}
      <PointerFollower rootRef={uiRef} />
    </>
  );
}
