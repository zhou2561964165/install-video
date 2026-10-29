"""E2: bounded preflight and original-value rows from one export catalog snapshot.

Every read uses the raw DBAPI connection inside the catalog's E0 transaction
under the read-contract guard; values are yielded unmodified as tuples, never
through SQLA Row/ORM processors. All tables are counted and every column's raw
cost is bounded before any payload SELECT. Fixed-width costs (real/float8=24,
date=10, timestamptz=33, bool=1) are capacity bounds, not exact byte counts.
SQLite reads use the standard cursor; PostgreSQL payloads use a named
non-scrollable, non-holdable psycopg ServerCursor with explicit FETCH 1.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import os
import re
import secrets
import sqlite3
import threading

from tools import production_db_snapshot_catalog as _catalog
from tools import production_db_snapshot_read_contract as _read_contract
from tools.production_db_snapshot_format import DEFAULT_LIMITS as _CODEC


_CODES = frozenset({'snapshot_inactive', 'snapshot_owner_mismatch', 'snapshot_arguments_invalid',
    'snapshot_resource_limit', 'source_codec_unsupported', 'source_read_failed',
    'source_row_count_mismatch', 'driver_contract_required'})
_MAX_TABLES = 18
_MAX_TOTAL_ROWS = 10_000_000
_REAL_COST = 24
_SQLITE_MIN = (3, 43, 0)
_NAME = re.compile(r'[a-z_][a-z0-9_]{0,127}\Z')
# SQLite storage class -> codec tag, and the exact Python type pysqlite yields for it.
_TAG = {'null': 'n', 'integer': 'i', 'real': 'f', 'text': 's', 'blob': 'x'}
_PYTYPE = {'null': type(None), 'integer': int, 'real': float, 'text': str, 'blob': bytes}
_STORAGE = {tag: storage for storage, tag in _TAG.items()}
_SMOKE = ("SELECT octet_length('é'), typeof(1), length(x'00ff'), length(CAST(-12 AS TEXT)), "
          "octet_length('a' || char(0) || 'b')")
# PG physical kind -> (type OID, exact Python type, codec tag, fixed cost or None for measured).
_PG_KINDS = {'pg_text': (25, str, 's', None), 'pg_varchar': (1043, str, 's', None),
    'pg_int4': (23, int, 'i', None), 'pg_int8': (20, int, 'i', None),
    'pg_float8': (701, float, 'f', _REAL_COST), 'pg_bool': (16, bool, 'b', 1),
    'pg_date': (1082, _dt.date, 'date', 10), 'pg_timestamptz': (1184, _dt.datetime, 'dt', 33)}
_PG_CURSOR_PREFIX = 'b6e2_'


class SnapshotRowsError(RuntimeError):
    """Fixed codes only; never driver text, SQL, parameters or values."""

    def __init__(self, code: str):
        self.code = code if type(code) is str and code in _CODES else 'source_read_failed'
        super().__init__(self.code)


def _fail(code):
    error = SnapshotRowsError(code)
    try:
        raise error
    except SnapshotRowsError:
        error.__context__ = error.__cause__ = None
        raise


@dataclass(frozen=True, slots=True)
class RowLimits:
    """Caller limits; each may only tighten the codec/export ceilings."""
    max_cell_bytes: int = _CODEC.max_cell_bytes
    max_row_bytes: int = _CODEC.max_row_bytes
    max_total_rows: int = _MAX_TOTAL_ROWS

    def __post_init__(self):
        for value, ceiling in ((self.max_cell_bytes, _CODEC.max_cell_bytes),
                               (self.max_row_bytes, _CODEC.max_row_bytes),
                               (self.max_total_rows, _MAX_TOTAL_ROWS)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError('row_limits_invalid')


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class PreflightSummary:
    """Counts and length bounds in table_order; not a read authorization."""
    counts: tuple[int, ...]
    max_cell: tuple[int, ...]
    max_row: tuple[int, ...]

    def __repr__(self):
        return '<preflight summary>'


def table_order(descriptor):
    """The fixed export table order: data and metadata tables sorted by name."""
    return tuple(sorted(descriptor.tables + descriptor.metadata_tables, key=lambda table: table.name))


def _allowed_tags(profile, table):
    for item, tags in zip(profile.descriptor.tables, profile.allowed_tags):
        if item.name == table.name:
            return tags
    return tuple(frozenset(('s',)) for _ in table.columns)


def _quote(name):
    if type(name) is not str or not _NAME.match(name):
        _fail('source_codec_unsupported')
    return '"' + name.replace('"', '""') + '"'


def _cost(column, over):
    """Raw byte cost of one SQLite cell, clamped to `over` (cell cap + 1)."""
    return ("min(CASE typeof({c}) WHEN 'null' THEN 1 WHEN 'text' THEN octet_length({c}) "
            "WHEN 'blob' THEN length({c}) WHEN 'integer' THEN length(CAST({c} AS TEXT)) "
            "WHEN 'real' THEN {real} ELSE {over} END, {over})").format(c=column, real=_REAL_COST, over=over)


def _payload_sql(table):
    columns = [_quote(column.name) for column in table.columns]
    order = ','.join(_quote(name) for name in table.primary_key)
    return ('SELECT ' + ','.join(c + ',typeof(' + c + ')' for c in columns) +
            ' FROM main.' + _quote(table.name) + ' ORDER BY ' + order)


def _pg_identifier(name):
    from psycopg import sql
    if type(name) is not str or not _NAME.match(name):
        _fail('source_codec_unsupported')
    return sql.Identifier(name)


def _pg_table(namespace, table):
    from psycopg import sql
    return sql.SQL('{}.{}').format(_pg_identifier(namespace), _pg_identifier(table.name))


def _pg_count_sql(table, namespace='app'):
    from psycopg import sql
    return sql.SQL('SELECT pg_catalog.count(*) FROM (SELECT 1 FROM {} LIMIT %s) AS bounded_rows').format(
        _pg_table(namespace, table))


def _pg_cost(column, kind, over):
    from psycopg import sql
    identifier = _pg_identifier(column.name)
    fixed = _PG_KINDS[kind][3]
    if fixed is not None:
        measured = sql.Literal(fixed)
    elif kind in ('pg_int4', 'pg_int8'):
        measured = sql.SQL('pg_catalog.octet_length({}::pg_catalog.text)').format(identifier)
    else:
        measured = sql.SQL('pg_catalog.octet_length({})').format(identifier)
    return sql.SQL('LEAST(CASE WHEN {c} IS NULL THEN 1 ELSE {m} END, {over})').format(
        c=identifier, m=measured, over=sql.Literal(over))


def _pg_violation(column, kind, allowed):
    """Counted, never returned: disallowed NULL, non-finite float, out-of-Python-range date/time."""
    from psycopg import sql
    c = _pg_identifier(column.name)
    parts = []
    if 'n' not in allowed:
        parts.append(sql.SQL('{} IS NULL').format(c))
    if kind == 'pg_float8':
        parts.append(sql.SQL("{} IN ('Infinity'::pg_catalog.float8, '-Infinity'::pg_catalog.float8, "
                             "'NaN'::pg_catalog.float8)").format(c))
    elif kind == 'pg_date':
        parts.append(sql.SQL("(NOT pg_catalog.isfinite({c}) OR {c} < '0001-01-01'::pg_catalog.date "
                             "OR {c} > '9999-12-31'::pg_catalog.date)").format(c=c))
    elif kind == 'pg_timestamptz':
        # Conservative: one day inside Python's datetime range at either end.
        parts.append(sql.SQL("(NOT pg_catalog.isfinite({c}) OR {c} < '0001-01-02 00:00:00+00'::pg_catalog.timestamptz "
                             "OR {c} >= '9999-12-31 00:00:00+00'::pg_catalog.timestamptz)").format(c=c))
    if not parts:
        return sql.SQL('0')
    return sql.SQL('CASE WHEN COALESCE({}, false) THEN 1 ELSE 0 END').format(sql.SQL(' OR ').join(parts))


def _pg_payload_sql(table, namespace='app'):
    from psycopg import sql
    return sql.SQL('SELECT {} FROM {} ORDER BY {}').format(
        sql.SQL(',').join(_pg_identifier(column.name) for column in table.columns),
        _pg_table(namespace, table),
        sql.SQL(',').join(_pg_identifier(name) for name in table.primary_key))


def _fetchone(cursor):
    return cursor.fetchone()


def _python_cost(storage, value):
    if storage == 'text':
        return len(value.encode('utf8'))
    if storage == 'blob':
        return len(value)
    if storage == 'integer':
        return len(str(value))
    return 1 if storage == 'null' else _REAL_COST


def _pg_python_cost(kind, value):
    if value is None:
        return 1
    fixed = _PG_KINDS[kind][3]
    if fixed is not None:
        return fixed
    if kind in ('pg_int4', 'pg_int8'):
        return len(str(value))
    return len(value.encode('utf8'))


class SnapshotRows:
    """Single-pass reader bound to one export catalog snapshot and its contract."""

    __slots__ = ('_source', '_contract', '_limits', '_tables', '_tags', '_state', '_summary',
                 '_consumed', '_iterating', '_cursors', '_pid', '_thread', '_dialect', '_namespace')

    def __init__(self, source, contract, limits, tables, tags, *, _key=None):
        if _key is not _KEY:
            raise TypeError('snapshot_rows_internal')
        self._source, self._contract, self._limits = source, contract, limits
        self._tables, self._tags = tables, tags
        self._dialect, self._namespace = source.descriptor.dialect, source.descriptor.namespace
        self._state, self._summary, self._consumed, self._iterating = 'open', None, set(), False
        self._cursors, self._pid, self._thread = [], os.getpid(), threading.get_ident()

    def __repr__(self):
        return '<snapshot rows>'

    def _active(self):
        """Re-verify reader, catalog snapshot and contract before each source operation."""
        if self._state not in ('open', 'preflighted'):
            _fail('snapshot_inactive')
        if self._pid != os.getpid() or self._thread != threading.get_ident():
            _fail('snapshot_owner_mismatch')
        code = None
        try:
            connection = _catalog._resolve(self._source)
            raw, guard = _read_contract._reading(self._contract, connection)
        except _catalog.CatalogError as error:
            code = error.code if error.code in _CODES else 'snapshot_inactive'
        except _read_contract.ReadContractError as error:
            code = error.code
        if code is not None:
            _fail(code)
        return raw, guard

    def _execute(self, sql, params=()):
        raw, guard = self._active()
        code = None
        try:
            guard.statement()
            cursor = raw.cursor()
            self._cursors.append(cursor)
            cursor.execute(sql, params)
            return cursor, guard
        except _read_contract.ReadContractError as error:
            code = error.code
        except Exception as error:
            code = 'snapshot_resource_limit' if guard.timed_out(error) else 'source_read_failed'
        _fail(code)

    def _scalar_row(self, sql, params=()):
        cursor, guard = self._execute(sql, params)
        code = None
        try:
            row = _fetchone(cursor)
            cursor.close()
            return row
        except Exception as error:
            code = 'snapshot_resource_limit' if guard.timed_out(error) else 'source_read_failed'
        _fail(code)

    def _failed(self, code):
        self._state = 'failed'
        _fail(code)

    def preflight(self) -> PreflightSummary:
        if self._state != 'open':
            _fail('snapshot_inactive')
        try:
            return self._preflight()
        except BaseException:
            if self._state == 'open':
                self._state = 'failed'
            raise

    def _preflight(self):
        limits = self._limits
        if self._dialect == 'sqlite':
            if sqlite3.sqlite_version_info < _SQLITE_MIN:
                self._failed('source_codec_unsupported')
            if self._scalar_row('PRAGMA encoding') != ('UTF-8',):
                self._failed('source_codec_unsupported')
            if self._scalar_row(_SMOKE) != (2, 'integer', 2, 3, 3):
                self._failed('source_codec_unsupported')
        counts, remaining = [], limits.max_total_rows
        for table in self._tables:
            if self._dialect == 'pg':
                sql = _pg_count_sql(table, self._namespace)
            else:
                sql = ('SELECT count(*) FROM (SELECT 1 FROM main.' + _quote(table.name) +
                       ' LIMIT ?) AS bounded_rows')
            row = self._scalar_row(sql, (remaining + 1,))
            count = row[0] if type(row) is tuple and row else None
            if type(count) is not int or count > remaining:
                self._failed('snapshot_resource_limit' if type(count) is int else 'source_read_failed')
            remaining -= count
            counts.append(count)
        over = limits.max_cell_bytes + 1
        max_cell, max_row = [], []
        for table, tags, count in zip(self._tables, self._tags, counts):
            sql = (self._pg_aggregate(table, tags, over) if self._dialect == 'pg'
                   else self._sqlite_aggregate(table, tags, over))
            row = self._scalar_row(sql, (count + 1,))
            values = [0 if value is None else value for value in row]
            if any(type(value) is not int for value in values):
                self._failed('source_read_failed')
            cells, total, bad = values[:-2], values[-2], values[-1]
            if bad:
                self._failed('source_codec_unsupported')
            if any(cell > limits.max_cell_bytes for cell in cells) or total > limits.max_row_bytes:
                self._failed('snapshot_resource_limit')
            max_cell.append(max(cells, default=0))
            max_row.append(total)
        self._summary = PreflightSummary(tuple(counts), tuple(max_cell), tuple(max_row))
        self._state = 'preflighted'
        return self._summary

    def _sqlite_aggregate(self, table, tags, over):
        columns = [_quote(column.name) for column in table.columns]
        costs = [_cost(c, over) for c in columns]
        violations = ['CASE WHEN typeof(' + c + ') IN (' +
                      ','.join("'" + _STORAGE[tag] + "'" for tag in sorted(allowed)) +
                      ') THEN 0 ELSE 1 END' for c, allowed in zip(columns, tags)]
        return ('SELECT ' + ','.join('max(' + cost + ')' for cost in costs) +
                ',max(' + '+'.join(costs) + '),sum(' + '+'.join(violations) + ')' +
                ' FROM (SELECT ' + ','.join(columns) + ' FROM main.' + _quote(table.name) +
                ' LIMIT ?) AS bounded_rows')

    def _pg_aggregate(self, table, tags, over):
        from psycopg import sql
        kinds = [column.physical_type.kind for column in table.columns]
        costs = [_pg_cost(column, kind, over) for column, kind in zip(table.columns, kinds)]
        violations = [_pg_violation(column, kind, allowed)
                      for column, kind, allowed in zip(table.columns, kinds, tags)]
        # int4 sums: at most 96 columns x (1 MiB + 1) stays below 2**31.
        return sql.SQL('SELECT {cells}, pg_catalog.max({row}), pg_catalog.sum({bad})::pg_catalog.int8 '
                       'FROM (SELECT {columns} FROM {table} LIMIT %s) AS bounded_rows').format(
            cells=sql.SQL(',').join(sql.SQL('pg_catalog.max({})').format(cost) for cost in costs),
            row=sql.SQL(' + ').join(costs), bad=sql.SQL(' + ').join(violations),
            columns=sql.SQL(',').join(_pg_identifier(column.name) for column in table.columns),
            table=_pg_table(self._namespace, table))

    def iter_table(self, table_index: int):
        """One sequential pass over a table's original values, ordered by its full primary key."""
        if type(table_index) is not int or not 0 <= table_index < len(self._tables):
            _fail('snapshot_arguments_invalid')
        if self._state != 'preflighted' or self._iterating or table_index in self._consumed:
            _fail('snapshot_inactive')
        self._active()
        self._consumed.add(table_index)
        self._iterating = True
        return self._iterate(table_index)

    def _open_payload(self, table):
        if self._dialect == 'sqlite':
            return self._execute(_payload_sql(table))
        import psycopg
        from psycopg.rows import tuple_row
        raw, guard = self._active()
        code = None
        try:
            guard.statement()
            cursor = raw.cursor(name=_PG_CURSOR_PREFIX + secrets.token_hex(8), row_factory=tuple_row,
                                scrollable=False, withhold=False, binary=False)
            self._cursors.append(cursor)
            if type(cursor) is not psycopg.ServerCursor:
                code = 'driver_contract_required'
            else:
                cursor.itersize = 1
                cursor.execute(_pg_payload_sql(table, self._namespace))
                expected = [_PG_KINDS[column.physical_type.kind][0] for column in table.columns]
                description = cursor.description
                if description is None or [item.type_code for item in description] != expected:
                    code = 'source_codec_unsupported'
                else:
                    return cursor, guard
        except _read_contract.ReadContractError as error:
            code = error.code
        except Exception as error:
            code = 'snapshot_resource_limit' if guard.timed_out(error) else 'source_read_failed'
        self._failed(code)

    def _iterate(self, index):
        table, tags = self._tables[index], self._tags[index]
        expected, limits = self._summary.counts[index], self._limits
        width = len(table.columns)
        checked = self._checked_pg if self._dialect == 'pg' else self._checked
        cursor = None
        try:
            cursor, guard = self._open_payload(table)
            seen = 0
            while True:
                code = None
                try:
                    self._active()
                    guard.fetch()
                    row = _fetchone(cursor)
                except SnapshotRowsError:
                    raise
                except _read_contract.ReadContractError as error:
                    code = error.code
                except Exception as error:
                    code = 'snapshot_resource_limit' if guard.timed_out(error) else 'source_read_failed'
                if code is not None:
                    self._failed(code)
                if row is None:
                    break
                seen += 1
                if seen > expected:
                    self._failed('source_row_count_mismatch')
                yield checked(row, width, tags, limits, table)
            if seen != expected:
                self._failed('source_row_count_mismatch')
        finally:
            self._iterating = False
            if cursor is not None:
                cursor.close()

    def _checked(self, row, width, tags, limits, table=None):
        if type(row) is not tuple or len(row) != 2 * width:
            self._failed('source_read_failed')
        values, total = [], 0
        for position in range(width):
            value, storage = row[2 * position], row[2 * position + 1]
            if (type(storage) is not str or storage not in _TAG or type(value) is not _PYTYPE[storage]
                    or _TAG[storage] not in tags[position]):
                self._failed('source_read_failed')
            cost = _python_cost(storage, value)
            total += cost
            if cost > limits.max_cell_bytes or total > limits.max_row_bytes:
                self._failed('snapshot_resource_limit')
            values.append(value)
        return tuple(values)

    def _checked_pg(self, row, width, tags, limits, table):
        if type(row) is not tuple or len(row) != width:
            self._failed('source_read_failed')
        total = 0
        for value, column, allowed in zip(row, table.columns, tags):
            kind = column.physical_type.kind
            pytype, tag = _PG_KINDS[kind][1], _PG_KINDS[kind][2]
            if value is None:
                if 'n' not in allowed:
                    self._failed('source_read_failed')
            elif type(value) is not pytype or tag not in allowed:
                self._failed('source_read_failed')
            elif kind == 'pg_timestamptz' and value.utcoffset() != _dt.timedelta(0):
                self._failed('source_read_failed')
            cost = _pg_python_cost(kind, value)
            total += cost
            if cost > limits.max_cell_bytes or total > limits.max_row_bytes:
                self._failed('snapshot_resource_limit')
        return row

    def _close(self):
        self._state = 'closed'
        failed = False
        for cursor in self._cursors:
            try:
                cursor.close()
            except Exception:
                failed = True
        return failed

    def _cursors_for_test(self):
        return tuple(self._cursors)


_KEY = object()


class _RowsContext:
    __slots__ = ('source', 'contract', 'limits', 'reader')

    def __init__(self, source, contract, limits):
        self.source, self.contract, self.limits, self.reader = source, contract, limits, None

    def __enter__(self):
        if self.reader is not None:
            _fail('snapshot_inactive')
        if type(self.limits) is not RowLimits:
            _fail('snapshot_arguments_invalid')
        code = None
        try:
            connection = _catalog._resolve(self.source)
            _read_contract._reading(self.contract, connection)
        except _catalog.CatalogError as error:
            code = error.code if error.code in _CODES else 'snapshot_inactive'
        except _read_contract.ReadContractError as error:
            code = error.code
        if code is not None:
            _fail(code)
        descriptor = self.source.descriptor
        if descriptor.dialect not in ('sqlite', 'pg'):
            _fail('source_codec_unsupported')
        tables = table_order(descriptor)
        if len(tables) > _MAX_TABLES:
            _fail('snapshot_resource_limit')
        tags = []
        for table in tables:
            allowed = _allowed_tags(self.source.profile, table)
            if (not table.columns or len(table.columns) > _CODEC.max_columns or not table.primary_key
                    or len(allowed) != len(table.columns)):
                _fail('source_codec_unsupported')
            if descriptor.dialect == 'pg':
                if any(column.physical_type.kind not in _PG_KINDS
                       or not allowed[position] <= {_PG_KINDS[column.physical_type.kind][2], 'n'}
                       for position, column in enumerate(table.columns)):
                    _fail('source_codec_unsupported')
            elif any(tag not in _STORAGE for group in allowed for tag in group):
                _fail('source_codec_unsupported')
            tags.append(allowed)
        self.reader = SnapshotRows(self.source, self.contract, self.limits, tables, tuple(tags), _key=_KEY)
        return self.reader

    def __exit__(self, kind, error, traceback):
        if self.reader._close() and error is None:
            _fail('source_read_failed')
        return False


def _open_rows(source, contract, limits):
    """Private export entry: rows of an active `_catalog_for_export` snapshot."""
    return _RowsContext(source, contract, limits)
