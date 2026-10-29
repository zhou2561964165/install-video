"""Explicit orphan inventory CLI: python -m app.orphans --media-root DIR [--once].

Scans the provisioned media root (bounded), records objects without database ownership,
quarantines unknown objects and links, and removes listed objects only after 24 h and a
fresh ownership check. A full scan is heavier than a cleaner round, so it runs on its own
schedule. Exit codes: 0 done, 1 round failed, 2 refused root, 3 storage outage (--once).
"""
import argparse
import logging
from pathlib import Path
import signal
import time

from .config import settings
from .db import assert_schema_current, build_engine
from .services import artifact_store
from .services.orphans import run_once


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--media-root', required=True)
    args = parser.parse_args(argv)
    log = logging.getLogger(__name__)
    media_root = Path(args.media_root)
    try:
        artifact_store.probe_root(media_root)
    except artifact_store.ArtifactError as error:
        log.error('Orphan scanner media root refused: %s', error)
        raise SystemExit(2) from None
    engine = build_engine(settings.db_url, role='worker')
    previous = signal.signal(signal.SIGTERM, _stop_on_sigterm)
    try:
        assert_schema_current(engine)
        cursor = None
        while True:
            try:
                counts = run_once(engine, media_root, start_after=cursor)
            except Exception as error:
                log.error('Orphan round did not complete: %s', type(error).__name__)
                if args.once:
                    raise SystemExit(1) from None
                counts = None
            if counts is not None:
                log.info('Orphan round %s', ' '.join(f'{key}={value}' for key, value in counts.items()))
            if args.once:
                if counts['storage_unavailable']:
                    raise SystemExit(3)
                if counts['scan_failed']:
                    raise SystemExit(1)
                return counts
            cursor = counts['next_cursor'] if counts is not None else None
            if cursor is None:  # wrapped around: a full pass is done, wait for the next interval
                time.sleep(settings.orphan_scan_interval_seconds)
    finally:
        signal.signal(signal.SIGTERM, previous)
        engine.dispose()


def _stop_on_sigterm(signum, frame):
    raise SystemExit(143)


if __name__ == '__main__':
    main()
