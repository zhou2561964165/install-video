"""C1 durable execution attempts (PG coordination source of truth; see c1_0005)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel


class JobAttempt(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint('job_id', 'epoch', name='uq_jobattempt_job_id_epoch'),
        UniqueConstraint('job_id', 'attempt_index', name='uq_jobattempt_job_id_attempt_index'),
        UniqueConstraint('job_id', 'id', name='uq_jobattempt_job_id_id'),  # target of Job's own-attempt key
        CheckConstraint('attempt_index BETWEEN 1 AND 3', name='index'),
        CheckConstraint('epoch >= 1', name='epoch'),
        CheckConstraint("state IN ('running','lost','failed','succeeded')", name='state'),
        CheckConstraint("(state = 'running') = (ended_at IS NULL)", name='end'),
        CheckConstraint('bytes_used >= 0', name='bytes'),  # C3 (c3_0007)
        Index('uq_jobattempt_running', 'job_id', unique=True, postgresql_where=text("state='running'"),
              sqlite_where=text("state='running'")),
    )
    id: str = Field(primary_key=True)
    job_id: str = Field(foreign_key='job.id', ondelete='RESTRICT')
    epoch: int = Field(sa_type=BigInteger)
    owner: str
    attempt_index: int
    state: str
    started_at: datetime = Field(sa_type=DateTime(timezone=True))
    ended_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    error_code: Optional[str] = None
    bytes_used: int = Field(default=0, sa_type=BigInteger)  # C3: this attempt's monotonic source bytes


class ArtifactManifest(SQLModel, table=True):
    """C2: the durable record of one attempt's published media (see c2_0006)."""
    __table_args__ = (
        UniqueConstraint('job_id', 'epoch', name='uq_artifactmanifest_job_id_epoch'),
        CheckConstraint('byte_size > 0', name='byte_size'),
        CheckConstraint('length(sha256) = 64', name='sha256'),  # PG additionally enforces lowercase hex
        CheckConstraint("media_check IN ('verified','signature')", name='media_check'),  # B5 U5b (b5_0012)
    )
    attempt_id: str = Field(primary_key=True, foreign_key='jobattempt.id', ondelete='RESTRICT')
    job_id: str = Field(foreign_key='job.id', ondelete='RESTRICT')
    epoch: int = Field(sa_type=BigInteger)
    relative_path: str
    byte_size: int = Field(sa_type=BigInteger)
    sha256: str
    media_format: str
    media_check: str
    created_at: datetime = Field(sa_type=DateTime(timezone=True))


class FileReadLease(SQLModel, table=True):
    """C4: one GET/Range read of a published artifact (see c4_0008); C5's cleaner never unlinks under a live one."""
    __table_args__ = (
        CheckConstraint('lease_deadline <= max_until', name='lease_bound'),
        # The 30-minute span check (ck_filereadlease_max_span) is PostgreSQL-only interval syntax and
        # lives in c4_0008 (as C2's hex check does); read leases exist only on PostgreSQL.
        CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='end'),
        Index('ix_filereadlease_open', 'job_id', postgresql_where=text('ended_at IS NULL'),
              sqlite_where=text('ended_at IS NULL')),
        Index('ix_filereadlease_job_id', 'job_id'),  # C5b: RESTRICT checks and retention purge
        # A read lease may only name an attempt of its own Job.
        ForeignKeyConstraint(['job_id', 'attempt_id'], ['jobattempt.job_id', 'jobattempt.id'],
                             ondelete='RESTRICT', name='fk_filereadlease_attempt_jobattempt'),
    )
    id: str = Field(primary_key=True)
    job_id: str = Field(foreign_key='job.id', ondelete='RESTRICT')
    attempt_id: str
    started_at: datetime = Field(sa_type=DateTime(timezone=True))
    lease_deadline: datetime = Field(sa_type=DateTime(timezone=True))
    max_until: datetime = Field(sa_type=DateTime(timezone=True))
    ended_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))


class CleanupIntent(SQLModel, table=True):
    """C5a: the deletion of one Job's published files, claimed by one cleaner at a time (see c5_0009)."""
    __table_args__ = (
        CheckConstraint("state IN ('pending','done','needs_review')", name='state'),
        CheckConstraint('attempts BETWEEN 0 AND 5', name='attempts'),
        CheckConstraint('epoch >= 0', name='epoch'),
        Index('ix_cleanupintent_due', 'next_run_at', postgresql_where=text("state = 'pending'"),
              sqlite_where=text("state = 'pending'")),
        ForeignKeyConstraint(['job_id', 'attempt_id'], ['jobattempt.job_id', 'jobattempt.id'],
                             ondelete='RESTRICT', name='fk_cleanupintent_attempt_jobattempt'),
    )
    job_id: str = Field(primary_key=True, foreign_key='job.id', ondelete='RESTRICT')
    attempt_id: str
    relative_path: str
    owner: Optional[str] = None
    epoch: int = Field(sa_type=BigInteger)
    state: str
    attempts: int = 0
    next_run_at: datetime = Field(sa_type=DateTime(timezone=True))
    last_error: Optional[str] = None
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class OrphanObject(SQLModel, table=True):
    """C5b-2: a media object without database ownership, by root-relative path (see c5b_0011)."""
    __table_args__ = (
        CheckConstraint("kind IN ('job_dir','attempt_dir','probe_file','unknown')", name='kind'),
        CheckConstraint("state IN ('listed','quarantined','released','removed')", name='state'),
        CheckConstraint('length(relative_path) BETWEEN 1 AND 200', name='path'),
        CheckConstraint('last_seen_at >= first_seen_at', name='seen'),
        CheckConstraint("kind <> 'unknown' OR state = 'quarantined'", name='unknown_quarantined'),
        Index('ix_orphanobject_due', 'first_seen_at', postgresql_where=text("state = 'listed'"),
              sqlite_where=text("state = 'listed'")),
    )
    relative_path: str = Field(primary_key=True)
    kind: str
    state: str
    reason: Optional[str] = None
    first_seen_at: datetime = Field(sa_type=DateTime(timezone=True))
    last_seen_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class DataImport(SQLModel, table=True):
    """B6 E3: one completed snapshot import per manifest SHA256 (see b6_0013); import role only."""
    __table_args__ = (
        # Portable lengths here (SQLite init compiles all metadata); PG (b6_0013) enforces lowercase hex.
        CheckConstraint('length(manifest_sha256) = 64', name='manifest_sha256'),
        CheckConstraint('length(export_id) = 32', name='export_id'),
        CheckConstraint('length(schema_fingerprint) = 64', name='schema_fingerprint'),
    )
    manifest_sha256: str = Field(primary_key=True, max_length=64)
    export_id: str = Field(max_length=32)
    schema_profile: str
    schema_fingerprint: str = Field(max_length=64)
    snapshot_method: str
    target_head: str
    table_rows: str = Field(sa_type=Text)
    transforms: str = Field(sa_type=Text)
    completed_at: datetime = Field(sa_type=DateTime(timezone=True))
