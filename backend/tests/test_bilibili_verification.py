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
        "page_error": None,
        "embedded_play_info": None,
    }
    video = {
        "bvid": "BV13vpG67ELM", "aid": 1, "cid": 2, "title": "视频实际标题",
        "duration": 30, "pages": [{"page": 1, "cid": 2, "part": "视频实际标题"}],
        "rights": {}, "stat": {},
    }
    webpage = '<script>window.__INITIAL_STATE__=' + json.dumps({"videoData": video}) + ';</script>'

    def page(self, url, *args, **kwargs):
        if state["page_error"]:
            from yt_dlp.utils import ExtractorError
            raise ExtractorError(state["page_error"], expected=True)
        embedded = state["embedded_play_info"]
        markup = webpage
        if embedded is not None:
            markup += '<script>window.__playinfo__=' + json.dumps({"data": embedded}) + ';</script>'
        return markup, SimpleNamespace(url=url)

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
    assert "[BiliBili]" not in failure.value.detail["error"]
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


@pytest.mark.parametrize("message", [
    "Unable to download webpage: HTTP Error 412: Precondition Failed",
    "You have exceeded the rate limit. Try again later",
])
def test_bilibili_page_verification_is_sanitized_and_does_not_probe_metadata(playback, message):
    playback["page_error"] = message
    with pytest.raises(DownloadError) as failure:
        service.extract_info(URL)
    assert service.classify_error(failure.value) == "verification_required"
    assert "安全校验" in str(failure.value)
    assert playback["paths"] == []


def test_parse_api_returns_safe_message_for_actual_bilibili_412_failure(playback):
    from app.routes.parse import parse
    from app.schemas import ParseRequest

    playback["page_error"] = "Unable to download webpage: HTTP Error 412: Precondition Failed"
    with pytest.raises(HTTPException) as failure:
        parse(ParseRequest(url=URL), _user=None)
    assert failure.value.status_code == 422
    assert failure.value.detail == {
        "error_type": "verification_required", "error": service.VERIFICATION_ERROR_MESSAGE,
    }
    assert playback["paths"] == []


def test_bilibili_ordinary_page_timeout_keeps_network_error(playback):
    playback["page_error"] = "Unable to download webpage: Connection timed out"
    with pytest.raises(DownloadError) as failure:
        service.extract_info(URL)
    assert service.classify_error(failure.value) == "network"
    assert "Connection timed out" in str(failure.value)


@pytest.mark.parametrize("code", [-401, -352])
def test_primary_bilibili_business_verification_stops_before_format_probes(playback, code):
    playback["code"] = code
    with pytest.raises(DownloadError) as failure:
        service.extract_info(URL)
    assert service.classify_error(failure.value) == "verification_required"
    assert "安全校验" in str(failure.value)
    assert playback["paths"].count("/x/player/wbi/playurl") == 1


@pytest.mark.parametrize("code", [-401, -352, 0])
@pytest.mark.parametrize("kind", ["dash", "progressive"])
def test_primary_api_verification_preserves_available_webpage_formats(playback, code, kind):
    playback["code"] = code
    if kind == "dash":
        playback["embedded_play_info"] = {
            "quality": 80,
            "dash": {"video": [{"id": 80, "baseUrl": "https://media.invalid/embedded.mp4",
                                "mimeType": "video/mp4", "codecs": "avc1.640028",
                                "width": 1920, "height": 1080, "frameRate": "25"}]},
        }
    else:
        playback["embedded_play_info"] = {
            "quality": 32, "timelength": 30000,
            "durl": [{"url": "https://media.invalid/embedded.mp4", "length": 30000, "size": 1000}],
        }
    info = service.extract_info(URL)
    assert info["title"] == "视频实际标题"
    assert {item["url"] for item in info["formats"]} == {"https://media.invalid/embedded.mp4"}
    assert playback["paths"].count("/x/player/wbi/playurl") == 1


def test_pending_api_verification_does_not_mask_subsequent_network_failure(playback, monkeypatch):
    from yt_dlp.utils import ExtractorError

    playback["code"] = -401
    original = BiliBiliIE.extract_formats

    def unavailable_formats(self, info):
        if getattr(self, "_primary_verification_pending", False):
            raise ExtractorError("Connection timed out")
        return original(self, info)

    monkeypatch.setattr(BiliBiliIE, "extract_formats", unavailable_formats)
    with pytest.raises(DownloadError) as failure:
        service.extract_info(URL)
    assert service.classify_error(failure.value) == "network"
    assert "Connection timed out" in str(failure.value)


def test_reused_extractor_does_not_apply_previous_verification_to_next_video(playback):
    playback["code"] = -401
    with service._youtube_dl({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        with pytest.raises(DownloadError) as first:
            ydl.extract_info(URL, download=False)
        assert service.classify_error(first.value) == "verification_required"
        playback["code"] = 0
        playback["data"] = {}
        with pytest.raises(DownloadError) as second:
            ydl.extract_info(URL, download=False)
        assert service.classify_error(second.value) == "network"
        assert "No video formats found" in str(second.value)


@pytest.mark.parametrize("message, expected", [
    ("[BiliBili] 16MJY6yEKq: Unable to download webpage: HTTP Error 412: Precondition Failed", "verification_required"),
    ("[BiliBili] id: Unable to download video info: 401: error", "verification_required"),
    ("[BiliBili] id: Unable to download video info: 352: error", "verification_required"),
    ("[BiliBili] id: You have exceeded the rate limit. Try again later", "verification_required"),
    ("[youtube] id: HTTP Error 412: Precondition Failed", "network"),
    ("[BiliBili] id: Connection timed out", "network"),
    ("[BiliBili] id: Unable to download video info: 10403: error", "network"),
])
def test_only_explicit_bilibili_verification_signals_change_classification(message, expected):
    assert service.classify_error(DownloadError(message)) == expected


@pytest.mark.parametrize("nested", [False, True])
def test_verification_survives_download_error_wrappers_that_lose_original_subclass(nested):
    from yt_dlp.utils import ExtractorError

    # Replay the deployed wrapper: its human-readable message survives, but exc_info
    # no longer points directly to the private verification exception subclass.
    inner = ExtractorError(service.VERIFICATION_ERROR_MESSAGE, expected=True)
    error = DownloadError(
        f"ERROR: [BiliBili] 16MJY6yEKq: {service.VERIFICATION_ERROR_MESSAGE}",
        exc_info=(ExtractorError, inner, None),
    )
    if nested:
        error = DownloadError(str(error), exc_info=(DownloadError, error, None))
    assert service.classify_error(error) == "verification_required"


@pytest.mark.parametrize("message", [
    "ERROR: [youtube] id: " + service.VERIFICATION_ERROR_MESSAGE,
    service.VERIFICATION_ERROR_MESSAGE,
    "ERROR: [BiliBili] id: B站触发了安全校验",
    "ERROR: [BiliBili] id: Connection timed out",
])
def test_local_verification_message_match_requires_complete_message_and_bilibili_context(message):
    assert service.classify_error(DownloadError(message)) == "network"


def test_parse_sanitizes_verification_after_nested_wrappers_lose_exception_subclass(monkeypatch):
    import importlib
    from app.schemas import ParseRequest
    from yt_dlp.utils import ExtractorError

    route = importlib.import_module("app.routes.parse")
    inner = DownloadError(
        f"ERROR: [BiliBili] 16MJY6yEKq: {service.VERIFICATION_ERROR_MESSAGE}",
        exc_info=(ExtractorError, ExtractorError(service.VERIFICATION_ERROR_MESSAGE), None),
    )
    wrapped = DownloadError(str(inner), exc_info=(DownloadError, inner, None))

    def failed_parse(url):
        raise wrapped

    monkeypatch.setattr(route, "parse_video", failed_parse)
    with pytest.raises(HTTPException) as failure:
        route.parse(ParseRequest(url=URL), _user=None)
    assert failure.value.detail == {
        "error_type": "verification_required", "error": service.VERIFICATION_ERROR_MESSAGE,
    }


def test_parse_uses_configurable_io_timeout_without_changing_download_retry_policy(monkeypatch):
    captured = []

    class FakeYDL:
        def __init__(self, options):
            captured.append(options)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def add_info_extractor(self, extractor):
            pass
        def extract_info(self, url, download):
            return {"id": "id", "formats": [{"url": "https://media.invalid/video.mp4"}]}

    monkeypatch.setattr(service.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(service.settings, "parse_socket_timeout_seconds", 12)
    monkeypatch.setattr(service.settings, "parse_extractor_retries", 1)
    monkeypatch.setattr(service.settings, "network_retries", 4)
    service.extract_info(URL)
    service.get_direct_url(URL, "best")
    assert captured[0]["socket_timeout"] == 12
    assert captured[0]["extractor_retries"] == 1
    assert captured[1]["extractor_retries"] == 4
    assert captured[1]["retries"] == 4
    assert "socket_timeout" not in captured[1]


@pytest.mark.parametrize("changes", [
    {"parse_socket_timeout_seconds": 0}, {"parse_socket_timeout_seconds": 61},
    {"parse_socket_timeout_seconds": True}, {"parse_extractor_retries": -1},
    {"parse_extractor_retries": 3}, {"parse_extractor_retries": False},
])
def test_parse_extraction_settings_require_finite_bounded_integers(changes):
    from app.config import Settings
    with pytest.raises(ValueError):
        Settings(**changes)


def test_parse_extraction_settings_load_from_environment(monkeypatch):
    from app.config import Settings
    assert Settings().parse_socket_timeout_seconds == 15
    assert Settings().parse_extractor_retries == 0
    monkeypatch.setenv("PARSE_SOCKET_TIMEOUT_SECONDS", "11")
    monkeypatch.setenv("PARSE_EXTRACTOR_RETRIES", "1")
    configured = Settings.from_env()
    assert configured.parse_socket_timeout_seconds == 11
    assert configured.parse_extractor_retries == 1


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
