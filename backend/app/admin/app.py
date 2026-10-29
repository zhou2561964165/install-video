"""Admin FastAPI sub-application: request ids, contract error shape, 503 gate, route assembly.

Its own middleware and exception handlers never touch the business API's error shapes.
build_asgi() mounts it at settings.api_base; the separate entry (app.admin_main) uses it with a schema check.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import AdminSettings
from .errors import AdminError, body

_log = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, 'request_id', None) or str(uuid.uuid4())


def _error(request: Request, status: int, error_type: str, *, field_errors=None, headers=None) -> JSONResponse:
    request_id = _request_id(request)
    response = JSONResponse(body(error_type, request_id, field_errors), status_code=status, headers=headers or {})
    response.headers['X-Request-ID'] = request_id
    return response


def create_admin_app(settings: AdminSettings, engine: Engine, *, session_reader=None) -> FastAPI:
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.state.settings, app.state.engine = settings, engine
    if session_reader is None and settings.stripe_read_key:
        from ..services.support_payment_check import StripeSessionReader
        session_reader = StripeSessionReader(settings.stripe_read_key, timeout=settings.stripe_timeout_seconds)
    app.state.session_reader = session_reader  # None: verification unavailable (no read key)
    unavailable = settings.unavailable_reason()

    @app.middleware('http')
    async def request_id_and_gate(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())  # contract: request id is a UUID
        if unavailable is not None:
            return _error(request, 503, 'admin_unavailable')
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        return response

    @app.exception_handler(AdminError)
    async def admin_error(request: Request, exc: AdminError):
        return _error(request, exc.status, exc.error_type, field_errors=exc.field_errors, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{'field': '.'.join(str(part) for part in item.get('loc', ())[1:]) or 'body', 'message': '字段值不合法'}
                  for item in exc.errors()]  # fixed safe text: never echo the input or the validator message
        return _error(request, 422, 'validation_failed', field_errors=fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        error_type = {404: 'not_found', 405: 'method_not_allowed'}.get(exc.status_code, 'internal_error')
        return _error(request, exc.status_code, error_type)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        _log.error('admin request failed: %s', type(exc).__name__)  # never the message (may carry data)
        return _error(request, 500, 'internal_error')

    from . import routes_auth, routes_read, routes_support
    app.include_router(routes_auth.router)
    app.include_router(routes_read.router)
    app.include_router(routes_support.router)
    return app


def build_asgi(settings: AdminSettings, engine: Engine, *, check_schema: bool = True, session_reader=None) -> FastAPI:
    """The admin app mounted at settings.api_base; optionally refuse to start on a stale schema."""
    @asynccontextmanager
    async def lifespan(_app):
        if check_schema:
            from ..db import assert_schema_current
            assert_schema_current(engine)
        yield

    outer = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    outer.mount(settings.api_base, create_admin_app(settings, engine, session_reader=session_reader))
    return outer
