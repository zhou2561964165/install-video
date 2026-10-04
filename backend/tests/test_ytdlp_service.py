import yt_dlp.utils
import httpx
import pytest

from app.config import settings
from app.services.ytdlp_service import (
    classify_error,
    download,
    extract_info,
    extract_subtitle_tracks,
    parse_video,
    is_valid_url,
)


class _FakeError(Exception):
    pass


def _err(msg: str) -> Exception:
    return yt_dlp.utils.ExtractorError(msg)


def test_is_valid_url():
    assert is_valid_url("https://www.youtube.com/watch?v=x") is True
    assert is_valid_url("http://example.com/v") is True
    assert is_valid_url("not a url") is False
    assert is_valid_url("ftp://example.com/v") is False


def test_classify_geo_restricted():
    assert (
        classify_error(yt_dlp.utils.GeoRestrictedError("blocked here"))
        == "geo_blocked"
    )


def test_classify_unsupported():
    assert classify_error(yt_dlp.utils.UnsupportedError("x")) == "unsupported_site"


def test_classify_drm():
    assert classify_error(_err("This video is DRM protected")) == "drm"


def test_classify_login_required():
    assert classify_error(_err("Sign in to your account to continue")) == "login_required"


def test_classify_age_restricted():
    assert classify_error(_err("Video is age restricted")) == "age_restricted"


def test_classify_network_fallback():
    assert classify_error(_err("something totally unknown")) == "network"


def test_extract_info_calls_ydl(monkeypatch):
    calls = {}

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            calls["url"] = url
            calls["download"] = download
            return {"id": "x", "title": "t"}

    monkeypatch.setattr("app.services.ytdlp_service.yt_dlp.YoutubeDL", FakeYDL)
    info = extract_info("https://example.com/v")
    assert calls == {"url": "https://example.com/v", "download": False}
    assert info["title"] == "t"


def test_extract_subtitle_tracks_normalizes_manual_and_auto(monkeypatch):
    monkeypatch.setattr(
        "app.services.ytdlp_service.extract_info",
        lambda url: {
            "title": "T",
            "subtitles": {"zh-Hans": [{"ext": "vtt", "url": "https://cdn/manual.vtt"}]},
            "automatic_captions": {"en": [{"ext": "json3", "url": "https://cdn/auto.json3"}]},
        },
    )
    payload = extract_subtitle_tracks("https://example.com/v")
    assert payload["title"] == "T"
    assert [(item["language"], item["is_auto"]) for item in payload["tracks"]] == [
        ("zh-Hans", False),
        ("en", True),
    ]


def test_subtitle_track_inherits_extractor_headers(monkeypatch):
    monkeypatch.setattr("app.services.ytdlp_service.extract_info", lambda url: {
        "http_headers": {"Referer": "https://example.com/video"},
        "subtitles": {"en": [{"ext": "vtt", "url": "https://cdn/track.vtt"}]},
    })
    tracks = extract_subtitle_tracks("https://example.com/video")["tracks"]
    assert tracks[0]["formats"][0]["http_headers"] == {"Referer": "https://example.com/video"}


def test_live_chat_is_not_advertised_or_selected_as_subtitles(monkeypatch):
    monkeypatch.setattr("app.services.ytdlp_service.extract_info", lambda url: {
        "subtitles": {"live_chat": [{"url": "https://example.com/watch", "ext": "json", "protocol": "youtube_live_chat_replay"}]},
        "automatic_captions": {"en": [{"url": "https://cdn/en.vtt", "ext": "vtt"}]},
    })
    assert [t["language"] for t in extract_subtitle_tracks("https://example.com/v")["tracks"]] == ["en"]
    assert parse_video("https://example.com/v")[0]["subtitles"] == ["en"]


def test_archive_public_caption_metadata_fallback_supplies_tracks_and_parse_languages(monkeypatch):
    monkeypatch.setattr('app.services.ytdlp_service.extract_info', lambda url: {'title': 'T', 'subtitles': {}})
    metadata = {
        'metadata': {'title': 'T', 'language': 'English'},
        'files': [
            {'name': 'lecture.en.vtt', 'format': 'Web Video Text Tracks'},
            {'name': 'lecture.fr.vtt', 'format': 'Web Video Text Tracks'},
            {'name': 'lecture.asr.srt', 'format': 'SubRip'},
            {'name': 'restricted.en.vtt', 'private': True},
            {'name': 'item_files.xml', 'format': 'Metadata'},
        ],
    }
    real_client = httpx.Client
    requests = []

    def server(request):
        requests.append(str(request.url))
        return httpx.Response(200, json=metadata)

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(server), **kwargs))
    payload = extract_subtitle_tracks('https://archive.org/details/example-item')
    assert [(t['language'], t['is_auto']) for t in payload['tracks']] == [('en', False), ('fr', False), ('en', True)]
    assert payload['tracks'][0]['formats'][0]['url'] == 'https://archive.org/download/example-item/lecture.en.vtt'
    assert all('restricted' not in f['url'] for t in payload['tracks'] for f in t['formats'])
    assert parse_video('https://archive.org/details/example-item')[0]['subtitles'] == ['en', 'fr']
    assert requests == ['https://archive.org/metadata/example-item'] * 2


def test_archive_fallback_does_not_query_other_domains(monkeypatch):
    monkeypatch.setattr('app.services.ytdlp_service.extract_info', lambda url: {'title': 'T'})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: (_ for _ in ()).throw(AssertionError('unexpected HTTP request')))
    assert extract_subtitle_tracks('https://example.com/video?source=archive.org')['tracks'] == []


def test_danmaku_is_not_used_as_video_content_for_summary(monkeypatch):
    monkeypatch.setattr('app.services.ytdlp_service.extract_info', lambda url: {
        'subtitles': {'danmaku': [{'ext': 'xml', 'url': 'https://cdn/comments.xml'}]},
        'automatic_captions': {'zh-Hans': [{'ext': 'vtt', 'url': 'https://cdn/speech.vtt'}]},
    })
    assert [t['language'] for t in extract_subtitle_tracks('https://example.com/video')['tracks']] == ['zh-Hans']
    assert parse_video('https://example.com/video')[0]['subtitles'] == ['zh-Hans']


def test_archive_summary_content_does_not_depend_on_video_webpage_extraction(monkeypatch):
    monkeypatch.setattr('app.services.ytdlp_service.extract_info', lambda url: (_ for _ in ()).throw(AssertionError('video extractor should not run')))
    real_client = httpx.Client
    metadata = {'metadata': {'title': 'T', 'language': 'English'}, 'files': [{'name': 'video.asr.vtt'}]}
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=metadata)), **kwargs))
    result = extract_subtitle_tracks('https://archive.org/details/test-item')
    assert result['tracks'][0]['language'] == 'en'


def test_native_subtitles_remain_available_if_optional_platform_adapter_fails(monkeypatch):
    monkeypatch.setattr('app.services.ytdlp_service.extract_info', lambda url: {
        'title': 'T', 'subtitles': {'en': [{'url': 'https://archive.org/native.vtt', 'ext': 'vtt'}]},
    })
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(503)), **kwargs))
    result = extract_subtitle_tracks('https://archive.org/details/test-item')
    assert result['tracks'][0]['formats'][0]['url'] == 'https://archive.org/native.vtt'


def test_file_specific_archive_link_cannot_take_part2_captions(monkeypatch):
    real_client = httpx.Client
    metadata = {'metadata': {'title': 'T'}, 'files': [
        {'name': 'movie.mp4'}, {'name': 'movie.part2.mp4'},
        {'name': 'movie.part2.en.vtt'}, {'name': 'movie.en.vtt'},
    ]}
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=metadata)), **kwargs))
    result = extract_subtitle_tracks('https://archive.org/download/item/movie.mp4')
    assert [f['name'] for t in result['tracks'] for f in t['formats']] == ['movie.en.vtt']


@pytest.mark.parametrize('metadata', [
    {'metadata': 'bad', 'files': []}, {'metadata': {}, 'files': [None]},
    {'metadata': {}, 'files': 'bad'}, {'metadata': {'title': ['bad']}, 'files': []},
])
def test_bad_platform_metadata_does_not_break_native_caption_or_video_parse(monkeypatch, metadata):
    monkeypatch.setattr('app.services.ytdlp_service.extract_info', lambda url: {
        'title': 'T', 'subtitles': {'en': [{'url': 'https://archive.org/native.vtt', 'ext': 'vtt'}]},
    })
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=metadata)), **kwargs))
    assert extract_subtitle_tracks('https://archive.org/details/item')['tracks'][0]['language'] == 'en'
    monkeypatch.setattr('app.services.ytdlp_service.extract_info', lambda url: {'title': 'T'})
    assert parse_video('https://archive.org/details/item')[0]['title'] == 'T'


def test_multi_video_archive_item_does_not_mix_caption_sources(monkeypatch):
    from app.services.subtitle_sources import resolve_public_subtitles
    real_client = httpx.Client
    metadata = {'metadata': {'title': 'Playlist'}, 'files': [
        {'name': 'movie.en.vtt'}, {'name': 'movie.part2.en.vtt'},
    ]}
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=metadata)), **kwargs))
    with pytest.raises(ValueError, match='多个'):
        resolve_public_subtitles('https://archive.org/details/item')


class _FakeDownloadYDL:
    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        return {"id": "x"}

    def prepare_filename(self, info):
        return "out.mp4"


def _run_download_capture(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        "app.services.ytdlp_service.yt_dlp.YoutubeDL",
        lambda opts: _capturing(opts, captured),
    )
    out = tmp_path / "job"
    out.mkdir()
    (out / "out.mp4").write_bytes(b"x")
    download("https://example.com/v", "best", str(out / "%(title)s.%(ext)s"), lambda d: None)
    return captured


class _capturing(_FakeDownloadYDL):
    def __init__(self, opts, captured):
        super().__init__(opts)
        captured["opts"] = opts


def test_download_passes_custom_ffmpeg_location(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ffmpeg_path", "C:/ffmpeg/ffmpeg.exe")
    captured = _run_download_capture(monkeypatch, tmp_path)
    assert captured["opts"]["ffmpeg_location"] == "C:/ffmpeg/ffmpeg.exe"


def test_download_default_ffmpeg_omits_location(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ffmpeg_path", "ffmpeg")
    captured = _run_download_capture(monkeypatch, tmp_path)
    assert "ffmpeg_location" not in captured["opts"]
