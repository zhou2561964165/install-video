import type { Schemas } from '../../services/admin/types';
import { normalizeAdminError } from '../../services/admin/errors';
import { isUtcTime } from '../../utils/adminTime';

export const membershipModes = { auto: '自动管理', enabled: '管理员启用', disabled: '管理员停用' } as const;
const reasons: Record<string, string> = {
  payment_active: '原会员记录已启用，仍在付款有效期内', payment_expired: '原付款会员已到期',
  payment_inactive: '暂无生效的付款会员', admin_enabled: '管理员启用的会员正在生效',
  admin_expired: '管理员设置的期限已到期', admin_disabled: '管理员已停用会员权益',
};
export const membershipReason = (reason: string) => reasons[reason] ?? '会员状态暂无法解释，请刷新核对';
export function membershipAuditLabel(change: Schemas['AuditChange'] | null) {
  if (!change || !('control_mode_after' in change)) return '设置会员权益';
  const value = change as Schemas['MembershipAuditChange'];
  if (value.control_revision_before === value.control_revision_after) return '保持原会员设置';
  return value.control_mode_after === 'auto' ? '恢复自动管理' : value.control_mode_after === 'disabled' ? '管理员停用会员' : '管理员启用会员';
}
export function membershipPatch(body: Schemas['MembershipPatch'], now = Date.now(), min = 10, max = 500): Schemas['MembershipPatch'] {
  const reason = body.reason.trim(), length = Array.from(reason).length;
  if (!Object.hasOwn(membershipModes, body.mode) || !/^(0|[1-9][0-9]*)$/.test(body.expected_revision) || length < min || length > max) throw new Error('请检查管理方式及操作原因。');
  if (body.expires_at !== null && (body.mode !== 'enabled' || !isUtcTime(body.expires_at) || Date.parse(body.expires_at) <= now)) throw new Error('请填写未来的有效期限。');
  return { mode: body.mode, expires_at: body.expires_at, reason, expected_revision: body.expected_revision };
}

/** Remains in memory when a dialog closes or its row is refreshed. Never persisted to disk. */
export class MembershipAttempt {
  pending?: { key: string; body: Readonly<Schemas['MembershipPatch']> };
  conflict = false;
  unknown = false;
  hasRefreshed = false;
  checked = false;
  busy = false;
  error?: unknown;
  canSubmit() { return !this.busy && !this.conflict && (!this.unknown || (this.hasRefreshed && this.checked)); }
  prepare(body: Schemas['MembershipPatch']) {
    if (!this.canSubmit()) throw new Error('请先核对上次请求的结果。');
    return this.pending ??= { key: crypto.randomUUID(), body: Object.freeze({ ...body }) };
  }
  fail(value: unknown) {
    this.error = value;
    const error = normalizeAdminError(value, true);
    // Only revision_conflict is issued after the locked transaction checks for the original receipt.
    // Authorization, schema/config rejections and generic conflicts do not settle an earlier unknown write.
    const unresolvedReplay = this.unknown && Boolean(this.pending) && !(error.status === 409 && error.errorType === 'revision_conflict');
    if (error.outcomeUnknown || error.errorType === 'transaction_uncertain' || unresolvedReplay) {
      this.unknown = true; this.checked = false; this.hasRefreshed = false;
    } else if (error.status === 409) {
      this.conflict = true; this.pending = undefined; this.unknown = false;
    } else { this.pending = undefined; this.unknown = false; }
  }
  refreshed(success: boolean) {
    this.checked = false;
    if (success) { this.hasRefreshed = true; this.conflict = false; }
  }
  complete() { this.pending = undefined; this.conflict = false; this.unknown = false; this.error = undefined; this.checked = false; this.hasRefreshed = false; }
}
const attempts = new Map<string, MembershipAttempt>();
export function membershipAttempt(actor: string, user: string) {
  const key = JSON.stringify([actor, user]);
  let attempt = attempts.get(key);
  if (!attempt) { attempt = new MembershipAttempt(); attempts.set(key, attempt); }
  return attempt;
}
