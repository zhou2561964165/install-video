import uuid
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, Enum as SAEnum, ForeignKeyConstraint, Index, Text,
                        UniqueConstraint, text)
from sqlmodel import Field, SQLModel

SQLModel.metadata.naming_convention = {
    'pk': 'pk_%(table_name)s', 'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s', 'ix': 'ix_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
}


class JobStatus(str, Enum):
    queued = "queued"
    downloading = "downloading"
    merging = "merging"
    done = "done"
    error = "error"


class Job(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint('execution_version IN (1,2)', name='execution_version'),
        CheckConstraint("internal_state IS NULL OR internal_state IN ('queued','running','retry_wait','succeeded',"
                        "'failed','needs_review','legacy_hold')", name='internal_state'),
        CheckConstraint('execution_version=1 OR (internal_state IS NOT NULL AND run_deadline_at IS NOT NULL)',
                        name='v2_state'),
        CheckConstraint('(lease_owner IS NULL)=(lease_deadline IS NULL)', name='lease_pair'),
        CheckConstraint('epoch>=0', name='epoch'),
        CheckConstraint('attempts_limit BETWEEN 1 AND 3 AND attempts_used BETWEEN 0 AND attempts_limit',
                        name='attempt_budget'),
        # Portable form: SQLite < 3.39 has no IS DISTINCT FROM.
        CheckConstraint("internal_state IS NULL OR internal_state<>'retry_wait' OR next_run_at IS NOT NULL",
                        name='retry_time'),
        CheckConstraint("execution_version=1 OR ((internal_state='running')=(lease_owner IS NOT NULL))",
                        name='v2_lease'),
        CheckConstraint("execution_version=2 OR internal_state IS NULL OR internal_state='legacy_hold'",
                        name='v1_state'),
        Index('ix_job_runnable', 'run_deadline_at', 'created_at',
              postgresql_where=text("execution_version=2 AND internal_state IN ('queued','retry_wait')")),
        Index('ix_job_running_lease', 'lease_deadline',
              postgresql_where=text("execution_version=2 AND internal_state='running'")),
        # C2: media lifecycle, and a succeeded Job always has a visible own attempt.
        CheckConstraint("media_state IS NULL OR media_state IN ('available','expired','deleting','deleted',"
                        "'missing','corrupt')", name='media_state'),
        # C5b (c5b_0010): a Job whose media is deleted may drop its visible attempt (retention breaks the
        # Job <-> JobAttempt RESTRICT cycle this way before deleting attempts and the Job).
        CheckConstraint("internal_state IS NULL OR internal_state<>'succeeded' OR ((visible_attempt_id IS NOT NULL "
                        "OR media_state='deleted') AND media_state IS NOT NULL AND completed_at IS NOT NULL)",
                        name='succeeded_visible'),
        # A Job may only point at one of its own attempts; Job <-> JobAttempt is a cycle (use_alter).
        ForeignKeyConstraint(['id', 'visible_attempt_id'], ['jobattempt.job_id', 'jobattempt.id'],
                             ondelete='RESTRICT', use_alter=True, name='fk_job_visible_attempt_jobattempt'),
        CheckConstraint('source_bytes_used >= 0', name='source_bytes'),  # C3 (c3_0007)
        Index('ix_job_cleanup_expiry', 'expires_at',  # C5a cleaner scan (c5_0009)
              postgresql_where=text("execution_version = 2 AND media_state = 'available'"),
              sqlite_where=text("execution_version = 2 AND media_state = 'available'")),
        Index('ix_job_cleanup_claim', 'expires_at',  # C5a claim scan (c5_0009)
              postgresql_where=text("execution_version = 2 AND media_state IN ('expired','deleting')"),
              sqlite_where=text("execution_version = 2 AND media_state IN ('expired','deleting')")),
        CheckConstraint("legacy_check IS NULL OR (execution_version = 1 AND legacy_check IN "
                        "('verified','missing','mismatch','unchecked'))", name='legacy_check'),  # B6 (b6_0013)
        CheckConstraint('legacy_cleanup_attempts BETWEEN 0 AND 5', name='legacy_cleanup_attempts'),  # C6c
        Index('ix_job_legacy_cleanup', 'expires_at',  # C6c legacy deletion scan (b6_0013)
              postgresql_where=text("execution_version = 1 AND legacy_check = 'verified' "
                                    "AND (media_state IS NULL OR media_state = 'deleting')"),
              sqlite_where=text("execution_version = 1 AND legacy_check = 'verified' "
                                "AND (media_state IS NULL OR media_state = 'deleting')")),
        Index('ix_job_retention', 'created_at',  # C5b-1 retention eligibility scan (c5b_0010)
              postgresql_where=text("execution_version = 2 AND internal_state IN ('succeeded','failed') "
                                    "AND (media_state IS NULL OR media_state = 'deleted')"),
              sqlite_where=text("execution_version = 2 AND internal_state IN ('succeeded','failed') "
                                "AND (media_state IS NULL OR media_state = 'deleted')")),
    )
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    url: str
    title: Optional[str] = None
    format_id: Optional[str] = None
    status: JobStatus = Field(default=JobStatus.queued, sa_type=SAEnum(
        JobStatus, native_enum=False, create_constraint=True, name='status'))
    progress: float = Field(default=0.0)
    file_path: Optional[str] = None
    file_size: Optional[int] = Field(default=None, sa_type=BigInteger)
    error_type: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True))
    expires_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    # v2：归属用户（nullable，匿名 v1 任务为 None）
    user_id: Optional[str] = Field(default=None, foreign_key="user.id")
    # C1 durable execution (c1_0005). Legacy rows stay execution_version=1 and are never leased.
    execution_version: int = 1
    internal_state: Optional[str] = None
    epoch: int = Field(default=0, sa_type=BigInteger)
    lease_owner: Optional[str] = None
    lease_deadline: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    attempts_used: int = 0
    attempts_limit: int = 3
    next_run_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    run_deadline_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    visible_attempt_id: Optional[str] = None
    media_state: Optional[str] = None
    completed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    # C3: source bytes downloaded across all attempts; a retry never resets it.
    source_bytes_used: int = Field(default=0, sa_type=BigInteger)
    # B6 E3 (b6_0013): import-time check of a v1 done Job's file in the old media root (C6b).
    legacy_check: Optional[str] = None
    # C6c (b6_0013): failed deletions of an expired v1 file (backoff, then review).
    legacy_cleanup_attempts: int = 0


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True))


class Quota(SQLModel, table=True):
    # (user_id, date) 唯一：每用户每日一行
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_quota_user_date"),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    date: str
    downloads_used: int = Field(default=0)
    limit: int


class DownloadIdempotency(SQLModel, table=True):
    """Submission receipts; pending rows are never automatically reclaimed."""

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_download_idempotency_user_key"),
                      UniqueConstraint('operation_id', name='uq_downloadidempotency_operation_id'))

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    key: str = Field(max_length=128)
    fingerprint: str
    state: str = Field(default="pending")
    created_at: float = Field(default_factory=time.time)
    # None protects pending/uncertain submissions from automatic dispatch again.
    expires_at: Optional[float] = Field(default=None, index=True)
    direct_expires_at: Optional[float] = None
    status_code: Optional[int] = None
    response_json: Optional[str] = None
    operation_id: Optional[str] = Field(default=None, foreign_key='downloadoperation.id', ondelete='RESTRICT')


class Membership(SQLModel, table=True):
    user_id: str = Field(primary_key=True, foreign_key="user.id")
    customer_id: Optional[str] = Field(default=None, unique=True)
    subscription_id: Optional[str] = Field(default=None, unique=True)
    status: str = "free"
    expires_at: float = 0
    cancel_at_period_end: bool = False
    active_checkout_id: Optional[str] = None
    revision: int = 0
    entitlement_source: Optional[str] = None


class BillingCheckout(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint("reconciliation IS NULL OR reconciliation IN ('not_started','unknown','verified','needs_review','closed')", name='reconciliation'),
        CheckConstraint('reconcile_attempts >= 0 AND reconcile_attempts <= 3', name='reconcile_attempts'),
    )
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    price_id: str
    mode: str
    duration_days: int
    origin: str
    customer_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    stripe_id: Optional[str] = Field(default=None, unique=True)
    url: Optional[str] = None
    expires_at: float = 0
    state: str = "pending"
    fulfilled: bool = False
    provider_account_scope: Optional[str] = None
    livemode: Optional[bool] = None
    create_payload: Optional[str] = Field(default=None, sa_type=Text)
    create_payload_sha256: Optional[str] = Field(default=None, max_length=64)
    create_payload_version: Optional[int] = None
    create_started_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    create_completed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    create_result_code: Optional[str] = None
    reconciliation: Optional[str] = None
    reconcile_attempts: int = 0
    reconciliation_started_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    reconciliation_evidence: Optional[str] = None
    reconciliation_actor: Optional[str] = None
    reconciliation_reason: Optional[str] = None
    revision: int = Field(default=0, sa_type=BigInteger)


class BillingEvent(SQLModel, table=True):
    __table_args__ = (CheckConstraint("(provider_account_scope = 'legacy_unknown' AND livemode IS NULL) OR (provider_account_scope <> 'legacy_unknown' AND livemode IS NOT NULL)", name='scope_mode'),)
    id: str = Field(primary_key=True)
    processed_at: float = Field(default_factory=time.time)
    provider_account_scope: str = 'legacy_unknown'
    livemode: Optional[bool] = None
    outcome: Optional[str] = None


class BillingPayment(SQLModel, table=True):
    payment_intent: str = Field(primary_key=True)
    user_id: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    source_id: Optional[str] = None
    revoked: bool = False


class DownloadAccess(SQLModel, table=True):
    job_id: str = Field(primary_key=True, foreign_key="job.id")
    # None means unrestricted at submission; free users cannot retrieve it later.
    max_height: Optional[int] = None


# Import after the legacy declarations so metadata registers all protocol tables.
from .models_operations import DownloadOperation, QuotaCharge, ResourceCounter, ResourceReservation  # noqa: E402,F401
from .models_billing import BillingInbox, BillingFact, BillingReconciliationTask, BillingReconciliationAudit  # noqa: E402,F401
from .models_execution import ArtifactManifest, JobAttempt  # noqa: E402,F401
from .models_support import MembershipReissue, SupportPaymentCheck, SupportTicket  # noqa: E402,F401
