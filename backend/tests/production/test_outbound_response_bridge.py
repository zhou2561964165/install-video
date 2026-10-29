"""GET/HEAD bridge foundation over real HTTPX/httpcore and offline backends."""
import gzip
import json

import httpx
import pytest

from app.services import outbound_httpx
from app.services.outbound_budget import BudgetLimits, OutboundBudget, OutboundBudgetError, RequestLimits
from app.services.outbound_httpx import ControlledHttpStatusError
from app.services.outbound_policy import OutboundPolicyError, OutboundUnavailableError
from test_outbound_httpx import budget, client, install, response, transport_network


def reply(body=b'ok', *, status=b'200 OK', headers=b''):
    return (b'HTTP/1.1 ' + status + b'\r\nConnection: close\r\nContent-Length: '
            + str(len(body)).encode('ascii') + b'\r\n' + headers + b'\r\n' + body)


def assert_safe(error):
    assert 'secret' not in str(error) + repr(error)
    assert error.__context__ is None and error.__cause__ is None
    assert 'secret' not in json.dumps(error.public_detail())


def test_redirect_effective_url_and_repeated_headers_use_verified_final_target(transport_network, caplog):
    net = transport_network
    net.replies = [
        reply(b'', status=b'302 Found', headers=b'Location: /nested/manifest?sig=secret-final\r\n'),
        reply(headers=(b'Set-Cookie: first=a; Path=/\r\nSet-Cookie: second=b; Path=/\r\n'
                       b'X-Repeated: one\r\nX-Repeated: two\r\nX-Text: caf\xe9\r\n')),
    ]
    counter = budget()
    with client() as source:
        with source.exchange('GET', 'http://public.example/start?sig=secret-start', budget=counter) as result:
            assert result.effective_url == 'http://public.example/nested/manifest?sig=secret-final'
            with pytest.raises(AttributeError):
                result.effective_url = 'http://other.example/'
            items = result.header_items()
            assert isinstance(items, tuple)
            assert [(k, v) for k, v in items if k == 'set-cookie'] == [
                ('set-cookie', 'first=a; Path=/'), ('set-cookie', 'second=b; Path=/')]
            assert [(k, v) for k, v in items if k == 'x-repeated'] == [
                ('x-repeated', 'one'), ('x-repeated', 'two')]
            assert ('x-text', 'café') in items
            result.headers['x-repeated'] = 'mutated consumer view'
            assert result.header_items() == items
            assert 'secret' not in repr(result)
            assert not any(hasattr(result, name) for name in ('raw', 'request', 'client', 'transport'))
            assert result.content == b'ok'
    assert counter.snapshot().requests == 2 and counter.snapshot().redirects == 1
    assert 'secret' not in caplog.text
    assert net.closed == 2


@pytest.mark.parametrize('method,data', [
    ('POST', None), ('PUT', None), ('get', None), ('', None), (None, None),
    ('GET', b''), ('HEAD', b'body'), ('GET', 'body'), ('GET', iter([b'body'])),
])
def test_invalid_method_or_any_body_rejected_before_scope_count_or_send(transport_network, monkeypatch, method, data):
    counter = budget()
    def no_scope(*args, **kwargs):
        pytest.fail('invalid exchange created a request scope')
    monkeypatch.setattr(counter, 'request_scope', no_scope)
    with client() as source:
        with pytest.raises(OutboundPolicyError) as caught:
            with source.exchange(method, 'http://public.example/?sig=secret', budget=counter, data=data):
                pytest.fail('invalid exchange yielded a response')
    assert_safe(caught.value)
    assert counter.snapshot().requests == 0
    assert not transport_network.connections and not transport_network.writes


def test_exchange_yields_live_response_then_eof_closes_and_releases_registry(transport_network):
    net = transport_network
    net.replies = [reply()]
    counter = budget()
    with client() as source:
        with source.exchange('GET', 'http://public.example/', budget=counter) as result:
            assert not result._closed and result in source._responses and net.closed == 0
            assert list(result.iter_bytes()) == [b'ok']
            assert result._closed and not source._responses and net.closed == 1
            result.close()
        assert net.closed == 1
    assert counter.snapshot().raw_bytes == counter.snapshot().decoded_bytes == 2


def test_head_has_no_body_accounting_and_preserves_headers(transport_network):
    net = transport_network
    net.replies = [reply(b'', headers=b'X-Text: head\r\n')]
    counter = budget()
    with client() as source:
        with source.exchange('HEAD', 'http://public.example/', budget=counter) as result:
            assert ('x-text', 'head') in result.header_items()
            assert result.read() == b''
        assert not source._responses
    assert counter.snapshot().requests == 1
    assert counter.snapshot().raw_bytes == counter.snapshot().decoded_bytes == 0
    assert b'HEAD http://public.example/ HTTP/1.1' in b''.join(net.writes)
    assert net.closed == 1


def test_early_close_is_idempotent_and_later_exchange_retains_original_budget(transport_network):
    net = transport_network
    net.replies = [reply(), reply(b'next')]
    counter = budget(requests=2)
    with client() as source:
        with source.exchange('GET', 'http://public.example/first', budget=counter) as result:
            result.close()
            result.close()
            assert not source._responses and net.closed == 1
            with pytest.raises(OutboundBudgetError) as caught:
                result.read()
            assert_safe(caught.value)
        with source.exchange('GET', 'http://public.example/next', budget=counter) as second:
            assert second.read() == b'next'
    assert counter.snapshot().requests == 2 and counter.snapshot().decoded_bytes == 4
    assert net.closed == 2


def test_client_close_inside_two_active_exchanges_closes_snapshot_without_callback_cycle(transport_network):
    import weakref
    net = transport_network
    net.replies = [reply(b'one'), reply(b'two')]
    counter = budget()
    source = client()
    first_cm = source.exchange('GET', 'http://public.example/one', budget=counter)
    second_cm = source.exchange('GET', 'http://public.example/two', budget=counter)
    first = first_cm.__enter__()
    second = second_cm.__enter__()
    assert len(source._responses) == 2
    source_ref = weakref.ref(source)
    source.close()
    source.close()
    assert not source._responses and first._closed and second._closed and net.closed == 2
    for result in (first, second):
        with pytest.raises(OutboundBudgetError) as caught:
            result.read()
        assert_safe(caught.value)
        result.close()
    first_cm.__exit__(None, None, None)
    second_cm.__exit__(None, None, None)
    assert net.closed == 2
    del source
    assert source_ref() is None


@pytest.mark.parametrize('failure', ['consumer', 'status'])
def test_consumer_and_explicit_status_failure_close_exchange_without_auto_raising(transport_network, failure):
    net = transport_network
    net.replies = [reply(b'error body', status=b'404 Not Found')]
    source = client()
    expected = RuntimeError if failure == 'consumer' else ControlledHttpStatusError
    try:
        with pytest.raises(expected) as caught:
            with source.exchange('GET', 'http://public.example/?sig=secret', budget=budget()) as result:
                assert result.status_code == 404 and not result._closed
                if failure == 'consumer':
                    raise RuntimeError('local consumer stopped')
                result.raise_for_status()
        assert result._closed and not source._responses and net.closed == 1
        if failure == 'status':
            assert caught.value.source_status == 404
            assert_safe(caught.value)
    finally:
        source.close()


@pytest.mark.parametrize('stage', ['response_construct', 'response_register', 'request_construct'])
def test_construction_and_registration_failure_release_owned_resources(transport_network, monkeypatch, stage):
    net = transport_network
    net.replies = [reply()]
    counter = budget()
    def bad_constructor(*args, **kwargs):
        raise ValueError('raw sig=secret')
    class BadRegistry(set):
        def add(self, value):
            raise RuntimeError('local registration failure')
    with client() as source:
        if stage == 'response_construct':
            monkeypatch.setattr(outbound_httpx, 'ControlledResponse', bad_constructor)
        elif stage == 'request_construct':
            monkeypatch.setattr(httpx, 'Request', bad_constructor)
        else:
            source._responses = BadRegistry()
        error = RuntimeError if stage == 'response_register' else OutboundUnavailableError
        with pytest.raises(error) as caught:
            with source.exchange('GET', 'http://public.example/?sig=secret', budget=counter):
                pytest.fail('failed constructor yielded a response')
        assert not source._responses
        if stage != 'response_register':
            assert_safe(caught.value)
    assert counter.snapshot().requests == 1
    assert net.closed == (0 if stage == 'request_construct' else 1)


def test_read_transport_error_is_safe_and_releases_response(transport_network):
    net = transport_network
    # The real h11 parser discovers truncated content while reading to EOF.
    net.replies = [b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: close\r\n\r\nshort']
    with client() as source:
        with pytest.raises(OutboundUnavailableError) as caught:
            with source.exchange('GET', 'http://public.example/?sig=secret', budget=budget()) as result:
                result.read()
        assert result._closed and not source._responses and net.closed == 1
    assert_safe(caught.value)


def test_exchange_preserves_decoded_body_and_wire_header_contract(transport_network):
    body = gzip.compress(b'decoded payload')
    net = transport_network
    net.replies = [reply(body, headers=b'Content-Encoding: gzip\r\n')]
    counter = budget()
    with client() as source:
        with source.exchange('GET', 'http://public.example/', budget=counter) as result:
            assert result.read() == b'decoded payload'
            assert ('content-encoding', 'gzip') in result.header_items()
            assert ('content-length', str(len(body))) in result.header_items()
    assert counter.snapshot().raw_bytes == len(body)
    assert counter.snapshot().decoded_bytes == len(b'decoded payload')


def test_exchange_request_cap_still_locks_original_budget(transport_network):
    net = transport_network
    net.replies = [reply(b'1234')]
    counter = budget(response_decoded_bytes=3)
    with client() as source:
        with pytest.raises(OutboundBudgetError) as caught:
            with source.exchange('GET', 'http://public.example/?sig=secret', budget=counter,
                                 request_limits=RequestLimits(response_decoded_bytes=100)) as result:
                result.read()
        assert not source._responses and result._closed and net.closed == 1
        with pytest.raises(OutboundBudgetError):
            with source.exchange('GET', 'http://public.example/again', budget=counter):
                pytest.fail('exhausted budget reused')
    assert_safe(caught.value)
    assert counter.snapshot().requests == 1


def test_exchange_redirect_phase_remains_one_scope(transport_network):
    net = transport_network
    net.replies = [reply(b'', status=b'302 Found', headers=b'Location: /final?sig=secret\r\n'), reply()]
    now = [0.0]
    net.before_read = lambda: now.__setitem__(0, now[0] + .6)
    counter = OutboundBudget(BudgetLimits(seconds=10), clock=lambda: now[0])
    with client() as source:
        with pytest.raises(OutboundBudgetError) as caught:
            with source.exchange('GET', 'http://public.example/start', budget=counter,
                                 request_limits=RequestLimits(seconds=1)):
                pytest.fail('expired phase yielded a response')
        assert not source._responses and net.closed == 2
        with pytest.raises(OutboundBudgetError):
            counter.request_scope()
    assert caught.value.code == 'source_timeout'
    assert_safe(caught.value)
    assert counter.snapshot().requests == 2


def test_get_head_stream_signatures_and_buffered_lifecycle_remain_compatible(install):
    import inspect
    fake = install(lambda request: response())
    assert str(inspect.signature(outbound_httpx.ControlledHttpxClient.get)) == (
        '(self, url, *, budget, headers=None, request_limits=None)')
    assert str(inspect.signature(outbound_httpx.ControlledHttpxClient.head)) == (
        '(self, url, *, budget, headers=None, request_limits=None)')
    assert str(inspect.signature(outbound_httpx.ControlledHttpxClient.stream)) == (
        '(self, method, url, *, budget, headers=None, request_limits=None)')
    with client() as source:
        get = source.get('http://public.example/', budget=budget())
        head = source.head('http://public.example/', budget=budget())
        assert get._closed and get.content == b'ok' and head._closed and head.content == b''
        assert not source._responses
        with source.stream('GET', 'http://public.example/', budget=budget()) as result:
            assert not result._closed
            assert result.content == b'ok'
    assert fake.closed
