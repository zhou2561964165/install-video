"""Customer-support issue types and reply templates (data only; change wording here, not in code)."""
from __future__ import annotations

NOTE_MAX = 500  # user note / reply note, trimmed, in code points

CATEGORIES: dict[str, str] = {
    'membership_not_credited': '会员付款后未到账',
    'download_failing': '下载一直失败',
    'login_problem': '账号无法登录',
    'other': '其他问题',
}

TEMPLATES: dict[str, str] = {
    'reissued': '已为您补发 {days} 天会员，请刷新会员页查看',
    'not_paid': '经核实该订单未完成支付，未产生扣款',
    'already_active': '经核实您的会员已生效，请刷新会员页查看',
    'download_help': '已收到，请尝试重新解析链接或更换清晰度；若仍失败请再次反馈',
    'login_help': '请使用注册邮箱登录；如忘记密码请联系客服说明注册邮箱',
    'generic': '已收到您的反馈，我们会尽快处理',
}

# 'reissued' is only ever sent automatically by a successful re-issue.
MANUAL_TEMPLATES: frozenset[str] = frozenset(TEMPLATES) - {'reissued'}


def render(template_id: str, **values) -> str:
    if template_id not in TEMPLATES:
        raise ValueError('unknown template')
    return TEMPLATES[template_id].format(**values)
