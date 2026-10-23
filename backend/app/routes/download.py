from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..db import get_session
from ..models import DownloadAccess, Job, JobStatus, User
from ..schemas import DownloadRequest, DownloadResponse, JobResponse
from ..services import download_idempotency, ytdlp_service
from ..services.auth import get_current_user
from ..services.bilibili_session import SessionError
from ..services.jobs import job_manager
from ..services.quota import check_and_reserve
from ..services.membership import max_height, required

router = APIRouter()


@router.post("/api/download", response_model=DownloadResponse)
def download(
    req: DownloadRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DownloadResponse:
    height_limit = max_height(session, user.id)
    if height_limit is not None:
        try:
            bounded_format = ytdlp_service.restrict_format(req.url, req.format_id, height_limit)
        except ValueError:
            raise required() from None
        except SessionError as exc:
            raise HTTPException(422, detail={
                "error_type": "verification_required",
                "error": ytdlp_service.public_error_message(exc),
            }) from None
        except Exception:
            raise HTTPException(422, detail={"error_type": "format_unverified", "error": "无法确认视频清晰度，请重新解析"}) from None
        # Check before idempotency replay, and retain the same canonical fingerprint.
        req = req.model_copy(update={"format_id": bounded_format})
    receipt_id = None
    if idempotency_key is not None:
        claim = download_idempotency.reserve(session, user.id, idempotency_key, req)
        if claim.response is not None:
            return claim.response
        receipt_id = claim.record_id
    try:
        response = _submit_download(req, session, user, height_limit)
    except HTTPException as exc:
        if receipt_id is not None:
            try:
                if download_idempotency.fail(session, receipt_id, exc):
                    exc.headers = {**(exc.headers or {}), "Idempotency-Status": "complete"}
            except Exception:
                raise download_idempotency.uncertain() from None
        raise
    except Exception:
        if receipt_id is None:
            raise
        session.rollback()
        error = download_idempotency.uncertain()
        try:
            download_idempotency.fail(session, receipt_id, error)
        except Exception:
            # Keep the durable pending row if completion itself failed.
            pass
        raise error from None
    if receipt_id is not None:
        try:
            download_idempotency.complete(session, receipt_id, response)
        except Exception:
            raise download_idempotency.uncertain() from None
    return response


def _submit_download(req: DownloadRequest, session: Session, user: User, height_limit: int | None = None) -> DownloadResponse:
    job_manager.cleanup_expired()  # 懒触发 TTL 清理
    # 已登录用户提交即扣额度（直链与服务端下载同计）。
    check_and_reserve(session, user.id)
    if not req.force_server and not ytdlp_service.requires_server_download(req.url):
        try:
            direct, headers = ytdlp_service.get_direct_url(req.url, req.format_id)
        except Exception:  # 直链探测失败（无效/过期/网络）→ 落到服务端下载
            direct = None
        if direct:
            return DownloadResponse(mode="direct", url=direct, headers=headers)

    job = Job(url=req.url, format_id=req.format_id, status=JobStatus.queued, user_id=user.id)
    session.add(job)
    session.commit()
    session.refresh(job)
    session.add(DownloadAccess(job_id=job.id, max_height=height_limit))
    session.commit()
    try:
        job_manager.submit_download(job, req.url, req.format_id)
    except Exception:
        # Queue acceptance can be uncertain. Do not expose an exception message
        # or treat an external HTTPException as a safe, replayable business error.
        raise RuntimeError("Download submission uncertain") from None
    return DownloadResponse(mode="server", job_id=job.id)


@router.get("/api/job/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobResponse:
    job = session.exec(select(Job).where(Job.id == job_id, Job.user_id == user.id)).first()
    if not job:
        raise HTTPException(status_code=404, detail={"error": "任务不存在"})
    return JobResponse(
        id=job.id, status=job.status, progress=job.progress,
        title=job.title, error_type=job.error_type, error=job.error,
    )


@router.get("/api/file/{job_id}")
def get_file(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    job = session.exec(select(Job).where(Job.id == job_id, Job.user_id == user.id)).first()
    if not job or job.status != JobStatus.done or not job.file_path:
        raise HTTPException(status_code=404, detail={"error": "文件不存在或未完成"})
    limit = max_height(session, user.id)
    access = session.get(DownloadAccess, job.id)
    if limit is not None and (not access or access.max_height is None or access.max_height > limit):
        raise required()
    path = Path(job.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "文件已过期清理"})
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
