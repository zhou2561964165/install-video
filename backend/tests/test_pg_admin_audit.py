"""Admin M1 Task 10: audit log list and the closed M2 access endpoint (nonce-owned PG)."""
import json
import os

import pytest
from sqlalchemy import text

from admin_pg_helpers import BASE, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def entries(client, **params):
    response = client.get(BASE + '/audit/logs', params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_audit_lists_login_events_with_contract_fields(case):
    admin = make_user(case)
    with admin_client(case) as client:
        client.post(BASE + '/auth/login', json={'email': 'admin@example.invalid', 'password': 'wrong one'})
        login(client)
        page = entries(client, sort='recorded_at:asc')
        failed = entries(client, outcome='failed')
        mine = entries(client, actor_user_id=admin)
    assert [item['action'] for item in page['items']] == ['auth.login_failed', 'auth.login']
    first = page['items'][0]
    assert set(first) >= {'id', 'actor_user_id', 'target_user_id', 'action', 'outcome', 'reason', 'request_id',
                          'recorded_at', 'change', 'operation'}
    assert (first['change'], first['operation'], first['actor_user_id']) == (None, None, None)
    assert first['recorded_at'].endswith('Z')
    assert [item['action'] for item in failed['items']] == ['auth.login_failed']
    assert [item['action'] for item in mine['items']] == ['auth.login']


def test_audit_time_filters_require_utc(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        assert client.get(BASE + '/audit/logs', params={'recorded_from': '2026-10-28T00:00:00+08:00'}).status_code == 422
        assert client.get(BASE + '/audit/logs', params={'recorded_from': 'yesterday'}).status_code == 422
        assert entries(client, recorded_from='2000-01-01T00:00:00Z')['total'] == 1
        assert entries(client, recorded_before='2000-01-01T00:00:00Z')['total'] == 0


def test_audit_entries_hide_cli_details_and_inputs(case):
    make_user(case)
    run(case, "INSERT INTO app.adminaudit (event_id,actor_kind,action,outcome,request_id,target_user_id,reason,changes) "
              "VALUES ('cli1','cli','admin.grant','succeeded','r-cli','u-x','operator reason here',"
              "'{\"role\":\"admin\",\"by\":\"cli:operator-login\"}')")
    with admin_client(case) as client:
        login(client)
        body = entries(client, action='admin.grant')
    assert body['total'] == 1 and body['items'][0]['change'] is None
    assert 'operator-login' not in json.dumps(body)


def test_access_patch_disabled_in_m1(case):
    make_user(case)
    target = make_user(case, 'target@example.invalid', grant=False)
    with admin_client(case) as client:
        csrf = login(client)
        response = client.patch(BASE + f'/users/{target}/access',
                                json={'enabled': False, 'reason': 'testing the closed endpoint', 'expected_revision': '0'},
                                headers={'X-CSRF-Token': csrf, 'Idempotency-Key': 'k-123456789'})
        listed = entries(client, action='users.access_denied')
    assert response.status_code == 503 and response.json()['detail']['error_type'] == 'capability_unavailable'
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.accountcontrol')) == 0
    assert listed['total'] == 1
    item = listed['items'][0]
    assert (item['outcome'], item['operation'], item['target_user_id']) == ('denied', 'users.access', target)


def test_access_patch_still_needs_session_origin_and_csrf(case):
    make_user(case)
    target = make_user(case, 'target@example.invalid', grant=False)
    body = {'enabled': False, 'reason': 'testing the closed endpoint', 'expected_revision': '0'}
    with admin_client(case) as anonymous:
        assert anonymous.patch(BASE + f'/users/{target}/access', json=body).status_code == 401
    with admin_client(case) as client:
        login(client)
        assert client.patch(BASE + f'/users/{target}/access', json=body).status_code == 403  # no CSRF


def test_audit_permission_required(case, monkeypatch):
    from app.admin import deps
    make_user(case, role='viewer')
    monkeypatch.setitem(deps.ROLE_PERMISSIONS, 'viewer', frozenset({'users:read'}))
    with admin_client(case) as client:
        login(client)
        assert client.get(BASE + '/audit/logs').status_code == 403
