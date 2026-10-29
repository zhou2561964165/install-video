"""C2 published artifacts: artifactmanifest, Job media_state/completed_at, own-attempt visibility."""
import re
from alembic import context,op
import sqlalchemy as sa

revision='c2_0006'
down_revision='c1_0005'
branch_labels=None
depends_on=None


def _runtime_roles():
    # Same validation contract as b3b_0004/c1_0005 (kept local: migrations stay self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('C2 migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('C2 migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('C2 migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('C2 runtime role has unsafe attributes')
    return tuple(roles)


UPGRADE_SQL=(
# A Job may only point at one of its own attempts (C1 review): composite key replaces the single-column FK.
"""ALTER TABLE app.jobattempt ADD CONSTRAINT uq_jobattempt_job_id_id UNIQUE (job_id, id)
""",
"""ALTER TABLE app.job DROP CONSTRAINT fk_job_visible_attempt_id_jobattempt
""",
"""ALTER TABLE app.job ADD CONSTRAINT fk_job_visible_attempt_jobattempt FOREIGN KEY(id, visible_attempt_id) REFERENCES app.jobattempt (job_id, id) ON DELETE RESTRICT
""",
"""ALTER TABLE app.job
 ADD COLUMN media_state VARCHAR,
 ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE,
 ADD CONSTRAINT ck_job_media_state CHECK (media_state IS NULL OR media_state IN ('available','expired','deleting','deleted','missing','corrupt')),
 ADD CONSTRAINT ck_job_succeeded_visible CHECK (internal_state IS NULL OR internal_state<>'succeeded' OR (visible_attempt_id IS NOT NULL AND media_state IS NOT NULL AND completed_at IS NOT NULL))
""",
"""CREATE TABLE app.artifactmanifest (
	attempt_id VARCHAR NOT NULL,
	job_id VARCHAR NOT NULL,
	epoch BIGINT NOT NULL,
	relative_path VARCHAR NOT NULL,
	byte_size BIGINT NOT NULL,
	sha256 VARCHAR NOT NULL,
	media_format VARCHAR NOT NULL,
	media_check VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_artifactmanifest PRIMARY KEY (attempt_id),
	CONSTRAINT fk_artifactmanifest_attempt_id_jobattempt FOREIGN KEY(attempt_id) REFERENCES app.jobattempt (id) ON DELETE RESTRICT,
	CONSTRAINT fk_artifactmanifest_job_id_job FOREIGN KEY(job_id) REFERENCES app.job (id) ON DELETE RESTRICT,
	CONSTRAINT uq_artifactmanifest_job_id_epoch UNIQUE (job_id, epoch),
	CONSTRAINT ck_artifactmanifest_byte_size CHECK (byte_size > 0),
	CONSTRAINT ck_artifactmanifest_sha256 CHECK (length(sha256)=64),
	-- PostgreSQL-only strengthening (SQLite has no regex operator; the model keeps the portable check).
	CONSTRAINT ck_artifactmanifest_sha256_hex CHECK (sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_artifactmanifest_media_check CHECK (media_check IN ('verified'))
)
""",
"""REVOKE ALL ON TABLE app.artifactmanifest FROM PUBLIC
""",
)


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        op.execute(sa.text('REVOKE ALL ON TABLE app.artifactmanifest FROM '+quoted))
        op.execute(sa.text('GRANT SELECT,INSERT ON TABLE app.artifactmanifest TO '+quoted))
        if not context.is_offline_mode():
            for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                actual=op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),{'role':role,'table':'app.artifactmanifest','privilege':privilege})
                if actual != (privilege in ('SELECT','INSERT')):
                    raise RuntimeError('C2 runtime effective privileges remain unsafe')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty artifact state')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.job, app.jobattempt, app.artifactmanifest IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.artifactmanifest) OR EXISTS(SELECT 1 FROM app.job WHERE media_state IS NOT NULL OR completed_at IS NOT NULL)')):
        raise RuntimeError('Refusing destructive downgrade of nonempty artifact state')
    op.drop_table('artifactmanifest',schema='app')
    op.execute(sa.text("""ALTER TABLE app.job DROP CONSTRAINT ck_job_succeeded_visible, DROP CONSTRAINT ck_job_media_state,
 DROP COLUMN completed_at, DROP COLUMN media_state"""))
    op.execute(sa.text('ALTER TABLE app.job DROP CONSTRAINT fk_job_visible_attempt_jobattempt'))
    op.execute(sa.text('ALTER TABLE app.job ADD CONSTRAINT fk_job_visible_attempt_id_jobattempt FOREIGN KEY(visible_attempt_id) REFERENCES app.jobattempt (id) ON DELETE RESTRICT'))
    op.execute(sa.text('ALTER TABLE app.jobattempt DROP CONSTRAINT uq_jobattempt_job_id_id'))
