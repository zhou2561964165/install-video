"""Admin security primitives: opaque session tokens, deterministic CSRF, Origin allowlist, throttle keys.

CSRF = HMAC-SHA256(ADMIN_CSRF_SECRET, session_id + token_hash + fixed version context): stable for the
session (GET never rotates it), valid across tabs, compared in constant time, never stored or logged.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from ..services.auth import hash_password

_CSRF_CONTEXT = b'iv-admin-csrf-v1'
_THROTTLE_CONTEXT = b'iv-admin-login-throttle-v1'
# Verified for unknown emails too, so a login answers in the same time whether the user exists.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def csrf_token(secret: bytes, session_id: str, token_hash_hex: str) -> str:
    message = b'\x00'.join((_CSRF_CONTEXT, session_id.encode('utf-8'), token_hash_hex.encode('ascii')))
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def csrf_valid(secret: bytes, session_id: str, token_hash_hex: str, presented: str | None) -> bool:
    if not presented or not presented.isascii():  # non-ASCII header bytes are simply not a valid token
        return False
    return hmac.compare_digest(csrf_token(secret, session_id, token_hash_hex), presented)


def origin_allowed(origin: str | None, allowed: tuple[str, ...]) -> bool:
    return bool(origin) and origin in allowed


def throttle_key(secret: bytes, client: str, email: str) -> str:
    message = b'\x00'.join((_THROTTLE_CONTEXT, client.encode('utf-8'), email.strip().lower().encode('utf-8')))
    return hmac.new(secret, message, hashlib.sha256).hexdigest()
