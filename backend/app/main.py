from fastapi import FastAPI

from .db import init_db
from .routes.parse import router as parse_router

app = FastAPI(title="万能视频下载")

init_db()
app.include_router(parse_router)
