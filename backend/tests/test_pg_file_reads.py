"""C4 Task 2: read decisions, read leases and safe open on nonce-owned PG with a really published file."""
import os
import threading
import time

import pytest
from sqlalchemy import text
from sqlmodel import Session

from test_pg_download_worker import media, worker  # noqa: F401  (fixtures)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
OWNER = 'c1-slot'  # the submitting user created by the submit fixture


@pytest.fixture
def reads():
    from app.services import file_reads
    return file_reads


@pytest.fixture
def published(case, worker, media, submit):
    job = submit('k1').job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:5000',
                           heartbeat_seconds=0.3, poll_seconds=0.02) == 'published'
    return job


def open_read(case, reads, media, job, *, user=OWNER, height_limit=None):
    with Session(case.application) as session:
        return reads.open_read(session, user, job, media_root=media, height_limit=height_limit)


def denied(case, reads, media, job, **options):
    with pytest.raises(reads.ReadDenied) as error:
        open_read(case, reads, media, job, **options)
    return error.value.status, error.value.error_type


def leases(case, job):
    with case.migration.connect() as connection:
        return connection.execute(text(
            'SELECT id, ended_at, extract(epoch from lease_deadline - started_at) AS lease, '
            'extract(epoch from max_until - started_at) AS span FROM app.filereadlease WHERE job_id=:j'),
            {'j': job}).all()


def test_owner_read_opens_file_and_records_lease(case, reads, media, published):
    opened = open_read(case, reads, media, published)
    try:
        assert opened.size == 5000 and opened.media_format == 'mp4' and opened.etag.startswith('"')
        assert opened.file.read() == b'\0' * 5000
    finally:
        opened.file.close()
    [lease] = leases(case, published)
    assert lease.id == opened.read_id and lease.ended_at is None
    assert 29 <= lease.lease <= 30 and 1799 <= lease.span <= 1800


def test_non_owner_and_unknown_job_are_not_found(case, reads, media, published):
    assert denied(case, reads, media, published, user='someone-else') == (404, 'file_missing')
    assert denied(case, reads, media, 'no-such-job') == (404, 'file_missing')
    assert leases(case, published) == []


def test_height_limit_below_submitted_access_is_forbidden(case, reads, media, published):
    # The submission snapshot allowed 720p; a current free limit of 480 may not read it.
    assert denied(case, reads, media, published, height_limit=480) == (403, 'membership_required')
    assert open_read(case, reads, media, published, height_limit=720).file.close() is None


def test_expired_new_read_is_gone_without_cleaner(case, reads, media, published):
    db(case, "UPDATE app.job SET expires_at = now() - interval '1 second' WHERE id=:j", j=published)
    assert denied(case, reads, media, published) == (410, 'file_expired')
    assert leases(case, published) == []


@pytest.mark.parametrize('state,expected', [('expired', (410, 'file_expired')), ('deleting', (410, 'file_expired')),
                                            ('deleted', (410, 'file_expired')), ('missing', (404, 'file_missing')),
                                            ('corrupt', (404, 'file_missing'))])
def test_media_state_decides_gone_or_missing(case, reads, media, published, state, expected):
    db(case, 'UPDATE app.job SET media_state=:s WHERE id=:j', s=state, j=published)
    assert denied(case, reads, media, published) == expected


def test_unpublished_job_is_not_found(case, reads, media, submit):
    job = submit('k1').job_id
    assert denied(case, reads, media, job) == (404, 'file_missing')


def test_size_mismatch_is_not_found(case, reads, media, published):
    with case.migration.connect() as connection:
        relative = connection.scalar(text('SELECT relative_path FROM app.artifactmanifest WHERE job_id=:j'),
                                     {'j': published})
    with open(media / relative, 'ab') as handle:
        handle.write(b'x')
    assert denied(case, reads, media, published) == (404, 'file_missing')
    assert leases(case, published) == []


@pytest.mark.skipif(os.name != 'nt', reason='junction escape is Windows-specific (PG suites run on Windows)')
def test_junction_escape_is_not_found(case, reads, media, published, tmp_path):
    import _winapi
    import shutil
    job_dir = media / published
    outside = tmp_path / 'outside'
    shutil.copytree(job_dir, outside)
    shutil.rmtree(job_dir)
    _winapi.CreateJunction(str(outside), str(job_dir))
    assert denied(case, reads, media, published) == (404, 'file_missing')


def test_renew_caps_at_max_until_and_end_stops_renewal(case, reads, media, published):
    opened = open_read(case, reads, media, published)
    opened.file.close()
    db(case, "UPDATE app.filereadlease SET max_until = lease_deadline WHERE id=:r", r=opened.read_id)
    with Session(case.application) as session:
        assert reads.renew_read(session, opened.read_id) is True
        session.commit()
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT lease_deadline <= max_until FROM app.filereadlease WHERE id=:r'),
                                 {'r': opened.read_id})
    db(case, "UPDATE app.filereadlease SET lease_deadline = now() - interval '1 second', "
             "max_until = now() - interval '1 second' WHERE id=:r", r=opened.read_id)
    with Session(case.application) as session:
        assert reads.renew_read(session, opened.read_id) is False  # an expired read lease never revives
        reads.end_read(session, opened.read_id)
        session.commit()
    assert leases(case, published)[0].ended_at is not None


def test_end_read_stops_further_renewal(case, reads, media, published):
    opened = open_read(case, reads, media, published)
    opened.file.close()
    with Session(case.application) as session:
        reads.end_read(session, opened.read_id)
        session.commit()
    with Session(case.application) as session:
        assert reads.renew_read(session, opened.read_id) is False


def test_new_read_waits_for_job_lock_and_rechecks_expiry(case, reads, media, published):
    # A cleaner holds the Job (FOR UPDATE) while marking it expired; a read arriving meanwhile must wait
    # for that decision and must not start on a file about to be deleted.
    outcome = {}
    with case.migration.connect() as cleaner:
        transaction = cleaner.begin()
        cleaner.execute(text('SELECT id FROM app.job WHERE id=:j FOR UPDATE'), {'j': published})

        def read():
            try:
                open_read(case, reads, media, published).file.close()
                outcome['value'] = 'opened'
            except reads.ReadDenied as error:
                outcome['value'] = (error.status, error.error_type)

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        assert waiting_on_lock(case), 'read did not wait for the Job lock'  # proof by state, inside lock_timeout
        assert thread.is_alive()
        cleaner.execute(text("UPDATE app.job SET media_state='expired' WHERE id=:j"), {'j': published})
        transaction.commit()
    thread.join(15)
    assert outcome['value'] == (410, 'file_expired')


def waiting_on_lock(case, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Same role as the waiting reader: PostgreSQL shows wait events of other roles only to privileged users.
        with case.application.connect() as connection:
            if connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                      "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()")) > 0:
                return True
        time.sleep(0.05)
    return False


# C4 review C1: once open_read returns, no transaction (and so no pooled connection) stays open.
def test_open_read_leaves_no_transaction_open(case, reads, media, published):
    with Session(case.application) as session:
        opened = reads.open_read(session, OWNER, published, media_root=media, height_limit=None)
        try:
            assert not session.in_transaction()
            assert (opened.size, opened.media_format) == (5000, 'mp4') and opened.etag.startswith('"sha256-')
        finally:
            opened.file.close()


# C4 review I5 / ruling C4-2: a cleaner holding the Job past lock_timeout makes the read busy (503), not an error.
def test_lock_timeout_is_busy(case, reads, media, published):
    with case.migration.connect() as cleaner:
        transaction = cleaner.begin()
        cleaner.execute(text('SELECT id FROM app.job WHERE id=:j FOR UPDATE'), {'j': published})
        try:
            assert denied(case, reads, media, published) == (503, 'file_busy')
        finally:
            transaction.rollback()
    assert leases(case, published) == []


# C4 review I5: the reverse order. A read in progress holds the Job; the cleaner cannot take it, and once the
# read commits the cleaner sees its live lease (so it will not unlink under it).
def test_cleaner_cannot_take_job_while_read_decides(case, reads, media, published, monkeypatch):
    from sqlalchemy.exc import OperationalError
    entered, release = threading.Event(), threading.Event()
    real = reads.artifact_store.open_published

    def paused(*args, **kwargs):
        entered.set()
        release.wait(10)
        return real(*args, **kwargs)
    monkeypatch.setattr(reads.artifact_store, 'open_published', paused)
    out = {}
    thread = threading.Thread(target=lambda: out.setdefault('read', open_read(case, reads, media, published)),
                              daemon=True)
    thread.start()
    assert entered.wait(10)
    with case.migration.connect() as cleaner:
        with pytest.raises(OperationalError):
            with cleaner.begin():
                cleaner.execute(text('SELECT id FROM app.job WHERE id=:j FOR UPDATE NOWAIT'), {'j': published})
    release.set()
    thread.join(15)
    out['read'].file.close()
    with case.migration.connect() as cleaner:
        with cleaner.begin():
            cleaner.execute(text('SELECT id FROM app.job WHERE id=:j FOR UPDATE NOWAIT'), {'j': published})
            assert cleaner.scalar(text('SELECT count(*) FROM app.filereadlease WHERE job_id=:j AND ended_at IS NULL '
                                       'AND lease_deadline > now()'), {'j': published}) == 1


# C4 review I4: a missing or unsafe storage root is an outage (503), not "file missing" (404).
def test_unusable_storage_root_is_unavailable(case, reads, media, published):
    assert denied(case, reads, media.parent / 'not-mounted', published) == (503, 'file_storage_unavailable')
    assert leases(case, published) == []


# C6a: a published file found missing or corrupt is revoked at once (no automatic re-download).
def media_facts(case, job):
    with case.migration.connect() as connection:
        return tuple(connection.execute(text(
            'SELECT media_state, error_type, internal_state FROM app.job WHERE id=:j'), {'j': job}).one())


def published_file(case, media, job):
    with case.migration.connect() as connection:
        return media / connection.scalar(text('SELECT relative_path FROM app.artifactmanifest WHERE job_id=:j'),
                                         {'j': job})


def test_missing_file_is_revoked_on_read(case, reads, media, published):
    published_file(case, media, published).unlink()
    assert denied(case, reads, media, published) == (404, 'file_missing')
    assert media_facts(case, published) == ('missing', 'media_missing', 'succeeded')
    assert denied(case, reads, media, published) == (404, 'file_missing')  # from the state, no file access
    assert leases(case, published) == []


def test_corrupt_file_is_revoked_on_read(case, reads, media, published):
    with open(published_file(case, media, published), 'ab') as handle:
        handle.write(b'x')
    assert denied(case, reads, media, published) == (404, 'file_missing')
    assert media_facts(case, published) == ('corrupt', 'media_corrupt', 'succeeded')


def test_outage_or_transient_error_never_revokes(case, reads, media, published, monkeypatch):
    assert denied(case, reads, media.parent / 'not-mounted', published) == (503, 'file_storage_unavailable')
    published_file(case, media, published).unlink()
    monkeypatch.setattr(reads.artifact_store, 'diagnose_published', lambda *args: None)  # transient
    assert denied(case, reads, media, published) == (404, 'file_missing')
    assert media_facts(case, published) == ('available', None, 'succeeded')


def test_revocation_never_overrides_a_lifecycle_change(case, reads, media, published, monkeypatch):
    published_file(case, media, published).unlink()
    real = reads.artifact_store.diagnose_published

    def cleaner_meanwhile(*args):
        db(case, "UPDATE app.job SET media_state='expired' WHERE id=:j", j=published)
        return real(*args)
    monkeypatch.setattr(reads.artifact_store, 'diagnose_published', cleaner_meanwhile)
    assert denied(case, reads, media, published) == (404, 'file_missing')
    assert media_facts(case, published)[0] == 'expired'


def test_revoked_job_is_left_to_a_person(case, reads, media, published):
    from app.services import cleaner
    published_file(case, media, published).unlink()
    denied(case, reads, media, published)
    db(case, "UPDATE app.job SET expires_at = now() - interval '1 second' WHERE id=:j", j=published)
    counts = cleaner.run_once(case.application, media, 'cl-1')
    assert (counts['marked'], counts['claimed'], counts['purged']) == (0, 0, 0)
    assert media_facts(case, published)[0] == 'missing'


# C6b: an imported v1 Job whose file was verified at import is readable under the new contract.
LEGACY = 'legacy-job-1'


@pytest.fixture
def legacy_file(case, tmp_path, submit):
    submit('k-user')  # creates the owner account
    old = (tmp_path / 'old').resolve()
    (old / LEGACY).mkdir(parents=True)
    path = old / LEGACY / 'clip.mp4'
    path.write_bytes(b'legacy-media')
    db(case, "INSERT INTO app.job (id,url,status,progress,file_path,file_size,created_at,updated_at,expires_at,user_id,"
             "legacy_check) VALUES (:j,'https://source.synthetic.invalid/v','done',100.0,:p,12,now(),now(),"
             "now() + interval '1 hour',:u,'verified')", j=LEGACY, p=str(path), u=OWNER)
    return old, path


def legacy_read(case, reads, media, old, *, user=OWNER, height_limit=None):
    with Session(case.application) as session:
        return reads.open_read(session, user, LEGACY, media_root=media, height_limit=height_limit, legacy_root=old)


def legacy_denied(case, reads, media, old, **options):
    with pytest.raises(reads.ReadDenied) as error:
        legacy_read(case, reads, media, old, **options)
    return error.value.status, error.value.error_type


def test_verified_legacy_file_is_readable_without_a_read_lease(case, reads, media, legacy_file):
    old, path = legacy_file
    opened = legacy_read(case, reads, media, old)
    with opened.file as handle:
        assert handle.read() == b'legacy-media'
    assert (opened.read_id, opened.size, opened.media_format) == (None, 12, 'mp4')
    assert leases(case, LEGACY) == []


def test_legacy_read_follows_the_new_contract_order(case, reads, media, legacy_file):
    old, path = legacy_file
    assert legacy_denied(case, reads, media, old, user='someone-else') == (404, 'file_missing')
    db(case, "INSERT INTO app.downloadaccess (job_id, max_height) VALUES (:j, 1080)", j=LEGACY)
    assert legacy_denied(case, reads, media, old, height_limit=720) == (403, 'membership_required')
    db(case, "UPDATE app.job SET expires_at = now() - interval '1 second' WHERE id=:j", j=LEGACY)
    assert legacy_denied(case, reads, media, old, height_limit=1080) == (410, 'file_expired')


@pytest.mark.parametrize('check', ['missing', 'mismatch', 'unchecked', None])
def test_only_verified_legacy_files_are_readable(case, reads, media, legacy_file, check):
    old, path = legacy_file
    db(case, 'UPDATE app.job SET legacy_check=:c WHERE id=:j', c=check, j=LEGACY)
    assert legacy_denied(case, reads, media, old) == (404, 'file_missing')


def test_without_the_old_root_nothing_is_read(case, reads, media, legacy_file):
    assert legacy_denied(case, reads, media, None) == (404, 'file_missing')


def test_legacy_file_gone_is_revoked_once(case, reads, media, legacy_file):
    old, path = legacy_file
    path.unlink()
    assert legacy_denied(case, reads, media, old) == (404, 'file_missing')
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT legacy_check FROM app.job WHERE id=:j'), {'j': LEGACY}) == 'missing'


def test_unusable_old_root_is_an_outage_not_a_revocation(case, reads, media, legacy_file, tmp_path):
    assert legacy_denied(case, reads, media, tmp_path / 'not-mounted') == (503, 'file_storage_unavailable')
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT legacy_check FROM app.job WHERE id=:j'), {'j': LEGACY}) == 'verified'



# C6b review M6/M2/M1: mismatch revocation, CAS never overwrites, no expiry is never readable, ETag identity.
def test_legacy_size_change_is_revoked_as_mismatch_once(case, reads, media, legacy_file):
    old, path = legacy_file
    path.write_bytes(b'longer-legacy-media')
    assert legacy_denied(case, reads, media, old) == (404, 'file_missing')
    db(case, "UPDATE app.job SET legacy_check='unchecked' WHERE id=:j", j=LEGACY)  # later operator decision
    assert legacy_denied(case, reads, media, old) == (404, 'file_missing')
    with case.migration.connect() as connection:
        assert connection.scalar(text('SELECT legacy_check FROM app.job WHERE id=:j'), {'j': LEGACY}) == 'unchecked'


def test_legacy_without_expiry_is_not_readable(case, reads, media, legacy_file):
    old, path = legacy_file
    db(case, 'UPDATE app.job SET expires_at=NULL WHERE id=:j', j=LEGACY)
    assert legacy_denied(case, reads, media, old) == (404, 'file_missing')


def test_legacy_etag_changes_when_the_file_is_replaced(case, reads, media, legacy_file):
    old, path = legacy_file
    opened = legacy_read(case, reads, media, old)
    opened.file.close()
    path.unlink()
    path.write_bytes(b'LEGACY-MEDIA')  # same size, different file
    second = legacy_read(case, reads, media, old)
    second.file.close()
    assert opened.etag != second.etag and opened.etag.startswith('"legacy-')


def test_unknown_suffix_falls_back_to_bin(case, reads, media, legacy_file):
    old, path = legacy_file
    odd = path.with_name('clip.weird-suffix')
    path.rename(odd)
    db(case, 'UPDATE app.job SET file_path=:p WHERE id=:j', p=str(odd), j=LEGACY)
    opened = legacy_read(case, reads, media, old)
    opened.file.close()
    assert opened.media_format == 'bin'
