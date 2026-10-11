from collections import defaultdict
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import Job, JobStatus, Quota, User
from app.services.auth import create_token
from app.services.quota import today_utc

client = TestClient(app)

NOT_FOUND = {
    "job": {"detail": {"error": "任务不存在"}},
    "file": {"detail": {"error": "文件不存在或未完成"}},
}


@pytest.fixture
def users(monkeypatch):
    # Keep the real authentication dependency and JWT verification; only reset
    # the per-process limiter so independent cases do not share request counts.
    monkeypatch.setattr("app.main._window", defaultdict(list))
    with Session(engine) as session:
        owner = User(email=f"owner-{uuid4()}@example.com", password_hash="unused")
        other = User(email=f"other-{uuid4()}@example.com", password_hash="unused")
        session.add(owner)
        session.add(other)
        session.commit()
        owner_id, other_id = owner.id, other.id
    return owner_id, other_id, {"Authorization": f"Bearer {create_token(owner_id)}"}


def _job(user_id, status=JobStatus.done, file_path=None):
    with Session(engine) as session:
        job = Job(
            url="https://example.com/private-source",
            user_id=user_id,
            status=status,
            progress=37.5,
            title="Private title",
            error_type="download_error",
            error="Private error details",
            file_path=file_path,
        )
        session.add(job)
        session.commit()
        return job.id


@pytest.mark.parametrize("route", ["job", "file"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
@pytest.mark.parametrize("existing", [True, False])
def test_get_requires_login_before_disclosing_job_existence(users, route, headers, existing):
    owner_id, _, _ = users
    job_id = _job(owner_id) if existing else str(uuid4())
    response = client.get(f"/api/{route}/{job_id}", headers=headers)
    assert response.status_code == 401
    assert response.json() == {
        "detail": {"error_type": "login_required", "error": "需要登录"},
    }


@pytest.mark.parametrize("route", ["job", "file"])
@pytest.mark.parametrize("ownership", ["other", "ownerless"])
@pytest.mark.parametrize(
    "status,file_exists",
    [
        (JobStatus.done, True),
        (JobStatus.done, False),
        (JobStatus.error, True),
        (JobStatus.queued, True),
        (JobStatus.downloading, True),
        (JobStatus.merging, True),
    ],
)
def test_inaccessible_job_matches_nonexistent_404(
    users, tmp_path, route, ownership, status, file_exists,
):
    _, other_id, headers = users
    path = tmp_path / "private.mp4"
    if file_exists:
        path.write_bytes(b"PRIVATE_BYTES")
    job_id = _job(other_id if ownership == "other" else None, status, str(path))

    response = client.get(f"/api/{route}/{job_id}", headers=headers)
    missing = client.get(f"/api/{route}/{uuid4()}", headers=headers)
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json() == NOT_FOUND[route]
    assert "PRIVATE_BYTES" not in response.text
    assert str(path) not in response.text
    with Session(engine) as session:
        # Legacy ownerless jobs must remain ownerless, rather than be claimed.
        assert session.get(Job, job_id).user_id == (other_id if ownership == "other" else None)


@pytest.mark.parametrize("status", list(JobStatus))
def test_owner_job_keeps_existing_response_fields_in_every_state(users, status):
    owner_id, _, headers = users
    job_id = _job(owner_id, status)
    response = client.get(f"/api/job/{job_id}", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "id": job_id,
        "status": status.value,
        "progress": 37.5,
        "title": "Private title",
        "error_type": "download_error",
        "error": "Private error details",
    }


@pytest.mark.parametrize("status", [JobStatus.queued, JobStatus.downloading, JobStatus.merging, JobStatus.error])
def test_owner_unfinished_file_is_not_streamed_even_when_path_exists(users, tmp_path, status):
    owner_id, _, headers = users
    path = tmp_path / "unfinished.mp4"
    path.write_bytes(b"UNFINISHED_BYTES")
    job_id = _job(owner_id, status, str(path))
    response = client.get(f"/api/file/{job_id}", headers=headers)
    assert response.status_code == 404
    assert response.json() == NOT_FOUND["file"]


@pytest.mark.parametrize("has_path", [False, True])
def test_owner_missing_or_expired_file_preserves_original_404(users, tmp_path, has_path):
    owner_id, _, headers = users
    job_id = _job(owner_id, file_path=str(tmp_path / "removed.mp4") if has_path else None)
    response = client.get(f"/api/file/{job_id}", headers=headers)
    assert response.status_code == 404
    assert response.json() == (
        {"detail": {"error": "文件已过期清理"}} if has_path else NOT_FOUND["file"]
    )


@pytest.mark.parametrize("has_owner_quota", [False, True])
def test_get_job_and_file_do_not_create_or_consume_quota(users, tmp_path, has_owner_quota):
    owner_id, other_id, headers = users
    with Session(engine) as session:
        session.add(Quota(user_id=other_id, date=today_utc(), downloads_used=3, limit=3))
        if has_owner_quota:
            session.add(Quota(user_id=owner_id, date=today_utc(), downloads_used=2, limit=3))
        session.commit()
        before = [
            quota.model_dump() for quota in session.exec(
                select(Quota).where(Quota.user_id.in_([owner_id, other_id])).order_by(Quota.id)
            ).all()
        ]
    path = tmp_path / "owner.mp4"
    path.write_bytes(b"OWNER_BYTES")
    job_id = _job(owner_id, file_path=str(path))
    other_job_id = _job(other_id, file_path=str(path))
    for _ in range(2):
        assert client.get(f"/api/job/{job_id}", headers=headers).status_code == 200
        response = client.get(f"/api/file/{job_id}", headers=headers)
        assert response.status_code == 200
        assert response.content == b"OWNER_BYTES"
        assert client.get(f"/api/job/{other_job_id}", headers=headers).status_code == 404
        assert client.get(f"/api/file/{other_job_id}", headers=headers).status_code == 404
    with Session(engine) as session:
        after = [
            quota.model_dump() for quota in session.exec(
                select(Quota).where(Quota.user_id.in_([owner_id, other_id])).order_by(Quota.id)
            ).all()
        ]
    assert after == before
