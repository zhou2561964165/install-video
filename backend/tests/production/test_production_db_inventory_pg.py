"""Explicit opt-in, existing isolated PG18.6/app only. No app imports or DDL."""
import json
import os
from pathlib import Path
import re

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from tools import production_db_inventory as inv

SECRET = 'B6_SYNTHETIC_PRIVATE_email_password_url_payload'
CONTROL = Path(r'E:\install_video\.planning\2026-10-24-production-execution\postgres-runtime\control.json')


def build_engine(role='application', **options):
    assert Path(os.environ['B6_PG_CONTROL']).resolve() == CONTROL.resolve()
    control = json.loads(CONTROL.read_text('utf8'))
    assert (control['host'], control['port'], control['database']) == ('127.0.0.1', 62328, 'pv_verify')
    private = json.loads((CONTROL.parent / 'private/credentials.json').read_text('utf8'))
    url = sa.URL.create('postgresql+psycopg', username=control['roles'][role], password=private[role],
                        host=control['host'], port=control['port'], database=control['database'])
    result = sa.create_engine(url, hide_parameters=True, poolclass=NullPool,
        connect_args={'connect_timeout': 3, 'options': '-c statement_timeout=10000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=20000'},
        **options)
    del private, url
    return result


def insert_user(con, uid):
    con.execute(sa.text('INSERT INTO app."user" (id,email,password_hash,created_at) VALUES (:id,:email,:secret,:now)'),
                {'id': uid, 'email': uid+'@synthetic.invalid', 'secret': SECRET, 'now': '2000-01-01T00:00:00Z'})


@pytest.fixture(scope='module')
def engines():
    if not os.environ.get('B6_PG_CONTROL'):
        pytest.skip('B6 explicit isolated PG opt-in required')
    app, migration = build_engine(), build_engine('migration')
    try:
        with app.connect() as con:
            assert con.scalar(sa.text('SHOW server_version')) == '18.6'
            assert con.scalar(sa.text('SELECT version_num FROM app.alembic_version')) == 'b1b_0003'
            for table in (inv.LEGACY.keys() | inv.PROTOCOL.keys()) - {'resourcecounter'}:
                assert con.scalar(sa.text('SELECT count(*) FROM app."'+table+'"')) == 0
        with migration.begin() as con:
            insert_user(con, 'b6-user')
            con.execute(sa.text('INSERT INTO app.quota (id,user_id,date,downloads_used,"limit") VALUES (:id,\'b6-user\',:day,:used,9)'),
                [{'id':'b6-q1','day':'2000-01-01','used':-1}, {'id':'b6-q2','day':'2000-01-02','used':2}])
            con.execute(sa.text('INSERT INTO app.job (id,user_id,url,status,progress,created_at,updated_at,error) VALUES (:id,\'b6-user\',:secret,:status,0,:now,:now,:secret)'),
                [{'id':'b6-j1','secret':SECRET,'status':'queued','now':'2000-01-01T00:00:00Z'},
                 {'id':'b6-j2','secret':SECRET,'status':'done','now':'2000-01-01T00:00:00Z'}])
            con.execute(sa.text('INSERT INTO app.downloadidempotency (id,user_id,key,fingerprint,state,created_at,response_json) VALUES (:id,\'b6-user\',:id,:secret,:state,0,:secret)'),
                [{'id':'b6-d1','secret':SECRET,'state':'pending'}, {'id':'b6-d2','secret':SECRET,'state':'uncertain'}])
        yield app, migration
    finally:
        with migration.begin() as con:
            for table in ('downloadidempotency','job','quota'):
                con.execute(sa.text('DELETE FROM app.'+table+' WHERE user_id LIKE \'b6-%\''))
            con.execute(sa.text('DELETE FROM app."user" WHERE id LIKE \'b6-%\''))
        app.dispose()
        migration.dispose()


def test_schema_only_has_no_business_select_and_safe_metadata(engines, tmp_path):
    statements = []
    with engines[0].connect() as con:
        sa.event.listen(con, 'before_cursor_execute', lambda c, cur, s, p, ctx, many: statements.append(s))
        report = inv.inventory_database(con, schema_only=True, output=tmp_path/'schema.json').to_dict()
        assert not con.in_transaction() and not con.closed
    reads = [s for s in statements if re.search(r'\b(?:FROM|JOIN)\s+app\.', s, re.I)]
    assert reads and all('app.alembic_version' in s for s in reads)
    assert len(report['schema']) == 16 and report['aggregates'] == {}
    assert report['version_heads'] == ['b1b_0003'] and report['postgres_server_version'][:2] == [18,6]
    assert SECRET not in json.dumps(report)


def test_aggregate_counts_and_private_values_redacted(engines, tmp_path):
    with engines[0].connect() as con:
        report = inv.inventory_database(con, schema_only=False, output=tmp_path/'counts.json').to_dict()
    counts = report['aggregates']
    assert counts['user']['row_count'] == 1 and counts['quota']['row_count'] == 2
    assert counts['quota']['negative_counts']['downloads_used'] == 1
    assert counts['job']['status_counts']['queued'] == 1 and counts['job']['legacy_job_count'] == 2
    assert counts['job']['queued_older_than_24h_count'] == 1
    assert counts['downloadidempotency']['pending_older_than_24h_count'] == 1
    assert counts['downloadidempotency']['state_counts']['uncertain'] == 1
    assert all(item['count'] == 0 for row in counts.values() for item in row['orphan_counts']+row['duplicate_groups'])
    assert SECRET not in (tmp_path/'counts.json').read_text('utf8')


@pytest.mark.parametrize('mode', ['default','serializable','option_auto','engine_auto','driver_auto_mismatch'])
@pytest.mark.parametrize('fail', [False, True])
def test_exact_driver_options_restore_on_success_and_failure(engines, tmp_path, monkeypatch, mode, fail):
    engine = build_engine(isolation_level='AUTOCOMMIT') if mode == 'engine_auto' else engines[0]
    try:
        with engine.connect() as con:
            if mode in ('serializable','driver_auto_mismatch'):
                con.execution_options(isolation_level='SERIALIZABLE', stream_results=False, no_parameters=True)
            elif mode == 'option_auto':
                con.execution_options(isolation_level='AUTOCOMMIT', stream_results=False)
            raw = con.connection.driver_connection
            if mode == 'driver_auto_mismatch':
                raw.autocommit = True
            before = (raw.isolation_level, raw.autocommit, dict(con.get_execution_options()), con.get_isolation_level())
            if fail:
                def forbidden(*_):
                    raise RuntimeError(SECRET)
                monkeypatch.setattr(inv, '_reflect', forbidden)
                with pytest.raises(inv.InventoryError, match='^inventory_failed$') as caught:
                    inv.inventory_database(con, schema_only=False, output=tmp_path/'absent.json')
                assert caught.value.__context__ is None and caught.value.__cause__ is None
                assert not (tmp_path/'absent.json').exists()
            else:
                inv.inventory_database(con, schema_only=True, output=tmp_path/'ok.json')
            assert not con.in_transaction() and not con.closed
            assert (raw.isolation_level, raw.autocommit, dict(con.get_execution_options()), con.get_isolation_level()) == before
            assert con.scalar(sa.text('SELECT 1')) == 1
            assert int(raw.info.transaction_status) == (0 if before[1] else 2)
            con.rollback()
    finally:
        if engine is not engines[0]:
            engine.dispose()


def test_database_enforces_readonly_even_for_autocommit_input(engines, tmp_path, monkeypatch):
    with engines[0].connect() as con:
        con.execution_options(isolation_level='AUTOCOMMIT')
        def forbidden_write(active, schema):
            assert schema == 'app' and int(active.connection.driver_connection.info.transaction_status) == 2
            assert active.scalar(sa.text('SHOW transaction_read_only')) == 'on'
            assert active.scalar(sa.text('SHOW transaction_isolation')) == 'repeatable read'
            try:
                active.exec_driver_sql('UPDATE app."user" SET password_hash=password_hash WHERE id=\'b6-user\'')
            except sa.exc.DBAPIError as exc:
                assert exc.orig.sqlstate == '25006'
                raise
            raise AssertionError('Database allowed a write inside inventory')
        monkeypatch.setattr(inv, '_reflect', forbidden_write)
        with pytest.raises(inv.InventoryError, match='^inventory_failed$'):
            inv.inventory_database(con, schema_only=True, output=tmp_path/'write.json')
        assert con.connection.driver_connection.autocommit and not con.in_transaction()
        assert not (tmp_path/'write.json').exists()


@pytest.mark.parametrize('native_status', ['sqlalchemy','raw','raw_error'])
def test_active_caller_transaction_remains_owned(engines, tmp_path, native_status):
    with engines[0].connect() as con:
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
        with pytest.raises(inv.InventoryError, match='^active_transaction_refused$'):
            inv.inventory_database(con, schema_only=True, output=tmp_path/'active.json')
        assert raw.info.transaction_status == status
        assert con.get_transaction() is tx
        if tx is not None:
            assert tx.is_active
            tx.rollback()
        else:
            raw.rollback()
        assert not (tmp_path/'active.json').exists()


def test_repeatable_snapshot_survives_concurrent_commit(engines, tmp_path, monkeypatch):
    original = inv._aggregates
    def concurrent(con, tables, now):
        assert con.scalar(sa.select(sa.func.count()).select_from(tables['user'])) == 1
        with engines[1].begin() as writer:
            insert_user(writer, 'b6-concurrent')
        return original(con, tables, now)
    monkeypatch.setattr(inv, '_aggregates', concurrent)
    try:
        with engines[0].connect() as con:
            data = inv.inventory_database(con, schema_only=False, output=tmp_path/'snapshot.json').to_dict()
            assert data['aggregates']['user']['row_count'] == 1
            assert con.scalar(sa.text('SELECT count(*) FROM app."user"')) == 2
    finally:
        with engines[1].begin() as writer:
            writer.exec_driver_sql('DELETE FROM app."user" WHERE id=\'b6-concurrent\'')


def test_application_role_has_dml_without_ddl_ownership(engines):
    with engines[0].connect() as con:
        row = con.execute(sa.text("SELECT r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolbypassrls,has_schema_privilege(current_user,'app','CREATE'),has_table_privilege(current_user,'app.user','SELECT,INSERT,UPDATE,DELETE'),(SELECT pg_get_userbyid(nspowner)=current_user FROM pg_namespace WHERE nspname='app') FROM pg_roles r WHERE rolname=current_user")).one()
        assert tuple(row) == (False,False,False,False,False,True,False)
