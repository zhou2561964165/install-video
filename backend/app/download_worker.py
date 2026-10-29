"""Explicit durable download worker CLI: python -m app.download_worker --media-root DIR [--once].

The media root is given explicitly (no guessed default) and probed before anything is
leased. The 'ytdlp' executor stays unavailable until B5 U5/U6 wire the controlled
download; 'fake:*' executors exist for tests only and need DOWNLOAD_WORKER_ALLOW_FAKE=1.
"""
import argparse
import logging
from pathlib import Path
import signal
import time
import uuid

from .config import settings
from .db import assert_schema_current, build_engine
from .services import artifact_store, child_isolation
from .services.download_worker import run_once


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--media-root', required=True)
    parser.add_argument('--executor', default='ytdlp')
    args = parser.parse_args(argv)
    log = logging.getLogger(__name__)
    media_root = Path(args.media_root)
    try:
        artifact_store.probe_root(media_root)
    except artifact_store.ArtifactError as error:
        log.error('Download worker media root refused: %s', error)
        raise SystemExit(2) from None
    try:
        isolation = child_isolation.from_settings(settings)
        if isolation is not None:
            child_isolation.preflight(isolation)  # a real isolated probe child must prove its isolation
    except child_isolation.IsolationError as error:
        log.error('Download worker isolation refused: %s', error)
        raise SystemExit(2) from None
    engine = build_engine(settings.db_url, role='worker')
    owner = 'dl-' + uuid.uuid4().hex
    # SIGTERM (service stop) unwinds like an exception, so run_once's finally still ends the child group.
    previous = signal.signal(signal.SIGTERM, _stop_on_sigterm)
    try:
        assert_schema_current(engine)
        while True:
            try:
                outcome = run_once(engine, media_root, owner, executor=args.executor, isolation=isolation)
            except ValueError:
                log.error('Download worker configuration refused')
                raise SystemExit(2) from None
            except child_isolation.IsolationError as error:
                # A child this worker cannot stop: never lease more; the service stop ends the cgroup.
                log.error('Download worker isolation failed: %s', error)
                raise SystemExit(2) from None
            except Exception:
                # A failed/unknown step never starts an unowned retry; the persisted lease,
                # attempt budget and recovery govern what happens next.
                log.error('Download worker attempt did not complete')
                if args.once:
                    raise SystemExit(1) from None
                outcome = None
            if args.once:
                return outcome
            if outcome in (None, 'idle'):
                time.sleep(1)
    finally:
        signal.signal(signal.SIGTERM, previous)
        engine.dispose()


def _stop_on_sigterm(signum, frame):
    raise SystemExit(143)


if __name__ == '__main__':
    main()
