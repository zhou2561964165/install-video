"""Admin authentication: POST /auth/login, GET /auth/me, POST /auth/logout (contract M1)."""
from __future__ import annotations

from datetime import timedelta
import math
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import and_, delete, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from ..models import User
from ..models_admin import accountcontrol, admingrant, adminloginthrottle, adminsession
from ..services import admin_audit
from ..services.auth import verify_password
from . import security
from .deps import (COOKIE, AdminContext, clear_cookie_header, current_admin, engine_of, require_csrf, require_origin,
                   settings_of)
from .errors import AdminError
from .schemas import AdminMe, LoginRequest, SessionCreated, capabilities, utc

router = APIRouter()


_RESERVE = text(
    'INSERT INTO app.adminloginthrottle (key_hash, window_start, failures) VALUES (:key, now(), 0) '
    'ON CONFLICT (key_hash) DO UPDATE SET '
    'window_start = CASE WHEN adminloginthrottle.window_start <= now() - make_interval(secs => :window) '
    'THEN now() ELSE adminloginthrottle.window_start END, '
    'failures = CASE WHEN adminloginthrottle.window_start <= now() - make_interval(secs => :window) '
    'THEN 0 ELSE adminloginthrottle.failures END '
    'RETURNING failures, window_start')


_PURGE = text('DELETE FROM app.adminloginthrottle WHERE window_start < now() - make_interval(secs => :age)')


def _reserve(connection, keys: dict[str, int], settings, now) -> int | None:
    """Lock every counter row of this attempt (address+email and address alone) for the whole attempt, in a
    fixed order (no deadlocks), so concurrent attempts are serialised and every failure is counted.
    Returns the Retry-After seconds when any bucket is blocked."""
    # Expired rows of other keys are dropped first, so the table cannot grow without bound.
    connection.execute(_PURGE, {'age': 2 * settings.login_window_seconds})
    wait = None
    for key in sorted(keys):
        row = connection.execute(_RESERVE, {'key': key, 'window': settings.login_window_seconds}).one()
        if row.failures >= keys[key]:
            remaining = settings.login_window_seconds - (now - row.window_start).total_seconds()
            wait = max(wait or 0, max(1, math.ceil(remaining)))
    return wait


@router.post('/auth/login', response_model=SessionCreated, dependencies=[Depends(require_origin)])
def admin_login(body: LoginRequest, request: Request, response: Response) -> SessionCreated:
    # Origin is a dependency so it is refused before the body is validated (403 before 422).
    settings, request_id = settings_of(request), request.state.request_id
    email = body.email.strip().lower()
    client = request.client.host if request.client else 'unknown'  # never a forwarded header
    key = security.throttle_key(settings.csrf_secret, client, email)
    client_key = security.throttle_key(settings.csrf_secret, client, '*')  # '*' is never a normalised email
    try:
        token, expires_at, allowed = _attempt(request, body, email, key, client_key, settings, request_id)
    except DBAPIError as error:
        if getattr(getattr(error, 'orig', None), 'sqlstate', None) == '55P03':  # lock_timeout on a busy key
            raise AdminError(429, 'rate_limited', headers={'Retry-After': '1'}) from None
        raise
    if not allowed:
        raise AdminError(401, 'login_failed')
    response.set_cookie(COOKIE, token, max_age=settings.session_ttl_seconds, path=settings.cookie_path,
                        secure=settings.cookie_secure, httponly=True, samesite='strict')
    return SessionCreated(session_expires_at=utc(expires_at))


def _attempt(request: Request, body: LoginRequest, email: str, key: str, client_key: str, settings,
             request_id: str):
    user = User.__table__
    token = expires_at = None
    with engine_of(request).begin() as connection:
        now = connection.scalar(select(func.now()))
        wait = _reserve(connection, {key: settings.login_max_failures, client_key: settings.login_ip_max_failures},
                        settings, now)
        if wait is not None:
            raise AdminError(429, 'rate_limited', headers={'Retry-After': str(wait)})
        row = connection.execute(
            select(user.c.id, user.c.password_hash, admingrant.c.active,
                   func.coalesce(accountcontrol.c.enabled, True).label('enabled'))
            .select_from(user.outerjoin(admingrant, admingrant.c.user_id == user.c.id)
                         .outerjoin(accountcontrol, accountcontrol.c.user_id == user.c.id))
            .where(func.lower(user.c.email) == email)).first()
        # The password is always verified (dummy hash for unknown users): same work either way.
        password_ok = verify_password(body.password, row.password_hash if row else security.DUMMY_PASSWORD_HASH)
        allowed = bool(row and password_ok and row.active is True and row.enabled is True)
        if not allowed:
            connection.execute(update(adminloginthrottle).where(adminloginthrottle.c.key_hash.in_((key, client_key)))
                               .values(failures=adminloginthrottle.c.failures + 1))
            admin_audit.record(connection, actor_user_id=None, actor_kind='anonymous', action='auth.login_failed',
                               outcome='failed', request_id=request_id)
        else:
            old = request.cookies.get(COOKIE)
            if old:  # one admin session per browser: logging in again replaces it
                connection.execute(update(adminsession).where(
                    and_(adminsession.c.token_hash == security.token_hash(old), adminsession.c.revoked_at.is_(None)))
                    .values(revoked_at=now))
            token, digest = security.new_session_token()
            expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
            connection.execute(insert(adminsession).values(id=str(uuid.uuid4()), token_hash=digest, user_id=row.id,
                                                           created_at=now, expires_at=expires_at))
            connection.execute(delete(adminloginthrottle).where(adminloginthrottle.c.key_hash == key))
            admin_audit.record(connection, actor_user_id=row.id, actor_kind='admin', action='auth.login',
                               outcome='succeeded', request_id=request_id)
    return token, expires_at, allowed


@router.get('/auth/me', response_model=AdminMe)
def admin_me(request: Request) -> AdminMe:
    context = current_admin(request)
    settings = settings_of(request)
    return AdminMe(user_id=context.user_id, email=context.email, role=context.role,
                   permissions=sorted(context.permissions), session_expires_at=utc(context.expires_at),
                   csrf_token=security.csrf_token(settings.csrf_secret, context.session_id, context.token_hash),
                   capabilities=capabilities(settings))


@router.post('/auth/logout', status_code=204)
def admin_logout(request: Request) -> Response:
    settings = settings_of(request)
    context: AdminContext = current_admin(request)  # expired/revoked: 401 and clear the cookie first
    require_origin(request)
    require_csrf(request, context)
    with engine_of(request).begin() as connection:
        connection.execute(update(adminsession).where(adminsession.c.id == context.session_id)
                           .values(revoked_at=func.now()))
        admin_audit.record(connection, actor_user_id=context.user_id, actor_kind='admin', action='auth.logout',
                           outcome='succeeded', request_id=request.state.request_id)
    return Response(status_code=204, headers={'Set-Cookie': clear_cookie_header(settings)})
