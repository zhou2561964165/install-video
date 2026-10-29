"""Durable signed receipts and fenced billing processing; no public replay API."""
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import uuid

from fastapi import HTTPException
import stripe
from sqlalchemy import and_, func, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from ..models import BillingInbox, BillingFact, BillingEvent, BillingPayment, BillingCheckout, Membership
from .billing_pg import BillingConfiguration, locked, lock_account, scope_matches, unavailable
from .billing_projection import (CHECKOUT, SUBSCRIPTION, INVOICE, REVERSALS, VERSION,
    InvalidPayload, canonical, digest, project_object, reference)
from .db_transactions import CommitResolution, ResolutionState, run_local_transaction
from .membership_fulfilment import PaymentBindingError, bind_payment, fulfil_paid_checkout

BACKOFF = (30, 120, 600, 1800)
TERMINAL = frozenset({'applied', 'ignored', 'needs_review'})


class LeaseLost(Exception):
    pass


class Deferred(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def now(session):
    return session.exec(select(func.clock_timestamp())).one()


def receive(engine, event, raw, cfg):
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, detail={'error_type': 'billing_payload', 'error': '通知过大'})
    invalid = False
    try:
        payload = canonical(event, cfg.scope, cfg.livemode)
    except (ValueError, TypeError, AttributeError, KeyError):
        invalid = True
    if invalid:
        raise HTTPException(400, detail={'error_type': 'billing_payload', 'error': '通知业务结构无效'})
    value, sha = json.loads(payload), digest(payload)
    inbox_id = str(uuid.uuid4())
    def action(session):
        stamp = now(session)
        # Conflict-safe insertion serializes duplicate deliveries without creating
        # a failed transaction or losing the winner's immutable original payload.
        session.execute(insert(BillingInbox).values(id=inbox_id, provider_account_scope=cfg.scope,
            livemode=cfg.livemode, event_id=value['id'], event_type=value['type'], api_version=value['api_version'],
            received_at=stamp, payload_sha256=hashlib.sha256(raw).hexdigest(),
            canonical_sha256=sha, canonical_version=VERSION, canonical_payload=payload,
            business_payload=payload, status='received', attempt_count=0, attempt_limit=5,
            budget_deadline=stamp+timedelta(hours=24), next_run_at=stamp, lease_epoch=0)
            .on_conflict_do_nothing(index_elements=['provider_account_scope','livemode','event_id']))
        row = session.exec(select(BillingInbox).where(BillingInbox.provider_account_scope == cfg.scope,
            BillingInbox.livemode == cfg.livemode, BillingInbox.event_id == value['id'])
            .with_for_update().execution_options(populate_existing=True)).one()
        conflict = row.canonical_version != VERSION or row.canonical_sha256 != sha or row.canonical_payload != payload
        if conflict:
            row.status, row.error_code, row.outcome_reason = 'needs_review', 'billing_event_conflict', 'canonical_conflict'
            row.lease_owner = row.lease_deadline = None
            row.lease_epoch += 1
            session.add(row)
        return conflict
    def resolve(session, _):
        row = session.exec(select(BillingInbox).where(BillingInbox.provider_account_scope == cfg.scope,
            BillingInbox.livemode == cfg.livemode, BillingInbox.event_id == value['id'])).first()
        if row and row.canonical_payload == payload and row.canonical_sha256 == sha:
            return CommitResolution(ResolutionState.COMMITTED, False)
        if row and row.status == 'needs_review' and row.error_code == 'billing_event_conflict':
            return CommitResolution(ResolutionState.COMMITTED, True)
        return CommitResolution(ResolutionState.UNKNOWN)
    conflict = run_local_transaction(engine, inbox_id, action, resolve)
    if conflict:
        raise HTTPException(409, detail={'error_type': 'billing_event_conflict', 'error': '通知业务内容冲突，已保留原件'})
    return {'received': True}


@dataclass(frozen=True)
class Claim:
    id: str
    event_id: str
    owner: str
    epoch: int
    payload: str
    attempt: int


def claim_one(engine, cfg, owner):
    if type(owner) is not str or not owner or len(owner) > 128:
        raise ValueError('bounded owner required')
    operation_id = str(uuid.uuid4())
    def action(session):
        stamp = now(session)
        candidates = select(BillingInbox).where(BillingInbox.provider_account_scope == cfg.scope,
            BillingInbox.livemode == cfg.livemode,
            or_(and_(BillingInbox.status.in_(['received','retry_wait','waiting_binding']), BillingInbox.next_run_at <= stamp),
                and_(BillingInbox.status == 'processing', BillingInbox.lease_deadline <= stamp)))
        row = session.exec(candidates.order_by(BillingInbox.next_run_at, BillingInbox.id)
            .with_for_update(skip_locked=True).limit(1).execution_options(populate_existing=True)).first()
        if row is None:
            return None
        row.lease_epoch += 1  # Expiry invalidates the old token before any recovery.
        committed = session.get(BillingEvent, row.event_id)
        if committed:
            if not scope_matches(committed, cfg) or committed.outcome not in {'applied', 'ignored'}:
                row.status, row.error_code = 'needs_review', 'event_scope_unverified'
            else:
                row.status, row.completed_at = committed.outcome, stamp
                row.outcome_reason = 'existing_business_commit'
            row.lease_owner = row.lease_deadline = None
            session.add(row)
            return None
        if row.attempt_count >= row.attempt_limit or stamp >= row.budget_deadline:
            row.status, row.error_code = 'needs_review', 'budget_exhausted'
            row.lease_owner = row.lease_deadline = None
            session.add(row)
            return None
        row.attempt_count += 1
        row.status, row.lease_owner = 'processing', owner
        row.lease_deadline = stamp + timedelta(seconds=cfg.lease_seconds)
        session.add(row)
        return Claim(row.id, row.event_id, owner, row.lease_epoch, row.business_payload, row.attempt_count)
    # An unknown claim ACK cannot launch provider reads: recovery will expire it.
    return run_local_transaction(engine, operation_id, action,
        lambda *_: CommitResolution(ResolutionState.UNKNOWN))


def _cas(session, token, status, code=None, reason=None):
    # Take this final lock AFTER all domain locks, then sample the clock. A time
    # bound sampled before waiting for the row lock is not a valid lease fence.
    row = locked(session, BillingInbox, BillingInbox.id, token.id)
    stamp = now(session)
    if (row is None or row.status != 'processing' or row.lease_owner != token.owner
            or row.lease_epoch != token.epoch or row.lease_deadline <= stamp):
        raise LeaseLost()
    if status in {'applied','ignored'} and stamp >= row.budget_deadline:
        raise Deferred('needs_review', 'budget_exhausted')
    terminal = status in TERMINAL
    if not terminal and (row.attempt_count >= row.attempt_limit or stamp >= row.budget_deadline):
        status, code, terminal = 'needs_review', 'budget_exhausted', True
    values = dict(status=status, error_code=code, outcome_reason=reason,
        lease_owner=None, lease_deadline=None, completed_at=stamp if terminal else None)
    if not terminal:
        values['next_run_at'] = min(stamp+timedelta(seconds=BACKOFF[min(row.attempt_count-1, 3)]), row.budget_deadline)
    # Python's sampled stamp can become stale after a scheduler pause. The final
    # write itself is the fence and must evaluate the actual database clock.
    predicates = [BillingInbox.id == token.id,
        BillingInbox.status == 'processing', BillingInbox.lease_owner == token.owner,
        BillingInbox.lease_epoch == token.epoch, BillingInbox.lease_deadline > func.clock_timestamp()]
    if status in {'applied','ignored'}:
        predicates.append(BillingInbox.budget_deadline > func.clock_timestamp())
    result = session.execute(update(BillingInbox).where(*predicates).values(**values)
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        # Still own the row lock. Re-sample only to classify the rejected write;
        # it never authorizes a second domain write or weakens the SQL fence.
        rejected_at = now(session)
        if row.lease_deadline > rejected_at and row.budget_deadline <= rejected_at:
            raise Deferred('needs_review', 'budget_exhausted')
        raise LeaseLost()
    return status


def _defer(engine, token, status, code):
    def action(session):
        return _cas(session, token, status, code)
    def resolve(session, _):
        row = session.get(BillingInbox, token.id)
        if (row and row.lease_epoch == token.epoch and row.lease_owner is None
                and row.error_code in {code, 'budget_exhausted'}):
            return CommitResolution(ResolutionState.COMMITTED)
        return CommitResolution(ResolutionState.UNKNOWN)
    return run_local_transaction(engine, token.id, action, resolve)


def _subscription_id(kind, obj):
    return (obj['id'] if kind in SUBSCRIPTION else obj.get('subscription') or
            ((obj.get('parent') or {}).get('subscription_details') or {}).get('subscription'))


def _discover(engine, event):
    kind, obj = event['type'], event['data']['object']
    with Session(engine) as session:
        account, attempt = None, None
        if kind in CHECKOUT:
            aid = obj['metadata']['checkout_id']
            attempt = session.get(BillingCheckout, aid) if aid else None
            account = session.get(Membership, attempt.user_id) if attempt else None
        elif kind in REVERSALS:
            pi = obj.get('payment_intent')
            payment = session.get(BillingPayment, pi) if pi else None
            account = session.get(Membership, payment.user_id) if payment and payment.user_id else None
        elif kind in INVOICE | SUBSCRIPTION:
            customer = obj.get('customer')
            account = session.exec(select(Membership).where(Membership.customer_id == customer)).first() if customer else None
        pending = session.get(BillingCheckout, account.active_checkout_id) if account and account.active_checkout_id else None
        superseded = bool(account and not account.subscription_id and account.entitlement_source
                          and (not pending or pending.mode != 'subscription' or pending.fulfilled))
        return {'uid': account.user_id if account else None, 'revision': account.revision if account else None,
            'checkout_id': attempt.id if attempt else None, 'checkout_revision': attempt.revision if attempt else None,
            'subscription_id': account.subscription_id if account else None,
            'active_checkout_id': account.active_checkout_id if account else None,
            'subscription_superseded': superseded}


def _revokes(kind, obj):
    if kind == 'charge.refunded':
        return obj.get('refunded') is True or (obj.get('amount') is not None and obj['amount'] > 0
            and obj.get('amount_refunded') is not None and obj['amount_refunded'] >= obj['amount'])
    return kind != 'charge.dispute.closed' or obj.get('status') == 'lost'


def _tombstone(engine, pi):
    def action(session):
        session.execute(insert(BillingPayment).values(payment_intent=pi, user_id=None, source_id=None, revoked=True)
            .on_conflict_do_nothing(index_elements=['payment_intent']))
        row = locked(session, BillingPayment, BillingPayment.payment_intent, pi)
        if row.user_id is not None:
            return False  # Never acquire User after PI; restart the normal path.
        row.revoked = True
        session.add(row)
        return True
    def resolve(session, _):
        row = session.get(BillingPayment, pi)
        if row and row.revoked:
            return CommitResolution(ResolutionState.COMMITTED, row.user_id is None)
        return CommitResolution(ResolutionState.UNKNOWN)
    return run_local_transaction(engine, str(uuid.uuid4()), action, resolve)


def _ensure_token(engine, token):
    with Session(engine) as session:
        row = session.get(BillingInbox, token.id)
        stamp = now(session)
        if (not row or row.status != 'processing' or row.lease_owner != token.owner
                or row.lease_epoch != token.epoch or row.lease_deadline <= stamp):
            raise LeaseLost()
        if stamp >= row.budget_deadline:
            raise Deferred('needs_review', 'budget_exhausted')


class _Reads:
    def __init__(self, provider, guard):
        self.provider, self.count, self.guard = provider, 0, guard

    def get(self, resource, identity, params=None):
        self.guard()
        if not identity or self.count >= 2:
            raise Deferred('needs_review', 'provider_structure')
        self.count += 1
        api = self.provider().v1
        endpoint = api
        for name in resource.split('.'):
            endpoint = getattr(endpoint, name)
        rejection = None
        try:
            result = endpoint.retrieve(identity, params=params) if params is not None else endpoint.retrieve(identity)
        except (stripe.APIConnectionError, stripe.RateLimitError, TimeoutError, ConnectionError):
            rejection = ('retry_wait', 'provider_temporary')
        except stripe.StripeError as exc:
            if getattr(exc, 'http_status', 0) and exc.http_status >= 500:
                rejection = ('retry_wait', 'provider_temporary')
            else:
                rejection = ('needs_review', 'provider_rejected')
        if rejection:
            raise Deferred(*rejection)
        return result


def _bind(session, account, pi, source):
    try:
        return bind_payment(session, account, pi, source)
    except PaymentBindingError as error:
        raise Deferred('needs_review', error.code) from None


def _apply_subscription(session, account, sid, sub, price, cfg):
    if (sub['id'] != sid or sub.get('customer') != account.customer_id
            or sub.get('_livemode') is not cfg.livemode):
        raise Deferred('needs_review', 'subscription_binding')
    account.subscription_id, account.cancel_at_period_end = sid, bool(sub.get('cancel_at_period_end'))
    if sub.get('status') in {'canceled','unpaid','incomplete_expired','paused'}:
        account.status, account.expires_at = 'expired', 0
        return None
    invoice = sub.get('latest_invoice')
    if not isinstance(invoice, dict) or invoice.get('status') != 'paid':
        return None
    if invoice.get('customer') != account.customer_id or _subscription_id('invoice.paid', invoice) != sid:
        raise Deferred('needs_review', 'invoice_binding')
    periods = [item.get('current_period_end') or sub.get('current_period_end') or 0
        for item in sub['items']['data'] if item.get('price') == price]
    paid_ends = [item['period']['end'] or 0 for item in invoice['lines']['data'] if item.get('price') == price]
    if not periods or not paid_ends or not max(periods) or not max(paid_ends):
        raise Deferred('needs_review', 'price_binding')
    pis = {p['payment']['payment_intent'] for p in invoice['payments']['data']
           if p['status'] == 'paid' and p['payment']['payment_intent']}
    if invoice.get('payment_intent'):
        pis.add(invoice['payment_intent'])
    if not pis or not invoice.get('id'):
        raise Deferred('needs_review', 'payment_binding_absent')
    allowed = all([_bind(session, account, pi, invoice['id']) for pi in sorted(pis)])
    account.entitlement_source = invoice['id']
    account.status = 'active' if allowed else 'expired'
    account.expires_at = min(max(periods), max(paid_ends)) if allowed else 0
    return invoice


def _fact(session, token, event, cfg, account, attempt, obj):
    kind = event['type']
    total = obj.get('amount_total') if kind in CHECKOUT else obj.get('amount') if kind in REVERSALS else obj.get('amount_paid')
    refunded = obj.get('amount_refunded')
    currency = obj.get('currency')
    fact = BillingFact(inbox_id=token.id, user_id=account.user_id if account else None,
        checkout_id=attempt.id if attempt else None, provider_account_scope=cfg.scope,
        livemode=cfg.livemode, event_id=token.event_id, payment_intent=obj.get('payment_intent'),
        session_id=obj['id'] if kind in CHECKOUT else None,
        invoice_id=obj['id'] if kind in INVOICE else None,
        charge_id=obj['id'] if kind == 'charge.refunded' else obj.get('charge'),
        subscription_id=_subscription_id(kind, obj) if kind in INVOICE | SUBSCRIPTION else obj.get('subscription'),
        provider_status=obj.get('status'), amount_total=total, amount_refunded=refunded,
        currency=currency, reconciliation='verified' if total is not None and currency is not None else 'unknown',
        observed_at=now(session))
    session.add(fact)


def process_claim(engine, token, cfg, provider):
    """One attempt, at most two GETs, immutable token; returns safe status only."""
    try:
        _ensure_token(engine, token)
        event = json.loads(token.payload)
        if canonical(event, cfg.scope, cfg.livemode) != token.payload:
            raise Deferred('needs_review', 'canonical_invalid')
        context = _discover(engine, event)
        kind, obj = event['type'], event['data']['object']
        reads = _Reads(provider, lambda: _ensure_token(engine, token))
        authoritative, sub = None, None
        if kind in REVERSALS:
            pi = obj.get('payment_intent')
            if not pi and kind.startswith('charge.dispute.'):
                charge = reads.get('charges', obj.get('charge'))
                if charge.get('id') != obj.get('charge') or charge.get('livemode') is not cfg.livemode:
                    raise Deferred('needs_review', 'charge_binding')
                pi = reference(charge.get('payment_intent'))
            if not pi:
                raise Deferred('needs_review', 'payment_binding_absent')
            obj = dict(obj, payment_intent=pi)
            if not context['uid']:
                if _revokes(kind, obj) and _tombstone(engine, pi):
                    raise Deferred('waiting_binding', 'payment_waiting_binding')
                context = _discover(engine, {'type': kind, 'data': {'object': obj}})
                if not context['uid']:
                    raise Deferred('waiting_binding', 'payment_waiting_binding')
        if kind in CHECKOUT:
            if not context['checkout_id']:
                raise Deferred('waiting_binding', 'checkout_waiting_binding')
            if obj.get('payment_status') == 'paid' and obj.get('status') == 'complete':
                raw = reads.get('checkout.sessions', obj['id'], {'expand': ['line_items']})
                if raw.get('livemode') is not cfg.livemode:
                    raise Deferred('needs_review', 'mode_binding')
                authoritative = project_object(kind, raw)
                for field in ('id','mode','client_reference_id','customer','payment_intent','subscription','status','payment_status','metadata'):
                    if authoritative.get(field) != obj.get(field):
                        raise Deferred('needs_review', 'checkout_binding')
                for field in ('amount_total', 'currency'):
                    if obj.get(field) is not None and authoritative.get(field) != obj[field]:
                        raise Deferred('needs_review', 'amount_binding')
                if obj.get('mode') == 'subscription':
                    rawsub = reads.get('subscriptions', obj.get('subscription'), {'expand': ['latest_invoice.payments']})
                    sub = project_object('customer.subscription.updated', rawsub)
                    sub['_livemode'] = rawsub.get('livemode')
        elif kind in INVOICE | SUBSCRIPTION:
            if not context['uid'] or (not context['subscription_id'] and not context['subscription_superseded']):
                raise Deferred('waiting_binding', 'subscription_waiting_binding')
            if _subscription_id(kind, obj) == context['subscription_id']:
                rawsub = reads.get('subscriptions', context['subscription_id'], {'expand': ['latest_invoice.payments']})
                sub = project_object('customer.subscription.updated', rawsub)
                sub['_livemode'] = rawsub.get('livemode')

        def action(session):
            account, attempt, reason = None, None, None
            if context['uid']:
                account = lock_account(session, context['uid'])
                if account.revision != context['revision']:
                    raise Deferred('retry_wait', 'revision_changed')
                if kind in CHECKOUT:
                    attempt = locked(session, BillingCheckout, BillingCheckout.id, context['checkout_id'])
                    if not attempt or attempt.revision != context['checkout_revision']:
                        raise Deferred('retry_wait', 'revision_changed')
                elif kind in INVOICE | SUBSCRIPTION:
                    # Checkout is locked before any Payment or BillingEvent.
                    sid = _subscription_id(kind, obj)
                    if sid != account.subscription_id:
                        reason = 'superseded_subscription'
                    else:
                        attempt = session.exec(select(BillingCheckout).where(BillingCheckout.user_id == account.user_id,
                            BillingCheckout.mode == 'subscription', BillingCheckout.fulfilled == True)
                            .order_by(BillingCheckout.created_at.desc()).with_for_update()
                            .execution_options(populate_existing=True)).first()
                        if not attempt:
                            raise Deferred('waiting_binding', 'checkout_waiting_binding')
            # User lock serializes all entitlement writes; event receipt duplicates
            # cannot cause a second grant even when Stripe uses a different event.
            existing = session.get(BillingEvent, token.event_id)
            if existing:
                if not scope_matches(existing, cfg) or existing.outcome not in {'applied','ignored'}:
                    raise Deferred('needs_review', 'event_scope_unverified')
                _cas(session, token, existing.outcome, reason='existing_business_commit')
                return existing.outcome
            if kind in CHECKOUT:
                if (attempt.provider_account_scope is not None and not scope_matches(attempt, cfg)):
                    raise Deferred('needs_review', 'checkout_scope')
                if (not attempt.stripe_id and attempt.provider_account_scope is None):
                    raise Deferred('needs_review', 'legacy_checkout_unverified')
                if (attempt.stripe_id and attempt.stripe_id != obj['id']) or obj.get('client_reference_id') != attempt.user_id or obj.get('mode') != attempt.mode:
                    raise Deferred('needs_review', 'checkout_binding')
                if account.customer_id and obj.get('customer') and account.customer_id != obj['customer']:
                    raise Deferred('needs_review', 'customer_binding')
                attempt.stripe_id = obj['id']
                if kind in {'checkout.session.expired','checkout.session.async_payment_failed'}:
                    if not attempt.fulfilled:
                        attempt.state = 'expired' if kind == 'checkout.session.expired' else 'failed'
                elif authoritative is not None:
                    lines = authoritative['line_items']['data']
                    if len(lines) != 1 or lines[0]['price'] != attempt.price_id or lines[0]['quantity'] != 1:
                        raise Deferred('needs_review', 'price_binding')
                    if not obj.get('customer'):
                        raise Deferred('needs_review', 'customer_binding')
                    account.customer_id = obj['customer']
                    if not attempt.fulfilled:
                        if account.active_checkout_id != attempt.id:
                            raise Deferred('needs_review', 'superseded_checkout')
                        if attempt.mode == 'payment':
                            try:
                                fulfil_paid_checkout(session, account, attempt, obj.get('payment_intent'),
                                                     now_ts=now(session).timestamp())
                            except PaymentBindingError as error:
                                raise Deferred('needs_review', error.code) from None
                        else:
                            if account.subscription_id not in {None, obj.get('subscription')}:
                                raise Deferred('needs_review', 'subscription_binding')
                            _apply_subscription(session, account, obj.get('subscription'), sub, attempt.price_id, cfg)
                        attempt.fulfilled, attempt.state = True, 'paid'
                    else:
                        reason = 'checkout_already_fulfilled'
                attempt.revision += 1
                account.revision += 1
                session.add(attempt)
                session.add(account)
            elif kind in INVOICE | SUBSCRIPTION and not reason:
                if attempt.provider_account_scope is not None and not scope_matches(attempt, cfg):
                    raise Deferred('needs_review', 'checkout_scope')
                _apply_subscription(session, account, account.subscription_id, sub, attempt.price_id, cfg)
                account.revision += 1
                session.add(account)
            elif kind in REVERSALS:
                receipt = locked(session, BillingPayment, BillingPayment.payment_intent, obj['payment_intent'])
                if not receipt or receipt.user_id != account.user_id:
                    raise Deferred('waiting_binding', 'payment_waiting_binding')
                if _revokes(kind, obj):
                    receipt.revoked = True
                    session.add(receipt)
                    if account.entitlement_source == receipt.source_id:
                        account.status, account.expires_at = 'expired', 0
                        account.revision += 1
                        session.add(account)
            else:
                reason = reason or 'unsupported_event_type'
            outcome = 'ignored' if reason in {'superseded_subscription','unsupported_event_type'} else 'applied'
            # PI locks have all been acquired before the success-event lock.
            locked(session, BillingEvent, BillingEvent.id, token.event_id)
            session.add(BillingEvent(id=token.event_id, provider_account_scope=cfg.scope, livemode=cfg.livemode, outcome=outcome))
            session.flush()
            _fact(session, token, event, cfg, account, attempt, authoritative or obj)
            session.flush()
            # Last statement owning the Inbox is the fencing CAS. On zero rows the
            # runner rolls back Checkout, payments, fact, event and entitlement.
            _cas(session, token, outcome, reason=reason)
            return outcome

        def resolve(session, _):
            row, eventrow = session.get(BillingInbox, token.id), session.get(BillingEvent, token.event_id)
            fact = session.exec(select(BillingFact).where(BillingFact.inbox_id == token.id)).first()
            if (row and eventrow and fact and scope_matches(eventrow, cfg) and scope_matches(row, cfg)
                    and row.status == eventrow.outcome and row.status in {'applied','ignored'}
                    and fact.event_id == token.event_id and scope_matches(fact, cfg)):
                return CommitResolution(ResolutionState.COMMITTED, row.status)
            return CommitResolution(ResolutionState.UNKNOWN)
        return run_local_transaction(engine, token.id, action, resolve)
    except Deferred as exc:
        deferred = (exc.status, exc.code)
    except LeaseLost:
        return 'lease_lost'
    except (InvalidPayload, ValueError, TypeError, KeyError, AttributeError):
        deferred = ('needs_review', 'provider_structure')
    # No supplier exception is active while a DB defer/unknown error propagates.
    try:
        return _defer(engine, token, *deferred)
    except LeaseLost:
        return 'lease_lost'


def run_once(engine, cfg, provider, owner):
    token = claim_one(engine, cfg, owner)
    return process_claim(engine, token, cfg, provider) if token else None
