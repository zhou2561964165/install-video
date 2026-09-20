from typing import Literal, Optional

from pydantic import BaseModel, Field

from .models import JobStatus


class ParseRequest(BaseModel):
    url: str = Field(min_length=1)


class FormatOption(BaseModel):
    format_id: str
    label: str
    height: Optional[int] = None
    ext: str = "mp4"
    filesize: Optional[int] = None
    direct: bool = False
    note: Optional[str] = None


class ParseResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    formats: list[FormatOption]


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1)
    format_id: str = Field(min_length=1)
    force_server: bool = False


class DownloadResponse(BaseModel):
    mode: Literal["direct", "server"]
    url: Optional[str] = None
    headers: dict = {}
    job_id: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    progress: float
    title: Optional[str] = None
    error_type: Optional[str] = None
    error: Optional[str] = None
