"""B1b protocol schema; PostgreSQL cases require explicit isolated opt-in."""
import io
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, BigInteger, DateTime, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session
from app import db
from app.config import Settings
from app.models import (SQLModel, BillingCheckout, BillingEvent, BillingFact, BillingInbox,
                        DownloadIdempotency, DownloadOperation, Job, QuotaCharge,
                        ResourceCounter, ResourceReservation, User)

LEGACY = ['user', 'job', 'quota', 'downloadidempotency', 'membership',
          'billingcheckout', 'billingevent', 'billingpayment', 'downloadaccess']
SEEDS = {('admission_slots', 'global'), ('receipt_entries', 'global')}


@pytest.fixture(scope='module')
def pg():
    marker = os.environ.get('B1B_PG_CONTROL')
    if not marker:
        pytest.skip('B1B_PG_CONTROL explicit isolated PostgreSQL opt-in is required')
    control_path = Path(marker).resolve()
    control = json.loads(control_path.read_text('utf8'))
    assert control_path.parent.name == 'postgres-runtime'
    assert control['host'] == '127.0.0.1' and control['port'] == 62328
    assert control['database'] == 'pv_verify' and control['schema'] == 'app'
    assert control['roles'] == {'bootstrap': 'pv_bootstrap', 'migration': 'pv_migrator', 'application': 'pv_app'}
    engines = {}
    try:
        secrets = json.loads((control_path.parent / 'private/credentials.json').read_text('utf8'))
        for role in ('migration', 'application'):
            url = URL.create('postgresql+psycopg', username=control['roles'][role],
                             password=secrets[role], host=control['host'], port=control['port'],
                             database=control['database'])
            engines[role] = db.build_engine(url, role='migration' if role == 'migration' else 'api')
        del secrets, url
        with engines['migration'].connect() as connection:
            assert connection.scalar(text('SHOW server_version')) == '18.6'
            assert connection.scalar(text('SELECT current_database()')) == 'pv_verify'
        # This dedicated empty synthetic instance may contain an earlier draft head.
        # Every downgrade still passes the revisions' all-business-facts guard.
        migrate(engines, 'downgrade', 'base')
        migrate(engines, 'upgrade', 'head')
        yield engines
    finally:
        for engine in engines.values():
            engine.dispose()


def migrate(pg, action, revision):
    config = db.migration_config()
    with pg['migration'].begin() as connection:
        config.attributes['connection'] = connection
        getattr(command, action)(config, revision)


@pytest.fixture(autouse=True)
def clear_synthetic_rows(request):
    if 'pg' not in request.fixturenames:
        yield
        return
    pg = request.getfixturevalue('pg')
    try:
        yield
    finally:
        with pg['migration'].begin() as connection:
            existing = set(inspect(connection).get_table_names(schema='app'))
            for table in reversed(SQLModel.metadata.sorted_tables):
                if table.name in existing and table.name != 'resourcecounter':
                    connection.execute(table.delete())
            if 'resourcecounter' in existing:
                connection.execute(text("DELETE FROM app.resourcecounter WHERE NOT(scope='global' AND resource IN ('admission_slots','receipt_entries'))"))
                connection.execute(text('UPDATE app.resourcecounter SET used=0'))


def make_operation(**changes):
    now = datetime(2026, 10, 24, 2, tzinfo=timezone.utc)
    def checkpoint(seconds,requests,size,children,purpose,response_bytes):
        return dict(limits=dict(seconds=seconds,requests=requests,redirects=5,raw_bytes=size,
                               decoded_bytes=size,response_raw_bytes=response_bytes,
                               response_decoded_bytes=response_bytes,children=children),
                    purpose=purpose,remaining_seconds=seconds,requests=0,redirects=0,
                    raw_bytes=0,decoded_bytes=0,blocked=None,children=[])
    budget=json.dumps({'download_parent':checkpoint(1800,3072,6*2**30,3,'media',2**31),
                       'direct_resolve_parent':checkpoint(60,128,32*2**20,2,'metadata',8*2**20)},sort_keys=True)
    values = dict(id='operation-one', user_id='user-one', canonical_payload='{}', fingerprint='f'*64,
                  canonical_format_id='best', membership_revision=3, quota_day=date(2026,10,24),
                  state='resolving', accepted_at=now, deadline_at=now+timedelta(minutes=30),
                  resolve_deadline_at=now+timedelta(seconds=60),resolve_attempts_limit=2,
                  budget_version=1,budget_checkpoint_json=budget,budget_checkpoint_at=now)
    values.update(changes)
    return DownloadOperation(**values)


def seed_operation(pg, **changes):
    with Session(pg['application']) as session:
        session.add(User(id='user-one', email='b1b@example.invalid', password_hash='synthetic'))
        session.commit()
        session.add(make_operation(**changes))
        session.commit()


def make_inbox(**changes):
    now = datetime(2026,10,24,tzinfo=timezone.utc)
    values = dict(id='inbox-one', provider_account_scope='synthetic-account', livemode=False,
                  event_id='event-one', event_type='checkout.session.completed', received_at=now,
                  payload_sha256='a'*64, canonical_sha256='b'*64, canonical_version=1,
                  canonical_payload='{}', business_payload='{}', attempt_limit=5,
                  budget_deadline=now+timedelta(hours=24), next_run_at=now)
    values.update(changes)
    return BillingInbox(**values)


def test_protocol_models_registered():
    assert {'downloadoperation', 'quotacharge', 'resourcecounter',
            'resourcereservation', 'billinginbox', 'billingfact'} <= set(SQLModel.metadata.tables)


def test_admission_limits_are_configurable_and_bounded(monkeypatch):
    assert Settings().download_admission_global_limit==32
    assert Settings().download_admission_user_limit==2
    monkeypatch.setenv('DOWNLOAD_ADMISSION_GLOBAL_LIMIT','7')
    monkeypatch.setenv('DOWNLOAD_ADMISSION_USER_LIMIT','3')
    settings=Settings.from_env()
    assert settings.download_admission_global_limit==7 and settings.download_admission_user_limit==3
    for values in ({'download_admission_global_limit':0},{'download_admission_user_limit':-1},
                   {'download_admission_global_limit':True},{'download_admission_user_limit':10001}):
        with pytest.raises(ValueError):
            Settings(**values)


def test_protocol_revision_single_chain():
    scripts = ScriptDirectory.from_config(db.migration_config())
    assert scripts.get_heads() == ['b1b_0003']
    assert scripts.get_revision('b1b_0003').down_revision == 'b1b_0002'
    assert scripts.get_revision('b1b_0002').down_revision == 'b1_0001'


def test_durable_budget_tree_and_absolute_deadlines_registered():
    columns=SQLModel.metadata.tables['downloadoperation'].columns
    assert {'budget_version','budget_checkpoint_json','budget_checkpoint_at',
            'deadline_at','resolve_deadline_at','resolve_attempt_deadline'} <= set(columns.keys())


def test_incremental_preserves_nine_legacy_tables_and_seeds_receipts(pg):
    migrate(pg, 'downgrade', 'base')
    migrate(pg, 'upgrade', 'b1_0001')
    statements = [
        "INSERT INTO app.\"user\" VALUES('old-user','old@example.invalid','fake','2020-01-02T03:04:05+08:00')",
        "INSERT INTO app.job(id,url,status,progress,file_size,created_at,updated_at,user_id) VALUES('old-job','synthetic','queued',0,2147483648,now(),now(),'old-user')",
        "INSERT INTO app.quota VALUES('old-quota','old-user','2020-01-01',7,123)",
        "INSERT INTO app.downloadidempotency(id,user_id,key,fingerprint,state,created_at) VALUES('old-receipt','old-user','old-key','old-fingerprint','pending',1234.125),('old-uncertain','old-user','uncertain-key','old-fingerprint','uncertain',1250.5)",
        "INSERT INTO app.membership VALUES('old-user',NULL,NULL,'free',1234.125,false,'old-checkout',19,'old-source')",
        "INSERT INTO app.billingcheckout(id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,fulfilled) VALUES('old-checkout','old-user','old-price','payment',30,'synthetic',1234.125,1250.5,'pending',false)",
        "INSERT INTO app.billingevent VALUES('old-event',1234.125)",
        "INSERT INTO app.billingpayment VALUES('old-pi',NULL,NULL,true)",
        "INSERT INTO app.downloadaccess VALUES('old-job',720)",
    ]
    with pg['migration'].begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        snapshots = {name: [dict(row) for row in connection.execute(text('SELECT * FROM app."'+name+'"')).mappings()] for name in LEGACY}
    migrate(pg, 'upgrade', 'b1b_0002')
    with pg['migration'].connect() as connection:
        assert connection.scalar(text("SELECT used FROM app.resourcecounter WHERE resource='receipt_entries' AND scope='global'")) == 2
        assert connection.scalar(text("SELECT used FROM app.resourcecounter WHERE resource='admission_slots' AND scope='global'")) == 0
        assert connection.scalar(text('SELECT count(*) FROM app.downloadoperation')) == 0
        assert connection.scalar(text('SELECT count(*) FROM app.quotacharge')) == 0
    migrate(pg, 'upgrade', 'b1b_0003')
    with pg['migration'].connect() as connection:
        for name, rows in snapshots.items():
            columns = ','.join('"'+column+'"' for column in rows[0])
            assert [dict(row) for row in connection.execute(text('SELECT '+columns+' FROM app."'+name+'"')).mappings()] == rows
        assert connection.scalar(text('SELECT count(*) FROM app.downloadidempotency WHERE operation_id IS NOT NULL OR expires_at IS NOT NULL')) == 0
        event = connection.execute(text('SELECT provider_account_scope,livemode,outcome FROM app.billingevent')).one()
        assert tuple(event) == ('legacy_unknown',None,None)
        checkout = connection.execute(text('SELECT create_payload,reconciliation,revision,reconcile_attempts FROM app.billingcheckout')).one()
        assert tuple(checkout) == (None,None,0,0)


def test_reflection_orm_named_constraints_and_types(pg):
    with pg['migration'].connect() as connection:
        inspector = inspect(connection)
        assert set(inspector.get_table_names(schema='app')) == set(SQLModel.metadata.tables) | {'alembic_version'}
        assert compare_metadata(MigrationContext.configure(connection), SQLModel.metadata) == []
        for table in SQLModel.metadata.sorted_tables:
            assert inspector.get_pk_constraint(table.name,schema='app')['name'] == table.primary_key.name
            assert {fk['name'] for fk in inspector.get_foreign_keys(table.name,schema='app')} == {fk.name for fk in table.foreign_key_constraints}
            assert {ck['name'] for ck in inspector.get_check_constraints(table.name,schema='app')} == {ck.name for ck in table.constraints if ck.__class__.__name__ == 'CheckConstraint'}
        for name in ('downloadoperation','quotacharge','resourcereservation','billinginbox','billingfact'):
            for column in SQLModel.metadata.tables[name].columns:
                if isinstance(column.type,DateTime):
                    assert column.type.timezone
                if column.name in ('used','units','delta','amount_total','amount_refunded','lease_epoch','resolve_epoch','source_bytes_limit'):
                    assert isinstance(column.type,BigInteger)
        for name in ('downloadoperation','quotacharge','resourcereservation','billinginbox','billingfact'):
            assert all(fk['options'].get('ondelete') == 'RESTRICT' for fk in inspector.get_foreign_keys(name,schema='app'))


@pytest.mark.parametrize('changes', [
    {'state':'invalid'}, {'membership_revision':-1}, {'max_height':0}, {'resolve_epoch':-1},
    {'resolve_attempts_used':3}, {'budget_version':0}, {'budget_checkpoint_json':''},
    {'resolve_owner':'unpaired'},
    {'deadline_at':datetime(2000,1,1,tzinfo=timezone.utc)},
    {'resolve_deadline_at':datetime(2000,1,1,tzinfo=timezone.utc)},
])
def test_operation_checks_reject_invalid_facts(pg, changes):
    with Session(pg['application']) as session:
        session.add(User(id='user-one',email='invalid@example.invalid',password_hash='synthetic'))
        session.commit()
        session.add(make_operation(**changes))
        with pytest.raises(IntegrityError):
            session.commit()


def test_unique_job_and_receipt_links_and_delete_restrict(pg):
    seed_operation(pg)
    with Session(pg['application']) as session:
        session.add(Job(id='job-one',url='synthetic',user_id='user-one'))
        session.commit()
        operation=session.get(DownloadOperation,'operation-one')
        operation.job_id='job-one'
        session.add(operation)
        session.add(DownloadIdempotency(id='receipt-one',user_id='user-one',key='one',fingerprint='f',operation_id=operation.id))
        session.commit()
    bad_statements = [
        "UPDATE app.downloadoperation SET user_id='orphan'",
        "DELETE FROM app.downloadoperation WHERE id='operation-one'",
        "DELETE FROM app.job WHERE id='job-one'",
        "INSERT INTO app.downloadidempotency(id,user_id,key,fingerprint,state,created_at,operation_id) VALUES('receipt-two','user-one','two','f','pending',1,'operation-one')",
    ]
    for sql in bad_statements:
        with pytest.raises(IntegrityError):
            with pg['application'].begin() as connection:
                connection.execute(text(sql))
    with Session(pg['application']) as session:
        session.add(make_operation(id='operation-two',job_id='job-one'))
        with pytest.raises(IntegrityError):
            session.commit()


def test_charge_unique_delta_and_utc_date_and_bigint(pg):
    local_time=datetime(2026,10,24,10,tzinfo=timezone(timedelta(hours=8)))
    seed_operation(pg,accepted_at=local_time)
    with Session(pg['application']) as session:
        charge=QuotaCharge(operation_id='operation-one',user_id='user-one',quota_day=date(2026,10,24),charged_at=local_time)
        session.add(charge)
        session.commit()
        session.refresh(charge)
        assert charge.charged_at.utcoffset() == timedelta(0)
        assert charge.quota_day == date(2026,10,24)
        operation=session.get(DownloadOperation,'operation-one')
        budget=json.loads(operation.budget_checkpoint_json)
        assert budget['download_parent']['limits']['raw_bytes'] == 6*2**30
        assert budget['direct_resolve_parent']['limits']['decoded_bytes'] == 32*2**20
        assert (operation.deadline_at-operation.accepted_at).total_seconds()==1800
        assert (operation.resolve_deadline_at-operation.accepted_at).total_seconds()==60
    for sql in ["UPDATE app.quotacharge SET delta=0", "UPDATE app.quotacharge SET delta=-1", "INSERT INTO app.quotacharge SELECT * FROM app.quotacharge"]:
        with pytest.raises(IntegrityError):
            with pg['application'].begin() as connection:
                connection.execute(text(sql))


def test_counter_reservation_conditional_release_once(pg):
    seed_operation(pg)
    with Session(pg['application']) as session:
        counter=session.get(ResourceCounter,('admission_slots','global'))
        counter.used=1
        session.add(counter)
        session.add(ResourceReservation(operation_id='operation-one',resource='admission_slots',scope='global',units=1,reserved_at=datetime.now(timezone.utc)))
        session.commit()
    for expected in (1,0):
        with pg['application'].begin() as connection:
            released=connection.execute(text("UPDATE app.resourcereservation SET released=true,released_at=now() WHERE operation_id='operation-one' AND resource='admission_slots' AND scope='global' AND released=false RETURNING units")).all()
            assert len(released)==expected
            if released:
                connection.execute(text("UPDATE app.resourcecounter SET used=used-:units WHERE resource='admission_slots' AND scope='global'"),{'units':released[0][0]})
    for sql in ["UPDATE app.resourcecounter SET used=-1", "UPDATE app.resourcereservation SET units=0", "UPDATE app.resourcereservation SET released_at=NULL", "DELETE FROM app.resourcecounter WHERE resource='admission_slots'", "INSERT INTO app.resourcereservation SELECT * FROM app.resourcereservation"]:
        with pytest.raises(IntegrityError):
            with pg['application'].begin() as connection:
                connection.execute(text(sql))


@pytest.mark.parametrize('changes',[
    {'status':'unknown'}, {'status':'processing'}, {'attempt_count':6}, {'lease_epoch':-1},
    {'lease_owner':'unpaired'}, {'canonical_version':0},
])
def test_inbox_checks(pg,changes):
    with Session(pg['application']) as session:
        session.add(make_inbox(**changes))
        with pytest.raises(IntegrityError):
            session.commit()


def test_inbox_scoped_unique_and_raw_hash_not_business_identity(pg):
    with Session(pg['application']) as session:
        session.add(make_inbox())
        session.add(make_inbox(id='different-mode',livemode=True))
        session.add(make_inbox(id='different-scope',provider_account_scope='another-account'))
        session.commit()
    with Session(pg['application']) as session:
        session.add(make_inbox(id='duplicate',payload_sha256='c'*64))
        with pytest.raises(IntegrityError):
            session.commit()
    with Session(pg['application']) as session:
        row=session.get(BillingInbox,'inbox-one')
        assert row.business_payload=='{}' and row.canonical_sha256=='b'*64
        row.business_payload='{"status":"paid"}'
        session.add(row)
        session.commit()
        session.expire_all()
        assert session.get(BillingInbox,'inbox-one').business_payload=='{"status":"paid"}'


def test_billing_fact_null_unknown_authority_bigint_and_fk(pg):
    with Session(pg['application']) as session:
        session.add(make_inbox())
        session.commit()
        session.add(BillingFact(id='unknown',observed_at=datetime.now(timezone.utc)))
        session.add(BillingFact(id='known',inbox_id='inbox-one',provider_account_scope='synthetic-account',livemode=False,amount_total=2**33,amount_refunded=1,currency='cny',reconciliation='verified',observed_at=datetime.now(timezone.utc)))
        session.commit()
        unknown=session.get(BillingFact,'unknown')
        assert unknown.amount_total is None and unknown.currency is None and unknown.livemode is None
        assert session.get(BillingFact,'known').amount_total==2**33
    for sql in ["UPDATE app.billingfact SET amount_total=-1", "UPDATE app.billingfact SET amount_refunded=-1", "UPDATE app.billingfact SET livemode=true WHERE id='unknown'", "UPDATE app.billingfact SET inbox_id='orphan'", "DELETE FROM app.billinginbox"]:
        with pytest.raises(IntegrityError):
            with pg['application'].begin() as connection:
                connection.execute(text(sql))


@pytest.mark.parametrize('fact',['inbox','fact','counter','reservation'])
def test_nonempty_new_fact_downgrade_refused(pg,fact):
    with Session(pg['application']) as session:
        if fact=='inbox':
            session.add(make_inbox())
        elif fact=='fact':
            session.add(BillingFact(id='protected-fact',observed_at=datetime.now(timezone.utc)))
        elif fact=='counter':
            session.add(ResourceCounter(resource='admission_slots',scope='user:synthetic',used=0))
        else:
            session.add(User(id='user-one',email='reservation@example.invalid',password_hash='fake'))
            session.commit()
            session.add(make_operation())
            session.commit()
            session.add(ResourceReservation(operation_id='operation-one',resource='admission_slots',scope='global',units=1,reserved_at=datetime.now(timezone.utc)))
        session.commit()
    with pytest.raises(RuntimeError,match='nonempty business'):
        migrate(pg,'downgrade','b1b_0002')
    db.assert_schema_current(pg['application'])


@pytest.mark.parametrize('revision',['b1b_0002','b1_0001','base'])
def test_nonempty_legacy_downgrade_refused(pg,revision):
    with Session(pg['application']) as session:
        session.add(BillingEvent(id='old-event',processed_at=1234.125))
        session.commit()
    with pytest.raises(RuntimeError,match='nonempty business'):
        migrate(pg,'downgrade',revision)
    db.assert_schema_current(pg['application'])


def test_empty_downgrade_upgrade_and_application_dml_only(pg):
    migrate(pg,'downgrade','base')
    migrate(pg,'upgrade','head')
    migrate(pg,'upgrade','head')
    db.assert_schema_current(pg['application'])
    with pg['application'].connect() as connection:
        assert set(connection.execute(text('SELECT resource,scope FROM app.resourcecounter')).all())==SEEDS
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError):
        with pg['application'].begin() as connection:
            connection.execute(text('CREATE TABLE app.protocol_forbidden(id BIGINT)'))


def test_offline_upgrade_preview_contains_explicit_incremental_ddl():
    config=db.migration_config()
    output=io.StringIO()
    config.output_buffer=output
    command.upgrade(config,'b1_0001:head',sql=True)
    sql=output.getvalue()
    assert 'CREATE TABLE app.downloadoperation' in sql
    assert 'ON DELETE RESTRICT' in sql
    assert 'TIMESTAMP WITH TIME ZONE' in sql and 'BIGINT' in sql
    assert 'COUNT(*) FROM app.downloadidempotency' in sql
