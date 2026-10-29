"""Append-only admin audit writes, shared by the admin app and the operator CLI.

Never records passwords, tokens, cookies, CSRF values, raw IPs or emails; `changes` is a small
allowlisted mapping chosen by the caller.
"""
from __future__ import annotations

import uuid

from sqlalchemy import insert
from sqlalchemy.engine import Connection

from ..models_admin import adminaudit

ACTOR_KINDS = frozenset({'admin', 'cli', 'system', 'anonymous'})
OUTCOMES = frozenset({'succeeded', 'failed', 'denied'})


def record(connection: Connection, *, actor_user_id: str | None, actor_kind: str, action: str, outcome: str,
           request_id: str, target_user_id: str | None = None, reason: str | None = None,
           changes: dict | None = None) -> str:
    if actor_kind not in ACTOR_KINDS or outcome not in OUTCOMES:
        raise ValueError('invalid audit classification')
    event_id = str(uuid.uuid4())
    connection.execute(insert(adminaudit).values(
        event_id=event_id, actor_user_id=actor_user_id, actor_kind=actor_kind, action=action, outcome=outcome,
        request_id=request_id, target_user_id=target_user_id, reason=reason, changes=changes))
    return event_id
