"""B3b schema/permissions in disposable owned databases; never old DELETE cleanup."""
from datetime import datetime,timedelta,timezone
import io
import json
import os
import socket
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

ADMIN_TABLES=frozenset({'admingrant','adminsession','accountcontrol','adminaudit','adminloginthrottle'})
from sqlalchemy import inspect,text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session

from alembic.script import ScriptDirectory
from app import db
from app.models import SQLModel
from b3b_pg_helpers import (IsolationError,guarded_sockets,isolated_database,pg,
                            schema_pg,validated_control,owned_probe_roles,
                            grant_probe_membership,connection_engine)


def seed(case):
    from app.models import BillingCheckout,BillingReconciliationTask,BillingReconciliationAudit,User
    with Session(case.application) as session:
        now=session.scalar(text('SELECT clock_timestamp()'))
        session.add(User(id='b3b-user',email='b3b@synthetic.invalid',password_hash='synthetic'))
        session.flush()
        session.add(BillingCheckout(id='b3b-checkout',user_id='b3b-user',price_id='b3b-price',mode='payment',duration_days=30,origin='synthetic'))
        session.flush()
        row=BillingReconciliationTask(id='00000000-0000-4000-8000-000000000001',
            checkout_id='b3b-checkout',user_id='b3b-user',provider_account_scope='b3b-scope',
            livemode=False,actor_ref='op:synthetic',reason_code='unknown_create',evidence_ref='ev:synthetic',
            input_sha256='a'*64,query_json='{}',policy_json='{}',initial_checkout_revision=0,
            expected_checkout_revision=0,membership_revision=0,owner_ref='synthetic-owner',
            started_at=now,budget_deadline=now+timedelta(seconds=120))
        session.add(row)
        session.flush()
        session.add(BillingReconciliationAudit(task_id=row.id,seq=1,event_kind='task_started',
                    recorded_at=now,actor_ref='op:synthetic',reason_code='unknown_create',
                    evidence_ref='ev:synthetic',projection_json='{}',projection_sha256='b'*64))
        session.commit()
        return row.id


def rejected(engine,statement,parameters=None,*,code=None):
    with pytest.raises(DBAPIError) as caught:
        with engine.begin() as connection:
            connection.execute(text(statement),parameters or {})
    if code:
        assert caught.value.orig.sqlstate==code


def test_single_successor_and_exact_metadata():
    assert {'billingreconciliationtask','billingreconciliationaudit'} <= set(SQLModel.metadata.tables)
    script=ScriptDirectory.from_config(db.migration_config())
    # C1 (c1_0005) is the single successor of b3b_0004; the b3b link itself is unchanged.
    assert len(script.get_heads())==1 and script.get_revision('c1_0005').down_revision=='b3b_0004'
    assert script.get_revision('b3b_0004').down_revision=='b1b_0003'
    assert len(SQLModel.metadata.tables)==28 and {'jobattempt','artifactmanifest','filereadlease','cleanupintent','orphanobject','dataimport','supportticket','supportpaymentcheck','membershipreissue','membershipcontrol','membershipcontroloperation'} <= set(SQLModel.metadata.tables)


def test_lifecycle_unique_cannot_depend_on_null_ordinal():
    audit=SQLModel.metadata.tables.get('billingreconciliationaudit')
    assert audit is not None
    partial=[i for i in audit.indexes if i.unique and i.dialect_options['postgresql'].get('where') is not None]
    assert len(partial)==1
    assert [c.name for c in partial[0].columns]==['task_id','event_kind']


def test_control_absence_and_wrong_target_fail_before_connect(monkeypatch,tmp_path):
    monkeypatch.delenv('B3B_PG_CONTROL',raising=False)
    monkeypatch.delenv('B3B_PG_OWNERSHIP',raising=False)
    with pytest.raises(IsolationError,match='Explicit'):
        validated_control()
    with pytest.raises(IsolationError,match='mismatch'):
        validated_control(tmp_path/'other.json',tmp_path/'b3b-db-ownership-other.json')


def test_provider_sockets_deny_all_unrelated_services(guarded_sockets):
    for address in [('1.1.1.1',443),('127.0.0.1',5173),('127.0.0.1',8000)]:
        with socket.socket() as connection:
            with pytest.raises(IsolationError,match='denied'):
                connection.connect(address)
    with pytest.raises(IsolationError,match='DNS'):
        socket.getaddrinfo('api.stripe.com',443)
    left,right=socket.socketpair()
    try:
        left.send(b'x')
        assert right.recv(1)==b'x'
    finally:
        left.close()
        right.close()


def test_existing_sqlite_initialization_still_compiles_all_metadata():
    engine=db.build_engine('sqlite://',role='api')
    try:
        SQLModel.metadata.create_all(engine)
        assert len(inspect(engine).get_table_names())==28  # prior 26 business tables + MC control/operation
    finally:
        engine.dispose()


def test_pg_new_tables_present(guarded_sockets):
    if not os.environ.get('B3B_PG_CONTROL'):
        pytest.skip('Explicit B3B_PG_CONTROL opt-in required')
    target='b1b_0003' if os.environ.get('B3B_BASELINE_RED')=='1' else 'head'
    with isolated_database(target=target) as case:
        with case.application.connect() as connection:
            assert {'billingreconciliationtask','billingreconciliationaudit'} <= set(inspect(connection).get_table_names(schema='app'))


def test_pg_exact_reflection_and_named_constraints(schema_pg):
    with schema_pg.migration.connect() as connection:
        inspector=inspect(connection)
        assert len(inspector.get_table_names(schema='app'))==34  # + MC two control tables + C1 jobattempt + C2 artifactmanifest + C4 filereadlease + C5 cleanupintent + orphanobject + B6 dataimport + M1 five admin tables + T1 three support tables
        assert connection.scalar(text('SELECT version_num FROM app.alembic_version'))=='mc_0016'
        # Admin M1 tables live on their own MetaData (app.models_admin), checked by test_pg_admin_schema.
        business=MigrationContext.configure(connection,opts={'include_object':lambda obj,name,type_,reflected,compare_to:
            not (type_=='table' and name in ADMIN_TABLES)})
        assert compare_metadata(business,SQLModel.metadata)==[]
        for name in ('billingreconciliationtask','billingreconciliationaudit'):
            table=SQLModel.metadata.tables[name]
            assert {c['name'] for c in inspector.get_columns(name,schema='app')}==set(table.c.keys())
            assert {c['name'] for c in inspector.get_check_constraints(name,schema='app')}=={c.name for c in table.constraints if c.__class__.__name__=='CheckConstraint'}
            assert all(fk['options']['ondelete']=='RESTRICT' for fk in inspector.get_foreign_keys(name,schema='app'))
        triggers=connection.execute(text("SELECT c.relname,t.tgname,t.tgenabled,p.prosecdef,p.proconfig FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_proc p ON p.oid=t.tgfoid WHERE c.relname IN ('billingreconciliationtask','billingreconciliationaudit') AND NOT t.tgisinternal")).all()
        assert len(triggers)==5 and all(row[2]=='O' and not row[3] and row[4]==['search_path=pg_catalog'] for row in triggers)


def test_effective_acl_narrows_inherited_default_dml(schema_pg):
    with schema_pg.migration.connect() as connection:
        for table,allowed in [('billingreconciliationaudit',{'SELECT','INSERT'}),('billingreconciliationtask',{'SELECT','INSERT','UPDATE'})]:
            for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                assert connection.scalar(text('SELECT has_table_privilege(\'pv_app\',:table,:privilege)'),{'table':'app.'+table,'privilege':privilege})==(privilege in allowed)
        assert connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_default_acl a,LATERAL aclexplode(a.defaclacl) x WHERE a.defaclnamespace='app'::regnamespace AND x.grantee='pv_app'::regrole AND x.privilege_type='DELETE')"))
        assert not connection.scalar(text("SELECT has_database_privilege('pv_app',current_database(),'TEMP') OR has_database_privilege('pv_app',current_database(),'CREATE') OR has_schema_privilege('pv_app','app','CREATE')"))


def test_application_audit_is_append_only(schema_pg):
    seed(schema_pg)
    for engine,code in [(schema_pg.application,'42501'),(schema_pg.migration,'23514')]:
        for sql in ['UPDATE app.billingreconciliationaudit SET projection_json=\'{}\'',
                    'DELETE FROM app.billingreconciliationaudit','TRUNCATE app.billingreconciliationaudit',
                    'DELETE FROM app.billingreconciliationtask','TRUNCATE app.billingreconciliationtask CASCADE']:
            rejected(engine,sql,code=code)
    rejected(schema_pg.application,'ALTER TABLE app.billingreconciliationaudit DISABLE TRIGGER ALL',code='42501')
    with schema_pg.application.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.billingreconciliationaudit'))==1


def test_task_identity_budget_and_terminal_are_monotonic(schema_pg):
    seed(schema_pg)
    for assignment in ["owner_ref='changed'","checkout_id='orphan'","user_id='orphan'",
                       "actor_ref='op:changed'","evidence_ref='ev:changed'","query_json='{\"changed\": true}'",
                       "policy_json='{\"changed\": true}'","budget_deadline=budget_deadline+interval '1 second'",
                       'get_limit=4','get_attempts=2','input_version=2','membership_revision=1']:
        rejected(schema_pg.application,'UPDATE app.billingreconciliationtask SET '+assignment,code='23514')
    with schema_pg.application.begin() as connection:
        connection.execute(text('UPDATE app.billingreconciliationtask SET get_attempts=1,next_audit_seq=5,revision=1,expected_checkout_revision=1'))
    for assignment in ['get_attempts=0','get_attempts=3','next_audit_seq=4','revision=0','expected_checkout_revision=0']:
        rejected(schema_pg.application,'UPDATE app.billingreconciliationtask SET '+assignment,code='23514')
    with schema_pg.application.begin() as connection:
        connection.execute(text("UPDATE app.billingreconciliationtask SET status='needs_review',outcome_reason='synthetic_finished',completed_at=clock_timestamp(),revision=2"))
    for assignment in ["status='running',completed_at=NULL",'get_attempts=2','revision=3',"outcome_reason='changed'"]:
        rejected(schema_pg.application,'UPDATE app.billingreconciliationtask SET '+assignment,code='23514')


def test_lifecycle_and_get_ordinal_uniqueness_are_enforced(schema_pg):
    task_id=seed(schema_pg)
    template="INSERT INTO app.billingreconciliationaudit(id,task_id,seq,event_kind,get_ordinal,recorded_at,actor_ref,reason_code,evidence_ref,projection_version,projection_json,projection_sha256) VALUES(:id,:task,:seq,:kind,:ordinal,clock_timestamp(),'op:synthetic','unknown_create','ev:synthetic',1,'{}',:sha)"
    def values(kind,ordinal,seq):
        return dict(id=str(uuid.uuid4()),task=task_id,seq=seq,kind=kind,ordinal=ordinal,sha='b'*64)
    rejected(schema_pg.application,template,values('task_started',None,2),code='23505')
    for kind,ordinal in [('get_reserved',None),('get_observed',0),('get_observed',4),('task_finished',1),('unknown',None)]:
        rejected(schema_pg.application,template,values(kind,ordinal,2),code='23514')
    with schema_pg.application.begin() as connection:
        connection.execute(text(template),values('get_reserved',1,2))
        connection.execute(text(template),values('get_observed',1,3))
        connection.execute(text(template),values('task_finished',None,4))
    rejected(schema_pg.application,template,values('get_reserved',1,5),code='23505')
    rejected(schema_pg.application,template,values('task_finished',None,5),code='23505')


def test_new_checks_json_size_hash_versions_and_unique_checkout(schema_pg):
    from app.models import BillingReconciliationTask,BillingReconciliationAudit
    task_id=seed(schema_pg)
    with Session(schema_pg.application) as session:
        original=session.get(BillingReconciliationTask,task_id)
        snapshot=original.model_dump()
    variants=[dict(input_version=2),dict(budget_version=2),dict(get_limit=4),dict(get_attempts=-1),
              dict(input_sha256='G'*64),dict(query_json='[]'),dict(policy_json='null'),
              dict(query_json=json.dumps({'x':'A'*65536})),dict(actor_ref='email@example.invalid')]
    for changes in variants:
        # Same Checkout uniqueness is avoided by testing each constraint on a new
        # raw INSERT whose checkout FK is the same; CHECKs precede unique checks.
        values=dict(snapshot,id=str(uuid.uuid4()),**changes)
        with Session(schema_pg.application) as session:
            session.add(BillingReconciliationTask(**values))
            with pytest.raises(DBAPIError) as caught:
                session.commit()
            assert caught.value.orig.sqlstate=='23514'
    with Session(schema_pg.application) as session:
        session.add(BillingReconciliationTask(**dict(snapshot,id=str(uuid.uuid4()))))
        with pytest.raises(DBAPIError) as caught:
            session.commit()
        assert caught.value.orig.sqlstate=='23505'


def test_legacy_checkout_fields_preserved(guarded_sockets):
    if not os.environ.get('B3B_PG_CONTROL'):
        pytest.skip('Explicit B3B_PG_CONTROL opt-in required')
    from app.models import BillingCheckout,User
    with isolated_database(target='b1b_0003') as case:
        with Session(case.application) as session:
            session.add(User(id='legacy',email='legacy@synthetic.invalid',password_hash='fake'))
            session.flush()
            session.add(BillingCheckout(id='old-reference',user_id='legacy',price_id='old-price',mode='payment',duration_days=30,origin='old-origin',created_at=1234.125,
                       reconcile_attempts=2,reconciliation_started_at=datetime(2020,1,1,tzinfo=timezone.utc),
                       reconciliation_actor='old-observation',reconciliation_evidence='old-evidence',revision=9))
            session.commit()
        with case.application.connect() as connection:
            before=connection.scalar(text('SELECT to_jsonb(t) FROM app.billingcheckout t'))
        case.migrate()
        with case.application.connect() as connection:
            assert connection.scalar(text('SELECT to_jsonb(t) FROM app.billingcheckout t'))==before
            assert connection.scalar(text('SELECT count(*) FROM app.billingreconciliationtask'))==0
            assert connection.scalar(text('SELECT count(*) FROM app.billingreconciliationaudit'))==0


def test_missing_or_unsafe_runtime_roles_fail_before_ddl(guarded_sockets):
    if not os.environ.get('B3B_PG_CONTROL'):
        pytest.skip('Explicit B3B_PG_CONTROL opt-in required')
    with isolated_database(target='b1b_0003') as case:
        for roles in (None,(),('pv_app;DROP',),('pv_migrator',),('pv_bootstrap',),('missing_b3b_role',)):
            with pytest.raises(RuntimeError,match='B3b'):
                case.migrate(runtime_roles=roles)
            with case.application.connect() as connection:
                assert connection.scalar(text('SELECT version_num FROM app.alembic_version'))=='b1b_0003'
                assert 'billingreconciliationtask' not in inspect(connection).get_table_names(schema='app')


@pytest.mark.parametrize('parent',['pg_read_server_files','pg_signal_backend'])
def test_runtime_rejects_predefined_role_inheritance_before_ddl(guarded_sockets,parent):
    if not os.environ.get('B3B_PG_CONTROL'):
        pytest.skip('Explicit B3B_PG_CONTROL opt-in required')
    with owned_probe_roles() as roles:
        with isolated_database(target='b1b_0003') as case:
            grant_probe_membership(parent,roles[0])
            with pytest.raises(RuntimeError,match='B3b'):
                case.migrate(runtime_roles=tuple(roles))
            with case.application.connect() as connection:
                assert 'billingreconciliationtask' not in inspect(connection).get_table_names(schema='app')


def test_runtime_rejects_existing_relation_owner_inheritance(guarded_sockets):
    if not os.environ.get('B3B_PG_CONTROL'):
        pytest.skip('Explicit B3B_PG_CONTROL opt-in required')
    with owned_probe_roles(2) as roles:
        with isolated_database(target='b1b_0003') as case:
            control,_,_=validated_control()
            admin=connection_engine(control,'bootstrap',case.database,bootstrap=True)
            try:
                with admin.begin() as connection:
                    connection.execute(text('CREATE TABLE app.b3b_existing_owned_probe(id INTEGER)'))
                    connection.execute(text('ALTER TABLE app.b3b_existing_owned_probe OWNER TO "'+roles[0]+'"'))
            finally:
                admin.dispose()
            grant_probe_membership(roles[0],roles[1])
            with pytest.raises(RuntimeError,match='B3b'):
                case.migrate(runtime_roles=(roles[1],))
            with case.application.connect() as connection:
                assert 'billingreconciliationtask' not in inspect(connection).get_table_names(schema='app')


def test_nonempty_audit_downgrade_refused(schema_pg):
    seed(schema_pg)
    with pytest.raises(RuntimeError,match='nonempty business'):
        schema_pg.migrate('downgrade','b1b_0003')
    with schema_pg.application.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.billingreconciliationaudit'))==1
        # The whole multi-step downgrade rolls back, so the database stays at the current head.
        assert connection.scalar(text('SELECT version_num FROM app.alembic_version'))=='mc_0016'


def test_empty_downgrade_and_upgrade_only_in_disposable_db(schema_pg):
    schema_pg.migrate('downgrade','b1b_0003')
    schema_pg.migrate()
    with schema_pg.application.connect() as connection:
        assert len(inspect(connection).get_table_names(schema='app'))==34  # + MC two control tables + C1/C2/C4/C5 tables + B6 dataimport + M1 admin + T1 support at head


def test_offline_preview_requires_explicit_roles_and_refuses_downgrade():
    config=db.migration_config()
    config.output_buffer=io.StringIO()
    with pytest.raises(RuntimeError,match='explicit runtime roles'):
        command.upgrade(config,'b1b_0003:b3b_0004',sql=True)
    config.attributes['b3b_runtime_roles']=('pv_app',)
    command.upgrade(config,'b1b_0003:b3b_0004',sql=True)
    assert 'CREATE TRIGGER trg_b3b_audit_truncate' in config.output_buffer.getvalue()
    with pytest.raises(RuntimeError,match='Offline destructive'):
        command.downgrade(config,'b3b_0004:b1b_0003',sql=True)
