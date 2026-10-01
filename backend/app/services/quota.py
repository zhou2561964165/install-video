"""额度服务：每用户每日下载额度（按 UTC 日粒度）。"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import settings
from ..models import Quota


def today_utc() -> str:
    """UTC 日期串（YYYY-MM-DD），额度按 UTC 日粒度。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_today(session: Session, user_id: str) -> Optional[Quota]:
    """取今日额度行；无则 None。"""
    return session.exec(
        select(Quota).where(Quota.user_id == user_id, Quota.date == today_utc())
    ).first()


def get_quota_info(session: Session, user_id: str) -> tuple[int, int, str]:
    """返回 (used, limit, date)；无今日行按默认额度计（不落库）。"""
    quota = get_today(session, user_id)
    used = quota.downloads_used if quota else 0
    limit = quota.limit if quota else settings.default_quota_limit
    return used, limit, today_utc()


def check_and_reserve(session: Session, user_id: str) -> None:
    """登录用户提交下载前扣额度；当日无行则按默认额度建行。

    超限抛 429 quota（前端 ERROR_SCENES.quota 已覆盖）；否则 downloads_used += 1 并提交。
    """
    quota = get_today(session, user_id)
    if quota is None:
        quota = Quota(user_id=user_id, date=today_utc(), downloads_used=0, limit=settings.default_quota_limit)
        session.add(quota)
    if quota.downloads_used >= quota.limit:
        raise HTTPException(status_code=429, detail={"error_type": "quota", "error": "今日下载额度已用完"})
    quota.downloads_used += 1
    session.commit()
