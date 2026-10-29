"""C3 Task 3: download worker loop on nonce-owned isolated PG with real child processes; never pv_verify."""
import os
from pathlib import Path
import time

import pytest
from sqlalchemy import text

from test_pg_job_repository import capacity, case, db, repo, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv('DOWNLOAD_WORKER_ALLOW_FAKE', '1')  # test-only executors; production never sets it
    from app.services import download_worker
    return download_worker


@pytest.fixture
def media(tmp_path):
    from app.services import artifact_store
    root = tmp_path / 'media'
    root.mkdir()
    artifact_store.provision_root(root.resolve())  # operators provision the media root once (C5a review I2)
    return root.resolve()


def run(case, worker, media, executor, **options):
    options.setdefault('heartbeat_seconds', 0.2)
    options.setdefault('poll_seconds', 0.02)
    return worker.run_once(case.application, media, 'w1', executor=executor, **options)


def job_row(case, job_id):
    with case.migration.connect() as connection:
        return connection.execute(text(
            'SELECT internal_state, status, media_state, error_type, source_bytes_used, visible_attempt_id '
            'FROM app.job WHERE id=:j'), {'j': job_id}).one()


def test_idle_without_runnable_job(case, worker, media):
    assert run(case, worker, media, 'fake:ok:10') == 'idle'


def test_success_publishes_file_and_facts(case, worker, media, submit):
    job = submit('k1').job_id
    assert run(case, worker, media, 'fake:ok:5000') == 'published'
    state = job_row(case, job)
    assert (state.internal_state, state.status, state.media_state, state.source_bytes_used) == (
        'succeeded', 'done', 'available', 5000)
    with case.migration.connect() as connection:
        relative = connection.scalar(text('SELECT relative_path FROM app.artifactmanifest WHERE job_id=:j'), {'j': job})
    final = media / relative
    assert final.stat().st_size == 5000
    assert sorted(entry.name for entry in final.parent.iterdir()) == ['manifest.json', 'media.mp4']
    assert capacity(case, job) == ('succeeded', True, 0, 0)
    with case.migration.connect() as connection:  # facts C4/C5 build on
        facts = connection.execute(text(
            'SELECT j.visible_attempt_id = m.attempt_id AS own, j.file_path, a.bytes_used, '
            'extract(epoch from j.expires_at - now()) AS ttl FROM app.job j JOIN app.artifactmanifest m '
            'ON m.job_id = j.id JOIN app.jobattempt a ON a.id = m.attempt_id WHERE j.id=:j'), {'j': job}).one()
    assert facts.own and facts.file_path == str(final) and facts.bytes_used == 5000 and 3500 < facts.ttl <= 3600


@pytest.mark.parametrize('executor,outcome,error_type', [
    ('fake:error:http_5xx', 'retry_wait', None),
    ('fake:error:http_412', 'failed', 'http_412'),
    ('fake:crash', 'failed', 'execution_crashed'),
    ('fake:garbage', 'failed', 'execution_protocol_error'),
    ('fake:error:surprise_code', 'failed', 'execution_failed'),  # unknown child codes never steer retries
])
def test_child_failures_map_to_c1_outcomes_and_remove_attempt(case, worker, media, submit, executor, outcome,
                                                              error_type):
    job = submit('k1').job_id
    assert run(case, worker, media, executor) == outcome
    state = job_row(case, job)
    assert (state.internal_state, state.error_type, state.visible_attempt_id) == (outcome, error_type, None)
    assert [entry for entry in (media / job).iterdir()] == []  # only this attempt's directory, now removed


def test_attempt_limit_follows_remaining_source_budget(case, worker, media, submit):
    from app.config import settings
    job = submit('k1').job_id
    db(case, 'UPDATE app.job SET source_bytes_used=:used WHERE id=:j', used=3 * settings.max_file_size - 100, j=job)
    assert run(case, worker, media, 'fake:ok:5000') == 'failed'
    assert job_row(case, job).error_type == 'file_too_large'


def test_fake_executor_without_opt_in_is_refused_before_claim(case, worker, media, submit, monkeypatch):
    job = submit('k1').job_id
    monkeypatch.delenv('DOWNLOAD_WORKER_ALLOW_FAKE')
    with pytest.raises(ValueError):
        run(case, worker, media, 'fake:ok:10')
    assert job_row(case, job).internal_state == 'queued'  # nothing was claimed


def test_cli_once_is_idle_without_work(case, worker, media, monkeypatch):
    from app import download_worker as cli
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    assert cli.main(['--once', '--media-root', str(media), '--executor', 'fake:ok:10']) == 'idle'


def test_cli_default_executor_refuses_until_b5(case, worker, media, monkeypatch, submit):
    # C3 review M3: the default 'ytdlp' executor is unavailable, so the CLI exits 2 and leases nothing.
    from app import download_worker as cli
    job = submit('k1').job_id
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(media)])
    assert stop.value.code == 2 and job_row(case, job).internal_state == 'queued'


def test_cli_refuses_unusable_media_root(case, worker, tmp_path, monkeypatch, submit):
    from app import download_worker as cli
    job = submit('k1').job_id
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(tmp_path / 'missing')])
    assert stop.value.code not in (0, None)
    assert job_row(case, job).internal_state == 'queued'


def test_unavailable_executor_is_refused_before_claim(case, worker, media, submit):
    # C3 review M3: until B5 wires the real download, a worker configured with 'ytdlp' leases nothing.
    job = submit('k1').job_id
    with pytest.raises(ValueError):
        run(case, worker, media, 'ytdlp')
    assert job_row(case, job).internal_state == 'queued'


def test_silent_child_bytes_are_counted_from_the_file(case, worker, media, submit):
    # C3 review M6: bytes count even when the child never reports progress.
    job = submit('k1').job_id
    assert run(case, worker, media, 'fake:silent:4000') == 'published'
    assert job_row(case, job).source_bytes_used == 4000


def test_progress_is_visible_while_running(case, worker, media, submit):
    # C3 review M8: Job.progress follows the child during the download, not only at the end.
    import threading
    job = submit('k1').job_id
    out = {}
    thread = threading.Thread(target=lambda: out.setdefault('value', run(case, worker, media, 'fake:progress_then_hang:3000')),
                              daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    progress = 0.0
    while time.monotonic() < deadline and progress < 100.0:
        with case.migration.connect() as connection:
            progress = connection.scalar(text('SELECT progress FROM app.job WHERE id=:j'), {'j': job})
        time.sleep(0.05)
    assert progress == 100.0 and job_row(case, job).internal_state == 'running'
    db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
    thread.join(30)
    assert out['value'] == 'lost'


def test_lease_lost_at_publish_removes_attempt(case, worker, media, submit, monkeypatch):
    # C6a: removed only once fenced by recover_expired; a merely expired lease keeps it for recovery.
    from sqlmodel import Session
    from app.services import job_repository
    job = submit('k1').job_id
    real = worker.publish_candidate

    def lose_then_publish(session, token, candidate, **kwargs):
        db(case, "UPDATE app.job SET lease_deadline = now() - interval '1 second' WHERE id=:j", j=job)
        with Session(case.application) as other:
            assert job_repository.recover_expired(other) == [job]
            other.commit()
        return real(session, token, candidate, **kwargs)
    monkeypatch.setattr(worker, 'publish_candidate', lose_then_publish)
    assert run(case, worker, media, 'fake:ok:1000') == 'lost'
    assert list((media / job).iterdir()) == []
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.artifactmanifest WHERE job_id=:j'), {'j': job}) == 0


def test_unknown_publish_commit_is_confirmed_by_identity(case, worker, media, submit, monkeypatch):
    from sqlalchemy.exc import OperationalError
    job = submit('k1').job_id
    real = worker.publish_candidate

    def commit_then_lose_ack(session, token, candidate, **kwargs):
        result = real(session, token, candidate, **kwargs)
        session.commit()  # the commit lands, but the worker never hears back
        raise OperationalError('commit', {}, Exception('synthetic connection loss after commit'))
    monkeypatch.setattr(worker, 'publish_candidate', commit_then_lose_ack)
    assert run(case, worker, media, 'fake:ok:1000') == 'published'
    assert job_row(case, job).internal_state == 'succeeded'


# --- External gate G3/G4: isolated download children -------------------------------------------

def isolation_config():
    from app.services import child_isolation
    return child_isolation.IsolationConfig('iv-fetch', 994, 994, 'http://127.0.0.1:4750')


def test_isolated_worker_shares_the_attempt_dir_then_locks_it_before_sealing(case, worker, media, submit,
                                                                             monkeypatch):
    # The child itself runs unisolated here (no download user on this host); the order is what matters.
    job = submit('k1').job_id
    events, real_start, real_seal = [], worker.execution_supervisor.start, worker.artifact_store.seal_candidate
    config = isolation_config()

    def start(request, isolation=None):
        events.append(('start', isolation))
        return real_start(request)

    def seal(*args, **kwargs):
        events.append(('seal', None))
        return real_seal(*args, **kwargs)
    monkeypatch.setattr(worker.execution_supervisor, 'start', start)
    monkeypatch.setattr(worker.artifact_store, 'seal_candidate', seal)
    monkeypatch.setattr(worker.child_isolation, 'share_attempt_dir',
                        lambda path, isolation: events.append(('share', isolation)))
    monkeypatch.setattr(worker.child_isolation, 'lock_attempt_dir', lambda path: events.append(('lock', None)))
    assert run(case, worker, media, 'fake:okmp4:50', isolation=config) == 'published'
    # Locked once more by run_once's finally (idempotent): every exit path ends locked (review I2).
    assert events == [('share', config), ('start', config), ('lock', None), ('seal', None), ('lock', None)]
    assert job_row(case, job).internal_state == 'succeeded'


def test_isolated_worker_locks_a_failed_attempt_too(case, worker, media, submit, monkeypatch):
    submit('k1')
    locked = []
    real_start = worker.execution_supervisor.start
    monkeypatch.setattr(worker.execution_supervisor, 'start', lambda request, isolation=None: real_start(request))
    monkeypatch.setattr(worker.child_isolation, 'share_attempt_dir', lambda path, isolation: None)
    monkeypatch.setattr(worker.child_isolation, 'lock_attempt_dir', lambda path: locked.append(path))
    run(case, worker, media, 'fake:error:network', isolation=isolation_config())
    assert len(locked) == 1  # the discarded directory is gone before the final relock


def test_ytdlp_is_leasable_only_by_an_isolated_worker(case, worker, media):
    with pytest.raises(ValueError):
        run(case, worker, media, 'ytdlp')
    assert run(case, worker, media, 'ytdlp', isolation=isolation_config()) == 'idle'


@pytest.mark.parametrize('user,proxy', [('iv-fetch', ''), ('', 'http://127.0.0.1:4750')])
def test_cli_refuses_incomplete_isolation_settings_before_claim(case, worker, media, monkeypatch, submit,
                                                                 user, proxy):
    from app import download_worker as cli
    job = submit('k1').job_id
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    monkeypatch.setattr(cli.settings, 'download_child_user', user)
    monkeypatch.setattr(cli.settings, 'source_egress_proxy', proxy)
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(media), '--executor', 'fake:ok:10'])
    assert stop.value.code == 2 and job_row(case, job).internal_state == 'queued'


def test_cli_stops_when_an_isolated_child_cannot_be_stopped(case, worker, media, monkeypatch, submit):
    from app import download_worker as cli
    from app.services import child_isolation
    submit('k1')
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)

    def denied(*args, **kwargs):
        raise child_isolation.IsolationError('isolation_kill_denied')
    monkeypatch.setattr(cli, 'run_once', denied)

    def looped(seconds):
        raise RuntimeError('worker kept looping after an isolation failure')
    monkeypatch.setattr(cli.time, 'sleep', looped)  # a regression fails fast instead of hanging
    with pytest.raises(SystemExit) as stop:
        cli.main(['--media-root', str(media), '--executor', 'fake:ok:10'])  # not --once: still fatal
    assert stop.value.code == 2


def test_isolated_worker_locks_before_discarding_when_the_lease_is_lost(case, worker, media, submit, monkeypatch):
    submit('k1')
    events = []
    real_start, real_discard = worker.execution_supervisor.start, worker._discard
    monkeypatch.setattr(worker.execution_supervisor, 'start', lambda request, isolation=None: real_start(request))
    monkeypatch.setattr(worker.child_isolation, 'share_attempt_dir', lambda path, isolation: None)
    monkeypatch.setattr(worker.child_isolation, 'lock_attempt_dir', lambda path: events.append('lock'))
    monkeypatch.setattr(worker, '_discard', lambda paths: events.append('discard') or real_discard(paths))
    monkeypatch.setattr(worker, '_beat', lambda *args: 'lost')
    assert run(case, worker, media, 'fake:progress_then_hang:10', isolation=isolation_config()) == 'lost'
    assert events[:2] == ['lock', 'discard']


def isolated_unshared(worker, monkeypatch):
    real_start = worker.execution_supervisor.start
    monkeypatch.setattr(worker.execution_supervisor, 'start', lambda request, isolation=None: real_start(request))
    monkeypatch.setattr(worker.child_isolation, 'share_attempt_dir', lambda path, isolation: None)
    monkeypatch.setattr(worker.child_isolation, 'lock_attempt_dir', lambda path: None)


def test_isolated_worker_rechecks_the_container_and_records_its_own_media_check(case, worker, media, submit,
                                                                              monkeypatch):
    # Review I3: the isolated child is untrusted. Its 'verified' claim is ignored; the worker
    # checks the container signature itself after locking and records 'signature'.
    job = submit('k1').job_id
    isolated_unshared(worker, monkeypatch)
    assert run(case, worker, media, 'fake:okmp4:64', isolation=isolation_config()) == 'published'
    with case.migration.connect() as connection:
        check = connection.scalar(text('SELECT media_check FROM app.artifactmanifest WHERE job_id=:j'), {'j': job})
    assert check == 'signature'


def test_isolated_worker_refuses_a_child_claim_the_file_does_not_back(case, worker, media, submit, monkeypatch):
    job = submit('k1').job_id
    isolated_unshared(worker, monkeypatch)
    assert run(case, worker, media, 'fake:ok:64', isolation=isolation_config()) == 'failed'  # zeros, claims 'verified'
    state = job_row(case, job)
    assert (state.internal_state, state.error_type) == ('failed', 'media_invalid')


def test_a_share_failure_stops_the_worker(case, worker, media, submit, monkeypatch):
    from app.services import child_isolation
    submit('k1')
    started = []
    monkeypatch.setattr(worker.execution_supervisor, 'start', lambda *args, **kwargs: started.append(1))

    def refused(path, isolation):
        raise child_isolation.IsolationError('isolation_share_failed')
    monkeypatch.setattr(worker.child_isolation, 'share_attempt_dir', refused)
    locked = []
    monkeypatch.setattr(worker.child_isolation, 'lock_attempt_dir', lambda path: locked.append(path))
    with pytest.raises(child_isolation.IsolationError):
        run(case, worker, media, 'fake:ok:10', isolation=isolation_config())
    assert started == [] and len(locked) == 1  # re-review N3: a half-applied share is locked again


def test_an_unexpected_failure_still_relocks_the_attempt_dir(case, worker, media, submit, monkeypatch):
    submit('k1')
    locked = []
    isolated_unshared(worker, monkeypatch)
    monkeypatch.setattr(worker.child_isolation, 'lock_attempt_dir', lambda path: locked.append(path))

    def broken(*args, **kwargs):
        raise RuntimeError('unexpected')
    monkeypatch.setattr(worker, '_execute', broken)
    with pytest.raises(RuntimeError):
        run(case, worker, media, 'fake:ok:10', isolation=isolation_config())
    assert len(locked) == 1


def test_cli_runs_the_isolation_preflight_before_leasing(case, worker, media, monkeypatch, submit):
    from app import download_worker as cli
    from app.services import child_isolation
    job = submit('k1').job_id
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    monkeypatch.setattr(cli.child_isolation, 'from_settings', lambda settings: isolation_config())

    def failed(config):
        raise child_isolation.IsolationError('isolation_preflight_failed')
    monkeypatch.setattr(cli.child_isolation, 'preflight', failed)
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(media), '--executor', 'fake:ok:10'])
    assert stop.value.code == 2 and job_row(case, job).internal_state == 'queued'
