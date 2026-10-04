import json

import httpx
import pytest

from app.services import subtitle_service
from app.services.subtitle_service import SubtitleServiceError, fetch_subtitle_document, parse_subtitle_text


@pytest.mark.parametrize(
    ("ext", "raw", "expected"),
    [
        ("vtt", "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<b>你好</b>\n\n00:00:01.000 --> 00:00:02.000\n世界", "你好\n世界"),
        ("srt", "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld", "Hello\nWorld"),
        ("json3", json.dumps({"events": [{"segs": [{"utf8": "A"}, {"utf8": "B"}]}, {"segs": [{"utf8": "C"}]}]}), "AB\nC"),
        ("ttml", '<tt xmlns="http://www.w3.org/ns/ttml"><body><p>第一句</p><p>第二句</p></body></tt>', "第一句\n第二句"),
    ],
)
def test_parse_subtitle_text(ext, raw, expected):
    assert parse_subtitle_text(raw, ext) == expected


class _FakeClient:
    def __init__(self, body: bytes):
        self.body = body
        self.calls = []

    def stream(self, method, url, headers):
        self.calls.append((url, headers))
        return httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=self.body)
        )).stream(method, url, headers=headers)


def test_fetch_prefers_manual_track_and_format(monkeypatch):
    monkeypatch.setattr(
        subtitle_service.ytdlp_service,
        "extract_subtitle_tracks",
        lambda url: {
            "title": "视频",
            "tracks": [
                {"language": "en", "is_auto": True, "formats": [{"url": "https://cdn/auto.vtt", "ext": "vtt", "http_headers": {}}]},
                {"language": "zh-Hans", "is_auto": False, "formats": [
                    {"url": "https://cdn/manual.json3", "ext": "json3", "http_headers": {}},
                    {"url": "https://cdn/manual.vtt", "ext": "vtt", "http_headers": {"Referer": "https://example.com"}},
                ]},
            ],
        },
    )
    client = _FakeClient(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello")
    doc = fetch_subtitle_document("https://example.com/v", client=client)
    assert doc.language == "zh-Hans"
    assert doc.is_auto is False
    assert doc.text == "hello"
    assert client.calls == [("https://cdn/manual.vtt", {"Referer": "https://example.com"})]


def test_requested_language_reports_available(monkeypatch):
    monkeypatch.setattr(
        subtitle_service.ytdlp_service,
        "extract_subtitle_tracks",
        lambda url: {
            "title": "视频",
            "tracks": [{"language": "en", "is_auto": False, "formats": [{"url": "https://cdn/en.vtt", "ext": "vtt", "http_headers": {}}]}],
        },
    )
    with pytest.raises(SubtitleServiceError) as exc:
        fetch_subtitle_document("https://example.com/v", "ja", client=_FakeClient(b""))
    assert exc.value.error_type == "subtitle_unavailable"
    assert exc.value.available_languages == ["en"]


def test_vtt_metadata_and_cue_identifier_are_not_transcript():
    raw = '\ufeffWEBVTT - captions\nKind: captions\n\nNOTE metadata\nnot spoken\n\nSTYLE\n::cue { color: red; }\n\ncue-first\n00:00:00.000 --> 00:00:01.000\nHello\n\ncue-second\n00:00:01.000 --> 00:00:02.000\nWorld'
    assert parse_subtitle_text(raw, "vtt") == "Hello\nWorld"


def test_large_srt_with_two_fraction_digits_matches_vtt_captions():
    expected = [
        f"caption cue {index:04d} includes representative long sample text for parser regression"
        for index in range(300)
    ]
    srt = "\n\n".join(
        f"{index}\n00:00:00,12 --> 00:00:01,34\n{text}"
        for index, text in enumerate(expected, 1)
    )
    vtt = "WEBVTT\n\n" + "\n\n".join(
        f"cue-{index}\n00:00:00.12 --> 00:00:01.34\n{text}"
        for index, text in enumerate(expected, 1)
    )

    srt_text = parse_subtitle_text(srt, "srt")
    vtt_text = parse_subtitle_text(vtt, "vtt")

    assert srt_text == "\n".join(expected)
    assert vtt_text == srt_text
    assert len(srt_text) > 20_000


@pytest.mark.parametrize('fraction', ['1', '49', '490'])
def test_caption_fraction_precision_is_tolerated(fraction):
    raw = f'1\n00:00:00,{fraction} --> 00:00:05,82\n42\n'
    assert parse_subtitle_text(raw, 'srt') == '42'


def test_ttml_line_break_preserves_word_boundary():
    raw = '<tt><body><p>Hello<br/>world</p></body></tt>'
    assert parse_subtitle_text(raw, "ttml") == "Hello world"


@pytest.mark.parametrize("raw", ['[]', '{"events":[null]}', '{"events":[{"segs":[null]}]}'])
def test_malformed_json3_reports_subtitle_invalid(raw):
    with pytest.raises(SubtitleServiceError) as exc:
        parse_subtitle_text(raw, "json3")
    assert exc.value.error_type == "subtitle_invalid"


def test_oversized_subtitle_stops_reading_before_entire_body(monkeypatch):
    monkeypatch.setattr(subtitle_service.settings, "subtitle_max_bytes", 10)
    monkeypatch.setattr(subtitle_service.ytdlp_service, "extract_subtitle_tracks", lambda url: {
        "title": "t", "tracks": [{"language": "en", "is_auto": False, "formats": [
            {"url": "https://cdn/en.vtt", "ext": "vtt", "http_headers": {}}
        ]}]
    })
    chunks_read = []

    class LargeStream(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(100):
                chunks_read.append(i)
                yield b"0123456789"

    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=LargeStream()))) as client:
        with pytest.raises(SubtitleServiceError) as exc:
            fetch_subtitle_document("https://example.com/v", client=client)
    assert exc.value.error_type == "subtitle_too_large"
    assert len(chunks_read) < 100
