"""Support tickets Task 7: verify with the payment provider (fake reader) and the reviewed re-issue (nonce-owned PG)."""
from concurrent.futures import ThreadPoolExecutor
import os
import time

import pytest
from sqlalchemy import text

from admin_pg_helpers import BASE, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
DAY = 86400
KEY = {'stripe_read_key': 'rk_test_synthetic', 'stripe_livemode': False}


class FakeReader:
    def __init__(self, payloads):
        self.payloads, self.calls = payloads, []

    def read(self, session_id):
        from app.services.support_payment_check import ReaderUnavailable
        self.calls.append(session_id)
        payload = self.payloads.get(session_id)
        if payload is None or isinstance(payload, Exception):
            raise ReaderUnavailable()
        return payload


def paid(user_id, pi='pi_1', **overrides):
    session = {'id': 'cs_1', 'status': 'complete', 'payment_status': 'paid', 'client_reference_id': user_id,
               'mode': 'payment', 'livemode': False, 'line_items': {'data': [{'price': {'id': 'price_test'}, 'quantity': 1}]},
               'payment_intent': {'id': pi, 'status': 'succeeded',
                                  'latest_charge': {'id': 'ch_1', 'paid': True, 'status': 'succeeded', 'amount_refunded': 0,
                                                   'refunded': False, 'disputed': False}}}
    session.update(overrides)
    return session


def setup_ticket(case, *, category='membership_not_credited', fulfilled=False, stripe_id='cs_1', ticket_id='t1'):
    make_user(case)
    user = make_user(case, 'payer@example.invalid', grant=False)
    run(case, "INSERT INTO app.billingcheckout (id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,"
              "fulfilled,reconcile_attempts,revision,stripe_id,provider_account_scope,livemode) VALUES ('co-1',:u,"
              "'price_test','payment',30,'https://s.invalid',extract(epoch from now()) - 600,0,'open',:f,0,0,:s,"
              "'acct_synthetic',false)", u=user, f=fulfilled, s=stripe_id)
    run(case, "INSERT INTO app.supportticket (id,user_id,category,checkout_id,priority,state,created_at,revision) "
              "VALUES (:t,:u,:c,:co,'priority','open',now(),0)", t=ticket_id, u=user, c=category,
        co='co-1' if category == 'membership_not_credited' else None)
    return user


def post(client, csrf, path, key=None):
    headers = {'X-CSRF-Token': csrf}
    if key:
        headers['Idempotency-Key'] = key
    return client.post(BASE + path, headers=headers)


def membership(case, user):
    with case.migration.connect() as connection:
        return connection.execute(text('SELECT status, expires_at FROM app.membership WHERE user_id=:u'), {'u': user}).first()


def test_verify_records_result_and_audit(case):
    user = setup_ticket(case)
    reader = FakeReader({'cs_1': paid(user)})
    with admin_client(case, session_reader=reader, **KEY) as client:
        csrf = login(client)
        response = post(client, csrf, '/support/tickets/t1/verify-payment')
        detail = client.get(BASE + '/support/tickets/t1').json()
    assert response.status_code == 200 and response.json()['result'] == 'verified' and response.json()['fresh'] is True
    assert reader.calls == ['cs_1'] and detail['actions']['reissue'] == {'allowed': True, 'reason': None}
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT payment_intent FROM app.supportpaymentcheck")) == 'pi_1'
        assert connection.scalar(text("SELECT count(*) FROM app.adminaudit WHERE action='support.verify'")) == 1


def test_verify_failure_reason_recorded(case):
    user = setup_ticket(case)
    reader = FakeReader({'cs_1': paid(user, payment_status='unpaid')})
    with admin_client(case, session_reader=reader, **KEY) as client:
        csrf = login(client)
        assert post(client, csrf, '/support/tickets/t1/verify-payment').json()['result'] == 'not_paid'
        assert post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001').json()['detail']['error_type'] == 'not_verified'


def test_verify_attempt_limit(case):
    user = setup_ticket(case)
    reader = FakeReader({'cs_1': paid(user, payment_status='unpaid')})
    with admin_client(case, session_reader=reader, verify_max_attempts=2, **KEY) as client:
        csrf = login(client)
        codes = [post(client, csrf, '/support/tickets/t1/verify-payment').status_code for _ in range(3)]
    assert codes == [200, 200, 409] and len(reader.calls) == 2


def test_reader_unavailable_is_503_and_records_nothing(case):
    setup_ticket(case)
    with admin_client(case, session_reader=FakeReader({}), **KEY) as client:
        csrf = login(client)
        response = post(client, csrf, '/support/tickets/t1/verify-payment')
    assert response.status_code == 503 and response.json()['detail']['error_type'] == 'payment_provider_unavailable'
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.supportpaymentcheck')) == 0


def test_reissue_happy_path(case):
    user = setup_ticket(case)
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        csrf = login(client)
        post(client, csrf, '/support/tickets/t1/verify-payment')
        before = time.time()
        response = post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001')
        detail = client.get(BASE + '/support/tickets/t1')  # the closed ticket renders its automatic reply
    body = response.json()
    assert detail.status_code == 200 and detail.json()['reply_text'] == '已为您补发 30 天会员，请刷新会员页查看'
    assert response.status_code == 200 and body['granted_days'] == 30
    assert body['reply_text'] == '已为您补发 30 天会员，请刷新会员页查看'
    status, expires = membership(case, user)
    assert status == 'active' and abs(expires - (before + 30 * DAY)) < 60
    with case.migration.connect() as connection:
        ticket = connection.execute(text("SELECT state, resolution, reply_template FROM app.supportticket")).one()
        fulfilled = connection.scalar(text("SELECT fulfilled FROM app.billingcheckout WHERE id='co-1'"))
        audits = connection.execute(text("SELECT action FROM app.adminaudit WHERE action LIKE 'support.%' ORDER BY recorded_at")).scalars().all()
    assert tuple(ticket) == ('resolved', 'reissued', 'reissued') and fulfilled is True
    assert audits == ['support.verify', 'support.reissue']


def test_reissue_requires_fresh_verification(case):
    setup_ticket(case)
    with admin_client(case, session_reader=FakeReader({}), **KEY) as client:
        csrf = login(client)
        response = post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001')
    assert response.status_code == 409 and response.json()['detail']['error_type'] == 'not_verified'
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM app.adminaudit WHERE action='support.reissue_denied'")) == 1


def test_stale_verification_refused(case):
    user = setup_ticket(case)
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        csrf = login(client)
        post(client, csrf, '/support/tickets/t1/verify-payment')
        run(case, "UPDATE app.supportpaymentcheck SET checked_at = now() - interval '16 minutes'")
        response = post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001')
    assert response.status_code == 409 and response.json()['detail']['error_type'] == 'verification_stale'


def test_payment_bound_to_other_user_conflicts(case):
    user = setup_ticket(case)
    other = make_user(case, 'other@example.invalid', grant=False)
    run(case, "INSERT INTO app.billingpayment (payment_intent,user_id,source_id,revoked) VALUES ('pi_1',:u,'pi_1',false)", u=other)
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        csrf = login(client)
        post(client, csrf, '/support/tickets/t1/verify-payment')
        response = post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001')
    assert response.status_code == 409 and response.json()['detail']['error_type'] == 'payment_conflict'
    assert membership(case, user) is None or membership(case, user).status != 'active'


def test_concurrent_reissue_grants_once(case):
    user = setup_ticket(case)
    reader = FakeReader({'cs_1': paid(user)})
    with admin_client(case, session_reader=reader, **KEY) as client:
        csrf = login(client)
        post(client, csrf, '/support/tickets/t1/verify-payment')
        cookie = client.cookies.get('iv_admin_session')

    def attempt(key):
        with admin_client(case, session_reader=reader, **KEY) as other:
            other.cookies.set('iv_admin_session', cookie, domain='testserver.local', path=BASE)
            return other.post(BASE + '/support/tickets/t1/reissue', headers={'X-CSRF-Token': csrf, 'Idempotency-Key': key})
    before = time.time()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(attempt, ['reissue-key-000a', 'reissue-key-000b']))
    codes = sorted(response.status_code for response in responses)
    assert codes == [200, 409]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()['detail']['error_type'] == 'already_reissued'
    _, expires = membership(case, user)
    assert abs(expires - (before + 30 * DAY)) < 60  # granted exactly once
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.membershipreissue')) == 1


def test_idempotent_replay_same_result(case):
    user = setup_ticket(case)
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        csrf = login(client)
        post(client, csrf, '/support/tickets/t1/verify-payment')
        first = post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001')
        replay = post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001')
        missing = post(client, csrf, '/support/tickets/t1/reissue')
        short = post(client, csrf, '/support/tickets/t1/reissue', 'short-key')
        invalid = post(client, csrf, '/support/tickets/t1/reissue', 'contains spaces 0000')
    assert first.status_code == replay.status_code == 200 and first.json() == replay.json()
    assert missing.status_code == short.status_code == invalid.status_code == 422


def test_superseded_checkout_can_be_reissued(case):
    user = setup_ticket(case)
    run(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision,active_checkout_id) "
              "VALUES (:u,'free',0,false,0,'some-newer-checkout')", u=user)
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        csrf = login(client)
        post(client, csrf, '/support/tickets/t1/verify-payment')
        assert post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001').status_code == 200


def test_other_category_cannot_reissue(case):
    setup_ticket(case, category='other')
    with admin_client(case, session_reader=FakeReader({}), **KEY) as client:
        csrf = login(client)
        assert post(client, csrf, '/support/tickets/t1/verify-payment').json()['detail']['error_type'] == 'not_reissuable_category'
        assert post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001').json()['detail']['error_type'] == 'not_reissuable_category'


def test_already_fulfilled_refused(case):
    setup_ticket(case, fulfilled=True)
    with admin_client(case, session_reader=FakeReader({}), **KEY) as client:
        csrf = login(client)
        assert post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001').json()['detail']['error_type'] == 'already_fulfilled'


def test_without_read_key_verify_503_and_reissue_permission_gated(case):
    setup_ticket(case)
    with admin_client(case, session_reader=FakeReader({})) as client:
        csrf = login(client)
        assert post(client, csrf, '/support/tickets/t1/verify-payment').status_code == 503
        # support:reissue is a capability-gated permission: absent without the read key (/me says why)
        assert post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001').status_code == 403
        assert 'support:reissue' not in client.get(BASE + '/auth/me').json()['permissions']


def verified_then_reissue(case, user):
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        csrf = login(client)
        post(client, csrf, '/support/tickets/t1/verify-payment')
        detail = client.get(BASE + '/support/tickets/t1').json()
        return detail, post(client, csrf, '/support/tickets/t1/reissue', 'reissue-key-0001')


def test_membership_active_from_other_payment_refused(case):
    user = setup_ticket(case)
    run(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision,entitlement_source) "
              "VALUES (:u,'active',extract(epoch from now()) + 864000,false,0,'pi_other')", u=user)
    detail, response = verified_then_reissue(case, user)
    assert detail['actions']['reissue'] == {'allowed': False, 'reason': 'membership_active'}
    assert response.status_code == 409 and response.json()['detail']['error_type'] == 'membership_active'
    assert abs(membership(case, user).expires_at - (time.time() + 10 * DAY)) < 60  # untouched


def test_expired_membership_from_other_payment_can_be_reissued(case):
    user = setup_ticket(case)
    run(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision,entitlement_source) "
              "VALUES (:u,'active',extract(epoch from now()) - 60,false,0,'pi_other')", u=user)
    assert verified_then_reissue(case, user)[1].status_code == 200


def test_bound_subscription_refused(case):
    user = setup_ticket(case)
    run(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision,subscription_id) "
              "VALUES (:u,'expired',0,false,0,'sub_1')", u=user)
    detail, response = verified_then_reissue(case, user)
    assert detail['actions']['reissue']['reason'] == 'subscription_active'
    assert response.status_code == 409 and response.json()['detail']['error_type'] == 'subscription_active'
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT subscription_id FROM app.membership')) == 'sub_1'


def test_revoked_receipt_conflicts(case):
    user = setup_ticket(case)
    run(case, "INSERT INTO app.billingpayment (payment_intent,user_id,source_id,revoked) VALUES ('pi_1',NULL,NULL,true)")
    assert verified_then_reissue(case, user)[1].json()['detail']['error_type'] == 'payment_conflict'


def test_verify_and_reissue_require_csrf(case):
    user = setup_ticket(case)
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        login(client)
        assert post(client, 'wrong', '/support/tickets/t1/verify-payment').status_code == 403
        assert post(client, 'wrong', '/support/tickets/t1/reissue', 'reissue-key-0001').status_code == 403
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.supportpaymentcheck')) == 0


def test_viewer_cannot_verify_or_reissue(case):
    make_user(case, 'viewer@example.invalid', role='viewer')
    user = make_user(case, 'payer2@example.invalid', grant=False)
    run(case, "INSERT INTO app.billingcheckout (id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,"
              "fulfilled,reconcile_attempts,revision,stripe_id) VALUES ('co-v',:u,'price_test','payment',30,'https://s.invalid',"
              "extract(epoch from now()),0,'open',false,0,0,'cs_1')", u=user)
    run(case, "INSERT INTO app.supportticket (id,user_id,category,checkout_id,priority,state,created_at,revision) "
              "VALUES ('tv',:u,'membership_not_credited','co-v','priority','open',now(),0)", u=user)
    with admin_client(case, session_reader=FakeReader({'cs_1': paid(user)}), **KEY) as client:
        csrf = login(client, 'viewer@example.invalid')
        assert post(client, csrf, '/support/tickets/tv/verify-payment').status_code == 403
        assert post(client, csrf, '/support/tickets/tv/reissue', 'reissue-key-0001').status_code == 403
