from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.main import app
from app.models import Job, User
from app.services import jobs as jobs_module

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit(monkeypatch):
    monkeypatch.setattr("app.main._window", defaultdict(list))


@pytest.fixture(autouse=True)
def _noop_download(monkeypatch):
    # 隔离真实下载：不碰 yt-dlp，不触发线程池实际下载
    from app.services import ytdlp_service

    monkeypatch.setattr(jobs_module, "_run_download", lambda job_id, url, fid: None)
    monkeypatch.setattr(ytdlp_service, "get_direct_url", lambda url, fid: (None, {}))


def _register(email, password="password123"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["token"]


def _download(headers):
    return client.post(
        "/api/download",
        json={"url": "https://example.com/v", "format_id": "18", "force_server": True},
        headers=headers,
    )


def test_quota_exhausted_returns_429(monkeypatch):
    monkeypatch.setattr(settings, "default_quota_limit", 2)
    token = _register("quota@example.com")
    h = {"Authorization": f"Bearer {token}"}

    assert _download(h).status_code == 200
    assert _download(h).status_code == 200
    r = _download(h)
    assert r.status_code == 429
    assert r.json()["detail"]["error_type"] == "quota"


def test_quota_me_reflects_usage(monkeypatch):
    monkeypatch.setattr(settings, "default_quota_limit", 3)
    token = _register("usage@example.com")
    h = {"Authorization": f"Bearer {token}"}
    assert _download(h).status_code == 200

    me = client.get("/api/auth/me", headers=h)
    quota = me.json()["quota"]
    assert quota["used"] == 1
    assert quota["limit"] == 3
    assert quota["remaining"] == 2


def test_unauthenticated_download_requires_login():
    r = _download({})
    assert r.status_code == 401
    assert r.json()["detail"]["error_type"] == "login_required"


def test_job_user_id_written_for_logged_in():
    token = _register("owner@example.com")
    h = {"Authorization": f"Bearer {token}"}
    job_id = _download(h).json()["job_id"]

    with Session(engine) as s:
        job = s.get(Job, job_id)
        assert job is not None
        assert job.user_id is not None
        assert s.get(User, job.user_id) is not None


def test_download_with_bad_token_requires_login():
    r = _download({"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["detail"]["error_type"] == "login_required"
