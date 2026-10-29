"""C4 Task 3: streaming from an already-open file with single-range support and read-lease renewal (no DB)."""
import anyio
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from app.services import file_stream

DATA = bytes(range(256)) * 20  # 5120 bytes, every offset distinguishable
ETAG = '"sha256-' + 'ab' * 32 + '"'


class Calls:
    def __init__(self, renew_results=()):
        self.renewals, self.ended, self.results = 0, 0, list(renew_results)

    def renew(self):
        self.renewals += 1
        return self.results.pop(0) if self.results else True

    def end(self):
        self.ended += 1


def make_file(tmp_path):
    path = tmp_path / 'media.mp4'
    path.write_bytes(DATA)
    return open(path, 'rb')


def client_for(tmp_path, calls, **options):
    handles = []

    def endpoint(request):
        handle = make_file(tmp_path)
        handles.append(handle)
        return file_stream.stream_response(
            handle, len(DATA), etag=ETAG, filename=options.pop('filename', '视频 title.mp4'), media_type='video/mp4',
            range_header=request.headers.get('range'), if_range=request.headers.get('if-range'),
            renew=calls.renew, end=calls.end, **options)
    return TestClient(Starlette(routes=[Route('/f', endpoint)])), handles


def test_full_response_headers_and_body(tmp_path):
    calls = Calls()
    client, handles = client_for(tmp_path, calls)
    response = client.get('/f')
    assert response.status_code == 200 and response.content == DATA
    assert response.headers['accept-ranges'] == 'bytes' and response.headers['etag'] == ETAG
    assert response.headers['content-length'] == str(len(DATA))
    disposition = response.headers['content-disposition']
    assert disposition.startswith('attachment;') and "filename*=UTF-8''%E8%A7%86%E9%A2%91%20title.mp4" in disposition
    assert calls.ended == 1 and handles[0].closed


@pytest.mark.parametrize('header,start,end', [('bytes=0-9', 0, 9), ('bytes=100-', 100, 5119),
                                              ('bytes=-5', 5115, 5119), ('bytes=5000-99999', 5000, 5119)])
def test_single_range_is_partial_content(tmp_path, header, start, end):
    calls = Calls()
    client, handles = client_for(tmp_path, calls)
    response = client.get('/f', headers={'Range': header})
    assert response.status_code == 206 and response.content == DATA[start:end + 1]
    assert response.headers['content-range'] == f'bytes {start}-{end}/{len(DATA)}'
    assert calls.ended == 1 and handles[0].closed


@pytest.mark.parametrize('header', ['bytes=0-1,4-5', 'items=0-5', 'bytes=abc', 'bytes=9-3'])
def test_multi_or_malformed_range_is_ignored(tmp_path, header):
    client, _ = client_for(tmp_path, Calls())
    response = client.get('/f', headers={'Range': header})
    assert response.status_code == 200 and response.content == DATA


def test_unsatisfiable_range(tmp_path):
    calls = Calls()
    client, handles = client_for(tmp_path, calls)
    response = client.get('/f', headers={'Range': 'bytes=6000-'})
    assert response.status_code == 416 and response.headers['content-range'] == f'bytes */{len(DATA)}'
    assert calls.ended == 1 and handles[0].closed


def test_if_range_must_match_strong_etag(tmp_path):
    client, _ = client_for(tmp_path, Calls())
    assert client.get('/f', headers={'Range': 'bytes=0-9', 'If-Range': '"other"'}).status_code == 200
    assert client.get('/f', headers={'Range': 'bytes=0-9', 'If-Range': ETAG}).status_code == 206


def drain(response):
    async def run():
        received = b''
        async for chunk in response.body_iterator:
            received += chunk
        return received
    return anyio.run(run)


def test_renew_failure_stops_stream(tmp_path):
    calls = Calls(renew_results=[True, False])
    handle = make_file(tmp_path)
    response = file_stream.stream_response(handle, len(DATA), etag=ETAG, filename='a.mp4', media_type='video/mp4',
                                           range_header=None, if_range=None, renew=calls.renew, end=calls.end,
                                           renew_seconds=0, chunk_size=1024)
    with pytest.raises(file_stream.ReadAborted):
        drain(response)
    assert calls.renewals == 2 and calls.ended == 1 and handle.closed


def test_max_duration_stops_stream(tmp_path):
    ticks = iter([0.0, 0.0, 1801.0, 1801.0, 1801.0])
    calls = Calls()
    handle = make_file(tmp_path)
    response = file_stream.stream_response(handle, len(DATA), etag=ETAG, filename='a.mp4', media_type='video/mp4',
                                           range_header=None, if_range=None, renew=calls.renew, end=calls.end,
                                           chunk_size=1024, clock=lambda: next(ticks))
    with pytest.raises(file_stream.ReadAborted):
        drain(response)
    assert calls.ended == 1 and handle.closed


def test_renewal_happens_periodically(tmp_path):
    ticks = iter([0.0] + [i * 4.0 for i in range(1, 30)])  # 4 s per chunk
    calls = Calls()
    handle = make_file(tmp_path)
    response = file_stream.stream_response(handle, len(DATA), etag=ETAG, filename='a.mp4', media_type='video/mp4',
                                           range_header=None, if_range=None, renew=calls.renew, end=calls.end,
                                           chunk_size=1024, clock=lambda: next(ticks))
    assert drain(response) == DATA
    assert calls.renewals == 2 and calls.ended == 1  # 5 chunks x 4 s = 20 s -> renewed at 10 s and 20 s


# C4 review I3: an absurd Range number is ignored, never an exception (Python int digit limit).
def test_oversized_range_number_is_ignored():
    assert file_stream.parse_range('bytes=' + '9' * 5000 + '-', 100) is None
    assert file_stream.parse_range('bytes=0-' + '9' * 5000, 100) is None


def new_response(tmp_path, calls, **options):
    handle = make_file(tmp_path)
    response = file_stream.stream_response(handle, len(DATA), etag=ETAG, filename='a.mp4', media_type='video/mp4',
                                           range_header=None, if_range=None, renew=calls.renew, end=calls.end,
                                           chunk_size=1024, **options)
    return handle, response


# C4 review I2: a client disconnect cancels the transfer; the read still ends and the file still closes.
def test_cancelled_transfer_still_finishes(tmp_path):
    calls = Calls()
    handle, response = new_response(tmp_path, calls)

    async def run():
        with anyio.CancelScope() as scope:
            async for _ in response.body_iterator:
                scope.cancel()  # what Starlette does on http.disconnect; the next step is cancelled
    anyio.run(run)
    assert calls.ended == 1 and handle.closed


def test_response_never_iterated_still_finishes(tmp_path):
    calls = Calls()
    handle, response = new_response(tmp_path, calls)
    scope = {'type': 'http', 'asgi': {'spec_version': '2.4'}, 'method': 'GET', 'headers': [], 'extensions': {}}

    async def receive():
        return {'type': 'http.disconnect'}

    async def send(message):
        raise OSError('client gone before the response started')

    from starlette.requests import ClientDisconnect
    with pytest.raises((OSError, ClientDisconnect)):  # Starlette reports a failed send as ClientDisconnect
        anyio.run(response, scope, receive, send)
    assert calls.ended == 1 and handle.closed


# C4 review minor 4: after a stall, renew once and continue the schedule (no immediate second renewal).
def test_stall_renews_once(tmp_path):
    ticks = iter([0.0, 35.0, 36.0, 37.0, 38.0, 39.0, 40.0, 41.0])
    calls = Calls()
    handle, response = new_response(tmp_path, calls, clock=lambda: next(ticks))
    assert drain(response) == DATA
    assert calls.renewals == 1 and calls.ended == 1
