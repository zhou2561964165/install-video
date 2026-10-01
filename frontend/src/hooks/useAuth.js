import { useCallback, useEffect, useState } from 'react';
import { login as apiLogin, register as apiRegister, getMe, setAuthToken, clearAuthToken } from '../api.js';

const TOKEN_KEY = 'auth_token';

// 登录态 hook：三态 status ∈ { loading, gate, authed }。
//   loading：启动读 token/验证中；gate：未登录（无 token/验证失败/退出后）；authed：已登录。
//   token 存 localStorage（记住登录），api.js 负责在请求头附 Authorization。
export function useAuth() {
  const [status, setStatus] = useState('loading');
  const [user, setUser] = useState(null);
  const [quota, setQuota] = useState(null);

  // 启动：读 localStorage token → 验证 → authed / gate
  useEffect(() => {
    let alive = true;
    (async () => {
      const t = localStorage.getItem(TOKEN_KEY);
      if (!t) { if (alive) setStatus('gate'); return; }
      setAuthToken(t);
      try {
        const me = await getMe();
        if (!alive) return;
        setUser(me.user);
        setQuota(me.quota);
        setStatus('authed');
      } catch {
        clearAuthToken();
        localStorage.removeItem(TOKEN_KEY);
        if (alive) { setUser(null); setQuota(null); setStatus('gate'); }
      }
    })();
    return () => { alive = false; };
  }, []);

  // register/login 响应只有 { token, user }，无 quota —— 登录后再补拉一次
  const applyAuth = useCallback(async (auth) => {
    setAuthToken(auth.token);
    localStorage.setItem(TOKEN_KEY, auth.token);
    setUser(auth.user);
    setStatus('authed');
    try { setQuota((await getMe()).quota); } catch { setQuota(null); }
  }, []);

  const login = useCallback((email, password) => apiLogin(email, password).then(applyAuth), [applyAuth]);
  const register = useCallback((email, password) => apiRegister(email, password).then(applyAuth), [applyAuth]);

  const logout = useCallback(() => {
    clearAuthToken();
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setQuota(null);
    setStatus('gate');
  }, []);

  // 额度刷新（下载提交后 / quota 错误时）：失败吞错，不影响下载流程
  const refreshQuota = useCallback(async () => {
    try { setQuota((await getMe()).quota); } catch { /* 忽略 */ }
  }, []);

  return { status, user, quota, login, register, logout, refreshQuota };
}
