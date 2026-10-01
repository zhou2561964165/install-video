import uuid
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
