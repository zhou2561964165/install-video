import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { billingUrl, useMembership } from './useMembership.js';
import { createBillingPortal, createCheckout, getMembership, getMembershipPlans } from '../api.js';

vi.mock('../api.js', () => ({ createBillingPortal: vi.fn(), createCheckout: vi.fn(), getMembership: vi.fn(), getMembershipPlans: vi.fn() }));
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
beforeEach(() => { vi.resetAllMocks(); getMembership.mockResolvedValue({ plan: 'free' }); getMembershipPlans.mockResolvedValue({ checkout_available: false }); });

describe('membership account and billing isolation', () => {
  it('only loads public plans when visible, and never requests account for a guest', async () => {
    const view = renderHook(({ visible }) => useMembership(null, visible), { initialProps: { visible: false } });
    expect(getMembershipPlans).not.toHaveBeenCalled(); expect(getMembership).not.toHaveBeenCalled();
    view.rerender({ visible: true });
    await waitFor(() => expect(view.result.current.plans).toEqual({ checkout_available: false }));
    await act(async () => view.result.current.checkout()); expect(createCheckout).not.toHaveBeenCalled();
  });
  it('ignores a late previous-account response and clears privileges immediately on account switch', async () => {
    const old = deferred(); getMembership.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ plan: 'free' });
    const view = renderHook(({ session }) => useMembership(session), { initialProps: { session: 'a' } });
    const signal = getMembership.mock.calls[0][0];
    view.rerender({ session: 'b' });
    expect(signal.aborted).toBe(true);
    await act(async () => old.resolve({ plan: 'vip' }));
    await waitFor(() => expect(view.result.current.account).toEqual({ plan: 'free' }));
  });
  it('only accepts the latest explicit refresh', async () => {
    const first = deferred(), second = deferred();
    getMembership.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const view = renderHook(() => useMembership('a'));
    act(() => { view.result.current.refresh(); });
    await act(async () => second.resolve({ plan: 'free', status: 'expired' }));
    await act(async () => first.resolve({ plan: 'vip' }));
    expect(view.result.current.account).toEqual({ plan: 'free', status: 'expired' });
  });
  it.each(['checkout', 'portal'])('cancels %s navigation on logout, even when fetch ignores abort', async (action) => {
    const request = deferred(), navigate = vi.fn();
    (action === 'checkout' ? createCheckout : createBillingPortal).mockReturnValue(request.promise);
    const view = renderHook(({ session }) => useMembership(session, true, navigate), { initialProps: { session: 'a' } });
    await act(async () => {});
    act(() => { view.result.current[action](); });
    view.rerender({ session: null });
    await act(async () => request.resolve({ url: 'https://checkout.stripe.com/c/pay/cs_test' }));
    expect(navigate).not.toHaveBeenCalled(); expect(view.result.current.account).toBeNull();
  });
  it('coalesces double-clicks and only navigates to a trusted Stripe HTTPS page', async () => {
    const request = deferred(), navigate = vi.fn(); createCheckout.mockReturnValue(request.promise);
    const view = renderHook(() => useMembership('a', true, navigate));
    await act(async () => {});
    act(() => { view.result.current.checkout(); view.result.current.checkout(); });
    expect(createCheckout).toHaveBeenCalledOnce();
    await act(async () => request.resolve({ url: 'https://checkout.stripe.com/c/pay/cs_test' }));
    expect(navigate).toHaveBeenCalledWith('https://checkout.stripe.com/c/pay/cs_test');
    expect(view.result.current.account.plan).toBe('free');
  });
  it.each(['hidden', 'cancel', 'unmount'])('prevents a late redirect after %s', async (method) => {
    const request = deferred(), navigate = vi.fn(); createCheckout.mockReturnValue(request.promise);
    const view = renderHook(({ visible }) => useMembership('a', visible, navigate), { initialProps: { visible: true } });
    await act(async () => {}); act(() => { view.result.current.checkout(); });
    const signal = createCheckout.mock.calls[0][0];
    if (method === 'hidden') view.rerender({ visible: false });
    else if (method === 'cancel') act(() => view.result.current.cancelAction());
    else view.unmount();
    await act(async () => request.resolve({ url: 'https://checkout.stripe.com/c/pay/cs_test' }));
    expect(signal.aborted).toBe(true); expect(navigate).not.toHaveBeenCalled();
  });
  it('exposes checkout errors without changing membership', async () => {
    createCheckout.mockRejectedValue({ error_type: 'billing_unavailable', error: '支付未配置' });
    const view = renderHook(() => useMembership('a', true, vi.fn())); await act(async () => {});
    await act(async () => view.result.current.checkout());
    expect(view.result.current.error.error).toBe('支付未配置'); expect(view.result.current.account.plan).toBe('free');
  });
  it.each(['javascript:alert(1)', 'http://checkout.stripe.com/pay', 'https://checkout.stripe.com.evil.com/pay', 'https://evil.com/pay', '/local'])('rejects untrusted URL %s', (url) => { expect(billingUrl(url)).toBeNull(); });
});
