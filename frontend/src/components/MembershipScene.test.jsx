import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import MembershipScene from './MembershipScene.jsx';

const fixture = (override = {}) => ({ plans: { checkout_available: false, price_label: null }, plansError: null, account: { plan: 'free', status: 'free', checkout_available: false }, loading: false, error: null, busy: null, refresh: vi.fn(), cancelAction: vi.fn(), checkout: vi.fn(), portal: vi.fn(), ...override });
describe('MembershipScene', () => {
  it('shows an administrator permanent entitlement without the former payment expiry', () => {
    const account = { plan: 'vip', status: 'active', control_mode: 'enabled', effective_reason: 'admin_permanent',
      effective_permanent: true, effective_expires_at: null, expires_at: '2020-01-01T00:00:00Z', checkout_available: false };
    render(<MembershipScene membership={fixture({ account })} authed onBack={() => {}} />);
    expect(screen.getByText('管理员已启用，永久有效')).toBeInTheDocument();
    expect(screen.queryByText(/权益有效期至/)).toBeNull();
    expect(screen.getByRole('button', { name: '当前方案', exact: true })).toBeDisabled();
  });
  it('explains an administrator-disabled entitlement and does not invite another purchase', () => {
    const account = { plan: 'free', status: 'expired', control_mode: 'disabled', effective_reason: 'admin_disabled',
      effective_permanent: false, effective_expires_at: null, checkout_available: false };
    render(<MembershipScene membership={fixture({ account, plans: { checkout_available: true, price_label: '¥9.9 / 30天' } })} authed onBack={() => {}} />);
    expect(screen.getByText('管理员已停用会员权益')).toBeInTheDocument();
    expect(screen.getByText('会员由管理员手动管理，如需调整请联系客服。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '管理员手动管理', exact: true })).toBeDisabled();
  });
  it('shows the administrator expiry rather than the underlying payment expiry', () => {
    const account = { plan: 'vip', status: 'active', control_mode: 'enabled', effective_reason: 'admin_until',
      effective_permanent: false, effective_expires_at: '2035-01-01T00:00:00Z', expires_at: '2020-01-01T00:00:00Z', checkout_available: false };
    render(<MembershipScene membership={fixture({ account })} authed onBack={() => {}} />);
    expect(screen.getByText('管理员已启用会员权益')).toBeInTheDocument();
    expect(screen.getByText(/权益有效期至/)).toHaveTextContent('2035');
    expect(screen.getByText(/权益有效期至/)).not.toHaveTextContent('2020');
  });
  it('keeps an expired administrator override distinct from an expired payment', () => {
    const account = { plan: 'free', status: 'expired', control_mode: 'enabled', effective_reason: 'admin_expired',
      effective_permanent: false, effective_expires_at: '2020-01-01T00:00:00Z', checkout_available: false };
    render(<MembershipScene membership={fixture({ account })} authed onBack={() => {}} />);
    expect(screen.getByText('管理员设置的会员期限已结束')).toBeInTheDocument();
  });
  it('uses the configured free resolution instead of promising a higher limit', () => {
    render(<MembershipScene membership={fixture({ plans: { checkout_available: false, free_max_height: 480 } })} onBack={() => {}} />);
    expect(screen.getByText('最高支持 480p 清晰度')).toBeInTheDocument();
    expect(screen.queryByText('最高支持 720p 清晰度')).toBeNull();
  });
  it('shows agreed unlimited tiers and pending features without inventing a price', () => {
    render(<MembershipScene membership={fixture()} authed onBack={() => {}} />);
    expect(screen.getAllByText('不限下载次数')).toHaveLength(2);
    expect(screen.getByText('价格待定')).toBeInTheDocument(); expect(screen.queryByText(/9\.9/)).toBeNull();
    expect(screen.getByText('即将支持')).toBeInTheDocument(); expect(screen.queryByText('筹备中')).toBeNull();
    expect(screen.getByRole('button', { name: '暂未开放支付' })).toBeDisabled();
  });
  it('opens customer support from the membership page', async () => {
    const support = vi.fn(); render(<MembershipScene membership={fixture()} authed onSupport={support} onBack={() => {}} />);
    expect(screen.getByText('优先客服支持')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '联系客服' })); expect(support).toHaveBeenCalledOnce();
  });
  it('preserves explicit login intent for a guest', async () => {
    const login = vi.fn(); render(<MembershipScene membership={fixture({ plans: { checkout_available: true, price_label: '$5 / 月', billing_mode: 'subscription' } })} onLogin={login} onBack={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: '登录后开通 VIP' })); expect(login).toHaveBeenCalledOnce();
  });
  it('does not invite a guest to buy when checkout is not configured', () => {
    render(<MembershipScene membership={fixture()} onLogin={vi.fn()} onBack={() => {}} />);
    expect(screen.getByRole('button', { name: '暂未开放支付' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '登录后开通 VIP' })).toBeNull();
  });
  it('does not grant VIP from the success return URL and offers a server refresh', async () => {
    const membership = fixture(); render(<MembershipScene membership={membership} authed paymentReturn="success" onBack={() => {}} />);
    expect(screen.getByText(/确认前不会开通 VIP/)).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: '当前会员状态' })).getByText('免费版')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '刷新会员状态' })); expect(membership.refresh).toHaveBeenCalledOnce();
  });
  it('shows configured subscription price and disclosure before checkout', async () => {
    const membership = fixture({ plans: { checkout_available: true, price_label: '$5 / 月', billing_mode: 'subscription', renewal_label: '每月自动续费' }, account: { plan: 'free', checkout_available: true } });
    render(<MembershipScene membership={membership} authed onBack={() => {}} />);
    expect(screen.getByText('$5 / 月')).toBeInTheDocument(); expect(screen.getByText(/可在账单管理中取消/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '通过 Stripe 开通 VIP' })); expect(membership.checkout).toHaveBeenCalledOnce();
  });
  it('shows active cancellation at term and portal, without selling another subscription', async () => {
    const membership = fixture({ account: { plan: 'vip', status: 'active', expires_at: '2030-01-01T00:00:00Z', cancel_at_period_end: true, portal_available: true } });
    render(<MembershipScene membership={membership} authed onBack={() => {}} />);
    expect(screen.getByText(/已取消续费，权益保留至/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '当前方案', exact: true })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '管理账单' })); expect(membership.portal).toHaveBeenCalledOnce();
  });
  it('shows expiry and an actionable checkout error', () => {
    render(<MembershipScene membership={fixture({ account: { plan: 'free', status: 'expired' }, error: { error: '支付暂不可用' } })} authed onBack={() => {}} />);
    expect(screen.getByText('会员已到期')).toBeInTheDocument(); expect(screen.getByRole('alert')).toHaveTextContent('支付暂不可用');
  });
});
