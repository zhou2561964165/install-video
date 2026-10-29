"""Admin settings: read once from the environment, range-checked against the contract policies.

Missing security configuration does not stop the process; it makes the admin app answer 503
admin_unavailable (contract) — see unavailable_reason(). Out-of-range values are a startup error.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re

MIN_SECRET_BYTES = 32
_ORIGIN = re.compile(r'https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?\Z')
_LOOPBACK = re.compile(r'http://(127\.0\.0\.1|localhost)(:[0-9]{1,5})?\Z')


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _optional_bool(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None or value == '':
        return None
    if value not in ('true', 'false'):
        raise ValueError(f'{name} must be true or false')
    return value == 'true'


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if not value:
        return default
    if value not in ('true', 'false'):
        raise ValueError(f'{name} must be true or false')
    return value == 'true'


@dataclass(frozen=True)
class AdminSettings:
    api_base: str = '/api/admin/v1'
    cookie_path: str | None = None
    cookie_secure: bool = True
    allowed_origins: tuple[str, ...] = ()
    csrf_secret: bytes | None = None
    session_ttl_seconds: int = 900
    default_page_size: int = 20
    max_page_size: int = 100
    reason_min_length: int = 10
    reason_max_length: int = 500
    refresh_interval_seconds: int = 0
    idempotency_replay_retention_seconds: int = 2592000
    login_max_failures: int = 5
    login_window_seconds: int = 900
    login_ip_max_failures: int = 20  # failures per client address per window, across all emails
    display_timezone: str = 'Asia/Shanghai'
    # Support re-issue: restricted read-only Stripe key (never the main secret), deployment mode, freshness.
    stripe_read_key: str | None = None
    stripe_livemode: bool | None = None
    stripe_timeout_seconds: float = 10.0
    verify_fresh_seconds: int = 900
    verify_max_attempts: int = 5

    def __post_init__(self):
        if not 300 <= self.session_ttl_seconds <= 3600:
            raise ValueError('ADMIN_SESSION_TTL_SECONDS must be 300..3600')
        if not 1 <= self.default_page_size <= self.max_page_size <= 1000:
            raise ValueError('page sizes must satisfy 1 <= default <= max <= 1000')
        if not (self.refresh_interval_seconds == 0 or 15 <= self.refresh_interval_seconds <= 300):
            raise ValueError('ADMIN_REFRESH_INTERVAL_SECONDS must be 0 or 15..300')
        if not 10 <= self.reason_min_length <= self.reason_max_length <= 2000:
            raise ValueError('reason lengths must satisfy 10 <= min <= max <= 2000')
        if self.idempotency_replay_retention_seconds < 604800:
            raise ValueError('idempotency retention must be at least 7 days')
        if not 60 <= self.verify_fresh_seconds <= 3600 or not 1 <= self.verify_max_attempts <= 20:
            raise ValueError('support verification limits out of range')
        if self.stripe_read_key is not None:
            # only a restricted read key, never the main secret key; its mode must match the deployment
            if not self.stripe_read_key.startswith(('rk_test_', 'rk_live_')):
                raise ValueError('ADMIN_STRIPE_READ_KEY must be a restricted key (rk_test_/rk_live_)')
            # Without a declared deployment mode every verification would fail as livemode_mismatch.
            if self.stripe_livemode is None:
                raise ValueError('ADMIN_STRIPE_READ_KEY requires STRIPE_LIVEMODE=true|false')
            if self.stripe_read_key.startswith('rk_live_') != self.stripe_livemode:
                raise ValueError('ADMIN_STRIPE_READ_KEY mode does not match STRIPE_LIVEMODE')
        if self.login_max_failures < 1 or self.login_window_seconds < 1 or self.login_ip_max_failures < 1:
            raise ValueError('login throttle values must be positive')
        if any(not _ORIGIN.match(origin) for origin in self.allowed_origins):
            raise ValueError('ADMIN_ALLOWED_ORIGINS entries must be exact origins (scheme://host[:port])')
        if not self.cookie_secure and any(not _LOOPBACK.match(origin) for origin in self.allowed_origins):
            raise ValueError('ADMIN_COOKIE_SECURE=false is only for loopback http development origins')

    @classmethod
    def from_env(cls) -> 'AdminSettings':
        secret = os.environ.get('ADMIN_CSRF_SECRET')
        origins = tuple(item.strip() for item in os.environ.get('ADMIN_ALLOWED_ORIGINS', '').split(',') if item.strip())
        return cls(
            api_base=os.environ.get('ADMIN_API_BASE') or '/api/admin/v1',
            cookie_path=os.environ.get('ADMIN_COOKIE_PATH') or None,
            cookie_secure=_bool('ADMIN_COOKIE_SECURE', True),
            allowed_origins=origins,
            csrf_secret=secret.encode('utf-8') if secret else None,
            session_ttl_seconds=_int('ADMIN_SESSION_TTL_SECONDS', 900),
            default_page_size=_int('ADMIN_PAGE_SIZE_DEFAULT', 20),
            max_page_size=_int('ADMIN_PAGE_SIZE_MAX', 100),
            refresh_interval_seconds=_int('ADMIN_REFRESH_INTERVAL_SECONDS', 0),
            display_timezone=os.environ.get('ADMIN_DISPLAY_TIMEZONE') or 'Asia/Shanghai',
            stripe_read_key=os.environ.get('ADMIN_STRIPE_READ_KEY') or None,
            stripe_livemode=_optional_bool('STRIPE_LIVEMODE'),
            verify_fresh_seconds=_int('SUPPORT_VERIFY_FRESH_SECONDS', 900),
        )

    def unavailable_reason(self) -> str | None:
        """Why the admin app must answer 503 admin_unavailable, or None when it may serve."""
        if not self.cookie_path or not self.cookie_path.rstrip('/').endswith(self.api_base.rstrip('/')):
            return 'cookie_path_unconfigured'
        if self.csrf_secret is None or len(self.csrf_secret) < MIN_SECRET_BYTES:
            return 'csrf_secret_unconfigured'
        return None
