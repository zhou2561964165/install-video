"""C4 read decisions and read leases for published media (PostgreSQL; A contract §7).

open_read decides, in one short transaction holding the Job FOR SHARE: ownership (404),
current height limit against the submission's DownloadAccess (403), expiry by the
database clock or a non-available lifecycle state (410, independent of any cleaner),
missing/corrupt/unpublished (404); then records a read lease, opens the file without
following links and commits before any byte is sent. A published file found definitely
missing or corrupt is revoked at once (C6a: media_state missing/corrupt, left to a person).

Why a read never starts under a deletion (C5a review M11): the safety rests on the
expiry gate, not on the cleaner's lease check alone. A read opens only while
statement_timestamp() < expires_at, holding the Job FOR SHARE until its lease commits;
C5a's mark_expired needs expires_at <= now() and skips locked Jobs, so a Job is marked
expired only after every deciding reader has committed its lease, and the later claim
transaction sees those leases. After the mark, reads answer 410. Changes that extend
expires_at after expiry or claim non-expired Jobs must preserve this ordering.

Errors are fixed codes; no path, manifest or lease id is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import logging
import os
from pathlib import Path
import re
import uuid

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import OperationalError

from ..models import DownloadAccess, Job
from ..models_execution import ArtifactManifest, FileReadLease
from ..models_operations import DownloadOperation
from . import artifact_store

READ_RENEW_SECONDS = 10
READ_LEASE_SECONDS = 30
READ_MAX_SECONDS = 30 * 60
if not 0 < READ_RENEW_SECONDS < READ_LEASE_SECONDS <= READ_MAX_SECONDS:
    raise RuntimeError('read lease timing invariant violated')  # a renewal must land before the lease lapses
_GONE = frozenset({'expired', 'deleting', 'deleted'})
_log = logging.getLogger(__name__)


class ReadDenied(Exception):
    def __init__(self, status: int, error_type: str):
        super().__init__(error_type)
        self.status, self.error_type = status, error_type


@dataclass(frozen=True, slots=True)
class OpenRead:
    read_id: str | None  # None for an imported v1 file: no attempt, so no read lease (C6b)
    file: object
    size: int
    etag: str
    media_format: str
    title: str | None


def _deny(session, status, error_type):
    session.rollback()
    error = ReadDenied(status, error_type)
    raise error


def open_read(session, user_id: str, job_id: str, *, media_root, height_limit: int | None,
              legacy_root=None) -> OpenRead:
    """Decide and open one read; commits on success, rolls back and raises ReadDenied otherwise.

    Everything the caller needs is captured before the commit: afterwards nothing touches the
    session, so no transaction (and no pooled connection) stays open while the file streams.
    """
    try:
        # Ownership in the WHERE clause: another user's job is never locked or waited on (plain 404).
        job = session.execute(select(Job).where(Job.id == job_id, Job.user_id == user_id)
                              .with_for_update(read=True)).scalar_one_or_none()
    except OperationalError as error:
        session.rollback()
        if getattr(error.orig, 'sqlstate', None) == '55P03':  # lock_not_available: a cleaner is deciding
            raise ReadDenied(503, 'file_busy') from None
        raise
    if job is None:
        # A Job purged by retention (C5b-1) is gone, not missing: its owner's operation keeps the
        # tombstone (A contract §7: tombstones answer 410). Anyone else still gets a plain 404.
        purged = session.execute(select(DownloadOperation.id).where(
            DownloadOperation.job_id_tombstone == job_id, DownloadOperation.job_id.is_(None),
            DownloadOperation.user_id == user_id)).first()
        _deny(session, 410 if purged is not None else 404, 'file_expired' if purged is not None else 'file_missing')
    legacy = job.execution_version != 2  # C6b: imported v1 Jobs follow the same order below
    if height_limit is not None:
        access = session.get(DownloadAccess, job.id)
        if access is None or access.max_height is None or access.max_height > height_limit:
            _deny(session, 403, 'membership_required')
    now = session.execute(select(func.statement_timestamp())).scalar_one()  # after any lock wait
    if job.media_state in _GONE or (job.expires_at is not None and now >= job.expires_at):
        _deny(session, 410, 'file_expired')
    if legacy:
        return _open_legacy(session, job, legacy_root)
    if job.internal_state != 'succeeded' or job.media_state != 'available' or job.visible_attempt_id is None:
        _deny(session, 404, 'file_missing')
    manifest = session.get(ArtifactManifest, job.visible_attempt_id)
    if manifest is None or manifest.job_id != job.id:
        _deny(session, 404, 'file_missing')
    try:
        handle = artifact_store.open_published(media_root, manifest.relative_path, manifest.byte_size)
    except artifact_store.ArtifactError as error:
        _log.warning('published media not readable: job=%s code=%s', job.id, error)
        if str(error) == 'artifact_root_unavailable':
            _deny(session, 503, 'file_storage_unavailable')  # an outage, not one missing file
        facts = (job.id, manifest.attempt_id, manifest.relative_path, manifest.byte_size)
        session.rollback()  # release the Job before any further file access
        _revoke_unreadable(session, media_root, *facts)
        raise ReadDenied(404, 'file_missing')
    read_id = str(uuid.uuid4())
    opened = OpenRead(read_id, handle, manifest.byte_size, f'"sha256-{manifest.sha256}"', manifest.media_format,
                      job.title)
    try:
        session.execute(insert(FileReadLease).values(
            id=read_id, job_id=job.id, attempt_id=manifest.attempt_id, started_at=func.now(),
            lease_deadline=func.now() + timedelta(seconds=READ_LEASE_SECONDS),
            max_until=func.now() + timedelta(seconds=READ_MAX_SECONDS)))
        session.commit()
    except BaseException:
        handle.close()
        session.rollback()
        raise
    return opened


def _revoke_unreadable(session, media_root, job_id: str, attempt_id: str, relative_path: str, byte_size: int) -> None:
    """C6a: a definitely missing or corrupt published file stops being readable at once.

    Diagnosed outside any transaction; an outage or transient error is no diagnosis. The state
    changes only while the Job is still available with the same visible attempt, so a cleaner's
    lifecycle change is never overridden. Nothing re-downloads or recovers it automatically.
    """
    diagnosis = artifact_store.diagnose_published(media_root, relative_path, byte_size)
    if diagnosis is None:
        return
    try:
        revoked = session.execute(
            update(Job).where(Job.id == job_id, Job.media_state == 'available', Job.visible_attempt_id == attempt_id)
            .values(media_state=diagnosis, error_type=f'media_{diagnosis}', updated_at=func.now())).rowcount
        session.commit()
    except Exception:
        session.rollback()
        _log.warning('published media revocation not recorded: job=%s code=db_error', job_id)
        return
    if revoked:
        _log.error('published media revoked: job=%s code=media_%s', job_id, diagnosis)


_LEGACY_FORMAT = re.compile(r'[a-z0-9]{1,8}\Z')


def _open_legacy(session, job, legacy_root) -> OpenRead:
    """C6b: a v1 file verified at import, opened in the old root without following links.

    v1 Jobs have no attempt, so no read lease is recorded; a transfer started before expiry stays
    bounded by READ_MAX_SECONDS. Expired v1 files are not deleted under PostgreSQL yet (follow-up
    C6c); reads still answer 410 by the database clock. Only the last path level is re-checked at
    open time (ino/nlink/size), as for v2 media.
    """
    if (job.legacy_check != 'verified' or legacy_root is None or not job.file_path or job.file_size is None
            or job.expires_at is None):  # every completed v1 Job had an expiry: none means untrusted data
        _deny(session, 404, 'file_missing')
    facts = (job.id, job.file_path, job.file_size)
    title = job.title
    try:
        handle = artifact_store.open_legacy(legacy_root, *facts)
    except artifact_store.ArtifactError as error:
        _log.warning('legacy media not readable: job=%s code=%s', job.id, error)
        if str(error) == 'artifact_root_unavailable':
            _deny(session, 503, 'file_storage_unavailable')
        session.rollback()
        _revoke_legacy(session, legacy_root, *facts)
        raise ReadDenied(404, 'file_missing')
    suffix = Path(facts[1]).suffix[1:].lower()
    media_format = suffix if _LEGACY_FORMAT.match(suffix) else 'bin'
    try:
        session.commit()  # release the Job; nothing else was written
    except BaseException:
        handle.close()
        session.rollback()
        raise
    return OpenRead(None, handle, facts[2], _legacy_etag(facts[0], handle), media_format, title)


def _legacy_etag(job_id, handle) -> str:
    """Strong ETag bound to the opened file's identity (no stored SHA for v1), so If-Range never
    resumes across a same-size replacement."""
    info = os.fstat(handle.fileno())
    digest = hashlib.sha256(f'{info.st_dev}:{info.st_ino}:{info.st_mtime_ns}:{info.st_size}'.encode()).hexdigest()
    return f'"legacy-{job_id}-{digest[:32]}"'


def _revoke_legacy(session, legacy_root, job_id, file_path, file_size) -> None:
    """A definitely missing/changed v1 file stops being readable (CAS on the import-time evidence)."""
    diagnosis = artifact_store.diagnose_legacy(legacy_root, job_id, file_path, file_size)
    if diagnosis is None:
        return
    try:
        revoked = session.execute(update(Job).where(Job.id == job_id, Job.legacy_check == 'verified')
                                  .values(legacy_check=diagnosis, updated_at=func.now())).rowcount
        session.commit()
    except Exception:
        session.rollback()
        _log.warning('legacy media revocation not recorded: job=%s code=db_error', job_id)
        return
    if revoked:
        _log.error('legacy media revoked: job=%s code=legacy_%s', job_id, diagnosis)


def renew_read(session, read_id: str) -> bool:
    """Extend a live read lease, never past max_until; an expired or ended lease never revives."""
    result = session.execute(
        update(FileReadLease)
        .where(FileReadLease.id == read_id, FileReadLease.ended_at.is_(None),
               FileReadLease.lease_deadline > func.now(), FileReadLease.max_until > func.now())
        .values(lease_deadline=func.least(func.now() + timedelta(seconds=READ_LEASE_SECONDS),
                                          FileReadLease.max_until)))
    return result.rowcount == 1


def end_read(session, read_id: str) -> None:
    session.execute(update(FileReadLease).where(FileReadLease.id == read_id, FileReadLease.ended_at.is_(None))
                    .values(ended_at=func.now()))
