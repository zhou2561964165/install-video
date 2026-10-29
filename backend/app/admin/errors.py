"""Admin error shape (contract Error): {detail:{error_type,error,request_id,field_errors?}}.

Only fixed safe texts are ever returned; exception messages, provider payloads and stack traces never are.
"""
from __future__ import annotations

SAFE_TEXT = {
    'not_found': '请求的资源不存在',
    'method_not_allowed': '不支持的请求方法',
    'validation_failed': '请求参数不合法',
    'unauthenticated': '请先登录管理后台',
    'login_failed': '邮箱或密码错误，或没有管理权限',
    'forbidden': '没有执行此操作的权限',
    'origin_rejected': '请求来源不被允许',
    'csrf_rejected': '请求校验失败，请刷新后重试',
    'capability_unavailable': '该功能当前未开放',
    'rate_limited': '尝试过于频繁，请稍后再试',
    'admin_unavailable': '管理后台暂不可用',
    'internal_error': '服务器内部错误',
    'invalid_template': '请选择可用的回复模板',
    'ticket_closed': '工单已结束，不能再修改',
    'not_reissuable_category': '该类型工单不能补发会员',
    'checkout_mismatch': '订单与工单用户不一致',
    'no_stripe_session': '该订单没有支付平台会话，无法自动核实',
    'already_fulfilled': '该订单已履行，无需补发',
    'attempts_exhausted': '核实次数已用完',
    'not_verified': '请先向支付平台核实付款',
    'verification_stale': '核实已过期，请重新核实',
    'payment_conflict': '付款记录冲突，无法补发',
    'already_reissued': '该订单已补发过',
    'membership_active': '用户会员仍由另一笔付款生效中，不能叠加补发',
    'subscription_active': '用户绑定了订阅，不能补发一次性会员',
    'payment_provider_unavailable': '支付平台暂时无法访问，请稍后重试',
    'idempotency_key_required': '缺少幂等键',
}


class AdminError(Exception):
    def __init__(self, status: int, error_type: str, *, field_errors: list | None = None,
                 headers: dict | None = None):
        super().__init__(error_type)
        self.status, self.error_type = status, error_type
        self.field_errors, self.headers = field_errors, headers or {}


def body(error_type: str, request_id: str, field_errors: list | None = None) -> dict:
    detail = {'error_type': error_type, 'error': SAFE_TEXT.get(error_type, SAFE_TEXT['internal_error']),
              'request_id': request_id}
    if field_errors:
        detail['field_errors'] = field_errors
    return {'detail': detail}
