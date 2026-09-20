import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..config import settings
from ..db import engine
from ..models import Job, JobStatus
from .ytdlp_service import classify_error


def _run_download(job_id: str, url: str, format_id: str) -> None:
    # 在 Task 8 中由 download 路由注入真实实现；此处为可替换的入口
    raise NotImplementedError


class JobManager:
    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or settings.max_concurrent_downloads
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._lock = threading.Lock()

    def submit_download(self, job: Job, url: str, format_id: str) -> None:
        self._executor.submit(self._safe_run, job.id, url, format_id)

    def _safe_run(self, job_id: str, url: str, format_id: str) -> None:
        try:
            _run_download(job_id, url, format_id)
        except Exception as exc:  # noqa: BLE001
            self._mark_error(job_id, exc)

    def _mark_error(self, job_id: str, exc: Exception) -> None:
        with self._lock, Session(engine) as s:
            job = s.get(Job, job_id)
            if job:
                job.status = JobStatus.error
                job.error_type = classify_error(exc)
                job.error = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                s.add(job)
                s.commit()

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        removed = 0
        with Session(engine) as s:
            jobs = s.exec(
                select(Job).where(
                    Job.expires_at.is_not(None), Job.expires_at < now
                )
            ).all()
            for job in jobs:
                if job.file_path:
                    p = Path(job.file_path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                s.delete(job)
                removed += 1
            s.commit()
        return removed


job_manager = JobManager()
