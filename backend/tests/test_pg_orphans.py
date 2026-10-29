"""C5b-2: orphan inventory and reclamation on nonce-owned PG with a real provisioned media root."""
import os
import uuid

import pytest
from sqlalchemy import text

from test_pg_cleanup_repository import expire  # noqa: F401  (helpers)
from test_pg_download_worker import media, worker  # noqa: F401  (fixtures)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')


@pytest.fixture
def orphans():
    from app.services import orphans
    return orphans


def inventory(case):
    with case.migration.connect() as connection:
        return {row.relative_path: (row.kind, row.state) for row in connection.execute(text(
            'SELECT relative_path, kind, state FROM app.orphanobject'))}


def backdate(case, relative_path, hours=25):
    db(case, f"UPDATE app.orphanobject SET first_seen_at = now() - interval '{hours} hours' "
             "WHERE relative_path=:p", p=relative_path)


def publish(case, worker, media, submit, key='k1'):
    job = submit(key).job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:100', heartbeat_seconds=0.3,
                           poll_seconds=0.02) == 'published'
    return job


def test_unowned_attempt_directory_is_listed_then_reclaimed_after_24h(case, orphans, media):
    stray = f'{uuid.uuid4()}/1-{uuid.uuid4()}'
    (media / stray).mkdir(parents=True)
    (media / stray / 'media.part').write_bytes(b'x')
    first = orphans.run_once(case.application, media)
    assert first['listed'] >= 1 and inventory(case)[stray] == ('attempt_dir', 'listed')
    assert (media / stray).exists()  # never removed inside the grace period
    backdate(case, stray)
    assert orphans.run_once(case.application, media)['removed'] >= 1
    assert not (media / stray).exists() and inventory(case)[stray] == ('attempt_dir', 'removed')


def test_published_media_is_never_listed(case, orphans, worker, media, submit):
    job = publish(case, worker, media, submit)
    orphans.run_once(case.application, media)
    assert not any(path.startswith(job) for path in inventory(case))


def test_failed_attempt_leaves_an_empty_job_dir_that_is_reclaimed(case, orphans, worker, media, submit):
    job = submit('k1').job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:error:http_412', heartbeat_seconds=0.3,
                           poll_seconds=0.02) == 'failed'
    assert (media / job).is_dir() and list((media / job).iterdir()) == []  # the worker discarded its attempt
    orphans.run_once(case.application, media)
    assert inventory(case)[job] == ('job_dir', 'listed')
    backdate(case, job)
    orphans.run_once(case.application, media)
    assert not (media / job).exists() and inventory(case)[job] == ('job_dir', 'removed')


def test_cleaner_prunes_the_job_dir_so_nothing_is_left_to_scan(case, orphans, worker, media, submit):
    from app.services import cleaner
    job = publish(case, worker, media, submit)
    expire(case, job)
    assert cleaner.run_once(case.application, media, 'cl-1')['deleted'] == 1
    assert not (media / job).exists()
    orphans.run_once(case.application, media)
    assert job not in inventory(case)


# Review I4: a job directory is owned while its Job can still create an attempt.
def test_job_dir_of_an_unfinished_job_is_owned(case, orphans, media, submit):
    job = submit('k1').job_id  # queued, not yet claimed
    (media / job).mkdir()
    orphans.run_once(case.application, media)
    assert job not in inventory(case)


def test_running_attempt_dir_is_owned(case, orphans, media, submit):
    from sqlmodel import Session
    from app.services import artifact_store, job_repository
    job = submit('k1').job_id
    with Session(case.application) as session:
        token = job_repository.claim_next(session, 'w1')
        session.commit()
    artifact_store.prepare_attempt(media, job, token.epoch, token.attempt_id)
    orphans.run_once(case.application, media)
    assert not any(path.startswith(job) for path in inventory(case))


# Review M5: a live read lease always owns its attempt directory (defence in depth).
def test_attempt_with_a_live_read_lease_is_owned(case, orphans, worker, media, submit):
    from sqlmodel import Session
    from app.services import file_reads
    job = publish(case, worker, media, submit)
    with Session(case.application) as session:
        file_reads.open_read(session, 'c1-slot', job, media_root=media, height_limit=None).file.close()
    db(case, "UPDATE app.job SET media_state='deleted' WHERE id=:j", j=job)  # even if the state says deleted
    orphans.run_once(case.application, media)
    assert not any(path.startswith(job) for path in inventory(case))


# Review M6/M7: objects that turn unsafe, or that removal refuses deterministically, are quarantined.
def test_listed_attempt_turning_into_a_junction_is_quarantined(case, orphans, media, tmp_path):
    import _winapi
    import shutil
    stray = f'{uuid.uuid4()}/1-{uuid.uuid4()}'
    (media / stray).mkdir(parents=True)
    orphans.run_once(case.application, media)
    assert inventory(case)[stray] == ('attempt_dir', 'listed')
    outside = tmp_path / 'outside'
    outside.mkdir()
    shutil.rmtree(media / stray)
    _winapi.CreateJunction(str(outside), str(media / stray))
    orphans.run_once(case.application, media)
    assert inventory(case)[stray] == ('unknown', 'quarantined')


def test_removal_refused_for_unknown_content_is_quarantined(case, orphans, media):
    stray = f'{uuid.uuid4()}/1-{uuid.uuid4()}'
    (media / stray).mkdir(parents=True)
    (media / stray / 'unexpected.bin').write_bytes(b'x')
    orphans.run_once(case.application, media)
    backdate(case, stray)
    orphans.run_once(case.application, media)
    assert inventory(case)[stray] == ('attempt_dir', 'quarantined') and (media / stray / 'unexpected.bin').exists()


# Review M8: a second scanner never fails on the first one's rows; it skips the round.
def test_concurrent_scanner_skips_the_round(case, orphans, media):
    with case.application.connect() as other:
        transaction = other.begin()
        other.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': orphans.SCANNER_LOCK_KEY})
        assert orphans.run_once(case.application, media)['skipped'] == 1
        transaction.rollback()
    assert orphans.run_once(case.application, media)['skipped'] == 0


# Review I3: inventory history (removed/released) is purged after the retention period.
def test_inventory_history_is_purged(case, orphans, media):
    db(case, "INSERT INTO app.orphanobject (relative_path,kind,state,first_seen_at,last_seen_at,updated_at) VALUES "
             "('old-removed','probe_file','removed',now()-interval '60 days',now()-interval '60 days',"
             "now()-interval '40 days'), ('recent-removed','probe_file','removed',now(),now(),now())")
    orphans.run_once(case.application, media)
    assert set(inventory(case)) >= {'recent-removed'} and 'old-removed' not in inventory(case)


# Review I2: a bounded scan resumes from its cursor, so every entry is eventually seen.
def test_scan_cursor_reaches_every_entry(case, orphans, media, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'orphan_scan_limit', 100)
    names = sorted(str(uuid.uuid4()) for _ in range(150))
    for name in names:
        (media / name).mkdir()
    first = orphans.run_once(case.application, media)
    assert first['next_cursor'] is not None
    second = orphans.run_once(case.application, media, start_after=first['next_cursor'])
    assert second['next_cursor'] is None  # wrapped: the next round starts from the beginning again
    assert set(names) <= set(inventory(case))


# Review M9: a failed scan makes --once exit 1.
def test_cli_once_scan_failure_exits_1(case, media, monkeypatch):
    from app import orphans as cli
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    monkeypatch.setattr(cli, 'run_once', lambda *args, **kwargs: dict(
        scanned=0, listed=0, quarantined=0, released=0, removed=0, failed=1, storage_unavailable=0, skipped=0,
        purged=0, scan_failed=1, next_cursor=None))
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(media)])
    assert stop.value.code == 1


def test_unknown_objects_stay_quarantined_forever(case, orphans, media):
    (media / 'stray.txt').write_bytes(b'operator note')
    orphans.run_once(case.application, media)
    assert inventory(case)['stray.txt'] == ('unknown', 'quarantined')
    backdate(case, 'stray.txt', hours=24 * 30)
    orphans.run_once(case.application, media)
    assert (media / 'stray.txt').exists() and inventory(case)['stray.txt'] == ('unknown', 'quarantined')


def test_probe_leftover_is_reclaimed_after_24h(case, orphans, media):
    probe = '.probe-1-' + 'cd' * 8 + '.part'
    (media / probe).write_bytes(b'x')
    orphans.run_once(case.application, media)
    backdate(case, probe)
    orphans.run_once(case.application, media)
    assert not (media / probe).exists() and inventory(case)[probe] == ('probe_file', 'removed')


def test_listed_object_that_regains_ownership_is_released(case, orphans, worker, media, submit):
    job = publish(case, worker, media, submit)
    with case.migration.connect() as connection:
        attempt = connection.scalar(text('SELECT visible_attempt_id FROM app.job WHERE id=:j'), {'j': job})
    path = f'{job}/1-{attempt}'
    db(case, "INSERT INTO app.orphanobject (relative_path,kind,state,first_seen_at,last_seen_at,updated_at) "
             "VALUES (:p,'attempt_dir','listed',now()-interval '30 hours',now(),now())", p=path)
    result = orphans.run_once(case.application, media)
    assert result['released'] >= 1 and inventory(case)[path] == ('attempt_dir', 'released')
    assert (media / path).exists()  # published media is never touched


def test_storage_outage_changes_nothing(case, orphans, media, tmp_path):
    empty = tmp_path / 'empty-mount'
    empty.mkdir()
    assert orphans.run_once(case.application, empty.resolve())['storage_unavailable'] == 1
    assert inventory(case) == {}


def test_cli_once_and_refused_root(case, media, monkeypatch, tmp_path):
    from app import orphans as cli
    monkeypatch.setattr(cli, 'build_engine', lambda *args, **kwargs: case.application)
    assert cli.main(['--once', '--media-root', str(media)])['storage_unavailable'] == 0
    with pytest.raises(SystemExit) as stop:
        cli.main(['--once', '--media-root', str(tmp_path / 'missing')])
    assert stop.value.code == 2


# C5b-2 Task 1: schema (c5b_0011).
def test_orphan_chain_follows_retention():
    from alembic.script import ScriptDirectory
    from app import db as app_db
    script = ScriptDirectory.from_config(app_db.migration_config())
    assert script.get_revision('c5b_0011').down_revision == 'c5b_0010'
    assert 'c5b_0010' not in script.get_heads()


@pytest.mark.parametrize('kind,state,path', [('unknown', 'listed', 'x'), ('attempt_dir', 'gone', 'x'),
                                             ('folder', 'listed', 'x'), ('job_dir', 'listed', '')])
def test_orphan_constraints(case, kind, state, path):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db(case, "INSERT INTO app.orphanobject (relative_path,kind,state,first_seen_at,last_seen_at,updated_at) "
                 "VALUES (:p,:k,:s,now(),now(),now())", p=path, k=kind, s=state)


def test_orphan_grants_and_downgrade(case):
    with case.migration.connect() as connection:
        granted = {privilege for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')
                   if connection.scalar(text("SELECT has_table_privilege('pv_app','app.orphanobject',:p)"),
                                        {'p': privilege})}
    assert granted == {'SELECT', 'INSERT', 'UPDATE', 'DELETE'}  # DELETE only for inventory history purge
    db(case, "INSERT INTO app.orphanobject (relative_path,kind,state,first_seen_at,last_seen_at,updated_at) "
             "VALUES ('x','probe_file','listed',now(),now(),now())")
    with pytest.raises(Exception):
        case.migrate(action='downgrade', target='c5b_0010')
    db(case, 'DELETE FROM app.orphanobject')
    case.migrate(action='downgrade', target='c5b_0010')
    with case.migration.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('app.orphanobject')")) is None


# The re-check right before removal is the last guard (ownership may return between record and removal).
def test_removal_rechecks_ownership_even_when_the_scan_did_not(case, orphans, worker, media, submit, monkeypatch):
    job = publish(case, worker, media, submit)
    with case.migration.connect() as connection:
        attempt = connection.scalar(text('SELECT visible_attempt_id FROM app.job WHERE id=:j'), {'j': job})
    path = f'{job}/1-{attempt}'
    db(case, "INSERT INTO app.orphanobject (relative_path,kind,state,first_seen_at,last_seen_at,updated_at) "
             "VALUES (:p,'attempt_dir','listed',now()-interval '30 hours',now(),now())", p=path)
    monkeypatch.setattr(orphans, 'record_scan', lambda session, entries: {})  # the scan did not see it
    result = orphans.run_once(case.application, media)
    assert result['released'] == 1 and result['removed'] == 0
    assert (media / path / 'media.mp4').exists()  # published media survives


# Review M11: ownership matches the exact attempt; a directory with the right id but another epoch is not owned.
def test_attempt_dir_with_a_foreign_epoch_is_not_owned(case, orphans, media, submit):
    from sqlmodel import Session
    from app.services import job_repository
    job = submit('k1').job_id
    with Session(case.application) as session:
        token = job_repository.claim_next(session, 'w1')
        session.commit()
    stray = f'{job}/{token.epoch + 7}-{token.attempt_id}'
    (media / stray).mkdir(parents=True)
    orphans.run_once(case.application, media)
    assert inventory(case)[stray] == ('attempt_dir', 'listed')


# A removed object that reappears starts a new 24 h grace period instead of being removed at once.
def test_reappeared_object_gets_a_new_grace_period(case, orphans, media):
    stray = f'{uuid.uuid4()}/1-{uuid.uuid4()}'
    (media / stray).mkdir(parents=True)
    orphans.run_once(case.application, media)
    backdate(case, stray)
    orphans.run_once(case.application, media)
    assert inventory(case)[stray] == ('attempt_dir', 'removed')
    (media / stray).mkdir(parents=True)
    orphans.run_once(case.application, media)
    assert inventory(case)[stray] == ('attempt_dir', 'listed')
    orphans.run_once(case.application, media)
    assert (media / stray).exists()
