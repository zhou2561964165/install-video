"""Replay Bilibili playback responses through real yt-dlp, without network access."""
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException
from yt_dlp.extractor.bilibili import BiliBiliIE
from yt_dlp.utils import DownloadError

from app.services import ytdlp_service as service


URL = "https://www.bilibili.com/video/BV13vpG67ELM/"
VOUCHER = "fixture-voucher-must-never-appear-in-error"


@pytest.fixture
def playback(monkeypatch):
    state = {
        "data": {"v_voucher": VOUCHER},
        "paths": [],
        "code": 0,
        "quality_probe_data": None,
    }
    video = {
        "bvid": "BV13vpG67ELM", "aid": 1, "cid": 2, "title": "视频实际标题",
        "duration": 30, "pages": [{"page": 1, "cid": 2, "part": "视频实际标题"}],
        "rights": {}, "stat": {},
    }
    webpage = '<script>window.__INITIAL_STATE__=' + json.dumps({"videoData": video}) + ';</script>'

    def page(self, url, *args, **kwargs):
        return webpage, SimpleNamespace(url=url)

    def api(self, url, *args, **kwargs):
        path = urlsplit(url).path
        state["paths"].append(path)
        if path.endswith("/pagelist"):
            return {"code": 0, "data": video["pages"]}
        if path.endswith("/playurl"):
            if (kwargs.get("query") or {}).get("qn") and state["quality_probe_data"] is not None:
                return {"code": 0, "message": "OK", "data": state["quality_probe_data"]}
            return {"code": state["code"], "message": "OK", "data": state["data"]}
        if path.endswith("/v2"):
            return {"code": 0, "data": {}}
        raise AssertionError(f"Unexpected metadata request: {path}")

    def no_network(*args, **kwargs):
        raise AssertionError("Offline replay must not open a network connection")

    monkeypatch.setattr(BiliBiliIE, "_download_webpage_handle", page)
    monkeypatch.setattr(BiliBiliIE, "_download_json", api)
    monkeypatch.setattr(BiliBiliIE, "_get_wbi_key", lambda self, video_id: "a" * 32)
    monkeypatch.setattr(service.yt_dlp.YoutubeDL, "urlopen", no_network)
    monkeypatch.setattr(service.settings, "network_retries", 2)
    monkeypatch.setattr(service.settings, "network_retry_backoff_seconds", 0)
    return state


@pytest.mark.parametrize("operation", ["extract_info", "get_direct_url", "download"])
def test_voucher_without_formats_has_specific_error_in_each_video_operation(playback, tmp_path, operation):
    # Removing the adapter registration, or treating code=0 as sufficient, must fail this test.
    with pytest.raises(DownloadError) as failure:
        if operation == "download":
            service.download(URL, "best", str(tmp_path / "%(title)s.%(ext)s"), lambda _: None)
        elif operation == "get_direct_url":
            service.get_direct_url(URL, "best")
        else:
            service.extract_info(URL)
    error = failure.value
    assert service.classify_error(error) == "verification_required"
    assert "安全校验" in str(error)
    assert "No video formats found" not in str(error)
    assert VOUCHER not in str(error)
    assert playback["paths"].count("/x/player/wbi/playurl") == 1
    assert list(tmp_path.iterdir()) == []


def test_parse_returns_specific_platform_verification_error(playback):
    from app.routes.parse import parse
    from app.schemas import ParseRequest

    with pytest.raises(HTTPException) as failure:
        parse(ParseRequest(url=URL), _user=None)
    assert failure.value.status_code == 422
    assert failure.value.detail["error_type"] == "verification_required"
    assert "安全校验" in failure.value.detail["error"]
    assert VOUCHER not in failure.value.detail["error"]


def test_voucher_with_available_dash_formats_remains_parseable(playback):
    playback["data"] = {
        "v_voucher": VOUCHER, "quality": 80,
        "dash": {
            "video": [{"id": 80, "baseUrl": "https://media.invalid/video.mp4", "mimeType": "video/mp4",
                       "codecs": "avc1.640028", "width": 1920, "height": 1080, "frameRate": "25"}],
            "audio": [{"id": 30280, "baseUrl": "https://media.invalid/audio.m4a", "mimeType": "audio/mp4",
                       "codecs": "mp4a.40.2"}],
        },
    }
    info = service.extract_info(URL)
    assert info["title"] == "视频实际标题"
    assert {f["url"] for f in info["formats"]} == {
        "https://media.invalid/video.mp4", "https://media.invalid/audio.m4a",
    }
    assert info["extractor_key"] == "BiliBili"
    assert info["extractor"] == "BiliBili"


def test_voucher_with_available_progressive_format_remains_parseable(playback):
    playback["data"] = {
        "v_voucher": VOUCHER, "quality": 32, "timelength": 30000,
        "durl": [{"url": "https://media.invalid/video.mp4", "length": 30000, "size": 1000}],
    }
    info = service.extract_info(URL)
    assert info["title"] == "视频实际标题"
    assert info["formats"][0]["url"] == "https://media.invalid/video.mp4"


def test_optional_quality_verification_preserves_available_primary_format(playback):
    # Rejecting every voucher also rejects a valid main stream when only a quality probe is blocked.
    playback["data"] = {
        "quality": 32, "timelength": 30000, "accept_quality": [32, 80],
        "durl": [{"url": "https://media.invalid/video.mp4", "length": 30000, "size": 1000}],
    }
    playback["quality_probe_data"] = {"v_voucher": VOUCHER}
    info = service.extract_info(URL)
    assert info["title"] == "视频实际标题"
    assert info["formats"][0]["url"] == "https://media.invalid/video.mp4"
    assert len(info["formats"]) == 1


@pytest.mark.parametrize("data", [{}, {"v_voucher": ""}])
def test_missing_formats_without_verification_evidence_keeps_original_error(playback, data):
    playback["data"] = data
    with pytest.raises(DownloadError) as failure:
        service.extract_info(URL)
    assert "No video formats found" in str(failure.value)
    assert service.classify_error(failure.value) != "verification_required"


def test_nonzero_api_business_error_is_not_misclassified_as_voucher_response(playback):
    playback["code"] = -10403
    with pytest.raises(DownloadError) as failure:
        service.extract_info(URL)
    assert service.classify_error(failure.value) != "verification_required"


def test_failed_download_job_exposes_verification_reason_through_job_response(playback, monkeypatch, tmp_path):
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

    from app.models import Job, JobStatus, User
    from app.routes.download import get_job
    from app.services import jobs

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(jobs, "engine", engine)
    monkeypatch.setattr(jobs.settings, "temp_dir", str(tmp_path))
    user = User(id="offline-user", email="offline@example.invalid", password_hash="unused")
    job = Job(url=URL, user_id=user.id, format_id="best")
    with Session(engine) as session:
        session.add(user)
        session.add(job)
        session.commit()
        job_id = job.id

    manager = jobs.JobManager(max_workers=1)
    try:
        # This exercises the real downloader, error classification and persistence boundary.
        manager._safe_run(job_id, URL, "best")
        with Session(engine) as session:
            response = get_job(job_id, session=session, user=session.get(User, "offline-user"))
        assert response.status == JobStatus.error
        assert response.error_type == "verification_required"
        assert "安全校验" in response.error
        assert VOUCHER not in response.error
        assert list(tmp_path.rglob("*.mp4")) == []
    finally:
        manager._executor.shutdown(wait=True)
        engine.dispose()
