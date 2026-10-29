"""C1 lease repository on nonce-owned isolated PG (c1_0005); never pv_verify."""
import math
import os
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.models import Job, JobStatus, User
from app.models_execution import JobAttempt

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


@pytest.fixture
def case():
    from b3b_pg_helpers import isolated_database
    # Current head: the ORM models always describe the latest schema.
    with isolated_database(target='head') as database:
        yield database


@pytest.fixture
def repo():
    from app.services import job_repository
    return job_repository


def seed(case, job_id='c1-j1', *, version=2, op_state='accepted_server', window="30 minutes", user='c1-u'):
    from b2_pg_helpers import operation, user as make_user
    with Session(case.migration) as session:
        if session.get(User, user) is None:
            make_user(session, user)
        now = session.scalar(text('SELECT now()'))
        job = Job(id=job_id, url='https://synthetic.invalid/v', user_id=user, status=JobStatus.queued)
        if version == 2:
            job.execution_version, job.internal_state = 2, 'queued'
            job.run_deadline_at = session.scalar(text(f"SELECT now() + interval '{window}'"))
        session.add(job)
        session.flush()
        op = operation(session, opid='op-' + job_id, userid=user, accepted_at=now)
        op.state, op.job_id, op.capacity_reserved = op_state, job_id, True
        session.add(op)
        session.commit()


def db(case, sql, **params):
    with case.migration.begin() as connection:
        return connection.execute(text(sql), params)


def row(case, job_id='c1-j1'):
    with case.migration.connect() as connection:
        return connection.execute(text(
            'SELECT internal_state, status, epoch, attempts_used, lease_owner, '
            'extract(epoch from next_run_at - now()) AS wait, error_type FROM app.job WHERE id=:j'), {'j': job_id}).one()


def claim(case, repo, owner='w1'):
    with Session(case.application) as session:
        token = repo.claim_next(session, owner)
        session.commit()
        return token


def test_claim_increments_epoch_and_attempts(case, repo):
    seed(case)
    token = claim(case, repo)
    assert token.job_id == 'c1-j1' and token.epoch == 1 and token.owner == 'w1'
    state = row(case)
    assert (state.internal_state, state.status, state.attempts_used, state.lease_owner) == ('running', 'downloading', 1, 'w1')
    with Session(case.migration) as session:
        attempt = session.get(JobAttempt, token.attempt_id)
        assert (attempt.epoch, attempt.attempt_index, attempt.state, attempt.ended_at) == (1, 1, 'running', None)
    assert 'w1' not in repr(token)


def test_concurrent_claim_skips_locked_row(case, repo):
    seed(case, 'c1-j1')
    seed(case, 'c1-j2')
    first, second = Session(case.application), Session(case.application)
    try:
        a = repo.claim_next(first, 'w1')      # row lock held until commit
        b = repo.claim_next(second, 'w2')     # must skip, not block
        assert a is not None and b is not None and a.job_id != b.job_id
        third = Session(case.application)
        try:
            assert repo.claim_next(third, 'w3') is None  # both rows locked by open transactions
        finally:
            third.rollback(); third.close()
        first.commit(); second.commit()
    finally:
        first.close(); second.close()


def test_only_v2_accepted_server_jobs_are_claimable(case, repo):
    seed(case, 'c1-v1', version=1)
    seed(case, 'c1-resolving', op_state='resolving')
    seed(case, 'c1-late', window='-1 second')
    assert claim(case, repo) is None


def test_lease_uses_database_clock(case, repo):
    seed(case)
    token = claim(case, repo)
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id='c1-j1'")
    with Session(case.application) as session:
        assert repo.heartbeat(session, token) is False
        assert repo.report_progress(session, token, 50.0) is False


def test_heartbeat_extends_lease_and_progress_is_fenced(case, repo):
    seed(case)
    token = claim(case, repo)
    with Session(case.application) as session:
        assert repo.heartbeat(session, token) is True
        assert repo.report_progress(session, token, 42.5) is True
        session.commit()
    with case.migration.connect() as connection:
        left, progress = connection.execute(text(
            "SELECT extract(epoch from lease_deadline - now()), progress FROM app.job WHERE id='c1-j1'")).one()
    assert 55 <= left <= 60 and progress == 42.5
    forged = repo.LeaseToken(job_id=token.job_id, attempt_id=token.attempt_id, owner='other', epoch=token.epoch)
    with Session(case.application) as session:
        assert repo.heartbeat(session, forged) is False


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1.0, 100.5])
def test_progress_rejects_invalid_values(case, repo, value):
    seed(case)
    token = claim(case, repo)
    with Session(case.application) as session:
        with pytest.raises(ValueError):
            repo.report_progress(session, token, value)


def test_stale_epoch_cannot_write_after_recovery(case, repo):
    seed(case)
    old = claim(case, repo)
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id='c1-j1'")
    with Session(case.application) as session:
        assert repo.recover_expired(session) == ['c1-j1']
        session.commit()
    state = row(case)
    assert (state.internal_state, state.status, state.epoch, state.lease_owner) == ('retry_wait', 'queued', 2, None)
    with Session(case.application) as session:
        assert repo.heartbeat(session, old) is False
        assert repo.report_progress(session, old, 10.0) is False
        assert repo.fail_attempt(session, old, 'network') == 'lost'
        session.commit()
    with Session(case.migration) as session:
        assert session.get(JobAttempt, old.attempt_id).state == 'lost'
    new = claim(case, repo, 'w2')
    assert new is not None and new.epoch == 3 and row(case).attempts_used == 2


def test_backoff_sequence_and_jitter_bounds(case, repo):
    seed(case)
    for attempt, (low, high), jitter in ((1, (10, 12), 0.2), (2, (60, 60.5), 0.0)):
        token = claim(case, repo)
        with Session(case.application) as session:
            assert repo.fail_attempt(session, token, 'http_5xx', jitter=lambda value=jitter: value) == 'retry_wait'
            session.commit()
        state = row(case)
        assert state.internal_state == 'retry_wait' and state.status == 'queued'
        assert low - 1 <= state.wait <= high
        db(case, "UPDATE app.job SET next_run_at = now() - interval '1 second' WHERE id='c1-j1'")
    token = claim(case, repo)
    with Session(case.application) as session:
        assert repo.fail_attempt(session, token, 'http_5xx') == 'failed'
        session.commit()
    state = row(case)
    assert (state.internal_state, state.status, state.attempts_used) == ('failed', 'error', 3)
    assert claim(case, repo) is None


def test_attempt_and_window_budget_never_reset(case, repo):
    seed(case, window='5 seconds')
    token = claim(case, repo)
    with Session(case.application) as session:
        # A 10 s backoff cannot fit in the remaining 5 s window: terminal, not retry_wait.
        assert repo.fail_attempt(session, token, 'network', jitter=lambda: 0.0) == 'failed'
        session.commit()
    assert row(case).attempts_used == 1


@pytest.mark.parametrize('code,expected', [('http_412', 'failed'), ('captcha', 'failed'), ('session_expired', 'needs_review'),
    ('permission_changed', 'needs_review'), ('http_5xx', 'retry_wait'), ('http_429', 'retry_wait'),
    ('network', 'retry_wait'), ('ssrf_blocked', 'failed'), ('unknown-code', 'failed')])
def test_error_classification(case, repo, code, expected):
    seed(case)
    token = claim(case, repo)
    with Session(case.application) as session:
        assert repo.fail_attempt(session, token, code, jitter=lambda: 0.0) == expected
        session.commit()
    state = row(case)
    assert state.internal_state == expected and state.lease_owner is None
    assert state.status == ('queued' if expected == 'retry_wait' else 'error')


def test_recover_exhausted_job_fails(case, repo):
    seed(case)
    for _ in range(3):
        token = claim(case, repo)
        db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id='c1-j1'")
        with Session(case.application) as session:
            repo.recover_expired(session)
            session.commit()
    state = row(case)
    assert (state.internal_state, state.attempts_used, state.error_type) == ('failed', 3, 'run_budget_exhausted')


def test_expire_window_fails_waiting_jobs(case, repo):
    seed(case, window='1 second')
    db(case, "UPDATE app.job SET run_deadline_at = now() - interval '1 second' WHERE id='c1-j1'")
    with Session(case.application) as session:
        assert repo.expire_window(session) == ['c1-j1']
        session.commit()
    state = row(case)
    assert (state.internal_state, state.status, state.error_type) == ('failed', 'error', 'run_deadline_exceeded')


@pytest.mark.parametrize('owner', ['', 'a' * 65, 'bad owner', None, 7])
def test_owner_validation(case, repo, owner):
    seed(case)
    with Session(case.application) as session:
        with pytest.raises(ValueError):
            repo.claim_next(session, owner)


# ---- C1 review fixes ------------------------------------------------------------------------------

@pytest.fixture
def submit(case, monkeypatch):
    """B4's real server submission (operation + admission slot reservations) on this nonce DB."""
    from app.schemas import DownloadRequest
    from app.services import download_submission as service, quota
    from app.services.download_submission import AccessSnapshot
    for name, value in (('membership_unlimited_downloads', False), ('default_quota_limit', 20),
                        ('download_admission_global_limit', 32), ('download_admission_user_limit', 2),
                        ('download_idempotency_max_entries', 10000)):
        monkeypatch.setattr(service.settings, name, value)
    monkeypatch.setattr(service, 'is_unlimited_user', lambda _: False)
    monkeypatch.setattr(quota, 'is_unlimited_user', lambda _: False)
    with Session(case.migration) as session:
        session.add(User(id='c1-slot', email='c1-slot@synthetic.invalid', password_hash='x'))
        session.commit()
    request = DownloadRequest(url='https://source.synthetic.invalid/video', format_id='synthetic', force_server=True)
    snapshot = AccessSnapshot(720, 0, 'synthetic')
    return lambda key: service.submit_download(case.application, 'c1-slot', request, key, snapshot)


def capacity(case, job_id):
    with case.migration.connect() as connection:
        op_state, done = connection.execute(text(
            'SELECT state, completed_at IS NOT NULL FROM app.downloadoperation WHERE job_id=:j'), {'j': job_id}).one()
        held = connection.scalar(text(
            'SELECT count(*) FROM app.resourcereservation r JOIN app.downloadoperation o ON o.id=r.operation_id '
            'WHERE o.job_id=:j AND r.released=false'), {'j': job_id})
        used = connection.scalar(text("SELECT used FROM app.resourcecounter WHERE resource='admission_slots' "
                                      "AND scope='user:c1-slot'"))
    return op_state, done, held, used


def claim_job(case, repo, job_id, owner='w1'):
    token = claim(case, repo, owner)
    assert token is not None and token.job_id == job_id
    return token


@pytest.mark.parametrize('code,expected', [('http_412', 'failed'), ('session_expired', 'needs_review')])
def test_terminal_failure_releases_slots_and_ends_operation(case, repo, submit, code, expected):
    job = submit('k1').job_id
    token = claim_job(case, repo, job)
    with Session(case.application) as session:
        assert repo.fail_attempt(session, token, code) == expected
        session.commit()
    assert capacity(case, job) == (expected, True, 0, 0)


def test_two_failures_do_not_lock_user_out(case, repo, submit):
    for key in ('k1', 'k2'):
        job = submit(key).job_id
        token = claim_job(case, repo, job)
        with Session(case.application) as session:
            assert repo.fail_attempt(session, token, 'http_412') == 'failed'
            session.commit()
    assert submit('k3').mode == 'server'  # slots were returned; no 503 download_capacity


def test_retry_keeps_slots_and_operation(case, repo, submit):
    job = submit('k1').job_id
    token = claim_job(case, repo, job)
    with Session(case.application) as session:
        assert repo.fail_attempt(session, token, 'http_5xx', jitter=lambda: 0.0) == 'retry_wait'
        session.commit()
    assert capacity(case, job) == ('accepted_server', False, 2, 1)


def test_recover_exhausted_releases_slots(case, repo, submit):
    job = submit('k1').job_id
    for _ in range(3):
        claim_job(case, repo, job)
        db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
        with Session(case.application) as session:
            assert repo.recover_expired(session) == [job]
            session.commit()
    assert row(case, job).internal_state == 'failed'
    assert capacity(case, job) == ('failed', True, 0, 0)


def test_expire_window_releases_slots(case, repo, submit):
    job = submit('k1').job_id
    db(case, "UPDATE app.job SET run_deadline_at = now() - interval '1 second' WHERE id=:j", j=job)
    with Session(case.application) as session:
        assert repo.expire_window(session) == [job]
        session.commit()
    assert capacity(case, job) == ('failed', True, 0, 0)


def test_lost_lease_terminal_failure_writes_nothing(case, repo, submit):
    job = submit('k1').job_id
    old = claim_job(case, repo, job)
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    with Session(case.application) as session:
        repo.recover_expired(session)
        session.commit()
    with Session(case.application) as session:
        assert repo.fail_attempt(session, old, 'http_412') == 'lost'
        session.commit()
    assert capacity(case, job) == ('accepted_server', False, 2, 1)


def test_running_attempt_bound_by_absolute_window(case, repo):
    seed(case, window='20 seconds')
    token = claim(case, repo)
    with case.migration.connect() as connection:
        left = connection.scalar(text("SELECT extract(epoch from lease_deadline - now()) FROM app.job WHERE id='c1-j1'"))
    assert left <= 20  # the lease never extends past the absolute run window
    db(case, "UPDATE app.job SET run_deadline_at = now() - interval '1 second' WHERE id='c1-j1'")
    with Session(case.application) as session:
        assert repo.heartbeat(session, token) is False
        assert repo.report_progress(session, token, 10.0) is False
        assert repo.recover_expired(session) == ['c1-j1']
        session.commit()
    state = row(case)
    assert (state.internal_state, state.error_type) == ('failed', 'run_deadline_exceeded')


def test_claim_result_carries_run_deadline(case, repo):
    seed(case)
    token = claim(case, repo)
    with case.migration.connect() as connection:
        assert token.run_deadline_at == connection.scalar(text("SELECT run_deadline_at FROM app.job WHERE id='c1-j1'"))


def test_same_owner_reclaim_fences_old_epoch(case, repo):
    seed(case)
    old = claim(case, repo, 'w1')
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id='c1-j1'")
    with Session(case.application) as session:
        repo.recover_expired(session)
        session.commit()
    new = claim(case, repo, 'w1')  # same process owner, new epoch
    assert new.epoch == old.epoch + 2
    with Session(case.application) as session:
        assert repo.heartbeat(session, old) is False
        assert repo.report_progress(session, old, 90.0) is False
        assert repo.fail_attempt(session, old, 'http_412') == 'lost'
        session.commit()
    state = row(case)
    assert (state.internal_state, state.epoch, state.lease_owner) == ('running', new.epoch, 'w1')
    with Session(case.application) as session:
        assert repo.heartbeat(session, new) is True
        session.commit()


def test_due_retry_claimed_before_newer_queued(case, repo):
    seed(case, 'c1-old')
    token = claim(case, repo)
    with Session(case.application) as session:
        assert repo.fail_attempt(session, token, 'network', jitter=lambda: 0.0) == 'retry_wait'
        session.commit()
    db(case, "UPDATE app.job SET next_run_at = now() - interval '5 seconds' WHERE id='c1-old'")
    seed(case, 'c1-new')
    assert claim(case, repo).job_id == 'c1-old'


def test_future_retry_is_not_claimable(case, repo):
    seed(case)
    token = claim(case, repo)
    with Session(case.application) as session:
        assert repo.fail_attempt(session, token, 'network', jitter=lambda: 0.0) == 'retry_wait'
        session.commit()
    assert claim(case, repo) is None


@pytest.mark.parametrize('code,expected', [('http_401', 'failed'), ('http_403', 'failed'), ('http_408', 'retry_wait')])
def test_more_error_classification(case, repo, code, expected):
    seed(case)
    token = claim(case, repo)
    with Session(case.application) as session:
        assert repo.fail_attempt(session, token, code, jitter=lambda: 0.0) == expected
        session.commit()


def test_run_window_matches_download_budget(repo):
    from app.services.outbound_budget import BudgetProfile
    assert repo.RUN_WINDOW.total_seconds() == BudgetProfile.download_parent().seconds == 1800


# C3 Task 1: cross-attempt source byte budget (c3_0007).
def source_bytes(case, job_id='c1-j1'):
    with case.migration.connect() as connection:
        job = connection.scalar(text('SELECT source_bytes_used FROM app.job WHERE id=:j'), {'j': job_id})
        attempts = dict(connection.execute(text(
            'SELECT id, bytes_used FROM app.jobattempt WHERE job_id=:j'), {'j': job_id}).all())
    return job, attempts


def report(case, repo, token, value):
    with Session(case.application) as session:
        result = repo.report_bytes(session, token, value)
        session.commit()
    return result


def test_report_bytes_adds_only_monotonic_increments(case, repo):
    seed(case)
    token = claim(case, repo)
    assert token.source_bytes_used == 0
    assert report(case, repo, token, 100) == 'ok'
    assert report(case, repo, token, 250) == 'ok'
    assert report(case, repo, token, 200) == 'ok'  # a lower cumulative value never subtracts
    assert source_bytes(case) == (250, {token.attempt_id: 250})


def test_source_bytes_carry_across_attempts(case, repo):
    seed(case)
    first = claim(case, repo)
    assert report(case, repo, first, 300) == 'ok'
    with Session(case.application) as session:
        assert repo.fail_attempt(session, first, 'http_5xx', jitter=lambda: 0.0) == 'retry_wait'
        session.commit()
    db(case, "UPDATE app.job SET next_run_at = now() - interval '1 second' WHERE id='c1-j1'")
    second = claim(case, repo)
    assert second.source_bytes_used == 300  # the budget is per Job, not reset by a new attempt
    assert report(case, repo, second, 50) == 'ok'
    assert source_bytes(case) == (350, {first.attempt_id: 300, second.attempt_id: 50})


def test_report_bytes_over_budget_writes_nothing(case, repo):
    from app.config import settings
    budget = 3 * settings.max_file_size
    seed(case)
    token = claim(case, repo)
    assert report(case, repo, token, budget) == 'ok'  # exactly the budget is allowed
    assert report(case, repo, token, budget + 1) == 'over_budget'
    assert source_bytes(case) == (budget, {token.attempt_id: budget})


def test_report_bytes_with_stale_token_is_lost(case, repo):
    seed(case)
    old = claim(case, repo)
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id='c1-j1'")
    with Session(case.application) as session:
        repo.recover_expired(session)
        session.commit()
    assert report(case, repo, old, 10) == 'lost'
    assert source_bytes(case) == (0, {old.attempt_id: 0})


@pytest.mark.parametrize('value', [-1, 1.0, '10', True, None])
def test_report_bytes_rejects_invalid_values(case, repo, value):
    seed(case)
    token = claim(case, repo)
    with Session(case.application) as session:
        with pytest.raises(ValueError):
            repo.report_bytes(session, token, value)


@pytest.mark.parametrize('table', ['job', 'jobattempt'])
def test_byte_counters_cannot_be_negative(case, repo, table):
    seed(case)
    claim(case, repo)
    column = 'source_bytes_used' if table == 'job' else 'bytes_used'
    with pytest.raises(Exception) as error:
        db(case, f"UPDATE app.{table} SET {column} = -1 WHERE {'id' if table == 'job' else 'job_id'}='c1-j1'")
    assert 'check' in str(error.value).lower()


def test_report_bytes_after_lease_expiry_before_recovery_is_lost(case, repo):
    # The attempt row is still 'running' until recovery runs; only the Job lease check stops this.
    seed(case)
    token = claim(case, repo)
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id='c1-j1'")
    assert report(case, repo, token, 10) == 'lost'
    assert source_bytes(case) == (0, {token.attempt_id: 0})
