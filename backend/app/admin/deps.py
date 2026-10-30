"""Admin request dependencies: live session check, role→permission map, permission/Origin/CSRF guards.

Every request re-reads the session, the AdminGrant and the account state (no caching): a revoked
grant, a disabled account or an expired session ends access on the very next request.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Request
from sqlalchemy import and_, func, select

from ..models import User
from ..models_admin import accountcontrol, admingrant, adminsession
from . import security
from .config import AdminSettings
from .errors import AdminError

COOKIE = 'iv_admin_session'
READ_PERMISSIONS = frozenset({'overview:read', 'users:read', 'memberships:read', 'jobs:read', 'billing:read',
                              'audit:read', 'system:read'})
# Initial seed roles (integration plan §5). users:access:write stays unusable while its capability is not ready.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    'admin': READ_PERMISSIONS | {'users:access:write', 'support:read', 'support:write', 'support:reissue', 'memberships:write'},
    'viewer': READ_PERMISSIONS | {'support:read'},
}
# A permission whose capability is not ready is not granted at all (integration plan §5: "M2 ready 后").
GATED_PERMISSIONS = {'users:access:write': 'account_access_write', 'support:reissue': 'support_reissue',
                     'memberships:write': 'membership_control_write'}


def ready_capabilities(settings: AdminSettings) -> frozenset[str]:
    """account_access_write (M2) and billing_amounts stay closed; support_reissue needs the Stripe read key."""
    return frozenset({'membership_control_write'} | ({'support_reissue'} if settings.stripe_read_key else set()))


def effective_permissions(role: str, ready: frozenset[str] = frozenset()) -> frozenset[str]:
    granted = ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(name for name in granted if name not in GATED_PERMISSIONS or GATED_PERMISSIONS[name] in ready)


@dataclass(frozen=True)
class AdminContext:
    user_id: str
    email: str
    role: str
    permissions: frozenset[str]
    session_id: str
    token_hash: str
    expires_at: datetime


def settings_of(request: Request) -> AdminSettings:
    return request.app.state.settings


def engine_of(request: Request):
    return request.app.state.engine


def clear_cookie_header(settings: AdminSettings) -> str:
    secure = '; Secure' if settings.cookie_secure else ''
    return (f'{COOKIE}=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path={settings.cookie_path}'
            f'; HttpOnly{secure}; SameSite=strict')


def unauthenticated(settings: AdminSettings) -> AdminError:
    return AdminError(401, 'unauthenticated', headers={'Set-Cookie': clear_cookie_header(settings)})


def live_session(connection, token: str):
    """The session row joined with its live grant/account/user, or None."""
    user = User.__table__
    return connection.execute(
        select(adminsession.c.id, adminsession.c.token_hash, adminsession.c.expires_at, user.c.id.label('user_id'),
               user.c.email, admingrant.c.role)
        .select_from(adminsession.join(user, user.c.id == adminsession.c.user_id)
                     .join(admingrant, and_(admingrant.c.user_id == user.c.id, admingrant.c.active.is_(True)))
                     .outerjoin(accountcontrol, accountcontrol.c.user_id == user.c.id))
        .where(adminsession.c.token_hash == security.token_hash(token), adminsession.c.revoked_at.is_(None),
               adminsession.c.expires_at > func.now(), func.coalesce(accountcontrol.c.enabled, True).is_(True))
    ).first()


def current_admin(request: Request) -> AdminContext:
    settings = settings_of(request)
    token = request.cookies.get(COOKIE)
    if not token:
        raise unauthenticated(settings)
    with engine_of(request).connect() as connection:
        row = live_session(connection, token)
    if row is None:
        raise unauthenticated(settings)
    return AdminContext(user_id=row.user_id, email=row.email, role=row.role,
                        permissions=effective_permissions(row.role, ready_capabilities(settings)), session_id=row.id,
                        token_hash=row.token_hash, expires_at=row.expires_at)


def require_permission(name: str):
    def check(request: Request) -> AdminContext:
        context = current_admin(request)
        if name not in context.permissions:
            raise AdminError(403, 'forbidden')
        return context
    return check


def require_origin(request: Request) -> None:
    """Login and every write method: exact Origin allowlist; an empty allowlist refuses all writes."""
    if not security.origin_allowed(request.headers.get('origin'), settings_of(request).allowed_origins):
        raise AdminError(403, 'origin_rejected')


def require_csrf(request: Request, context: AdminContext) -> None:
    settings = settings_of(request)
    if not security.csrf_valid(settings.csrf_secret, context.session_id, context.token_hash,
                               request.headers.get('x-csrf-token')):
        raise AdminError(403, 'csrf_rejected')
