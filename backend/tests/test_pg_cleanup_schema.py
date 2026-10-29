"""C5a Task 1 schema (c5_0009 deletion intents) on nonce-owned isolated PG only; never pv_verify."""
import os

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('c5-u','c5@synthetic.invalid','x',now())"
JOB = ("INSERT INTO app.job (id,url,status,progress,created_at,updated_at,user_id,execution_version,internal_state,"
       "run_deadline_at) VALUES ('{job}','https://synthetic.invalid/v','queued',0,now(),now(),'c5-u',2,'queued',"
       "now()+interval '30 minutes')")
ATTEMPT = ("INSERT INTO app.jobattempt (id,job_id,epoch,owner,attempt_index,state,started_at,ended_at) "
           "VALUES ('{attempt}','{job}',1,'w1',1,'failed',now(),now())")


def intent_sql(**columns):
    values = {'job_id': "'c5-j'", 'attempt_id': "'c5-a'", 'relative_path': "'c5-j/1-c5-a/media.mp4'",
              'owner': "'cl-1'", 'epoch': '1', 'state': "'pending'", 'attempts': '0', 'next_run_at': 'now()',
              'created_at': 'now()', 'updated_at': 'now()'}
    values.update(columns)
    return 'INSERT INTO app.cleanupintent (' + ','.join(values) + ') VALUES (' + ','.join(values.values()) + ')'


def seeded(case, jobs=(('c5-j', 'c5-a'),)):
    with case.migration.begin() as connection:
        connection.execute(text(USER))
        for job, attempt in jobs:
            connection.execute(text(JOB.format(job=job)))
            connection.execute(text(ATTEMPT.format(job=job, attempt=attempt)))


def test_c5_chain_follows_c4():
    script = ScriptDirectory.from_config(db.migration_config())
    assert script.get_revision('c5_0009').down_revision == 'c4_0008'
    assert 'c4_0008' not in script.get_heads()


def test_valid_intents_and_scan_indexes():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5_0009') as case:
        seeded(case)
        with case.migration.begin() as connection:
            connection.execute(text(intent_sql()))
            indexes = dict(connection.execute(text(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='app' AND indexname IN "
                "('ix_cleanupintent_due','ix_job_cleanup_expiry','ix_job_cleanup_claim')")).all())
    assert indexes['ix_cleanupintent_due'].endswith("WHERE ((state)::text = 'pending'::text)")
    assert 'expires_at' in indexes['ix_job_cleanup_expiry'] and "'available'" in indexes['ix_job_cleanup_expiry']
    assert "'expired'" in indexes['ix_job_cleanup_claim'] and "'deleting'" in indexes['ix_job_cleanup_claim']


@pytest.mark.parametrize('columns', [
    dict(state="'available'"),                 # unknown state
    dict(attempts='6'),                        # beyond the 5-attempt budget
    dict(attempts='-1'),
    dict(epoch='-1'),
    dict(attempt_id="'c5-a2'"),                # an attempt of another Job (composite FK)
    dict(job_id="'missing'"),
])
def test_constraints_reject_invalid_intents(columns):
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5_0009') as case:
        seeded(case, jobs=(('c5-j', 'c5-a'), ('c5-j2', 'c5-a2')))
        with pytest.raises(IntegrityError):
            with case.migration.begin() as connection:
                connection.execute(text(intent_sql(**columns)))


def test_one_intent_per_job():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5_0009') as case:
        seeded(case)
        with case.migration.begin() as connection:
            connection.execute(text(intent_sql()))
        with pytest.raises(IntegrityError):
            with case.migration.begin() as connection:
                connection.execute(text(intent_sql()))


def test_runtime_role_privileges_on_cleanupintent():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5_0009') as case:
        with case.migration.connect() as connection:
            granted = {privilege for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
                       if connection.scalar(text("SELECT has_table_privilege('pv_app','app.cleanupintent',:p)"),
                                            {'p': privilege})}
    assert granted == {'SELECT', 'INSERT', 'UPDATE'}


def test_downgrade_refuses_intents_then_allows_empty():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5_0009') as case:
        seeded(case)
        with case.migration.begin() as connection:
            connection.execute(text(intent_sql()))
        with pytest.raises(Exception):
            case.migrate(action='downgrade', target='c4_0008')
        with case.migration.begin() as connection:
            connection.execute(text('DELETE FROM app.cleanupintent'))
        case.migrate(action='downgrade', target='c4_0008')
        with case.migration.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == 'c4_0008'
            assert connection.scalar(text("SELECT to_regclass('app.cleanupintent')")) is None
            assert connection.scalar(text("SELECT to_regclass('app.ix_job_cleanup_expiry')")) is None
            assert connection.scalar(text("SELECT to_regclass('app.ix_job_cleanup_claim')")) is None
