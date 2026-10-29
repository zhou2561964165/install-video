import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import SupportScene from './SupportScene.jsx';

const META = {
  categories: [
    { id: 'membership_not_credited', label: '会员付款后未到账' }, { id: 'download_failing', label: '下载一直失败' },
    { id: 'login_problem', label: '账号无法登录' }, { id: 'other', label: '其他问题' },
  ],
  note_max: 500,
  checkouts: [{ checkout_id: 'co-12345678', label: '12345678', created_at: '2026-10-27T02:00:00Z', state: 'open' }],
};
const TICKETS = [
  { id: 't2', category: 'membership_not_credited', category_label: '会员付款后未到账', state: 'resolved', resolution: 'reissued',
    reply_text: '已为您补发 30 天会员，请刷新会员页查看', reply_note: null, user_note: null, checkout_label: '12345678',
    created_at: '2026-10-27T03:00:00Z', resolved_at: '2026-10-27T04:00:00Z' },
  { id: 't1', category: 'other', category_label: '其他问题', state: 'open', resolution: null, reply_text: null, reply_note: null,
    user_note: '<script>alert(1)</script>', checkout_label: null, created_at: '2026-10-26T03:00:00Z', resolved_at: null },
];
const api = (override = {}) => ({
  getSupportMeta: vi.fn().mockResolvedValue(META),
  listSupportTickets: vi.fn().mockResolvedValue({ items: TICKETS }),
  submitSupportTicket: vi.fn().mockResolvedValue({ id: 't3', state: 'open' }),
  ...override,
});
const view = (props = {}) => render(<SupportScene authed onLogin={vi.fn()} onBack={vi.fn()} api={api()} {...props} />);

describe('SupportScene', () => {
  it('asks a guest to log in instead of loading tickets', async () => {
    const login = vi.fn(), client = api();
    render(<SupportScene authed={false} onLogin={login} onBack={vi.fn()} api={client} />);
    await userEvent.click(screen.getByRole('button', { name: '登录后联系客服' }));
    expect(login).toHaveBeenCalledOnce();
    expect(client.getSupportMeta).not.toHaveBeenCalled();
  });

  it('offers the four issue types as a single choice', async () => {
    view();
    const group = await screen.findByRole('radiogroup', { name: '问题类型' });
    expect(within(group).getAllByRole('radio').map((radio) => radio.closest('label').textContent))
      .toEqual(['会员付款后未到账', '下载一直失败', '账号无法登录', '其他问题']);
  });

  it('requires choosing an eligible order for a not-credited membership', async () => {
    const client = api(); view({ api: client });
    await userEvent.click(await screen.findByRole('radio', { name: '会员付款后未到账' }));
    const submit = screen.getByRole('button', { name: '提交问题' });
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByRole('radio', { name: /订单 12345678/ }));
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(client.submitSupportTicket).toHaveBeenCalledWith({ category: 'membership_not_credited', note: null, checkout_id: 'co-12345678' });
  });

  it('explains when there is no order to appeal and keeps submit disabled', async () => {
    view({ api: api({ getSupportMeta: vi.fn().mockResolvedValue({ ...META, checkouts: [] }) }) });
    await userEvent.click(await screen.findByRole('radio', { name: '会员付款后未到账' }));
    expect(screen.getByText(/近 90 天没有可申诉的订单/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '提交问题' })).toBeDisabled();
  });

  it('counts the note against the server limit', async () => {
    view();
    await userEvent.click(await screen.findByRole('radio', { name: '其他问题' }));
    await userEvent.type(screen.getByLabelText('补充说明（可选）'), '你好');
    expect(screen.getByText('2 / 500')).toBeInTheDocument();
  });

  it('switches to my tickets after a successful submit', async () => {
    const client = api(); view({ api: client });
    await userEvent.click(await screen.findByRole('radio', { name: '下载一直失败' }));
    await userEvent.click(screen.getByRole('button', { name: '提交问题' }));
    expect(await screen.findByRole('tab', { name: '我的工单', selected: true })).toBeInTheDocument();
    expect(client.listSupportTickets).toHaveBeenCalled();
    expect(client.getSupportMeta).toHaveBeenCalledTimes(2);  // appealable orders refreshed
    expect(screen.getByRole('status')).toHaveTextContent('已提交');
  });

  it('shows ticket state and the reply text', async () => {
    view();
    await userEvent.click(await screen.findByRole('tab', { name: '我的工单' }));
    const items = await screen.findAllByRole('listitem');
    expect(within(items[0]).getByText('已解决')).toBeInTheDocument();
    expect(within(items[0]).getByText('已为您补发 30 天会员，请刷新会员页查看')).toBeInTheDocument();
    expect(within(items[1]).getByText('处理中')).toBeInTheDocument();
  });

  it('renders note as text', async () => {
    const { container } = view();
    await userEvent.click(await screen.findByRole('tab', { name: '我的工单' }));
    expect(await screen.findByText('<script>alert(1)</script>')).toBeInTheDocument();
    expect(container.querySelector('script')).toBeNull();
  });

  it('shows the server error text when submitting fails', async () => {
    view({ api: api({ submitSupportTicket: vi.fn().mockRejectedValue({ error_type: 'too_many_open', error: '处理中的工单过多，请等待处理后再提交' }) }) });
    await userEvent.click(await screen.findByRole('radio', { name: '其他问题' }));
    await userEvent.click(screen.getByRole('button', { name: '提交问题' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('处理中的工单过多');
  });

  it('shows a readable error when meta cannot load', async () => {
    view({ api: api({ getSupportMeta: vi.fn().mockRejectedValue({ error_type: 'network', error: '请求失败' }) }) });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('请求失败'));
  });
});
