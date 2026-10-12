import os
from pathlib import Path

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


@pytest.mark.parametrize("operation", ["extract_info", "get_direct_url", "download"])
def test_ydlp_calls_use_configured_finite_retries_and_exponential_backoff(
    monkeypatch, tmp_path, operation
):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download):
            info = {
                "id": "x",
                "formats": [{"format_id": "best", "url": "https://cdn.example/video.mp4"}],
            }
            if download:
                info["requested_downloads"] = [{
                    "filepath": str(Path(self.opts["outtmpl"]).parent / "out.mp4"),
                }]
            return info

        def prepare_filename(self, info):
            return str(Path(self.opts["outtmpl"]).parent / "out.mp4")

    monkeypatch.setattr(settings, "network_retries", 4)
    monkeypatch.setattr(settings, "network_retry_backoff_seconds", 0.25)
    monkeypatch.setattr("app.services.ytdlp_service.yt_dlp.YoutubeDL", FakeYDL)

    if operation == "extract_info":
        extract_info("https://example.com/v")
    elif operation == "get_direct_url":
        from app.services.ytdlp_service import get_direct_url

        assert get_direct_url("https://example.com/v", "best")[0] == "https://cdn.example/video.mp4"
    else:
        output_dir = tmp_path / "job"
        output_dir.mkdir()
        (output_dir / "out.mp4").write_bytes(b"video")
        download("https://example.com/v", "best", str(output_dir / "%(title)s.%(ext)s"), lambda _: None)

    options = captured["opts"]
    assert options["retries"] == 4
    assert options["extractor_retries"] == 4
    sleep_functions = options["retry_sleep_functions"]
    assert sleep_functions["http"](0) == 0.25
    assert sleep_functions["http"](1) == 0.5
    assert sleep_functions["http"](2) == 1.0
    assert sleep_functions["extractor"](0) == 0.25
    assert sleep_functions["extractor"](1) == 0.5
    assert sleep_functions["extractor"](2) == 1.0

    delays = []
    monkeypatch.setattr(yt_dlp.utils._utils.time, "sleep", delays.append)
    for count in (1, 2):
        yt_dlp.utils.RetryManager.report_retry(
            Exception("temporary failure"),
            count,
            4,
            sleep_func=sleep_functions["http"],
            info=lambda _: None,
            warn=lambda _: None,
        )
    assert delays == [0.25, 0.5]


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
        info = {"id": "x"}
        if download:
            info["requested_downloads"] = [{
                "filepath": str(Path(self.opts["outtmpl"]).parent / "out.mp4"),
            }]
        return info

    def prepare_filename(self, info):
        return str(Path(self.opts["outtmpl"]).parent / "out.mp4")


class _ArtifactDownloadYDL:
    def __init__(self, opts, info, prepared_filename):
        self.opts = opts
        self.info = info
        self.prepared_filename = prepared_filename

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        assert download is True
        return self.info

    def prepare_filename(self, info):
        return str(self.prepared_filename)


def _download_with_artifacts(monkeypatch, tmp_path, info, prepared_filename, artifacts):
    out_dir = tmp_path / "job"
    out_dir.mkdir()
    for filename, modified in artifacts:
        path = out_dir / filename
        path.write_bytes(b"offline test artifact")
        os.utime(path, (modified, modified))

    monkeypatch.setattr(
        "app.services.ytdlp_service.yt_dlp.YoutubeDL",
        lambda opts: _ArtifactDownloadYDL(opts, info, prepared_filename),
    )
    outtmpl = str(out_dir / "%(title)s.%(ext)s")
    return Path(download("https://example.com/v", "best", outtmpl, lambda _: None)), out_dir


def test_download_uses_ytdlp_final_filepath_instead_of_newer_unrelated_files(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    final_video = out_dir / "Original lesson.mp4"
    info = {"title": "Original lesson", "ext": "mp4", "requested_downloads": [{"filepath": str(final_video)}]}

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        out_dir / "Original lesson.mp4",
        [
            ("Original lesson.mp4", 10),
            ("课后总结.json", 20),
            ("课后总结.mp4", 30),
        ],
    )

    assert result == final_video


def test_download_uses_final_merged_filepath_not_premerge_filename(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    merged_video = out_dir / "Original lesson.mp4"
    info = {"title": "Original lesson", "ext": "webm", "requested_downloads": [{"filepath": str(merged_video)}]}

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        out_dir / "Original lesson.webm",
        [
            ("Original lesson.mp4", 10),
            ("Original lesson.webm", 20),
        ],
    )

    assert result == merged_video


@pytest.mark.parametrize("extension", ["ts", "mpeg", "asf", "m2ts"])
def test_download_accepts_video_containers_recognized_by_yt_dlp_mime_mapping(monkeypatch, tmp_path, extension):
    out_dir = tmp_path / "job"
    final_video = out_dir / f"Original lesson.{extension}"
    info = {
        "title": "Original lesson",
        "requested_downloads": [{"filepath": str(final_video), "vcodec": None}],
    }

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        final_video,
        [(final_video.name, 10)],
    )

    assert result == final_video


def test_download_rejects_asf_when_yt_dlp_marks_selected_format_audio_only(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    audio_path = out_dir / "Original lesson.asf"
    info = {
        "title": "Original lesson",
        "requested_downloads": [{"filepath": str(audio_path), "vcodec": "none"}],
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            audio_path,
            [(audio_path.name, 10)],
        )


def test_download_rejects_unrecognized_container_without_video_mime(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    candidate = out_dir / "Original lesson.vob"
    info = {
        "title": "Original lesson",
        "requested_downloads": [{"filepath": str(candidate), "vcodec": None}],
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            candidate,
            [(candidate.name, 10)],
        )


@pytest.mark.parametrize("video_metadata", [{"vcodec": "mpeg2video"}, {"height": 480}])
def test_download_accepts_vob_when_terminal_format_metadata_proves_video(monkeypatch, tmp_path, video_metadata):
    out_dir = tmp_path / "job"
    video_path = out_dir / "Original lesson.vob"
    info = {
        "title": "Original lesson",
        "ext": "vob",
        **video_metadata,
        # yt-dlp may remove fields equal to the parent from this processed entry.
        "requested_downloads": [{"filepath": str(video_path)}],
    }

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        video_path,
        [(video_path.name, 10)],
    )

    assert result == video_path


def test_download_accepts_vob_from_top_level_final_filepath_metadata(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    video_path = out_dir / "Original lesson.vob"
    info = {
        "title": "Original lesson",
        "filepath": str(video_path),
        "ext": "vob",
        "height": 576,
        "vcodec": "mpeg2video",
    }

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        video_path,
        [(video_path.name, 10)],
    )

    assert result == video_path


def test_download_accepts_generic_direct_vob_with_video_mime_format_id(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    video_path = out_dir / "Original lesson.vob"
    info = {
        "title": "Original lesson",
        "ext": "vob",
        "vcodec": None,
        "height": None,
        "extractor_key": "Generic",
        "direct": True,
        "format_id": "mpeg",
        # The terminal request entry can omit unchanged parent metadata.
        "requested_downloads": [{
            "filepath": str(video_path),
        }],
    }

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        video_path,
        [(video_path.name, 10)],
    )

    assert result == video_path


@pytest.mark.parametrize(("extension", "format_info"), [
    ("exe", {"ext": "exe", "vcodec": "h264", "height": 720}),
    ("part", {"ext": "part", "vcodec": "h264", "height": 720}),
    ("json", {"ext": "json", "vcodec": "h264", "height": 720}),
    ("vtt", {"ext": "vtt", "vcodec": "h264", "height": 720}),
    ("vob", {"ext": "vob"}),
    ("vob", {"ext": "mp4", "vcodec": "h264", "height": 720}),
    ("vob", {"ext": "vob", "vcodec": "none", "height": 480}),
])
def test_download_rejects_unknown_mime_without_matching_video_evidence(monkeypatch, tmp_path, extension, format_info):
    out_dir = tmp_path / "job"
    candidate = out_dir / f"Original lesson.{extension}"
    info = {
        "title": "Original lesson",
        **format_info,
        "requested_downloads": [{"filepath": str(candidate)}],
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            candidate,
            [(candidate.name, 10)],
        )


def test_download_rejects_missing_top_level_terminal_path_without_using_other_files(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    missing_video = out_dir / "Original lesson.mp4"
    info = {
        "title": "Original lesson",
        "filepath": str(missing_video),
        "ext": "mp4",
        "vcodec": "h264",
        "height": 720,
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            missing_video,
            [("unrelated.mp4", 20)],
        )


def test_download_does_not_use_unknown_video_metadata_for_prepare_filename_fallback(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    prepared = out_dir / "Original lesson.vob"
    info = {"title": "Original lesson", "ext": "vob", "vcodec": "mpeg2video"}

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            prepared,
            [(prepared.name, 10)],
        )


def test_download_uses_effective_requested_codec_over_parent_metadata(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    video_path = out_dir / "Original lesson.vob"
    info = {
        "title": "Original lesson",
        "ext": "vob",
        "vcodec": "none",
        "requested_downloads": [{"filepath": str(video_path), "vcodec": "mpeg2video"}],
    }

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        video_path,
        [(video_path.name, 10)],
    )

    assert result == video_path


def test_download_rejects_effective_requested_none_codec_over_parent_video_metadata(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    video_path = out_dir / "Original lesson.vob"
    info = {
        "title": "Original lesson",
        "ext": "vob",
        "vcodec": "mpeg2video",
        "height": 480,
        "requested_downloads": [{"filepath": str(video_path), "vcodec": "none"}],
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            video_path,
            [(video_path.name, 10)],
        )


def test_download_does_not_treat_infinite_height_as_video_evidence(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    candidate = out_dir / "Original lesson.vob"
    info = {
        "title": "Original lesson",
        "ext": "vob",
        "height": float("inf"),
        "requested_downloads": [{"filepath": str(candidate)}],
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            candidate,
            [(candidate.name, 10)],
        )


@pytest.mark.parametrize("extension", ["tmp", "temp", "ytdl", "lrc"])
def test_download_rejects_mime_unknown_temp_and_subtitle_extensions_with_video_metadata(monkeypatch, tmp_path, extension):
    out_dir = tmp_path / "job"
    candidate = out_dir / f"Original lesson.{extension}"
    info = {
        "title": "Original lesson",
        "ext": extension,
        "vcodec": "h264",
        "height": 720,
        "requested_downloads": [{"filepath": str(candidate)}],
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            candidate,
            [(candidate.name, 10)],
        )


@pytest.mark.parametrize("terminal", ["part", "missing", "outside", "json", "subtitle"])
def test_download_rejects_invalid_explicit_terminal_filepath(monkeypatch, tmp_path, terminal):
    out_dir = tmp_path / "job"
    if terminal == "part":
        terminal_path = out_dir / "Original lesson.mp4.part"
    elif terminal == "missing":
        terminal_path = out_dir / "Missing final.mp4"
    elif terminal == "outside":
        terminal_path = tmp_path / "outside.mp4"
        terminal_path.write_bytes(b"outside output directory")
    elif terminal == "json":
        terminal_path = out_dir / "Original lesson.info.json"
    else:
        terminal_path = out_dir / "Original lesson.en.vtt"

    info = {"title": "Original lesson", "ext": "mp4", "requested_downloads": [{"filepath": str(terminal_path)}]}
    artifacts = [("Original lesson.mp4", 10), ("课后总结.mp4", 30)]
    if terminal == "part":
        artifacts.append((terminal_path.name, 20))
    elif terminal == "json":
        artifacts.append((terminal_path.name, 20))
    elif terminal == "subtitle":
        artifacts.append((terminal_path.name, 20))

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            out_dir / "Original lesson.mp4",
            artifacts,
        )


def test_download_rejects_ambiguous_requested_download_paths(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    info = {
        "requested_downloads": [
            {"filepath": str(out_dir / "part-one.mp4")},
            {"filepath": str(out_dir / "part-two.mp4")},
        ],
    }

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            out_dir / "fallback.mp4",
            [("part-one.mp4", 10), ("part-two.mp4", 20), ("课后总结.mp4", 30)],
        )


def test_download_uses_prepare_filename_when_final_path_metadata_is_absent(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    prepared = out_dir / "Original lesson.mp4"
    info = {"title": "Original lesson", "ext": "mp4"}

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        prepared,
        [("Original lesson.mp4", 10), ("课后总结.mp4", 20)],
    )

    assert result == prepared


def test_download_uses_known_merge_extension_for_legacy_filename_fallback(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    merged_video = out_dir / "Original lesson.mp4"
    info = {
        "title": "Original lesson",
        "ext": "webm",
        "requested_formats": [{"format_id": "video"}, {"format_id": "audio"}],
    }

    result, _ = _download_with_artifacts(
        monkeypatch,
        tmp_path,
        info,
        out_dir / "Original lesson.webm",
        [("Original lesson.mp4", 10), ("Original lesson.webm", 20)],
    )

    assert result == merged_video


def test_download_fails_when_no_explicit_or_compatible_candidate_exists(monkeypatch, tmp_path):
    out_dir = tmp_path / "job"
    info = {"title": "Original lesson", "ext": "mp4"}

    with pytest.raises(FileNotFoundError):
        _download_with_artifacts(
            monkeypatch,
            tmp_path,
            info,
            out_dir / "Original lesson.mp4",
            [("课后总结.mp4", 30)],
        )


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
