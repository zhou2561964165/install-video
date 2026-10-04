import json
from types import SimpleNamespace

import httpx
import pytest

from app.services import network_retry, subtitle_service, subtitle_sources
from app.services.subtitle_service import SubtitleServiceError, fetch_subtitle_document
from app.services.subtitle_sources import resolve_public_subtitles


class _TrackedStream(httpx.SyncByteStream):
    def __init__(self, body: bytes):
        self.body = body
        self.consumed = False
        self.closed = False

    def __iter__(self):
        self.consumed = True
        yield self.body

    def close(self):
        self.closed = True


def _patch_retry_sleep(monkeypatch, delays, assert_retry_ready=None):
    real_retry_get = network_retry.retry_get

    def retry_without_wait(get, *, max_retries, backoff_seconds):
        def record_delay(delay):
            if assert_retry_ready is not None:
                assert_retry_ready()
            delays.append(delay)

        return real_retry_get(
            get,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            sleep=record_delay,
        )

    monkeypatch.setattr(network_retry, "retry_get", retry_without_wait)


def test_archive_metadata_get_retries_503_and_closes_each_response(monkeypatch):
    delays = []
    streams = []
    requests = []
    monkeypatch.setattr(
        subtitle_sources,
        "settings",
        SimpleNamespace(
            subtitle_timeout_seconds=1,
            subtitle_max_bytes=1024,
            network_retries=1,
            network_retry_backoff_seconds=0.2,
        ),
    )

    def assert_error_stream_closed_before_retry():
        assert streams
        assert not streams[-1].consumed
        assert streams[-1].closed

    _patch_retry_sleep(monkeypatch, delays, assert_error_stream_closed_before_retry)

    metadata = {"metadata": {"title": "Lecture", "language": "en"}, "files": [{"name": "lecture.en.vtt"}]}

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            stream = _TrackedStream(b"temporary gateway error")
            streams.append(stream)
            return httpx.Response(503, stream=stream, request=request)
        stream = _TrackedStream(json.dumps(metadata).encode())
        streams.append(stream)
        return httpx.Response(200, stream=stream, request=request)

    real_client = httpx.Client
    monkeypatch.setattr(
        subtitle_sources.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    result = resolve_public_subtitles("https://archive.org/details/lecture-item")

    assert len(requests) == 2
    assert delays == [0.2]
    assert not streams[0].consumed and streams[0].closed
    assert streams[1].consumed and streams[1].closed
    assert result["title"] == "Lecture"
    assert result["tracks"][0]["language"] == "en"


def test_archive_invalid_metadata_is_not_retried(monkeypatch):
    delays = []
    requests = []
    monkeypatch.setattr(
        subtitle_sources,
        "settings",
        SimpleNamespace(
            subtitle_timeout_seconds=1,
            subtitle_max_bytes=1024,
            network_retries=2,
            network_retry_backoff_seconds=0.2,
        ),
    )

    def assert_error_stream_closed_before_retry():
        assert streams
        assert not streams[-1].consumed
        assert streams[-1].closed

    _patch_retry_sleep(monkeypatch, delays, assert_error_stream_closed_before_retry)

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b"not json", request=request)

    real_client = httpx.Client
    monkeypatch.setattr(
        subtitle_sources.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    with pytest.raises(json.JSONDecodeError):
        resolve_public_subtitles("https://archive.org/details/lecture-item")

    assert len(requests) == 1
    assert delays == []


def test_selected_subtitle_body_get_retries_and_returns_complete_document(monkeypatch):
    delays = []
    streams = []
    requests = []
    monkeypatch.setattr(
        subtitle_service,
        "settings",
        SimpleNamespace(
            subtitle_max_bytes=1024,
            network_retries=1,
            network_retry_backoff_seconds=0.3,
        ),
    )
    monkeypatch.setattr(
        subtitle_service.ytdlp_service,
        "extract_subtitle_tracks",
        lambda url: {
            "title": "Lecture",
            "tracks": [{
                "language": "en",
                "is_auto": False,
                "formats": [{"url": "https://cdn.example/lecture.vtt", "ext": "vtt", "http_headers": {}}],
            }],
        },
    )
    _patch_retry_sleep(monkeypatch, delays)

    body = b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n\n00:00:01.000 --> 00:00:02.000\nworld"

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            stream = _TrackedStream(b"temporarily unavailable")
            streams.append(stream)
            return httpx.Response(502, stream=stream, request=request)
        stream = _TrackedStream(body)
        streams.append(stream)
        return httpx.Response(200, stream=stream, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_subtitle_document("https://example.com/lecture", client=client)

    assert len(requests) == 2
    assert delays == [0.3]
    assert not streams[0].consumed and streams[0].closed
    assert streams[1].consumed and streams[1].closed
    assert result.title == "Lecture"
    assert result.text == "hello\nworld"


def test_missing_captions_do_not_issue_a_retryable_body_get(monkeypatch):
    monkeypatch.setattr(
        subtitle_service.ytdlp_service,
        "extract_subtitle_tracks",
        lambda url: {"title": "Lecture", "tracks": []},
    )

    class UnexpectedClient:
        def stream(self, *args, **kwargs):
            raise AssertionError("no-caption result must not make a body request")

    with pytest.raises(SubtitleServiceError) as raised:
        fetch_subtitle_document("https://example.com/lecture", client=UnexpectedClient())

    assert raised.value.error_type == "subtitle_unavailable"
