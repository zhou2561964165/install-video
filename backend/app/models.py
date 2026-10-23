import uuid
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    merging = "merging"
    done = "done"
    error = "error"


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    url: str
    title: Optional[str] = None
    format_id: Optional[str] = None
    status: JobStatus = Field(default=JobStatus.queued)
    progress: float = Field(default=0.0)
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    error_type: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    # v2：归属用户（nullable，匿名 v1 任务为 None）
    user_id: Optional[str] = Field(default=None, foreign_key="user.id")


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Quota(SQLModel, table=True):
    # (user_id, date) 唯一：每用户每日一行
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_quota_user_date"),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    date: str
    downloads_used: int = Field(default=0)
    limit: int


class DownloadIdempotency(SQLModel, table=True):
    """Submission receipts; pending rows are never automatically reclaimed."""

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_download_idempotency_user_key"),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    key: str = Field(max_length=128)
    fingerprint: str
    state: str = Field(default="pending")
    created_at: float = Field(default_factory=time.time)
    # None protects pending/uncertain submissions from automatic dispatch again.
    expires_at: Optional[float] = Field(default=None, index=True)
    direct_expires_at: Optional[float] = None
    status_code: Optional[int] = None
    response_json: Optional[str] = None


class Membership(SQLModel, table=True):
    user_id: str = Field(primary_key=True, foreign_key="user.id")
    customer_id: Optional[str] = Field(default=None, unique=True)
    subscription_id: Optional[str] = Field(default=None, unique=True)
    status: str = "free"
    expires_at: float = 0
    cancel_at_period_end: bool = False
    active_checkout_id: Optional[str] = None
    revision: int = 0
    entitlement_source: Optional[str] = None


class BillingCheckout(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    price_id: str
    mode: str
    duration_days: int
    origin: str
    customer_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    stripe_id: Optional[str] = Field(default=None, unique=True)
    url: Optional[str] = None
    expires_at: float = 0
    state: str = "pending"
    fulfilled: bool = False


class BillingEvent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    processed_at: float = Field(default_factory=time.time)


class BillingPayment(SQLModel, table=True):
    payment_intent: str = Field(primary_key=True)
    user_id: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    source_id: Optional[str] = None
    revoked: bool = False


class DownloadAccess(SQLModel, table=True):
    job_id: str = Field(primary_key=True, foreign_key="job.id")
    # None means unrestricted at submission; free users cannot retrieve it later.
    max_height: Optional[int] = None
