"""Admin M1 Task 9: billing checkouts/payments — independent states, facts_state rules, no money (nonce-owned PG)."""
import json
import os

import pytest

from admin_pg_helpers import BASE, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def checkout(case, checkout_id, user_id, *, state='paid', fulfilled=False, scope='acct_test', livemode=False,
             reconciliation=None):
    run(case, "INSERT INTO app.billingcheckout (id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,"
              "fulfilled,provider_account_scope,livemode,reconciliation,reconcile_attempts,revision,url,create_payload) "
              "VALUES (:i,:u,'price_test','payment',30,'https://site.invalid',extract(epoch from now()),"
              "extract(epoch from now()) + 3600,:s,:f,:scope,:live,:r,0,2,'https://checkout.invalid/SECRETURL',"
              "'{\"secret\":\"PAYLOADSECRET\"}')",
        i=checkout_id, u=user_id, s=state, f=fulfilled, scope=scope, live=livemode, r=reconciliation)


def payment(case, pi, user_id, revoked=False):
    run(case, 'INSERT INTO app.billingpayment (payment_intent,user_id,source_id,revoked) VALUES (:p,:u,:s,:r)',
        p=pi, u=user_id, s='src_' + pi, r=revoked)


def fact(case, fact_id, *, user_id, pi=None, checkout_id=None, scope='acct_test', livemode=False, reconciliation='verified'):
    run(case, "INSERT INTO app.billingfact (id,user_id,checkout_id,provider_account_scope,livemode,payment_intent,"
              "provider_status,amount_total,amount_refunded,currency,reconciliation,observed_at) "
              "VALUES (:i,:u,:c,:scope,:live,:pi,'succeeded',990,0,'cny',:r,now())",
        i=fact_id, u=user_id, c=checkout_id, scope=scope, live=livemode, pi=pi, r=reconciliation)


def get(client, path, **params):
    response = client.get(BASE + path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_payment_available_only_with_verified_single_group(case):
    user = make_user(case)
    payment(case, 'pi_ok', user)
    fact(case, 'f1', user_id=user, pi='pi_ok')
    fact(case, 'f2', user_id=user, pi='pi_ok', reconciliation='unknown')
    with admin_client(case) as client:
        login(client)
        detail = get(client, '/billing/payments/pi_ok')
    assert detail['facts_state'] == 'available' and [f['id'] for f in detail['verified_facts']] == ['f1']
    assert detail['verified_facts'][0]['reconciliation'] == 'verified' and detail['verified_facts'][0]['money'] is None
    assert (detail['money'], detail['amount_state'], detail['amount_source']) == (None, 'unknown', None)


def test_payment_ambiguous_across_scopes(case):
    user = make_user(case)
    payment(case, 'pi_x', user)
    fact(case, 'f1', user_id=user, pi='pi_x', livemode=False)
    fact(case, 'f2', user_id=user, pi='pi_x', livemode=True)
    with admin_client(case) as client:
        login(client)
        detail = get(client, '/billing/payments/pi_x')
    assert (detail['facts_state'], detail['verified_facts'], detail['money']) == ('ambiguous', [], None)
    assert detail['facts_reason']


def test_payment_ambiguous_on_user_mismatch(case):
    user = make_user(case)
    other = make_user(case, 'other@example.invalid', grant=False)
    payment(case, 'pi_u', user)
    fact(case, 'f1', user_id=other, pi='pi_u')
    payment(case, 'pi_unbound', None)
    fact(case, 'f2', user_id=user, pi='pi_unbound')
    with admin_client(case) as client:
        login(client)
        assert get(client, '/billing/payments/pi_u')['facts_state'] == 'ambiguous'
        assert get(client, '/billing/payments/pi_unbound')['facts_state'] == 'ambiguous'


def test_payment_none_without_candidates_or_verified(case):
    user = make_user(case)
    payment(case, 'pi_none', user)
    payment(case, 'pi_unverified', user)
    fact(case, 'f1', user_id=user, pi='pi_unverified', reconciliation='needs_review')
    with admin_client(case) as client:
        login(client)
        assert get(client, '/billing/payments/pi_none')['facts_state'] == 'none'
        assert get(client, '/billing/payments/pi_unverified')['facts_state'] == 'none'
        assert client.get(BASE + '/billing/payments/pi_missing').status_code == 404


def test_money_always_null_in_m1(case):
    user = make_user(case)
    payment(case, 'pi_m', user)
    fact(case, 'f1', user_id=user, pi='pi_m')
    with admin_client(case) as client:
        login(client)
        listing = get(client, '/billing/payments')
        detail = get(client, '/billing/payments/pi_m')
    assert all(item['money'] is None and item['amount_state'] == 'unknown' for item in listing['items'])
    assert detail['money'] is None and detail['verified_facts']
    assert all(fact['money'] is None and fact['amount_refunded_minor'] is None for fact in detail['verified_facts'])


def test_checkout_state_reconciliation_fulfilled_independent(case):
    user = make_user(case)
    checkout(case, 'co_paid', user, state='paid', fulfilled=False, reconciliation='verified')
    checkout(case, 'co_open', user, state='open', fulfilled=False)
    fact(case, 'f1', user_id=user, checkout_id='co_paid')
    with admin_client(case) as client:
        login(client)
        unfulfilled = get(client, '/billing/checkouts', state='paid', fulfilled='false')
        detail = get(client, '/billing/checkouts/co_paid')
    assert [item['id'] for item in unfulfilled['items']] == ['co_paid']
    item = unfulfilled['items'][0]
    assert (item['state'], item['reconciliation'], item['fulfilled'], item['revision']) == ('paid', 'verified', False, '2')
    assert item['created_at'].endswith('Z') and item['expires_at'].endswith('Z')
    assert detail['facts_state'] == 'available' and [f['id'] for f in detail['verified_facts']] == ['f1']
    assert (detail['price_id'], detail['mode'], detail['duration_days'], detail['reconcile_attempts']) == (
        'price_test', 'payment', 30, 0)


def test_checkout_facts_ambiguous_on_scope_mismatch_or_unknown_scope(case):
    user = make_user(case)
    checkout(case, 'co_mismatch', user, livemode=False)
    fact(case, 'f1', user_id=user, checkout_id='co_mismatch', livemode=True)
    checkout(case, 'co_unknown', user, scope=None, livemode=None)
    fact(case, 'f2', user_id=user, checkout_id='co_unknown')
    with admin_client(case) as client:
        login(client)
        for checkout_id in ('co_mismatch', 'co_unknown'):
            detail = get(client, f'/billing/checkouts/{checkout_id}')
            assert (detail['facts_state'], detail['verified_facts']) == ('ambiguous', [])


def test_checkout_detail_no_raw_provider_payload(case):
    user = make_user(case)
    checkout(case, 'co_1', user)
    with admin_client(case) as client:
        login(client)
        dumped = json.dumps([get(client, '/billing/checkouts'), get(client, '/billing/checkouts/co_1')])
    for leak in ('SECRETURL', 'PAYLOADSECRET', 'create_payload', '"url"'):
        assert leak not in dumped
    with admin_client(case) as client:
        login(client)
        assert client.get(BASE + '/billing/checkouts/co_missing').status_code == 404
        assert client.get(BASE + '/billing/checkouts', params={'state': 'completed'}).status_code == 422
