"""Explicit source scopes: synthetic fixtures, never real DNS/proxy/source I/O."""
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy

import httpx
import pytest

from app.config import settings
from app.services import bilibili_api_source, bilibili_subtitle_source, subtitle_service, subtitle_sources
from app.services.outbound_budget import BudgetLimits, OutboundBudget, OutboundBudgetError
from app.services.outbound_httpx import ControlledHttpStatusError, ProxyChannel
from app.services.outbound_policy import OutboundPolicyError, OutboundUnavailableError
from test_outbound_httpx import install, response, transport_network

ARCHIVE = 'https://archive.org/details/lecture-item'
BILI = 'https://www.bilibili.com/video/BV1DdnM6bEL4'
CAPTION = b'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello'


def network_module():
    return importlib.import_module('app.services.source_network')


def context(**limits):
    budget = OutboundBudget(BudgetLimits(**limits))
    return network_module().SourceNetworkContext(ProxyChannel('http://127.0.0.1:4750', True), budget)


def metadata():
    return {'metadata': {'title': 'Lecture', 'language': 'en'}, 'files': [{'name': 'lecture.en.vtt'}]}


def forbid_extractor(monkeypatch):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail('guarded HTTPX scope reached unguarded yt-dlp extraction')
    monkeypatch.setattr(subtitle_service.ytdlp_service, 'extract_info', forbidden)
    return calls


def test_scope_resets_on_error_and_nested_none_cannot_remove_guard():
    mod, ctx = network_module(), context()
    assert mod.current_source_network() is None
    with pytest.raises(RuntimeError):
        with mod.source_network_scope(ctx):
            with mod.source_network_scope(None):
                assert mod.current_source_network() is ctx
            with pytest.raises(OutboundUnavailableError):
                with mod.source_network_scope(context()):
                    pytest.fail('replaced budget')
            raise RuntimeError('synthetic')
    assert mod.current_source_network() is None


def test_context_cannot_move_to_another_thread():
    mod, ctx = network_module(), context()
    def enter():
        with mod.source_network_scope(ctx):
            pass
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OutboundUnavailableError):
            pool.submit(enter).result()


def test_inherited_context_is_rejected_after_pid_change(monkeypatch):
    mod, ctx = network_module(), context()
    with mod.source_network_scope(ctx):
        monkeypatch.setattr(mod, 'getpid', lambda: ctx._process + 1)
        with pytest.raises(OutboundUnavailableError):
            mod.current_source_network()
        fresh = context()
        fresh.check_owner()


def test_runtime_factory_is_closed_before_transport(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('closed runtime factory constructed a transport')
    monkeypatch.setattr(httpx, 'HTTPTransport', forbidden)
    with pytest.raises(OutboundUnavailableError):
        network_module().make_runtime_source_network()


def test_archive_metadata_and_caption_share_original_budget(install, monkeypatch):
    calls = forbid_extractor(monkeypatch)
    wire_metadata = json.dumps(metadata()).encode()
    fake = install(lambda req: response(wire_metadata if req.url.path.startswith('/metadata/') else CAPTION))
    ctx = context()
    doc = subtitle_service.fetch_subtitle_document(ARCHIVE, network=ctx)
    assert doc.title == 'Lecture' and doc.text == 'Hello' and len(doc.segments) == 1
    assert len(fake.calls) == ctx.budget.snapshot().requests == 2
    assert ctx.budget.snapshot().raw_bytes == len(wire_metadata) + len(CAPTION)
    assert ctx.budget.snapshot().decoded_bytes == ctx.budget.snapshot().raw_bytes
    assert ctx.budget.checkpoint().children == ()
    assert calls == [] and network_module().current_source_network() is None


@pytest.mark.parametrize('failure', ['status', 'malformed', 'empty', 'unsupported'])
def test_guarded_metadata_never_reaches_legacy_fallback(failure, install, monkeypatch):
    calls = forbid_extractor(monkeypatch)
    body = b'not-json' if failure == 'malformed' else json.dumps({'files': []}).encode()
    fake = install(lambda req: response(body, status=503 if failure == 'status' else 200))
    ctx = context()
    expected = ControlledHttpStatusError if failure == 'status' else OutboundUnavailableError
    with pytest.raises(expected) as error:
        subtitle_service.fetch_subtitle_document('https://other.example/video' if failure == 'unsupported' else ARCHIVE, network=ctx)
    assert len(fake.calls) == (0 if failure == 'unsupported' else 1)
    assert calls == [] and error.value.__context__ is None


@pytest.mark.parametrize('failure', ['language', 'invalid_body'])
def test_guarded_document_fallback_is_closed(failure, install, monkeypatch):
    calls = forbid_extractor(monkeypatch)
    fake = install(lambda req: response(json.dumps(metadata()).encode() if req.url.path.startswith('/metadata/') else b'invalid-caption'))
    with pytest.raises(OutboundUnavailableError):
        subtitle_service.fetch_subtitle_document(ARCHIVE, 'ja' if failure == 'language' else None, network=context())
    assert len(fake.calls) == (1 if failure == 'language' else 2) and calls == []


def test_guarded_raw_client_injection_rejected_before_metadata(install, monkeypatch):
    calls = forbid_extractor(monkeypatch)
    fake = install(lambda req: response())
    with pytest.raises(OutboundUnavailableError):
        subtitle_service.fetch_subtitle_document(ARCHIVE, client=object(), network=context())
    assert fake.calls == [] and calls == []


def test_parent_request_limit_cannot_reset_between_metadata_and_body(install, monkeypatch):
    forbid_extractor(monkeypatch)
    fake = install(lambda req: response(json.dumps(metadata()).encode()))
    ctx = context(requests=1)
    with pytest.raises(OutboundBudgetError) as error:
        subtitle_service.fetch_subtitle_document(ARCHIVE, network=ctx)
    assert error.value.code == 'source_budget_exhausted'
    assert len(fake.calls) == ctx.budget.snapshot().requests == 1


def test_subtitle_raw_limit_closes_without_generic_retry(install, monkeypatch):
    forbid_extractor(monkeypatch)
    monkeypatch.setattr(settings, 'subtitle_max_bytes', 200)
    fake = install(lambda req: response(json.dumps(metadata()).encode() if req.url.path.startswith('/metadata/') else b'x' * 201))
    with pytest.raises(OutboundBudgetError) as error:
        subtitle_service.fetch_subtitle_document(ARCHIVE, network=context())
    assert error.value.code == 'subtitle_too_large' and len(fake.calls) == 2 and fake.closed


def strict_jar():
    jar = CookieJar(policy=DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
    for name, domain, specified, path, secure in [
        ('official', '.bilibili.com', True, '/', True),
        ('hostonly', 'www.bilibili.com', False, '/', True),
        ('pathonly', '.bilibili.com', True, '/private', True),
    ]:
        jar.set_cookie(Cookie(0, name, 'synthetic', None, False, domain, specified,
                              domain.startswith('.'), path, True, secure, None, True, None, None, {}, False))
    return jar


def patch_jar(monkeypatch):
    monkeypatch.setattr(bilibili_subtitle_source, 'cookie_jar_for_url', lambda url: strict_jar())
    monkeypatch.setattr(bilibili_api_source, 'cookie_jar_for_url', lambda url: strict_jar())


def bili_view():
    return {'bvid': 'BV1DdnM6bEL4', 'aid': 123, 'title': 'Example',
            'pages': [{'page': 1, 'cid': 456, 'duration': 100}]}


def bili_play():
    return {'timelength': 100000, 'dash': {
        'video': [{'id': 64, 'baseUrl': 'https://cdn.bilivideo.com/video', 'codecs': 'avc1', 'height': 720, 'width': 1280}],
        'audio': [{'id': 30280, 'baseUrl': 'https://cdn.bilivideo.com/audio', 'codecs': 'mp4a'}]}}


def test_bili_api_identity_and_strict_cookie_selection(install, monkeypatch):
    patch_jar(monkeypatch)
    fake = install(lambda req: response(json.dumps({'code': 0, 'data': bili_view() if req.url.path.endswith('/view') else bili_play()}).encode()))
    ctx = context()
    with network_module().source_network_scope(ctx):
        result = bilibili_api_source.extract_api_video(BILI)
    assert result['duration'] == 100 and len(fake.calls) == 2
    for req in fake.calls:
        assert req.headers['cookie'] == 'official=synthetic'
        assert req.headers['accept-encoding'] == 'identity'
    assert ctx.budget.checkpoint().children == ()


@pytest.mark.parametrize('adapter', ['api', 'subtitle'])
def test_bili_redirect_denied_at_first_response(adapter, install, monkeypatch):
    patch_jar(monkeypatch)
    fake = install(lambda req: response(b'', status=301, headers={'location': 'https://api.bilibili.com/next'}))
    with network_module().source_network_scope(context()):
        with pytest.raises(OutboundPolicyError):
            (bilibili_api_source.extract_api_video if adapter == 'api' else bilibili_subtitle_source.bilibili_tracks)(BILI)
    assert len(fake.calls) == 1


def test_bili_subtitle_cdn_never_receives_cookies(install, monkeypatch):
    patch_jar(monkeypatch)
    forbid_extractor(monkeypatch)
    def handler(req):
        if req.url.path.endswith('/web-interface/view'):
            data = bili_view()
        elif req.url.host == 'api.bilibili.com':
            data = {'subtitle': {'subtitles': [{'lan': 'en', 'subtitle_url': 'https://i0.hdslb.com/bfs/subtitle/test.json'}]}}
        else:
            return response(json.dumps({'body': [{'from': 0, 'to': 1, 'content': 'Hello'}]}).encode())
        return response(json.dumps({'code': 0, 'data': data}).encode())
    fake = install(handler)
    assert subtitle_service.fetch_subtitle_document(BILI, network=context()).text == 'Hello'
    assert len(fake.calls) == 3
    assert fake.calls[0].headers['cookie'] == fake.calls[1].headers['cookie'] == 'official=synthetic'
    assert 'cookie' not in fake.calls[2].headers and 'authorization' not in fake.calls[2].headers


def test_filtered_extractor_credentials_do_not_reach_caption(install, monkeypatch):
    fake = install(lambda req: response(CAPTION))
    monkeypatch.setattr(subtitle_service.ytdlp_service, 'extract_subtitle_tracks', lambda url: {
        'title': 'Fixture', 'tracks': [{'language': 'en', 'is_auto': False, 'formats': [{
            'url': 'https://caption.example/caption', 'ext': 'vtt', 'http_headers': {
                'Cookie': 'synthetic', 'Authorization': 'Bearer synthetic', 'X-Custom': 'value', 'User-Agent': 'Fixture'}
        }]}]})
    assert subtitle_service.fetch_subtitle_document(ARCHIVE, network=context()).text == 'Hello'
    assert fake.calls[0].headers['user-agent'] == 'Fixture'
    assert not {'cookie', 'authorization', 'x-custom'} & set(fake.calls[0].headers)


def test_archive_redirect_uses_real_httpx_stack_and_fixed_proxy(transport_network):
    state = transport_network
    body = json.dumps(metadata()).encode()
    state.replies = [b'HTTP/1.1 200 Connection established\r\n\r\n',
        b'HTTP/1.1 302 Found\r\nLocation: https://metadata.example/lecture\r\nContent-Length: 0\r\n\r\n',
        b'HTTP/1.1 200 Connection established\r\n\r\n',
        b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body]
    ctx = context()
    with network_module().source_network_scope(ctx):
        result = subtitle_sources.resolve_public_subtitles(ARCHIVE)
    assert result['tracks'][0]['language'] == 'en'
    assert ctx.budget.snapshot().requests == 2 and ctx.budget.snapshot().redirects == 1
    assert all(connection[:2] == ('127.0.0.1', 4750) for connection in state.connections)
    assert [tls[0] for tls in state.tls] == ['archive.org', 'metadata.example']


def test_session_helper_has_single_lower_layer_implementation():
    from app.services import bilibili_session
    assert bilibili_subtitle_source.apply_session_cookies is bilibili_session.apply_session_cookies
    assert bilibili_api_source.apply_session_cookies is bilibili_session.apply_session_cookies
    assert network_module().apply_session_cookies is bilibili_session.apply_session_cookies


@pytest.mark.parametrize('order', [
    ('source_network', 'bilibili_subtitle_source', 'bilibili_api_source'),
    ('bilibili_api_source', 'bilibili_subtitle_source', 'source_network'),
])
def test_fresh_import_orders_have_no_adapter_cycle(order):
    import os
    from pathlib import Path
    import subprocess
    import sys
    backend = str(Path(__file__).resolve().parents[2])
    code = f'''
import sys, socket, importlib
sys.path.insert(0, {backend!r})
def forbidden(*args, **kwargs):
    raise AssertionError("offline")
socket.getaddrinfo = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
# Check installation before attempting numeric targets: a missing patch must
# fail without allowing this regression test itself to touch the network.
assert socket.socket.connect is forbidden
assert socket.socket.connect_ex is forbidden
with socket.socket() as probe:
    for operation in (probe.connect, probe.connect_ex):
        try:
            operation(('192.0.2.1', 443))
        except AssertionError as error:
            assert str(error) == 'offline'
        else:
            raise AssertionError('numeric socket was not denied')
try:
    socket.getaddrinfo('example.invalid', 443)
except AssertionError as error:
    assert str(error) == 'offline'
else:
    raise AssertionError('DNS was not denied')
[importlib.import_module('app.services.' + name) for name in {order!r}]
'''
    result = subprocess.run([sys.executable, '-B', '-c', code], env=dict(os.environ),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('failure', ['size', 'deadline', 'encoded', 'status'])
def test_bili_api_preserves_tighter_limits_and_terminal_errors(failure, install, monkeypatch):
    from test_outbound_httpx import Wire
    patch_jar(monkeypatch)
    now = [0.0]
    if failure == 'size':
        body, headers = b'x' * (1024 * 1024 + 1), {}
    else:
        body, headers = json.dumps({'code': 0, 'data': bili_view()}).encode(), {}
    if failure == 'encoded':
        headers = {'content-encoding': 'gzip'}
    stream = Wire([body], before=(lambda: now.__setitem__(0, 17.0)) if failure == 'deadline' else None)
    fake = install(lambda req: httpx.Response(412 if failure == 'status' else 200, headers=headers, stream=stream))
    ctx = network_module().SourceNetworkContext(ProxyChannel('http://127.0.0.1:4750', True),
        OutboundBudget(BudgetLimits(), clock=lambda: now[0]))
    expected = ControlledHttpStatusError if failure == 'status' else OutboundUnavailableError if failure == 'encoded' else OutboundBudgetError
    with network_module().source_network_scope(ctx):
        with pytest.raises(expected):
            bilibili_api_source.extract_api_video(BILI)
    assert len(fake.calls) == 1 and stream.closed
    if failure in {'encoded', 'status'}:
        assert stream.reads == 0


@pytest.mark.parametrize('error_type', ['budget', 'status'])
def test_legacy_generic_fallback_cannot_swallow_guard_error(error_type, monkeypatch):
    from app.services.outbound_budget import BudgetReason
    terminal = OutboundBudgetError(BudgetReason.REQUESTS) if error_type == 'budget' else ControlledHttpStatusError(503)
    calls = []
    def extract(url, **kwargs):
        calls.append(kwargs)
        if kwargs:
            raise terminal
        return {**metadata(), 'title': 'Example', '_source': 'public', 'tracks': []}
    monkeypatch.setattr(subtitle_service.ytdlp_service, 'extract_subtitle_tracks', extract)
    with pytest.raises(type(terminal)) as error:
        subtitle_service.fetch_subtitle_document(ARCHIVE)
    assert error.value is terminal and calls == [{}, {'use_public_sources': False}]


def test_bili_caption_replaces_case_insensitive_extractor_referer(install, monkeypatch):
    fake = install(lambda req: response(json.dumps({'body': [{'from': 0, 'to': 1, 'content': 'Hello'}]}).encode()))
    monkeypatch.setattr(subtitle_service.ytdlp_service, 'extract_subtitle_tracks', lambda url: {
        'title': 'Fixture', 'tracks': [{'language': 'en', 'is_auto': False, 'formats': [{
            'url': 'https://i0.hdslb.com/bfs/subtitle/test.json', 'ext': 'bilibili_json',
            'http_headers': {'referer': 'https://other.example/path?token=synthetic'}
        }]}]})
    assert subtitle_service.fetch_subtitle_document(BILI + '?p=1', network=context()).text == 'Hello'
    assert fake.calls[0].headers['referer'] == BILI
