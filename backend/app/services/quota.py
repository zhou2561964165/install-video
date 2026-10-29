"""额度服务：每用户每日下载额度（按 UTC 日粒度）。"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from ..config import settings
from ..models import DownloadOperation, Quota, QuotaCharge
from .db_transactions import lock_user
from .quota_policy import is_unlimited_user


def today_utc() -> str:
    """UTC 日期串（YYYY-MM-DD），额度按 UTC 日粒度。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_today(session: Session, user_id: str) -> Optional[Quota]:
    """取今日额度行；无则 None。"""
    return session.exec(
        select(Quota).where(Quota.user_id == user_id, Quota.date == today_utc())
    ).first()


def get_quota_info(session: Session, user_id: str) -> tuple[int, Optional[int], str]:
    """返回 (used, limit, date)；豁免时 limit=None，仍保留使用计数。"""
    quota = get_today(session, user_id)
    used = quota.downloads_used if quota else 0
    limit = quota.limit if quota else settings.default_quota_limit
    if settings.membership_unlimited_downloads or is_unlimited_user(user_id):
        limit = None
    return used, limit, today_utc()


def check_and_reserve(session: Session, user_id: str) -> None:
    """登录用户提交下载前扣额度；当日无行则按默认额度建行。

    超限抛 429 quota；开发豁免只跳过耗尽检查，仍累计 downloads_used。
    """
    # The legacy compatibility wrapper does not create durable operations. New PG
    # submissions must use charge_submission within their acceptance transaction.
    if session.get_bind().dialect.name == 'postgresql':
        raise RuntimeError('PostgreSQL submissions require charge_submission')
    day = today_utc()
    # SQLite arbitrates concurrent first-use inserts and increments atomically.
    # Preserve each existing row's configured limit and development exemption.
    session.exec(insert(Quota).values(
        user_id=user_id, date=day, downloads_used=0, limit=settings.default_quota_limit,
    ).on_conflict_do_nothing(index_elements=["user_id", "date"]))
    statement = update(Quota).where(Quota.user_id == user_id, Quota.date == day)
    if not settings.membership_unlimited_downloads and not is_unlimited_user(user_id):
        statement = statement.where(Quota.downloads_used < Quota.limit)
    result = session.exec(statement.values(downloads_used=Quota.downloads_used + 1))
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=429, detail={"error_type": "quota", "error": "今日下载额度已用完"})
    session.commit()


def charge_submission(session: Session, user_id: str, operation_id: str, accepted_at: datetime) -> QuotaCharge:
    """Charge once at the DB-accepted UTC day; never commit or move day on replay.

Call after resource/User/Membership/receipt locks and operation INSERT, before
Quota/Job locks. accepted_at must be the operation's DB-clock acceptance value.
Unlimited and local development exemption policy remain the existing policy.
"""
    lock_user(session, user_id)
    session.flush()
    operation = session.exec(select(DownloadOperation).where(
        DownloadOperation.id == operation_id).with_for_update().execution_options(populate_existing=True)).first()
    if (accepted_at.tzinfo is None or operation is None or operation.user_id != user_id or
            operation.accepted_at != accepted_at or
            operation.quota_day != accepted_at.astimezone(timezone.utc).date()):
        raise HTTPException(409, detail={'error_type': 'submission_changed', 'error': '提交记录不一致'})
    existing = session.get(QuotaCharge, operation_id, populate_existing=True)
    if existing is not None:
        if existing.user_id != user_id or existing.quota_day != operation.quota_day or existing.delta != 1:
            raise HTTPException(409, detail={'error_type': 'submission_changed', 'error': '提交记录不一致'})
        return existing
    day = operation.quota_day.isoformat()
    session.exec(pg_insert(Quota).values(user_id=user_id, date=day, downloads_used=0,
        limit=settings.default_quota_limit).on_conflict_do_nothing(constraint='uq_quota_user_date'))
    statement = update(Quota).where(Quota.user_id == user_id, Quota.date == day)
    if not settings.membership_unlimited_downloads and not is_unlimited_user(user_id):
        statement = statement.where(Quota.downloads_used < Quota.limit)
    result = session.exec(statement.values(downloads_used=Quota.downloads_used + 1).returning(Quota.id)).first()
    if result is None:
        raise HTTPException(429, detail={'error_type': 'quota', 'error': '今日下载额度已用完'})
    charge = QuotaCharge(operation_id=operation_id, user_id=user_id, quota_day=operation.quota_day,
                         charged_at=session.exec(select(func.clock_timestamp())).one())
    session.add(charge)
    session.flush()
    return charge
