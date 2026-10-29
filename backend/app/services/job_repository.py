"""C1 durable-execution lease repository (PostgreSQL coordination source of truth).

Pure database operations: callers own short transactions and commit; nothing
here performs external I/O. Every comparison uses the database clock (now()).
After a claim, every state change is a CAS on job_id + lease_owner + epoch +
internal_state='running' + lease_deadline > now() + run_deadline_at > now();
rowcount != 1 means the lease was lost and nothing is written. Legacy
(execution_version=1) Jobs are never leased.

Lock order (A contract §5): resources -> operation -> Job -> attempt. Terminal
outcomes (failed/needs_review) release the operation's admission slots and end
the operation in the same transaction, so B2's release_capacity (counters ->
operation -> reservations) runs before the Job row is locked. Each terminal
step runs in a savepoint: if the Job CAS then fails, the release is undone too.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
import random
import re
import uuid

from sqlalchemy import and_, func, insert, or_, select, update

from ..config import settings
from ..models import Job, JobStatus
from ..models_execution import JobAttempt
from ..models_operations import DownloadOperation
from .resource_capacity import release_capacity

HEARTBEAT_SECONDS = 10
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
SOURCE_BUDGET_FACTOR = 3  # A contract §6: cross-attempt source bytes <= 3 * max_file_size
RUN_WINDOW = timedelta(minutes=30)  # equals BudgetProfile.download_parent().seconds and B4's deadline_at
BACKOFF_SECONDS = (10, 60)
JITTER = 0.2
# Only network-class failures retry; session/permission changes need a person.
RETRYABLE = frozenset({'network', 'http_408', 'http_429', 'http_5xx'})
NEEDS_REVIEW = frozenset({'session_expired', 'permission_changed'})
_OWNER = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_CODE = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')
_LEASE = timedelta(seconds=LEASE_SECONDS)


@dataclass(frozen=True, slots=True)
class LeaseToken:
    job_id: str
    attempt_id: str
    owner: str = field(repr=False)
    epoch: int
    run_deadline_at: datetime | None = None  # absolute window end, for C3's execution budget
    source_bytes_used: int = 0  # Job's cross-attempt source bytes at claim time (C3 budget)


class _Lost(Exception):
    """Internal: unwind a savepoint when the lease or the expected row state is gone."""


def _token(token):
    if type(token) is not LeaseToken:
        raise ValueError('lease_token_invalid')
    return token


def _held(token):
    return and_(Job.id == token.job_id, Job.lease_owner == token.owner, Job.epoch == token.epoch,
                Job.internal_state == 'running', Job.lease_deadline > func.now(), Job.run_deadline_at > func.now())


def _lease_until():
    return func.least(func.now() + _LEASE, Job.run_deadline_at)


def _jitter():
    return random.uniform(0.0, JITTER)


def _operation_id(session, job_id):
    return session.execute(select(DownloadOperation.id).where(DownloadOperation.job_id == job_id)).scalar_one_or_none()


def _release_and_end_operation(session, operation_id, state, code):
    """Resources then operation: release admission slots and end the operation (idempotent)."""
    if operation_id is None:
        return
    release_capacity(session, operation_id, ('admission_slots',))
    session.execute(update(DownloadOperation)
                    .where(DownloadOperation.id == operation_id, DownloadOperation.state == 'accepted_server')
                    .values(state=state, completed_at=func.now(), error_code=code))


def _end_attempt(session, job_id, epoch, state, code, *, attempt_id=None):
    conditions = [JobAttempt.job_id == job_id, JobAttempt.epoch == epoch, JobAttempt.state == 'running']
    if attempt_id is not None:
        conditions.append(JobAttempt.id == attempt_id)
    result = session.execute(update(JobAttempt).where(*conditions)
                             .values(state=state, ended_at=func.now(), error_code=code))
    if result.rowcount != 1:
        raise _Lost()


def claim_next(session, owner: str) -> LeaseToken | None:
    """Lease one runnable v2 Job (SKIP LOCKED, earliest deadline first) and open its running attempt."""
    if type(owner) is not str or not _OWNER.match(owner):
        raise ValueError('lease_owner_invalid')
    runnable = (select(Job.id)
                .join(DownloadOperation, DownloadOperation.job_id == Job.id)
                .where(Job.execution_version == 2,
                       or_(Job.internal_state == 'queued',
                           and_(Job.internal_state == 'retry_wait', Job.next_run_at <= func.now())),
                       DownloadOperation.state == 'accepted_server',
                       Job.run_deadline_at > func.now(),
                       Job.attempts_used < Job.attempts_limit)
                .order_by(Job.run_deadline_at, Job.created_at)
                .limit(1)
                .with_for_update(of=Job, skip_locked=True))
    job_id = session.execute(runnable).scalar_one_or_none()
    if job_id is None:
        return None
    claimed = session.execute(
        update(Job).where(Job.id == job_id)
        .values(epoch=Job.epoch + 1, lease_owner=owner, lease_deadline=_lease_until(),
                internal_state='running', status=JobStatus.downloading, progress=0.0,
                attempts_used=Job.attempts_used + 1, next_run_at=None, updated_at=func.now())
        .returning(Job.epoch, Job.attempts_used, Job.run_deadline_at, Job.source_bytes_used)).one()
    attempt_id = str(uuid.uuid4())
    session.execute(insert(JobAttempt).values(
        id=attempt_id, job_id=job_id, epoch=claimed.epoch, owner=owner,
        attempt_index=claimed.attempts_used, state='running', started_at=func.now()))
    return LeaseToken(job_id, attempt_id, owner, claimed.epoch, claimed.run_deadline_at, claimed.source_bytes_used)


def report_bytes(session, token: LeaseToken, attempt_bytes: int) -> str:
    """Record this attempt's cumulative source bytes; returns 'ok', 'over_budget' or 'lost'.

    attempt_bytes is monotonic per attempt: only max(0, attempt_bytes - recorded) is added,
    to the attempt and to the Job's cross-attempt total, which a retry never resets. A total
    above SOURCE_BUDGET_FACTOR * max_file_size writes nothing and returns 'over_budget'.
    Lock order Job -> attempt (A contract §5); runs in a savepoint, callers commit.
    """
    token = _token(token)
    if type(attempt_bytes) is not int or attempt_bytes < 0:
        raise ValueError('attempt_bytes_invalid')
    with session.begin_nested():
        total = session.execute(select(Job.source_bytes_used).where(_held(token)).with_for_update()
                                ).scalar_one_or_none()
        if total is None:
            return 'lost'
        recorded = session.execute(
            select(JobAttempt.bytes_used)
            .where(JobAttempt.id == token.attempt_id, JobAttempt.job_id == token.job_id,
                   JobAttempt.epoch == token.epoch, JobAttempt.state == 'running')
            .with_for_update()).scalar_one_or_none()
        if recorded is None:
            return 'lost'
        delta = max(0, attempt_bytes - recorded)
        if delta == 0:
            return 'ok'
        if total + delta > SOURCE_BUDGET_FACTOR * settings.max_file_size:
            return 'over_budget'
        session.execute(update(Job).where(Job.id == token.job_id)
                        .values(source_bytes_used=Job.source_bytes_used + delta))
        session.execute(update(JobAttempt).where(JobAttempt.id == token.attempt_id)
                        .values(bytes_used=JobAttempt.bytes_used + delta))
    return 'ok'


def heartbeat(session, token: LeaseToken) -> bool:
    token = _token(token)
    result = session.execute(update(Job).where(_held(token)).values(lease_deadline=_lease_until()))
    return result.rowcount == 1


def report_progress(session, token: LeaseToken, progress: float) -> bool:
    token = _token(token)
    if type(progress) not in (int, float) or not math.isfinite(progress) or not 0 <= progress <= 100:
        raise ValueError('progress_invalid')
    result = session.execute(update(Job).where(_held(token)).values(progress=float(progress), updated_at=func.now()))
    return result.rowcount == 1


def _decide(error_code, used, limit, run_deadline, now, jitter):
    if error_code in RETRYABLE and used < limit:
        spread = jitter()
        if type(spread) not in (int, float) or not 0 <= spread <= JITTER:
            raise ValueError('jitter_invalid')
        candidate = now + timedelta(seconds=BACKOFF_SECONDS[min(used, len(BACKOFF_SECONDS)) - 1] * (1 + spread))
        if candidate < run_deadline:
            return 'retry_wait', candidate
    return ('needs_review' if error_code in NEEDS_REVIEW else 'failed'), None


def fail_attempt(session, token: LeaseToken, error_code: str, *, jitter=_jitter) -> str:
    """End the attempt; returns 'retry_wait' | 'failed' | 'needs_review', or 'lost' without writing."""
    token = _token(token)
    if type(error_code) is not str or not _CODE.match(error_code):
        raise ValueError('error_code_invalid')
    seen = session.execute(select(Job.attempts_used, Job.attempts_limit, Job.run_deadline_at, func.now())
                           .where(_held(token))).one_or_none()
    if seen is None:
        return 'lost'
    state, next_run = _decide(error_code, *seen, jitter)
    try:
        with session.begin_nested():
            if state != 'retry_wait':
                _release_and_end_operation(session, _operation_id(session, token.job_id), state, error_code)
            locked = session.execute(select(Job.attempts_used, Job.attempts_limit, Job.run_deadline_at)
                                     .where(_held(token)).with_for_update()).one_or_none()
            if locked is None or tuple(locked) != tuple(seen[:3]):
                raise _Lost()
            values = dict(internal_state=state, lease_owner=None, lease_deadline=None, next_run_at=next_run,
                          status=JobStatus.queued if state == 'retry_wait' else JobStatus.error, updated_at=func.now())
            if state != 'retry_wait':
                values['error_type'] = error_code
            if session.execute(update(Job).where(_held(token)).values(**values)).rowcount != 1:
                raise _Lost()
            _end_attempt(session, token.job_id, token.epoch, 'failed', error_code, attempt_id=token.attempt_id)
    except _Lost:
        return 'lost'
    return state


def recover_expired(session, *, limit: int = 50, lease_fence=None) -> list[str]:
    """Fence expired leases or windows: bump epoch, mark the attempt lost, then retry or end in budget.

    lease_fence (C6a): when given, an expired lease is fenced only for these Job ids (those the
    recovery round examined and found without a sealed candidate); an expired window always is.
    """
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('limit_invalid')
    lease_gone = Job.lease_deadline <= func.now()
    if lease_fence is not None:
        lease_gone = and_(lease_gone, Job.id.in_(list(lease_fence)))
    candidates = session.execute(
        select(Job.id, Job.epoch, Job.attempts_used, Job.attempts_limit, Job.run_deadline_at, func.now())
        .where(Job.execution_version == 2, Job.internal_state == 'running',
               or_(lease_gone, Job.run_deadline_at <= func.now()))
        .order_by(Job.lease_deadline).limit(limit)).all()
    recovered = []
    for job_id, epoch, used, attempts_limit, run_deadline, now in candidates:
        window_gone = run_deadline <= now
        retry = used < attempts_limit and not window_gone
        code = None if retry else ('run_deadline_exceeded' if window_gone else 'run_budget_exhausted')
        try:
            with session.begin_nested():
                if not retry:
                    _release_and_end_operation(session, _operation_id(session, job_id), 'failed', code)
                locked = session.execute(
                    select(Job.id).where(Job.id == job_id, Job.epoch == epoch, Job.internal_state == 'running',
                                         or_(Job.lease_deadline <= func.now(), Job.run_deadline_at <= func.now()))
                    .with_for_update(skip_locked=True)).scalar_one_or_none()
                if locked is None:
                    raise _Lost()  # a live worker holds or just renewed it, or it changed state
                values = dict(epoch=Job.epoch + 1, lease_owner=None, lease_deadline=None, updated_at=func.now(),
                              internal_state='retry_wait' if retry else 'failed',
                              status=JobStatus.queued if retry else JobStatus.error,
                              next_run_at=func.now() if retry else None)
                if not retry:
                    values['error_type'] = code
                session.execute(update(Job).where(Job.id == job_id).values(**values))
                _end_attempt(session, job_id, epoch, 'lost', 'lease_expired')
        except _Lost:
            continue
        recovered.append(job_id)
    return recovered


def expire_window(session, *, limit: int = 50) -> list[str]:
    """Waiting v2 Jobs past their absolute run window become failed and return their slots."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('limit_invalid')
    candidates = session.execute(
        select(Job.id)
        .where(Job.execution_version == 2, Job.internal_state.in_(('queued', 'retry_wait')),
               Job.run_deadline_at <= func.now())
        .order_by(Job.run_deadline_at).limit(limit)).scalars().all()
    expired = []
    for job_id in candidates:
        try:
            with session.begin_nested():
                _release_and_end_operation(session, _operation_id(session, job_id), 'failed', 'run_deadline_exceeded')
                locked = session.execute(
                    select(Job.id).where(Job.id == job_id, Job.internal_state.in_(('queued', 'retry_wait')),
                                         Job.run_deadline_at <= func.now())
                    .with_for_update(skip_locked=True)).scalar_one_or_none()
                if locked is None:
                    raise _Lost()
                session.execute(update(Job).where(Job.id == job_id).values(
                    internal_state='failed', status=JobStatus.error, error_type='run_deadline_exceeded',
                    next_run_at=None, updated_at=func.now()))
        except _Lost:
            continue
        expired.append(job_id)
    return expired
