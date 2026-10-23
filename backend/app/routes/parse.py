from fastapi import APIRouter, Depends, HTTPException

from ..models import User
from ..schemas import FormatOption, ParseRequest, ParseResponse
from ..services.auth import get_current_user
from ..services.ytdlp_service import (
    classify_error, is_valid_url, parse_video, public_error_message,
)

router = APIRouter()


@router.post("/api/parse", response_model=ParseResponse)
def parse(req: ParseRequest, _user: User = Depends(get_current_user)) -> ParseResponse:
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail={"error_type": "invalid_url", "error": "无效链接"})
    try:
        meta, options = parse_video(req.url)
    except Exception as exc:  # noqa: BLE001
        error_type = classify_error(exc)
        message = public_error_message(exc)
        raise HTTPException(status_code=422, detail={"error_type": error_type, "error": message})
    return ParseResponse(
        title=meta["title"],
        thumbnail=meta["thumbnail"],
        duration=meta["duration"],
        duration_string=meta.get("duration_string"),
        uploader=meta.get("uploader"),
        platform=meta.get("platform"),
        view_count=meta.get("view_count"),
        upload_date=meta.get("upload_date"),
        description=meta.get("description"),
        subtitles=meta.get("subtitles", []),
        formats=[FormatOption(**o) for o in options],
    )
