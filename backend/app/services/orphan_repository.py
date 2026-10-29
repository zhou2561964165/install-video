"""C5b-2 orphan inventory (database side; A contract §7 paragraph 4, last sentences).

Ownership is decided here, files are handled by artifact_store.
- An attempt directory `<job>/<epoch>-<attempt>` is owned while that exact attempt (job, epoch,
  id) is running, holds a live read lease, is its Job's visible attempt with media not yet
  deleted, or belongs to a Job in needs_review (kept for review, C6a).
- A job directory is owned while its Job is unfinished (it may still create an attempt) or any
  of its attempts is owned.
- Probe leftovers are never owned (the 24 h grace protects a probe in progress).
- Unknown objects and links are quarantined and never removed; so is a listed object that
  later turns into one.
Owned objects found again are released from the inventory. Inventory history (removed,
released) is purged after the retention period.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..config import settings
from ..models import Job
from ..models_execution import FileReadLease, JobAttempt, OrphanObject

ORPHAN_GRACE = timedelta(hours=24)
BATCH_LIMIT = 50
_UNFINISHED = ('queued', 'running', 'retry_wait', 'needs_review', 'legacy_hold')


def _attempt_owned_clause():
    live_read = exists().where(FileReadLease.attempt_id == JobAttempt.id, FileReadLease.ended_at.is_(None),
                               FileReadLease.lease_deadline > func.now())
    visible_media = exists().where(Job.id == JobAttempt.job_id, Job.visible_attempt_id == JobAttempt.id,
                                   Job.media_state.is_not(None), Job.media_state != 'deleted')
    # C6a: a Job in review keeps every attempt's files for the person examining it.
    in_review = exists().where(Job.id == JobAttempt.job_id, Job.internal_state == 'needs_review')
    return or_(JobAttempt.state == 'running', live_read, visible_media, in_review)


def is_owned(session, relative_path: str, kind: str) -> bool:
    if kind == 'attempt_dir':
        job_id, rest = relative_path.split('/', 1)
        epoch, attempt_id = rest.split('-', 1)
        return bool(session.execute(select(exists().where(
            JobAttempt.id == attempt_id, JobAttempt.job_id == job_id, JobAttempt.epoch == int(epoch),
            _attempt_owned_clause()))).scalar())
    if kind == 'job_dir':
        unfinished = exists().where(Job.id == relative_path, Job.internal_state.in_(_UNFINISHED))
        owned_attempt = exists().where(JobAttempt.job_id == relative_path, _attempt_owned_clause())
        return bool(session.execute(select(or_(unfinished, owned_attempt))).scalar())
    return False  # probe leftovers and unknown objects are never owned


def record_scan(session, entries) -> dict:
    """Upsert scanned entries into the inventory; returns counts. Callers commit (in chunks)."""
    counts = dict(scanned=0, listed=0, quarantined=0, quarantined_new=0, released=0)
    for entry in entries:
        counts['scanned'] += 1
        if entry.kind != 'unknown' and is_owned(session, entry.relative_path, entry.kind):
            released = session.execute(
                update(OrphanObject).where(OrphanObject.relative_path == entry.relative_path,
                                           OrphanObject.state == 'listed')
                .values(state='released', last_seen_at=func.now(), updated_at=func.now()))
            counts['released'] += released.rowcount
            continue
        kind, state = (entry.kind, 'listed') if entry.kind != 'unknown' else ('unknown', 'quarantined')
        # A concurrent scanner may insert the same row: never fail the round on it.
        inserted = session.execute(pg_insert(OrphanObject).values(
            relative_path=entry.relative_path, kind=kind, state=state, reason=entry.reason,
            first_seen_at=func.now(), last_seen_at=func.now(), updated_at=func.now())
            .on_conflict_do_nothing(index_elements=['relative_path'])
            .returning(OrphanObject.relative_path)).scalar()  # rowcount is -1 through the ORM session
        if inserted is None:
            current = session.execute(select(OrphanObject).where(OrphanObject.relative_path == entry.relative_path)
                                      .with_for_update()).scalar_one()
            if current.state in ('released', 'removed'):  # reappeared: the 24 h grace starts again
                session.execute(update(OrphanObject).where(OrphanObject.relative_path == entry.relative_path)
                                .values(kind=kind, state=state, reason=entry.reason, first_seen_at=func.now(),
                                        last_seen_at=func.now(), updated_at=func.now()))
            elif state == 'quarantined' and current.state != 'quarantined':
                # A listed object that turned into a link/unknown object: quarantine it now.
                session.execute(update(OrphanObject).where(OrphanObject.relative_path == entry.relative_path)
                                .values(kind=kind, state=state, reason=entry.reason, last_seen_at=func.now(),
                                        updated_at=func.now()))
            else:
                session.execute(update(OrphanObject).where(OrphanObject.relative_path == entry.relative_path)
                                .values(last_seen_at=func.now(), updated_at=func.now()))
                counts[state] += 1
                continue
        counts[state] += 1
        if state == 'quarantined':
            counts['quarantined_new'] += 1
    return counts


def due_for_removal(session, *, limit: int = BATCH_LIMIT) -> list[OrphanObject]:
    if type(limit) is not int or not 1 <= limit <= BATCH_LIMIT:
        raise ValueError('limit_invalid')
    return session.execute(
        select(OrphanObject).where(OrphanObject.state == 'listed',
                                   OrphanObject.first_seen_at <= func.now() - ORPHAN_GRACE)
        .order_by(OrphanObject.first_seen_at).limit(limit).with_for_update(skip_locked=True)).scalars().all()


def mark(session, relative_path: str, state: str, reason: str | None = None) -> None:
    session.execute(update(OrphanObject).where(OrphanObject.relative_path == relative_path,
                                               OrphanObject.state == 'listed')
                    .values(state=state, reason=reason, updated_at=func.now()))


def purge_history(session) -> int:
    """Delete removed/released rows older than the retention period (they would keep purged ids)."""
    cutoff = func.now() - timedelta(days=settings.job_metadata_retention_days)
    return session.execute(delete(OrphanObject).where(OrphanObject.state.in_(('removed', 'released')),
                                                      OrphanObject.updated_at < cutoff)).rowcount
