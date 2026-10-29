"""Six static expected schemas; synthetic-only, never DB source authentication."""
from dataclasses import fields, replace, FrozenInstanceError
from datetime import date, datetime, timezone
import hashlib
import json
import sys

import pytest

from tools.production_db_snapshot_format import (
    SnapshotError, canonical_json_bytes, encode_row, decode_row,
)
from tools.production_db_snapshot_schema import (
    PhysicalType, ColumnDescriptor, UniqueDescriptor, ForeignKeyDescriptor,
    IndexDescriptor, TriggerDescriptor, TableDescriptor, SchemaDescriptor,
    schema_document, schema_fingerprint,
)
from tools.production_db_snapshot_profiles import (
    KNOWN_PROFILE_IDS, SOURCE_PROFILES, SchemaProfile, require_source_profile,
)

IDS = ('legacy_sqlite9_v1', 'sqlite_models17_v1', 'pg_b1_0001_v1',
       'pg_b1b_0002_v1', 'pg_b1b_0003_v1', 'pg_b3b_0004_v1')
COUNTS = ((9, 63), (17, 203), (9, 63), (13, 105), (15, 165), (17, 203))


class Hostile:
    def __repr__(self):
        raise AssertionError('B6_PROFILE_PRIVATE_CANARY')
    __str__ = __repr__
    __iter__ = __repr__
    __hash__ = __repr__
    def __eq__(self, other):
        raise AssertionError('B6_PROFILE_PRIVATE_CANARY')


def rejected(call, code='source_profile_unsupported'):
    caught = None
    try:
        call()
    except SnapshotError as error:
        caught = error
    assert caught is not None
    assert caught.code == code and str(caught) == code
    assert caught.__cause__ is None and caught.__context__ is None
    return caught


def table(d, name):
    return next(t for t in d.tables if t.name == name)


def changed_table(d, t):
    return replace(d, tables=tuple(t if x.name == t.name else x for x in d.tables))


def must_reject(make):
    def action():
        descriptor = make()
        require_source_profile(descriptor)
    rejected(action)


@pytest.mark.parametrize('profile_id,count', tuple(zip(IDS, COUNTS)))
def test_six_complete_expected_schemas(profile_id, count):
    p = SOURCE_PROFILES[profile_id]
    d = p.descriptor
    assert type(p) is SchemaProfile and type(d) is SchemaDescriptor
    assert (len(d.tables), sum(len(t.columns) for t in d.tables)) == count
    assert tuple(t.name for t in d.tables) == tuple(sorted(t.name for t in d.tables))
    assert require_source_profile(d) is p
    assert require_source_profile(descriptor=d) is p
    assert len(p.allowed_tags) == len(d.tables)
    assert all(len(tags) == len(t.columns) for tags, t in zip(p.allowed_tags, d.tables))
    assert KNOWN_PROFILE_IDS == frozenset(IDS)
    assert all(c.default_id == c.generated_id == c.identity_id == 'absent'
               for t in d.tables + d.metadata_tables for c in t.columns)
    if d.dialect == 'sqlite':
        assert d.namespace == 'main' and d.heads == () and d.metadata_tables == ()
        assert d.function_ids == () and all(t.triggers == () for t in d.tables)
    else:
        assert d.namespace == 'app' and len(d.heads) == 1
        assert d.metadata_tables[0].name == 'alembic_version'
        c = d.metadata_tables[0].columns[0]
        assert c.name == 'version_num' and c.physical_type == PhysicalType('pg_varchar', (32,))
        assert not c.nullable and d.metadata_tables[0].primary_key == ('version_num',)
    assert d.internal_ids == ()


def test_expected_registry_and_every_nested_object_are_immutable_and_repr_safe():
    p = SOURCE_PROFILES[IDS[-1]]
    with pytest.raises(TypeError):
        SOURCE_PROFILES['new'] = p
    items = [p, p.descriptor, p.descriptor.tables[0], p.descriptor.tables[0].columns[0],
             p.descriptor.tables[0].columns[0].physical_type]
    for t in p.descriptor.tables:
        items.extend(t.uniques + t.foreign_keys + t.indexes + t.triggers)
    for item in items:
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            setattr(item, fields(item)[0].name, Hostile())
        assert not hasattr(item, '__dict__')
        assert 'B6_PROFILE_PRIVATE_CANARY' not in repr(item)
    # Even a bypassed invalid field is never interpolated by repr().
    col = replace(p.descriptor.tables[0].columns[0])
    object.__setattr__(col, 'name', Hostile())
    assert 'B6_PROFILE_PRIVATE_CANARY' not in repr(col)
    must_reject(lambda: changed_table(p.descriptor, replace(p.descriptor.tables[0],
        columns=(col,) + p.descriptor.tables[0].columns[1:])))


@pytest.mark.parametrize('value', [None, True, 1, 'legacy_sqlite9_v1', {}, [], Hostile()])
def test_wrong_argument_types_never_authorize(value):
    for call in (lambda: require_source_profile(value), lambda: require_source_profile(descriptor=value),
                 lambda: schema_document(value), lambda: schema_fingerprint(value)):
        try:
            raise RuntimeError('B6_PROFILE_PRIVATE_CANARY')
        except RuntimeError:
            rejected(call)


def test_all_binding_misuse_is_safely_rejected_even_in_active_exception(capsys):
    d = SOURCE_PROFILES[IDS[0]].descriptor
    for call in (lambda: require_source_profile(), lambda: require_source_profile(d, d),
            lambda: require_source_profile(d, descriptor=d), lambda: require_source_profile(profile_id=IDS[0]),
            lambda: require_source_profile(descriptor=d, private=Hostile()),
            lambda: schema_document(), lambda: schema_fingerprint(d, d),
            lambda: PhysicalType(), lambda: PhysicalType('pg_text', (), private=Hostile()),
            lambda: ColumnDescriptor(private=Hostile())):
        try:
            raise RuntimeError('B6_PROFILE_PRIVATE_CANARY')
        except RuntimeError:
            rejected(call)
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('profile_id', IDS)
def test_nested_exact_types_bounds_and_unknown_fields(profile_id):
    d = SOURCE_PROFILES[profile_id].descriptor
    c = d.tables[0].columns[0]
    class Str(str):
        pass
    class Int(int):
        pass
    class Tuple(tuple):
        pass
    class DescriptorSubclass(SchemaDescriptor):
        pass
    for make in (lambda: replace(c, name=Str(c.name)), lambda: replace(c, nullable=1),
            lambda: replace(c, nullable=Hostile()), lambda: replace(c, physical_type=Hostile()),
            lambda: PhysicalType('pg_varchar', (True,)), lambda: PhysicalType('pg_varchar', (Int(32),)),
            lambda: PhysicalType('pg_varchar', (0,)), lambda: PhysicalType('pg_varchar', (2**100,)),
            lambda: PhysicalType('pg_text', (1,)), lambda: PhysicalType(Str('pg_text'), ()),
            lambda: PhysicalType('pg_numeric', ()), lambda: PhysicalType('pg_domain', ()),
            lambda: PhysicalType('sqlite_datetime', (6,)), lambda: replace(d, descriptor_version=True),
            lambda: replace(d, descriptor_version=Int(1)), lambda: replace(d, tables=Tuple(d.tables)),
            lambda: replace(d, tables=(Hostile(),) * 19),
            lambda: replace(d.tables[0], columns=(Hostile(),) * 97),
            lambda: replace(c, name='x' * 129), lambda: replace(c, name='B6_PROFILE_PRIVATE_CANARY'),
            lambda: DescriptorSubclass(**{f.name: getattr(d, f.name) for f in fields(d)})):
        rejected(make)


@pytest.mark.parametrize('left', IDS)
@pytest.mark.parametrize('right', IDS)
def test_cross_profile_heads_never_authorize_other_structure(left, right):
    a, b = SOURCE_PROFILES[left].descriptor, SOURCE_PROFILES[right].descriptor
    if a.heads != b.heads:
        must_reject(lambda: replace(a, heads=b.heads))
    if left != right and a.dialect == b.dialect:
        # Replacing only one table creates an unsupported mixed generation.
        candidates = [x for x in a.tables if any(y.name == x.name and y != x for y in b.tables)]
        if candidates:
            x = candidates[0]
            replacement = table(b, x.name)
            def check():
                mixed = replace(a, tables=tuple(replacement if t.name == x.name else t for t in a.tables))
                # Any exact other complete schema is still supported; an incomplete
                # hybrid, including a dangling FK, must fail at construction/match.
                if mixed not in tuple(p.descriptor for p in SOURCE_PROFILES.values()):
                    require_source_profile(mixed)
                else:
                    raise AssertionError('cross_case_is_an_entire_supported_schema')
            rejected(check)


@pytest.mark.parametrize('profile_id', IDS)
def test_whole_schema_missing_extra_objects_and_metadata_are_rejected(profile_id):
    d = SOURCE_PROFILES[profile_id].descriptor
    for make in (lambda: replace(d, tables=d.tables[:-1]),
            lambda: replace(d, tables=d.tables + (d.tables[0],)),
            lambda: replace(d, tables=d.tables + (replace(d.tables[0], name='unrecognized'),)),
            lambda: replace(d, heads=('unknown',)), lambda: replace(d, heads=('a', 'b')),
            lambda: replace(d, internal_ids=('sqlite_stat1',)), lambda: replace(d, function_ids=('unknown.v1',)),
            lambda: replace(d, descriptor_version=2), lambda: replace(d, namespace='other'),
            lambda: replace(d, metadata_tables=() if d.metadata_tables else (d.tables[0],))):
        must_reject(make)


@pytest.mark.parametrize('profile_id', IDS)
def test_every_column_dimension_is_exact(profile_id):
    d = SOURCE_PROFILES[profile_id].descriptor
    for t in d.tables:
        for i, c in enumerate(t.columns):
            for change in ({'nullable': not c.nullable}, {'name': 'unknown_column'},
                    {'default_id': 'unknown_default'}, {'generated_id': 'stored'},
                    {'identity_id': 'always'}, {'collation_id': 'custom'},
                    {'physical_type': PhysicalType('pg_text' if d.dialect == 'pg' else 'sqlite_text', ())}):
                if change.get('physical_type') == c.physical_type:
                    continue
                must_reject(lambda t=t, i=i, c=c, change=change: changed_table(d,
                    replace(t, columns=t.columns[:i] + (replace(c, **change),) + t.columns[i+1:])))
        must_reject(lambda t=t: changed_table(d, replace(t, columns=t.columns[:-1])))
        must_reject(lambda t=t: changed_table(d, replace(t,
            columns=t.columns + (replace(t.columns[0], name='extra_column'),))))
        if len(t.columns) > 1:
            must_reject(lambda t=t: changed_table(d, replace(t, columns=tuple(reversed(t.columns)))))
        for change in ({'primary_key': ()}, {'primary_key': ('unknown',)},
                {'table_policy_id': 'partitioned'}, {'pk_policy_id': 'deferrable'},
                {'check_ids': t.check_ids + ('unknown.check.v1',)}):
            must_reject(lambda t=t, change=change: changed_table(d, replace(t, **change)))


@pytest.mark.parametrize('profile_id', IDS)
def test_every_constraint_index_check_trigger_and_function_is_exact(profile_id):
    d = SOURCE_PROFILES[profile_id].descriptor
    for t in d.tables:
        for attribute in ('uniques', 'foreign_keys', 'indexes', 'check_ids', 'triggers'):
            values = getattr(t, attribute)
            if values:
                must_reject(lambda t=t, attribute=attribute, values=values:
                    changed_table(d, replace(t, **{attribute: values[1:]})))
                must_reject(lambda t=t, attribute=attribute, values=values:
                    changed_table(d, replace(t, **{attribute: values + values[:1]})))
        for attribute in ('uniques', 'foreign_keys', 'indexes', 'triggers'):
            for i, item in enumerate(getattr(t, attribute)):
                for f in fields(item):
                    value = getattr(item, f.name)
                    altered = (not value if type(value) is bool else
                        tuple(reversed(value)) if type(value) is tuple and len(value) > 1 else
                        ('unknown',) if type(value) is tuple else 'unknown')
                    if f.name in ('on_update', 'on_delete'):
                        altered = 'RESTRICT' if value == 'NO_ACTION' else 'NO_ACTION'
                    elif f.name == 'predicate_id':
                        altered = 'get_ordinal_is_null_v1' if value == 'absent' else 'absent'
                    if altered == value:
                        continue
                    def make(t=t, attribute=attribute, i=i, item=item, f=f, altered=altered):
                        values = getattr(t, attribute)
                        return changed_table(d, replace(t, **{attribute:
                            values[:i] + (replace(item, **{f.name: altered}),) + values[i+1:]}))
                    must_reject(make)
        if len(t.primary_key) > 1:
            must_reject(lambda t=t: changed_table(d, replace(t, primary_key=tuple(reversed(t.primary_key)))))
    if d.function_ids:
        must_reject(lambda: replace(d, function_ids=d.function_ids[1:]))


def test_sqlite_pg_reconciliation_policies_and_legacy_physical_differences():
    old, sq, pg = (SOURCE_PROFILES[x] for x in (IDS[0], IDS[1], IDS[-1]))
    oldjob, sqjob = table(old.descriptor, 'job'), table(sq.descriptor, 'job')
    assert oldjob.columns[7].physical_type.kind == 'sqlite_integer'
    assert sqjob.columns[7].physical_type.kind == 'sqlite_bigint'
    assert oldjob.check_ids == () and sqjob.check_ids == ('job.status.v1',)
    for name, missing in (('billingreconciliationtask', {'input_sha256', 'audit_context', 'query_json', 'policy_json'}),
                          ('billingreconciliationaudit', {'projection_sha256', 'audit_context', 'projection_json'})):
        s, p = table(sq.descriptor, name), table(pg.descriptor, name)
        assert set(p.check_ids) - set(s.check_ids) == {name + '.' + x + '.v1' for x in missing}
        assert s.triggers == () and p.triggers
    assert sum(len(t.triggers) for t in pg.descriptor.tables) == 5
    assert pg.descriptor.function_ids == ('b3b_reject_mutation.v1', 'b3b_task_update_guard.v1')
    assert 'acl_not_assessed_v1' in pg.policy_ids
    assert 'legacy_naive_utc_requires_import_policy_v1' in sq.policy_ids


@pytest.mark.parametrize('profile_id', IDS[:2])
def test_sqlite_all_storage_classes_roundtrip_without_affinity_or_temporal_repair(profile_id):
    p = SOURCE_PROFILES[profile_id]
    for t, tags in zip(p.descriptor.tables, p.allowed_tags):
        for c, allowed in zip(t.columns, tags):
            assert allowed == frozenset({'s', 'i', 'f', 'x'} | ({'n'} if c.nullable else set()))
            for value in ('2026-01-02 03:04:05.0000', ' { "z":1 } ', 'broken-date', 0, 1, 2, -3, 1.25, b'\0\xff'):
                result = decode_row(encode_row((value,), allowed_tags=(allowed,)), allowed_tags=(allowed,))[0]
                assert type(result) is type(value) and result == value
            for value in (True, date(2026, 1, 1), datetime(2026, 1, 1)):
                rejected(lambda: encode_row((value,), allowed_tags=(allowed,)), 'codec_tag_invalid')
            if c.nullable:
                assert decode_row(encode_row((None,), allowed_tags=(allowed,))) == (None,)
            else:
                rejected(lambda: encode_row((None,), allowed_tags=(allowed,)), 'codec_tag_invalid')


@pytest.mark.parametrize('profile_id', IDS[2:])
def test_pg_native_type_mapping_matrix_uses_codec_exact_types(profile_id):
    p = SOURCE_PROFILES[profile_id]
    examples = {'s': '2026-01-01', 'i': 2, 'f': 1.25, 'b': True,
        'date': date(2026, 1, 1), 'dt': datetime(2026, 1, 1, tzinfo=timezone.utc)}
    kinds = {'pg_varchar': 's', 'pg_text': 's', 'pg_int4': 'i', 'pg_int8': 'i',
        'pg_float8': 'f', 'pg_bool': 'b', 'pg_date': 'date', 'pg_timestamptz': 'dt'}
    for t, tags in zip(p.descriptor.tables, p.allowed_tags):
        for c, allowed in zip(t.columns, tags):
            tag = kinds[c.physical_type.kind]
            assert allowed == frozenset({tag} | ({'n'} if c.nullable else set()))
            value = examples[tag]
            result = decode_row(encode_row((value,), allowed_tags=(allowed,)), allowed_tags=(allowed,))[0]
            assert type(result) is type(value) and result == value
            for other, bad in examples.items():
                if other != tag:
                    rejected(lambda: encode_row((bad,), allowed_tags=(allowed,)), 'codec_tag_invalid')
            if tag == 'dt':
                rejected(lambda: encode_row((datetime(2026, 1, 1),), allowed_tags=(allowed,)), 'codec_tag_invalid')


@pytest.mark.parametrize('profile_id', IDS)
def test_canonical_document_is_detached_sorted_and_set_reordering_stable(profile_id):
    d = SOURCE_PROFILES[profile_id].descriptor
    reordered = replace(d, tables=tuple(replace(t,
        uniques=tuple(reversed(t.uniques)), foreign_keys=tuple(reversed(t.foreign_keys)),
        indexes=tuple(reversed(t.indexes)), check_ids=tuple(reversed(t.check_ids)),
        triggers=tuple(reversed(t.triggers))) for t in reversed(d.tables)),
        function_ids=tuple(reversed(d.function_ids)))
    assert require_source_profile(reordered) is SOURCE_PROFILES[profile_id]
    body = schema_document(d)
    assert body == schema_document(reordered)
    wire = canonical_json_bytes(body, max_bytes=2 << 20)
    assert wire == json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    assert hashlib.sha256(wire).hexdigest() == schema_fingerprint(d) == schema_fingerprint(reordered)
    body['tables'].clear()
    assert schema_document(d)['tables']


def test_no_application_database_modules_were_imported_and_no_source_capability_exists():
    assert not any(x.split('.')[0] in {'app', 'sqlalchemy', 'sqlmodel', 'alembic', 'sqlite3',
                                     'psycopg', 'psycopg2', 'dotenv'} for x in sys.modules)
    p = SOURCE_PROFILES[IDS[-1]]
    assert {f.name for f in fields(p)} == {'profile_id', 'descriptor', 'allowed_tags', 'policy_ids'}
    assert not hasattr(p, 'export') and not hasattr(p, 'source')


def test_unknown_metaclass_and_policy_members_never_receive_equality_calls():
    calls = []
    class Meta(type):
        def __eq__(self, other):
            calls.append('class_equal')
            return False
    class Sub(PhysicalType, metaclass=Meta):
        pass
    rejected(lambda: Sub('pg_text', ()))
    class EqualityTrap:
        def __eq__(self, other):
            calls.append('policy_equal')
            return False
    p = SOURCE_PROFILES[IDS[0]]
    rejected(lambda: SchemaProfile(p.profile_id, p.descriptor, p.allowed_tags,
        (EqualityTrap(),) + p.policy_ids[1:]))
    assert calls == []


@pytest.mark.parametrize('profile_id', IDS)
def test_every_varchar_length_and_metadata_dimension_is_exact(profile_id):
    d = SOURCE_PROFILES[profile_id].descriptor
    for t in d.tables + d.metadata_tables:
        for i, c in enumerate(t.columns):
            if c.physical_type.kind.endswith('_varchar'):
                args = (c.physical_type.args[0] + 1,) if c.physical_type.args else (32,)
                def make(t=t, i=i, c=c, args=args):
                    changed = replace(t, columns=t.columns[:i] + (replace(c,
                        physical_type=replace(c.physical_type, args=args)),) + t.columns[i+1:])
                    if t in d.metadata_tables:
                        return replace(d, metadata_tables=(changed,))
                    return changed_table(d, changed)
                must_reject(make)
    if d.metadata_tables:
        metadata = d.metadata_tables[0]
        for make in (lambda: replace(d, metadata_tables=(replace(metadata,
                    columns=(replace(metadata.columns[0], nullable=True),)),)),
                lambda: replace(d, metadata_tables=(replace(metadata, indexes=(
                    IndexDescriptor(('version_num',), False, 'btree', ('asc',),
                        ('dialect_default',), 'absent', (), True),)),))):
            must_reject(make)


def test_duplicate_matching_declarations_fail_closed_and_baseexceptions_propagate(monkeypatch):
    import tools.production_db_snapshot_profiles as module
    d = SOURCE_PROFILES[IDS[0]].descriptor
    original = module._DECLARATIONS
    monkeypatch.setattr(module, '_DECLARATIONS', original + original[:1])
    rejected(lambda: require_source_profile(d))
    monkeypatch.setattr(module, '_DECLARATIONS', original)
    def interrupt(value):
        raise KeyboardInterrupt()
    monkeypatch.setattr(module, '_schema_bytes', interrupt)
    with pytest.raises(KeyboardInterrupt):
        require_source_profile(d)


def test_preflight_rejects_oversized_containers_before_touching_members():
    class TrapTuple(tuple):
        def __iter__(self):
            raise AssertionError('B6_PROFILE_PRIVATE_CANARY')
    class TrapStr(str):
        def __hash__(self):
            raise AssertionError('B6_PROFILE_PRIVATE_CANARY')
    rejected(lambda: PhysicalType('pg_varchar', (Hostile(),) * 2))
    rejected(lambda: UniqueDescriptor((Hostile(),) * 97, True, False, False, True))
    rejected(lambda: UniqueDescriptor(TrapTuple(('id',)), True, False, False, True))
    rejected(lambda: UniqueDescriptor((TrapStr('id'),), True, False, False, True))
    rejected(lambda: IndexDescriptor(('id',), False, 'btree', (Hostile(),) * 97,
        ('dialect_default',), 'absent', (), True))


GOLDENS = {
    'legacy_sqlite9_v1': (17346, 'e2708dd76e0c6ee93625739aad8afaf7198bb581314848a9183d69b866646bb6'),
    'sqlite_models17_v1': (54099, '6f7310a7b3bf4c54a9aaf0eb50b3814654230a4ce7fc814ea60ada57eb9ee899'),
    'pg_b1_0001_v1': (17468, 'e0b5434539a42173948f7052ace42e50ab33dbe562cbf5142054323a0c883c04'),
    'pg_b1b_0002_v1': (29592, '2668efe7c4fbd5f952c1ad7072fb1ca84bf073b0e9152bc9f102c13e9dd2148c'),
    'pg_b1b_0003_v1': (43766, '62e8d032508ac00f7444d6c93a5907472d8eccff484ab2d934179264748924ff'),
    'pg_b3b_0004_v1': (54778, '9e21e9a1d8e90db4dcb85d7af795558638bbba4d40c16dcb91beb9039b678b19'),
}


@pytest.mark.parametrize('profile_id', IDS)
def test_static_canonical_bytes_and_sha256_are_frozen(profile_id):
    d = SOURCE_PROFILES[profile_id].descriptor
    expected_length, expected_sha = GOLDENS[profile_id]
    wire = canonical_json_bytes(schema_document(d), max_bytes=2 << 20)
    assert len(wire) == expected_length
    assert hashlib.sha256(wire).hexdigest() == schema_fingerprint(d) == expected_sha
