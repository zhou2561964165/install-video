"""Support tickets Task 6: admin ticket list, detail, reply and reject (nonce-owned PG)."""
import os

import pytest
from sqlalchemy import text

from admin_pg_helpers import BASE, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def checkout(case, checkout_id, user_id, *, stripe_id='cs_test_1', fulfilled=False):
    run(case, "INSERT INTO app.billingcheckout (id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,"
              "fulfilled,reconcile_attempts,revision,stripe_id,provider_account_scope,livemode) VALUES (:i,:u,'price_test',"
              "'payment',30,'https://s.invalid',extract(epoch from now()) - 600,0,'open',:f,0,0,:s,'acct_synthetic',false)",
        i=checkout_id, u=user_id, f=fulfilled, s=stripe_id)


def ticket(case, ticket_id, user_id, *, category='other', checkout_id=None, priority='normal', minutes_ago=0, note=None):
    run(case, "INSERT INTO app.supportticket (id,user_id,category,user_note,checkout_id,priority,state,created_at,revision) "
              "VALUES (:i,:u,:c,:n,:co,:p,'open',now() - make_interval(mins => :m),0)",
        i=ticket_id, u=user_id, c=category, n=note, co=checkout_id, p=priority, m=minutes_ago)


def customer(case, email='customer@example.invalid'):
    return make_user(case, email, grant=False)


def test_priority_first_then_oldest(case):
    make_user(case)
    user = customer(case)
    ticket(case, 'n-old', user, minutes_ago=50)
    ticket(case, 'p-new', user, priority='priority', minutes_ago=5)
    ticket(case, 'p-old', user, priority='priority', minutes_ago=30)
    ticket(case, 'n-new', user, minutes_ago=1)
    with admin_client(case) as client:
        login(client)
        page = client.get(BASE + '/support/tickets').json()
        only_priority = client.get(BASE + '/support/tickets', params={'priority': 'priority'}).json()
    assert [item['id'] for item in page['items']] == ['p-old', 'p-new', 'n-old', 'n-new']
    first = page['items'][0]
    assert first['category_label'] == '其他问题' and first['priority'] == 'priority' and first['user_email'] == 'customer@example.invalid'
    assert only_priority['total'] == 2


def test_detail_shows_checkout_membership_and_actions(case):
    make_user(case)
    user = customer(case)
    checkout(case, 'co-1', user)
    ticket(case, 't1', user, category='membership_not_credited', checkout_id='co-1', priority='priority', note='付了钱')
    with admin_client(case, stripe_read_key='rk_test_synthetic', stripe_livemode=False) as client:
        login(client)
        detail = client.get(BASE + '/support/tickets/t1').json()
    assert detail['user_note'] == '付了钱' and detail['checkout']['id'] == 'co-1' and detail['checkout']['fulfilled'] is False
    assert detail['membership']['status'] == 'free' and detail['latest_check'] is None
    assert detail['actions']['verify'] == {'allowed': True, 'reason': None}
    assert detail['actions']['reissue'] == {'allowed': False, 'reason': 'not_verified'}
    assert detail['actions']['reply']['allowed'] and detail['actions']['reject']['allowed']


def test_detail_actions_explain_unavailable(case):
    make_user(case)
    user = customer(case)
    checkout(case, 'co-1', user)
    checkout(case, 'co-2', user, stripe_id=None)
    ticket(case, 't1', user, category='membership_not_credited', checkout_id='co-1')
    ticket(case, 't2', user, category='membership_not_credited', checkout_id='co-2')
    ticket(case, 't3', user)
    with admin_client(case) as client:  # no read key configured
        login(client)
        no_key = client.get(BASE + '/support/tickets/t1').json()['actions']
    with admin_client(case, stripe_read_key='rk_test_synthetic', stripe_livemode=False) as client:
        login(client)
        no_session = client.get(BASE + '/support/tickets/t2').json()['actions']
        other = client.get(BASE + '/support/tickets/t3').json()['actions']
    assert no_key['verify'] == {'allowed': False, 'reason': 'stripe_read_key_missing'}
    assert no_key['reissue']['reason'] == 'stripe_read_key_missing'
    assert no_session['verify'] == {'allowed': False, 'reason': 'no_stripe_session'}
    assert other['verify']['reason'] == other['reissue']['reason'] == 'not_reissuable_category'


def test_reply_closes_and_user_sees_text(case):
    from sqlmodel import Session
    from app.services import support_tickets
    make_user(case)
    user = customer(case)
    ticket(case, 't1', user, category='download_failing')
    with admin_client(case) as client:
        csrf = login(client)
        response = client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'download_help', 'note': '换 720p'},
                               headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200 and response.json()['state'] == 'resolved'
    with Session(case.application) as session:
        item = support_tickets.list_tickets(session, user)[0]
    assert item['reply_text'] == '已收到，请尝试重新解析链接或更换清晰度；若仍失败请再次反馈' and item['reply_note'] == '换 720p'
    assert (item['state'], item['resolution']) == ('resolved', 'replied')


def test_reject_and_closed_ticket_cannot_change(case):
    make_user(case)
    user = customer(case)
    checkout(case, 'co-1', user)
    ticket(case, 't1', user, category='membership_not_credited', checkout_id='co-1')
    with admin_client(case) as client:
        csrf = login(client)
        rejected = client.post(BASE + '/support/tickets/t1/reject', json={'template_id': 'not_paid'},
                               headers={'X-CSRF-Token': csrf})
        again = client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'generic'},
                            headers={'X-CSRF-Token': csrf})
    assert rejected.status_code == 200 and rejected.json()['state'] == 'rejected'
    assert again.status_code == 409 and again.json()['detail']['error_type'] == 'ticket_closed'


def test_reply_rejects_reissued_template_and_long_note(case):
    make_user(case)
    ticket(case, 't1', customer(case))
    with admin_client(case) as client:
        csrf = login(client)
        reissued = client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'reissued'},
                               headers={'X-CSRF-Token': csrf})
        long_note = client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'generic', 'note': '字' * 501},
                                headers={'X-CSRF-Token': csrf})
    assert reissued.status_code == 422 and reissued.json()['detail']['error_type'] == 'invalid_template'
    assert long_note.status_code == 422


def test_viewer_reads_cannot_reply(case):
    make_user(case, role='viewer')
    ticket(case, 't1', customer(case))
    with admin_client(case) as client:
        csrf = login(client)
        assert client.get(BASE + '/support/tickets').status_code == 200
        response = client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'generic'},
                               headers={'X-CSRF-Token': csrf})
        permissions = client.get(BASE + '/auth/me').json()['permissions']
    assert response.status_code == 403
    assert 'support:read' in permissions and 'support:write' not in permissions


def test_writes_need_csrf_and_origin(case):
    make_user(case)
    ticket(case, 't1', customer(case))
    with admin_client(case) as client:
        csrf = login(client)
        assert client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'generic'}).status_code == 403
        assert client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'generic'},
                           headers={'X-CSRF-Token': csrf, 'Origin': 'https://evil.example'}).status_code == 403


def test_audit_rows_for_reply_reject(case):
    admin = make_user(case)
    user = customer(case)
    ticket(case, 't1', user)
    ticket(case, 't2', user)
    with admin_client(case) as client:
        csrf = login(client)
        client.post(BASE + '/support/tickets/t1/reply', json={'template_id': 'generic'}, headers={'X-CSRF-Token': csrf})
        client.post(BASE + '/support/tickets/t2/reject', json={'template_id': 'generic'}, headers={'X-CSRF-Token': csrf})
    with case.migration.connect() as connection:
        rows = connection.execute(text("SELECT action, actor_user_id, target_user_id FROM app.adminaudit "
                                       "WHERE action LIKE 'support.%' ORDER BY recorded_at")).all()
    assert [tuple(row) for row in rows] == [('support.reply', admin, user), ('support.reject', admin, user)]


def test_capabilities_report_support_reissue(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        off = client.get(BASE + '/auth/me').json()['capabilities']['support_reissue']
    with admin_client(case, stripe_read_key='rk_test_synthetic', stripe_livemode=False) as client:
        login(client)
        me = client.get(BASE + '/auth/me').json()
    assert off == {'ready': False, 'reason': 'stripe_read_key_missing'}
    assert me['capabilities']['support_reissue'] == {'ready': True, 'reason': None}
    assert 'support:reissue' in me['permissions']
