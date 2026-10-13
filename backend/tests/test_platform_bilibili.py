import json

import httpx
import pytest

from app.config import settings
from app.services import subtitle_service, ytdlp_service


VIDEO = "https://www.bilibili.com/video/BV12N4y1M7rh"
CAPTION = "https://i0.hdslb.com/bfs/subtitle/manual.json"


def install_server(monkeypatch, *, view=None, player=None, content=None):
    real_client = httpx.Client
    requested = []
    view = view if view is not None else {"code": 0, "data": {"bvid": "BV12N4y1M7rh", "aid": 898179753, "title": "Lecture", "pages": [{"cid": 101, "page": 1}, {"cid": 202, "page": 2}]}}
    player = player if player is not None else {"code": 0, "data": {"subtitle": {"subtitles": [{"lan": "zh-Hans", "type": 0, "subtitle_url": CAPTION}]}}}

    def handler(request):
        requested.append(request)
        if request.url.path == "/x/web-interface/view":
            return httpx.Response(200, json=view)
        if request.url.path == "/x/v2/dm/view":
            return httpx.Response(200, json=player)
        if str(request.url) == CAPTION:
            return httpx.Response(200, json=content or {"body": [{"from": 0, "to": 1, "content": "First sentence"}, {"from": 1, "to": 2, "content": "Last conclusion"}]})
        raise AssertionError(f"Unexpected request {request.url}")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return requested


def test_bilibili_native_captions_bypass_video_extraction_and_preserve_part(monkeypatch):
    requested = install_server(monkeypatch)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: (_ for _ in ()).throw(AssertionError("Video extraction must not run")))
    payload = ytdlp_service.extract_subtitle_tracks(VIDEO + "?p=2")
    assert payload["title"] == "Lecture"
    assert payload["tracks"][0]["formats"][0]["url"] == CAPTION
    assert requested[1].url.params["oid"] == "202"
    assert requested[1].url.params["aid"] == "898179753"


def test_bilibili_json_body_flows_through_existing_document_contract(monkeypatch):
    install_server(monkeypatch)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "generic", "subtitles": {}})
    document = subtitle_service.fetch_subtitle_document(VIDEO)
    assert document.text == "First sentence\nLast conclusion"
    assert document.language == "zh-Hans"
    assert document.is_auto is False


@pytest.mark.parametrize("part", ["0", "-1", "x", "3", "2&p=1"])
def test_invalid_or_missing_bilibili_part_never_uses_another_parts_captions(monkeypatch, part):
    from app.services.subtitle_sources import resolve_public_subtitles
    requested = install_server(monkeypatch)
    with pytest.raises(ValueError):
        resolve_public_subtitles(VIDEO + "?p=" + part)
    assert all(r.url.path != "/x/v2/dm/view" for r in requested)


def test_bilibili_manual_priority_ai_language_normalization_and_protocol_relative_url(monkeypatch):
    install_server(monkeypatch, player={"code": 0, "data": {"subtitle": {"subtitles": [
        {"lan": "ai-zh", "type": 1, "subtitle_url": "//aisubtitle.hdslb.com/bfs/subtitle/auto.json"},
        {"lan": "en", "type": 0, "subtitle_url": "//i0.hdslb.com/bfs/subtitle/manual.json"},
    ]}}})
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"subtitles": {}})
    payload = ytdlp_service.extract_subtitle_tracks(VIDEO)
    assert [(t["language"], t["is_auto"]) for t in payload["tracks"]] == [("zh", True), ("en", False)]
    assert payload["tracks"][0]["formats"][0]["url"] == "https://aisubtitle.hdslb.com/bfs/subtitle/auto.json"
    assert subtitle_service._select_track(payload["tracks"], None)["language"] == "en"


@pytest.mark.parametrize("player", [
    {"code": 0, "data": {"subtitle": {"subtitles": []}}},
    {"code": -101, "data": None},
    {"code": 0, "data": {"need_login_subtitle": True}},
    {"code": 0, "data": {"subtitle": {"subtitles": "bad"}}},
    {"code": 0, "data": {"subtitle": {"subtitles": [None]}}},
    {"code": 0, "data": {"subtitle": {"subtitles": [{"lan": "en", "type": 0, "subtitle_url": "https://evil.example/subtitle.json"}]}}},
])
def test_native_empty_restricted_malformed_or_foreign_urls_retain_ytdlp_fallback(monkeypatch, player):
    install_server(monkeypatch, player=player)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "Generic", "subtitles": {"en": [{"url": "https://generic.example/en.vtt", "ext": "vtt"}]}})
    payload = ytdlp_service.extract_subtitle_tracks(VIDEO)
    assert payload["title"] == "Generic"
    assert payload["tracks"][0]["formats"][0]["url"] == "https://generic.example/en.vtt"


@pytest.mark.parametrize("url", ["https://example.com/?source=bilibili.com/video/BV12N4y1M7rh", "https://bilibili.com.evil.example/video/BV12N4y1M7rh", "https://www.bilibili.com/video/invalid"])
def test_bilibili_adapter_matches_exact_host_and_video_path(monkeypatch, url):
    from app.services.subtitle_sources import resolve_public_subtitles
    requested = install_server(monkeypatch)
    assert resolve_public_subtitles(url) == {"tracks": []}
    assert requested == []


@pytest.mark.parametrize("payload", [[], {"body": "bad"}, {"body": [None]}, {"body": [{"content": 42}]}, {"body": [{"from": 2, "to": 1, "content": "reversed"}]}, {"body": [{"from": True, "to": 1, "content": "bool"}]}])
def test_invalid_bilibili_caption_json_uses_subtitle_invalid(payload):
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.parse_subtitle_text(json.dumps(payload), "bilibili_json")
    assert error.value.error_type == "subtitle_invalid"


def test_bilibili_metadata_and_body_apply_byte_limit(monkeypatch):
    from app.services.subtitle_sources import resolve_public_subtitles
    install_server(monkeypatch)
    monkeypatch.setattr(settings, "subtitle_max_bytes", 20)
    with pytest.raises(ValueError, match="大小"):
        resolve_public_subtitles(VIDEO)
    monkeypatch.setattr(ytdlp_service, "extract_subtitle_tracks", lambda url: {"title": "T", "tracks": [{"language": "en", "is_auto": False, "formats": [{"url": CAPTION, "ext": "bilibili_json", "http_headers": {}}]}]})
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.fetch_subtitle_document(VIDEO)
    assert error.value.error_type == "subtitle_too_large"


def test_bilibili_transient_metadata_error_uses_bounded_retry(monkeypatch):
    real_client = httpx.Client
    attempts = []
    monkeypatch.setattr(settings, "network_retry_backoff_seconds", 0)
    def server(request):
        attempts.append(str(request.url))
        if len(attempts) == 1:
            raise httpx.ConnectError("temporary TLS error", request=request)
        if request.url.path.endswith("/view") and "bvid" in request.url.params:
            return httpx.Response(200, json={"code": 0, "data": {"bvid": "BV12N4y1M7rh", "aid": 1, "title": "Recovered", "pages": [{"page": 1, "cid": 10}]}})
        return httpx.Response(200, json={"code": 0, "data": {"subtitle": {"subtitles": [{"lan": "en", "type": 0, "subtitle_url": CAPTION}]}}})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(server), **kwargs))
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"subtitles": {}})
    assert ytdlp_service.extract_subtitle_tracks(VIDEO)["title"] == "Recovered"
    assert len(attempts) == 3


@pytest.mark.parametrize("native_error", ["http", "invalid", "language"])
def test_native_body_or_requested_language_failure_falls_back_once_to_inline_ytdlp(monkeypatch, native_error):
    real_client = httpx.Client
    content = {"body": [{"from": 0, "to": 1, "content": 42}]} if native_error == "invalid" else None
    install_server(monkeypatch, content=content)
    if native_error == "http":
        original = httpx.Client
        def client_factory(**kwargs):
            if "headers" in kwargs:
                return original(**kwargs)
            return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(403)), **kwargs)
        monkeypatch.setattr(httpx, "Client", client_factory)
    calls = []
    def generic(url):
        calls.append(url)
        return {"title": "Generic", "subtitles": {"en": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nRecovered generic content"}]}}
    monkeypatch.setattr(ytdlp_service, "extract_info", generic)
    doc = subtitle_service.fetch_subtitle_document(VIDEO, "en" if native_error == "language" else None)
    assert doc.text == "Recovered generic content"
    assert doc.title == "Generic"
    assert calls == [VIDEO]


def test_inline_generic_captions_enforce_byte_limit_without_http(monkeypatch):
    monkeypatch.setattr(settings, "subtitle_max_bytes", 20)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "T", "subtitles": {"en": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nToo long"}]}})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: (_ for _ in ()).throw(AssertionError("Inline data must not use HTTP")))
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.fetch_subtitle_document("https://example.com/video")
    assert error.value.error_type == "subtitle_too_large"


def test_empty_generic_fallback_preserves_meaningful_native_error(monkeypatch):
    install_server(monkeypatch, content={"body": [{"from": 0, "to": 1, "content": 42}]})
    calls = []
    def generic(url):
        calls.append(url)
        return {"subtitles": {}}
    monkeypatch.setattr(ytdlp_service, "extract_info", generic)
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.fetch_subtitle_document(VIDEO)
    assert error.value.error_type == "subtitle_invalid"
    assert calls == [VIDEO]


def test_generic_body_failure_does_not_reinvoke_extractor(monkeypatch):
    calls = []
    def generic(url):
        calls.append(url)
        return {"title": "T", "subtitles": {"en": [{"url": "https://example.com/en.vtt", "ext": "vtt"}]}}
    monkeypatch.setattr(ytdlp_service, "extract_info", generic)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(403))) as client:
        with pytest.raises(subtitle_service.SubtitleServiceError) as error:
            subtitle_service.fetch_subtitle_document("https://example.com/video", client=client)
    assert error.value.error_type == "subtitle_fetch_failed"
    assert calls == ["https://example.com/video"]


@pytest.mark.parametrize("url", ["http://i0.hdslb.com:80/bfs/subtitle/manual.json", "https://i0.hdslb.com:443/bfs/subtitle/manual.json"])
def test_bilibili_caption_url_upgrades_http_and_normalizes_default_port(monkeypatch, url):
    install_server(monkeypatch, player={"code": 0, "data": {"subtitle": {"subtitles": [{"lan": "en", "type": 0, "subtitle_url": url}]}}})
    payload = ytdlp_service.extract_subtitle_tracks(VIDEO)
    assert payload["tracks"][0]["formats"][0]["url"] == CAPTION


def test_bilibili_caption_redirect_cannot_change_source_host(monkeypatch):
    real_client = httpx.Client
    install_server(monkeypatch)
    original = httpx.Client
    def client_factory(**kwargs):
        if "headers" in kwargs:
            return original(**kwargs)
        def redirect(request):
            if request.url.host != "i0.hdslb.com":
                return httpx.Response(200, json={"body": [{"from": 0, "to": 1, "content": "Foreign source"}]})
            return httpx.Response(302, headers={"Location": "https://foreign.example/subtitle.json"})
        return real_client(transport=httpx.MockTransport(redirect), **kwargs)
    monkeypatch.setattr(httpx, "Client", client_factory)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"subtitles": {}})
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.fetch_subtitle_document(VIDEO)
    assert error.value.error_type == "subtitle_fetch_failed"


@pytest.mark.parametrize("view", [
    {"code": 0, "data": {"bvid": "BVother12345", "aid": 1, "title": "Wrong video", "pages": [{"page": 1, "cid": 5}]}},
    {"code": 0, "data": {"bvid": "BV12N4y1M7rh", "aid": True, "title": "Bad aid", "pages": [{"page": 1, "cid": 5}]}},
    {"code": 0, "data": {"bvid": "BV12N4y1M7rh", "aid": 1, "title": [], "pages": [{"page": 1, "cid": 5}]}},
    {"code": 0, "data": {"bvid": "BV12N4y1M7rh", "aid": 1, "title": "Ambiguous parts", "pages": [{"page": 1, "cid": 5}, {"page": 1, "cid": 6}]}},
])
def test_native_view_association_failure_retains_generic_captions(monkeypatch, view):
    requested = install_server(monkeypatch, view=view)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "Generic", "subtitles": {"en": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nGeneric fallback"}]}})
    assert subtitle_service.fetch_subtitle_document(VIDEO).text == "Generic fallback"
    assert all(r.url.path != "/x/v2/dm/view" for r in requested)


@pytest.mark.parametrize("part", ["0", "x", "3", "2&p=1"])
def test_invalid_user_part_is_rejected_at_public_entrypoint_before_generic_default(monkeypatch, part):
    install_server(monkeypatch)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "Wrong default part", "subtitles": {"en": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nWrong part"}]}})
    with pytest.raises(ValueError, match="分P"):
        ytdlp_service.extract_subtitle_tracks(VIDEO + "?p=" + part)


def test_invalid_user_part_is_reported_as_invalid_url_by_api_boundary(monkeypatch):
    from fastapi import HTTPException
    from app.routes.insight_common import load_subtitle
    install_server(monkeypatch)
    with pytest.raises(HTTPException) as error:
        load_subtitle(VIDEO + "?p=0", None)
    assert error.value.detail["error_type"] == "invalid_url"


def test_bilibili_generic_ai_language_keeps_automatic_identity_and_user_language_match(monkeypatch):
    install_server(monkeypatch, player={"code": 0, "data": {"subtitle": {"subtitles": []}}})
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "Generic AI", "subtitles": {"ai-zh": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nChinese automatic speech"}]}})
    document = subtitle_service.fetch_subtitle_document(VIDEO, "zh")
    assert document.language == "zh"
    assert document.is_auto is True
    assert document.text == "Chinese automatic speech"


def test_oversized_integer_bilibili_timestamp_is_subtitle_invalid():
    raw = json.dumps({"body": [{"from": 10 ** 400, "to": 10 ** 401, "content": "Too large"}]})
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.parse_subtitle_text(raw, "bilibili_json")
    assert error.value.error_type == "subtitle_invalid"


def test_oversized_bilibili_part_does_not_fall_back_to_default_video(monkeypatch):
    from app.services.bilibili_subtitle_source import InvalidVideoPartError
    requested = install_server(monkeypatch)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "Wrong default part", "subtitles": {"en": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nWrong part"}]}})
    with pytest.raises(InvalidVideoPartError) as error:
        ytdlp_service.extract_subtitle_tracks(VIDEO + "?p=" + "9" * 4301)
    assert ytdlp_service.classify_error(error.value) == "invalid_url"
    assert requested == []


@pytest.mark.parametrize("prefix", ["http://", "https://", "//"])
def test_production_ai_caption_url_upgrades_https_and_preserves_signature(prefix):
    from app.services.bilibili_subtitle_source import _caption_url

    path = "aisubtitle.hdslb.com/bfs/ai_subtitle/prod/0123456789abcdef_test-caption"
    assert _caption_url(prefix + path + "?auth_key=synthetic%2Fsignature&expires=123#fragment") == (
        "https://" + path + "?auth_key=synthetic%2Fsignature&expires=123"
    )


def test_sample_video_empty_query_fetches_production_ai_subtitle_without_generic_extraction(monkeypatch):
    real_client = httpx.Client
    video = "https://www.bilibili.com/video/BV1gPH96dEUC/?"
    caption = "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/test-caption?auth_key=synthetic"
    requested = []

    def handler(request):
        requested.append(request)
        if request.url.path == "/x/web-interface/view":
            return httpx.Response(200, json={"code": 0, "data": {
                "bvid": "BV1gPH96dEUC", "aid": 123, "title": "Sample",
                "pages": [{"page": 1, "cid": 456}],
            }})
        if request.url.path == "/x/v2/dm/view":
            return httpx.Response(200, json={"code": 0, "data": {"subtitle": {"subtitles": [
                {"lan": "ai-zh", "type": 1, "subtitle_url": caption.replace("https://", "http://")},
            ]}}})
        if str(request.url) == caption:
            return httpx.Response(200, json={"body": [{"from": 0, "to": 1, "content": "公开 AI 字幕"}]})
        raise AssertionError("Unexpected subtitle request")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: (_ for _ in ()).throw(AssertionError("Generic extraction must not run")))
    document = subtitle_service.fetch_subtitle_document(video)
    assert (document.title, document.language, document.is_auto, document.text) == (
        "Sample", "zh", True, "公开 AI 字幕",
    )
    assert len(requested) == 3
    assert requested[0].url.params["bvid"] == "BV1gPH96dEUC"
    assert requested[1].url.params["oid"] == "456"


@pytest.mark.parametrize("url", [
    "https://evil.example/bfs/ai_subtitle/prod/caption",
    "https://aisubtitle.hdslb.com.evil.example/bfs/ai_subtitle/prod/caption",
    "https://i0.hdslb.com/bfs/ai_subtitle/prod/caption",
    "https://aisubtitle.hdslb.com/bfs/ai_subtitle/staging/caption",
    "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/",
    "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/../private",
    "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/%2e%2e",
    "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/caption/other",
    "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/caption%2Fother",
    "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/caption.json",
    "https://user:password@aisubtitle.hdslb.com/bfs/ai_subtitle/prod/caption",
    "https://aisubtitle.hdslb.com:8080/bfs/ai_subtitle/prod/caption",
    "file://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/caption",
])
def test_production_ai_caption_support_keeps_trusted_host_and_path_boundary(url):
    from app.services.bilibili_subtitle_source import _caption_url

    with pytest.raises(ValueError, match="字幕来源地址无效"):
        _caption_url(url)


def test_production_ai_caption_rejects_semicolon_parameters():
    from app.services.bilibili_subtitle_source import _caption_url

    with pytest.raises(ValueError, match="字幕来源地址无效"):
        _caption_url(
            "https://aisubtitle.hdslb.com/bfs/ai_subtitle/prod/caption;extra?auth_key=synthetic"
        )
