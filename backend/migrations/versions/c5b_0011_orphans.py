"""C5b-2 orphan inventory: orphanobject (media objects without database ownership, by relative path)."""
import re
from alembic import context,op
import sqlalchemy as sa

revision='c5b_0011'
down_revision='c5b_0010'
branch_labels=None
depends_on=None


def _runtime_roles():
    # Same validation contract as b3b_0004..c5b_0010 (kept local: migrations stay self-contained).
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


UPGRADE_SQL=(
"""CREATE TABLE app.orphanobject (
	relative_path VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	state VARCHAR NOT NULL,
	reason VARCHAR,
	first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_orphanobject PRIMARY KEY (relative_path),
	CONSTRAINT ck_orphanobject_kind CHECK (kind IN ('job_dir','attempt_dir','probe_file','unknown')),
	CONSTRAINT ck_orphanobject_state CHECK (state IN ('listed','quarantined','released','removed')),
	CONSTRAINT ck_orphanobject_path CHECK (length(relative_path) BETWEEN 1 AND 200),
	CONSTRAINT ck_orphanobject_seen CHECK (last_seen_at >= first_seen_at),
	CONSTRAINT ck_orphanobject_unknown_quarantined CHECK (kind <> 'unknown' OR state = 'quarantined')
)
""",
"""CREATE INDEX ix_orphanobject_due ON app.orphanobject (first_seen_at) WHERE state = 'listed'
""",
"""REVOKE ALL ON TABLE app.orphanobject FROM PUBLIC
""",
)


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        op.execute(sa.text('REVOKE ALL ON TABLE app.orphanobject FROM '+quoted))
        # DELETE: inventory history (removed/released) is purged after the retention period.
        op.execute(sa.text('GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE app.orphanobject TO '+quoted))
        if not context.is_offline_mode():
            for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                actual=op.get_bind().scalar(sa.text('SELECT has_table_privilege(:role,:table,:privilege)'),{'role':role,'table':'app.orphanobject','privilege':privilege})
                if actual != (privilege in ('SELECT','INSERT','UPDATE','DELETE')):
                    raise RuntimeError('C5b runtime effective privileges remain unsafe')


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline destructive downgrade cannot verify an empty orphan inventory')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE app.orphanobject IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.orphanobject)')):
        raise RuntimeError('Refusing destructive downgrade of nonempty orphan inventory')
    op.drop_table('orphanobject',schema='app')
