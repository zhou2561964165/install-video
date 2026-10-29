"""C3 cross-attempt source byte budget: Job.source_bytes_used and JobAttempt.bytes_used."""
from alembic import context,op
import sqlalchemy as sa

revision='c3_0007'
down_revision='c2_0006'
branch_labels=None
depends_on=None

# No new table: the runtime roles already hold UPDATE on app.job and app.jobattempt (C1),
# so no grant changes are needed for the worker to advance these counters.
UPGRADE_SQL=(
"""ALTER TABLE app.job
 ADD COLUMN source_bytes_used BIGINT NOT NULL DEFAULT 0,
 ADD CONSTRAINT ck_job_source_bytes CHECK (source_bytes_used >= 0)
""",
"""ALTER TABLE app.jobattempt
 ADD COLUMN bytes_used BIGINT NOT NULL DEFAULT 0,
 ADD CONSTRAINT ck_jobattempt_bytes CHECK (bytes_used >= 0)
""",
)


def upgrade():
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty byte budget')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.job, app.jobattempt IN ACCESS EXCLUSIVE MODE'))
    # Dropping recorded counters would silently reset a Job's budget and allow re-downloading past it.
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.job WHERE source_bytes_used<>0) '
                                 'OR EXISTS(SELECT 1 FROM app.jobattempt WHERE bytes_used<>0)')):
        raise RuntimeError('Refusing destructive downgrade of recorded source bytes')
    op.execute(sa.text('ALTER TABLE app.jobattempt DROP CONSTRAINT ck_jobattempt_bytes, DROP COLUMN bytes_used'))
    op.execute(sa.text('ALTER TABLE app.job DROP CONSTRAINT ck_job_source_bytes, DROP COLUMN source_bytes_used'))
