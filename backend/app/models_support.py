"""Customer support tickets and the reviewed membership re-issue (see t1_0015 and the support design).

Business tables (SQLite in development, PostgreSQL in production). One ticket is one question and one
answer. membershipreissue is the once-per-checkout anchor of a re-issue; supportpaymentcheck records each
"verify with the payment provider" result (no provider payload is stored).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, text
from sqlmodel import Field, SQLModel

CATEGORY_CHECK = "category IN ('membership_not_credited','download_failing','login_problem','other')"


class SupportTicket(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint(CATEGORY_CHECK, name='category'),
        CheckConstraint("priority IN ('priority','normal')", name='priority'),
        CheckConstraint("state IN ('open','resolved','rejected')", name='state'),
        CheckConstraint("resolution IS NULL OR resolution IN ('reissued','replied','rejected')", name='resolution'),
        CheckConstraint("(category = 'membership_not_credited') = (checkout_id IS NOT NULL)", name='checkout'),
        CheckConstraint("(state = 'open') = (resolved_at IS NULL)", name='resolved'),
        CheckConstraint("user_note IS NULL OR length(user_note) <= 2000", name='user_note'),
        CheckConstraint("reply_note IS NULL OR length(reply_note) <= 2000", name='reply_note'),
        Index('uq_supportticket_open_checkout', 'checkout_id', unique=True,
              postgresql_where=text("state = 'open' AND category = 'membership_not_credited'"),
              sqlite_where=text("state = 'open' AND category = 'membership_not_credited'")),
        Index('ix_supportticket_queue', 'state', 'priority', 'created_at'),
        Index('ix_supportticket_user', 'user_id', 'created_at'),
    )
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key='user.id', ondelete='RESTRICT')
    category: str
    user_note: Optional[str] = None
    checkout_id: Optional[str] = Field(default=None, foreign_key='billingcheckout.id', ondelete='RESTRICT')
    priority: str
    state: str
    resolution: Optional[str] = None
    reply_template: Optional[str] = None
    reply_note: Optional[str] = None
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    resolved_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    resolved_by: Optional[str] = None
    revision: int = Field(default=0, sa_type=BigInteger)


class SupportPaymentCheck(SQLModel, table=True):
    __table_args__ = (Index('ix_supportpaymentcheck_checkout', 'checkout_id', 'checked_at'),)
    id: str = Field(primary_key=True)
    ticket_id: str = Field(foreign_key='supportticket.id', ondelete='RESTRICT')
    checkout_id: str = Field(foreign_key='billingcheckout.id', ondelete='RESTRICT')
    payment_intent: Optional[str] = None
    result: str
    checked_at: datetime = Field(sa_type=DateTime(timezone=True))
    actor_user_id: str


class MembershipReissue(SQLModel, table=True):
    __table_args__ = (CheckConstraint('granted_days >= 1', name='granted_days'),)
    checkout_id: str = Field(primary_key=True, foreign_key='billingcheckout.id', ondelete='RESTRICT')
    ticket_id: str = Field(foreign_key='supportticket.id', ondelete='RESTRICT')
    actor_user_id: str
    payment_intent: str
    granted_days: int
    expires_before: float
    expires_after: float
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    idempotency_key: str = Field(max_length=128)
