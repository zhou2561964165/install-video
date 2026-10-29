"""C5a Task 2: cleanup lifecycle on nonce-owned PG with really published files; never pv_verify."""
import os

import pytest
from sqlalchemy import text
from sqlmodel import Session

from test_pg_download_worker import media, worker  # noqa: F401  (fixtures)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
OWNER = 'c1-slot'


@pytest.fixture
def cleanup():
    from app.services import cleanup_repository
    return cleanup_repository


@pytest.fixture
def published(case, worker, media, submit):
    job = submit('k1').job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:3000',
                           heartbeat_seconds=0.3, poll_seconds=0.02) == 'published'
    return job


def call(case, function, *args, **kwargs):
    with Session(case.application) as session:
        result = function(session, *args, **kwargs)
        session.commit()
    return result


def state(case, job):
    with case.migration.connect() as connection:
        return connection.execute(text(
            'SELECT j.media_state, j.file_path, i.state AS intent, i.epoch, i.attempts, i.owner, '
            'extract(epoch from i.next_run_at - now()) AS wait FROM app.job j '
            'LEFT JOIN app.cleanupintent i ON i.job_id = j.id WHERE j.id=:j'), {'j': job}).one()


def expire(case, job):
    db(case, "UPDATE app.job SET expires_at = now() - interval '1 second' WHERE id=:j", j=job)


def make_due(case, job):
    db(case, "UPDATE app.cleanupintent SET next_run_at = now() - interval '1 second' WHERE job_id=:j", j=job)


def test_mark_expired_only_after_expiry(case, cleanup, published):
    assert call(case, cleanup.mark_expired) == []
    expire(case, published)
    assert call(case, cleanup.mark_expired) == [published]
    assert state(case, published).media_state == 'expired'
    assert call(case, cleanup.mark_expired) == []


def test_live_read_lease_blocks_deletion(case, cleanup, media, published):
    from app.services import file_reads
    with Session(case.application) as session:
        opened = file_reads.open_read(session, OWNER, published, media_root=media, height_limit=None)
    opened.file.close()
    expire(case, published)
    call(case, cleanup.mark_expired)
    assert call(case, cleanup.claim_deletions, 'cl-1') == []  # a read is in flight: never unlink under it
    assert state(case, published).media_state == 'expired'
    with Session(case.application) as session:
        file_reads.end_read(session, opened.read_id)
        session.commit()
    [claim] = call(case, cleanup.claim_deletions, 'cl-1')
    assert (claim.job_id, claim.epoch) == (published, 1) and claim.relative_path.endswith('/media.mp4')
    row = state(case, published)
    assert (row.media_state, row.intent, row.owner) == ('deleting', 'pending', 'cl-1')


def test_lapsed_read_lease_does_not_block(case, cleanup, media, published):
    from app.services import file_reads
    with Session(case.application) as session:
        file_reads.open_read(session, OWNER, published, media_root=media, height_limit=None).file.close()
    db(case, "UPDATE app.filereadlease SET lease_deadline = now() - interval '1 second', "
             "max_until = now() - interval '1 second' WHERE job_id=:j", j=published)
    expire(case, published)
    call(case, cleanup.mark_expired)
    assert [claim.job_id for claim in call(case, cleanup.claim_deletions, 'cl-1')] == [published]


def test_job_held_by_a_reader_is_skipped_not_waited(case, cleanup, published):
    expire(case, published)
    call(case, cleanup.mark_expired)
    with case.application.connect() as reader:
        transaction = reader.begin()
        reader.execute(text('SELECT id FROM app.job WHERE id=:j FOR SHARE'), {'j': published})
        assert call(case, cleanup.claim_deletions, 'cl-1') == []
        # Proof by state, not wall clock: had the call waited on the reader's lock it would have raised
        # (lock_timeout 2 s). Returning normally with nothing selected means the Job was skipped.
        transaction.rollback()
    assert len(call(case, cleanup.claim_deletions, 'cl-1')) == 1


def test_confirm_marks_deleted_and_reads_are_gone(case, cleanup, media, published):
    from app.services import file_reads
    expire(case, published)
    call(case, cleanup.mark_expired)
    [claim] = call(case, cleanup.claim_deletions, 'cl-1')
    assert call(case, cleanup.confirm_deleted, claim) is True
    row = state(case, published)
    assert (row.media_state, row.file_path, row.intent, row.owner) == ('deleted', None, 'done', None)
    with Session(case.application) as session:
        with pytest.raises(file_reads.ReadDenied) as denied:
            file_reads.open_read(session, OWNER, published, media_root=media, height_limit=None)
    assert (denied.value.status, denied.value.error_type) == (410, 'file_expired')


def test_stale_claim_cannot_confirm_or_record(case, cleanup, published):
    expire(case, published)
    call(case, cleanup.mark_expired)
    [old] = call(case, cleanup.claim_deletions, 'cl-1')
    make_due(case, published)  # the first cleaner stalled past its claim; another takes over
    [new] = call(case, cleanup.claim_deletions, 'cl-2')
    assert new.epoch == old.epoch + 1
    assert call(case, cleanup.confirm_deleted, old) is False
    assert call(case, cleanup.record_failure, old, 'artifact_io_failed') == 'lost'
    assert call(case, cleanup.confirm_deleted, new) is True


def test_failures_back_off_then_need_review_never_available(case, cleanup, published):
    expire(case, published)
    call(case, cleanup.mark_expired)
    for expected_wait in (30, 120, 600, 1800):
        [claim] = call(case, cleanup.claim_deletions, 'cl-1')
        assert call(case, cleanup.record_failure, claim, 'artifact_io_failed') == 'retry'
        row = state(case, published)
        assert row.media_state == 'deleting' and row.owner is None and expected_wait - 5 <= row.wait <= expected_wait
        assert call(case, cleanup.claim_deletions, 'cl-1') == []  # backing off
        make_due(case, published)
    [claim] = call(case, cleanup.claim_deletions, 'cl-1')
    assert call(case, cleanup.record_failure, claim, 'artifact_io_failed') == 'needs_review'
    row = state(case, published)
    assert (row.media_state, row.intent, row.attempts) == ('deleting', 'needs_review', 5)
    make_due(case, published)
    assert call(case, cleanup.claim_deletions, 'cl-1') == []  # no automatic retry after needs_review


def test_unpublished_and_legacy_jobs_are_ignored(case, cleanup, submit):
    job = submit('k1').job_id  # queued v2 job: nothing published
    db(case, "UPDATE app.job SET expires_at = now() - interval '1 second' WHERE id=:j", j=job)
    db(case, "INSERT INTO app.job (id,url,status,progress,created_at,updated_at,execution_version,expires_at) "
             "VALUES ('legacy-v1','https://synthetic.invalid/v','done',100,now(),now(),1,now()-interval '1 day')")
    assert call(case, cleanup.mark_expired) == [] and call(case, cleanup.claim_deletions, 'cl-1') == []


# C5a review M3: a deleting Job without any intent (manual edit, partial restore) is still picked up.
def test_deleting_job_without_intent_is_claimable(case, cleanup, published):
    db(case, "UPDATE app.job SET media_state='deleting' WHERE id=:j", j=published)
    assert [claim.job_id for claim in call(case, cleanup.claim_deletions, 'cl-1')] == [published]


# C5a review M2: finished intents and broken rows never take batch slots or stall a round.
def test_finished_or_broken_jobs_do_not_block_the_batch(case, cleanup, worker, media, submit):
    jobs = []
    for key in ('k1', 'k2', 'k3'):
        jobs.append(submit(key).job_id)
        assert worker.run_once(case.application, media, 'w1', executor='fake:ok:100', heartbeat_seconds=0.3,
                               poll_seconds=0.02) == 'published'
    for offset, job in enumerate(jobs):  # oldest first: jobs[0], then jobs[1], then jobs[2]
        db(case, f"UPDATE app.job SET expires_at = now() - interval '{10 - offset} minutes' WHERE id=:j", j=job)
    call(case, cleanup.mark_expired)
    db(case, "INSERT INTO app.cleanupintent (job_id,attempt_id,relative_path,owner,epoch,state,attempts,next_run_at,"
             "created_at,updated_at) SELECT id, visible_attempt_id, 'x', NULL, 1, 'needs_review', 5, now(), now(), now() "
             "FROM app.job WHERE id=:j", j=jobs[0])
    db(case, 'DELETE FROM app.artifactmanifest WHERE job_id=:j', j=jobs[1])  # broken row: no manifest
    claims = call(case, cleanup.claim_deletions, 'cl-1', limit=1)
    assert [claim.job_id for claim in claims] == [jobs[2]]


@pytest.mark.parametrize('owner', ['', 'has space', 'x' * 65, None])
def test_owner_is_validated(case, cleanup, owner):
    with Session(case.application) as session:
        with pytest.raises(ValueError):
            cleanup.claim_deletions(session, owner)
