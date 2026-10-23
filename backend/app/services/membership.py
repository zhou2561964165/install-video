"""Persistent, request-time entitlements. Payment configuration does not disable enforcement."""
import time
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..models import Membership, User
from .auth import get_current_user
from .quota_policy import is_unlimited_user


def required() -> HTTPException:
    return HTTPException(403, detail={"error_type": "membership_required", "error": "此功能需要 VIP 会员"})


def is_vip(session: Session, user_id: str) -> bool:
    row = session.get(Membership, user_id)
    return bool(row and row.status == "active" and row.expires_at > time.time())


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
    vip = is_vip(session, user_id)
    return {
        "plan": "vip" if vip else "free",
        "status": ("active" if vip else "expired") if row and row.expires_at else "free",
        "expires_at": datetime.fromtimestamp(row.expires_at, timezone.utc).isoformat() if row and row.expires_at else None,
        "cancel_at_period_end": bool(row and row.cancel_at_period_end),
        "checkout_available": checkout_available() and not vip,
        "portal_available": bool(row and row.customer_id and row.subscription_id and portal_configured()),
        "features": {"max_height": max_height(session, user_id), "subtitles": vip,
                     "translation": vip, "summary": vip},
    }
