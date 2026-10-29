"""C5b-1 retention: deleted media may drop its visible attempt; runtime DELETE on the retention tables."""
import re
from alembic import context,op
import sqlalchemy as sa

revision='c5b_0010'
down_revision='c5_0009'
branch_labels=None
depends_on=None

# Only these tables lose rows at the end of retention; operations, charges, reservations,
# receipts and billing are never deleted (A contract §7 paragraph 4).
RETENTION_TABLES=('filereadlease','cleanupintent','artifactmanifest','downloadaccess','jobattempt','job')
# Tables whose earlier migrations explicitly restricted the runtime roles (REVOKE ALL, then
# SELECT/INSERT/UPDATE only); only these are revoked again on downgrade. job/downloadaccess keep
# whatever the deployment granted them before this revision.
RESTRICTED_TABLES=('filereadlease','cleanupintent','artifactmanifest','jobattempt')
STRICT_VISIBLE=("internal_state IS NULL OR internal_state<>'succeeded' OR (visible_attempt_id IS NOT NULL "
                "AND media_state IS NOT NULL AND completed_at IS NOT NULL)")
# Job <-> JobAttempt is a RESTRICT cycle: a deleted-media Job must be able to drop its visible
# attempt before the attempts and the Job are deleted.
# Only the visible attempt is relaxed; media_state and completed_at stay required (C5b-1 review M1).
RELAXED_VISIBLE=("internal_state IS NULL OR internal_state<>'succeeded' OR ((visible_attempt_id IS NOT NULL "
                 "OR media_state='deleted') AND media_state IS NOT NULL AND completed_at IS NOT NULL)")
# Indexes: the retention eligibility scan (review M4) and the tombstone lookup that answers 410 for a
# purged Job (review I3).
RETENTION_INDEXES=(
    "CREATE INDEX ix_job_retention ON app.job (created_at) WHERE execution_version = 2 "
    "AND internal_state IN ('succeeded','failed') AND (media_state IS NULL OR media_state = 'deleted')",
    'CREATE INDEX ix_downloadoperation_job_id_tombstone ON app.downloadoperation (job_id_tombstone)',
)


def _runtime_roles():
    # Same validation contract as b3b_0004..c5_0009 (kept local: migrations stay self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('C5b migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('C5b migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('C5b migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('C5b runtime role has unsafe attributes')
    return tuple(roles)


def _verify_delete(roles,expected,tables):
    if context.is_offline_mode():
        return
    for role in roles:
        for table in tables:
            actual=op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),
                                        {'role':role,'table':'app."'+table+'"','privilege':'DELETE'})
            if actual!=expected:
                raise RuntimeError('C5b runtime DELETE privilege not as expected')


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    op.execute(sa.text('ALTER TABLE app.job DROP CONSTRAINT ck_job_succeeded_visible, '
                       'ADD CONSTRAINT ck_job_succeeded_visible CHECK ('+RELAXED_VISIBLE+')'))
    op.execute(sa.text('CREATE INDEX ix_filereadlease_job_id ON app.filereadlease (job_id)'))
    for statement in RETENTION_INDEXES:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        for table in RETENTION_TABLES:
            op.execute(sa.text('GRANT DELETE ON TABLE app."'+table+'" TO '+quoted))
    _verify_delete(roles,True,RETENTION_TABLES)


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline downgrade cannot verify the strict visible-attempt invariant')
    roles=_runtime_roles()
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.job IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.job WHERE NOT ('+STRICT_VISIBLE+'))')):
        raise RuntimeError('Refusing downgrade: a deleted-media Job no longer has a visible attempt')
    for role in roles:
        quoted='"'+role+'"'
        for table in RESTRICTED_TABLES:
            op.execute(sa.text('REVOKE DELETE ON TABLE app."'+table+'" FROM '+quoted))
    _verify_delete(roles,False,RESTRICTED_TABLES)
    op.execute(sa.text('DROP INDEX app.ix_downloadoperation_job_id_tombstone'))
    op.execute(sa.text('DROP INDEX app.ix_job_retention'))
    op.execute(sa.text('DROP INDEX app.ix_filereadlease_job_id'))
    op.execute(sa.text('ALTER TABLE app.job DROP CONSTRAINT ck_job_succeeded_visible, '
                       'ADD CONSTRAINT ck_job_succeeded_visible CHECK ('+STRICT_VISIBLE+')'))
