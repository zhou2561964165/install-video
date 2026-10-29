"""C5b-1 Task 1 schema (c5b_0010 retention) on nonce-owned isolated PG only; never pv_verify."""
import os

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('r-u','r@synthetic.invalid','x',now())"


def job_sql(job_id, media_state):
    return ("INSERT INTO app.job (id,url,status,progress,created_at,updated_at,user_id,execution_version,internal_state,"
            "run_deadline_at,media_state,completed_at) VALUES "
            f"('{job_id}','https://synthetic.invalid/v','done',100,now(),now(),'r-u',2,'succeeded',"
            f"now()+interval '30 minutes','{media_state}',now())")


def test_retention_follows_cleanup():
    script = ScriptDirectory.from_config(db.migration_config())
    assert script.get_revision('c5b_0010').down_revision == 'c5_0009'
    assert 'c5_0009' not in script.get_heads()


def test_deleted_media_may_drop_its_visible_attempt_but_nothing_else_may():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5b_0010') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql('r-deleted', 'deleted')))  # media gone: reference may be cleared
        with pytest.raises(IntegrityError):
            with case.migration.begin() as connection:
                connection.execute(text(job_sql('r-available', 'available')))  # still served: must stay visible


TABLES = ('filereadlease', 'cleanupintent', 'artifactmanifest', 'downloadaccess', 'jobattempt', 'job',
          'downloadoperation', 'quotacharge', 'downloadidempotency', 'resourcereservation', 'billingfact',
          'billingpayment', 'billingcheckout', 'billinginbox', 'membership', 'user')


def delete_privileges(case):
    with case.migration.connect() as connection:
        return {table for table in TABLES
                if connection.scalar(text("SELECT has_table_privilege('pv_app', :t, 'DELETE')"), {'t': f'app."{table}"'})}


def test_retention_grants_delete_only_on_its_tables_and_downgrade_restores():
    from b3b_pg_helpers import isolated_database
    retention = {'filereadlease', 'cleanupintent', 'artifactmanifest', 'downloadaccess', 'jobattempt', 'job'}
    with isolated_database(target='c5_0009') as case:
        before = delete_privileges(case)
        case.migrate(action='upgrade', target='c5b_0010')
        after = delete_privileges(case)
        assert retention <= after
        assert after - before <= retention and before <= after  # nothing else gained or lost DELETE
        assert after - retention == before - retention          # operations/charges/receipts/billing unchanged
        case.migrate(action='downgrade', target='c5_0009')
        assert delete_privileges(case) == before                 # downgrade restores the earlier grants


def test_full_read_lease_index_for_restrict_checks():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5b_0010') as case:
        with case.migration.connect() as connection:
            indexdef = connection.scalar(text(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='app' AND indexname='ix_filereadlease_job_id'"))
    assert indexdef is not None and 'WHERE' not in indexdef


def test_downgrade_refuses_while_a_succeeded_job_lacks_its_visible_attempt():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c5b_0010') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql('r-deleted', 'deleted')))
        with pytest.raises(Exception):  # the restored strict check would no longer hold
            case.migrate(action='downgrade', target='c5_0009')
        with case.migration.begin() as connection:
            connection.execute(text("DELETE FROM app.job WHERE id='r-deleted'"))
        case.migrate(action='downgrade', target='c5_0009')
        with case.migration.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == 'c5_0009'
            assert connection.scalar(text("SELECT has_table_privilege('pv_app','app.jobattempt','DELETE')")) is False
