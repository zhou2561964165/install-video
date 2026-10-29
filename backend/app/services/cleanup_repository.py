"""C5a cleanup lifecycle for published media (PostgreSQL; A contract §7 paragraph 3).

available -> expired -> deleting -> deleted. Pure database steps, each in the caller's
short transaction (callers commit), all on the database clock:

- mark_expired: available Jobs past expires_at become expired (the read path already
  answers 410 by expires_at; this is the state machine's entry point).
- claim_deletions: lock expired (or due, retrying) Jobs with SKIP LOCKED, skip any with a
  live read lease, move them to deleting and record a deletion intent owned by this
  cleaner (epoch + 1). The caller commits, and only then deletes files.
- confirm_deleted / record_failure: CAS on the intent's owner + epoch. Success marks the
  Job deleted and clears its file reference; failure backs off 30/120/600/1800 s and
  the fifth failure leaves the intent needs_review. A Job never returns to available.

Lock order: Job (FOR UPDATE SKIP LOCKED) before its intent; readers hold the Job FOR
SHARE while deciding, so a Job being read is skipped this round instead of waited on.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import re

from sqlalchemy import and_, case, exists, func, insert, literal_column, or_, select, update

from ..config import settings
from ..models import Job
from ..models_execution import ArtifactManifest, CleanupIntent, FileReadLease

BATCH_LIMIT = 50
BACKOFF_SECONDS = (30, 120, 600, 1800)
MAX_FAILURES = 5
_OWNER = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_CODE = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')


@dataclass(frozen=True, slots=True)
class DeletionClaim:
    job_id: str
    attempt_id: str
    relative_path: str
    owner: str
    epoch: int


def _limit(limit):
    if type(limit) is not int or not 1 <= limit <= BATCH_LIMIT:
        raise ValueError('limit_invalid')
    return limit


def mark_expired(session, *, limit: int = BATCH_LIMIT) -> list[str]:
    jobs = session.execute(
        select(Job.id).where(Job.execution_version == 2, Job.media_state == 'available',
                             Job.expires_at <= func.now())
        .order_by(Job.expires_at).limit(_limit(limit)).with_for_update(skip_locked=True)).scalars().all()
    if jobs:
        session.execute(update(Job).where(Job.id.in_(jobs), Job.media_state == 'available')
                        .values(media_state='expired', updated_at=func.now()))
    return list(jobs)


def _live_read(job_id_column):
    return exists().where(FileReadLease.job_id == job_id_column, FileReadLease.ended_at.is_(None),
                          FileReadLease.lease_deadline > func.now())


def claim_deletions(session, owner: str, *, limit: int = BATCH_LIMIT) -> list[DeletionClaim]:
    if type(owner) is not str or not _OWNER.match(owner):
        raise ValueError('cleanup_owner_invalid')
    any_intent = exists().where(CleanupIntent.job_id == Job.id)
    finished_intent = exists().where(CleanupIntent.job_id == Job.id, CleanupIntent.state != 'pending')
    due_retry = exists().where(CleanupIntent.job_id == Job.id, CleanupIntent.state == 'pending',
                               CleanupIntent.next_run_at <= func.now())
    has_manifest = exists().where(ArtifactManifest.attempt_id == Job.visible_attempt_id,
                                  ArtifactManifest.job_id == Job.id)
    candidates = session.execute(
        select(Job.id, Job.visible_attempt_id)
        .where(Job.execution_version == 2, Job.visible_attempt_id.is_not(None), has_manifest,
               # Finished/needs_review intents and broken rows never take a batch slot (no starvation);
               # a deleting Job whose intent vanished (manual edit, partial restore) is picked up again.
               or_(and_(Job.media_state == 'expired', ~finished_intent),
                   and_(Job.media_state == 'deleting', or_(due_retry, ~any_intent))),
               ~_live_read(Job.id))
        .order_by(Job.expires_at).limit(_limit(limit)).with_for_update(of=Job, skip_locked=True)).all()
    claims = []
    for job_id, attempt_id in candidates:
        relative_path = session.execute(select(ArtifactManifest.relative_path)
                                        .where(ArtifactManifest.attempt_id == attempt_id,
                                               ArtifactManifest.job_id == job_id)).scalar_one_or_none()
        if relative_path is None:
            continue
        intent = session.execute(select(CleanupIntent).where(CleanupIntent.job_id == job_id)
                                 .with_for_update()).scalar_one_or_none()
        claim_until = func.now() + timedelta(seconds=settings.cleanup_claim_seconds)
        if intent is None:
            session.execute(insert(CleanupIntent).values(
                job_id=job_id, attempt_id=attempt_id, relative_path=relative_path, owner=owner, epoch=1,
                state='pending', attempts=0, next_run_at=claim_until, created_at=func.now(), updated_at=func.now()))
            epoch = 1
        elif intent.state == 'pending':
            # Re-check due-ness on the locked row: the scan's correlated subquery saw an older
            # snapshot, and another cleaner may have just re-claimed this intent (no double claim).
            epoch = session.execute(
                update(CleanupIntent).where(CleanupIntent.job_id == job_id, CleanupIntent.state == 'pending',
                                            CleanupIntent.next_run_at <= func.now())
                .values(owner=owner, epoch=CleanupIntent.epoch + 1, next_run_at=claim_until, updated_at=func.now())
                .returning(CleanupIntent.epoch)).scalar_one_or_none()
            if epoch is None:
                continue
        else:
            continue  # done or needs_review: never claimed again automatically
        session.execute(update(Job).where(Job.id == job_id)
                        .values(media_state='deleting', updated_at=func.now()))
        claims.append(DeletionClaim(job_id, attempt_id, relative_path, owner, epoch))
    return claims


def _held(claim: DeletionClaim):
    if type(claim) is not DeletionClaim:
        raise ValueError('deletion_claim_invalid')
    return and_(CleanupIntent.job_id == claim.job_id, CleanupIntent.owner == claim.owner,
                CleanupIntent.epoch == claim.epoch, CleanupIntent.state == 'pending')


def confirm_deleted(session, claim: DeletionClaim) -> bool:
    """The files are gone (deleted now or already absent): Job deleted, intent done. False if not ours."""
    condition = _held(claim)
    locked = session.execute(select(Job.id).where(Job.id == claim.job_id, Job.media_state == 'deleting')
                             .with_for_update()).scalar_one_or_none()
    if locked is None or session.execute(select(CleanupIntent.job_id).where(condition)
                                         .with_for_update()).scalar_one_or_none() is None:
        return False
    session.execute(update(Job).where(Job.id == claim.job_id)
                    .values(media_state='deleted', file_path=None, updated_at=func.now()))
    session.execute(update(CleanupIntent).where(condition)
                    .values(state='done', owner=None, last_error=None, updated_at=func.now()))
    return True


def record_failure(session, claim: DeletionClaim, code: str, *, final: bool = False) -> str:
    """'retry' (backed off), 'needs_review' (fifth failure, or a final refusal that a retry cannot
    change, e.g. an unknown entry) or 'lost' (not our claim any more)."""
    if type(code) is not str or not _CODE.match(code):
        raise ValueError('error_code_invalid')
    condition = _held(claim)
    attempts = session.execute(select(CleanupIntent.attempts).where(condition).with_for_update()
                               ).scalar_one_or_none()
    if attempts is None:
        return 'lost'
    attempts += 1
    if attempts >= MAX_FAILURES or final:
        session.execute(update(CleanupIntent).where(condition).values(
            state='needs_review', attempts=attempts, owner=None, last_error=code, updated_at=func.now()))
        return 'needs_review'
    wait = timedelta(seconds=BACKOFF_SECONDS[attempts - 1])
    session.execute(update(CleanupIntent).where(condition).values(
        attempts=attempts, owner=None, last_error=code, next_run_at=func.now() + wait, updated_at=func.now()))
    return 'retry'



# C6c: expired imported v1 files (no attempt, no manifest, no read lease). media_state moves
# NULL -> deleting -> deleted; a refused object is quarantined as corrupt/mismatch.
@dataclass(frozen=True)
class LegacyClaim:
    job_id: str
    file_path: str


LEGACY_BACKOFF_SECONDS = (30, 120, 600, 1800)  # A contract §7: retry after 30/120/600/1800 s
LEGACY_MAX_ATTEMPTS = 5  # then a person reviews it (media_state 'corrupt' for a v1 Job)


def _legacy_due():
    """A failed deletion waits for its backoff before it is claimed again."""
    delay = case(*((Job.legacy_cleanup_attempts == index, seconds) for index, seconds in
                   enumerate(LEGACY_BACKOFF_SECONDS)), else_=LEGACY_BACKOFF_SECONDS[-1])
    return Job.updated_at <= func.now() - delay * literal_column("interval '1 second'")


def _legacy_expired():
    return and_(Job.execution_version == 1, Job.legacy_check == 'verified', Job.file_path.is_not(None),
                Job.expires_at <= func.now())


def claim_legacy_deletions(session, *, limit: int = BATCH_LIMIT) -> list[LegacyClaim]:
    """Lock expired verified v1 Jobs (SKIP LOCKED) and mark them deleting; callers commit at once."""
    rows = session.execute(
        select(Job.id, Job.file_path)
        .where(_legacy_expired(), or_(Job.media_state.is_(None),
                                      and_(Job.media_state == 'deleting', _legacy_due())))
        .order_by(Job.expires_at).limit(_limit(limit)).with_for_update(skip_locked=True)).all()
    claims = [LegacyClaim(job_id, file_path) for job_id, file_path in rows]
    if claims:
        session.execute(update(Job).where(Job.id.in_([claim.job_id for claim in claims]))
                        .values(media_state='deleting', updated_at=func.now()))
    return claims


def confirm_legacy_deleted(session, claim: LegacyClaim) -> bool:
    return session.execute(update(Job).where(Job.id == claim.job_id, Job.media_state == 'deleting')
                           .values(media_state='deleted', file_path=None, updated_at=func.now())).rowcount == 1


def record_legacy_failure(session, claim: LegacyClaim) -> str:
    """One more failed attempt: 'retry' (after the backoff) or 'review' after the last attempt."""
    attempts = session.execute(
        update(Job).where(Job.id == claim.job_id, Job.media_state == 'deleting')
        .values(legacy_cleanup_attempts=Job.legacy_cleanup_attempts + 1, updated_at=func.now())
        .returning(Job.legacy_cleanup_attempts)).scalar_one_or_none()
    if attempts is None:
        return 'lost'
    if attempts >= LEGACY_MAX_ATTEMPTS:
        session.execute(update(Job).where(Job.id == claim.job_id, Job.media_state == 'deleting')
                        .values(media_state='corrupt', updated_at=func.now()))
        return 'review'
    return 'retry'


def count_legacy_pending(session) -> int:
    """Expired verified v1 files still waiting for deletion (a reminder when no old root is set)."""
    return session.execute(select(func.count()).select_from(Job).where(
        _legacy_expired(), or_(Job.media_state.is_(None), Job.media_state == 'deleting'))).scalar_one()


def refuse_legacy(session, claim: LegacyClaim) -> bool:
    """A deterministic refusal (link, other names, outside the job directory): never retried."""
    return session.execute(update(Job).where(Job.id == claim.job_id, Job.media_state == 'deleting')
                           .values(media_state='corrupt', legacy_check='mismatch', updated_at=func.now())).rowcount == 1
