"""Offline boundary tests: fake transports never resolve or connect."""

import gzip
from types import SimpleNamespace
import zlib

import httpx
import pytest

from app.services.outbound_budget import BudgetLimits, OutboundBudget, OutboundBudgetError
from app.services.outbound_policy import (
    OutboundPolicy, OutboundPolicyError, OutboundUnavailableError,
)
from app.services.outbound_httpx import ControlledHttpxClient, ProxyChannel


class Wire(httpx.SyncByteStream):
    def __init__(self, chunks, before=None):
        self.chunks = chunks
        self.before = before
        self.closed = False
        self.reads = 0

    def __iter__(self):
        for chunk in self.chunks:
            if self.before:
                self.before()
            self.reads += 1
            yield chunk

    def close(self):
        self.closed = True


class FakeProxy(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.options = None
        self.closed = False

    def handle_request(self, request):
        self.calls.append(request)
        return self.handler(request)

    def close(self):
        self.closed = True


@pytest.fixture
def install(monkeypatch):
    def build(handler):
        transport = FakeProxy(handler)

        def factory(**options):
            transport.options = options
            return transport

        monkeypatch.setattr(httpx, 'HTTPTransport', factory)
        return transport
    return build


def budget(**kwargs):
    return OutboundBudget(BudgetLimits(**kwargs))


def client(**kwargs):
    return ControlledHttpxClient(
        ProxyChannel('http://proxy-user:proxy-secret@127.0.0.1:4750', readiness_confirmed=True),
        **kwargs,
    )


def response(body=b'ok', *, status=200, headers=None):
    return httpx.Response(status, headers=headers, stream=Wire([body]))


@pytest.fixture
def transport_network(monkeypatch):
    """Exercise real HTTPTransport/httpcore with a fake lowest network backend."""
    from httpcore._backends.sync import SyncBackend
    import socket

    state = SimpleNamespace(connections=[], writes=[], reads=[], tls=[], closed=0,
                            replies=[], connect_error=None, tls_error=None, before_read=None)

    class Network:
        def read(self, max_bytes, timeout=None):
            state.reads.append((max_bytes, timeout))
            if state.before_read:
                state.before_read()
            if not state.replies:
                return b''
            reply = state.replies[0]
            part = reply[:max_bytes]
            if len(part) == len(reply):
                state.replies.pop(0)
            else:
                state.replies[0] = reply[max_bytes:]
            return part

        def write(self, buffer, timeout=None):
            state.writes.append(bytes(buffer))

        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            state.tls.append((server_hostname, ssl_context.check_hostname,
                              ssl_context.verify_mode, timeout))
            if state.tls_error:
                raise state.tls_error
            return self

        def get_extra_info(self, info):
            return None

        def close(self):
            state.closed += 1

    def connect(backend, host, port, timeout=None, local_address=None, socket_options=None):
        state.connections.append((host, port, timeout))
        if state.connect_error:
            raise state.connect_error
        return Network()

    def forbidden(*args, **kwargs):
        pytest.fail('offline transport test attempted DNS or a real socket')

    monkeypatch.setattr(SyncBackend, 'connect_tcp', connect)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    return state


@pytest.mark.parametrize('channel', [None, ProxyChannel(None), ProxyChannel('http://127.0.0.1:4750')])
def test_missing_reviewed_proxy_never_constructs_transport(channel, monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('fail-closed channel attempted transport construction')
    monkeypatch.setattr(httpx, 'HTTPTransport', forbidden)
    with pytest.raises(OutboundUnavailableError):
        ControlledHttpxClient(channel)


def test_fixed_proxy_tls_environment_and_no_source_proxy_auth(install, monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://evil.example:80')
    monkeypatch.setenv('NO_PROXY', '*')
    fake = install(lambda request: response())
    with client() as source:
        result = source.get('https://public.example/video?token=secret', budget=budget())
    assert result.status_code == 200 and result.content == b'ok'
    assert fake.options['proxy'] == 'http://proxy-user:proxy-secret@127.0.0.1:4750'
    assert fake.options['trust_env'] is False and fake.options['verify'] is True
    assert fake.options['retries'] == 0 and fake.options['http2'] is False
    assert 'proxy-authorization' not in fake.calls[0].headers
    assert fake.calls[0].url.host == 'public.example'
    assert fake.closed


@pytest.mark.parametrize('override', ['proxy', 'proxies', 'trust_env', 'verify', 'follow_redirects', 'cookies', 'auth', 'timeout'])
def test_request_api_rejects_transport_security_overrides(install, override):
    fake = install(lambda request: response())
    with client() as source:
        with pytest.raises(TypeError):
            source.get('https://public.example/', budget=budget(), **{override: False})
    assert fake.calls == []


@pytest.mark.parametrize('method', ['POST', 'PUT', 'CONNECT', 'TRACE', 'get'])
def test_source_stream_rejects_other_methods_before_request(install, method):
    fake = install(lambda request: response())
    with client() as source:
        with pytest.raises(OutboundPolicyError):
            with source.stream(method, 'https://public.example/', budget=budget()):
                pass
    assert fake.calls == []


def test_provider_scope_cannot_be_borrowed_by_source_adapter(install):
    fake = install(lambda request: response())
    with pytest.raises(OutboundPolicyError):
        client(purpose='provider', policy=OutboundPolicy(provider_origins=frozenset({('https', 'public.example', 443)})))
    assert fake.calls == []


@pytest.mark.parametrize('location', ['http://169.254.169.254/', 'https://127.0.0.1/', 'https://[::1]/', 'http://public.example/', '//user:secret@public.example/', '/bad\r\nCookie:x'])
def test_redirect_revalidates_and_never_sends_rejected_hop(install, location):
    body = Wire([b'discarded'])
    fake = install(lambda request: httpx.Response(302, headers={'location': location}, stream=body))
    counter = budget()
    with client() as source:
        with pytest.raises(OutboundPolicyError):
            source.get('https://public.example/', budget=counter)
    assert len(fake.calls) == 1 and body.closed and body.reads == 0
    assert counter.snapshot().requests == 1


def test_redirect_counts_every_hop_and_strips_credentials_permanently(install):
    locations = ['https://other.example/final', 'https://public.example/back']
    fake = install(lambda request: response(status=302, headers={'location': locations.pop(0)}) if locations else response())
    counter = budget()
    with client(credential_origin='https://public.example', operator_headers={'Cookie': 'session=secret', 'Authorization': 'Bearer secret', 'User-Agent': 'Tool/1'}) as source:
        result = source.get('https://public.example/', budget=counter, headers={'Referer': 'https://public.example/view?private=secret'})
    assert result.content == b'ok'
    assert counter.snapshot().requests == 3 and counter.snapshot().redirects == 2
    assert fake.calls[0].headers['cookie'] == 'session=secret'
    for request in fake.calls[1:]:
        assert 'cookie' not in request.headers and 'authorization' not in request.headers
    assert fake.calls[0].headers['referer'] == 'https://public.example/view'


def test_redirect_has_independent_five_hop_ceiling(install):
    fake = install(lambda request: response(status=302, headers={'location': '/again'}))
    with client() as source:
        with pytest.raises(OutboundBudgetError):
            source.get('https://public.example/', budget=budget(redirects=100, requests=100))
    assert len(fake.calls) == 6


def test_platform_policy_can_disable_redirects(install):
    fake = install(lambda request: response(status=302, headers={'location': '/same'}))
    with client(policy=OutboundPolicy(follow_redirects=False)) as source:
        with pytest.raises(OutboundPolicyError):
            source.get('https://public.example/', budget=budget())
    assert len(fake.calls) == 1


@pytest.mark.parametrize('headers', [
    {'X-Extractor-Secret': 'secret'}, {'Proxy-Authorization': 'secret'},
    {'Host': '127.0.0.1'}, {'Cookie': 'secret'}, {'Authorization': 'secret'},
    {'User-Agent': 'safe\r\nCookie: secret'}, {'Bad\r\nKey': 'value'},
    {'Referer': 'https://user:secret@public.example/'}, {'Accept-Encoding': 'br'},
])
def test_runtime_headers_are_narrow_and_control_characters_rejected(install, headers):
    fake = install(lambda request: response())
    with client() as source:
        with pytest.raises(OutboundPolicyError):
            source.get('https://public.example/', budget=budget(), headers=headers)
    assert fake.calls == []


@pytest.mark.parametrize('encoding,encoded', [
    ('identity', b'hello'), ('gzip', gzip.compress(b'hello')),
    ('deflate', zlib.compress(b'hello')), ('gzip', gzip.compress(b'he') + gzip.compress(b'llo')),
])
def test_raw_and_decoded_accounting_uses_actual_stream(install, encoding, encoded):
    wire = Wire([encoded[:2], encoded[2:]])
    install(lambda request: httpx.Response(200, headers={'Content-Encoding': encoding}, stream=wire))
    counter = budget()
    with client() as source:
        with source.stream('GET', 'https://public.example/', budget=counter) as result:
            assert b''.join(result.iter_bytes()) == b'hello'
    assert counter.snapshot().raw_bytes == len(encoded)
    assert counter.snapshot().decoded_bytes == 5 and wire.closed


@pytest.mark.parametrize('length', [None, '1', '10000000000'])
def test_raw_over_limit_closes_actual_stream_even_without_truthful_length(install, length):
    wire = Wire([b'abcd', b'e'])
    install(lambda request: httpx.Response(200, headers={} if length is None else {'Content-Length': length}, stream=wire))
    counter = budget(raw_bytes=4, response_raw_bytes=4)
    with client() as source:
        with pytest.raises(OutboundBudgetError) as caught:
            source.get('https://public.example/', budget=counter)
        with pytest.raises(OutboundBudgetError):
            source.get('https://public.example/', budget=counter)
    assert caught.value.code == 'source_too_large' and wire.closed


def test_compression_bomb_has_bounded_output_and_closes_stream(install):
    payload = gzip.compress(b'x' * (2 * 1024 * 1024))
    wire = Wire([payload])
    install(lambda request: httpx.Response(200, headers={'Content-Encoding': 'gzip'}, stream=wire))
    counter = budget(decoded_bytes=31, response_decoded_bytes=31)
    with client() as source:
        with pytest.raises(OutboundBudgetError):
            source.get('https://public.example/', budget=counter)
    assert wire.closed and counter.snapshot().decoded_bytes <= 31


@pytest.mark.parametrize('encoding,encoded', [
    ('br', b'body'), ('gzip, deflate', b'body'),
    ('gzip', gzip.compress(b'hello')[:-1]), ('gzip', gzip.compress(b'hello') + b'garbage'),
    ('deflate', zlib.compress(b'hello')[:-1]), ('deflate', zlib.compress(b'hello') + b'garbage'),
])
def test_unsupported_truncated_or_trailing_compressed_data_fails_closed(install, encoding, encoded):
    wire = Wire([encoded])
    install(lambda request: httpx.Response(200, headers={'Content-Encoding': encoding}, stream=wire))
    with client() as source:
        with pytest.raises(OutboundUnavailableError):
            source.get('https://public.example/?token=secret', budget=budget())
    assert wire.closed


def test_exact_decoded_limit_is_not_treated_as_unlimited_decoder_output(install):
    encoded = gzip.compress(b'hello')
    install(lambda request: httpx.Response(200, headers={'Content-Encoding': 'gzip'}, stream=Wire([encoded])))
    with client() as source:
        result = source.get('https://public.example/', budget=budget(decoded_bytes=5, response_decoded_bytes=5))
    assert result.content == b'hello'


def test_child_cannot_reset_parent_cumulative_budget(install):
    install(lambda request: response(b'abc'))
    parent = budget(raw_bytes=5, decoded_bytes=5, children=2)
    with client() as source:
        assert source.get('https://public.example/', budget=parent.child(BudgetLimits())).content == b'abc'
        with pytest.raises(OutboundBudgetError):
            source.get('https://public.example/', budget=parent.child(BudgetLimits()))


def test_head_returns_headers_without_reading_a_body(install):
    wire = Wire([b'forbidden body'])
    install(lambda request: httpx.Response(200, headers={'Content-Length': '500'}, stream=wire))
    with client() as source:
        result = source.head('https://public.example/', budget=budget())
    assert result.status_code == 200 and result.headers['Content-Length'] == '500'
    assert result.content == b'' and wire.closed and wire.reads == 0


def test_error_response_body_is_still_limited(install):
    wire = Wire([b'12345'])
    install(lambda request: httpx.Response(500, stream=wire))
    with client() as source:
        with pytest.raises(OutboundBudgetError):
            source.get('https://public.example/', budget=budget(response_raw_bytes=4))
    assert wire.closed


@pytest.mark.parametrize('error', [httpx.ConnectError, httpx.ProxyError, httpx.RemoteProtocolError, httpx.ReadTimeout])
def test_transport_errors_are_fixed_nonretryable_and_drop_sensitive_exception_chains(install, error):
    def broken(request):
        raise error('https://user:secret@private.example/?signed=secret')
    fake = install(broken)
    with client() as source:
        with pytest.raises((OutboundUnavailableError, OutboundBudgetError)) as caught:
            source.get('https://public.example/?signed=secret', budget=budget())
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert caught.value.retryable is False and 'secret' not in str(caught.value)
    assert len(fake.calls) == 1


def test_deadline_checked_after_each_read_and_closes_actual_stream(install):
    now = [0.0]
    wire = Wire([b'a', b'b'], before=lambda: now.__setitem__(0, now[0] + 0.6))
    install(lambda request: httpx.Response(200, stream=wire))
    counter = OutboundBudget(BudgetLimits(seconds=1), clock=lambda: now[0])
    with client() as source:
        with pytest.raises(OutboundBudgetError) as caught:
            source.get('https://public.example/', budget=counter)
    assert caught.value.code == 'source_timeout' and wire.closed


def test_stream_context_closes_on_consumer_abandonment(install):
    wire = Wire([b'a', b'b'])
    install(lambda request: httpx.Response(200, stream=wire))
    with client() as source:
        with source.stream('GET', 'https://public.example/', budget=budget()) as result:
            assert next(result.iter_bytes()) == b'a'
    assert wire.closed and wire.reads == 1


def test_narrow_response_does_not_expose_raw_client_response_or_sensitive_repr(install):
    install(lambda request: response(b'{"ok": true}', headers={'Content-Type': 'application/json'}))
    with client() as source:
        result = source.get('https://public.example/?signed=secret', budget=budget())
    assert result.json() == {'ok': True}
    assert result.text == '{"ok": true}'
    for obj in (result, source):
        assert not hasattr(obj, 'request') and not hasattr(obj, 'send')
        assert 'secret' not in repr(obj)


def test_credentials_require_explicit_operator_origin(install):
    fake = install(lambda request: response())
    with pytest.raises(OutboundPolicyError):
        client(operator_headers={'Cookie': 'session=secret'})
    assert fake.calls == []


def test_credentials_cannot_follow_another_initial_url_on_reused_client(install):
    fake = install(lambda request: response())
    with client(credential_origin='https://public.example', operator_headers={'Cookie': 'session=secret'}) as source:
        source.get('https://other.example/', budget=budget())
        source.get('https://public.example/', budget=budget())
    assert 'cookie' not in fake.calls[0].headers
    assert fake.calls[1].headers['cookie'] == 'session=secret'


@pytest.mark.parametrize('origin', ['http://public.example', 'https://public.example/path', 'https://public.example/?token=secret', 'https://u:p@public.example/'])
def test_credential_origin_is_https_origin_without_path_or_secrets(install, origin):
    install(lambda request: response())
    with pytest.raises(OutboundPolicyError):
        client(credential_origin=origin, operator_headers={'Authorization': 'Bearer secret'})


def test_set_cookie_is_not_persisted_in_a_hidden_client_jar(install):
    fake = install(lambda request: response(headers={'Set-Cookie': 'session=untrusted; Path=/'}))
    with client() as source:
        source.get('https://public.example/one', budget=budget())
        source.get('https://public.example/two', budget=budget())
    assert all('cookie' not in request.headers for request in fake.calls)


def test_httpx_stream_error_is_sanitized_and_closes_wire(install):
    class Broken(Wire):
        def __iter__(self):
            raise httpx.StreamError('signed=secret')
            yield b''
    wire = Broken([])
    install(lambda request: httpx.Response(200, stream=wire))
    with client() as source:
        with pytest.raises(OutboundUnavailableError) as caught:
            source.get('https://public.example/?token=secret', budget=budget())
    assert caught.value.__context__ is None and caught.value.__cause__ is None and wire.closed


def test_real_httpx_proxy_transport_uses_only_proxy_backend_and_preserves_tls_host(monkeypatch, caplog):
    """Real HTTPTransport/httpcore HTTPProxy; only network I/O is synthetic.

    It proves client routing/CONNECT/TLS arguments, not actual Smokescreen DNS
    policy or real TLS handshake, Linux firewall isolation, or source access.
    """
    import ssl
    from httpcore._backends.sync import SyncBackend

    connections = []
    writes = []
    tls = []
    reads = []

    class FakeNetwork:
        def __init__(self):
            self.responses = [b'HTTP/1.1 200 Connection established\r\n\r\n',
                              b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok']

        def read(self, max_bytes, timeout=None):
            reads.append((max_bytes, timeout))
            return self.responses.pop(0)

        def write(self, buffer, timeout=None):
            writes.append(bytes(buffer))

        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            tls.append((server_hostname, ssl_context.check_hostname, ssl_context.verify_mode, timeout))
            return self

        def get_extra_info(self, info):
            return None

        def close(self):
            pass

    def connect(backend, host, port, timeout=None, local_address=None, socket_options=None):
        connections.append((host, port, timeout))
        return FakeNetwork()

    monkeypatch.setattr(SyncBackend, 'connect_tcp', connect)
    monkeypatch.setenv('HTTPS_PROXY', 'http://evil.example:9999')
    monkeypatch.setenv('NO_PROXY', '*')
    caplog.set_level('INFO')
    with client() as source:
        assert source.get('https://public.example/video?token=secret', budget=budget()).content == b'ok'
    assert [(host, port) for host, port, timeout in connections] == [('127.0.0.1', 4750)]
    assert writes[0].startswith(b'CONNECT public.example:443 HTTP/1.1\r\n')
    assert b'Proxy-Authorization: Basic ' in writes[0]
    source_headers = b''.join(writes[1:])
    assert b'GET /video?token=secret HTTP/1.1\r\n' in source_headers
    assert b'Host: public.example\r\n' in source_headers
    assert b'proxy-authorization' not in source_headers.lower()
    assert tls[0][:3] == ('public.example', True, ssl.CERT_REQUIRED)
    assert all(0 < timeout <= 10 and size <= 65536 for size, timeout in reads)
    assert 'token=secret' not in caplog.text and 'proxy-secret' not in caplog.text


def test_httpx_invalid_url_during_transport_construction_drops_original_context(monkeypatch):
    def broken(**kwargs):
        raise httpx.InvalidURL('http://proxy-user:proxy-secret@bad-proxy')
    monkeypatch.setattr(httpx, 'HTTPTransport', broken)
    with pytest.raises(OutboundUnavailableError) as caught:
        client()
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'proxy-secret' not in str(caught.value)


@pytest.mark.parametrize('encoding,encode', [('gzip', gzip.compress), ('deflate', zlib.compress)])
def test_large_valid_compressed_stream_decodes_in_bounded_chunks(install, encoding, encode):
    body = b'abc' * 70000
    encoded = encode(body)
    wire = Wire([bytes([value]) for value in encoded])
    install(lambda request: httpx.Response(200, headers={'Content-Encoding': encoding}, stream=wire))
    with client() as source:
        with source.stream('GET', 'https://public.example/', budget=budget()) as result:
            chunks = list(result.iter_bytes())
    assert b''.join(chunks) == body and max(map(len, chunks)) <= 65536 and wire.closed


def test_invalid_initial_literal_never_requests_proxy(install):
    fake = install(lambda request: response())
    counter = budget()
    with client() as source:
        with pytest.raises(OutboundPolicyError):
            source.get('http://169.254.169.254/', budget=counter)
    assert fake.calls == [] and counter.snapshot().requests == 0


def test_existing_request_budget_is_not_reset_by_a_second_get(install):
    fake = install(lambda request: response())
    counter = budget(requests=1)
    with client() as source:
        assert source.get('https://public.example/', budget=counter).content == b'ok'
        with pytest.raises(OutboundBudgetError):
            source.get('https://public.example/', budget=counter)
    assert len(fake.calls) == 1


def test_second_redirect_send_uses_remaining_timeout(install):
    now = [0.0]
    def handler(request):
        if len(fake.calls) == 1:
            now[0] = 1.25
            return response(status=302, headers={'Location': '/final'})
        return response()
    fake = install(handler)
    counter = OutboundBudget(BudgetLimits(seconds=2), clock=lambda: now[0])
    with client() as source:
        assert source.get('https://public.example/', budget=counter).content == b'ok'
    assert fake.calls[0].extensions['timeout']['read'] == 2
    assert fake.calls[1].extensions['timeout']['read'] == 0.75


@pytest.mark.parametrize('status', [401, 403, 412, 429, 500, 503])
def test_http_status_error_preserves_source_status_without_application_auth_semantics(install, status):
    from app.services.outbound_httpx import ControlledHttpStatusError

    fake = install(lambda request: response(status=status))
    with client() as source:
        result = source.get('https://public.example/?signed=secret', budget=budget())
        assert result.status_code == status
        with pytest.raises(ControlledHttpStatusError) as caught:
            result.raise_for_status()
    error = caught.value
    assert error.source_status == status and error.status_code == 502
    assert error.public_detail() == {'error_type': 'source_http_error',
                                    'error': '来源返回失败状态', 'source_status': status}
    assert error.retryable is False and error.__context__ is None and error.__cause__ is None
    assert not hasattr(error, 'request') and not hasattr(error, 'response')
    assert 'secret' not in str(error) and len(fake.calls) == 1


def test_pool_timeout_is_safe_busy_error_without_retry_or_sensitive_chain(install):
    from app.services.outbound_httpx import ControlledHttpBusyError

    def fail(request):
        raise httpx.PoolTimeout('signed=secret proxy-secret')
    fake = install(fail)
    with client() as source:
        with pytest.raises(ControlledHttpBusyError) as caught:
            source.get('https://public.example/?signed=secret', budget=budget())
    assert caught.value.status_code == 503 and caught.value.retryable is False
    assert caught.value.public_detail() == {'error_type': 'source_busy', 'error': '来源处理繁忙'}
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'secret' not in str(caught.value) and len(fake.calls) == 1


def test_real_http_forward_uses_proxy_and_absolute_target_with_original_host(transport_network):
    network = transport_network
    network.replies = [b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok']
    with client() as source:
        assert source.get('http://public.example/video?sig=a%2Fb', budget=budget()).content == b'ok'
    assert [(host, port) for host, port, timeout in network.connections] == [('127.0.0.1', 4750)]
    sent = b''.join(network.writes)
    assert sent.startswith(b'GET http://public.example/video?sig=a%2Fb HTTP/1.1\r\n')
    assert b'Host: public.example\r\n' in sent and b'Proxy-Authorization: Basic ' in sent
    assert network.tls == [] and network.closed >= 1


@pytest.mark.parametrize('phase', ['connect', 'tls'])
def test_real_transport_failure_does_not_retry_or_connect_direct(transport_network, phase):
    import httpcore

    network = transport_network
    if phase == 'connect':
        network.connect_error = httpcore.ConnectError('proxy-secret signed=secret')
    else:
        network.replies = [b'HTTP/1.1 200 Connection established\r\n\r\n']
        network.tls_error = httpcore.ConnectError('certificate signed=secret')
    with client() as source:
        with pytest.raises(OutboundUnavailableError) as caught:
            source.get('https://public.example/?signed=secret', budget=budget())
    assert [(host, port) for host, port, timeout in network.connections] == [('127.0.0.1', 4750)]
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'secret' not in str(caught.value)
    if phase == 'tls':
        assert network.closed >= 1 and len(network.tls) == 1


def test_real_stream_over_budget_closes_prefetched_chunk_before_decode(transport_network):
    network = transport_network
    network.replies = [b'HTTP/1.1 200 Connection established\r\n\r\n',
                       b'HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n' + b'x' * 65536,
                       b'not consumed']
    counter = budget(raw_bytes=4, response_raw_bytes=4)
    with client() as source:
        with pytest.raises(OutboundBudgetError):
            source.get('https://public.example/', budget=counter)
    assert network.closed >= 1 and len(network.reads) == 2
    assert all(size <= 65536 for size, timeout in network.reads)
    assert counter.snapshot().decoded_bytes == 0


def test_real_body_timeout_remains_initial_cap_while_cooperative_deadline_stops_drip(transport_network):
    network = transport_network
    now = [0.0]
    network.replies = [b'HTTP/1.1 200 Connection established\r\n\r\n',
                       b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\na', b'b', b'c']
    network.before_read = lambda: now.__setitem__(0, now[0] + 0.3)
    counter = OutboundBudget(BudgetLimits(seconds=1), clock=lambda: now[0])
    with client() as source:
        with pytest.raises(OutboundBudgetError) as caught:
            source.get('https://public.example/', budget=counter)
    assert caught.value.code == 'source_timeout' and network.closed >= 1
    assert [timeout for size, timeout in network.reads] == [1.0] * 4
    assert counter.snapshot().raw_bytes == 2 and counter.snapshot().decoded_bytes == 2


def test_real_response_header_parse_is_bounded_by_httpcore(transport_network):
    network = transport_network
    network.replies = [b'HTTP/1.1 200 Connection established\r\n\r\n',
                       b'HTTP/1.1 200 OK\r\nX-Large: ' + b'x' * 200000]
    with client() as source:
        with pytest.raises(OutboundUnavailableError) as caught:
            source.get('https://public.example/?signed=secret', budget=budget())
    assert network.closed >= 1
    assert all(size <= 65536 for size, timeout in network.reads)
    assert len(network.reads) <= 3
    assert caught.value.__context__ is None and caught.value.__cause__ is None


def test_real_chunked_terminal_read_cannot_complete_after_deadline(transport_network):
    network = transport_network
    now = [0.0]
    network.replies = [b'HTTP/1.1 200 Connection established\r\n\r\n',
                       b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\na\r\n',
                       b'0\r\n\r\n']
    network.before_read = lambda: now.__setitem__(0, now[0] + 0.4)
    counter = OutboundBudget(BudgetLimits(seconds=1), clock=lambda: now[0])
    with client() as source:
        with pytest.raises(OutboundBudgetError) as caught:
            source.get('https://public.example/', budget=counter)
    assert caught.value.code == 'source_timeout' and network.closed >= 1
    assert len(network.reads) == 3 and counter.snapshot().raw_bytes == 1
