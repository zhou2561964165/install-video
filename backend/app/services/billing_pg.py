"""PostgreSQL Checkout coordinator. Provider calls never own a DB connection."""
from dataclasses import dataclass
import json
import re
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import select

from ..models import Membership, BillingCheckout, BillingReconciliationTask
from .db_transactions import CommitResolution, ResolutionState, lock_user, run_local_transaction
from .billing_projection import digest, encode, reference, mapping, project_object, scalar
from .membership import require_checkout_auto


def unavailable():
    return HTTPException(503, detail={'error_type': 'billing_unavailable', 'error': '支付状态待核实，请稍后重试'})


@dataclass(frozen=True)
class BillingConfiguration:
    scope: str
    livemode: bool
    lease_seconds: int = 60

    def __post_init__(self):
        if (type(self.scope) is not str or self.scope == 'legacy_unknown'
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', self.scope) is None
                or type(self.livemode) is not bool
                or type(self.lease_seconds) is not int or not 10 <= self.lease_seconds <= 300):
            raise unavailable()

    @classmethod
    def configured(cls, settings, dialect):
        if dialect != 'postgresql' or settings.billing_inbox_mode != 'durable':
            raise unavailable()
        return cls(settings.stripe_provider_account_scope, settings.stripe_livemode,
                   settings.billing_inbox_lease_seconds)


def locked(session, model, column, key):
    return session.exec(select(model).where(column == key).with_for_update()
                        .execution_options(populate_existing=True)).first()


def lock_account(session, uid):
    lock_user(session, uid)
    row = locked(session, Membership, Membership.user_id, uid)
    if row is None:
        row = Membership(user_id=uid)
        session.add(row)
        session.flush()
    return row


def scope_matches(row, cfg):
    return row.provider_account_scope == cfg.scope and row.livemode is cfg.livemode


def parameters(row):
    value = {'mode': row.mode, 'line_items': [{'price': row.price_id, 'quantity': 1}],
        'managed_payments': {'enabled': False}, 'client_reference_id': row.user_id,
        'metadata': {'checkout_id': row.id}, 'success_url': row.origin + '/?membership=success',
        'cancel_url': row.origin + '/?membership=cancel'}
    if row.customer_id:
        value['customer'] = row.customer_id
    elif row.mode == 'payment':
        value['customer_creation'] = 'always'
    if row.mode == 'subscription':
        value['payment_method_types'] = ['card']
    return value


def checkout_url(value):
    if value is None:
        return None
    if type(value) is not str or len(value) > 8192 or any(ord(ch) < 33 or ord(ch) == 127 for ch in value):
        raise ValueError('invalid_checkout_url')
    parsed = urlsplit(value)
    parsed.port
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('invalid_checkout_url')
    return value


def _freeze(row):
    # Include all business input, including duration which is not sent to Stripe.
    return encode({'version': 1, 'scope': row.provider_account_scope, 'livemode': row.livemode,
        'user_id': row.user_id, 'price_id': row.price_id, 'mode': row.mode,
        'duration_days': row.duration_days, 'origin': row.origin, 'customer_id': row.customer_id,
        'params': parameters(row)})


@dataclass(frozen=True)
class CheckoutSnapshot:
    id: str
    user_id: str
    revision: int
    account_revision: int
    stripe_id: str | None
    frozen: str | None
    mode: str
    customer_id: str | None
    blocked: bool


def snapshot(row, account, blocked=False):
    return CheckoutSnapshot(row.id, row.user_id, row.revision, account.revision,
        row.stripe_id, row.create_payload, row.mode, row.customer_id, blocked)


def checkout(engine, user_id, cfg, settings, provider):
    """provider is a factory so constructing a network client is outside DB work."""
    # Existing subscription requires an authoritative preflight before a new intent.
    from sqlmodel import Session
    with Session(engine) as session:
        require_checkout_auto(session, user_id)
        account = session.get(Membership, user_id)
        prior = (account.revision, account.subscription_id) if account else (None, None)
    old_sub = None
    preflight_failed = False
    if prior[1]:
        try:
            raw_sub = mapping(provider().v1.subscriptions.retrieve(prior[1]))
            old_sub = {'id': reference(raw_sub.get('id')), 'customer': reference(raw_sub.get('customer')),
                'livemode': raw_sub.get('livemode'), 'status': scalar(raw_sub.get('status'), str)}
        except Exception:
            preflight_failed = True
    if preflight_failed:
        raise unavailable()
    proposed_id = str(uuid.uuid4())

    def prepare(session):
        account = lock_account(session, user_id)
        require_checkout_auto(session, user_id)
        now = session.exec(select(func.clock_timestamp())).one()
        if account.status == 'active' and account.expires_at > now.timestamp():
            raise HTTPException(409, detail={'error_type': 'membership_active', 'error': '会员已生效，请使用会员管理'})
        row = locked(session, BillingCheckout, BillingCheckout.id, account.active_checkout_id) if account.active_checkout_id else None
        if row is None or row.state in {'expired', 'paid', 'failed'}:
            if account.subscription_id:
                if (account.revision, account.subscription_id) != prior or not old_sub or old_sub.get('status') not in {'canceled', 'incomplete_expired'}:
                    raise unavailable()
                if reference(old_sub.get('id')) != account.subscription_id or reference(old_sub.get('customer')) != account.customer_id or old_sub.get('livemode') is not cfg.livemode:
                    raise unavailable()
                # Only an authoritative ended subscription, checked against the
                # unchanged local revision, may be detached for a new purchase.
                # Keep its payment/source history; a late old event cannot grant.
                account.subscription_id = None
                account.cancel_at_period_end = False
            row = BillingCheckout(id=proposed_id, user_id=user_id, price_id=settings.stripe_price_id,
                mode=settings.stripe_billing_mode, duration_days=settings.stripe_vip_duration_days,
                origin=settings.stripe_public_origin.rstrip('/'), customer_id=account.customer_id,
                provider_account_scope=cfg.scope, livemode=cfg.livemode,
                created_at=now.timestamp(), reconciliation='not_started')
            row.create_payload = _freeze(row)
            row.create_payload_sha256 = digest(row.create_payload)
            row.create_payload_version = 1
            session.add(row)
            account.active_checkout_id = row.id
            account.revision += 1
        blocked = False
        if not row.stripe_id:
            # A manual observation permanently occupies this original intent.
            # Lock after Checkout; no GET result can prove create never happened.
            manual_task = locked(session, BillingReconciliationTask,
                BillingReconciliationTask.checkout_id, row.id)
            blocked = (manual_task is not None or not scope_matches(row, cfg) or row.create_payload_version != 1
                or not row.create_payload or digest(row.create_payload) != row.create_payload_sha256
                or row.create_payload != _freeze(row) or now.timestamp() - row.created_at >= 23 * 3600
                or row.reconciliation in {'needs_review', 'closed'})
        elif row.provider_account_scope is not None and not scope_matches(row, cfg):
            blocked = True
        if blocked:
            row.reconciliation, row.create_result_code = 'needs_review', 'input_unverified'
        else:
            row.create_started_at, row.create_result_code = now, 'retrieve_started' if row.stripe_id else 'create_started'
            row.reconciliation = 'unknown'
        row.revision += 1
        session.add(row)
        session.add(account)
        session.flush()
        return snapshot(row, account, blocked)

    def resolve_prepare(session, _):
        account = session.get(Membership, user_id)
        if account and account.active_checkout_id:
            row = session.get(BillingCheckout, account.active_checkout_id)
            # Only the preallocated id proves this new intent's commit. Existing
            # intent ACK loss remains unknown rather than replaying a preparation.
            if row and row.id == proposed_id and row.create_payload == _freeze(row):
                return CommitResolution(ResolutionState.COMMITTED, snapshot(row, account))
        return CommitResolution(ResolutionState.UNKNOWN)

    frozen = run_local_transaction(engine, proposed_id, prepare, resolve_prepare)
    if frozen.blocked:
        raise unavailable()
    obj = None
    failure = None
    try:
        api = provider()
        raw_obj = (api.v1.checkout.sessions.retrieve(frozen.stripe_id) if frozen.stripe_id else
            api.v1.checkout.sessions.create(json.loads(frozen.frozen)['params'],
                options={'idempotency_key': 'membership-' + frozen.id}))
    except Exception:
        failure = 'provider_unknown'
    if failure is None:
        try:
            raw_obj = mapping(raw_obj)
            obj = project_object('checkout.session.completed', raw_obj)
            obj.update(livemode=raw_obj.get('livemode'), url=checkout_url(raw_obj.get('url')),
                       expires_at=scalar(raw_obj.get('expires_at'), int))
        except (ValueError, TypeError, KeyError, AttributeError):
            failure = 'provider_structure'

    def finish(session):
        account = lock_account(session, user_id)
        row = locked(session, BillingCheckout, BillingCheckout.id, frozen.id)
        if row is None or row.revision != frozen.revision or account.revision != frozen.account_revision:
            # A paid notification or another request owns the newer state.
            return None
        row.create_completed_at = session.exec(select(func.clock_timestamp())).one()
        if failure:
            row.create_result_code = failure
            row.reconciliation = 'needs_review' if failure == 'provider_structure' else 'unknown'
        else:
            valid = (obj.get('livemode') is cfg.livemode and reference(obj.get('id'))
                and (not frozen.stripe_id or obj['id'] == frozen.stripe_id)
                and obj.get('client_reference_id') == user_id and obj.get('mode') == frozen.mode
                and (obj.get('metadata') or {}).get('checkout_id') == frozen.id
                and (not frozen.customer_id or reference(obj.get('customer')) == frozen.customer_id))
            if not valid:
                row.create_result_code, row.reconciliation = 'binding_mismatch', 'needs_review'
            else:
                row.stripe_id = obj['id']
                row.url, row.expires_at = obj.get('url'), obj.get('expires_at') or 0
                row.create_result_code, row.reconciliation = 'retrieved' if frozen.stripe_id else 'created', 'verified'
                if row.state not in {'paid', 'expired', 'failed'}:
                    row.state = 'expired' if obj.get('status') == 'expired' else 'open'
                row.revision += 1
                session.add(row)
                if row.state == 'open' and obj.get('status') == 'open' and row.url:
                    return {'url': row.url}
        row.revision += 1
        session.add(row)
        return None

    def resolve_finish(session, _):
        row = session.get(BillingCheckout, frozen.id)
        if (obj is not None and row and row.revision > frozen.revision and row.stripe_id == obj.get('id')
                and row.reconciliation == 'verified' and row.state == 'open' and row.url == obj.get('url')):
            return CommitResolution(ResolutionState.COMMITTED, {'url': row.url})
        return CommitResolution(ResolutionState.UNKNOWN)

    result = run_local_transaction(engine, frozen.id, finish, resolve_finish)
    if result is None:
        raise unavailable()
    return result
