"""C2 Task 3: lease-fenced publish on nonce-owned isolated PG (current head); never pv_verify."""
import os
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.services.artifact_store import ArtifactCandidate
from test_pg_job_repository import capacity, case, claim, db, repo, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
HASH = 'ab' * 32


@pytest.fixture
def publish():
    from app.services import artifact_publish
    return artifact_publish


def candidate(token, **changes):
    values = dict(job_id=token.job_id, epoch=token.epoch, attempt_id=token.attempt_id,
                  relative_path=f'{token.job_id}/{token.epoch}-{token.attempt_id}/media.mp4',
                  byte_size=1000, sha256=HASH, media_format='mp4', media_check='verified')
    values.update(changes)
    return ArtifactCandidate(**values)


def do_publish(case, publish, token, made=None):
    with Session(case.application) as session:
        result = publish.publish_candidate(session, token, made or candidate(token), absolute_path='/media/abs/media.mp4')
        session.commit()
    return result


def job_row(case, job_id):
    with case.migration.connect() as connection:
        return connection.execute(text(
            'SELECT internal_state, status, visible_attempt_id, media_state, file_size, file_path, lease_owner, '
            'completed_at IS NOT NULL AS done, extract(epoch from expires_at - now()) AS ttl, epoch '
            'FROM app.job WHERE id=:j'), {'j': job_id}).one()


def test_publish_commits_all_facts_in_one_transaction(case, repo, submit, publish):
    job = submit('k1').job_id
    token = claim(case, repo)
    result = do_publish(case, publish, token)
    assert result.job_id == job and result.attempt_id == token.attempt_id and result.byte_size == 1000
    row = job_row(case, job)
    assert (row.internal_state, row.status, row.visible_attempt_id, row.media_state) == (
        'succeeded', 'done', token.attempt_id, 'available')
    assert (row.file_size, row.file_path, row.lease_owner, row.done) == (1000, '/media/abs/media.mp4', None, True)
    assert 3590 <= row.ttl <= 3600
    with case.migration.connect() as connection:
        manifest = connection.execute(text('SELECT job_id, epoch, relative_path, byte_size, sha256 FROM app.artifactmanifest')).one()
        attempt = connection.execute(text('SELECT state, ended_at IS NOT NULL FROM app.jobattempt WHERE id=:a'),
                                     {'a': token.attempt_id}).one()
    assert tuple(manifest) == (job, token.epoch, candidate(token).relative_path, 1000, HASH)
    assert tuple(attempt) == ('succeeded', True)
    assert capacity(case, job) == ('succeeded', True, 0, 0)


def test_stale_token_publish_is_lease_lost_and_writes_nothing(case, repo, submit, publish):
    job = submit('k1').job_id
    old = claim(case, repo, 'w1')
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    with Session(case.application) as session:
        repo.recover_expired(session)
        session.commit()
    new = claim(case, repo, 'w1')
    assert do_publish(case, publish, old) is publish.LEASE_LOST
    row = job_row(case, job)
    assert (row.internal_state, row.visible_attempt_id, row.epoch) == ('running', None, new.epoch)
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.artifactmanifest')) == 0
    assert capacity(case, job) == ('accepted_server', False, 2, 1)


def test_republish_and_unknown_commit_lookup(case, repo, submit, publish):
    job = submit('k1').job_id
    token = claim(case, repo)
    with Session(case.application) as session:
        assert publish.find_published(session, job, token.epoch, token.attempt_id) is None
    first = do_publish(case, publish, token)
    # C2 review I1: a retry after a lost commit acknowledgement is an idempotent success, so the
    # worker never treats its already-visible files as a lease loss and deletes them.
    assert do_publish(case, publish, token) == first
    with Session(case.application) as session:
        assert publish.find_published(session, job, token.epoch, token.attempt_id) == first
    assert capacity(case, job) == ('succeeded', True, 0, 0)  # released exactly once, never below zero


@pytest.mark.parametrize('field', ['sha256', 'byte_size', 'media_format'])
def test_republish_with_different_candidate_is_lease_lost(case, repo, submit, publish, field):
    job = submit('k1').job_id
    token = claim(case, repo)
    first = do_publish(case, publish, token)
    changes = {'sha256': dict(sha256='cd' * 32), 'byte_size': dict(byte_size=999),
               'media_format': dict(media_format='mkv',
                                    relative_path=f'{token.job_id}/{token.epoch}-{token.attempt_id}/media.mkv')}[field]
    assert do_publish(case, publish, token, candidate(token, **changes)) is publish.LEASE_LOST
    with Session(case.application) as session:
        assert publish.find_published(session, job, token.epoch, token.attempt_id) == first
    assert capacity(case, job) == ('succeeded', True, 0, 0)


def test_find_published_waits_for_in_flight_publish(case, repo, submit, publish):
    # C2 review I2: an unknown-outcome lookup must not answer "not published" while the
    # publishing transaction still holds the Job; it waits for that commit and then sees it.
    import threading
    job = submit('k1').job_id
    token = claim(case, repo)
    seen = {}
    with Session(case.application) as writer:
        made = publish.publish_candidate(writer, token, candidate(token), absolute_path='/media/abs/media.mp4')

        def lookup():
            with Session(case.application) as reader:
                seen['result'] = publish.find_published(reader, job, token.epoch, token.attempt_id)

        thread = threading.Thread(target=lookup, daemon=True)
        thread.start()
        # Proof by state, not wall clock (re-review M7): wait until the reader is blocked on a lock
        # (or has answered early, which is the failure this test exists to catch).
        import time
        blocked, deadline = False, time.monotonic() + 15
        while not blocked and thread.is_alive() and time.monotonic() < deadline:
            with case.application.connect() as probe:
                blocked = probe.scalar(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()")) > 0
            time.sleep(0.05)
        assert blocked and thread.is_alive(), 'lookup answered while the publish was still in flight'
        writer.commit()
    thread.join(15)
    assert not thread.is_alive() and seen['result'] == made


def test_publish_after_window_is_lease_lost(case, repo, submit, publish):
    job = submit('k1').job_id
    token = claim(case, repo)
    db(case, "UPDATE app.job SET run_deadline_at = now() - interval '1 second' WHERE id=:j", j=job)
    assert do_publish(case, publish, token) is publish.LEASE_LOST
    assert capacity(case, job) == ('accepted_server', False, 2, 1)


def test_publish_bigint_boundary(case, repo, submit, publish):
    from app.config import settings
    assert settings.max_file_size == 2147483648
    submit('k1')
    token = claim(case, repo)
    with Session(case.application) as session:
        with pytest.raises(ValueError):
            publish.publish_candidate(session, token, candidate(token, byte_size=2147483649), absolute_path='/m/x')
    assert do_publish(case, publish, token, candidate(token, byte_size=2147483648)).byte_size == 2147483648


@pytest.mark.parametrize('changes', [
    dict(epoch=99), dict(job_id='other'), dict(attempt_id='other'), dict(byte_size=0), dict(byte_size=True),
    dict(sha256='AB' * 32), dict(sha256='ab'), dict(media_check='unverified'),
    dict(relative_path='elsewhere/media.mp4'), dict(media_format='m p4')],
    ids=['epoch', 'job', 'attempt', 'zero', 'bool', 'upper-hash', 'short-hash', 'check', 'path', 'format'])
def test_candidate_must_match_token_and_contract(case, repo, submit, publish, changes):
    submit('k1')
    token = claim(case, repo)
    with Session(case.application) as session:
        with pytest.raises(ValueError):
            publish.publish_candidate(session, token, replace(candidate(token), **changes), absolute_path='/m/x')
