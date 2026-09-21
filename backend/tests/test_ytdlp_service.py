import yt_dlp.utils

from app.config import settings
from app.services.ytdlp_service import (
    classify_error,
    download,
    extract_info,
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
