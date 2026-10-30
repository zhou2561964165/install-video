"""Admin membership controls. Local transactions only; payment facts are never rewritten."""
from datetime import datetime, timezone
import hashlib
import json
import re
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import and_, func, select as sa_select
from sqlmodel import select

from ..admin.errors import AdminError
from ..admin.schemas import utc
from ..models import Membership, MembershipControl, MembershipControlOperation, User
from ..models_admin import accountcontrol, admingrant, adminsession
from . import admin_audit
from .admin_queries import membership_projection
from .db_transactions import CommitResolution, ResolutionState, lock_user, run_local_transaction


def validate_deadline(mode, deadline, now):
    if deadline is not None and (mode != 'enabled' or deadline <= now):
        raise AdminError(422, 'validation_failed', field_errors=[
            {'field': 'expires_at', 'message': '指定到期时间必须晚于本次操作时间'}])
    return deadline


def _authorize(session, context):
    """Re-read the grant and session inside each transaction attempt, including replays."""
    actor = session.execute(sa_select(adminsession.c.id).select_from(
        adminsession.join(admingrant, admingrant.c.user_id == adminsession.c.user_id)
        .outerjoin(accountcontrol, accountcontrol.c.user_id == adminsession.c.user_id)).where(
            adminsession.c.id == context.session_id, adminsession.c.token_hash == context.token_hash,
            adminsession.c.user_id == context.user_id, adminsession.c.revoked_at.is_(None),
            adminsession.c.expires_at > func.now(), admingrant.c.active.is_(True),
            admingrant.c.role == 'admin', func.coalesce(accountcontrol.c.enabled, True).is_(True))).first()
    if actor is None:
        raise AdminError(403, 'forbidden')


def _result(operation, *, user_id, actor_user_id, digest):
    if (operation.user_id, operation.actor_user_id, operation.request_sha256) != (user_id, actor_user_id, digest):
        raise AdminError(409, 'idempotency_conflict')
    return json.loads(operation.result_json)


def set_membership(engine, user_id, body, *, context, request_id, idempotency_key, settings):
    if not isinstance(idempotency_key, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{16,128}', idempotency_key):
        raise AdminError(422, 'idempotency_key_required')
    if not settings.reason_min_length <= len(body.reason) <= settings.reason_max_length:
        raise AdminError(422, 'validation_failed')
    canonical = json.dumps({'operation': 'users.membership', 'method': 'PATCH',
                            'path': f'/users/{user_id}/membership', 'target': user_id, 'actor': context.user_id,
                            **body.model_dump()}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(canonical.encode('utf8')).hexdigest()

    def action(session):
        _authorize(session, context)
        lock_user(session, user_id)
        # The user lock serializes first-row initialization and same-user writes.
        account = session.exec(select(Membership).where(Membership.user_id == user_id).with_for_update()
                               .execution_options(populate_existing=True)).first()
        control = session.exec(select(MembershipControl).where(MembershipControl.user_id == user_id)
                               .with_for_update().execution_options(populate_existing=True)).first()
        operation = session.get(MembershipControlOperation, idempotency_key)
        if operation is not None:
            return _result(operation, user_id=user_id, actor_user_id=context.user_id, digest=digest)
        now = session.exec(select(func.clock_timestamp())).one().astimezone(timezone.utc)
        revision = control.revision if control else 0
        if revision != int(body.expected_revision):
            raise AdminError(409, 'revision_conflict')
        deadline = datetime.fromisoformat(body.expires_at.replace('Z', '+00:00')) if body.expires_at else None
        validate_deadline(body.mode, deadline, now)
        before_mode, before_deadline = (control.mode, control.expires_at) if control else ('auto', None)
        changed = (before_mode, before_deadline) != (body.mode, deadline)
        if account is None:
            account = Membership(user_id=user_id)
            session.add(account)
        if changed:
            if revision >= 9223372036854775807 or account.revision >= 2147483647:
                raise AdminError(409, 'revision_conflict')
            if control is None:
                control = MembershipControl(user_id=user_id, mode=body.mode, expires_at=deadline,
                    revision=revision + 1, updated_at=now, actor_user_id=context.user_id)
            else:
                control.mode, control.expires_at, control.revision = body.mode, deadline, revision + 1
                control.updated_at, control.actor_user_id = now, context.user_id
            session.add(control)
            # Payment fields remain facts. This version fences in-flight payment/download snapshots (ABA).
            account.revision += 1
            session.add(account)
        session.flush()
        changes = {'control_mode_before': before_mode, 'control_mode_after': body.mode,
                   'control_expires_at_before': utc(before_deadline), 'control_expires_at_after': utc(deadline),
                   'control_revision_before': str(revision),
                   'control_revision_after': str(control.revision if control else revision)}
        audit_id = admin_audit.record(session.connection(), actor_user_id=context.user_id, actor_kind='admin',
            action='users.membership', outcome='succeeded', request_id=request_id, target_user_id=user_id,
            reason=body.reason, changes=changes)
        row = SimpleNamespace(m_status=account.status, m_expires_at=account.expires_at, m_revision=account.revision,
            m_source=account.entitlement_source, m_cancel=account.cancel_at_period_end,
            mc_mode=control.mode if control else 'auto', mc_revision=control.revision if control else 0,
            mc_expires_at=control.expires_at if control else None)
        projected = membership_projection(row, user_id, now)
        for name in ('expires_at', 'control_expires_at', 'effective_expires_at'):
            projected[name] = utc(projected[name])
        result = {'membership': projected, 'changed': changed, 'audit_id': audit_id, 'as_of': utc(now)}
        session.add(MembershipControlOperation(idempotency_key=idempotency_key, request_sha256=digest,
            user_id=user_id, actor_user_id=context.user_id, result_json=json.dumps(result, ensure_ascii=False),
            audit_id=audit_id, created_at=now))
        session.flush()
        return result

    def resolve_unknown(session, _key):
        _authorize(session, context)
        operation = session.get(MembershipControlOperation, idempotency_key)
        if operation is None:
            return CommitResolution(ResolutionState.UNKNOWN)
        return CommitResolution(ResolutionState.COMMITTED,
                                _result(operation, user_id=user_id, actor_user_id=context.user_id, digest=digest))

    try:
        return run_local_transaction(engine, idempotency_key, action, resolve_unknown)
    except HTTPException as error:
        code = error.detail.get('error_type') if isinstance(error.detail, dict) else 'database_unavailable'
        if code == 'database_conflict':
            # A duplicate key raced across different target users: reject rather than dispatching another write.
            code = 'idempotency_conflict'
        if code == 'user_not_found':
            code = 'not_found'
        raise AdminError(error.status_code, code) from None
