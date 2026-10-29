from fastapi import HTTPException
from ..config import settings

from ..services import ytdlp_service
from ..services.outbound_httpx import ControlledHttpError
from ..services.outbound_policy import OutboundError
from ..services.subtitle_service import SubtitleServiceError, fetch_subtitle_document
from ..services.request_cache import reuse


def load_cached_subtitle(user_id: str, url: str, language: str | None):
    return reuse('subtitle', user_id, (url, language), lambda: load_subtitle(url, language))


def load_subtitle(url: str, language: str | None):
    if not ytdlp_service.is_valid_url(url):
        raise HTTPException(status_code=400, detail={"error_type": "invalid_url", "error": "无效链接"})
    try:
        if settings.pg_business_enabled:
            from ..services.source_broker import fetch_subtitle_document as isolated_subtitle
            return isolated_subtitle(settings.source_broker_socket, url, language)
        return fetch_subtitle_document(url, language)
    except (OutboundError, ControlledHttpError) as exc:
        raise HTTPException(exc.status_code, detail=exc.public_detail()) from None
    except SubtitleServiceError as exc:
        detail = {"error_type": exc.error_type, "error": str(exc)}
        if exc.available_languages:
            detail["available_languages"] = exc.available_languages
        raise HTTPException(status_code=422, detail=detail) from exc
    except Exception as exc:  # yt-dlp extraction failures
        raise HTTPException(
            status_code=422,
            detail={"error_type": ytdlp_service.classify_error(exc), "error": str(exc)},
        ) from exc
