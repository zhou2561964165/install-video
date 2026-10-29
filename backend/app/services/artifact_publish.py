"""C2 lease-fenced publish of one attempt's sealed artifact (database only, no file I/O).

One savepoint, A contract §5 lock order: resources (B2 release_capacity: counters ->
operation -> reservations) -> operation -> Job (C1 lease CAS) -> attempt. The
manifest, Job succeeded/done with its single visible own attempt, operation
succeeded and slot release commit together. If the lease is gone nothing is
written (the savepoint also undoes the release) and LEASE_LOST is returned; the
attempt's files are then only an orphan for C6 to reconcile. A retry of this
attempt's own identical, already visible publish returns that PublishedArtifact
(idempotent success after a lost commit acknowledgement). Callers commit.

Both functions may leave a FOR SHARE lock on the Job (find_published): the caller
must commit or roll back immediately, before any file I/O or further locking, or
it blocks the Job's new owner and inverts the resources -> Job lock order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from sqlalchemy import and_, func, insert, select, update

from ..config import settings
from ..models import Job, JobStatus
from ..models_execution import ArtifactManifest
from .artifact_store import MEDIA_CHECKS, ArtifactCandidate
from .job_repository import (LeaseToken, _Lost, _end_attempt, _held, _operation_id,
                             _release_and_end_operation, _token)

_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_FORMAT = re.compile(r'[a-z0-9]{1,8}\Z')


@dataclass(frozen=True, slots=True)
class PublishedArtifact:
    job_id: str
    attempt_id: str
    relative_path: str
    byte_size: int
    sha256: str
    expires_at: datetime


class _LeaseLost:
    """Sentinel: the lease (or the absolute run window) was gone; nothing was written."""

    def __repr__(self):
        return 'LEASE_LOST'


LEASE_LOST = _LeaseLost()


def _validate(token: LeaseToken, candidate: ArtifactCandidate, absolute_path: str) -> None:
    if type(candidate) is not ArtifactCandidate:
        raise ValueError('candidate_invalid')
    if (candidate.job_id, candidate.epoch, candidate.attempt_id) != (token.job_id, token.epoch, token.attempt_id):
        raise ValueError('candidate_token_mismatch')
    if type(candidate.byte_size) is not int or not 0 < candidate.byte_size <= settings.max_file_size:
        raise ValueError('candidate_size_invalid')
    if type(candidate.sha256) is not str or not _HEX64.match(candidate.sha256):
        raise ValueError('candidate_hash_invalid')
    if candidate.media_check not in MEDIA_CHECKS or type(candidate.media_format) is not str or not _FORMAT.match(candidate.media_format):
        raise ValueError('candidate_media_invalid')
    expected = f'{token.job_id}/{token.epoch}-{token.attempt_id}/media.{candidate.media_format}'
    if candidate.relative_path != expected:
        raise ValueError('candidate_path_invalid')
    if type(absolute_path) is not str or not absolute_path:
        raise ValueError('candidate_path_invalid')


def publish_candidate(session, token: LeaseToken, candidate: ArtifactCandidate, *,
                      absolute_path: str) -> PublishedArtifact | _LeaseLost:
    token = _token(token)
    _validate(token, candidate, absolute_path)
    try:
        with session.begin_nested():
            expires_at = _write_publish(session, _held(token), candidate, absolute_path)
    except _Lost:
        # A retry after a lost commit acknowledgement finds its own identical publish: that is
        # success, so the caller never removes files the database already shows as available.
        existing = find_published(session, token.job_id, token.epoch, token.attempt_id)
        if existing is not None and (existing.relative_path, existing.byte_size, existing.sha256) == (
                candidate.relative_path, candidate.byte_size, candidate.sha256):
            return existing
        return LEASE_LOST
    return PublishedArtifact(candidate.job_id, candidate.attempt_id, candidate.relative_path,
                             candidate.byte_size, candidate.sha256, expires_at)


def _write_publish(session, guard, candidate: ArtifactCandidate, absolute_path: str) -> datetime:
    """The publish writes, in lock order, for the Job row matching guard; raises _Lost otherwise."""
    _release_and_end_operation(session, _operation_id(session, candidate.job_id), 'succeeded', None)
    if session.execute(select(Job.id).where(guard).with_for_update()).scalar_one_or_none() is None:
        raise _Lost()
    session.execute(insert(ArtifactManifest).values(
        attempt_id=candidate.attempt_id, job_id=candidate.job_id, epoch=candidate.epoch,
        relative_path=candidate.relative_path, byte_size=candidate.byte_size, sha256=candidate.sha256,
        media_format=candidate.media_format, media_check=candidate.media_check, created_at=func.now()))
    published = session.execute(
        update(Job).where(guard)
        .values(internal_state='succeeded', status=JobStatus.done, visible_attempt_id=candidate.attempt_id,
                media_state='available', file_size=candidate.byte_size, file_path=absolute_path,
                progress=100.0, completed_at=func.now(),
                expires_at=func.now() + timedelta(seconds=settings.ttl_seconds),
                lease_owner=None, lease_deadline=None, updated_at=func.now())
        .returning(Job.expires_at)).one_or_none()
    if published is None:
        raise _Lost()
    _end_attempt(session, candidate.job_id, candidate.epoch, 'succeeded', None, attempt_id=candidate.attempt_id)
    return published.expires_at


def _expired(job_id: str, epoch: int):
    """C6a guard: the Job is still running at this epoch, its lease has expired and its window has not."""
    return and_(Job.id == job_id, Job.epoch == epoch, Job.execution_version == 2, Job.internal_state == 'running',
                Job.lease_deadline <= func.now(), Job.run_deadline_at > func.now())


def adopt_candidate(session, candidate: ArtifactCandidate, *, absolute_path: str) -> PublishedArtifact | None:
    """C6a: publish a verified sealed candidate of an expired, unfenced lease (same writes as a publish).

    Returns None (nothing written) when the Job was fenced, renewed, finished or its window passed
    since the candidate was selected. Runs in a savepoint; callers commit.
    """
    token = LeaseToken(candidate.job_id, candidate.attempt_id, 'recovery', candidate.epoch)
    _validate(token, candidate, absolute_path)
    try:
        with session.begin_nested():
            expires_at = _write_publish(session, _expired(candidate.job_id, candidate.epoch), candidate, absolute_path)
    except _Lost:
        return None
    return PublishedArtifact(candidate.job_id, candidate.attempt_id, candidate.relative_path,
                             candidate.byte_size, candidate.sha256, expires_at)


def review_candidate(session, job_id: str, epoch: int, attempt_id: str, code: str) -> bool:
    """C6a: an expired, unfenced attempt whose candidate cannot be adopted goes to needs_review.

    The epoch is fenced, the attempt ends lost with code, the operation ends needs_review and its
    slot is released; files are kept for a person to examine. False when the Job changed meanwhile.
    """
    try:
        with session.begin_nested():
            _release_and_end_operation(session, _operation_id(session, job_id), 'needs_review', code)
            guard = _expired(job_id, epoch)
            if session.execute(select(Job.id).where(guard).with_for_update()).scalar_one_or_none() is None:
                raise _Lost()
            session.execute(update(Job).where(guard).values(
                internal_state='needs_review', status=JobStatus.error, error_type=code, epoch=Job.epoch + 1,
                lease_owner=None, lease_deadline=None, next_run_at=None, updated_at=func.now()))
            _end_attempt(session, job_id, epoch, 'lost', code, attempt_id=attempt_id)
    except _Lost:
        return False
    return True


def find_published(session, job_id: str, epoch: int, attempt_id: str) -> PublishedArtifact | None:
    """Resolve an unknown commit outcome by identity only; never re-download or re-publish.

    Run under READ COMMITTED. The FOR SHARE statement first waits for any transaction
    still holding the Job (an in-flight publish); the read is a separate statement so it
    takes a fresh snapshot that includes that commit (a single joined FOR SHARE query
    would re-check with its old snapshot and could still miss the new manifest row).
    """
    session.execute(select(Job.id).where(Job.id == job_id).with_for_update(read=True))
    row = session.execute(
        select(ArtifactManifest.job_id, ArtifactManifest.attempt_id, ArtifactManifest.relative_path,
               ArtifactManifest.byte_size, ArtifactManifest.sha256, Job.expires_at)
        .join(Job, Job.id == ArtifactManifest.job_id)
        .where(ArtifactManifest.job_id == job_id, ArtifactManifest.epoch == epoch,
               ArtifactManifest.attempt_id == attempt_id, Job.visible_attempt_id == attempt_id)).one_or_none()
    return None if row is None else PublishedArtifact(*row)
