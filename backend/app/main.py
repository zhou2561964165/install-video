import time
from collections import defaultdict

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from .config import settings
from .db import init_db
from .routes.auth import router as auth_router
from .routes.download import router as download_router
from .routes.parse import router as parse_router
from .routes.subtitle import router as subtitle_router
from .routes.summary import router as summary_router

app = FastAPI(title="万能视频下载")

init_db()

_settings_rate_limit = settings.rate_limit_requests  # 测试可覆盖

_window: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        now = time.monotonic()
        key = request.client.host if request.client else "unknown"
        window = _settings_rate_limit
        win_sec = settings.rate_limit_window_seconds
        _window[key] = [t for t in _window[key] if now - t < win_sec]
        if len(_window[key]) >= window:
            return JSONResponse(status_code=429, content={"detail": {"error_type": "quota", "error": "请求过于频繁"}})
        _window[key].append(now)
    return await call_next(request)

app.include_router(parse_router)
app.include_router(download_router)
app.include_router(auth_router)
app.include_router(subtitle_router)
app.include_router(summary_router)
