"""Run B1 independently with --noconftest; never load a real application env."""
import inspect

import pytest
from sqlalchemy import BigInteger, inspect as sa_inspect, text
from alembic.config import Config

from app import db
from app.config import Settings
from app.models import Job, SQLModel


def test_engine_contract_and_sqlite_parameters():
    assert 'role' in inspect.signature(db.build_engine).parameters
    engine = db.build_engine('sqlite://', role='api')
    with engine.connect() as conn:
        assert conn.scalar(text('PRAGMA busy_timeout')) == 30000
    assert engine.hide_parameters is True
    engine.dispose()


@pytest.mark.parametrize('url', ['not-a-url-secret', 'mysql://u:secret@host/db',
                                'postgresql://u:secret@host/db'])
def test_bad_configuration_does_not_expose_url(url):
    with pytest.raises(db.DatabaseConfigurationError) as error:
        db.build_engine(url, role='api')
    assert 'secret' not in str(error.value)
    assert error.value.__cause__ is None


def test_invalid_role_fails_closed():
    with pytest.raises(db.DatabaseConfigurationError):
        db.build_engine('sqlite://', role='unknown')


@pytest.mark.parametrize('role', ['api', 'worker', 'migration'])
def test_pg_engine_options_without_connecting(role):
    engine = db.build_engine('postgresql+psycopg://u:secret@localhost/db', role=role)
    _, kwargs = engine.dialect.create_connect_args(engine.url)
    assert 'check_same_thread' not in kwargs
    assert engine.hide_parameters
    if role != 'migration':
        assert engine.pool.size() == 5
        assert engine.pool._max_overflow == 0
        assert engine.pool.timeout() == 5
    engine.dispose()


@pytest.mark.parametrize('name,value', [('db_pool_size', 0), ('db_pool_max_overflow', -1),
    ('db_pool_timeout_seconds', 0), ('db_connect_timeout_seconds', 0),
    ('db_lock_timeout_ms', 0), ('db_statement_timeout_ms', 0),
    ('db_idle_transaction_timeout_ms', 0)])
def test_database_setting_boundaries(name, value):
    with pytest.raises(ValueError, match=name):
        Settings(**{name: value})


def test_database_settings_from_env(monkeypatch):
    monkeypatch.setenv('DB_POOL_SIZE', '3')
    monkeypatch.setenv('DB_STATEMENT_TIMEOUT_MS', '6000')
    assert Settings.from_env().db_pool_size == 3
    assert Settings.from_env().db_statement_timeout_ms == 6000


def test_models_bigint_utc_and_named_constraints():
    assert isinstance(Job.__table__.c.file_size.type, BigInteger)
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            if column.type.__class__.__name__ == 'DateTime':
                assert column.type.timezone
        assert all(c.name for c in table.constraints)


def test_sqlite_init_still_explicitly_creates_schema(monkeypatch):
    engine = db.build_engine('sqlite://', role='api')
    monkeypatch.setattr(db, 'engine', engine)
    db.init_db()
    legacy = {'user','job','quota','downloadidempotency','membership',
              'billingcheckout','billingevent','billingpayment','downloadaccess'}
    protocol = {'downloadoperation','quotacharge','resourcecounter','resourcereservation',
                'billinginbox','billingfact','billingreconciliationtask','billingreconciliationaudit',
                'jobattempt', 'artifactmanifest', 'filereadlease', 'cleanupintent', 'orphanobject', 'dataimport'}
    support = {'supportticket', 'supportpaymentcheck', 'membershipreissue'}  # T1 (t1_0015), user tickets work on SQLite dev
    assert set(sa_inspect(engine).get_table_names()) == legacy | protocol | support
    engine.dispose()


def test_pg_init_cannot_start_legacy_business(monkeypatch):
    engine = db.build_engine('postgresql+psycopg://u:secret@localhost/db', role='api')
    monkeypatch.setattr(db, 'engine', engine)
    checked = []
    monkeypatch.setattr(db, 'assert_schema_current', lambda eng: checked.append(eng))
    with pytest.raises(db.DatabaseConfigurationError, match='business'):
        db.init_db()
    assert checked == [engine]
    engine.dispose()


def test_query_cannot_override_fixed_pg_safety_settings():
    with pytest.raises(db.DatabaseConfigurationError):
        db.build_engine('postgresql+psycopg://u:secret@localhost/db?options=-c%20timezone=local', role='api')


def test_connection_failure_is_safe_and_schema_check_has_no_writes():
    engine = db.build_engine('postgresql+psycopg://synthetic:secret@127.0.0.1:1/absent', role='api')
    try:
        with pytest.raises(db.DatabaseConfigurationError) as failure:
            db.assert_schema_current(engine)
        assert str(failure.value) == 'Database schema is not at the required migration head'
        assert failure.value.__cause__ is None
    finally:
        engine.dispose()


@pytest.mark.parametrize('revision_files', [[], ['a', 'b']])
def test_local_missing_or_multiple_migration_heads_fail_closed(tmp_path, monkeypatch, revision_files):
    versions = tmp_path / 'versions'
    versions.mkdir()
    for revision in revision_files:
        (versions / f'{revision}.py').write_text(
            f"revision = '{revision}'\ndown_revision = None\n", encoding='utf8')
    config = Config()
    config.set_main_option('script_location', str(tmp_path))
    monkeypatch.setattr(db, 'migration_config', lambda: config)
    engine = db.build_engine('sqlite://', role='api')
    try:
        with pytest.raises(db.DatabaseConfigurationError):
            db.assert_schema_current(engine)
        assert sa_inspect(engine).get_table_names() == []
    finally:
        engine.dispose()
