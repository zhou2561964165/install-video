# backend/tests/test_parse_route.py
from collections import defaultdict
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app  # Task 1 已建最小 app，此处挂载 router

from app.services import ytdlp_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit(monkeypatch):
    monkeypatch.setattr("app.main._window", defaultdict(list))


def _auth_headers():
    r = client.post(
        "/api/auth/register",
        json={"email": f"parse-{uuid4()}@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_parse_ok(monkeypatch):
    def fake_extract(url):
        return {
            "title": "测试标题",
            "thumbnail": "https://i.example/t.jpg",
            "duration": 125.0,
            "uploader": "某人",
            "extractor": "youtube",
            "view_count": 12345,
            "upload_date": "20240101",
            "description": "desc",
            "subtitles": {"zh-Hans": [{}], "en": [{}]},
            "formats": [
                {"format_id": "18", "height": 360, "width": 640, "vcodec": "avc1",
                 "acodec": "mp4a", "url": "https://cdn/18.mp4", "ext": "mp4", "filesize": 1000},
            ],
        }

    monkeypatch.setattr(ytdlp_service, "extract_info", fake_extract)
    r = client.post("/api/parse", json={"url": "https://example.com/v"}, headers=_auth_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "测试标题"
    assert data["duration_string"] == "2:05"
    assert data["uploader"] == "某人"
    assert data["platform"] == "youtube"
    assert data["view_count"] == 12345
    assert data["upload_date"] == "20240101"
    assert data["subtitles"] == ["zh-Hans", "en"]
    assert data["formats"][0]["label"] == "360p MP4 (1KB)"
    assert data["formats"][0]["resolution"] == "640x360"
    assert data["formats"][0]["has_audio"] is True
    assert data["formats"][0]["direct"] is True


def test_parse_invalid_url():
    r = client.post("/api/parse", json={"url": "not a url"}, headers=_auth_headers())
    assert r.status_code == 400
    assert r.json()["detail"]["error_type"] == "invalid_url"


def test_parse_unsupported(monkeypatch):
    def fake_extract(url):
        from yt_dlp.utils import UnsupportedError

        raise UnsupportedError("unsupported")

    monkeypatch.setattr(ytdlp_service, "extract_info", fake_extract)
    r = client.post("/api/parse", json={"url": "https://example.com/v"}, headers=_auth_headers())
    assert r.status_code == 422
    assert r.json()["detail"]["error_type"] == "unsupported_site"


def test_parse_requires_login():
    r = client.post("/api/parse", json={"url": "https://example.com/v"})
    assert r.status_code == 401
    assert r.json()["detail"]["error_type"] == "login_required"
