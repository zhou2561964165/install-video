from fastapi import APIRouter, Depends, HTTPException

from ..models import User
from ..schemas import (
    SubtitleRequest,
    SubtitleResponse,
    SubtitleTranslateRequest,
    SubtitleTranslateResponse,
)
from ..services.auth import get_current_user
from ..services.llm_service import LLMServiceError, translate_text
from .insight_common import load_subtitle

router = APIRouter()


@router.post("/api/subtitle", response_model=SubtitleResponse)
def subtitle(req: SubtitleRequest, _user: User = Depends(get_current_user)) -> SubtitleResponse:
    doc = load_subtitle(req.url, req.language)
    return SubtitleResponse(**doc.__dict__)


@router.post("/api/subtitle/translate", response_model=SubtitleTranslateResponse)
def translate(
    req: SubtitleTranslateRequest,
    _user: User = Depends(get_current_user),
) -> SubtitleTranslateResponse:
    doc = load_subtitle(req.url, req.source_language)
    try:
        result = translate_text(doc.text, req.target_language, source_language=doc.language)
    except LLMServiceError as exc:
        status = 503 if exc.error_type == "llm_unconfigured" else 502
        raise HTTPException(status_code=status, detail={"error_type": exc.error_type, "error": str(exc)}) from exc
    return SubtitleTranslateResponse(
        title=doc.title,
        source_language=doc.language,
        target_language=req.target_language,
        text=result.text,
        provider=result.provider,
        model=result.model,
    )
