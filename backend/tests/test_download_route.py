from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import engine, init_db
from app.main import app
from app.models import Job, JobStatus
from app.services import ytdlp_service

client = TestClient(app)


def test_download_server_mode_creates_job(monkeypatch):
    init_db()
    monkeypatch.setattr(
        ytdlp_service,
        "get_direct_url",
        lambda url, fid: (None, {}),  # 直链不可用 → server
    )
    from app.services import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_run_download", lambda job_id, url, fid: None)
    r = client.post(
        "/api/download",
        json={"url": "https://example.com/v", "format_id": "bestvideo[height<=1080]+bestaudio"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "server"
    assert data["job_id"]

    with Session(engine) as s:
        job = s.get(Job, data["job_id"])
        assert job is not None
        assert job.status == JobStatus.queued


def test_download_direct_mode_returns_url(monkeypatch):
    monkeypatch.setattr(
        ytdlp_service,
        "get_direct_url",
        lambda url, fid: ("https://cdn/18.mp4", {"User-Agent": "test"}),
    )
    r = client.post(
        "/api/download",
        json={"url": "https://example.com/v", "format_id": "18"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "direct"
    assert data["url"] == "https://cdn/18.mp4"
    assert data["headers"]["User-Agent"] == "test"


def test_download_falls_back_to_server_when_direct_fails(monkeypatch):
    from app.services import jobs as jobs_module

    def _boom(url, fid):
        raise RuntimeError("extraction failed")

    monkeypatch.setattr(ytdlp_service, "get_direct_url", _boom)
    monkeypatch.setattr(jobs_module, "_run_download", lambda job_id, url, fid: None)
    r = client.post(
        "/api/download",
        json={"url": "https://example.com/v", "format_id": "18"},
    )
    assert r.status_code == 200
    assert r.json()["mode"] == "server"


def test_get_job_returns_status():
    init_db()
    with Session(engine) as s:
        job = Job(url="https://example.com/v", title="t", status=JobStatus.done, progress=100.0)
        s.add(job)
        s.commit()
        job_id = job.id
    r = client.get(f"/api/job/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_get_file_streams_content(monkeypatch, tmp_path):
    init_db()
    f = tmp_path / "v.mp4"
    f.write_bytes(b"VIDEO_BYTES")
    with Session(engine) as s:
        job = Job(url="https://example.com/v", status=JobStatus.done, file_path=str(f))
        s.add(job)
        s.commit()
        job_id = job.id
    r = client.get(f"/api/file/{job_id}")
    assert r.status_code == 200
    assert r.content == b"VIDEO_BYTES"
