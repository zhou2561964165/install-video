"""Explicit disposable PG opt-in; E0 helper only, no private input in this file.

The existing reviewed ownership fixture creates and drops each synthetic DB.
Root schedules its server lifecycle. This file is only AST-parsed offline.
"""
import pytest
import sqlalchemy as sa

from b3b_pg_helpers import guarded_sockets, pg, schema_pg  # noqa: F401
from tools import production_db_snapshot as snap

SECRET = 'B6_E0_PG_SYNTHETIC_PRIVATE_password_email_url'


@pytest.mark.parametrize('mode', ['default', 'serializable', 'option_auto',
                                 'engine_auto', 'driver_auto_mismatch'])
@pytest.mark.parametrize('fail', [False, True])
def test_helper_exact_pg_driver_options_restored(pg, mode, fail):
    engine = pg.execution_options(isolation_level='AUTOCOMMIT') if mode == 'engine_auto' else pg
    with engine.connect() as con:
        if mode in ('serializable', 'driver_auto_mismatch'):
            con.execution_options(isolation_level='SERIALIZABLE', stream_results=False, no_parameters=True)
        elif mode == 'option_auto':
            con.execution_options(isolation_level='AUTOCOMMIT', stream_results=False)
        raw = con.connection.driver_connection
        if mode == 'driver_auto_mismatch':
            raw.autocommit = True
        before = (raw.isolation_level, raw.autocommit, dict(con.get_execution_options()),
                  con.get_isolation_level())
        failure = RuntimeError(SECRET)
        observed = []
        try:
            with snap.readonly_snapshot(con) as token:
                observed.append(token)
                assert token.connection is con and token.schema_scope == 'app'
                assert con.scalar(sa.text('SHOW transaction_read_only')) == 'on'
                assert con.scalar(sa.text('SHOW transaction_isolation')) == 'repeatable read'
                assert int(raw.info.transaction_status) == 2
                if fail:
                    raise failure
        except RuntimeError as error:
            assert fail and error is failure
        else:
            assert not fail
        assert not con.in_transaction() and not con.closed
        assert (raw.isolation_level, raw.autocommit, dict(con.get_execution_options()),
                con.get_isolation_level()) == before
        with pytest.raises(snap.SnapshotConnectionError) as caught:
            observed[0].assert_active()
        assert str(caught.value) == 'snapshot_inactive'
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert con.scalar(sa.text('SELECT 1')) == 1
        assert int(raw.info.transaction_status) == (0 if before[1] else 2)
        con.rollback()


def test_helper_pg_readonly_is_enforced_in_autocommit(pg):
    with pg.connect() as con:
        con.execution_options(isolation_level='AUTOCOMMIT')
        with pytest.raises(sa.exc.DBAPIError) as caught:
            with snap.readonly_snapshot(con):
                con.exec_driver_sql('UPDATE app."user" SET password_hash=password_hash')
        assert caught.value.orig.sqlstate == '25006'
        assert con.connection.driver_connection.autocommit
        assert not con.in_transaction() and not con.closed


@pytest.mark.parametrize('native_status', ['sqlalchemy', 'raw', 'raw_error'])
def test_helper_pg_caller_transaction_remains_owned(pg, native_status):
    with pg.connect() as con:
        raw = con.connection.driver_connection
        tx = con.begin() if native_status == 'sqlalchemy' else None
        if tx is not None:
            con.exec_driver_sql('SELECT 1')
        else:
            raw.execute('SELECT 1')
            if native_status == 'raw_error':
                try:
                    raw.execute('SELECT 1/0')
                except Exception:
                    pass
        status = raw.info.transaction_status
        with pytest.raises(snap.SnapshotConnectionError) as caught:
            with snap.readonly_snapshot(con):
                pytest.fail('Caller PG transaction accepted')
        assert str(caught.value) == 'active_transaction_refused'
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert raw.info.transaction_status == status
        assert con.get_transaction() is tx and not con.closed
        if tx is not None:
            assert tx.is_active
            tx.rollback()
        else:
            raw.rollback()


def test_helper_pg_snapshot_survives_concurrent_commit(schema_pg):
    with schema_pg.application.connect() as con:
        with snap.readonly_snapshot(con):
            assert con.scalar(sa.text('SELECT count(*) FROM app."user"')) == 0
            with schema_pg.migration.begin() as writer:
                writer.execute(sa.text('INSERT INTO app."user" (id,email,password_hash,created_at) '
                    'VALUES (:id,:email,:secret,:now)'),
                    {'id': 'e0-user', 'email': 'e0@synthetic.invalid',
                     'secret': SECRET, 'now': '2000-01-01T00:00:00Z'})
            assert con.scalar(sa.text('SELECT count(*) FROM app."user"')) == 0
        assert con.scalar(sa.text('SELECT count(*) FROM app."user"')) == 1
        con.rollback()
