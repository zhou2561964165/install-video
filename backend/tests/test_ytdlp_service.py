import yt_dlp.utils

from app.services.ytdlp_service import (
    classify_error,
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
