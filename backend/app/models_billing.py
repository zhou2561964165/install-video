"""Inbox and authority snapshots. JSON is canonical TEXT, replaced as a whole."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel


class BillingInbox(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint('provider_account_scope', 'livemode', 'event_id', name='uq_billinginbox_scope_event'),
        CheckConstraint("status IN ('received','processing','retry_wait','waiting_binding','applied','ignored','needs_review')", name='status'),
        CheckConstraint('attempt_count >= 0 AND attempt_limit > 0 AND attempt_count <= attempt_limit AND lease_epoch >= 0', name='budget'),
        CheckConstraint('canonical_version > 0', name='canonical_version'),
        CheckConstraint('(lease_owner IS NULL) = (lease_deadline IS NULL)', name='lease_pair'),
        CheckConstraint("status <> 'processing' OR lease_owner IS NOT NULL", name='processing_lease'),
        CheckConstraint('budget_deadline >= received_at', name='budget_deadline'),
        Index('ix_billinginbox_status_next_run', 'status', 'next_run_at'),
        Index('ix_billinginbox_status_lease', 'status', 'lease_deadline'),
    )
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    provider_account_scope: str
    livemode: bool
    event_id: str
    event_type: str
    api_version: Optional[str] = None
    received_at: datetime = Field(sa_type=DateTime(timezone=True))
    payload_sha256: str = Field(max_length=64)
    canonical_sha256: str = Field(max_length=64)
    canonical_version: int
    canonical_payload: str = Field(sa_type=Text)
    business_payload: Optional[str] = Field(default=None, sa_type=Text)
    status: str = 'received'
    attempt_count: int = Field(default=0, sa_type=BigInteger)
    attempt_limit: int = Field(sa_type=BigInteger)
    budget_deadline: datetime = Field(sa_type=DateTime(timezone=True))
    next_run_at: datetime = Field(sa_type=DateTime(timezone=True))
    lease_owner: Optional[str] = None
    lease_epoch: int = Field(default=0, sa_type=BigInteger)
    lease_deadline: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    error_code: Optional[str] = None
    outcome_reason: Optional[str] = None
    completed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    payload_purged_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))


class BillingFact(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint('inbox_id', name='uq_billingfact_inbox_id'),
        CheckConstraint('amount_total IS NULL OR amount_total >= 0', name='amount_total'),
        CheckConstraint('amount_refunded IS NULL OR amount_refunded >= 0', name='amount_refunded'),
        CheckConstraint("reconciliation IN ('unknown','verified','needs_review')", name='reconciliation'),
        CheckConstraint('(provider_account_scope = \'legacy_unknown\' AND livemode IS NULL) OR (provider_account_scope <> \'legacy_unknown\' AND livemode IS NOT NULL)', name='scope_mode'),
        Index('ix_billingfact_scope_pi', 'provider_account_scope', 'livemode', 'payment_intent'),
        Index('ix_billingfact_checkout_id', 'checkout_id'),
    )
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    inbox_id: Optional[str] = Field(default=None, foreign_key='billinginbox.id', ondelete='RESTRICT')
    user_id: Optional[str] = Field(default=None, foreign_key='user.id', ondelete='RESTRICT')
    checkout_id: Optional[str] = Field(default=None, foreign_key='billingcheckout.id', ondelete='RESTRICT')
    provider_account_scope: str = 'legacy_unknown'
    livemode: Optional[bool] = None
    event_id: Optional[str] = None
    payment_intent: Optional[str] = None
    session_id: Optional[str] = None
    invoice_id: Optional[str] = None
    charge_id: Optional[str] = None
    subscription_id: Optional[str] = None
    provider_status: Optional[str] = None
    amount_total: Optional[int] = Field(default=None, sa_type=BigInteger)
    amount_refunded: Optional[int] = Field(default=None, sa_type=BigInteger)
    currency: Optional[str] = Field(default=None, max_length=3)
    reconciliation: str = 'unknown'
    observed_at: datetime = Field(sa_type=DateTime(timezone=True))


def _pg_check(expression, name):
    # Existing local SQLite create_all remains usable; these PG-only protections
    # are also emitted explicitly by the reviewed PostgreSQL migration.
    return CheckConstraint(expression, name=name).ddl_if(dialect='postgresql')


class BillingReconciliationTask(SQLModel, table=True):
    """One immutable manual-read identity per Checkout; no lease/restart cycle."""
    __table_args__ = (
        UniqueConstraint('checkout_id',name='uq_billingreconciliationtask_checkout_id'),
        CheckConstraint("provider_account_scope <> 'legacy_unknown' AND length(provider_account_scope)>0",name='scope'),
        CheckConstraint("reason_code IN ('unknown_create','missing_reference','legacy_verification')",name='reason'),
        CheckConstraint('input_version=1 AND budget_version=1 AND get_limit=3',name='versions_limits'),
        CheckConstraint('initial_checkout_revision>=0 AND expected_checkout_revision>=initial_checkout_revision AND membership_revision>=0 AND revision>=0 AND next_audit_seq>=1',name='revisions'),
        CheckConstraint('get_attempts>=0 AND get_attempts<=get_limit',name='get_budget'),
        CheckConstraint('budget_deadline>=started_at',name='deadline'),
        CheckConstraint("(status='running' AND completed_at IS NULL) OR (status IN ('verified','needs_review') AND completed_at IS NOT NULL)",name='terminal'),
        _pg_check("input_sha256 ~ '^[0-9a-f]{64}$'",'input_sha256'),
        _pg_check("actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'",'audit_context'),
        _pg_check("octet_length(query_json) BETWEEN 1 AND 65536 AND jsonb_typeof(query_json::jsonb)='object'",'query_json'),
        _pg_check("octet_length(policy_json) BETWEEN 1 AND 65536 AND jsonb_typeof(policy_json::jsonb)='object'",'policy_json'),
        Index('ix_billingreconciliationtask_status_deadline','status','budget_deadline'),
        Index('ix_billingreconciliationtask_user_id','user_id'),
    )
    id: str = Field(default_factory=lambda: str(uuid.uuid4()),primary_key=True,max_length=36)
    checkout_id: str = Field(foreign_key='billingcheckout.id',ondelete='RESTRICT')
    user_id: str = Field(foreign_key='user.id',ondelete='RESTRICT')
    provider_account_scope: str = Field(max_length=128)
    livemode: bool
    actor_ref: str = Field(max_length=63)
    reason_code: str = Field(max_length=32)
    evidence_ref: str = Field(max_length=123)
    input_version: int = 1
    input_sha256: str = Field(max_length=64)
    query_json: str = Field(sa_type=Text)
    policy_json: str = Field(sa_type=Text)
    initial_checkout_revision: int = Field(sa_type=BigInteger)
    expected_checkout_revision: int = Field(sa_type=BigInteger)
    membership_revision: int = Field(sa_type=BigInteger)
    owner_ref: str = Field(max_length=128)
    started_at: datetime = Field(sa_type=DateTime(timezone=True))
    budget_deadline: datetime = Field(sa_type=DateTime(timezone=True))
    get_attempts: int = Field(default=0,sa_type=BigInteger)
    get_limit: int = 3
    budget_version: int = 1
    status: str = Field(default='running',max_length=16)
    outcome_reason: Optional[str] = Field(default=None,max_length=64)
    completed_at: Optional[datetime] = Field(default=None,sa_type=DateTime(timezone=True))
    next_audit_seq: int = Field(default=1,sa_type=BigInteger)
    revision: int = Field(default=0,sa_type=BigInteger)


class BillingReconciliationAudit(SQLModel, table=True):
    """Append-only projections; database trigger/ACL protects UPDATE/DELETE/TRUNCATE."""
    __table_args__ = (
        UniqueConstraint('task_id','seq',name='uq_billingreconciliationaudit_task_seq'),
        UniqueConstraint('task_id','event_kind','get_ordinal',name='uq_billingreconciliationaudit_get_event'),
        CheckConstraint('seq>0 AND projection_version=1',name='sequence_version'),
        CheckConstraint("(event_kind IN ('task_started','task_finished') AND get_ordinal IS NULL) OR (event_kind IN ('get_reserved','get_observed') AND get_ordinal IS NOT NULL AND get_ordinal BETWEEN 1 AND 3)",name='event_ordinal'),
        CheckConstraint("reason_code IN ('unknown_create','missing_reference','legacy_verification')",name='reason'),
        _pg_check("projection_sha256 ~ '^[0-9a-f]{64}$'",'projection_sha256'),
        _pg_check("actor_ref ~ '^op:[A-Za-z0-9_.:-]{1,60}$' AND evidence_ref ~ '^ev:[A-Za-z0-9_.:-]{1,120}$'",'audit_context'),
        _pg_check("octet_length(projection_json) BETWEEN 1 AND 65536 AND jsonb_typeof(projection_json::jsonb)='object'",'projection_json'),
        Index('uq_billingreconciliationaudit_lifecycle','task_id','event_kind',unique=True,
              postgresql_where=text('get_ordinal IS NULL'),sqlite_where=text('get_ordinal IS NULL')),
    )
    id: str = Field(default_factory=lambda: str(uuid.uuid4()),primary_key=True,max_length=36)
    task_id: str = Field(foreign_key='billingreconciliationtask.id',ondelete='RESTRICT')
    seq: int = Field(sa_type=BigInteger)
    event_kind: str = Field(max_length=16)
    get_ordinal: Optional[int] = None
    recorded_at: datetime = Field(sa_type=DateTime(timezone=True))
    actor_ref: str = Field(max_length=63)
    reason_code: str = Field(max_length=32)
    evidence_ref: str = Field(max_length=123)
    projection_version: int = 1
    projection_json: str = Field(sa_type=Text)
    projection_sha256: str = Field(max_length=64)
