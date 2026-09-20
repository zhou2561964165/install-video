import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

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
