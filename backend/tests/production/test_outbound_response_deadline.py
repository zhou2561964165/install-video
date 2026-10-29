"""Public response phase checks through real HTTPX and synthetic backend I/O."""
import pytest

from app.services.outbound_budget import BudgetLimits, OutboundBudget, OutboundBudgetError, OutboundBudgetGroup, RequestLimits
from app.services.outbound_httpx import ControlledHttpxClient, ProxyChannel
from app.services.outbound_policy import OutboundPurpose
from test_outbound_httpx import transport_network

URL = 'https://public.example/file?signature=synthetic-secret'
CHANNEL = ProxyChannel('http://127.0.0.1:4750', True)


def counters(nodes):
    return [tuple(getattr(node.snapshot(), key) for key in ('requests', 'redirects', 'raw_bytes', 'decoded_bytes'))
            for node in nodes]


def setup(group):
    ticks = [1.]
    clock = lambda: ticks[0]
    roots = [OutboundBudget(BudgetLimits(seconds=60, children=1), clock=clock) for _ in range(2 if group else 1)]
    leaves = [root.child(BudgetLimits(seconds=30), purpose=OutboundPurpose.SUBTITLE) for root in roots]
    budget = OutboundBudgetGroup(tuple(leaves)) if group else leaves[0]
    return ticks, roots, leaves, budget


def reply(state):
    state.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n',
                          b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: close\r\n\r\nabc'])


@pytest.mark.parametrize('group', [False, True])
@pytest.mark.parametrize('completion', ['open', 'eof', 'explicit_close'])
def test_public_check_uses_same_phase_after_eof_or_close_no_accounting_delta(transport_network, group, completion):
    ticks, roots, leaves, budget = setup(group)
    reply(transport_network)
    with ControlledHttpxClient(CHANNEL, purpose=OutboundPurpose.SUBTITLE) as client:
        with client.stream('GET', URL, budget=budget, request_limits=RequestLimits(seconds=2)) as response:
            if completion == 'eof':
                assert response.read() == b'abc'
            elif completion == 'explicit_close':
                response.close()
            nodes = roots + leaves
            before = counters(nodes)
            io_before = (len(transport_network.connections), len(transport_network.reads), len(transport_network.writes))
            assert response.check_deadline() is None
            ticks[0] = 2.
            assert response.check_deadline() is None
            assert counters(nodes) == before
            assert io_before == (len(transport_network.connections), len(transport_network.reads), len(transport_network.writes))
        # The client/context closing the response must not remove its phase.
        assert response.check_deadline() is None
        ticks[0] = 3.
        with pytest.raises(OutboundBudgetError) as caught:
            response.check_deadline()
        assert caught.value.reason == 'deadline' and caught.value.code == 'source_timeout'
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert 'synthetic-secret' not in str(caught.value) and 'signature' not in repr(caught.value)
        assert counters(nodes) == before
        # Phase poison applies to participating leaves, not healthy ancestors.
        assert all(root.checkpoint().blocked is None for root in roots)
        assert all(root.checkpoint().children[0].blocked == 'deadline' for root in roots)
        with pytest.raises(OutboundBudgetError):
            budget.request_scope(RequestLimits(seconds=10), purpose=OutboundPurpose.SUBTITLE)
        with pytest.raises(OutboundBudgetError):
            response.check_deadline()
    assert transport_network.closed > 0


@pytest.mark.parametrize('group', [False, True])
def test_phase_error_drops_active_caller_exception_context(transport_network, group):
    ticks, roots, leaves, budget = setup(group)
    reply(transport_network)
    with ControlledHttpxClient(CHANNEL) as client:
        with client.stream('GET', URL, budget=budget, request_limits=RequestLimits(seconds=2)) as response:
            response.close()
            ticks[0] = 3.
            try:
                raise RuntimeError('caller signed query signature=synthetic-secret')
            except RuntimeError:
                with pytest.raises(OutboundBudgetError) as caught:
                    response.check_deadline()
            assert caught.value.__context__ is None and caught.value.__cause__ is None


@pytest.mark.parametrize('group', [False, True])
def test_public_check_preserves_original_scope_purpose_for_prior_cap_poison(transport_network, group):
    ticks, roots, leaves, budget = setup(group)
    reply(transport_network)
    with ControlledHttpxClient(CHANNEL, purpose=OutboundPurpose.SUBTITLE) as client:
        with client.stream('GET', URL, budget=budget,
                request_limits=RequestLimits(seconds=2, response_decoded_bytes=2)) as response:
            with pytest.raises(OutboundBudgetError) as first:
                response.read()
            assert first.value.code == 'subtitle_too_large'
            with pytest.raises(OutboundBudgetError) as checked:
                response.check_deadline()
            assert checked.value.code == 'subtitle_too_large'
            assert checked.value.reason == first.value.reason == 'response_decoded_bytes'
            assert checked.value.__context__ is None and checked.value.__cause__ is None


@pytest.mark.parametrize('group', [False, True])
def test_invalid_clock_check_drops_active_caller_context(transport_network, group):
    ticks, roots, leaves, budget = setup(group)
    reply(transport_network)
    with ControlledHttpxClient(CHANNEL) as client:
        with client.stream('HEAD', URL, budget=budget) as response:
            response.close()
            ticks[0] = float('nan')
            try:
                raise RuntimeError('caller signature=synthetic-secret')
            except RuntimeError:
                with pytest.raises(ValueError) as caught:
                    response.check_deadline()
            assert caught.value.__context__ is None and caught.value.__cause__ is None
            assert str(caught.value) == 'Invalid outbound budget clock'
