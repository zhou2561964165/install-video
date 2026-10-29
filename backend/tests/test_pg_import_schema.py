"""B6 E3 T1: b6_0013_import — data-import ledger and job.legacy_check (nonce-owned PG)."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from test_pg_job_repository import case, db  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')

USER = "INSERT INTO app.\"user\" (id,email,password_hash,created_at) VALUES ('u1','u1@synthetic.invalid','x',now())"


def job(case, job_id='j1', **values):
    columns = dict(id=job_id, url='https://source.synthetic.invalid/v', status='done', progress=100.0,
                   created_at='2026-01-01T00:00:00+00', updated_at='2026-01-01T00:00:00+00', user_id='u1') | values
    names = ','.join(columns)
    params = ','.join(':' + name for name in columns)
    db(case, f'INSERT INTO app.job ({names}) VALUES ({params})', **columns)


def ledger(case, sha='a' * 64):
    db(case, "INSERT INTO app.dataimport (manifest_sha256,export_id,schema_profile,schema_fingerprint,snapshot_method,"
             "target_head,table_rows,transforms,completed_at) VALUES (:s,'e' || repeat('0',31),'legacy_sqlite9_v1',:f,"
             "'sqlite_readonly_snapshot_v1','b6_0013','{}','{}',now())", s=sha, f='f' * 64)


def test_chain_and_head():
    from alembic.script import ScriptDirectory
    from app import db as app_db
    script = ScriptDirectory.from_config(app_db.migration_config())
    assert script.get_revision('b6_0013').down_revision == 'b5_0012'
    assert script.get_revision('m1_0014').down_revision == 'b6_0013'  # admin M1 follows; head pinned there


def test_legacy_check_values_only_on_v1_jobs(case):
    db(case, USER)
    for index, value in enumerate(('verified', 'missing', 'mismatch', 'unchecked')):
        job(case, f'v1-{index}', legacy_check=value)
    with pytest.raises(IntegrityError):
        job(case, 'bad-value', legacy_check='ok')


def test_legacy_check_refused_on_v2_jobs(case):
    db(case, USER)
    with pytest.raises(IntegrityError):
        job(case, 'v2', execution_version=2, internal_state='queued', run_deadline_at='2026-01-01T00:30:00+00',
            status='queued', progress=0.0, legacy_check='verified')


def test_ledger_constraints_and_runtime_has_no_access(case):
    ledger(case)
    with pytest.raises(IntegrityError):
        ledger(case)  # one import per manifest
    with pytest.raises(IntegrityError):
        ledger(case, sha='not-a-hash')
    with case.migration.connect() as connection:
        granted = [privilege for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
                   if connection.scalar(text("SELECT has_table_privilege('pv_app','app.dataimport',:p)"),
                                        {'p': privilege})]
    assert granted == []


def test_downgrade_refuses_imported_data_then_allows_empty(case):
    db(case, USER)
    job(case, 'v1', legacy_check='verified')
    with pytest.raises(Exception):
        case.migrate(action='downgrade', target='b5_0012')
    db(case, 'UPDATE app.job SET legacy_check=NULL')
    ledger(case)
    with pytest.raises(Exception):
        case.migrate(action='downgrade', target='b5_0012')
    db(case, 'DELETE FROM app.dataimport')
    case.migrate(action='downgrade', target='b5_0012')
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('app.dataimport')")) is None
        assert connection.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='app' "
                                      "AND table_name='job' AND column_name='legacy_check'")) == 0
