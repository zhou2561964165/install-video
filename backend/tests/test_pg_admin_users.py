"""Admin M1 Task 7: users and memberships (nonce-owned PG)."""
import json
import os

import pytest

from admin_pg_helpers import BASE, add_membership, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def get(client, path, **params):
    response = client.get(BASE + path, params=params)
    return response


def test_membership_effective_boundary(case):
    admin = make_user(case)
    exact = make_user(case, 'exact@example.invalid', grant=False)
    later = make_user(case, 'later@example.invalid', grant=False)
    cancelled = make_user(case, 'cancelled@example.invalid', grant=False)
    # The boundary is the snapshot's own DB clock: expires_at == as_of is not effective.
    run(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision) "
              "VALUES (:u,'active',extract(epoch from now()),false,3)", u=exact)
    add_membership(case, later, 'active', 3600)
    add_membership(case, cancelled, 'canceled', 3600)
    with admin_client(case) as client:
        login(client)
        items = {item['user_id']: item for item in get(client, '/memberships', page_size='100').json()['items']}
        effective = get(client, '/memberships', effective='true').json()
    assert items[exact]['effective'] is False and items[later]['effective'] is True
    assert items[cancelled]['effective'] is False and items[cancelled]['status'] == 'canceled'
    assert [item['user_id'] for item in effective['items']] == [later] and effective['total'] == 1
    assert items[exact]['revision'] == '3' and items[later]['expires_at'].endswith('Z')
    assert admin not in items


def test_user_without_membership_is_free_with_nulls(case):
    user = make_user(case)
    with admin_client(case) as client:
        login(client)
        detail = get(client, f'/users/{user}').json()
    assert detail['membership'] == {'user_id': user, 'status': 'free', 'effective': False, 'expires_at': None,
                                    'revision': None, 'entitlement_source': None, 'cancel_at_period_end': False}


def test_missing_account_control_defaults_enabled(case):
    admin = make_user(case)
    plain = make_user(case, 'plain@example.invalid', grant=False)
    disabled = make_user(case, 'off@example.invalid', grant=False, enabled=False)
    with admin_client(case) as client:
        login(client)
        enabled = {item['id'] for item in get(client, '/users', enabled='true').json()['items']}
        off = get(client, '/users', enabled='false').json()['items']
        plain_access = get(client, f'/users/{plain}').json()['access']
    assert enabled == {admin, plain} and [item['id'] for item in off] == [disabled]
    assert plain_access == {'enabled': True, 'revision': '0', 'protected_account': False}


def test_admin_accounts_are_protected(case):
    admin = make_user(case)
    other_admin = make_user(case, 'second@example.invalid')
    with admin_client(case) as client:
        login(client)
        assert get(client, f'/users/{admin}').json()['access']['protected_account'] is True
        assert get(client, f'/users/{other_admin}').json()['access']['protected_account'] is True


def test_quota_unlimited_keeps_used_and_negative_remaining(case, monkeypatch):
    from app.config import settings
    admin = make_user(case)
    run(case, "INSERT INTO app.quota (id,user_id,date,downloads_used,\"limit\") "
              "VALUES ('q1',:u,to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD'),7,5)", u=admin)
    monkeypatch.setattr(settings, 'membership_unlimited_downloads', False)
    monkeypatch.setattr('app.services.quota_policy.is_unlimited_user', lambda user_id: False)
    with admin_client(case) as client:
        login(client)
        quota = get(client, f'/users/{admin}').json()['quota']
        assert (quota['used'], quota['limit'], quota['remaining'], quota['unlimited']) == (7, 5, -2, False)
        monkeypatch.setattr(settings, 'membership_unlimited_downloads', True)
        unlimited = get(client, f'/users/{admin}').json()
    quota = unlimited['quota']
    assert (quota['used'], quota['limit'], quota['remaining'], quota['unlimited']) == (7, None, None, True)
    assert quota['quota_day'] == unlimited['as_of'][:10]


def test_user_list_filters_sorts_and_effective_vip(case):
    admin = make_user(case, 'b@example.invalid')
    vip = make_user(case, 'a-vip@example.invalid', grant=False)
    add_membership(case, vip, 'active', 600)
    with admin_client(case) as client:
        login(client, 'b@example.invalid')
        by_email = get(client, '/users', sort='email:asc').json()
        vips = get(client, '/users', effective_vip='true').json()
        searched = get(client, '/users', email='VIP').json()
    assert [item['email'] for item in by_email['items']] == ['a-vip@example.invalid', 'b@example.invalid']
    assert by_email['page'] == 1 and by_email['page_size'] == 20 and by_email['as_of'].endswith('Z')
    assert [item['id'] for item in vips['items']] == [vip] and vips['items'][0]['membership']['effective'] is True
    assert [item['id'] for item in searched['items']] == [vip]
    assert admin in {item['id'] for item in by_email['items']}


def test_user_detail_excludes_secrets(case):
    user = make_user(case)
    with admin_client(case) as client:
        login(client)
        body = json.dumps(get(client, f'/users/{user}').json()) + json.dumps(get(client, '/users').json())
    for forbidden in ('password', 'pbkdf2', 'token', 'cookie', 'csrf'):
        assert forbidden not in body.lower()


def test_user_not_found_404(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        response = get(client, '/users/u-missing')
    assert response.status_code == 404 and response.json()['detail']['error_type'] == 'not_found'


def test_unknown_filter_or_sort_422(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        assert get(client, '/users', sort='password_hash:asc').status_code == 422
        assert get(client, '/users', role='admin').status_code == 422
        assert get(client, '/memberships', status='gold').status_code == 422
        assert get(client, '/users', page_size='101').status_code == 422


def test_users_permission_required(case, monkeypatch):
    from app.admin import deps
    make_user(case, role='viewer')
    monkeypatch.setitem(deps.ROLE_PERMISSIONS, 'viewer', frozenset({'overview:read'}))
    with admin_client(case) as client:
        login(client)
        assert get(client, '/users').status_code == 403
        assert get(client, '/memberships').status_code == 403


def test_membership_effective_at_exact_expiry_instant(case):
    # Review-focus boundary pinned exactly: as_of == expires_at is NOT effective, one microsecond earlier is.
    from datetime import datetime, timedelta, timezone
    from app.admin.config import AdminSettings
    from app.services import admin_queries
    user = make_user(case, grant=False)
    expires = 1893456000.0  # 2030-01-01T00:00:00Z, exactly representable
    run(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision) "
              "VALUES (:u,'active',:e,false,1)", u=user, e=expires)
    at = datetime.fromtimestamp(expires, tz=timezone.utc)
    settings = AdminSettings(cookie_path='/api/admin/v1', allowed_origins=('https://a.example',), csrf_secret=b'k' * 32)
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListMemberships'], {'effective': 'true'}, settings)
    with admin_queries.read_snapshot(case.application) as (connection, _):
        exact, _ = admin_queries.list_memberships(connection, at, query)
        before, _ = admin_queries.list_memberships(connection, at - timedelta(microseconds=1), query)
    assert exact == [] and [item['user_id'] for item in before] == [user]
    assert before[0]['effective'] is True


def test_membership_sort_puts_missing_expiry_last(case):
    make_user(case)
    soon = make_user(case, 'soon@example.invalid', grant=False)
    later = make_user(case, 'later2@example.invalid', grant=False)
    none = make_user(case, 'none@example.invalid', grant=False)
    add_membership(case, soon, 'active', 60)
    add_membership(case, later, 'active', 6000)
    run(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision) "
              "VALUES (:u,'free',0,false,0)", u=none)
    with admin_client(case) as client:
        login(client)
        ascending = [i['user_id'] for i in get(client, '/memberships', sort='expires_at:asc').json()['items']]
        descending = [i['user_id'] for i in get(client, '/memberships', sort='expires_at:desc').json()['items']]
    assert ascending == [soon, later, none] and descending == [later, soon, none]
