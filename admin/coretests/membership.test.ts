import { describe, expect, it, vi } from 'vitest';
import { request } from '@umijs/max';
import { MembershipAttempt, membershipAttempt, membershipAuditLabel, membershipPatch, membershipReason } from '../src/components/business/membershipPolicy';
import { AdminApiError } from '../src/services/admin/errors';
import { adminApi } from '../src/services/admin/api';
import { setSession } from '../src/services/admin/session';
import { canUseFeature } from '../src/config/resourceConfig';
import { mockMeta, users } from '../mock/fixtures';
import { readFileSync } from 'node:fs';

describe('membership control request safety', () => {
  it('keeps the frozen contract and generated Chinese descriptions intact', () => {
    for (const path of ['../docs/production/admin-api-v1.openapi.yaml', 'src/services/admin/types.ts', 'mock/fixtures.ts', 'src/config/resourceConfig.ts']) {
      expect(readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')).not.toMatch(/\?{3,}/);
    }
  });
  it('supports permanent, independent future expiry, disabled and auto', () => {
    const base = { mode: 'enabled' as const, expires_at: null, reason: '管理员核实后为此用户开通会员', expected_revision: '9007199254740993' };
    expect(membershipPatch(base, Date.parse('2026-10-29T00:00:00Z'))).toEqual(base);
    expect(membershipPatch({ ...base, expires_at: '2027-01-01T00:00:00Z' }, 0).expires_at).toContain('2027');
    for (const mode of ['auto', 'disabled'] as const) expect(membershipPatch({ ...base, mode }, 0).expires_at).toBeNull();
    expect(() => membershipPatch({ ...base, expires_at: '2026-10-29T00:00:00Z' }, Date.parse('2026-10-29T00:00:00Z'))).toThrow();
    expect(() => membershipPatch({ ...base, mode: 'auto', expires_at: '2027-01-01T00:00:00Z' }, 0)).toThrow();
    expect(() => membershipPatch({ ...base, reason: '太短' }, 0)).toThrow();
  });
  it('freezes body and key through unknown results and dialog reopen', () => {
    const attempt = new MembershipAttempt();
    const body = membershipPatch({ mode: 'enabled', expires_at: null, reason: '管理员核实后为此用户开通会员', expected_revision: '0' }, 0);
    const first = attempt.prepare(body);
    attempt.fail(new AdminApiError(503, 'transaction_uncertain', undefined, undefined, [], true));
    expect(attempt.canSubmit()).toBe(false);
    attempt.refreshed(true); expect(attempt.canSubmit()).toBe(false);
    attempt.checked = true; expect(attempt.canSubmit()).toBe(true);
    expect(attempt.prepare({ ...body, mode: 'disabled' })).toBe(first);
    expect(first.body.mode).toBe('enabled'); expect(Object.isFrozen(first.body)).toBe(true);
  });
  it('conflict blocks new attempts until explicit successful refresh and fresh confirmation', () => {
    const attempt = new MembershipAttempt();
    attempt.prepare({ mode: 'disabled', expires_at: null, reason: '管理员核实后暂停此用户的会员', expected_revision: '0' });
    attempt.fail(new AdminApiError(409, 'revision_conflict'));
    expect(attempt.conflict).toBe(true); expect(attempt.canSubmit()).toBe(false);
    attempt.refreshed(false); expect(attempt.conflict).toBe(true);
    attempt.refreshed(true); expect(attempt.conflict).toBe(false); expect(attempt.pending).toBeUndefined();
  });
  it.each([
    [401, 'unauthenticated'], [403, 'forbidden'], [404, 'not_found'], [422, 'validation_failed'],
    [429, 'rate_limited'], [503, 'capability_unavailable'], [409, 'idempotency_conflict'], [409, 'unknown'],
  ])('retains an unknown original request when replay is rejected with %s/%s', (status, errorType) => {
    const actor = `unknown-replay-actor-${status}-${errorType}`, target = `unknown-replay-target-${status}-${errorType}`;
    const attempt = membershipAttempt(actor, target);
    const body = membershipPatch({ mode: 'enabled', expires_at: '2027-01-01T00:00:00Z', reason: '管理员核实后为此用户开通会员', expected_revision: '0' }, 0);
    const original = attempt.prepare(body);
    attempt.fail(new AdminApiError(503, 'transaction_uncertain', undefined, undefined, [], true));
    attempt.refreshed(true); attempt.checked = true;
    expect(attempt.prepare(body)).toBe(original);
    attempt.fail(new AdminApiError(Number(status), String(errorType)));
    const sameActor = membershipAttempt(actor, target);
    expect(sameActor.pending).toBe(original);
    expect(sameActor.unknown).toBe(true);
    expect(sameActor.checked).toBe(false); expect(sameActor.hasRefreshed).toBe(false);
    expect(sameActor.canSubmit()).toBe(false);
    expect(membershipAttempt(`${actor}-replacement`, target).pending).toBeUndefined();
    sameActor.refreshed(true); sameActor.checked = true;
    // Replaying after the original deadline passes must still use the exact original body/key.
    expect(sameActor.prepare({ ...body, expires_at: null, mode: 'disabled' })).toBe(original);
    expect(sameActor.pending?.body).toEqual(body);
    sameActor.complete();
  });
  it('accepts an authoritative receipt-missing revision conflict after an unknown result', () => {
    const attempt = new MembershipAttempt();
    attempt.prepare({ mode: 'disabled', expires_at: null, reason: '管理员核实后暂停此用户的会员', expected_revision: '0' });
    attempt.fail(new AdminApiError(503, 'transaction_uncertain', undefined, undefined, [], true));
    attempt.fail(new AdminApiError(409, 'revision_conflict'));
    expect(attempt.pending).toBeUndefined(); expect(attempt.unknown).toBe(false);
    expect(attempt.conflict).toBe(true); expect(attempt.canSubmit()).toBe(false);
  });
  it.each([401, 403])('releases a first attempt definitely rejected with %s', (status) => {
    const attempt = new MembershipAttempt();
    attempt.prepare({ mode: 'disabled', expires_at: null, reason: '管理员核实后暂停此用户的会员', expected_revision: '0' });
    attempt.fail(new AdminApiError(status, 'forbidden'));
    expect(attempt.pending).toBeUndefined(); expect(attempt.unknown).toBe(false);
  });
  it('requires the new permission plus known capability and supports no payment record', () => {
    const meta = mockMeta('2026-10-29T00:00:00Z'); meta.features.membership_control_write.ready = true;
    expect(canUseFeature(['memberships:write'], meta, 'memberships:write', 'membership_control_write')).toBe(true);
    expect(canUseFeature(['users:read'], meta, 'memberships:write', 'membership_control_write')).toBe(false);
    expect(users.find(u => u.membership.revision === null)?.membership.control_revision).toBe('0');
    expect(membershipReason('admin_expired')).toContain('到期');
  });
  it('explains backend membership audit action from actual before/after control fields', () => {
    const change = { control_mode_before: 'enabled', control_mode_after: 'disabled', control_revision_before: '2', control_revision_after: '3', control_expires_at_before: null, control_expires_at_after: null } as const;
    expect(membershipAuditLabel(change)).toBe('管理员停用会员');
    expect(membershipAuditLabel({ ...change, control_mode_after: 'auto' })).toBe('恢复自动管理');
    expect(membershipAuditLabel({ ...change, control_revision_after: '2' })).toBe('保持原会员设置');
  });
  it('sends the new PATCH once with csrf and unchanged key', async () => {
    setSession({ user_id: 'synthetic', csrf_token: 'csrf' } as never);
    vi.mocked(request).mockResolvedValueOnce({ changed: true });
    await adminApi.adminSetUserMembership('target', { mode: 'enabled', expires_at: null, reason: '管理员核实后为此用户开通会员', expected_revision: '0' }, 'same-membership-key-123');
    expect(request).toHaveBeenLastCalledWith('/demo/api/admin/v1/users/target/membership', expect.objectContaining({ method: 'PATCH', headers: { 'X-CSRF-Token': 'csrf', 'Idempotency-Key': 'same-membership-key-123' } }));
  });
});
