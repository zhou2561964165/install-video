from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..models import User
from ..services.auth import get_current_user
from ..services import asr_service, ytdlp_service
from ..services.asr_languages import LANGUAGE_CODES
from ..services.request_cache import lookup_reused, reuse

router = APIRouter()


class TranscribeRequest(BaseModel):
    url: str = Field(min_length=1)
    language: str | None = Field(default=None, max_length=16)

    @field_validator('language')
    @classmethod
    def language_code(cls, value):
        if not value:
            return None
        value = value.lower().split('-')[0]
        # Keep HTTP validation independent of the optional inference package.
        if value not in LANGUAGE_CODES:
            raise ValueError('不支持的语音识别语言')
        return value


class TranscriptionExportRequest(TranscribeRequest):
    format: Literal['srt', 'vtt']


def _parameters(req: TranscribeRequest):
    return (req.url, req.language, asr_service.profile())


@router.get('/api/transcribe/capabilities')
def capabilities(_user: User = Depends(get_current_user)):
    return asr_service.capabilities()


@router.post('/api/transcribe')
def transcribe(req: TranscribeRequest, user: User = Depends(get_current_user)):
    if not ytdlp_service.is_valid_url(req.url):
        raise HTTPException(400, detail={'error_type': 'invalid_url', 'error': '无效链接'})
    def produce():
        try:
            return asdict(asr_service.transcribe_video(req.url, req.language))
        except asr_service.ASRError as exc:
            status = 503 if exc.error_type in {'transcription_unavailable', 'transcription_busy'} else 422
            raise HTTPException(status, detail={'error_type': exc.error_type, 'error': str(exc)}) from exc
    return reuse('transcription', user.id, _parameters(req), produce)


@router.post('/api/transcribe/export')
def export_transcription(req: TranscriptionExportRequest, user: User = Depends(get_current_user)):
    from ..services.subtitle_timing import SubtitleSegment, TimingError, export_segments, safe_export_filename
    result = lookup_reused('transcription', user.id, _parameters(req))
    if result is None:
        raise HTTPException(422, detail={'error_type': 'transcription_unavailable',
                                         'error': '请先完成音频转写，再导出时间轴。'})
    try:
        return {'filename': safe_export_filename(result['title'], req.format), 'format': req.format,
                'content': export_segments([SubtitleSegment(**seg) for seg in result['segments']], req.format)}
    except TimingError as exc:
        raise HTTPException(422, detail={'error_type': exc.error_type, 'error': str(exc)}) from exc
