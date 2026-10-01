from datetime import datetime
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
    resolution: Optional[str] = None
    filesize: Optional[int] = None
    has_audio: bool = True
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    direct: bool = False
    note: Optional[str] = None


class ParseResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    duration_string: Optional[str] = None
    uploader: Optional[str] = None
    platform: Optional[str] = None
    view_count: Optional[int] = None
    upload_date: Optional[str] = None
    description: Optional[str] = None
    subtitles: list[str] = []
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


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime


class QuotaInfo(BaseModel):
    date: str
    limit: int
    used: int
    remaining: int


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class MeResponse(BaseModel):
    user: UserResponse
    quota: QuotaInfo
