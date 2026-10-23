"""Offline session consumers: temporary databases and synthetic CookieJar only."""
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy

import httpx
import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.models import Job, Quota, User
from app.routes import download as download_route, parse as parse_route
from app.schemas import DownloadRequest, ParseRequest
from app.services import bilibili_subtitle_source, jobs, quota, subtitle_service, ytdlp_service
from app.services.bilibili_session import SessionError


VIDEO = "https://www.bilibili.com/video/BV12N4y1M7rh?p=2"
CAPTION = "https://i0.hdslb.com/bfs/subtitle/manual.json"
VTT = b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nSynthetic caption"


def synthetic_jar():
    jar = CookieJar()
    for name, path, secure in [("synthetic_session", "/", True), ("wrong_path", "/private", True)]:
        jar.set_cookie(Cookie(0, name, "synthetic-only", None, False, ".bilibili.com", True, True,
                              path, True, secure, None, True, None, None, {}, False))
    return jar


@pytest.fixture
def download_db(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'consumers.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    user = User(id="synthetic-user", email="synthetic@example.invalid", password_hash="unused")
    with Session(engine, expire_on_commit=False) as db:
        db.add(user)
        db.commit()
    monkeypatch.setattr(settings, "membership_unlimited_downloads", False)
    monkeypatch.setattr(settings, "default_quota_limit", 2)
    monkeypatch.setattr(quota, "is_unlimited_user", lambda uid: False)
    monkeypatch.setattr(download_route, "max_height", lambda *_: None)
    monkeypatch.setattr(jobs.job_manager, "cleanup_expired", lambda: 0)
    submitted = []
    monkeypatch.setattr(jobs.job_manager, "submit_download", lambda job, *_: submitted.append(job.id))
    monkeypatch.setattr(ytdlp_service, "requires_server_download", lambda url: "bilibili.com" in url)
    yield engine, user, submitted
    engine.dispose()


def test_session_download_is_server_and_replays_once(download_db, monkeypatch):
    engine, user, submitted = download_db
    monkeypatch.setattr(ytdlp_service, "get_direct_url", lambda *_: pytest.fail("Session download must not probe direct URLs"))
    request = DownloadRequest(url=VIDEO, format_id="18", force_server=False)
    with Session(engine) as db:
        first = download_route.download(request, db, user, "synthetic-request")
        second = download_route.download(request, db, user, "synthetic-request")
        assert first == second
        assert first.mode == "server"
        assert submitted == [first.job_id]
        assert db.exec(select(Quota)).one().downloads_used == 1
        assert len(db.exec(select(Job)).all()) == 1


@pytest.mark.parametrize("url", ["https://example.invalid/v", VIDEO])
def test_unconfigured_bilibili_or_other_platform_keeps_direct_download(download_db, monkeypatch, url):
    engine, user, submitted = download_db
    monkeypatch.setattr(ytdlp_service, "requires_server_download", lambda _: False)
    monkeypatch.setattr(ytdlp_service, "get_direct_url", lambda *_: ("https://cdn.example.invalid/v.mp4", {"User-Agent": "synthetic"}))
    with Session(engine) as db:
        response = download_route.download(DownloadRequest(url=url, format_id="18"), db, user, None)
        assert response.mode == "direct"
        assert response.headers == {"User-Agent": "synthetic"}
        assert db.exec(select(Quota)).one().downloads_used == 1
        assert submitted == []


def test_session_download_retains_quota_rejection(download_db, monkeypatch):
    engine, user, submitted = download_db
    monkeypatch.setattr(settings, "default_quota_limit", 0)
    with Session(engine) as db, pytest.raises(HTTPException) as error:
        download_route.download(DownloadRequest(url=VIDEO, format_id="18"), db, user, None)
    assert error.value.status_code == 429
    assert submitted == []


def test_session_download_retains_member_height_gate(download_db, monkeypatch):
    engine, user, submitted = download_db
    monkeypatch.setattr(download_route, "max_height", lambda *_: 720)
    monkeypatch.setattr(ytdlp_service, "restrict_format", lambda *_: (_ for _ in ()).throw(ValueError("1080p not entitled")))
    with Session(engine) as db, pytest.raises(HTTPException) as error:
        download_route.download(DownloadRequest(url=VIDEO, format_id="80"), db, user, None)
    assert error.value.status_code == 403
    assert submitted == []
    with Session(engine) as db:
        assert db.exec(select(Quota)).first() is None


def test_session_expired_during_free_format_check_stops_before_quota_or_queue(download_db, monkeypatch):
    engine, user, submitted = download_db
    monkeypatch.setattr(download_route, "max_height", lambda *_: 720)
    monkeypatch.setattr(ytdlp_service, "restrict_format", lambda *_: (_ for _ in ()).throw(
        SessionError("B站访问凭据已过期，请管理员更新Cookie文件后重试。")))
    monkeypatch.setattr(download_route, "check_and_reserve", lambda *_: pytest.fail("Expired session must not reserve quota"))
    with Session(engine) as db, pytest.raises(HTTPException) as error:
        download_route.download(DownloadRequest(url=VIDEO, format_id="18"), db, user, None)
    assert error.value.status_code == 422
    assert error.value.detail["error_type"] == "verification_required"
    assert "已过期" in error.value.detail["error"]
    assert "重新解析" not in error.value.detail["error"]
    assert submitted == []
    with Session(engine) as db:
        assert db.exec(select(Quota)).first() is None
        assert db.exec(select(Job)).first() is None


def test_parse_uses_public_error_formatter(monkeypatch):
    secret_error = RuntimeError("synthetic-cookie-value /synthetic/private/path")
    monkeypatch.setattr(parse_route, "parse_video", lambda *_: (_ for _ in ()).throw(secret_error))
    monkeypatch.setattr(parse_route, "public_error_message", lambda exc: "安全提示" if exc is secret_error else pytest.fail("Wrong exception"))
    with pytest.raises(HTTPException) as error:
        parse_route.parse(ParseRequest(url=VIDEO), _user=None)
    assert error.value.detail["error"] == "安全提示"


def test_job_persists_public_error_formatter(download_db, monkeypatch):
    engine, _, _ = download_db
    monkeypatch.setattr(jobs, "engine", engine)
    monkeypatch.setattr(jobs, "public_error_message", lambda _: "安全任务提示")
    with Session(engine) as db:
        job = Job(url=VIDEO, format_id="18")
        db.add(job)
        db.commit()
        job_id = job.id
    manager = jobs.JobManager(max_workers=1)
    try:
        manager._mark_error(job_id, RuntimeError("synthetic-cookie-value"))
    finally:
        manager._executor.shutdown(wait=True)
    with Session(engine) as db:
        assert db.get(Job, job_id).error == "安全任务提示"


def install_native_transport(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def test_native_metadata_uses_scoped_jar_and_never_returns_cookie_headers(monkeypatch):
    requests = []
    monkeypatch.setattr(bilibili_subtitle_source, "cookie_jar_for_url", lambda _: synthetic_jar())

    def handler(request):
        requests.append(request)
        if request.url.path == "/x/web-interface/view":
            return httpx.Response(200, json={"code": 0, "data": {"bvid": "BV12N4y1M7rh", "aid": 1, "title": "Synthetic", "pages": [{"page": 2, "cid": 2}]}})
        return httpx.Response(200, json={"code": 0, "data": {"subtitle": {"subtitles": [{"lan": "en", "type": 0, "subtitle_url": CAPTION}]}}})

    install_native_transport(monkeypatch, handler)
    payload = bilibili_subtitle_source.bilibili_tracks(VIDEO)
    assert len(requests) == 2
    for request in requests:
        assert request.url.host == "api.bilibili.com"
        assert request.headers["cookie"] == "synthetic_session=synthetic-only"
        assert request.headers["referer"] == VIDEO.split("?", 1)[0]
    headers = payload["tracks"][0]["formats"][0]["http_headers"]
    assert all(key.casefold() not in {"cookie", "authorization"} for key in headers)


def test_native_metadata_redirect_never_reaches_foreign_host(monkeypatch):
    requests = []
    monkeypatch.setattr(bilibili_subtitle_source, "cookie_jar_for_url", lambda _: synthetic_jar())
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://foreign.invalid/metadata"})
    install_native_transport(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        bilibili_subtitle_source.bilibili_tracks(VIDEO)
    assert len(requests) == 1
    assert requests[0].url.host == "api.bilibili.com"


def track_payload(url=CAPTION, ext="vtt", *, public=False):
    return {"title": "Synthetic", **({"_source": "public"} if public else {}), "tracks": [{
        "language": "en", "is_auto": False, "formats": [{"url": url, "ext": ext, "http_headers": {
            "cOoKiE": "synthetic-leak", "Authorization": "Bearer synthetic-leak", "Proxy-Authorization": "synthetic-leak",
            "User-Agent": "synthetic-agent",
        }}],
    }]}


@pytest.mark.parametrize("caption_url, expected_cookie", [
    (CAPTION, None),
    ("https://api.bilibili.com/caption.vtt", "synthetic_session=synthetic-only"),
    ("http://api.bilibili.com/caption.vtt", None),
    ("https://bilibili.com.evil.invalid/caption.vtt", None),
])
def test_body_uses_cookie_domain_path_and_secure_rules(monkeypatch, caption_url, expected_cookie):
    requests = []
    monkeypatch.setattr(subtitle_service.ytdlp_service, "extract_subtitle_tracks", lambda _: track_payload(caption_url))
    monkeypatch.setattr(subtitle_service, "cookie_jar_for_url", lambda _: synthetic_jar())
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=VTT)
    install_native_transport(monkeypatch, handler)
    assert subtitle_service.fetch_subtitle_document(VIDEO).text == "Synthetic caption"
    assert len(requests) == 1
    assert requests[0].headers.get("cookie") == expected_cookie
    assert "authorization" not in requests[0].headers
    assert "proxy-authorization" not in requests[0].headers
    assert requests[0].headers["referer"].startswith("https://www.bilibili.com/video/")


def test_bilibili_caption_redirect_is_not_followed(monkeypatch):
    requests = []
    monkeypatch.setattr(subtitle_service.ytdlp_service, "extract_subtitle_tracks", lambda _: track_payload("https://api.bilibili.com/caption.vtt"))
    monkeypatch.setattr(subtitle_service, "cookie_jar_for_url", lambda _: synthetic_jar())
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://foreign.invalid/caption.vtt"})
    install_native_transport(monkeypatch, handler)
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.fetch_subtitle_document(VIDEO)
    assert error.value.error_type == "subtitle_fetch_failed"
    assert len(requests) == 1


def test_non_bilibili_preserves_initial_track_credentials_and_redirect_behavior(monkeypatch):
    requests = []
    monkeypatch.setattr(subtitle_service.ytdlp_service, "extract_subtitle_tracks", lambda _: track_payload("https://original.invalid/caption.vtt"))
    monkeypatch.setattr(subtitle_service, "cookie_jar_for_url", lambda _: CookieJar())
    def handler(request):
        requests.append(request)
        if request.url.host == "original.invalid":
            return httpx.Response(302, headers={"Location": "https://foreign.invalid/caption.vtt"})
        return httpx.Response(200, content=VTT)
    install_native_transport(monkeypatch, handler)
    assert subtitle_service.fetch_subtitle_document("https://example.invalid/video").text == "Synthetic caption"
    assert len(requests) == 2
    assert requests[0].headers["cookie"] == "synthetic-leak"
    assert requests[0].headers["authorization"] == "Bearer synthetic-leak"
    # HTTPX retains its original redirect handling for these existing sources.
    assert "cookie" not in requests[1].headers
    assert "authorization" not in requests[1].headers


@pytest.mark.parametrize("injected", [False, True])
@pytest.mark.parametrize("caption_url, expected_cookie", [
    ("https://api.bilibili.com/private/caption.vtt", "host_only=synthetic-only"),
    ("https://child.api.bilibili.com/private/caption.vtt", None),
    ("https://api.bilibili.com/other/caption.vtt", None),
    ("http://api.bilibili.com/private/caption.vtt", None),
])
def test_all_clients_preserve_original_cookie_policy(monkeypatch, injected, caption_url, expected_cookie):
    jar = CookieJar(policy=DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
    jar.set_cookie(Cookie(0, "host_only", "synthetic-only", None, False, "api.bilibili.com", False, False,
                          "/private", True, True, None, True, None, None, {}, False))
    requests = []
    monkeypatch.setattr(ytdlp_service, "extract_subtitle_tracks", lambda _: track_payload(caption_url))
    monkeypatch.setattr(subtitle_service, "cookie_jar_for_url", lambda _: jar)
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=VTT)
    if injected:
        with httpx.Client(transport=httpx.MockTransport(handler), headers={
            "Cookie": "client-level-secret", "Authorization": "Bearer client-level-secret"
        }) as client:
            assert subtitle_service.fetch_subtitle_document(VIDEO, client=client).text == "Synthetic caption"
            assert not list(client.cookies.jar)
    else:
        install_native_transport(monkeypatch, handler)
        assert subtitle_service.fetch_subtitle_document(VIDEO).text == "Synthetic caption"
    assert requests[0].headers.get("cookie") == expected_cookie
    assert "authorization" not in requests[0].headers


def test_native_owned_client_does_not_expand_host_only_cookie_to_api(monkeypatch):
    jar = CookieJar(policy=DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
    jar.set_cookie(Cookie(0, "host_only", "synthetic-only", None, False, "bilibili.com", False, False,
                          "/", True, True, None, True, None, None, {}, False))
    monkeypatch.setattr(bilibili_subtitle_source, "cookie_jar_for_url", lambda _: jar)
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == "/x/web-interface/view":
            return httpx.Response(200, json={"code": 0, "data": {"bvid": "BV12N4y1M7rh", "aid": 1, "title": "Synthetic", "pages": [{"page": 2, "cid": 2}]}})
        return httpx.Response(200, json={"code": 0, "data": {"subtitle": {"subtitles": []}}})
    install_native_transport(monkeypatch, handler)
    bilibili_subtitle_source.bilibili_tracks(VIDEO)
    assert len(requests) == 2
    assert all("cookie" not in request.headers for request in requests)


def test_missing_or_expired_native_session_is_not_generic_fallback(monkeypatch):
    def fail(_):
        raise SessionError("B站会话已过期，请更新服务端会话文件")
    monkeypatch.setattr(bilibili_subtitle_source, "cookie_jar_for_url", fail)
    monkeypatch.setattr(ytdlp_service, "extract_info", lambda _: pytest.fail("Session failure must not retry generic extraction"))
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.fetch_subtitle_document(VIDEO)
    assert error.value.error_type == "verification_required"
    assert "会话" in str(error.value)


def test_session_expiry_during_native_body_fallback_remains_verification(monkeypatch):
    calls = []
    def extract(url, **kwargs):
        calls.append(kwargs)
        if kwargs:
            raise SessionError("B站会话已过期，请更新服务端会话文件")
        return track_payload(public=True)
    monkeypatch.setattr(ytdlp_service, "extract_subtitle_tracks", extract)
    monkeypatch.setattr(subtitle_service, "cookie_jar_for_url", lambda _: CookieJar())
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(403))) as client:
        with pytest.raises(subtitle_service.SubtitleServiceError) as error:
            subtitle_service.fetch_subtitle_document(VIDEO, client=client)
    assert error.value.error_type == "verification_required"
    assert calls == [{}, {"use_public_sources": False}]


def test_session_expiry_before_native_body_never_retries_extraction(monkeypatch):
    calls = []
    def extract(url, **kwargs):
        calls.append(kwargs)
        assert not kwargs
        return track_payload(public=True)
    def expired(_):
        raise SessionError("B站会话已过期，请更新服务端会话文件")
    monkeypatch.setattr(ytdlp_service, "extract_subtitle_tracks", extract)
    monkeypatch.setattr(subtitle_service, "cookie_jar_for_url", expired)
    with pytest.raises(subtitle_service.SubtitleServiceError) as error:
        subtitle_service.fetch_subtitle_document(VIDEO)
    assert error.value.error_type == "verification_required"
    assert calls == [{}]
