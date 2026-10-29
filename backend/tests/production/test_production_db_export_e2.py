"""E2 T3: contract-gated SQLite export orchestration; run via run_b6_e2_export.py only."""
import json
import os
from pathlib import Path
import sqlite3
import uuid

import pytest

from tools import production_db_export as export
from tools import production_db_snapshot_files as files
from tools import production_db_snapshot_format as codec
import tools.production_db_snapshot_catalog as catalog
import tools.production_db_snapshot_read_contract as rc
import tools.production_db_snapshot_rows as rows
from tools.production_db_snapshot_profiles import SOURCE_PROFILES

FIXTURES = Path(__file__).parent / 'fixtures' / 'snapshot_catalog'
USERS = [('u1', 'a@example.com', 'h1', '2026-10-25 01:02:03'),
         ('u2', 'bé\U0001f600@example.com', '', 'not-a-date'),
         ('u3', 'c@example.com', 'x\x00y', '2026-10-25T01:02:03.123456+08:00')]
QUOTA = "INSERT INTO quota VALUES ('q1','u1','2026-10-25',0,9223372036854775807),('q2','u2',X'00FF',2.5,-1);"


def make_db(tmp_path, version=17, populate=True):
    path = tmp_path / f'export{version}.db'
    writer = sqlite3.connect(str(path))
    try:
        writer.executescript((FIXTURES / f'sqlite{version}.sql').read_text('utf8'))
        if populate:
            writer.executemany('INSERT INTO user VALUES (?,?,?,?)', USERS)
            if version == 17:
                writer.executescript(QUOTA)
        writer.commit()
    finally:
        writer.close()
    return str(path.resolve())


def destination():
    return os.environ['B6_BUNDLE_PARENT'] + os.sep + 'e2-' + uuid.uuid4().hex[:12]


def oracle(path, table):
    connection = sqlite3.connect(path)
    try:
        order = ','.join('"' + name + '"' for name in table.primary_key)
        return connection.execute(f'SELECT * FROM "{table.name}" ORDER BY {order}').fetchall()
    finally:
        connection.close()


def decoded(dest, manifest, profile):
    """Independent decode of the published chunks, keyed by table name."""
    result = {}
    for table, doc in zip(rows.table_order(profile.descriptor), manifest['tables']):
        tags = export._tags(profile, table)
        values = []
        for name in doc['chunks']:
            data = Path(dest, name).read_bytes()
            for line in data.splitlines(keepends=True):
                values.append(tuple(codec.decode_row(line, allowed_tags=tags)))
        result[table.name] = values
    return result


def run(path, dest=None, **kwargs):
    dest = dest or destination()
    with rc._open_synthetic_sqlite(path) as (connection, contract):
        raw = connection.connection.driver_connection
        kwargs.setdefault('driver_contract', contract)
        kwargs.setdefault('trusted_parent_ack', True)
        try:
            result = export.export_snapshot(connection, dest, **kwargs)
        finally:
            state = (connection.in_transaction(), raw.in_transaction,
                     raw.execute('PRAGMA busy_timeout').fetchone(), raw.execute('PRAGMA query_only').fetchone(),
                     rc._guard_of(contract).installed, contract._state)
    return result, dest, state


RESTORED = (False, False, (5000,), (0,), False, 'consumed')


def expect(code, path, **kwargs):
    dest = kwargs.pop('dest', None) or destination()
    with pytest.raises(export.SnapshotExportError) as caught:
        run(path, dest, **kwargs)
    assert caught.value.code == code
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    return dest


@pytest.mark.parametrize('version,profile_id,count', [(17, 'sqlite_models17_v1', 5), (9, 'legacy_sqlite9_v1', 3)],
                         ids=['s17', 's9'])
def test_export_publishes_and_matches_oracle(tmp_path, version, profile_id, count):
    path = make_db(tmp_path, version)
    result, dest, state = run(path)
    assert state == RESTORED
    assert result.published and result.status == 'published' and result.error_codes == ()
    assert result.row_count == count and result.table_count == (17 if version == 17 else 9)
    assert '@example' not in repr(result)
    report = export.validate_export(dest + os.sep + 'manifest.json', trusted_parent_ack=True)
    assert report.accepted and report.row_count == count and report.manifest_sha256 == result.manifest_sha256
    manifest = json.loads(Path(dest, 'manifest.json').read_bytes())
    assert manifest['snapshot_method'] == 'sqlite_synthetic_readonly_snapshot_v1'
    assert manifest['source'] == dict(dialect='sqlite', namespace=SOURCE_PROFILES[profile_id].descriptor.namespace,
                                      version=sqlite3.sqlite_version)
    assert manifest['schema_profile'] == profile_id and manifest['migration_eligible'] == 'not_assessed'
    assert manifest['started_at'] <= manifest['ended_at'] <= manifest['created_at']
    got = decoded(dest, manifest, SOURCE_PROFILES[profile_id])
    for table in rows.table_order(SOURCE_PROFILES[profile_id].descriptor):
        assert got[table.name] == oracle(path, table)


def test_empty_database_exports(tmp_path):
    result, dest, state = run(make_db(tmp_path, 9, populate=False))
    assert state == RESTORED and result.published and result.row_count == 0


@pytest.fixture
def no_source_sql(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('source_sql_before_argument_checks')
    monkeypatch.setattr(catalog, 'readonly_snapshot', forbidden)


@pytest.mark.parametrize('contract', [None, True, object()], ids=['none', 'bool', 'object'])
def test_contract_required_before_source_or_target(tmp_path, no_source_sql, contract):
    dest = expect('driver_contract_required', make_db(tmp_path), driver_contract=contract)
    assert not os.path.exists(dest)


def test_arguments_checked_before_source(tmp_path, no_source_sql):
    path = make_db(tmp_path)
    for kwargs, code in ((dict(trusted_parent_ack=False), 'snapshot_arguments_invalid'),
                         (dict(trusted_parent_ack=1), 'snapshot_arguments_invalid'),
                         (dict(limits=object()), 'snapshot_limits_invalid'),
                         (dict(dest='relative-dir'), 'snapshot_path_invalid'),
                         (dict(dest=os.environ['B6_BUNDLE_PARENT'] + os.sep + 'Upper'), 'snapshot_path_invalid')):
        expect(code, path, **kwargs)


def test_export_binding_is_safe_for_hostile_calls():
    for args, kwargs in [((), {}), ((object(),), {}), ((object(), object()), {'unknown': 1})]:
        with pytest.raises(export.SnapshotExportError) as caught:
            export.export_snapshot(*args, **kwargs)
        assert caught.value.code in ('snapshot_arguments_invalid', 'driver_contract_required')
        assert caught.value.__context__ is None and caught.value.__cause__ is None


def test_preflight_failure_never_reserves_target(tmp_path, monkeypatch):
    from dataclasses import replace
    reserved = []
    original = files.reserve_directory
    monkeypatch.setattr(files, 'reserve_directory', lambda *a, **k: reserved.append(1) or original(*a, **k))
    limits = replace(export.DEFAULT_LIMITS, codec=codec.CodecLimits(max_cell_bytes=12))
    dest = expect('snapshot_resource_limit', make_db(tmp_path), limits=limits)
    assert reserved == [] and not os.path.exists(dest)


def test_restore_failure_code_survives_staging_cleanup_failure(tmp_path, monkeypatch):
    def broken(self):
        raise sqlite3.OperationalError('private_restore_detail')

    def abort_fails(self):
        raise files.SnapshotFileError('snapshot_cleanup_failed')
    monkeypatch.setattr(rc._SqliteGuard, '_restore', broken)
    monkeypatch.setattr(files.OwnedDirectory, 'abort', abort_fails)
    publishes = []
    monkeypatch.setattr(files.OwnedDirectory, 'publish_marker', lambda self, data: publishes.append(1))
    expect('connection_restore_failed', make_db(tmp_path))
    assert publishes == []


def test_staging_failure_aborts_and_restores_source(tmp_path, monkeypatch):
    original = files.OwnedDirectory.write_file
    calls = []

    def failing(self, name, blocks):
        calls.append(name)
        if len(calls) == 3:
            raise files.SnapshotFileError('snapshot_io_failed')
        return original(self, name, blocks)
    monkeypatch.setattr(files.OwnedDirectory, 'write_file', failing)
    path = make_db(tmp_path)
    dest = destination()
    with rc._open_synthetic_sqlite(path) as (connection, contract):
        raw = connection.connection.driver_connection
        with pytest.raises(export.SnapshotExportError) as caught:
            export.export_snapshot(connection, dest, driver_contract=contract, trusted_parent_ack=True)
        assert caught.value.code == 'snapshot_io_failed'
        assert not raw.in_transaction and not rc._guard_of(contract).installed
    assert not os.path.exists(dest)


def test_source_restore_failure_wins_and_never_publishes(tmp_path, monkeypatch):
    def broken(self):
        raise sqlite3.OperationalError('private_restore_detail')
    monkeypatch.setattr(rc._SqliteGuard, '_restore', broken)
    publishes = []
    monkeypatch.setattr(files.OwnedDirectory, 'publish_marker', lambda self, data: publishes.append(1))
    dest = expect('connection_restore_failed', make_db(tmp_path))
    assert publishes == [] and not os.path.exists(dest)


def test_source_closed_before_validation_and_publish(tmp_path, monkeypatch):
    seen = []
    original_validate = export._validate_core
    original_publish = files.OwnedDirectory.publish_marker

    def validate(*args, **kwargs):
        seen.append(('validate', dict(catalog._ACTIVE), [g.installed for g in guards]))
        return original_validate(*args, **kwargs)

    def publish(self, data):
        seen.append(('publish', dict(catalog._ACTIVE), [g.installed for g in guards]))
        return original_publish(self, data)
    monkeypatch.setattr(export, '_validate_core', validate)
    monkeypatch.setattr(files.OwnedDirectory, 'publish_marker', publish)
    path = make_db(tmp_path)
    with rc._open_synthetic_sqlite(path) as (connection, contract):
        guards = [rc._guard_of(contract)]
        raw = connection.connection.driver_connection
        result = export.export_snapshot(connection, destination(), driver_contract=contract, trusted_parent_ack=True)
        assert not raw.in_transaction
    assert result.published
    assert [event[0] for event in seen] == ['validate', 'publish']
    assert all(event[1] == {} and event[2] == [False] for event in seen)


def test_publish_exception_is_uncertain_without_abort(tmp_path, monkeypatch):
    aborts = []
    original_abort = files.OwnedDirectory.abort
    original_publish = files.OwnedDirectory.publish_marker

    def publish(self, data):
        original_publish(self, data)
        raise RuntimeError('after_effect')

    def abort(self):
        aborts.append(1)
        return original_abort(self)
    monkeypatch.setattr(files.OwnedDirectory, 'publish_marker', publish)
    monkeypatch.setattr(files.OwnedDirectory, 'abort', abort)
    dest = expect('snapshot_publish_outcome_uncertain', make_db(tmp_path))
    assert aborts == []
    assert Path(dest, 'manifest.json').exists()


def test_contract_single_use(tmp_path):
    path = make_db(tmp_path)
    with rc._open_synthetic_sqlite(path) as (connection, contract):
        export.export_snapshot(connection, destination(), driver_contract=contract, trusted_parent_ack=True)
        with pytest.raises(export.SnapshotExportError) as caught:
            export.export_snapshot(connection, destination(), driver_contract=contract, trusted_parent_ack=True)
        assert caught.value.code == 'driver_contract_required'


def _published_manifest(tmp_path):
    result, dest, _ = run(make_db(tmp_path, 9))
    return json.loads(Path(dest, 'manifest.json').read_bytes())


@pytest.mark.parametrize('change', [
    dict(snapshot_method='pg_repeatable_read_readonly_v1'),
    dict(snapshot_method='sqlite_readonly_snapshot_v2'),
    dict(source_version='synthetic-not-observed'),
    dict(source_version='3.45.x'),
    dict(source_version='1' * 33),
    dict(snapshot_method='synthetic_rows_v1'),
], ids=['pg-method-on-sqlite', 'unknown-method', 'synthetic-version', 'letters', 'long', 'synthetic-method-real-version'])
def test_manifest_method_and_version_bound(tmp_path, change):
    manifest = _published_manifest(tmp_path)
    if 'snapshot_method' in change:
        manifest['snapshot_method'] = change['snapshot_method']
    if 'source_version' in change:
        manifest['source']['version'] = change['source_version']
    raw = codec.canonical_json_bytes(manifest, max_bytes=2 << 20)
    with pytest.raises(export.SnapshotExportError) as caught:
        export._parse_manifest(raw, export.DEFAULT_LIMITS)
    assert caught.value.code == 'snapshot_manifest_invalid'


def test_real_manifest_parses(tmp_path):
    manifest = _published_manifest(tmp_path)
    raw = codec.canonical_json_bytes(manifest, max_bytes=2 << 20)
    parsed, profile, _ = export._parse_manifest(raw, export.DEFAULT_LIMITS)
    assert profile.profile_id == 'legacy_sqlite9_v1'


def test_synthetic_contract_export_is_marked_synthetic(tmp_path):
    # Review I3: a fixture export must be distinguishable from a real-source export.
    result, dest, _ = run(make_db(tmp_path, 9))
    manifest = json.loads(Path(dest, 'manifest.json').read_bytes())
    assert manifest['snapshot_method'] == 'sqlite_synthetic_readonly_snapshot_v1'
    report = export.validate_export(dest + os.sep + 'manifest.json', trusted_parent_ack=True)
    assert report.snapshot_method == 'sqlite_synthetic_readonly_snapshot_v1'


@pytest.mark.parametrize('dialect,method,ok', [
    ('pg', 'pg_repeatable_read_readonly_v1', True),
    ('pg', 'pg_synthetic_repeatable_read_readonly_v1', True),
    ('sqlite', 'sqlite_readonly_snapshot_v1', True),
    ('sqlite', 'sqlite_synthetic_readonly_snapshot_v1', True),
    ('pg', 'sqlite_readonly_snapshot_v1', False),
    ('sqlite', 'pg_repeatable_read_readonly_v1', False),
], ids=['pg', 'pg-synthetic', 'sqlite', 'sqlite-synthetic', 'sqlite-on-pg', 'pg-on-sqlite'])
def test_real_method_bound_to_descriptor_dialect(dialect, method, ok):
    # Review I1: descriptors use 'pg', not the SQLAlchemy name 'postgresql'.
    assert export._method_allowed(method, dialect) is ok
