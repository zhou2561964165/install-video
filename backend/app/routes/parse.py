from fastapi import APIRouter, HTTPException

from ..schemas import FormatOption, ParseRequest, ParseResponse
from ..services.ytdlp_service import classify_error, is_valid_url, parse_video

router = APIRouter()


@router.post("/api/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    if not is_valid_url(req.url):
        raise HTTPException(status_code=400, detail={"error_type": "invalid_url", "error": "无效链接"})
    try:
        meta, options = parse_video(req.url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail={"error_type": classify_error(exc), "error": str(exc)})
    return ParseResponse(
        title=meta["title"],
        thumbnail=meta["thumbnail"],
        duration=meta["duration"],
        formats=[FormatOption(**o) for o in options],
    )
