import { AdminApiError } from '@/services/admin/errors';
import type { Schemas } from '@/services/admin/types';

/** Display data for support tickets. Server codes stay authoritative; unknown future values remain visible. */
const labels = {
  category: { membership_not_credited: '会员付款后未到账', download_failing: '下载一直失败', login_problem: '账号无法登录', other: '其他问题' },
  state: { open: '待处理', resolved: '已解决', rejected: '已驳回' },
  priority: { priority: '优先', normal: '普通' },
  resolution: { reissued: '已补发会员', replied: '已回复', rejected: '已驳回' },
  check: {
    verified: '已核实付款', session_incomplete: '支付会话未完成', not_paid: '未支付', user_mismatch: '付款用户不一致',
    mode_mismatch: '支付类型不符', livemode_mismatch: '环境不一致', price_mismatch: '商品价格不符',
    payment_not_succeeded: '付款未成功', refunded: '已退款', disputed: '有争议',
  },
  reason: {
    ticket_closed: '工单已结单', not_reissuable_category: '该问题类型不能补发', stripe_read_key_missing: '未配置支付平台只读核实密钥',
    no_stripe_session: '该订单没有支付平台会话，只能人工处理', already_fulfilled: '该订单已开通会员', attempts_exhausted: '核实次数已用完',
    already_reissued: '该订单已补发过', not_verified: '尚未向支付平台核实付款', verification_stale: '核实结果已过期，请重新核实付款',
    membership_active: '用户会员仍由另一笔付款生效中，不能叠加补发', subscription_active: '用户绑定了订阅，不能补发一次性会员',
    checkout_mismatch: '订单与工单用户不一致', payment_conflict: '付款记录冲突，无法补发',
    payment_provider_unavailable: '支付平台暂时无法访问，请稍后重试', capability_unavailable: '补发能力未就绪',
    invalid_template: '请选择可用的回复模板', idempotency_key_required: '请求缺少幂等键，请刷新后重试',
  },
} as const;
export type SupportLabelDomain = keyof typeof labels;

export function supportLabel(domain: SupportLabelDomain, value: string | null | undefined): string {
  if (value === null || value === undefined) return '未设置';
  return (labels[domain] as Record<string, string>)[value] ?? `未知（${value}）`;
}
export const supportEnumText = (domain: SupportLabelDomain) => labels[domain] as Record<string, string>;

/** Manual replies only; the re-issue reply is sent automatically by a successful re-issue. Mirrors support_catalog.py. */
export const replyTemplates = [
  { id: 'not_paid', name: '未完成支付', text: '经核实该订单未完成支付，未产生扣款' },
  { id: 'already_active', name: '会员已生效', text: '经核实您的会员已生效，请刷新会员页查看' },
  { id: 'download_help', name: '下载问题指引', text: '已收到，请尝试重新解析链接或更换清晰度；若仍失败请再次反馈' },
  { id: 'login_help', name: '登录问题指引', text: '请使用注册邮箱登录；如忘记密码请联系客服说明注册邮箱' },
  { id: 'generic', name: '通用回复', text: '已收到您的反馈，我们会尽快处理' },
] as const;
export const NOTE_MAX = 500;

export type ActionName = 'verify' | 'reissue' | 'reply' | 'reject';
const ACTION_ORDER: ActionName[] = ['verify', 'reissue', 'reply', 'reject'];
const PERMISSION: Record<ActionName, string> = { verify: 'support:write', reissue: 'support:reissue', reply: 'support:write', reject: 'support:write' };
export type ActionView = { action: ActionName; visible: boolean; enabled: boolean; reason?: string };

/** Write buttons are shown to operators with support:write; enabled only when the server allows it and the permission is held. */
export function actionViews(actions: Schemas['SupportActions'], permissions: readonly string[]): ActionView[] {
  const writer = permissions.includes('support:write');
  return ACTION_ORDER.map((action) => {
    const server = actions[action] as Schemas['SupportAction'];
    const permitted = permissions.includes(PERMISSION[action]);
    const reason = !server.allowed ? supportLabel('reason', server.reason ?? 'unknown') : !permitted ? '当前账号没有补发权限' : undefined;
    return { action, visible: writer, enabled: writer && server.allowed && permitted, reason };
  });
}

export function supportErrorText(error: unknown): string {
  if (!(error instanceof AdminApiError)) return new AdminApiError(0).message;
  const known = (labels.reason as Record<string, string>)[error.errorType];
  return known ?? error.message;
}

export type ReissueState = {
  phase: 'idle' | 'confirming' | 'submitting' | 'unknown' | 'rejected';
  key?: string; refreshed: boolean; message?: string;
};
export type ReissueEvent =
  | { type: 'open'; key: string } | { type: 'close' } | { type: 'submit' } | { type: 'succeeded' }
  | { type: 'failed'; error: unknown } | { type: 'refreshed' };
export const initialReissue: ReissueState = { phase: 'idle', refreshed: false };

/** One confirmed re-issue = one idempotency key. An unknown outcome keeps the key and never resends until the operator refreshed. */
export function reissueReducer(state: ReissueState, event: ReissueEvent): ReissueState {
  switch (event.type) {
    case 'open':
      return state.phase === 'unknown' ? { ...state } : { phase: 'confirming', key: state.key ?? event.key, refreshed: false };
    case 'close':
      // After an unknown outcome the dialog closes only once the operator refreshed; a later attempt with a
      // new key cannot grant twice (the server refuses an already re-issued order).
      return state.phase === 'submitting' || (state.phase === 'unknown' && !state.refreshed) ? state : initialReissue;
    case 'submit':
      if (!state.key || state.phase === 'submitting' || (state.phase === 'unknown' && !state.refreshed)) return state;
      return { ...state, phase: 'submitting', message: undefined };
    case 'succeeded':
      return initialReissue;
    case 'refreshed':
      return state.phase === 'unknown' ? { ...state, refreshed: true } : state;
    case 'failed': {
      const error = event.error;
      const unknown = !(error instanceof AdminApiError) || error.outcomeUnknown || error.status === 0 || error.status >= 500;
      if (unknown) return { phase: 'unknown', key: state.key, refreshed: false, message: '结果未知，请刷新核对后再确认' };
      return { phase: 'rejected', key: undefined, refreshed: false, message: supportErrorText(error) };
    }
  }
}
