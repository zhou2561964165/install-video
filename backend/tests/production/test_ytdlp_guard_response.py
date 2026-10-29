"""Real HTTPX/httpcore -> context -> yt-dlp Response semantics."""
import gzip

import pytest
from yt_dlp.networking.common import Response
from yt_dlp.networking.exceptions import HTTPError, RequestError, TransportError

from app.services.outbound_budget import OutboundBudgetError
from test_outbound_httpx import install, response, Wire, transport_network
from test_ytdlp_guard_director import context, guarded, reply, safe


def test_real_response_partial_buffer_read_zero_and_eof(transport_network):
    transport_network.replies = [reply(b'abcdef')]
    network = context()
    with guarded(network) as ydl:
        result = ydl.urlopen('http://public.example/body')
        assert isinstance(result, Response)
        reads_before = len(transport_network.reads)
        assert result.read(0) == b'' and len(transport_network.reads) == reads_before
        assert network.budget.snapshot().decoded_bytes == 0
        assert result.read(1) == b'a'
        assert result.read(2) == b'bc'
        assert result.read(10 ** 30) == b'def'
        assert result.read() == result.read(-1) == b''
        assert network.budget.snapshot().decoded_bytes == 6
        assert transport_network.closed == 1
        result.close()
        result.close()


@pytest.mark.parametrize('amount', [True, False, -2, 1.2, '2'])
def test_read_rejects_invalid_amount_before_body_io(amount, transport_network):
    transport_network.replies = [reply(b'abc')]
    with guarded() as ydl:
        result = ydl.urlopen('http://public.example/body')
        reads_before = len(transport_network.reads)
        with pytest.raises(RequestError) as error:
            result.read(amount)
        safe(error.value)
        assert len(transport_network.reads) == reads_before
    assert transport_network.closed == 1


def test_gzip_bridge_removes_wire_length_encoding_and_preserves_repeated_headers(transport_network):
    body = b'hello decoded'
    transport_network.replies = [reply(gzip.compress(body), headers=(
        b'Content-Encoding: gzip\r\nSet-Cookie: a=1; Secure\r\nSet-Cookie: b=2; Secure\r\n'))]
    with guarded() as ydl:
        result = ydl.urlopen('http://public.example/body')
        assert result.headers.get_all('Set-Cookie') == ['a=1; Secure', 'b=2; Secure']
        assert result.headers.get('Content-Encoding') is None
        assert result.headers.get('Content-Length') is None
        assert result.read() == body


def test_identity_range_status_length_and_effective_redirect_url(transport_network):
    transport_network.replies = [
        reply(b'', status=b'302 Found', headers=b'Location: /nested/body?sig=synthetic-secret\r\n'),
        reply(b'abc', status=b'206 Partial Content', headers=b'Content-Range: bytes 1-3/10\r\n')]
    network = context()
    with guarded(network, identity_only=True) as ydl:
        result = ydl.urlopen('http://public.example/start')
        assert result.status == 206 and result.reason == 'Partial Content'
        assert result.url == 'http://public.example/nested/body?sig=synthetic-secret'
        assert result.headers['Content-Length'] == '3'
        assert result.headers['Content-Range'] == 'bytes 1-3/10'
        assert result.read() == b'abc'
    assert network.budget.snapshot().requests == 2


@pytest.mark.parametrize('mode', ['buffer', 'eof'])
def test_same_phase_checked_even_when_no_further_wire_read(mode, transport_network):
    now = [0.]
    network = context(lambda: now[0])
    transport_network.replies = [reply(b'abc')]
    with guarded(network, phase_seconds=1) as ydl:
        result = ydl.urlopen('http://public.example/body')
        assert result.read(1 if mode == 'buffer' else None) == (b'a' if mode == 'buffer' else b'abc')
        before = len(transport_network.reads)
        now[0] = 2.
        with pytest.raises(RequestError) as error:
            result.read(1)
        safe(error.value)
        assert not isinstance(error.value, TransportError)
        assert len(transport_network.reads) == before
        with pytest.raises(OutboundBudgetError):
            network.budget.request_scope().remaining_seconds()
    assert transport_network.closed == 1


@pytest.mark.parametrize('close_by', ['caller', 'ydl'])
def test_live_response_owns_exchange_until_close(close_by, transport_network):
    transport_network.replies = [reply(b'abc')]
    ydl = guarded()
    result = ydl.urlopen('http://public.example/body')
    assert transport_network.closed == 0
    if close_by == 'caller':
        result.close()
    else:
        ydl.close()
    assert transport_network.closed == 1
    ydl.close()


def test_http_error_response_stays_live_until_closed(transport_network):
    transport_network.replies = [reply(b'no', status=b'404 Not Found')]
    with guarded() as ydl:
        with pytest.raises(HTTPError) as error:
            ydl.urlopen('http://public.example/body')
        assert error.value.response.status == 404
        assert error.value.response.read() == b'no'
        error.value.close()
    assert transport_network.closed == 1


def test_response_limit_closes_and_never_exposes_excess(transport_network):
    transport_network.replies = [reply(b'abcd')]
    with guarded(max_bytes=3) as ydl:
        result = ydl.urlopen('http://public.example/body')
        with pytest.raises(RequestError) as error:
            result.read()
        safe(error.value)
    assert transport_network.closed == 1


def test_unknown_read_error_closes_owned_client_and_removes_context(install):
    def broken():
        yield b'a'
        raise RuntimeError('synthetic-secret')
    wire = Wire([])
    wire.chunks = broken()
    import httpx
    fake = install(lambda request: httpx.Response(200, stream=wire))
    with guarded() as ydl:
        result = ydl.urlopen('https://public.example/body?sig=synthetic-secret')
        assert result.read(1) == b'a'
        with pytest.raises(RequestError) as error:
            result.read()
        safe(error.value)
    assert wire.closed and fake.closed


def test_bridge_constructor_failure_closes_live_exchange(transport_network, monkeypatch):
    from app.services import ytdlp_service
    transport_network.replies = [reply(b'abc')]
    def broken(*args):
        raise RuntimeError('synthetic-secret')
    monkeypatch.setattr(ytdlp_service._ControlledYtdlpResponse, '__init__', broken)
    with guarded() as ydl:
        with pytest.raises(RequestError) as error:
            ydl.urlopen('http://public.example/body?sig=synthetic-secret')
        safe(error.value)
    assert transport_network.closed == 1


@pytest.mark.parametrize('expiry', ['phase', 'operation'])
def test_expiry_after_bridge_construction_closes_before_caller_can_receive_it(expiry, transport_network, monkeypatch):
    from app.services import ytdlp_service
    now = [0.]
    network = context(lambda: now[0])
    transport_network.replies = [reply(b'abc')]
    original = ytdlp_service._ControlledYtdlpResponse.__init__
    def advance(bridge, *args):
        original(bridge, *args)
        now[0] = 2. if expiry == 'phase' else 101.
    monkeypatch.setattr(ytdlp_service._ControlledYtdlpResponse, '__init__', advance)
    ydl = guarded(network, phase_seconds=1)
    try:
        with pytest.raises(RequestError) as error:
            ydl.urlopen('http://public.example/body')
        safe(error.value)
        assert transport_network.closed == 1
        assert not next(iter(ydl._request_director.handlers.values()))._responses
    finally:
        ydl.close()


@pytest.mark.parametrize('status', [b'200 OK', b'404 Not Found'])
@pytest.mark.parametrize('expiry', ['phase', 'operation'])
def test_outer_urlopen_postcheck_closes_normal_and_http_error_responses(status, expiry, transport_network, monkeypatch):
    import yt_dlp
    now = [0.]
    transport_network.replies = [reply(b'abc', status=status)]
    real_open = yt_dlp.YoutubeDL.urlopen
    def delayed(ydl, request):
        try:
            return real_open(ydl, request)
        finally:
            now[0] = 2. if expiry == 'phase' else 101.
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'urlopen', delayed)
    ydl = guarded(context(lambda: now[0]), phase_seconds=1)
    try:
        with pytest.raises(RequestError) as error:
            ydl.urlopen('http://public.example/body')
        safe(error.value)
        assert not isinstance(error.value, HTTPError)
        assert transport_network.closed == 1
        assert not next(iter(ydl._request_director.handlers.values()))._responses
    finally:
        ydl.close()


@pytest.mark.parametrize('status', [b'200 OK', b'404 Not Found'])
@pytest.mark.parametrize('failure', ['deadline', 'policy'])
def test_extractor_terminal_failure_closes_its_unread_owned_responses(status, failure, transport_network):
    from yt_dlp.extractor.common import InfoExtractor
    from app.services.outbound_policy import OutboundError
    now = [0.]
    transport_network.replies = [reply(b'abc', status=status)]
    class HoldingIE(InfoExtractor):
        _VALID_URL = r'http://public\.example/(?P<id>[a-z]+)'
        def _real_extract(self, url):
            try:
                self._downloader.urlopen(url)
            except HTTPError:
                pass
            if failure == 'deadline':
                now[0] = 101.
            else:
                try:
                    self._downloader.urlopen('http://127.0.0.1/private')
                except Exception:
                    pass
            return {'id': 'fixture', 'title': 'fake success'}
    ydl = guarded(context(lambda: now[0]))
    ydl.add_info_extractor(HoldingIE())
    try:
        with pytest.raises(OutboundError) as error:
            ydl.extract_info('http://public.example/page', download=False, process=False)
        safe(error.value)
        assert transport_network.closed == 1
        assert not next(iter(ydl._request_director.handlers.values()))._responses
    finally:
        ydl.close()
