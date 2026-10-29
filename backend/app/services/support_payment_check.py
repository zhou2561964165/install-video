"""Verify a one-time Checkout's payment with Stripe for the reviewed membership re-issue.

Reads only, with a dedicated restricted read key (ADMIN_STRIPE_READ_KEY) — never the main secret key.
evaluate() is pure: it decides "verified" or one fixed reason code from the Session (expanded with
line_items and payment_intent.latest_charge). Only the PaymentIntent id and the result are kept.
"""
from __future__ import annotations

from typing import Protocol

import stripe


class ReaderUnavailable(Exception):
    """The provider could not be read (network, auth, timeout, unknown object): nothing is recorded."""


class SessionReader(Protocol):
    def read(self, session_id: str) -> dict: ...


class StripeSessionReader:
    def __init__(self, key: str, timeout: float):
        if not key:
            raise ValueError('a restricted read key is required')
        client = stripe.StripeClient(key, max_network_retries=0, http_client=stripe.RequestsClient(timeout=timeout))
        self._sessions = client.v1.checkout.sessions  # stripe-python >= 14 namespace

    def read(self, session_id: str) -> dict:
        try:
            obj = self._sessions.retrieve(session_id, params={'expand': ['line_items', 'payment_intent.latest_charge']})
            return obj.to_dict()
        except Exception:
            raise ReaderUnavailable() from None


def _price_id(item) -> str | None:
    price = item.get('price') if isinstance(item, dict) else None
    return price.get('id') if isinstance(price, dict) else price


def evaluate(session: dict, *, checkout_price_id: str, user_id: str, livemode: bool | None) -> tuple[str, str | None]:
    """('verified', payment_intent) or (reason, payment_intent-or-None)."""
    intent = session.get('payment_intent')
    intent = intent if isinstance(intent, dict) else None
    pi = intent.get('id') if intent else (session.get('payment_intent') if isinstance(session.get('payment_intent'), str) else None)
    if session.get('status') != 'complete':
        return 'session_incomplete', pi
    if session.get('payment_status') != 'paid':
        return 'not_paid', pi
    if session.get('client_reference_id') != user_id:
        return 'user_mismatch', pi
    if session.get('mode') != 'payment':
        return 'mode_mismatch', pi
    if livemode is None or session.get('livemode') is not livemode:
        return 'livemode_mismatch', pi
    items = (session.get('line_items') or {}).get('data') or []
    if len(items) != 1 or _price_id(items[0]) != checkout_price_id or items[0].get('quantity') != 1:
        return 'price_mismatch', pi
    if not intent or intent.get('status') != 'succeeded':
        return 'payment_not_succeeded', pi
    charge = intent.get('latest_charge')
    if not isinstance(charge, dict) or charge.get('paid') is not True or charge.get('status') != 'succeeded':
        return 'payment_not_succeeded', pi  # unexpanded or unpaid charge: refund/dispute state unknown, fail closed
    if charge.get('refunded') or (charge.get('amount_refunded') or 0) > 0:
        return 'refunded', pi
    if charge.get('disputed'):
        return 'disputed', pi
    return 'verified', pi
