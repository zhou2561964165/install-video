"""Independent admin entitlement overrides and durable write receipts (mc_0016)."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Text
from sqlmodel import Field, SQLModel
from .models_admin import adminaudit


class MembershipControl(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint("mode IN ('auto','enabled','disabled')", name='mode'),
        CheckConstraint("mode = 'enabled' OR expires_at IS NULL", name='expires_mode'),
        CheckConstraint('revision >= 1', name='revision'),
    )
    user_id: str = Field(primary_key=True, foreign_key='user.id', ondelete='RESTRICT')
    mode: str
    expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    revision: int = Field(sa_type=BigInteger)
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))
    actor_user_id: str = Field(foreign_key='user.id', ondelete='RESTRICT')


class MembershipControlOperation(SQLModel, table=True):
    __table_args__ = (CheckConstraint('length(request_sha256) = 64', name='request_sha256'),
                      ForeignKeyConstraint(['audit_id'], [adminaudit.c.event_id],
                                           name='fk_membershipcontroloperation_audit_id_adminaudit', ondelete='RESTRICT'))
    # Globally unique within this operation type; other admin writes have separate tables.
    idempotency_key: str = Field(primary_key=True, max_length=128)
    request_sha256: str = Field(max_length=64)
    user_id: str = Field(foreign_key='user.id', ondelete='RESTRICT')
    actor_user_id: str = Field(foreign_key='user.id', ondelete='RESTRICT')
    result_json: str = Field(sa_type=Text)
    audit_id: str = Field(max_length=64)
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
