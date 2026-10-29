"""C5b-2 orphan round: scan the controlled root, record the inventory, reclaim old unowned objects.

One scanner at a time (session advisory lock; a second scanner skips its round). Each database
step is a short transaction (the inventory is recorded in chunks); files are removed outside
transactions. Objects are removed only when listed for at least 24 h and re-checked as unowned
right before removal; unknown objects, links and objects whose removal is refused
deterministically stay quarantined (never deleted). A bounded scan resumes from a cursor and
wraps, so every entry is eventually seen. A missing root stops the round. Logs carry fixed
codes only.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

from ..config import settings
from . import artifact_store
from .orphan_repository import BATCH_LIMIT, due_for_removal, is_owned, mark, purge_history, record_scan

SCANNER_LOCK_KEY = 0x0C5B2  # advisory lock key reserved for the orphan scanner
RECORD_CHUNK = 500
MAX_REMOVAL_BATCHES = 20
FINAL_REFUSALS = frozenset({'artifact_unknown_entry', 'artifact_path_unsafe'})
_log = logging.getLogger(__name__)


def run_once(engine, media_root: Path, *, start_after: str | None = None) -> dict:
    counts = dict(scanned=0, listed=0, quarantined=0, quarantined_new=0, released=0, removed=0, failed=0,
                  storage_unavailable=0, skipped=0, purged=0, scan_failed=0, next_cursor=None)
    with engine.connect() as lock:
        acquired = lock.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': SCANNER_LOCK_KEY}).scalar()
        lock.commit()  # the session-level lock outlives this transaction; the connection stays idle
        if not acquired:
            counts['skipped'] = 1
            return counts
        try:
            _round(engine, media_root, start_after, counts)
        finally:
            lock.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': SCANNER_LOCK_KEY})
            lock.commit()
    return counts


def _round(engine, media_root, start_after, counts) -> None:
    limit = settings.orphan_scan_limit
    try:
        entries = artifact_store.scan_root(media_root, limit=limit, start_after=start_after)
    except artifact_store.ArtifactError as error:
        _log.error('orphan scan stopped: %s', error)
        counts['storage_unavailable' if str(error) == 'artifact_root_unavailable' else 'scan_failed'] = 1
        counts['failed'] = counts['scan_failed']
        return
    if len(entries) >= limit:
        counts['next_cursor'] = entries[-1].relative_path.split('/', 1)[0]  # resume after this top-level name
    for start in range(0, len(entries), RECORD_CHUNK):
        with Session(engine) as session:
            chunk = record_scan(session, entries[start:start + RECORD_CHUNK])
            session.commit()
        for key, value in chunk.items():
            counts[key] += value
    if counts['quarantined_new']:
        _log.warning('orphan objects newly quarantined: count=%s', counts['quarantined_new'])
    for _ in range(MAX_REMOVAL_BATCHES):
        if not _removal_batch(engine, media_root, counts):
            break
    with Session(engine) as session:
        counts['purged'] = purge_history(session)
        session.commit()


def _removal_batch(engine, media_root, counts) -> bool:
    """One batch of due removals; returns whether another batch may have work."""
    with Session(engine) as session:
        removable, settled = [], 0  # settled: rows that left the listed state
        due = due_for_removal(session, limit=BATCH_LIMIT)
        for row in due:
            if is_owned(session, row.relative_path, row.kind):  # ownership regained since it was listed
                mark(session, row.relative_path, 'released')
                counts['released'] += 1
                settled += 1
            else:
                removable.append((row.relative_path, row.kind))
        session.commit()
    for relative_path, kind in removable:
        try:
            artifact_store.remove_orphan(media_root, relative_path, kind)
        except artifact_store.ArtifactError as error:
            code = str(error)
            if code == 'artifact_root_unavailable':
                _log.error('orphan removal stopped: artifact_root_unavailable')
                counts['storage_unavailable'] = 1
                return False
            _log.warning('orphan not removed: kind=%s code=%s', kind, code)
            with Session(engine) as session:
                # A refusal a retry cannot change (unknown content, unsafe path) is quarantined.
                mark(session, relative_path, 'quarantined' if code in FINAL_REFUSALS else 'listed', code)
                session.commit()
            settled += code in FINAL_REFUSALS
            counts['failed'] += 1
            continue
        with Session(engine) as session:
            mark(session, relative_path, 'removed')
            session.commit()
        counts['removed'] += 1
        settled += 1
    # A failed (retryable) row stays listed and would be picked again: stop when nothing settled.
    return len(due) == BATCH_LIMIT and settled > 0
