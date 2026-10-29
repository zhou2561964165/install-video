"""Opt-in B1 tests. Run --noconftest and provide the task control manifest explicitly."""
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import URL, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlmodel import Session

from app import db
from app.models import Job, JobStatus, SQLModel, User


@pytest.fixture(scope='module')
def pg():
    marker = os.environ.get('B1_PG_CONTROL')
    if not marker:
        pytest.skip('B1_PG_CONTROL explicit isolated PostgreSQL opt-in is required')
    control_path = Path(marker).resolve()
    control = json.loads(control_path.read_text('utf8'))
    assert control_path.parent.name == 'postgres-runtime'
    assert control['host'] == '127.0.0.1' and control['port'] == 62328
    assert control['database'] == 'pv_verify' and control['schema'] == 'app'
    assert control['roles'] == {'bootstrap': 'pv_bootstrap', 'migration': 'pv_migrator', 'application': 'pv_app'}
    secret_values = json.loads((control_path.parent / 'private/credentials.json').read_text('utf8'))
    engines = {}
    try:
        for role in ['migration', 'application']:
            url = URL.create('postgresql+psycopg', username=control['roles'][role],
                             password=secret_values[role], host=control['host'], port=control['port'],
                             database=control['database'])
            engines[role] = db.build_engine(url, role='migration' if role == 'migration' else 'api')
        del secret_values, url
        with engines['migration'].connect() as connection:
            assert connection.scalar(text('SHOW server_version')) == '18.6'
            assert connection.scalar(text('SELECT current_database()')) == 'pv_verify'
        config = db.migration_config()
        with engines['migration'].begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        yield engines
    finally:
        for engine in engines.values():
            engine.dispose()


@pytest.fixture(autouse=True)
def clear_synthetic_rows(pg):
    yield
    with pg['migration'].begin() as connection:
        for table in reversed(SQLModel.metadata.sorted_tables):
            connection.execute(table.delete())


def test_pg_schema_reflects_all_nine_models(pg):
    with pg['migration'].connect() as connection:
        actual = inspect(connection)
        assert set(actual.get_table_names(schema='app')) == set(SQLModel.metadata.tables) | {'alembic_version'}
        assert compare_metadata(MigrationContext.configure(connection), SQLModel.metadata) == []
        for table in SQLModel.metadata.sorted_tables:
            assert actual.get_pk_constraint(table.name, schema='app')['name'] == table.primary_key.name
            assert {fk['name'] for fk in actual.get_foreign_keys(table.name, schema='app')} == {fk.name for fk in table.foreign_key_constraints}
            assert {index['name'] for index in actual.get_indexes(table.name, schema='app') if not index.get('duplicates_constraint')} == {i.name for i in table.indexes}
            from sqlalchemy import UniqueConstraint
            assert {item['name'] for item in actual.get_unique_constraints(table.name, schema='app')} == {
                constraint.name for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
        assert {item['name'] for item in actual.get_check_constraints('job', schema='app')} == {'ck_job_status'}


def test_pg_file_size_boundary_and_utc_roundtrip(pg):
    original_time = datetime(2026, 10, 24, 10, 30, tzinfo=timezone(timedelta(hours=8)))
    with Session(pg['application']) as session:
        user = User(id='synthetic-string-user', email='synthetic@example.invalid', password_hash='fake')
        session.add(user)
        session.commit()
        job = Job(id='old-string-id-preserved', url='https://example.invalid/v', user_id=user.id,
                  file_size=2147483648, created_at=original_time, updated_at=original_time)
        session.add(job)
        session.commit()
        session.refresh(job)
        assert job.id == 'old-string-id-preserved' and job.file_size == 2147483648
        assert job.status == JobStatus.queued
        assert job.created_at == original_time
        assert job.created_at.utcoffset() == timedelta(0)
    with pg['application'].connect() as connection:
        assert connection.scalar(text('SHOW TimeZone')) == 'UTC'
        assert connection.scalar(text('SHOW search_path')) == 'app,pg_catalog'
        assert connection.scalar(text('SHOW lock_timeout')) == '2s'
        assert connection.scalar(text('SHOW statement_timeout')) == '10s'
        assert connection.scalar(text('SHOW idle_in_transaction_session_timeout')) == '15s'


@pytest.mark.parametrize('sql', [
    "INSERT INTO quota(id,user_id,date,downloads_used,\"limit\") VALUES('orphan','absent','2026-10-24',0,1)",
    "INSERT INTO downloadaccess(job_id) VALUES('absent')",
    "INSERT INTO job(id,url,status,progress,created_at,updated_at) VALUES('bad','synthetic','invalid',0,now(),now())",
])
def test_pg_foreign_key_and_status_constraints(pg, sql):
    with pytest.raises(IntegrityError):
        with pg['application'].begin() as connection:
            connection.execute(text(sql))


@pytest.mark.parametrize('table,sql', [
    ('user', "INSERT INTO \"user\"(id,email,password_hash,created_at) VALUES('u2','unique@example.invalid','fake',now())"),
    ('quota', "INSERT INTO quota(id,user_id,date,downloads_used,\"limit\") VALUES('q2','u1','2026-10-24',0,1)"),
    ('downloadidempotency', "INSERT INTO downloadidempotency(id,user_id,key,fingerprint,state,created_at) VALUES('r2','u1','k','f','pending',1)"),
    ('membership', "INSERT INTO membership(user_id,customer_id,status,expires_at,cancel_at_period_end,revision) VALUES('u2','cust','free',0,false,0)"),
    ('billingcheckout', "INSERT INTO billingcheckout(id,user_id,price_id,mode,duration_days,origin,created_at,stripe_id,expires_at,state,fulfilled) VALUES('c2','u1','p','payment',30,'synthetic',1,'s',0,'pending',false)"),
])
def test_pg_unique_constraints(pg, table, sql):
    with pg['application'].begin() as connection:
        connection.execute(text("INSERT INTO \"user\"(id,email,password_hash,created_at) VALUES('u1','unique@example.invalid','fake',now()),('u2','other@example.invalid','fake',now())"))
        connection.execute(text("INSERT INTO quota(id,user_id,date,downloads_used,\"limit\") VALUES('q1','u1','2026-10-24',0,1)"))
        connection.execute(text("INSERT INTO downloadidempotency(id,user_id,key,fingerprint,state,created_at) VALUES('r1','u1','k','f','pending',1)"))
        connection.execute(text("INSERT INTO membership(user_id,customer_id,status,expires_at,cancel_at_period_end,revision) VALUES('u1','cust','free',0,false,0)"))
        connection.execute(text("INSERT INTO billingcheckout(id,user_id,price_id,mode,duration_days,origin,created_at,stripe_id,expires_at,state,fulfilled) VALUES('c1','u1','p','payment',30,'synthetic',1,'s',0,'pending',false)"))
    # For email uniqueness use a new primary key, so the email index is exercised.
    if table == 'user':
        sql = sql.replace("'u2'", "'u3'")
    with pytest.raises(IntegrityError):
        with pg['application'].begin() as connection:
            connection.execute(text(sql))


def test_pg_application_has_dml_but_no_ddl(pg, monkeypatch):
    db.assert_schema_current(pg['application'])
    monkeypatch.setattr(db, 'engine', pg['application'])
    with pytest.raises(db.DatabaseConfigurationError, match='business startup'):
        db.init_db()
    for sql in ['CREATE TABLE app.denied(id int)', 'CREATE TEMP TABLE denied(id int)',
                'ALTER TABLE app.job ADD COLUMN denied int', 'DROP TABLE app.billingevent']:
        with pytest.raises(DBAPIError) as failure:
            with pg['application'].begin() as connection:
                connection.execute(text(sql))
        assert failure.value.orig.sqlstate == '42501'


def test_pg_epoch_and_optional_legacy_fields_preserved(pg):
    from app.models import BillingCheckout, DownloadIdempotency, Membership, Quota
    epoch = 1792800000.125
    with Session(pg['application']) as session:
        session.add(User(id='epoch-user', email='epoch@example.invalid', password_hash='fake'))
        session.commit()
        receipt = DownloadIdempotency(id='legacy-receipt', user_id='epoch-user', key='key',
                                      fingerprint='original-fingerprint', state='uncertain', created_at=epoch)
        membership = Membership(user_id='epoch-user', expires_at=epoch, revision=7,
                                entitlement_source='legacy-source')
        quota = Quota(id='legacy-quota', user_id='epoch-user', date='2026-10-24', limit=99, downloads_used=3)
        checkout = BillingCheckout(id='legacy-checkout', user_id='epoch-user', price_id='fake-price',
                                   mode='payment', duration_days=30, origin='synthetic', created_at=epoch)
        for row in [receipt, membership, quota, checkout]:
            session.add(row)
        session.commit()
        for row in [receipt, membership, quota, checkout]:
            session.refresh(row)
        assert receipt.created_at == checkout.created_at == membership.expires_at == epoch
        assert receipt.expires_at is receipt.direct_expires_at is receipt.response_json is None
        assert receipt.state == 'uncertain' and receipt.fingerprint == 'original-fingerprint'
        assert membership.revision == 7 and membership.entitlement_source == 'legacy-source'
        assert quota.date == '2026-10-24' and quota.limit == 99 and quota.downloads_used == 3


@pytest.mark.parametrize('revision', [None, 'wrong_head', 'second_head'])
def test_pg_schema_check_failure_is_read_only(pg, revision):
    with pg['migration'].begin() as connection:
        original_heads = list(connection.scalars(text('SELECT version_num FROM app.alembic_version')))
        if revision is None:
            connection.execute(text('ALTER TABLE app.alembic_version RENAME TO saved_alembic_version'))
        elif revision == 'second_head':
            connection.execute(text("INSERT INTO app.alembic_version VALUES('second_head')"))
        else:
            connection.execute(text("UPDATE app.alembic_version SET version_num='wrong_head'"))
    statements = []
    from sqlalchemy import event
    def collect(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(pg['application'], 'before_cursor_execute', collect)
    try:
        with pytest.raises(db.DatabaseConfigurationError):
            db.assert_schema_current(pg['application'])
        assert statements and all(s.lstrip().upper().startswith('SELECT') for s in statements)
        if revision is None:
            assert 'alembic_version' not in inspect(pg['migration']).get_table_names(schema='app')
    finally:
        event.remove(pg['application'], 'before_cursor_execute', collect)
        with pg['migration'].begin() as connection:
            if revision is None:
                connection.execute(text('ALTER TABLE app.saved_alembic_version RENAME TO alembic_version'))
            else:
                connection.execute(text('DELETE FROM app.alembic_version'))
                for head in original_heads:
                    connection.execute(text('INSERT INTO app.alembic_version VALUES(:head)'), {'head': head})


def test_pg_migration_non_cwd_and_idempotent(pg, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pg['migration'].begin() as connection:
        config = db.migration_config()
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
    db.assert_schema_current(pg['application'])


def test_pg_downgrade_refuses_business_rows(pg):
    with pg['application'].begin() as connection:
        connection.execute(text("INSERT INTO billingevent(id,processed_at) VALUES('synthetic-event',1)"))
    with pytest.raises(RuntimeError, match='nonempty'):
        with pg['migration'].begin() as connection:
            config = db.migration_config()
            config.attributes['connection'] = connection
            command.downgrade(config, 'base')
    db.assert_schema_current(pg['application'])


def test_pg_empty_downgrade_then_upgrade(pg):
    with pg['migration'].begin() as connection:
        config = db.migration_config()
        config.attributes['connection'] = connection
        command.downgrade(config, 'base')
        assert inspect(connection).get_table_names(schema='app') == ['alembic_version']
        command.upgrade(config, 'head')
    db.assert_schema_current(pg['application'])
