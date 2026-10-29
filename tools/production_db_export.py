"""Snapshot bundles: synthetic or contract-gated source export, plus validation.

Hashes establish byte integrity, not source authentication or migration safety.
No environment or application configuration is read. Only export_snapshot reads
a database, through a caller Connection plus a module-issued read contract; the
DB helpers are imported lazily so validation and synthetic builds stay DB-free.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from functools import wraps
import hashlib
import os
import re
import time
import uuid

from tools import production_db_snapshot_files as files
from tools import production_db_snapshot_format as codec
from tools.production_db_snapshot_profiles import SOURCE_PROFILES
from tools.production_db_snapshot_schema import schema_document, schema_fingerprint


_CODES = frozenset(('source_export_not_implemented', 'snapshot_arguments_invalid',
    'snapshot_limits_invalid', 'snapshot_path_invalid', 'snapshot_permissions_invalid',
    'filesystem_security_unsupported', 'snapshot_resource_limit', 'snapshot_manifest_invalid',
    'snapshot_schema_invalid', 'snapshot_file_set_invalid', 'snapshot_integrity_failed',
    'snapshot_record_invalid', 'snapshot_identity_changed', 'snapshot_io_failed',
    'snapshot_cleanup_failed', 'snapshot_publish_outcome_uncertain',
    # Source export: read contract, row reader and catalog fixed codes pass through.
    'driver_contract_required', 'source_codec_unsupported', 'source_read_failed',
    'source_row_count_mismatch', 'source_profile_unsupported', 'catalog_failed',
    'catalog_limit_exceeded', 'connection_required', 'active_transaction_refused',
    'unsupported_dialect', 'sql_logging_refused', 'sqlite_readonly_uri_required',
    'postgres_driver_unsupported', 'connection_restore_failed', 'snapshot_failed',
    'snapshot_inactive', 'snapshot_owner_mismatch'))
_FILE_MAP = {name: name for name in ('snapshot_limits_invalid', 'snapshot_path_invalid',
    'snapshot_permissions_invalid', 'filesystem_security_unsupported', 'snapshot_resource_limit',
    'snapshot_identity_changed', 'snapshot_io_failed', 'snapshot_cleanup_failed')}
_FILE_MAP.update(snapshot_file_invalid='snapshot_file_set_invalid',
    snapshot_name_invalid='snapshot_file_set_invalid')
_RESOURCE = frozenset(('codec_cell_limit', 'codec_row_limit', 'codec_record_limit',
    'json_resource_limit'))
_HASH = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_IDENTIFIER = re.compile(r'[0-9a-f]{32}\Z', re.ASCII)
_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z', re.ASCII)
_FORMAT = 'install-video-db-snapshot'
_SYNTHETIC_METHOD, _SYNTHETIC_VERSION = 'synthetic_rows_v1', 'synthetic-not-observed'
# (descriptor dialect, contract domain) -> method. Descriptors name PostgreSQL 'pg'.
_METHODS = {('sqlite', 'operational'): 'sqlite_readonly_snapshot_v1',
            ('sqlite', 'synthetic'): 'sqlite_synthetic_readonly_snapshot_v1',
            ('pg', 'operational'): 'pg_repeatable_read_readonly_v1',
            ('pg', 'synthetic'): 'pg_synthetic_repeatable_read_readonly_v1'}
_VERSION = re.compile(r'[0-9]{1,6}(?:\.[0-9]{1,6}){0,3}\Z', re.ASCII)


class SnapshotExportError(RuntimeError):
    def __init__(self, *args, **kwargs):
        value = args[0] if len(args) == 1 and not kwargs and type(args[0]) is str else ''
        self.code = value if value in _CODES else 'snapshot_arguments_invalid'
        super().__init__(self.code)


def _fail(code):
    error = SnapshotExportError(code)
    try:
        raise error
    except SnapshotExportError:
        error.__cause__ = error.__context__ = None
        raise


def _safe(function):
    @wraps(function)
    def boundary(*args, **kwargs):
        code = None
        try:
            return function(*args, **kwargs)
        except SnapshotExportError as error:
            code = error.code
        except files.SnapshotFileError as error:
            code = _FILE_MAP.get(error.code, 'snapshot_io_failed')
        except codec.SnapshotError as error:
            code = 'snapshot_resource_limit' if error.code in _RESOURCE else 'snapshot_schema_invalid'
        except TypeError:
            code = 'snapshot_arguments_invalid'
        except Exception:
            code = 'snapshot_io_failed'
        _fail(code)
    return boundary


class _LimitsMeta(type):
    def __call__(cls, *args, **kwargs):
        try:
            return super().__call__(*args, **kwargs)
        except Exception:
            pass
        _fail('snapshot_limits_invalid')


_CODEC_HARD = codec.CodecLimits()
_FILES_HARD = files.FileLimits()


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportLimits(metaclass=_LimitsMeta):
    codec: codec.CodecLimits = _CODEC_HARD
    files: files.FileLimits = _FILES_HARD
    max_tables: int = 18
    max_total_rows: int = 10_000_000
    max_wall_seconds: int = 300

    def __post_init__(self):
        if type(self.codec) is not codec.CodecLimits or type(self.files) is not files.FileLimits:
            _fail('snapshot_limits_invalid')
        for value, maximum in ((self.max_tables, 18), (self.max_total_rows, 10_000_000),
                (self.max_wall_seconds, 300)):
            if type(value) is not int or not 1 <= value <= maximum:
                _fail('snapshot_limits_invalid')
        for actual, hard in ((self.codec, _CODEC_HARD), (self.files, _FILES_HARD)):
            for field in fields(hard):
                value = getattr(actual, field.name)
                if type(value) is not int or not 1 <= value <= getattr(hard, field.name):
                    _fail('snapshot_limits_invalid')
        if self.files.max_record_bytes > self.files.max_file_bytes:
            _fail('snapshot_limits_invalid')


DEFAULT_LIMITS = ExportLimits()


@dataclass(frozen=True, slots=True, repr=False)
class ExportValidationReport:
    accepted: bool
    format: str
    schema_profile: str
    table_count: int
    row_count: int
    data_bytes: int
    file_count: int
    manifest_sha256: str
    migration_eligible: str
    error_codes: tuple[str, ...]
    snapshot_method: str


@dataclass(frozen=True, slots=True, repr=False)
class _SyntheticBuildResult:
    status: str
    published: bool
    cleanup_complete: bool
    directory_synced: bool | None
    error_codes: tuple[str, ...]
    table_count: int
    row_count: int
    data_bytes: int
    file_count: int
    manifest_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class ExportResult:
    status: str
    published: bool
    cleanup_complete: bool
    directory_synced: bool | None
    error_codes: tuple[str, ...]
    table_count: int
    row_count: int
    data_bytes: int
    file_count: int
    manifest_sha256: str


def _require(condition, code):
    if not condition:
        _fail(code)


def _method_allowed(method, dialect):
    return any(value == method and key[0] == dialect for key, value in _METHODS.items())


def _limits(value):
    _require(type(value) is ExportLimits, 'snapshot_limits_invalid')
    # Recheck public frozen values defensively before any I/O.
    value.__post_init__()
    return value


def _keys(value, expected, code):
    _require(type(value) is dict and len(value) == len(expected), code)
    _require(all(type(k) is str for k in value) and set(value) == set(expected), code)


def _integer(value, maximum, code, minimum=0):
    _require(type(value) is int and minimum <= value <= maximum, code)
    return value


def _count(value, maximum, minimum=0):
    _require(type(value) is int and value >= minimum, 'snapshot_manifest_invalid')
    _require(value <= maximum, 'snapshot_resource_limit')
    return value


def _constant(value, expected, code):
    _require(type(value) is type(expected) and value == expected, code)


def _json(data, limits, code):
    try:
        return codec.strict_json_loads(data, max_bytes=min(limits.files.max_metadata_bytes,
            limits.codec.max_record_bytes), limits=limits.codec)
    except codec.SnapshotError as error:
        resource = error.code in _RESOURCE
    _fail('snapshot_resource_limit' if resource else code)


def _canonical(value, limits, code):
    try:
        return codec.canonical_json_bytes(value, max_bytes=min(limits.files.max_metadata_bytes,
            limits.codec.max_record_bytes), limits=limits.codec)
    except codec.SnapshotError as error:
        resource = error.code in _RESOURCE
    _fail('snapshot_resource_limit' if resource else code)


def _limits_document(limits):
    return {'codec': {f.name: getattr(limits.codec, f.name) for f in fields(limits.codec)},
        'files': {f.name: getattr(limits.files, f.name) for f in fields(limits.files)},
        'max_tables': limits.max_tables, 'max_total_rows': limits.max_total_rows,
        'max_wall_seconds': limits.max_wall_seconds}


def _effective(value, local):
    code = 'snapshot_manifest_invalid'
    _keys(value, ('codec', 'files', 'max_tables', 'max_total_rows', 'max_wall_seconds'), code)
    chosen = {}
    for key, constructor, hard in (('codec', codec.CodecLimits, _CODEC_HARD),
            ('files', files.FileLimits, _FILES_HARD)):
        names = tuple(f.name for f in fields(hard))
        _keys(value[key], names, code)
        for name in names:
            _integer(value[key][name], getattr(hard, name), code, 1)
        chosen[key] = constructor(**{name: min(value[key][name], getattr(getattr(local, key), name))
            for name in names})
    _require(value['files']['max_record_bytes'] <= value['files']['max_file_bytes'], code)
    for name, maximum in (('max_tables', 18), ('max_total_rows', 10_000_000), ('max_wall_seconds', 300)):
        _integer(value[name], maximum, code, 1)
        chosen[name] = min(value[name], getattr(local, name))
    # Caller and declaration each obey record<=chunk, so their minima do too.
    return ExportLimits(**chosen)


def _timestamp(value):
    _require(type(value) is str and len(value) == 27 and _TIME.fullmatch(value) is not None,
        'snapshot_manifest_invalid')
    try:
        return datetime(int(value[:4]), int(value[5:7]), int(value[8:10]), int(value[11:13]),
            int(value[14:16]), int(value[17:19]), int(value[20:26]), tzinfo=timezone.utc)
    except ValueError:
        pass
    _fail('snapshot_manifest_invalid')


def _tables(profile):
    return tuple(sorted(profile.descriptor.tables + profile.descriptor.metadata_tables,
        key=lambda table: table.name))


def _tags(profile, table):
    for item, tags in zip(profile.descriptor.tables, profile.allowed_tags):
        if item.name == table.name:
            return tags
    return (frozenset(('s',)),)


def _chunk_name(table, chunk):
    return f't{table:02d}-{chunk:06d}.jsonl'


def _parse_manifest(raw, local):
    code = 'snapshot_manifest_invalid'
    manifest = _json(raw, local, code)
    _keys(manifest, ('format', 'format_version', 'codec_version', 'schema_profile',
        'schema_profile_version', 'export_id', 'created_at', 'started_at', 'ended_at',
        'source', 'snapshot_method', 'schema_fingerprint', 'limits_used', 'privacy',
        'migration_eligible', 'tables', 'files', 'totals'), code)
    limits = _effective(manifest['limits_used'], local)
    _json(raw, limits, code)  # Same bounded bytes; never reread marker from disk.
    for key, value in (('format', _FORMAT), ('format_version', 1), ('codec_version', 1),
            ('schema_profile_version', 1),
            ('privacy', 'restricted-local-plaintext'), ('migration_eligible', 'not_assessed')):
        _constant(manifest[key], value, code)
    method = manifest['snapshot_method']
    _require(type(method) is str and (method == _SYNTHETIC_METHOD or method in _METHODS.values()), code)
    profile_id = manifest['schema_profile']
    _require(type(profile_id) is str and profile_id in SOURCE_PROFILES, 'snapshot_schema_invalid')
    profile = SOURCE_PROFILES[profile_id]
    _require(type(manifest['export_id']) is str and _IDENTIFIER.fullmatch(manifest['export_id']) is not None, code)
    started, ended, created = (_timestamp(manifest[k]) for k in ('started_at', 'ended_at', 'created_at'))
    _require(started <= ended <= created, code)
    _keys(manifest['source'], ('dialect', 'namespace', 'version'), code)
    for key, value in (('dialect', profile.descriptor.dialect), ('namespace', profile.descriptor.namespace)):
        _constant(manifest['source'][key], value, code)
    version = manifest['source']['version']
    if method == _SYNTHETIC_METHOD:
        _constant(version, _SYNTHETIC_VERSION, code)
    else:
        # A real method is bound to the profile's dialect; version is an observed numeric release.
        _require(_method_allowed(method, profile.descriptor.dialect), code)
        _require(type(version) is str and len(version) <= 32 and _VERSION.fullmatch(version) is not None, code)
    fingerprint = schema_fingerprint(profile.descriptor)
    _constant(manifest['schema_fingerprint'], fingerprint, 'snapshot_schema_invalid')
    expected = _tables(profile)
    table_docs, file_docs = manifest['tables'], manifest['files']
    _require(type(table_docs) is list and len(table_docs) <= limits.max_tables, 'snapshot_resource_limit')
    _require(len(table_docs) == len(expected), code)
    _require(type(file_docs) is list and 1 <= len(file_docs) < limits.files.max_files, 'snapshot_resource_limit')
    _keys(manifest['totals'], ('table_count', 'row_count', 'data_bytes', 'file_count'), code)
    for key, maximum in (('table_count', limits.max_tables), ('row_count', limits.max_total_rows),
            ('data_bytes', limits.files.max_total_bytes), ('file_count', limits.files.max_files)):
        _count(manifest['totals'][key], maximum)
    ordered = [('schema.json', 'schema', None)]
    total_rows = 0
    for index, (table_doc, table) in enumerate(zip(table_docs, expected)):
        _keys(table_doc, ('table_index', 'name', 'columns', 'rows', 'chunks'), code)
        _constant(table_doc['table_index'], index, code)
        _constant(table_doc['name'], table.name, 'snapshot_schema_invalid')
        columns = table_doc['columns']
        _require(type(columns) is list and len(columns) == len(table.columns) and
            all(type(item) is str for item in columns), 'snapshot_schema_invalid')
        _require(columns == [column.name for column in table.columns], 'snapshot_schema_invalid')
        rows = _count(table_doc['rows'], limits.max_total_rows)
        total_rows += rows
        _require(total_rows <= limits.max_total_rows, 'snapshot_resource_limit')
        chunks = table_doc['chunks']
        _require(type(chunks) is list and 1 <= len(chunks) <= min(1_000_000, limits.files.max_files - 2), code)
        _require(len(ordered) + len(chunks) < limits.files.max_files, 'snapshot_resource_limit')
        if rows == 0:
            _require(len(chunks) == 1, code)
        for chunk_index, name in enumerate(chunks):
            _constant(name, _chunk_name(index, chunk_index), 'snapshot_file_set_invalid')
            ordered.append((name, 'rows', rows))
    _require(len(file_docs) == len(ordered), 'snapshot_file_set_invalid')
    data_bytes, counted_rows = 0, 0
    for file_doc, (name, kind, table_rows) in zip(file_docs, ordered):
        _keys(file_doc, ('name', 'kind', 'byte_count', 'row_count', 'sha256'), code)
        _constant(file_doc['name'], name, 'snapshot_file_set_invalid')
        _constant(file_doc['kind'], kind, code)
        cap = limits.files.max_metadata_bytes if kind == 'schema' else limits.files.max_file_bytes
        byte_count = _count(file_doc['byte_count'], cap, int(kind == 'schema'))
        if kind == 'schema':
            _constant(file_doc['row_count'], None, code)
        else:
            rows = _count(file_doc['row_count'], limits.max_total_rows)
            _require((rows == 0 and byte_count == 0 and table_rows == 0) or
                (rows > 0 and byte_count > 0 and table_rows > 0), code)
            counted_rows += rows
        _require(type(file_doc['sha256']) is str and _HASH.fullmatch(file_doc['sha256']) is not None, code)
        data_bytes += byte_count
        _require(data_bytes <= limits.files.max_total_bytes, 'snapshot_resource_limit')
    totals = dict(table_count=len(expected), row_count=total_rows, data_bytes=data_bytes, file_count=len(file_docs) + 1)
    _require(counted_rows == total_rows, 'snapshot_integrity_failed')
    for key, value in totals.items():
        _constant(manifest['totals'][key], value, 'snapshot_integrity_failed')
    return manifest, profile, limits


class _Budget:
    def __init__(self, limits, started):
        self.limits, self.started, self.data_bytes, self.rows = limits, started, 0, 0

    def tick(self):
        _require(time.monotonic() - self.started <= self.limits.max_wall_seconds, 'snapshot_resource_limit')

    def data(self, size):
        self.tick()
        self.data_bytes += size
        _require(self.data_bytes <= self.limits.files.max_total_bytes, 'snapshot_resource_limit')

    def row(self):
        self.tick()
        _require(self.rows < self.limits.max_total_rows, 'snapshot_resource_limit')
        self.rows += 1


@contextmanager
def _closing(resource):
    try:
        yield resource
    except BaseException as primary:
        try:
            resource.close()
        except BaseException as cleanup:
            # An existing cancellation wins; a new cancellation supersedes an
            # ordinary failure and outer owners still perform their closes.
            if isinstance(primary, Exception) and not isinstance(cleanup, Exception):
                raise
        raise
    else:
        resource.close()


def _read_metadata(directory, name, maximum, *, staged, budget):
    budget.tick()
    opener = directory.open_owned if staged else directory.open_file
    with _closing(opener(name)) as reader:
        data = bytearray()
        while True:
            budget.tick()
            block = reader.read_chunk(65536)
            budget.tick()
            if not block:
                break
            _require(len(data) + len(block) <= maximum, 'snapshot_resource_limit')
            data.extend(block)
    return bytes(data)


def _row(record, tags, limits):
    try:
        return codec.decode_row(record, allowed_tags=tags, limits=limits.codec)
    except codec.SnapshotError as error:
        resource = error.code in _RESOURCE
    _fail('snapshot_resource_limit' if resource else 'snapshot_record_invalid')


def _read_chunk(directory, entry, tags, budget, metadata_head, *, staged, sink=None):
    size, count, digest = 0, 0, hashlib.sha256()
    pending = bytearray()
    limit = min(budget.limits.files.max_record_bytes, budget.limits.codec.max_record_bytes)
    opener = directory.open_owned if staged else directory.open_file
    with _closing(opener(entry['name'])) as reader:
        while True:
            budget.tick()
            block = reader.read_chunk(65536)
            if not block:
                break
            size += len(block)
            _require(size <= budget.limits.files.max_file_bytes, 'snapshot_resource_limit')
            budget.data(len(block))
            digest.update(block)
            offset = 0
            while offset < len(block):
                end = block.find(b'\n', offset)
                end = len(block) if end < 0 else end + 1
                take = end - offset
                _require(len(pending) + take <= limit, 'snapshot_resource_limit')
                pending.extend(block[offset:end])
                offset = end
                if pending[-1] == 10:
                    budget.row()
                    values = _row(bytes(pending), tags, budget.limits)
                    if metadata_head is not None:
                        _require(len(values) == 1 and type(values[0]) is str and values[0] == metadata_head,
                            'snapshot_schema_invalid')
                    elif sink is not None:
                        sink.append(values)  # B6 E3 import: rows of a chunk whose bytes are then hash-checked
                    del values
                    pending.clear()
                    count += 1
        _require(not pending, 'snapshot_record_invalid')
    _require(size == entry['byte_count'] and count == entry['row_count'] and
        digest.hexdigest() == entry['sha256'], 'snapshot_integrity_failed')
    return count


def _collect(rows_by_table, name):
    return rows_by_table.setdefault(name, []) if rows_by_table is not None else None


def _validate_core(raw, directory, local, started, *, staged=False, sealed=None, initial_names=None,
                   rows_by_table=None):
    manifest, profile, limits = _parse_manifest(raw, local)
    budget = _Budget(limits, started)
    names = tuple(sorted(entry['name'] for entry in manifest['files']))
    expected_names = names if staged else tuple(sorted(names + ('manifest.json',)))
    if initial_names is None:
        initial_names = directory.file_names()
    _require(initial_names == expected_names, 'snapshot_file_set_invalid')
    if staged:
        _require(type(sealed) is tuple and len(sealed) == len(manifest['files']), 'snapshot_integrity_failed')
        for actual, entry in zip(sealed, manifest['files']):
            _require(type(actual) is files.FileDigest and actual.name == entry['name'] and
                actual.byte_count == entry['byte_count'] and actual.sha256 == entry['sha256'],
                'snapshot_integrity_failed')
    schema_raw = _read_metadata(directory, 'schema.json', limits.files.max_metadata_bytes,
        staged=staged, budget=budget)
    budget.data(len(schema_raw))
    schema = _json(schema_raw, limits, 'snapshot_schema_invalid')
    _keys(schema, ('descriptor', 'fingerprint'), 'snapshot_schema_invalid')
    _constant(schema['fingerprint'], schema_fingerprint(profile.descriptor), 'snapshot_schema_invalid')
    _require(_canonical(schema['descriptor'], limits, 'snapshot_schema_invalid') ==
        _canonical(schema_document(profile.descriptor), limits, 'snapshot_schema_invalid'), 'snapshot_schema_invalid')
    entry = manifest['files'][0]
    _require(len(schema_raw) == entry['byte_count'] and hashlib.sha256(schema_raw).hexdigest() == entry['sha256'],
        'snapshot_integrity_failed')
    file_index = 1
    metadata_names = frozenset(table.name for table in profile.descriptor.metadata_tables)
    for table, table_doc in zip(_tables(profile), manifest['tables']):
        count = 0
        head = profile.descriptor.heads[0] if table.name in metadata_names else None
        for unused in table_doc['chunks']:
            entry = manifest['files'][file_index]
            file_index += 1
            count += _read_chunk(directory, entry, _tags(profile, table), budget, head, staged=staged,
                                 sink=None if head is not None else _collect(rows_by_table, table.name))
        _require(count == table_doc['rows'], 'snapshot_integrity_failed')
        if head is not None:
            _require(count == 1, 'snapshot_schema_invalid')
    _require(budget.rows == manifest['totals']['row_count'] and budget.data_bytes == manifest['totals']['data_bytes'],
        'snapshot_integrity_failed')
    _require(directory.file_names() == expected_names, 'snapshot_file_set_invalid')
    budget.tick()
    report = ExportValidationReport(True, _FORMAT, profile.profile_id, len(manifest['tables']), budget.rows,
        budget.data_bytes, len(manifest['files']) + 1, hashlib.sha256(raw).hexdigest(), 'not_assessed', (),
        manifest['snapshot_method'])
    return report, limits


def _manifest_path(value):
    code = 'snapshot_path_invalid'
    _require(type(value) is str and 1 <= len(value) <= 240 and
        not any(ord(x) < 32 or ord(x) == 127 for x in value), code)
    if os.name == 'nt':
        _require(re.match(r'^[A-Za-z]:\\', value) is not None and '/' not in value and ':' not in value[2:], code)
        parts, separator, anchor = value[3:].split('\\'), '\\', value[:3]
        for part in parts:
            _require(not ('~' in part or any(x in part for x in '<>"|?*') or part.endswith((' ', '.')) or
                re.match(r'^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', part, re.I)), code)
    else:
        _require(value.startswith('/') and not value.startswith('//') and '//' not in value and ':' not in value, code)
        parts, separator, anchor = value[1:].split('/'), '/', '/'
    _require(2 <= len(parts) <= 64 and all(0 < len(part) <= 128 and part not in ('.', '..') for part in parts), code)
    _require(parts[-1] == 'manifest.json' and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', parts[-2], re.ASCII) is not None, code)
    return anchor + separator.join(parts[:-2]), parts[-2]


@_safe
def validate_export(manifest_path, *, trusted_parent_ack, limits=DEFAULT_LIMITS):
    """Validate final marker and synthetic bytes using public file capabilities."""
    _require(type(trusted_parent_ack) is bool and trusted_parent_ack is True, 'snapshot_arguments_invalid')
    local = _limits(limits)
    parent_path, basename = _manifest_path(manifest_path)
    started = time.monotonic()
    with _closing(files.open_trusted_parent(parent_path, trusted_parent_ack=True)) as parent:
        with _closing(files.open_directory(parent, basename, limits=local.files)) as directory:
            initial_names = directory.file_names()
            _require('manifest.json' in initial_names, 'snapshot_file_set_invalid')
            raw = _read_metadata(directory, 'manifest.json', local.files.max_metadata_bytes,
                staged=False, budget=_Budget(local, started))
            report, effective = _validate_core(raw, directory, local, started, initial_names=initial_names)
    _Budget(effective, started).tick()
    return report


@_safe
def load_export(manifest_path, *, trusted_parent_ack, limits=DEFAULT_LIMITS):
    """B6 E3: validate a published bundle exactly as validate_export and return its decoded rows.

    Returns (report, rows, export_id): rows maps each business table name to its decoded value tuples
    in bundle order (the PG metadata table is checked, not returned); export_id is the validated
    manifest's own local identifier. Rows come from the same single
    validating pass, so every returned value belongs to a chunk whose size, row count and SHA256
    matched the manifest; any failure raises the fixed SnapshotExportError and returns nothing.
    """
    _require(type(trusted_parent_ack) is bool and trusted_parent_ack is True, 'snapshot_arguments_invalid')
    local = _limits(limits)
    parent_path, basename = _manifest_path(manifest_path)
    started = time.monotonic()
    rows_by_table = {}
    with _closing(files.open_trusted_parent(parent_path, trusted_parent_ack=True)) as parent:
        with _closing(files.open_directory(parent, basename, limits=local.files)) as directory:
            initial_names = directory.file_names()
            _require('manifest.json' in initial_names, 'snapshot_file_set_invalid')
            raw = _read_metadata(directory, 'manifest.json', local.files.max_metadata_bytes,
                staged=False, budget=_Budget(local, started))
            report, effective = _validate_core(raw, directory, local, started, initial_names=initial_names,
                                               rows_by_table=rows_by_table)
    _Budget(effective, started).tick()
    manifest, unused_profile, unused_limits = _parse_manifest(raw, local)
    return report, {name: tuple(values) for name, values in rows_by_table.items()}, manifest['export_id']


def _blocks(data, budget):
    for index in range(0, len(data), 65536):
        budget.tick()
        yield data[index:index + 65536]


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


class _Stage:
    """Opaque single-use staging state: owned directory, digests and docs; never a marker."""

    __slots__ = ('local', 'budget', 'started', 'started_at', 'parent', 'owner', 'publish_attempted',
                 'digests', 'table_docs', 'file_docs')

    def __init__(self, local, started, started_at):
        self.local, self.started, self.started_at = local, started, started_at
        self.budget = _Budget(local, started)
        self.parent = self.owner = None
        self.publish_attempted = False
        self.digests, self.table_docs, self.file_docs = [], [], []


class _DictRows:
    """Synthetic row source; the same narrow iter_table protocol as the source row reader."""

    __slots__ = ('rows', 'tables')

    def __init__(self, rows, tables):
        self.rows, self.tables = rows, tables

    def iter_table(self, table_index):
        return self.rows[self.tables[table_index].name]


def _open_target(stage, parent_path, basename):
    stage.parent = files.open_trusted_parent(parent_path, trusted_parent_ack=True)
    stage.owner = files.reserve_directory(stage.parent, basename, limits=stage.local.files)


def _stage_bundle(stage, descriptor, profile, row_source):
    """Write schema.json and every table's chunks into the owned directory."""
    local, budget, owner = stage.local, stage.budget, stage.owner
    digests, table_docs, file_docs = stage.digests, stage.table_docs, stage.file_docs
    tables = tuple(sorted(descriptor.tables + descriptor.metadata_tables, key=lambda table: table.name))
    schema = _canonical(dict(descriptor=schema_document(descriptor),
        fingerprint=schema_fingerprint(descriptor)), local, 'snapshot_schema_invalid')
    budget.data(len(schema))
    _require(local.files.max_files >= len(tables) + 2, 'snapshot_resource_limit')
    digest = owner.write_file('schema.json', _blocks(schema, budget))
    digests.append(digest)
    file_docs.append(dict(name='schema.json', kind='schema', byte_count=digest.byte_count,
        row_count=None, sha256=digest.sha256))
    del schema
    for table_index, table in enumerate(tables):
        tags = _tags(profile, table)
        table_rows, chunk_index, chunk_rows = 0, 0, 0
        chunk, names = bytearray(), []

        def flush():
            nonlocal chunk_index, chunk_rows
            _require(len(file_docs) + 2 <= local.files.max_files and chunk_index <= 999999,
                'snapshot_resource_limit')
            name = _chunk_name(table_index, chunk_index)
            digest = owner.write_file(name, _blocks(bytes(chunk), budget))
            digests.append(digest)
            file_docs.append(dict(name=name, kind='rows', byte_count=digest.byte_count,
                row_count=chunk_rows, sha256=digest.sha256))
            names.append(name)
            chunk.clear()
            chunk_index += 1
            chunk_rows = 0

        for values in row_source.iter_table(table_index):
            budget.tick()
            try:
                record = codec.encode_row(values, allowed_tags=tags, limits=local.codec)
            except codec.SnapshotError as error:
                _fail('snapshot_resource_limit' if error.code in _RESOURCE else 'snapshot_record_invalid')
            _require(len(record) <= min(local.files.max_record_bytes, local.files.max_file_bytes),
                'snapshot_resource_limit')
            if chunk and len(chunk) + len(record) > local.files.max_file_bytes:
                flush()
            budget.row()
            budget.data(len(record))
            chunk.extend(record)
            table_rows += 1
            chunk_rows += 1
        if chunk or not names:
            flush()
        table_docs.append(dict(table_index=table_index, name=table.name,
            columns=[column.name for column in table.columns], rows=table_rows, chunks=names))


def _seal_validate(stage, profile, source_facts):
    """Build the manifest in memory and validate the staged bytes; nothing is published."""
    local = stage.local
    manifest = dict(format=_FORMAT, format_version=1, codec_version=1,
        schema_profile=profile.profile_id, schema_profile_version=1, export_id=uuid.uuid4().hex,
        created_at=_now(), started_at=stage.started_at, ended_at=source_facts['ended_at'],
        source=dict(dialect=profile.descriptor.dialect, namespace=profile.descriptor.namespace,
            version=source_facts['version']), snapshot_method=source_facts['method'],
        schema_fingerprint=schema_fingerprint(profile.descriptor), limits_used=_limits_document(local),
        privacy='restricted-local-plaintext', migration_eligible='not_assessed', tables=stage.table_docs,
        files=stage.file_docs, totals=dict(table_count=len(stage.table_docs), row_count=stage.budget.rows,
            data_bytes=stage.budget.data_bytes, file_count=len(stage.file_docs) + 1))
    raw = _canonical(manifest, local, 'snapshot_manifest_invalid')
    report, unused = _validate_core(raw, stage.owner, local, stage.started, staged=True,
        sealed=tuple(stage.digests))
    return raw, report


def _publish_staged(stage, raw, report, result_type):
    stage.budget.tick()
    # This boundary may commit and then throw. Never abort after attempting it.
    stage.publish_attempted = True
    try:
        publication = stage.owner.publish_marker(raw)
    except Exception:
        _fail('snapshot_publish_outcome_uncertain')
    try:
        closing_owner = stage.owner
        stage.owner = None
        closing_owner.close()
        closing_parent = stage.parent
        stage.parent = None
        closing_parent.close()
        stage.budget.tick()
    except Exception:
        _fail('snapshot_publish_outcome_uncertain')
    return result_type(publication.status, publication.published,
        publication.cleanup_complete, publication.directory_synced, publication.codes,
        report.table_count, report.row_count, report.data_bytes, report.file_count, report.manifest_sha256)


def _release(stage, primary):
    """Call inside `except BaseException as primary`; the caller re-raises primary after it.

    Before publish only the owned staging is aborted; after an attempt nothing is
    aborted. An existing cancellation wins; a new one supersedes an ordinary failure.
    A source restore failure keeps its code over staging cleanup failure.
    """
    cleanup_failed = False
    propagate = primary
    owner, parent = stage.owner, stage.parent
    if owner is not None:
        if not stage.publish_attempted:
            try:
                owner.abort()
            except Exception:
                cleanup_failed = True
            except BaseException as cleanup:
                if isinstance(propagate, Exception):
                    propagate = cleanup
        try:
            owner.close()
        except Exception:
            cleanup_failed = True
        except BaseException as cleanup:
            if isinstance(propagate, Exception):
                propagate = cleanup
    if parent is not None:
        try:
            parent.close()
        except Exception:
            cleanup_failed = True
        except BaseException as cleanup:
            if isinstance(propagate, Exception):
                propagate = cleanup
    if propagate is not primary:
        raise propagate
    if (cleanup_failed and isinstance(primary, Exception)
            and getattr(primary, 'code', None) != 'connection_restore_failed'):
        _fail('snapshot_publish_outcome_uncertain' if stage.publish_attempted else 'snapshot_cleanup_failed')


@_safe
def _build_synthetic_bundle(parent_path, basename, profile_id, rows, *, trusted_parent_ack,
        limits=DEFAULT_LIMITS):
    """Private test-only rows stream. This grants no DB source capability."""
    _require(type(trusted_parent_ack) is bool and trusted_parent_ack is True, 'snapshot_arguments_invalid')
    local = _limits(limits)
    _require(type(profile_id) is str and profile_id in SOURCE_PROFILES, 'snapshot_schema_invalid')
    profile = SOURCE_PROFILES[profile_id]
    tables = _tables(profile)
    _require(len(tables) <= local.max_tables, 'snapshot_resource_limit')
    _require(type(rows) is dict and len(rows) == len(tables) and all(type(k) is str for k in rows) and
        set(rows) == {table.name for table in tables}, 'snapshot_arguments_invalid')
    stage = _Stage(local, time.monotonic(), _now())
    try:
        _open_target(stage, parent_path, basename)
        _stage_bundle(stage, profile.descriptor, profile, _DictRows(rows, tables))
        raw, report = _seal_validate(stage, profile, dict(method=_SYNTHETIC_METHOD,
            version=_SYNTHETIC_VERSION, ended_at=_now()))
        return _publish_staged(stage, raw, report, _SyntheticBuildResult)
    except BaseException as primary:
        _release(stage, primary)
        raise


def _destination(value):
    _require(type(value) is str, 'snapshot_path_invalid')
    return _manifest_path(value + ('\\' if os.name == 'nt' else '/') + 'manifest.json')


@_safe
def export_snapshot(source, destination, *, driver_contract, trusted_parent_ack, limits=DEFAULT_LIMITS):
    """Export one read-only snapshot of `source` to the exact absolute `destination`.

    `source` is the caller's idle Connection; `driver_contract` is the read
    contract issued for exactly that connection by a reviewed bootstrap (only
    synthetic SQLite exists at this stage). Order: arguments -> catalog/head in
    E0 -> full preflight -> stage original rows -> close source cursors and exit
    E0 (rollback/restore) -> manifest -> staged validation -> publish -> close.
    No marker unless the source was restored; after a publish attempt nothing is
    aborted or retried, and ambiguous outcomes are snapshot_publish_outcome_uncertain.
    """
    _require(type(trusted_parent_ack) is bool and trusted_parent_ack is True, 'snapshot_arguments_invalid')
    local = _limits(limits)
    parent_path, basename = _destination(destination)
    from tools import production_db_snapshot_catalog as catalog
    from tools import production_db_snapshot_read_contract as read_contract
    from tools import production_db_snapshot_rows as rows
    source_errors = (catalog.CatalogError, rows.SnapshotRowsError, read_contract.ReadContractError)
    stage = _Stage(local, time.monotonic(), _now())
    read_budget = read_contract.ReadBudget(local.max_wall_seconds)
    row_limits = rows.RowLimits(max_cell_bytes=local.codec.max_cell_bytes,
        max_row_bytes=local.codec.max_row_bytes, max_total_rows=local.max_total_rows)
    try:
        with catalog._catalog_for_export(source, driver_contract, read_budget) as snapshot:
            descriptor, profile = snapshot.descriptor, snapshot.profile
            _require(schema_document(descriptor) == schema_document(profile.descriptor), 'snapshot_schema_invalid')
            _require(len(rows.table_order(descriptor)) <= local.max_tables, 'snapshot_resource_limit')
            method = _METHODS.get((descriptor.dialect, read_contract._domain(driver_contract)))
            _require(method is not None, 'source_codec_unsupported')
            version = read_contract._source_version(driver_contract)
            with rows._open_rows(snapshot, driver_contract, row_limits) as reader:
                reader.preflight()
                # No target write before every table passed preflight.
                _open_target(stage, parent_path, basename)
                _stage_bundle(stage, descriptor, profile, reader)
        # Reached only after source cursors closed and E0 rolled back and restored.
        raw, report = _seal_validate(stage, profile, dict(method=method, version=version, ended_at=_now()))
        return _publish_staged(stage, raw, report, ExportResult)
    except BaseException as primary:
        _release(stage, primary)
        if isinstance(primary, source_errors):
            _fail(primary.code if primary.code in _CODES else 'source_read_failed')
        raise
