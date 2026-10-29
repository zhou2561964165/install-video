"""One-shot Checkout reference reconciliation; never applies payment or membership.

Pure functions consume a version-one original snapshot, never current price or
customer settings. Provider responses are reduced to an explicit audit allowlist.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
import json
import math
import re
import time
import uuid

from .billing_projection import digest, encode


class ReconciliationRejected(ValueError):
    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__(reason_code)


def _reject(reason):
    raise ReconciliationRejected(reason)


@dataclass(frozen=True)
class AuditContext:
    request_id: str
    actor_ref: str
    reason_code: str
    evidence_ref: str


@dataclass(frozen=True)
class ReconciliationPolicy:
    total_seconds: int = 120
    per_get_timeout_seconds: int = 15
    max_gets: int = 3
    max_list_pages: int = 2
    page_size: int = 100

    def __post_init__(self):
        values = ((self.total_seconds, 1, 300), (self.per_get_timeout_seconds, 1, 15),
                  (self.max_gets, 3, 3), (self.max_list_pages, 2, 2), (self.page_size, 100, 100))
        if any(type(v) is not int or not lo <= v <= hi for v, lo, hi in values):
            _reject('invalid_policy')


@dataclass(frozen=True)
class ReconciliationResult:
    task_id: str | None
    checkout_id: str
    status: str
    reason_code: str | None
    get_attempts: int | None


def validate_audit_context(audit: AuditContext) -> None:
    if type(audit) is not AuditContext:
        _reject('invalid_audit_context')
    try:
        valid_uuid = type(audit.request_id) is str and str(uuid.UUID(audit.request_id)) == audit.request_id
    except (ValueError, AttributeError, TypeError):
        valid_uuid = False
    if (not valid_uuid or type(audit.actor_ref) is not str or type(audit.evidence_ref) is not str
            or re.fullmatch(r'op:[A-Za-z0-9_.:-]{1,60}', audit.actor_ref) is None
            or re.fullmatch(r'ev:[A-Za-z0-9_.:-]{1,120}', audit.evidence_ref) is None
            or type(audit.reason_code) is not str
            or audit.reason_code not in {'unknown_create', 'missing_reference', 'legacy_verification'}):
        _reject('invalid_audit_context')


def _ref(value, *, required=False):
    if isinstance(value, Mapping):
        value = value.get('id')
    if value is None and not required:
        return None
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_.:-]{1,255}', value) is None:
        _reject('invalid_provider_reference')
    return value


def _mapping(value):
    if not isinstance(value, Mapping):
        _reject('provider_structure')
    return value


def _freeze_valid(original):
    # Drop parsing/encoding exceptions outside their handlers: JSONDecodeError
    # retains the entire original document in .doc even with `from None`.
    reason = None
    try:
        return _freeze_checked(original)
    except ReconciliationRejected as error:
        reason = error.reason_code
    except (ValueError, TypeError, OverflowError, RecursionError):
        reason = 'invalid_frozen_input'
    _reject(reason)


def _freeze_checked(original):
    payload = original.get('create_payload')
    if (type(payload) is not str or len(payload) > 20000
            or type(original.get('create_payload_version')) is not int or original['create_payload_version'] != 1
            or digest(payload) != original.get('create_payload_sha256')):
        _reject('historical_evidence_missing')
    value = json.loads(payload)
    if (type(original.get('duration_days')) is not int or not 1 <= original['duration_days'] <= 36500
            or type(original.get('livemode')) is not bool or not original.get('provider_account_scope')
            or original.get('provider_account_scope') == 'legacy_unknown'
            or original.get('mode') not in {'payment','subscription'}
            or type(original.get('origin')) is not str):
        _reject('invalid_frozen_input')
    for field in ('id', 'user_id', 'price_id'):
        _ref(original.get(field), required=True)
    params = dict(mode=original['mode'], line_items=[dict(price=original['price_id'], quantity=1)],
        managed_payments=dict(enabled=False), client_reference_id=original['user_id'],
        metadata=dict(checkout_id=original['id']), success_url=original['origin']+'/?membership=success',
        cancel_url=original['origin']+'/?membership=cancel')
    customer = _ref(original.get('customer_id'))
    if customer:
        params['customer'] = customer
    elif original['mode']=='payment':
        params['customer_creation']='always'
    if original['mode']=='subscription':
        params['payment_method_types']=['card']
    expected = dict(version=1, scope=original['provider_account_scope'], livemode=original['livemode'],
        user_id=original['user_id'], price_id=original['price_id'], mode=original['mode'],
        duration_days=original['duration_days'], origin=original['origin'], customer_id=customer,params=params)
    # Canonical equality also rejects bool masquerading as int and extra keys.
    if encode(value) != encode(expected) or payload != encode(expected):
        _reject('invalid_frozen_input')
    return value


def plan_checkout_reads(original: Mapping, cfg, policy: ReconciliationPolicy, started_at: datetime) -> Mapping:
    if type(policy) is not ReconciliationPolicy or not isinstance(started_at,datetime) or started_at.tzinfo is None:
        _reject('invalid_policy')
    if (type(cfg.scope) is not str or cfg.scope=='legacy_unknown' or type(cfg.livemode) is not bool):
        _reject('invalid_read_scope')
    known_scope = original.get('provider_account_scope')
    if known_scope not in {None,'legacy_unknown'} and (known_scope != cfg.scope or original.get('livemode') is not cfg.livemode):
        _reject('scope_mismatch')
    references = original.get('references', ())
    if not isinstance(references,(list,tuple)) or len(references)>100:
        _reject('reference_conflict')
    refs = {'session_id':set(), 'payment_intent':set(), 'subscription_id':set(), 'customer_id':set()}
    if original.get('stripe_id'):
        refs['session_id'].add(_ref(original['stripe_id'],required=True))
    if original.get('customer_id'):
        refs['customer_id'].add(_ref(original['customer_id'],required=True))
    for evidence in references:
        evidence=_mapping(evidence)
        if not evidence.get('inbox_id') or not evidence.get('fact_id'):
            _reject('reference_provenance_missing')
        for field in refs:
            value=_ref(evidence.get(field))
            if value: refs[field].add(value)
    if any(len(values)>1 for values in refs.values()):
        _reject('reference_conflict')
    refs={k:next(iter(v),None) for k,v in refs.items()}
    try:
        _freeze_valid(original)
        verifiable=True
    except ReconciliationRejected:
        if not refs['session_id']:
            raise
        verifiable=False
    created=original.get('created_at')
    trusted_time=type(created) in {int,float} and 0 <= created <= started_at.timestamp()
    bounds=(dict(gte=max(0,math.floor(created)-300),lte=math.floor(started_at.timestamp())+300)
        if trusted_time else None)
    if not trusted_time and not refs['session_id']:
        _reject('untrusted_creation_time')
    if not trusted_time:verifiable=False
    result = dict(version=1, scope=cfg.scope, livemode=cfg.livemode, checkout_id=original['id'],
        verifiable=verifiable, created_bounds=bounds, **refs)
    if refs['session_id']:
        return dict(result,strategy='retrieve')
    if (original.get('create_result_code')=='create_started'
            or original.get('state') in {'paid','expired','failed'} or original.get('fulfilled')
            or original.get('active_checkout_id')!=original['id']):
        _reject('original_intent_unstable')
    params=dict(created=bounds,limit=100)
    if refs['customer_id']: params['customer']=refs['customer_id']
    if refs['payment_intent']: params['payment_intent']=refs['payment_intent']
    elif refs['subscription_id']: params['subscription']=refs['subscription_id']
    return dict(result,strategy='list',params=params)


def _created(obj,query):
    value=obj.get('created'); bounds=query.get('created_bounds')
    if not bounds or type(value) is not int or not bounds['gte']<=value<=bounds['lte']:
        _reject('created_outside_query')


def _candidate(obj,query):
    metadata=_mapping(obj.get('metadata',{}))
    matched=metadata.get('checkout_id')==query['checkout_id']
    for field,remote in (('session_id','id'),('payment_intent','payment_intent'),('subscription_id','subscription')):
        if query.get(field) and _ref(obj.get(remote))==query[field]: matched=True
    return matched


def select_session_candidate(pages: tuple[Mapping, ...], query: Mapping) -> str | None:
    if not isinstance(pages,tuple) or not 1<=len(pages)<=2:
        _reject('pagination_incomplete')
    seen=set(); candidates=[]
    for index,page in enumerate(pages):
        page=_mapping(page); data=page.get('data'); more=page.get('has_more')
        if (type(more) is not bool or type(data) is not list or len(data)>100
                or more is not (index<len(pages)-1) or (more and not data)):
            _reject('pagination_incomplete')
        for raw in data:
            obj=_mapping(raw); identity=_ref(obj.get('id'),required=True)
            if identity in seen: _reject('pagination_duplicate')
            seen.add(identity)
            if _candidate(obj,query):
                _created(obj,query)
                candidates.append(identity)
    if len(candidates)>1: _reject('candidate_conflict')
    return candidates[0] if candidates else None


def project_session(observed: Mapping) -> Mapping:
    """No URLs, arbitrary metadata, Customer bodies, free text or raw hashes."""
    obj=_mapping(observed)
    value={k:_ref(obj.get(k),required=k=='id') for k in
        ('id','customer','payment_intent','subscription','client_reference_id')}
    value['metadata']={'checkout_id':_ref(_mapping(obj.get('metadata',{})).get('checkout_id'))}
    for name,kind in (('livemode',bool),('created',int),('amount_total',int),('currency',str),
                      ('mode',str),('status',str),('payment_status',str)):
        item=obj.get(name)
        if item is not None and (type(item) is not kind or (kind is int and not 0<=item<=9223372036854775807)
                or (kind is str and (len(item)>40 or re.fullmatch(r'[a-z_]+',item) is None))):
            _reject('provider_structure')
        value[name]=item
    if value['currency'] is not None and re.fullmatch(r'[a-z]{3}',value['currency']) is None:
        _reject('provider_structure')
    container=_mapping(obj.get('line_items',{})); data=container.get('data',[])
    if type(data) is not list or len(data)>100: _reject('provider_structure')
    value['line_items']={'has_more':container.get('has_more'), 'data':[]}
    if value['line_items']['has_more'] is not None and type(value['line_items']['has_more']) is not bool:
        _reject('provider_structure')
    for item in data:
        item=_mapping(item);quantity=item.get('quantity')
        if type(quantity) is not int or not 0<=quantity<=9223372036854775807:
            _reject('provider_structure')
        value['line_items']['data'].append(dict(price=_ref(item.get('price'),required=True),quantity=quantity))
    return value


def verify_session_binding(original: Mapping, observed: Mapping, query: Mapping) -> Mapping:
    frozen=_freeze_valid(original)
    if (not query.get('verifiable') or query['scope']!=original['provider_account_scope']
            or query['livemode'] is not original['livemode']): _reject('historical_evidence_missing')
    obj=_mapping(observed); value=project_session(obj); params=frozen['params']
    expected_id=query.get('candidate_id') or query.get('session_id')
    if (not expected_id or value['id']!=expected_id or value['livemode'] is not original['livemode']
            or value['mode']!=original['mode'] or value['client_reference_id']!=original['user_id']
            or value['metadata']['checkout_id']!=original['id']): _reject('binding_mismatch')
    _created(obj,query)
    prior=query.get('candidate_binding')
    if prior is not None:
        prior=_mapping(prior)
        if any(value[field]!=prior.get(field) for field in
               ('id','metadata','client_reference_id','mode','customer','payment_intent','subscription')):
            _reject('reference_changed')
    lines=value['line_items']
    if lines['has_more'] is not False or lines['data'] != [dict(price=original['price_id'],quantity=1)]:
        _reject('line_items_mismatch')
    for field in ('success_url','cancel_url'):
        if obj.get(field)!=params[field]: _reject('frozen_url_mismatch')
    for field,remote in (('customer_id','customer'),('payment_intent','payment_intent'),('subscription_id','subscription')):
        if query.get(field) and value[remote]!=query[field]: _reject('reference_changed')
    if original.get('membership_customer_id') and value['customer']!=original['membership_customer_id']:
        _reject('customer_mismatch')
    if original['mode']=='subscription' and obj.get('payment_method_types')!=['card']:
        _reject('payment_methods_mismatch')
    if (original.get('state') in {'paid','expired','failed'} or original.get('fulfilled')
            or original.get('active_checkout_id')!=original['id'] or original.get('create_result_code')=='create_started'):
        _reject('original_intent_unstable')
    return dict(session_id=value['id'],local_freeze_verified=True,remote_managed_payments_verified=False,
                remote_duration_verified=False,session=value)


# Database imports deliberately follow the pure contract. No app.db/settings or
# environment loading: engine/config/provider are explicit trusted dependencies.
from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select
from ..models import (Membership, BillingCheckout, BillingFact, BillingInbox,
    BillingReconciliationTask, BillingReconciliationAudit)
from .db_transactions import CommitResolution, ResolutionState, lock_user, run_local_transaction
from .billing_pg import locked


def _require_pg(engine):
    if engine.dialect.name != 'postgresql':
        _reject('postgresql_required')


def _now(session):
    return session.exec(select(func.clock_timestamp())).one()


def _result(task, now):
    if task.status=='running' and now>=task.budget_deadline:
        return ReconciliationResult(task.id,task.checkout_id,'needs_review','deadline_elapsed',task.get_attempts)
    return ReconciliationResult(task.id,task.checkout_id,
        'in_progress' if task.status=='running' else task.status,task.outcome_reason,task.get_attempts)


def inspect_reconciliation(task_id: str, *, engine) -> ReconciliationResult:
    _require_pg(engine)
    with Session(engine) as session:
        task=session.get(BillingReconciliationTask,task_id)
        if task is None:
            _reject('task_not_found')
        return _result(task,_now(session))


def _read_uncertain_attempts(engine, task_id, checkout_id):
    try:
        with Session(engine) as session:
            task=session.get(BillingReconciliationTask,task_id)
            if task is not None and task.checkout_id==checkout_id:
                return task.get_attempts
    except Exception:
        pass
    return None


def _unknown(session, operation_id):
    # A visible reservation is not permission to dispatch after lost commit ACK.
    return CommitResolution(ResolutionState.UNKNOWN)


def _references(session, row, cfg):
    """Only same-intent Fact references backed by an authenticated Inbox record.

The original Checkout FK and user binding come from the existing trusted Fact
writer, not a present-day Membership subscription. Only canonical references
that match the Fact are admitted. A malformed/conflicting source fails closed.
"""
    facts=session.exec(select(BillingFact).where(BillingFact.checkout_id==row.id)
        .order_by(BillingFact.id).limit(101)).all()
    if len(facts)>100:
        _reject('reference_evidence_unbounded')
    references=[]
    for fact in facts:
        inbox=session.get(BillingInbox,fact.inbox_id) if fact.inbox_id else None
        if (inbox is None or fact.user_id!=row.user_id or fact.provider_account_scope!=cfg.scope
                or fact.livemode is not cfg.livemode or inbox.provider_account_scope!=cfg.scope
                or inbox.livemode is not cfg.livemode or fact.event_id!=inbox.event_id
                or inbox.canonical_version!=1 or not inbox.canonical_payload
                or digest(inbox.canonical_payload)!=inbox.canonical_sha256):
            _reject('reference_provenance_missing')
        failed=False
        try:
            event=json.loads(inbox.canonical_payload)
            obj=event['data']['object']
            kind=event['type']
            if (event['id']!=inbox.event_id or event['scope']!=cfg.scope
                    or event['livemode'] is not cfg.livemode or event['version']!=1):
                failed=True
        except (ValueError,TypeError,KeyError,RecursionError):
            failed=True
        if failed:
            _reject('reference_provenance_missing')
        if kind.startswith('checkout.session.'):
            canonical_session=obj.get('id')
            canonical_sub=obj.get('subscription')
            if _mapping(obj.get('metadata',{})).get('checkout_id')!=row.id:
                _reject('reference_provenance_missing')
        elif kind in {'invoice.paid','invoice.payment_failed'}:
            canonical_session=None
            canonical_sub=(obj.get('subscription') or
                _mapping(_mapping(obj.get('parent',{})).get('subscription_details',{})).get('subscription'))
        else:
            # Other Fact kinds do not establish a Checkout Session read target.
            if fact.session_id or fact.payment_intent or fact.subscription_id:
                _reject('reference_provenance_missing')
            continue
        if (fact.session_id!=_ref(canonical_session) or fact.payment_intent!=_ref(obj.get('payment_intent'))
                or fact.subscription_id!=_ref(canonical_sub)):
            _reject('reference_provenance_missing')
        references.append(dict(fact_id=fact.id,inbox_id=inbox.id,session_id=fact.session_id,
            payment_intent=fact.payment_intent,subscription_id=fact.subscription_id,
            customer_id=_ref(obj.get('customer'))))
    return references


_ORIGINAL_FIELDS=('id','user_id','provider_account_scope','livemode','mode','price_id','duration_days',
    'origin','customer_id','stripe_id','created_at','revision','state','fulfilled','create_result_code',
    'create_payload','create_payload_sha256','create_payload_version')


def _snapshot(session,row,account,cfg):
    value={field:getattr(row,field) for field in _ORIGINAL_FIELDS}
    value.update(membership_revision=account.revision,membership_customer_id=account.customer_id,
        active_checkout_id=account.active_checkout_id)
    error=None
    try:
        value['references']=_references(session,row,cfg)
    except ReconciliationRejected as failure:
        error=failure.reason_code
    if error:
        value.update(references=[],reference_error=error)
    return value


def _signature(value):
    # Only transient hashing touches frozen URLs. The audit retains this digest,
    # never the URLs or raw create JSON. Own reservation revisions are excluded.
    return digest(encode({k:v for k,v in value.items() if k not in {'revision','membership_revision'}}))


def _input_projection(original):
    return dict(version=1,checkout_id=original['id'],user_id=original['user_id'],
        provider_account_scope=original['provider_account_scope'],livemode=original['livemode'],
        stripe_id=original['stripe_id'],price_id=original['price_id'],mode=original['mode'],
        duration_days=original['duration_days'],customer_id=original['customer_id'],
        created_at=original['created_at'],freeze_version=original['create_payload_version'],
        freeze_sha256=original['create_payload_sha256'],references=original['references'],
        initial_checkout_revision=original['revision'],membership_revision=original['membership_revision'],
        binding_sha256=_signature(original),reference_error=original.get('reference_error'))


def _lock(session, uid, checkout_id, task_id=None):
    lock_user(session,uid)
    account=locked(session,Membership,Membership.user_id,uid)
    row=locked(session,BillingCheckout,BillingCheckout.id,checkout_id)
    if account is None or row is None or row.user_id!=uid:
        _reject('original_not_found')
    task=(locked(session,BillingReconciliationTask,BillingReconciliationTask.id,task_id)
        if task_id else locked(session,BillingReconciliationTask,BillingReconciliationTask.checkout_id,checkout_id))
    return account,row,task


def _append(session,task,identity,kind,projection,now,ordinal=None):
    if task.status!='running':
        _reject('task_already_terminal')
    payload=encode(projection)
    if len(payload.encode('utf8'))>65536:
        _reject('audit_projection_unbounded')
    audit=BillingReconciliationAudit(id=identity,task_id=task.id,seq=task.next_audit_seq,
        event_kind=kind,get_ordinal=ordinal,recorded_at=now,actor_ref=task.actor_ref,
        reason_code=task.reason_code,evidence_ref=task.evidence_ref,
        projection_json=payload,projection_sha256=digest(payload))
    task.next_audit_seq+=1;task.revision+=1
    session.add(task);session.add(audit)
    return audit


def _seal(session,task,row,identity,reason,now,witness,*,verified=False):
    status='verified' if verified else 'needs_review'
    projection=dict(version=1,status=status,reason_code=reason,get_attempts=task.get_attempts,
        linked_session_id=row.stripe_id,expected_checkout_revision=task.expected_checkout_revision)
    audit=_append(session,task,identity,'task_finished',projection,now)
    task.status=status;task.outcome_reason=reason;task.completed_at=now
    session.add(task)
    witness.update(id=audit.id,sha256=audit.projection_sha256,status=status,reason=reason,
        attempts=task.get_attempts,session_id=row.stripe_id,expected_revision=task.expected_checkout_revision)
    session.info['b3b_stage']='task_finished'
    return _result(task,now)


def _resolve_final(task_id,checkout_id,witness):
    def resolve(session,_):
        if not witness:
            return CommitResolution(ResolutionState.UNKNOWN)
        audit=session.get(BillingReconciliationAudit,witness['id'])
        task=session.get(BillingReconciliationTask,task_id)
        row=session.get(BillingCheckout,checkout_id)
        if (audit is not None and audit.task_id==task_id and audit.event_kind=='task_finished'
                and audit.projection_sha256==witness['sha256'] and digest(audit.projection_json)==witness['sha256']
                and task is not None and task.checkout_id==checkout_id and task.status==witness['status']
                and task.outcome_reason==witness['reason'] and task.completed_at is not None
                and task.get_attempts==witness['attempts'] and task.expected_checkout_revision==witness['expected_revision']
                and row is not None and row.stripe_id==witness['session_id']
                and (task.status!='verified' or row.reconciliation=='verified')):
            return CommitResolution(ResolutionState.COMMITTED,_result(task,_now(session)))
        return CommitResolution(ResolutionState.UNKNOWN)
    return resolve


@dataclass(frozen=True)
class _Work:
    task_id: str
    checkout_id: str
    user_id: str
    owner_ref: str
    original: Mapping
    query: Mapping


class _ReservationExpired(Exception):
    """Internal savepoint control: no partial task/Checkout reservation."""


def _guard(session,task,row,account,work,cfg):
    if task is None or task.owner_ref!=work.owner_ref or task.checkout_id!=work.checkout_id:
        return 'task_identity_changed'
    if row.revision!=task.expected_checkout_revision or account.revision!=task.membership_revision:
        return 'original_revision_changed'
    if _signature(_snapshot(session,row,account,cfg))!=_signature(work.original):
        return 'original_binding_changed'
    return None


def _project_page(raw,query):
    page=_mapping(raw);data=page.get('data');more=page.get('has_more')
    if type(data) is not list or len(data)>100 or type(more) is not bool or (more and not data):
        _reject('pagination_incomplete')
    projected=[project_session(value) for value in data]
    ids=[value['id'] for value in projected]
    if len(ids)!=len(set(ids)):
        _reject('pagination_duplicate')
    candidates=[]
    for value in projected:
        if _candidate(value,query):
            _created(value,query)
            candidates.append({key:value[key] for key in ('id','metadata','client_reference_id','mode',
                'customer','payment_intent','subscription','created')})
    if len(candidates)>1:
        _reject('candidate_conflict')
    summary=dict(version=1,operation='list',object_count=len(data),has_more=more,candidates=candidates,
                 last_id=ids[-1] if ids else None)
    return dict(data=projected,has_more=more),summary


def _prepare_provider_projection(projection):
    """Encode and bound untrusted projections while no DB connection is held.

    Leave room for the fixed terminal outcome added by the database action.
    Exception objects are never retained or chained into a domain result.
    """
    reason=None
    try:
        payload=encode(projection)
        if len(payload.encode('utf8'))>64000:
            reason='provider_projection_too_large'
    except (ValueError,TypeError,OverflowError,RecursionError):
        reason='provider_projection_invalid'
    if reason:
        return dict(version=1,operation=projection['operation'],result_code=reason),reason
    return projection,None


def reconcile_checkout(checkout_id: str, audit: AuditContext, *, engine, cfg,
                       policy: ReconciliationPolicy, provider) -> ReconciliationResult:
    """Internal trusted operation. Permanent one task; no resume or new cycle."""
    validate_audit_context(audit)
    _require_pg(engine)
    if type(policy) is not ReconciliationPolicy:
        _reject('invalid_policy')
    local_deadline=time.monotonic()+policy.total_seconds
    _ref(checkout_id,required=True)
    with Session(engine) as discovery:
        row=discovery.get(BillingCheckout,checkout_id)
        if row is None:
            _reject('original_not_found')
        uid=row.user_id
    owner=str(uuid.uuid4());start_id=str(uuid.uuid4());finish_id=str(uuid.uuid4())
    task_id=audit.request_id

    def transaction(identity,action,resolver):
        try:
            return run_local_transaction(engine,identity,action,resolver)
        except HTTPException as error:
            detail=error.detail if isinstance(error.detail,dict) else {}
            reason=detail.get('error_type','database_unavailable')
        # Read-only count recovery never grants permission for another GET.
        return ReconciliationResult(task_id,checkout_id,'transaction_uncertain',reason,
            _read_uncertain_attempts(engine,task_id,checkout_id))

    start_witness={}
    def start(session):
        account,row,existing=_lock(session,uid,checkout_id)
        now=_now(session)
        if existing is not None:
            return _result(existing,now)
        collision=session.get(BillingReconciliationTask,audit.request_id)
        if collision is not None:
            _reject('request_id_conflict')
        original=_snapshot(session,row,account,cfg)
        reason=original.get('reference_error')
        plan=None
        if reason is None:
            try:
                plan=plan_checkout_reads(original,cfg,policy,now)
            except ReconciliationRejected as failure:
                reason=failure.reason_code
        old=bool(row.reconcile_attempts or row.reconciliation_started_at or row.reconciliation_actor
                 or row.reconciliation_reason or row.reconciliation_evidence)
        if old:reason='prior_manual_evidence'
        plan=plan or dict(version=1,strategy='none',reason_code=reason)
        projection=_input_projection(original)
        task=BillingReconciliationTask(id=audit.request_id,checkout_id=row.id,user_id=uid,
            provider_account_scope=cfg.scope,livemode=cfg.livemode,actor_ref=audit.actor_ref,
            reason_code=audit.reason_code,evidence_ref=audit.evidence_ref,input_sha256=digest(encode(projection)),
            query_json=encode(plan),policy_json=encode(dict(**policy.__dict__,created_skew_seconds=300)),
            initial_checkout_revision=row.revision,expected_checkout_revision=row.revision,
            membership_revision=account.revision,owner_ref=owner,started_at=now,
            budget_deadline=now+timedelta(seconds=policy.total_seconds))
        session.add(task);session.flush()
        _append(session,task,start_id,'task_started',dict(version=1,input=projection,query=plan),now)
        session.info['b3b_stage']='task_started'
        if not old:
            row.reconciliation_started_at=now;row.reconciliation_actor=audit.actor_ref
            row.reconciliation_reason=audit.reason_code;row.reconciliation_evidence=audit.evidence_ref
            row.revision+=1;task.expected_checkout_revision=row.revision;session.add(row)
        if reason:
            return _seal(session,task,row,finish_id,reason,now,start_witness)
        return _Work(task.id,row.id,uid,owner,original,plan)

    # Establishment ACK loss always stops; even a known terminal start is safe
    # to inspect later but cannot authorize network within this invocation.
    work=transaction(start_id,start,_unknown)
    if isinstance(work,ReconciliationResult):
        return work

    def finish_without_get(reason):
        identity=str(uuid.uuid4());witness={}
        def finish(session):
            account,row,task=_lock(session,uid,checkout_id,work.task_id)
            now=_now(session)
            if task is None:_reject('task_not_found')
            if task.status!='running':return _result(task,now)
            return _seal(session,task,row,identity,reason,now,witness)
        return transaction(identity,finish,_resolve_final(work.task_id,checkout_id,witness))

    api=None;construction_failed=False
    try:
        api=provider()
    except Exception:
        construction_failed=True
    if construction_failed:
        return finish_without_get('provider_construction_failed')
    pages=[];query=dict(work.query);operation='retrieve' if query['strategy']=='retrieve' else 'list'
    params=dict(query.get('params',{}));session_id=query.get('session_id')
    for _ in range(policy.max_gets):
        reserve_id=str(uuid.uuid4());reserve_finish_id=str(uuid.uuid4());reserve_witness={}
        reserved_projection=dict(version=1,operation=operation,
            **({'session_id':session_id} if operation=='retrieve' else {'params':params}))
        def reserve(session):
            account,row,task=_lock(session,uid,checkout_id,work.task_id)
            now=_now(session)
            if task is None:_reject('task_not_found')
            if task.status!='running':return _result(task,now)
            reason=_guard(session,task,row,account,work,cfg)
            if now>=task.budget_deadline:reason='deadline_elapsed'
            if task.get_attempts>=3 or row.reconcile_attempts>=3:reason='get_budget_exhausted'
            if reason:
                return _seal(session,task,row,reserve_finish_id,reason,now,reserve_witness)
            expired=False
            try:
                with session.begin_nested():
                    changed=session.execute(update(BillingReconciliationTask).where(
                        BillingReconciliationTask.id==task.id,
                        BillingReconciliationTask.status=='running',
                        BillingReconciliationTask.owner_ref==work.owner_ref,
                        BillingReconciliationTask.expected_checkout_revision==row.revision,
                        BillingReconciliationTask.get_attempts==task.get_attempts,
                        BillingReconciliationTask.get_attempts<BillingReconciliationTask.get_limit,
                        func.clock_timestamp()<BillingReconciliationTask.budget_deadline)
                        .values(get_attempts=BillingReconciliationTask.get_attempts+1,
                            expected_checkout_revision=row.revision+1,
                            revision=BillingReconciliationTask.revision+1)
                        .returning(BillingReconciliationTask.get_attempts,
                            BillingReconciliationTask.expected_checkout_revision,BillingReconciliationTask.revision)
                        .execution_options(synchronize_session=False)).first()
                    if changed is None:raise _ReservationExpired()
                    mirrored=session.execute(update(BillingCheckout).where(
                        BillingCheckout.id==row.id,BillingCheckout.revision==row.revision,
                        BillingCheckout.reconcile_attempts==row.reconcile_attempts,
                        BillingCheckout.reconcile_attempts<3,func.clock_timestamp()<task.budget_deadline)
                        .values(reconcile_attempts=BillingCheckout.reconcile_attempts+1,
                            revision=BillingCheckout.revision+1)
                        .returning(BillingCheckout.reconcile_attempts,BillingCheckout.revision)
                        .execution_options(synchronize_session=False)).first()
                    if mirrored is None:raise _ReservationExpired()
                    from sqlalchemy.orm.attributes import set_committed_value
                    for name,value in zip(('get_attempts','expected_checkout_revision','revision'),changed):
                        set_committed_value(task,name,value)
                    for name,value in zip(('reconcile_attempts','revision'),mirrored):
                        set_committed_value(row,name,value)
                    _append(session,task,reserve_id,'get_reserved',reserved_projection,_now(session),task.get_attempts)
                    session.flush()
            except _ReservationExpired:
                expired=True
            if expired:
                # Both guarded counter updates rolled back to the savepoint.
                # Re-read the held rows before allocating terminal audit seq.
                session.refresh(task);session.refresh(row)
                return _seal(session,task,row,reserve_finish_id,'deadline_elapsed',_now(session),reserve_witness)
            session.info['b3b_stage']='get_reserved'
            return task.get_attempts
        ordinal=transaction(reserve_id,reserve,_unknown)
        if isinstance(ordinal,ReconciliationResult):return ordinal
        if time.monotonic()>=local_deadline:
            # A scheduler pause after durable reservation never restores the GET.
            # Its unused-but-reserved ordinal remains conservatively consumed.
            return finish_without_get('deadline_elapsed')
        reason=None;projection=None;verification=None;next_params=None;next_session=None
        try:
            raw=api.retrieve_session(session_id) if operation=='retrieve' else api.list_sessions(params)
        except Exception:
            reason='provider_read_failed'
        if reason is None:
            try:
                if operation=='retrieve':
                    projected=project_session(raw)
                    projection=dict(version=1,operation='retrieve',session=projected)
                    verification=verify_session_binding(work.original,raw,query)
                else:
                    page,projection=_project_page(raw,query)
                    pages.append(page)
                    ids=[item['id'] for previous in pages for item in previous['data']]
                    if len(ids)!=len(set(ids)):_reject('pagination_duplicate')
                    if page['has_more']:
                        if len(pages)>=2:_reject('pagination_incomplete')
                        next_params=dict(query['params'],starting_after=page['data'][-1]['id'])
                    else:
                        candidate=select_session_candidate(tuple(pages),query)
                        if candidate is None:
                            reason='candidate_absent'
                        else:
                            prior=next(item for previous in pages for item in previous['data'] if item['id']==candidate)
                            query=dict(query,candidate_id=candidate,candidate_binding=prior)
                            next_session=candidate
            except ReconciliationRejected as failure:
                reason=failure.reason_code
            except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
                reason='provider_structure'
        projection=projection or dict(version=1,operation=operation,result_code=reason)
        if reason:projection=dict(projection,result_code=reason)
        projection,projection_failure=_prepare_provider_projection(projection)
        if projection_failure:reason=projection_failure
        observe_id=str(uuid.uuid4());observed_finish_id=str(uuid.uuid4());witness={}
        def observe(session):
            account,row,task=_lock(session,uid,checkout_id,work.task_id)
            now=_now(session)
            if task is None:_reject('task_not_found')
            if task.status!='running':return _result(task,now)
            invalid=_guard(session,task,row,account,work,cfg)
            outcome=invalid or reason
            if now>=task.budget_deadline:outcome='late_result'
            audit_projection=dict(projection,result_code=outcome or 'observed')
            _append(session,task,observe_id,'get_observed',audit_projection,now,ordinal)
            session.info['b3b_stage']='get_observed'
            if outcome:
                return _seal(session,task,row,observed_finish_id,outcome,now,witness)
            if verification is not None:
                target=verification['session_id']
                if row.stripe_id not in {None,target}:
                    return _seal(session,task,row,observed_finish_id,'reference_changed',now,witness)
                # Qualify the actual write against a fresh DB clock, not the
                # transaction's first time sample. No payment/URL/state writes.
                changed=session.execute(update(BillingCheckout).where(BillingCheckout.id==row.id,
                    BillingCheckout.revision==task.expected_checkout_revision,
                    func.clock_timestamp()<task.budget_deadline).values(stripe_id=target,
                    reconciliation='verified',revision=BillingCheckout.revision+1)
                    .returning(BillingCheckout.revision).execution_options(synchronize_session=False)).first()
                final_now=_now(session)
                if changed is None:
                    return _seal(session,task,row,observed_finish_id,'late_result',final_now,witness)
                # Keep the loaded ORM row clean; assigning would flush a second
                # unchecked UPDATE after the qualified statement above.
                from sqlalchemy.orm.attributes import set_committed_value
                set_committed_value(row,'stripe_id',target)
                set_committed_value(row,'reconciliation','verified')
                set_committed_value(row,'revision',changed[0])
                task.expected_checkout_revision=changed[0]
                return _seal(session,task,row,observed_finish_id,'binding_verified',final_now,witness,verified=True)
            return None
        outcome=transaction(observe_id,observe,_resolve_final(work.task_id,checkout_id,witness))
        if isinstance(outcome,ReconciliationResult):return outcome
        if next_session:
            operation='retrieve';session_id=next_session
        elif next_params is not None:
            params=next_params
        else:
            return finish_without_get('pagination_incomplete')
    return finish_without_get('get_budget_exhausted')
