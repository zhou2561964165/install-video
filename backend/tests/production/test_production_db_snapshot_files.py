"""Synthetic-only E1b: native Windows oracle; no DB/app/codec fixtures."""
import ctypes as c
from ctypes import wintypes as w
from dataclasses import replace
from dataclasses import FrozenInstanceError
import hashlib
import importlib
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import uuid

import pytest


@pytest.fixture
def m():
    # Collection remains possible during the initial RED: assert missing feature.
    assert importlib.util.find_spec('tools.production_db_snapshot_files') is not None
    return importlib.import_module('tools.production_db_snapshot_files')


@pytest.fixture
def base(request):
    return Path(request.config.option.basetemp).parent


def rejected(m, call, code=None):
    got = None
    try:
        call()
    except m.SnapshotFileError as e:
        got = e
    assert got is not None
    assert got.__cause__ is None and got.__context__ is None
    assert str(got) == got.code
    if code:
        assert got.code == code
    return got


def oracle(path):
    """Independent native descriptor oracle, reads owner/DACL via named API."""
    a, k = c.WinDLL('advapi32', use_last_error=True), c.WinDLL('kernel32', use_last_error=True)
    query = a.GetNamedSecurityInfoW
    query.argtypes = [w.LPWSTR, c.c_int, w.DWORD, c.POINTER(w.LPVOID), w.LPVOID,
                     c.POINTER(w.LPVOID), w.LPVOID, c.POINTER(w.LPVOID)]
    query.restype = w.DWORD
    owner, acl, sd = w.LPVOID(), w.LPVOID(), w.LPVOID()
    assert query(str(path), 1, 5, c.byref(owner), None, c.byref(acl), None, c.byref(sd)) == 0
    conv = a.ConvertSecurityDescriptorToStringSecurityDescriptorW
    conv.argtypes = [w.LPVOID, w.DWORD, w.DWORD, c.POINTER(w.LPWSTR), w.LPVOID]
    conv.restype = w.BOOL
    free = k.LocalFree
    free.argtypes, free.restype = [w.LPVOID], w.LPVOID
    out = w.LPWSTR()
    try:
        assert conv(sd, 1, 5, c.byref(out), None)
        text = out.value
        # Query raw control separately instead of relying only on SDDL ordering.
        ctl, rev = w.WORD(), w.DWORD()
        control = a.GetSecurityDescriptorControl
        control.argtypes, control.restype = [w.LPVOID, c.POINTER(w.WORD), c.POINTER(w.DWORD)], w.BOOL
        assert control(sd, c.byref(ctl), c.byref(rev))
        assert ctl.value & 0x1000 and ctl.value & 4
        assert acl.value and owner.value
        assert 'D:P' in text and '(A;;FA;;;SY)' in text
        assert text.count('(A;') == 2 and 'ID;' not in text
        return True
    finally:
        if out:
            free(c.cast(out, w.LPVOID))
        free(sd)


@pytest.fixture
def parent(m, base):
    with m.open_trusted_parent(str(base), trusted_parent_ack=True) as p:
        yield p


def fresh():
    return 'case-' + uuid.uuid4().hex


def test_module_available_without_import_sideeffects():
    assert importlib.util.find_spec('tools.production_db_snapshot_files') is not None


def test_import_has_no_app_db_or_network(m):
    assert not any(n == 'app' or n.startswith('app.') for n in sys.modules)
    assert 'sqlalchemy' not in sys.modules
    assert 'tools.production_db_snapshot_format' not in sys.modules
    for call in (lambda: socket.socket().connect(('127.0.0.1', 1)),
                 lambda: socket.getaddrinfo('example.invalid', 80)):
        with pytest.raises(RuntimeError, match='network_forbidden'):
            call()


@pytest.mark.parametrize('path', ['relative', 'C:relative', '\\\\server\\share',
    '\\\\?\\C:\\x', '\\\\.\\NUL', 'C:\\x:secret', 'C:\\a\\..\\b',
    'C:\\a\\CON.txt', 'C:\\a\\x.', 'C:\\a\\x ', 'https://example.invalid',
    'C:/mixed', 'C:\\a\x00b', 'C:\\a\\COM¹', 'C:\\a\\x~1'])
def test_reject_nonlocal_and_ambiguous_paths_before_open(m, path, monkeypatch):
    monkeypatch.setattr(os, 'open', lambda *a, **k: pytest.fail('unexpected_os_open'))
    rejected(m, lambda: m.open_trusted_parent(path, trusted_parent_ack=True), 'snapshot_path_invalid')


def test_limits_frozen_and_call_binding_safe(m):
    for call in (lambda: m.FileLimits(max_files=True), lambda: m.FileLimits(1),
                 lambda: m.FileLimits(extra=1), lambda: m.open_trusted_parent(),
                 lambda: m.open_trusted_parent('x', path='y', trusted_parent_ack=True),
                 lambda: m.OwnedDirectory(), lambda: m.TrustedParent()):
        try:
            raise RuntimeError('B6_FILES_SYNTHETIC_PRIVATE')
        except RuntimeError:
            rejected(m, call)
    with pytest.raises(FrozenInstanceError):
        m.DEFAULT_FILE_LIMITS.max_files = 2


@pytest.mark.parametrize('part', ['CLOCK$', 'CONIN$', 'CONOUT$', 'x?', 'x*', 'x|', 'x<', 'x>', 'x"', 'x\x7f'])
def test_additional_windows_aliases_rejected_before_metadata(m, monkeypatch, part):
    monkeypatch.setattr(os, 'lstat', lambda *a, **k: pytest.fail('unexpected_metadata_read'))
    rejected(m, lambda: m.open_trusted_parent('C:\\' + part, trusted_parent_ack=True), 'snapshot_path_invalid')


def test_network_drive_refused_before_lstat(m, monkeypatch):
    original = m._Windows.__init__
    def initialize(self):
        original(self)
        self.drive_type = lambda path: 4
    monkeypatch.setattr(m._Windows, '__init__', initialize)
    monkeypatch.setattr(os, 'lstat', lambda *a, **k: pytest.fail('network_metadata_attempt'))
    rejected(m, lambda: m.open_trusted_parent('Z:\\candidate', trusted_parent_ack=True), 'filesystem_security_unsupported')


def test_parent_permissions_checked_never_changed(m, parent, base):
    assert oracle(base)
    rejected(m, lambda: m.open_trusted_parent(str(base), trusted_parent_ack=False))
    assert oracle(base)


def test_permission_is_private_before_first_payload_byte(m, parent, base, monkeypatch):
    name = fresh()
    actual = os.write
    checked = []
    def checked_write(fd, data):
        assert oracle(base / name)
        assert oracle(base / name / 'schema.json')
        checked.append(True)
        return actual(fd, data)
    monkeypatch.setattr(os, 'write', checked_write)
    monkeypatch.setattr(os, 'chmod', lambda *a, **k: pytest.fail('windows_chmod_used'))
    with m.reserve_directory(parent, name) as d:
        digest = d.write_file('schema.json', [b'B6_FILES_SYNTHETIC_PRIVATE'])
        assert digest.byte_count == 26
    assert checked and not (base / name).exists()


def test_create_new_collision_preserves_existing_bytes(m, parent, base):
    name = fresh()
    with m.reserve_directory(parent, name) as d:
        d.write_file('schema.json', [b'original'])
        rejected(m, lambda: d.write_file('schema.json', [b'replacement']))
        rejected(m, lambda: m.reserve_directory(parent, name), 'snapshot_destination_exists')
        assert (base / name / 'schema.json').read_bytes() == b'original'


def test_bounded_and_chunk_reads_have_distinct_limits(m, parent):
    with m.reserve_directory(parent, fresh()) as d:
        payload = b'a' * 65536
        d.write_file('t00-000000.jsonl', [payload] * 40)
        with d.open_owned('t00-000000.jsonl') as r:
            h, count = hashlib.sha256(), 0
            while True:
                block = r.read_chunk(65536)
                if not block:
                    break
                assert len(block) <= 65536
                h.update(block)
                count += len(block)
            assert count == 2621440 and h.digest() == hashlib.sha256(payload * 40).digest()
        d.write_file('schema.json', [b'abc\ndef\n'])
        with d.open_owned('schema.json') as r:
            assert r.readline(4) == b'abc\n'
            assert r.read_bounded(4) == b'def\n'
        with d.open_owned('schema.json') as r:
            rejected(m, lambda: r.read_bounded(7), 'snapshot_resource_limit')


def test_limits_empty_chunks_and_short_write(m, parent, monkeypatch):
    with m.reserve_directory(parent, fresh(), limits=m.FileLimits(max_total_bytes=5)) as d:
        rejected(m, lambda: d.write_file('schema.json', [b'']), 'snapshot_file_invalid')
    with m.reserve_directory(parent, fresh(), limits=m.FileLimits(max_total_bytes=5)) as d:
        actual = os.write
        monkeypatch.setattr(os, 'write', lambda fd, data: actual(fd, data[:1]))
        assert d.write_file('schema.json', [b'abcde']).byte_count == 5
        rejected(m, lambda: d.write_file('t00-000000.jsonl', [b'x']), 'snapshot_resource_limit')


def test_failed_stream_query_closes_new_reader_fd(m, parent, monkeypatch):
    import msvcrt
    with m.reserve_directory(parent, fresh()) as d:
        d.write_file('schema.json', [b'x'])
        opened = []
        actual = msvcrt.open_osfhandle
        def tracking(*args):
            fd = actual(*args)
            opened.append(fd)
            return fd
        with monkeypatch.context() as fault:
            fault.setattr(msvcrt, 'open_osfhandle', tracking)
            streams = d._os.streams
            def failed_file_stream(path, directory):
                if directory:
                    return streams(path, directory)
                raise OSError('synthetic')
            fault.setattr(d._os, 'streams', failed_file_stream)
            rejected(m, lambda: d.open_owned('schema.json'))
        assert len(opened) == 1
        try:
            with pytest.raises(OSError):
                os.fstat(opened[0])
        finally:
            try:
                os.close(opened[0])
            except OSError:
                pass


def test_baseexception_from_writer_not_replaced_by_close_fault(m, parent, monkeypatch):
    d = m.reserve_directory(parent, fresh())
    actual, fired = os.close, []
    def failing_close(fd):
        actual(fd)
        if not fired:
            fired.append(True)
            raise OSError('synthetic')
    def interrupted():
        yield b'x'
        raise KeyboardInterrupt()
    monkeypatch.setattr(os, 'close', failing_close)
    with pytest.raises(KeyboardInterrupt):
        d.write_file('schema.json', interrupted())
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()


def test_failed_writer_close_prevents_later_publication(m, parent, base, monkeypatch):
    name = fresh()
    d = m.reserve_directory(parent, name)
    actual = os.close
    def failed_close(fd):
        actual(fd)
        raise OSError('synthetic')
    with monkeypatch.context() as fault:
        fault.setattr(os, 'close', failed_close)
        rejected(m, lambda: d.write_file('schema.json', [b'x']), 'snapshot_io_failed')
    rejected(m, lambda: d.publish_marker(b'x'), 'snapshot_inactive')
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()
    assert (base / name / 'schema.json').exists()


@pytest.mark.parametrize('fault', ['open_osfhandle', 'set_inheritable'])
def test_acquisition_failure_is_tracked_and_blocks_publish(m, parent, base, monkeypatch, fault):
    import msvcrt
    name = fresh()
    d = m.reserve_directory(parent, name)
    target = msvcrt if fault == 'open_osfhandle' else os
    with monkeypatch.context() as inject:
        inject.setattr(target, fault, lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic_acquisition')))
        rejected(m, lambda: d.write_file('schema.json', [b'x']), 'snapshot_io_failed')
    assert (base / name / 'schema.json').is_file()
    assert 'schema.json' in d._journal and d._journal['schema.json'] is None
    assert d._failed
    rejected(m, lambda: d.publish_marker(b'x'), 'snapshot_inactive')
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()
    assert not (base / name / 'manifest.json').exists()


def test_postlink_same_baseexception_preserves_all_published_files(m, parent, base, monkeypatch):
    name = fresh()
    d = m.reserve_directory(parent, name)
    interrupted = KeyboardInterrupt()
    actual = os.link
    def link_then_interrupt(*args, **kwargs):
        actual(*args, **kwargs)
        raise interrupted
    caught = None
    try:
        with d:
            d.write_file('schema.json', [b'synthetic'])
            with monkeypatch.context() as inject:
                inject.setattr(os, 'link', link_then_interrupt)
                d.publish_marker(b'marker')
    except KeyboardInterrupt as error:
        caught = error
    assert caught is interrupted
    assert d._published and not d._active
    assert (base / name / 'schema.json').read_bytes() == b'synthetic'
    assert (base / name / 'manifest.json').read_bytes() == b'marker'
    assert (base / name / '.manifest.part').read_bytes() == b'marker'


def test_acquisition_collision_never_claims_existing_object(m, parent, base):
    name = fresh()
    d = m.reserve_directory(parent, name)
    original = base / name / 'schema.json'
    original.write_bytes(b'foreign')
    rejected(m, lambda: d.write_file('schema.json', [b'replacement']), 'snapshot_destination_exists')
    assert not d._journal
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()
    assert original.read_bytes() == b'foreign'


def test_acquisition_baseexception_preserved_with_unknown_object(m, parent, base, monkeypatch):
    name = fresh()
    d = m.reserve_directory(parent, name)
    interrupted = KeyboardInterrupt()
    def interrupt(*args, **kwargs):
        raise interrupted
    caught = None
    try:
        with d:
            with monkeypatch.context() as inject:
                inject.setattr(os, 'set_inheritable', interrupt)
                d.write_file('schema.json', [b'x'])
    except KeyboardInterrupt as error:
        caught = error
    assert caught is interrupted and not d._active
    assert d._journal == {'schema.json': None} and d._failed
    assert (base / name / 'schema.json').exists()
    assert not (base / name / 'manifest.json').exists()


def test_postlink_unprovable_outcome_preserves_all_files(m, parent, base, monkeypatch):
    name = fresh()
    d = m.reserve_directory(parent, name)
    interrupted = KeyboardInterrupt()
    actual = os.link
    def link_then_interrupt(*args, **kwargs):
        actual(*args, **kwargs)
        monkeypatch.setattr(d._os, 'file_info', lambda *a: (_ for _ in ()).throw(OSError('synthetic_metadata')))
        raise interrupted
    caught = None
    try:
        with d:
            d.write_file('schema.json', [b'synthetic'])
            with monkeypatch.context() as inject:
                inject.setattr(os, 'link', link_then_interrupt)
                d.publish_marker(b'marker')
    except KeyboardInterrupt as error:
        caught = error
    assert caught is interrupted and not d._active
    assert d._commit_uncertain and not d._published
    assert (base / name / 'schema.json').read_bytes() == b'synthetic'
    assert (base / name / 'manifest.json').read_bytes() == b'marker'
    assert (base / name / '.manifest.part').read_bytes() == b'marker'


def test_growth_and_identity_change_rejected(m, parent, monkeypatch):
    with m.reserve_directory(parent, fresh()) as d:
        d.write_file('schema.json', [b'abc'])
        with d.open_owned('schema.json') as r:
            original = d._os.file_info
            def changed(fd):
                info = original(fd)
                return replace(info, size=info.size + 1) if fd == r._fd else info
            with monkeypatch.context() as fault:
                fault.setattr(d._os, 'file_info', changed)
                rejected(m, lambda: r.read_chunk(1), 'snapshot_identity_changed')


def test_unknown_file_identity_is_retained(m, parent, base, monkeypatch):
    name = fresh()
    d = m.reserve_directory(parent, name)
    with monkeypatch.context() as fault:
        fault.setattr(d._os, 'file_info', lambda *a: (_ for _ in ()).throw(OSError('synthetic')))
        rejected(m, lambda: d.write_file('schema.json', [b'x']))
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()
    assert (base / name / 'schema.json').exists()
    assert oracle(base / name / 'schema.json')


@pytest.mark.parametrize('stage', ['write', 'fsync'])
def test_prepublication_io_fault_leaves_no_marker(m, parent, base, monkeypatch, stage):
    name = fresh()
    with m.reserve_directory(parent, name) as d:
        with monkeypatch.context() as fault:
            fault.setattr(os, stage, lambda *a: (_ for _ in ()).throw(OSError('B6_FILES_SYNTHETIC_PRIVATE')))
            rejected(m, lambda: d.publish_marker(b'x'), 'snapshot_io_failed')
        assert not (base / name / 'manifest.json').exists()


def test_native_named_stream_and_hardlink_are_rejected(m, parent, base):
    name = fresh()
    d = m.reserve_directory(parent, name)
    d.write_file('schema.json', [b'x'])
    file = base / name / 'schema.json'
    with open(str(file) + ':synthetic', 'wb') as stream:
        stream.write(b'synthetic')
    rejected(m, lambda: d.open_owned('schema.json'), 'snapshot_file_invalid')
    d.close()


def test_native_junction_rejected_before_stream_enumeration(m, parent, base, monkeypatch):
    target_name, junction_name = fresh(), fresh()
    target = m.reserve_directory(parent, target_name)
    target.close()
    path = str(base / junction_name)
    adapter = parent._os
    adapter.mkdir(path, parent._chain[-1][1], junction_name)
    handle = adapter.create(path, 0x40000000, 0, None, 3, 0x02200000, None)
    assert handle != c.c_void_p(-1).value
    ioctl = adapter.k.DeviceIoControl
    ioctl.argtypes = [w.HANDLE, w.DWORD, w.LPVOID, w.DWORD, w.LPVOID, w.DWORD, c.POINTER(w.DWORD), w.LPVOID]
    ioctl.restype = w.BOOL
    substitute = ('\\??\\' + str(base / target_name)).encode('utf-16-le')
    printable = str(base / target_name).encode('utf-16-le')
    paths = substitute + b'\0\0' + printable + b'\0\0'
    data = struct.pack('<IHHHHHH', 0xA0000003, 8 + len(paths), 0, 0, len(substitute), len(substitute) + 2, len(printable)) + paths
    buffer = c.create_string_buffer(data)
    done = w.DWORD()
    try:
        assert ioctl(handle, 0x900A4, buffer, len(data), None, 0, c.byref(done), None)
    finally:
        adapter.close_handle(handle)
    # Calling a path-based stream enumeration on this junction would follow it.
    with monkeypatch.context() as fault:
        fault.setattr(adapter, 'streams', lambda *a: pytest.fail('stream_on_reparse'))
        rejected(m, lambda: m.open_directory(parent, junction_name), 'snapshot_file_invalid')
    rejected(m, lambda: m.open_trusted_parent(path, trusted_parent_ack=True), 'snapshot_path_invalid')


def test_child_hard_exit_preserves_restricted_incomplete_directory(m, parent, base):
    name = fresh()
    code = '''import os,sys
from tools.production_db_snapshot_files import open_trusted_parent,reserve_directory
with open_trusted_parent(sys.argv[1],trusted_parent_ack=True) as parent:
    with reserve_directory(parent,sys.argv[2]) as directory:
        directory.write_file('schema.json',[b'synthetic'])
        os._exit(73)
'''
    result = subprocess.run([sys.executable, '-B', '-c', code, str(base), name],
        env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 73
    assert not (base / name / 'manifest.json').exists()
    assert oracle(base / name) and oracle(base / name / 'schema.json')


def test_reentrant_iterator_cannot_publish_or_abort_active_writer(m, parent, base):
    name = fresh()
    with m.reserve_directory(parent, name) as d:
        def blocks():
            rejected(m, lambda: d.publish_marker(b'x'), 'snapshot_inactive')
            rejected(m, d.abort, 'snapshot_cleanup_failed')
            yield b'x'
        d.write_file('schema.json', blocks())
        assert not (base / name / 'manifest.json').exists()


def test_reader_limits_and_operation_binding_errors_are_fixed(m, parent):
    with m.reserve_directory(parent, fresh()) as d:
        d.write_file('schema.json', [b'12345\n'])
        with d.open_owned('schema.json') as reader:
            for call in (lambda: reader.read_chunk(True), lambda: reader.read_chunk(65537),
                         lambda: reader.read_chunk(), lambda: reader.read_chunk(1, 2),
                         lambda: reader.read_bounded(0), lambda: reader.readline(max_bytes=3),
                         lambda: d.write_file(name='x', unknown='synthetic'),
                         lambda: d.publish_marker(b'x', unknown=True)):
                rejected(m, call)
            rejected(m, lambda: reader.readline(5), 'snapshot_resource_limit')


def test_read_directory_detects_replacement_between_lstat_and_open(m, parent, base, monkeypatch):
    first, second = fresh(), fresh()
    left, right = m.reserve_directory(parent, first), m.reserve_directory(parent, second)
    left.write_file('schema.json', [b'original'])
    right.write_file('schema.json', [b'replacement'])
    left.publish_marker(b'marker')
    left.close()
    right.close()
    with m.open_directory(parent, first) as reader:
        actual = reader._os.read_file
        changed = []
        def replace_before_open(path, handle, name):
            if name == 'schema.json' and not changed:
                changed.append(True)
                os.replace(base / second / 'schema.json', base / first / 'schema.json')
            return actual(path, handle, name)
        with monkeypatch.context() as fault:
            fault.setattr(reader._os, 'read_file', replace_before_open)
            rejected(m, lambda: reader.open_file('schema.json'), 'snapshot_identity_changed')


def test_file_metadata_and_count_limits_are_prewrite(m, parent):
    with m.reserve_directory(parent, fresh(), limits=m.FileLimits(max_metadata_bytes=2)) as d:
        rejected(m, lambda: d.write_file('schema.json', [b'abc']), 'snapshot_resource_limit')
    with m.reserve_directory(parent, fresh(), limits=m.FileLimits(max_files=1)) as d:
        rejected(m, lambda: d.write_file('schema.json', []), 'snapshot_resource_limit')
    with m.reserve_directory(parent, fresh(), limits=m.FileLimits(max_file_bytes=2)) as d:
        rejected(m, lambda: d.write_file('t00-000000.jsonl', [b'abc']), 'snapshot_resource_limit')


def test_native_hardlink_is_rejected_and_preserved(m, parent, base):
    name = fresh()
    d = m.reserve_directory(parent, name)
    d.write_file('schema.json', [b'x'])
    os.link(base / name / 'schema.json', base / name / 't00-000000.jsonl')
    rejected(m, lambda: d.open_owned('schema.json'), 'snapshot_file_invalid')
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()


@pytest.mark.parametrize('bad', ['../x', 'x/y', 'SCHEMA.JSON', '.manifest.part', 'manifest.json',
                                   't0-1.jsonl', 'NUL', 'x:stream', '\\server', '未知'])
def test_fixed_flat_names(m, parent, bad):
    with m.reserve_directory(parent, fresh()) as d:
        rejected(m, lambda: d.write_file(bad, [b'x']), 'snapshot_name_invalid')


def test_empty_file_and_marker_publish_native_identity_acl(m, parent, base):
    name = fresh()
    with m.reserve_directory(parent, name) as d:
        assert d.write_file('t00-000000.jsonl', []).byte_count == 0
        result = d.publish_marker(b'synthetic-marker')
        assert result.published and result.status == 'published'
        assert result.cleanup_complete and result.directory_synced is None
        assert oracle(base / name / 'manifest.json')
        assert (base / name / 'manifest.json').stat().st_nlink == 1
    with m.open_directory(parent, name) as d:
        assert d.file_names() == ('manifest.json', 't00-000000.jsonl')
        with d.open_file('manifest.json') as r:
            assert r.read_bounded(100) == b'synthetic-marker'


def test_no_fallback_when_link_unsupported(m, parent, base, monkeypatch):
    name = fresh()
    with m.reserve_directory(parent, name) as d:
        monkeypatch.setattr(os, 'link', lambda *a, **k: (_ for _ in ()).throw(OSError('B6_FILES_SYNTHETIC_PRIVATE')))
        rejected(m, lambda: d.publish_marker(b'x'), 'snapshot_io_failed')
        assert not (base / name / 'manifest.json').exists()


def test_part_unlink_failure_preserves_published_final(m, parent, base, monkeypatch):
    name = fresh()
    unlink = os.unlink
    def fail_part(path, *a, **k):
        if str(path).endswith('.manifest.part'):
            raise PermissionError('B6_FILES_SYNTHETIC_PRIVATE')
        return unlink(path, *a, **k)
    with m.reserve_directory(parent, name) as d:
        monkeypatch.setattr(os, 'unlink', fail_part)
        result = d.publish_marker(b'x')
        assert result.published and result.status == 'published_cleanup_pending'
        assert not result.cleanup_complete and 'part_cleanup_failed' in result.codes
        rejected(m, d.abort)
    assert (base / name / 'manifest.json').exists()
    assert (base / name / '.manifest.part').exists()


@pytest.mark.parametrize('unlink_fault', [False, True])
def test_directory_sync_failure_is_distinct_from_cleanup(m, parent, base, monkeypatch, unlink_fault):
    name = fresh()
    with m.reserve_directory(parent, name) as d:
        monkeypatch.setattr(d._os, 'sync_directory', lambda *a: (_ for _ in ()).throw(OSError('synthetic')))
        if unlink_fault:
            monkeypatch.setattr(d, '_unlink', lambda *a: (_ for _ in ()).throw(OSError('synthetic')))
        result = d.publish_marker(b'x')
        assert result.published and result.directory_synced is False
        assert result.cleanup_complete is not unlink_fault
        assert result.status == ('published_cleanup_pending' if unlink_fault else 'published_durability_pending')
        assert 'directory_sync_failed' in result.codes
        assert ('part_cleanup_failed' in result.codes) is unlink_fault
    assert (base / name / 'manifest.json').exists()


def test_final_name_collision_never_overwrites(m, parent, base):
    name = fresh()
    d = m.reserve_directory(parent, name)
    (base / name / 'manifest.json').write_bytes(b'original')
    rejected(m, lambda: d.publish_marker(b'new'))
    assert (base / name / 'manifest.json').read_bytes() == b'original'
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()


def test_postlink_identity_fault_preserves_published_fact(m, parent, base, monkeypatch):
    name = fresh()
    with m.reserve_directory(parent, name) as d:
        actual = os.link
        def link_then_break(*args, **kwargs):
            actual(*args, **kwargs)
            monkeypatch.setattr(d._os, 'file_info', lambda *a: (_ for _ in ()).throw(OSError('synthetic')))
        monkeypatch.setattr(os, 'link', link_then_break)
        result = d.publish_marker(b'x')
        assert result.published and not result.cleanup_complete
        assert 'published_identity_check_failed' in result.codes
    assert (base / name / 'manifest.json').exists()


def test_foreign_entry_and_identity_replacement_preserved(m, parent, base):
    name = fresh()
    d = m.reserve_directory(parent, name)
    d.write_file('schema.json', [b'x'])
    original = base / name / 'schema.json'
    original.rename(base / name / 'foreign')
    original.write_bytes(b'foreign-replacement')
    rejected(m, d.abort, 'snapshot_cleanup_failed')
    d.close()
    assert original.read_bytes() == b'foreign-replacement'
    assert (base / name / 'foreign').read_bytes() == b'x'


def test_body_baseexception_survives_cleanup_error(m, parent, base):
    name = fresh()
    with pytest.raises(KeyboardInterrupt):
        with m.reserve_directory(parent, name):
            (base / name / 'foreign').write_bytes(b'synthetic')
            raise KeyboardInterrupt()
    name = fresh()
    def body():
        with m.reserve_directory(parent, name):
            (base / name / 'foreign').write_bytes(b'synthetic')
            raise ValueError('B6_FILES_SYNTHETIC_PRIVATE')
    rejected(m, body, 'snapshot_cleanup_failed')


def test_thread_and_closed_capabilities_fail(m, parent):
    d = m.reserve_directory(parent, fresh())
    errors = []
    def other():
        errors.append(rejected(m, lambda: d.write_file('schema.json', []), 'snapshot_owner_mismatch').code)
    t = threading.Thread(target=other)
    t.start()
    t.join()
    assert errors == ['snapshot_owner_mismatch']
    d.abort()
    d.close()
    rejected(m, lambda: d.write_file('schema.json', []), 'snapshot_inactive')


@pytest.mark.skipif(os.name != 'posix', reason='Linux native permissions/fstatfs require separate local Linux window')
def test_linux_native_modes_and_no_global_umask(m, parent, base, monkeypatch):
    assert sys.platform == 'linux'
    before = base.stat()
    monkeypatch.setattr(os, 'umask', lambda *a: pytest.fail('global_umask_called'))
    with m.reserve_directory(parent, fresh()) as d:
        assert os.fstat(d._handle).st_mode & 0o7777 == 0o700
        d.write_file('schema.json', [b'synthetic'])
        with d.open_owned('schema.json') as r:
            assert os.fstat(r._fd).st_mode & 0o7777 == 0o600
            assert r.read_bounded(100) == b'synthetic'
    after = base.stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (before.st_uid, before.st_gid, before.st_mode)

