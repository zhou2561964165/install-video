"""C6a: recovery adopts a sealed candidate whose publish never reached the database (nonce-owned PG)."""
import os
import uuid

import pytest
from sqlalchemy import text

from test_pg_download_worker import job_row, media, run, worker  # noqa: F401  (fixtures/helpers)
from test_pg_job_repository import capacity, case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


@pytest.fixture
def recovery():
    from app.services import recovery
    return recovery


def sealed_unpublished(case, worker, media, submit, monkeypatch, key='k1'):
    """The worker sealed its candidate, the publish outcome stayed unknown, and its lease then expired."""
    from sqlalchemy.exc import OperationalError
    job = submit(key).job_id
    real = worker.publish_candidate

    def lost_connection(session, token, candidate, **kwargs):
        raise OperationalError('publish', {}, Exception('synthetic connection loss before commit'))
    monkeypatch.setattr(worker, 'publish_candidate', lost_connection)
    assert run(case, worker, media, 'fake:ok:1000') == 'lost'
    monkeypatch.setattr(worker, 'publish_candidate', real)
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    return job


def attempt_dir(case, media, job):
    with case.migration.connect() as connection:
        epoch, attempt = connection.execute(text(
            "SELECT epoch, id FROM app.jobattempt WHERE job_id=:j AND state='running'"), {'j': job}).one()
    return media / job / f'{epoch}-{attempt}'


def attempt_states(case, job):
    with case.migration.connect() as connection:
        return [tuple(row) for row in connection.execute(text(
            'SELECT state, error_code FROM app.jobattempt WHERE job_id=:j ORDER BY epoch'), {'j': job})]


def test_sealed_candidate_is_adopted_once(case, worker, media, submit, monkeypatch, recovery):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    directory = attempt_dir(case, media, job)
    assert recovery.adopt_expired(case.application, media)['adopted'] == 1
    state = job_row(case, job)
    assert (state.internal_state, state.status, state.media_state, state.visible_attempt_id) == (
        'succeeded', 'done', 'available', directory.name.split('-', 1)[1])
    assert capacity(case, job) == ('succeeded', True, 0, 0)
    assert attempt_states(case, job) == [('succeeded', None)]
    with case.migration.connect() as connection:
        lease = connection.execute(text('SELECT lease_owner, lease_deadline FROM app.job WHERE id=:j'), {'j': job}).one()
        assert tuple(lease) == (None, None)
        assert connection.scalar(text('SELECT count(*) FROM app.artifactmanifest WHERE job_id=:j'), {'j': job}) == 1
    assert recovery.adopt_expired(case.application, media)['adopted'] == 0  # nothing left to adopt


def test_adopted_media_is_readable(case, worker, media, submit, monkeypatch, recovery):
    from sqlmodel import Session
    from app.services import file_reads
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    recovery.adopt_expired(case.application, media)
    with Session(case.application) as session:
        opened = file_reads.open_read(session, 'c1-slot', job, media_root=media, height_limit=None)
    with opened.file as handle:
        assert len(handle.read()) == 1000


def test_hash_mismatch_goes_to_review_and_keeps_files(case, worker, media, submit, monkeypatch, recovery):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    directory = attempt_dir(case, media, job)
    final = directory / 'media.mp4'
    final.write_bytes(bytes((value + 1) % 256 for value in final.read_bytes()))  # same size, other content
    counts = recovery.adopt_expired(case.application, media)
    assert (counts['adopted'], counts['needs_review']) == (0, 1)
    state = job_row(case, job)
    assert (state.internal_state, state.status, state.error_type, state.media_state) == (
        'needs_review', 'error', 'recovery_candidate_invalid', None)
    assert capacity(case, job) == ('needs_review', True, 0, 0)
    assert attempt_states(case, job) == [('lost', 'recovery_candidate_invalid')]
    assert sorted(entry.name for entry in directory.iterdir()) == ['manifest.json', 'media.mp4']


def test_multiple_candidates_are_never_picked_automatically(case, worker, media, submit, monkeypatch, recovery):
    from app.services import artifact_store
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    other = artifact_store.prepare_attempt(media, job, 99, str(uuid.uuid4()))
    other.part.write_bytes(b'x' * 1000)
    artifact_store.seal_candidate(other, ext='mp4', max_bytes=4096, media_check='verified')
    counts = recovery.adopt_expired(case.application, media)
    assert (counts['adopted'], counts['needs_review']) == (0, 1)
    assert job_row(case, job).error_type == 'recovery_multiple_candidates'


def test_attempt_without_a_sealed_candidate_is_left_to_the_normal_retry(case, worker, media, submit, recovery):
    from sqlmodel import Session
    from app.services import artifact_store, job_repository
    job = submit('k1').job_id
    with Session(case.application) as session:
        token = job_repository.claim_next(session, 'w1')
        session.commit()
    paths = artifact_store.prepare_attempt(media, job, token.epoch, token.attempt_id)
    paths.part.write_bytes(b'partial')
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    assert recovery.adopt_expired(case.application, media) == dict(adopted=0, needs_review=0, storage_unavailable=0,
                                                                   fenceable=[job])
    assert job_row(case, job).internal_state == 'running'
    with Session(case.application) as session:
        assert job_repository.recover_expired(session, lease_fence=[job]) == [job]
        session.commit()
    assert job_row(case, job).internal_state == 'retry_wait'


def test_live_lease_is_never_adopted(case, worker, media, submit, monkeypatch, recovery):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    db(case, "UPDATE app.job SET lease_deadline = now() + interval '60 seconds' WHERE id=:j", j=job)
    assert recovery.adopt_expired(case.application, media)['adopted'] == 0
    assert job_row(case, job).internal_state == 'running'


def test_expired_run_window_is_never_adopted(case, worker, media, submit, monkeypatch, recovery):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    db(case, "UPDATE app.job SET run_deadline_at = now() - interval '1 second', "
             "created_at = now() - interval '1 hour' WHERE id=:j", j=job)
    assert recovery.adopt_expired(case.application, media)['adopted'] == 0
    assert job_row(case, job).internal_state == 'running'


def test_fenced_while_verifying_is_not_adopted(case, worker, media, submit, monkeypatch, recovery):
    from sqlmodel import Session
    from app.services import job_repository
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    real = recovery.artifact_store.read_sealed

    def fence_then_read(*args, **kwargs):
        with Session(case.application) as session:  # recover_expired wins the race
            assert job_repository.recover_expired(session) == [job]
            session.commit()
        return real(*args, **kwargs)
    monkeypatch.setattr(recovery.artifact_store, 'read_sealed', fence_then_read)
    assert recovery.adopt_expired(case.application, media)['adopted'] == 0
    assert job_row(case, job).internal_state == 'retry_wait'
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.artifactmanifest WHERE job_id=:j'), {'j': job}) == 0


# Review M3: nothing deletes an unfenced attempt's files, so media missing beside its manifest is damage.
def test_manifest_without_media_goes_to_review(case, worker, media, submit, monkeypatch, recovery):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    directory = attempt_dir(case, media, job)
    (directory / 'media.mp4').unlink()
    counts = recovery.adopt_expired(case.application, media)
    assert (counts['needs_review'], counts['fenceable']) == (1, [])
    assert job_row(case, job).error_type == 'recovery_candidate_invalid'
    assert (directory / 'manifest.json').exists()


def test_transient_read_error_is_neither_reviewed_nor_fenced(case, worker, media, submit, monkeypatch, recovery):
    from app.services import artifact_store
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)

    def transient(*args, **kwargs):
        raise artifact_store.ArtifactError('artifact_io_failed')
    monkeypatch.setattr(recovery.artifact_store, 'read_sealed', transient)
    assert recovery.adopt_expired(case.application, media) == dict(adopted=0, needs_review=0, storage_unavailable=0,
                                                                   fenceable=[])
    assert job_row(case, job).internal_state == 'running'


def test_storage_outage_changes_nothing(case, worker, media, submit, monkeypatch, recovery, tmp_path):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    unprovisioned = tmp_path / 'other'
    unprovisioned.mkdir()
    assert recovery.adopt_expired(case.application, unprovisioned.resolve())['storage_unavailable'] == 1
    assert job_row(case, job).internal_state == 'running'


def test_review_keeps_the_attempt_directory_from_the_orphan_scanner(case, worker, media, submit, monkeypatch,
                                                                    recovery):
    from app.services import orphans
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    directory = attempt_dir(case, media, job)
    final = directory / 'media.mp4'
    final.write_bytes(bytes((value + 1) % 256 for value in final.read_bytes()))
    recovery.adopt_expired(case.application, media)
    orphans.run_once(case.application, media)
    with case.migration.connect() as connection:
        listed = connection.scalars(text('SELECT relative_path FROM app.orphanobject')).all()
    assert not any(path.startswith(job) for path in listed)


# Worker wiring: a lease that merely expired (not fenced) keeps its sealed files for recovery.
def test_worker_keeps_an_unfenced_candidate_and_its_next_round_adopts_it(case, worker, media, submit, monkeypatch):
    job = submit('k1').job_id
    real = worker.publish_candidate

    def expire_then_publish(session, token, candidate, **kwargs):
        db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
        return real(session, token, candidate, **kwargs)
    monkeypatch.setattr(worker, 'publish_candidate', expire_then_publish)
    assert run(case, worker, media, 'fake:ok:1000') == 'lost'
    assert any((media / job).iterdir())  # not discarded: recovery decides
    monkeypatch.setattr(worker, 'publish_candidate', real)
    assert run(case, worker, media, 'fake:ok:1000') == 'idle'  # maintenance adopted it first
    assert job_row(case, job).internal_state == 'succeeded'



# The adopt/review writes guard on an expired lease themselves (not only the round's selection).
def test_adopt_and_review_refuse_a_live_lease(case, worker, media, submit, monkeypatch):
    from sqlmodel import Session
    from app.services import artifact_publish, artifact_store
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    directory = attempt_dir(case, media, job)
    epoch, attempt = directory.name.split('-', 1)
    candidate = artifact_store.read_sealed(media, job, int(epoch), attempt, max_bytes=4096)
    db(case, "UPDATE app.job SET lease_deadline = now() + interval '60 seconds' WHERE id=:j", j=job)
    with Session(case.application) as session:
        assert artifact_publish.adopt_candidate(session, candidate,
                                                absolute_path=str(media / candidate.relative_path)) is None
        assert artifact_publish.review_candidate(session, job, int(epoch), attempt, 'recovery_candidate_invalid') is False
        session.commit()
    assert job_row(case, job).internal_state == 'running'
    assert capacity(case, job)[0] == 'accepted_server'


# Review I2: the worker's maintenance never fences a lease the recovery round could not examine.
def test_maintenance_never_fences_during_a_storage_outage(case, worker, media, submit, monkeypatch, tmp_path):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    unprovisioned = tmp_path / 'other'
    unprovisioned.mkdir()
    worker._maintain(case.application, unprovisioned.resolve())
    assert job_row(case, job).internal_state == 'running'
    worker._maintain(case.application, media)  # storage back: the candidate is adopted, not re-downloaded
    assert job_row(case, job).internal_state == 'succeeded'


def test_maintenance_never_fences_a_transient_skip(case, worker, media, submit, monkeypatch, recovery):
    from app.services import artifact_store
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    real = recovery.artifact_store.read_sealed

    def transient(*args, **kwargs):
        raise artifact_store.ArtifactError('artifact_io_failed')
    monkeypatch.setattr(recovery.artifact_store, 'read_sealed', transient)
    worker._maintain(case.application, media)
    assert job_row(case, job).internal_state == 'running'
    monkeypatch.setattr(recovery.artifact_store, 'read_sealed', real)
    worker._maintain(case.application, media)
    assert job_row(case, job).internal_state == 'succeeded'


def test_maintenance_still_fails_an_expired_run_window(case, worker, media, submit, monkeypatch, tmp_path):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    db(case, "UPDATE app.job SET run_deadline_at = now() - interval '1 second', "
             "created_at = now() - interval '1 hour' WHERE id=:j", j=job)
    unprovisioned = tmp_path / 'other'
    unprovisioned.mkdir()
    worker._maintain(case.application, unprovisioned.resolve())
    assert job_row(case, job).internal_state == 'failed'


def test_maintenance_fences_an_examined_lease_without_a_candidate(case, worker, media, submit):
    from sqlmodel import Session
    from app.services import job_repository
    job = submit('k1').job_id
    with Session(case.application) as session:
        job_repository.claim_next(session, 'w1')
        session.commit()
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    worker._maintain(case.application, media)
    assert job_row(case, job).internal_state == 'retry_wait'


# Review I1: a worker that resumes after recovery sent its Job to review keeps the evidence.
def test_late_worker_keeps_files_of_a_job_in_review(case, worker, media, submit, monkeypatch, recovery):
    job = submit('k1').job_id
    real = worker.publish_candidate

    def stall_then_publish(session, token, candidate, **kwargs):
        db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
        final = media / candidate.relative_path
        final.write_bytes(bytes((value + 1) % 256 for value in final.read_bytes()))
        assert recovery.adopt_expired(case.application, media)['needs_review'] == 1
        return real(session, token, candidate, **kwargs)
    monkeypatch.setattr(worker, 'publish_candidate', stall_then_publish)
    assert run(case, worker, media, 'fake:ok:1000') == 'lost'
    assert job_row(case, job).internal_state == 'needs_review'
    directory = next((media / job).iterdir())
    assert sorted(entry.name for entry in directory.iterdir()) == ['manifest.json', 'media.mp4']


# Review M6: a worker that resumes after recovery adopted its candidate confirms it by identity.
def test_late_worker_confirms_an_adopted_candidate(case, worker, media, submit, monkeypatch, recovery):
    job = submit('k1').job_id
    real = worker.publish_candidate

    def stall_then_publish(session, token, candidate, **kwargs):
        db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
        assert recovery.adopt_expired(case.application, media)['adopted'] == 1
        return real(session, token, candidate, **kwargs)
    monkeypatch.setattr(worker, 'publish_candidate', stall_then_publish)
    assert run(case, worker, media, 'fake:ok:1000') == 'published'
    state = job_row(case, job)
    assert (state.internal_state, state.media_state) == ('succeeded', 'available')
    directory = next((media / job).iterdir())
    assert sorted(entry.name for entry in directory.iterdir()) == ['manifest.json', 'media.mp4']


def test_concurrent_recovery_adopts_once(case, worker, media, submit, monkeypatch, recovery):
    job = sealed_unpublished(case, worker, media, submit, monkeypatch)
    real = recovery.artifact_store.read_sealed
    inner = []

    def other_recovery_first(*args, **kwargs):
        if not inner:
            inner.append(None)  # mark first: the other round reads through this same patch
            inner[0] = recovery.adopt_expired(case.application, media)
        return real(*args, **kwargs)
    monkeypatch.setattr(recovery.artifact_store, 'read_sealed', other_recovery_first)
    assert recovery.adopt_expired(case.application, media)['adopted'] == 0
    assert inner[0]['adopted'] == 1
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.artifactmanifest WHERE job_id=:j'), {'j': job}) == 1
