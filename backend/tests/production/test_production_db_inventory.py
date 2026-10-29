"""Synthetic-only inventory checks. No app/config/real database fixtures."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tools import production_db_inventory as inv

SECRET = 'SENTINEL_credentials_email_url_password'


def legacy_schema(connection, *, drift=False):
    metadata = sa.MetaData()
    integers = {'downloads_used', 'limit', 'revision', 'file_size', 'duration_days', 'max_height'}
    epochs = {'created_at', 'expires_at', 'direct_expires_at', 'processed_at'}
    for name, columns in inv.LEGACY.items():
        fields = []
        pk = inv.UNIQUE[name][0]
        for column in columns.split():
            if drift and name == 'user' and column == 'password_hash':
                continue
            kind = sa.Integer() if column in integers else sa.String()
            if column in epochs and name in inv.EPOCHS:
                kind = sa.Float()
            if name == 'job' and column == 'progress':
                kind = sa.Float()
            fields.append(sa.Column(column, kind, primary_key=column in pk, nullable=column not in pk,
                                    server_default=sa.text("'" + SECRET + "'") if name == 'user' and column == 'email' else None))
        constraints = []
        if not drift:
            for cols in inv.UNIQUE[name][1:]:
                if set(cols) <= set(columns.split()):
                    constraints.append(sa.UniqueConstraint(*cols))
            for fields_fk, target, remote in inv.RELATIONS.get(name, []):
                if target in inv.LEGACY:
                    constraints.append(sa.ForeignKeyConstraint(fields_fk, [target + '.' + c for c in remote]))
        if drift and name == 'user':
            fields.append(sa.Column(SECRET, sa.String()))
            constraints.append(sa.CheckConstraint("email <> '" + SECRET + "'", name=SECRET))
        sa.Table(name, metadata, *fields, *constraints)
    metadata.create_all(connection)
    if drift:
        connection.exec_driver_sql('CREATE TABLE "' + SECRET + '" (value TEXT)')
    connection.commit()
    return metadata


@pytest.fixture
def connection():
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.connect() as con:
        yield con
    engine.dispose()


def test_original_nine_tables_schema_and_no_business_select(connection, tmp_path):
    legacy_schema(connection)
    statements = []
    sa.event.listen(connection, 'before_cursor_execute', lambda c, cur, s, p, ctx, many: statements.append(s))
    output = tmp_path / 'schema.json'
    report = inv.inventory_database(connection, schema_only=True, output=output).to_dict()
    assert set(report['schema']) == set(inv.LEGACY)
    assert report['missing_legacy_tables'] == []
    assert report['missing_protocol_tables'] == sorted(inv.PROTOCOL)
    assert report['known_business_table_count'] == report['known_table_count'] == 9
    assert report['known_business_table_counts'] == {'legacy': 9, 'protocol': 0, 'reconciliation': 0}
    assert report['connection_pragmas']['query_only'] == 1
    assert report['aggregates'] == {}
    assert report == json.loads(output.read_text())
    assert all(not item['missing_columns'] and not item['missing_unique'] and not item['missing_foreign_keys'] for item in report['schema'].values())
    assert not any(s.lstrip().upper().startswith('SELECT') and 'sqlite_master' not in s and 'sqlite_temp_master' not in s for s in statements)
    assert SECRET not in output.read_text()
    assert not connection.in_transaction()
    assert connection.connection.driver_connection.execute('PRAGMA query_only').fetchone()[0] == 0


def test_drift_redacts_unknown_objects_defaults_and_checks(connection, tmp_path):
    legacy_schema(connection, drift=True)
    result = inv.inventory_database(connection, schema_only=True, output=tmp_path / 'schema.json').to_dict()
    user = result['schema']['user']
    assert user['missing_columns'] == ['password_hash']
    assert user['unknown_column_count'] == 1
    assert user['missing_unique'] == [['email']]
    assert user['check_constraint_count'] == 1
    assert result['schema']['quota']['missing_foreign_keys']
    assert result['unknown_table_count'] == 1
    assert SECRET not in json.dumps(result)
    assert user['columns'][1]['default'] == 'present_redacted'


def test_aggregates_duplicates_orphans_states_time_no_repair(connection, tmp_path):
    tables = legacy_schema(connection, drift=True).tables
    connection.execute(tables['user'].insert(), [{'id': 'u1', 'email': SECRET + '_row'}, {'id': 'u2', 'email': SECRET + '_row'}])
    connection.execute(tables['quota'].insert(), [
        {'id': 'q1', 'user_id': 'missing', 'date': 'bad', 'downloads_used': -1, 'limit': 2},
        {'id': 'q2', 'user_id': 'missing', 'date': 'bad', 'downloads_used': 0, 'limit': 2}])
    connection.execute(tables['downloadaccess'].insert(), {'job_id': SECRET, 'max_height': -1})
    connection.execute(tables['job'].insert(), [
        {'id': 'j1', 'status': 'queued', 'created_at': '2000-01-01T00:00:00Z', 'updated_at': 'not-time', 'user_id': 'u1'},
        {'id': 'j2', 'status': SECRET, 'created_at': 'bad', 'updated_at': '2020-01-01', 'user_id': 'missing'}])
    connection.execute(tables['downloadidempotency'].insert(), [
        {'id': 'd1', 'state': 'pending', 'created_at': 0, 'user_id': 'u1'},
        {'id': 'd2', 'state': 'uncertain', 'created_at': -1, 'user_id': 'u1'}])
    connection.commit()
    before = connection.connection.driver_connection.total_changes
    report = inv.inventory_database(connection, schema_only=False, output=tmp_path / 'counts.json').to_dict()
    counts = report['aggregates']
    assert counts['user']['duplicate_groups'][1]['count'] == 1
    assert counts['quota']['duplicate_groups'][1]['count'] == 1
    assert counts['quota']['orphan_counts'][0]['count'] == 2
    assert counts['downloadaccess']['orphan_counts'][0]['count'] == 1
    assert counts['quota']['negative_counts']['downloads_used'] == 1
    assert counts['quota']['invalid_time_counts']['date'] == 2
    assert counts['job']['status_unknown_count'] == 1
    assert counts['job']['invalid_time_counts']['created_at'] == 1
    assert counts['job']['invalid_time_counts']['updated_at'] == 1
    assert counts['job']['queued_older_than_24h_count'] == 1
    assert counts['job']['legacy_job_count'] == 2
    assert counts['downloadidempotency']['pending_older_than_24h_count'] == 1
    assert counts['downloadidempotency']['state_counts']['uncertain'] == 1
    assert connection.connection.driver_connection.total_changes == before
    assert SECRET not in json.dumps(report)


def test_active_caller_transaction_is_untouched(connection, tmp_path):
    connection.exec_driver_sql('CREATE TABLE user (id TEXT)')
    connection.commit()
    txn = connection.begin()
    connection.exec_driver_sql('INSERT INTO user VALUES (?)', (SECRET,))
    with pytest.raises(inv.InventoryError, match='^active_transaction_refused$'):
        inv.inventory_database(connection, schema_only=True, output=tmp_path / 'absent.json')
    assert connection.get_transaction() is txn and txn.is_active
    assert connection.exec_driver_sql('SELECT COUNT(*) FROM user').scalar_one() == 1
    assert not (tmp_path / 'absent.json').exists()
    txn.rollback()


def test_query_only_setting_restored_if_already_enabled(connection, tmp_path):
    connection.connection.driver_connection.execute('PRAGMA query_only=ON')
    inv.inventory_database(connection, schema_only=True, output=tmp_path / 'empty.json')
    assert connection.connection.driver_connection.execute('PRAGMA query_only').fetchone()[0] == 1


def test_existing_and_invalid_output_refused_before_sql(connection, tmp_path):
    output = tmp_path / 'existing.json'
    output.write_text(SECRET)
    with pytest.raises(inv.InventoryError, match='^output_exists$'):
        inv.inventory_database(connection, schema_only=True, output=output)
    assert output.read_text() == SECRET
    with pytest.raises(inv.InventoryError, match='^output_path_invalid$'):
        inv.inventory_database(connection, schema_only=True, output=tmp_path / SECRET / 'x.json')
    assert not connection.in_transaction()


def test_output_symlink_refused(connection, tmp_path):
    target = tmp_path / 'target'
    target.mkdir()
    link = tmp_path / 'link'
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('OS symlink privilege unavailable')
    with pytest.raises(inv.InventoryError, match='^output_path_unsafe$'):
        inv.inventory_database(connection, schema_only=True, output=link / 'x.json')


def test_failed_inventory_sanitizes_error_and_removes_partial(connection, tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError(SECRET)
    monkeypatch.setattr(inv, '_reflect', fail)
    with pytest.raises(inv.InventoryError) as caught:
        inv.inventory_database(connection, schema_only=False, output=tmp_path / 'failure.json')
    assert str(caught.value) == 'inventory_failed'
    assert SECRET not in repr(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert list(tmp_path.iterdir()) == []
    assert not connection.in_transaction()
    assert connection.connection.driver_connection.execute('PRAGMA query_only').fetchone()[0] == 0


def test_atomic_publication_race_and_failure_clean_temp(tmp_path, monkeypatch):
    output = tmp_path / 'report.json'
    original_link = inv.os.link
    def race(source, destination):
        Path(destination).write_text(SECRET)
        return original_link(source, destination)
    monkeypatch.setattr(inv.os, 'link', race)
    with pytest.raises(inv.InventoryError, match='^output_exists$'):
        inv._publish(output, {'safe': True})
    assert output.read_text() == SECRET
    assert list(tmp_path.iterdir()) == [output]


def test_regular_file_sqlite_connection_refused(tmp_path):
    engine = sa.create_engine('sqlite:///' + (tmp_path / 'synthetic.db').as_posix())
    # No file connection opened: only the explicit URL precondition is exercised.
    con = MagicMock(spec=sa.engine.Connection)
    con.closed = False
    con.in_transaction.return_value = False
    con.engine = engine
    con.dialect = engine.dialect
    with pytest.raises(inv.InventoryError, match='^sqlite_readonly_uri_required$'):
        inv.inventory_database(con, schema_only=True, output=tmp_path / 'absent.json')
    assert not (tmp_path / 'synthetic.db').exists()
    engine.dispose()


def test_version_heads_known_only_and_unknown_redacted(connection, tmp_path):
    connection.exec_driver_sql('CREATE TABLE alembic_version (version_num TEXT)')
    connection.exec_driver_sql('INSERT INTO alembic_version VALUES (?), (?)', ('b1b_0003', SECRET))
    connection.commit()
    with pytest.raises(inv.InventoryError, match='^unknown_version_head$') as error:
        inv.inventory_database(connection, schema_only=True, output=tmp_path / 'v.json')
    assert SECRET not in str(error.value)
    assert not (tmp_path / 'v.json').exists()
    assert not connection.in_transaction()


def test_pg_reflection_uses_app_schema_and_redacts_objects(monkeypatch):
    class FakeInspector:
        def get_table_names(self, *, schema):
            assert schema == 'app'
            return ['user', SECRET]
        def get_columns(self, name, *, schema):
            return [{'name': 'id', 'type': sa.String(), 'nullable': False, 'default': SECRET},
                    {'name': SECRET, 'type': sa.String(), 'nullable': True}]
        def get_pk_constraint(self, *args, **kwargs):
            return {'name': SECRET, 'constrained_columns': ['id']}
        def get_unique_constraints(self, *args, **kwargs):
            return [{'name': SECRET, 'column_names': [SECRET]}]
        def get_indexes(self, *args, **kwargs):
            return []
        def get_foreign_keys(self, *args, **kwargs):
            return [{'constrained_columns': [SECRET], 'referred_table': SECRET, 'referred_columns': [SECRET]}]
        def get_check_constraints(self, *args, **kwargs):
            return [{'name': SECRET, 'sqltext': SECRET}]
    monkeypatch.setattr(inv, 'inspect', lambda con: FakeInspector())
    tables, metadata, unknown = inv._reflect(object(), 'app')
    assert tables['user'].schema == 'app'
    assert unknown == 1
    assert SECRET not in json.dumps(metadata)


def test_pg_aggregate_statements_compile_bound_and_no_business_rows():
    # Fake transport checks SQL shape only, never claims a PostgreSQL execution.
    tables = {}
    for name, fields in inv.FIELDS.items():
        if name == 'alembic_version':
            continue
        numeric = set(inv.NONNEGATIVE.get(name, '').split()) | set(inv.EPOCHS.get(name, '').split())
        columns = [sa.Column(c, sa.Float() if c in numeric else sa.DateTime(timezone=True) if c in inv.TIMES.get(name, '').split() else sa.String()) for c in fields]
        tables[name] = sa.Table(name, sa.MetaData(), *columns, schema='app')
    statements = []
    class FakePG:
        dialect = SimpleNamespace(name='postgresql')
        def execute(self, stmt):
            compiled = stmt.compile(dialect=postgresql.dialect())
            sql = str(compiled)
            assert sql.startswith('SELECT count(')
            assert 'app.' in sql
            assert 'queued' not in sql and 'pending' not in sql
            statements.append(compiled)
            return SimpleNamespace(scalar_one=lambda: 0)
    data = inv._aggregates(FakePG(), tables, datetime.now(timezone.utc))
    assert 100 < len(statements) <= inv.MAX_QUERIES == 800
    assert data['billinginbox']['status_counts']['needs_review'] == 0
    assert all(SECRET not in str(stmt) for stmt in statements)


def test_pg_snapshot_order_and_caller_connection_not_closed(tmp_path, monkeypatch):
    connection = MagicMock(spec=sa.engine.Connection)
    connection.closed = False
    connection.in_transaction.return_value = False
    raw = SimpleNamespace(autocommit=False, isolation_level=None,
                          info=SimpleNamespace(transaction_status=0))
    connection.connection = SimpleNamespace(driver_connection=raw)
    connection.get_execution_options.return_value = {}
    connection.dialect = SimpleNamespace(name='postgresql', driver='psycopg', server_version_info=(17, 0),
                                        set_isolation_level=lambda driver, level: events.append({'isolation_level': level}))
    connection.get_isolation_level.return_value = 'READ COMMITTED'
    connection.engine = MagicMock()
    connection.engine._should_log_info.return_value = False
    connection.engine._should_log_debug.return_value = False
    events = []
    connection.execution_options.side_effect = lambda **kw: events.append(kw)
    connection.begin.side_effect = lambda: events.append('begin') or MagicMock()
    connection.exec_driver_sql.side_effect = lambda sql: events.append(sql)
    def reflect(con, schema):
        assert schema == 'app'
        events.append('reflect')
        return {}, {}, 0
    monkeypatch.setattr(inv, '_reflect', reflect)
    inv.inventory_database(connection, schema_only=True, output=tmp_path / 'pg.json')
    assert events == [{'isolation_level': 'REPEATABLE READ'}, 'begin', 'SET TRANSACTION READ ONLY', 'reflect']
    assert raw.autocommit is False and raw.isolation_level is None
    connection.close.assert_not_called()


def test_cli_never_echoes_password_dsn(capsys):
    assert inv.main(['--dsn', 'postgresql://user:' + SECRET + '@host/db']) == 2
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert inv.main(['--help']) == 0
    assert 'API only' in capsys.readouterr().out


def test_raw_caller_transaction_is_also_untouched(connection, tmp_path):
    raw = connection.connection.driver_connection
    raw.execute('BEGIN')
    with pytest.raises(inv.InventoryError, match='^active_transaction_refused$'):
        inv.inventory_database(connection, schema_only=True, output=tmp_path / 'raw.json')
    assert raw.in_transaction
    assert raw.execute('PRAGMA query_only').fetchone()[0] == 0
    raw.rollback()


def test_sqlite_snapshot_begins_and_enforces_database_readonly(connection, tmp_path, monkeypatch):
    connection.exec_driver_sql('CREATE TABLE user (id TEXT)')
    connection.commit()
    def forbidden_write(con, schema):
        assert schema == 'main'
        assert con.connection.driver_connection.in_transaction
        con.exec_driver_sql('INSERT INTO main.user VALUES (?)', (SECRET,))
    monkeypatch.setattr(inv, '_reflect', forbidden_write)
    with pytest.raises(inv.InventoryError, match='^inventory_failed$'):
        inv.inventory_database(connection, schema_only=False, output=tmp_path / 'write.json')
    assert connection.exec_driver_sql('SELECT COUNT(*) FROM user').scalar_one() == 0
    assert not (tmp_path / 'write.json').exists()


def test_temp_table_cannot_shadow_main_inventory(connection, tmp_path):
    connection.exec_driver_sql('CREATE TABLE main.user (id TEXT PRIMARY KEY)')
    connection.exec_driver_sql('CREATE TEMP TABLE user (secret TEXT)')
    connection.exec_driver_sql('INSERT INTO temp.user VALUES (?)', (SECRET,))
    connection.commit()
    data = inv.inventory_database(connection, schema_only=False, output=tmp_path / 'main.json').to_dict()
    assert data['aggregates']['user']['row_count'] == 0
    assert data['schema']['user']['unknown_column_count'] == 0


def test_reparse_attribute_is_rejected_portably(tmp_path, monkeypatch):
    original = Path.lstat
    def fake_lstat(path):
        value = original(path)
        if path == tmp_path:
            return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
        return value
    monkeypatch.setattr(Path, 'lstat', fake_lstat)
    with pytest.raises(inv.InventoryError, match='^output_path_unsafe$'):
        inv._path_check(tmp_path / 'reparse.json')


def test_debug_sql_logging_is_refused(connection, tmp_path):
    connection.engine.echo = 'debug'
    with pytest.raises(inv.InventoryError, match='^sql_logging_refused$'):
        inv.inventory_database(connection, schema_only=True, output=tmp_path / 'debug.json')


@pytest.mark.parametrize('fail', [False, True])
def test_pg_autocommit_and_full_options_restore_offline(tmp_path, monkeypatch, fail):
    """Stateful fake reproduces the driver/SQLAlchemy isolation distinction."""
    connection = MagicMock(spec=sa.engine.Connection)
    connection.closed = False
    connection.in_transaction.return_value = False
    raw = SimpleNamespace(autocommit=True, isolation_level=None,
                          info=SimpleNamespace(transaction_status=0))
    connection.connection = SimpleNamespace(driver_connection=raw)
    options = {'isolation_level': 'AUTOCOMMIT', 'stream_results': True}
    connection.get_execution_options.side_effect = lambda: options.copy()
    connection.get_isolation_level.return_value = 'READ COMMITTED'
    def change(level):
        raw.autocommit = level == 'AUTOCOMMIT'
        raw.isolation_level = None if raw.autocommit else level
    connection.execution_options.side_effect = lambda **kw: (options.update(kw), change(kw['isolation_level']))
    connection.dialect = SimpleNamespace(name='postgresql', driver='psycopg', server_version_info=(18, 6),
                                        set_isolation_level=lambda driver, level: change(level))
    connection.engine = MagicMock()
    connection.engine._should_log_info.return_value = False
    connection.engine._should_log_debug.return_value = False
    def reflect(con, schema):
        assert raw.autocommit is False
        if fail:
            raise RuntimeError(SECRET)
        return {}, {}, 0
    monkeypatch.setattr(inv, '_reflect', reflect)
    if fail:
        with pytest.raises(inv.InventoryError, match='^inventory_failed$'):
            inv.inventory_database(connection, schema_only=True, output=tmp_path / 'pg.json')
    else:
        inv.inventory_database(connection, schema_only=True, output=tmp_path / 'pg.json')
    assert raw.autocommit is True
    assert raw.isolation_level is None
    assert connection.get_execution_options() == {'isolation_level': 'AUTOCOMMIT', 'stream_results': True}
    connection.close.assert_not_called()


def test_pg_restore_failure_is_explicit_and_no_report_published(tmp_path, monkeypatch):
    class Driver:
        autocommit = True
        info = SimpleNamespace(transaction_status=0)
        _isolation = None
        @property
        def isolation_level(self):
            return self._isolation
        @isolation_level.setter
        def isolation_level(self, value):
            if value is None:
                raise RuntimeError(SECRET)
            self._isolation = value
    raw = Driver()
    con = MagicMock(spec=sa.engine.Connection)
    con.closed = False
    con.in_transaction.return_value = False
    con.connection = SimpleNamespace(driver_connection=raw)
    con.get_execution_options.return_value = {'isolation_level': 'AUTOCOMMIT'}
    con.engine = MagicMock()
    con.engine._should_log_info.return_value = False
    con.engine._should_log_debug.return_value = False
    def change(driver, level):
        driver.autocommit = False
        driver.isolation_level = level
    con.dialect = SimpleNamespace(name='postgresql', driver='psycopg', server_version_info=(18,6), set_isolation_level=change)
    monkeypatch.setattr(inv, '_reflect', lambda *_: ({}, {}, 0))
    with pytest.raises(inv.InventoryError, match='^connection_restore_failed$') as caught:
        inv.inventory_database(con, schema_only=True, output=tmp_path/'absent.json')
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert raw.autocommit is True  # attempted even when restoring isolation fails
    assert not (tmp_path/'absent.json').exists()
    con.close.assert_not_called()


def synthetic_inventory_schema(connection, *, reconciliation):
    """Deliberately unconstrained synthetic rows test anomaly counts, never repair."""
    metadata = sa.MetaData()
    names = set(inv.LEGACY) | set(inv.PROTOCOL)
    if reconciliation:
        names |= {'billingreconciliationtask', 'billingreconciliationaudit'}
    for name in sorted(names):
        numeric = set(inv.NONNEGATIVE.get(name, '').split()) | set(inv.EPOCHS.get(name, '').split())
        columns = [sa.Column(field, sa.Float() if field in numeric else sa.String())
                   for field in sorted(inv.FIELDS[name])]
        if name == 'billingreconciliationtask':
            columns.append(sa.Column(SECRET, sa.String(), server_default=sa.text("'" + SECRET + "'")))
            sa.Table(name, metadata, *columns, sa.CheckConstraint("status <> '" + SECRET + "_schema_constraint'", name=SECRET))
        else:
            sa.Table(name, metadata, *columns)
    sa.Table('alembic_version', metadata, sa.Column('version_num', sa.String()))
    metadata.create_all(connection)
    connection.execute(metadata.tables['alembic_version'].insert(), {'version_num': 'b3b_0004' if reconciliation else 'b1b_0003'})
    connection.commit()
    return metadata.tables


@pytest.mark.parametrize('reconciliation,counts', [(False, (15, 16)), (True, (17, 18))])
def test_exact_old_and_new_inventory_table_groups(connection, tmp_path, reconciliation, counts):
    synthetic_inventory_schema(connection, reconciliation=reconciliation)
    result = inv.inventory_database(connection, schema_only=True, output=tmp_path/'groups.json').to_dict()
    assert result['known_business_table_count'] == counts[0]
    assert result['known_table_count'] == counts[1]
    assert result['known_business_table_counts'] == {'legacy': 9, 'protocol': 6, 'reconciliation': 2 if reconciliation else 0}
    assert result['missing_reconciliation_tables'] == ([] if reconciliation else ['billingreconciliationaudit', 'billingreconciliationtask'])
    assert result['unknown_table_count'] == 0
    assert result['version_heads'] == ['b3b_0004' if reconciliation else 'b1b_0003']
    assert SECRET not in json.dumps(result)


def test_b3b_actual_models_sqlite_schema_only(connection, tmp_path):
    # Models have no app config/db import; SQLite is metadata evidence only.
    from app.models import SQLModel
    SQLModel.metadata.create_all(connection)
    connection.exec_driver_sql('CREATE TABLE alembic_version (version_num TEXT)')
    connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('b3b_0004')")
    connection.commit()
    statements = []
    sa.event.listen(connection, 'before_cursor_execute', lambda c, cur, s, p, ctx, many: statements.append(s))
    result = inv.inventory_database(connection, schema_only=True, output=tmp_path/'models.json').to_dict()
    assert (result['known_business_table_count'], result['known_table_count']) == (17, 18)
    assert len(result['schema']) == 18 and result['aggregates'] == {}
    for name in ('billingreconciliationtask', 'billingreconciliationaudit'):
        assert {column['name'] for column in result['schema'][name]['columns']} == inv.FIELDS[name]
        assert result['schema'][name]['unknown_column_count'] == 0
        assert not result['schema'][name]['missing_columns']
        assert not result['schema'][name]['missing_unique']
        assert not result['schema'][name]['missing_foreign_keys']
        assert result['schema'][name]['check_expressions'] == 'redacted'
    audit = result['schema']['billingreconciliationaudit']
    assert any(index['partial'] and index['unique'] and index['columns'] == ['task_id', 'event_kind'] for index in audit['indexes'])
    assert ['task_id', 'event_kind'] not in audit['missing_unique']
    selects = [s for s in statements if s.lstrip().upper().startswith('SELECT')]
    assert all('sqlite_master' in s or 'sqlite_temp_master' in s or 'main.alembic_version' in s for s in selects)


def test_b3b_aggregates_anomalies_and_sensitive_values_never_escape(connection, tmp_path):
    tables = synthetic_inventory_schema(connection, reconciliation=True)
    task = tables['billingreconciliationtask']
    audit = tables['billingreconciliationaudit']
    sensitive = {'id', 'checkout_id', 'user_id', 'task_id', 'provider_account_scope', 'actor_ref',
                 'reason_code', 'evidence_ref', 'owner_ref', 'input_sha256', 'query_json', 'policy_json',
                 'outcome_reason', 'projection_json', 'projection_sha256'}
    for table, state_field, states in ((task, 'status', ('running', 'verified', 'needs_review', 'unexpected')),
                                       (audit, 'event_kind', ('task_started', 'get_reserved', 'get_observed', 'task_finished', 'unexpected'))):
        for index, state in enumerate(states):
            row = {field: SECRET + '_' + field + '_' + str(index) for field in sensitive if field in table.c}
            row.update({field: -1 if index == 0 else index for field in inv.NONNEGATIVE[table.name].split()})
            row.update({field: 'not-time' if index == 0 else '2026-01-01T00:00:00Z' for field in inv.TIMES[table.name].split()})
            row[state_field] = SECRET if state == 'unexpected' else state
            connection.execute(table.insert(), row)
    connection.commit()
    before = connection.connection.driver_connection.total_changes
    statements = []
    sa.event.listen(connection, 'before_cursor_execute', lambda c, cur, s, p, ctx, many: statements.append(s))
    output = tmp_path/'b3b-counts.json'
    result = inv.inventory_database(connection, schema_only=False, output=output).to_dict()
    assert SECRET not in output.read_text() and SECRET not in json.dumps(result)
    assert connection.connection.driver_connection.total_changes == before
    counts = result['aggregates']
    assert counts[task.name]['row_count'] == 4
    assert counts[task.name]['status_counts'] == {'running': 1, 'verified': 1, 'needs_review': 1}
    assert counts[task.name]['status_unknown_count'] == 1
    assert counts[audit.name]['row_count'] == 5
    assert counts[audit.name]['event_kind_counts'] == {'task_started': 1, 'get_reserved': 1, 'get_observed': 1, 'task_finished': 1}
    assert counts[audit.name]['event_kind_unknown_count'] == 1
    for name in (task.name, audit.name):
        assert set(counts[name]['negative_counts'].values()) == {1}
        assert set(counts[name]['invalid_time_counts'].values()) == {1}
        assert set(item['count'] for item in counts[name]['orphan_counts']) == {4 if name == task.name else 5}
        for field in sensitive:
            assert field not in counts[name]  # No sensitive-field grouping/projection.
    aggregate_sql = [s for s in statements if s.startswith('SELECT count(')]
    assert 100 < len(aggregate_sql) <= inv.MAX_QUERIES == 800


@pytest.mark.parametrize('heads', [('b1_0001',), ('b1b_0002',), ('b1b_0003',), ('b3b_0004',), ('b1b_0003', 'b3b_0004')])
def test_known_heads_are_observed_without_claiming_migration_validity(connection, tmp_path, heads):
    connection.exec_driver_sql('CREATE TABLE alembic_version (version_num TEXT)')
    for head in heads:
        connection.exec_driver_sql('INSERT INTO alembic_version VALUES (?)', (head,))
    connection.commit()
    result = inv.inventory_database(connection, schema_only=True, output=tmp_path/'heads.json').to_dict()
    assert result['version_heads'] == sorted(heads)
    assert result['known_business_table_count'] == 0
    assert result['unknown_version_head_count'] == 0
    assert result['missing_legacy_tables'] == sorted(inv.LEGACY)
