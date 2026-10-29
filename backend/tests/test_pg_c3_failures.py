"""C3 Task 4: process-level failure acceptance, real PG (nonce-owned) + real child processes; never pv_verify.

Every test also checks that each child it started is gone afterwards (no leftover processes).
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

import pytest
from sqlalchemy import text
from sqlmodel import Session

from test_pg_download_worker import job_row, media, worker  # noqa: F401  (fixtures/helpers)
from test_pg_job_repository import case, db, repo, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
BACKEND = Path(__file__).resolve().parents[1]


def alive(pid):
    if os.name == 'nt':
        output = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True).stdout
        return re.search(rb'\s%d\s' % pid, output) is not None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_for(predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def runs(worker, monkeypatch):
    """Record every child the worker starts, so the test can prove none is left behind."""
    started = []
    real = worker.execution_supervisor.start

    def recording(request, isolation=None):
        run = real(request, isolation=isolation)
        started.append(run)
        return run
    monkeypatch.setattr(worker.execution_supervisor, 'start', recording)
    monkeypatch.setattr(worker, 'TERMINATE_GRACE_SECONDS', 2.0)
    return started


def in_background(function):
    out = {}
    thread = threading.Thread(target=lambda: out.setdefault('value', function()), daemon=True)
    thread.start()
    return thread, out


def manifests(case, job):
    with case.migration.connect() as connection:
        return connection.scalar(text('SELECT count(*) FROM app.artifactmanifest WHERE job_id=:j'), {'j': job})


def attempts(case, job):
    with case.migration.connect() as connection:
        return connection.execute(text(
            'SELECT epoch, state, error_code FROM app.jobattempt WHERE job_id=:j ORDER BY epoch'), {'j': job}).all()


def recover(case, repo):
    with Session(case.application) as session:
        recovered = repo.recover_expired(session)
        session.commit()
    return recovered


# Review Focus 3: the lease is taken while the child runs -> stop it, never publish, remove only this attempt.
def test_lease_loss_stops_child_without_publish(case, worker, repo, media, submit, runs):
    job = submit('k1').job_id
    thread, out = in_background(lambda: worker.run_once(case.application, media, 'w1', executor='fake:hang',
                                                        heartbeat_seconds=0.3, poll_seconds=0.02))
    assert wait_for(lambda: runs and job_row(case, job).internal_state == 'running')
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    thread.join(30)
    assert not thread.is_alive() and out['value'] == 'lost'
    assert wait_for(lambda: not alive(runs[0].pid), 10)
    assert manifests(case, job) == 0 and list((media / job).iterdir()) == []
    assert recover(case, repo) == [job]
    assert job_row(case, job).internal_state == 'retry_wait' and attempts(case, job)[0].state == 'lost'


# Review Focus 2: the worker process is killed outright; its orphaned child stops on stdin EOF, the lease
# expires, and another worker recovers and completes the Job. The old worker never publishes.
def test_killed_worker_recovered_by_another(case, worker, repo, media, submit, runs):
    job = submit('k1').job_id
    env = dict(os.environ, DB_URL=case.application.url.render_as_string(hide_password=False),
               DOWNLOAD_WORKER_ALLOW_FAKE='1', PYTHONPATH=str(BACKEND))
    process = subprocess.Popen([sys.executable, '-m', 'app.download_worker', '--once', '--media-root', str(media),
                                '--executor', 'fake:hang_pid'], cwd=BACKEND, env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        pid_files = lambda: list((media / job).glob('*/child.pid')) if (media / job).exists() else []
        assert wait_for(lambda: job_row(case, job).internal_state == 'running' and pid_files())
        orphan = int(pid_files()[0].read_text())
        assert alive(orphan)
        process.kill()  # the worker only: no chance to clean up, terminate or fail the attempt
        process.wait(10)
        assert wait_for(lambda: not alive(orphan), 15), 'orphaned child kept running after its worker died'
    finally:
        if process.poll() is None:
            process.kill()
    assert job_row(case, job).internal_state == 'running'  # nothing recorded by the dead worker
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    assert worker.run_once(case.application, media, 'w2', executor='fake:ok:2000',
                           heartbeat_seconds=0.3, poll_seconds=0.02) == 'published'
    state = job_row(case, job)
    assert (state.internal_state, state.media_state, state.source_bytes_used) == ('succeeded', 'available', 2000)
    # Recovery bumps the epoch to fence the dead worker (C1), then the new claim bumps it again.
    assert [(row.epoch, row.state) for row in attempts(case, job)] == [(1, 'lost'), (3, 'succeeded')]
    assert manifests(case, job) == 1 and not alive(runs[0].pid)


# Review Focus 4: bytes of a failed attempt count; the next attempt is cut off within the remaining budget.
def test_byte_budget_spans_attempts(case, worker, media, submit, runs):
    from app.config import settings
    job = submit('k1').job_id
    budget = 3 * settings.max_file_size
    db(case, 'UPDATE app.job SET source_bytes_used=:used WHERE id=:j', used=budget - 5000, j=job)
    # No periodic heartbeat fires: the failure path itself must record the attempt's bytes.
    assert worker.run_once(case.application, media, 'w1', executor='fake:partial:3000:http_5xx',
                           heartbeat_seconds=600, poll_seconds=0.02) == 'retry_wait'
    assert job_row(case, job).source_bytes_used == budget - 2000
    db(case, "UPDATE app.job SET next_run_at = now() - interval '1 second' WHERE id=:j", j=job)
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:5000',
                           heartbeat_seconds=600, poll_seconds=0.02) == 'failed'
    state = job_row(case, job)
    assert state.error_type == 'file_too_large' and state.source_bytes_used <= budget
    assert manifests(case, job) == 0 and all(not alive(run.pid) for run in runs)


def test_heartbeat_db_error_stops_child_without_publish(case, worker, media, submit, runs, monkeypatch):
    from sqlalchemy.exc import OperationalError
    job = submit('k1').job_id

    def unavailable(session, token):
        raise OperationalError('heartbeat', {}, Exception('synthetic connection loss'))
    monkeypatch.setattr(worker, 'heartbeat', unavailable)
    assert worker.run_once(case.application, media, 'w1', executor='fake:hang',
                           heartbeat_seconds=0.3, poll_seconds=0.02) == 'lost'
    assert wait_for(lambda: not alive(runs[0].pid), 10)
    assert manifests(case, job) == 0 and list((media / job).iterdir()) == []
    assert job_row(case, job).internal_state == 'running'  # no DB write to "rescue" anything


def test_run_window_expiry_stops_child_and_fails(case, worker, repo, media, submit, runs):
    job = submit('k1').job_id
    db(case, "UPDATE app.job SET run_deadline_at = now() + interval '2 seconds' WHERE id=:j", j=job)
    assert worker.run_once(case.application, media, 'w1', executor='fake:hang',
                           heartbeat_seconds=0.3, poll_seconds=0.02) == 'lost'
    assert wait_for(lambda: not alive(runs[0].pid), 10)
    assert manifests(case, job) == 0 and list((media / job).iterdir()) == []
    assert recover(case, repo) == [job]
    state = job_row(case, job)
    assert (state.internal_state, state.error_type) == ('failed', 'run_deadline_exceeded')


# C3 review I2: an unexpected exception inside the loop must not leave the child (group) running.
def test_unexpected_exception_leaves_no_child(case, worker, media, submit, runs, monkeypatch):
    submit('k1')

    def broken(engine, token, attempt_bytes, percent=0.0):
        raise RuntimeError('synthetic unexpected failure')
    monkeypatch.setattr(worker, '_beat', broken)
    with pytest.raises(RuntimeError):
        worker.run_once(case.application, media, 'w1', executor='fake:hang',
                        heartbeat_seconds=0.3, poll_seconds=0.02)
    assert runs and wait_for(lambda: not alive(runs[0].pid), 15)
