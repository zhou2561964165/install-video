"""C1 durable execution: v2 Job lease/attempt fields and jobattempt; explicit runtime roles."""
import re
from alembic import context,op
import sqlalchemy as sa

revision='c1_0005'
down_revision='b3b_0004'
branch_labels=None
depends_on=None


def _runtime_roles():
    # Same validation contract as b3b_0004 (kept local: migrations stay immutable and self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('C1 migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('C1 migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('C1 migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('C1 runtime role has unsafe attributes')
    return tuple(roles)


UPGRADE_SQL=(
"""ALTER TABLE app.job
 ADD COLUMN execution_version INTEGER NOT NULL DEFAULT 1,
 ADD COLUMN internal_state VARCHAR,
 ADD COLUMN epoch BIGINT NOT NULL DEFAULT 0,
 ADD COLUMN lease_owner VARCHAR,
 ADD COLUMN lease_deadline TIMESTAMP WITH TIME ZONE,
 ADD COLUMN attempts_used INTEGER NOT NULL DEFAULT 0,
 ADD COLUMN attempts_limit INTEGER NOT NULL DEFAULT 3,
 ADD COLUMN next_run_at TIMESTAMP WITH TIME ZONE,
 ADD COLUMN run_deadline_at TIMESTAMP WITH TIME ZONE,
 ADD COLUMN visible_attempt_id VARCHAR
""",
"""ALTER TABLE app.job
 ADD CONSTRAINT ck_job_execution_version CHECK (execution_version IN (1,2)),
 ADD CONSTRAINT ck_job_internal_state CHECK (internal_state IS NULL OR internal_state IN ('queued','running','retry_wait','succeeded','failed','needs_review','legacy_hold')),
 ADD CONSTRAINT ck_job_v2_state CHECK (execution_version=1 OR (internal_state IS NOT NULL AND run_deadline_at IS NOT NULL)),
 ADD CONSTRAINT ck_job_lease_pair CHECK ((lease_owner IS NULL)=(lease_deadline IS NULL)),
 ADD CONSTRAINT ck_job_epoch CHECK (epoch>=0),
 ADD CONSTRAINT ck_job_attempt_budget CHECK (attempts_limit BETWEEN 1 AND 3 AND attempts_used BETWEEN 0 AND attempts_limit),
 ADD CONSTRAINT ck_job_retry_time CHECK (internal_state IS NULL OR internal_state<>'retry_wait' OR next_run_at IS NOT NULL),
 ADD CONSTRAINT ck_job_v2_lease CHECK (execution_version=1 OR ((internal_state='running')=(lease_owner IS NOT NULL))),
 ADD CONSTRAINT ck_job_v1_state CHECK (execution_version=2 OR internal_state IS NULL OR internal_state='legacy_hold')
""",
"""CREATE TABLE app.jobattempt (
	id VARCHAR NOT NULL,
	job_id VARCHAR NOT NULL,
	epoch BIGINT NOT NULL,
	owner VARCHAR NOT NULL,
	attempt_index INTEGER NOT NULL,
	state VARCHAR NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ended_at TIMESTAMP WITH TIME ZONE,
	error_code VARCHAR,
	CONSTRAINT pk_jobattempt PRIMARY KEY (id),
	CONSTRAINT fk_jobattempt_job_id_job FOREIGN KEY(job_id) REFERENCES app.job (id) ON DELETE RESTRICT,
	CONSTRAINT uq_jobattempt_job_id_epoch UNIQUE (job_id, epoch),
	CONSTRAINT uq_jobattempt_job_id_attempt_index UNIQUE (job_id, attempt_index),
	CONSTRAINT ck_jobattempt_index CHECK (attempt_index BETWEEN 1 AND 3),
	CONSTRAINT ck_jobattempt_epoch CHECK (epoch>=1),
	CONSTRAINT ck_jobattempt_state CHECK (state IN ('running','lost','failed','succeeded')),
	CONSTRAINT ck_jobattempt_end CHECK ((state='running')=(ended_at IS NULL))
)
""",
"""ALTER TABLE app.job ADD CONSTRAINT fk_job_visible_attempt_id_jobattempt FOREIGN KEY(visible_attempt_id) REFERENCES app.jobattempt (id) ON DELETE RESTRICT
""",
"""CREATE INDEX ix_job_runnable ON app.job (run_deadline_at, created_at) WHERE execution_version=2 AND internal_state IN ('queued','retry_wait')
""",
"""CREATE INDEX ix_job_running_lease ON app.job (lease_deadline) WHERE execution_version=2 AND internal_state='running'
""",
"""CREATE UNIQUE INDEX uq_jobattempt_running ON app.jobattempt (job_id) WHERE state='running'
""",
"""REVOKE ALL ON TABLE app.jobattempt FROM PUBLIC
""",
)


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        op.execute(sa.text('REVOKE ALL ON TABLE app.jobattempt FROM '+quoted))
        op.execute(sa.text('GRANT SELECT,INSERT,UPDATE ON TABLE app.jobattempt TO '+quoted))
        if not context.is_offline_mode():
            for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                actual=op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),{'role':role,'table':'app.jobattempt','privilege':privilege})
                if actual != (privilege in ('SELECT','INSERT','UPDATE')):
                    raise RuntimeError('C1 runtime effective privileges remain unsafe')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty execution state')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.job, app.jobattempt IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.jobattempt) OR EXISTS(SELECT 1 FROM app.job WHERE execution_version<>1)')):
        raise RuntimeError('Refusing destructive downgrade of nonempty execution state')
    op.execute(sa.text('DROP INDEX app.ix_job_runnable'))
    op.execute(sa.text('DROP INDEX app.ix_job_running_lease'))
    op.execute(sa.text('ALTER TABLE app.job DROP CONSTRAINT fk_job_visible_attempt_id_jobattempt'))
    op.drop_table('jobattempt',schema='app')
    op.execute(sa.text("""ALTER TABLE app.job
 DROP CONSTRAINT ck_job_execution_version, DROP CONSTRAINT ck_job_internal_state, DROP CONSTRAINT ck_job_v2_state,
 DROP CONSTRAINT ck_job_lease_pair, DROP CONSTRAINT ck_job_epoch, DROP CONSTRAINT ck_job_attempt_budget,
 DROP CONSTRAINT ck_job_retry_time, DROP CONSTRAINT ck_job_v2_lease, DROP CONSTRAINT ck_job_v1_state,
 DROP COLUMN visible_attempt_id, DROP COLUMN run_deadline_at, DROP COLUMN next_run_at, DROP COLUMN attempts_limit,
 DROP COLUMN attempts_used, DROP COLUMN lease_deadline, DROP COLUMN lease_owner, DROP COLUMN epoch,
 DROP COLUMN internal_state, DROP COLUMN execution_version"""))
