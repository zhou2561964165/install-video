from datetime import datetime, timezone

from app.db import engine, init_db
from app.models import Job, JobStatus


def test_job_defaults():
    job = Job(url="https://example.com/video")
    assert job.status == JobStatus.queued
    assert job.progress == 0.0
    assert job.id  # uuid 自动生成
    assert job.created_at.tzinfo is not None


def test_job_persist_roundtrip():
    init_db()
    from sqlmodel import Session

    job = Job(url="https://example.com/v", title="测试视频")
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        got = session.get(Job, job.id)
        assert got is not None
        assert got.title == "测试视频"
