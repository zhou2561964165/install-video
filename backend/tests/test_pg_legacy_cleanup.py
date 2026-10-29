"""C6c: expired imported v1 files are deleted by the cleaner round under PostgreSQL (nonce-owned PG)."""
import os

import pytest
from sqlalchemy import text

from test_pg_download_worker import media  # noqa: F401  (fixture)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
OWNER = 'c1-slot'


@pytest.fixture
def cleaner():
    from app.services import cleaner
    return cleaner


@pytest.fixture
def old(tmp_path, submit):
    submit('k-owner')  # creates the owner account
    root = (tmp_path / 'old').resolve()
    root.mkdir()
    from app.services import artifact_store
    artifact_store.provision_legacy_root(root)
    return root


def legacy_job(case, old, job_id, *, expired=True, check='verified', content=b'legacy-media'):
    (old / job_id).mkdir()
    path = old / job_id / 'clip.mp4'
    path.write_bytes(content)
    when = "now() - interval '1 minute'" if expired else "now() + interval '1 hour'"
    db(case, "INSERT INTO app.job (id,url,status,progress,file_path,file_size,created_at,updated_at,expires_at,user_id,"
             f"legacy_check) VALUES (:j,'https://source.synthetic.invalid/v','done',100.0,:p,:s,now(),now(),{when},:u,:c)",
       j=job_id, p=str(path), s=len(content), u=OWNER, c=check)
    return path


def state(case, job_id):
    with case.migration.connect() as connection:
        return tuple(connection.execute(text('SELECT media_state, legacy_check FROM app.job WHERE id=:j'),
                                        {'j': job_id}).one())


def test_expired_verified_file_is_deleted_and_confirmed(case, cleaner, media, old):
    path = legacy_job(case, old, 'l-1')
    counts = cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)
    assert counts['legacy_deleted'] == 1 and not path.exists() and (old / 'l-1').is_dir()
    assert state(case, 'l-1') == ('deleted', 'verified')
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT file_path FROM app.job WHERE id='l-1'")) is None
    assert cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)['legacy_deleted'] == 0


def test_only_expired_verified_v1_files_are_touched(case, cleaner, media, old):
    keep_fresh = legacy_job(case, old, 'l-fresh', expired=False)
    keep_unchecked = legacy_job(case, old, 'l-unchecked', check='unchecked')
    cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)
    assert keep_fresh.exists() and keep_unchecked.exists()
    assert state(case, 'l-fresh') == (None, 'verified') and state(case, 'l-unchecked') == (None, 'unchecked')


def test_reads_answer_gone_after_deletion(case, cleaner, media, old):
    from sqlmodel import Session
    from app.services import file_reads
    legacy_job(case, old, 'l-2')
    cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)
    with Session(case.application) as session:
        with pytest.raises(file_reads.ReadDenied) as error:
            file_reads.open_read(session, OWNER, 'l-2', media_root=media, height_limit=None, legacy_root=old)
    assert (error.value.status, error.value.error_type) == (410, 'file_expired')


def test_already_gone_file_is_confirmed(case, cleaner, media, old):
    legacy_job(case, old, 'l-3').unlink()
    assert cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)['legacy_deleted'] == 1
    assert state(case, 'l-3') == ('deleted', 'verified')


def test_unusable_old_root_changes_nothing(case, cleaner, media, old, tmp_path):
    path = legacy_job(case, old, 'l-4')
    empty = (tmp_path / 'empty-mount').resolve()
    empty.mkdir()
    counts = cleaner.run_once(case.application, media, 'cl-1', legacy_root=empty)
    # A legacy outage is its own signal: the v2 lifecycle and its retention purge keep running.
    assert counts['legacy_deleted'] == 0 and counts['legacy_storage_unavailable'] == 1
    assert counts['storage_unavailable'] == 0
    assert path.exists() and state(case, 'l-4') == (None, 'verified')
    assert cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)['legacy_deleted'] == 1  # retried later


def test_refused_file_is_quarantined_not_retried(case, cleaner, media, old, tmp_path):
    path = legacy_job(case, old, 'l-5')
    os.link(path, tmp_path / 'second-name')  # not this Job's own single-name file
    counts = cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)
    assert counts['legacy_refused'] == 1 and path.exists()
    assert state(case, 'l-5') == ('corrupt', 'mismatch')
    assert cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)['legacy_refused'] == 0


def test_without_an_old_root_v1_files_are_left_alone(case, cleaner, media, old):
    path = legacy_job(case, old, 'l-6')
    counts = cleaner.run_once(case.application, media, 'cl-1')
    assert counts['legacy_deleted'] == 0 and path.exists() and state(case, 'l-6') == (None, 'verified')


def test_locked_job_is_skipped(case, cleaner, media, old):
    path = legacy_job(case, old, 'l-7')
    with case.application.connect() as other:
        transaction = other.begin()
        other.execute(text("SELECT id FROM app.job WHERE id='l-7' FOR UPDATE"))
        assert cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)['legacy_deleted'] == 0
        transaction.rollback()
    assert path.exists()



def test_missing_job_directory_on_the_marked_root_is_confirmed(case, cleaner, media, old):
    import shutil
    legacy_job(case, old, 'l-8')
    shutil.rmtree(old / 'l-8')
    assert cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)['legacy_deleted'] == 1
    assert state(case, 'l-8') == ('deleted', 'verified')


def test_failures_back_off_then_go_to_review(case, cleaner, media, old, monkeypatch):
    from app.services import artifact_store

    def busy(*args, **kwargs):
        raise artifact_store.ArtifactError('artifact_io_failed')  # e.g. a file still open on Windows
    monkeypatch.setattr(cleaner.artifact_store, 'remove_legacy', busy)
    legacy_job(case, old, 'l-9')
    for attempt in range(1, 6):
        counts = cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)
        assert counts['legacy_failed' if attempt < 5 else 'legacy_review'] == 1
        again = cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)
        assert again['legacy_failed'] == again['legacy_review'] == 0  # backoff: not claimed again yet
        db(case, "UPDATE app.job SET updated_at = now() - interval '1 hour' WHERE id='l-9'")
    with case.migration.connect() as connection:
        row = connection.execute(text("SELECT media_state, legacy_cleanup_attempts FROM app.job WHERE id='l-9'")).one()
    assert tuple(row) == ('corrupt', 5)


def test_outside_path_is_a_per_row_failure_not_a_stop(case, cleaner, media, old):
    legacy_job(case, old, 'l-10')
    other = legacy_job(case, old, 'l-11')
    db(case, "UPDATE app.job SET file_path = :p WHERE id='l-10'", p=str(old / 'elsewhere' / 'x.mp4'))
    counts = cleaner.run_once(case.application, media, 'cl-1', legacy_root=old)
    assert counts['legacy_failed'] == 1 and counts['legacy_deleted'] == 1 and not other.exists()


def test_pending_files_are_reported_when_no_old_root_is_configured(case, cleaner, media, old):
    legacy_job(case, old, 'l-12')
    assert cleaner.run_once(case.application, media, 'cl-1')['legacy_pending'] == 1
