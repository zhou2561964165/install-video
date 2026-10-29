"""B6 E3 T7: real-data drill (user-authorized 2026-10-27). Not part of the regular suites.

The operator-named real SQLite source is copied into the private bundle parent, exported read-only
through the operational bootstrap, imported (dry run, then for real) into a fresh nonce-owned PG at
head and verified. The receipt holds only table names, counts, fixed codes and hashes; the copy and
the bundle are removed afterwards and the database is dropped by the isolated-database fixture.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from tools import production_db_export as export
from tools import production_db_import as importer
import tools.production_db_snapshot_read_contract as rc


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def test_real_source_export_import_verify():
    from b3b_pg_helpers import isolated_database
    source = Path(os.environ['B6_REAL_SOURCE'])
    legacy_root = os.environ.get('B6_REAL_LEGACY_ROOT') or None
    parent = Path(os.environ['B6_BUNDLE_PARENT'])
    receipt = dict(source_name=source.name, source_bytes=source.stat().st_size, source_sha256=_sha256(source),
                   legacy_root_given=legacy_root is not None)
    sidecars = [suffix for suffix in ('-wal', '-journal', '-shm') if Path(str(source) + suffix).exists()]
    receipt['sidecars'] = sidecars
    assert not sidecars, 'source has SQLite sidecar files: stop writers and checkpoint before copying'
    copy = parent / ('source-' + uuid.uuid4().hex[:12] + '.db')
    destination = str(parent) + os.sep + 'real-' + uuid.uuid4().hex[:12]
    shutil.copyfile(source, copy)
    try:
        receipt['copy_sha256_matches'] = _sha256(copy) == receipt['source_sha256']
        with rc.open_operational_sqlite(str(copy.resolve())) as (connection, contract):
            exported = export.export_snapshot(connection, destination, driver_contract=contract,
                                              trusted_parent_ack=True)
        receipt['export'] = dict(status=exported.status, error_codes=list(exported.error_codes),
                                 table_count=exported.table_count, row_count=exported.row_count)
        assert exported.status == 'published'
        manifest = destination + os.sep + 'manifest.json'
        with isolated_database(target='head') as target:
            dry = importer.import_snapshot(manifest, target.migration, legacy_media_root=legacy_root,
                                           trusted_parent_ack=True)
            done = importer.import_snapshot(manifest, target.migration, dry_run=False, legacy_media_root=legacy_root,
                                            trusted_parent_ack=True)
            verified = importer.verify_snapshot(manifest, target.migration, legacy_media_root=legacy_root,
                                                trusted_parent_ack=True)
            again = importer.import_snapshot(manifest, target.migration, dry_run=False,
                                             legacy_media_root=legacy_root, trusted_parent_ack=True)
        receipt.update(schema_profile=done.schema_profile, manifest_sha256=done.manifest_sha256,
                       dry_run=dry.status, imported=done.status, table_rows=done.table_rows,
                       transforms=done.transforms, verify_accepted=verified.accepted,
                       verify_differences=[list(item) for item in verified.differences],
                       reimport=again.status)
        assert dry.status == 'dry_run_ok' and done.status == 'imported' and again.status == 'already_imported'
        assert verified.accepted, verified.differences
    except importer.ImportFailure as error:
        receipt['import_failure'] = error.code
        raise
    except export.SnapshotExportError as error:
        receipt['export_failure'] = error.code
        raise
    finally:
        copy.unlink(missing_ok=True)
        shutil.rmtree(destination, ignore_errors=True)
        receipt['copy_removed'] = not copy.exists()
        receipt['bundle_removed'] = not Path(destination).exists()
        Path(os.environ['B6_DRILL_RECEIPT']).write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding='utf8')
