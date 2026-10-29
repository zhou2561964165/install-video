import { describe, expect, it } from 'vitest';
import { AdminApiError } from '@/services/admin/errors';
import type { Schemas } from '@/services/admin/types';
import {
  actionViews, initialReissue, reissueReducer, replyTemplates, supportErrorText, supportLabel,
} from './supportPolicy';

const allowed = { allowed: true, reason: null };
const actions = (overrides: Partial<Schemas['SupportActions']> = {}): Schemas['SupportActions'] =>
  ({ verify: allowed, reissue: allowed, reply: allowed, reject: allowed, ...overrides });
const admin = ['support:read', 'support:write', 'support:reissue'];

describe('support labels', () => {
  it('shows Chinese labels and keeps unknown future values visible', () => {
    expect(supportLabel('priority', 'priority')).toBe('优先');
    expect(supportLabel('state', 'open')).toBe('待处理');
    expect(supportLabel('check', 'refunded')).toBe('已退款');
    expect(supportLabel('reason', 'membership_active')).toMatch('另一笔付款');
    expect(supportLabel('state', 'future_state')).toBe('未知（future_state）');
  });
});

describe('action buttons follow server actions and the operator permissions', () => {
  it('viewer sees no write buttons', () => {
    expect(actionViews(actions(), ['support:read']).filter((view) => view.visible)).toEqual([]);
  });
  it('admin sees all four; disabled ones carry a readable reason', () => {
    const views = actionViews(actions({ reissue: { allowed: false, reason: 'not_verified' } }), admin);
    expect(views.map((view) => [view.action, view.visible, view.enabled])).toEqual([
      ['verify', true, true], ['reissue', true, false], ['reply', true, true], ['reject', true, true]]);
    expect(views[1].reason).toBe('尚未向支付平台核实付款');
  });
  it('without the reissue permission the button stays visible but disabled with the capability reason', () => {
    const views = actionViews(actions({ reissue: { allowed: false, reason: 'stripe_read_key_missing' } }), ['support:read', 'support:write']);
    expect(views[1]).toMatchObject({ visible: true, enabled: false, reason: '未配置支付平台只读核实密钥' });
    const serverAllowed = actionViews(actions(), ['support:read', 'support:write']);
    expect(serverAllowed[1]).toMatchObject({ enabled: false, reason: '当前账号没有补发权限' });
  });
});

describe('reply templates', () => {
  it('never offers the automatic re-issue reply', () => {
    expect(replyTemplates.map((item) => item.id)).toEqual(['not_paid', 'already_active', 'download_help', 'login_help', 'generic']);
    expect((replyTemplates as readonly { id: string }[]).some((item) => item.id === 'reissued')).toBe(false);
  });
});

describe('re-issue flow', () => {
  it('a confirmed submit fixes one idempotency key; unknown outcome keeps it and requires a refresh before resending', () => {
    let state = reissueReducer(initialReissue, { type: 'open', key: 'k'.repeat(36) });
    state = reissueReducer(state, { type: 'submit' });
    expect(state).toMatchObject({ phase: 'submitting', key: 'k'.repeat(36) });
    state = reissueReducer(state, { type: 'failed', error: new AdminApiError(0, 'unknown', undefined, undefined, [], true) });
    expect(state).toMatchObject({ phase: 'unknown', key: 'k'.repeat(36), refreshed: false });
    expect(reissueReducer(state, { type: 'submit' })).toBe(state);  // no automatic resend
    expect(reissueReducer(state, { type: 'close' })).toBe(state);   // cannot dismiss before checking
    expect(reissueReducer(reissueReducer(state, { type: 'refreshed' }), { type: 'close' })).toEqual(initialReissue);
    state = reissueReducer(state, { type: 'refreshed' });
    state = reissueReducer(state, { type: 'submit' });
    expect(state).toMatchObject({ phase: 'submitting', key: 'k'.repeat(36) });
  });
  it('a definite rejection drops the key and shows the reason; success closes', () => {
    let state = reissueReducer(initialReissue, { type: 'open', key: 'a'.repeat(36) });
    state = reissueReducer(reissueReducer(state, { type: 'submit' }), { type: 'failed', error: new AdminApiError(409, 'verification_stale') });
    expect(state).toMatchObject({ phase: 'rejected', key: undefined, message: '核实结果已过期，请重新核实付款' });
    state = reissueReducer(initialReissue, { type: 'open', key: 'b'.repeat(36) });
    expect(reissueReducer(reissueReducer(state, { type: 'submit' }), { type: 'succeeded' })).toEqual(initialReissue);
  });
  it('maps support error codes, falling back to the generic message', () => {
    expect(supportErrorText(new AdminApiError(409, 'subscription_active'))).toBe('用户绑定了订阅，不能补发一次性会员');
    expect(supportErrorText(new AdminApiError(409, 'something_else'))).toBe(new AdminApiError(409).message);
  });
});
