"""Dialect-specific setup with explicit PostgreSQL business readiness checks."""
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, make_url
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

from .config import settings


class DatabaseConfigurationError(RuntimeError):
    """Safe operator message without connection strings or SQL parameters."""


def migration_config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))


def build_engine(url: str, *, role: Literal['api', 'worker', 'migration']) -> Engine:
    try:
        parsed = make_url(url)
        if role not in {'api', 'worker', 'migration'}:
            raise ValueError('role')
        if parsed.drivername not in {'sqlite', 'sqlite+pysqlite', 'postgresql+psycopg'}:
            raise ValueError('driver')
        if parsed.get_backend_name() == 'sqlite':
            return create_engine(parsed, echo=False, hide_parameters=True,
                                 connect_args={'check_same_thread': False, 'timeout': 30})
        if set(parsed.query) - {'sslmode', 'sslrootcert', 'sslcert', 'sslkey'}:
            raise ValueError('query')
        options = ('-c timezone=UTC -c search_path=app,pg_catalog '
                   f'-c lock_timeout={settings.db_lock_timeout_ms} '
                   f'-c statement_timeout={settings.db_statement_timeout_ms} '
                   f'-c idle_in_transaction_session_timeout={settings.db_idle_transaction_timeout_ms}')
        pool = ({'poolclass': NullPool} if role == 'migration' else {
            'pool_size': settings.db_pool_size, 'max_overflow': settings.db_pool_max_overflow,
            'pool_timeout': settings.db_pool_timeout_seconds, 'pool_pre_ping': True})
        return create_engine(parsed, echo=False, hide_parameters=True, isolation_level='READ COMMITTED',
                             connect_args={'connect_timeout': settings.db_connect_timeout_seconds,
                                           'options': options}, **pool)
    except Exception:
        raise DatabaseConfigurationError('Invalid database configuration') from None


def assert_schema_current(engine: Engine) -> None:
    """Read only the installed revision; never create, migrate or stamp."""
    try:
        expected = ScriptDirectory.from_config(migration_config()).get_heads()
        if len(expected) != 1:
            raise ValueError('ambiguous migration heads')
        with engine.connect() as connection:
            schema = 'app' if engine.dialect.name == 'postgresql' else None
            current = MigrationContext.configure(connection, opts={
                'version_table_schema': schema}).get_current_heads()
        if tuple(current) != tuple(expected):
            raise ValueError('schema revision mismatch')
    except Exception:
        raise DatabaseConfigurationError('Database schema is not at the required migration head') from None


engine = build_engine(settings.db_url, role='api')


def assert_source_ready() -> None:
    from .services.source_broker import ping
    if not ping(settings.source_broker_socket):
        raise DatabaseConfigurationError('Isolated source broker is unavailable')


def init_db() -> None:
    if engine.dialect.name == 'postgresql':
        assert_schema_current(engine)
        if not settings.pg_business_enabled:
            raise DatabaseConfigurationError('PostgreSQL business startup requires explicit operator enablement')
        if (not settings.source_broker_socket or settings.media_root is None
                or settings.billing_inbox_mode != 'durable' or settings.stripe_livemode is None
                or not settings.stripe_provider_account_scope):
            raise DatabaseConfigurationError('PostgreSQL business configuration is incomplete')
        assert_source_ready()
        return
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
