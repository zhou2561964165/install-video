"""C2 artifact schema on nonce-owned isolated PG only; never pv_verify."""
import os

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('c2-u','c2@synthetic.invalid','x',now())"
HASH = 'a' * 64


def job_sql(job_id='c2-j', **columns):
    values = {'id': f"'{job_id}'", 'url': "'https://synthetic.invalid/v'", 'status': "'queued'", 'progress': '0',
              'created_at': 'now()', 'updated_at': 'now()', 'user_id': "'c2-u'", 'execution_version': '2',
              'internal_state': "'queued'", 'run_deadline_at': "now()+interval '30 minutes'"}
    values.update(columns)
    return 'INSERT INTO app.job (' + ','.join(values) + ') VALUES (' + ','.join(values.values()) + ')'


def attempt_sql(attempt_id='c2-a', job_id='c2-j', **columns):
    values = {'id': f"'{attempt_id}'", 'job_id': f"'{job_id}'", 'epoch': '1', 'owner': "'w1'", 'attempt_index': '1',
              'state': "'succeeded'", 'started_at': 'now()', 'ended_at': 'now()'}
    values.update(columns)
    return 'INSERT INTO app.jobattempt (' + ','.join(values) + ') VALUES (' + ','.join(values.values()) + ')'


def manifest_sql(**columns):
    values = {'attempt_id': "'c2-a'", 'job_id': "'c2-j'", 'epoch': '1', 'relative_path': "'c2-j/1-c2-a/media.mp4'",
              'byte_size': '10', 'sha256': f"'{HASH}'", 'media_format': "'mp4'", 'media_check': "'verified'",
              'created_at': 'now()'}
    values.update(columns)
    return 'INSERT INTO app.artifactmanifest (' + ','.join(values) + ') VALUES (' + ','.join(values.values()) + ')'


SUCCEEDED = dict(internal_state="'succeeded'", status="'done'", visible_attempt_id="'c2-a'",
                 media_state="'available'", completed_at='now()')


def test_c2_head_chain():
    script = ScriptDirectory.from_config(db.migration_config())
    assert script.get_revision('c2_0006') is not None  # head moved on to c3_0007 (C3 Task 1)
    assert script.get_revision('c2_0006').down_revision == 'c1_0005'


def test_valid_published_rows_accepted_including_bigint_boundary():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c2_0006') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql()))
            connection.execute(text(attempt_sql()))
            connection.execute(text(manifest_sql(byte_size='2147483648')))
            connection.execute(text("UPDATE app.job SET internal_state='succeeded', status='done', "
                                    "visible_attempt_id='c2-a', media_state='available', completed_at=now() WHERE id='c2-j'"))
            assert connection.scalar(text('SELECT byte_size FROM app.artifactmanifest')) == 2147483648


BAD = {
    'zero-size': [manifest_sql(byte_size='0')],
    'short-hash': [manifest_sql(sha256="'abc'")],
    'non-hex-hash': [manifest_sql(sha256="'" + 'Z' * 64 + "'")],
    'unknown-check': [manifest_sql(media_check="'skipped'")],
    'duplicate-epoch': [manifest_sql(), attempt_sql('c2-b', epoch='2', attempt_index='2'),
                        manifest_sql(attempt_id="'c2-b'")],
    'succeeded-without-visible': ["UPDATE app.job SET internal_state='succeeded', media_state='available', "
                                  "completed_at=now() WHERE id='c2-j'"],
    'unknown-media-state': ["UPDATE app.job SET media_state='gone' WHERE id='c2-j'"],
    'visible-other-jobs-attempt': [job_sql('c2-other'), attempt_sql('c2-x', 'c2-other'),
                                   "UPDATE app.job SET visible_attempt_id='c2-x' WHERE id='c2-j'"],
}


@pytest.mark.parametrize('case_name', sorted(BAD))
def test_constraints_reject_inconsistent_rows(case_name):
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c2_0006') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql()))
            connection.execute(text(attempt_sql()))
        with pytest.raises(IntegrityError):
            with case.migration.begin() as connection:
                for statement in BAD[case_name]:
                    connection.execute(text(statement))


def test_runtime_role_privileges_on_artifactmanifest():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c2_0006') as case:
        with case.migration.connect() as connection:
            granted = {privilege: connection.scalar(text(
                "SELECT has_table_privilege('pv_app','app.artifactmanifest',:p)"), {'p': privilege})
                for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')}
    assert granted == {'SELECT': True, 'INSERT': True, 'UPDATE': False, 'DELETE': False, 'TRUNCATE': False}


def test_downgrade_refuses_manifests_then_allows_empty():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='c2_0006') as case:
        with case.migration.begin() as connection:
            connection.execute(text(USER))
            connection.execute(text(job_sql()))
            connection.execute(text(attempt_sql()))
            connection.execute(text(manifest_sql()))
        with pytest.raises(Exception):
            case.migrate(action='downgrade', target='c1_0005')
        with case.migration.begin() as connection:
            connection.execute(text('DELETE FROM app.artifactmanifest'))
        case.migrate(action='downgrade', target='c1_0005')
        with case.migration.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == 'c1_0005'
            assert connection.scalar(text("SELECT to_regclass('app.artifactmanifest')")) is None
