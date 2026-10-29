"""B3b additions only; disposable PG fixture, synthetic provider, no real HTTP."""
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import event, func, text
from sqlmodel import Session, select

from b3b_pg_helpers import pg, schema_pg, guarded_sockets
from app.models import (User, Membership, BillingCheckout, BillingReconciliationTask as Task,
    BillingReconciliationAudit as Audit, BillingPayment, BillingEvent, BillingInbox, BillingFact)
from app.services.billing_pg import BillingConfiguration, _freeze
from app.services.billing_projection import digest, encode
import app.services.billing_reconciliation as subject
from app.services.billing_reconciliation import AuditContext, ReconciliationPolicy

CFG=BillingConfiguration('b3b-synthetic',False)


# Runs in a fresh interpreter before importing any test/app/helper module.
# Keep it stdlib-only: b3b_pg_helpers itself imports app.db at module scope.
_CHILD_SOCKET_BOOTSTRAP = r'''
import socket as _b3b_socket
from threading import local as _b3b_local
_b3b_state = _b3b_local()
_b3b_connect = _b3b_socket.socket.connect
_b3b_connect_ex = _b3b_socket.socket.connect_ex
_b3b_resolve = _b3b_socket.getaddrinfo
_b3b_pair = _b3b_socket.socketpair
def _b3b_allowed(address):
    return (isinstance(address,tuple) and address[0] in {'127.0.0.1','::1'}
            and (address[1]==62328 or getattr(_b3b_state,'pair',False)))
def _b3b_guard_connect(sock,address):
    if not _b3b_allowed(address): raise AssertionError('B3b child external socket denied')
    return _b3b_connect(sock,address)
def _b3b_guard_connect_ex(sock,address):
    if not _b3b_allowed(address): raise AssertionError('B3b child external socket denied')
    return _b3b_connect_ex(sock,address)
def _b3b_guard_resolve(host,port,*args,**kwargs):
    if host not in {'127.0.0.1','::1'} or str(port)!='62328':
        raise AssertionError('B3b child external DNS denied')
    return _b3b_resolve(host,port,*args,**kwargs)
def _b3b_guard_sendto(*args,**kwargs):
    raise AssertionError('B3b child UDP denied')
def _b3b_guard_pair(*args,**kwargs):
    _b3b_state.pair=True
    try: return _b3b_pair(*args,**kwargs)
    finally: _b3b_state.pair=False
_b3b_socket.socket.connect=_b3b_guard_connect
_b3b_socket.socket.connect_ex=_b3b_guard_connect_ex
_b3b_socket.socket.sendto=_b3b_guard_sendto
_b3b_socket.getaddrinfo=_b3b_guard_resolve
_b3b_socket.socketpair=_b3b_guard_pair
_b3b_socket._b3b_preimport_guard_installed=True
'''


def context():
    return AuditContext(str(uuid.uuid4()),'op:synthetic','unknown_create','ev:synthetic')


def seed(engine, *, known=True, legacy=False, old=False):
    with Session(engine,expire_on_commit=False) as session:
        now=session.exec(select(func.clock_timestamp())).one()
        session.add(User(id='b3b-user',email='b3b@synthetic.invalid',password_hash='disabled'))
        session.flush()
        session.add(Membership(user_id='b3b-user',active_checkout_id='b3b-checkout'))
        row=BillingCheckout(id='b3b-checkout',user_id='b3b-user',price_id='price_original',mode='payment',
            duration_days=30,origin='https://synthetic.invalid',provider_account_scope=CFG.scope,
            livemode=False,stripe_id='cs_original' if known else None,created_at=now.timestamp()-1000,
            create_result_code='provider_unknown',reconciliation='unknown')
        if not legacy:
            row.create_payload=_freeze(row);row.create_payload_sha256=digest(row.create_payload);row.create_payload_version=1
        if old:row.reconcile_attempts=1;row.reconciliation_actor='historical'
        session.add(row);session.commit()
        return row


def obj(row):
    return dict(id='cs_original',livemode=False,mode='payment',metadata=dict(checkout_id=row.id),
        client_reference_id=row.user_id,customer='cus_observed',payment_intent='pi_observed',subscription=None,
        created=int(row.created_at)+1,line_items=dict(has_more=False,data=[dict(price=row.price_id,quantity=1)]),
        success_url=row.origin+'/?membership=success',cancel_url=row.origin+'/?membership=cancel',
        amount_total=990,currency='cny',status='complete',payment_status='paid')


class Provider:
    def __init__(self, value, pages=None):
        self.value=value;self.pages=pages or [];self.calls=[];self.callback=None;self.failure=None
    def __call__(self):return self
    def _call(self,kind,value):
        self.calls.append((kind,copy.deepcopy(value)))
        if self.callback:self.callback(kind,value)
        if self.failure:raise self.failure
    def retrieve_session(self,identity):
        self._call('retrieve',identity);return copy.deepcopy(self.value)
    def list_sessions(self,params):
        self._call('list',params);return copy.deepcopy(self.pages.pop(0))


def run(engine,provider,audit=None,policy=None):
    return subject.reconcile_checkout('b3b-checkout',audit or context(),engine=engine,cfg=CFG,
        policy=policy or ReconciliationPolicy(),provider=provider)


def rows(engine):
    with Session(engine) as session:
        task=session.exec(select(Task)).one()
        audits=session.exec(select(Audit).order_by(Audit.seq)).all()
        checkout=session.get(BillingCheckout,'b3b-checkout')
        return task,audits,checkout


def domain(engine):
    with Session(engine) as session:
        return {model.__name__:[row.model_dump() for row in session.exec(select(model)).all()]
                for model in (Membership,BillingPayment,BillingEvent,BillingInbox,BillingFact)}


def test_reference_only_success_preserves_payment_domain(pg):
    row=seed(pg,known=False);provider=Provider(obj(row),[dict(data=[obj(row)],has_more=False)])
    before=domain(pg);result=run(pg,provider)
    assert result.status=='verified' and result.get_attempts==2
    task,audits,current=rows(pg)
    assert current.stripe_id=='cs_original' and current.reconciliation=='verified'
    assert (current.state,current.url,current.expires_at,current.fulfilled,current.create_payload)==(
        row.state,row.url,row.expires_at,row.fulfilled,row.create_payload)
    assert before==domain(pg)
    assert [a.event_kind for a in audits]==['task_started','get_reserved','get_observed','get_reserved','get_observed','task_finished']
    assert task.status=='verified' and task.next_audit_seq==7


def test_reservation_commit_precedes_every_get(pg):
    row=seed(pg,known=False);value=obj(row)
    provider=Provider(value,[dict(data=[value],has_more=True),dict(data=[],has_more=False)])
    checked_out=[0]
    def checkout(*args):checked_out[0]+=1
    def checkin(*args):checked_out[0]-=1
    event.listen(pg,'checkout',checkout);event.listen(pg,'checkin',checkin)
    def assert_reserved(kind,params):
        assert checked_out[0]==0
        with Session(pg) as session:
            task=session.exec(select(Task)).one();current=session.get(BillingCheckout,row.id)
            reserved=session.exec(select(Audit).where(Audit.event_kind=='get_reserved')).all()
            assert task.get_attempts==current.reconcile_attempts==len(provider.calls)==len(reserved)
        if len(provider.calls)==2:
            assert params['starting_after']=='cs_original'
            assert params['created']==provider.calls[0][1]['created']
    provider.callback=assert_reserved
    try:assert run(pg,provider).status=='verified'
    finally:
        event.remove(pg,'checkout',checkout);event.remove(pg,'checkin',checkin)
    assert len(provider.calls)==3


def test_one_task_across_parallel_calls_and_restart(pg):
    row=seed(pg);providers=[Provider(obj(row)),Provider(obj(row))]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda p:run(pg,p),providers))
    assert len({r.task_id for r in results})==1
    assert sum(len(p.calls) for p in providers)==1
    current=rows(pg)[0];p=Provider(obj(row));again=run(pg,p)
    assert again.task_id==current.id and not p.calls
    assert rows(pg)[0].budget_deadline==current.budget_deadline


@pytest.mark.parametrize('stage',['task_started','get_reserved','get_observed'])
@pytest.mark.parametrize('visible',[True,False])
def test_unknown_commits_never_dispatch_next_get(pg,monkeypatch,stage,visible):
    row=seed(pg,known=False);provider=Provider(obj(row),[dict(data=[obj(row)],has_more=False)])
    original_commit=Session.commit;injected=[False]
    def commit(session):
        current=session.info.get('b3b_stage')
        original_commit(session)
        if current==stage and not injected[0]:
            injected[0]=True;raise RuntimeError('synthetic_commit_ack_loss')
    monkeypatch.setattr(Session,'commit',commit)
    if not visible:
        monkeypatch.setattr(subject,'_read_uncertain_attempts',lambda *args:None)
    result=run(pg,provider)
    assert injected[0] and result.status=='transaction_uncertain'
    assert len(provider.calls)==(1 if stage=='get_observed' else 0)
    assert result.get_attempts is None if not visible else result.get_attempts is not None
    task,audits,current=rows(pg)
    assert task.get_attempts==current.reconcile_attempts==(0 if stage=='task_started' else 1)
    provider2=Provider(obj(row));run(pg,provider2);assert not provider2.calls


@pytest.mark.parametrize('stage',['task_started','get_reserved','get_observed'])
def test_control_flow_interruption_after_commit_never_resumes_network(pg,monkeypatch,stage):
    row=seed(pg,known=False);provider=Provider(obj(row),[dict(data=[obj(row)],has_more=False)])
    original=subject.run_local_transaction
    class ProcessDeath(BaseException):pass
    def run_transaction(engine,op,action,resolver,**kwargs):
        stage_seen=[]
        def wrapped(session):
            result=action(session);stage_seen.append(session.info.get('b3b_stage'));return result
        result=original(engine,op,wrapped,resolver,**kwargs)
        if stage_seen==[stage]:raise ProcessDeath()
        return result
    monkeypatch.setattr(subject,'run_local_transaction',run_transaction)
    with pytest.raises(ProcessDeath):run(pg,provider)
    task=rows(pg)[0]
    monkeypatch.setattr(subject,'run_local_transaction',original)
    provider2=Provider(obj(row));result=run(pg,provider2)
    assert result.task_id==task.id and not provider2.calls
    now=rows(pg)[0];assert (now.owner_ref,now.budget_deadline,now.actor_ref)==(task.owner_ref,task.budget_deadline,task.actor_ref)


def _spawn_crash_after_commit(database,stage):
    """Child entry: only the parent's explicitly owned application database.

    DB name and fixed stage are nonsecret argv. DSN/password are never in argv
    or output; existing B3b fixture helper supplies the application connection.
    No new lifecycle, migration, bootstrap connection or database cleanup.
    """
    from b3b_pg_helpers import (validated_control, connection_engine, IsolationError,
        guarded_sockets as socket_guard)
    monkeypatch=pytest.MonkeyPatch()
    socket_guard.__wrapped__(monkeypatch)
    control,_,ownership=validated_control()
    cases=[case for case in ownership['databases'] if case['database']==database]
    if (len(cases)!=1 or cases[0].get('phase')!='migrated' or cases[0].get('dropped')
            or type(cases[0].get('oid')) is not int or cases[0].get('owner')!='pv_migrator'):
        raise IsolationError('B3b subprocess case ownership rejected')
    case=cases[0]
    engine=connection_engine(control,'application',database)
    with engine.connect() as connection:
        identity=connection.execute(text("SELECT current_database(),current_user,current_setting('server_version'),host(inet_server_addr()),inet_server_port(),(SELECT oid FROM pg_database WHERE datname=current_database()),(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database())")).one()
        if tuple(identity)!=(database,'pv_app','18.6','127.0.0.1',62328,case['oid'],'pv_migrator'):
            raise IsolationError('B3b subprocess live database identity rejected')
    with Session(engine) as session:
        row=session.get(BillingCheckout,'b3b-checkout')
        value=obj(row)
    provider=Provider(value,[dict(data=[value],has_more=False)])
    real_runner=subject.run_local_transaction
    def runner(instance,operation,action,resolver,**kwargs):
        stages=[]
        def wrapped(session):
            result=action(session);stages.append(session.info.get('b3b_stage'));return result
        result=real_runner(instance,operation,wrapped,resolver,**kwargs)
        if stages==[stage]:
            # os.write is unbuffered; the parent observes actual child provider
            # calls, not its own separate fake provider's empty list.
            os.write(1,(json.dumps(dict(committed_stage=stage,fake_get_calls=len(provider.calls)))+'\n').encode('ascii'))
            os._exit(91)
        return result
    subject.run_local_transaction=runner
    run(engine,provider)
    raise AssertionError('Expected commit stage was never reached')


@pytest.mark.parametrize('stage',['task_started','get_reserved','get_observed'])
def test_spawn_process_death_after_real_commit_never_resumes_network(pg,stage):
    row=seed(pg,known=False)
    root=Path(__file__).resolve().parents[2]
    os_keys={'SYSTEMROOT','WINDIR','TEMP','TMP','PATH','COMSPEC','PATHEXT','SYSTEMDRIVE'}
    child_env={key:value for key,value in os.environ.items() if key.upper() in os_keys}
    child_env.update(DB_URL='sqlite://',BILIBILI_COOKIE_FILE='',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
        LC_ALL='C',LANG='C',PYTHONPATH=os.pathsep.join((str(root/'backend'),str(root/'backend/tests'))),
        B3B_PG_CONTROL=os.environ['B3B_PG_CONTROL'],B3B_PG_OWNERSHIP=os.environ['B3B_PG_OWNERSHIP'])
    code=_CHILD_SOCKET_BOOTSTRAP+'\nimport sys; from test_pg_billing_reconciliation import _spawn_crash_after_commit; _spawn_crash_after_commit(sys.argv[1],sys.argv[2])'
    child=subprocess.run([sys.executable,'-B','-c',code,pg.url.database,stage],cwd=root,env=child_env,
        capture_output=True,text=True,encoding='utf8',timeout=30,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert child.returncode==91,child.stderr
    receipt=json.loads(child.stdout.strip())
    assert receipt==dict(committed_stage=stage,fake_get_calls=1 if stage=='get_observed' else 0)
    task,audits,current=rows(pg)
    assert task.status=='running'
    assert task.get_attempts==current.reconcile_attempts==(0 if stage=='task_started' else 1)
    expected=['task_started']+(['get_reserved'] if stage!='task_started' else [])+(['get_observed'] if stage=='get_observed' else [])
    assert [audit.event_kind for audit in audits]==expected
    provider=Provider(obj(row));result=run(pg,provider)
    after,after_audits,_=rows(pg)
    assert result.status=='in_progress' and result.task_id==task.id and provider.calls==[]
    assert (after.owner_ref,after.budget_deadline,after.actor_ref,after.get_attempts)==(
        task.owner_ref,task.budget_deadline,task.actor_ref,task.get_attempts)
    assert [audit.model_dump() for audit in after_audits]==[audit.model_dump() for audit in audits]


def test_expired_running_task_inspects_as_needs_review(pg,monkeypatch):
    row=seed(pg);provider=Provider(obj(row));original=subject.run_local_transaction
    class ProcessDeath(BaseException):pass
    def runner(*args,**kwargs):
        original(*args,**kwargs);raise ProcessDeath()
    monkeypatch.setattr(subject,'run_local_transaction',runner)
    with pytest.raises(ProcessDeath):run(pg,provider,policy=ReconciliationPolicy(total_seconds=1))
    task,audits,_=rows(pg)
    assert subject.inspect_reconciliation(task.id,engine=pg).status=='in_progress'
    with pg.connect() as connection:connection.execute(text('SELECT pg_sleep(1.05)'))
    result=subject.inspect_reconciliation(task.id,engine=pg)
    assert (result.status,result.reason_code)==('needs_review','deadline_elapsed')
    after=rows(pg);assert after[0].status=='running' and len(after[1])==len(audits)


@pytest.mark.parametrize('legacy,old,known',[(True,False,False),(True,False,True),(False,True,True)])
def test_legacy_evidence_and_prior_manual_markers_never_reconstructed(pg,legacy,old,known):
    row=seed(pg,known=known,legacy=legacy,old=old);provider=Provider(obj(row))
    result=run(pg,provider)
    assert result.status=='needs_review' and len(provider.calls)==(1 if legacy and known and not old else 0)
    task,_,current=rows(pg)
    assert task.get_attempts==len(provider.calls)
    if old:assert current.reconcile_attempts==1 and current.reconciliation_actor=='historical'
    assert current.create_payload==row.create_payload


@pytest.mark.parametrize('change',['membership','checkout','reference'])
def test_revision_scope_or_reference_changes_block_binding(pg,change):
    row=seed(pg);provider=Provider(obj(row))
    def callback(*args):
        with Session(pg) as session:
            model=Membership if change=='membership' else BillingCheckout
            current=session.get(model,row.user_id if model is Membership else row.id)
            if change=='reference':current.stripe_id='cs_changed'
            current.revision+=1;session.add(current);session.commit()
    provider.callback=callback;result=run(pg,provider)
    assert result.status=='needs_review'
    assert rows(pg)[2].stripe_id==('cs_changed' if change=='reference' else 'cs_original')


def test_late_result_cannot_bind_and_retains_refund_tombstone(pg):
    row=seed(pg,known=False);value=obj(row);provider=Provider(value,[dict(data=[value],has_more=False)])
    with Session(pg) as session:
        session.add(BillingPayment(payment_intent='pi_observed',user_id=row.user_id,revoked=True));session.commit()
    before=domain(pg)
    def callback(*args):
        with pg.connect() as connection:connection.execute(text('SELECT pg_sleep(1.05)'))
    provider.callback=callback
    result=run(pg,provider,policy=ReconciliationPolicy(total_seconds=1))
    assert result.status=='needs_review' and result.reason_code=='late_result' and len(provider.calls)==1
    assert rows(pg)[2].stripe_id is None and before==domain(pg)


def test_network_error_is_one_get_no_retry(pg):
    row=seed(pg);provider=Provider(obj(row));provider.failure=RuntimeError('secret-provider-body')
    result=run(pg,provider)
    assert result.status=='needs_review' and len(provider.calls)==1
    assert 'secret-provider-body' not in encode([a.model_dump(mode='json') for a in rows(pg)[1]])


@pytest.mark.parametrize('pages',[
    [dict(data=[],has_more=True)],
    [dict(data=[],has_more=1)],
    [dict(data=[],has_more=False)],
    [dict(data=[],has_more=False),dict(data=[],has_more=False)],
])
def test_incomplete_or_empty_query_never_establishes_a_reference(pg,pages):
    row=seed(pg,known=False);provider=Provider(obj(row),copy.deepcopy(pages))
    result=run(pg,provider)
    assert result.status=='needs_review' and rows(pg)[2].stripe_id is None
    assert len(provider.calls)==1


def test_monotonic_expiry_after_reservation_preserves_count_without_get(pg,monkeypatch):
    row=seed(pg);provider=Provider(obj(row));times=iter([0,301])
    monkeypatch.setattr(subject.time,'monotonic',lambda:next(times))
    result=run(pg,provider)
    assert (result.status,result.reason_code,result.get_attempts)==('needs_review','deadline_elapsed',1)
    assert provider.calls==[] and rows(pg)[2].reconcile_attempts==1


@pytest.mark.parametrize('table,counter',[('billingreconciliationtask','get_attempts='),('billingcheckout','reconcile_attempts=')])
def test_reservation_uses_db_clock_at_actual_update_without_partial_counts(pg,table,counter):
    row=seed(pg);provider=Provider(obj(row));delayed=[False]
    def delay(connection,cursor,statement,parameters,context,executemany):
        sql=statement.lower().replace(' ','')
        if not delayed[0] and sql.startswith('update') and table in sql and counter in sql:
            delayed[0]=True
            # Delays the actual UPDATE after the coordinator sampled DB `now`.
            # Direct cursor avoids recursive SQLAlchemy event dispatch.
            cursor.execute('SELECT pg_sleep(1.05)')
    event.listen(pg,'before_cursor_execute',delay)
    try:result=run(pg,provider,policy=ReconciliationPolicy(total_seconds=1))
    finally:event.remove(pg,'before_cursor_execute',delay)
    assert delayed[0] and result.status=='needs_review' and result.reason_code=='deadline_elapsed'
    task,audits,current=rows(pg)
    assert task.get_attempts==current.reconcile_attempts==0 and provider.calls==[]
    assert not [a for a in audits if a.event_kind=='get_reserved']


def test_final_commit_ack_is_confirmed_by_exact_audit(pg,monkeypatch):
    row=seed(pg);provider=Provider(obj(row));original=Session.commit;injected=[False]
    def commit(session):
        stage=session.info.get('b3b_stage');original(session)
        if stage=='task_finished' and not injected[0]:injected[0]=True;raise RuntimeError('ack_lost')
    monkeypatch.setattr(Session,'commit',commit)
    result=run(pg,provider)
    assert injected[0] and result.status=='verified' and len(provider.calls)==1


def test_final_reference_update_uses_real_db_clock_after_delay(pg):
    row=seed(pg,known=False);value=obj(row)
    provider=Provider(value,[dict(data=[value],has_more=False)])
    delayed=[False]
    def delay(connection,cursor,statement,parameters,context,executemany):
        sql=statement.lower().replace(' ','')
        if (not delayed[0] and sql.startswith('update') and 'billingcheckout' in sql
                and 'stripe_id=' in sql and 'reconciliation=' in sql):
            delayed[0]=True;cursor.execute('SELECT pg_sleep(1.05)')
    before=domain(pg)
    event.listen(pg,'before_cursor_execute',delay)
    try:result=run(pg,provider,policy=ReconciliationPolicy(total_seconds=1))
    finally:event.remove(pg,'before_cursor_execute',delay)
    task,audits,current=rows(pg)
    assert delayed[0] and result.status=='needs_review' and result.reason_code=='late_result'
    assert current.stripe_id is None and task.get_attempts==current.reconcile_attempts==2
    assert len(provider.calls)==2 and before==domain(pg)
    assert json.loads(audits[-1].projection_json)['reason_code']=='late_result'


def test_request_id_collision_across_users_cannot_attach_a_second_checkout(pg):
    row=seed(pg);request=context();provider=Provider(obj(row))
    assert run(pg,provider,audit=request).status=='verified'
    with Session(pg) as session:
        session.add(User(id='b3b-user-other',email='b3b-other@synthetic.invalid',password_hash='disabled'))
        session.flush()
        session.add(Membership(user_id='b3b-user-other',active_checkout_id='b3b-checkout-other'))
        second=BillingCheckout(id='b3b-checkout-other',user_id='b3b-user-other',price_id='price_original',
            mode='payment',duration_days=30,origin='https://synthetic.invalid',stripe_id='cs_other',
            provider_account_scope=CFG.scope,livemode=False)
        second.create_payload=_freeze(second);second.create_payload_sha256=digest(second.create_payload)
        second.create_payload_version=1;session.add(second);session.commit()
    other=Provider({})
    with pytest.raises(subject.ReconciliationRejected,match='request_id_conflict'):
        subject.reconcile_checkout('b3b-checkout-other',request,engine=pg,cfg=CFG,
            policy=ReconciliationPolicy(),provider=other)
    assert other.calls==[]
    with Session(pg) as session:
        tasks=session.exec(select(Task)).all()
        assert len(tasks)==1 and tasks[0].checkout_id==row.id
        assert session.get(BillingCheckout,'b3b-checkout-other').reconcile_attempts==0


def test_invalid_audit_creates_no_task_and_terminal_reentry_appends_nothing(pg):
    row=seed(pg);provider=Provider(obj(row))
    with pytest.raises(subject.ReconciliationRejected):
        run(pg,provider,audit=AuditContext('invalid','op:synthetic','unknown_create','ev:synthetic'))
    with Session(pg) as session:assert session.exec(select(Task)).all()==[]
    assert provider.calls==[]
    first=run(pg,provider);task,audits,current=rows(pg)
    repeat=Provider(obj(row));again=run(pg,repeat)
    after,after_audits,after_checkout=rows(pg)
    assert again==first and repeat.calls==[]
    assert task.model_dump()==after.model_dump() and current.model_dump()==after_checkout.model_dump()
    assert [value.model_dump() for value in audits]==[value.model_dump() for value in after_audits]


def test_manual_task_prevents_original_create(pg):
    from app.services.billing_pg import checkout
    row=seed(pg,known=False,old=True);provider=Provider(obj(row))
    assert run(pg,provider).status=='needs_review'
    with Session(pg) as session:
        current=session.get(BillingCheckout,row.id);current.reconciliation='unknown';session.add(current);session.commit()
    forbidden=SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(
        create=lambda *a,**k:pytest.fail('manual task must block original create')))))
    settings=SimpleNamespace()
    from fastapi import HTTPException
    with pytest.raises(HTTPException):checkout(pg,row.user_id,CFG,settings,lambda:forbidden)
