"""C6a recovery: adopt a sealed candidate whose publish never reached the database (A contract §6).

A worker whose publish outcome stayed unknown, or whose lease merely expired after sealing,
leaves its sealed attempt (media renamed, manifest persisted). Before the lease is fenced
for a retry, this round reads such a candidate back and verifies it outside any transaction
(manifest identity, size, SHA256, format), then in one short transaction either publishes
it (same writes as a publish) or sends the Job to needs_review: never more than one
candidate is picked automatically, and nothing is downloaded, moved or deleted here. An
attempt without a sealed candidate is left to the normal retry (recover_expired). A
missing root stops the round. Logs carry fixed codes only.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from ..config import settings
from ..models import Job
from ..models_execution import JobAttempt
from . import artifact_store
from .artifact_publish import adopt_candidate, review_candidate

BATCH_LIMIT = 10  # each candidate is hashed in full: keep a round short (the rest wait, unfenced)
_TRANSIENT = frozenset({'artifact_io_failed'})
_log = logging.getLogger(__name__)


def adopt_expired(engine, media_root: Path, *, limit: int = BATCH_LIMIT) -> dict:
    """One recovery round; counts plus 'fenceable': the Job ids examined and found without a sealed
    candidate, the only expired leases the caller may fence (recover_expired lease_fence)."""
    counts = dict(adopted=0, needs_review=0, storage_unavailable=0, fenceable=[])
    try:
        artifact_store.check_root(media_root)
    except artifact_store.ArtifactError:
        _log.error('recovery stopped: artifact_root_unavailable')
        counts['storage_unavailable'] = 1
        return counts
    with Session(engine) as session:
        expired = session.exec(
            select(Job.id, Job.epoch, JobAttempt.id)
            .join(JobAttempt, (JobAttempt.job_id == Job.id) & (JobAttempt.epoch == Job.epoch)
                  & (JobAttempt.state == 'running'))
            .where(Job.execution_version == 2, Job.internal_state == 'running', Job.lease_deadline <= func.now(),
                   Job.run_deadline_at > func.now())
            .order_by(Job.lease_deadline).limit(limit)).all()
        session.commit()
    for job_id, epoch, attempt_id in expired:
        code = None
        try:
            sealed = artifact_store.sealed_attempts(media_root, job_id)
            if f'{epoch}-{attempt_id}' not in sealed:
                counts['fenceable'].append(job_id)  # nothing sealed by this attempt: the normal retry
                continue
            candidate = artifact_store.read_sealed(media_root, job_id, epoch, attempt_id,
                                                   max_bytes=settings.max_file_size)
            if candidate is None:  # the manifest vanished after the listing: nothing is sealed
                counts['fenceable'].append(job_id)
                continue
            # The source byte budget needs no check here: report_bytes never records more than it
            # allows, and a worker over budget never seals.
            if len(sealed) > 1:
                code = 'recovery_multiple_candidates'  # never pick one automatically
        except artifact_store.ArtifactError as error:
            reason = str(error)
            if reason == 'artifact_root_unavailable':
                _log.error('recovery stopped: artifact_root_unavailable')
                counts['storage_unavailable'] = 1
                break  # Jobs already examined stay fenceable; the rest wait for the storage
            if reason in _TRANSIENT:
                _log.warning('recovery skipped job=%s code=%s', job_id, reason)
                continue  # not fenced: examined again next round (its run window still bounds it)
            # Nothing deletes an unfenced attempt's files, so a missing media file is damage too.
            code = 'recovery_candidate_invalid'
        except Exception as error:  # never let one damaged candidate stop the worker's maintenance
            _log.warning('recovery skipped job=%s code=unexpected_%s', job_id, type(error).__name__)
            continue
        with Session(engine) as session:
            if code is None:
                done = adopt_candidate(session, candidate,
                                       absolute_path=str(media_root / candidate.relative_path)) is not None
            else:
                done = review_candidate(session, job_id, epoch, attempt_id, code)
            session.commit()
        if done:
            counts['adopted' if code is None else 'needs_review'] += 1
            if code is not None:
                _log.warning('recovery sent job=%s to review: code=%s', job_id, code)
    return counts
