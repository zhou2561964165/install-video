import React, { useEffect, useRef, useState } from 'react';
import { unlock, playSfx } from '../audio/audioManager.js';

// 与服务端注册规则一致（routes/auth.py）：邮箱格式与至少 8 位密码；登录只校验非空，交由服务端判断。
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PASSWORD_MIN = 8;
const EMAIL_ERROR = '请输入有效的邮箱地址，例如 you@example.com';
const PASSWORD_ERROR = `密码至少 ${PASSWORD_MIN} 位`;

// 按需登录/注册场景，返回首页由 App 保存链接草稿并恢复焦点。
//   onLogin / onRegister 返回 promise，抛错由本组件捕获就近展示；成功则 useAuth 切 authed，本组件卸载。
export default function AuthScene({ loading, onLogin, onRegister, onBack }) {
  const [tab, setTab] = useState('login'); // login | register
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [touched, setTouched] = useState({ email: false, password: false });
  const [attempted, setAttempted] = useState(false);
  const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const loadingRef = useRef(null);
  useEffect(() => {
    (loading ? loadingRef : emailRef).current?.focus();
  }, [loading]);

  const isLogin = tab === 'login';
  // 注册才做本地格式校验；失焦或提交后才显示，避免输入过程中打断。
  const emailError = !isLogin && (touched.email || attempted) && !EMAIL_RE.test(email.trim()) ? EMAIL_ERROR : null;
  const passwordError = !isLogin && (touched.password || attempted) && password.length < PASSWORD_MIN ? PASSWORD_ERROR : null;
  const switchTab = (next) => { setTab(next); setError(null); setTouched({ email: false, password: false }); setAttempted(false); };
  const describedBy = (fieldError, id) => [fieldError ? id : null, error ? 'auth-error' : null].filter(Boolean).join(' ') || undefined;

  const submit = async (e) => {
    e.preventDefault();
    if (busy || !email.trim() || !password) return;
    if (!isLogin) {
      const badEmail = !EMAIL_RE.test(email.trim());
      if (badEmail || password.length < PASSWORD_MIN) {
        setAttempted(true);
        (badEmail ? emailRef : passwordRef).current?.focus();
        return;
      }
    }
    unlock();
    playSfx('paste');
    setBusy(true);
    setError(null);
    try {
      await (isLogin ? onLogin : onRegister)(email.trim(), password);
      // 成功后 useAuth 切 authed → 本组件卸载，无需复位 busy
    } catch (err) {
      setError(err?.error || (isLogin ? '登录失败，请重试' : '注册失败，请重试'));
      setBusy(false);
    }
  };

  return (
    <div data-testid="auth-scene" className="scene auth-scene" data-ui-follow>
      <div className="auth-layout">
        <section className="auth-intro" aria-label="产品介绍">
          <p className="auth-intro__title" data-follow-plane>让每一段视频，都有去处。</p>
        </section>
        <div className="auth-card" data-follow-exclude="panel" aria-busy={loading || busy || undefined}>
          <button type="button" className="auth-back" onClick={onBack} disabled={busy}>返回首页</button>
          {loading ? (
            <>
              <div className="spinner" />
              <p className="auth-loading" ref={loadingRef} tabIndex={-1}>正在恢复登录状态…</p>
            </>
          ) : (
            <>
              <h1>登录后开始下载</h1>
              <div className="auth-tabs" role="group" aria-label="登录方式">
                <button
                  type="button"
                  className="auth-tabs__opt"
                  aria-pressed={isLogin}
                  onClick={() => switchTab('login')}
                >
                  登录
                </button>
                <button
                  type="button"
                  className="auth-tabs__opt"
                  aria-pressed={!isLogin}
                  onClick={() => switchTab('register')}
                >
                  注册
                </button>
              </div>
              <form className="auth-form" onSubmit={submit} noValidate>
                <div className="auth-field">
                  <label htmlFor="auth-email">邮箱</label>
                  <input
                    ref={emailRef}
                    id="auth-email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onBlur={() => setTouched((value) => ({ ...value, email: true }))}
                    aria-invalid={emailError ? true : undefined}
                    aria-describedby={describedBy(emailError, 'auth-email-error')}
                  />
                  {emailError && <p id="auth-email-error" className="auth-field-error">{emailError}</p>}
                </div>
                <div className="auth-field">
                  <label htmlFor="auth-password">密码</label>
                  <div className="auth-password">
                    <input
                      ref={passwordRef}
                      id="auth-password"
                      type={showPw ? 'text' : 'password'}
                      autoComplete={isLogin ? 'current-password' : 'new-password'}
                      placeholder={isLogin ? '输入密码' : '至少 8 位'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      onBlur={() => setTouched((value) => ({ ...value, password: true }))}
                      aria-invalid={passwordError ? true : undefined}
                      aria-describedby={describedBy(passwordError, 'auth-password-error')}
                    />
                    <button
                      type="button"
                      className="auth-password__toggle"
                      onClick={() => setShowPw((v) => !v)}
                      aria-pressed={showPw}
                      aria-label={showPw ? '隐藏密码' : '显示密码'}
                    >
                      {showPw ? '隐藏' : '显示'}
                    </button>
                  </div>
                  {passwordError && <p id="auth-password-error" className="auth-field-error">{passwordError}</p>}
                </div>
                {error && <p id="auth-error" className="auth-error" role="alert">{error}</p>}
                <button type="submit" disabled={busy || !email.trim() || !password}>
                  {busy ? (isLogin ? '登录中…' : '注册中…') : (isLogin ? '立即登录' : '立即注册')}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
