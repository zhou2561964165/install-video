"""C5b-1 review fixes: one-guard-at-a-time retention protections, fault isolation, tombstone 410 (nonce PG)."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session

from test_pg_cleanup_repository import call  # noqa: F401  (helpers)
from test_pg_download_worker import media, worker  # noqa: F401  (fixtures)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)
from test_pg_retention import age, count, media_deleted, publish, retention  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


def purge(case, retention, **kwargs):
    stats = {}
    with Session(case.application) as session:
        purged = retention.purge_expired_metadata(session, stats=stats, **kwargs)
        session.commit()
    return purged, stats


def ready(case, worker, media, submit, key='k1'):
    return ready_many(case, worker, media, submit, (key,))[0]


def ready_many(case, worker, media, submit, keys):
    # Delete every Job's media first and age them last: a cleaner round also purges, so aging one
    # Job before the next one's cleanup round would purge it early.
    jobs = [publish(case, worker, media, submit, key=key) for key in keys]
    for job in jobs:
        media_deleted(case, media, job)
    for job in jobs:
        age(case, job, 31)
    return jobs


# Review I1: a database error on one Job is isolated: counted, logged, the batch continues.
def test_db_error_on_one_job_does_not_abort_the_batch(case, retention, worker, media, submit, monkeypatch):
    first, second = ready_many(case, worker, media, submit, ('k1', 'k2'))
    db(case, "UPDATE app.job SET created_at = now() - interval '40 days' WHERE id=:j", j=first)  # oldest first
    real = retention._purge_one

    def failing(session, job_id):
        if job_id == first:
            raise OperationalError('purge', {}, Exception('synthetic lock timeout'))
        return real(session, job_id)
    monkeypatch.setattr(retention, '_purge_one', failing)
    purged, stats = purge(case, retention)
    assert purged == [second] and stats['failed'] == 1
    assert count(case, 'SELECT count(*) FROM app.job WHERE id=:j', j=first) == 1  # intact for the next run


# Review I2: a Job whose operation tombstone names another Job is never selected, and is reported.
def test_tombstone_mismatch_is_excluded_and_reported(case, retention, worker, media, submit):
    job = ready(case, worker, media, submit)
    db(case, "UPDATE app.downloadoperation SET job_id_tombstone='another-job' WHERE job_id=:j", j=job)
    purged, stats = purge(case, retention)
    assert purged == [] and stats['mismatched'] == 1
    assert count(case, 'SELECT count(*) FROM app.jobattempt WHERE job_id=:j', j=job) >= 1  # nothing deleted


def test_null_tombstone_is_backfilled(case, retention, worker, media, submit):
    job = ready(case, worker, media, submit)
    db(case, 'UPDATE app.downloadoperation SET job_id_tombstone=NULL WHERE job_id=:j', j=job)
    assert purge(case, retention)[0] == [job]
    assert count(case, 'SELECT count(*) FROM app.downloadoperation WHERE job_id_tombstone=:j', j=job) == 1


# Review I4: each protection holds on its own.
def test_needs_review_job_is_kept(case, retention, worker, media, submit):
    job = publish(case, worker, media, submit, executor='fake:error:session_expired')
    age(case, job, 31)
    assert count(case, "SELECT count(*) FROM app.job WHERE id=:j AND internal_state='needs_review'", j=job) == 1
    assert purge(case, retention)[0] == []


def test_unfinished_intent_alone_protects(case, retention, worker, media, submit):
    job = ready(case, worker, media, submit)
    db(case, "UPDATE app.cleanupintent SET state='pending' WHERE job_id=:j", j=job)  # media itself is deleted
    assert purge(case, retention)[0] == []


def test_active_operation_alone_protects(case, retention, worker, media, submit):
    job = ready(case, worker, media, submit)
    db(case, "UPDATE app.downloadoperation SET state='accepted_server', completed_at=NULL WHERE job_id=:j", j=job)
    assert purge(case, retention)[0] == []


def test_another_jobs_live_receipt_does_not_block(case, retention, worker, media, submit):
    first, second = ready_many(case, worker, media, submit, ('k1', 'k2'))
    db(case, "UPDATE app.downloadidempotency SET expires_at = extract(epoch from now()) + 3600 "
             "WHERE operation_id = (SELECT id FROM app.downloadoperation WHERE job_id=:j)", j=second)
    assert purge(case, retention)[0] == [first]


def test_multiple_attempts_are_all_removed(case, retention, worker, media, submit):
    job = submit('k1').job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:partial:100:http_5xx',
                           heartbeat_seconds=0.3, poll_seconds=0.02) == 'retry_wait'
    db(case, "UPDATE app.job SET next_run_at = now() - interval '1 second' WHERE id=:j", j=job)
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:100', heartbeat_seconds=0.3,
                           poll_seconds=0.02) == 'published'
    media_deleted(case, media, job)
    age(case, job, 31)
    assert purge(case, retention)[0] == [job]
    assert count(case, 'SELECT count(*) FROM app.jobattempt WHERE job_id=:j', j=job) == 0


def test_receipts_reservations_and_charges_are_untouched(case, retention, worker, media, submit):
    job = ready(case, worker, media, submit)
    tables = ('downloadidempotency', 'resourcereservation', 'quotacharge', 'downloadoperation')
    before = {table: count(case, f'SELECT count(*) FROM app.{table}') for table in tables}
    assert purge(case, retention)[0] == [job]
    assert {table: count(case, f'SELECT count(*) FROM app.{table}') for table in tables} == before


def test_batch_limit_is_respected(case, retention, worker, media, submit):
    jobs = ready_many(case, worker, media, submit, ('k1', 'k2', 'k3'))
    assert len(purge(case, retention, limit=2)[0]) == 2
    assert len(purge(case, retention, limit=2)[0]) == 1
    assert count(case, 'SELECT count(*) FROM app.job WHERE id = ANY(:ids)', ids=jobs) == 0


# Review M1: the relaxation drops only the visible attempt; a succeeded Job still needs completed_at.
def test_succeeded_deleted_job_still_needs_completed_at(case):
    with pytest.raises(IntegrityError):
        db(case, "INSERT INTO app.job (id,url,status,progress,created_at,updated_at,execution_version,internal_state,"
                 "run_deadline_at,media_state) VALUES ('r-no-completion','https://synthetic.invalid/v','done',100,"
                 "now(),now(),2,'succeeded',now()+interval '30 minutes','deleted')")


# Review I3: after the purge the owner's old link answers 410 (tombstone); anyone else still gets 404.
def test_tombstoned_job_is_gone_for_its_owner_only(case, retention, worker, media, submit):
    from app.services import file_reads
    job = ready(case, worker, media, submit)
    assert purge(case, retention)[0] == [job]
    with Session(case.application) as session:
        with pytest.raises(file_reads.ReadDenied) as owner:
            file_reads.open_read(session, 'c1-slot', job, media_root=media, height_limit=None)
    with Session(case.application) as session:
        with pytest.raises(file_reads.ReadDenied) as stranger:
            file_reads.open_read(session, 'someone-else', job, media_root=media, height_limit=None)
    assert (owner.value.status, owner.value.error_type) == (410, 'file_expired')
    assert (stranger.value.status, stranger.value.error_type) == (404, 'file_missing')
