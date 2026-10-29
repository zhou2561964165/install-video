"""Admin side of customer support: ticket list/detail (with the selected order, membership, verification
state and available actions), reply and reject. Verification and re-issue live further below (Task 7).
"""
from __future__ import annotations

from datetime import datetime, timedelta
import re
import uuid

from sqlalchemy import func, select, update

from ..admin.errors import AdminError
from ..models import BillingCheckout, Membership, User
from ..models_support import MembershipReissue, SupportPaymentCheck, SupportTicket
from . import admin_audit
from . import support_catalog as catalog
from .admin_queries import ListQuery, _checkout_columns, _checkout_summary, membership_projection, paginate

ticket_t, check_t, reissue_t = SupportTicket.__table__, SupportPaymentCheck.__table__, MembershipReissue.__table__


def _summary(row) -> dict:
    return {'id': row.id, 'user_id': row.user_id, 'user_email': row.email, 'category': row.category,
            'category_label': catalog.CATEGORIES.get(row.category, row.category), 'priority': row.priority,
            'state': row.state, 'resolution': row.resolution, 'checkout_id': row.checkout_id,
            'created_at': row.created_at, 'resolved_at': row.resolved_at}


def _ticket_select():
    user = User.__table__
    return select(ticket_t, user.c.email).select_from(ticket_t.join(user, user.c.id == ticket_t.c.user_id))


def list_tickets(connection, as_of: datetime, query: ListQuery):
    statement = _ticket_select()
    for name in ('state', 'category', 'priority', 'user_id'):
        if name in query.filters:
            statement = statement.where(ticket_t.c[name] == query.filters[name])
    rows, total = paginate(connection, statement, query,
                           {'priority': ticket_t.c.priority, 'created_at': ticket_t.c.created_at}, ticket_t.c.id,
                           secondary={'priority': [ticket_t.c.created_at.asc()]})  # priority first, then oldest
    return [_summary(row) for row in rows], total


def latest_check(connection, ticket, as_of: datetime, settings) -> dict | None:
    if not ticket.checkout_id:
        return None
    row = connection.execute(select(check_t.c.result, check_t.c.checked_at, check_t.c.payment_intent)
                             .where(check_t.c.checkout_id == ticket.checkout_id)
                             .order_by(check_t.c.checked_at.desc(), check_t.c.id.desc()).limit(1)).first()
    if row is None:
        return None
    fresh = row.result == 'verified' and row.checked_at > as_of - timedelta(seconds=settings.verify_fresh_seconds)
    return {'result': row.result, 'checked_at': row.checked_at, 'fresh': fresh, 'payment_intent': row.payment_intent}


def membership_block(status, expires_at, source, subscription_id, payment_intent, now_ts: float) -> str | None:
    """Re-issue never stacks onto another payment's live membership (a later refund of either payment
    could then not revoke only its own days) and never detaches a bound subscription."""
    if subscription_id:
        return 'subscription_active'
    if status == 'active' and (expires_at or 0) > now_ts and source != payment_intent:
        return 'membership_active'
    return None


def _check_count(connection, ticket_id: str) -> int:
    return connection.scalar(select(func.count()).select_from(check_t).where(check_t.c.ticket_id == ticket_id))


def actions(connection, ticket, checkout, check, settings, member=None, now_ts: float = 0.0) -> dict:
    def result(reason):
        return {'allowed': reason is None, 'reason': reason}
    closed = 'ticket_closed' if ticket.state != 'open' else None
    category = None if ticket.category == 'membership_not_credited' else 'not_reissuable_category'
    key = None if settings.stripe_read_key else 'stripe_read_key_missing'
    verify = closed or category or key
    if verify is None:
        if checkout is None or not checkout.stripe_id:
            verify = 'no_stripe_session'
        elif checkout.fulfilled:
            verify = 'already_fulfilled'
        elif _check_count(connection, ticket.id) >= settings.verify_max_attempts:
            verify = 'attempts_exhausted'
    reissue = closed or category or key
    if reissue is None:
        if checkout is None or checkout.fulfilled:
            reissue = 'already_fulfilled'
        elif connection.scalar(select(func.count()).select_from(reissue_t).where(reissue_t.c.checkout_id == checkout.id)):
            reissue = 'already_reissued'
        elif member is not None and (blocked := membership_block(
                member.m_status, member.m_expires_at, member.m_source, member.m_subscription,
                check['payment_intent'] if check else None, now_ts)):
            reissue = blocked
        elif check is None or check['result'] != 'verified':
            reissue = 'not_verified'
        elif not check['fresh']:
            reissue = 'verification_stale'
    return {'verify': result(verify), 'reissue': result(reissue), 'reply': result(closed), 'reject': result(closed)}


def ticket_detail(connection, as_of: datetime, ticket_id: str, settings) -> dict | None:
    ticket = connection.execute(_ticket_select().where(ticket_t.c.id == ticket_id)).first()
    if ticket is None:
        return None
    checkout_t, membership = BillingCheckout.__table__, Membership.__table__
    checkout = None
    if ticket.checkout_id:
        checkout = connection.execute(select(*_checkout_columns(checkout_t), checkout_t.c.stripe_id, checkout_t.c.duration_days)
                                      .where(checkout_t.c.id == ticket.checkout_id)).first()
    member = connection.execute(select(membership.c.status.label('m_status'), membership.c.expires_at.label('m_expires_at'),
                                       membership.c.revision.label('m_revision'),
                                       membership.c.entitlement_source.label('m_source'),
                                       membership.c.cancel_at_period_end.label('m_cancel'),
                                       membership.c.subscription_id.label('m_subscription'))
                                .where(membership.c.user_id == ticket.user_id)).first()
    check = latest_check(connection, ticket, as_of, settings)
    reply = None
    if ticket.reply_template:
        values = {'days': checkout.duration_days} if ticket.reply_template == 'reissued' and checkout else {}
        reply = catalog.render(ticket.reply_template, **values) if ticket.reply_template != 'reissued' or checkout else None
    return {**_summary(ticket), 'user_note': ticket.user_note, 'reply_template': ticket.reply_template,
            'reply_text': reply, 'reply_note': ticket.reply_note, 'resolved_by': ticket.resolved_by,
            'checkout': _checkout_summary(checkout) if checkout else None,
            'membership': membership_projection(member, ticket.user_id, as_of),
            'latest_check': None if check is None else {k: check[k] for k in ('result', 'checked_at', 'fresh')},
            'actions': actions(connection, ticket, checkout, check, settings, member, as_of.timestamp()), 'as_of': as_of}


def _validate_reply(template_id: str, note: str | None) -> str | None:
    if template_id not in catalog.MANUAL_TEMPLATES:
        raise AdminError(422, 'invalid_template', field_errors=[{'field': 'template_id', 'message': '请选择可用的回复模板'}])
    note = (note or '').strip() or None
    if note is not None and len(note) > catalog.NOTE_MAX:
        raise AdminError(422, 'validation_failed', field_errors=[{'field': 'note', 'message': '补充说明过长'}])
    return note


def close_ticket(engine, ticket_id: str, *, actor_user_id: str, request_id: str, template_id: str, note: str | None,
                 rejected: bool) -> dict:
    note = _validate_reply(template_id, note)
    with engine.begin() as connection:
        ticket = connection.execute(select(ticket_t).where(ticket_t.c.id == ticket_id).with_for_update()).first()
        if ticket is None:
            raise AdminError(404, 'not_found')
        if ticket.state != 'open':
            raise AdminError(409, 'ticket_closed')
        state, resolution = ('rejected', 'rejected') if rejected else ('resolved', 'replied')
        connection.execute(update(ticket_t).where(ticket_t.c.id == ticket_id).values(
            state=state, resolution=resolution, reply_template=template_id, reply_note=note,
            resolved_at=func.now(), resolved_by=actor_user_id, revision=ticket_t.c.revision + 1))
        admin_audit.record(connection, actor_user_id=actor_user_id, actor_kind='admin',
                           action='support.reject' if rejected else 'support.reply', outcome='succeeded',
                           request_id=request_id, target_user_id=ticket.user_id,
                           changes={'ticket_id': ticket_id, 'template': template_id})
    return {'id': ticket_id, 'state': state, 'resolution': resolution}


# --- Verify with the payment provider, and the reviewed re-issue (Task 7) ---------------------------

def _deny(engine, ticket, actor_user_id, request_id, code, status=409):
    with engine.begin() as connection:
        admin_audit.record(connection, actor_user_id=actor_user_id, actor_kind='admin', action='support.reissue_denied',
                           outcome='denied', request_id=request_id, target_user_id=getattr(ticket, 'user_id', None),
                           changes={'ticket_id': getattr(ticket, 'id', None), 'reason': code})
    raise AdminError(status, code)


def verify_payment(engine, ticket_id: str, *, actor_user_id: str, request_id: str, settings, reader) -> dict:
    """Read the checkout's Stripe Session (outside any DB lock), evaluate it and record the result."""
    from .support_payment_check import ReaderUnavailable, evaluate
    if reader is None or not settings.stripe_read_key:
        raise AdminError(503, 'capability_unavailable')
    checkout_t = BillingCheckout.__table__
    with engine.begin() as connection:
        ticket = connection.execute(select(ticket_t).where(ticket_t.c.id == ticket_id)).first()
        if ticket is None:
            raise AdminError(404, 'not_found')
        if ticket.state != 'open':
            raise AdminError(409, 'ticket_closed')
        if ticket.category != 'membership_not_credited':
            raise AdminError(409, 'not_reissuable_category')
        checkout = connection.execute(select(checkout_t).where(checkout_t.c.id == ticket.checkout_id)).first()
        if checkout is None or not checkout.stripe_id:
            raise AdminError(409, 'no_stripe_session')
        if checkout.fulfilled:
            raise AdminError(409, 'already_fulfilled')
        if _check_count(connection, ticket_id) >= settings.verify_max_attempts:
            raise AdminError(409, 'attempts_exhausted')
    try:
        session = reader.read(checkout.stripe_id)
    except ReaderUnavailable:
        raise AdminError(503, 'payment_provider_unavailable') from None
    result, payment_intent = evaluate(session, checkout_price_id=checkout.price_id, user_id=ticket.user_id,
                                      livemode=settings.stripe_livemode)
    with engine.begin() as connection:
        checked_at = connection.scalar(select(func.now()))
        connection.execute(check_t.insert().values(id=str(uuid.uuid4()), ticket_id=ticket_id,
                                                   checkout_id=checkout.id, payment_intent=payment_intent, result=result,
                                                   checked_at=checked_at, actor_user_id=actor_user_id))
        admin_audit.record(connection, actor_user_id=actor_user_id, actor_kind='admin', action='support.verify',
                           outcome='succeeded', request_id=request_id, target_user_id=ticket.user_id,
                           changes={'ticket_id': ticket_id, 'result': result})
    return {'result': result, 'checked_at': checked_at, 'fresh': result == 'verified'}


IDEMPOTENCY_KEY = re.compile(r'[A-Za-z0-9._:-]{16,128}')


class _Denied(Exception):
    def __init__(self, code: str):
        self.code = code


def reissue(engine, ticket_id: str, *, actor_user_id: str, request_id: str, settings, idempotency_key: str | None) -> dict:
    """Grant the paid checkout's days once: every precondition is re-checked under row locks
    (user → membership first, like the payment notification path, then ticket → checkout). A denial rolls the
    whole transaction back, then is audited separately."""
    from sqlmodel import Session, select as orm_select
    from ..models import BillingPayment
    from .billing_pg import lock_account, locked
    from .membership_fulfilment import PaymentBindingError, fulfil_paid_checkout
    if not idempotency_key or not IDEMPOTENCY_KEY.fullmatch(idempotency_key):  # contract IdempotencyKey
        raise AdminError(422, 'idempotency_key_required', field_errors=[{'field': 'Idempotency-Key', 'message': '缺少幂等键'}])
    with engine.connect() as connection:
        peek = connection.execute(select(ticket_t).where(ticket_t.c.id == ticket_id)).first()
    if peek is None:
        raise AdminError(404, 'not_found')
    try:
        with Session(engine) as session, session.begin():
            account = lock_account(session, peek.user_id)
            ticket = locked(session, SupportTicket, SupportTicket.id, ticket_id)
            checkout = locked(session, BillingCheckout, BillingCheckout.id, ticket.checkout_id) if ticket.checkout_id else None
            ledger = session.get(MembershipReissue, checkout.id) if checkout else None
            if ledger is not None:
                if ledger.ticket_id == ticket_id and ledger.idempotency_key == idempotency_key:
                    return _reissue_result(ledger, checkout)  # replay: the original result, nothing re-executed
                raise _Denied('already_reissued')
            if ticket.state != 'open':
                raise _Denied('ticket_closed')
            if ticket.category != 'membership_not_credited':
                raise _Denied('not_reissuable_category')
            if not settings.stripe_read_key:
                raise _Denied('capability_unavailable')
            if checkout is None or checkout.user_id != ticket.user_id or checkout.mode != 'payment':
                raise _Denied('checkout_mismatch')
            if checkout.fulfilled:
                raise _Denied('already_fulfilled')
            now = session.scalar(select(func.now()))
            check = session.exec(orm_select(SupportPaymentCheck).where(SupportPaymentCheck.checkout_id == checkout.id)
                                 .order_by(SupportPaymentCheck.checked_at.desc(), SupportPaymentCheck.id.desc())).first()
            if check is None or check.result != 'verified':
                raise _Denied('not_verified')
            if check.checked_at <= now - timedelta(seconds=settings.verify_fresh_seconds):
                raise _Denied('verification_stale')
            receipt = session.get(BillingPayment, check.payment_intent)
            if receipt is not None and (receipt.revoked or receipt.user_id not in (None, ticket.user_id)):
                raise _Denied('payment_conflict')
            blocked = membership_block(account.status, account.expires_at, account.entitlement_source,
                                       account.subscription_id, check.payment_intent, now.timestamp())
            if blocked:
                raise _Denied(blocked)
            expires_before = account.expires_at or 0
            try:
                allowed = fulfil_paid_checkout(session, account, checkout, check.payment_intent, now_ts=now.timestamp())
            except PaymentBindingError:
                allowed = False
            if not allowed:
                raise _Denied('payment_conflict')
            account.revision += 1
            checkout.revision += 1
            ledger = MembershipReissue(checkout_id=checkout.id, ticket_id=ticket_id, actor_user_id=actor_user_id,
                                       payment_intent=check.payment_intent, granted_days=checkout.duration_days,
                                       expires_before=expires_before, expires_after=account.expires_at, created_at=now,
                                       idempotency_key=idempotency_key)
            ticket.state, ticket.resolution, ticket.reply_template = 'resolved', 'reissued', 'reissued'
            ticket.resolved_at, ticket.resolved_by, ticket.revision = now, actor_user_id, ticket.revision + 1
            session.add_all([account, checkout, ledger, ticket])
            session.flush()
            admin_audit.record(session.connection(), actor_user_id=actor_user_id, actor_kind='admin',
                               action='support.reissue', outcome='succeeded', request_id=request_id,
                               target_user_id=ticket.user_id,
                               changes={'ticket_id': ticket_id, 'checkout_id': checkout.id, 'days': checkout.duration_days})
            return _reissue_result(ledger, checkout)
    except _Denied as denied:
        _deny(engine, peek, actor_user_id, request_id, denied.code, 503 if denied.code == 'capability_unavailable' else 409)


def _reissue_result(ledger, checkout) -> dict:
    from datetime import timezone
    return {'ticket_id': ledger.ticket_id, 'granted_days': ledger.granted_days,
            'expires_at': datetime.fromtimestamp(ledger.expires_after, tz=timezone.utc),
            'reply_text': catalog.render('reissued', days=ledger.granted_days)}
