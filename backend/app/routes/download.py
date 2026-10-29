from pathlib import Path
from dataclasses import replace
import unicodedata
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..models import DownloadAccess, Job, JobStatus, User
from ..schemas import DownloadRequest, DownloadResponse, JobResponse
from ..services import download_idempotency, download_submission, file_reads, file_stream, ytdlp_service
from ..services.auth import get_current_user
from ..services.bilibili_session import SessionError
from ..services.jobs import job_manager
from ..services.quota import check_and_reserve
from ..services.membership import max_height, required
from ..services.outbound_httpx import ControlledHttpError
from ..services.outbound_policy import OutboundError

router = APIRouter()


@router.post("/api/download", response_model=DownloadResponse)
def download(
    req: DownloadRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DownloadResponse:
    if session.get_bind().dialect.name == 'postgresql':
        return _submit_durable(req, session, user, idempotency_key)
    height_limit = max_height(session, user.id)
    if height_limit is not None:
        try:
            bounded_format = ytdlp_service.restrict_format(req.url, req.format_id, height_limit)
        except (OutboundError, ControlledHttpError) as exc:
            raise HTTPException(exc.status_code, detail=exc.public_detail()) from None
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


def _verify_source_format(path, url, format_id, height):
    from ..services.source_broker import verify_format
    return verify_format(path, url, format_id, height)


def _submit_durable(req, session, user, idempotency_key):
    if settings.pg_cutover_read_only:
        raise HTTPException(503, detail={'error_type': 'maintenance', 'error': '系统维护中，请稍后重试'})
    download_submission.validate_key(idempotency_key)
    engine, user_id = session.get_bind(), user.id
    # Close the auth/request transaction before any broker/network wait.
    session.close()
    access = download_submission.read_access_snapshot(engine, user_id)
    try:
        canonical = _verify_source_format(settings.source_broker_socket, req.url, req.format_id, access.max_height)
    except (OutboundError, ControlledHttpError) as exc:
        raise HTTPException(exc.status_code, detail=exc.public_detail()) from None
    bounded = req.model_copy(update={'format_id': canonical})
    return download_submission.submit_download(engine, user_id, bounded, idempotency_key,
        replace(access, canonical_format_id=canonical), server_required=True)


def _submit_download(req: DownloadRequest, session: Session, user: User, height_limit: int | None = None) -> DownloadResponse:
    job_manager.cleanup_expired()  # 懒触发 TTL 清理
    # 已登录用户提交即扣额度（直链与服务端下载同计）。
    check_and_reserve(session, user.id)
    if not req.force_server and not ytdlp_service.requires_server_download(req.url):
        try:
            direct, headers = ytdlp_service.get_direct_url(req.url, req.format_id)
        except (OutboundError, ControlledHttpError) as exc:
            raise HTTPException(exc.status_code, detail=exc.public_detail()) from None
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


_LEGACY_RECOVERY_MESSAGE = "该任务在系统迁移时中断，请重新发起下载"


@router.get("/api/job/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JobResponse:
    job = session.exec(select(Job).where(Job.id == job_id, Job.user_id == user.id)).first()
    if not job:
        raise HTTPException(status_code=404, detail={"error": "任务不存在"})
    status, error_type, error, progress = job.status, job.error_type, job.error, job.progress
    if job.internal_state == 'legacy_hold' and job.status != JobStatus.queued:
        # C6b (A contract §6): an imported v1 Job that was mid-download is never resumed automatically.
        status, error_type, error, progress = JobStatus.error, 'legacy_recovery_required', _LEGACY_RECOVERY_MESSAGE, 0.0
    return JobResponse(
        id=job.id, status=status, progress=progress,
        title=job.title, error_type=error_type, error=error,
    )


_READ_ERRORS = {'file_missing': '文件不存在或已不可用', 'file_expired': '文件已过期',
                'file_busy': '文件正在处理，请稍后重试', 'file_storage_unavailable': '文件存储暂不可用'}
_BUSY_RETRY_SECONDS = '2'


def _download_name(title: str | None, job_id: str, media_format: str) -> str:
    # Drop control and Unicode format characters (e.g. bidi overrides that disguise the extension).
    cleaned = ''.join('_' if unicodedata.category(char)[0] == 'C' or char in '/\\' else char for char in title or '')
    name = cleaned.strip()[:150] or job_id
    return f'{name}.{media_format}'


def _durable_file(request: Request, session: Session, user: User, job_id: str):
    """C4: durable (PostgreSQL) read; decisions and read lease in file_reads, bytes from the open handle.

    The request session is closed before the response is returned: a download never holds a pooled
    connection or an open transaction (renewal and end use their own short sessions).
    """
    if settings.media_root is None:
        session.close()
        raise HTTPException(503, detail={'error_type': 'file_storage_unavailable', 'error': '文件存储暂不可用'})
    try:
        opened = file_reads.open_read(session, user.id, job_id, media_root=settings.media_root,
                                      height_limit=max_height(session, user.id),
                                      legacy_root=Path(settings.temp_dir).resolve())  # as v1 wrote it
    except file_reads.ReadDenied as denied:
        if denied.error_type == 'membership_required':
            raise required() from None
        headers = {'Retry-After': _BUSY_RETRY_SECONDS} if denied.error_type == 'file_busy' else None
        raise HTTPException(denied.status, detail={'error_type': denied.error_type,
                                                   'error': _READ_ERRORS[denied.error_type]},
                            headers=headers) from None
    finally:
        session.close()
    engine = session.get_bind()

    def renew() -> bool:
        if opened.read_id is None:
            return True  # C6b imported v1 file: no read lease; the transfer cap still applies
        try:
            with Session(engine) as renewal:
                renewed = file_reads.renew_read(renewal, opened.read_id)
                renewal.commit()
                return renewed
        except Exception:
            return False  # cannot prove the read lease: stop the transfer

    def end() -> None:
        if opened.read_id is None:
            return
        with Session(engine) as ending:
            file_reads.end_read(ending, opened.read_id)
            ending.commit()

    try:
        return file_stream.stream_response(
            opened.file, opened.size, etag=opened.etag,
            filename=_download_name(opened.title, job_id, opened.media_format),
            media_type='application/octet-stream', range_header=request.headers.get('range'),
            if_range=request.headers.get('if-range'), renew=renew, end=end,
            renew_seconds=file_reads.READ_RENEW_SECONDS, max_seconds=file_reads.READ_MAX_SECONDS)
    except BaseException:
        # Nothing will stream: release the file and the read lease now instead of leaking them.
        opened.file.close()
        end()
        raise


@router.get("/api/file/{job_id}")
def get_file(
    job_id: str,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if session.get_bind().dialect.name == 'postgresql':
        return _durable_file(request, session, user, job_id)
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
