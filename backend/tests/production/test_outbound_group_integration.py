"""Joint budget consumers, using synthetic I/O only; no real resolver or PG."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import gzip
import json
import zlib

import httpx
import pytest

from app.services import download_budget_codec as codec, source_network as network
from app.services.download_submission import ResolveAccounting
from app.services.outbound_budget import (
    BudgetLimits, BudgetProfile, OutboundBudget, OutboundBudgetError, OutboundBudgetGroup,
)
from app.services.outbound_httpx import ControlledHttpxClient, ControlledHttpStatusError, ProxyChannel
from app.services.outbound_policy import OutboundPolicyError, OutboundPurpose, OutboundUnavailableError
from test_outbound_httpx import Wire, install, response, transport_network

URL = 'https://public.example/start?token=synthetic'
CHANNEL = ProxyChannel('http://127.0.0.1:4750', True)
OPTIONS = dict(purpose=OutboundPurpose.METADATA, max_bytes=1024 * 1024,
               phase_seconds=10, io_timeout=5)


def accounting(**child_caps):
    clock = lambda: 1.
    download = OutboundBudget(BudgetProfile.download_parent(), purpose=OutboundPurpose.SOURCE, clock=clock)
    direct = OutboundBudget(BudgetProfile.direct_parent(), clock=clock)
    child = direct.child(BudgetLimits(**child_caps))
    return ResolveAccounting(download, direct, child)


def context(account):
    return network.SourceNetworkContext(CHANNEL, OutboundBudgetGroup(account.source_budgets()))


def counts(account):
    return [tuple(getattr(node.snapshot(), key) for key in ('requests', 'redirects', 'raw_bytes', 'decoded_bytes'))
            for node in (account.download, account.direct, account.child)]


def reply(state, body=b'', *, status='200 OK', headers=(), head=False):
    state.replies.extend([
        b'HTTP/1.1 200 Connection established\r\n\r\n',
        ('HTTP/1.1 ' + status + '\r\nContent-Length: ' + str(len(body))
         + '\r\nConnection: close\r\n' + ''.join(key + ': ' + value + '\r\n' for key, value in headers)
         + '\r\n').encode() + (b'' if head else body),
    ])


@pytest.mark.parametrize('encoding,encode', [('gzip', gzip.compress), ('deflate', zlib.compress)])
def test_source_group_real_httpx_redirect_compression_and_metadata(transport_network, encoding, encode):
    state, account = transport_network, accounting()
    ctx = context(account)
    group = ctx.budget
    body = b'joint body' * 1500
    compressed = encode(body)
    reply(state, status='302 Found', headers=[('Location', '/middle')])
    reply(state, status='307 Temporary Redirect', headers=[('Location', '/final?signature=synthetic')])
    reply(state, compressed, headers=[('Content-Encoding', encoding), ('X-Value', 'one'), ('X-Value', 'two')])
    with ctx.exchange('GET', URL, **OPTIONS) as result:
        assert result._closed is False
        assert result.effective_url == 'https://public.example/final?signature=synthetic'
        assert [value for key, value in result.header_items() if key == 'x-value'] == ['one', 'two']
        assert result.read() == body
    assert result._closed and ctx.budget is group
    assert counts(account) == [(3, 2, len(compressed), len(body))] * 3
    assert len(state.connections) == 3 and state.closed >= 3
    assert all(host == '127.0.0.1' and port == 4750 for host, port, _ in state.connections)


def test_group_real_range_then_head_counts_once_and_zero_head_body(transport_network):
    state, account = transport_network, accounting()
    ctx = context(account)
    reply(state, b'abc', status='206 Partial Content', headers=[('Content-Range', 'bytes 0-2/20')])
    with ctx.stream(URL, headers={'Range': 'bytes=0-2'}, identity_only=True, **OPTIONS) as result:
        assert result.status_code == 206 and result.headers['content-range'] == 'bytes 0-2/20'
        assert result.read() == b'abc'
    reply(state, b'not-read', head=True)
    with ctx.exchange('HEAD', URL, **OPTIONS) as result:
        assert not result._closed and result.read() == b''
    assert counts(account) == [(2, 0, 3, 3)] * 3
    sent = b''.join(state.writes)
    assert b'HEAD /start?token=synthetic HTTP/1.1' in sent
    assert b'Range: bytes=0-2' in sent or b'range: bytes=0-2' in sent
    assert b'accept-encoding: identity' in sent.lower()


def test_exchange_response_open_until_caller_exit_and_early_close(install):
    account, wire = accounting(), Wire([b'a', b'b'])
    fake = install(lambda req: httpx.Response(200, stream=wire))
    with context(account).exchange('GET', URL, **OPTIONS) as result:
        assert not wire.closed and not result._closed
        assert result.status_code == 200
    assert wire.closed and result._closed and len(fake.calls) == 1
    assert counts(account) == [(1, 0, 0, 0)] * 3


def test_second_tree_request_cap_rejects_before_send_without_first_tree_half_charge(install):
    account = accounting(requests=1)
    used = account.child.begin_request()
    used.close()
    before = counts(account)
    fake = install(lambda req: response())
    ctx = context(account)
    with pytest.raises(OutboundBudgetError):
        with ctx.exchange('GET', URL, **OPTIONS):
            pytest.fail('exhausted second tree sent')
    assert fake.calls == [] and counts(account) == before
    with pytest.raises(OutboundBudgetError):
        with ctx.stream(URL, **OPTIONS):
            pass
    assert fake.calls == [] and counts(account) == before


@pytest.mark.parametrize('kind', ['raw', 'decoded'])
def test_rejected_chunk_never_delivered_both_roots_equal_old_charge_order(install, kind):
    account = accounting(**{kind + '_bytes': 2})
    wire = Wire([b'abc'])
    fake = install(lambda req: httpx.Response(200, stream=wire))
    delivered = []
    with pytest.raises(OutboundBudgetError):
        with context(account).exchange('GET', URL, **OPTIONS) as result:
            for chunk in result.iter_bytes():
                delivered.append(chunk)
    # Existing transport deliberately charges raw before decoded separately.
    assert counts(account) == [(1, 0, 0 if kind == 'raw' else 3, 0)] * 3
    assert not delivered and wire.closed and len(fake.calls) == 1


@pytest.mark.parametrize('encoding,encode', [('gzip', gzip.compress), ('deflate', zlib.compress)])
def test_compression_cap_charges_equal_roots_and_discards_probe(install, encoding, encode):
    account = accounting(decoded_bytes=2)
    body = encode(b'abc' * 100)
    wire = Wire([body])
    install(lambda req: httpx.Response(200, headers={'content-encoding': encoding}, stream=wire))
    delivered = []
    with pytest.raises(OutboundBudgetError):
        with context(account).stream(URL, **OPTIONS) as result:
            delivered.extend(result.iter_bytes())
    assert delivered == [] and counts(account) == [(1, 0, len(body), 0)] * 3 and wire.closed


@pytest.mark.parametrize('method,data', [('POST', None), ('post', b''), ('GET', b''), ('HEAD', b'x'), ('PUT', None)])
def test_context_rejects_post_or_body_before_scope_and_transport(method, data, monkeypatch):
    account = accounting()
    ctx = context(account)
    def forbidden(*args, **kwargs):
        pytest.fail('invalid context method/body constructed transport or scope')
    monkeypatch.setattr(httpx, 'HTTPTransport', forbidden)
    monkeypatch.setattr(OutboundBudgetGroup, 'request_scope', forbidden)
    with pytest.raises(OutboundUnavailableError):
        with ctx.exchange(method, URL, data=data, **OPTIONS):
            pass
    assert counts(account) == [(0, 0, 0, 0)] * 3


def test_group_identity_frozen_scope_owner_and_runtime_boundaries(monkeypatch):
    account = accounting()
    ctx = context(account)
    original = ctx.budget
    with pytest.raises(FrozenInstanceError):
        ctx.budget = OutboundBudgetGroup(account.source_budgets())
    with network.source_network_scope(ctx):
        with network.source_network_scope(None) as reused:
            assert reused is ctx and reused.budget is original
        with pytest.raises(OutboundUnavailableError):
            with network.source_network_scope(context(account)):
                pass
    def enter():
        with ctx.exchange('HEAD', URL, **OPTIONS):
            pass
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OutboundUnavailableError):
            pool.submit(enter).result()
    monkeypatch.setattr(network, 'getpid', lambda: ctx._process + 1)
    with pytest.raises(OutboundUnavailableError):
        enter()
    with pytest.raises(OutboundUnavailableError):
        network.make_runtime_source_network()


@pytest.mark.parametrize('kind', ['fake', 'subclass'])
def test_nonexact_group_is_not_a_budget_even_if_interface_matches(install, kind):
    account = accounting()
    class Fake:
        request_scope = lambda *args, **kwargs: pytest.fail('duck scope executed')
    class Subclass(OutboundBudgetGroup):
        pass
    bad = Fake() if kind == 'fake' else Subclass(account.source_budgets())
    with pytest.raises(ValueError):
        network.SourceNetworkContext(CHANNEL, bad)
    fake = install(lambda req: response())
    with ControlledHttpxClient(CHANNEL) as client:
        with pytest.raises(ValueError):
            client.get(URL, budget=bad)
    assert fake.calls == [] and counts(account) == [(0, 0, 0, 0)] * 3


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_single_budget_context_compatibility(method, install):
    budget = OutboundBudget(BudgetLimits())
    fake = install(lambda req: response(b'ok'))
    ctx = network.SourceNetworkContext(CHANNEL, budget)
    with ctx.exchange(method, URL, **OPTIONS) as result:
        assert result.read() == (b'' if method == 'HEAD' else b'ok')
    assert budget.snapshot().requests == 1 and len(fake.calls) == 1
    assert budget.checkpoint().children == ()


def test_official_cookie_origin_and_header_policy_shared_with_get(monkeypatch, install):
    from http.cookiejar import CookieJar
    jar = CookieJar()
    methods = []
    def apply(request, supplied):
        assert supplied is jar
        methods.append(request.method)
        request.headers['cookie'] = 'official=synthetic'
    monkeypatch.setattr(network, 'apply_session_cookies', apply)
    def handle(request):
        return response(b'', status=302, headers={'location': 'https://i0.hdslb.com/file'}) if len(fake.calls) == 1 else response(b'')
    fake = install(handle)
    with context(accounting()).exchange('HEAD', 'https://api.bilibili.com/x/view', cookies=jar,
            headers={'Cookie': 'extractor=blocked', 'Authorization': 'blocked', 'X-Api': 'blocked',
                     'Referer': 'https://www.bilibili.com/video/fixture?secret=synthetic'}, **OPTIONS) as result:
        assert result.read() == b''
    assert methods == ['HEAD'] and len(fake.calls) == 2
    assert fake.calls[0].headers['cookie'] == 'official=synthetic'
    assert not {'cookie', 'authorization', 'x-api'} & set(fake.calls[1].headers)
    assert fake.calls[0].headers['referer'] == 'https://www.bilibili.com/video/fixture'


@pytest.mark.parametrize('status', [401, 403, 412])
def test_source_status_is_safe_terminal_no_fallback(status, install):
    account = accounting()
    wire = Wire([b'private failure'])
    fake = install(lambda req: httpx.Response(status, stream=wire))
    with pytest.raises(ControlledHttpStatusError) as caught:
        with context(account).exchange('GET', URL, **OPTIONS) as result:
            result.raise_for_status()
    assert caught.value.source_status == status and caught.value.retryable is False
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert 'token' not in str(caught.value) and wire.closed and len(fake.calls) == 1
    assert counts(account) == [(1, 0, 0, 0)] * 3


def test_b4_getter_is_read_only_existing_child_no_precharge(monkeypatch):
    account = accounting()
    before = account.checkpoint()
    monkeypatch.setattr(account, 'begin_get', lambda: pytest.fail('source getter precharged'))
    for _ in range(2):
        download, child = account.source_budgets()
        assert download is account.download and child is account.child
    assert account.checkpoint() == before and len(before.direct_resolve_parent.children) == 1


def test_b4_double_checkpoint_codec_restore_same_clock_continues_same_child(install):
    account = accounting()
    fake = install(lambda req: response(b'abc'))
    with context(account).stream(URL, **OPTIONS) as result:
        assert result.read() == b'abc'
    # All response/client contexts have exited before either root is read.
    envelope = account.checkpoint()
    payload = codec.encode_budget(envelope, resolve_attempts_used=1)
    assert codec.decode_budget(1, payload, resolve_attempts_used=1) == envelope
    assert set(json.loads(payload)) == {'download_parent', 'direct_resolve_parent'}
    clock = lambda: 20.
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    download, direct = codec.restore_budget(1, payload, checkpoint_at=now, db_now=now + timedelta(seconds=1),
        deadline_at=now + timedelta(seconds=1700), resolve_deadline_at=now + timedelta(seconds=50),
        resolve_attempt_deadline=now + timedelta(seconds=20), resolve_attempts_used=1, clock=clock)
    child = direct.resume_child(0)
    restored = ResolveAccounting(download, direct, child)
    restored_ctx = context(restored)
    with restored_ctx.exchange('GET', URL, **OPTIONS) as result:
        assert result.read() == b'abc'
    checkpoint = restored.checkpoint()
    codec.encode_budget(checkpoint, resolve_attempts_used=1)
    assert counts(restored) == [(2, 0, 6, 6)] * 3 and len(fake.calls) == 2
    assert len(checkpoint.direct_resolve_parent.children) == 1
    assert checkpoint.download_parent.requests == checkpoint.direct_resolve_parent.requests


def test_transport_post_optin_also_accepts_real_group_without_context_enable(install):
    account = accounting()
    group = OutboundBudgetGroup(account.source_budgets())
    fake = install(lambda req: response(b'ok'))
    with ControlledHttpxClient(CHANNEL, request_body_limit=16) as client:
        with client.exchange('POST', URL, budget=group, data=b'{}', headers={'Content-Type': 'application/json'}) as result:
            assert result.read() == b'ok'
    assert len(fake.calls) == 1 and fake.calls[0].method == 'POST'
    assert counts(account) == [(1, 0, 2, 2)] * 3


def test_second_tree_request_exhaustion_uses_real_httpx_and_zero_backend_send(transport_network):
    account = accounting(requests=1)
    account.child.begin_request().close()
    before = counts(account)
    with pytest.raises(OutboundBudgetError):
        with context(account).exchange('HEAD', URL, **OPTIONS):
            pass
    assert transport_network.connections == [] and transport_network.writes == []
    assert counts(account) == before


@pytest.mark.parametrize('kind', ['raw', 'decoded'])
def test_real_httpx_cap_failure_closes_and_never_delivers_chunk(transport_network, kind):
    account = accounting(**{kind + '_bytes': 2})
    reply(transport_network, b'abc')
    delivered = []
    with pytest.raises(OutboundBudgetError):
        with context(account).stream(URL, **OPTIONS) as result:
            delivered.extend(result.iter_bytes())
    assert delivered == [] and result._closed and transport_network.closed > 0
    assert counts(account) == [(1, 0, 0 if kind == 'raw' else 3, 0)] * 3


def test_existing_download_attempt_history_preserved_group_only_adds_matching_delta(install):
    account = accounting()
    attempt = account.download.child(BudgetProfile.download_attempt())
    prior = attempt.begin_request()
    prior.consume(raw_bytes=11, decoded_bytes=13)
    prior.close()
    before = counts(account)
    install(lambda req: response(b'abc'))
    with context(account).stream(URL, **OPTIONS) as result:
        assert result.read() == b'abc'
    assert [tuple(end - start for start, end in zip(old, new))
            for old, new in zip(before, counts(account))] == [(1, 0, 3, 3)] * 3
    envelope = account.checkpoint()
    codec.encode_budget(envelope, resolve_attempts_used=1)
    for key in ('requests', 'redirects', 'raw_bytes', 'decoded_bytes'):
        assert getattr(envelope.download_parent, key) == (
            getattr(envelope.direct_resolve_parent, key)
            + sum(getattr(child, key) for child in envelope.download_parent.children))


def test_original_single_budget_subclass_still_accepted(install):
    class Single(OutboundBudget):
        pass
    budget = Single(BudgetLimits())
    fake = install(lambda req: response())
    with network.SourceNetworkContext(CHANNEL, budget).stream(URL, **OPTIONS) as result:
        assert result.read() == b'ok'
    assert len(fake.calls) == budget.snapshot().requests == 1


def test_group_scope_deadline_not_reset_by_redirect_and_rejects_next_send(transport_network):
    ticks = [1.]
    clock = lambda: ticks[0]
    left = OutboundBudget(BudgetLimits(), clock=clock)
    right = OutboundBudget(BudgetLimits(), clock=clock)
    group = OutboundBudgetGroup((left, right))
    ctx = network.SourceNetworkContext(CHANNEL, group)
    reply(transport_network, status='302 Found', headers=[('Location', '/next')])
    calls = [0]
    def advance():
        calls[0] += 1
        if calls[0] == 2:  # source headers, after proxy CONNECT
            ticks[0] = 11.
    transport_network.before_read = advance
    with pytest.raises(OutboundBudgetError):
        with ctx.exchange('GET', URL, **OPTIONS):
            pass
    assert ctx.budget is group and len(transport_network.connections) == 1
    assert [node.snapshot().requests for node in (left, right)] == [1, 1]


@pytest.mark.parametrize('url,expected', [('https://api.bilibili.com/x/view', True),
    ('https://i0.hdslb.com/file', False), ('http://api.bilibili.com/x/view', False)])
def test_real_cookie_jar_rules_also_apply_to_head(url, expected, install):
    from test_source_httpx_integration import strict_jar
    fake = install(lambda req: response(b''))
    with context(accounting()).exchange('HEAD', url, cookies=strict_jar(), **OPTIONS) as result:
        assert result.read() == b''
    assert len(fake.calls) == 1 and ('cookie' in fake.calls[0].headers) is expected
    if expected:
        assert fake.calls[0].headers['cookie'] == 'official=synthetic'
