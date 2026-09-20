import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from ..config import settings
from ..db import engine
from ..models import Job, JobStatus
from .ytdlp_service import classify_error
from .ytdlp_service import download as _ytdlp_download


def _run_download(job_id: str, url: str, format_id: str) -> None:
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if not job:
            return
        job.status = JobStatus.downloading
        job.updated_at = datetime.now(timezone.utc)
        s.add(job)
        s.commit()

    job_dir = Path(settings.temp_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(job_dir / "%(title)s.%(ext)s")

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = (d.get("downloaded_bytes") or 0) / total * 100 if total else 0
            _update_progress(job_id, min(pct, 100.0))
        elif d.get("status") == "finished":
            _update_progress(job_id, 100.0)

    file_path = _ytdlp_download(url, format_id, outtmpl, hook)

    size = os.path.getsize(file_path)
    if size > settings.max_file_size:
        Path(file_path).unlink(missing_ok=True)
        with Session(engine) as s:
            job = s.get(Job, job_id)
            job.status = JobStatus.error
            job.error_type = "quota"
            job.error = "文件超过大小上限"
            job.updated_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
        return

    with Session(engine) as s:
        job = s.get(Job, job_id)
        job.status = JobStatus.done
        job.progress = 100.0
        job.file_path = file_path
        job.file_size = size
        job.expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.ttl_seconds)
        job.updated_at = datetime.now(timezone.utc)
        s.add(job)
        s.commit()


def _update_progress(job_id: str, pct: float) -> None:
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if job:
            job.progress = pct
            job.updated_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()


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
