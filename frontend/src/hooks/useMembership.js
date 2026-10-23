import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createBillingPortal, createCheckout, getMembership, getMembershipPlans } from '../api.js';

// The URL returned by Stripe is navigation only. Membership always comes from GET /membership.
export function billingUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && (url.hostname === 'checkout.stripe.com' || url.hostname === 'billing.stripe.com') ? url.href : null;
  } catch { return null; }
}

export function useMembership(sessionKey, visible = false, navigate = (url) => window.location.assign(url)) {
  const [plans, setPlans] = useState(null);
  const [plansError, setPlansError] = useState(null);
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const generation = useRef(0);
  const refreshId = useRef(0);
  const accountController = useRef(null);
  const actionController = useRef(null);
  const busyRef = useRef(false);
  const sessionRef = useRef(sessionKey);
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  const cancelAction = useCallback(() => {
    actionController.current?.abort();
    actionController.current = null;
    busyRef.current = false;
    setBusy(null);
  }, []);

  useLayoutEffect(() => {
    sessionRef.current = sessionKey;
    generation.current += 1;
    refreshId.current += 1;
    accountController.current?.abort();
    cancelAction();
    setAccount(null);
    setError(null);
    setLoading(sessionKey != null);
    return () => {
      generation.current += 1;
      refreshId.current += 1;
      accountController.current?.abort();
      actionController.current?.abort();
      busyRef.current = false;
    };
  }, [sessionKey, cancelAction]);

  const refresh = useCallback(async () => {
    if (sessionKey == null || sessionRef.current !== sessionKey) return;
    const epoch = generation.current;
    const id = ++refreshId.current;
    accountController.current?.abort();
    const controller = new AbortController();
    accountController.current = controller;
    setLoading(true);
    setError(null);
    try {
      const value = await getMembership(controller.signal);
      if (controller.signal.aborted || epoch !== generation.current || id !== refreshId.current) return;
      setAccount(value);
    } catch (failure) {
      if (controller.signal.aborted || epoch !== generation.current || id !== refreshId.current) return;
      setError(failure);
    } finally {
      if (!controller.signal.aborted && epoch === generation.current && id === refreshId.current) setLoading(false);
    }
  }, [sessionKey]);
  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    setPlans(null);
    setPlansError(null);
    getMembershipPlans(controller.signal).then((value) => {
      if (!controller.signal.aborted) setPlans(value);
    }).catch((failure) => {
      if (!controller.signal.aborted) setPlansError(failure);
    });
    return () => controller.abort();
  }, [visible]);

  // Leaving the page or changing identity prevents a late response from navigating another session.
  useEffect(() => { if (!visible) cancelAction(); }, [visible, cancelAction]);
  const begin = useCallback(async (kind) => {
    if (sessionKey == null || sessionRef.current !== sessionKey || busyRef.current) return;
    busyRef.current = true;
    const epoch = generation.current;
    const controller = new AbortController();
    actionController.current = controller;
    setBusy(kind);
    setError(null);
    try {
      const result = await (kind === 'checkout' ? createCheckout : createBillingPortal)(controller.signal);
      if (controller.signal.aborted || epoch !== generation.current || actionController.current !== controller) return;
      const url = billingUrl(result?.url);
      if (!url) throw { error: '支付链接不可用，请刷新会员状态后重试。' };
      navigateRef.current(url);
    } catch (failure) {
      if (!controller.signal.aborted && epoch === generation.current && actionController.current === controller) setError(failure);
    } finally {
      if (actionController.current === controller) { actionController.current = null; busyRef.current = false; setBusy(null); }
    }
  }, [sessionKey]);

  return { plans, plansError, account, loading, error, busy, refresh, cancelAction, checkout: () => begin('checkout'), portal: () => begin('portal') };
}
