"""Offline broker boundary tests; no source, credentials, database or environment file."""
import importlib
import json
import socket
import struct
import threading

import pytest


def broker():
    return importlib.import_module('app.services.source_broker')


@pytest.mark.parametrize('payload', [
    {}, {'version': True, 'op': 'ping'}, {'version': 1, 'op': 'exec'},
    {'version': 1, 'op': 'ping', 'path': '/etc/passwd'},
    {'version': 1, 'op': 'parse', 'url': 'http://127.0.0.1/private'},
    {'version': 1, 'op': 'parse', 'url': 'https://example.com', 'bili_cookie_snapshot': 'secret'},
    {'version': 1, 'op': 'verify', 'url': 'https://example.com', 'format_id': 'best', 'max_height': True},
    {'version': 1, 'op': 'verify', 'url': 'https://example.com', 'format_id': 'x' * 1025, 'max_height': 720},
])
def test_rejects_rpc_shape_url_and_privileged_fields(payload):
    with pytest.raises(broker().SourceBrokerError) as error:
        broker().validate_request(payload)
    assert error.value.status_code in {400, 422, 503}


OPTIONS = [
    {'format_id': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', 'height': 1080},
    {'format_id': 'p720', 'height': 720},
    {'format_id': 'p360', 'height': 360},
]


@pytest.mark.parametrize('choice,limit,want', [
    ('best', 720, 'p720[height<=720]'),
    ('p360', 720, 'p360[height<=720]'),
    ('best', None, 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'),
    ('p720', None, 'p720[height<=720]'),
])
def test_canonical_selector_is_proven_from_options(choice, limit, want):
    assert broker().canonical_format(OPTIONS, choice, limit) == want


@pytest.mark.parametrize('options,choice,limit,code,status', [
    (OPTIONS, OPTIONS[0]['format_id'], 720, 'membership_required', 403),
    (OPTIONS, 'p999', 720, 'format_unverified', 422),
    ([{'format_id': 'best', 'height': None}], 'best', 720, 'format_unverified', 422),
    ([{'format_id': 'p', 'height': True}], 'p', 720, 'format_unverified', 422),
    ([{'format_id': 'p/best', 'height': 360}], 'p/best', 720, 'format_unverified', 422),
])
def test_unproven_or_over_entitlement_selection_is_rejected(options, choice, limit, code, status):
    with pytest.raises(broker().SourceBrokerError) as error:
        broker().canonical_format(options, choice, limit)
    assert (error.value.code, error.value.status_code) == (code, status)


def test_verify_parses_once_and_cookie_snapshot_is_private():
    calls = []
    def run(config, url, snapshot):
        calls.append((url, snapshot))
        return {'title': 'example'}, OPTIONS
    service = broker().Broker(object(), api_uid=123, api_gid=456,
        child_runner=run, snapshot_reader=lambda url: 'private-cookie')
    result = service.dispatch({'version': 1, 'op': 'verify', 'url': 'https://example.com',
                               'format_id': 'p360', 'max_height': 720})
    assert result == {'version': 1, 'ok': True, 'format_id': 'p360[height<=720]'}
    assert calls == [('https://example.com/', 'private-cookie')]
    assert 'private-cookie' not in json.dumps(result)


def test_error_payload_never_contains_untrusted_exception():
    def fail(*args):
        raise RuntimeError('secret-cookie https://private.example')
    service = broker().Broker(object(), api_uid=1, api_gid=2, child_runner=fail,
                              snapshot_reader=lambda url: None)
    assert service.dispatch({'version': 1, 'op': 'parse', 'url': 'https://example.com'}) == {
        'version': 1, 'ok': False, 'code': 'outbound_unavailable', 'status': 503}


def test_length_prefix_rejects_oversized_frame_without_reading_body():
    left, right = socket.socketpair()
    try:
        left.sendall(struct.pack('!I', 65537))
        with pytest.raises(broker().SourceBrokerError):
            broker().read_frame(right, 65536)
    finally:
        left.close()
        right.close()


def test_unauthorized_peer_never_runs_source():
    service = broker().Broker(object(), api_uid=123, api_gid=456,
        child_runner=lambda *args: pytest.fail('unauthorized source invocation'),
        snapshot_reader=lambda url: pytest.fail('unauthorized cookie read'))
    left, right = socket.socketpair()
    try:
        service.handle_connection(right, peer_uid=lambda conn: 999)
        assert broker().read_frame(left, 524288) == {
            'version': 1, 'ok': False, 'code': 'outbound_unavailable', 'status': 503}
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize('reply', [
    {'version': 1, 'ok': True, 'pong': True, 'ready': False},
    {'version': 2, 'ok': True, 'pong': True, 'ready': True},
    {'version': 1, 'ok': True, 'pong': True, 'ready': True, 'extra': 'bad'},
])
def test_ping_rejects_unready_or_wrong_protocol(monkeypatch, reply):
    monkeypatch.setattr(broker(), '_request', lambda *args, **kwargs: reply)
    assert broker().ping('/not-used') is False


def test_child_private_snapshot_always_scoped(monkeypatch):
    from contextlib import contextmanager
    child = importlib.import_module('app.source_child')
    state = []
    @contextmanager
    def scope(value):
        state.append(value)
        yield
        state.pop()
    monkeypatch.setattr(child, 'cookie_snapshot_scope', scope)
    monkeypatch.setattr(child, 'make_runtime_source_network', lambda budget: None)
    def parse(url):
        assert state == [None]
        return {'title': 'anonymous'}, OPTIONS
    monkeypatch.setattr(child, 'source_parse_video', parse)
    assert child.execute({'version': 1, 'op': 'parse', 'url': 'https://example.com',
                          'bili_cookie_snapshot': None})['meta']['title'] == 'anonymous'


def test_child_untrusted_exception_becomes_fixed_safe_code(monkeypatch):
    child = importlib.import_module('app.source_child')
    def fail(budget):
        raise ValueError('cookie-secret')
    monkeypatch.setattr(child, 'make_runtime_source_network', fail)
    assert child.execute({'version': 1, 'op': 'parse', 'url': 'https://example.com',
                          'bili_cookie_snapshot': None}) == {
        'version': 1, 'ok': False, 'code': 'outbound_unavailable', 'status': 503}


def test_broker_errors_use_existing_http_error_base():
    from app.services.outbound_policy import OutboundError
    assert isinstance(broker().SourceBrokerError('membership_required'), OutboundError)


def test_subtitle_rpc_reconstructs_timeline(monkeypatch):
    monkeypatch.setattr(broker(), '_request', lambda *args, **kwargs: {
        'version': 1, 'ok': True, 'document': {'title': 'Example', 'language': 'en',
        'is_auto': False, 'available_languages': ['en'], 'text': 'hello',
        'segments': [{'start': 0.0, 'end': 1.5, 'text': 'hello'}]}})
    document = broker().fetch_subtitle_document('/not-used', 'https://example.com', 'en')
    assert (document.title, document.text, document.segments[0].end) == ('Example', 'hello', 1.5)


@pytest.mark.parametrize('language', [True, 'x' * 129, 'en\nsecret', ['en']])
def test_subtitle_rpc_rejects_invalid_language(language):
    with pytest.raises(broker().SourceBrokerError):
        broker().validate_request({'version': 1, 'op': 'subtitle', 'url': 'https://example.com',
                                   'language': language})


def test_child_subtitles_use_explicit_network_and_anonymous_snapshot(monkeypatch):
    from app.services.subtitle_service import SubtitleDocument
    child = importlib.import_module('app.source_child')
    monkeypatch.setattr(child, 'make_runtime_source_network', lambda budget: None)
    def fetch(url, language, *, network):
        assert url == 'https://example.com/' and language == 'en' and network is None
        return SubtitleDocument('Example', 'en', False, ['en'], 'hello')
    monkeypatch.setattr(child, 'source_fetch_subtitle_document', fetch)
    result = child.execute({'version': 1, 'op': 'subtitle', 'url': 'https://example.com',
                            'language': 'en', 'bili_cookie_snapshot': None})
    assert result['document']['text'] == 'hello'


def test_child_subtitle_errors_keep_fixed_type_and_strip_source_text(monkeypatch):
    from app.services.subtitle_service import SubtitleServiceError
    child = importlib.import_module('app.source_child')
    monkeypatch.setattr(child, 'make_runtime_source_network', lambda budget: None)
    def fetch(*args, **kwargs):
        raise SubtitleServiceError('subtitle_unavailable', 'untrusted cookie-value')
    monkeypatch.setattr(child, 'source_fetch_subtitle_document', fetch)
    assert child.execute({'version': 1, 'op': 'subtitle', 'url': 'https://example.com',
        'language': None, 'bili_cookie_snapshot': None}) == {
            'version': 1, 'ok': False, 'code': 'subtitle_unavailable', 'status': 422}


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(broker().SourceBrokerError):
        broker()._decode(b'{"version":1,"op":"ping","op":"exec"}')


def test_output_limit_rejects_large_metadata():
    with pytest.raises(broker().SourceBrokerError):
        broker()._encode({'title': 'x' * (512 * 1024)}, 512 * 1024)


@pytest.mark.parametrize('field', ['ready', 'pong'])
def test_ping_requires_boolean_readiness(monkeypatch, field):
    reply = {'version': 1, 'ok': True, 'pong': True, 'ready': True, field: 1}
    monkeypatch.setattr(broker(), '_request', lambda *args, **kwargs: reply)
    assert broker().ping('/not-used') is False


def test_known_bilibili_error_preserves_safe_category(monkeypatch):
    from app.services import ytdlp_service
    child = importlib.import_module('app.source_child')
    monkeypatch.setattr(child, 'make_runtime_source_network', lambda budget: None)
    def fail(url):
        raise ytdlp_service._BilibiliSourceError('verification_required')
    monkeypatch.setattr(child, 'source_parse_video', fail)
    assert child.execute({'version': 1, 'op': 'parse', 'url': 'https://example.com',
                          'bili_cookie_snapshot': None})['code'] == 'verification_required'


def test_sweep_failure_disables_readiness_and_followup_source(monkeypatch):
    calls = []
    def fail(*args):
        calls.append(1)
        raise broker().child_isolation.IsolationError('isolation_sweep_failed')
    service = broker().Broker(object(), api_uid=1, api_gid=2, child_runner=fail,
                              snapshot_reader=lambda url: None)
    service.ready = True
    payload = {'version': 1, 'op': 'parse', 'url': 'https://example.com'}
    service.dispatch(payload)
    assert service.ready is False
    service.dispatch(payload)
    assert calls == [1]


@pytest.mark.parametrize('change', [
    {'is_auto': 1}, {'segments': [{'start': -1, 'end': 0, 'text': 'bad'}]},
    {'segments': [{'start': True, 'end': 1, 'text': 'bad'}]},
    {'segments': [{'start': 0, 'end': float('inf'), 'text': 'bad'}]},
    {'available_languages': [123]}, {'unknown': 'field'},
])
def test_subtitle_reconstruction_refuses_untrusted_shape(change):
    value = {'title': 'Example', 'language': 'en', 'is_auto': False,
             'available_languages': ['en'], 'text': 'hello', 'segments': []}
    with pytest.raises(broker().SourceBrokerError):
        broker()._subtitle_document({**value, **change})


def test_client_without_unix_socket_support_fails_closed_before_socket_creation(monkeypatch):
    from types import SimpleNamespace
    def forbidden(*args, **kwargs):
        pytest.fail('unsupported runtime must not create a socket')
    monkeypatch.setattr(broker(), 'socket', SimpleNamespace(socket=forbidden))
    with pytest.raises(broker().SourceBrokerError) as error:
        broker().parse_video('/run/source.sock', 'https://example.com')
    assert (error.value.code, error.value.status_code) == ('outbound_unavailable', 503)
    assert broker().ping('/run/source.sock') is False


@pytest.mark.parametrize('path', [None, '', b'', 123, [], '/run/\x00source.sock'])
def test_invalid_socket_path_is_rejected_before_socket_creation(monkeypatch, path):
    def forbidden(*args, **kwargs):
        pytest.fail('invalid path must not create a socket')
    monkeypatch.setattr(broker().socket, 'socket', forbidden)
    monkeypatch.setattr(broker().socket, 'AF_UNIX', 1, raising=False)
    monkeypatch.setattr(broker().socket, 'SOCK_STREAM', 1, raising=False)
    with pytest.raises(broker().SourceBrokerError) as error:
        broker().parse_video(path, 'https://example.com')
    assert (error.value.code, error.value.status_code) == ('outbound_unavailable', 503)
