from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..db import get_session
from ..models import Job, JobStatus
from ..schemas import DownloadRequest, DownloadResponse, JobResponse
from ..services import ytdlp_service
from ..services.jobs import job_manager

router = APIRouter()


@router.post("/api/download", response_model=DownloadResponse)
def download(req: DownloadRequest, session: Session = Depends(get_session)) -> DownloadResponse:
    job_manager.cleanup_expired()  # 懒触发 TTL 清理
    if not req.force_server:
        direct, headers = ytdlp_service.get_direct_url(req.url, req.format_id)
        if direct:
            return DownloadResponse(mode="direct", url=direct, headers=headers)

    job = Job(url=req.url, format_id=req.format_id, status=JobStatus.queued)
    session.add(job)
    session.commit()
    session.refresh(job)
    job_manager.submit_download(job, req.url, req.format_id)
    return DownloadResponse(mode="server", job_id=job.id)


@router.get("/api/job/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "任务不存在"})
    return JobResponse(
        id=job.id, status=job.status, progress=job.progress,
        title=job.title, error_type=job.error_type, error=job.error,
    )


@router.get("/api/file/{job_id}")
def get_file(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job or job.status != JobStatus.done or not job.file_path:
        raise HTTPException(status_code=404, detail={"error": "文件不存在或未完成"})
    path = Path(job.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "文件已过期清理"})
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
