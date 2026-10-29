"""Bounded immutable schema declarations; no catalog, DB, config or source I/O.

Only a complete registered expected descriptor can be published as a document.
Agreement with that declaration authenticates neither a source nor its collector.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from functools import wraps
import hashlib
import re

from tools.production_db_snapshot_format import canonical_json_bytes, _raise_safe


_MAX_BYTES = 2 << 20
_NAME = re.compile(r'[a-z_][a-z0-9_]{0,127}\Z')
_ID = re.compile(r'[a-z_][a-z0-9_.]{0,127}\Z')
_KINDS = frozenset('sqlite_varchar sqlite_text sqlite_integer sqlite_bigint sqlite_float '
    'sqlite_boolean sqlite_date sqlite_datetime pg_varchar pg_text pg_int4 pg_int8 '
    'pg_float8 pg_bool pg_date pg_timestamptz'.split())


def _boundary(function):
    @wraps(function)
    def safe(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            pass
        # Deliberately outside except: strip the caller's active context too.
        _raise_safe('source_profile_unsupported')
    return safe


def _require(condition):
    if not condition:
        _raise_safe('source_profile_unsupported')


class _Descriptor:
    __slots__ = ()

    @_boundary
    def __init__(self, *args, **kwargs):
        cls = type(self)
        _require(any(cls is accepted for accepted in _TYPES))
        names = tuple(f.name for f in fields(cls))
        _require(len(args) <= len(names) and len(args) + len(kwargs) == len(names))
        _require(all(type(k) is str and k in names[len(args):] for k in kwargs))
        for index, name in enumerate(names):
            object.__setattr__(self, name, args[index] if index < len(args) else kwargs[name])
        _validate(self)


@dataclass(frozen=True, slots=True, init=False, repr=False)
class PhysicalType(_Descriptor):
    kind: str
    args: tuple[int, ...]


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ColumnDescriptor(_Descriptor):
    name: str
    physical_type: PhysicalType
    nullable: bool
    default_id: str
    generated_id: str
    identity_id: str
    collation_id: str


@dataclass(frozen=True, slots=True, init=False, repr=False)
class UniqueDescriptor(_Descriptor):
    columns: tuple[str, ...]
    nulls_distinct: bool
    deferrable: bool
    initially_deferred: bool
    validated: bool


@dataclass(frozen=True, slots=True, init=False, repr=False)
class ForeignKeyDescriptor(_Descriptor):
    columns: tuple[str, ...]
    target_schema: str
    target_table: str
    target_columns: tuple[str, ...]
    on_update: str
    on_delete: str
    match: str
    deferrable: bool
    initially_deferred: bool
    validated: bool


@dataclass(frozen=True, slots=True, init=False, repr=False)
class IndexDescriptor(_Descriptor):
    columns: tuple[str, ...]
    unique: bool
    method_id: str
    order_ids: tuple[str, ...]
    collation_ids: tuple[str, ...]
    predicate_id: str
    include_columns: tuple[str, ...]
    nulls_distinct: bool


@dataclass(frozen=True, slots=True, init=False, repr=False)
class TriggerDescriptor(_Descriptor):
    rule_id: str
    function_id: str
    timing: str
    events: tuple[str, ...]
    level: str
    enabled_id: str


@dataclass(frozen=True, slots=True, init=False, repr=False)
class TableDescriptor(_Descriptor):
    name: str
    columns: tuple[ColumnDescriptor, ...]
    primary_key: tuple[str, ...]
    uniques: tuple[UniqueDescriptor, ...]
    foreign_keys: tuple[ForeignKeyDescriptor, ...]
    indexes: tuple[IndexDescriptor, ...]
    check_ids: tuple[str, ...]
    triggers: tuple[TriggerDescriptor, ...]
    table_policy_id: str
    pk_policy_id: str


@dataclass(frozen=True, slots=True, init=False, repr=False)
class SchemaDescriptor(_Descriptor):
    descriptor_version: int
    dialect: str
    namespace: str
    heads: tuple[str, ...]
    tables: tuple[TableDescriptor, ...]
    metadata_tables: tuple[TableDescriptor, ...]
    function_ids: tuple[str, ...]
    internal_ids: tuple[str, ...]


_TYPES = (PhysicalType, ColumnDescriptor, UniqueDescriptor, ForeignKeyDescriptor,
          IndexDescriptor, TriggerDescriptor, TableDescriptor, SchemaDescriptor)
_TRIGGERS = {
    'trg_b3b_audit_row.v1': ('b3b_reject_mutation.v1', ('UPDATE', 'DELETE'), 'ROW'),
    'trg_b3b_audit_truncate.v1': ('b3b_reject_mutation.v1', ('TRUNCATE',), 'STATEMENT'),
    'trg_b3b_task_delete.v1': ('b3b_reject_mutation.v1', ('DELETE',), 'ROW'),
    'trg_b3b_task_truncate.v1': ('b3b_reject_mutation.v1', ('TRUNCATE',), 'STATEMENT'),
    'trg_b3b_task_update.v1': ('b3b_task_update_guard.v1', ('UPDATE',), 'ROW'),
}


def _text(value, pattern=_ID):
    _require(type(value) is str and len(value) <= 128 and pattern.fullmatch(value) is not None)


def _tuple(value, maximum=96, minimum=0):
    _require(type(value) is tuple and minimum <= len(value) <= maximum)


def _names(value, minimum=1):
    _tuple(value, minimum=minimum)
    for name in value:
        _text(name, _NAME)
    _require(len(set(value)) == len(value))


def _ids(value, maximum=96):
    _tuple(value, maximum)
    for name in value:
        _text(name)
    _require(len(set(value)) == len(value))


def _objects(value, cls, maximum=96, minimum=0):
    _tuple(value, maximum, minimum)
    # Check ALL exact types before recursing, hashing, sorting or equality.
    _require(all(type(item) is cls for item in value))
    for item in value:
        _validate(item)
    _require(len(set(value)) == len(value))


def _bools(item, names):
    _require(all(type(getattr(item, name)) is bool for name in names))


def _validate(item):
    cls = type(item)
    _require(any(cls is accepted for accepted in _TYPES))
    if cls is PhysicalType:
        _text(item.kind)
        _require(item.kind in _KINDS)
        _tuple(item.args, 1)
        _require(all(type(x) is int and 1 <= x <= 10_485_760 for x in item.args))
        _require(item.kind.endswith('_varchar') or not item.args)
    elif cls is ColumnDescriptor:
        _text(item.name, _NAME)
        _require(type(item.physical_type) is PhysicalType)
        _validate(item.physical_type)
        _bools(item, ('nullable',))
        for name in ('default_id', 'generated_id', 'identity_id'):
            value = getattr(item, name)
            _require(type(value) is str and value == 'absent')
        _require(type(item.collation_id) is str and item.collation_id == 'dialect_default')
    elif cls is UniqueDescriptor:
        _names(item.columns)
        _bools(item, ('nulls_distinct', 'deferrable', 'initially_deferred', 'validated'))
        _require(item.nulls_distinct and not item.deferrable and not item.initially_deferred and item.validated)
    elif cls is ForeignKeyDescriptor:
        _names(item.columns)
        _names(item.target_columns)
        _require(len(item.columns) == len(item.target_columns))
        _text(item.target_schema, _NAME)
        _text(item.target_table, _NAME)
        _require(item.target_schema in ('main', 'app'))
        for name in ('on_update', 'on_delete'):
            value = getattr(item, name)
            _require(type(value) is str and value in ('NO_ACTION', 'RESTRICT'))
        _require(type(item.match) is str and item.match == 'SIMPLE')
        _bools(item, ('deferrable', 'initially_deferred', 'validated'))
        _require(not item.deferrable and not item.initially_deferred and item.validated)
    elif cls is IndexDescriptor:
        _names(item.columns)
        _bools(item, ('unique', 'nulls_distinct'))
        _require(item.nulls_distinct)
        for name, expected in (('method_id', 'btree'),):
            value = getattr(item, name)
            _require(type(value) is str and value == expected)
        for name, expected in (('order_ids', 'asc'), ('collation_ids', 'dialect_default')):
            value = getattr(item, name)
            _tuple(value)
            _require(len(value) == len(item.columns))
            _require(all(type(v) is str and v == expected for v in value))
        _require(type(item.predicate_id) is str and item.predicate_id in ('absent', 'get_ordinal_is_null_v1'))
        _tuple(item.include_columns, 0)
    elif cls is TriggerDescriptor:
        _text(item.rule_id)
        _text(item.function_id)
        _require(type(item.timing) is str and item.timing == 'BEFORE')
        _tuple(item.events, 2, 1)
        _require(all(type(v) is str and v in ('UPDATE', 'DELETE', 'TRUNCATE') for v in item.events))
        _require(type(item.level) is str and item.level in ('ROW', 'STATEMENT'))
        _require(type(item.enabled_id) is str and item.enabled_id == 'origin_enabled_v1')
        _require(item.rule_id in _TRIGGERS and
            (item.function_id, item.events, item.level) == _TRIGGERS[item.rule_id])
    elif cls is TableDescriptor:
        _text(item.name, _NAME)
        _objects(item.columns, ColumnDescriptor, minimum=1)
        names = tuple(c.name for c in item.columns)
        _require(len(set(names)) == len(names))
        _names(item.primary_key)
        _objects(item.uniques, UniqueDescriptor)
        _objects(item.foreign_keys, ForeignKeyDescriptor)
        _objects(item.indexes, IndexDescriptor)
        _ids(item.check_ids)
        _objects(item.triggers, TriggerDescriptor)
        _require(len({t.rule_id for t in item.triggers}) == len(item.triggers))
        for columns in (item.primary_key,) + tuple(x.columns for x in item.uniques + item.foreign_keys + item.indexes):
            _require(all(c in names for c in columns))
        for name, allowed in (('table_policy_id', ('sqlite_ordinary_rowid_v1', 'pg_ordinary_heap_v1')),
                              ('pk_policy_id', ('nondeferrable_validated_v1',))):
            value = getattr(item, name)
            _require(type(value) is str and value in allowed)
    else:
        _require(type(item.descriptor_version) is int and item.descriptor_version == 1)
        _require(type(item.dialect) is str and item.dialect in ('sqlite', 'pg'))
        expected_namespace = 'main' if item.dialect == 'sqlite' else 'app'
        _require(type(item.namespace) is str and item.namespace == expected_namespace)
        _ids(item.heads, 1)
        _tuple(item.tables, 18, 1)
        _tuple(item.metadata_tables, 18)
        _require(len(item.tables) + len(item.metadata_tables) <= 18)
        _objects(item.tables, TableDescriptor, 18, 1)
        _objects(item.metadata_tables, TableDescriptor, 18)
        _ids(item.function_ids)
        _ids(item.internal_ids)
        tables = item.tables + item.metadata_tables
        names = tuple(t.name for t in tables)
        _require(len(set(names)) == len(names))
        lookup = {t.name: t for t in tables}
        for t in tables:
            expected_policy = 'sqlite_ordinary_rowid_v1' if item.dialect == 'sqlite' else 'pg_ordinary_heap_v1'
            _require(t.table_policy_id == expected_policy)
            _require(all(c.physical_type.kind.startswith(item.dialect + '_') for c in t.columns))
            for fk in t.foreign_keys:
                _require(fk.target_schema == item.namespace and fk.target_table in lookup)
                target = lookup[fk.target_table]
                _require(all(c in tuple(x.name for x in target.columns) for c in fk.target_columns))
                _require(fk.target_columns in (target.primary_key,) + tuple(u.columns for u in target.uniques))
        # Preflight before allocating the detached document. Each scalar/key/list
        # contributes a conservative upper bound; canonical encoding checks again.
        _size(item, [0])


def _size(value, budget):
    cls = type(value)
    if any(cls is accepted for accepted in _TYPES):
        budget[0] += 2
        for f in fields(value):
            budget[0] += len(f.name) + 4
            _size(getattr(value, f.name), budget)
    elif cls is tuple:
        budget[0] += len(value) + 2
        for child in value:
            _size(child, budget)
    elif cls is str:
        budget[0] += len(value) * 6 + 2
    else:
        budget[0] += 12
    _require(budget[0] <= _MAX_BYTES)


def _document(value):
    cls = type(value)
    if any(cls is accepted for accepted in _TYPES):
        document = {f.name: _document(getattr(value, f.name)) for f in fields(value)}
        if cls is TableDescriptor:
            for key in ('uniques', 'foreign_keys', 'indexes'):
                document[key].sort(key=lambda x: canonical_json_bytes(x, max_bytes=_MAX_BYTES))
            document['check_ids'].sort()
            document['triggers'].sort(key=lambda x: x['rule_id'])
        elif cls is SchemaDescriptor:
            document['tables'].sort(key=lambda x: x['name'])
            document['metadata_tables'].sort(key=lambda x: x['name'])
            document['function_ids'].sort()
            document['internal_ids'].sort()
        return document
    if cls is tuple:
        return [_document(child) for child in value]
    return value


def _schema_bytes(descriptor):
    _require(type(descriptor) is SchemaDescriptor)
    _validate(descriptor)
    return canonical_json_bytes(_document(descriptor), max_bytes=_MAX_BYTES)


def _argument(args, kwargs):
    if len(args) == 1 and not kwargs:
        descriptor = args[0]
    elif (not args and len(kwargs) == 1 and type(next(iter(kwargs))) is str
            and next(iter(kwargs)) == 'descriptor'):
        descriptor = kwargs['descriptor']
    else:
        _raise_safe('source_profile_unsupported')
    _require(type(descriptor) is SchemaDescriptor)
    return descriptor


@_boundary
def schema_document(*args, **kwargs) -> dict:
    """Return a detached canonical expected structure, never source attestation."""
    from tools.production_db_snapshot_profiles import require_source_profile
    descriptor = _argument(args, kwargs)
    profile = require_source_profile(descriptor)
    return _document(profile.descriptor)


@_boundary
def schema_fingerprint(*args, **kwargs) -> str:
    """SHA256 of canonical JSON body with LF; only full expected schemas match."""
    document = schema_document(*args, **kwargs)
    return hashlib.sha256(canonical_json_bytes(document, max_bytes=_MAX_BYTES)).hexdigest()
