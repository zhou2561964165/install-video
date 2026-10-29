"""Synthetic only bundle contract; never opens a source database."""
from dataclasses import fields, replace
from datetime import date, datetime, timezone
import hashlib
import os
import sys
import uuid
from pathlib import Path

import pytest

from tools import production_db_export as export
from tools import production_db_snapshot_files as files
from tools import production_db_snapshot_format as codec
from tools.production_db_snapshot_profiles import SOURCE_PROFILES
from tools.production_db_snapshot_schema import schema_document, schema_fingerprint


CANARY = 'B6_BUNDLE_SYNTHETIC_PRIVATE'


class Hostile:
    def __repr__(self):
        raise AssertionError('hostile_callback')
    __str__ = __repr__
    def __eq__(self, other):
        raise AssertionError('hostile_callback')
    def __fspath__(self):
        raise AssertionError('hostile_callback')


def test_export_malformed_binding_has_no_callbacks():
    # E2: export_snapshot is contract-gated; malformed calls fail at binding
    # without touching hostile arguments or importing DB helpers.
    for args, kwargs in [((), {}), ((Hostile(), Hostile()), {}),
            ((Hostile(),), {'source': Hostile(), 'unknown': Hostile()})]:
        with pytest.raises(export.SnapshotExportError) as caught:
            export.export_snapshot(*args, **kwargs)
        assert caught.value.code == 'snapshot_arguments_invalid'
        assert caught.value.__cause__ is caught.value.__context__ is None


@pytest.mark.parametrize('change', [dict(max_tables=True), dict(max_tables=19),
    dict(max_total_rows=0), dict(max_wall_seconds=301), dict(codec=Hostile()),
    dict(files=Hostile()), dict(unknown=1)])
def test_limits_exact_and_tightening(change):
    with pytest.raises(export.SnapshotExportError) as caught:
        export.ExportLimits(**change)
    assert caught.value.code == 'snapshot_limits_invalid'


def test_default_budget_and_result_privacy():
    limits = export.DEFAULT_LIMITS
    assert limits.files.max_file_bytes == 64 << 20
    assert limits.files.max_record_bytes == limits.codec.max_record_bytes == 32 << 20
    assert limits.files.max_metadata_bytes == 2 << 20
    assert limits.max_tables == 18
    assert limits.max_total_rows == 10_000_000
    assert limits.max_wall_seconds == 300


@pytest.mark.parametrize('path', [Hostile(), '', 'manifest.json', '/x/../b/manifest.json',
    r'C:\x\b\MANIFEST.json', r'\\host\x\b\manifest.json',
    r'C:\x\b\manifest.json:stream', r'C:\x\b.\manifest.json'])
def test_path_rejected_before_capability(monkeypatch, path):
    monkeypatch.setattr(files, 'open_trusted_parent', lambda *a, **k: pytest.fail('io_attempt'))
    with pytest.raises(export.SnapshotExportError) as caught:
        export.validate_export(path, trusted_parent_ack=True)
    assert caught.value.code == 'snapshot_path_invalid'


def test_validate_argument_binding_safe():
    for args, kwargs in [((), {}), ((Hostile(),), {}),
            ((Hostile(),), {'trusted_parent_ack': Hostile()}),
            ((Hostile(),), {'manifest_path': Hostile(), 'trusted_parent_ack': True})]:
        with pytest.raises(export.SnapshotExportError) as caught:
            export.validate_export(*args, **kwargs)
        assert caught.value.__cause__ is caught.value.__context__ is None


def test_safe_error_inside_active_except():
    try:
        raise ValueError(CANARY)
    except ValueError:
        with pytest.raises(export.SnapshotExportError) as caught:
            export.export_snapshot()
    assert caught.value.__cause__ is caught.value.__context__ is None
    assert str(caught.value) == 'snapshot_arguments_invalid'


def test_linux_native_not_run_here():
    if os.name != 'posix':
        pytest.skip('linux_native_not_run')
    pytest.skip('requires_separate_linux_native_acceptance')


def _values(profile, table, index=0):
    result = []
    tags = export._tags(profile, table)
    for allowed in tags:
        if 's' in allowed:
            result.append(CANARY + '\x00\n{"pending":"uncertain"}')
        elif 'i' in allowed:
            result.append(-index - 1)
        elif 'f' in allowed:
            result.append(-0.0)
        elif 'b' in allowed:
            result.append(False)
        elif 'date' in allowed:
            result.append(date(2020, 2, 29))
        elif 'dt' in allowed:
            result.append(datetime(2020, 2, 29, tzinfo=timezone.utc))
        else:
            pytest.fail('unexpected_static_tag')
    return tuple(result)


def _rows(profile, count=1):
    metadata = {table.name for table in profile.descriptor.metadata_tables}
    return {table.name: ((profile.descriptor.heads[0],),) if table.name in metadata else
        _stream(profile, table, count) for table in export._tables(profile)}


def _stream(profile, table, count):
    for index in range(count):
        yield _values(profile, table, index)


def _wire(profile_id='legacy_sqlite9_v1', count=1, limits=export.DEFAULT_LIMITS, split=False):
    profile = SOURCE_PROFILES[profile_id]
    schema = export._canonical(dict(descriptor=schema_document(profile.descriptor),
        fingerprint=schema_fingerprint(profile.descriptor)), limits, 'snapshot_schema_invalid')
    data = {'schema.json': schema}
    entries = [dict(name='schema.json', kind='schema', byte_count=len(schema), row_count=None,
        sha256=hashlib.sha256(schema).hexdigest())]
    docs = []
    row_count = 0
    for index, table in enumerate(export._tables(profile)):
        records = [codec.encode_row(row, allowed_tags=export._tags(profile, table), limits=limits.codec)
            for row in _rows(profile, count)[table.name]]
        chunks = records if split and records else [b''.join(records)]
        names = []
        for chunk_index, chunk in enumerate(chunks):
            name = export._chunk_name(index, chunk_index)
            names.append(name)
            data[name] = chunk
            entries.append(dict(name=name, kind='rows', byte_count=len(chunk),
                row_count=chunk.count(b'\n'), sha256=hashlib.sha256(chunk).hexdigest()))
        docs.append(dict(table_index=index, name=table.name, columns=[c.name for c in table.columns],
            rows=len(records), chunks=names))
        row_count += len(records)
    manifest = dict(format='install-video-db-snapshot', format_version=1, codec_version=1,
        schema_profile=profile_id, schema_profile_version=1, export_id='a' * 32,
        created_at='2026-01-02T03:04:05.000006Z', started_at='2026-01-02T03:04:05.000004Z',
        ended_at='2026-01-02T03:04:05.000005Z', source=dict(dialect=profile.descriptor.dialect,
            namespace=profile.descriptor.namespace, version='synthetic-not-observed'),
        snapshot_method='synthetic_rows_v1', schema_fingerprint=schema_fingerprint(profile.descriptor),
        limits_used=export._limits_document(limits), privacy='restricted-local-plaintext',
        migration_eligible='not_assessed', tables=docs, files=entries,
        totals=dict(table_count=len(docs), row_count=row_count,
            data_bytes=sum(len(v) for v in data.values()), file_count=len(data) + 1))
    return manifest, data


def _raw(manifest):
    return codec.canonical_json_bytes(manifest, max_bytes=2 << 20)


class Reader:
    def __init__(self, directory, name):
        self.directory, self.name, self.position = directory, name, 0
        self.closed = False
    def read_bounded(self, maximum):
        self.directory.reads.append((self.name, 'bounded'))
        value = self.directory.data[self.name]
        if len(value) > maximum:
            raise files.SnapshotFileError('snapshot_resource_limit')
        return value
    def read_chunk(self, maximum):
        assert maximum == 65536
        self.directory.reads.append((self.name, maximum))
        value = self.directory.data[self.name][self.position:self.position + maximum]
        self.position += len(value)
        return value
    def close(self):
        assert not self.closed
        self.closed = True
        self.directory.closed_readers += 1


class Directory:
    def __init__(self, data):
        self.data = data
        self.scans = 0
        self.reads = []
        self.closed_readers = 0
        self.opened = []
        self.closed = False
    def file_names(self):
        self.scans += 1
        return tuple(sorted(self.data))
    def open_file(self, name):
        self.opened.append(name)
        return Reader(self, name)
    def open_owned(self, name):
        return self.open_file(name)
    def close(self):
        self.closed = True
    def __getattr__(self, name):
        raise AssertionError('private_capability_access')


def _core(manifest, data, *, limits=export.DEFAULT_LIMITS):
    raw = _raw(manifest)
    directory = Directory(dict(data, **{'manifest.json': raw}))
    report, unused = export._validate_core(raw, directory, limits, export.time.monotonic())
    return report, directory


@pytest.mark.parametrize('profile_id', tuple(SOURCE_PROFILES))
@pytest.mark.parametrize('count', [0, 1, 3])
def test_pure_complete_six_profiles(profile_id, count):
    manifest, data = _wire(profile_id, count, split=True)
    report, directory = _core(manifest, data)
    assert report.accepted is True
    assert report.migration_eligible == 'not_assessed'
    assert report.row_count == manifest['totals']['row_count']
    assert directory.scans == 2
    assert directory.closed_readers == len(data)
    assert len(directory.opened) == len(set(directory.opened))
    assert CANARY not in repr(report)
    assert report.schema_profile == profile_id


@pytest.mark.parametrize('key,value', [('format', CANARY), ('format_version', True),
    ('codec_version', 2), ('schema_profile_version', False), ('export_id', 'A' * 32),
    ('created_at', '2026-02-30T03:04:05.000006Z'), ('ended_at', '2025-01-02T03:04:05.000005Z'),
    ('started_at', '2026-01-02T03:04:05Z'), ('privacy', CANARY),
    ('migration_eligible', 'yes'), ('snapshot_method', 'database'),
    ('schema_profile', CANARY), ('schema_fingerprint', '0' * 64)], ids=[f'constant-{i}' for i in range(13)])
def test_manifest_exact_constants(key, value):
    manifest, data = _wire()
    manifest[key] = value
    with pytest.raises(export.SnapshotExportError):
        _core(manifest, data)


@pytest.mark.parametrize('location', ['root', 'source', 'totals', 'table', 'file', 'limits', 'codec', 'files'])
@pytest.mark.parametrize('operation', ['extra', 'missing'])
def test_manifest_exact_keys(location, operation):
    manifest, data = _wire()
    obj = {'root': manifest, 'source': manifest['source'], 'totals': manifest['totals'],
        'table': manifest['tables'][0], 'file': manifest['files'][0], 'limits': manifest['limits_used'],
        'codec': manifest['limits_used']['codec'], 'files': manifest['limits_used']['files']}[location]
    if operation == 'extra':
        obj[CANARY] = 1
    else:
        del obj[next(iter(obj))]
    with pytest.raises(export.SnapshotExportError):
        _core(manifest, data)


@pytest.mark.parametrize('operation', ['table-bool', 'table-order', 'table-name', 'column-order',
    'rows-bool', 'rows-negative', 'chunk-order', 'chunk-wrong-table', 'chunk-case', 'chunk-path',
    'chunk-gap', 'chunk-duplicate', 'file-extra', 'file-order', 'hash-upper', 'hash-invalid',
    'bytes-bool', 'totals-bool', 'source-extra', 'source-dialect', 'schema-profile-shell'])
def test_table_file_mapping_shape(operation):
    manifest, data = _wire(count=2, split=True)
    if operation == 'table-bool': manifest['tables'][0]['table_index'] = False
    elif operation == 'table-order': manifest['tables'].reverse()
    elif operation == 'table-name': manifest['tables'][0]['name'] = CANARY
    elif operation == 'column-order': manifest['tables'][0]['columns'].reverse()
    elif operation == 'rows-bool': manifest['tables'][0]['rows'] = True
    elif operation == 'rows-negative': manifest['tables'][0]['rows'] = -1
    elif operation == 'chunk-order': manifest['tables'][0]['chunks'].reverse()
    elif operation == 'chunk-wrong-table': manifest['tables'][0]['chunks'][0] = 't01-000000.jsonl'
    elif operation == 'chunk-case': manifest['tables'][0]['chunks'][0] = 'T00-000000.jsonl'
    elif operation == 'chunk-path': manifest['tables'][0]['chunks'][0] = '../' + CANARY
    elif operation == 'chunk-gap': manifest['tables'][0]['chunks'][1] = 't00-000002.jsonl'
    elif operation == 'chunk-duplicate': manifest['tables'][0]['chunks'][1] = 't00-000000.jsonl'
    elif operation == 'file-extra': manifest['files'].append(dict(manifest['files'][0]))
    elif operation == 'file-order': manifest['files'].reverse()
    elif operation == 'hash-upper': manifest['files'][0]['sha256'] = 'A' * 64
    elif operation == 'hash-invalid': manifest['files'][0]['sha256'] = 'g' * 64
    elif operation == 'bytes-bool': manifest['files'][0]['byte_count'] = True
    elif operation == 'totals-bool': manifest['totals']['table_count'] = True
    elif operation == 'source-extra': manifest['source'][CANARY] = 'x'
    elif operation == 'source-dialect': manifest['source']['dialect'] = 'postgresql'
    elif operation == 'schema-profile-shell': manifest['schema_profile'] = 'pg_b1_0001_v1'
    with pytest.raises(export.SnapshotExportError):
        _core(manifest, data)


def _replace_data(manifest, data, name, value):
    data[name] = value
    entry = next(item for item in manifest['files'] if item['name'] == name)
    entry['byte_count'] = len(value)
    entry['sha256'] = hashlib.sha256(value).hexdigest()
    manifest['totals']['data_bytes'] = sum(item['byte_count'] for item in manifest['files'])


@pytest.mark.parametrize('operation', ['descriptor-bool', 'descriptor-nullable', 'descriptor-column',
    'fingerprint', 'extra', 'missing', 'noncanonical'])
def test_complete_expected_schema_matching(operation):
    manifest, data = _wire()
    schema = codec.strict_json_loads(data['schema.json'], max_bytes=2 << 20)
    if operation == 'descriptor-bool': schema['descriptor']['descriptor_version'] = True
    elif operation == 'descriptor-nullable':
        schema['descriptor']['tables'][0]['columns'][0]['nullable'] = 0
    elif operation == 'descriptor-column': schema['descriptor']['tables'][0]['columns'].reverse()
    elif operation == 'fingerprint': schema['fingerprint'] = '0' * 64
    elif operation == 'extra': schema[CANARY] = 0
    elif operation == 'missing': del schema['descriptor']
    raw = codec.canonical_json_bytes(schema, max_bytes=2 << 20)
    if operation == 'noncanonical': raw = raw[:-1] + b' \n'
    _replace_data(manifest, data, 'schema.json', raw)
    with pytest.raises(export.SnapshotExportError) as caught:
        _core(manifest, data)
    assert caught.value.code == 'snapshot_schema_invalid'


@pytest.mark.parametrize('operation', ['missing-lf', 'extra-lf', 'empty-line', 'wrong-tag', 'wrong-columns',
    'noncanonical', 'bad-integer', 'duplicate-key', 'truncated', 'hash', 'size', 'row-count'])
def test_chunk_integrity_and_records(operation):
    manifest, data = _wire()
    name = manifest['tables'][0]['chunks'][0]
    original = data[name]
    entry = manifest['files'][1]
    if operation == 'missing-lf': _replace_data(manifest, data, name, original[:-1])
    elif operation == 'extra-lf': _replace_data(manifest, data, name, original + b'\n')
    elif operation == 'empty-line': _replace_data(manifest, data, name, b'\n')
    elif operation == 'wrong-tag': _replace_data(manifest, data, name, original.replace(b'"s"', b'"b"', 1))
    elif operation == 'wrong-columns': _replace_data(manifest, data, name, b'[]\n')
    elif operation == 'noncanonical': _replace_data(manifest, data, name, b' ' + original)
    elif operation == 'bad-integer': _replace_data(manifest, data, name, b'[["i","01"]]\n')
    elif operation == 'duplicate-key': _replace_data(manifest, data, name, b'{"x":1,"x":2}\n')
    elif operation == 'truncated': data[name] = original[:-3]
    elif operation == 'hash': entry['sha256'] = '0' * 64
    elif operation == 'size': entry['byte_count'] += 1; manifest['totals']['data_bytes'] += 1
    elif operation == 'row-count': entry['row_count'] += 1
    with pytest.raises(export.SnapshotExportError):
        _core(manifest, data)


@pytest.mark.parametrize('operation', ['missing', 'extra', 'part', 'unicode', 'case', 'marker-missing'])
def test_directory_exact_file_set(operation):
    manifest, data = _wire()
    raw = _raw(manifest)
    data['manifest.json'] = raw
    name = manifest['tables'][0]['chunks'][0]
    if operation == 'missing': del data[name]
    elif operation == 'extra': data['t17-999999.jsonl'] = b''
    elif operation == 'part': data['.manifest.part'] = raw
    elif operation == 'unicode': data['schem\u0430.json'] = data.pop('schema.json')
    elif operation == 'case': data['Schema.json'] = data.pop('schema.json')
    elif operation == 'marker-missing': del data['manifest.json']
    with pytest.raises(export.SnapshotExportError):
        export._validate_core(raw, Directory(data), export.DEFAULT_LIMITS, export.time.monotonic())


@pytest.mark.parametrize('operation', ['noncanonical', 'duplicate', 'depth', 'node', 'integer', 'size'])
def test_bounded_hostile_metadata(operation):
    manifest, data = _wire()
    raw = _raw(manifest)
    limits = export.DEFAULT_LIMITS
    if operation == 'noncanonical': raw = b' ' + raw
    elif operation == 'duplicate': raw = b'{"x":1,"x":2}\n'
    elif operation == 'depth': raw = b'[' * 33 + b'0' + b']' * 33 + b'\n'
    elif operation == 'node': limits = replace(limits, codec=replace(limits.codec, max_json_nodes=5))
    elif operation == 'integer': raw = b'{"x":' + b'1' * 4097 + b'}\n'
    elif operation == 'size': raw = b' ' * ((2 << 20) + 1)
    with pytest.raises(export.SnapshotExportError):
        export._parse_manifest(raw, limits)


@pytest.mark.parametrize('scope,key,value', [('codec', 'max_json_depth', 2),
    ('codec', 'max_json_nodes', 20), ('files', 'max_metadata_bytes', 100),
    ('files', 'max_record_bytes', 1), ('files', 'max_file_bytes', 1),
    ('files', 'max_files', 3), ('files', 'max_total_bytes', 1)])
def test_manifest_self_declared_budget_cannot_be_escaped(scope, key, value):
    manifest, data = _wire()
    manifest['limits_used'][scope][key] = value
    if key == 'max_file_bytes': manifest['limits_used']['files']['max_record_bytes'] = 1
    with pytest.raises(export.SnapshotExportError):
        _core(manifest, data)


@pytest.mark.parametrize('profile_id', tuple(SOURCE_PROFILES))
@pytest.mark.parametrize('count', [0, 1, 3])
def test_native_build_then_final_validate(profile_id, count):
    profile = SOURCE_PROFILES[profile_id]
    basename = 'b-' + uuid.uuid4().hex
    parent = os.environ['B6_BUNDLE_PARENT']
    result = export._build_synthetic_bundle(parent, basename, profile_id, _rows(profile, count),
        trusted_parent_ack=True)
    assert result.status == 'published'
    assert result.published and result.cleanup_complete
    assert result.directory_synced is None if os.name == 'nt' else result.directory_synced is True
    report = export.validate_export(str(Path(parent)/basename/'manifest.json'), trusted_parent_ack=True)
    assert report.accepted
    assert report.manifest_sha256 == result.manifest_sha256
    assert report.file_count == result.file_count
    assert CANARY not in repr(result)
    assert not hasattr(result, 'to_dict')


def _mock_final(monkeypatch, manifest, data):
    raw = _raw(manifest)
    directory = Directory(dict(data, **{'manifest.json': raw}))
    parent = Directory({})
    monkeypatch.setattr(files, 'open_trusted_parent', lambda *a, **k: parent)
    monkeypatch.setattr(files, 'open_directory', lambda *a, **k: directory)
    return directory, parent


def _manifest_path():
    return r'C:\synthetic\bundle\manifest.json' if os.name == 'nt' else '/synthetic/bundle/manifest.json'


def test_final_reader_one_pass_and_all_closed(monkeypatch):
    manifest, data = _wire()
    directory, parent = _mock_final(monkeypatch, manifest, data)
    report = export.validate_export(_manifest_path(), trusted_parent_ack=True)
    assert report.accepted and directory.closed and parent.closed
    assert directory.scans == 2
    assert directory.opened.count('manifest.json') == directory.opened.count('schema.json') == 1
    assert directory.closed_readers == len(data) + 1


@pytest.mark.parametrize('resource', ['reader', 'directory', 'parent'])
def test_final_close_failure_never_accepted(monkeypatch, resource):
    manifest, data = _wire()
    directory, parent = _mock_final(monkeypatch, manifest, data)
    def broken(*args):
        raise OSError(CANARY)
    if resource == 'reader': monkeypatch.setattr(Reader, 'close', broken)
    elif resource == 'directory': monkeypatch.setattr(directory, 'close', broken)
    else: monkeypatch.setattr(parent, 'close', broken)
    with pytest.raises(export.SnapshotExportError) as caught:
        export.validate_export(_manifest_path(), trusted_parent_ack=True)
    assert caught.value.code == 'snapshot_io_failed'
    assert caught.value.__cause__ is caught.value.__context__ is None


def test_evolving_directory_detected_second_scan(monkeypatch):
    manifest, data = _wire()
    directory, unused = _mock_final(monkeypatch, manifest, data)
    original = directory.file_names
    def scan():
        names = original()
        return names if directory.scans == 1 else names + ('t17-999999.jsonl',)
    monkeypatch.setattr(directory, 'file_names', scan)
    with pytest.raises(export.SnapshotExportError) as caught:
        export.validate_export(_manifest_path(), trusted_parent_ack=True)
    assert caught.value.code == 'snapshot_file_set_invalid'


def test_final_set_scan_precedes_marker_open(monkeypatch):
    manifest, data = _wire()
    directory, unused = _mock_final(monkeypatch, manifest, data)
    original = directory.open_file
    def opening(name):
        assert directory.scans == 1
        return original(name)
    monkeypatch.setattr(directory, 'open_file', opening)
    assert export.validate_export(_manifest_path(), trusted_parent_ack=True).accepted


def test_self_declared_deadline_includes_final_closes(monkeypatch):
    manifest, data = _wire()
    manifest['limits_used']['max_wall_seconds'] = 1
    directory, parent = _mock_final(monkeypatch, manifest, data)
    now = [0]
    monkeypatch.setattr(export.time, 'monotonic', lambda: now[0])
    def close(): now[0] = 2
    monkeypatch.setattr(parent, 'close', close)
    with pytest.raises(export.SnapshotExportError) as caught:
        export.validate_export(_manifest_path(), trusted_parent_ack=True)
    assert caught.value.code == 'snapshot_resource_limit'


@pytest.mark.parametrize('resource', ['reader', 'directory', 'parent'])
def test_original_baseexception_preserved_when_close_fails(monkeypatch, resource):
    manifest, data = _wire()
    directory, parent = _mock_final(monkeypatch, manifest, data)
    original = KeyboardInterrupt(CANARY)
    def stop(*args): raise original
    def close(*args): raise OSError(CANARY)
    monkeypatch.setattr(Reader, 'read_chunk', stop)
    monkeypatch.setattr(Reader, 'read_bounded', stop)
    if resource == 'reader': monkeypatch.setattr(Reader, 'close', close)
    elif resource == 'directory': monkeypatch.setattr(directory, 'close', close)
    else: monkeypatch.setattr(parent, 'close', close)
    with pytest.raises(KeyboardInterrupt) as caught:
        export.validate_export(_manifest_path(), trusted_parent_ack=True)
    assert caught.value is original


class Owner(Directory):
    def __init__(self, fault=None, publication=None):
        super().__init__({})
        self.fault, self.publication = fault, publication
        self.events = []
        self.aborts, self.closes, self.publishes = 0, 0, 0
    def write_file(self, name, blocks):
        self.events.append(('write', name))
        if self.fault == 'write': raise OSError(CANARY)
        collected = bytearray()
        for block in blocks:
            assert type(block) is bytes and len(block) <= 65536
            collected.extend(block)
        value = bytes(collected)
        self.data[name] = value
        return files.FileDigest(name, len(value), hashlib.sha256(value).hexdigest())
    def open_owned(self, name):
        self.events.append(('read', name))
        assert 'manifest.json' not in self.data and '.manifest.part' not in self.data
        if self.fault == 'read': raise OSError(CANARY)
        return super().open_owned(name)
    def publish_marker(self, raw):
        self.events.append(('publish',))
        self.publishes += 1
        assert self.closed_readers == len(self.data)
        if isinstance(self.fault, BaseException): raise self.fault
        if self.fault == 'publish': raise OSError(CANARY)
        self.data['manifest.json'] = raw
        return self.publication or files.PublishResult('published', True, True, None, (),
            files.FileDigest('manifest.json', len(raw), hashlib.sha256(raw).hexdigest()))
    def abort(self):
        self.events.append(('abort',))
        self.aborts += 1
        if self.fault == 'abort': raise OSError(CANARY)
        self.data.clear()
    def close(self):
        self.events.append(('close',))
        self.closes += 1
        if self.fault == 'close': raise OSError(CANARY)
        super().close()


def _mock_builder(monkeypatch, owner=None):
    owner = owner or Owner()
    parent = Directory({})
    monkeypatch.setattr(files, 'open_trusted_parent', lambda *a, **k: parent)
    monkeypatch.setattr(files, 'reserve_directory', lambda *a, **k: owner)
    monkeypatch.setattr(export, 'validate_export', lambda *a, **k: pytest.fail('public_validator_in_builder'))
    return owner, parent


def _build(monkeypatch, *, owner=None, rows=None, limits=export.DEFAULT_LIMITS):
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    owner, parent = _mock_builder(monkeypatch, owner)
    result = export._build_synthetic_bundle('opaque-trusted-parent', 'synthetic', profile.profile_id,
        _rows(profile) if rows is None else rows, trusted_parent_ack=True, limits=limits)
    return result, owner, parent


def test_staged_validation_precedes_only_real_marker(monkeypatch):
    result, owner, parent = _build(monkeypatch)
    assert result.published and owner.closed and parent.closed
    assert owner.aborts == 0 and owner.publishes == owner.closes == 1
    assert owner.events[-2:] == [('publish',), ('close',)]
    assert owner.scans == 2
    assert sum(event[0] == 'read' for event in owner.events) == result.file_count - 1
    assert owner.file_names() == tuple(sorted(owner.data))


@pytest.mark.parametrize('fault', ['write', 'read', 'staged-hash', 'record'])
def test_prepublication_failures_abort_only_owned(monkeypatch, fault):
    owner = Owner(fault if fault in ('write', 'read') else None)
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    rows = _rows(profile)
    if fault == 'record': rows[profile.descriptor.tables[0].name] = ((Hostile(),),)
    if fault == 'staged-hash':
        original = owner.write_file
        def write(name, blocks):
            digest = original(name, blocks)
            return files.FileDigest(name, digest.byte_count, '0' * 64)
        monkeypatch.setattr(owner, 'write_file', write)
    with pytest.raises(export.SnapshotExportError):
        _build(monkeypatch, owner=owner, rows=rows)
    assert owner.aborts == owner.closes == 1 and owner.publishes == 0
    assert not owner.data


@pytest.mark.parametrize('status,cleanup,synced,codes', [
    ('published', True, None, ()),
    ('published_cleanup_pending', False, None, ('part_cleanup_failed',)),
    ('published_durability_pending', True, False, ('directory_sync_failed',)),
    ('published_cleanup_pending', False, False, ('part_cleanup_failed', 'directory_sync_failed'))])
def test_exact_publication_outcomes_are_preserved(monkeypatch, status, cleanup, synced, codes):
    publication = files.PublishResult(status, True, cleanup, synced, codes,
        files.FileDigest('manifest.json', 1, '0' * 64))
    result, owner, unused = _build(monkeypatch, owner=Owner(publication=publication))
    assert (result.status, result.cleanup_complete, result.directory_synced, result.error_codes) == (
        status, cleanup, synced, codes)
    assert result.published and owner.aborts == 0


@pytest.mark.parametrize('fault', ['publish', 'close'])
def test_publish_attempted_never_aborts_or_retries_close(monkeypatch, fault):
    owner = Owner(fault)
    with pytest.raises(export.SnapshotExportError) as caught:
        _build(monkeypatch, owner=owner)
    assert caught.value.code == 'snapshot_publish_outcome_uncertain'
    assert caught.value.__cause__ is caught.value.__context__ is None
    assert owner.publishes == 1 and owner.aborts == 0 and owner.closes == 1
    assert len(owner.data) >= 10


@pytest.mark.parametrize('phase', ['before', 'publish'])
@pytest.mark.parametrize('error_type', [KeyboardInterrupt, SystemExit])
def test_builder_baseexception_original_object_survives_cleanup(monkeypatch, phase, error_type):
    original = error_type(CANARY)
    owner = Owner(original if phase == 'publish' else None)
    if phase == 'before':
        def stop(*args): raise original
        monkeypatch.setattr(owner, 'write_file', stop)
    close = owner.close
    def bad_close():
        close()
        raise OSError(CANARY)
    monkeypatch.setattr(owner, 'close', bad_close)
    with pytest.raises(error_type) as caught:
        _build(monkeypatch, owner=owner)
    assert caught.value is original
    assert owner.aborts == int(phase == 'before')
    assert owner.publishes == int(phase == 'publish')


def test_builder_cleanup_failure_fixed_code(monkeypatch):
    owner = Owner('abort')
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    rows = _rows(profile)
    rows[profile.descriptor.tables[0].name] = ((Hostile(),),)
    with pytest.raises(export.SnapshotExportError) as caught:
        _build(monkeypatch, owner=owner, rows=rows)
    assert caught.value.code == 'snapshot_cleanup_failed'
    assert owner.aborts == owner.closes == 1 and owner.publishes == 0


def test_builder_no_table_row_cache_and_greedy_chunks(monkeypatch):
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    first = profile.descriptor.tables[0]
    record = codec.encode_row(_values(profile, first), allowed_tags=export._tags(profile, first))
    chunk_limit = len(record) * 2
    limits = replace(export.DEFAULT_LIMITS,
        files=replace(export.DEFAULT_LIMITS.files, max_file_bytes=chunk_limit, max_record_bytes=len(record)))
    seen = [0]
    owner = Owner()
    rows = _rows(profile, 0)
    def stream():
        for index in range(7):
            seen[0] += 1
            if index >= 3:
                assert any(event[0] == 'write' and event[1].endswith('.jsonl') for event in owner.events)
            yield _values(profile, first)
    rows[first.name] = stream()
    result, owner, unused = _build(monkeypatch, owner=owner, rows=rows, limits=limits)
    assert seen[0] == 7 and result.row_count == 7
    manifest = codec.strict_json_loads(owner.data['manifest.json'], max_bytes=2 << 20)
    index = next(i for i, table in enumerate(export._tables(profile)) if table.name == first.name)
    chunks = manifest['tables'][index]['chunks']
    assert len(chunks) == 4
    assert [entry['row_count'] for entry in manifest['files'] if entry['name'] in chunks] == [2, 2, 2, 1]


@pytest.mark.parametrize('operation', ['wrong', 'zero', 'two', 'type'])
def test_pg_metadata_single_exact_static_head(operation):
    manifest, data = _wire('pg_b1_0001_v1', 0)
    doc = next(table for table in manifest['tables'] if table['name'] == 'alembic_version')
    name = doc['chunks'][0]
    entry = next(item for item in manifest['files'] if item['name'] == name)
    if operation == 'wrong': raw = codec.encode_row((CANARY,))
    elif operation == 'zero': raw = b''
    elif operation == 'two': raw = data[name] * 2
    else: raw = codec.encode_row((42,))
    rows = raw.count(b'\n')
    delta = rows - doc['rows']
    doc['rows'] = rows
    entry['row_count'] = rows
    manifest['totals']['row_count'] += delta
    _replace_data(manifest, data, name, raw)
    with pytest.raises(export.SnapshotExportError) as caught:
        _core(manifest, data)
    assert caught.value.code in ('snapshot_schema_invalid', 'snapshot_record_invalid')


@pytest.mark.parametrize('value', [None, -42, -0.0, b'\x00\xff', CANARY + '\x00\n'])
def test_sqlite_physical_values_and_null_history_roundtrip(value, monkeypatch):
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    table = next(table for table in profile.descriptor.tables if any(c.nullable for c in table.columns))
    index = next(i for i, c in enumerate(table.columns) if c.nullable)
    values = list(_values(profile, table))
    values[index] = value
    rows = _rows(profile, 0)
    rows[table.name] = (tuple(values), tuple(values))  # Duplicate logical keys are preserved.
    result, owner, unused = _build(monkeypatch, rows=rows)
    assert result.row_count == 2
    table_index = next(i for i, t in enumerate(export._tables(profile)) if t.name == table.name)
    record = owner.data[export._chunk_name(table_index, 0)].splitlines(keepends=True)[0]
    decoded = codec.decode_row(record, allowed_tags=export._tags(profile, table))
    assert type(decoded[index]) is type(value) and decoded[index] == value
    if type(value) is float: assert decoded[index].hex() == value.hex()


@pytest.mark.parametrize('scope', ['codec', 'files'])
def test_all_limit_fields_exact_int_and_hard_bounds(scope):
    hard = getattr(export.DEFAULT_LIMITS, scope)
    for field in fields(hard):
        for value in (True, 0, getattr(hard, field.name) + 1, CANARY):
            manifest, data = _wire(count=0)
            manifest['limits_used'][scope][field.name] = value
            with pytest.raises(export.SnapshotExportError):
                _core(manifest, data)


@pytest.mark.parametrize('name', ['max_tables', 'max_total_rows', 'max_wall_seconds'])
@pytest.mark.parametrize('value', [True, 0, CANARY])
def test_scalar_declared_limits_exact(name, value):
    manifest, data = _wire(count=0)
    manifest['limits_used'][name] = value
    with pytest.raises(export.SnapshotExportError):
        _core(manifest, data)


@pytest.mark.parametrize('key', ['table_count', 'row_count', 'data_bytes', 'file_count'])
@pytest.mark.parametrize('delta', [-1, 1])
def test_totals_recomputed_exactly(key, delta):
    manifest, data = _wire()
    manifest['totals'][key] += delta
    with pytest.raises(export.SnapshotExportError) as caught:
        _core(manifest, data)
    assert caught.value.code == 'snapshot_integrity_failed'


@pytest.mark.parametrize('kind', ['rows', 'files', 'bytes', 'chunk', 'record'])
@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_local_resource_boundaries(kind, delta):
    manifest, data = _wire(count=0)
    # One business row, keeping the rest empty, makes exact boundaries small.
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    table = export._tables(profile)[0]
    name = export._chunk_name(0, 0)
    raw = codec.encode_row(_values(profile, table), allowed_tags=export._tags(profile, table))
    row_count = 2 if kind == 'rows' else 1
    raw *= row_count
    manifest['tables'][0]['rows'] = row_count
    manifest['files'][1]['row_count'] = row_count
    manifest['totals']['row_count'] = row_count
    _replace_data(manifest, data, name, raw)
    local = export.DEFAULT_LIMITS
    if kind == 'rows': local = replace(local, max_total_rows=row_count + delta)
    elif kind == 'files': local = replace(local, files=replace(local.files,
        max_files=manifest['totals']['file_count'] + delta))
    elif kind == 'bytes': local = replace(local, files=replace(local.files,
        max_total_bytes=manifest['totals']['data_bytes'] + delta))
    elif kind == 'chunk': local = replace(local, files=replace(local.files,
        max_file_bytes=len(raw) + delta, max_record_bytes=len(raw) + delta))
    elif kind == 'record': local = replace(local, files=replace(local.files, max_record_bytes=len(raw) + delta))
    if delta < 0:
        with pytest.raises(export.SnapshotExportError) as caught:
            _core(manifest, data, limits=local)
        assert caught.value.code == 'snapshot_resource_limit'
    else:
        assert _core(manifest, data, limits=local)[0].accepted


@pytest.mark.parametrize('extra', [False, True])
def test_builder_total_row_boundary_stops_stream(monkeypatch, extra):
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    table = profile.descriptor.tables[0]
    rows = _rows(profile, 0)
    consumed = [0]
    def stream():
        for index in range(2 + int(extra)):
            consumed[0] += 1
            yield _values(profile, table)
        if extra: pytest.fail('unbounded_consumption')
    rows[table.name] = stream()
    local = replace(export.DEFAULT_LIMITS, max_total_rows=2)
    if extra:
        with pytest.raises(export.SnapshotExportError) as caught:
            _build(monkeypatch, rows=rows, limits=local)
        assert caught.value.code == 'snapshot_resource_limit'
        assert consumed[0] == 3
    else:
        assert _build(monkeypatch, rows=rows, limits=local)[0].row_count == 2


def test_no_greedy_boundary_requirement_in_validator():
    manifest, data = _wire(count=3, split=True)
    assert _core(manifest, data)[0].accepted


@pytest.mark.parametrize('invalid', ['middle-empty', 'tail-empty', 'empty-multiple'])
def test_chunk_empty_rules(invalid):
    manifest, data = _wire(count=3 if invalid != 'empty-multiple' else 0, split=True)
    doc = manifest['tables'][0]
    if invalid == 'empty-multiple':
        name = export._chunk_name(0, 1)
        doc['chunks'].append(name)
        manifest['files'].insert(2, dict(name=name, kind='rows', byte_count=0, row_count=0,
            sha256=hashlib.sha256(b'').hexdigest()))
        data[name] = b''
        manifest['totals']['file_count'] += 1
    else:
        name = doc['chunks'][0 if invalid == 'middle-empty' else -1]
        entry = next(item for item in manifest['files'] if item['name'] == name)
        entry['row_count'] = 0
        _replace_data(manifest, data, name, b'')
    with pytest.raises(export.SnapshotExportError):
        _core(manifest, data)


def test_record_spans_read_blocks_and_only_64k_reads():
    manifest, data = _wire(count=0)
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    table = export._tables(profile)[0]
    row = list(_values(profile, table))
    row[0] = 'x' * 150000
    raw = codec.encode_row(row, allowed_tags=export._tags(profile, table))
    manifest['tables'][0]['rows'] = 1
    manifest['files'][1]['row_count'] = 1
    manifest['totals']['row_count'] = 1
    _replace_data(manifest, data, export._chunk_name(0, 0), raw)
    report, directory = _core(manifest, data)
    assert report.accepted
    assert len([item for item in directory.reads if item == (export._chunk_name(0, 0), 65536)]) >= 4


def test_wall_clock_checked_between_row_and_write(monkeypatch):
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    first = profile.descriptor.tables[0]
    rows = _rows(profile, 0)
    now = [0]
    monkeypatch.setattr(export.time, 'monotonic', lambda: now[0])
    def stream():
        yield _values(profile, first)
        now[0] = 2
        yield _values(profile, first)
        pytest.fail('unbounded_consumption')
    rows[first.name] = stream()
    with pytest.raises(export.SnapshotExportError) as caught:
        _build(monkeypatch, rows=rows, limits=replace(export.DEFAULT_LIMITS, max_wall_seconds=1))
    assert caught.value.code == 'snapshot_resource_limit'


def test_import_network_guard_and_no_db_application_modules():
    import socket
    with pytest.raises(RuntimeError): socket.getaddrinfo('invalid.example', 443)
    with pytest.raises(RuntimeError): socket.socket().connect(('127.0.0.1', 1))
    assert not any(name.split('.')[0] in {'app', 'sqlalchemy', 'sqlmodel', 'alembic', 'sqlite3',
        '_sqlite3', 'psycopg', 'psycopg2', 'dotenv'} for name in sys.modules)
    assert 'tools.production_db_snapshot' not in sys.modules
    assert 'tools.production_db_inventory' not in sys.modules


@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_metadata_limit_boundary(delta):
    manifest, data = _wire(count=0)
    cap = max(len(data['schema.json']), len(_raw(manifest))) + delta
    limits = replace(export.DEFAULT_LIMITS, files=replace(export.DEFAULT_LIMITS.files, max_metadata_bytes=cap))
    if delta < 0:
        with pytest.raises(export.SnapshotExportError) as caught:
            _core(manifest, data, limits=limits)
        assert caught.value.code == 'snapshot_resource_limit'
    else:
        assert _core(manifest, data, limits=limits)[0].accepted


def test_metadata_clock_cooperates_each_64k_read(monkeypatch):
    manifest, data = _wire()
    manifest['limits_used']['max_wall_seconds'] = 1
    manifest['export_id'] = 'b' * 32
    directory, unused = _mock_final(monkeypatch, manifest, data)
    now = [0]
    monkeypatch.setattr(export.time, 'monotonic', lambda: now[0])
    original = Reader.read_chunk
    def read(reader, size):
        value = original(reader, size)
        if reader.name == 'manifest.json': now[0] = 2
        return value
    monkeypatch.setattr(Reader, 'read_chunk', read)
    with pytest.raises(export.SnapshotExportError) as caught:
        export.validate_export(_manifest_path(), trusted_parent_ack=True,
            limits=replace(export.DEFAULT_LIMITS, max_wall_seconds=1))
    assert caught.value.code == 'snapshot_resource_limit'


@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_clock_limit_exact_boundary(monkeypatch, delta):
    monkeypatch.setattr(export.time, 'monotonic', lambda: 2 + delta)
    budget = export._Budget(replace(export.DEFAULT_LIMITS, max_wall_seconds=2), 0)
    if delta > 0:
        with pytest.raises(export.SnapshotExportError): budget.tick()
    else:
        budget.tick()


def test_native_greedy_multi_chunk_and_empty_tables():
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    table = profile.descriptor.tables[0]
    row = _values(profile, table)
    record = codec.encode_row(row, allowed_tags=export._tags(profile, table))
    local = replace(export.DEFAULT_LIMITS, files=replace(export.DEFAULT_LIMITS.files,
        max_file_bytes=len(record) * 2, max_record_bytes=len(record)))
    parent, basename = os.environ['B6_BUNDLE_PARENT'], 'multi-' + uuid.uuid4().hex
    rows = _rows(profile, 0)
    rows[table.name] = (row for unused in range(7))
    result = export._build_synthetic_bundle(parent, basename, profile.profile_id, rows,
        trusted_parent_ack=True, limits=local)
    report = export.validate_export(str(Path(parent)/basename/'manifest.json'), trusted_parent_ack=True, limits=local)
    assert report.accepted and report.row_count == 7
    assert result.file_count == len(profile.descriptor.tables) + 5


def test_native_foreign_object_retained_on_abort_failure(monkeypatch):
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    parent, basename = os.environ['B6_BUNDLE_PARENT'], 'foreign-' + uuid.uuid4().hex
    original = files.reserve_directory
    def reserve(*args, **kwargs):
        owner = original(*args, **kwargs)
        # Test-owned unrelated inode. The builder must never gain its deletion authority.
        with (Path(parent)/basename/'foreign.txt').open('xb'):
            pass
        return owner
    monkeypatch.setattr(files, 'reserve_directory', reserve)
    rows = _rows(profile, 0)
    rows[profile.descriptor.tables[0].name] = ((Hostile(),),)
    with pytest.raises(export.SnapshotExportError) as caught:
        export._build_synthetic_bundle(parent, basename, profile.profile_id, rows, trusted_parent_ack=True)
    assert caught.value.code == 'snapshot_cleanup_failed'
    assert (Path(parent)/basename/'foreign.txt').is_file()
    assert not (Path(parent)/basename/'manifest.json').exists()


@pytest.mark.parametrize('phase', ['reader', 'directory', 'parent'])
@pytest.mark.parametrize('error_type', [KeyboardInterrupt, SystemExit])
def test_review_i1_new_close_baseexception_supersedes_ordinary_and_closes_rest(monkeypatch, phase, error_type):
    manifest, data = _wire()
    manifest['format_version'] = 2
    directory, parent = _mock_final(monkeypatch, manifest, data)
    stop = error_type(CANARY)
    calls = [0]
    def close(*args):
        calls[0] += 1
        raise stop
    if phase == 'reader':
        def invalid(*args): raise export.SnapshotExportError('snapshot_manifest_invalid')
        monkeypatch.setattr(Reader, 'read_chunk', invalid)
        monkeypatch.setattr(Reader, 'close', close)
    else:
        monkeypatch.setattr(directory if phase == 'directory' else parent, 'close', close)
    with pytest.raises(error_type) as caught:
        export.validate_export(_manifest_path(), trusted_parent_ack=True)
    assert caught.value is stop and calls[0] == 1
    if phase == 'reader': assert directory.closed
    if phase != 'parent': assert parent.closed


@pytest.mark.parametrize('phase', ['abort', 'owner-close', 'parent-close'])
@pytest.mark.parametrize('error_type', [KeyboardInterrupt, SystemExit])
def test_review_i2_new_cleanup_baseexception_still_closes_remaining_once(monkeypatch, phase, error_type):
    owner, parent = _mock_builder(monkeypatch, Owner('write'))
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    stop = error_type(CANARY)
    interrupted_calls, parent_calls = [0], [0]
    def interrupt():
        interrupted_calls[0] += 1
        raise stop
    original_parent_close = parent.close
    def parent_close():
        parent_calls[0] += 1
        if phase == 'parent-close': raise stop
        original_parent_close()
    monkeypatch.setattr(parent, 'close', parent_close)
    if phase == 'abort': monkeypatch.setattr(owner, 'abort', interrupt)
    elif phase == 'owner-close': monkeypatch.setattr(owner, 'close', interrupt)
    with pytest.raises(error_type) as caught:
        export._build_synthetic_bundle('opaque', 'synthetic', profile.profile_id, _rows(profile, 0),
            trusted_parent_ack=True)
    assert caught.value is stop
    assert parent_calls[0] == 1
    assert owner.closes == (0 if phase == 'owner-close' else 1)
    assert owner.publishes == 0
    assert owner.aborts == (0 if phase == 'abort' else 1)
    if phase != 'parent-close': assert interrupted_calls[0] == 1


@pytest.mark.parametrize('primary_type', [KeyboardInterrupt, SystemExit])
def test_review_i2_primary_baseexception_retained_through_all_cleanup_stops(monkeypatch, primary_type):
    owner, parent = _mock_builder(monkeypatch)
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    primary = primary_type(CANARY)
    counts = dict(write=0, abort=0, owner_close=0, parent_close=0)
    def stop_write(*args):
        counts['write'] += 1
        raise primary
    def cleanup(name):
        def stop():
            counts[name] += 1
            raise KeyboardInterrupt(CANARY)
        return stop
    monkeypatch.setattr(owner, 'write_file', stop_write)
    monkeypatch.setattr(owner, 'abort', cleanup('abort'))
    monkeypatch.setattr(owner, 'close', cleanup('owner_close'))
    monkeypatch.setattr(parent, 'close', cleanup('parent_close'))
    with pytest.raises(primary_type) as caught:
        export._build_synthetic_bundle('opaque', 'synthetic', profile.profile_id, _rows(profile, 0),
            trusted_parent_ack=True)
    assert caught.value is primary
    assert counts == dict(write=1, abort=1, owner_close=1, parent_close=1)


@pytest.mark.parametrize('phase', ['publish', 'owner-close', 'parent-close'])
def test_review_i3_builder_deadline_after_publish_closes_is_uncertain(monkeypatch, phase):
    owner, parent = _mock_builder(monkeypatch)
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    now, parent_calls = [0], [0]
    monkeypatch.setattr(export.time, 'monotonic', lambda: now[0])
    original_parent_close = parent.close
    def parent_close():
        parent_calls[0] += 1
        original_parent_close()
        if phase == 'parent-close': now[0] = 2
    monkeypatch.setattr(parent, 'close', parent_close)
    if phase != 'parent-close':
        target, name = (owner, 'publish_marker' if phase == 'publish' else 'close')
        old = getattr(target, name)
        def delayed(*args):
            result = old(*args)
            now[0] = 2
            return result
        monkeypatch.setattr(target, name, delayed)
    with pytest.raises(export.SnapshotExportError) as caught:
        export._build_synthetic_bundle('opaque', 'synthetic', profile.profile_id, _rows(profile, 0),
            trusted_parent_ack=True, limits=replace(export.DEFAULT_LIMITS, max_wall_seconds=1))
    assert caught.value.code == 'snapshot_publish_outcome_uncertain'
    assert caught.value.__cause__ is caught.value.__context__ is None
    assert owner.publishes == owner.closes == parent_calls[0] == 1 and owner.aborts == 0
    assert 'manifest.json' in owner.data


def test_review_i4_default_32mib_record_preserves_over_2mib_wire_native():
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    table = profile.descriptor.tables[0]
    values = list(_values(profile, table))
    values[0] = '\x00' * 400000
    # Raw cell <1MiB/raw row <4MiB, while JSON escaping makes record >2MiB.
    record = codec.encode_row(values, allowed_tags=export._tags(profile, table))
    assert 2 << 20 < len(record) <= 32 << 20
    rows = _rows(profile, 0)
    rows[table.name] = (tuple(values),)
    parent, basename = os.environ['B6_BUNDLE_PARENT'], 'record32-' + uuid.uuid4().hex
    built = export._build_synthetic_bundle(parent, basename, profile.profile_id, rows, trusted_parent_ack=True)
    report = export.validate_export(str(Path(parent)/basename/'manifest.json'), trusted_parent_ack=True)
    assert built.published and report.accepted and report.row_count == 1
    assert export.DEFAULT_LIMITS.files.max_metadata_bytes == 2 << 20


def test_review_i4_tight_record_limit_remains_effective(monkeypatch):
    profile = SOURCE_PROFILES['legacy_sqlite9_v1']
    table = profile.descriptor.tables[0]
    values = list(_values(profile, table))
    values[0] = '\x00' * 400000
    rows = _rows(profile, 0)
    rows[table.name] = (tuple(values),)
    limits = replace(export.DEFAULT_LIMITS, files=replace(export.DEFAULT_LIMITS.files, max_record_bytes=2 << 20))
    with pytest.raises(export.SnapshotExportError) as caught:
        _build(monkeypatch, rows=rows, limits=limits)
    assert caught.value.code == 'snapshot_resource_limit'
