import { useCallback, useEffect, useRef, useState } from 'react';
import { login as apiLogin, register as apiRegister, getMe, setAuthToken, clearAuthToken } from '../api.js';
import { AUTH_TOKEN_KEY as TOKEN_KEY } from '../lib/appBase.js';

// 登录态 hook：三态 status ∈ { loading, gate, authed }。
//   loading：启动读 token/验证中；gate：未登录（无 token/验证失败/退出后）；authed：已登录。
//   token 存 localStorage（记住登录），api.js 负责在请求头附 Authorization。
export function useAuth() {
  const [status, setStatus] = useState('loading');
  const [user, setUser] = useState(null);
  const [quota, setQuota] = useState(null);
  const mounted = useRef(false);
  const sessionEpoch = useRef(0);
  const authenticated = useRef(false);
  const authRequest = useRef(0);
  const quotaRequest = useRef(0);

  const isCurrent = useCallback((epoch) => mounted.current && sessionEpoch.current === epoch, []);

  // 同一会话也可能并发刷新：只接受最后发起的请求，避免额度倒退。
  const loadQuota = useCallback(async (epoch) => {
    const requestId = ++quotaRequest.current;
    try {
      const me = await getMe();
      if (isCurrent(epoch) && requestId === quotaRequest.current) setQuota(me.quota);
    } catch { /* 保留当前额度；登录时已清空为未知，不影响登录/下载流程 */ }
  }, [isCurrent]);

  // 启动：读 localStorage token → 验证 → authed / gate
  useEffect(() => {
    mounted.current = true;
    const epoch = ++sessionEpoch.current;
    (async () => {
      const t = localStorage.getItem(TOKEN_KEY);
      if (!t) { setStatus('gate'); return; }
      setAuthToken(t);
      try {
        const me = await getMe();
        if (!isCurrent(epoch)) return;
        authenticated.current = true;
        setUser(me.user);
        setQuota(me.quota);
        setStatus('authed');
      } catch {
        // 旧恢复失败也不能清除新会话的全局 token / localStorage。
        if (!isCurrent(epoch)) return;
        authenticated.current = false;
        clearAuthToken();
        localStorage.removeItem(TOKEN_KEY);
        setUser(null); setQuota(null); setStatus('gate');
      }
    })();
    return () => {
      mounted.current = false;
      authenticated.current = false;
      sessionEpoch.current += 1;
    };
  }, [isCurrent]);

  // register/login 响应只有 { token, user }，无 quota —— 登录后再补拉一次
  const authenticate = useCallback(async (apiAuthenticate, email, password) => {
    if (!mounted.current) return;
    const attemptEpoch = sessionEpoch.current;
    const requestId = ++authRequest.current;
    const auth = await apiAuthenticate(email, password);
    if (!isCurrent(attemptEpoch) || requestId !== authRequest.current) return;
    // 身份真正变化时换代；认证失败仍保留旧会话及尚未完成的启动恢复。
    const epoch = ++sessionEpoch.current;
    authenticated.current = true;
    setAuthToken(auth.token);
    localStorage.setItem(TOKEN_KEY, auth.token);
    setUser(auth.user);
    setQuota(null);
    setStatus('authed');
    await loadQuota(epoch);
  }, [isCurrent, loadQuota]);

  const login = useCallback((email, password) => authenticate(apiLogin, email, password), [authenticate]);
  const register = useCallback((email, password) => authenticate(apiRegister, email, password), [authenticate]);

  const logout = useCallback(() => {
    sessionEpoch.current += 1;
    authenticated.current = false;
    clearAuthToken();
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setQuota(null);
    setStatus('gate');
  }, []);

  // 额度刷新（下载提交后 / quota 错误时）：失败吞错，不影响下载流程
  const refreshQuota = useCallback(async () => {
    if (!mounted.current || !authenticated.current) return;
    await loadQuota(sessionEpoch.current);
  }, [loadQuota]);

  return { status, user, quota, login, register, logout, refreshQuota };
}
