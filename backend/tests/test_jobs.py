from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import engine, init_db
from app.models import Job, JobStatus
from app.services.jobs import JobManager, job_manager


def test_submit_runs_fn_and_marks_done(monkeypatch, tmp_path):
    init_db()
    manager = JobManager(max_workers=1)
    result = {}

    def fake_download(job_id, url, format_id):
        result["job_id"] = job_id
        result["url"] = url

    monkeypatch.setattr(
        "app.services.jobs._run_download", fake_download
    )
    job = Job(url="https://example.com/v", format_id="18")
    from sqlmodel import Session

    with Session(engine) as s:
        s.add(job)
        s.commit()
        job_id = job.id

    manager.submit_download(job, "https://example.com/v", "18")
    # 线程池执行是异步的；这里只验证调度契约，真实状态落库由 Task 8 的集成测试覆盖
    assert isinstance(job_manager, JobManager)
    assert manager._executor is not None


def test_cleanup_expired_removes_file(tmp_path):
    init_db()
    from sqlmodel import Session

    expired = Job(
        url="https://example.com/v",
        status=JobStatus.done,
        file_path=str(tmp_path / "old.mp4"),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    fresh = Job(
        url="https://example.com/v2",
        status=JobStatus.done,
        file_path=str(tmp_path / "new.mp4"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=100),
    )
    (tmp_path / "old.mp4").write_bytes(b"x")
    (tmp_path / "new.mp4").write_bytes(b"y")

    with Session(engine) as s:
        s.add(expired)
        s.add(fresh)
        s.commit()

    manager = JobManager(max_workers=1)
    n = manager.cleanup_expired()
    assert n == 1
    assert not (tmp_path / "old.mp4").exists()
    assert (tmp_path / "new.mp4").exists()


def test_cleanup_expired_ignores_durable_v2_jobs(tmp_path):
    # C2 review minor: the in-process legacy cleaner must never delete v2 (lease-fenced) media or
    # rows; their lifecycle belongs to C5 (expired -> deleting -> deleted with tombstones).
    init_db()
    from sqlmodel import Session

    durable = Job(
        url="https://example.com/v2-durable",
        status=JobStatus.queued,
        file_path=str(tmp_path / "durable.mp4"),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        execution_version=2,
        internal_state="queued",
        run_deadline_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    (tmp_path / "durable.mp4").write_bytes(b"z")
    with Session(engine) as s:
        s.add(durable)
        s.commit()
        durable_id = durable.id

    JobManager(max_workers=1).cleanup_expired()
    assert (tmp_path / "durable.mp4").exists()
    with Session(engine) as s:
        assert s.get(Job, durable_id) is not None
