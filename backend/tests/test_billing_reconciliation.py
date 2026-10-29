"""B3b pure contract tests: synthetic values; no DB, DNS or provider sockets."""
import copy
import ast
from datetime import datetime, timezone
import json
import socket
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import uuid

import pytest

from app.services.billing_projection import digest, encode
from app.services.billing_reconciliation import (
    AuditContext, ReconciliationPolicy, ReconciliationRejected,
    plan_checkout_reads, select_session_candidate, verify_session_binding,
    validate_audit_context, project_session,
)
from app.services.billing_reconciliation_provider import build_read_only_provider

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
CFG = SimpleNamespace(scope='synthetic-account', livemode=False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('B3b pure tests prohibit all sockets and DNS')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket.socket, 'sendto', denied)
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


def original(**changes):
    row = dict(id='checkout-original', user_id='user-original', provider_account_scope=CFG.scope,
        livemode=False, mode='payment', price_id='price_original', duration_days=30,
        origin='https://synthetic.invalid', customer_id=None, stripe_id=None,
        created_at=NOW.timestamp()-1000, revision=1, membership_revision=2,
        membership_customer_id=None, active_checkout_id='checkout-original',
        state='creating', fulfilled=False, create_result_code='provider_unknown', references=[])
    row.update(changes)
    params = dict(mode=row['mode'], line_items=[dict(price=row['price_id'], quantity=1)],
        managed_payments=dict(enabled=False), client_reference_id=row['user_id'],
        metadata=dict(checkout_id=row['id']), success_url=row['origin']+'/?membership=success',
        cancel_url=row['origin']+'/?membership=cancel')
    if row['customer_id']:
        params['customer'] = row['customer_id']
    elif row['mode'] == 'payment':
        params['customer_creation'] = 'always'
    if row['mode'] == 'subscription':
        params['payment_method_types'] = ['card']
    freeze = dict(version=1, scope=row['provider_account_scope'], livemode=row['livemode'],
        user_id=row['user_id'], price_id=row['price_id'], mode=row['mode'],
        duration_days=row['duration_days'], origin=row['origin'], customer_id=row['customer_id'], params=params)
    row.update(create_payload=encode(freeze), create_payload_sha256=digest(encode(freeze)), create_payload_version=1)
    return row


def observed(**changes):
    obj = dict(id='cs_original', livemode=False, mode='payment', metadata=dict(checkout_id='checkout-original'),
        client_reference_id='user-original', customer='cus_new', payment_intent='pi_original', subscription=None,
        created=int(NOW.timestamp())-900, line_items=dict(has_more=False, data=[dict(price=dict(id='price_original'), quantity=1)]),
        success_url='https://synthetic.invalid/?membership=success', cancel_url='https://synthetic.invalid/?membership=cancel',
        status='complete', payment_status='paid', amount_total=990, currency='cny')
    obj.update(changes)
    return obj


def query(row=None):
    return plan_checkout_reads(row or original(), CFG, ReconciliationPolicy(), NOW)


def test_query_uses_only_supported_original_filters():
    q = query()
    assert q['params'] == dict(created=dict(gte=int(NOW.timestamp())-1300, lte=int(NOW.timestamp())+300), limit=100)
    assert q['strategy'] == 'list'
    assert query(original(stripe_id='cs_original'))['session_id'] == 'cs_original'
    row = original(references=[dict(inbox_id='inbox', fact_id='fact', session_id=None,
        payment_intent='pi_original', subscription_id=None, customer_id='cus_original')])
    assert query(row)['params']['payment_intent'] == 'pi_original'
    assert query(row)['params']['customer'] == 'cus_original'
    assert set(q['params']) <= {'created', 'limit', 'customer', 'payment_intent', 'subscription'}


@pytest.mark.parametrize('changes', [dict(has_more=1), {}, dict(has_more=True), dict(has_more=False,data='bad'),
    dict(has_more=False,data=[observed()]*101), dict(has_more=False,data=[observed(),observed()])])
def test_complete_pages_are_required_before_uniqueness(changes):
    with pytest.raises(ReconciliationRejected):
        select_session_candidate((changes,), query())


def test_complete_zero_one_and_conflicting_candidates():
    q = query()
    assert select_session_candidate((dict(data=[],has_more=False),),q) is None
    assert select_session_candidate((dict(data=[observed()],has_more=False),),q) == 'cs_original'
    conflict = observed(id='cs_conflict', client_reference_id='other-user')
    with pytest.raises(ReconciliationRejected):
        select_session_candidate((dict(data=[observed(),conflict],has_more=False),),q)
    assert select_session_candidate((dict(data=[observed()],has_more=True), dict(data=[],has_more=False)),q) == 'cs_original'
    with pytest.raises(ReconciliationRejected):
        select_session_candidate((dict(data=[observed()],has_more=False),dict(data=[],has_more=False)),q)


@pytest.mark.parametrize('created', [None, True, 1.1, int(NOW.timestamp())-1301, int(NOW.timestamp())+301])
def test_candidate_and_retrieve_created_must_be_strict_closed_interval(created):
    q = query()
    with pytest.raises(ReconciliationRejected):
        select_session_candidate((dict(data=[observed(created=created)],has_more=False),),q)
    with pytest.raises(ReconciliationRejected):
        verify_session_binding(original(),observed(created=created),dict(q, candidate_id='cs_original'))


@pytest.mark.parametrize('created',[None,True,int(NOW.timestamp())-1301,int(NOW.timestamp())+301])
def test_known_original_id_retrieve_also_requires_frozen_created_interval(created):
    row=original(stripe_id='cs_original')
    with pytest.raises(ReconciliationRejected):verify_session_binding(row,observed(created=created),query(row))


def test_legacy_evidence_cannot_be_reconstructed_from_settings():
    row = original(stripe_id='cs_original')
    row.update(create_payload=None, create_payload_sha256=None, create_payload_version=None,provider_account_scope=None,livemode=None)
    q = query(row)
    assert q['strategy']=='retrieve' and q['verifiable'] is False
    with pytest.raises(ReconciliationRejected):
        verify_session_binding(row,observed(),q)
    row['stripe_id']=None
    with pytest.raises(ReconciliationRejected):
        query(row)


@pytest.mark.parametrize('field,value', [('livemode',True),('mode','subscription'),('client_reference_id','other'),
    ('metadata',dict(checkout_id='other')),('success_url','https://other.invalid'),('cancel_url',None),
    ('line_items',dict(data=[dict(price='price_original',quantity=True)],has_more=False)),
    ('line_items',dict(data=[dict(price='other',quantity=1)],has_more=False)),
    ('line_items',dict(data=[dict(price='price_original',quantity=1)])),
    ('line_items',dict(data=[dict(price='price_original',quantity=1)],has_more=True))])
def test_all_frozen_binding_fields_are_checked(field,value):
    with pytest.raises(ReconciliationRejected):
        verify_session_binding(original(), observed(**{field:value}),dict(query(),candidate_id='cs_original'))


def test_freeze_hash_and_local_contract_must_all_match():
    for change in [dict(duration_days=True),dict(price_id='changed'),dict(provider_account_scope='changed'),
                   dict(create_payload_sha256='0'*64),dict(create_payload_version=True)]:
        row=original();row.update(change)
        with pytest.raises(ReconciliationRejected):
            verify_session_binding(row,observed(),dict(query(),candidate_id='cs_original'))
    row=original(); data=json.loads(row['create_payload']);data['params']['managed_payments']['enabled']=True
    row['create_payload']=encode(data);row['create_payload_sha256']=digest(row['create_payload'])
    with pytest.raises(ReconciliationRejected):query(row)


def test_success_projects_allowlist_without_claiming_remote_managed_payments():
    value=verify_session_binding(original(),observed(email='never-store',url='https://secret.invalid'),dict(query(),candidate_id='cs_original'))
    assert value['session_id']=='cs_original' and value['local_freeze_verified'] is True
    assert value['remote_managed_payments_verified'] is False
    assert 'never-store' not in encode(value) and 'secret.invalid' not in encode(value)
    assert 'success_url' not in project_session(observed())


@pytest.mark.parametrize('field,value', [('customer','cus_changed'),('payment_intent','pi_changed'),
    ('subscription','sub_new'),('client_reference_id','user_changed'),('mode','subscription'),
    ('metadata',dict(checkout_id='changed'))])
def test_retrieve_cannot_change_list_candidate_binding(field,value):
    q=dict(query(),candidate_id='cs_original',candidate_binding=project_session(observed()))
    with pytest.raises(ReconciliationRejected):
        verify_session_binding(original(),observed(**{field:value}),q)


def test_original_customer_membership_and_subscription_card_contract():
    row=original(customer_id='cus_original')
    with pytest.raises(ReconciliationRejected):
        verify_session_binding(row,observed(),dict(query(row),candidate_id='cs_original'))
    row=original(membership_customer_id='cus_original')
    with pytest.raises(ReconciliationRejected):
        verify_session_binding(row,observed(),dict(query(row),candidate_id='cs_original'))
    row=original(mode='subscription')
    value=observed(mode='subscription',payment_method_types=['card'])
    assert verify_session_binding(row,value,dict(query(row),candidate_id='cs_original'))['session_id']=='cs_original'
    value['payment_method_types']=['card','link']
    with pytest.raises(ReconciliationRejected):
        verify_session_binding(row,value,dict(query(row),candidate_id='cs_original'))


@pytest.mark.parametrize('changes', [dict(create_result_code='create_started'),dict(fulfilled=True),
    dict(state='paid'),dict(active_checkout_id='new-checkout'),dict(created_at=True),
    dict(created_at=float('nan')),dict(created_at=NOW.timestamp()+1)])
def test_unstable_or_untrusted_original_never_scans(changes):
    with pytest.raises(ReconciliationRejected): query(original(**changes))


def test_reference_provenance_and_conflicts():
    row=original(references=[dict(session_id='cs_original')])
    with pytest.raises(ReconciliationRejected): query(row)
    row=original(stripe_id='cs_original',references=[dict(inbox_id='in',fact_id='fact',session_id='cs_other')])
    with pytest.raises(ReconciliationRejected): query(row)


@pytest.mark.parametrize('field,value', [('total_seconds',True),('total_seconds',301),('per_get_timeout_seconds',16),
    ('max_gets',4),('max_list_pages',3),('page_size',101)])
def test_policy_is_strict_and_bounded(field,value):
    with pytest.raises(ReconciliationRejected):ReconciliationPolicy(**{field:value})


def test_audit_context_requires_bounded_identifiers():
    valid=AuditContext(str(uuid.uuid4()),'op:synthetic','unknown_create','ev:synthetic')
    validate_audit_context(valid)
    for field,value in [('request_id','not-uuid'),('actor_ref','op:a@b.invalid'),('evidence_ref','https://secret.invalid'),('reason_code','anything')]:
        bad=dict(valid.__dict__);bad[field]=value
        with pytest.raises(ReconciliationRejected):validate_audit_context(AuditContext(**bad))


@pytest.mark.parametrize('reason', [[],{},None,True])
def test_bad_reason_is_a_safe_rejection(reason):
    with pytest.raises(ReconciliationRejected):
        validate_audit_context(AuditContext(str(uuid.uuid4()),'op:test',reason,'ev:test'))


@pytest.mark.parametrize('payload', ['{secret-frozen-params','{"version":NaN}', '['*1100+'0'+']'*1100])
def test_bad_frozen_json_has_no_original_exception_context(payload):
    row=original();row.update(create_payload=payload,create_payload_sha256=digest(payload))
    with pytest.raises(ReconciliationRejected) as error: query(row)
    assert error.value.__cause__ is None and error.value.__context__ is None


def test_huge_created_int_is_safely_rejected():
    with pytest.raises(ReconciliationRejected):query(original(created_at=10**1000))


@pytest.mark.parametrize('currency', ['usd_fake','us','usd_','USD','_',123])
def test_currency_is_strict_iso_shape(currency):
    with pytest.raises(ReconciliationRejected):project_session(observed(currency=currency))


@pytest.mark.parametrize('count,quantity',[(1,10**5000),(100,10**4000),(1,9223372036854775808)],
    ids=['single-5000digits','hundred-4000digits','above-bigint'])
def test_quantity_is_bigint_bounded_before_any_projection_encoding(count,quantity):
    lines=dict(has_more=False,data=[dict(price='price_original',quantity=quantity) for _ in range(count)])
    with pytest.raises(ReconciliationRejected) as error:project_session(observed(line_items=lines))
    assert error.value.reason_code=='provider_structure'
    assert error.value.__context__ is None and error.value.__cause__ is None


@pytest.mark.parametrize('value',[dict(data='private-body'*7000),dict(quantity=10**5000)])
def test_provider_projection_encoding_is_bounded_before_db_action(value):
    import app.services.billing_reconciliation as subject
    projection,reason=subject._prepare_provider_projection(dict(version=1,operation='retrieve',session=value))
    assert reason in {'provider_projection_invalid','provider_projection_too_large'}
    assert projection==dict(version=1,operation='retrieve',result_code=reason)
    assert len(encode(projection))<150


def test_fresh_child_installs_guard_before_any_application_import():
    path=Path(__file__).with_name('test_pg_billing_reconciliation.py')
    module=ast.parse(path.read_text('utf8'))
    node=next(node for node in module.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='_CHILD_SOCKET_BOOTSTRAP' for target in node.targets))
    bootstrap=ast.literal_eval(node.value)
    probe='''
import sys,json,socket
assert not any(name=='app' or name.startswith('app.') or name=='b3b_pg_helpers' for name in sys.modules)
assert socket._b3b_preimport_guard_installed is True
denied=0
for probe in (lambda: socket.getaddrinfo('synthetic.invalid',443),
              lambda: socket.socket().connect(('127.0.0.1',8000)),
              lambda: socket.socket().connect_ex(('127.0.0.1',8000))):
    try: probe()
    except AssertionError: denied+=1
assert denied==3
import app.services.billing_reconciliation
print(json.dumps({'preimport_guard':True,'blocked_probes':denied}))
'''
    keys={'SYSTEMROOT','WINDIR','TEMP','TMP','PATH','COMSPEC','PATHEXT','SYSTEMDRIVE'}
    env={key:value for key,value in os.environ.items() if key.upper() in keys}
    env.update(DB_URL='sqlite://',BILIBILI_COOKIE_FILE='',PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        LC_ALL='C',LANG='C',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    child=subprocess.run([sys.executable,'-B','-c',bootstrap+probe],env=env,capture_output=True,text=True,
        encoding='utf8',timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert child.returncode==0,child.stderr
    assert json.loads(child.stdout)==dict(preimport_guard=True,blocked_probes=3)


def test_pg_coordinator_requires_explicit_postgres_engine_before_database_access():
    import app.services.billing_reconciliation as subject
    engine=SimpleNamespace(dialect=SimpleNamespace(name='sqlite'))
    with pytest.raises(ReconciliationRejected):
        subject.reconcile_checkout('checkout-original',AuditContext(str(uuid.uuid4()),'op:test','unknown_create','ev:test'),
            engine=engine,cfg=CFG,policy=ReconciliationPolicy(),provider=lambda:pytest.fail('no provider'))


@pytest.mark.parametrize('mutation', [None,'missing_audit','wrong_hash','wrong_task','running','wrong_association'])
def test_final_resolver_requires_exact_commit_witness(mutation):
    import app.services.billing_reconciliation as subject
    from app.services.db_transactions import ResolutionState
    payload=encode(dict(status='verified'))
    witness=dict(id='audit-final',sha256=digest(payload),status='verified',reason='binding_verified',
        attempts=1,session_id='cs_original',expected_revision=3)
    audit=SimpleNamespace(task_id='task-original',event_kind='task_finished',projection_sha256=digest(payload),projection_json=payload)
    task=SimpleNamespace(id='task-original',checkout_id='checkout-original',status='verified',
        outcome_reason='binding_verified',completed_at=NOW,get_attempts=1,expected_checkout_revision=3)
    row=SimpleNamespace(stripe_id='cs_original',reconciliation='verified')
    if mutation=='wrong_hash':audit.projection_sha256='0'*64
    if mutation=='wrong_task':audit.task_id='different-task'
    if mutation=='running':task.status='running'
    if mutation=='wrong_association':row.stripe_id='different-session'
    values={subject.BillingReconciliationTask:task,subject.BillingCheckout:row,
        subject.BillingReconciliationAudit:None if mutation=='missing_audit' else audit}
    session=SimpleNamespace(get=lambda model,key:values[model],exec=lambda query:SimpleNamespace(one=lambda:NOW))
    result=subject._resolve_final('task-original','checkout-original',witness)(session,'operation')
    assert result.state is (ResolutionState.COMMITTED if mutation is None else ResolutionState.UNKNOWN)


def test_read_adapter_has_no_post_retry_or_auto_paging(monkeypatch):
    import stripe
    calls=[]
    class Sessions:
        def retrieve(self,*args,**kwargs): calls.append(('retrieve',args,kwargs));return observed()
        def list(self,*args,**kwargs): calls.append(('list',args,kwargs));return dict(data=[],has_more=False)
    def client(key,**kwargs):
        assert key=='sk_test_synthetic'; calls.append(('client',kwargs))
        return SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=Sessions())))
    monkeypatch.setattr(stripe,'StripeClient',client)
    monkeypatch.setattr(stripe,'RequestsClient',lambda **kwargs:SimpleNamespace(**kwargs))
    provider=build_read_only_provider(api_key='sk_test_synthetic',timeout_seconds=7)
    provider.retrieve_session('cs_original');provider.list_sessions(query()['params'])
    assert calls[0][1]['max_network_retries']==0
    assert calls[0][1]['http_client'].timeout==7
    assert calls[1]==('retrieve',('cs_original',{'expand':['line_items']}),{})
    assert calls[2][0]=='list' and len(calls)==3
    assert not hasattr(provider,'create') and not hasattr(provider,'v1')
