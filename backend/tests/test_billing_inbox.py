import copy
import json
import pytest
from app.config import Settings
from app.services.billing_pg import BillingConfiguration
from app.services.billing_projection import InvalidPayload, canonical, project_object


def body():
    return {'id':'b3-event','type':'checkout.session.completed','livemode':False,
        'data':{'object':{'id':'b3-session','metadata':{'checkout_id':'b3-checkout'}, 'amount_total':990}}}


def test_projection_retains_nulls_and_ignores_secrets():
    value = body()
    first = canonical(value, 'operator', False)
    value['data']['object'].update(customer_email='private@synthetic.invalid', card={'number':'sensitive'},
        client_secret='sensitive')
    value['data']['object']['metadata']['unrelated_secret'] = 'sensitive'
    assert first == canonical(value,'operator',False)
    assert 'sensitive' not in first and 'private' not in first
    assert json.loads(first)['data']['object']['currency'] is None


@pytest.mark.parametrize('field,value', [('amount_total',True),('amount_total',-1),('amount_total',1.2),
    ('currency','CNY'),('currency','xx'),('metadata',[]),('line_items',{'has_more':True})])
def test_projection_rejects_unknown_structure(field,value):
    payload = body()
    payload['data']['object'][field] = value
    with pytest.raises(InvalidPayload):
        canonical(payload,'operator',False)


@pytest.mark.parametrize('changes', [dict(parent=[]),dict(parent={'subscription_details':'bad'}),
    dict(payments={'data':[{'payment':[]}]}),dict(payments={'has_more':True}),
    dict(lines={'data':[{'pricing':[]}]}),dict(lines={'data':[{'period':[]} ]})])
def test_invoice_nested_objects_are_strict(changes):
    with pytest.raises(InvalidPayload):
        project_object('invoice.paid',dict(id='b3-invoice',**changes))


@pytest.mark.parametrize('scope', ['', 'legacy_unknown','bad scope','x'*129,'é'])
def test_explicit_scope_is_required(scope):
    with pytest.raises(Exception):
        BillingConfiguration(scope,False)


@pytest.mark.parametrize('mode', [None,0,1,'false'])
def test_livemode_is_exact_bool(mode):
    with pytest.raises(Exception):
        BillingConfiguration('operator',mode)


@pytest.mark.parametrize('value', ['0','1','TRUE','False','','yes'])
def test_mode_environment_requires_literal_bool(monkeypatch,value):
    monkeypatch.setenv('STRIPE_LIVEMODE',value)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_config_defaults_do_not_enable_durable(monkeypatch):
    monkeypatch.delenv('STRIPE_LIVEMODE',raising=False)
    monkeypatch.delenv('BILLING_INBOX_MODE',raising=False)
    current = Settings.from_env()
    assert current.stripe_livemode is None and current.billing_inbox_mode == 'legacy_sync'
    for dialect in ('sqlite','postgresql'):
        with pytest.raises(Exception):
            BillingConfiguration.configured(current,dialect)


def test_canonical_is_stable_when_projected_again():
    first = canonical(body(),'operator',False)
    assert canonical(json.loads(first),'operator',False) == first


def test_worker_checks_schema_before_claim(monkeypatch):
    from app import billing_worker as worker
    from types import SimpleNamespace
    calls=[]
    instance=SimpleNamespace(dialect=SimpleNamespace(name='postgresql'),dispose=lambda:calls.append('dispose'))
    monkeypatch.setattr(worker,'build_engine',lambda *a,**k:instance)
    monkeypatch.setattr(worker.BillingConfiguration,'configured',lambda *a:object())
    def invalid_schema(_):
        calls.append('schema');raise RuntimeError('synthetic revision mismatch')
    monkeypatch.setattr(worker,'assert_schema_current',invalid_schema)
    monkeypatch.setattr(worker,'run_once',lambda *a:pytest.fail('must not claim old schema'))
    monkeypatch.setattr('sys.argv',['billing_worker','--once'])
    with pytest.raises(RuntimeError):worker.main()
    assert calls==['schema','dispose']


def test_portal_provider_exception_has_no_context(monkeypatch):
    from app.services import billing
    from app.models import Membership
    from types import SimpleNamespace
    class Local:
        def get(self,*args):return Membership(user_id='user',customer_id='customer',subscription_id='sub')
        def rollback(self):pass
    def fail(*args,**kwargs):raise RuntimeError('sensitive-provider-body')
    monkeypatch.setattr(billing,'portal_configured',lambda:True)
    monkeypatch.setattr(billing,'client',lambda:SimpleNamespace(v1=SimpleNamespace(billing_portal=SimpleNamespace(
        sessions=SimpleNamespace(create=fail)))))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as caught:billing.portal(Local(),SimpleNamespace(id='user'))
    assert caught.value.__context__ is caught.value.__cause__ is None


def test_checkout_url_accepts_bounded_hosted_url_longer_than_identifier():
    from app.services.billing_pg import checkout_url
    value='https://checkout.stripe.com/c/pay/'+('a'*1000)
    assert checkout_url(value)==value


@pytest.mark.parametrize('value',['http://checkout.stripe.com/pay','https://user:secret@host/pay',
    'https://checkout.stripe.com/\nsecret','https://checkout.stripe.com/'+('a'*8192),True])
def test_checkout_url_rejects_unsafe_or_unbounded_values(value):
    from app.services.billing_pg import checkout_url
    with pytest.raises(ValueError):checkout_url(value)
