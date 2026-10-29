"""An explicit Connection's owned, read-only snapshot; no app/config/file I/O.

The caller supplies an idle connection and owns its lifecycle. This helper never
commits or closes it. Its own failures use fixed codes; exceptions raised by the
with-body propagate unchanged after restoration. On connection_restore_failed,
discard the connection. A token prevents accidental reuse, not malicious code.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
import threading
from typing import ContextManager

from sqlalchemy.engine import Connection


_CODES = frozenset({
    'connection_required', 'active_transaction_refused', 'unsupported_dialect',
    'sql_logging_refused', 'sqlite_readonly_uri_required',
    'postgres_driver_unsupported', 'connection_restore_failed', 'snapshot_failed',
    'snapshot_inactive', 'snapshot_owner_mismatch',
})
_TOKEN_KEY = object()


class SnapshotConnectionError(RuntimeError):
    """Fixed helper error codes only; never a driver exception or its text."""

    def __init__(self, code: str):
        self.code = code if type(code) is str and code in _CODES else 'snapshot_failed'
        super().__init__(self.code)


def _raise_safe(code: str) -> None:
    # Construct only after the driver/body except suites have ended. During
    # contextlib.gen.throw, Python still attaches the with-body exception to a
    # new raise. Clear that automatic link on this same safe exception before
    # a bare re-raise (which does not reattach it). `from None` alone only hides
    # the context in tracebacks; it would leave the private object reachable.
    error = SnapshotConnectionError(code)
    try:
        raise error
    except SnapshotConnectionError:
        error.__context__ = None
        error.__cause__ = None
        raise


class ReadonlySnapshot:
    """An active context's connection/scope; no public constructor or ownership."""

    __slots__ = ('__connection', '__dialect', '__schema_scope', '__pid', '__thread', '__active')

    def __init__(self, connection: Connection, *, _key, dialect: str, schema_scope: str):
        if _key is not _TOKEN_KEY:
            raise TypeError('snapshot_token_internal')
        self.__connection = connection
        self.__dialect = dialect
        self.__schema_scope = schema_scope
        self.__pid = os.getpid()
        self.__thread = threading.get_ident()
        self.__active = True

    def assert_active(self) -> None:
        if not self.__active:
            _raise_safe('snapshot_inactive')
        if self.__pid != os.getpid() or self.__thread != threading.get_ident():
            _raise_safe('snapshot_owner_mismatch')

    @property
    def connection(self) -> Connection:
        self.assert_active()
        return self.__connection

    @property
    def dialect(self) -> str:
        self.assert_active()
        return self.__dialect

    @property
    def schema_scope(self) -> str:
        self.assert_active()
        return self.__schema_scope

    def _invalidate(self) -> None:
        self.__active = False


@contextmanager
def readonly_snapshot(connection: Connection) -> ContextManager[ReadonlySnapshot]:
    """Own exactly one snapshot; restore physical driver state and SQLA options.

    PostgreSQL supports synchronous psycopg/psycopg2 and app only. SQLite uses
    main; a file connection must explicitly use URI mode=ro (memory is synthetic
    test input). No caller transaction is rolled back. Body exceptions keep
    their type; restoration failure overrides them. New safe exceptions are
    raised outside except suites, without retaining driver exception context.
    """
    original_query_only = None
    pg_state = None
    tx = None
    token = None
    error = None
    body_error = None
    try:
        try:
            if not isinstance(connection, Connection) or connection.closed:
                raise SnapshotConnectionError('connection_required')
            if connection.in_transaction():
                raise SnapshotConnectionError('active_transaction_refused')
            dialect = connection.dialect.name
            if dialect not in ('sqlite', 'postgresql'):
                raise SnapshotConnectionError('unsupported_dialect')
            if connection.engine._should_log_info() or connection.engine._should_log_debug():
                raise SnapshotConnectionError('sql_logging_refused')
            if dialect == 'sqlite':
                url = connection.engine.url
                if url.database not in (None, '', ':memory:') and not (url.query.get('mode') == 'ro' and str(url.query.get('uri')).lower() == 'true'):
                    raise SnapshotConnectionError('sqlite_readonly_uri_required')
                raw = connection.connection.driver_connection
                if raw.in_transaction:
                    raise SnapshotConnectionError('active_transaction_refused')
                original_query_only = raw.execute('PRAGMA query_only').fetchone()[0]
                raw.execute('PRAGMA query_only=ON')
                tx = connection.begin()
                # pysqlite legacy mode does not physically begin on SELECT.
                if not raw.in_transaction:
                    connection.exec_driver_sql('BEGIN')
                schema = 'main'
            else:
                if connection.dialect.driver not in ('psycopg', 'psycopg2'):
                    raise SnapshotConnectionError('postgres_driver_unsupported')
                raw = connection.connection.driver_connection
                status = raw.info.transaction_status if connection.dialect.driver == 'psycopg' else raw.get_transaction_status()
                if status != 0:  # libpq PQTRANS_IDLE, including INERROR refusal.
                    raise SnapshotConnectionError('active_transaction_refused')
                pg_state = (raw, raw.isolation_level, raw.autocommit,
                            dict(connection.get_execution_options()))
                # Preserve DBAPI AUTOCOMMIT exactly, including when it differs
                # from SQLA options. Do not add an unremovable SQLA option.
                connection.dialect.set_isolation_level(raw, 'REPEATABLE READ')
                tx = connection.begin()
                connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                schema = 'app'
            token = ReadonlySnapshot(connection, _key=_TOKEN_KEY, dialect=dialect, schema_scope=schema)
        except SnapshotConnectionError as exc:
            error = exc.code
        except Exception:
            error = 'snapshot_failed'
        except BaseException as exc:
            body_error = exc
        if error is None and body_error is None:
            try:
                yield token
            except BaseException as exc:
                body_error = exc
    finally:
        if token is not None:
            token._invalidate()
        try:
            if tx is not None:
                tx.rollback()
            if original_query_only is not None:
                connection.connection.driver_connection.execute('PRAGMA query_only=' + ('ON' if original_query_only else 'OFF'))
        except Exception:
            error = 'connection_restore_failed'
        if pg_state is not None:
            raw, isolation, autocommit, options = pg_state
            try:
                try:
                    raw.isolation_level = isolation
                finally:
                    raw.autocommit = autocommit
                if dict(connection.get_execution_options()) != options:
                    raise SnapshotConnectionError('connection_restore_failed')
            except Exception:
                error = 'connection_restore_failed'
    if error is not None:
        _raise_safe(error)
    if body_error is not None:
        raise body_error
