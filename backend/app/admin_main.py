"""Separate admin ASGI entry: `uvicorn app.admin_main:app` (PostgreSQL only).

Serves only the admin API at ADMIN_API_BASE; never imports the business app (app.main), never calls
init_db() and never lifts the business PostgreSQL startup block. Refuses to start unless the database
is at the migration head.
"""
from .admin.app import build_asgi
from .admin.config import AdminSettings
from .config import settings
from .db import build_engine

app = build_asgi(AdminSettings.from_env(), build_engine(settings.db_url, role='api'))
