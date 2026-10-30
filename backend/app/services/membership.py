"""Persistent, request-time entitlements. Payment configuration does not disable enforcement."""
import time
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..models import Membership, MembershipControl, User
from .auth import get_current_user
from .quota_policy import is_unlimited_user
from .membership_policy import resolve


def entitlement(session: Session, user_id: str, as_of: datetime | None = None):
    return resolve(session.get(Membership, user_id), session.get(MembershipControl, user_id),
                   as_of or datetime.now(timezone.utc))


def manual_control(session: Session, user_id: str) -> bool:
    row = session.get(MembershipControl, user_id)
    return row is not None and row.mode != 'auto'


def require_checkout_auto(session: Session, user_id: str) -> None:
    if manual_control(session, user_id):
        raise HTTPException(409, detail={'error_type': 'membership_managed',
                                        'error': '会员由管理员手动管理，请联系客服'})


def required() -> HTTPException:
    return HTTPException(403, detail={"error_type": "membership_required", "error": "此功能需要 VIP 会员"})


def is_vip(session: Session, user_id: str) -> bool:
    return entitlement(session, user_id).effective


def require_vip(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> User:
    if not is_vip(session, user.id):
        raise required()
    return user


def max_height(session: Session, user_id: str) -> int | None:
    # Existing explicit local developer exemptions retain their access.
    return None if is_vip(session, user_id) or is_unlimited_user(user_id) else settings.membership_free_max_height


def info(session: Session, user_id: str) -> dict:
    from .billing import checkout_available, portal_configured
    row = session.get(Membership, user_id)
    control = session.get(MembershipControl, user_id)
    actual = entitlement(session, user_id)
    vip = actual.effective
    deadline = actual.expires_at.isoformat() if actual.expires_at else None
    managed = control is not None and control.mode != 'auto'
    return {
        "plan": "vip" if vip else "free",
        "status": "active" if vip else ("expired" if actual.reason in {'admin_expired', 'payment_expired'} else "free"),
        "expires_at": deadline,
        "effective_expires_at": deadline,
        "effective_permanent": actual.permanent,
        "effective_reason": actual.reason,
        "control_mode": control.mode if control else 'auto',
        "control_revision": str(control.revision) if control else '0',
        "control_expires_at": control.expires_at.isoformat() if control and control.expires_at else None,
        "base_expires_at": datetime.fromtimestamp(row.expires_at, timezone.utc).isoformat() if row and row.expires_at else None,
        "cancel_at_period_end": bool(row and row.cancel_at_period_end),
        "checkout_available": checkout_available() and not vip and not managed,
        "checkout_unavailable_reason": '会员由管理员手动管理，请联系客服' if managed else None,
        "portal_available": bool(row and row.customer_id and row.subscription_id and portal_configured()),
        "features": {"max_height": None if vip or is_unlimited_user(user_id) else settings.membership_free_max_height, "subtitles": vip,
                     "translation": vip, "summary": vip},
    }
