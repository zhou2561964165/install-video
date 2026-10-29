"""C1 execution schema on nonce-owned isolated PG only; never pv_verify."""
import os

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('c1-u','c1@synthetic.invalid','x',now())"


def job_sql(job_id='c1-j', **columns):
    values = {'id': f"'{job_id}'", 'url': "'https://synthetic.invalid/v'", 'status': "'queued'", 'progress': '0',
              'created_at': 'now()', 'updated_at': 'now()', 'user_id': "'c1-u'"}
    values.update(columns)
    return 'INSERT INTO app.job (' + ','.join(values) + ') VALUES (' + ','.join(values.values()) + ')'


def attempt_sql(**columns):
    values = {'id': "'c1-a'", 'job_id': "'c1-j'", 'epoch': '1', 'owner': "'w1'", 'attempt_index': '1',
              'state': "'running'", 'started_at': 'now()'}
    values.update(columns)
    return 'INSERT INTO app.jobattempt (' + ','.join(values) + ') VALUES (' + ','.join(values.values()) + ')'


V2 = dict(execution_version='2', internal_state="'queued'", run_deadline_at="now()+interval '30 minutes'")


def test_c1_head_chain():
    script = ScriptDirectory.from_config(db.migration_config())
    # c1_0005 stays the single successor of b3b_0004; later stages extend the chain.
    assert script.get_revision('c1_0005').down_revision == 'b3b_0004'
    assert len(script.get_heads()) == 1


def test_upgrade_keeps_existing_jobs_v1():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='b3b_0004') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql()))
        case.migrate(target='c1_0005')
        with case.migration.connect() as connection:
            row = connection.execute(text("SELECT execution_version, internal_state, epoch, attempts_used, "
                                          "attempts_limit, lease_owner, visible_attempt_id FROM app.job WHERE id='c1-j'")).one()
    assert tuple(row) == (1, None, 0, 0, 3, None, None)


BAD = {
    'lease-pair': [job_sql(lease_owner="'w1'")],
    'v2-without-state': [job_sql(execution_version='2', run_deadline_at='now()')],
    'v2-without-deadline': [job_sql(execution_version='2', internal_state="'queued'")],
    'unknown-state': [job_sql(**{**V2, 'internal_state': "'paused'"})],
    'used-over-limit': [job_sql(attempts_used='4')],
    'limit-over-three': [job_sql(attempts_limit='4')],
    'retry-without-time': [job_sql(**{**V2, 'internal_state': "'retry_wait'"})],
    'attempt-index-four': [job_sql(**V2), attempt_sql(attempt_index='4')],
    'running-with-end': [job_sql(**V2), attempt_sql(ended_at='now()')],
    'ended-not-running-without-end': [job_sql(**V2), attempt_sql(state="'failed'")],
    'duplicate-epoch': [job_sql(**V2), attempt_sql(), attempt_sql(id="'c1-b'", attempt_index='2')],
    'v2-running-without-lease': [job_sql(**{**V2, 'internal_state': "'running'"})],
    'v2-queued-with-lease': [job_sql(**V2, lease_owner="'w1'", lease_deadline="now()")],
    'v1-with-execution-state': [job_sql(internal_state="'queued'")],
    'two-running-attempts': [job_sql(**V2), attempt_sql(), attempt_sql(id="'c1-b'", epoch='2', attempt_index='2')],
}


@pytest.mark.parametrize('case_name', sorted(BAD))
def test_constraints_reject_inconsistent_rows(case_name):
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c1_0005') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
        with pytest.raises(IntegrityError):
            with case.migration.begin() as connection:
                for statement in BAD[case_name]:
                    connection.execute(text(statement))


def test_valid_v2_job_and_attempt_accepted():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c1_0005') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql(**V2)))
            connection.execute(text(attempt_sql()))
            connection.execute(text("UPDATE app.job SET visible_attempt_id='c1-a' WHERE id='c1-j'"))


def test_runtime_role_privileges_on_jobattempt():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c1_0005') as case:
        with case.migration.connect() as connection:
            granted = {privilege: connection.scalar(text("SELECT has_table_privilege('pv_app','app.jobattempt',:p)"),
                                                    {'p': privilege})
                       for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')}
    assert granted == {'SELECT': True, 'INSERT': True, 'UPDATE': True, 'DELETE': False, 'TRUNCATE': False}


def test_downgrade_refuses_business_rows_then_allows_empty():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c1_0005') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql(**V2)))
            connection.execute(text(attempt_sql()))
        with pytest.raises(Exception):
            case.migrate(action='downgrade', target='b3b_0004')
        with case.migration.begin() as connection:
            connection.execute(text("DELETE FROM app.jobattempt"))
            connection.execute(text("DELETE FROM app.job"))
        case.migrate(action='downgrade', target='b3b_0004')
        with case.migration.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == 'b3b_0004'
            assert connection.scalar(text("SELECT to_regclass('app.jobattempt')")) is None


def test_model_metadata_matches_current_head():
    # Replaces B1's pv_verify-based compare: full model metadata vs the current head, nonce DB only.
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import inspect
    from sqlmodel import SQLModel
    import app.models  # noqa: F401  (registers every table)
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='head') as case:
        with case.migration.connect() as connection:
            # Admin M1 tables live on their own MetaData (app.models_admin), checked by test_pg_admin_schema.
            admin_tables = {'admingrant', 'adminsession', 'accountcontrol', 'adminaudit', 'adminloginthrottle'}
            context = MigrationContext.configure(connection, opts={
                'include_schemas': False,
                'include_object': lambda obj, name, type_, reflected, compare_to: not (type_ == 'table' and name in admin_tables)})
            connection.exec_driver_sql('SET search_path=app')
            assert set(inspect(connection).get_table_names(schema='app')) == (
                set(SQLModel.metadata.tables) | {'alembic_version'} | admin_tables)
            assert compare_metadata(context, SQLModel.metadata) == []


def test_job_checks_portable_to_older_sqlite():
    # SQLite < 3.39 (e.g. Ubuntu 22.04's 3.37.2) has no IS DISTINCT FROM; create_all must still work there.
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateTable
    from app.models import Job
    from app.models_execution import JobAttempt
    for table in (Job.__table__, JobAttempt.__table__):
        assert 'IS DISTINCT FROM' not in str(CreateTable(table).compile(dialect=sqlite.dialect())).upper()
