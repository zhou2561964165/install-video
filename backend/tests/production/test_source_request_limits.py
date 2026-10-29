"""Transient tightening must not change the durable resolve/attempt tree."""
import math

import pytest

from app.services.outbound_budget import BudgetLimits, OutboundBudget, OutboundBudgetError
from app.services.outbound_httpx import ControlledHttpxClient, ProxyChannel
from test_outbound_httpx import install, response, transport_network


def test_request_scopes_charge_original_budget_without_children():
    root = OutboundBudget(BudgetLimits(requests=3))
    for _ in range(2):
        scope = root.request_scope()
        allowance = scope.begin_request()
        allowance.consume(raw_bytes=2, decoded_bytes=3)
        allowance.close()
    assert root.snapshot().requests == 2
    assert root.snapshot().raw_bytes == 4
    assert root.snapshot().decoded_bytes == 6
    assert root.checkpoint().children == ()


def test_identity_choice_is_constructor_only(install):
    fake = install(lambda request: response())
    with ControlledHttpxClient(ProxyChannel('http://127.0.0.1:4750', True), accept_encoding='identity') as client:
        client.get('https://public.example/', budget=OutboundBudget(BudgetLimits()))
    assert fake.calls[0].headers['accept-encoding'] == 'identity'


@pytest.mark.parametrize('value', ['br', '', None, True, ['identity']])
def test_invalid_encoding_rejected_before_transport(value, monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('invalid constructor constructed a transport')
    monkeypatch.setattr('httpx.HTTPTransport', forbidden)
    with pytest.raises(ValueError):
        ControlledHttpxClient(ProxyChannel('http://127.0.0.1:4750', True), accept_encoding=value)


@pytest.mark.parametrize('field,value', [
    ('seconds', 0), ('seconds', -1), ('seconds', True), ('seconds', math.nan),
    ('seconds', math.inf), ('seconds', 10 ** 1000), ('seconds', '1'),
    ('response_raw_bytes', True), ('response_raw_bytes', 0),
    ('response_decoded_bytes', 1.1), ('response_decoded_bytes', -1),
])
def test_invalid_request_limits_do_not_charge(field, value):
    from app.services.outbound_budget import RequestLimits
    root = OutboundBudget(BudgetLimits())
    with pytest.raises(ValueError):
        root.request_scope(RequestLimits(**{field: value}))
    assert root.snapshot().requests == 0


@pytest.mark.parametrize('cap,parent_cap', [(3, 8), (100, 3)])
def test_response_cap_tightens_and_locks_original_budget(cap, parent_cap):
    from app.services.outbound_budget import RequestLimits
    root = OutboundBudget(BudgetLimits(response_raw_bytes=parent_cap))
    scope = root.request_scope(RequestLimits(response_raw_bytes=cap), purpose='subtitle')
    allowance = scope.begin_request()
    assert allowance.remaining_raw_bytes() == min(cap, parent_cap)
    with pytest.raises(OutboundBudgetError) as error:
        allowance.consume(raw_bytes=min(cap, parent_cap) + 1)
    assert error.value.code == 'subtitle_too_large'
    with pytest.raises(OutboundBudgetError):
        root.request_scope().begin_request()
    assert root.snapshot().requests == 1


def test_phase_deadline_shared_clock_and_cannot_restart():
    from app.services.outbound_budget import RequestLimits
    now = [100.0]
    root = OutboundBudget(BudgetLimits(seconds=30), clock=lambda: now[0])
    phase = root.request_scope(RequestLimits(seconds=2))
    assert phase.remaining_seconds() == 2
    phase.begin_request().close()
    now[0] += 1
    phase.begin_request(redirect=True).close()
    assert phase.remaining_seconds() == 1
    now[0] += 1
    with pytest.raises(OutboundBudgetError) as error:
        phase.remaining_seconds()
    assert error.value.code == 'source_timeout'
    with pytest.raises(OutboundBudgetError):
        root.request_scope(RequestLimits(seconds=30))
    assert root.snapshot().requests == 2
    assert root.checkpoint().children == ()


def test_phase_never_extends_parent_deadline():
    from app.services.outbound_budget import RequestLimits
    root = OutboundBudget(BudgetLimits(seconds=1), clock=lambda: 1.0)
    assert root.request_scope(RequestLimits(seconds=30)).remaining_seconds() == 1


def test_httpx_phase_covers_redirect_and_eof(transport_network):
    from app.services.outbound_budget import RequestLimits
    state = transport_network
    now = [0.0]
    state.before_read = lambda: now.__setitem__(0, now[0] + .4)
    state.replies = [b'HTTP/1.1 200 Connection established\r\n\r\n',
                     b'HTTP/1.1 302 Found\r\nLocation: /caption\r\nContent-Length: 0\r\n\r\n',
                     b'HTTP/1.1 200 Connection established\r\n\r\n',
                     b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok']
    root = OutboundBudget(BudgetLimits(seconds=30), clock=lambda: now[0])
    with ControlledHttpxClient(ProxyChannel('http://127.0.0.1:4750', True)) as client:
        with pytest.raises(OutboundBudgetError):
            client.get('https://public.example/', budget=root, request_limits=RequestLimits(seconds=1))
    assert state.closed > 0
    with pytest.raises(OutboundBudgetError):
        root.begin_request()


def test_read_error_after_phase_expiry_poison_original_budget(install):
    import httpx
    from app.services.outbound_budget import RequestLimits
    from test_outbound_httpx import Wire
    now = [0.0]
    def expired_read():
        now[0] = 3.0
        raise httpx.ReadTimeout('synthetic-signed-url')
    wire = Wire([b'not-delivered'], before=expired_read)
    install(lambda req: httpx.Response(200, stream=wire))
    root = OutboundBudget(BudgetLimits(seconds=30), clock=lambda: now[0])
    with ControlledHttpxClient(ProxyChannel('http://127.0.0.1:4750', True)) as client:
        with pytest.raises(OutboundBudgetError):
            client.get('https://public.example/', budget=root, request_limits=RequestLimits(seconds=2))
    assert wire.closed
    with pytest.raises(OutboundBudgetError):
        root.request_scope()


def test_request_cap_also_bounds_real_gzip_decoded_output(install):
    import gzip
    from app.services.outbound_budget import RequestLimits
    fake = install(lambda req: response(gzip.compress(b'x' * 1000), headers={'content-encoding': 'gzip'}))
    root = OutboundBudget(BudgetLimits())
    with ControlledHttpxClient(ProxyChannel('http://127.0.0.1:4750', True)) as client:
        with pytest.raises(OutboundBudgetError) as error:
            client.get('https://public.example/', budget=root,
                       request_limits=RequestLimits(response_decoded_bytes=50))
    assert error.value.reason == 'response_decoded_bytes' and fake.closed
    assert root.snapshot().decoded_bytes == 0


@pytest.mark.parametrize('decoder_failure', [False, True])
def test_decompress_crossing_phase_never_delivers_and_locks_budget(install, monkeypatch, decoder_failure):
    import gzip
    import zlib
    from app.services.outbound_budget import RequestLimits
    from app.services import outbound_httpx
    from test_outbound_httpx import Wire
    now = [0.0]
    original = zlib.decompressobj
    original_calls = []

    class AdvancingDecoder:
        def __init__(self, *args):
            self.decoder = original(*args)

        def __getattr__(self, name):
            return getattr(self.decoder, name)

        def decompress(self, data, size):
            now[0] = 3.0
            original_calls.append(size)
            if decoder_failure:
                raise zlib.error('synthetic-source-secret')
            return self.decoder.decompress(data, size)

    body = gzip.compress(b'legal bounded decoded output')
    wire = Wire([body])
    install(lambda req: __import__('httpx').Response(200, headers={'content-encoding': 'gzip'}, stream=wire))
    monkeypatch.setattr(outbound_httpx.zlib, 'decompressobj', AdvancingDecoder)
    root = OutboundBudget(BudgetLimits(seconds=30), clock=lambda: now[0])
    delivered = []
    with ControlledHttpxClient(ProxyChannel('http://127.0.0.1:4750', True)) as client:
        with pytest.raises(OutboundBudgetError) as error:
            with client.stream('GET', 'https://public.example/?token=synthetic-source-secret',
                    budget=root, request_limits=RequestLimits(seconds=2)) as result:
                # Read exactly the first yielded block: checking at the next
                # chunk or EOF is too late once output has left the adapter.
                delivered.append(next(result.iter_bytes()))
    assert original_calls and delivered == [] and wire.closed
    assert root.snapshot().decoded_bytes == 0
    assert error.value.code == 'source_timeout'
    assert error.value.__context__ is None and error.value.__cause__ is None
    assert 'synthetic-source-secret' not in str(error.value)
    with pytest.raises(OutboundBudgetError):
        root.request_scope()
