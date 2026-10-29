"""C3 Task 1 schema (c3_0007 source byte budget) on nonce-owned isolated PG only; never pv_verify."""
import os

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app import db

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('c3-u','c3@synthetic.invalid','x',now())"
JOB = ("INSERT INTO app.job (id,url,status,progress,created_at,updated_at,user_id,execution_version,internal_state,"
       "run_deadline_at) VALUES ('c3-j','https://synthetic.invalid/v','queued',0,now(),now(),'c3-u',2,'queued',"
       "now()+interval '30 minutes')")
ATTEMPT = ("INSERT INTO app.jobattempt (id,job_id,epoch,owner,attempt_index,state,started_at,ended_at) "
           "VALUES ('c3-a','c3-j',1,'w1',1,'failed',now(),now())")


def test_c3_chain_follows_c2():
    script = ScriptDirectory.from_config(db.migration_config())
    assert script.get_revision('c3_0007').down_revision == 'c2_0006'
    assert 'c2_0006' not in script.get_heads()


def test_counters_default_to_zero_and_are_bigint():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c3_0007') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(JOB))
            connection.execute(text(ATTEMPT))
            assert connection.scalar(text("SELECT source_bytes_used FROM app.job WHERE id='c3-j'")) == 0
            assert connection.scalar(text("SELECT bytes_used FROM app.jobattempt WHERE id='c3-a'")) == 0
            connection.execute(text("UPDATE app.job SET source_bytes_used = 6442450944 WHERE id='c3-j'"))
            types = dict(connection.execute(text(
                "SELECT table_name, data_type FROM information_schema.columns WHERE table_schema='app' AND "
                "((table_name='job' AND column_name='source_bytes_used') OR "
                "(table_name='jobattempt' AND column_name='bytes_used'))")).all())
    assert types == {'job': 'bigint', 'jobattempt': 'bigint'}


def test_downgrade_refuses_recorded_bytes_then_allows_zero():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c3_0007') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(JOB))
            connection.execute(text(ATTEMPT))
            connection.execute(text("UPDATE app.jobattempt SET bytes_used = 5 WHERE id='c3-a'"))
        with pytest.raises(Exception):  # dropping a recorded budget would silently reset it
            case.migrate(action='downgrade', target='c2_0006')
        with case.migration.begin() as connection:
            connection.execute(text("UPDATE app.jobattempt SET bytes_used = 0 WHERE id='c3-a'"))
        case.migrate(action='downgrade', target='c2_0006')
        with case.migration.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == 'c2_0006'
            assert connection.scalar(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema='app' AND "
                "column_name IN ('source_bytes_used','bytes_used')")) == 0
