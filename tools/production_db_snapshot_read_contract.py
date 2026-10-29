"""E2 read contract: a module-issued capability for one dedicated connection.

Only the guarded bootstraps in this module create connections and issue
contracts. A contract records how its connection was constructed and checks
the observable driver state it must keep; it cannot prove the absence of
unexposed driver configuration and does not resist malicious same-process
code. Synthetic contracts cover SQLite read-only URI files and loopback PostgreSQL
(psycopg 3); the operational SQLite bootstrap (B6 E3) issues the same guarded
read-only connection for an operator-named real file.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Connection
from sqlalchemy.pool import NullPool


_CODES = frozenset({'driver_contract_required', 'active_transaction_refused',
    'snapshot_resource_limit', 'connection_restore_failed'})
_KEY = object()
_MAX_WALL_SECONDS = 300
_STATEMENT_SECONDS = 10
_LOCK_MS = 1000
_PROGRESS_STEPS = 1000
_CONFIG_SQLITE = 'sqlite_synthetic_ro_v1'
_CONFIG_SQLITE_OPERATIONAL = 'sqlite_operational_ro_v1'  # B6 E3 real-data drill (user-authorized 2026-10-27)
_CONFIG_PG = 'pg_synthetic_psycopg3_v1'
_CONNECTION_EVENTS = ('before_cursor_execute', 'after_cursor_execute', 'before_execute',
    'after_execute', 'engine_connect', 'begin', 'commit', 'rollback', 'set_connection_execution_options')
_POOL_EVENTS = ('connect', 'first_connect', 'checkout', 'checkin', 'reset')
_DIALECT_EVENTS = ('do_connect', 'do_execute', 'do_execute_no_params', 'do_executemany',
    'do_setinputsizes', 'handle_error')
# The PG types E2 reads (text, varchar, int4, int8, float8, bool, date, timestamptz).
_PG_OIDS = (25, 1043, 23, 20, 701, 16, 1082, 1184)
_PG_LOADER_MODULES = ('psycopg_binary._psycopg', 'psycopg_c._psycopg', 'psycopg.types.')
# Transaction-local session settings for every PG export statement (SET LOCAL semantics).
# extra_float_digits=3 keeps text-format float8 output shortest-exact even when a
# database/role default sets it <= 0 (which would round to 15 significant digits).
_PG_LOCALS = (('search_path', 'pg_catalog'), ('TimeZone', 'UTC'), ('DateStyle', 'ISO, YMD'),
    ('IntervalStyle', 'iso_8601'), ('extra_float_digits', '3'))
_PG_TIMEOUT_STATES = ('57014', '55P03')  # query_canceled, lock_not_available
_DB_NAME = re.compile(r'[a-z_][a-z0-9_]{0,62}\Z')
_REGISTRY = {}
_monotonic = time.monotonic


class ReadContractError(RuntimeError):
    """Fixed contract/guard codes only; never driver text."""

    def __init__(self, code: str):
        self.code = code if type(code) is str and code in _CODES else 'driver_contract_required'
        super().__init__(self.code)


def _fail(code):
    error = ReadContractError(code)
    try:
        raise error
    except ReadContractError:
        error.__context__ = error.__cause__ = None
        raise


class ReadBudget:
    """One shared monotonic wall budget (whole seconds, at most 300)."""

    __slots__ = ('_deadline',)

    def __init__(self, seconds):
        if type(seconds) is not int or not 0 <= seconds <= _MAX_WALL_SECONDS:
            raise ValueError('read_budget_invalid')
        self._deadline = _monotonic() + seconds

    def remaining(self) -> float:
        return self._deadline - _monotonic()

    def __repr__(self):
        return '<read budget>'


class _ConstructionRecord:
    __slots__ = ('config_id', 'domain', 'dialect', 'listeners', 'isolation_level', 'autocommit', 'loaders')

    def __init__(self, *, _key, config_id, domain, dialect, listeners, isolation_level=None,
                 autocommit=None, loaders=()):
        if _key is not _KEY:
            raise TypeError('construction_record_internal')
        self.config_id, self.domain, self.dialect = config_id, domain, dialect
        self.listeners, self.isolation_level = listeners, isolation_level
        self.autocommit, self.loaders = autocommit, loaders


class RawReadContract:
    """Opaque, single-use; bound to one Connection/raw/PID/thread."""

    __slots__ = ('_connection', '_raw', '_engine', '_pid', '_thread', '_record', '_state', '_guard')

    def __init_subclass__(cls, **kwargs):
        raise TypeError('read_contract_final')

    def __init__(self, *args, _key=None, **kwargs):
        if _key is not _KEY:
            raise TypeError('read_contract_internal')

    def __repr__(self):
        return '<read contract>'


class _SqliteGuard:
    """Owned progress handler and busy_timeout on a handler-free dedicated raw.

    Cooperative cancellation of SQLite VM steps and a bound on busy waits only;
    not a hard deadline for blocking I/O, the driver or the OS.
    """

    __slots__ = ('raw', 'budget', 'installed', 'expired', 'deadline', 'original_busy')
    sqla_dialect = 'sqlite'

    def __init__(self, raw):
        self.raw, self.budget = raw, None
        self.installed = self.expired = False
        self.deadline = self.original_busy = None

    def install(self, raw, budget=None):
        if raw is not self.raw or self.installed:
            _fail('driver_contract_required')
        if budget is not None:
            self.budget = budget
        self.original_busy = _busy_timeout(raw)
        self.installed = True
        raw.set_progress_handler(self._progress, _PROGRESS_STEPS)
        self.statement()

    def statement(self):
        """Start one statement window: at most 10 seconds and the remaining budget."""
        remaining = self.budget.remaining()
        if remaining <= 0:
            self.expired = True
            _fail('snapshot_resource_limit')
        window = min(_STATEMENT_SECONDS, remaining)
        self.deadline = _monotonic() + window
        self.raw.execute('PRAGMA busy_timeout=' + str(max(1, int(window * 1000)))).fetchall()

    # SQLite applies the window per VM run, so each fetch starts a new one.
    fetch = statement

    def check(self):
        if self.expired or _monotonic() > self.deadline:
            self.expired = True
            _fail('snapshot_resource_limit')

    def timed_out(self, error):
        return self.expired

    def _progress(self):
        if _monotonic() > self.deadline:
            self.expired = True
            return 1
        return 0

    def _restore(self):
        self.raw.set_progress_handler(None, 0)
        self.raw.execute('PRAGMA busy_timeout=' + str(self.original_busy)).fetchall()

    def teardown(self):
        if self.installed:
            self._restore()
            self.installed = False


class _PgGuard:
    """Transaction-local timeouts and session settings inside the E0 transaction.

    Values are set with pg_catalog.set_config(name, value, true) (SET LOCAL), so
    the E0 rollback removes them; teardown runs no SQL in a possibly aborted
    transaction. The server enforces statement_timeout per statement, including
    each FETCH; the client additionally checks the shared wall budget per fetch.
    """

    __slots__ = ('raw', 'budget', 'installed', 'expired', 'deadline')
    sqla_dialect = 'postgresql'

    def __init__(self, raw):
        self.raw, self.budget = raw, None
        self.installed = self.expired = False
        self.deadline = None

    def _set(self, name, value):
        with self.raw.cursor() as cursor:
            cursor.execute('SELECT pg_catalog.set_config(%s, %s, true)', (name, value))
            cursor.fetchall()

    def install(self, raw, budget=None):
        if raw is not self.raw or self.installed:
            _fail('driver_contract_required')
        if budget is not None:
            self.budget = budget
        self.installed = True
        for name, value in _PG_LOCALS:
            self._set(name, value)
        self.statement()

    def statement(self):
        """Tighten statement/lock timeouts to at most 10 s/1 s and the remaining budget."""
        remaining = self.budget.remaining()
        if remaining <= 0:
            self.expired = True
            _fail('snapshot_resource_limit')
        window = min(_STATEMENT_SECONDS, remaining)
        self.deadline = _monotonic() + window
        milliseconds = max(1, int(window * 1000))
        self._set('statement_timeout', str(milliseconds) + 'ms')
        self._set('lock_timeout', str(min(_LOCK_MS, milliseconds)) + 'ms')

    def check(self):
        if self.expired or self.budget.remaining() <= 0:
            self.expired = True
            _fail('snapshot_resource_limit')

    fetch = check

    def timed_out(self, error):
        for item in (error, getattr(error, 'orig', None)):
            if getattr(item, 'sqlstate', None) in _PG_TIMEOUT_STATES:
                self.expired = True
        if self.deadline is not None and _monotonic() > self.deadline:
            self.expired = True
        return self.expired

    def _restore(self):
        pass

    def teardown(self):
        if self.installed:
            self._restore()
            self.installed = False


def _busy_timeout(raw):
    value = raw.execute('PRAGMA busy_timeout').fetchone()[0]
    if type(value) is not int or value < 0:
        _fail('connection_restore_failed')
    return value


def _listener_counts(connection):
    """Connection, dialect and pool listener counts plus the pool connect listeners themselves."""
    engine = connection.engine
    pool = engine.pool.dispatch
    return (tuple(len(getattr(connection.dispatch, name)) for name in _CONNECTION_EVENTS),
            tuple(len(getattr(engine.dialect.dispatch, name)) for name in _DIALECT_EVENTS),
            tuple(len(getattr(pool, name)) for name in _POOL_EVENTS),
            tuple(pool.connect))


def _pristine(listeners):
    """The frozen SQLA 2.0 default: no connection/dialect hooks; pool connect only SQLA's own."""
    connection_counts, dialect_counts, pool_counts, connect = listeners
    return (not any(connection_counts) and not any(dialect_counts) and not any(pool_counts[1:])
            and all(getattr(listener, '__module__', '').startswith('sqlalchemy.') for listener in connect))


def _pg_loaders(raw):
    import psycopg
    from psycopg.pq import Format
    loaders = tuple(raw.adapters.get_loader(oid, Format.TEXT) for oid in _PG_OIDS)
    approved = all(loader is not None and loader is psycopg.adapters.get_loader(oid, Format.TEXT)
                   and loader.__module__.startswith(_PG_LOADER_MODULES)
                   for oid, loader in zip(_PG_OIDS, loaders))
    return loaders, approved


def _pg_state_ok(raw, record):
    import psycopg
    from psycopg.pq import PipelineStatus
    from psycopg.rows import tuple_row
    return (type(raw) is psycopg.Connection and raw.row_factory is tuple_row
            and raw.cursor_factory is psycopg.Cursor and raw.server_cursor_factory is psycopg.ServerCursor
            and raw.autocommit is record.autocommit and raw.info.pipeline_status == PipelineStatus.OFF
            and raw.info.encoding == 'utf-8' and raw.info.parameter_status('server_encoding') == 'UTF8'
            and _pg_loaders(raw)[0] == record.loaders)


def _sqlite_state_ok(raw, record):
    return (type(raw) is sqlite3.Connection and raw.row_factory is None and raw.text_factory is str
            and raw.isolation_level == record.isolation_level)


def _issue_dedicated_contract(connection, construction_record):
    """Private: only a reviewed bootstrap that built `connection` may call this."""
    if type(construction_record) is not _ConstructionRecord or not isinstance(connection, Connection):
        raise TypeError('construction_record_required')
    raw = connection.connection.driver_connection
    contract = RawReadContract(_key=_KEY)
    contract._connection, contract._raw, contract._engine = connection, raw, connection.engine
    contract._pid, contract._thread = os.getpid(), threading.get_ident()
    guard = _PgGuard(raw) if construction_record.dialect == 'pg' else _SqliteGuard(raw)
    contract._record, contract._state, contract._guard = construction_record, 'issued', guard
    _REGISTRY[id(contract)] = contract
    return contract


def _guard_of(contract):
    return contract._guard


def _verify(contract, connection):
    """Exact identity and observable state; refusals happen before any source SQL."""
    if type(contract) is not RawReadContract or _REGISTRY.get(id(contract)) is not contract:
        _fail('driver_contract_required')
    if contract._state != 'issued' or contract._pid != os.getpid() or contract._thread != threading.get_ident():
        _fail('driver_contract_required')
    if connection is not contract._connection or connection.closed or connection.engine is not contract._engine:
        _fail('driver_contract_required')
    raw = connection.connection.driver_connection
    record = contract._record
    engine = contract._engine
    state_ok = _pg_state_ok if record.dialect == 'pg' else _sqlite_state_ok
    if raw is not contract._raw or not state_ok(raw, record):
        _fail('driver_contract_required')
    if engine.echo or engine.pool.echo or engine._should_log_info() or engine._should_log_debug():
        _fail('driver_contract_required')
    if _listener_counts(connection) != record.listeners:
        _fail('driver_contract_required')
    busy = raw.info.transaction_status != 0 if record.dialect == 'pg' else raw.in_transaction
    if connection.in_transaction() or busy:
        _fail('active_transaction_refused')


def _begin_use(contract, connection, budget):
    """Verify, bind the budget and mark the contract in use; returns its guard."""
    _verify(contract, connection)
    if type(budget) is not ReadBudget:
        _fail('snapshot_resource_limit')
    if budget.remaining() <= 0:
        _fail('snapshot_resource_limit')
    contract._state = 'in_use'
    contract._guard.budget = budget
    return contract._guard


def _reading(contract, connection):
    """An in-use contract bound to `connection` with its guard installed: (raw, guard)."""
    if type(contract) is not RawReadContract or _REGISTRY.get(id(contract)) is not contract:
        _fail('driver_contract_required')
    if contract._state != 'in_use' or contract._pid != os.getpid() or contract._thread != threading.get_ident():
        _fail('driver_contract_required')
    if connection is not contract._connection or connection.closed:
        _fail('driver_contract_required')
    raw = connection.connection.driver_connection
    if raw is not contract._raw or not contract._guard.installed:
        _fail('driver_contract_required')
    return raw, contract._guard


def _domain(contract):
    """Issuing domain of a verified contract: 'synthetic' or 'operational' (SQLite only)."""
    return contract._record.domain


def _source_version(contract):
    """Observed source release as bounded ASCII digits, e.g. '3.45.3' or '18.6'."""
    if contract._record.dialect == 'pg':
        version = contract._raw.info.server_version
        return str(version // 10000) + '.' + str(version % 10000)
    return sqlite3.sqlite_version


def _end_use(contract):
    if _REGISTRY.get(id(contract)) is contract:
        contract._state = 'consumed'


def _retire(contract):
    contract._state = 'consumed'
    _REGISTRY.pop(id(contract), None)


def _sqlite_ro_url(path):
    if (type(path) is not str or not path or not os.path.isabs(path) or path.startswith('file:')
            or any(character in path for character in '?#%') or not os.path.isfile(path)):
        raise ValueError('source_path_invalid')  # shared by the synthetic and operational bootstraps
    return URL.create('sqlite', database='file:' + Path(path).as_posix(), query={'mode': 'ro', 'uri': 'true'})


@contextmanager
def _open_synthetic_sqlite(path):
    """Guarded synthetic bootstrap: a dedicated read-only URI connection.

    Default pysqlite construction (detect_types=0, str text_factory, no
    row_factory, no echo/events beyond SQLA defaults) is recorded at issue.
    The caller must not commit, roll back, close or reconfigure it.
    """
    with _open_sqlite(path, 'synthetic', _CONFIG_SQLITE) as opened:
        yield opened


@contextmanager
def open_operational_sqlite(path):
    """B6 E3: the same guarded read-only bootstrap for an operator-named real SQLite file.

    Issued in the 'operational' domain, so the export records sqlite_readonly_snapshot_v1 and never
    marks real data as synthetic. Read-only URI (mode=ro): the source is never written.
    """
    with _open_sqlite(path, 'operational', _CONFIG_SQLITE_OPERATIONAL) as opened:
        yield opened


@contextmanager
def _open_sqlite(path, domain, config_id):
    url = _sqlite_ro_url(path)
    engine = create_engine(url, echo=False)
    connection = contract = None
    try:
        connection = engine.connect()
        raw = connection.connection.driver_connection
        if (type(raw) is not sqlite3.Connection or raw.row_factory is not None
                or raw.text_factory is not str or connection.in_transaction() or raw.in_transaction):
            raise ValueError('synthetic_connection_unexpected')
        listeners = _listener_counts(connection)
        if not _pristine(listeners):
            raise ValueError('synthetic_connection_unexpected')
        record = _ConstructionRecord(_key=_KEY, config_id=config_id, domain=domain,
            dialect='sqlite', listeners=listeners, isolation_level=raw.isolation_level)
        contract = _issue_dedicated_contract(connection, record)
        yield connection, contract
    finally:
        if contract is not None:
            _retire(contract)
        try:
            if connection is not None:
                connection.close()
        finally:
            engine.dispose()


def _pg_url(url):
    if (type(url) is not URL or url.drivername != 'postgresql+psycopg' or url.host != '127.0.0.1'
            or type(url.port) is not int or url.query or type(url.database) is not str
            or not _DB_NAME.match(url.database) or not url.username or url.password is None):
        raise ValueError('synthetic_url_invalid')
    return url


@contextmanager
def _open_synthetic_pg(url):
    """Guarded synthetic bootstrap: one dedicated loopback psycopg 3 connection.

    `url` is a SQLAlchemy URL object (never a DSN string, so credentials stay out
    of argv/logs). The engine is built here with SQLA/psycopg defaults only:
    NullPool, a 3 s connect_timeout and no server options, echo or hooks. The
    effective libpq target (host/hostaddr/port) and options are re-checked after
    connecting, so PGHOSTADDR/PGOPTIONS/PGSERVICE defaults cannot silently change
    what the record certifies. tuple_row, the standard
    Cursor/ServerCursor factories, the default text loaders for the read types,
    pipeline off, UTF-8 client/server encoding and autocommit are recorded.
    """
    url = _pg_url(url)
    engine = create_engine(url, echo=False, hide_parameters=True, poolclass=NullPool,
                           connect_args={'connect_timeout': 3})
    connection = contract = None
    try:
        connection = engine.connect()
        raw = connection.connection.driver_connection
        if connection.dialect.driver != 'psycopg' or connection.in_transaction():
            raise ValueError('synthetic_connection_unexpected')
        info = raw.info
        if (info.host != '127.0.0.1' or info.hostaddr not in ('', '127.0.0.1') or info.port != url.port
                or info.options != ''):
            raise ValueError('synthetic_connection_unexpected')
        listeners = _listener_counts(connection)
        loaders, approved = _pg_loaders(raw)
        record = _ConstructionRecord(_key=_KEY, config_id=_CONFIG_PG, domain='synthetic', dialect='pg',
            listeners=listeners, autocommit=False, loaders=loaders)
        if (not _pristine(listeners) or not approved or not _pg_state_ok(raw, record)
                or raw.info.transaction_status != 0):
            raise ValueError('synthetic_connection_unexpected')
        contract = _issue_dedicated_contract(connection, record)
        yield connection, contract
    finally:
        if contract is not None:
            _retire(contract)
        try:
            if connection is not None:
                connection.close()
        finally:
            engine.dispose()
