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
    limit: Optional[int]
    used: int
    remaining: Optional[int]
    unlimited: bool = False


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class MeResponse(BaseModel):
    user: UserResponse
    quota: QuotaInfo


class SubtitleRequest(BaseModel):
    url: str = Field(min_length=1)
    language: Optional[str] = Field(default=None, max_length=32)


class SubtitleResponse(BaseModel):
    title: str
    language: str
    is_auto: bool
    available_languages: list[str]
    text: str


class SubtitleTranslateRequest(BaseModel):
    url: str = Field(min_length=1)
    source_language: Optional[str] = Field(default=None, max_length=32)
    target_language: str = Field(default="zh-CN", min_length=2, max_length=32)


class SubtitleTranslateResponse(BaseModel):
    title: str
    source_language: str
    target_language: str
    text: str
    provider: str
    model: str


class SummaryRequest(BaseModel):
    url: str = Field(min_length=1)
    subtitle_language: Optional[str] = Field(default=None, max_length=32)
    output_language: str = Field(default="zh-CN", min_length=2, max_length=32)


class SummaryResponse(BaseModel):
    title: str
    source_language: str
    summary: str
    key_points: list[str]
    provider: str
    model: str
    format: Literal["structured", "markdown"] = "structured"
