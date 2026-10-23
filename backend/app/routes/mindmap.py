from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..config import settings
from ..models import User
from ..services.auth import get_current_user
from ..services.llm_service import LLMServiceError
from ..services.mindmap_service import (
    MindMapNode, generate_mindmap, validate_mindmap_configuration,
)
from ..services.request_cache import reuse
from .insight_common import load_cached_subtitle

router = APIRouter()


class MindMapRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    url: str = Field(min_length=1)
    subtitle_language: str | None = Field(default=None, min_length=1, max_length=32)
    output_language: str = Field(default="zh-CN", min_length=2, max_length=32)


class MindMapResponse(BaseModel):
    title: str
    source_language: str
    root: MindMapNode
    provider: str
    model: str


def _model_error(exc: LLMServiceError) -> HTTPException:
    return HTTPException(
        status_code=503 if exc.error_type == "llm_unconfigured" else 502,
        detail={"error_type": exc.error_type, "error": str(exc)},
    )


@router.post("/api/mindmap", response_model=MindMapResponse)
def mindmap(req: MindMapRequest, _user: User = Depends(get_current_user)) -> MindMapResponse:
    try:
        validate_mindmap_configuration()
    except LLMServiceError as exc:
        raise _model_error(exc) from exc
    doc = load_cached_subtitle(_user.id, req.url, req.subtitle_language)
    if len(doc.text) > settings.mindmap_max_source_chars:
        raise HTTPException(status_code=422, detail={
            "error_type": "mindmap_unsupported_length",
            "error": "字幕超过当前思维导图长度上限，仍可查看字幕或下载视频。",
        })

    def produce():
        try:
            result = generate_mindmap(doc.text, title=doc.title, output_language=req.output_language)
        except LLMServiceError as exc:
            raise _model_error(exc) from exc
        return MindMapResponse(title=doc.title, source_language=doc.language, root=result.root,
                               provider=result.provider, model=result.model)

    limits = {name: getattr(settings, name) for name in (
        "mindmap_max_source_chars", "mindmap_max_output_tokens", "mindmap_max_nodes", "mindmap_max_depth",
    )}
    return reuse("mindmap", _user.id, (req.model_dump(), doc, limits), produce)
