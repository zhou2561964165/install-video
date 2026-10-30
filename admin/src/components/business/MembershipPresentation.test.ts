import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import routes from '../../../config/routes';
import { membershipAttempt } from './membershipPolicy';

const session = vi.hoisted(() => ({ write: false, ready: false }));
const dialog = vi.hoisted(() => ({ states: [] as unknown[], data: undefined as unknown }));
vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>();
  return { ...actual, useState: (initial: unknown) => actual.useState(dialog.states.length ? dialog.states.shift() : initial) };
});
vi.mock('@/hooks/useAdminSession', () => ({ useAdminSession: () => ({ meta: { display_timezone: 'Asia/Singapore' }, me: { user_id: 'actor' }, can: () => session.write, canFeature: () => session.write && session.ready }) }));
vi.mock('@umijs/max', () => ({ Link: ({ children }: { children: React.ReactNode }) => React.createElement('a', {}, children) }));
vi.mock('@/components/AdminState', () => ({ AdminError: () => null, AdminTimestamp: ({ value }: { value: string }) => React.createElement('time', {}, value) }));
vi.mock('./BusinessShared', () => ({ useReadResource: () => ({ data: dialog.data, reload: vi.fn() }) }));
vi.mock('antd', () => ({
  Alert: ({ title, description }: { title: React.ReactNode; description: React.ReactNode }) => React.createElement('aside', {}, title, description), Button: ({ children, disabled }: { children: React.ReactNode; disabled: boolean }) => React.createElement('button', { disabled }, children),
  Checkbox: () => null, Form: Object.assign(({ children }: { children: React.ReactNode }) => React.createElement('form', {}, children), { Item: ({ children, help, validateStatus }: { children: React.ReactNode; help: React.ReactNode; validateStatus?: string }) => React.createElement('label', { 'data-validation': validateStatus }, children, help) }), Input: Object.assign(() => null, { TextArea: () => null }), Modal: ({ open, children, okButtonProps }: { open: boolean; children: React.ReactNode; okButtonProps: { disabled: boolean } }) => open ? React.createElement('section', {}, children, React.createElement('button', { disabled: okButtonProps.disabled }, '确认')) : null,
  Radio: { Group: () => null }, Space: ({ children }: { children: React.ReactNode }) => React.createElement('div', {}, children), Typography: { Text: ({ children }: { children: React.ReactNode }) => React.createElement('span', {}, children) },
}));
import MembershipControl, { MembershipSummary } from './MembershipControl';

describe('membership UI and navigation presentation', () => {
  afterEach(() => { dialog.data = undefined; dialog.states = []; });
  it('has five daily menus and keeps advanced/legacy deep links', () => {
    const named = routes.filter(route => 'name' in route && route.name !== '高级管理');
    expect(named.map(route => route.name)).toEqual(['概览', '用户管理', '支付订单', '客服工单', '下载记录']);
    const advanced = routes.find(route => 'name' in route && route.name === '高级管理');
    expect(advanced?.routes?.map(route => route.path)).toEqual(['/audit', '/system']);
    expect(routes.find(route => 'path' in route && route.path === '/memberships')).toMatchObject({ hideInMenu: true });
  });
  it('viewer has no write control; unavailable capability cannot be activated', () => {
    session.write = false; session.ready = true;
    expect(renderToStaticMarkup(React.createElement(MembershipControl, { userId: 'target' }))).toBe('');
    session.write = true; session.ready = false;
    expect(renderToStaticMarkup(React.createElement(MembershipControl, { userId: 'target' }))).toContain('disabled');
    session.ready = true;
    expect(renderToStaticMarkup(React.createElement(MembershipControl, { userId: 'target' }))).not.toContain('disabled');
  });
  it('shared row/detail guard survives unmount, reopen and a second entry point', () => {
    const original = membershipAttempt('one-actor', 'one-user');
    original.conflict = true;
    expect(membershipAttempt('one-actor', 'one-user')).toBe(original);
    expect(membershipAttempt('one-actor', 'one-user').canSubmit()).toBe(false);
    expect(membershipAttempt('another-actor', 'one-user').conflict).toBe(false);
  });
  it('permanent display does not confuse the original expired payment deadline', () => {
    const html = renderToStaticMarkup(React.createElement(MembershipSummary, { membership: {
      control_mode: 'enabled', effective: true, effective_reason: 'admin_enabled', effective_permanent: true,
      effective_expires_at: null, expires_at: '2020-01-01T00:00:00Z', status: 'expired',
    } as never }));
    expect(html).toContain('永久有效'); expect(html).toContain('管理员启用'); expect(html).not.toContain('2020');
  });
  it.each(['', 'not-a-date', '2020-01-01T00:00'])('never describes an invalid selected deadline as permanent: %s', (date) => {
    session.write = true; session.ready = true;
    dialog.data = { email: 'target@example.invalid', membership: { control_mode: 'auto', control_revision: '0', effective: false, effective_permanent: false, effective_expires_at: null }, as_of: '2026-10-29T00:00:00Z' };
    dialog.states = [true, 'enabled', 'until', date, '管理员核实后为此用户开通会员', true];
    const html = renderToStaticMarkup(React.createElement(MembershipControl, { userId: 'invalid-deadline-target' }));
    expect(html).toContain('请先填写有效的未来到期时间');
    expect(html).not.toContain('管理员启用，永久有效');
    expect(html).toContain('data-validation="error"');
    expect(html).toMatch(/<button disabled="">确认<\/button>/);
  });
  it('does not show an inline deadline error before the administrator touches the field', () => {
    session.write = true; session.ready = true;
    dialog.data = { email: 'target@example.invalid', membership: { control_mode: 'auto', control_revision: '0' } };
    dialog.states = [true, 'enabled', 'until', '', '', false];
    const html = renderToStaticMarkup(React.createElement(MembershipControl, { userId: 'untouched-deadline-target' }));
    expect(html).toContain('请先填写有效的未来到期时间');
    expect(html).not.toContain('data-validation="error"');
  });
  it('shows the selected valid deadline even while another field is invalid', () => {
    session.write = true; session.ready = true;
    dialog.data = { email: 'target@example.invalid', membership: { control_mode: 'auto', control_revision: '0' } };
    dialog.states = [true, 'enabled', 'until', '2099-01-01T00:00', '太短', true];
    const html = renderToStaticMarkup(React.createElement(MembershipControl, { userId: 'valid-deadline-target' }));
    expect(html).toContain('管理员启用，独立有效至');
    expect(html).not.toContain('管理员启用，永久有效');
    expect(html).not.toContain('data-validation="error"');
    expect(html).toMatch(/<button disabled="">确认<\/button>/);
  });
  it('keeps the original expired deadline visible for an unknown request replay', () => {
    session.write = true; session.ready = true;
    dialog.data = { email: 'target@example.invalid', membership: { control_mode: 'auto', control_revision: '0' } };
    dialog.states = [true, 'enabled', 'permanent', '', '', false];
    const attempt = membershipAttempt('actor', 'expired-replay-target');
    attempt.prepare({ mode: 'enabled', expires_at: '2020-01-01T00:00:00Z', reason: '管理员核实后为此用户开通会员', expected_revision: '0' });
    attempt.unknown = true;
    const html = renderToStaticMarkup(React.createElement(MembershipControl, { userId: 'expired-replay-target' }));
    expect(html).toContain('管理员启用，独立有效至');
    expect(html).toContain('2020-01-01T00:00:00Z');
    expect(html).not.toContain('请先填写有效的未来到期时间');
    attempt.complete();
  });
});
