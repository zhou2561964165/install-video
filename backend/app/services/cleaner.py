"""C5a cleaner round: check the root, mark expired, claim deletions, delete outside transactions, confirm.

Each database step is its own short transaction committed at once; file deletion happens
only after the claim is committed and never inside a transaction. The provisioned media
root is checked before anything is marked or claimed, and again by remove_published
before "already absent" counts as deleted: an unmounted volume or empty mount point stops
the round as an outage and never turns Jobs into deleted or burns retry budgets.
Deterministic refusals (unknown entries, unsafe paths, a path that does not belong to the
claim) go straight to needs_review; other failures back off. Logs carry fixed codes only.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlmodel import Session

from . import artifact_store
from .cleanup_repository import (BATCH_LIMIT, claim_deletions, claim_legacy_deletions, confirm_deleted,
                                 confirm_legacy_deleted, count_legacy_pending, mark_expired, record_failure,
                                 record_legacy_failure, refuse_legacy)
from .retention_repository import purge_expired_metadata

FINAL_REFUSALS = frozenset({'artifact_unknown_entry', 'artifact_path_unsafe'})
_log = logging.getLogger(__name__)


def _belongs(claim) -> bool:
    return claim.relative_path.startswith(f'{claim.job_id}/') and f'-{claim.attempt_id}/' in claim.relative_path


def run_once(engine, media_root: Path, owner: str, *, limit: int = BATCH_LIMIT, legacy_root: Path | None = None) -> dict:
    counts = dict(marked=0, claimed=0, deleted=0, retry=0, needs_review=0, lost=0, storage_unavailable=0,
                  purged=0, purge_failed=0, purge_mismatched=0, legacy_deleted=0, legacy_failed=0, legacy_refused=0,
                  legacy_review=0, legacy_storage_unavailable=0, legacy_pending=0)
    try:
        artifact_store.check_root(media_root)
    except artifact_store.ArtifactError:
        _log.error('cleaner stopped before claiming: artifact_root_unavailable')
        counts['storage_unavailable'] = 1
        return counts
    with Session(engine) as session:
        counts['marked'] = len(mark_expired(session, limit=limit))
        session.commit()
    with Session(engine) as session:
        claims = claim_deletions(session, owner, limit=limit)
        session.commit()
    counts['claimed'] = len(claims)
    for claim in claims:
        code = None
        if not _belongs(claim):
            code = 'artifact_path_unsafe'  # never delete another job's or attempt's objects
        else:
            try:
                artifact_store.remove_published(media_root, claim.relative_path, prune_job_dir=True)  # Job finished
            except artifact_store.ArtifactError as error:
                code = str(error)
        if code == 'artifact_root_unavailable':
            _log.error('cleaner stopped: artifact_root_unavailable')
            counts['storage_unavailable'] = 1
            break  # the remaining claims lapse and are retried after the outage
        if code is not None:
            _log.warning('cleaner could not delete job=%s code=%s', claim.job_id, code)
            with Session(engine) as session:
                outcome = record_failure(session, claim, code, final=code in FINAL_REFUSALS)
                session.commit()
            counts[outcome] += 1
            continue
        with Session(engine) as session:
            confirmed = confirm_deleted(session, claim)
            session.commit()
        counts['deleted' if confirmed else 'lost'] += 1
    if not counts['storage_unavailable']:
        # C6c: imported v1 files; a legacy outage never stops the v2 lifecycle or the retention purge.
        _legacy_round(engine, legacy_root, counts, limit)
    if not counts['storage_unavailable']:
        # C5b-1: metadata past retention (database only; its media is already deleted or never existed).
        stats = {}
        with Session(engine) as session:
            counts['purged'] = len(purge_expired_metadata(session, limit=limit, stats=stats))
            session.commit()
        counts['purge_failed'], counts['purge_mismatched'] = stats['failed'], stats['mismatched']
    return counts



def _legacy_round(engine, legacy_root: Path | None, counts: dict, limit: int) -> None:
    """C6c: expired imported v1 files, deleted outside transactions after a committed claim."""
    if legacy_root is None:
        with Session(engine) as session:
            counts['legacy_pending'] = count_legacy_pending(session)
        if counts['legacy_pending']:
            _log.warning('expired legacy files wait for deletion (no legacy root configured): count=%s',
                         counts['legacy_pending'])
        return
    try:
        artifact_store.check_legacy_root(legacy_root)
    except artifact_store.ArtifactError:
        _log.error('legacy deletion skipped: legacy artifact_root_unavailable')
        counts['legacy_storage_unavailable'] = 1
        return
    with Session(engine) as session:
        claims = claim_legacy_deletions(session, limit=limit)
        session.commit()
    for claim in claims:
        try:
            artifact_store.remove_legacy(legacy_root, claim.job_id, claim.file_path)
        except artifact_store.ArtifactError as error:
            code = str(error)
            if code == 'artifact_root_unavailable':
                _log.error('legacy deletion stopped: legacy artifact_root_unavailable job=%s', claim.job_id)
                counts['legacy_storage_unavailable'] = 1
                return  # the claims stay 'deleting' and are retried once the old root is back
            _log.warning('cleaner could not delete legacy job=%s code=%s', claim.job_id, code)
            with Session(engine) as session:
                if code == 'artifact_path_unsafe':
                    outcome = 'refused' if refuse_legacy(session, claim) else 'lost'
                else:
                    outcome = record_legacy_failure(session, claim)  # backoff, then review
                session.commit()
            counts['legacy_refused'] += outcome == 'refused'
            counts['legacy_failed'] += outcome == 'retry'
            counts['legacy_review'] += outcome == 'review'
            continue
        with Session(engine) as session:
            confirmed = confirm_legacy_deleted(session, claim)
            session.commit()
        counts['legacy_deleted'] += int(confirmed)
