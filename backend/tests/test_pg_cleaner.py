"""C5a Task 3: cleaner orchestration and CLI on nonce-owned PG with really published files; never pv_verify."""
import os

import pytest
from sqlalchemy import text
from sqlmodel import Session

from test_pg_cleanup_repository import call, expire, make_due, published, state  # noqa: F401  (fixtures/helpers)
from test_pg_download_worker import media, worker  # noqa: F401  (fixtures)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
OWNER = 'c1-slot'


@pytest.fixture
def cleaner():
    from app.services import cleaner
    return cleaner


def media_path(case, media, job):
    with case.migration.connect() as connection:
        return media / connection.scalar(text('SELECT relative_path FROM app.artifactmanifest WHERE job_id=:j'),
                                         {'j': job})


def test_expired_file_is_deleted_end_to_end(case, cleaner, media, published):
    from app.services import file_reads
    final = media_path(case, media, published)
    assert final.exists()
    expire(case, published)
    assert cleaner.run_once(case.application, media, 'cl-1') == dict(marked=1, claimed=1, deleted=1, retry=0,
                                                                      needs_review=0, lost=0, storage_unavailable=0,
                                                                      purged=0, purge_failed=0, purge_mismatched=0,
                legacy_deleted=0, legacy_failed=0, legacy_refused=0,
                legacy_review=0, legacy_storage_unavailable=0, legacy_pending=0)
    assert not final.parent.exists() and not (media / published).exists()  # finished Job: empty job dir pruned
    assert state(case, published).media_state == 'deleted'
    with Session(case.application) as session:
        with pytest.raises(file_reads.ReadDenied) as denied:
            file_reads.open_read(session, OWNER, published, media_root=media, height_limit=None)
    assert denied.value.status == 410


def test_live_read_defers_deletion_to_a_later_round(case, cleaner, media, published):
    from app.services import file_reads
    with Session(case.application) as session:
        opened = file_reads.open_read(session, OWNER, published, media_root=media, height_limit=None)
    expire(case, published)
    first = cleaner.run_once(case.application, media, 'cl-1')
    assert (first['marked'], first['deleted']) == (1, 0) and media_path(case, media, published).exists()
    opened.file.close()
    with Session(case.application) as session:
        file_reads.end_read(session, opened.read_id)
        session.commit()
    assert cleaner.run_once(case.application, media, 'cl-1')['deleted'] == 1


def test_delete_failure_backs_off_and_keeps_file(case, cleaner, media, published, monkeypatch):
    def denied(media_root, relative_path, **options):
        raise cleaner.artifact_store.ArtifactError('artifact_io_failed')  # e.g. permission denied / file in use
    monkeypatch.setattr(cleaner.artifact_store, 'remove_published', denied)
    expire(case, published)
    assert cleaner.run_once(case.application, media, 'cl-1')['retry'] == 1
    row = state(case, published)
    assert (row.media_state, row.attempts, row.intent) == ('deleting', 1, 'pending')
    assert media_path(case, media, published).exists()


def test_unknown_entry_is_never_deleted_and_goes_to_review(case, cleaner, media, published):
    final = media_path(case, media, published)
    (final.parent / 'unexpected.bin').write_bytes(b'x')
    expire(case, published)
    # A deterministic refusal will not change on retry: straight to review (C5a review M5).
    assert cleaner.run_once(case.application, media, 'cl-1')['needs_review'] == 1
    assert final.exists() and (final.parent / 'unexpected.bin').exists()
    assert state(case, published).intent == 'needs_review'


def test_confirmation_lost_after_delete_is_completed_by_a_retry(case, cleaner, media, published, monkeypatch):
    from sqlalchemy.exc import OperationalError
    real = cleaner.confirm_deleted

    def connection_lost(session, claim):
        raise OperationalError('confirm', {}, Exception('synthetic connection loss after unlink'))
    monkeypatch.setattr(cleaner, 'confirm_deleted', connection_lost)
    expire(case, published)
    with pytest.raises(OperationalError):
        cleaner.run_once(case.application, media, 'cl-1')
    assert not media_path(case, media, published).exists() and state(case, published).media_state == 'deleting'
    monkeypatch.setattr(cleaner, 'confirm_deleted', real)
    make_due(case, published)  # the crashed cleaner's claim lapses
    assert cleaner.run_once(case.application, media, 'cl-2')['deleted'] == 1  # already absent counts as deleted
    assert state(case, published).media_state == 'deleted'


def test_storage_outage_stops_the_round_before_claiming(case, cleaner, media, published):
    expire(case, published)
    result = cleaner.run_once(case.application, media.parent / 'not-mounted', 'cl-1')
    assert result['storage_unavailable'] == 1 and (result['marked'], result['claimed']) == (0, 0)
    row = state(case, published)
    assert row.media_state == 'available' and row.intent is None


# C5a review I2: an empty mount point (volume not attached) must never turn Jobs into "deleted".
def test_unmounted_volume_never_marks_media_deleted(case, cleaner, media, published, tmp_path):
    expire(case, published)
    empty_mount_point = tmp_path / 'empty-mount'
    empty_mount_point.mkdir()
    result = cleaner.run_once(case.application, empty_mount_point.resolve(), 'cl-1')
    assert result['storage_unavailable'] == 1 and result['deleted'] == 0
    assert state(case, published).media_state == 'available'
    assert media_path(case, media, published).exists()


# C5a review M10: a claim whose path does not belong to its own job/attempt is refused, nothing deleted.
def test_path_not_matching_claim_is_refused(case, cleaner, media, submit, worker):
    first = submit('k1').job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:100', heartbeat_seconds=0.3,
                           poll_seconds=0.02) == 'published'
    second = submit('k2').job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:100', heartbeat_seconds=0.3,
                           poll_seconds=0.02) == 'published'
    with case.migration.begin() as connection:  # corrupt the second manifest to point at the first job's files
        other = connection.scalar(text('SELECT relative_path FROM app.artifactmanifest WHERE job_id=:j'), {'j': first})
        connection.execute(text('UPDATE app.artifactmanifest SET relative_path=:p WHERE job_id=:j'),
                           {'p': other, 'j': second})
    expire(case, second)
    assert cleaner.run_once(case.application, media, 'cl-1')['needs_review'] == 1
    assert (media / other).exists()  # the first job's media was not touched


def test_cli_once_runs_a_round(case, media, published, monkeypatch):
    from app import cleaner as cli
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    expire(case, published)
    assert cli.main(['--once', '--media-root', str(media)])['deleted'] == 1


# C5a review I1: the module entry point really runs a round.
def test_python_m_entry_point_runs_a_round(case, media, published):
    import subprocess
    import sys
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    expire(case, published)
    env = dict(os.environ, DB_URL=case.application.url.render_as_string(hide_password=False), PYTHONPATH=str(backend))
    completed = subprocess.run([sys.executable, '-m', 'app.cleaner', '--once', '--media-root', str(media)],
                               cwd=backend, env=env, capture_output=True, timeout=120)
    assert completed.returncode == 0
    assert state(case, published).media_state == 'deleted'


# C5a review M8: --once reports a storage outage through the exit status.
def test_cli_once_storage_outage_exits_3(case, media, published, monkeypatch):
    from app import cleaner as cli
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    monkeypatch.setattr(cli, 'run_once', lambda *args, **kwargs: dict(marked=0, claimed=0, deleted=0, retry=0,
                                                                     needs_review=0, lost=0, storage_unavailable=1,
                                                                     purged=0, purge_failed=0, purge_mismatched=0,
                legacy_deleted=0, legacy_failed=0, legacy_refused=0,
                legacy_review=0, legacy_storage_unavailable=0, legacy_pending=0))
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(media)])
    assert stop.value.code == 3


def test_cli_refuses_unusable_media_root(case, tmp_path, published, monkeypatch):
    from app import cleaner as cli
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    expire(case, published)
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(tmp_path / 'missing')])
    assert stop.value.code == 2 and state(case, published).media_state == 'available'  # nothing touched


# C5b-1 Task 3: each cleaner round also purges metadata whose retention period has passed.
def test_round_purges_metadata_after_retention(case, cleaner, media, published):
    expire(case, published)
    assert cleaner.run_once(case.application, media, 'cl-1')['deleted'] == 1
    db(case, "UPDATE app.job SET created_at = now() - interval '31 days' WHERE id=:j", j=published)
    db(case, "UPDATE app.downloadidempotency SET expires_at = extract(epoch from now()) - 1")
    assert cleaner.run_once(case.application, media, 'cl-1')['purged'] == 1
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM app.job WHERE id=:j'), {'j': published}) == 0
