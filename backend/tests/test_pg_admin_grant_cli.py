"""Admin M1 Task 5: operator grant CLI (dry-run default, privileged role only) on nonce-owned PG."""
import os

import pytest
from sqlalchemy import text

from admin_pg_helpers import make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
REASON = 'initial operator grant for testing'


def cli(case, monkeypatch, argv, *, engine='migration'):
    from app import admin_grant
    url = getattr(case, engine).url.render_as_string(hide_password=False)
    monkeypatch.setenv('ADMIN_CLI_DB_URL', url)
    return admin_grant.main(argv)


def grant_row(case, user_id):
    with case.migration.connect() as connection:
        return connection.execute(text('SELECT role, active, revision FROM app.admingrant WHERE user_id=:u'),
                                  {'u': user_id}).first()


def audit_rows(case):
    with case.migration.connect() as connection:
        return connection.execute(text('SELECT actor_kind, action, outcome, target_user_id, reason, changes '
                                       'FROM app.adminaudit ORDER BY recorded_at')).all()


def test_grant_dry_run_writes_nothing(case, monkeypatch, capsys):
    user_id = make_user(case, grant=False)
    assert cli(case, monkeypatch, ['grant', '--user-id', user_id, '--role', 'admin', '--reason', REASON]) == 0
    assert grant_row(case, user_id) is None and audit_rows(case) == []
    assert 'dry-run' in capsys.readouterr().out


def test_grant_apply_creates_active_grant_and_audit(case, monkeypatch):
    user_id = make_user(case, grant=False)
    assert cli(case, monkeypatch, ['grant', '--user-id', user_id, '--role', 'viewer', '--reason', REASON, '--apply']) == 0
    assert tuple(grant_row(case, user_id)) == ('viewer', True, 1)
    assert cli(case, monkeypatch, ['grant', '--user-id', user_id, '--role', 'admin', '--reason', REASON, '--apply']) == 0
    assert tuple(grant_row(case, user_id)) == ('admin', True, 2)
    rows = audit_rows(case)
    assert [(row.actor_kind, row.action, row.outcome, row.target_user_id) for row in rows] == [
        ('cli', 'admin.grant', 'succeeded', user_id)] * 2
    assert rows[0].reason == REASON and rows[0].changes['role'] == 'viewer' and rows[0].changes['by'].startswith('cli:')


def test_grant_unknown_user_exits_2(case, monkeypatch):
    assert cli(case, monkeypatch, ['grant', '--user-id', 'nobody', '--role', 'admin', '--reason', REASON, '--apply']) == 2


@pytest.mark.parametrize('reason', ['short', '   too short ', 'x' * 501])
def test_reason_length_enforced(case, monkeypatch, reason):
    user_id = make_user(case, grant=False)
    assert cli(case, monkeypatch, ['grant', '--user-id', user_id, '--role', 'admin', '--reason', reason, '--apply']) == 2
    assert grant_row(case, user_id) is None


def test_missing_connection_setting_exits_2(monkeypatch):
    from app import admin_grant
    monkeypatch.delenv('ADMIN_CLI_DB_URL', raising=False)
    assert admin_grant.main(['list']) == 2


def test_revoke_deactivates_and_ends_sessions(case, monkeypatch):
    user_id = make_user(case)
    run(case, "INSERT INTO app.adminsession (id,token_hash,user_id,created_at,expires_at) "
              "VALUES ('s1',repeat('a',64),:u,now(),now() + interval '15 minutes')", u=user_id)
    assert cli(case, monkeypatch, ['revoke', '--user-id', user_id, '--reason', REASON, '--apply']) == 0
    assert grant_row(case, user_id).active is False
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT revoked_at IS NOT NULL FROM app.adminsession WHERE id='s1'")) is True
    assert audit_rows(case)[-1].action == 'admin.revoke'


def test_runtime_role_cannot_grant(case, monkeypatch):
    user_id = make_user(case, grant=False)
    code = cli(case, monkeypatch, ['grant', '--user-id', user_id, '--role', 'admin', '--reason', REASON, '--apply'],
               engine='application')
    assert code != 0 and grant_row(case, user_id) is None


def test_list_prints_no_secrets(case, monkeypatch, capsys):
    user_id = make_user(case, 'listed@example.invalid')
    assert cli(case, monkeypatch, ['list']) == 0
    out = capsys.readouterr().out
    assert user_id in out and 'admin' in out
    assert 'pbkdf2' not in out and 'listed@example.invalid' not in out


def test_revoke_without_grant_refused_in_dry_run_and_apply(case, monkeypatch):
    user_id = make_user(case, grant=False)
    assert cli(case, monkeypatch, ['revoke', '--user-id', user_id, '--reason', REASON]) == 2
    assert cli(case, monkeypatch, ['revoke', '--user-id', user_id, '--reason', REASON, '--apply']) == 2


def test_revoke_of_inactive_grant_refused(case, monkeypatch):
    user_id = make_user(case, active=False)
    assert cli(case, monkeypatch, ['revoke', '--user-id', user_id, '--reason', REASON, '--apply']) == 2
    assert grant_row(case, user_id).revision == 1 and audit_rows(case) == []
