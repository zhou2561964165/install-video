"""Explicit durable media cleaner CLI: python -m app.cleaner --media-root DIR [--once].

The media root is given explicitly (same provisioned root as the download worker) and
checked before anything is claimed. Each round marks expired media, claims deletions,
deletes only the claimed attempts' controlled objects and confirms; failures back off and
end in needs_review without ever making media available again. Exit codes: 0 done,
1 round failed, 2 refused configuration/root, 3 storage outage during a --once round.
"""
import argparse
import logging
from pathlib import Path
import signal
import time
import uuid

from .config import settings
from .db import assert_schema_current, build_engine
from .services import artifact_store
from .services.cleaner import run_once
from .services.cleanup_repository import BATCH_LIMIT


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--media-root', required=True)
    # C6c: the old v1 file root (settings.temp_dir as v1 wrote it); omitted -> v1 files are left alone.
    parser.add_argument('--legacy-root')
    args = parser.parse_args(argv)
    log = logging.getLogger(__name__)
    media_root = Path(args.media_root)
    try:
        artifact_store.probe_root(media_root)
    except artifact_store.ArtifactError as error:
        log.error('Cleaner media root refused: %s', error)
        raise SystemExit(2) from None
    legacy_root = Path(args.legacy_root).resolve() if args.legacy_root else None
    if legacy_root is not None:
        try:
            artifact_store.check_legacy_root(legacy_root)
        except artifact_store.ArtifactError as error:
            log.error('Cleaner legacy root refused: %s', error)
            raise SystemExit(2) from None
    engine = build_engine(settings.db_url, role='worker')
    owner = 'cl-' + uuid.uuid4().hex
    previous = signal.signal(signal.SIGTERM, _stop_on_sigterm)
    try:
        assert_schema_current(engine)
        while True:
            try:
                counts = run_once(engine, media_root, owner, legacy_root=legacy_root)
            except Exception as error:
                # Claims lapse and are retried by a later round; nothing is forced here.
                log.error('Cleaner round did not complete: %s', type(error).__name__)
                if args.once:
                    raise SystemExit(1) from None
                counts = None
            if counts is not None:
                log.info('Cleaner round %s', ' '.join(f'{key}={value}' for key, value in counts.items()))
            if args.once:
                if counts['storage_unavailable']:
                    raise SystemExit(3)
                return counts
            if counts is None or (counts['claimed'] < BATCH_LIMIT and counts['purged'] < BATCH_LIMIT):
                time.sleep(settings.cleaner_round_pause_seconds)  # a full batch continues at once (backlog)
    finally:
        signal.signal(signal.SIGTERM, previous)
        engine.dispose()


def _stop_on_sigterm(signum, frame):
    raise SystemExit(143)


if __name__ == '__main__':
    main()
