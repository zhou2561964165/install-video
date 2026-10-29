"""E2 T1: synthetic SQLite read contract and catalog bridge; no app/real DB/network."""
from pathlib import Path
import sqlite3
import threading
import time

import pytest
from sqlalchemy import create_engine, event

import tools.production_db_snapshot_catalog as catalog
import tools.production_db_snapshot_read_contract as rc
from tools.production_db_snapshot_catalog import CatalogError, catalog_snapshot
from tools.production_db_snapshot_profiles import SOURCE_PROFILES
from tools.production_db_snapshot_schema import schema_document

FIXTURES = Path(__file__).parent / 'fixtures' / 'snapshot_catalog'
PROFILES = {9: 'legacy_sqlite9_v1', 17: 'sqlite_models17_v1'}


def make_db(tmp_path, version=17, extra=None):
    path = tmp_path / f'source{version}.db'
    writer = sqlite3.connect(str(path))
    try:
        writer.executescript((FIXTURES / f'sqlite{version}.sql').read_text('utf8'))
        if extra:
            writer.executescript(extra)
        writer.commit()
    finally:
        writer.close()
    return str(path.resolve())


def budget(seconds=300):
    return rc.ReadBudget(seconds)


def refuse(connection, contract, code='driver_contract_required', read_budget=None):
    with pytest.raises(CatalogError) as caught:
        with catalog._catalog_for_export(connection, contract, read_budget or budget()):
            pytest.fail('unexpected capability')
    assert caught.value.code == code
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert not catalog._ACTIVE
    return caught.value


@pytest.fixture
def no_snapshot(monkeypatch):
    """Contract refusals must happen before E0 runs any source SQL."""
    def forbidden(*args, **kwargs):
        raise AssertionError('source_sql_before_contract')
    monkeypatch.setattr(catalog, 'readonly_snapshot', forbidden)


@pytest.mark.parametrize('version', [9, 17], ids=['s9', 's17'])
def test_bridge_matches_profile_and_restores(tmp_path, version):
    with rc._open_synthetic_sqlite(make_db(tmp_path, version)) as (connection, contract):
        raw = connection.connection.driver_connection
        assert raw.execute('PRAGMA busy_timeout').fetchone() == (5000,)
        with catalog._catalog_for_export(connection, contract, budget()) as source:
            source.assert_active()
            assert source.profile.profile_id == PROFILES[version]
            assert schema_document(source.descriptor) == schema_document(SOURCE_PROFILES[PROFILES[version]].descriptor)
            guard = rc._guard_of(contract)
            assert guard.installed
            assert 0 < raw.execute('PRAGMA busy_timeout').fetchone()[0] <= 10000
        assert not rc._guard_of(contract).installed
        assert not raw.in_transaction
        assert raw.execute('PRAGMA busy_timeout').fetchone() == (5000,)
        assert raw.execute('PRAGMA query_only').fetchone() == (0,)
        with pytest.raises(CatalogError, match='snapshot_inactive'):
            source.assert_active()
        # Single lifecycle: a consumed contract never authorizes a second read.
        refuse(connection, contract)


def test_public_catalog_snapshot_unchanged(tmp_path):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, _contract):
        with catalog_snapshot(connection) as source:
            assert source.profile.profile_id == PROFILES[17]


@pytest.mark.parametrize('value', [None, True, 'contract', object()], ids=['none', 'bool', 'str', 'object'])
def test_missing_or_fake_contract(tmp_path, no_snapshot, value):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, _contract):
        refuse(connection, value)


def test_contract_not_constructible_or_subclassable(tmp_path, no_snapshot):
    with pytest.raises(TypeError):
        rc.RawReadContract()
    with pytest.raises(TypeError):
        class Fake(rc.RawReadContract):
            pass
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        assert 'RawReadContract' not in repr(contract) or 'raw' not in repr(contract).lower()
        with pytest.raises(AttributeError):
            contract.extra = 1


def test_contract_bound_to_exact_connection(tmp_path, no_snapshot):
    path = make_db(tmp_path)
    with rc._open_synthetic_sqlite(path) as (_first, contract):
        with rc._open_synthetic_sqlite(path) as (second, _other):
            refuse(second, contract)
        engine = create_engine('sqlite:///file:' + Path(path).as_posix() + '?mode=ro&uri=true')
        try:
            with engine.connect() as foreign:
                refuse(foreign, contract)
        finally:
            engine.dispose()


def test_contract_invalid_after_bootstrap_exit(tmp_path, no_snapshot):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        pass
    with pytest.raises(CatalogError) as caught:
        with catalog._catalog_for_export(connection, contract, budget()):
            pytest.fail('unexpected capability')
    assert caught.value.code in ('driver_contract_required', 'connection_required')


def test_other_thread_refused(tmp_path, no_snapshot):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        seen = []

        def worker():
            try:
                with catalog._catalog_for_export(connection, contract, budget()):
                    seen.append('capability')
            except CatalogError as error:
                seen.append(error.code)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert seen == ['driver_contract_required']


def test_other_pid_refused(tmp_path, no_snapshot, monkeypatch):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        monkeypatch.setattr(rc.os, 'getpid', lambda: -1)
        refuse(connection, contract)


@pytest.mark.parametrize('mutation', [
    lambda c, raw, e: setattr(raw, 'row_factory', sqlite3.Row),
    lambda c, raw, e: setattr(raw, 'text_factory', bytes),
    lambda c, raw, e: setattr(raw, 'isolation_level', None),
    lambda c, raw, e: setattr(e, 'echo', True),
    lambda c, raw, e: event.listen(e, 'before_cursor_execute', lambda *a: None),
    lambda c, raw, e: event.listen(e.pool, 'connect', lambda *a: None),
], ids=['row_factory', 'text_factory', 'isolation', 'echo', 'cursor_event', 'pool_event'])
def test_observable_driver_drift_refused(tmp_path, no_snapshot, mutation):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        mutation(connection, connection.connection.driver_connection, connection.engine)
        refuse(connection, contract)


def test_active_transaction_refused_without_rollback(tmp_path, no_snapshot):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        transaction = connection.begin()
        connection.exec_driver_sql('SELECT 1')
        refuse(connection, contract, 'active_transaction_refused')
        assert transaction.is_active
        transaction.rollback()


def test_expired_budget_refused_before_sql(tmp_path, no_snapshot):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        refuse(connection, contract, 'snapshot_resource_limit', rc.ReadBudget(0))


@pytest.mark.parametrize('value', [-1, 301, 1.5, True, '10'], ids=['neg', 'over', 'float', 'bool', 'str'])
def test_budget_validation(value):
    with pytest.raises(ValueError):
        rc.ReadBudget(value)


def test_catalog_interrupted_by_deadline(tmp_path, monkeypatch):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        raw = connection.connection.driver_connection
        clock = [time.monotonic()]
        monkeypatch.setattr(rc, '_monotonic', lambda: clock[0])
        read_budget = budget(5)
        original = catalog._collect

        def slow_collect(conn):
            clock[0] += 60  # every following VM step sees an expired statement deadline
            return original(conn)
        monkeypatch.setattr(catalog, '_collect', slow_collect)
        refuse(connection, contract, 'snapshot_resource_limit', read_budget)
        assert not rc._guard_of(contract).installed
        assert not raw.in_transaction
        assert raw.execute('PRAGMA busy_timeout').fetchone() == (5000,)
        assert raw.execute('PRAGMA query_only').fetchone() == (0,)


def test_guard_teardown_failure_still_rolls_back(tmp_path, monkeypatch):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        raw = connection.connection.driver_connection

        def broken(self):
            raise sqlite3.OperationalError('private_teardown_detail')
        monkeypatch.setattr(rc._SqliteGuard, '_restore', broken)
        with pytest.raises(CatalogError) as caught:
            with catalog._catalog_for_export(connection, contract, budget()):
                pass
        assert caught.value.code == 'connection_restore_failed'
        assert 'private_teardown_detail' not in str(caught.value)
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert not raw.in_transaction
        assert not catalog._ACTIVE


def test_body_base_exception_same_object_after_cleanup(tmp_path):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        raw = connection.connection.driver_connection
        stop = KeyboardInterrupt('body')
        with pytest.raises(KeyboardInterrupt) as caught:
            with catalog._catalog_for_export(connection, contract, budget()):
                raise stop
        assert caught.value is stop
        assert not rc._guard_of(contract).installed
        assert not raw.in_transaction
        assert raw.execute('PRAGMA busy_timeout').fetchone() == (5000,)


def test_body_exception_propagates_unchanged(tmp_path):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        failure = ValueError('body')
        with pytest.raises(ValueError) as caught:
            with catalog._catalog_for_export(connection, contract, budget()):
                raise failure
        assert caught.value is failure
        assert not rc._guard_of(contract).installed


def test_profile_mismatch_cleans_guard(tmp_path):
    path = make_db(tmp_path, 9, 'CREATE TABLE extra (id INTEGER);')
    with rc._open_synthetic_sqlite(path) as (connection, contract):
        refuse(connection, contract, 'source_profile_unsupported')
        assert not rc._guard_of(contract).installed
        assert not connection.connection.driver_connection.in_transaction


@pytest.mark.parametrize('value', ['relative.db', '', 'file:x.db?mode=rw', None, 7], ids=['relative', 'empty', 'uri', 'none', 'int'])
def test_bootstrap_requires_absolute_existing_path(tmp_path, value):
    with pytest.raises(ValueError):
        with rc._open_synthetic_sqlite(value):
            pytest.fail('unexpected connection')
    with pytest.raises(ValueError):
        with rc._open_synthetic_sqlite(str(tmp_path / 'missing.db')):
            pytest.fail('unexpected connection')


def test_bootstrap_connection_is_read_only(tmp_path):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, _contract):
        with pytest.raises(sqlite3.OperationalError):
            connection.connection.driver_connection.execute('DELETE FROM user')


def test_issue_requires_module_record(tmp_path):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, _contract):
        for record in (None, {'detect_types': 0}, True):
            with pytest.raises(TypeError):
                rc._issue_dedicated_contract(connection, record)


def test_progress_handler_interrupts_long_statement(tmp_path, monkeypatch):
    query = ('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<100000) '
             'SELECT count(*) FROM n')
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        raw = connection.connection.driver_connection
        guard = rc._guard_of(contract)
        clock = [time.monotonic()]
        monkeypatch.setattr(rc, '_monotonic', lambda: clock[0])
        guard.install(raw, budget(5))
        clock[0] += 60
        with pytest.raises(sqlite3.OperationalError, match='interrupted'):
            raw.execute(query).fetchone()
        assert guard.expired
        guard.teardown()
        assert not guard.installed
        assert raw.execute(query).fetchone() == (100000,)
        assert raw.execute('PRAGMA busy_timeout').fetchone() == (5000,)


def test_bootstrap_refuses_preexisting_class_listener(tmp_path):
    # Review I2: a global instrumentation hook must not become the approved baseline.
    from sqlalchemy.engine import Engine

    def hook(*args):
        return args[2], args[3]
    event.listen(Engine, 'before_cursor_execute', hook, retval=True)
    try:
        with pytest.raises(ValueError):
            with rc._open_synthetic_sqlite(make_db(tmp_path)):
                pytest.fail('contract issued with foreign listener')
    finally:
        event.remove(Engine, 'before_cursor_execute', hook)


@pytest.mark.parametrize('name', ['do_execute', 'do_execute_no_params', 'handle_error', 'do_connect'])
def test_dialect_event_after_issue_refused(tmp_path, no_snapshot, name):
    with rc._open_synthetic_sqlite(make_db(tmp_path)) as (connection, contract):
        event.listen(connection.engine, name, lambda *a: None)
        refuse(connection, contract)
