from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from threading import Event
import time
import copy
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from b3_pg_helpers import CFG, Provider, event, pg, receipt, seed
from app.config import Settings
from app.models import BillingInbox, BillingFact, BillingEvent, BillingPayment, BillingCheckout, Membership, User
from app.services import billing_inbox as inbox, billing_pg, db_transactions as tx
from app.services.billing_projection import encode


def row(instance, model, key):
    with Session(instance) as session:
        return session.get(model,key)


def run(instance, provider):
    return inbox.run_once(instance,CFG,provider,'b3-worker')


def inboxrow(instance):
    with Session(instance) as session:
        return session.exec(select(BillingInbox)).one()


def test_duplicate_json_metadata_ignored_and_original_retained(pg):
    value=event()
    receipt(pg,value)
    first=inboxrow(pg)
    value['data']['object']['metadata']['secret']='never-save'
    assert inbox.receive(pg,value,json.dumps(value,indent=4).encode(),CFG)=={'received':True}
    current=inboxrow(pg)
    assert current.payload_sha256==first.payload_sha256 and current.canonical_sha256==first.canonical_sha256
    assert 'never-save' not in current.business_payload


def test_real_canonical_conflict_is_409_and_fences_processing(pg):
    value=event()
    receipt(pg,value)
    token=inbox.claim_one(pg,CFG,'b3-worker')
    value['data']['object']['amount_total']=991
    with pytest.raises(HTTPException) as caught:
        receipt(pg,value)
    assert caught.value.status_code==409
    current=inboxrow(pg)
    assert current.status=='needs_review' and current.lease_epoch>token.epoch
    assert json.loads(current.business_payload)['data']['object']['amount_total']==990


def test_two_concurrent_delivery_receipts_are_one(pg):
    value=event()
    barrier=Barrier(2)
    def work():
        barrier.wait(5)
        return receipt(pg,value)
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _:work(),range(2)))==[{'received':True}]*2
    assert inboxrow(pg).attempt_count==0


def test_paid_once_and_different_events_same_checkout_do_not_extend(pg):
    attempt=seed(pg)
    value=event(attempt)
    provider=Provider(value)
    receipt(pg,value)
    assert run(pg,provider)=='applied'
    first=row(pg,Membership,'b3-user')
    value['id']='b3-event-second'
    receipt(pg,value)
    assert run(pg,provider)=='applied'
    assert row(pg,Membership,'b3-user').expires_at==first.expires_at
    assert row(pg,BillingCheckout,'b3-checkout').fulfilled
    assert row(pg,BillingPayment,'b3-payment').source_id=='b3-payment'


def test_parallel_paid_claims_one_grant(pg):
    attempt=seed(pg)
    value=event(attempt)
    receipt(pg,value)
    value2=copy.deepcopy(value); value2['id']='b3-event-second'; receipt(pg,value2)
    tokens=[inbox.claim_one(pg,CFG,'b3-'+str(i)) for i in range(2)]
    providers=[Provider(value),Provider(value2)]
    barrier=Barrier(2)
    for provider in providers:
        provider.callback=lambda:barrier.wait(5)
    with ThreadPoolExecutor(2) as pool:
        statuses=list(pool.map(lambda pair:inbox.process_claim(pg,pair[0],CFG,pair[1]),zip(tokens,providers)))
    assert sorted(statuses)==['applied','retry_wait']
    assert row(pg,Membership,'b3-user').expires_at < 2000000000


def test_reversal_before_binding_tombstone_never_grants(pg):
    seed(pg)
    rev=event(eid='b3-refund',kind='charge.refunded',id='b3-charge',amount=990,amount_refunded=990,refunded=True)
    receipt(pg,rev)
    assert run(pg,Provider(rev))=='waiting_binding'
    assert row(pg,BillingPayment,'b3-payment').revoked
    assert row(pg,BillingEvent,'b3-refund') is None
    paid=event(); receipt(pg,paid)
    assert run(pg,Provider(paid))=='applied'
    assert row(pg,Membership,'b3-user').status=='expired'
    with Session(pg) as session:
        session.execute(update(BillingInbox).where(BillingInbox.event_id=='b3-refund').values(next_run_at=func.clock_timestamp()))
        session.commit()
    assert run(pg,Provider(rev))=='applied'
    assert row(pg,BillingEvent,'b3-refund') is not None


@pytest.mark.parametrize('kind,changes', [('charge.refunded',dict(amount=990,amount_refunded=50,refunded=False)),
    ('charge.dispute.closed',dict(status='won'))])
def test_partial_or_dispute_won_only_fact_preserves_entitlement(pg,kind,changes):
    seed(pg); paid=event();receipt(pg,paid);assert run(pg,Provider(paid))=='applied'
    before=row(pg,Membership,'b3-user').expires_at
    rev=event(eid='b3-reversal',kind=kind,id='b3-charge',**changes)
    receipt(pg,rev);assert run(pg,Provider(rev))=='applied'
    assert row(pg,Membership,'b3-user').expires_at==before
    assert not row(pg,BillingPayment,'b3-payment').revoked


def test_old_payment_cannot_revoke_new_source(pg):
    seed(pg);paid=event();receipt(pg,paid);run(pg,Provider(paid))
    with Session(pg) as session:
        account=session.get(Membership,'b3-user');account.entitlement_source='b3-new-payment';session.add(account);session.commit()
    rev=event(eid='b3-refund',kind='charge.refunded',id='b3-charge',amount=990,amount_refunded=990,refunded=True)
    receipt(pg,rev);assert run(pg,Provider(rev))=='applied'
    assert row(pg,Membership,'b3-user').status=='active'
    assert row(pg,BillingPayment,'b3-payment').revoked


def test_revision_changes_during_get_and_no_connection_held(pg):
    seed(pg);value=event();provider=Provider(value);receipt(pg,value)
    def concurrent():
        # A second DB connection can update/commit while the fake GET is active.
        with Session(pg) as session:
            account=session.get(Membership,'b3-user');account.revision+=1
            session.add(account);session.commit()
    provider.callback=concurrent
    assert run(pg,provider)=='retry_wait'
    assert row(pg,BillingPayment,'b3-payment') is None
    assert not row(pg,BillingCheckout,'b3-checkout').fulfilled


def test_expired_lease_final_cas_rolls_back_entire_domain(pg,monkeypatch):
    seed(pg);value=event();provider=Provider(value);receipt(pg,value)
    token=inbox.claim_one(pg,CFG,'b3-worker')
    original=inbox._cas
    def lost(session,*args,**kwargs):
        session.execute(update(BillingInbox).where(BillingInbox.id==token.id).values(lease_deadline=func.clock_timestamp()-timedelta(seconds=1)))
        return original(session,*args,**kwargs)
    monkeypatch.setattr(inbox,'_cas',lost)
    assert inbox.process_claim(pg,token,CFG,provider)=='lease_lost'
    assert row(pg,BillingPayment,'b3-payment') is None
    assert row(pg,BillingEvent,'b3-event') is None
    assert row(pg,Membership,'b3-user').status=='free'
    assert not row(pg,BillingCheckout,'b3-checkout').fulfilled
    with Session(pg) as session:
        assert session.exec(select(BillingFact)).all()==[]


def test_expired_epoch_cannot_finish_after_reclaim(pg):
    receipt(pg,event(kind='unsupported.event'))
    old=inbox.claim_one(pg,CFG,'b3-old')
    with Session(pg) as session:
        session.execute(update(BillingInbox).where(BillingInbox.id==old.id).values(lease_deadline=func.clock_timestamp()-timedelta(seconds=1)))
        session.commit()
    current=inbox.claim_one(pg,CFG,'b3-new')
    assert current.epoch>old.epoch and current.attempt==2
    assert inbox.process_claim(pg,old,CFG,Provider(event()))=='lease_lost'
    assert inbox.process_claim(pg,current,CFG,Provider(event()))=='ignored'


@pytest.mark.parametrize('by_attempts',[False,True])
def test_budget_exhaustion_terminal_without_network_or_reset(pg,by_attempts):
    receipt(pg,event())
    with Session(pg) as session:
        record=session.exec(select(BillingInbox)).one()
        if by_attempts:record.attempt_count=5
        else:record.received_at-=timedelta(days=2);record.budget_deadline=func.clock_timestamp()-timedelta(seconds=1)
        session.add(record);session.commit()
    provider=Provider(event())
    assert run(pg,provider) is None
    assert inboxrow(pg).status=='needs_review' and provider.calls==[]
    receipt(pg,event());assert run(pg,provider) is None


def test_missing_invoice_binding_waits_not_ignored(pg):
    value=event(kind='invoice.paid',id='b3-invoice',subscription='b3-sub')
    receipt(pg,value);assert run(pg,Provider(value))=='waiting_binding'
    assert row(pg,BillingEvent,'b3-event') is None


def test_old_subscription_is_ignored_without_network(pg):
    seed(pg)
    with Session(pg) as session:
        account=session.get(Membership,'b3-user');account.customer_id='b3-customer';account.subscription_id='b3-current'
        account.status='active';account.expires_at=9999999999;session.add(account);session.commit()
    value=event(kind='invoice.paid',id='b3-invoice',subscription='b3-old')
    receipt(pg,value);provider=Provider(value)
    assert run(pg,provider)=='ignored' and provider.calls==[]
    assert row(pg,Membership,'b3-user').expires_at==9999999999
    assert inboxrow(pg).outcome_reason=='superseded_subscription'


def test_unknown_amount_stays_null_fact(pg):
    seed(pg);value=event(amount_total=None,currency=None);provider=Provider(value);receipt(pg,value)
    assert run(pg,provider)=='applied'
    with Session(pg) as session:
        fact=session.exec(select(BillingFact)).one()
        assert fact.amount_total is None and fact.currency is None and fact.reconciliation=='unknown'


@pytest.mark.parametrize('field,value',[('livemode',True),('line_items',{'data':[{'price':'other','quantity':1}]}),
    ('amount_total',999),('client_reference_id','other')])
def test_provider_binding_conflicts_need_review(pg,field,value):
    seed(pg);paid=event();receipt(pg,paid);provider=Provider(paid);provider.obj[field]=value
    assert run(pg,provider)=='needs_review'
    assert row(pg,Membership,'b3-user').status=='free'
    assert row(pg,BillingEvent,'b3-event') is None


def settings():
    return Settings(stripe_price_id='b3-price',stripe_billing_mode='payment',stripe_public_origin='https://synthetic.invalid')


def test_checkout_freezes_payload_and_stable_provider_key(pg):
    with Session(pg) as session:
        session.add(User(id='b3-user',email='b3-user@synthetic.invalid',password_hash='no-login'));session.commit()
    provider=Provider(event());provider.obj['payment_status']='unpaid'
    assert billing_pg.checkout(pg,'b3-user',CFG,settings(),provider)['url'].startswith('https://checkout.stripe.com/')
    with Session(pg) as session:
        attempt=session.exec(select(BillingCheckout)).one()
        assert provider.calls[0][2]['idempotency_key']=='membership-'+attempt.id
        frozen=json.loads(attempt.create_payload)
        assert frozen['duration_days']==30 and frozen['scope']==CFG.scope and frozen['livemode'] is False
        assert attempt.create_payload_sha256==billing_pg.digest(attempt.create_payload)
        # Rename only this synthetic ID for scoped cleanup after arbitrary UUID.
        session.delete(attempt);session.commit()


def test_legacy_unknown_checkout_never_creates(pg):
    attempt=seed(pg)
    with Session(pg) as session:
        attempt=session.get(BillingCheckout,attempt.id);attempt.stripe_id=None;attempt.provider_account_scope=None;attempt.livemode=None
        session.add(attempt);session.commit()
    provider=Provider(event())
    with pytest.raises(HTTPException):
        billing_pg.checkout(pg,'b3-user',CFG,settings(),provider)
    assert provider.calls==[] and row(pg,BillingCheckout,'b3-checkout').reconciliation=='needs_review'


def test_business_commit_ack_loss_resolves_once(pg,monkeypatch):
    seed(pg);value=event();receipt(pg,value)
    original=Session.commit
    lost=[False]
    def commit(session):
        has_event=any(isinstance(item,BillingEvent) for item in session.new)
        # Flush normally happens before runner commit, so identify transaction's
        # inserted event through the local DB view without relying on identity.
        has_event=bool(session.get(BillingEvent,'b3-event')) if isinstance(session,tx.LocalSession) else has_event
        original(session)
        if has_event and not lost[0]:
            lost[0]=True
            from sqlalchemy.exc import OperationalError
            raise OperationalError('synthetic ACK lost',{},Exception(),connection_invalidated=True)
    monkeypatch.setattr(Session,'commit',commit)
    assert run(pg,Provider(value))=='applied' and lost[0]
    assert inboxrow(pg).status=='applied'
    assert row(pg,BillingCheckout,'b3-checkout').fulfilled


def test_paid_and_refund_concurrent_cannot_restore_revoked(pg):
    seed(pg)
    paid=event(); rev=event(eid='b3-refund',kind='charge.refunded',id='b3-charge',amount=990,amount_refunded=990,refunded=True)
    receipt(pg,paid); receipt(pg,rev)
    tokens=[inbox.claim_one(pg,CFG,'b3-'+str(i)) for i in range(2)]
    byid={token.event_id:token for token in tokens}
    provider=Provider(paid);entered=Event();resume=Event()
    def pause():entered.set();assert resume.wait(5)
    provider.callback=pause
    with ThreadPoolExecutor(2) as pool:
        future=pool.submit(inbox.process_claim,pg,byid['b3-event'],CFG,provider)
        assert entered.wait(5)
        assert inbox.process_claim(pg,byid['b3-refund'],CFG,Provider(rev))=='waiting_binding'
        resume.set();assert future.result(5)=='applied'
    assert row(pg,BillingPayment,'b3-payment').revoked
    assert row(pg,Membership,'b3-user').expires_at==0


def test_real_rowlock_wait_expires_token_and_rolls_back_domain(pg):
    seed(pg);paid=event();receipt(pg,paid);token=inbox.claim_one(pg,CFG,'b3-worker')
    # Keep the token initially valid; holder shortens its actual lease in the
    # locked transaction, commits after the deadline, and releases the lock.
    held=Event();release=Event()
    def holder():
        with Session(pg) as session:
            record=session.exec(select(BillingInbox).where(BillingInbox.id==token.id).with_for_update()).one()
            record.lease_deadline=session.exec(select(func.clock_timestamp())).one()+timedelta(milliseconds=150)
            session.add(record);session.flush();held.set()
            assert release.wait(5);time.sleep(.2);session.commit()
    with ThreadPoolExecutor(2) as pool:
        locked_future=pool.submit(holder);assert held.wait(5)
        applying=pool.submit(inbox.process_claim,pg,token,CFG,Provider(paid))
        time.sleep(.05);release.set()
        locked_future.result(5);assert applying.result(5)=='lease_lost'
    assert row(pg,BillingPayment,'b3-payment') is None
    assert row(pg,BillingEvent,'b3-event') is None
    assert row(pg,Membership,'b3-user').status=='free'


def test_processing_total_budget_expires_before_apply(pg):
    seed(pg);paid=event();receipt(pg,paid);token=inbox.claim_one(pg,CFG,'b3-worker')
    with Session(pg) as session:
        record=session.get(BillingInbox,token.id);record.received_at-=timedelta(days=2)
        record.budget_deadline=session.exec(select(func.clock_timestamp())).one()-timedelta(seconds=1)
        session.add(record);session.commit()
    provider=Provider(paid)
    assert inbox.process_claim(pg,token,CFG,provider)=='needs_review'
    assert provider.calls==[] and row(pg,Membership,'b3-user').status=='free'


def test_initial_subscription_uses_two_gets_and_paid_invoice_bound(pg):
    attempt=seed(pg,mode='subscription')
    paid=event(attempt,subscription='b3-sub',payment_intent=None)
    provider=Provider(paid)
    provider.sub={'id':'b3-sub','customer':'b3-customer','livemode':False,'status':'active',
        'current_period_end':2000000000,'items':{'data':[{'price':'b3-price','current_period_end':2000000000}]},
        'latest_invoice':{'id':'b3-invoice','customer':'b3-customer','subscription':'b3-sub','status':'paid',
            'payment_intent':'b3-payment','lines':{'data':[{'price':'b3-price','period':{'end':1999999999}}]}}}
    receipt(pg,paid);assert run(pg,provider)=='applied'
    assert len(provider.calls)==2
    account=row(pg,Membership,'b3-user')
    assert account.expires_at==1999999999 and account.entitlement_source=='b3-invoice'


def test_one_time_source_old_subscription_notification_ignored(pg):
    seed(pg);paid=event();receipt(pg,paid);run(pg,Provider(paid))
    old=event(eid='b3-old',kind='customer.subscription.deleted',id='b3-old-sub',status='canceled')
    receipt(pg,old);provider=Provider(old)
    assert run(pg,provider)=='ignored' and provider.calls==[]
    assert row(pg,Membership,'b3-user').status=='active'


def test_unknown_checkout_create_preserves_frozen_key_and_23h_guard(pg):
    seed(pg)
    with Session(pg) as session:
        attempt=session.get(BillingCheckout,'b3-checkout');attempt.stripe_id=None
        attempt.create_payload=billing_pg._freeze(attempt);attempt.create_payload_sha256=billing_pg.digest(attempt.create_payload)
        attempt.create_payload_version=1;session.add(attempt);session.commit()
    provider=Provider(event());calls=[]
    def unknown(params,options):
        calls.append((params,options));raise TimeoutError('synthetic secret must never escape')
    provider.v1.checkout.sessions.create=unknown
    for _ in range(2):
        with pytest.raises(HTTPException):billing_pg.checkout(pg,'b3-user',CFG,settings(),provider)
    assert calls[0]==calls[1] and calls[0][1]['idempotency_key']=='membership-b3-checkout'
    with Session(pg) as session:
        attempt=session.get(BillingCheckout,'b3-checkout');attempt.created_at-=24*3600;session.add(attempt);session.commit()
    with pytest.raises(HTTPException):billing_pg.checkout(pg,'b3-user',CFG,settings(),provider)
    assert len(calls)==2 and row(pg,BillingCheckout,'b3-checkout').reconciliation=='needs_review'


def test_durable_route_acks_only_receipt_and_does_no_provider_calls(pg,monkeypatch):
    import hashlib,hmac
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes.billing import router
    from app.db import get_session
    from app.config import settings as current
    app=FastAPI();app.include_router(router)
    def sessions():
        with Session(pg) as session:yield session
    app.dependency_overrides[get_session]=sessions
    for name,value in dict(stripe_webhook_secret='b3-signing',billing_inbox_mode='durable',
        stripe_provider_account_scope=CFG.scope,stripe_livemode=False,billing_inbox_lease_seconds=10).items():
        monkeypatch.setattr(current,name,value)
    seed(pg);body=encode(event()).encode();stamp=int(time.time())
    signature=hmac.new(b'b3-signing',str(stamp).encode()+b'.'+body,hashlib.sha256).hexdigest()
    result=TestClient(app).post('/api/billing/webhook',content=body,headers={'stripe-signature':f't={stamp},v1={signature}'})
    assert result.status_code==200 and result.json()=={'received':True}
    assert inboxrow(pg).status=='received' and row(pg,Membership,'b3-user').status=='free'


def test_pg_legacy_apply_event_is_closed(pg):
    from app.services import billing
    with Session(pg) as session:
        with pytest.raises(HTTPException):billing.apply_event(session,event())


def test_bad_payload_safe_exception_has_no_raw_context(pg):
    value=event();value['data']['object']['amount_total']='sensitive-invalid-value'
    with pytest.raises(HTTPException) as caught:receipt(pg,value)
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert 'sensitive' not in str(caught.value.detail)


def test_ended_subscription_new_purchase_paid_then_old_event_is_safe(pg):
    attempt=seed(pg,mode='subscription',fulfilled=True)
    with Session(pg) as session:
        account=session.get(Membership,'b3-user');account.customer_id='b3-customer';account.subscription_id='b3-old-sub'
        account.entitlement_source='b3-old-invoice';account.status='expired';session.add(account)
        old=session.get(BillingCheckout,attempt.id);old.state='paid';session.add(old);session.commit()
    provider=Provider(event());provider.sub={'id':'b3-old-sub','customer':'b3-customer','status':'canceled','livemode':False}
    config=settings();config.stripe_billing_mode='subscription'
    assert billing_pg.checkout(pg,'b3-user',CFG,config,provider)['url']
    with Session(pg) as session:
        account=session.get(Membership,'b3-user');assert account.subscription_id is None
        new=session.get(BillingCheckout,account.active_checkout_id)
        paid=event(new,subscription='b3-new-sub',payment_intent=None)
    provider=Provider(paid)
    provider.sub={'id':'b3-new-sub','customer':'b3-customer','livemode':False,'status':'active',
        'items':{'data':[{'price':'b3-price','current_period_end':2000000000}]},
        'latest_invoice':{'id':'b3-new-invoice','customer':'b3-customer','subscription':'b3-new-sub','status':'paid',
            'payment_intent':'b3-new-payment','lines':{'data':[{'price':'b3-price','period':{'end':1999999999}}]}}}
    receipt(pg,paid);assert run(pg,provider)=='applied'
    oldevent=event(eid='b3-old-event',kind='customer.subscription.deleted',id='b3-old-sub',status='canceled')
    receipt(pg,oldevent);assert run(pg,Provider(oldevent))=='ignored'
    current=row(pg,Membership,'b3-user')
    assert current.subscription_id=='b3-new-sub' and current.entitlement_source=='b3-new-invoice'
    assert current.expires_at==1999999999 and current.status=='active'


@pytest.mark.parametrize('obj',[[],{'id':'b3-session','metadata':[]},{'id':'b3-session','expires_at':'sensitive-invalid'}])
def test_checkout_invalid_provider_object_is_safe_review(pg,obj):
    seed(pg)
    provider=Provider(event());provider.v1.checkout.sessions.retrieve=lambda _:obj
    with pytest.raises(HTTPException) as caught:
        billing_pg.checkout(pg,'b3-user',CFG,settings(),provider)
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert row(pg,BillingCheckout,'b3-checkout').reconciliation=='needs_review'


def test_checkout_preflight_provider_exception_is_detached(pg):
    seed(pg)
    with Session(pg) as session:
        account=session.get(Membership,'b3-user');account.subscription_id='b3-old';session.add(account);session.commit()
    provider=Provider(event())
    def failure(*args,**kwargs):raise RuntimeError('sensitive-provider-body')
    provider.v1.subscriptions.retrieve=failure
    with pytest.raises(HTTPException) as caught:billing_pg.checkout(pg,'b3-user',CFG,settings(),provider)
    assert caught.value.__context__ is caught.value.__cause__ is None


def test_supplier_failure_then_defer_db_error_has_no_supplier_context(pg,monkeypatch):
    seed(pg);paid=event();receipt(pg,paid);provider=Provider(paid)
    def fail(*args,**kwargs):raise TimeoutError('sensitive-provider-body')
    provider.v1.checkout.sessions.retrieve=fail
    def defer_fail(*args,**kwargs):raise HTTPException(503,detail={'error_type':'synthetic_db_failure'})
    monkeypatch.setattr(inbox,'_defer',defer_fail)
    with pytest.raises(HTTPException) as caught:run(pg,provider)
    assert caught.value.__context__ is caught.value.__cause__ is None


@pytest.mark.parametrize('boundary',['lease','budget'])
def test_final_update_database_clock_rejects_pause_after_clock_sample(pg,boundary):
    """Real pg_sleep AFTER _cas read its timestamp, BEFORE its final UPDATE."""
    from sqlalchemy import event as sa_event
    seed(pg);paid=event();receipt(pg,paid);token=inbox.claim_one(pg,CFG,'b3-worker')
    with Session(pg) as session:
        record=session.get(BillingInbox,token.id)
        deadline=session.exec(select(func.clock_timestamp())).one()+timedelta(milliseconds=500)
        if boundary=='lease':
            record.lease_deadline=deadline
        else:
            record.budget_deadline=deadline
        session.add(record);session.commit()
    pauses=[]
    def pause_before_update(connection,cursor,statement,parameters,context,many):
        if statement.startswith('UPDATE billinginbox') and not pauses:
            pauses.append(1)
            # This runs on the real transaction's connection while all domain
            # writes are uncommitted. It cannot be replaced by a mocked clock.
            connection.exec_driver_sql('SELECT pg_sleep(0.7)')
    sa_event.listen(pg,'before_cursor_execute',pause_before_update)
    try:
        result=inbox.process_claim(pg,token,CFG,Provider(paid))
    finally:
        sa_event.remove(pg,'before_cursor_execute',pause_before_update)
    assert pauses==[1]
    assert result==('lease_lost' if boundary=='lease' else 'needs_review')
    account=row(pg,Membership,'b3-user')
    attempt=row(pg,BillingCheckout,'b3-checkout')
    assert account.status=='free' and account.expires_at==0 and account.revision==0
    assert not attempt.fulfilled and attempt.state=='pending' and attempt.revision==0
    assert row(pg,BillingPayment,'b3-payment') is None
    assert row(pg,BillingEvent,'b3-event') is None
    with Session(pg) as session:
        assert session.exec(select(BillingFact)).all()==[]
    if boundary=='budget':
        assert inboxrow(pg).status=='needs_review' and inboxrow(pg).error_code=='budget_exhausted'
