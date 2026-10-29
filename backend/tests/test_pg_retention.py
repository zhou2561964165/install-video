"""C5b-1 Task 2: retention purge of durable Job metadata on nonce-owned PG; never pv_verify."""
import os

import pytest
from sqlalchemy import text
from sqlmodel import Session

from test_pg_cleanup_repository import call, expire  # noqa: F401  (helpers)
from test_pg_download_worker import media, worker  # noqa: F401  (fixtures)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


@pytest.fixture
def retention():
    from app.services import retention_repository
    return retention_repository


def publish(case, worker, media, submit, key='k1', executor='fake:ok:500'):
    job = submit(key).job_id
    worker.run_once(case.application, media, 'w1', executor=executor, heartbeat_seconds=0.3, poll_seconds=0.02)
    return job


def media_deleted(case, media, job):
    from app.services import cleaner
    expire(case, job)
    assert cleaner.run_once(case.application, media, 'cl-1')['deleted'] == 1


def age(case, job, days):
    db(case, f"UPDATE app.job SET created_at = now() - interval '{days} days' WHERE id=:j", j=job)
    db(case, "UPDATE app.downloadidempotency SET expires_at = extract(epoch from now()) - 1")  # receipts lapsed


def count(case, sql, **params):
    with case.migration.connect() as connection:
        return connection.scalar(text(sql), params)


def test_purges_metadata_in_order_and_keeps_charges_and_tombstone(case, retention, worker, media, submit):
    from app.services import file_reads
    job = publish(case, worker, media, submit)
    with Session(case.application) as session:  # a finished read leaves lease history behind
        opened = file_reads.open_read(session, 'c1-slot', job, media_root=media, height_limit=None)
    opened.file.close()
    with Session(case.application) as session:
        file_reads.end_read(session, opened.read_id)
        session.commit()
    media_deleted(case, media, job)
    age(case, job, 31)
    charges_before = count(case, 'SELECT count(*) FROM app.quotacharge')
    assert call(case, retention.purge_expired_metadata) == [job]
    for table in ('job', 'jobattempt', 'artifactmanifest', 'downloadaccess', 'filereadlease', 'cleanupintent'):
        column = 'id' if table == 'job' else 'job_id'
        assert count(case, f'SELECT count(*) FROM app.{table} WHERE {column}=:j', j=job) == 0, table
    operation = None
    with case.migration.connect() as connection:
        operation = connection.execute(text(
            'SELECT job_id, job_id_tombstone FROM app.downloadoperation WHERE job_id_tombstone=:j'), {'j': job}).one()
    assert (operation.job_id, operation.job_id_tombstone) == (None, job)
    assert count(case, 'SELECT count(*) FROM app.quotacharge') == charges_before  # charges are never deleted


def test_retention_boundary_is_thirty_days(case, retention, worker, media, submit):
    job = publish(case, worker, media, submit)
    media_deleted(case, media, job)
    age(case, job, 29)
    assert call(case, retention.purge_expired_metadata) == []
    age(case, job, 31)
    assert call(case, retention.purge_expired_metadata) == [job]


def test_never_published_failed_job_is_purged(case, retention, worker, media, submit):
    job = publish(case, worker, media, submit, executor='fake:error:http_412')
    age(case, job, 31)
    assert call(case, retention.purge_expired_metadata) == [job]


@pytest.mark.parametrize('protection', ['live_read', 'receipt', 'deleting', 'needs_review'])
def test_protected_jobs_are_kept(case, retention, worker, media, submit, protection):
    job = publish(case, worker, media, submit)
    if protection == 'live_read':
        from app.services import file_reads
        with Session(case.application) as session:
            file_reads.open_read(session, 'c1-slot', job, media_root=media, height_limit=None).file.close()
        db(case, "UPDATE app.job SET media_state='deleted', file_path=NULL WHERE id=:j", j=job)
        age(case, job, 31)
    else:
        media_deleted(case, media, job)
        age(case, job, 31)
        if protection == 'receipt':
            db(case, "UPDATE app.downloadidempotency SET expires_at = extract(epoch from now()) + 3600")
        else:
            db(case, "UPDATE app.job SET media_state='deleting' WHERE id=:j", j=job)
            state = 'pending' if protection == 'deleting' else 'needs_review'
            db(case, 'UPDATE app.cleanupintent SET state=:s WHERE job_id=:j', s=state, j=job)
    assert call(case, retention.purge_expired_metadata) == []
    assert count(case, 'SELECT count(*) FROM app.job WHERE id=:j', j=job) == 1


def test_legacy_and_unfinished_jobs_are_never_purged(case, retention, submit):
    queued = submit('k1').job_id
    db(case, "UPDATE app.job SET created_at = now() - interval '90 days' WHERE id=:j", j=queued)
    db(case, "INSERT INTO app.job (id,url,status,progress,created_at,updated_at,execution_version) "
             "VALUES ('legacy-v1','https://synthetic.invalid/v','done',100,now()-interval '90 days',now(),1)")
    assert call(case, retention.purge_expired_metadata) == []


def test_job_held_by_a_reader_is_skipped_not_waited(case, retention, worker, media, submit):
    job = publish(case, worker, media, submit)
    media_deleted(case, media, job)
    age(case, job, 31)
    with case.application.connect() as reader:
        transaction = reader.begin()
        reader.execute(text('SELECT id FROM app.job WHERE id=:j FOR SHARE'), {'j': job})
        assert call(case, retention.purge_expired_metadata) == []
        # Proof by state, not wall clock: had the call waited on the reader's lock it would have raised
        # (lock_timeout 2 s). Returning normally with nothing selected means the Job was skipped.
        transaction.rollback()
    assert call(case, retention.purge_expired_metadata) == [job]
