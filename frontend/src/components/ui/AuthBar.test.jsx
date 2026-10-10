import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuthBar from './AuthBar.jsx';

const user = { email: 'developer@example.com' };

describe('AuthBar', () => {
  it('shows unlimited downloads for nullable quota without an exhausted warning', () => {
    render(<AuthBar user={user} quota={{ used: 45, date: '2026-10-08', limit: null, remaining: null, unlimited: true }} />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('下载额度不限');
    expect(status).toHaveAttribute('aria-atomic', 'true');
    expect(status).not.toHaveClass('auth-bar__exhausted');
    expect(screen.queryByText('今日额度已用完')).not.toBeInTheDocument();
  });

  it.each([false, undefined])('keeps ordinary quota visible with unlimited=%s', (unlimited) => {
    render(<AuthBar user={user} quota={{ used: 2, date: '2026-10-08', limit: 3, remaining: 1, unlimited }} />);

    expect(screen.getByRole('status')).toHaveTextContent('今日剩余 1/3');
    expect(screen.getByRole('status')).not.toHaveClass('auth-bar__exhausted');
  });

  it('warns when an ordinary quota is exhausted', () => {
    render(<AuthBar user={user} quota={{ used: 3, date: '2026-10-08', limit: 3, remaining: 0, unlimited: false }} />);

    expect(screen.getByRole('status')).toHaveTextContent('今日额度已用完');
    expect(screen.getByRole('status')).toHaveClass('auth-bar__exhausted');
  });

  it.each([undefined, null, {}, { limit: null, remaining: null }, { limit: 3 }])('omits unknown quota instead of displaying missing numbers: %j', (quota) => {
    render(<AuthBar user={user} quota={quota} />);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText(/今日|下载额度|null|undefined/)).not.toBeInTheDocument();
    expect(screen.getByText(user.email)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '退出' })).toBeEnabled();
  });

  it('updates one complete status without moving focus away from logout', () => {
    const { rerender } = render(<AuthBar user={user} quota={{ used: 2, date: '2026-10-08', limit: 3, remaining: 1 }} />);
    const logout = screen.getByRole('button', { name: '退出' });
    logout.focus();

    rerender(<AuthBar user={user} quota={{ used: 3, date: '2026-10-08', limit: null, remaining: null, unlimited: true }} />);

    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(screen.getByRole('status')).toHaveTextContent('下载额度不限');
    expect(screen.getByRole('status')).toHaveAttribute('aria-atomic', 'true');
    expect(logout).toHaveFocus();
  });

  it('keeps email visible and invokes logout once when activated', async () => {
    let logoutCount = 0;
    render(<AuthBar user={user} quota={{ used: 4, date: '2026-10-08', limit: null, remaining: null, unlimited: true }} onLogout={() => { logoutCount += 1; }} />);

    expect(screen.getByText(user.email)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '退出' }));
    expect(logoutCount).toBe(1);
  });
});
