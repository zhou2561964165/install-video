"""Synthetic-only E0 transaction contract; no application/database configuration."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

from tools import production_db_inventory as inv
from tools import production_db_snapshot as snap

SECRET = 'B6_E0_SYNTHETIC_PRIVATE_password_email_url'


def safe_error(error, code):
    assert type(error) is snap.SnapshotConnectionError
    assert str(error) == code
    assert error.__context__ is None and error.__cause__ is None
    assert SECRET not in repr(error)


@pytest.fixture
def connection():
    engine = sa.create_engine('sqlite:///:memory:')
    with engine.connect() as con:
        yield con
    engine.dispose()


@pytest.mark.parametrize('query_only', [0, 1])
def test_sqlite_begin_readonly_token_and_exact_restore(connection, query_only):
    raw = connection.connection.driver_connection
    raw.execute('PRAGMA query_only=' + str(query_only))
    before = dict(connection.get_execution_options())
    with snap.readonly_snapshot(connection) as token:
        assert token.connection is connection
        assert token.schema_scope == 'main' and token.dialect == 'sqlite'
        assert token.assert_active() is None
        assert raw.in_transaction and connection.in_transaction()
        assert raw.execute('PRAGMA query_only').fetchone()[0] == 1
        with pytest.raises(sa.exc.DBAPIError):
            connection.exec_driver_sql('CREATE TABLE forbidden (value TEXT)')
        for attr in ('connection', 'schema_scope', 'dialect'):
            with pytest.raises(AttributeError):
                setattr(token, attr, SECRET)
    assert not raw.in_transaction and not connection.in_transaction()
    assert not connection.closed
    assert raw.execute('PRAGMA query_only').fetchone()[0] == query_only
    assert dict(connection.get_execution_options()) == before
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        token.assert_active()
    safe_error(caught.value, 'snapshot_inactive')
    with pytest.raises(snap.SnapshotConnectionError, match='^snapshot_inactive$'):
        _ = token.connection


@pytest.mark.parametrize('raw_only', [False, True])
def test_caller_transaction_rejected_without_rollback(connection, raw_only):
    raw = connection.connection.driver_connection
    tx = None if raw_only else connection.begin()
    if raw_only:
        raw.execute('BEGIN')
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(connection):
            pytest.fail('Caller-owned transaction accepted')
    safe_error(caught.value, 'active_transaction_refused')
    assert connection.get_transaction() is tx
    assert raw.in_transaction if raw_only else tx.is_active
    assert raw.execute('PRAGMA query_only').fetchone()[0] == 0
    (raw if raw_only else tx).rollback()


@pytest.mark.parametrize('failure', [RuntimeError(SECRET), inv.InventoryError('schema_limit_exceeded'),
                                     KeyboardInterrupt(), SystemExit(37)])
def test_body_exception_is_preserved_and_state_restored(connection, failure):
    raw = connection.connection.driver_connection
    with pytest.raises(type(failure)) as caught:
        with snap.readonly_snapshot(connection) as token:
            raise failure
    assert caught.value is failure
    assert not connection.in_transaction() and not raw.in_transaction
    assert raw.execute('PRAGMA query_only').fetchone()[0] == 0
    with pytest.raises(snap.SnapshotConnectionError, match='^snapshot_inactive$'):
        token.assert_active()


def test_token_rejects_other_thread_and_pid(connection, monkeypatch):
    with snap.readonly_snapshot(connection) as token:
        with ThreadPoolExecutor(max_workers=1) as executor:
            def use_token():
                try:
                    token.assert_active()
                except snap.SnapshotConnectionError as error:
                    return error
            error = executor.submit(use_token).result()
        safe_error(error, 'snapshot_owner_mismatch')
        original_pid = snap.os.getpid()
        with monkeypatch.context() as local:
            local.setattr(snap.os, 'getpid', lambda: original_pid + 1)
            with pytest.raises(snap.SnapshotConnectionError) as caught:
                token.assert_active()
            safe_error(caught.value, 'snapshot_owner_mismatch')
        token.assert_active()


def test_nested_helper_does_not_rollback_outer(connection):
    with snap.readonly_snapshot(connection) as outer:
        with pytest.raises(snap.SnapshotConnectionError, match='^active_transaction_refused$'):
            with snap.readonly_snapshot(connection):
                pytest.fail('Nested snapshot accepted')
        outer.assert_active()
        assert connection.in_transaction()


@pytest.mark.parametrize('state', ['inactive', 'pid', 'thread'])
def test_token_safe_error_inside_caller_except_has_no_private_context(connection, monkeypatch, state):
    manager = snap.readonly_snapshot(connection)
    token = manager.__enter__()
    if state == 'inactive':
        manager.__exit__(None, None, None)
    try:
        with monkeypatch.context() as local:
            if state == 'pid':
                original = snap.os.getpid()
                local.setattr(snap.os, 'getpid', lambda: original + 1)
            elif state == 'thread':
                original = snap.threading.get_ident()
                local.setattr(snap.threading, 'get_ident', lambda: original + 1)
            try:
                raise RuntimeError(SECRET)
            except RuntimeError:
                try:
                    token.assert_active()
                except snap.SnapshotConnectionError as error:
                    caught = error
            safe_error(caught, 'snapshot_inactive' if state == 'inactive' else 'snapshot_owner_mismatch')
    finally:
        if state != 'inactive':
            manager.__exit__(None, None, None)


def test_token_constructor_is_not_a_public_connection_entry(connection):
    with pytest.raises(TypeError):
        snap.ReadonlySnapshot(connection)
    with snap.readonly_snapshot(connection) as token:
        with pytest.raises(snap.SnapshotConnectionError) as caught:
            with snap.readonly_snapshot(token):
                pytest.fail('Token accepted instead of Connection')
        safe_error(caught.value, 'connection_required')


@pytest.mark.parametrize('invalid', [None, object(), 'sqlite:///private'])
def test_connection_required(invalid):
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(invalid):
            pytest.fail('Non-connection accepted')
    safe_error(caught.value, 'connection_required')


def test_closed_connection_required(connection):
    connection.close()
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(connection):
            pytest.fail('Closed connection accepted')
    safe_error(caught.value, 'connection_required')


def fake_pg(*, driver='psycopg', status=0, raw=None):
    con = MagicMock(spec=sa.engine.Connection)
    con.closed = False
    con.in_transaction.return_value = False
    raw = raw or SimpleNamespace(autocommit=True, isolation_level=None,
        info=SimpleNamespace(transaction_status=status), get_transaction_status=lambda: status)
    con.connection = SimpleNamespace(driver_connection=raw)
    con.get_execution_options.return_value = {'isolation_level': 'AUTOCOMMIT', 'stream_results': False}
    def change(active, level):
        active.autocommit = False
        active.isolation_level = level
    con.dialect = SimpleNamespace(name='postgresql', driver=driver, set_isolation_level=change)
    con.engine = MagicMock()
    con.engine._should_log_info.return_value = False
    con.engine._should_log_debug.return_value = False
    return con, raw


@pytest.mark.parametrize('driver', ['psycopg', 'psycopg2'])
@pytest.mark.parametrize('fail', [False, True])
def test_fake_pg_exact_physical_options_and_order(driver, fail):
    con, raw = fake_pg(driver=driver)
    before = (raw.isolation_level, raw.autocommit, dict(con.get_execution_options()))
    if fail:
        with pytest.raises(RuntimeError, match=SECRET):
            with snap.readonly_snapshot(con) as token:
                assert token.schema_scope == 'app'
                assert raw.autocommit is False and raw.isolation_level == 'REPEATABLE READ'
                raise RuntimeError(SECRET)
    else:
        with snap.readonly_snapshot(con) as token:
            assert token.dialect == 'postgresql' and token.schema_scope == 'app'
    assert (raw.isolation_level, raw.autocommit, dict(con.get_execution_options())) == before
    con.exec_driver_sql.assert_called_once_with('SET TRANSACTION READ ONLY')
    con.begin.return_value.rollback.assert_called_once()
    con.close.assert_not_called()
    con.execution_options.assert_not_called()


@pytest.mark.parametrize('driver', ['psycopg', 'psycopg2'])
@pytest.mark.parametrize('status', [1, 2, 3, 4])
def test_fake_pg_nonidle_is_untouched(driver, status):
    con, raw = fake_pg(driver=driver, status=status)
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(con):
            pytest.fail('Non-idle raw driver accepted')
    safe_error(caught.value, 'active_transaction_refused')
    assert raw.autocommit is True and raw.isolation_level is None
    con.begin.assert_not_called()


@pytest.mark.parametrize('kind,code', [('dialect', 'unsupported_dialect'),
    ('driver', 'postgres_driver_unsupported'), ('info', 'sql_logging_refused'),
    ('debug', 'sql_logging_refused'), ('unknown', 'snapshot_failed')])
def test_setup_failures_are_fixed_and_no_transaction(kind, code):
    con, _ = fake_pg()
    if kind == 'dialect':
        con.dialect.name = SECRET
    elif kind == 'driver':
        con.dialect.driver = SECRET
    elif kind in ('info', 'debug'):
        getattr(con.engine, '_should_log_' + kind).return_value = True
    else:
        con.begin.side_effect = RuntimeError(SECRET)
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(con):
            pytest.fail('Invalid setup accepted')
    safe_error(caught.value, code)
    con.close.assert_not_called()


@pytest.mark.parametrize('body', [False, True, 'base'])
def test_restore_failure_wins_and_autocommit_still_attempted(body):
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
    con, raw = fake_pg(raw=Driver())
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(con):
            if body == 'base':
                raise KeyboardInterrupt()
            if body:
                raise inv.InventoryError('schema_limit_exceeded')
    safe_error(caught.value, 'connection_restore_failed')
    assert raw.autocommit is True
    con.close.assert_not_called()


def test_options_mismatch_restore_failure():
    con, _ = fake_pg()
    con.get_execution_options.side_effect = [{'stream_results': False}, {'stream_results': True}]
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(con):
            pass
    safe_error(caught.value, 'connection_restore_failed')


def test_rollback_failure_inactivates_token():
    con, _ = fake_pg()
    con.begin.return_value.rollback.side_effect = RuntimeError(SECRET)
    with pytest.raises(snap.SnapshotConnectionError) as caught:
        with snap.readonly_snapshot(con) as token:
            pass
    safe_error(caught.value, 'connection_restore_failed')
    with pytest.raises(snap.SnapshotConnectionError, match='^snapshot_inactive$'):
        token.assert_active()


def test_synthetic_readonly_file_uri(tmp_path):
    path = tmp_path / 'synthetic-source.sqlite'
    writer = sa.create_engine('sqlite:///' + path.as_posix())
    with writer.begin() as con:
        con.exec_driver_sql('CREATE TABLE facts (value TEXT)')
        con.exec_driver_sql('INSERT INTO facts VALUES (?)', (SECRET,))
    writer.dispose()
    reader = sa.create_engine('sqlite:///' + path.as_uri() + '?mode=ro&uri=true')
    with reader.connect() as con:
        with snap.readonly_snapshot(con) as token:
            assert token.connection.exec_driver_sql('SELECT count(*) FROM main.facts').scalar_one() == 1
        assert not con.in_transaction() and not con.closed
    reader.dispose()


@pytest.mark.parametrize('code', ['schema_limit_exceeded', 'unknown_version_head'])
def test_inventory_preserves_body_error_code_and_clears_exception_chain(connection, tmp_path, monkeypatch, code):
    def fail(*_):
        try:
            raise RuntimeError(SECRET)
        except RuntimeError:
            raise inv.InventoryError(code)
    monkeypatch.setattr(inv, '_reflect', fail)
    output = tmp_path / 'absent.json'
    with pytest.raises(inv.InventoryError) as caught:
        inv.inventory_database(connection, schema_only=True, output=output)
    assert str(caught.value) == code
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert not output.exists() and not connection.in_transaction()


def test_inventory_uses_helper_and_has_same_output(connection, tmp_path, monkeypatch):
    calls = []
    original = snap.readonly_snapshot
    def capture(con):
        calls.append(con)
        return original(con)
    monkeypatch.setattr(inv, 'readonly_snapshot', capture)
    output = tmp_path / 'result.json'
    report = inv.inventory_database(connection, schema_only=True, output=output).to_dict()
    assert calls == [connection]
    assert report == json.loads(output.read_text('utf8'))
    assert report['schema_scope'] == 'main'
    assert report['known_table_count'] == 0 and report['aggregates'] == {}


@pytest.mark.parametrize('arguments,code', [(['--help'], 0), (['--dsn', SECRET], 2)])
def test_direct_script_cli_without_repository_pythonpath(arguments, code):
    # Preserve only the stdlib sitecustomize network guard, not repo/backend.
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH', 'COMSPEC',
                              'PATHEXT', 'SYSTEMDRIVE', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD',
                              'PYTHONDONTWRITEBYTECODE', 'LC_ALL', 'LANG'}}
    guards = [part for part in os.environ['PYTHONPATH'].split(os.pathsep)
              if (Path(part)/'sitecustomize.py').is_file()]
    assert len(guards) == 1
    env['PYTHONPATH'] = guards[0]
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([sys.executable, '-B', str(root/'tools/production_db_inventory.py'),
        *arguments], cwd=root, env=env, capture_output=True, text=True, timeout=15,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == code
    assert SECRET not in result.stdout + result.stderr
    assert ('API only:' in result.stdout) if code == 0 else (
        result.stderr == 'inventory_cli_connection_not_implemented\n')
