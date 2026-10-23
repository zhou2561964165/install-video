"""Download submission guarantees use temporary SQLite and no external I/O."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
pytestmark = pytest.mark.usefixtures("legacy_daily_quota")
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.db import get_session
from app.models import DownloadIdempotency, Job, Quota, User
from app.routes.download import router
from app.services import download_idempotency, quota, ytdlp_service
from app.schemas import DownloadRequest
from app.services.auth import create_token
from app.services.jobs import job_manager


PAYLOAD = {"url": "https://example.com/video", "format_id": "18", "force_server": True}


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    test_engine = create_engine(
        f"sqlite:///{(tmp_path / 'idempotency.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        session.add_all([
            User(id="alice", email="alice@example.com", password_hash="unused"),
            User(id="bob", email="bob@example.com", password_hash="unused"),
        ])
        session.commit()
    test_app = FastAPI()
    test_app.include_router(router)

    def sessions():
        with Session(test_engine) as session:
            yield session

    test_app.dependency_overrides[get_session] = sessions
    monkeypatch.setattr(settings, "default_quota_limit", 20)
    monkeypatch.setattr(settings, "download_idempotency_ttl_seconds", 86400, raising=False)
    monkeypatch.setattr(settings, "download_idempotency_direct_ttl_seconds", 300, raising=False)
    monkeypatch.setattr(settings, "download_idempotency_max_entries", 10000, raising=False)
    monkeypatch.setattr(quota, "is_unlimited_user", lambda _: False)
    monkeypatch.setattr(job_manager, "cleanup_expired", lambda: 0)
    submitted = []
    monkeypatch.setattr(job_manager, "submit_download", lambda job, *_: submitted.append(job.id))
    monkeypatch.setattr(ytdlp_service, "get_direct_url", lambda *_: ("https://cdn.example/v.mp4", {"Referer": "https://example.com"}))
    with TestClient(test_app, raise_server_exceptions=False) as client:
        yield client, test_engine, submitted
    test_engine.dispose()


def post(client, key="one", *, user="alice", payload=None):
    headers = {"Authorization": f"Bearer {create_token(user)}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post("/api/download", json=payload or PAYLOAD, headers=headers)


def usage(test_engine, user="alice"):
    with Session(test_engine) as session:
        row = session.exec(select(Quota).where(Quota.user_id == user)).first()
        return row.downloads_used if row else 0


def test_server_replay_reuses_job_without_charge_or_submit(sandbox):
    client, test_engine, submitted = sandbox
    first, second = post(client), post(client)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert submitted == [first.json()["job_id"]]
    assert usage(test_engine) == 1
    with Session(test_engine) as session:
        assert len(session.exec(select(Job)).all()) == 1


def test_direct_replay_reuses_response_without_probe(sandbox, monkeypatch):
    client, test_engine, _ = sandbox
    payload = {**PAYLOAD, "force_server": False}
    first = post(client, payload=payload)
    monkeypatch.setattr(ytdlp_service, "get_direct_url", lambda *_: ("https://cdn.example/changed.mp4", {}))
    second = post(client, payload=payload)
    assert second.status_code == first.status_code == 200
    assert second.json() == first.json()
    assert usage(test_engine) == 1


@pytest.mark.parametrize("change", [{"url": "https://example.com/other"}, {"format_id": "22"}, {"force_server": False}])
def test_key_cannot_be_rebound_to_changed_payload(sandbox, change):
    client, test_engine, submitted = sandbox
    assert post(client).status_code == 200
    response = post(client, payload={**PAYLOAD, **change})
    assert response.status_code == 409
    assert usage(test_engine) == len(submitted) == 1


def test_same_key_is_isolated_by_authenticated_user(sandbox):
    client, test_engine, submitted = sandbox
    first, second = post(client), post(client, user="bob")
    assert first.status_code == second.status_code == 200
    assert first.json()["job_id"] != second.json()["job_id"]
    assert usage(test_engine, "alice") == usage(test_engine, "bob") == 1
    assert len(submitted) == 2


@pytest.mark.parametrize("key", ["", "x" * 129, "has space", "has\ttab", "\x7f"])
def test_invalid_key_rejected_before_charge(sandbox, key):
    client, test_engine, submitted = sandbox
    assert post(client, key).status_code == 422
    assert usage(test_engine) == 0
    assert submitted == []


def test_visible_ascii_boundary_keys_are_accepted(sandbox):
    client, _, _ = sandbox
    assert post(client, "!").status_code == 200
    assert post(client, "~" * 128).status_code == 200


def test_no_header_preserves_independent_submissions(sandbox):
    client, test_engine, submitted = sandbox
    first, second = post(client, None), post(client, None)
    assert first.status_code == second.status_code == 200
    assert first.json()["job_id"] != second.json()["job_id"]
    assert usage(test_engine) == len(submitted) == 2


def test_quota_failure_is_replayed_even_if_limit_changes(sandbox, monkeypatch):
    client, test_engine, submitted = sandbox
    monkeypatch.setattr(settings, "default_quota_limit", 0)
    first = post(client)
    monkeypatch.setattr(settings, "default_quota_limit", 20)
    second = post(client)
    assert first.status_code == second.status_code == 429
    assert first.json() == second.json()
    assert usage(test_engine) == 0
    assert submitted == []


def test_submit_exception_is_persisted_and_never_retried(sandbox, monkeypatch):
    client, test_engine, _ = sandbox
    calls = []

    def fail_submit(job, *_):
        calls.append(job.id)
        raise RuntimeError("internal private submit context")

    monkeypatch.setattr(job_manager, "submit_download", fail_submit)
    first, second = post(client), post(client)
    assert first.status_code == second.status_code == 503
    assert first.json() == second.json()
    assert "private" not in first.text
    assert len(calls) == usage(test_engine) == 1


def test_pending_duplicate_conflicts_before_charge(sandbox, monkeypatch):
    client, test_engine, submitted = sandbox
    entered, release = Event(), Event()

    def blocked_probe(*_):
        entered.set()
        assert release.wait(5)
        return "https://cdn.example/v.mp4", {}

    monkeypatch.setattr(ytdlp_service, "get_direct_url", blocked_probe)
    payload = {**PAYLOAD, "force_server": False}
    with ThreadPoolExecutor(max_workers=1) as pool:
        owner = pool.submit(post, client, payload=payload)
        try:
            assert entered.wait(5)
            duplicate = post(client, payload=payload)
        finally:
            release.set()
        assert owner.result(timeout=5).status_code == 200
    assert duplicate.status_code == 409
    assert usage(test_engine) == 1
    assert submitted == []


def test_capacity_rejects_new_key_but_allows_existing_replay(sandbox, monkeypatch):
    client, test_engine, submitted = sandbox
    monkeypatch.setattr(settings, "download_idempotency_max_entries", 1, raising=False)
    first = post(client)
    assert post(client, "two").status_code == 503
    assert post(client).json() == first.json()
    assert usage(test_engine) == len(submitted) == 1


def test_parallel_different_keys_respect_quota_limit(sandbox, monkeypatch):
    client, test_engine, submitted = sandbox
    monkeypatch.setattr(settings, "default_quota_limit", 1)
    ready = Barrier(4)

    def run(index):
        ready.wait(timeout=5)
        return post(client, str(index)).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(run, range(4)))
    assert sorted(statuses) == [200, 429, 429, 429]
    assert usage(test_engine) == len(submitted) == 1


@pytest.fixture
def receipt_clock(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(download_idempotency, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(settings, "download_idempotency_ttl_seconds", 10)
    monkeypatch.setattr(settings, "download_idempotency_direct_ttl_seconds", 3)
    return clock


def test_direct_expiry_returns_410_without_probe_or_charge(sandbox, receipt_clock, monkeypatch):
    client, test_engine, submitted = sandbox
    payload = {**PAYLOAD, "force_server": False}
    assert post(client, payload=payload).status_code == 200
    receipt_clock[0] += 3
    monkeypatch.setattr(ytdlp_service, "get_direct_url", lambda *_: (_ for _ in ()).throw(RuntimeError("no probe")))
    first, second = post(client, payload=payload), post(client, payload=payload)
    assert first.status_code == second.status_code == 410
    assert first.json()["detail"]["error_type"] == "idempotency_expired"
    assert first.json() == second.json()
    assert usage(test_engine) == 1
    assert submitted == []


def test_expired_terminal_receipt_releases_capacity_and_key(sandbox, receipt_clock, monkeypatch):
    client, test_engine, submitted = sandbox
    monkeypatch.setattr(settings, "download_idempotency_max_entries", 1)
    first = post(client)
    receipt_clock[0] += 9.999
    assert post(client).json() == first.json()
    assert post(client, "two").status_code == 503
    receipt_clock[0] += 0.001
    renewed = post(client)
    assert renewed.status_code == 200
    assert renewed.json()["job_id"] != first.json()["job_id"]
    assert usage(test_engine) == len(submitted) == 2


def test_expired_receipt_does_not_keep_payload_binding(sandbox, receipt_clock):
    client, test_engine, _ = sandbox
    assert post(client).status_code == 200
    receipt_clock[0] += 10
    assert post(client, payload={**PAYLOAD, "url": "https://example.com/new"}).status_code == 200
    assert usage(test_engine) == 2


def test_stale_pending_receipt_is_not_reclaimed_or_evicted(sandbox, receipt_clock, monkeypatch):
    client, test_engine, submitted = sandbox
    monkeypatch.setattr(settings, "download_idempotency_max_entries", 1)
    with Session(test_engine) as session:
        claim = download_idempotency.reserve(session, "alice", "one", DownloadRequest(**PAYLOAD))
        assert claim.record_id is not None
    receipt_clock[0] += 10_000_000
    response = post(client)
    assert response.status_code == 409
    assert response.json()["detail"]["error_type"] == "idempotency_in_progress"
    assert post(client, "two").status_code == 503
    assert usage(test_engine) == 0
    assert submitted == []
    with Session(test_engine) as session:
        assert session.get(DownloadIdempotency, claim.record_id).state == "pending"


def test_replay_survives_new_engine_and_application(sandbox):
    client, test_engine, submitted = sandbox
    first = post(client)
    reopened = create_engine(test_engine.url, connect_args={"check_same_thread": False})
    fresh_app = FastAPI()
    fresh_app.include_router(router)

    def sessions():
        with Session(reopened) as session:
            yield session

    fresh_app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(fresh_app) as fresh_client:
            second = post(fresh_client)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert usage(test_engine) == len(submitted) == 1
    finally:
        reopened.dispose()


def test_parallel_claims_cannot_exceed_capacity(sandbox, monkeypatch):
    client, test_engine, submitted = sandbox
    monkeypatch.setattr(settings, "download_idempotency_max_entries", 1)
    ready = Barrier(4)

    def run(index):
        ready.wait(timeout=5)
        return post(client, str(index)).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(run, range(4)))
    assert sorted(statuses) == [200, 503, 503, 503]
    assert usage(test_engine) == len(submitted) == 1


def test_parallel_same_key_has_only_one_owner(sandbox):
    client, test_engine, submitted = sandbox
    ready = Barrier(4)

    def run(_):
        ready.wait(timeout=5)
        return post(client)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(run, range(4)))
    assert all(response.status_code in (200, 409) for response in responses)
    assert any(response.status_code == 200 for response in responses)
    job_ids = {response.json()["job_id"] for response in responses if response.status_code == 200}
    assert len(job_ids) == usage(test_engine) == len(submitted) == 1


def test_authentication_precedes_receipt_lookup(sandbox):
    client, test_engine, submitted = sandbox
    assert post(client).status_code == 200
    assert post(client, user="missing").status_code == 401
    response = client.post("/api/download", json=PAYLOAD, headers={"Idempotency-Key": "one"})
    assert response.status_code == 401
    assert usage(test_engine) == len(submitted) == 1


def test_failed_completion_leaves_pending_and_never_resubmits(sandbox, monkeypatch):
    client, test_engine, submitted = sandbox

    def storage_failure(*_):
        raise RuntimeError("receipt storage unavailable")

    monkeypatch.setattr(download_idempotency, "complete", storage_failure)
    first, second = post(client), post(client)
    assert first.status_code == 503
    assert first.json()["detail"]["error_type"] == "idempotency_uncertain"
    assert second.status_code == 409
    assert usage(test_engine) == len(submitted) == 1


def test_sqlite_busy_fails_closed_before_work(sandbox):
    _, test_engine, submitted = sandbox
    quick_engine = create_engine(test_engine.url, connect_args={"timeout": 0.01})
    try:
        with test_engine.connect() as lock:
            lock.exec_driver_sql("BEGIN IMMEDIATE")
            with Session(quick_engine) as session:
                with pytest.raises(Exception) as error:
                    download_idempotency.reserve(session, "alice", "one", DownloadRequest(**PAYLOAD))
            assert error.value.status_code == 503
            assert error.value.detail["error_type"] == "idempotency_unavailable"
            lock.rollback()
        assert usage(test_engine) == 0
        assert submitted == []
    finally:
        quick_engine.dispose()


def test_uncertain_submission_is_never_reclaimed_after_retention(sandbox, receipt_clock, monkeypatch):
    client, test_engine, _ = sandbox
    calls = []

    def accepted_then_raised(job, *_):
        calls.append(job.id)
        raise RuntimeError("cannot determine whether executor accepted job")

    monkeypatch.setattr(job_manager, "submit_download", accepted_then_raised)
    first = post(client)
    receipt_clock[0] += 10_000_000
    second = post(client)
    assert first.status_code == second.status_code == 503
    assert first.json() == second.json()
    assert len(calls) == usage(test_engine) == 1


@pytest.mark.parametrize("change", ["delete", "expire", "foreign"])
def test_server_replay_rejects_missing_expired_or_foreign_job(sandbox, change):
    client, test_engine, submitted = sandbox
    first = post(client)
    assert first.status_code == 200
    with Session(test_engine) as session:
        job = session.get(Job, first.json()["job_id"])
        if change == "delete":
            session.delete(job)
        elif change == "expire":
            job.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(job)
        else:
            job.user_id = "bob"
            session.add(job)
        session.commit()
    replay, repeated = post(client), post(client)
    assert replay.status_code == repeated.status_code == 410
    assert replay.json()["detail"]["error_type"] == "idempotency_expired"
    assert replay.json() == repeated.json()
    assert usage(test_engine) == len(submitted) == 1
    with Session(test_engine) as session:
        receipt = session.exec(select(DownloadIdempotency)).one()
        assert receipt.state == "complete"


@pytest.mark.parametrize("field,value", [("url", "https://example.com/\ud800"), ("format_id", "\udfff")])
def test_fingerprint_handles_json_decodable_surrogates(sandbox, field, value):
    _, test_engine, submitted = sandbox
    # Pydantic rejects these at HTTP validation; exercise only the internal
    # fingerprint adapter defensively, without changing public schema behavior.
    request = DownloadRequest.model_construct(**{**PAYLOAD, field: value})
    encoding_error = None
    with Session(test_engine) as session:
        try:
            claim = download_idempotency.reserve(session, "alice", "surrogate", request)
        except UnicodeEncodeError as error:
            encoding_error = error
        assert encoding_error is None
        assert claim.record_id is not None
        with pytest.raises(Exception) as duplicate:
            download_idempotency.reserve(session, "alice", "surrogate", request)
        assert duplicate.value.status_code == 409
    assert usage(test_engine) == 0
    assert submitted == []


def test_authoritative_quota_failure_and_replay_have_complete_receipt_header(sandbox, monkeypatch):
    client, test_engine, _ = sandbox
    monkeypatch.setattr(settings, "default_quota_limit", 0)
    first = post(client)
    replay = post(client)
    assert first.status_code == replay.status_code == 429
    assert first.json() == replay.json()
    assert first.headers.get("Idempotency-Status") == "complete"
    assert replay.headers.get("Idempotency-Status") == "complete"
    assert usage(test_engine) == 0


def test_uncertain_failure_and_replay_have_no_complete_receipt_header(sandbox, monkeypatch):
    client, test_engine, _ = sandbox

    def accepted_then_raised(*_):
        raise RuntimeError("uncertain acceptance")

    monkeypatch.setattr(job_manager, "submit_download", accepted_then_raised)
    first, replay = post(client), post(client)
    assert first.status_code == replay.status_code == 503
    assert first.headers.get("Idempotency-Status") is None
    assert replay.headers.get("Idempotency-Status") is None
    assert usage(test_engine) == 1


def test_pending_conflict_has_no_complete_receipt_header(sandbox):
    client, test_engine, _ = sandbox
    with Session(test_engine) as session:
        download_idempotency.reserve(session, "alice", "one", DownloadRequest(**PAYLOAD))
    pending = post(client)
    assert pending.status_code == 409
    assert pending.headers.get("Idempotency-Status") is None
    assert usage(test_engine) == 0


def test_capacity_failure_has_no_complete_receipt_header(sandbox, monkeypatch):
    client, test_engine, _ = sandbox
    monkeypatch.setattr(settings, "download_idempotency_max_entries", 1)
    assert post(client).status_code == 200
    unavailable = post(client, "two")
    assert unavailable.status_code == 503
    assert unavailable.headers.get("Idempotency-Status") is None
    assert usage(test_engine) == 1
