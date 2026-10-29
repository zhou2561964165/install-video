"""B6 E3: one-shot import of a validated snapshot bundle into an empty PostgreSQL at the expected head.

import_snapshot(manifest, target, *, dry_run=True, legacy_media_root=None, trusted_parent_ack)
  1. load_export: the bundle is fully validated (manifest, schema, sizes, hashes) in the same pass
     that yields its rows; nothing is read twice.
  2. Target gate, inside the import transaction: alembic head == TARGET_HEAD, the import ledger is
     empty, every business table is empty and resourcecounter holds only the migration seeds.
  3. Rows are inserted in foreign-key order with values converted to the reflected target types.
     Equivalence rule: the result equals running the migration chain in place on the source, plus
     the contract's legacy transforms (A contract §6 paragraph 6, C6b):
       - queued/downloading/merging v1 Jobs -> internal_state 'legacy_hold' (status kept);
       - done v1 Jobs -> legacy_check from an lstat-only look in the old media root
         (verified / missing / mismatch / unchecked); files are never opened, copied or hashed.
     Counters: the receipt seed is recomputed from the imported receipts (as b1b_0002 does);
     a source that has counters replaces the seeds. The ledger row is written last.
  4. dry_run rolls the whole transaction back: PostgreSQL itself checks every FK, CHECK and unique
     constraint, and nothing persists. A recorded manifest returns 'already_imported' with no write.
verify_snapshot re-reads the bundle and compares every row and field read-only.

Output never carries row values, e-mail addresses, URLs or credentials: only table names, counts
and fixed codes. The target engine is supplied explicitly (no .env, no application settings).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import stat

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, Float, Integer, MetaData, Numeric, String, Text,
                        delete, func, insert, select, text, update)
from sqlalchemy.exc import DBAPIError, IntegrityError

from tools import production_db_export as export
from tools.production_db_snapshot_profiles import SOURCE_PROFILES
from tools.production_db_snapshot_schema import schema_fingerprint

TARGET_HEAD = 't1_0015'  # admin M1 tables exist but stay empty at import time (grants come after import)
SCHEMA = 'app'
_LEGACY_RUNNING = frozenset({'queued', 'downloading', 'merging'})
# NOT NULL columns the migration chain backfilled for pre-existing rows, then dropped the default.
_BACKFILL = {'billingcheckout': {'reconcile_attempts': 0, 'revision': 0},
             'billingevent': {'provider_account_scope': 'legacy_unknown'}}
_SEED_COUNTERS = {('receipt_entries', 'global'): 0, ('admission_slots', 'global'): 0}
_NOT_BUSINESS = frozenset({'alembic_version', 'resourcecounter', 'dataimport'})
_SEGMENT = re.compile(r'[A-Za-z0-9-]{1,64}\Z')
# Business values the application writes (models/services); legacy columns without a PG CHECK.
_ENUMS = {('downloadidempotency', 'state'): frozenset({'pending', 'complete', 'uncertain'}),
          ('billingcheckout', 'state'): frozenset({'pending', 'open', 'paid', 'expired', 'failed'}),
          ('membership', 'status'): frozenset({'free', 'active', 'expired'})}
_NON_NEGATIVE = {('quota', 'downloads_used'), ('quota', 'limit'), ('membership', 'revision'),
                 ('job', 'file_size'), ('downloadaccess', 'max_height'), ('billingcheckout', 'duration_days')}
# Exactly what SQLModel/SQLite or PG text produce: date, time, optional fraction, optional offset.
_DATETIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?'
                       r'(Z|[+-][0-9]{2}:[0-9]{2})?\Z', re.ASCII)
_DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}\Z', re.ASCII)
_REAL_METHODS = frozenset({'sqlite_readonly_snapshot_v1', 'pg_repeatable_read_readonly_v1'})
_IDENT = re.compile(r'[a-z_][a-z0-9_]{0,62}\Z')
_REPARSE_POINT = 0x400


class ImportFailure(RuntimeError):
    """Fixed, value-free failure code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _Rollback(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ImportReport:
    status: str  # 'dry_run_ok' | 'imported' | 'already_imported'
    manifest_sha256: str
    schema_profile: str
    table_rows: dict
    transforms: dict


@dataclass(frozen=True, slots=True)
class VerificationReport:
    accepted: bool
    manifest_sha256: str
    table_rows: dict
    differences: tuple  # (table, code) pairs; no values


def _fail(code):
    error = ImportFailure(code)
    error.__suppress_context__ = True
    raise error


def _clean(code):
    """A fixed failure with no attached exception (its text could carry SQL parameters)."""
    error = ImportFailure(code)
    error.__context__ = error.__cause__ = None
    error.__suppress_context__ = True
    return error


def _load(manifest_path, trusted_parent_ack, allow_synthetic):
    code = None
    try:
        report, rows, export_id = export.load_export(manifest_path, trusted_parent_ack=trusted_parent_ack)
    except export.SnapshotExportError as error:
        code = 'bundle_' + error.code
    if code is not None:
        raise _clean(code)
    if not report.accepted or report.schema_profile not in SOURCE_PROFILES:
        _fail('bundle_not_accepted')
    if report.snapshot_method not in _REAL_METHODS and allow_synthetic is not True:
        _fail('bundle_synthetic_refused')  # production imports only real snapshots
    return report, SOURCE_PROFILES[report.schema_profile], rows, export_id


def _reflect(connection):
    metadata = MetaData(schema=SCHEMA)
    metadata.reflect(connection)
    return metadata


def _table(metadata, name):
    return metadata.tables[SCHEMA + '.' + name]


def _gate(connection, metadata, manifest_sha256):
    """Inside the import transaction: right head, nothing imported yet, business tables empty.

    Every app table is locked (EXCLUSIVE: readers still read, nobody else writes) before anything
    is checked, so no concurrent writer can slip rows or counter increments in after the check.
    """
    head = connection.scalar(text('SELECT version_num FROM app.alembic_version'))
    if head != TARGET_HEAD:
        _fail('target_head_mismatch')
    names = ', '.join('app."' + table.name + '"' for table in sorted(metadata.tables.values(), key=lambda t: t.name)
                      if _IDENT.match(table.name))
    connection.execute(text('LOCK TABLE ' + names + ' IN EXCLUSIVE MODE'))
    ledger = _table(metadata, 'dataimport')
    if connection.scalar(select(func.count()).select_from(ledger).where(
            ledger.c.manifest_sha256 == manifest_sha256)):
        return 'already_imported'
    if connection.scalar(select(func.count()).select_from(ledger)):
        _fail('target_already_imported')
    for table in sorted(metadata.tables.values(), key=lambda table: table.name):
        if table.name not in _NOT_BUSINESS and connection.scalar(select(func.count()).select_from(table)):
            _fail('target_not_empty')
    counters = _table(metadata, 'resourcecounter')
    seeds = {(row.resource, row.scope): row.used for row in connection.execute(select(counters))}
    if seeds != _SEED_COUNTERS:
        _fail('target_not_empty')
    return None


def _to_time(value, kind):
    if isinstance(value, datetime):
        result = value
    elif type(value) is str and _DATETIME.match(value):
        try:
            result = datetime.fromisoformat(value)
        except ValueError:
            _fail('import_time_invalid')
    else:
        _fail('import_time_invalid')
    if kind is date:
        return result.date() if isinstance(result, datetime) else result
    # SQLModel wrote naive UTC timestamps to SQLite; an explicit offset is kept as given.
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


def _convert(value, column):
    """Source value -> the reflected target column type; never guesses or repairs a value."""
    if value is None:
        return None
    kind = column.type
    if isinstance(kind, DateTime):
        return _to_time(value, datetime)
    if isinstance(kind, Date):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if type(value) is str and _DATE.match(value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                _fail('import_time_invalid')
        _fail('import_time_invalid')
    if isinstance(kind, Boolean):
        if type(value) is bool:
            return value
        if type(value) is int and value in (0, 1):
            return bool(value)
        _fail('import_type_invalid')
    if isinstance(kind, (Integer, BigInteger)):
        if type(value) is not int:
            _fail('import_type_invalid')
        return value
    if isinstance(kind, (Float, Numeric)):
        if type(value) not in (int, float):
            _fail('import_type_invalid')
        return value
    if isinstance(kind, (String, Text)):
        if type(value) is not str:
            _fail('import_type_invalid')
        return value
    _fail('import_type_invalid')  # a target type this importer does not know: never pass through


def _plain_dir(path):
    info = path.lstat()
    return (stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT)


def _legacy_check(root, job_id, file_path, file_size):
    """lstat-only check of a v1 done Job's file under root/<job_id>/ (never opened or followed)."""
    if root is None:
        return 'unchecked'
    if (type(job_id) is not str or not _SEGMENT.match(job_id) or type(file_path) is not str or not file_path
            or type(file_size) is not int or isinstance(file_size, bool) or file_size < 0):
        return 'mismatch'
    candidate = Path(file_path)
    job_dir = root / job_id
    if (not candidate.is_absolute() or any(part in ('.', '..') for part in Path(file_path).parts)
            or '\x00' in file_path or (candidate.parent != job_dir and job_dir not in candidate.parents)):
        return 'mismatch'  # never fold '..' lexically: the stored path is taken literally
    try:
        level = job_dir
        if not _plain_dir(level):
            return 'mismatch'
        for part in candidate.relative_to(job_dir).parts[:-1]:
            level = level / part
            if not _plain_dir(level):
                return 'mismatch'
        info = candidate.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return 'missing'
    except (OSError, ValueError):
        return 'mismatch'  # an unusable path is not evidence of a good file
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1
            or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT):
        return 'mismatch'
    return 'verified' if info.st_size == file_size else 'mismatch'


def _legacy_root(value):
    if value is None:
        return None
    root = Path(value)
    if not root.is_absolute():
        _fail('legacy_root_invalid')
    try:
        if not _plain_dir(root):
            _fail('legacy_root_invalid')
    except OSError:
        _fail('legacy_root_invalid')
    return root


def _source_tables(profile, metadata):
    """The imported tables in foreign-key order (deterministic; only FKs among these tables count)."""
    names = {table.name for table in profile.descriptor.tables}
    if any(SCHEMA + '.' + name not in metadata.tables for name in names):
        _fail('target_schema_mismatch')
    needs = {name: {key.column.table.name for key in _table(metadata, name).foreign_keys
                    if key.column.table.name in names and key.column.table.name != name} for name in names}
    ordered = []
    while needs:
        ready = sorted(name for name, required in needs.items() if not required - set(ordered))
        if not ready:
            _fail('target_schema_mismatch')  # a cycle among imported tables
        ordered.extend(ready)
        for name in ready:
            del needs[name]
    return [_table(metadata, name) for name in ordered]


def _operated_jobs(rows, columns):
    """Job ids an operation still refers to: such a Job is not a lease-less legacy Job."""
    names = columns.get('downloadoperation')
    if not names or 'job_id' not in names:
        return frozenset()
    index = names.index('job_id')
    return frozenset(values[index] for values in rows.get('downloadoperation', ()) if values[index] is not None)


def _rows_for(profile_table_columns, target, source_rows, root, transforms, operated=frozenset()):
    """Converted insert dicts for one table, with the backfill and legacy transforms applied."""
    if any(name not in target.c for name in profile_table_columns):
        _fail('target_schema_mismatch')
    columns = [target.c[name] for name in profile_table_columns]
    backfill = _BACKFILL.get(target.name, {})
    result = []
    for values in source_rows:
        if len(values) != len(columns):
            _fail('bundle_shape_invalid')
        row = {column.name: _convert(value, column) for column, value in zip(columns, values)}
        for name, value in row.items():
            allowed = _ENUMS.get((target.name, name))
            if allowed is not None and value not in allowed:
                _fail('import_enum_invalid')
            if (target.name, name) in _NON_NEGATIVE and value is not None and value < 0:
                _fail('import_negative_count')
        for name, value in backfill.items():
            row.setdefault(name, value)
        if target.name == 'job':
            row.setdefault('internal_state', None)  # uniform keys for executemany; NULL unless transformed
            row.setdefault('legacy_check', None)
            status = row.get('status')
            if status in _LEGACY_RUNNING and row.get('id') in operated:
                _fail('import_legacy_job_has_operation')  # the contract holds only lease-less Jobs
            if status in _LEGACY_RUNNING:
                row['internal_state'] = 'legacy_hold'
                transforms['job_legacy_hold'] = transforms.get('job_legacy_hold', 0) + 1
            elif status == 'done':
                check = _legacy_check(root, row.get('id'), row.get('file_path'), row.get('file_size'))
                row['legacy_check'] = check
                key = 'job_legacy_' + check
                transforms[key] = transforms.get(key, 0) + 1
        result.append(row)
    return result


def _constraint_code(error):
    name = getattr(getattr(getattr(error, 'orig', None), 'diag', None), 'constraint_name', None)
    return 'import_constraint:' + name if type(name) is str and _IDENT.match(name) else 'import_constraint_violation'


def import_snapshot(manifest_path, target, *, dry_run=True, legacy_media_root=None, trusted_parent_ack,
                    allow_synthetic=False):
    if type(dry_run) is not bool or type(allow_synthetic) is not bool:
        _fail('import_arguments_invalid')
    root = _legacy_root(legacy_media_root)
    report, profile, rows, export_id = _load(manifest_path, trusted_parent_ack, allow_synthetic)
    operated = _operated_jobs(rows, {table.name: [column.name for column in table.columns]
                                     for table in profile.descriptor.tables})
    columns = {table.name: [column.name for column in table.columns] for table in profile.descriptor.tables}
    transforms, table_rows = {}, {}
    status = code = None
    try:
        # A real transaction whatever the engine default: dry_run's rollback must undo everything.
        with target.connect().execution_options(isolation_level='READ COMMITTED') as connection:
            with connection.begin():
                metadata = _reflect(connection)
                if _gate(connection, metadata, report.manifest_sha256) == 'already_imported':
                    status = 'already_imported'
                    raise _Rollback()
                for target_table in _source_tables(profile, metadata):
                    batch = _rows_for(columns[target_table.name], target_table, rows.get(target_table.name, ()),
                                      root, transforms, operated)
                    table_rows[target_table.name] = len(batch)
                    if target_table.name == 'resourcecounter' and batch:
                        connection.execute(delete(target_table))  # real source counters replace the seeds
                    if batch:
                        connection.execute(insert(target_table), batch)
                if not table_rows.get('resourcecounter'):
                    counters = _table(metadata, 'resourcecounter')
                    connection.execute(update(counters).where(
                        counters.c.resource == 'receipt_entries', counters.c.scope == 'global').values(
                        used=table_rows.get('downloadidempotency', 0)))  # as b1b_0002 seeds it in place
                ledger = _table(metadata, 'dataimport')
                connection.execute(insert(ledger).values(
                    manifest_sha256=report.manifest_sha256, export_id=export_id,
                    schema_profile=report.schema_profile, schema_fingerprint=schema_fingerprint(profile.descriptor),
                    snapshot_method=report.snapshot_method,
                    target_head=TARGET_HEAD, table_rows=json.dumps(table_rows, sort_keys=True),
                    transforms=json.dumps(transforms, sort_keys=True), completed_at=func.now()))
                if dry_run:
                    status = 'dry_run_ok'
                    raise _Rollback()
                status = 'imported'
    except _Rollback:
        pass
    except IntegrityError as error:
        code = _constraint_code(error)
    except DBAPIError:
        code = 'import_database_error'
    if code is not None:
        raise _clean(code)  # raised outside the except suite: no SQL or parameters attached
    return ImportReport(status, report.manifest_sha256, report.schema_profile, dict(table_rows), dict(transforms))


def _column_default(column):
    """The value the migration chain gives a column absent from the source (integer default or NULL)."""
    default = column.server_default
    if default is None:
        return None
    literal = str(getattr(default, 'arg', '')).strip().strip("'")
    if re.fullmatch(r'-?[0-9]{1,18}', literal):
        return int(literal)
    _fail('target_schema_mismatch')  # an unknown default: refuse to guess what in-place would give


def verify_snapshot(manifest_path, target, *, legacy_media_root=None, trusted_parent_ack, allow_synthetic=False):
    """Read-only: every bundle row and every target column is present, equal (after the allowed
    transforms, migration defaults for columns the source lacks) and alone."""
    root = _legacy_root(legacy_media_root)
    report, profile, rows, export_id = _load(manifest_path, trusted_parent_ack, allow_synthetic)
    columns = {table.name: [column.name for column in table.columns] for table in profile.descriptor.tables}
    differences, table_rows, transforms = [], {}, {}
    with target.connect().execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True) as connection:
        with connection.begin():
            metadata = _reflect(connection)
            if connection.scalar(text('SELECT version_num FROM app.alembic_version')) != TARGET_HEAD:
                differences.append(('alembic_version', 'target_head_mismatch'))
            ledger = _table(metadata, 'dataimport')
            entries = connection.execute(select(ledger)).all()
            recorded = next((entry for entry in entries if entry.manifest_sha256 == report.manifest_sha256), None)
            if recorded is None:
                differences.append(('dataimport', 'ledger_missing'))
            elif len(entries) != 1:
                differences.append(('dataimport', 'unexpected_rows'))
            if recorded is not None and (recorded.export_id, recorded.schema_profile, recorded.schema_fingerprint,
                                         recorded.snapshot_method, recorded.target_head) != (
                    export_id, report.schema_profile, schema_fingerprint(profile.descriptor),
                    report.snapshot_method, TARGET_HEAD):
                differences.append(('dataimport', 'ledger_fields_mismatch'))
            for target_table in _source_tables(profile, metadata):
                expected = _rows_for(columns[target_table.name], target_table, rows.get(target_table.name, ()),
                                     root, transforms, _operated_jobs(rows, columns))
                absent = {column.name: _column_default(column) for column in target_table.columns
                          if column.name not in columns[target_table.name]}
                key = [column for column in target_table.primary_key.columns]
                actual = [dict(row._mapping) for row in connection.execute(select(target_table).order_by(*key))]
                table_rows[target_table.name] = len(actual)
                if len(actual) != len(expected):
                    differences.append((target_table.name, 'row_count_mismatch'))
                index = {tuple(row[column.name] for column in key): row for row in actual}
                for row in expected:
                    found = index.get(tuple(row[column.name] for column in key))
                    if found is None:
                        differences.append((target_table.name, 'row_missing'))
                        continue
                    full = absent | row  # every target column: source/transform value, else in-place default
                    for name, value in full.items():
                        if found.get(name) == value:
                            continue
                        # A file that changed since the import is drift, not a database edit.
                        drift = (name == 'legacy_check' and found.get(name) in ('verified', 'missing', 'mismatch',
                                                                                'unchecked'))
                        differences.append((target_table.name, 'legacy_check_changed' if drift else 'value_mismatch'))
            for table in sorted(metadata.tables.values(), key=lambda table: table.name):
                if table.name not in columns and table.name not in _NOT_BUSINESS:
                    if connection.scalar(select(func.count()).select_from(table)):
                        differences.append((table.name, 'unexpected_rows'))
            if recorded is not None and json.loads(recorded.table_rows) != table_rows:
                differences.append(('dataimport', 'ledger_counts_mismatch'))
            if recorded is not None and json.loads(recorded.transforms) != transforms:
                differences.append(('dataimport', 'ledger_transforms_mismatch'))
            if not rows.get('resourcecounter'):
                counters = {(row.resource, row.scope): row.used
                            for row in connection.execute(select(_table(metadata, 'resourcecounter')))}
                expected = dict(_SEED_COUNTERS) | {('receipt_entries', 'global'): table_rows.get('downloadidempotency', 0)}
                if counters != expected:
                    differences.append(('resourcecounter', 'counter_mismatch'))
    return VerificationReport(not differences, report.manifest_sha256, table_rows, tuple(sorted(set(differences))))
