"""E2 gate D: contract-gated PG export on nonce-owned isolated databases; run via run_b6_e2_export_pg.py."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import pytest
from sqlalchemy import text

from tools import production_db_export as export
from tools import production_db_snapshot_format as codec
import tools.production_db_snapshot_read_contract as rc
import tools.production_db_snapshot_rows as rows
from tools.production_db_snapshot_profiles import SOURCE_PROFILES

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
HEADS = ('b1_0001', 'b1b_0002', 'b1b_0003', 'b3b_0004')
STAMP = datetime(2026, 10, 25, 1, 2, 3, 123456, tzinfo=timezone.utc)


def seed(case):
    with case.migration.begin() as connection:
        connection.execute(text('SET LOCAL search_path=app'))
        connection.execute(text('INSERT INTO "user" (id,email,password_hash,created_at) VALUES '
            "('u1','a@example.com','h1',:t),('u2','bé\U0001f600@example.com','',:t)"), {'t': STAMP})
        connection.execute(text('INSERT INTO membership (user_id,customer_id,subscription_id,status,expires_at,'
            'cancel_at_period_end,active_checkout_id,revision,entitlement_source) VALUES '
            "('u1',NULL,NULL,'active','-0'::float8,true,NULL,7,NULL)"))  # numeric -0.0 has no sign
        connection.execute(text('INSERT INTO job (id,url,title,format_id,status,progress,file_path,file_size,'
            'error_type,error,created_at,updated_at,expires_at,user_id) VALUES '
            "('j1','https://example.invalid/v',NULL,NULL,'done',0.5,NULL,1099511627776,NULL,NULL,:t,:t,NULL,'u1')"),
            {'t': STAMP})


def destination():
    return os.environ['B6_BUNDLE_PARENT'] + os.sep + 'pg-' + uuid.uuid4().hex[:12]


def oracle(case, table):
    with case.migration.connect() as connection:
        raw = connection.connection.driver_connection
        order = ','.join('"' + name + '"' for name in table.primary_key)
        with raw.cursor() as cursor:
            cursor.execute(f'SELECT * FROM app."{table.name}" ORDER BY {order}')
            return [tuple(row) for row in cursor.fetchall()]


def decoded(dest, manifest, profile):
    result = {}
    for table, doc in zip(rows.table_order(profile.descriptor), manifest['tables']):
        tags = export._tags(profile, table)
        values = []
        for name in doc['chunks']:
            for line in Path(dest, name).read_bytes().splitlines(keepends=True):
                values.append(tuple(codec.decode_row(line, allowed_tags=tags)))
        result[table.name] = values
    return result


GUCS = ('statement_timeout', 'lock_timeout', 'TimeZone', 'DateStyle', 'IntervalStyle', 'search_path',
        'extra_float_digits')


def session_settings(raw):
    values = tuple(raw.execute('SHOW ' + name).fetchone()[0] for name in GUCS)
    raw.rollback()
    return values


def export_capture(case, dest=None, isolation=None, **kwargs):
    """Export and capture connection state right after it returns or raises (review I3)."""
    dest = dest or destination()
    result = error = None
    with rc._open_synthetic_pg(case.migration.url) as (connection, contract):
        raw = connection.connection.driver_connection
        if isolation is not None:
            raw.isolation_level = isolation
        before = (raw.autocommit, raw.isolation_level, dict(connection.get_execution_options()),
                  session_settings(raw))
        try:
            result = export.export_snapshot(connection, dest, driver_contract=contract,
                                            trusted_parent_ack=True, **kwargs)
        except export.SnapshotExportError as caught:
            error = caught
        status = int(raw.info.transaction_status)  # before this test runs any SQL
        after = (raw.autocommit, raw.isolation_level, dict(connection.get_execution_options()),
                 session_settings(raw))
        restored = (before == after, status, rc._guard_of(contract).installed, contract._state)
    return result, error, dest, restored


def export_case(case, dest=None, **kwargs):
    result, error, dest, restored = export_capture(case, dest, **kwargs)
    if error is not None:
        raise error
    return result, dest, restored


RESTORED = (True, 0, False, 'consumed')


@pytest.mark.parametrize('head', HEADS)
def test_four_heads_export_and_match_oracle(head):
    from b3b_pg_helpers import isolated_database
    with isolated_database(target=head) as case:
        seed(case)
        result, dest, restored = export_case(case)
        assert restored == RESTORED
        assert result.published and result.error_codes == ()
        profile = SOURCE_PROFILES['pg_' + head + '_v1']
        report = export.validate_export(dest + os.sep + 'manifest.json', trusted_parent_ack=True)
        assert report.accepted and report.schema_profile == profile.profile_id
        assert report.snapshot_method == 'pg_synthetic_repeatable_read_readonly_v1'
        manifest = json.loads(Path(dest, 'manifest.json').read_bytes())
        assert manifest['source']['dialect'] == 'pg' and manifest['source']['version'].startswith('18.')
        got = decoded(dest, manifest, profile)
        for table in rows.table_order(profile.descriptor):
            if table.name == 'alembic_version':
                assert got[table.name] == [(head,)]
            else:
                assert got[table.name] == oracle(case, table)
        assert got['user'][1][1] == 'bé\U0001f600@example.com'
        assert got['user'][0][3] == STAMP
        membership = got['membership'][0]
        assert membership[5] is True and str(membership[4]) == '-0.0'
        assert got['job'][0][7] == 1099511627776


def test_named_cursor_gucs_and_snapshot_isolation(monkeypatch):
    from b3b_pg_helpers import isolated_database
    evidence = {}
    with isolated_database(target='b3b_0004') as case:
        seed(case)
        original_preflight = rows.SnapshotRows.preflight
        original_fetch = rows._fetchone

        def preflight_then_concurrent_write(self):
            summary = original_preflight(self)
            with case.migration.begin() as other:
                other.execute(text('INSERT INTO app."user" (id,email,password_hash,created_at) '
                                   "VALUES ('u9','z@example.com','h',now())"))
                other.execute(text('DELETE FROM app.membership'))
            return summary

        def fetch_with_evidence(cursor):
            if 'cursors' not in evidence and getattr(cursor, 'name', None):
                connection = cursor.connection
                evidence['cursors'] = connection.execute(
                    'SELECT name,is_holdable,is_scrollable FROM pg_catalog.pg_cursors').fetchall()
                evidence['own'] = (cursor.name, type(cursor).__name__, cursor.itersize)
                evidence['gucs'] = tuple(connection.execute('SHOW ' + name).fetchone()[0] for name in (
                    'statement_timeout', 'lock_timeout', 'TimeZone', 'DateStyle', 'IntervalStyle',
                    'search_path', 'transaction_read_only', 'transaction_isolation', 'extra_float_digits'))
            return original_fetch(cursor)
        monkeypatch.setattr(rows.SnapshotRows, 'preflight', preflight_then_concurrent_write)
        monkeypatch.setattr(rows, '_fetchone', fetch_with_evidence)
        result, dest, restored = export_case(case)
        assert restored == RESTORED and result.published
        manifest = json.loads(Path(dest, 'manifest.json').read_bytes())
        got = decoded(dest, manifest, SOURCE_PROFILES['pg_b3b_0004_v1'])
        assert [row[0] for row in got['user']] == ['u1', 'u2']
        assert len(got['membership']) == 1
        assert [row[0] for row in oracle(case, next(t for t in rows.table_order(
            SOURCE_PROFILES['pg_b3b_0004_v1'].descriptor) if t.name == 'user'))] == ['u1', 'u2', 'u9']
    name, kind, itersize = evidence['own']
    assert kind == 'ServerCursor' and itersize == 1
    assert (name, False, False) in [tuple(row) for row in evidence['cursors']]
    timeout, lock, zone, style, interval, path, read_only, isolation, float_digits = evidence['gucs']
    assert timeout.endswith('ms') or timeout.endswith('s')
    assert float_digits == '3'
    assert lock == '1s' and zone == 'UTC' and style == 'ISO, YMD' and interval == 'iso_8601'
    assert path == 'pg_catalog' and read_only == 'on' and isolation == 'repeatable read'


def test_server_statement_timeout_maps_to_resource_limit(monkeypatch):
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='b1_0001') as case:
        monkeypatch.setattr(rc, '_STATEMENT_SECONDS', 1)
        original = rows._pg_count_sql
        reached = []

        def slow_count(table, namespace='app'):
            from psycopg import sql
            reached.append(table.name)
            return sql.SQL('SELECT ({}), pg_catalog.pg_sleep(3)').format(original(table, namespace))
        monkeypatch.setattr(rows, '_pg_count_sql', slow_count)
        result, error, dest, restored = export_capture(case)
        assert error is not None and error.code == 'snapshot_resource_limit'
        assert len(reached) == 1  # the server cancelled the first count, not a catalog-phase timeout
        assert error.__context__ is None and error.__cause__ is None
        assert restored == RESTORED and not os.path.exists(dest)


@pytest.mark.parametrize('mutation', ['dict_row', 'loader', 'autocommit', 'cursor_factory'])
def test_observable_psycopg_drift_refused(mutation):
    from b3b_pg_helpers import isolated_database
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.string import TextLoader
    with isolated_database(target='b1_0001') as case:
        with rc._open_synthetic_pg(case.migration.url) as (connection, contract):
            raw = connection.connection.driver_connection
            if mutation == 'dict_row':
                raw.row_factory = dict_row
            elif mutation == 'loader':
                class Custom(TextLoader):
                    pass
                raw.adapters.register_loader('text', Custom)
            elif mutation == 'autocommit':
                raw.autocommit = True
            else:
                class OtherCursor(psycopg.Cursor):
                    pass
                raw.cursor_factory = OtherCursor
            with pytest.raises(export.SnapshotExportError) as caught:
                export.export_snapshot(connection, destination(), driver_contract=contract, trusted_parent_ack=True)
            assert caught.value.code == 'driver_contract_required'


def test_pg_bootstrap_refuses_non_loopback_and_options():
    from sqlalchemy import URL
    for url in (URL.create('postgresql+psycopg', username='x', password='y', host='10.0.0.1', port=5432, database='d'),
                URL.create('postgresql+psycopg', username='x', password='y', host='127.0.0.1', port=5432,
                           database='d', query={'options': '-c search_path=evil'}),
                URL.create('postgresql+psycopg2', username='x', password='y', host='127.0.0.1', port=5432, database='d'),
                'postgresql+psycopg://x:y@127.0.0.1/d'):
        with pytest.raises(ValueError):
            with rc._open_synthetic_pg(url):
                pytest.fail('unexpected connection')


@pytest.mark.parametrize('statement', [
    "UPDATE membership SET expires_at='Infinity'::float8",
    "UPDATE membership SET expires_at='NaN'::float8",
    "UPDATE job SET created_at='infinity'::timestamptz",
], ids=['float-inf', 'float-nan', 'timestamptz-infinity'])
def test_non_python_values_refused_before_target(statement, monkeypatch):
    from b3b_pg_helpers import isolated_database
    from tools import production_db_snapshot_files as files
    reserved = []
    original = files.reserve_directory
    monkeypatch.setattr(files, 'reserve_directory', lambda *a, **k: reserved.append(1) or original(*a, **k))
    with isolated_database(target='b1_0001') as case:
        seed(case)
        with case.migration.begin() as connection:
            connection.execute(text('SET LOCAL search_path=app'))
            connection.execute(text(statement))
        dest = destination()
        with pytest.raises(export.SnapshotExportError) as caught:
            export_case(case, dest)
        assert caught.value.code == 'source_codec_unsupported'
        assert reserved == [] and not os.path.exists(dest)


@pytest.mark.parametrize('isolation', [None, 'READ_UNCOMMITTED', 'READ_COMMITTED', 'REPEATABLE_READ', 'SERIALIZABLE'])
def test_export_restores_connection_state_from_each_isolation(isolation):
    # Review I3: isolation/autocommit/execution options and session settings are restored.
    from b3b_pg_helpers import isolated_database
    from psycopg import IsolationLevel
    with isolated_database(target='b1_0001') as case:
        seed(case)
        result, error, dest, restored = export_capture(
            case, isolation=None if isolation is None else IsolationLevel[isolation])
        assert error is None and result.published and restored == RESTORED


def test_lock_timeout_maps_to_resource_limit_and_restores():
    # Review I3: a real row lock wait ends at lock_timeout (1 s), not statement_timeout (10 s).
    import time
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='b1_0001') as case:
        seed(case)
        with case.migration.connect() as holder:
            transaction = holder.begin()
            holder.execute(text('LOCK TABLE app.job IN ACCESS EXCLUSIVE MODE'))
            started = time.monotonic()
            try:
                result, error, dest, restored = export_capture(case)
            finally:
                elapsed = time.monotonic() - started
                transaction.rollback()
        assert error is not None and error.code == 'snapshot_resource_limit'
        assert elapsed < 8 and restored == RESTORED and not os.path.exists(dest)


def test_float8_exact_despite_database_extra_float_digits():
    # Review I1: a database-level extra_float_digits=0 must not round exported float8 values.
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='b1_0001') as case:
        seed(case)
        with case.migration.begin() as connection:
            connection.execute(text('ALTER DATABASE "' + case.database + '" SET extra_float_digits = 0'))
            connection.execute(text('UPDATE app.membership SET expires_at = 1761360123.4567891::float8'))
        result, dest, restored = export_case(case)
        assert restored == RESTORED
        with case.migration.connect() as connection:
            raw = connection.connection.driver_connection
            with raw.cursor(binary=True) as cursor:  # independent binary-protocol oracle
                cursor.execute('SELECT expires_at FROM app.membership')
                exact = cursor.fetchone()[0]
        manifest = json.loads(Path(dest, 'manifest.json').read_bytes())
        got = decoded(dest, manifest, SOURCE_PROFILES['pg_b1_0001_v1'])
        assert got['membership'][0][4] == exact and exact != round(exact, 5)


def test_pg_bootstrap_refuses_libpq_environment_options(monkeypatch):
    # Review I2: libpq environment defaults must not silently change the recorded construction.
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='b1_0001') as case:
        monkeypatch.setenv('PGOPTIONS', '-c extra_float_digits=0')
        with pytest.raises(ValueError):
            with rc._open_synthetic_pg(case.migration.url):
                pytest.fail('contract issued under PGOPTIONS')
