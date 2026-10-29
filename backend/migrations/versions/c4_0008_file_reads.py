"""C4 read leases: filereadlease (one row per GET/Range read of a published artifact)."""
import re
from alembic import context,op
import sqlalchemy as sa

revision='c4_0008'
down_revision='c3_0007'
branch_labels=None
depends_on=None


def _runtime_roles():
    # Same validation contract as b3b_0004/c1_0005/c2_0006 (kept local: migrations stay self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('C4 migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('C4 migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('C4 migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('C4 runtime role has unsafe attributes')
    return tuple(roles)


UPGRADE_SQL=(
"""CREATE TABLE app.filereadlease (
	id VARCHAR NOT NULL,
	job_id VARCHAR NOT NULL,
	attempt_id VARCHAR NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	lease_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
	max_until TIMESTAMP WITH TIME ZONE NOT NULL,
	ended_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_filereadlease PRIMARY KEY (id),
	CONSTRAINT fk_filereadlease_job_id_job FOREIGN KEY(job_id) REFERENCES app.job (id) ON DELETE RESTRICT,
	CONSTRAINT fk_filereadlease_attempt_jobattempt FOREIGN KEY(job_id, attempt_id) REFERENCES app.jobattempt (job_id, id) ON DELETE RESTRICT,
	CONSTRAINT ck_filereadlease_lease_bound CHECK (lease_deadline <= max_until),
	CONSTRAINT ck_filereadlease_max_span CHECK (max_until <= started_at + interval '30 minutes'),
	CONSTRAINT ck_filereadlease_end CHECK (ended_at IS NULL OR ended_at >= started_at)
)
""",
"""CREATE INDEX ix_filereadlease_open ON app.filereadlease (job_id) WHERE ended_at IS NULL
""",
"""REVOKE ALL ON TABLE app.filereadlease FROM PUBLIC
""",
)


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        op.execute(sa.text('REVOKE ALL ON TABLE app.filereadlease FROM '+quoted))
        # Deleting read leases belongs to C5's metadata deletion order; granted there, not here.
        op.execute(sa.text('GRANT SELECT,INSERT,UPDATE ON TABLE app.filereadlease TO '+quoted))
        if not context.is_offline_mode():
            for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                actual=op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),{'role':role,'table':'app.filereadlease','privilege':privilege})
                if actual != (privilege in ('SELECT','INSERT','UPDATE')):
                    raise RuntimeError('C4 runtime effective privileges remain unsafe')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty read-lease state')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.filereadlease IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.filereadlease)')):
        raise RuntimeError('Refusing destructive downgrade of nonempty read-lease state')
    op.drop_table('filereadlease',schema='app')
