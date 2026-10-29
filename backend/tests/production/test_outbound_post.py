"""Explicit bounded POST opt-in; all source traffic is synthetic and offline."""
import io
import json

import httpx
import pytest

from app.services.outbound_budget import BudgetLimits, OutboundBudget, OutboundBudgetError, RequestLimits
from app.services.outbound_policy import OutboundPolicy, OutboundPolicyError, OutboundUnavailableError
from test_outbound_httpx import budget, client, install, response, transport_network
from test_outbound_response_bridge import assert_safe, reply


API_HEADERS = frozenset({'origin', 'x-youtube-client-name', 'x-youtube-client-version', 'x-goog-visitor-id'})
API_VALUES = {'Origin': 'https://www.youtube.com/', 'X-YouTube-Client-Name': '1',
              'X-YouTube-Client-Version': '2.20260819.01.00', 'X-Goog-Visitor-Id': 'synthetic-secret'}
TOKEN = b'{"token":"synthetic-secret"}'


def post_client(**kwargs):
    return client(request_body_limit=64, api_headers=API_HEADERS, **kwargs)


def captured_requests(net):
    """Read actual HTTP/1.1 bytes emitted by HTTPcore to the fake proxy."""
    wire = b''.join(net.writes)
    result = []
    while wire:
        head, separator, rest = wire.partition(b'\r\n\r\n')
        assert separator
        lines = head.split(b'\r\n')
        headers = dict((key.lower(), value.strip()) for key, value in
                       (line.split(b':', 1) for line in lines[1:]))
        size = int(headers.get(b'content-length', b'0'))
        result.append((lines[0], headers, rest[:size]))
        wire = rest[size:]
    return result


@pytest.mark.parametrize('options', [
    {'request_body_limit': True}, {'request_body_limit': 0}, {'request_body_limit': -1},
    {'request_body_limit': 1.0}, {'request_body_limit': 1024 * 1024 + 1},
    {'request_header_limit': True}, {'request_header_limit': 0},
    {'request_header_limit': 16385}, {'request_header_limit': 1.0},
    {'api_headers': ['origin']}, {'api_headers': {'origin'}},
    {'api_headers': frozenset({'Origin'}), 'request_body_limit': 64},
    {'api_headers': frozenset({'x-arbitrary-secret'}), 'request_body_limit': 64},
    {'api_headers': frozenset({'authorization'}), 'request_body_limit': 64},
    {'api_headers': frozenset({'x-goog-visitor-id'})},
])
def test_invalid_constructor_bounds_or_api_names_never_construct_transport(monkeypatch, options):
    def forbidden(**kwargs):
        pytest.fail('invalid POST configuration constructed a transport')
    monkeypatch.setattr(httpx, 'HTTPTransport', forbidden)
    with pytest.raises(ValueError) as caught:
        client(**options)
    assert 'secret' not in str(caught.value) + repr(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


@pytest.mark.parametrize('data', [None, b'', TOKEN])
def test_post_is_disabled_by_default_even_for_empty_bytes(transport_network, data):
    counter = budget()
    with client() as source:
        with pytest.raises(OutboundPolicyError) as caught:
            with source.exchange('POST', 'http://public.example/?sig=secret', data=data, budget=counter):
                pytest.fail('default client enabled POST')
    assert_safe(caught.value)
    assert counter.snapshot().requests == 0 and not transport_network.writes


@pytest.mark.parametrize('data', [None, True, bytearray(b'x'), memoryview(b'x'), io.BytesIO(b'x'), (b'x',)])
def test_non_bytes_body_never_reads_or_creates_scope(transport_network, monkeypatch, data):
    counter = budget()
    def forbidden(*args, **kwargs):
        pytest.fail('invalid body entered request scope')
    monkeypatch.setattr(counter, 'request_scope', forbidden)
    with post_client() as source:
        with pytest.raises(OutboundPolicyError) as caught:
            with source.exchange('POST', 'http://public.example/?sig=secret', data=data, budget=counter):
                pytest.fail('invalid body yielded response')
    assert_safe(caught.value)
    assert counter.snapshot().requests == 0 and not transport_network.connections


def test_unbounded_iterable_and_bytes_subclass_are_not_consumed(transport_network):
    class NeverConsume:
        def __iter__(self):
            pytest.fail('body iterable was consumed')
    class SubBytes(bytes):
        def __len__(self):
            pytest.fail('body subclass length was trusted')
    counter = budget()
    with post_client() as source:
        for data in (NeverConsume(), SubBytes(b'x')):
            with pytest.raises(OutboundPolicyError):
                with source.exchange('POST', 'http://public.example/', data=data, budget=counter):
                    pytest.fail('non-exact bytes accepted')
    assert counter.snapshot().requests == 0 and not transport_network.writes


@pytest.mark.parametrize('data', [b'', b'x' * 64])
def test_body_limit_includes_empty_and_exact_boundary_with_computed_length(transport_network, data):
    net = transport_network
    net.replies = [reply()]
    with post_client() as source:
        with source.exchange('POST', 'http://public.example/api', budget=budget(), data=data) as result:
            assert not result._closed and result.read() == b'ok'
        assert not source._responses
    sent = captured_requests(net)
    assert len(sent) == 1 and sent[0][0] == b'POST http://public.example/api HTTP/1.1'
    assert sent[0][1][b'content-length'] == str(len(data)).encode() and sent[0][2] == data
    assert b'transfer-encoding' not in sent[0][1] and net.closed == 1


def test_one_byte_over_body_limit_has_zero_scope_count_and_send(transport_network, monkeypatch):
    counter = budget()
    def forbidden(*args, **kwargs):
        pytest.fail('oversized body created a scope')
    monkeypatch.setattr(counter, 'request_scope', forbidden)
    with post_client() as source:
        with pytest.raises(OutboundPolicyError) as caught:
            with source.exchange('POST', 'http://public.example/?sig=secret', budget=counter, data=b'x' * 65):
                pytest.fail('oversized body sent')
    assert_safe(caught.value)
    assert counter.snapshot().requests == 0 and not transport_network.connections


@pytest.mark.parametrize('content_type,expected,body', [
    ('Application/JSON ; CHARSET=UTF-8', 'application/json; charset=utf-8', b'{"n":1}'),
    (' application/x-www-form-urlencoded ', 'application/x-www-form-urlencoded', b'n=1&value=a%2Fb'),
    ('application/json', 'application/json', b'not parsed as JSON by transport'),
])
def test_json_form_content_type_normalized_without_parsing_body(transport_network, content_type, expected, body):
    net = transport_network
    net.replies = [reply()]
    with post_client() as source:
        with source.exchange('POST', 'http://public.example/api', budget=budget(),
                             data=body, headers={'Content-Type': content_type, 'Accept': 'application/json'}) as result:
            assert result.read() == b'ok'
    sent = captured_requests(net)[0]
    assert sent[1][b'content-type'] == expected.encode() and sent[2] == body


BAD_HEADERS = [
    {'Host': 'private.example'}, {'Content-Length': '1'}, {'Transfer-Encoding': 'chunked'},
    {'Connection': 'keep-alive'}, {'Proxy-Authorization': 'secret'}, {'Cookie': 'secret'},
    {'Authorization': 'Bearer secret'}, {'Content-Encoding': 'gzip'}, {'X-Arbitrary': 'value'},
    {'Content-Type': 'text/plain'}, {'Content-Type': 'application/json; charset=latin1'},
    {'Content-Type': 'application/json\r\nX-Test: secret'}, {'Content-Type': True},
    {'Content-Type': 'application/json', 'content-type': 'application/json'},
    {'X-YouTube-Client-Name': '1' * 65}, {'X-YouTube-Client-Version': 'v' * 129},
    {'X-Goog-Visitor-Id': 'v' * 2049}, {'X-Goog-Visitor-Id': 'x\nsecret'},
    {'Origin': 'http://www.youtube.com'}, {'Origin': 'https://www.youtube.com/path'},
    {'Origin': 'https://user:secret@www.youtube.com'}, {'Origin': 'https://www.youtube.com/?sig=secret'},
    {'Origin': 'https://www.youtube.com/#secret'}, {'Origin': 'https://127.0.0.1/'},
    {str(i): 'x' for i in range(33)},
]


@pytest.mark.parametrize('headers', BAD_HEADERS)
def test_invalid_post_headers_have_zero_scope_count_and_send(transport_network, monkeypatch, headers):
    counter = budget()
    def forbidden(*args, **kwargs):
        pytest.fail('invalid headers entered scope')
    monkeypatch.setattr(counter, 'request_scope', forbidden)
    with post_client() as source:
        with pytest.raises(OutboundPolicyError) as caught:
            with source.exchange('POST', 'http://public.example/?sig=secret', budget=counter,
                                 data=TOKEN, headers=headers):
                pytest.fail('invalid headers yielded response')
    assert_safe(caught.value)
    assert counter.snapshot().requests == 0 and not transport_network.connections


def test_api_headers_require_explicit_subset_and_are_not_added_to_get_or_operator_inputs(install):
    fake = install(lambda request: response())
    counter = budget()
    with client(request_body_limit=64) as source:
        with pytest.raises(OutboundPolicyError):
            with source.exchange('POST', 'https://public.example/', budget=counter, data=TOKEN, headers=API_VALUES):
                pytest.fail('unconfigured API headers accepted')
    with post_client() as source:
        for method in ('GET', 'HEAD'):
            with pytest.raises(OutboundPolicyError):
                with source.exchange(method, 'https://public.example/', budget=counter, headers=API_VALUES):
                    pytest.fail('new headers added to GET/HEAD')
        with pytest.raises(OutboundPolicyError):
            with source.stream('POST', 'https://public.example/', budget=counter):
                pytest.fail('old stream gained POST')
    with pytest.raises(OutboundPolicyError):
        post_client(operator_headers={'Content-Type': 'application/json'})
    assert counter.snapshot().requests == 0 and not fake.calls


def test_merged_headers_total_is_bounded_and_can_only_tighten(install):
    fake = install(lambda request: response())
    counter = budget()
    # Each input is individually below the old 16KiB cap; the merged input is not.
    with client(operator_headers={'User-Agent': 'a' * 9000}) as source:
        with pytest.raises(OutboundPolicyError):
            source.get('http://public.example/', budget=counter, headers={'Accept': 'b' * 9000})
    with client(request_header_limit=128, operator_headers={'User-Agent': 'a' * 60}) as source:
        with pytest.raises(OutboundPolicyError):
            source.get('http://public.example/', budget=counter, headers={'Accept': 'b' * 60})
    assert counter.snapshot().requests == 0 and not fake.calls


def test_header_total_exact_limit_includes_automatic_accept_encoding(install):
    fake = install(lambda request: response())
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    size = sum(len(k) + len(v) for k, v in headers.items()) + len('accept-encoding') + len('gzip, deflate, identity')
    with post_client(request_header_limit=size) as source:
        with source.exchange('POST', 'http://public.example/', budget=budget(), data=TOKEN, headers=headers) as result:
            assert result.read() == b'ok'
    with post_client(request_header_limit=size - 1) as source:
        with pytest.raises(OutboundPolicyError):
            with source.exchange('POST', 'http://public.example/', budget=budget(), data=TOKEN, headers=headers):
                pytest.fail('fixed automatic header excluded from bound')
    assert len(fake.calls) == 1


def test_locked_innertube_shape_is_only_a_synthetic_bounded_request(transport_network, caplog):
    net = transport_network
    net.replies = [reply(b'{"ok":true}')]
    body = b'{"context":{"client":{"clientName":"WEB"}},"videoId":"fixture"}'
    assert len(body) <= 64
    with post_client() as source:
        with source.exchange('POST', 'http://public.example/youtubei/v1/player?key=secret', budget=budget(),
                             data=body, headers=API_VALUES | {'Content-Type': 'application/json'}) as result:
            assert result.json() == {'ok': True} and 'secret' not in repr(result)
        assert not source._responses
    _, headers, sent_body = captured_requests(net)[0]
    assert headers[b'origin'] == b'https://www.youtube.com'
    assert headers[b'x-goog-visitor-id'] == b'synthetic-secret' and sent_body == body
    assert 'secret' not in caplog.text


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_post_redirect_method_body_entity_headers_and_shared_counter(transport_network, status):
    net = transport_network
    net.replies = [reply(b'', status=str(status).encode() + b' Redirect', headers=b'Location: /next\r\n'), reply()]
    counter = budget()
    with post_client() as source:
        with source.exchange('POST', 'http://public.example/start', budget=counter,
                             data=TOKEN, headers=API_VALUES | {'Content-Type': 'application/json'}) as result:
            assert result.read() == b'ok' and result.effective_url == 'http://public.example/next'
    sent = captured_requests(net)
    assert len(sent) == 2 and sent[0][2] == TOKEN
    if status in (301, 302, 303):
        assert sent[1][0].startswith(b'GET ') and sent[1][2] == b''
        assert b'content-type' not in sent[1][1] and b'content-length' not in sent[1][1]
    else:
        assert sent[1][0].startswith(b'POST ') and sent[1][2] == TOKEN
        assert sent[1][1][b'content-type'] == b'application/json'
    assert sent[1][1][b'x-goog-visitor-id'] == b'synthetic-secret'
    assert counter.snapshot().requests == 2 and counter.snapshot().redirects == 1 and net.closed == 2


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_get_head_303_keeps_original_method_without_body(transport_network, method):
    net = transport_network
    net.replies = [reply(b'', status=b'303 Other', headers=b'Location: /next\r\n'), reply(b'')]
    with post_client() as source:
        with source.exchange(method, 'http://public.example/start', budget=budget()) as result:
            assert result.read() == b''
    assert [row[0].split()[0] for row in captured_requests(net)] == [method.encode()] * 2


@pytest.mark.parametrize('status', [307, 308])
@pytest.mark.parametrize('data', [b'', TOKEN])
def test_cross_origin_post_replay_is_terminal_before_second_charge_or_send(transport_network, caplog, status, data):
    net = transport_network
    net.replies = [reply(b'', status=str(status).encode() + b' Redirect',
                         headers=b'Location: http://other.example/api?sig=secret-target\r\n')]
    counter = budget()
    with post_client() as source:
        with pytest.raises(OutboundUnavailableError) as caught:
            with source.exchange('POST', 'http://public.example/api?sig=secret-source', budget=counter,
                                 data=data, headers=API_VALUES):
                pytest.fail('cross origin POST body replay yielded')
        assert not source._responses
    assert_safe(caught.value)
    assert counter.snapshot().requests == 1 and counter.snapshot().redirects == 0
    assert len(captured_requests(net)) == 1 and len(net.connections) == 1 and net.closed == 1
    assert 'secret' not in caplog.text


@pytest.mark.parametrize('status', [301, 302, 303])
def test_cross_origin_get_conversion_strips_credentials_and_all_api_headers_permanently(install, status):
    locations = ['https://other.example/api', 'https://public.example/back']
    fake = install(lambda request: response(status=status, headers={'Location': locations.pop(0)})
                   if locations else response())
    with post_client(credential_origin='https://public.example',
                     operator_headers={'Cookie': 'session=secret', 'Authorization': 'Bearer secret'}) as source:
        with source.exchange('POST', 'https://public.example/start', budget=budget(), data=TOKEN,
                             headers=API_VALUES | {'Content-Type': 'application/json'}) as result:
            assert result.read() == b'ok'
    assert len(fake.calls) == 3 and fake.calls[0].content == TOKEN
    assert fake.calls[0].headers['cookie'] == 'session=secret'
    for request in fake.calls[1:]:
        assert request.method == 'GET' and request.content == b''
        assert not (set(request.headers) & (API_HEADERS | {'cookie', 'authorization', 'content-type', 'content-length'}))


@pytest.mark.parametrize('converted', [False, True])
def test_post_operation_forbids_downgrade_even_after_get_conversion_and_policy_exception(install, converted):
    locations = ['https://public.example/next', 'http://public.example/end'] if converted else ['http://public.example/end']
    fake = install(lambda request: response(status=303, headers={'Location': locations.pop(0)}))
    counter = budget()
    policy = OutboundPolicy(downgrade_origins=frozenset({('https', 'public.example', 443)}))
    with post_client(policy=policy) as source:
        with pytest.raises(OutboundPolicyError) as caught:
            with source.exchange('POST', 'https://public.example/start', budget=counter, data=TOKEN):
                pytest.fail('POST operation downgraded HTTPS')
    assert_safe(caught.value)
    assert len(fake.calls) == (2 if converted else 1) and counter.snapshot().requests == len(fake.calls)


def test_post_redirects_cannot_reset_phase_or_original_budget(transport_network):
    net = transport_network
    net.replies = [reply(b'', status=b'307 Same', headers=b'Location: /next\r\n'), reply()]
    now = [0.0]
    net.before_read = lambda: now.__setitem__(0, now[0] + .6)
    counter = OutboundBudget(BudgetLimits(seconds=10), clock=lambda: now[0])
    with post_client() as source:
        with pytest.raises(OutboundBudgetError) as caught:
            with source.exchange('POST', 'http://public.example/start', budget=counter, data=TOKEN,
                                 request_limits=RequestLimits(seconds=1)):
                pytest.fail('POST redirect reset phase')
        assert not source._responses
        with pytest.raises(OutboundBudgetError):
            counter.request_scope()
    assert_safe(caught.value)
    assert counter.snapshot().requests == 2 and net.closed == 2


def test_post_io_failure_is_safe_has_no_retry_and_explicit_retry_still_charges_original_budget(transport_network, caplog):
    import httpcore
    net = transport_network
    net.connect_error = httpcore.ConnectError('synthetic-secret body/query')
    counter = budget(requests=1)
    with post_client() as source:
        with pytest.raises(OutboundUnavailableError) as caught:
            with source.exchange('POST', 'http://public.example/?sig=secret', budget=counter, data=TOKEN):
                pytest.fail('failed POST yielded')
        assert_safe(caught.value)
        assert not source._responses and len(net.connections) == 1
        with pytest.raises(OutboundBudgetError):
            with source.exchange('POST', 'http://public.example/', budget=counter, data=TOKEN):
                pytest.fail('explicit retry bypassed original request cap')
    assert len(net.connections) == 1 and counter.snapshot().requests == 1 and 'secret' not in caplog.text


def test_post_loop_keeps_independent_redirect_ceiling_and_closes_all_responses(install):
    fake = install(lambda request: response(status=307, headers={'Location': '/again'}))
    counter = budget(requests=100, redirects=100)
    with post_client() as source:
        with pytest.raises(OutboundBudgetError):
            with source.exchange('POST', 'https://public.example/start', budget=counter, data=TOKEN):
                pytest.fail('POST redirect loop yielded')
        assert not source._responses
    assert len(fake.calls) == 6 and counter.snapshot().requests == 6
    assert all(request.content == TOKEN for request in fake.calls)


def test_post_client_close_preserves_u1_resource_lifetime(transport_network):
    net = transport_network
    net.replies = [reply()]
    counter = budget()
    with post_client() as source:
        with source.exchange('POST', 'http://public.example/', budget=counter, data=TOKEN) as result:
            assert result in source._responses and not result._closed
            source.close()
            with pytest.raises(OutboundBudgetError) as caught:
                result.read()
            assert_safe(caught.value)
            result.close()
        assert not source._responses and net.closed == 1
