"""Admin M1 Task 4: login/me/logout, live session checks, throttling and audit (nonce-owned PG)."""
import json
import os

import pytest
from sqlalchemy import text

from admin_pg_helpers import BASE, ORIGIN, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
EMAIL, PASSWORD = 'admin@example.invalid', 'correct horse battery'
READ = ['audit:read', 'billing:read', 'jobs:read', 'memberships:read', 'overview:read', 'system:read', 'users:read']


def without_request_id(response):
    detail = dict(response.json()['detail'])
    detail.pop('request_id')
    return response.status_code, json.dumps(detail, sort_keys=True, ensure_ascii=False)


def audits(case):
    with case.migration.connect() as connection:
        return connection.execute(text('SELECT actor_user_id, actor_kind, action, outcome, request_id, changes '
                                       'FROM app.adminaudit ORDER BY recorded_at, event_id')).all()


def test_login_sets_strict_cookie_and_me_returns_permissions(case):
    user_id = make_user(case)
    with admin_client(case) as client:
        response = client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': PASSWORD})
        assert response.status_code == 200 and response.json()['session_expires_at'].endswith('Z')
        cookie = response.headers['set-cookie']
        for part in ('iv_admin_session=', 'HttpOnly', 'Secure', 'SameSite=strict', 'Path=/api/admin/v1', 'Max-Age=900'):
            assert part.lower() in cookie.lower(), part
        assert 'domain=' not in cookie.lower()
        me = client.get(BASE + '/auth/me').json()
    assert me['user_id'] == user_id and me['email'] == EMAIL and me['role'] == 'admin'
    # users:access:write only once account_access_write is ready (M2); support:reissue only with the Stripe read key.
    assert sorted(me['permissions']) == sorted(READ + ['support:read', 'support:write'])
    assert me['capabilities']['account_access_write']['ready'] is False
    assert me['capabilities']['billing_amounts']['ready'] is False
    assert len(me['csrf_token']) >= 32 and me['session_expires_at'].endswith('Z')


def test_viewer_gets_read_permissions_only(case):
    make_user(case, role='viewer')
    with admin_client(case) as client:
        login(client)
        assert sorted(client.get(BASE + '/auth/me').json()['permissions']) == sorted(READ + ['support:read'])


def test_login_failures_are_indistinguishable(case):
    make_user(case)
    make_user(case, 'nogrant@example.invalid', grant=False)
    make_user(case, 'inactive@example.invalid', active=False)
    make_user(case, 'disabled@example.invalid', enabled=False)
    attempts = [('unknown@example.invalid', PASSWORD), (EMAIL, 'wrong password'), ('nogrant@example.invalid', PASSWORD),
                ('inactive@example.invalid', PASSWORD), ('disabled@example.invalid', PASSWORD)]
    with admin_client(case) as client:
        results = {without_request_id(client.post(BASE + '/auth/login', json={'email': email, 'password': password}))
                   for email, password in attempts}
    assert len(results) == 1 and next(iter(results))[0] == 401


def test_login_body_validation_uses_field_errors(case):
    with admin_client(case) as client:
        response = client.post(BASE + '/auth/login', json={'email': EMAIL})
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['error_type'] == 'validation_failed'
    assert {'field': 'password', 'message': detail['field_errors'][0]['message']} in detail['field_errors']


def test_login_refused_without_origin_allowlist(case):
    make_user(case)
    with admin_client(case, allowed_origins=()) as client:
        response = client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': PASSWORD})
    assert response.status_code == 403 and 'set-cookie' not in response.headers


def test_login_wrong_or_missing_origin_403(case):
    make_user(case)
    with admin_client(case) as client:
        wrong = client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': PASSWORD},
                            headers={'Origin': 'https://evil.example'})
        client.headers.pop('Origin')
        missing = client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': PASSWORD})
    assert wrong.status_code == 403 and missing.status_code == 403


def test_login_throttle_429_with_retry_after(case):
    make_user(case)
    with admin_client(case) as client:
        for _ in range(5):
            assert client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': 'nope'}).status_code == 401
        blocked = client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers['Retry-After']) >= 1
    assert blocked.json()['detail']['request_id'] == blocked.headers['X-Request-ID']
    with case.migration.connect() as connection:
        stored = connection.execute(text('SELECT key_hash FROM app.adminloginthrottle')).scalars().all()
    assert stored and all('admin' not in key and 'example' not in key for key in stored)


def test_successful_login_clears_failures(case):
    make_user(case)
    with admin_client(case) as client:
        for _ in range(4):
            client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': 'nope'})
        login(client)
    with case.migration.connect() as connection:
        # The address+email counter is cleared; the per-address bucket keeps its 4 failures (a successful
        # login on one account must not reset spraying across other emails).
        assert connection.execute(text('SELECT failures FROM app.adminloginthrottle')).scalars().all() == [4]


def test_session_expires_absolutely(case):
    make_user(case)
    with admin_client(case, session_ttl_seconds=300) as client:
        login(client)
        run(case, "UPDATE app.adminsession SET created_at = now() - interval '10 minutes', "
                  "expires_at = now() - interval '5 minutes'")
        response = client.get(BASE + '/auth/me')
    assert response.status_code == 401
    assert 'iv_admin_session=' in response.headers.get('set-cookie', '') and 'max-age=0' in response.headers['set-cookie'].lower()


def test_revoked_grant_ends_session_on_next_request(case):
    user_id = make_user(case)
    with admin_client(case) as client:
        login(client)
        run(case, 'UPDATE app.admingrant SET active=false WHERE user_id=:u', u=user_id)
        response = client.get(BASE + '/auth/me')
    assert response.status_code == 401 and 'max-age=0' in response.headers['set-cookie'].lower()


def test_disabled_account_ends_session_on_next_request(case):
    user_id = make_user(case)
    with admin_client(case) as client:
        login(client)
        run(case, "INSERT INTO app.accountcontrol (user_id,enabled,revision,auth_revision,protected_account,updated_at) "
                  "VALUES (:u,false,1,0,false,now())", u=user_id)
        assert client.get(BASE + '/auth/me').status_code == 401


def test_logout_requires_csrf_and_origin(case):
    make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        assert client.post(BASE + '/auth/logout').status_code == 403
        assert client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': 'x' * 64}).status_code == 403
        assert client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': csrf, 'Origin': 'https://evil.example'}).status_code == 403
        done = client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': csrf})
        assert done.status_code == 204 and 'max-age=0' in done.headers['set-cookie'].lower()
        assert 'path=/api/admin/v1' in done.headers['set-cookie'].lower()
    with admin_client(case) as client:
        csrf = login(client)
        token = client.cookies.get('iv_admin_session')
        client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': csrf})
        client.cookies.set('iv_admin_session', token, domain='testserver.local', path=BASE)
        again = client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': csrf})
    assert again.status_code == 401 and 'max-age=0' in again.headers['set-cookie'].lower()


def test_csrf_stable_across_me_calls(case):
    make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        assert client.get(BASE + '/auth/me').json()['csrf_token'] == csrf


def test_login_replaces_previous_browser_session(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        login(client)
    with case.migration.connect() as connection:
        rows = connection.execute(text('SELECT revoked_at IS NOT NULL FROM app.adminsession ORDER BY created_at')).scalars().all()
    assert rows == [True, False]


def test_auth_events_audited_without_secrets(case):
    user_id = make_user(case)
    with admin_client(case) as client:
        failed = client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': 'nope'})
        ok = client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': PASSWORD})
        csrf = client.get(BASE + '/auth/me').json()['csrf_token']
        out = client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': csrf})
    rows = audits(case)
    assert [(row.actor_kind, row.action, row.outcome) for row in rows] == [
        ('anonymous', 'auth.login_failed', 'failed'), ('admin', 'auth.login', 'succeeded'), ('admin', 'auth.logout', 'succeeded')]
    assert [row.request_id for row in rows] == [failed.headers['X-Request-ID'], ok.headers['X-Request-ID'], out.headers['X-Request-ID']]
    assert rows[0].actor_user_id is None and rows[1].actor_user_id == user_id
    dumped = repr(rows)
    assert PASSWORD not in dumped and 'nope' not in dumped and EMAIL not in dumped and csrf not in dumped


def test_normal_user_jwt_rejected(case):
    from app.services.auth import create_token
    user_id = make_user(case)
    with admin_client(case) as client:
        response = client.get(BASE + '/auth/me', headers={'Authorization': 'Bearer ' + create_token(user_id)})
    assert response.status_code == 401


def test_login_origin_checked_before_body(case):
    with admin_client(case, allowed_origins=()) as client:
        response = client.post(BASE + '/auth/login', json={'email': EMAIL})  # invalid body too
    assert response.status_code == 403 and response.json()['detail']['error_type'] == 'origin_rejected'


def test_logout_of_expired_session_is_401_even_with_bad_origin(case):
    make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        run(case, "UPDATE app.adminsession SET created_at = now() - interval '20 minutes', "
                  "expires_at = now() - interval '5 minutes'")
        response = client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': csrf, 'Origin': 'https://evil.example'})
    assert response.status_code == 401 and 'max-age=0' in response.headers['set-cookie'].lower()


def test_csrf_of_another_session_is_rejected(case):
    make_user(case)
    with admin_client(case) as first, admin_client(case) as second:
        csrf_first = login(first)
        login(second)
        assert second.post(BASE + '/auth/logout', headers={'X-CSRF-Token': csrf_first}).status_code == 403


def test_non_ascii_csrf_header_is_403(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        response = client.post(BASE + '/auth/logout', headers={'X-CSRF-Token': 'caf\u00e9'.encode('latin-1')})
    assert response.status_code == 403


def test_concurrent_failed_logins_are_all_counted(case):
    from concurrent.futures import ThreadPoolExecutor
    make_user(case)

    def attempt(_):
        with admin_client(case) as client:
            return client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': 'nope'}).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(attempt, range(12)))
    assert set(codes) <= {401, 429} and codes.count(401) == 5, codes
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT failures FROM app.adminloginthrottle')) == 5
        assert connection.scalar(text("SELECT count(*) FROM app.adminaudit WHERE action='auth.login_failed'")) == 5


def test_rotating_emails_from_one_client_hit_the_per_ip_limit(case):
    make_user(case)
    with admin_client(case) as client:
        codes = [client.post(BASE + '/auth/login', json={'email': f'spray{i}@example.invalid', 'password': 'nope'}).status_code
                 for i in range(25)]
    assert codes[:20] == [401] * 20 and set(codes[20:]) == {429}
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM app.adminaudit WHERE action='auth.login_failed'")) == 20


def test_expired_throttle_rows_are_purged(case):
    make_user(case)
    run(case, "INSERT INTO app.adminloginthrottle (key_hash,window_start,failures) "
              "VALUES (repeat('e',64), now() - interval '2 days', 3)")
    with admin_client(case) as client:
        client.post(BASE + '/auth/login', json={'email': EMAIL, 'password': 'nope'})
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM app.adminloginthrottle WHERE key_hash=repeat('e',64)")) == 0
