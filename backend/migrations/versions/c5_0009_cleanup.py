"""C5a deletion intents: cleanupintent (one per Job) and the partial indexes the cleaner scans."""
import re
from alembic import context,op
import sqlalchemy as sa

revision='c5_0009'
down_revision='c4_0008'
branch_labels=None
depends_on=None


def _runtime_roles():
    # Same validation contract as b3b_0004/c1_0005/c2_0006/c4_0008 (kept local: migrations stay self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('C5 migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('C5 migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('C5 migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('C5 runtime role has unsafe attributes')
    return tuple(roles)


UPGRADE_SQL=(
"""CREATE TABLE app.cleanupintent (
	job_id VARCHAR NOT NULL,
	attempt_id VARCHAR NOT NULL,
	relative_path VARCHAR NOT NULL,
	owner VARCHAR,
	epoch BIGINT NOT NULL,
	state VARCHAR NOT NULL,
	attempts INTEGER NOT NULL,
	next_run_at TIMESTAMP WITH TIME ZONE NOT NULL,
	last_error VARCHAR,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_cleanupintent PRIMARY KEY (job_id),
	CONSTRAINT fk_cleanupintent_job_id_job FOREIGN KEY(job_id) REFERENCES app.job (id) ON DELETE RESTRICT,
	CONSTRAINT fk_cleanupintent_attempt_jobattempt FOREIGN KEY(job_id, attempt_id) REFERENCES app.jobattempt (job_id, id) ON DELETE RESTRICT,
	CONSTRAINT ck_cleanupintent_state CHECK (state IN ('pending','done','needs_review')),
	CONSTRAINT ck_cleanupintent_attempts CHECK (attempts BETWEEN 0 AND 5),
	CONSTRAINT ck_cleanupintent_epoch CHECK (epoch >= 0)
)
""",
"""CREATE INDEX ix_cleanupintent_due ON app.cleanupintent (next_run_at) WHERE state = 'pending'
""",
"""CREATE INDEX ix_job_cleanup_expiry ON app.job (expires_at) WHERE execution_version = 2 AND media_state = 'available'
""",
"""CREATE INDEX ix_job_cleanup_claim ON app.job (expires_at) WHERE execution_version = 2 AND media_state IN ('expired','deleting')
""",
"""REVOKE ALL ON TABLE app.cleanupintent FROM PUBLIC
""",
)


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        op.execute(sa.text('REVOKE ALL ON TABLE app.cleanupintent FROM '+quoted))
        # Intents are history for C5b's retention order; deleting them is granted there, not here.
        op.execute(sa.text('GRANT SELECT,INSERT,UPDATE ON TABLE app.cleanupintent TO '+quoted))
        if not context.is_offline_mode():
            for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                actual=op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),{'role':role,'table':'app.cleanupintent','privilege':privilege})
                if actual != (privilege in ('SELECT','INSERT','UPDATE')):
                    raise RuntimeError('C5 runtime effective privileges remain unsafe')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty cleanup state')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.cleanupintent, app.job IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.cleanupintent)')):
        raise RuntimeError('Refusing destructive downgrade of nonempty cleanup state')
    op.execute(sa.text('DROP INDEX app.ix_job_cleanup_expiry'))
    op.execute(sa.text('DROP INDEX app.ix_job_cleanup_claim'))
    op.drop_table('cleanupintent',schema='app')
