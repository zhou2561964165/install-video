"""Development exemptions use real auth/download APIs and isolated SQLite rows."""
import json
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Job, Quota, User
from app.services import jobs, quota, ytdlp_service
from app.services.auth import create_token


DEV_ID = "abcdefab-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    policy = tmp_path / "dev-quota-policy.json"
    monkeypatch.setenv("DEV_QUOTA_POLICY_FILE", str(policy))
    monkeypatch.setattr(settings, "default_quota_limit", 2)
    monkeypatch.setattr("app.main._window", defaultdict(list))
    monkeypatch.setattr(quota, "today_utc", lambda: "2026-10-08")
    # Only external download work and unrelated expiry cleanup are replaced.
    monkeypatch.setattr(jobs.job_manager, "cleanup_expired", lambda: 0)
    monkeypatch.setattr(jobs, "_run_download", lambda job_id, url, fid: None)
    monkeypatch.setattr(ytdlp_service, "get_direct_url", lambda url, fid: ("https://cdn.example/v.mp4", {}))
    test_engine = create_engine(
        f"sqlite:///{(tmp_path / 'quota.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        session.add(User(id=DEV_ID, email="dev@example.com", password_hash="unused"))
        session.add(User(id=OTHER_ID, email="other@example.com", password_hash="unused"))
        session.commit()

    def session_override():
        with Session(test_engine) as session:
            yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            yield client, test_engine, policy
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        test_engine.dispose()


def _headers(user_id=DEV_ID):
    return {"Authorization": f"Bearer {create_token(user_id)}"}


def _download(client, user_id=DEV_ID, *, force_server=False):
    return client.post(
        "/api/download",
        json={"url": "https://example.com/v", "format_id": "18", "force_server": force_server},
        headers=_headers(user_id),
    )


def _me(client, user_id=DEV_ID):
    response = client.get("/api/auth/me", headers=_headers(user_id))
    assert response.status_code == 200
    return response.json()["quota"]


def _enable(policy):
    policy.write_text(json.dumps({"unlimited_user_ids": [DEV_ID]}), encoding="utf-8")


@pytest.mark.parametrize("force_server", [False, True])
def test_exempt_user_downloads_beyond_limit_and_keeps_usage(sandbox, force_server):
    # A skipped increment or a fabricated large limit breaks this contract.
    client, test_engine, policy = sandbox
    _enable(policy)
    for _ in range(4):
        response = _download(client, force_server=force_server)
        assert response.status_code == 200
        assert response.json()["mode"] == ("server" if force_server else "direct")
    assert _me(client) == {
        "date": "2026-10-08", "limit": None, "used": 4, "remaining": None, "unlimited": True,
    }
    with Session(test_engine) as session:
        row = session.exec(select(Quota).where(Quota.user_id == DEV_ID)).one()
        assert (row.downloads_used, row.limit) == (4, 2)
        if force_server:
            assert len(session.exec(select(Job).where(Job.user_id == DEV_ID)).all()) == 4


def test_existing_exhausted_row_survives_enable_and_immediate_revoke(sandbox):
    # Replacing the row/default instead of preserving its original limit fails.
    client, test_engine, policy = sandbox
    with Session(test_engine) as session:
        row = Quota(user_id=DEV_ID, date="2026-10-08", downloads_used=1, limit=1)
        row_id = row.id
        session.add(row)
        session.commit()
    assert _download(client).status_code == 429
    _enable(policy)
    assert _download(client).status_code == 200
    assert _me(client)["used"] == 2
    policy.write_text('{"unlimited_user_ids": []}', encoding="utf-8")
    assert _me(client) == {
        "date": "2026-10-08", "limit": 1, "used": 2, "remaining": -1, "unlimited": False,
    }
    assert _download(client).status_code == 429
    with Session(test_engine) as session:
        row = session.get(Quota, row_id)
        assert (row.downloads_used, row.limit) == (2, 1)


def test_other_user_keeps_integer_contract_and_exhaustion(sandbox):
    # Accidentally applying the exemption to all users must be rejected.
    client, _, policy = sandbox
    _enable(policy)
    assert _download(client, OTHER_ID).status_code == 200
    assert _me(client, OTHER_ID) == {
        "date": "2026-10-08", "limit": 2, "used": 1, "remaining": 1, "unlimited": False,
    }
    assert _download(client, OTHER_ID).status_code == 200
    response = _download(client, OTHER_ID)
    assert response.status_code == 429
    assert response.json()["detail"]["error_type"] == "quota"
    assert _me(client, OTHER_ID)["used"] == 2


@pytest.mark.parametrize("invalid_policy", [
    None, "{", "[]", "null", "{}",
    '{"unlimited_user_ids": "*"}',
    '{"unlimited_user_ids": null}',
    '{"unlimited_user_ids": [true]}',
    '{"unlimited_user_ids": [1]}',
    '{"unlimited_user_ids": [""]}',
    '{"unlimited_user_ids": ["*"]}',
    json.dumps({"unlimited_user_ids": [DEV_ID, "*"]}),
    json.dumps({"unlimited_user_ids": [DEV_ID, DEV_ID]}),
    json.dumps({"unlimited_user_ids": [DEV_ID], "unexpected": True}),
    '{"unlimited_user_ids": [], "unlimited_user_ids": ["' + DEV_ID + '"]}',
    json.dumps({"unlimited_user_ids": [" " + DEV_ID]}),
    json.dumps({"unlimited_user_ids": [DEV_ID.upper()]}),
])
def test_missing_or_invalid_policy_fails_closed(sandbox, invalid_policy):
    # Bad data must never open the exhaustion branch or remove finite integers.
    client, _, policy = sandbox
    if invalid_policy is not None:
        policy.write_text(invalid_policy, encoding="utf-8")
    assert _download(client).status_code == 200
    assert _download(client).status_code == 200
    response = _download(client)
    assert response.status_code == 429
    assert response.json()["detail"]["error_type"] == "quota"
    assert _me(client) == {
        "date": "2026-10-08", "limit": 2, "used": 2, "remaining": 0, "unlimited": False,
    }


@pytest.mark.parametrize("replacement", [None, "broken", b"\xff"])
def test_removal_or_corruption_revokes_without_resetting_usage(sandbox, replacement):
    client, _, policy = sandbox
    _enable(policy)
    for _ in range(3):
        assert _download(client).status_code == 200
    if replacement is None:
        policy.unlink()
    elif isinstance(replacement, bytes):
        policy.write_bytes(replacement)
    else:
        policy.write_text(replacement, encoding="utf-8")
    assert _download(client).status_code == 429
    info = _me(client)
    assert (info["used"], info["limit"], info["unlimited"]) == (3, 2, False)


def test_exemption_remains_on_next_day_and_revoke_uses_default(sandbox, monkeypatch):
    client, test_engine, policy = sandbox
    _enable(policy)
    for _ in range(3):
        assert _download(client).status_code == 200
    monkeypatch.setattr(quota, "today_utc", lambda: "2026-10-09")
    assert _me(client) == {
        "date": "2026-10-09", "limit": None, "used": 0, "remaining": None, "unlimited": True,
    }
    assert _download(client).status_code == 200
    policy.write_text('{"unlimited_user_ids": []}', encoding="utf-8")
    assert _me(client) == {
        "date": "2026-10-09", "limit": 2, "used": 1, "remaining": 1, "unlimited": False,
    }
    assert _download(client).status_code == 200
    assert _download(client).status_code == 429
    with Session(test_engine) as session:
        rows = session.exec(select(Quota).where(Quota.user_id == DEV_ID).order_by(Quota.date)).all()
        assert [(row.date, row.downloads_used, row.limit) for row in rows] == [
            ("2026-10-08", 3, 2), ("2026-10-09", 2, 2),
        ]


def test_unlimited_policy_does_not_bypass_authentication_or_ip_limit(sandbox, monkeypatch):
    client, _, policy = sandbox
    _enable(policy)
    unauthenticated = client.post("/api/download", json={"url": "https://example.com/v", "format_id": "18"})
    assert unauthenticated.status_code == 401
    monkeypatch.setattr("app.main._window", defaultdict(list))
    monkeypatch.setattr("app.main._settings_rate_limit", 1)
    assert _download(client).status_code == 200
    assert _download(client).status_code == 429
