"""Shared fulfilment of a paid one-time Checkout (PostgreSQL): used by payment notifications (billing_inbox)
and by the admin's reviewed re-issue, so both grant membership by exactly the same rule.

Callers hold the account/checkout row locks, decide whether the checkout may be fulfilled (e.g. the
notification path's superseded-checkout check) and bump revisions.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert

from ..models import BillingPayment
from .billing_pg import locked


class PaymentBindingError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def bind_payment(session, account, payment_intent, source) -> bool:
    """Bind the PaymentIntent receipt to this account; False if the payment was revoked."""
    if not payment_intent:
        raise PaymentBindingError('payment_binding_absent')
    session.execute(insert(BillingPayment).values(payment_intent=payment_intent, user_id=None, source_id=None, revoked=False)
                    .on_conflict_do_nothing(index_elements=['payment_intent']))
    receipt = locked(session, BillingPayment, BillingPayment.payment_intent, payment_intent)
    if receipt.user_id not in {None, account.user_id} or receipt.source_id not in {None, source}:
        raise PaymentBindingError('payment_binding_mismatch')
    receipt.user_id, receipt.source_id = account.user_id, source
    session.add(receipt)
    return not receipt.revoked


def fulfil_paid_checkout(session, account, attempt, payment_intent, *, now_ts: float) -> bool:
    """Grant attempt.duration_days from the later of now and the current expiry; mark the checkout paid."""
    allowed = bind_payment(session, account, payment_intent, payment_intent)
    account.entitlement_source = payment_intent
    account.status = 'active' if allowed else 'expired'
    account.expires_at = max(now_ts, account.expires_at) + attempt.duration_days * 86400 if allowed else 0
    account.subscription_id, account.cancel_at_period_end = None, False
    attempt.fulfilled, attempt.state = True, 'paid'
    session.add(account)
    session.add(attempt)
    return allowed
