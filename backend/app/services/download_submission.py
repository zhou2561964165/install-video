"""PG durable acceptance, receipts and direct completion. No source implementation.

Every database action composes with B2 and never commits. Only submit_download
owns transaction runners. The optional trusted resolver is an explicit test /
future adapter seam, not a declaration that the legacy yt-dlp path is safe.
"""
from dataclasses import dataclass, field, replace
from datetime import timedelta, timezone
import hashlib
import json
import math
import re
import time
import uuid
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from sqlalchemy import Engine, delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from ..config import settings
from ..models import (DownloadAccess, DownloadIdempotency, DownloadOperation, Job, JobStatus,
                      Membership, Quota, QuotaCharge, ResourceReservation)
from ..schemas import DownloadRequest, DownloadResponse
from . import download_budget_codec as codec
from .bilibili_session import SessionError
from .db_transactions import CommitResolution, ResolutionState, lock_user, run_local_transaction
from .outbound_budget import BudgetProfile, OutboundBudget
from .outbound_httpx import ControlledHttpError
from .outbound_policy import OutboundError, OutboundPurpose, validate_url
from .quota import charge_submission
from .quota_policy import is_unlimited_user
from .membership import entitlement
from .resource_capacity import (CapacityDemand, lock_capacity_counters, release_capacity,
                                release_receipt_entry, reserve_capacity, reserve_receipt_entry)


def _error(status, code, message):
    return HTTPException(status, detail={'error_type': code, 'error': message})


def unavailable():
    return _error(503, 'outbound_unavailable', '安全访问通道暂不可用')


@dataclass(frozen=True)
class AccessSnapshot:
    max_height: int | None
    membership_revision: int
    canonical_format_id: str


@dataclass(frozen=True)
class ResolveToken:
    operation_id: str
    owner: str
    epoch: int


@dataclass(frozen=True)
class SubmissionDecision:
    kind: str
    response: DownloadResponse | None = None
    token: ResolveToken | None = None
    error: HTTPException | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DirectResult:
    response: DownloadResponse | None = None
    expires_at: float | None = None


def canonical_request(request):
    payload = json.dumps(request.model_dump(), sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return payload, hashlib.sha256(payload.encode('utf8')).hexdigest()


def validate_key(key):
    if key is not None and (type(key) is not str or not 1 <= len(key) <= 128 or
                           any(not '!' <= character <= '~' for character in key)):
        raise _error(422, 'idempotency_key', 'Idempotency-Key 必须为1至128个可见ASCII字符')


def _now(session):
    return session.exec(select(func.clock_timestamp())).one().astimezone(timezone.utc)


def _demands(user_id, receipt=False):
    result = (CapacityDemand('admission_slots', 'global'), CapacityDemand('admission_slots', 'user:' + user_id))
    return result + ((CapacityDemand('receipt_entries', 'global'),) if receipt else ())


def _membership(session, user_id, now):
    session.exec(insert(Membership).values(user_id=user_id, status='free', expires_at=0,
        cancel_at_period_end=False, revision=0).on_conflict_do_nothing(index_elements=['user_id']))
    row = session.exec(select(Membership).where(Membership.user_id == user_id).with_for_update()
                       .execution_options(populate_existing=True)).one()
    height = None if entitlement(session, user_id, now).effective or is_unlimited_user(user_id) else settings.membership_free_max_height
    return AccessSnapshot(height, row.revision, '')


def read_access_snapshot(engine: Engine, user_id: str) -> AccessSnapshot:
    """Read, close, then let the trusted caller verify/bound formats outside DB."""
    with Session(engine) as session:
        now = _now(session)
        row = session.get(Membership, user_id)
        height = None if entitlement(session, user_id, now).effective or is_unlimited_user(user_id) else settings.membership_free_max_height
        return AccessSnapshot(height, row.revision if row else 0, '')


def _receipt(session, user_id, key):
    return session.exec(select(DownloadIdempotency).where(DownloadIdempotency.user_id == user_id,
        DownloadIdempotency.key == key).with_for_update().execution_options(populate_existing=True)).first()


def expire_complete_receipts(session, now):
    """Caller prelocks receipt capacity. Protected history never qualifies.

    No operation owns a reverse FK: deleting a receipt leaves its independent
    operation/charge/Job history intact. Each successful delete decrements once.
    """
    rows = session.exec(select(DownloadIdempotency.id).where(DownloadIdempotency.state == 'complete',
        DownloadIdempotency.expires_at.is_not(None), DownloadIdempotency.expires_at <= now.timestamp())
        .order_by(DownloadIdempotency.id).limit(settings.download_idempotency_max_entries)
        .with_for_update(skip_locked=True)).all()
    for identity in rows:
        deleted = session.exec(delete(DownloadIdempotency).where(DownloadIdempotency.id == identity,
            DownloadIdempotency.state == 'complete', DownloadIdempotency.expires_at <= now.timestamp())
            .returning(DownloadIdempotency.id)).first()
        if deleted is not None:
            release_receipt_entry(session)


def _finish_receipt(session, receipt, now, *, response=None, error=None, direct_expires_at=None):
    if receipt is None:
        return
    if receipt.state != 'pending':
        raise _error(409, 'submission_changed', '提交记录已变化')
    receipt.state = 'complete'
    receipt.status_code = error.status_code if error else 200
    receipt.response_json = json.dumps({'detail': error.detail} if error else response.model_dump(),
                                       ensure_ascii=False, separators=(',', ':'))
    receipt.expires_at = now.timestamp() + settings.download_idempotency_ttl_seconds
    receipt.direct_expires_at = direct_expires_at
    session.add(receipt)


def replay_receipt(session, user_id, key, fingerprint, *, now=None):
    row = _receipt(session, user_id, key)
    if row is None:
        return None
    return _replay(session, row, fingerprint, now or _now(session))


def _replay(session, row, fingerprint, now, *, lock_job=True):
    if row.fingerprint != fingerprint:
        return SubmissionDecision('error', error=_error(409, 'idempotency_conflict', '同一Idempotency-Key不能用于不同的下载请求'))
    if row.state == 'pending':
        return SubmissionDecision('error', error=_error(409, 'idempotency_in_progress', '下载提交仍在处理或状态待确认，请保留原请求标识'))
    if row.state != 'complete':
        # Preserve a safe legacy uncertain response verbatim when present;
        # imported rows without a response remain durably blocked as before.
        detail = None
        try:
            saved = json.loads(row.response_json)
            candidate = saved['detail']
            if row.state == 'uncertain' and row.status_code == 503 and type(candidate) is dict and candidate.get('error_type') == 'idempotency_uncertain':
                detail = candidate
        except (ValueError, TypeError, KeyError):
            pass
        if detail is not None:
            return SubmissionDecision('error', error=HTTPException(503, detail=detail))
        return SubmissionDecision('error', error=_error(503, 'idempotency_uncertain', '下载提交状态未确定，请保留原请求标识'))
    try:
        body = json.loads(row.response_json)
        if row.status_code != 200:
            return SubmissionDecision('error', error=HTTPException(row.status_code, detail=body['detail'],
                                      headers={'Idempotency-Status': 'complete'}))
        response = DownloadResponse.model_validate(body)
    except (ValueError, TypeError, KeyError):
        return SubmissionDecision('error', error=_error(503, 'idempotency_uncertain', '下载提交状态未确定，请保留原请求标识'))
    expired = row.direct_expires_at is not None and row.direct_expires_at <= now.timestamp()
    if response.mode == 'server':
        statement = select(Job).where(Job.id == response.job_id, Job.user_id == row.user_id)
        if lock_job:
            statement = statement.with_for_update()
        job = session.exec(statement.execution_options(populate_existing=True)).first()
        expired = job is None or (job.expires_at is not None and job.expires_at <= now)
    if expired:
        return SubmissionDecision('error', error=_error(410, 'idempotency_expired', '此下载请求已失效，请明确发起一次新的下载'))
    return SubmissionDecision('replay', response=response)


def _queue(session, op, request):
    if op.job_id is not None:
        raise _error(409, 'submission_changed', '提交记录已变化')
    # C1: a v2 Job, leasable by the durable worker; its absolute run window is the operation deadline.
    job = Job(user_id=op.user_id, url=request.url, format_id=request.format_id, status=JobStatus.queued,
              execution_version=2, internal_state='queued', run_deadline_at=op.deadline_at)
    session.add(job)
    session.flush()
    session.add(DownloadAccess(job_id=job.id, max_height=op.max_height))
    session.flush()
    op.job_id = op.job_id_tombstone = job.id
    op.state = 'accepted_server'
    op.resolve_owner = op.resolve_lease_deadline = None
    op.resolve_attempt_deadline = None
    session.add(op)
    return DownloadResponse(mode='server', job_id=job.id)


def accept_submission(session, user_id, request, key, snapshot, *, operation_id, receipt_id,
                      owner, server_required=False, resolver_ready=False):
    """Pure local acceptance: resources→User→Membership→receipt→op→quota→Job."""
    validate_key(key)
    payload, fingerprint = canonical_request(request)
    lock_capacity_counters(session, _demands(user_id, key is not None))
    lock_user(session, user_id)
    now = _now(session)
    current = _membership(session, user_id, now)
    receipt = _receipt(session, user_id, key) if key is not None else None
    # Only complete receipts may release a key. Legacy pending/uncertain remain.
    if receipt is not None and receipt.state == 'complete' and receipt.expires_at is not None and receipt.expires_at <= now.timestamp():
        removed = session.exec(delete(DownloadIdempotency).where(DownloadIdempotency.id == receipt.id,
                    DownloadIdempotency.state == 'complete').returning(DownloadIdempotency.id)).first()
        if removed is not None:
            release_receipt_entry(session)
        receipt = None
    if receipt is not None:
        return _replay(session, receipt, fingerprint, now)
    if (type(snapshot) is not AccessSnapshot or current.max_height != snapshot.max_height or
            current.membership_revision != snapshot.membership_revision or
            request.format_id != snapshot.canonical_format_id):
        raise _error(409, 'submission_changed', '提交期间会员或视频格式已变化，请重新解析')
    if not (request.force_server or server_required) and not resolver_ready:
        raise unavailable()
    if key is not None:
        expire_complete_receipts(session, now)
        reserve_receipt_entry(session)
        receipt = DownloadIdempotency(id=receipt_id, user_id=user_id, key=key,
                                     fingerprint=fingerprint, created_at=now.timestamp())
        session.add(receipt)
        session.flush()
    decision = None
    rejected = None
    try:
        # Explicit pre-accept rejection can complete a receipt, while every
        # attempted op / capacity / quota / Job write rolls back together.
        with session.begin_nested():
            envelope = codec.initial_budget()
            resolving = not (request.force_server or server_required)
            op = DownloadOperation(id=operation_id, user_id=user_id, canonical_payload=payload,
                fingerprint=fingerprint, canonical_format_id=request.format_id, max_height=snapshot.max_height,
                membership_revision=snapshot.membership_revision, quota_day=now.date(),
                state='resolving' if resolving else 'accepted_server', accepted_at=now,
                deadline_at=now + timedelta(seconds=BudgetProfile.download_parent().seconds),
                resolve_deadline_at=now + timedelta(seconds=BudgetProfile.direct_parent().seconds),
                resolve_attempts_limit=BudgetProfile.direct_parent().children,
                budget_version=codec.VERSION, budget_checkpoint_json=codec.encode_budget(envelope), budget_checkpoint_at=now,
                resolve_owner=owner if resolving else None, resolve_epoch=1 if resolving else 0,
                resolve_lease_deadline=now + timedelta(seconds=BudgetProfile.direct_parent().seconds) if resolving else None)
            session.add(op)
            session.flush()
            if receipt is not None:
                receipt.operation_id = op.id
                session.add(receipt)
                session.flush()
            reserve_capacity(session, _demands(user_id), operation_id=op.id)
            charge_submission(session, user_id, op.id, now)
            if resolving:
                decision = SubmissionDecision('resolve', token=ResolveToken(op.id, owner, op.resolve_epoch))
            else:
                response = _queue(session, op, request)
                _finish_receipt(session, receipt, now, response=response)
                decision = SubmissionDecision('server', response=response)
            session.flush()
    except HTTPException as error:
        if error.status_code not in (429, 503) or receipt is None:
            raise
        rejected = _error(error.status_code, error.detail['error_type'], error.detail['error'])
    if rejected is not None:
        # SAVEPOINT rollback expires its modifications; re-read this exact row.
        receipt = session.get(DownloadIdempotency, receipt_id, populate_existing=True)
        if receipt is None or receipt.operation_id is not None:
            raise _error(503, 'idempotency_uncertain', '下载提交状态未确定，请保留原请求标识')
        _finish_receipt(session, receipt, _now(session), error=rejected)
        rejected.headers = {'Idempotency-Status': 'complete'}
        return SubmissionDecision('error', error=rejected)
    return decision


def _locked_resolve(session, token):
    # Discover immutable identity without locks, then acquire the complete set.
    user_id = session.exec(select(DownloadOperation.user_id).where(DownloadOperation.id == token.operation_id)).first()
    if user_id is None:
        raise _error(409, 'resolve_lost', '处理归属已变化')
    lock_capacity_counters(session, _demands(user_id))
    lock_user(session, user_id)
    now = _now(session)
    _membership(session, user_id, now)
    receipt = session.exec(select(DownloadIdempotency).where(DownloadIdempotency.operation_id == token.operation_id)
        .with_for_update().execution_options(populate_existing=True)).first()
    op = session.exec(select(DownloadOperation).where(DownloadOperation.id == token.operation_id)
        .with_for_update().execution_options(populate_existing=True)).one()
    now = _now(session)
    if (type(token) is not ResolveToken or op.state != 'resolving' or op.resolve_owner != token.owner or
            op.resolve_epoch != token.epoch or op.resolve_lease_deadline is None or op.resolve_lease_deadline <= now):
        raise _error(409, 'resolve_lost', '处理归属已变化')
    return op, receipt, now


def _cas_checkpoint(session, op, token, envelope, now, **values):
    if callable(envelope):
        envelope = envelope()
    codec.encode_budget(envelope, resolve_attempts_used=len(envelope.direct_resolve_parent.children))
    previous = codec.decode_budget(op.budget_version, op.budget_checkpoint_json,
                                   resolve_attempts_used=op.resolve_attempts_used)
    elapsed = max(0., (now - op.budget_checkpoint_at).total_seconds())
    def progress(before, after):
        if (before.limits != after.limits or before.purpose != after.purpose or
                len(after.children) < len(before.children) or
                (before.blocked is not None and before.blocked != after.blocked) or
                any(getattr(after, key) < getattr(before, key) for key in ('requests', 'redirects', 'raw_bytes', 'decoded_bytes'))):
            raise _error(409, 'submission_changed', '处理预算已变化')
        for old, new in zip(before.children, after.children):
            progress(old, new)
    progress(previous.download_parent, envelope.download_parent)
    progress(previous.direct_resolve_parent, envelope.direct_resolve_parent)
    def tighten(before, after, parent_remaining):
        remaining = min(after.remaining_seconds, parent_remaining,
                        max(0., before.remaining_seconds - elapsed) if before else after.remaining_seconds)
        return replace(after, remaining_seconds=remaining, children=tuple(
            tighten(before.children[index] if before and index < len(before.children) else None, child, remaining)
            for index, child in enumerate(after.children)))
    envelope = codec.BudgetEnvelope(
        tighten(previous.download_parent, envelope.download_parent, max(0., (op.deadline_at - now).total_seconds())),
        tighten(previous.direct_resolve_parent, envelope.direct_resolve_parent, max(0., (op.resolve_deadline_at - now).total_seconds())))
    payload = codec.encode_budget(envelope, resolve_attempts_used=len(envelope.direct_resolve_parent.children))
    statement = update(DownloadOperation).where(DownloadOperation.id == token.operation_id,
        DownloadOperation.state == 'resolving', DownloadOperation.resolve_owner == token.owner,
        DownloadOperation.resolve_epoch == token.epoch, DownloadOperation.resolve_lease_deadline > func.clock_timestamp())
    if values.get('state') == 'direct_ready':
        statement = statement.where(DownloadOperation.resolve_attempt_deadline > func.clock_timestamp(),
            DownloadOperation.resolve_deadline_at > func.clock_timestamp(),
            DownloadOperation.deadline_at > func.clock_timestamp())
    changed = session.exec(statement
        .values(budget_checkpoint_json=payload, budget_checkpoint_at=now,
                resolve_attempts_used=len(envelope.direct_resolve_parent.children), **values)
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise _error(409, 'resolve_lost', '处理归属已变化')
    session.refresh(op)


def begin_resolve(session, token):
    op, _, now = _locked_resolve(session, token)
    download, direct = codec.restore_budget(op.budget_version, op.budget_checkpoint_json,
        checkpoint_at=op.budget_checkpoint_at, db_now=now, deadline_at=op.deadline_at,
        resolve_deadline_at=op.resolve_deadline_at, resolve_attempts_used=op.resolve_attempts_used)
    child = direct.child(BudgetProfile.resolve())
    envelope = codec.BudgetEnvelope(download.checkpoint(), direct.checkpoint())
    attempt_deadline = min(now + timedelta(seconds=BudgetProfile.resolve().seconds), op.resolve_deadline_at)
    _cas_checkpoint(session, op, token, envelope, now, resolve_attempt_deadline=attempt_deadline)
    return download, direct, child


_EPOCH = re.compile(r'[0-9]{1,12}')


def _validate_direct(response):
    if type(response) is not DownloadResponse or response.mode != 'direct' or not response.url or response.job_id is not None:
        raise _error(422, 'outbound_blocked', '来源地址不符合安全策略')
    validate_url(response.url, OutboundPurpose.MEDIA, initial=False)
    if any(type(key) is not str or key.lower() not in {'referer', 'user-agent', 'accept', 'accept-language'} or
           type(value) is not str or '\r' in value or '\n' in value for key, value in response.headers.items()):
        raise _error(422, 'outbound_blocked', '来源地址不符合安全策略')


def complete_direct(session, token, response, envelope, *, expires_at=None):
    _validate_direct(response)
    op, receipt, now = _locked_resolve(session, token)
    if (op.resolve_attempt_deadline is None or now >= op.resolve_attempt_deadline or now >= op.resolve_deadline_at):
        raise _error(409, 'resolve_lost', '处理归属已变化')
    deadline = now.timestamp() + settings.download_idempotency_direct_ttl_seconds
    # Common explicit provider expiry fields; ambiguous forms never extend TTL.
    query = parse_qs(urlsplit(response.url).query)
    candidates = [expires_at] if expires_at is not None else []
    for key in ('expires', 'expire', 'deadline'):
        # Source-controlled: only a plain bounded epoch counts (an oversized one cannot overflow).
        if key in query and len(query[key]) == 1 and _EPOCH.fullmatch(query[key][0]):
            candidates.append(int(query[key][0]))
    for candidate in candidates:
        if type(candidate) not in (int, float) or not math.isfinite(candidate):
            raise _error(422, 'outbound_blocked', '来源地址不符合安全策略')
        deadline = min(deadline, candidate)
    if deadline <= now.timestamp():
        raise _error(422, 'source_expired', '来源链接已失效，请重新解析')
    _cas_checkpoint(session, op, token, envelope, now, state='direct_ready', completed_at=now,
                    resolve_owner=None, resolve_lease_deadline=None, resolve_attempt_deadline=None)
    _finish_receipt(session, receipt, now, response=response, direct_expires_at=deadline)
    release_capacity(session, op.id, ('admission_slots',))
    return SubmissionDecision('direct', response=response)


def fallback_to_server(session, token, envelope):
    op, receipt, now = _locked_resolve(session, token)
    _cas_checkpoint(session, op, token, envelope, now)
    response = _queue(session, op, DownloadRequest.model_validate_json(op.canonical_payload))
    _finish_receipt(session, receipt, now, response=response)
    return SubmissionDecision('server', response=response)


def fail_resolve(session, token, envelope, error):
    op, receipt, now = _locked_resolve(session, token)
    _cas_checkpoint(session, op, token, envelope, now, state='failed', completed_at=now,
        resolve_owner=None, resolve_lease_deadline=None, resolve_attempt_deadline=None, error_code=error.detail['error_type'])
    _finish_receipt(session, receipt, now, error=error)
    release_capacity(session, op.id, ('admission_slots',))
    if receipt is not None:
        error.headers = {'Idempotency-Status': 'complete'}
    return SubmissionDecision('error', error=error)


def inspect_operation(session, operation_id, *, user_id, request, key, receipt_id=None, expected=None, snapshot=None):
    """Read-only unknown-COMMIT resolver: absence is never rollback evidence."""
    unknown = CommitResolution(ResolutionState.UNKNOWN)
    payload, fingerprint = canonical_request(request)
    receipt = session.get(DownloadIdempotency, receipt_id) if receipt_id else None
    if receipt is None and key is not None:
        receipt = session.exec(select(DownloadIdempotency).where(DownloadIdempotency.user_id == user_id,
            DownloadIdempotency.key == key)).first()
    if key is not None and (receipt is None or receipt.user_id != user_id or receipt.key != key or receipt.fingerprint != fingerprint):
        return unknown
    op = session.get(DownloadOperation, operation_id)
    if op is None:
        if receipt is not None and expected is not None and 'existing_receipt' in expected:
            observed = expected['existing_receipt']
            if all(getattr(receipt, name) == value for name, value in observed.items()):
                return CommitResolution(ResolutionState.COMMITTED,
                    _replay(session, receipt, fingerprint, _now(session), lock_job=False))
        # Deterministic pre-accept rejection has a receipt but no operation or
        # charge/reservation/Job. Never interpret absence as rollback.
        if (receipt is not None and receipt.operation_id is None and receipt.state == 'complete' and
                receipt.status_code in (429, 503) and session.get(QuotaCharge, operation_id) is None and
                not session.exec(select(ResourceReservation).where(ResourceReservation.operation_id == operation_id)).first()):
            return CommitResolution(ResolutionState.COMMITTED, _replay(session, receipt, fingerprint, _now(session), lock_job=False))
        return unknown
    if (op.user_id != user_id or op.fingerprint != fingerprint or op.canonical_payload != payload or
            op.resolve_attempts_limit != BudgetProfile.direct_parent().children):
        return unknown
    if snapshot is not None and (op.max_height != snapshot.max_height or
            op.membership_revision != snapshot.membership_revision or
            op.canonical_format_id != snapshot.canonical_format_id):
        return unknown
    if key is not None and receipt.operation_id != op.id:
        return unknown
    charge = session.get(QuotaCharge, op.id)
    quota = session.exec(select(Quota).where(Quota.user_id == user_id, Quota.date == op.quota_day.isoformat())).first()
    facts = session.exec(select(ResourceReservation).where(ResourceReservation.operation_id == op.id)).all()
    if (charge is None or charge.user_id != user_id or charge.quota_day != op.quota_day or charge.delta != 1 or
            quota is None or quota.downloads_used < 1 or op.quota_day != op.accepted_at.astimezone(timezone.utc).date() or
            {(fact.resource, fact.scope, fact.units) for fact in facts} !=
            {('admission_slots', 'global', 1), ('admission_slots', 'user:' + user_id, 1)}):
        return unknown
    try:
        codec.decode_budget(op.budget_version, op.budget_checkpoint_json, resolve_attempts_used=op.resolve_attempts_used)
    except ValueError:
        return unknown
    if op.state == 'resolving' and op.job_id is None and op.capacity_reserved and all(not fact.released for fact in facts):
        if op.resolve_owner is None or (receipt is not None and receipt.state != 'pending'):
            return unknown
        return CommitResolution(ResolutionState.COMMITTED, SubmissionDecision('resolve', token=ResolveToken(op.id, op.resolve_owner, op.resolve_epoch)))
    if op.state == 'accepted_server' and op.job_id is not None and op.capacity_reserved and all(not fact.released for fact in facts):
        job = session.get(Job, op.job_id)
        access = session.get(DownloadAccess, op.job_id)
        if (job is None or access is None or access.max_height != op.max_height or job.user_id != user_id or
                job.url != request.url or job.format_id != request.format_id or op.job_id_tombstone != job.id):
            return unknown
        response = DownloadResponse(mode='server', job_id=job.id)
        if receipt is not None and (receipt.state != 'complete' or receipt.status_code != 200 or
                json.loads(receipt.response_json) != response.model_dump()):
            return unknown
        return CommitResolution(ResolutionState.COMMITTED, SubmissionDecision('server', response=response))
    if op.state in ('direct_ready', 'failed') and not op.capacity_reserved and all(fact.released for fact in facts):
        if receipt is None:
            # Only this HTTP invocation may recover its already held response;
            # a new no-key POST always creates another independent operation.
            if (expected is not None and op.completed_at is not None and
                    op.resolve_epoch == expected['epoch'] and op.state == expected['state'] and
                    op.completed_at == expected['completed_at'] and
                    op.budget_checkpoint_at == expected['checkpoint_at'] and
                    hashlib.sha256(op.budget_checkpoint_json.encode('utf8')).hexdigest() == expected['checkpoint_sha256'] and
                    ((op.state == 'direct_ready' and expected['decision'].response is not None and expected['decision'].response.mode == 'direct') or
                     (op.state == 'failed' and expected['decision'].error is not None and expected['decision'].error.detail['error_type'] == op.error_code))):
                return CommitResolution(ResolutionState.COMMITTED, expected['decision'])
            return unknown
        if receipt.state != 'complete':
            return unknown
        return CommitResolution(ResolutionState.COMMITTED, _replay(session, receipt, fingerprint, _now(session), lock_job=False))
    return unknown


class ResolveAccounting:
    """Synthetic/future resolver seam. Not an OutboundBudget or HTTPX adapter.

    Each synthetic GET and byte observation charges BOTH accounting trees.
    Actual transport integration and its atomic crash accounting require B5/C.
    """
    def __init__(self, download, direct, child):
        self.download, self.direct, self.child = download, direct, child

    def begin_get(self):
        return self.download.begin_request(), self.child.begin_request()

    def source_budgets(self) -> tuple[OutboundBudget, OutboundBudget]:
        """Borrow existing roots/attempt for a joint transport, without charge.

        That transport must not also call begin_get. Checkpoint only after all
        source I/O and responses have finished, with no concurrent accounting.
        """
        return self.download, self.child

    def checkpoint(self):
        return codec.BudgetEnvelope(self.download.checkpoint(), self.direct.checkpoint())


def submit_download(engine, user_id, request, key, snapshot, *, server_required=False,
                    trusted_resolver: Callable | None = None):
    """One stable operation per HTTP invocation; no in-process Job dispatch."""
    validate_key(key)
    try:
        validate_url(request.url, OutboundPurpose.SOURCE)
    except OutboundError as error:
        raise HTTPException(error.status_code, detail=error.public_detail()) from None
    operation_id, receipt_id, owner = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    expected = None
    resolver = lambda session, opid: inspect_operation(session, opid, user_id=user_id,
        request=request, key=key, receipt_id=receipt_id if key is not None else None, expected=expected, snapshot=snapshot)
    def accept(session):
        nonlocal expected
        outcome = accept_submission(session, user_id, request, key, snapshot,
            operation_id=operation_id, receipt_id=receipt_id, owner=owner, server_required=server_required,
            resolver_ready=trusted_resolver is not None)
        if key is not None:
            row = _receipt(session, user_id, key)
            if row is not None and row.id != receipt_id:
                expected = {'existing_receipt': {name: getattr(row, name) for name in
                    ('id', 'user_id', 'key', 'fingerprint', 'operation_id', 'state', 'status_code',
                     'response_json', 'expires_at', 'direct_expires_at')}}
        return outcome
    decision = run_local_transaction(engine, operation_id, accept, resolver)
    if decision.kind == 'resolve':
        token = decision.token
        # Starting a source attempt is itself a durable checkpoint. Unknown
        # checkpoint COMMIT never triggers a speculative external GET.
        unknown = lambda *_: CommitResolution(ResolutionState.UNKNOWN)
        download, direct, child = run_local_transaction(engine, operation_id,
            lambda session: begin_resolve(session, token), unknown)
        accounting = ResolveAccounting(download, direct, child)
        result, failure = None, None
        try:
            result = trusted_resolver(request, accounting)
            if type(result) is not DirectResult:
                raise TypeError('Invalid trusted resolver result')
            if result.response is not None:
                _validate_direct(result.response)
        except (OutboundError, ControlledHttpError) as error:
            status = getattr(error, 'source_status', None)
            failure = (_error(422, 'verification_required', '来源需要安全校验，请更新有效会话后重试')
                       if status in (401, 403, 412) else HTTPException(error.status_code, detail=error.public_detail()))
        except SessionError:
            failure = _error(422, 'verification_required', '来源需要安全校验，请更新有效会话后重试')
        except HTTPException as error:
            # No arbitrary callback detail is trusted as safe response text.
            failure = _error(422, 'verification_required' if error.status_code in (401, 403, 412) else 'outbound_blocked',
                             '来源访问已停止，请重新解析')
        except (TimeoutError, ConnectionError):
            result = DirectResult()
        except Exception:
            failure = _error(422, 'source_failed', '来源解析失败，请重新解析')
        envelope = accounting.checkpoint()
        frozen_at = time.monotonic()
        def current_envelope():
            from dataclasses import replace
            elapsed = max(0., time.monotonic() - frozen_at)
            def age(node):
                return replace(node, remaining_seconds=max(0., node.remaining_seconds - elapsed),
                               children=tuple(age(child) for child in node.children))
            return codec.BudgetEnvelope(age(envelope.download_parent), age(envelope.direct_resolve_parent))
        if failure is not None:
            complete_action = lambda session: fail_resolve(session, token, current_envelope, failure)
        elif result.response is None:
            complete_action = lambda session: fallback_to_server(session, token, current_envelope)
        else:
            complete_action = lambda session: complete_direct(session, token, result.response, current_envelope, expires_at=result.expires_at)
        def action(session):
            nonlocal expected
            outcome = None
            safe_failure = None
            try:
                outcome = complete_action(session)
            except HTTPException as error:
                # Deterministic expiry validation happened before any terminal
                # write. Complete the same accepted operation as a safe error.
                if error.status_code == 422 and error.detail.get('error_type') == 'source_expired':
                    safe_failure = _error(422, 'source_expired', '来源链接已失效，请重新解析')
                else:
                    raise
            if safe_failure is not None:
                outcome = fail_resolve(session, token, current_envelope, safe_failure)
            session.flush()
            saved = session.get(DownloadOperation, operation_id, populate_existing=True)
            expected = {'decision': outcome, 'epoch': token.epoch, 'state': saved.state,
                        'completed_at': saved.completed_at, 'checkpoint_at': saved.budget_checkpoint_at,
                        'checkpoint_sha256': hashlib.sha256(saved.budget_checkpoint_json.encode('utf8')).hexdigest()}
            return outcome
        decision = run_local_transaction(engine, operation_id, action, resolver)
    if decision.error is not None:
        raise decision.error
    return decision.response
