"""SQLite submission receipts, isolated from download/queue implementation.

The terminal retention window begins on completion. Once it expires the key
may represent a new submission. Pending/uncertain receipts have no expiry: reclaiming
them could dispatch work again after an interrupted or uncertain submission.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from ..config import settings
from ..models import DownloadIdempotency, Job
from ..schemas import DownloadRequest, DownloadResponse


@dataclass(frozen=True)
class Claim:
    record_id: str | None = None
    response: DownloadResponse | None = None


def _error(status: int, kind: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error_type": kind, "error": message})


def reserve(session: Session, user_id: str, key: str, request: DownloadRequest) -> Claim:
    """Claim before quota/work, or replay the same authenticated submission.

    BEGIN IMMEDIATE serializes cleanup, capacity checking and insertion across
    processes. The database unique constraint is the final ownership boundary.
    No database lock is held during quota, provider I/O or queue submission.
    """
    if not 1 <= len(key) <= 128 or any(not "!" <= char <= "~" for char in key):
        raise _error(422, "idempotency_key", "Idempotency-Key 必须为1至128个可见ASCII字符")
    payload = json.dumps(request.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    try:
        with Session(session.get_bind(), expire_on_commit=False) as receipts:
            receipts.connection().exec_driver_sql("BEGIN IMMEDIATE")
            now = time.time()
            receipts.exec(delete(DownloadIdempotency).where(
                DownloadIdempotency.state != "pending",
                DownloadIdempotency.expires_at <= now,
            ))
            row = receipts.exec(select(DownloadIdempotency).where(
                DownloadIdempotency.user_id == user_id, DownloadIdempotency.key == key,
            )).first()
            if row is None:
                count = receipts.exec(select(func.count()).select_from(DownloadIdempotency)).one()
                if count >= settings.download_idempotency_max_entries:
                    raise _error(503, "idempotency_unavailable", "下载请求记录已满，请稍后再试")
                row = DownloadIdempotency(user_id=user_id, key=key, fingerprint=fingerprint, created_at=now)
                receipts.add(row)
                receipts.commit()
                return Claim(record_id=row.id)
            # Commit cleanup and release the writer lock before replay parsing.
            receipts.commit()
    except (OperationalError, IntegrityError) as exc:
        raise _error(503, "idempotency_unavailable", "下载请求记录暂不可用，请稍后再试") from exc

    if row.fingerprint != fingerprint:
        raise _error(409, "idempotency_conflict", "同一Idempotency-Key不能用于不同的下载请求")
    if row.state == "pending":
        raise _error(409, "idempotency_in_progress", "下载提交仍在处理或状态待确认，请保留原请求标识")
    if row.direct_expires_at is not None and row.direct_expires_at <= time.time():
        raise _error(410, "idempotency_expired", "此下载直链已过期，请明确发起一次新的下载")
    body = json.loads(row.response_json)
    if row.status_code != 200:
        headers = {"Idempotency-Status": "complete"} if row.state == "complete" else None
        raise HTTPException(status_code=row.status_code, detail=body["detail"], headers=headers)
    response = DownloadResponse.model_validate(body)
    if response.mode == "server":
        # Job/file retention can be shorter than receipt retention. Keep this
        # receipt even when its task disappeared, so replay never redispatches.
        with Session(session.get_bind()) as jobs:
            job_id = jobs.exec(select(Job.id).where(
                Job.id == response.job_id,
                Job.user_id == user_id,
                or_(Job.expires_at.is_(None), Job.expires_at > datetime.fromtimestamp(time.time(), timezone.utc)),
            )).first()
        if job_id is None:
            raise _error(410, "idempotency_expired", "此下载任务已失效，请明确发起一次新的下载")
    return Claim(response=response)


def _finish(
    session: Session, record_id: str, status_code: int, body: dict,
    *, direct: bool = False, uncertain_submission: bool = False,
) -> None:
    now = time.time()
    with Session(session.get_bind()) as receipts:
        result = receipts.exec(update(DownloadIdempotency).where(
            DownloadIdempotency.id == record_id, DownloadIdempotency.state == "pending",
        ).values(
            state="uncertain" if uncertain_submission else "complete", status_code=status_code,
            response_json=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            expires_at=None if uncertain_submission else now + settings.download_idempotency_ttl_seconds,
            direct_expires_at=(now + settings.download_idempotency_direct_ttl_seconds) if direct else None,
        ))
        if result.rowcount != 1:
            raise RuntimeError("Submission receipt ownership lost")
        receipts.commit()


def complete(session: Session, record_id: str, response: DownloadResponse) -> None:
    _finish(session, record_id, 200, response.model_dump(), direct=response.mode == "direct")


def fail(session: Session, record_id: str, error: HTTPException) -> bool:
    """Persist a failure and report whether a certain terminal receipt is durable."""
    uncertain_submission = (
        isinstance(error.detail, dict) and error.detail.get("error_type") == "idempotency_uncertain"
    )
    _finish(session, record_id, error.status_code, {"detail": error.detail}, uncertain_submission=uncertain_submission)
    return not uncertain_submission


def uncertain() -> HTTPException:
    return _error(503, "idempotency_uncertain", "下载提交状态未确定，请保留原请求标识，勿重复提交新任务")
