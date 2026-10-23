from fastapi import APIRouter, Depends, HTTPException

from ..models import User
from ..schemas import (
    SubtitleExportRequest,
    SubtitleExportResponse,
    SubtitleRequest,
    SubtitleResponse,
    SubtitleTranslateRequest,
    SubtitleTranslateResponse,
)
from ..services.auth import get_current_user
from ..services.membership import require_vip
from ..services.llm_service import LLMServiceError, translate_text
from ..services.request_cache import reuse
from ..services.subtitle_timing import TimingError, export_segments, safe_export_filename
from .insight_common import load_cached_subtitle

router = APIRouter()


@router.post("/api/subtitle", response_model=SubtitleResponse)
def subtitle(req: SubtitleRequest, _user: User = Depends(require_vip)) -> SubtitleResponse:
    doc = load_cached_subtitle(_user.id, req.url, req.language)
    return SubtitleResponse(**doc.__dict__)


@router.post("/api/subtitle/export", response_model=SubtitleExportResponse)
def export_subtitle(req: SubtitleExportRequest, _user: User = Depends(require_vip)) -> SubtitleExportResponse:
    doc = load_cached_subtitle(_user.id, req.url, req.language)
    try:
        content = export_segments(doc.segments, req.format)
        filename = safe_export_filename(doc.title, req.format)
    except TimingError as exc:
        raise HTTPException(status_code=422, detail={"error_type": exc.error_type, "error": str(exc)}) from exc
    return SubtitleExportResponse(filename=filename, format=req.format, content=content)


@router.post("/api/subtitle/translate", response_model=SubtitleTranslateResponse)
def translate(
    req: SubtitleTranslateRequest,
    _user: User = Depends(require_vip),
) -> SubtitleTranslateResponse:
    doc = load_cached_subtitle(_user.id, req.url, req.source_language)
    def produce():
        try:
            result = translate_text(doc.text, req.target_language, source_language=doc.language)
        except LLMServiceError as exc:
            status = 503 if exc.error_type == "llm_unconfigured" else 502
            raise HTTPException(status_code=status, detail={"error_type": exc.error_type, "error": str(exc)}) from exc
        return SubtitleTranslateResponse(
            title=doc.title, source_language=doc.language, target_language=req.target_language,
            text=result.text, provider=result.provider, model=result.model,
        )
    return reuse('translation', _user.id, (req.model_dump(), doc), produce)
