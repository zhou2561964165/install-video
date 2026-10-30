"""One entitlement rule for request checks and SQL projections; no I/O or configuration."""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, case, func, or_


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Entitlement:
    effective: bool
    reason: str
    expires_at: datetime | None
    permanent: bool = False


def resolve(payment, control, as_of: datetime) -> Entitlement:
    now = utc(as_of)
    mode = control.mode if control is not None else 'auto'
    if mode == 'disabled':
        return Entitlement(False, 'admin_disabled', None)
    if mode == 'enabled':
        deadline = utc(control.expires_at) if control.expires_at is not None else None
        effective = deadline is None or deadline > now
        return Entitlement(effective, 'admin_enabled' if effective else 'admin_expired', deadline, deadline is None)
    deadline = (datetime.fromtimestamp(payment.expires_at, timezone.utc)
                if payment is not None and payment.expires_at and payment.expires_at > 0 else None)
    if payment is None or payment.status != 'active':
        return Entitlement(False, 'payment_inactive', deadline)
    effective = deadline is not None and deadline > now
    return Entitlement(effective, 'payment_active' if effective else 'payment_expired', deadline)


def effective_sql(as_of: datetime, payment, control):
    """Use with a LEFT JOIN from users to payment and control; never requires a payment row."""
    return func.coalesce(case(
        (control.c.mode == 'disabled', False),
        (control.c.mode == 'enabled', or_(control.c.expires_at.is_(None), control.c.expires_at > as_of)),
        else_=and_(payment.c.status == 'active', payment.c.expires_at > as_of.timestamp())), False)
