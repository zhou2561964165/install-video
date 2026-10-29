"""Admin M1 Task 1: m1_0014_admin — admin grant/session/account control/audit/login throttle (nonce-owned PG)."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from test_pg_job_repository import case, db  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('u1','u1@synthetic.invalid','x',now())"
TABLES = ('admingrant', 'adminsession', 'accountcontrol', 'adminaudit', 'adminloginthrottle')
EXPECTED = {
    'admingrant': {'SELECT'},
    'adminsession': {'SELECT', 'INSERT'},  # UPDATE only on revoked_at (column privilege)
    'accountcontrol': {'SELECT'},
    'adminaudit': {'SELECT', 'INSERT'},
    'adminloginthrottle': {'SELECT', 'INSERT', 'UPDATE', 'DELETE'},
}


def grant(case, user_id='u1', role='admin'):
    db(case, "INSERT INTO app.admingrant (user_id,role,active,revision,granted_at,granted_by,reason) "
             "VALUES (:u,:r,true,1,now(),'cli:test','initial grant for tests')", u=user_id, r=role)


def audit(connection, event_id='e1'):
    connection.execute(text("INSERT INTO app.adminaudit (event_id,actor_kind,action,outcome,request_id) "
                            "VALUES (:e,'system','auth.login','succeeded','r1')"), {'e': event_id})


def test_head_is_m1_0014():
    from alembic.script import ScriptDirectory
    from app import db as app_db
    script = ScriptDirectory.from_config(app_db.migration_config())
    assert script.get_revision('m1_0014').down_revision == 'b6_0013'
    assert script.get_revision('t1_0015').down_revision == 'm1_0014'  # head pinned by support schema test


def test_runtime_role_privileges(case):
    with case.migration.connect() as connection:
        for table, expected in EXPECTED.items():
            granted = {privilege for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
                       if connection.scalar(text("SELECT has_table_privilege('pv_app',:t,:p)"),
                                            {'t': 'app.' + table, 'p': privilege})}
            assert granted == expected, table


def test_audit_is_append_only(case):
    with case.application.begin() as connection:
        audit(connection)
    for statement in ("UPDATE app.adminaudit SET outcome='failed'", 'DELETE FROM app.adminaudit'):
        with pytest.raises(DBAPIError):
            with case.migration.begin() as connection:  # even the owner role cannot rewrite history
                connection.execute(text(statement))
    with case.application.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.adminaudit')) == 1


def test_role_check_and_foreign_key(case):
    db(case, USER)
    with pytest.raises(IntegrityError):
        grant(case, role='root')
    with pytest.raises(IntegrityError):
        grant(case, user_id='missing')
    grant(case)


def test_runtime_role_cannot_write_grants(case):
    db(case, USER)
    with pytest.raises(DBAPIError):
        with case.application.begin() as connection:
            connection.execute(text("INSERT INTO app.admingrant (user_id,role,active,revision,granted_at,granted_by,reason) "
                                    "VALUES ('u1','admin',true,1,now(),'web','self grant attempt')"))


def test_downgrade_refuses_when_admin_rows_exist_then_allows_empty(case):
    db(case, USER)
    grant(case)
    with pytest.raises(Exception):
        case.migrate(action='downgrade', target='b6_0013')
    db(case, 'DELETE FROM app.admingrant')
    case.migrate(action='downgrade', target='b6_0013')
    with case.migration.connect() as connection:
        for table in TABLES:
            assert connection.scalar(text('SELECT to_regclass(:t)'), {'t': 'app.' + table}) is None


def test_business_metadata_untouched():
    from sqlmodel import SQLModel
    import app.models  # noqa: F401
    import app.models_admin as admin_models
    assert not set(TABLES) & set(SQLModel.metadata.tables)
    assert set(TABLES) <= {table.name for table in admin_models.metadata.tables.values()}


def test_runtime_role_may_only_revoke_sessions(case):
    db(case, USER)
    db(case, "INSERT INTO app.adminsession (id,token_hash,user_id,created_at,expires_at) "
             "VALUES ('s1',repeat('a',64),'u1',now(),now() + interval '15 minutes')")
    with case.application.begin() as connection:
        connection.execute(text("UPDATE app.adminsession SET revoked_at=now() WHERE id='s1'"))
    for statement in ("UPDATE app.adminsession SET expires_at=now() + interval '1 day' WHERE id='s1'",
                      "UPDATE app.adminsession SET revoked_at=NULL, expires_at=now() + interval '1 day' WHERE id='s1'"):
        with pytest.raises(DBAPIError):
            with case.application.begin() as connection:
                connection.execute(text(statement))


def test_audit_time_is_the_database_clock(case):
    with case.application.begin() as connection:
        connection.execute(text("INSERT INTO app.adminaudit (event_id,recorded_at,actor_kind,action,outcome,request_id) "
                                "VALUES ('old','2000-01-01T00:00:00Z','system','auth.login','succeeded','r1')"))
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT recorded_at > now() - interval '1 hour' FROM app.adminaudit WHERE event_id='old'"))


def test_audit_rows_make_downgrade_refuse(case):
    with case.application.begin() as connection:
        audit(connection)
    with pytest.raises(Exception):
        case.migrate(action='downgrade', target='b6_0013')
