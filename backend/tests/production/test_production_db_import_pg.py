"""B6 E3: import_snapshot / verify_snapshot on nonce-owned PG at head, from real exported legacy bundles.

Run via run_b6_import_pg.py (nonce-owned DBs, private bundle parent, pv_verify preserved).
"""
import os
from pathlib import Path
import sqlite3
import uuid

import pytest
from sqlalchemy import text

from tools import production_db_export as export
from tools import production_db_import as importer
import tools.production_db_snapshot_read_contract as rc

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
FIXTURES = Path(__file__).parent / 'fixtures' / 'snapshot_catalog'
T0 = '2026-10-01 08:00:00.000000'


@pytest.fixture
def target():
    from b3b_pg_helpers import isolated_database
    with isolated_database(target='head') as database:
        yield database


@pytest.fixture
def legacy_root(tmp_path):
    root = tmp_path / 'legacy'
    (root / 'j-done').mkdir(parents=True)
    (root / 'j-done' / 'clip.mp4').write_bytes(b'x' * 10)
    (root / 'j-short').mkdir()
    (root / 'j-short' / 'clip.mp4').write_bytes(b'x' * 3)
    return root.resolve()


def legacy_db(tmp_path, legacy_root, *, extra_sql=''):
    path = tmp_path / f'legacy-{uuid.uuid4().hex[:8]}.db'
    writer = sqlite3.connect(str(path))
    try:
        writer.executescript((FIXTURES / 'sqlite9.sql').read_text('utf8'))
        writer.executemany('INSERT INTO user VALUES (?,?,?,?)', [
            ('u1', 'u1@synthetic.invalid', 'h1', T0), ('u2', 'u2@synthetic.invalid', 'h2', '2026-10-02 09:30:00')])
        jobs = [('j-queued', 'queued', None, None), ('j-down', 'downloading', None, None),
                ('j-merge', 'merging', None, None), ('j-error', 'error', None, None),
                ('j-done', 'done', str(legacy_root / 'j-done' / 'clip.mp4'), 10),
                ('j-short', 'done', str(legacy_root / 'j-short' / 'clip.mp4'), 10),
                ('j-gone', 'done', str(legacy_root / 'j-gone' / 'clip.mp4'), 10),
                ('j-outside', 'done', str(legacy_root / 'j-done' / 'clip.mp4'), 10)]
        writer.executemany('INSERT INTO job VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
            (job_id, 'https://source.synthetic.invalid/' + job_id, 'title', 'best', status,
             100.0 if status == 'done' else 0.0, file_path, size, None, None, T0, T0, None, 'u1')
            for job_id, status, file_path, size in jobs])
        writer.execute("INSERT INTO downloadaccess VALUES ('j-done', 720)")
        writer.executemany('INSERT INTO downloadidempotency VALUES (?,?,?,?,?,?,?,?,?,?)', [
            ('r1', 'u1', 'k1', 'f' * 64, 'complete', 1.0, 2.0, None, 200, '{}'),
            ('r2', 'u2', 'k2', 'e' * 64, 'pending', 1.0, None, None, None, None)])
        writer.execute("INSERT INTO quota VALUES ('q1','u1','2026-10-01',2,20)")
        writer.execute("INSERT INTO membership VALUES ('u1','cus_1','sub_1','active',1900000000.5,0,NULL,3,'stripe')")
        writer.execute("INSERT INTO billingcheckout VALUES ('c1','u1','price_1','payment',30,'http://localhost:5173',"
                       "NULL,1.5,'cs_1',NULL,2.5,'paid',1)")
        writer.execute("INSERT INTO billingevent VALUES ('evt_1', 3.5)")
        writer.execute("INSERT INTO billingpayment VALUES ('pi_1','u1','c1',0)")
        if extra_sql:
            writer.executescript(extra_sql)
        writer.commit()
    finally:
        writer.close()
    return str(path.resolve())


def bundle(path):
    destination = os.environ['B6_BUNDLE_PARENT'] + os.sep + 'imp-' + uuid.uuid4().hex[:12]
    with rc._open_synthetic_sqlite(path) as (connection, contract):
        result = export.export_snapshot(connection, destination, driver_contract=contract, trusted_parent_ack=True)
    assert result.status == 'published'
    return destination + os.sep + 'manifest.json'


def counts(engine, *tables):
    with engine.connect() as connection:
        return {name: connection.scalar(text(f'SELECT count(*) FROM app."{name}"')) for name in tables}


def run_import(manifest, target, **options):
    options.setdefault('allow_synthetic', True)  # test bundles are synthetic; production refuses them
    return importer.import_snapshot(manifest, target.migration, trusted_parent_ack=True, **options)


def run_verify(manifest, target, **options):
    options.setdefault('allow_synthetic', True)
    return importer.verify_snapshot(manifest, target.migration, trusted_parent_ack=True, **options)


def test_dry_run_import_verify_and_idempotence(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    dry = run_import(manifest, target, legacy_media_root=str(legacy_root))
    assert dry.status == 'dry_run_ok' and dry.table_rows['job'] == 8
    assert counts(target.migration, 'user', 'job', 'dataimport') == {'user': 0, 'job': 0, 'dataimport': 0}
    done = run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    assert done.status == 'imported' and done.manifest_sha256 == dry.manifest_sha256
    assert done.table_rows == {'billingcheckout': 1, 'billingevent': 1, 'billingpayment': 1, 'downloadaccess': 1,
                               'downloadidempotency': 2, 'job': 8, 'membership': 1, 'quota': 1, 'user': 2}
    assert done.transforms == {'job_legacy_hold': 3, 'job_legacy_verified': 1, 'job_legacy_mismatch': 2,
                               'job_legacy_missing': 1}
    with target.migration.connect() as connection:
        jobs = dict(connection.execute(text('SELECT id, coalesce(internal_state, legacy_check) FROM app.job')).all())
        assert jobs == {'j-queued': 'legacy_hold', 'j-down': 'legacy_hold', 'j-merge': 'legacy_hold', 'j-error': None,
                        'j-done': 'verified', 'j-short': 'mismatch', 'j-gone': 'missing', 'j-outside': 'mismatch'}
        assert connection.scalar(text("SELECT count(*) FROM app.job WHERE execution_version=1 AND epoch=0")) == 8
        counter = connection.scalar(text("SELECT used FROM app.resourcecounter WHERE resource='receipt_entries'"))
        assert counter == 2  # recomputed from the imported receipts, as b1b_0002 seeds it in place
        checkout = connection.execute(text('SELECT reconcile_attempts, revision, fulfilled FROM app.billingcheckout')).one()
        assert tuple(checkout) == (0, 0, True)
        assert connection.scalar(text('SELECT provider_account_scope FROM app.billingevent')) == 'legacy_unknown'
        created = connection.scalar(text("SELECT created_at FROM app.\"user\" WHERE id='u1'"))
        assert created.isoformat() == '2026-10-01T08:00:00+00:00'  # naive SQLite UTC kept as UTC
    verified = run_verify(manifest, target, legacy_media_root=str(legacy_root))
    assert verified.accepted and verified.differences == () and verified.table_rows['job'] == 8
    again = run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    assert again.status == 'already_imported' and counts(target.migration, 'job')['job'] == 8


def test_without_a_legacy_root_done_jobs_are_unchecked(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    done = run_import(manifest, target, dry_run=False)
    assert done.transforms['job_legacy_unchecked'] == 4


def test_orphan_access_is_refused_with_no_writes(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root, extra_sql="INSERT INTO downloadaccess VALUES ('ghost', 360);"))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(manifest, target, dry_run=False)
    assert error.value.code.startswith('import_constraint')
    assert counts(target.migration, 'user', 'job', 'dataimport') == {'user': 0, 'job': 0, 'dataimport': 0}


def test_unparsable_time_is_refused(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root,
                                extra_sql="INSERT INTO user VALUES ('u3','u3@synthetic.invalid','h','not-a-date');"))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(manifest, target)
    assert error.value.code == 'import_time_invalid'


def test_target_must_be_empty(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    with target.migration.begin() as connection:
        connection.execute(text("INSERT INTO app.\"user\" (id,email,password_hash,created_at) "
                                "VALUES ('x','x@synthetic.invalid','h',now())"))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(manifest, target)
    assert error.value.code == 'target_not_empty'


def test_one_import_per_target(tmp_path, legacy_root, target):
    first = bundle(legacy_db(tmp_path, legacy_root))
    run_import(first, target, dry_run=False)
    second = bundle(legacy_db(tmp_path, legacy_root))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(second, target)
    assert error.value.code == 'target_already_imported'  # the ledger is checked before the tables


def test_target_head_must_match(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    with target.migration.begin() as connection:
        connection.execute(text("UPDATE app.alembic_version SET version_num='b5_0012'"))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(manifest, target)
    assert error.value.code == 'target_head_mismatch'


@pytest.mark.parametrize('tamper, code', [
    ("UPDATE app.quota SET downloads_used = downloads_used + 1", ('quota', 'value_mismatch')),
    ("DELETE FROM app.billingevent", ('billingevent', 'row_count_mismatch')),
    ("UPDATE app.resourcecounter SET used = 99 WHERE resource='receipt_entries'", ('resourcecounter', 'counter_mismatch')),
])
def test_verify_reports_tampering_by_table(tmp_path, legacy_root, target, tamper, code):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    with target.migration.begin() as connection:
        connection.execute(text(tamper))
    verified = run_verify(manifest, target, legacy_media_root=str(legacy_root))
    assert not verified.accepted and code in verified.differences


def test_reports_carry_no_row_values(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    report = run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    verified = run_verify(manifest, target, legacy_media_root=str(legacy_root))
    rendered = repr(report) + repr(verified)
    assert 'synthetic.invalid' not in rendered and 'cus_1' not in rendered and 'source.synthetic' not in rendered


# T4: the legacy check never follows a link or junction out of the old media root.
def test_linked_job_directory_is_a_mismatch(tmp_path, legacy_root, target):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'clip.mp4').write_bytes(b'x' * 10)
    linked = legacy_root / 'j-linked'
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(outside), str(linked))
    else:
        linked.symlink_to(outside, target_is_directory=True)
    extra = ("INSERT INTO job VALUES ('j-linked','https://source.synthetic.invalid/l','t','best','done',100.0,"
             f"'{linked / 'clip.mp4'}',10,NULL,NULL,'{T0}','{T0}',NULL,'u1');")
    manifest = bundle(legacy_db(tmp_path, legacy_root, extra_sql=extra))
    run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    with target.migration.connect() as connection:
        assert connection.scalar(text("SELECT legacy_check FROM app.job WHERE id='j-linked'")) == 'mismatch'



# Review M5: production imports refuse synthetic bundles unless explicitly allowed.
def test_synthetic_bundle_is_refused_by_default(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    with pytest.raises(importer.ImportFailure) as error:
        importer.import_snapshot(manifest, target.migration, trusted_parent_ack=True)
    assert error.value.code == 'bundle_synthetic_refused'


# Review I2: business values without a PG CHECK are refused before any write.
@pytest.mark.parametrize('extra, code', [
    ("UPDATE downloadidempotency SET state='bogus' WHERE id='r1';", 'import_enum_invalid'),
    ("UPDATE membership SET status='vip' WHERE user_id='u1';", 'import_enum_invalid'),
    ("UPDATE billingcheckout SET state='weird' WHERE id='c1';", 'import_enum_invalid'),
    ("UPDATE quota SET downloads_used=-5 WHERE id='q1';", 'import_negative_count'),
    ('UPDATE quota SET "limit"=-1 WHERE id=\'q1\';', 'import_negative_count'),
])
def test_business_values_are_checked(tmp_path, legacy_root, target, extra, code):
    manifest = bundle(legacy_db(tmp_path, legacy_root, extra_sql=extra))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(manifest, target)
    assert error.value.code == code
    assert error.value.__context__ is None


# Review M1: only the timestamp shapes the application writes.
@pytest.mark.parametrize('value', ['2026-10-01', '2026-10-01T08', '2026-W40-4', ' 2026-10-01 08:00:00'])
def test_loose_time_shapes_are_refused(tmp_path, legacy_root, target, value):
    manifest = bundle(legacy_db(tmp_path, legacy_root,
                                extra_sql=f"INSERT INTO user VALUES ('u9','u9@synthetic.invalid','h','{value}');"))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(manifest, target)
    assert error.value.code == 'import_time_invalid'


# Review I3: a head-only column changed after the import is reported.
@pytest.mark.parametrize('tamper', ["UPDATE app.job SET attempts_used = 3 WHERE id='j-error'",
                                    "UPDATE app.billingcheckout SET reconciliation = 'verified'",
                                    "UPDATE app.billingevent SET outcome = 'applied'"])
def test_verify_covers_columns_the_source_lacks(tmp_path, legacy_root, target, tamper):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    with target.migration.begin() as connection:
        connection.execute(text(tamper))
    verified = run_verify(manifest, target, legacy_media_root=str(legacy_root))
    assert not verified.accepted and any(code == 'value_mismatch' for unused, code in verified.differences)


# Review M4: the ledger itself and the head are checked; file drift has its own code.
def test_verify_checks_the_ledger_and_reports_file_drift_separately(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    (legacy_root / 'j-done' / 'clip.mp4').unlink()  # the file went away after the import
    verified = run_verify(manifest, target, legacy_media_root=str(legacy_root))
    assert ('job', 'legacy_check_changed') in verified.differences
    with target.migration.begin() as connection:
        connection.execute(text("UPDATE app.dataimport SET schema_profile='x'"))
    verified = run_verify(manifest, target, legacy_media_root=str(legacy_root))
    assert ('dataimport', 'ledger_fields_mismatch') in verified.differences


# Review I4: an AUTOCOMMIT engine cannot turn a dry run into writes.
def test_dry_run_is_transactional_even_on_an_autocommit_engine(tmp_path, legacy_root, target):
    manifest = bundle(legacy_db(tmp_path, legacy_root))
    autocommit = target.migration.execution_options(isolation_level='AUTOCOMMIT')
    report = importer.import_snapshot(manifest, autocommit, trusted_parent_ack=True, allow_synthetic=True)
    assert report.status == 'dry_run_ok'
    assert counts(target.migration, 'user', 'job', 'dataimport') == {'user': 0, 'job': 0, 'dataimport': 0}


# Review I1: a running legacy Job an operation still refers to is never held (models17 source).
def test_operated_legacy_job_is_refused(tmp_path, target):
    path = tmp_path / 'models17.db'
    import sqlite3
    writer = sqlite3.connect(str(path))
    try:
        writer.executescript((FIXTURES / 'sqlite17.sql').read_text('utf8'))
        writer.execute(f"INSERT INTO user VALUES ('u1','u1@synthetic.invalid','h','{T0}')")
        writer.execute("INSERT INTO job (id,url,title,format_id,status,progress,created_at,updated_at,user_id) "
                       f"VALUES ('j1','https://source.synthetic.invalid/1','t','best','queued',0.0,'{T0}','{T0}','u1')")
        columns = [row[1] for row in writer.execute('PRAGMA table_info(downloadoperation)')]
        values = {name: None for name in columns} | dict(
            id='op1', user_id='u1', job_id='j1', canonical_payload='{}', fingerprint='f' * 64,
            canonical_format_id='best', membership_revision=0, quota_day='2026-10-01', state='accepted_server',
            accepted_at=T0, deadline_at=T0, resolve_deadline_at=T0, capacity_reserved=1, resolve_epoch=0,
            resolve_attempts_used=0, resolve_attempts_limit=1, budget_version=1, budget_checkpoint_json='{}',
            budget_checkpoint_at=T0)
        writer.execute(f"INSERT INTO downloadoperation ({','.join(values)}) VALUES ({','.join('?' * len(values))})",
                       tuple(values.values()))
        writer.commit()
    finally:
        writer.close()
    manifest = bundle(str(path.resolve()))
    with pytest.raises(importer.ImportFailure) as error:
        run_import(manifest, target)
    assert error.value.code == 'import_legacy_job_has_operation'


# Review M3: '..' is never folded away, and hard links are not evidence of a good file.
def test_dot_dot_paths_and_hard_links_are_mismatches(tmp_path, legacy_root, target):
    (legacy_root / 'j-hard').mkdir()
    os.link(legacy_root / 'j-done' / 'clip.mp4', legacy_root / 'j-hard' / 'clip.mp4')
    folded = str(legacy_root / 'j-dots' / '..' / 'j-done' / 'clip.mp4')
    extra = ''.join(
        f"INSERT INTO job VALUES ('{job_id}','https://source.synthetic.invalid/x','t','best','done',100.0,"
        f"'{file_path}',10,NULL,NULL,'{T0}','{T0}',NULL,'u1');"
        for job_id, file_path in (('j-hard', legacy_root / 'j-hard' / 'clip.mp4'), ('j-dots', folded)))
    manifest = bundle(legacy_db(tmp_path, legacy_root, extra_sql=extra))
    run_import(manifest, target, dry_run=False, legacy_media_root=str(legacy_root))
    with target.migration.connect() as connection:
        checks = dict(connection.execute(text("SELECT id, legacy_check FROM app.job WHERE id IN ('j-hard','j-dots')")).all())
    assert checks == {'j-hard': 'mismatch', 'j-dots': 'mismatch'}
