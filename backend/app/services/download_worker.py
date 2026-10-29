"""C3 durable download worker: one leased Job per run_once, executed in a supervised child.

The only layer that joins C1 (lease), the supervisor (child process, no DB) and C2
(seal + publish). Every DB step is its own short transaction, committed at once:
maintenance, claim, each heartbeat + byte report, failure, publish. Nothing here
retries a DB write to rescue a lease: a lost lease, a DB error, an expired window
or an exhausted byte budget stops the child, never publishes, and removes only this
attempt's own directory. Logs carry fixed codes only (no URLs, paths or tokens).

Ordering contracts (C2 review): the child's whole process group is reaped before
sealing; the final byte report commits before publishing (its Job lock must not
precede publish's resources -> operation -> Job order); publish/find_published
results commit or roll back immediately; on LEASE_LOST the attempt is removed only
after confirming it is not the Job's visible artifact and the Job has been fenced past
its epoch (a merely expired lease keeps the sealed candidate for C6a recovery).
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import time

from sqlmodel import Session, select

from ..config import settings
from ..models import Job
from ..models_execution import JobAttempt
from . import artifact_store, child_isolation, execution_supervisor, executors, recovery
from .artifact_publish import LEASE_LOST, find_published, publish_candidate
from .job_repository import (HEARTBEAT_SECONDS, NEEDS_REVIEW, RETRYABLE, SOURCE_BUDGET_FACTOR, claim_next,
                             expire_window, fail_attempt, heartbeat, recover_expired, report_bytes, report_progress)

TERMINATE_GRACE_SECONDS = 10.0
POLL_SECONDS = 0.2
# Codes a child may report: the executor layer's own codes and C1's classification. Anything else
# becomes 'execution_failed', so a child cannot pick retry/review semantics with an arbitrary code.
CHILD_ERROR_CODES = RETRYABLE | NEEDS_REVIEW | frozenset({
    'source_unavailable', 'file_too_large', 'disk_error', 'execution_crashed', 'execution_protocol_error',
    'execution_terminated', 'execution_request_invalid', 'execution_scenario_unknown', 'executor_unknown',
    'http_403', 'http_404', 'http_410', 'http_412',
    # B5 U5b ytdlp executor: policy refusal, request budget, other 4xx, failed container signature.
    'http_401', 'http_4xx', 'source_blocked', 'source_budget_exhausted', 'media_invalid', 'format_unsupported'})
_log = logging.getLogger(__name__)


def _maintain(engine, media_root: Path) -> None:
    # C6a: an expired lease is fenced only after the recovery round examined it and found no sealed
    # candidate; skipped Jobs (storage outage, transient I/O, not yet examined) wait for a later round.
    fenceable = recovery.adopt_expired(engine, media_root)['fenceable']
    with Session(engine) as session:
        recover_expired(session, lease_fence=fenceable)
        session.commit()
    with Session(engine) as session:
        expire_window(session)
        session.commit()


def _claim(engine, owner):
    with Session(engine) as session:
        token = claim_next(session, owner)
        if token is None:
            session.rollback()
            return None, None
        source = session.exec(select(Job.url, Job.format_id).where(Job.id == token.job_id)).one()
        session.commit()
    return token, source


def _beat(engine, token, attempt_bytes: int, percent: float | None = None) -> str:
    """Heartbeat, byte and progress report in one short transaction:
    'ok' | 'lost' | 'over_budget' | 'db_error'."""
    try:
        with Session(engine) as session:
            if not heartbeat(session, token):
                session.rollback()
                return 'lost'
            result = report_bytes(session, token, attempt_bytes)
            if result == 'ok' and percent is not None:
                report_progress(session, token, percent)
            session.commit()
            return result
    except Exception:
        _log.warning('download worker heartbeat failed: db_error')
        return 'db_error'


def _fail(engine, token, code: str) -> str:
    try:
        with Session(engine) as session:
            result = fail_attempt(session, token, code)
            session.commit()
            return result
    except Exception:
        _log.warning('download worker could not record failure: db_error')
        return 'lost'


def _discard(paths) -> None:
    try:
        artifact_store.remove_own_attempt(paths)
    except artifact_store.ArtifactError as error:
        _log.warning('download worker left attempt for reconciliation: %s', error)
    except OSError:
        _log.warning('download worker left attempt for reconciliation: artifact_io_failed')


def _part_size(paths) -> int:
    size = 0
    try:
        size = paths.part.lstat().st_size
    except OSError:
        pass
    # An abruptly terminated DASH child may leave only its two local inputs.
    # Count them after reaping, before cleanup, even if its last event was lost.
    source = 0
    for name in ('video.bin', 'audio.bin'):
        try:
            source += (paths.directory / artifact_store.SCRATCH_DIR / name).lstat().st_size
        except OSError:
            pass
    return max(size, source)


def _visible(engine, token) -> bool:
    with Session(engine) as session:
        found = find_published(session, token.job_id, token.epoch, token.attempt_id)
        session.rollback()  # drop find_published's FOR SHARE lock at once
    return found is not None


def _fenced(engine, token) -> bool:
    """This attempt was ended by a lease fence (recover_expired): it can never be adopted.

    An attempt still running may yet be adopted by C6a recovery; one ended by recovery itself
    (recovery_* codes, Job in needs_review) keeps its files for the person reviewing it.
    """
    with Session(engine) as session:
        ended = session.exec(select(JobAttempt.state, JobAttempt.error_code)
                             .where(JobAttempt.id == token.attempt_id)).one_or_none()
        session.rollback()
    return ended is not None and tuple(ended) == ('lost', 'lease_expired')


def _stop(run, paths, isolation=None) -> None:
    run.terminate(grace=TERMINATE_GRACE_SECONDS)
    run.reap()
    if isolation is not None:
        child_isolation.lock_attempt_dir(paths.directory)
    _discard(paths)


def _publish(engine, token, candidate, media_root: Path) -> str:
    try:
        with Session(engine) as session:
            result = publish_candidate(session, token, candidate,
                                       absolute_path=str(media_root / candidate.relative_path))
            session.commit()
    except Exception:
        # Unknown commit outcome: confirm by identity; never re-download or re-publish.
        _log.warning('download worker publish outcome unknown: db_error')
        try:
            return 'published' if _visible(engine, token) else 'lost'  # unconfirmed files stay for C6
        except Exception:
            return 'lost'
    if result is LEASE_LOST:
        try:
            visible = _visible(engine, token)
            fenced = not visible and _fenced(engine, token)
        except Exception:
            _log.warning('download worker could not confirm visibility after lease loss: db_error')
            return 'lost'  # files stay for C6
        if visible:
            _log.warning('download worker lease lost but attempt is visible: left for reconciliation')
        elif fenced:
            _discard(artifact_store.AttemptPaths(media_root, token.job_id, token.epoch, token.attempt_id))
        else:
            # Expired but not fenced: C6a recovery may still adopt this sealed candidate.
            _log.warning('download worker lease expired after sealing: left for recovery')
        return 'lost'
    return 'published'


def run_once(engine, media_root: Path, owner: str, *, executor: str, heartbeat_seconds: float = HEARTBEAT_SECONDS,
             poll_seconds: float = POLL_SECONDS, clock=time.monotonic, sleep=time.sleep,
             isolation: child_isolation.IsolationConfig | None = None) -> str:
    """'idle' | 'published' | 'failed' | 'retry_wait' | 'needs_review' | 'lost'.

    With `isolation` (external gate G3/G4) the child runs as the firewalled download user: its
    attempt directory is shared with it while it runs and locked once it has been reaped, before
    anything is sealed, discarded or published.
    """
    if type(executor) is not str or not executors.available(executor, isolated=isolation is not None):
        raise ValueError('executor_unavailable')  # before any claim: a misconfigured worker leases nothing
    _maintain(engine, media_root)
    token, source = _claim(engine, owner)
    if token is None:
        return 'idle'
    remaining = SOURCE_BUDGET_FACTOR * settings.max_file_size - token.source_bytes_used
    attempt_limit = min(settings.max_file_size, remaining)
    if attempt_limit <= 0:
        return _fail(engine, token, 'file_too_large')
    try:
        paths = artifact_store.prepare_attempt(media_root, token.job_id, token.epoch, token.attempt_id)
    except artifact_store.ArtifactError as error:
        return _fail(engine, token, str(error))
    run = None
    try:
        if isolation is not None:
            child_isolation.share_attempt_dir(paths.directory, isolation)  # IsolationError stops the worker
        window = (token.run_deadline_at - datetime.now(timezone.utc)).total_seconds()
        from .bilibili_session import cookie_snapshot_for_url, SessionError
        try:
            snapshot = cookie_snapshot_for_url(source.url) if executor == 'ytdlp' else None
        except SessionError:
            _discard(paths)
            return _fail(engine, token, 'source_unavailable')
        run = execution_supervisor.start(execution_supervisor.ExecutionRequest(
            job_id=token.job_id, epoch=token.epoch, attempt_id=token.attempt_id, url=source.url,
            format_id=source.format_id or '', attempt_dir=str(paths.directory), max_bytes=attempt_limit,
            deadline_seconds=max(1.0, window), executor=executor,
            bili_cookie_snapshot=snapshot), isolation=isolation)
        return _execute(engine, token, run, paths, media_root, attempt_limit,
                        heartbeat_seconds, poll_seconds, clock, sleep, isolation)
    finally:
        # Whatever happened, including an unexpected exception, this run's child group never outlives it,
        # and an isolated attempt directory never stays shared with the download user (review I2).
        try:
            if run is not None:
                try:
                    run.terminate(grace=TERMINATE_GRACE_SECONDS)
                finally:
                    run.reap()
        finally:
            if isolation is not None and os.path.lexists(paths.directory):
                child_isolation.lock_attempt_dir(paths.directory)


def _execute(engine, token, run, paths, media_root, attempt_limit, heartbeat_seconds, poll_seconds, clock, sleep,
             isolation=None):
    attempt_bytes, percent, last_beat = 0, 0.0, clock()
    while run.result() is None:
        for event in run.poll():
            attempt_bytes, percent = max(attempt_bytes, event.bytes), max(percent, event.percent)
        if clock() - last_beat >= heartbeat_seconds:
            status = _beat(engine, token, attempt_bytes, percent)
            if status != 'ok':
                _stop(run, paths, isolation)
                return _fail(engine, token, 'file_too_large') if status == 'over_budget' else 'lost'
            last_beat = clock()
        sleep(poll_seconds)
    for event in run.poll():
        attempt_bytes, percent = max(attempt_bytes, event.bytes), max(percent, event.percent)
    outcome = run.result()
    run.reap()  # no group member may still be writing before seal or cleanup
    if isolation is not None:
        child_isolation.lock_attempt_dir(paths.directory)  # the download user can no longer reach it
    # Record this attempt's bytes on every path, failed attempts included (the budget spans attempts),
    # counting what is on disk even if the child under-reported; on success this also commits
    # before publish (lock order).
    status = _beat(engine, token, max(attempt_bytes, _part_size(paths)), percent)
    media_check = outcome.media_check
    if outcome.ok and status == 'ok' and isolation is not None:
        # The isolated child is untrusted (review I3): its media_check claim is ignored and the
        # worker checks the container signature itself, now that nothing else can write the file.
        try:
            signed = artifact_store.container_signature_ok(paths.part, outcome.ext)
        except artifact_store.ArtifactError:
            signed = False
        if not signed:
            _discard(paths)
            return _fail(engine, token, 'media_invalid')
        media_check = 'signature'
    if not outcome.ok or status != 'ok':
        _discard(paths)
        if status == 'over_budget':
            return _fail(engine, token, 'file_too_large')
        if status != 'ok':
            return 'lost'
        return _fail(engine, token, outcome.code if outcome.code in CHILD_ERROR_CODES else 'execution_failed')
    try:
        candidate = artifact_store.seal_candidate(paths, ext=outcome.ext, max_bytes=attempt_limit,
                                                  media_check=media_check)
    except artifact_store.ArtifactError as error:
        _discard(paths)
        code = 'file_too_large' if str(error) == 'artifact_size_invalid' else str(error)
        return _fail(engine, token, code)
    return _publish(engine, token, candidate, media_root)
