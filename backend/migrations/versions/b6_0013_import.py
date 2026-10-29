"""B6 E3: data-import ledger (dataimport) and job.legacy_check (A contract §6 paragraph 6, C6b).

dataimport records one completed snapshot import per manifest SHA256 (idempotent import, verify
anchor). Only the migration/import role uses it: runtime roles get no privileges. legacy_check
records the import-time check of a v1 done Job's file in the old controlled media root
(verified/missing/mismatch/unchecked); v2 Jobs never carry it. Downgrade refuses imported data.
"""
import re
from alembic import context,op
import sqlalchemy as sa

revision='b6_0013'
down_revision='b5_0012'
branch_labels=None
depends_on=None


def _runtime_roles():
    # Same validation contract as b3b_0004..c5b_0011 (kept local: migrations stay self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('B6 migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('B6 migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('B6 migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('B6 runtime role has unsafe attributes')
    return tuple(roles)


UPGRADE_SQL=(
"""CREATE TABLE app.dataimport (
	manifest_sha256 VARCHAR(64) NOT NULL,
	export_id VARCHAR(32) NOT NULL,
	schema_profile VARCHAR NOT NULL,
	schema_fingerprint VARCHAR(64) NOT NULL,
	snapshot_method VARCHAR NOT NULL,
	target_head VARCHAR NOT NULL,
	table_rows TEXT NOT NULL,
	transforms TEXT NOT NULL,
	completed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_dataimport PRIMARY KEY (manifest_sha256),
	CONSTRAINT ck_dataimport_manifest_sha256 CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_dataimport_export_id CHECK (export_id ~ '^[0-9a-f]{32}$'),
	CONSTRAINT ck_dataimport_schema_fingerprint CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$')
)
""",
"""REVOKE ALL ON TABLE app.dataimport FROM PUBLIC
""",
"""ALTER TABLE app.job ADD COLUMN legacy_check VARCHAR
""",
"""ALTER TABLE app.job ADD CONSTRAINT ck_job_legacy_check CHECK (legacy_check IS NULL OR (execution_version = 1 AND legacy_check IN ('verified','missing','mismatch','unchecked')))
""",
"""ALTER TABLE app.job ADD COLUMN legacy_cleanup_attempts INTEGER NOT NULL DEFAULT 0
""",
"""ALTER TABLE app.job ADD CONSTRAINT ck_job_legacy_cleanup_attempts CHECK (legacy_cleanup_attempts BETWEEN 0 AND 5)
""",
"""CREATE INDEX ix_job_legacy_cleanup ON app.job (expires_at) WHERE execution_version = 1 AND legacy_check = 'verified' AND (media_state IS NULL OR media_state = 'deleting')
""",
)


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        op.execute(sa.text('REVOKE ALL ON TABLE app.dataimport FROM '+quoted))
        if not context.is_offline_mode():
            for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                if op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),
                                        {'role':role,'table':'app.dataimport','privilege':privilege}):
                    raise RuntimeError('B6 runtime role keeps a privilege on the import ledger')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline downgrade cannot verify that no imported data exists')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.dataimport, app.job IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.dataimport)')):
        raise RuntimeError('Refusing downgrade while an import is recorded')
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.job WHERE legacy_check IS NOT NULL)')):
        raise RuntimeError('Refusing downgrade while legacy checks are recorded')
    op.execute(sa.text('DROP INDEX app.ix_job_legacy_cleanup'))
    op.execute(sa.text('ALTER TABLE app.job DROP CONSTRAINT ck_job_legacy_cleanup_attempts'))
    op.execute(sa.text('ALTER TABLE app.job DROP COLUMN legacy_cleanup_attempts'))
    op.execute(sa.text('ALTER TABLE app.job DROP CONSTRAINT ck_job_legacy_check'))
    op.execute(sa.text('ALTER TABLE app.job DROP COLUMN legacy_check'))
    op.drop_table('dataimport',schema='app')
