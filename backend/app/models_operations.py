"""Durable submission/admission facts. Services own transactions and transitions."""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class DownloadOperation(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint("state IN ('resolving','accepted_server','direct_ready','succeeded','failed','needs_review')", name='state'),
        CheckConstraint('membership_revision >= 0 AND (max_height IS NULL OR max_height > 0)', name='access_snapshot'),
        CheckConstraint('resolve_epoch >= 0 AND resolve_attempts_used >= 0 AND resolve_attempts_used <= resolve_attempts_limit AND resolve_attempts_limit > 0', name='resolve_budget'),
        CheckConstraint('budget_version > 0 AND length(budget_checkpoint_json) > 0', name='budget_checkpoint'),
        CheckConstraint('(resolve_owner IS NULL) = (resolve_lease_deadline IS NULL)', name='resolve_lease_pair'),
        CheckConstraint('deadline_at >= accepted_at', name='deadline'),
        CheckConstraint('resolve_deadline_at >= accepted_at AND resolve_deadline_at <= deadline_at', name='resolve_deadline'),
        CheckConstraint('budget_checkpoint_at >= accepted_at', name='checkpoint_time'),
        UniqueConstraint('job_id', name='uq_downloadoperation_job_id'),
        Index('ix_downloadoperation_user_id_accepted_at', 'user_id', 'accepted_at'),
        Index('ix_downloadoperation_state_lease', 'state', 'resolve_lease_deadline'),
        Index('ix_downloadoperation_job_id_tombstone', 'job_id_tombstone'),  # C5b: 410 for purged Jobs
    )
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key='user.id', ondelete='RESTRICT')
    canonical_payload: str = Field(sa_type=Text)
    fingerprint: str = Field(max_length=64)
    canonical_format_id: str
    max_height: Optional[int] = None
    membership_revision: int = Field(sa_type=BigInteger)
    quota_day: date = Field(sa_type=Date)
    state: str
    job_id: Optional[str] = Field(default=None, foreign_key='job.id', ondelete='RESTRICT')
    job_id_tombstone: Optional[str] = None
    accepted_at: datetime = Field(sa_type=DateTime(timezone=True))
    deadline_at: datetime = Field(sa_type=DateTime(timezone=True))
    resolve_deadline_at: datetime = Field(sa_type=DateTime(timezone=True))
    completed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    capacity_reserved: bool = False
    resolve_owner: Optional[str] = None
    resolve_epoch: int = Field(default=0, sa_type=BigInteger)
    resolve_lease_deadline: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    resolve_attempts_used: int = Field(default=0, sa_type=BigInteger)
    resolve_attempts_limit: int = Field(sa_type=BigInteger)
    resolve_attempt_deadline: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    budget_version: int
    budget_checkpoint_json: str = Field(sa_type=Text)
    budget_checkpoint_at: datetime = Field(sa_type=DateTime(timezone=True))
    error_code: Optional[str] = None


class QuotaCharge(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint('delta = 1', name='delta_one'),
        Index('ix_quotacharge_user_id_quota_day', 'user_id', 'quota_day'),
    )
    operation_id: str = Field(primary_key=True, foreign_key='downloadoperation.id', ondelete='RESTRICT')
    user_id: str = Field(foreign_key='user.id', ondelete='RESTRICT')
    quota_day: date = Field(sa_type=Date)
    delta: int = Field(default=1, sa_type=BigInteger)
    charged_at: datetime = Field(sa_type=DateTime(timezone=True))


class ResourceCounter(SQLModel, table=True):
    __table_args__ = (CheckConstraint('used >= 0', name='used_nonnegative'),)
    resource: str = Field(primary_key=True)
    scope: str = Field(primary_key=True)
    used: int = Field(default=0, sa_type=BigInteger)


class ResourceReservation(SQLModel, table=True):
    __table_args__ = (
        ForeignKeyConstraint(['resource', 'scope'], ['resourcecounter.resource', 'resourcecounter.scope'],
                             name='fk_resourcereservation_counter', ondelete='RESTRICT'),
        CheckConstraint('units > 0', name='units_positive'),
        CheckConstraint('(released = false AND released_at IS NULL) OR (released = true AND released_at IS NOT NULL)', name='release_state'),
        Index('ix_resourcereservation_counter_released', 'resource', 'scope', 'released'),
    )
    operation_id: str = Field(primary_key=True, foreign_key='downloadoperation.id', ondelete='RESTRICT')
    resource: str = Field(primary_key=True)
    scope: str = Field(primary_key=True)
    units: int = Field(sa_type=BigInteger)
    released: bool = False
    reserved_at: datetime = Field(sa_type=DateTime(timezone=True))
    released_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
