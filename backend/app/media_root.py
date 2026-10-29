"""Operator step, once per media volume: python -m app.media_root DIR

Writes the media-root marker into an existing, canonical, mounted directory. The download
worker, the read path and the cleaner refuse a root without it, so an unmounted volume or
an empty mount point is never mistaken for storage whose files are gone. Idempotent; never
overwrites a different marker. Exit codes: 0 provisioned, 2 refused.
"""
import argparse
from pathlib import Path

from .services import artifact_store


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('media_root')
    # C6c: mark the old v1 file root instead (python -m app.media_root --legacy DIR).
    parser.add_argument('--legacy', action='store_true')
    args = parser.parse_args(argv)
    try:
        provision = artifact_store.provision_legacy_root if args.legacy else artifact_store.provision_root
        provision(Path(args.media_root))
    except artifact_store.ArtifactError as error:
        print(f'media root refused: {error}')
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
