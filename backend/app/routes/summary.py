from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..models import User
from ..schemas import SummaryRequest, SummaryResponse
from ..services.auth import get_current_user
from ..services.llm_service import LLMServiceError, summarize_long_text, summarize_text
from .insight_common import load_subtitle

router = APIRouter()


@router.post("/api/summary", response_model=SummaryResponse)
def summary(req: SummaryRequest, _user: User = Depends(get_current_user)) -> SummaryResponse:
    doc = load_subtitle(req.url, req.subtitle_language)
    if len(doc.text) > settings.summary_max_source_chars:
        raise HTTPException(status_code=422, detail={
            "error_type": "summary_unsupported_length",
            "error": "字幕超过当前总结长度上限，仍可查看字幕或下载视频。",
        })
    is_long = len(doc.text) > settings.summary_long_threshold_chars
    if is_long and len(doc.text) > settings.llm_long_summary_max_input_chars:
        raise HTTPException(status_code=422, detail={
            "error_type": "summary_unsupported_length",
            "error": "字幕超过当前长文总结长度上限，仍可查看字幕或下载视频。",
        })
    try:
        generate = summarize_long_text if is_long else summarize_text
        result = generate(doc.text, title=doc.title, output_language=req.output_language)
    except LLMServiceError as exc:
        status = 503 if exc.error_type in {"llm_unconfigured", "llm_busy"} else 502
        raise HTTPException(status_code=status, detail={"error_type": exc.error_type, "error": str(exc)}) from exc
    return SummaryResponse(
        title=doc.title,
        source_language=doc.language,
        summary=result.summary,
        key_points=result.key_points,
        provider=result.provider,
        model=result.model,
        format="markdown" if is_long else "structured",
    )
