"""U5a single native HTTP file: synthetic wire, real director/HTTPX/HttpFD."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.downloader.http import HttpFD
from yt_dlp.networking.common import _REQUEST_HANDLERS
from yt_dlp import globals as yt_globals

from app.services import ytdlp_service as service
from app.services.outbound_budget import BudgetLimits, OutboundBudget, OutboundBudgetGroup
from app.services.outbound_policy import OutboundError, OutboundPurpose
from app.services.outbound_httpx import ControlledHttpStatusError
from app.services.source_network import SourceNetworkContext, make_runtime_source_network
from test_outbound_httpx import transport_network
from test_ytdlp_guard_director import context, guarded, reply, safe


BODY = bytes(range(256)) * 260  # 66560 bytes, crosses the fixed 65536-byte read
MEDIA = 'http://other.example/media?sig=synthetic-secret'


def info(**changes):
    return dict(url=MEDIA, protocol='http', id='unit', title='unit', ext='bin', **changes)


def owned(tmp_path):
    result = tmp_path / 'owned'
    result.mkdir()
    return result


def bridge_set(ydl):
    return next(iter(ydl._request_director.handlers.values()))._responses


def sends(wire):
    # httpcore emits separate empty body/end writes; these are not GET sends.
    return sum(part.startswith(b'GET ') for part in wire.writes)


class FixtureIE(InfoExtractor):
    _VALID_URL = r'http://public\.example/(?P<id>unit)'

    def _real_extract(self, url):
        return self._download_json(url, self._match_id(url))


def metadata(ydl, wire, data=None):
    raw = json.dumps(data or info()).encode()
    wire.replies.append(reply(raw))
    ydl.add_info_extractor(FixtureIE())
    result = ydl.extract_info('http://public.example/unit', ie_key=FixtureIE.ie_key())
    assert result['webpage_url'] == 'http://public.example/unit'
    return result, len(raw)


def assert_empty(directory):
    assert directory.is_dir() and list(directory.iterdir()) == []


def test_real_get_metadata_to_native_httpfd_owned_file(transport_network, tmp_path):
    before_env, before_handlers = dict(os.environ), dict(_REQUEST_HANDLERS)
    before_plugins = (dict(yt_globals.plugin_ies.value), dict(yt_globals.plugin_pps.value))
    directory, network = owned(tmp_path), context()
    with guarded(network, identity_only=True, max_bytes=100000) as ydl:
        extracted, size = metadata(ydl, transport_network)
        transport_network.replies.append(reply(BODY))
        with ydl._download_http_file(extracted, target_dir=directory) as path:
            assert type(path) is type(directory) and path == directory / 'media.bin'
            assert path.read_bytes() == BODY
            assert not bridge_set(ydl) and transport_network.closed == 2
        assert_empty(directory)
        saved = network.budget.snapshot()
        assert (saved.requests, saved.redirects, saved.raw_bytes, saved.decoded_bytes) == (2, 0, size + len(BODY), size + len(BODY))
    assert dict(os.environ) == before_env and _REQUEST_HANDLERS == before_handlers
    assert before_plugins == (yt_globals.plugin_ies.value, yt_globals.plugin_pps.value)


@pytest.mark.parametrize('use_group', [False, True])
def test_unrelated_public_hosts_redirect_and_group_charge_once(use_group, transport_network, tmp_path):
    root = OutboundBudget(BudgetLimits(seconds=100, requests=8, children=1))
    child = root.child(BudgetLimits(seconds=100, requests=8)) if use_group else None
    budget = OutboundBudgetGroup((root, child, root)) if use_group else root
    network = SourceNetworkContext(context().channel, budget)
    directory = owned(tmp_path)
    data = info(formats=[{'url': 'http://unused.example/f', 'protocol': 'http'}],
                subtitles={'en': [{'url': 'http://subs.example/s', 'name': 'English'}]})
    with guarded(network, identity_only=True, max_bytes=100000) as ydl:
        extracted, size = metadata(ydl, transport_network, data)
        transport_network.replies.extend([reply(b'', status=b'302 Found', headers=b'Location: http://cdn.example/final\r\n'), reply(BODY)])
        with ydl._download_http_file(extracted, target_dir=directory) as path:
            assert path.read_bytes() == BODY
        for node in [root] + ([child] if child else []):
            saved = node.snapshot()
            assert (saved.requests, saved.redirects, saved.raw_bytes, saved.decoded_bytes) == (3, 1, size + len(BODY), size + len(BODY))
        wire = b''.join(transport_network.writes)
        assert b'Host: other.example' in wire and b'Host: cdn.example' in wire
        assert b'unused.example' not in wire and b'subs.example' not in wire
    assert_empty(directory)


def invalid_cases():
    for url in ['http://127.0.0.1/x', 'http://169.254.169.254/x', 'http://u:p@public.example/x', 'ftp://public.example/x']:
        yield info() | {'url': url}
    for protocol in [None, 'HTTP', 'ftp', 'm3u8_native', 'https']:
        yield info() | {'protocol': protocol}
    missing = info(); del missing['protocol']; yield missing
    for key in ['request_data', 'requested_formats', 'requested_downloads', 'manifest_url', 'fragment_base_url',
                'fragments', 'section_start', 'section_end', 'is_live', 'live_status', 'impersonate',
                'downloader_options', 'available_at', 'unknown']:
        yield info() | {key: None}
    yield info(formats=[{'url': MEDIA, 'unknown': {}}])
    yield info(formats=[{'url': MEDIA, 'name': 'forbidden-format-name'}])
    yield info(subtitles={'en': [{'url': 'http://127.0.0.1/sub'}]})
    yield info(formats=[{'url': MEDIA, 'protocol': 'https'}])
    yield info(formats=(x for x in []))
    yield info() | {'title': b'bytes'}
    yield info() | {'title': 'x' * 8193}
    yield info() | {'title': 'é' * 4097}
    yield info(formats=[{'url': MEDIA}] * 2)
    yield info(formats=[{'url': MEDIA, 'title': 'x' * 8000} for _ in range(9)])
    yield info(formats=[{'url': MEDIA} for _ in range(90)])
    loop = []; loop.append(loop); yield info(formats=loop)
    deep = []; cursor = deep
    for _ in range(9):
        nested = []; cursor.append(nested); cursor = nested
    yield info(formats=deep)
    class Custom(dict): pass
    yield Custom(info())
    yield info(formats=[{'url': MEDIA, 'title': object()}])


@pytest.mark.parametrize('bad', list(invalid_cases()))
def test_derived_rejection_before_media_io(bad, transport_network, tmp_path, caplog):
    directory = owned(tmp_path)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        metadata(ydl, transport_network)
        sends = len(transport_network.writes)
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(bad, target_dir=directory):
                pytest.fail('invalid graph yielded')
        safe(error.value)
        assert len(transport_network.writes) == sends
        assert_empty(directory)
    assert 'synthetic-secret' not in caplog.text


def test_headers_are_bounded_copied_and_credentials_stripped(transport_network, tmp_path):
    headers = {'Cookie': 'synthetic-secret', 'AUTHORIZATION': 'synthetic-secret', 'Proxy-Authorization': 'synthetic-secret',
               'User-Agent': 'safe-agent', 'Referer': 'http://public.example/base', 'Accept': 'video/*'}
    data = info(http_headers=headers, formats=[{'url': MEDIA, 'http_headers': dict(headers)}],
                automatic_captions={'en': [{'url': 'http://subs.example/s', 'http_headers': dict(headers)}]})
    original = copy.deepcopy(data)
    directory = owned(tmp_path)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        clean = service._validate_derived_info(data, ydl._u4_state)
        assert clean['http_headers'] == {'User-Agent': 'safe-agent', 'Referer': 'http://public.example/base', 'Accept': 'video/*'}
        assert set(clean) == {'url', 'protocol', 'id', 'title', 'ext', 'http_headers'}
        transport_network.replies.append(reply(BODY, headers=b'Set-Cookie: synthetic-secret=value\r\n'))
        with ydl._download_http_file(data, target_dir=directory) as path:
            assert path.read_bytes() == BODY
        assert data == original
        wire = b''.join(transport_network.writes)
        # Signed URL is internal; only secret credential header values must disappear.
        assert b'Cookie:' not in wire and b'Authorization:' not in wire
        assert b'user-agent: safe-agent' in wire.lower() and b'accept-encoding: identity' in wire.lower()
        assert b'referer: http://public.example/base' in wire.lower() and b'accept: video/*' in wire.lower()
        assert not ydl.cookiejar
    assert_empty(directory)


@pytest.mark.parametrize('bad_headers', [
    [], {'User-Agent': 2}, {'User-Agent': 'ok', 'user-agent': 'duplicate'}, {'Accept': 'a\r\nsynthetic-secret'},
    {'Accept': '\x7f'}, {'X-Unknown': 'x'}, {'Host': 'public.example'}, {'Accept-Encoding': 'identity'},
    {'Proxy-Test': 'x'}, {'Referer': 'http://127.0.0.1/x'}, {'Accept': 'x' * 8193},
    {'Accept': 'a' * 8000, 'User-Agent': 'a' * 8000, 'Referer': 'http://public.example/' + 'x' * 1000},
])
@pytest.mark.parametrize('location', ['root', 'format', 'subtitle'])
def test_bad_headers_reject_every_leaf_before_send(bad_headers, location, transport_network, tmp_path):
    leaf = {'url': MEDIA, 'http_headers': bad_headers}
    data = info(http_headers=bad_headers) if location == 'root' else (
        info(formats=[leaf]) if location == 'format' else info(subtitles={'en': [leaf]}))
    directory = owned(tmp_path)
    with guarded(identity_only=True) as ydl:
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(data, target_dir=directory): pass
        safe(error.value)
    assert not transport_network.writes
    assert_empty(directory)


def test_native_params_and_real_tuple_contract(monkeypatch, transport_network, tmp_path):
    real = HttpFD.download
    seen = []
    def observe(fd, filename, data, subtitle=False):
        assert type(fd) is HttpFD
        seen.append(dict(fd.params))
        result = real(fd, filename, data, subtitle=subtitle)
        assert result == (True, True)
        return result
    monkeypatch.setattr(HttpFD, 'download', observe)
    transport_network.replies.append(reply(BODY))
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with ydl._download_http_file(info(), target_dir=owned(tmp_path)) as path:
            assert path.read_bytes() == BODY
    expected = dict(retries=0, fragment_retries=0, file_access_retries=0, continuedl=False,
                    nopart=False, overwrites=False, http_chunk_size=0, buffersize=65536,
                    noresizebuffer=True, test=False, updatetime=False, xattr_set_filesize=False,
                    external_downloader='native', concurrent_fragment_downloads=1)
    assert {k: seen[0][k] for k in expected} == expected
    assert not any(seen[0].get(k) for k in ['sleep_interval', 'ratelimit', 'throttledratelimit', 'progress_hooks', 'postprocessors'])


@pytest.mark.parametrize('result', [(False, True), (True, False), True, (True,), (1, True), [True, True]])
def test_non_success_tuple_cannot_yield(monkeypatch, transport_network, tmp_path, result):
    real = HttpFD.download
    def changed(*args, **kwargs):
        real(*args, **kwargs)
        return result
    monkeypatch.setattr(HttpFD, 'download', changed)
    transport_network.replies.append(reply(BODY))
    directory = owned(tmp_path)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(info(), target_dir=directory): pass
        safe(error.value)
        assert not bridge_set(ydl)
    assert_empty(directory)


@pytest.mark.parametrize('request_cap', [1, 2])
def test_416_extra_get_share_budget(request_cap, transport_network, tmp_path):
    network = SourceNetworkContext(context().channel, OutboundBudget(BudgetLimits(seconds=100, requests=request_cap)))
    transport_network.replies.extend([reply(b'', status=b'416 Range Not Satisfiable'), reply(BODY)])
    directory = owned(tmp_path)
    with guarded(network, identity_only=True, max_bytes=100000) as ydl:
        if request_cap == 2:
            with ydl._download_http_file(info(), target_dir=directory) as path:
                assert path.read_bytes() == BODY
        else:
            with pytest.raises(OutboundError) as error:
                with ydl._download_http_file(info(), target_dir=directory): pass
            assert error.value.code == 'source_budget_exhausted'
            safe(error.value)
        assert sends(transport_network) == request_cap and not bridge_set(ydl)
        assert network.budget.snapshot().requests == request_cap
        assert network.budget.snapshot().decoded_bytes == (len(BODY) if request_cap == 2 else 0)
        assert network.budget.snapshot().raw_bytes == (len(BODY) if request_cap == 2 else 0)
    assert_empty(directory)


def test_identity_206_and_unknown_length_read_eof(transport_network, tmp_path):
    directory = owned(tmp_path)
    transport_network.replies.append(reply(BODY, status=b'206 Partial Content',
        headers=b'Content-Range: bytes 2-66561/100000\r\n'))
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with ydl._download_http_file(info(http_headers={'Range': 'bytes=2-66561'}), target_dir=directory) as path:
            assert path.read_bytes() == BODY
    transport_network.replies.append(b'HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n' + BODY)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with ydl._download_http_file(info(), target_dir=directory) as path:
            assert path.read_bytes() == BODY
    assert_empty(directory)


@pytest.mark.parametrize('status', [401, 403, 412, 500])
def test_http_failure_download_boundary_has_safe_status_without_retry(status, transport_network, tmp_path, caplog):
    transport_network.replies.append(reply(b'synthetic-secret', status=f'{status} Synthetic'.encode()))
    directory = owned(tmp_path)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with pytest.raises(ControlledHttpStatusError) as error:
            with ydl._download_http_file(info(), target_dir=directory): pass
        assert error.value.source_status == status
        safe(error.value)
        assert sends(transport_network) == 1 and not bridge_set(ydl)
    assert 'synthetic-secret' not in caplog.text
    assert_empty(directory)


@pytest.mark.parametrize('failure', ['phase_after_length', 'root_after_length', 'read', 'size'])
def test_terminal_after_write_or_length_break_releases_before_return(failure, monkeypatch, transport_network, tmp_path):
    now = [100.0]
    network = context(clock=lambda: now[0])
    transport_network.replies.append(reply(BODY))
    directory = owned(tmp_path)
    real_download = HttpFD.download
    def after_download(*args, **kwargs):
        result = real_download(*args, **kwargs)
        now[0] += 6 if failure == 'phase_after_length' else 101
        return result
    if failure.endswith('after_length'):
        monkeypatch.setattr(HttpFD, 'download', after_download)
    elif failure == 'read':
        count = [0]
        real_read = service._ControlledYtdlpResponse.read
        def broken(response, amount=None):
            count[0] += 1
            if count[0] == 2:
                now[0] += 6
            return real_read(response, amount)
        monkeypatch.setattr(service._ControlledYtdlpResponse, 'read', broken)
    with guarded(network, identity_only=True, max_bytes=65536 if failure == 'size' else 100000) as ydl:
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(info(), target_dir=directory): pass
        assert error.value.code == ('source_too_large' if failure == 'size' else 'source_timeout')
        safe(error.value)
        assert transport_network.closed == 1 and not bridge_set(ydl)
        with pytest.raises(OutboundError):
            with ydl._download_http_file(info(), target_dir=directory): pass
        assert sends(transport_network) == 1
    assert_empty(directory)


@pytest.mark.parametrize('kind', ['nonempty', 'file', 'stdout', 'relative', 'reparse'])
def test_owned_target_rejects_without_media_io(kind, transport_network, tmp_path, monkeypatch):
    directory = owned(tmp_path)
    if kind == 'nonempty':
        (directory / 'keep').write_text('existing')
    if kind == 'file':
        directory = tmp_path / 'file'; directory.write_text('existing')
    if kind == 'stdout': directory = '-'
    if kind == 'relative': directory = Path('relative')
    if kind == 'reparse':
        real = Path.lstat
        def reparse(path, *args, **kwargs):
            result = real(path, *args, **kwargs)
            if path == directory:
                return SimpleNamespace(st_mode=result.st_mode, st_dev=result.st_dev, st_ino=result.st_ino,
                                       st_file_attributes=1024)
            return result
        monkeypatch.setattr(Path, 'lstat', reparse)
    with guarded(identity_only=True) as ydl:
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(info(), target_dir=directory): pass
        safe(error.value)
    assert not transport_network.writes
    if kind == 'nonempty': assert (directory / 'keep').read_text() == 'existing'
    if kind == 'file': assert directory.read_text() == 'existing'


def test_symlink_or_linked_ancestor_rejected(transport_network, tmp_path):
    directory = owned(tmp_path)
    link = tmp_path / 'link'
    try:
        link.symlink_to(directory, target_is_directory=True)
    except OSError:
        pytest.skip('Windows account lacks symlink privilege; controlled reparse rejection covered')
    with guarded(identity_only=True) as ydl:
        with pytest.raises(OutboundError):
            with ydl._download_http_file(info(), target_dir=link): pass
    assert not transport_network.writes and directory.is_dir() and link.is_symlink()


def test_yield_caller_exception_identity_and_early_exit(transport_network, tmp_path):
    class CallerError(Exception): pass
    error = CallerError('synthetic-secret')
    transport_network.replies.append(reply(BODY))
    directory = owned(tmp_path)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with pytest.raises(CallerError) as caught:
            with ydl._download_http_file(info(), target_dir=directory) as path:
                assert path.is_file()
                raise error
        assert caught.value is error and error.__cause__ is None and error.__context__ is None
        assert ydl._u4_state._failure is None
    assert_empty(directory)


@pytest.mark.parametrize('failure', ['write', 'rename', 'unlink', 'caller_unlink', 'replace', 'unknown_create'])
def test_file_failure_ownership_and_cleanup_priority(failure, transport_network, tmp_path, monkeypatch):
    directory = owned(tmp_path)
    transport_network.replies.append(reply(BODY))
    caller_error = RuntimeError('synthetic-secret')
    real_open, real_rename, real_unlink = HttpFD.sanitize_open, HttpFD.try_rename, Path.unlink
    class BrokenWrite:
        def __init__(self, stream): self.stream = stream
        def fileno(self): return self.stream.fileno()
        def close(self): return self.stream.close()
        def write(self, data): raise OSError('synthetic-secret')
    if failure in ('write', 'unknown_create'):
        def broken_open(fd, filename, mode):
            stream, name = real_open(fd, filename, mode)
            if failure == 'unknown_create':
                stream.close()
                raise OSError('synthetic-secret')
            return BrokenWrite(stream), name
        monkeypatch.setattr(HttpFD, 'sanitize_open', broken_open)
    if failure == 'rename':
        def broken_rename(*args): raise OSError('synthetic-secret')
        monkeypatch.setattr(HttpFD, 'try_rename', broken_rename)
    if failure in ('unlink', 'caller_unlink'):
        def broken_unlink(path, *args, **kwargs):
            if path == directory / 'media.bin': raise OSError('synthetic-secret')
            return real_unlink(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'unlink', broken_unlink)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        if failure in ('write', 'rename', 'unknown_create', 'unlink'):
            with pytest.raises(OutboundError) as error:
                with ydl._download_http_file(info(), target_dir=directory): pass
            safe(error.value)
        elif failure == 'caller_unlink':
            with pytest.raises(RuntimeError) as error:
                with ydl._download_http_file(info(), target_dir=directory):
                    raise caller_error
            assert error.value is caller_error and ydl._u4_state._failure is None
            safe_text = repr(error.value.__context__) + repr(error.value.__cause__)
            assert 'synthetic-secret' not in safe_text
        else:
            with pytest.raises(OutboundError):
                with ydl._download_http_file(info(), target_dir=directory) as path:
                    # Keep the original inode alive, avoiding OS identity reuse.
                    path.rename(directory / 'original')
                    path.write_bytes(b'unknown replacement')
                    (directory / 'other').write_bytes(b'unknown')
            assert (directory / 'media.bin').read_bytes() == b'unknown replacement'
            assert (directory / 'other').read_bytes() == b'unknown'
        assert not bridge_set(ydl) and transport_network.closed == 1
    if failure in ('write', 'rename'): assert_empty(directory)
    if failure == 'unknown_create': assert (directory / 'media.bin.part').is_file()
    if failure in ('unlink', 'caller_unlink'): assert (directory / 'media.bin').is_file()


@pytest.mark.parametrize('restriction', ['identity', 'closed', 'once', 'owner'])
def test_single_call_and_owner_restrictions(restriction, transport_network, tmp_path, monkeypatch):
    directory = owned(tmp_path)
    with guarded(identity_only=restriction != 'identity', max_bytes=100000) as ydl:
        if restriction == 'closed': ydl.close()
        if restriction == 'once':
            transport_network.replies.append(reply(BODY))
            with ydl._download_http_file(info(), target_dir=directory): pass
        if restriction == 'owner':
            monkeypatch.setattr('app.services.source_network.get_ident', lambda: -1)
        before = len(transport_network.writes)
        with pytest.raises(OutboundError):
            with ydl._download_http_file(info(), target_dir=directory): pass
        assert len(transport_network.writes) == before
    assert_empty(directory)


def test_private_seam_does_not_open_old_downloader_or_factory():
    for method in ['process_info', 'dl', 'download_true', 'process_true']:
        with guarded(identity_only=True) as ydl:
            with pytest.raises(OutboundError):
                if method == 'process_info': ydl.process_info(info())
                elif method == 'dl': ydl.dl('never', info())
                else: ydl.extract_info('http://public.example/unit', **({'download': True} if method == 'download_true' else {'process': True}))
    with pytest.raises(OutboundError): make_runtime_source_network()


@pytest.mark.parametrize('source_failure', [False, True])
def test_response_cleanup_failure_is_safe_and_preserves_source_first_error(source_failure, transport_network, tmp_path, monkeypatch):
    directory = owned(tmp_path)
    transport_network.replies.append(reply(BODY))
    real_close = service._ControlledYtdlpResponse.close
    once = [False]
    def broken_close(response):
        real_close(response)
        if not once[0]:
            once[0] = True
            raise RuntimeError('synthetic-secret')
    monkeypatch.setattr(service._ControlledYtdlpResponse, 'close', broken_close)
    with guarded(identity_only=True, max_bytes=65536 if source_failure else 100000) as ydl:
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(info(), target_dir=directory): pass
        assert error.value.code == ('source_too_large' if source_failure else 'outbound_unavailable')
        safe(error.value)
        assert not bridge_set(ydl) and transport_network.closed == 1
    assert_empty(directory)


def test_directory_replacement_during_yield_does_not_delete_new_occupant(transport_network, tmp_path):
    directory = owned(tmp_path)
    transport_network.replies.append(reply(BODY))
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(info(), target_dir=directory):
                directory.rename(tmp_path / 'original-directory')
                directory.mkdir()
                (directory / 'media.bin').write_bytes(b'unknown replacement')
        safe(error.value)
    assert (directory / 'media.bin').read_bytes() == b'unknown replacement'
    assert (tmp_path / 'original-directory' / 'media.bin').read_bytes() == BODY


def test_no_external_execution_or_hooks_for_native_path(transport_network, tmp_path, monkeypatch):
    import subprocess
    import threading
    def denied(*args, **kwargs): pytest.fail('native seam used external execution/thread/hook')
    monkeypatch.setattr(subprocess, 'Popen', denied)
    monkeypatch.setattr(threading.Thread, 'start', denied)
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'run_all_pps', denied)
    transport_network.replies.append(reply(BODY))
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with ydl._download_http_file(info(), target_dir=owned(tmp_path)) as path:
            assert path.read_bytes() == BODY


def test_416_does_not_reclassify_later_unknown_file_failure(transport_network, tmp_path, monkeypatch):
    directory = owned(tmp_path)
    transport_network.replies.extend([reply(b'', status=b'416 Range Not Satisfiable'), reply(BODY)])
    def broken_rename(*args): raise RuntimeError('synthetic-secret')
    monkeypatch.setattr(HttpFD, 'try_rename', broken_rename)
    with guarded(identity_only=True, max_bytes=100000) as ydl:
        with pytest.raises(OutboundError) as error:
            with ydl._download_http_file(info(), target_dir=directory): pass
        assert error.value.code == 'outbound_unavailable'
        safe(error.value)
    assert sends(transport_network) == 2
    assert_empty(directory)
