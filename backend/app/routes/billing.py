import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from ..config import settings
from ..db import get_session
from ..models import User
from ..services import billing, membership
from ..services.auth import get_current_user

router = APIRouter()


@router.get("/api/membership/plans")
def plans():
    return billing.plans()


@router.get("/api/membership")
def current(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return membership.info(session, user.id)


@router.post("/api/billing/checkout")
def checkout(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return billing.checkout(session, user)


@router.post("/api/billing/portal")
def portal(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return billing.portal(session, user)


@router.post("/api/billing/webhook")
async def webhook(request: Request, session: Session = Depends(get_session)):
    if not settings.stripe_webhook_secret:
        raise billing.unavailable()
    # Bound before buffering. Streaming also bounds requests without Content-Length.
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 1024 * 1024:
            raise HTTPException(413, detail={"error_type": "billing_payload", "error": "通知过大"})
    try:
        event = stripe.Webhook.construct_event(bytes(payload), request.headers.get("stripe-signature", ""),
                                              settings.stripe_webhook_secret, tolerance=300)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(400, detail={"error_type": "billing_signature", "error": "支付通知签名无效"}) from None
    # The synchronous SDK runs off the event loop, bounded by its configured timeout.
    from starlette.concurrency import run_in_threadpool
    if session.get_bind().dialect.name == 'postgresql' or settings.billing_inbox_mode != 'legacy_sync':
        from ..services.billing_pg import BillingConfiguration
        from ..services.billing_inbox import receive
        cfg = BillingConfiguration.configured(settings, session.get_bind().dialect.name)
        engine = session.get_bind()
        session.rollback()
        return await run_in_threadpool(receive, engine, event, bytes(payload), cfg)
    await run_in_threadpool(billing.apply_event, session, event)
    return {"received": True}
