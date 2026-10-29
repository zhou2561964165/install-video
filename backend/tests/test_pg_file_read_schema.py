"""C4 Task 1 schema (c4_0008 file read leases) on nonce-owned isolated PG only; never pv_verify."""
import os

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('c4-u','c4@synthetic.invalid','x',now())"
JOB = ("INSERT INTO app.job (id,url,status,progress,created_at,updated_at,user_id,execution_version,internal_state,"
       "run_deadline_at) VALUES ('c4-j','https://synthetic.invalid/v','queued',0,now(),now(),'c4-u',2,'queued',"
       "now()+interval '30 minutes')")
ATTEMPT = ("INSERT INTO app.jobattempt (id,job_id,epoch,owner,attempt_index,state,started_at,ended_at) "
           "VALUES ('c4-a','c4-j',1,'w1',1,'failed',now(),now())")


def lease_sql(lease_id='c4-r', **columns):
    values = {'id': f"'{lease_id}'", 'job_id': "'c4-j'", 'attempt_id': "'c4-a'", 'started_at': 'now()',
              'lease_deadline': "now()+interval '30 seconds'", 'max_until': "now()+interval '30 minutes'"}
    values.update(columns)
    return 'INSERT INTO app.filereadlease (' + ','.join(values) + ') VALUES (' + ','.join(values.values()) + ')'


def seeded(case):
    with case.migration.begin() as connection:
        connection.execute(text(USER))
        connection.execute(text(JOB))
        connection.execute(text(ATTEMPT))


def test_c4_chain_follows_c3():
    script = ScriptDirectory.from_config(db.migration_config())
    assert script.get_revision('c4_0008').down_revision == 'c3_0007'
    assert 'c3_0007' not in script.get_heads()


def test_valid_lease_accepted_and_open_index_exists():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c4_0008') as case:
        seeded(case)
        with case.migration.begin() as connection:
            connection.execute(text(lease_sql()))
            connection.execute(text(lease_sql('c4-r2', ended_at='now()')))
            assert connection.scalar(text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='app' AND indexname='ix_filereadlease_open'"
            )).endswith('WHERE (ended_at IS NULL)')


@pytest.mark.parametrize('columns', [
    dict(lease_deadline="now()+interval '31 minutes'"),                          # beyond max_until
    dict(max_until="now()+interval '31 minutes'", lease_deadline='now()'),       # longer than 30 minutes
    dict(ended_at="now()-interval '1 hour'"),                                    # ends before it starts
    dict(job_id="'missing-job'"),                                                # FK
    dict(attempt_id="'missing-attempt'"),                                        # FK
])
def test_constraints_reject_invalid_leases(columns):
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c4_0008') as case:
        seeded(case)
        with pytest.raises(IntegrityError):
            with case.migration.begin() as connection:
                connection.execute(text(lease_sql(**columns)))


def test_runtime_role_privileges_on_filereadlease():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c4_0008') as case:
        with case.migration.connect() as connection:
            granted = {privilege for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
                       if connection.scalar(text("SELECT has_table_privilege('pv_app','app.filereadlease',:p)"),
                                            {'p': privilege})}
    assert granted == {'SELECT', 'INSERT', 'UPDATE'}  # deletion order belongs to C5


def test_downgrade_refuses_leases_then_allows_empty():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c4_0008') as case:
        seeded(case)
        with case.migration.begin() as connection:
            connection.execute(text(lease_sql()))
        with pytest.raises(Exception):
            case.migrate(action='downgrade', target='c3_0007')
        with case.migration.begin() as connection:
            connection.execute(text('DELETE FROM app.filereadlease'))
        case.migrate(action='downgrade', target='c3_0007')
        with case.migration.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == 'c3_0007'
            assert connection.scalar(text("SELECT to_regclass('app.filereadlease')")) is None


def test_lease_cannot_point_at_another_jobs_attempt():
    # C4 review minor 6: composite (job_id, attempt_id) -> jobattempt(job_id, id).
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c4_0008') as case:
        seeded(case)
        with case.migration.begin() as connection:
            connection.execute(text(JOB.replace("'c4-j'", "'c4-j2'")))
            connection.execute(text(ATTEMPT.replace("'c4-a'", "'c4-a2'").replace("'c4-j'", "'c4-j2'")))
        with pytest.raises(IntegrityError):
            with case.migration.begin() as connection:
                connection.execute(text(lease_sql(attempt_id="'c4-a2'")))
