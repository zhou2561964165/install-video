"""User-side customer support: eligible orders, ticket submission and the user's own ticket list.

One ticket is one question and one answer. Priority is a snapshot at submission: an effective member,
or a "membership not credited" complaint (the user has paid), gets 'priority'. Notes are plain text.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..config import settings
from ..models import BillingCheckout
from ..models_support import SupportTicket
from . import support_catalog as catalog
from .membership import is_vip

ELIGIBLE_DAYS = 90


def _error(status: int, error_type: str, message: str) -> HTTPException:
    return HTTPException(status, detail={'error_type': error_type, 'error': message})


def _utc(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value, tz=timezone.utc)
    elif value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _eligible_query(user_id: str, now: datetime):
    since = (now - timedelta(days=ELIGIBLE_DAYS)).timestamp()
    return select(BillingCheckout).where(
        BillingCheckout.user_id == user_id, BillingCheckout.fulfilled.is_(False), BillingCheckout.state != 'failed',
        BillingCheckout.mode == 'payment', BillingCheckout.created_at >= since)


def eligible_checkouts(session: Session, user_id: str, now: datetime) -> list[dict]:
    rows = session.exec(_eligible_query(user_id, now).order_by(BillingCheckout.created_at.desc())).all()
    return [{'checkout_id': row.id, 'label': row.id[-8:], 'created_at': _utc(row.created_at), 'state': row.state}
            for row in rows]


def _has_open_ticket(session: Session, checkout_id: str) -> bool:
    return session.exec(select(SupportTicket.id).where(
        SupportTicket.checkout_id == checkout_id, SupportTicket.state == 'open')).first() is not None


def create_ticket(session: Session, user_id: str, category: str, note: str | None, checkout_id: str | None,
                  now: datetime) -> SupportTicket:
    if category not in catalog.CATEGORIES:
        raise _error(422, 'invalid_category', '请选择有效的问题类型')
    note = (note or '').strip() or None
    checkout_id = checkout_id or None
    if note is not None and len(note) > catalog.NOTE_MAX:
        raise _error(422, 'note_too_long', f'补充说明最多 {catalog.NOTE_MAX} 字')
    if category == 'membership_not_credited':
        if not checkout_id:
            raise _error(422, 'checkout_required', '请选择未到账的那笔订单')
        if session.exec(_eligible_query(user_id, now).where(BillingCheckout.id == checkout_id)).first() is None:
            raise _error(422, 'checkout_not_eligible', '所选订单不可申诉，请重新选择')  # also for others' / unknown ids
        if _has_open_ticket(session, checkout_id):
            raise _error(422, 'ticket_exists', '这笔订单已有处理中的工单')
    elif checkout_id:
        raise _error(422, 'checkout_not_allowed', '该问题类型无需选择订单')
    hour_ago = now - timedelta(hours=1)
    recent = session.exec(select(func.count()).select_from(SupportTicket).where(
        SupportTicket.user_id == user_id, SupportTicket.created_at >= hour_ago)).one()
    if recent >= settings.support_submit_per_hour:
        raise _error(429, 'rate_limited', '提交过于频繁，请稍后再试')
    open_count = session.exec(select(func.count()).select_from(SupportTicket).where(
        SupportTicket.user_id == user_id, SupportTicket.state == 'open')).one()
    if open_count >= settings.support_max_open_tickets:
        raise _error(422, 'too_many_open', '处理中的工单过多，请等待处理后再提交')
    priority = 'priority' if category == 'membership_not_credited' or is_vip(session, user_id) else 'normal'
    ticket = SupportTicket(id=str(uuid.uuid4()), user_id=user_id, category=category, user_note=note,
                           checkout_id=checkout_id, priority=priority, state='open', created_at=now, revision=0)
    session.add(ticket)
    try:
        session.commit()
    except IntegrityError:  # a concurrent appeal for the same order won the open-ticket unique index
        session.rollback()
        raise _error(422, 'ticket_exists', '这笔订单已有处理中的工单')
    session.refresh(ticket)
    return ticket


def reply_text(session: Session, ticket: SupportTicket) -> str | None:
    if not ticket.reply_template:
        return None
    values = {}
    if ticket.reply_template == 'reissued' and ticket.checkout_id:
        checkout = session.get(BillingCheckout, ticket.checkout_id)
        values['days'] = checkout.duration_days if checkout else 30
    return catalog.render(ticket.reply_template, **values)


def list_tickets(session: Session, user_id: str) -> list[dict]:
    rows = session.exec(select(SupportTicket).where(SupportTicket.user_id == user_id)
                        .order_by(SupportTicket.created_at.desc(), SupportTicket.id)).all()
    return [{'id': row.id, 'category': row.category, 'category_label': catalog.CATEGORIES[row.category],
             'state': row.state, 'resolution': row.resolution, 'reply_text': reply_text(session, row),
             'reply_note': row.reply_note, 'user_note': row.user_note, 'checkout_label': (row.checkout_id or '')[-8:] or None,
             'created_at': _utc(row.created_at), 'resolved_at': _utc(row.resolved_at)} for row in rows]
