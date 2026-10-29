"""Stripe hosted billing; durable checkout intents and signed, transactional fulfilment.

Never grant from redirect parameters. Webhooks reconcile the current Stripe subscription
so delivery order cannot restore a canceled subscription. No SDK network retries.
"""
import logging
import time
from urllib.parse import urlsplit

import stripe
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from ..config import settings
from ..models import BillingCheckout, BillingEvent, BillingPayment, Membership, User
from .membership import is_vip

logger = logging.getLogger(__name__)


def _checkout_failure(operation, exc):
    # Never log exception text, headers or response bodies: provider messages can
    # contain credentials and request data. Fixed fields still identify failures.
    status = getattr(exc, "http_status", None)
    logger.warning("Stripe checkout failed operation=%s exception_class=%s http_status=%s",
                   operation, type(exc).__name__, status if type(status) is int else None)
    if isinstance(exc, stripe.IdempotencyError):
        return unavailable("支付状态待核实，请稍后刷新会员状态或联系管理员；原支付请求已保留")
    if isinstance(exc, (stripe.InvalidRequestError, stripe.AuthenticationError, stripe.PermissionError)):
        return unavailable("支付服务配置暂不可用，请联系管理员；原支付请求已保留")
    return unavailable("支付连接失败，请稍后重试；重复点击不会创建新的支付")


def unavailable(message="支付暂未开放"):
    return HTTPException(503, detail={"error_type": "billing_unavailable", "error": message})


def portal_configured() -> bool:
    try:
        origin = urlsplit(settings.stripe_public_origin)
        origin.port  # Validate malformed ports without exposing config values.
        return bool(settings.stripe_secret_key
                and origin.scheme in {"http", "https"} and origin.netloc and not origin.username
                and origin.hostname
                and not origin.query and not origin.fragment and origin.path in {"", "/"}
                and (origin.scheme == "https" or origin.hostname in {"localhost", "127.0.0.1"}))
    except ValueError:
        return False


def checkout_available() -> bool:
    return bool(portal_configured() and settings.stripe_webhook_secret and settings.stripe_price_id
                and settings.stripe_price_label and settings.stripe_billing_mode in {"payment", "subscription"})


def client():
    return stripe.StripeClient(settings.stripe_secret_key, max_network_retries=0,
        http_client=stripe.RequestsClient(timeout=settings.stripe_timeout_seconds))


def _mapping(obj):
    return isinstance(obj, (dict, stripe.StripeObject))


def plans() -> dict:
    mode = settings.stripe_billing_mode or None
    return {"enabled": checkout_available(), "checkout_available": checkout_available(),
            "price_label": settings.stripe_price_label or None, "billing_mode": mode,
            "renewal_label": ("自动续费，可在会员管理中取消" if mode == "subscription" else
                              f"单次支付，有效 {settings.stripe_vip_duration_days} 天，不自动续费") if mode else "价格与周期待配置",
            "free_max_height": settings.membership_free_max_height,
            "plans": [{"id": "free", "name": "免费版", "downloads_limit": None, "max_height": settings.membership_free_max_height},
                      {"id": "vip", "name": "VIP 高级版", "downloads_limit": None, "max_height": None,
                       "subtitles": True, "translation": True, "summary": True,
                       "batch_download": False, "priority_support": False}]}


def _write_lock(session):
    # SQLite is this project's supported store. Serialize claims and webhook application
    # across workers; the lock is released before outbound checkout API calls.
    session.rollback()
    session.exec(text("BEGIN IMMEDIATE"))


def checkout(session: Session, user: User) -> dict:
    if session.get_bind().dialect.name == 'postgresql' or settings.billing_inbox_mode != 'legacy_sync':
        from .billing_pg import BillingConfiguration, checkout as pg_checkout
        cfg = BillingConfiguration.configured(settings, session.get_bind().dialect.name)
        if not checkout_available():
            raise unavailable()
        uid, engine = user.id, session.get_bind()
        session.rollback()
        return pg_checkout(engine, uid, cfg, settings, client)
    if not checkout_available():
        raise unavailable()
    user_id = user.id
    _write_lock(session)
    account = session.get(Membership, user_id)
    if account is None:
        account = Membership(user_id=user_id)
        session.add(account)
    if is_vip(session, user_id):
        session.rollback()
        raise HTTPException(409, detail={"error_type": "membership_active", "error": "会员已生效，请使用会员管理"})
    attempt = session.get(BillingCheckout, account.active_checkout_id) if account.active_checkout_id else None
    if attempt and attempt.state == "open" and attempt.expires_at > time.time():
        result = {"url": attempt.url}
        session.rollback()
        return result
    if attempt and attempt.state not in {"expired", "paid", "failed"}:
        if not attempt.stripe_id and time.time() - attempt.created_at > 23 * 3600:
            # Stripe idempotency retention is finite. Never replace an uncertain charge
            # with a new intent after retention; an operator must reconcile it.
            session.rollback()
            raise unavailable("支付状态待核实，请稍后再试")
    else:
        if account.subscription_id:
            revision, old_id = account.revision, account.subscription_id
            session.rollback()
            try:
                current_sub = client().v1.subscriptions.retrieve(old_id)
            except Exception:
                session.rollback()
                raise unavailable("订阅状态待核实，请使用会员管理") from None
            _write_lock(session)
            account = session.get(Membership, user_id)
            if account.revision != revision:
                session.rollback()
                raise unavailable("会员状态已更新，请重试")
            if current_sub.get("status") not in {"canceled", "incomplete_expired"}:
                session.rollback()
                raise HTTPException(409, detail={"error_type": "membership_active", "error": "已有订阅，请使用会员管理"})
        attempt = BillingCheckout(user_id=user_id, price_id=settings.stripe_price_id,
            mode=settings.stripe_billing_mode, duration_days=settings.stripe_vip_duration_days,
            origin=settings.stripe_public_origin.rstrip("/"), customer_id=account.customer_id)
        session.add(attempt)
        account.active_checkout_id = attempt.id
        account.revision += 1
        session.add(account)
    attempt_id, customer_id = attempt.id, attempt.customer_id
    params = {"mode": attempt.mode, "line_items": [{"price": attempt.price_id, "quantity": 1}],
              # This integration uses ordinary Checkout. An account-level Managed
              # Payments default must not silently opt this session into it.
              "managed_payments": {"enabled": False},
              "client_reference_id": user_id, "metadata": {"checkout_id": attempt_id},
              "success_url": attempt.origin + "/?membership=success",
              "cancel_url": attempt.origin + "/?membership=cancel"}
    if customer_id:
        params["customer"] = customer_id
    elif attempt.mode == "payment":
        params["customer_creation"] = "always"
    if attempt.mode == "subscription":
        # Delayed initial payments may fail while Stripe keeps the subscription
        # active. Card-only subscriptions avoid orphan recurring billing; one-time
        # payments retain dynamic methods and the async success/failure lifecycle.
        params["payment_method_types"] = ["card"]
    session.commit()
    operation = "connect"
    try:
        api = client()
        # Existing sessions are retrieved rather than recreated after local expiration.
        current = session.get(BillingCheckout, attempt_id)
        stripe_id = current.stripe_id
        session.rollback()
        operation = "retrieve" if stripe_id else "create"
        obj = (api.v1.checkout.sessions.retrieve(stripe_id) if stripe_id else
               api.v1.checkout.sessions.create(params, options={"idempotency_key": "membership-" + attempt_id}))
        _write_lock(session)
        current = session.get(BillingCheckout, attempt_id)
        current.stripe_id = obj["id"]
        current.url = obj.get("url")
        current.expires_at = obj.get("expires_at", 0)
        if current.state not in {"paid", "expired", "failed"}:
            current.state = "expired" if obj.get("status") == "expired" else "open"
        session.add(current)
        session.commit()
        if obj.get("status") != "open" or not obj.get("url"):
            raise unavailable("支付状态待确认，请稍后刷新")
        return {"url": obj["url"]}
    except HTTPException:
        raise
    except Exception as exc:
        session.rollback()
        raise _checkout_failure(operation, exc) from None


def portal(session: Session, user: User):
    row = session.get(Membership, user.id)
    if not portal_configured() or not row or not row.customer_id or not row.subscription_id:
        raise unavailable("当前没有可管理的订阅")
    customer_id = row.customer_id
    session.rollback()  # Provider I/O never holds a read transaction/connection.
    failed = False
    try:
        obj = client().v1.billing_portal.sessions.create({"customer": customer_id,
            "return_url": settings.stripe_public_origin.rstrip("/") + "/?membership=return"})
        result = {"url": obj["url"]}
    except Exception:
        failed = True
    if failed:
        raise unavailable("会员管理暂不可用")
    return result


def _id(obj):
    return obj.get("id") if _mapping(obj) else obj


def _bind_payment(session, account, payment_intent, source_id):
    if not payment_intent:
        raise ValueError("Payment intent required")
    receipt = session.get(BillingPayment, payment_intent)
    if receipt and receipt.user_id not in {None, account.user_id}:
        raise ValueError("Payment binding mismatch")
    if receipt is None:
        receipt = BillingPayment(payment_intent=payment_intent)
    receipt.user_id, receipt.source_id = account.user_id, source_id
    session.add(receipt)
    return not receipt.revoked


def _subscription_state(session, account, subscription_id, sub, price_id):
    if _id(sub.get("customer")) != account.customer_id:
        raise ValueError("Customer mismatch")
    if account.subscription_id and account.subscription_id != subscription_id:
        raise ValueError("Subscription mismatch")
    account.subscription_id = subscription_id
    account.cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
    if sub.get("status") in {"canceled", "unpaid", "incomplete_expired", "paused"}:
        account.status, account.expires_at = "expired", 0
        return
    invoice = sub.get("latest_invoice")
    if not _mapping(invoice) or invoice.get("status") != "paid":
        return  # active/trialing without a confirmed paid invoice never grants VIP
    periods = []
    for item in (sub.get("items") or {}).get("data", []):
        if _id(item.get("price")) == price_id:
            periods.append(item.get("current_period_end", sub.get("current_period_end", 0)))
    # The paid invoice's matching line period is the upper bound; a pending renewal
    # may already have moved the subscription's period into an unpaid future month.
    paid_ends = [line.get("period", {}).get("end", 0)
        for line in (invoice.get("lines") or {}).get("data", [])
        if _id(line.get("price")) == price_id or
           _id(((line.get("pricing") or {}).get("price_details") or {}).get("price")) == price_id]
    if periods and paid_ends:
        source_id = invoice.get("id")
        payment_ids = [_id(item.get("payment", {}).get("payment_intent"))
                       for item in (invoice.get("payments") or {}).get("data", []) if item.get("status") == "paid"]
        if invoice.get("payment_intent"):
            payment_ids.append(_id(invoice["payment_intent"]))  # legacy webhook/API versions
        payment_ids = list(dict.fromkeys(pi for pi in payment_ids if pi))
        if not source_id or not payment_ids:
            raise ValueError("Paid invoice payment binding absent")
        allowed = all([_bind_payment(session, account, pi, source_id) for pi in payment_ids])
        account.entitlement_source = source_id
        if not allowed:
            account.status, account.expires_at = "expired", 0
            return
        account.expires_at = min(max(periods), max(paid_ends))
        account.status = "active"


_REVERSALS = {"charge.refunded", "charge.dispute.created", "charge.dispute.funds_withdrawn", "charge.dispute.closed"}


def _preload(session, event):
    """All Stripe network reads happen without a SQLite write/read transaction.

    Capture a local revision first; application must verify it again under lock.
    Concurrent membership changes cause a retry instead of overwriting them.
    """
    kind, obj = event["type"], event["data"]["object"]
    if session.get(BillingEvent, event["id"]):
        session.rollback()
        return None
    account, attempt = None, None
    if kind.startswith("checkout.session."):
        aid = (obj.get("metadata") or {}).get("checkout_id")
        attempt = session.get(BillingCheckout, aid) if aid else None
        if attempt:
            account = session.get(Membership, attempt.user_id)
    elif kind in _REVERSALS:
        pi = _id(obj.get("payment_intent"))
        receipt = session.get(BillingPayment, pi) if pi else None
        account = session.get(Membership, receipt.user_id) if receipt and receipt.user_id else None
    else:
        customer = _id(obj.get("customer"))
        account = session.exec(select(Membership).where(Membership.customer_id == customer)).first() if customer else None
    context = {"user_id": account.user_id if account else None, "revision": account.revision if account else None,
               "old_id": account.subscription_id if account else None,
               "attempt_fulfilled": bool(attempt and attempt.fulfilled), "subscriptions": {}}
    sub_id = None
    if attempt and attempt.mode == "subscription" and obj.get("payment_status") == "paid" and obj.get("status") == "complete":
        sub_id = _id(obj.get("subscription"))
    elif account and account.subscription_id and kind not in _REVERSALS:
        candidate = obj.get("id") if kind.startswith("customer.subscription") else _id(obj.get("subscription")) or _id(
            ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
        if candidate == account.subscription_id:
            sub_id = candidate
    session.rollback()
    if kind in _REVERSALS:
        pi = _id(obj.get("payment_intent"))
        if not pi and kind.startswith("charge.dispute."):
            charge = client().v1.charges.retrieve(_id(obj.get("charge")))
            pi = _id(charge.get("payment_intent"))
        context["payment_intent"] = pi
        # A dispute's Charge lookup may have resolved a previously unknown PI.
        if not context["user_id"] and pi:
            receipt = session.get(BillingPayment, pi)
            account = session.get(Membership, receipt.user_id) if receipt and receipt.user_id else None
            if account:
                context["user_id"], context["revision"] = account.user_id, account.revision
            session.rollback()
    if sub_id:
        context["subscriptions"][sub_id] = client().v1.subscriptions.retrieve(sub_id,
            params={"expand": ["latest_invoice.payments"]})
        if context["old_id"] and context["old_id"] != sub_id and not context["attempt_fulfilled"]:
            context["subscriptions"][context["old_id"]] = client().v1.subscriptions.retrieve(context["old_id"])
    return context


def apply_event(session: Session, event: dict):
    if session.get_bind().dialect.name != 'sqlite' or settings.billing_inbox_mode != 'legacy_sync':
        # PG signed events may only be applied with a durable Inbox lease.
        raise unavailable()
    event_id, kind = event["id"], event["type"]
    obj = event["data"]["object"]
    try:
        context = _preload(session, event)
        if context is None:
            return
        _write_lock(session)
        if session.get(BillingEvent, event_id):
            session.rollback()
            return
        if context["user_id"]:
            current = session.get(Membership, context["user_id"])
            if current is None or current.revision != context["revision"]:
                raise ValueError("Concurrent membership update")
        if kind in {"checkout.session.completed", "checkout.session.async_payment_succeeded",
                    "checkout.session.async_payment_failed", "checkout.session.expired"}:
            attempt_id = (obj.get("metadata") or {}).get("checkout_id")
            attempt = session.get(BillingCheckout, attempt_id) if attempt_id else None
            if not attempt:
                raise ValueError("Unknown checkout")
            if attempt.stripe_id and attempt.stripe_id != obj["id"]:
                raise ValueError("Session mismatch")
            if obj.get("client_reference_id") != attempt.user_id or obj.get("mode") != attempt.mode:
                raise ValueError("Binding mismatch")
            account = session.get(Membership, attempt.user_id)
            customer = _id(obj.get("customer"))
            if account.customer_id and customer and account.customer_id != customer:
                raise ValueError("Customer mismatch")
            attempt.stripe_id = obj["id"]
            if kind in {"checkout.session.expired", "checkout.session.async_payment_failed"}:
                if not attempt.fulfilled:
                    attempt.state = "expired" if kind == "checkout.session.expired" else "failed"
            elif obj.get("payment_status") == "paid" and obj.get("status") == "complete":
                if not customer:
                    raise ValueError("Customer required")
                account.customer_id = customer
                if attempt.mode == "payment":
                    if not attempt.fulfilled:
                        pi = _id(obj.get("payment_intent"))
                        allowed = _bind_payment(session, account, pi, pi)
                        account.entitlement_source = pi
                        account.expires_at = max(time.time(), account.expires_at) + attempt.duration_days * 86400 if allowed else 0
                        account.status = "active" if allowed else "expired"
                        # A verified one-time purchase replaces the ended subscription
                        # as the entitlement source. Its old lifecycle must not revoke it.
                        account.subscription_id = None
                        account.cancel_at_period_end = False
                else:
                    subscription_id = _id(obj.get("subscription"))
                    if not subscription_id:
                        raise ValueError("Subscription required")
                    if account.subscription_id != subscription_id:
                        if attempt.fulfilled:
                            session.add(BillingEvent(id=event_id))
                            session.commit()
                            return
                        if (account.active_checkout_id != attempt.id or is_vip(session, account.user_id)):
                            raise ValueError("Superseded checkout")
                        if account.subscription_id:
                            old = context["subscriptions"][account.subscription_id]
                            if old.get("status") not in {"canceled", "incomplete_expired"}:
                                # Expired local payment coverage does not mean Stripe
                                # stopped renewing the previous subscription.
                                raise ValueError("Existing subscription needs management")
                        account.subscription_id = subscription_id
                    _subscription_state(session, account, subscription_id, context["subscriptions"][subscription_id], attempt.price_id)
                attempt.fulfilled, attempt.state = True, "paid"
            account.revision += 1
            session.add(account)
            session.add(attempt)
        elif kind in {"invoice.paid", "invoice.payment_failed", "customer.subscription.updated", "customer.subscription.deleted"}:
            customer = _id(obj.get("customer"))
            account = session.exec(select(Membership).where(Membership.customer_id == customer)).first() if customer else None
            if account and not account.subscription_id:
                pending = session.get(BillingCheckout, account.active_checkout_id) if account.active_checkout_id else None
                if not pending or pending.mode != "subscription" or pending.fulfilled:
                    session.add(BillingEvent(id=event_id))
                    session.commit()
                    return
            if not account or not account.subscription_id:
                # A renewal can arrive before checkout.completed. Stripe must retry it.
                raise ValueError("Checkout binding not received")
            sub_id = (obj.get("id") if kind.startswith("customer.subscription") else
                      _id(obj.get("subscription")) or _id(((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")))
            if sub_id != account.subscription_id:
                # A late notification for an older subscription cannot affect the
                # current one. It is acknowledged without any entitlement mutation.
                session.add(BillingEvent(id=event_id))
                session.commit()
                return
            attempt = session.exec(select(BillingCheckout).where(BillingCheckout.user_id == account.user_id,
                BillingCheckout.mode == "subscription", BillingCheckout.fulfilled == True)
                .order_by(BillingCheckout.created_at.desc())).first()
            if not attempt:
                raise ValueError("Paid checkout absent")
            _subscription_state(session, account, sub_id, context["subscriptions"][sub_id], attempt.price_id)
            account.revision += 1
            session.add(account)
        elif kind in _REVERSALS:
            pi = context.get("payment_intent")
            if not pi:
                raise ValueError("Reversal payment binding absent")
            is_reversal = (kind != "charge.refunded" or obj.get("refunded") is True or
                (obj.get("amount", 0) > 0 and obj.get("amount_refunded", 0) >= obj["amount"]))
            if kind == "charge.dispute.closed" and obj.get("status") != "lost":
                is_reversal = False
            if is_reversal:
                receipt = session.get(BillingPayment, pi)
                if receipt is None:
                    receipt = BillingPayment(payment_intent=pi, revoked=True)
                receipt.revoked = True
                session.add(receipt)
                if not receipt.user_id:
                    # Preserve a tombstone before requesting retry. A late checkout
                    # cannot grant access for this already reversed payment.
                    session.commit()
                    raise ValueError("Reversed payment awaits checkout binding")
                account = session.get(Membership, receipt.user_id)
                if account.entitlement_source == receipt.source_id:
                    account.status, account.expires_at = "expired", 0
                    account.revision += 1
                    session.add(account)
        session.add(BillingEvent(id=event_id))
        session.commit()
    except Exception:
        session.rollback()
        raise unavailable("支付通知尚未处理，请稍后重试") from None
