"""Shared helpers for the admin M1 PG tests (nonce-owned isolated PG via the `case` fixture)."""
import dataclasses
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.admin.config import AdminSettings

SECRET = b'k' * 32
ORIGIN = 'https://admin.test'
BASE = '/api/admin/v1'


def admin_settings(**changes) -> AdminSettings:
    base = AdminSettings(cookie_path=BASE, allowed_origins=(ORIGIN,), csrf_secret=SECRET)
    return dataclasses.replace(base, **changes)


def admin_client(case, *, check_schema: bool = False, session_reader=None, **changes) -> TestClient:
    from app.admin.app import build_asgi
    app = build_asgi(admin_settings(**changes), case.application, check_schema=check_schema, session_reader=session_reader)
    return TestClient(app, base_url='https://testserver', headers={'Origin': ORIGIN})


def run(case, sql, **params):
    with case.migration.begin() as connection:
        return connection.execute(text(sql), params)


def make_user(case, email='admin@example.invalid', password='correct horse battery', *, role='admin',
              grant=True, active=True, enabled=None, protected=False, user_id=None):
    """A user (migration role writes everything, like the operator CLI would for grants)."""
    from app.services.auth import hash_password
    user_id = user_id or 'u-' + uuid.uuid4().hex[:12]
    run(case, 'INSERT INTO app."user" (id,email,password_hash,created_at) VALUES (:i,:e,:p,now())',
        i=user_id, e=email, p=hash_password(password))
    if grant:
        run(case, "INSERT INTO app.admingrant (user_id,role,active,revision,granted_at,granted_by,reason) "
                  "VALUES (:u,:r,:a,1,now(),'cli:test','granted for admin tests')", u=user_id, r=role, a=active)
    if enabled is not None:
        run(case, "INSERT INTO app.accountcontrol (user_id,enabled,revision,auth_revision,protected_account,updated_at) "
                  "VALUES (:u,:e,1,0,:p,now())", u=user_id, e=enabled, p=protected)
    return user_id


def login(client, email='admin@example.invalid', password='correct horse battery') -> str:
    """Log in and return the CSRF token from /auth/me."""
    response = client.post(BASE + '/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    me = client.get(BASE + '/auth/me')
    assert me.status_code == 200, me.text
    return me.json()['csrf_token']


def add_job(case, job_id, user_id, *, version=1, status='done', internal_state=None, error_type=None, error=None,
            url='https://Video.Example.invalid:8443/watch?v=1&token=SECRET'):
    columns = dict(id=job_id, url=url, status=status, progress=100.0, user_id=user_id, execution_version=version,
                   internal_state=internal_state, error_type=error_type, error=error)
    deadline = "now() + interval '30 minutes'" if version == 2 else 'NULL'  # v2 rows need it at insert (CHECK)
    names = ','.join(columns)
    run(case, f'INSERT INTO app.job ({names},created_at,updated_at,run_deadline_at) '
              f'VALUES ({",".join(":" + n for n in columns)},now(),now(),{deadline})', **columns)


def add_membership(case, user_id, status, expires_in_seconds):
    """Membership.expires_at is epoch seconds; relative to the DB clock."""
    run(case, 'INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision) '
              'VALUES (:u,:s,extract(epoch from now()) + :d,false,0)', u=user_id, s=status, d=expires_in_seconds)
