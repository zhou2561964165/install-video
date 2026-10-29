"""C5b-1 retention: delete durable Job metadata after the retention period (A contract §7 paragraph 4).

Eligible: v2 Jobs created more than job_metadata_retention_days ago, finished (succeeded or
failed), whose media never existed or is deleted, with no live read lease, no unfinished
cleanup intent, no active operation, no unexpired idempotency receipt and an operation
tombstone that (if set) names this Job. deleting, needs_review and legacy (v1) Jobs are never
touched. A Job whose tombstone names another Job is never rewritten: it is reported
(stats['mismatched']) for review.

One service controls the order (foreign keys stay RESTRICT, nothing cascades): read leases,
cleanup intents, manifests, DownloadAccess, then the operation's nullable Job reference is
cleared while its job_id tombstone keeps the original id, then the Job's visible attempt
reference (Job <-> JobAttempt is a cycle), the attempts and finally the Job. Charges,
reservations, receipts and payments are never deleted.

Each Job runs in its own savepoint inside the caller's short transaction: a database error on
one Job (e.g. a lock timeout) rolls back only that Job, is counted (stats['failed']) and the
batch continues; the Job stays intact for a later run. A lost connection still propagates.

Lock order (documented invariant): retention locks the Job (FOR UPDATE SKIP LOCKED) and then
its operation, while job_repository updates an operation before its Job. They never meet:
retention only touches terminal Jobs whose operation has already ended, and job_repository
only updates operations still in accepted_server.
"""
from __future__ import annotations

from datetime import timedelta
import logging

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.exc import DBAPIError

from ..config import settings
from ..models import DownloadAccess, DownloadIdempotency, Job
from ..models_execution import ArtifactManifest, CleanupIntent, FileReadLease, JobAttempt
from ..models_operations import DownloadOperation

BATCH_LIMIT = 50
_ACTIVE_OPERATION_STATES = ('resolving', 'accepted_server')
_log = logging.getLogger(__name__)


def _tombstone_mismatch():
    return exists().where(DownloadOperation.job_id == Job.id, DownloadOperation.job_id_tombstone.is_not(None),
                          DownloadOperation.job_id_tombstone != Job.id)


def _eligible(now):
    live_read = exists().where(FileReadLease.job_id == Job.id, FileReadLease.ended_at.is_(None),
                               FileReadLease.lease_deadline > now)
    open_intent = exists().where(CleanupIntent.job_id == Job.id, CleanupIntent.state != 'done')
    active_operation = exists().where(DownloadOperation.job_id == Job.id,
                                      DownloadOperation.state.in_(_ACTIVE_OPERATION_STATES))
    live_receipt = exists().where(DownloadOperation.job_id == Job.id,
                                  DownloadIdempotency.operation_id == DownloadOperation.id,
                                  or_(DownloadIdempotency.expires_at.is_(None),
                                      DownloadIdempotency.expires_at > func.extract('epoch', now)))
    return (Job.execution_version == 2, Job.internal_state.in_(('succeeded', 'failed')),
            or_(Job.media_state.is_(None), Job.media_state == 'deleted'),
            Job.created_at <= now - timedelta(days=settings.job_metadata_retention_days),
            ~live_read, ~open_intent, ~active_operation, ~live_receipt)


def _purge_one(session, job_id: str) -> None:
    session.execute(delete(FileReadLease).where(FileReadLease.job_id == job_id))
    session.execute(delete(CleanupIntent).where(CleanupIntent.job_id == job_id))
    session.execute(delete(ArtifactManifest).where(ArtifactManifest.job_id == job_id))
    session.execute(delete(DownloadAccess).where(DownloadAccess.job_id == job_id))
    session.execute(update(DownloadOperation).where(DownloadOperation.job_id == job_id)
                    .values(job_id_tombstone=job_id, job_id=None))
    session.execute(update(Job).where(Job.id == job_id).values(visible_attempt_id=None))
    session.execute(delete(JobAttempt).where(JobAttempt.job_id == job_id))
    session.execute(delete(Job).where(Job.id == job_id))


def purge_expired_metadata(session, *, limit: int = BATCH_LIMIT, stats: dict | None = None) -> list[str]:
    """Purge up to `limit` eligible Jobs; returns their ids. `stats` (optional) receives
    'failed' (Jobs rolled back by a database error) and 'mismatched' (tombstone conflicts)."""
    if type(limit) is not int or not 1 <= limit <= BATCH_LIMIT:
        raise ValueError('limit_invalid')
    stats = {} if stats is None else stats
    now = func.now()
    eligible = _eligible(now)
    stats['mismatched'] = session.execute(select(func.count()).select_from(Job)
                                          .where(*eligible, _tombstone_mismatch())).scalar_one()
    if stats['mismatched']:
        _log.warning('retention skipped jobs: retention_tombstone_mismatch count=%s', stats['mismatched'])
    jobs = session.execute(select(Job.id).where(*eligible, ~_tombstone_mismatch()).order_by(Job.created_at)
                           .limit(limit).with_for_update(of=Job, skip_locked=True)).scalars().all()
    purged, stats['failed'] = [], 0
    for job_id in jobs:
        try:
            with session.begin_nested():
                _purge_one(session, job_id)
        except DBAPIError as error:
            if error.connection_invalidated:
                raise
            stats['failed'] += 1
            _log.warning('retention_job_failed job=%s sqlstate=%s', job_id, getattr(error.orig, 'sqlstate', None))
            continue
        purged.append(job_id)
    return purged
