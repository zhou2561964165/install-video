"""Admin M1: admin grants, sessions, account control, append-only audit and login throttle.

The admin console (contract 1.0.0-proposal.20261026.2) authenticates existing users that hold an
active AdminGrant. Grants are written only by the operator CLI through a privileged role: the
runtime roles may read them but never write them. Sessions store only a token hash. AccountControl
rows are optional (a missing row means enabled); M1 never writes them. The audit table is
append-only for every role (trigger). Throttle keys are HMACs, never raw IPs or emails.
Downgrade refuses while any admin row exists; once audit rows exist (they can never be deleted) the
migration is effectively one-way. The runtime role may only set adminsession.revoked_at, and audit
times always come from the database clock.
"""
import re
from alembic import context,op
import sqlalchemy as sa

revision='m1_0014'
down_revision='b6_0013'
branch_labels=None
depends_on=None

TABLES=('admingrant','adminsession','accountcontrol','adminaudit','adminloginthrottle')
RUNTIME_PRIVILEGES={
    'admingrant':('SELECT',),
    'adminsession':('SELECT','INSERT','UPDATE (revoked_at)'),  # runtime may only revoke a session
    'accountcontrol':('SELECT',),
    'adminaudit':('SELECT','INSERT'),
    'adminloginthrottle':('SELECT','INSERT','UPDATE','DELETE'),
}


def _runtime_roles():
    # Same validation contract as b3b_0004..b6_0013 (kept local: migrations stay self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('M1 migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('M1 migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('M1 migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('M1 runtime role has unsafe attributes')
    return tuple(roles)


UPGRADE_SQL=(
"""CREATE TABLE app.admingrant (
	user_id VARCHAR NOT NULL,
	role VARCHAR(32) NOT NULL,
	active BOOLEAN NOT NULL,
	revision BIGINT NOT NULL,
	granted_at TIMESTAMP WITH TIME ZONE NOT NULL,
	granted_by VARCHAR(128) NOT NULL,
	reason VARCHAR(2000) NOT NULL,
	CONSTRAINT pk_admingrant PRIMARY KEY (user_id),
	CONSTRAINT fk_admingrant_user FOREIGN KEY (user_id) REFERENCES app."user" (id),
	CONSTRAINT ck_admingrant_role CHECK (role IN ('admin','viewer')),
	CONSTRAINT ck_admingrant_revision CHECK (revision >= 1)
)
""",
"""CREATE TABLE app.adminsession (
	id VARCHAR(64) NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	user_id VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_adminsession PRIMARY KEY (id),
	CONSTRAINT uq_adminsession_token_hash UNIQUE (token_hash),
	CONSTRAINT fk_adminsession_user FOREIGN KEY (user_id) REFERENCES app."user" (id),
	CONSTRAINT ck_adminsession_token_hash CHECK (token_hash ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_adminsession_expiry CHECK (expires_at > created_at)
)
""",
"""CREATE INDEX ix_adminsession_user ON app.adminsession (user_id)
""",
"""CREATE TABLE app.accountcontrol (
	user_id VARCHAR NOT NULL,
	enabled BOOLEAN NOT NULL,
	revision BIGINT NOT NULL,
	auth_revision BIGINT NOT NULL,
	protected_account BOOLEAN NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_accountcontrol PRIMARY KEY (user_id),
	CONSTRAINT fk_accountcontrol_user FOREIGN KEY (user_id) REFERENCES app."user" (id),
	CONSTRAINT ck_accountcontrol_revision CHECK (revision >= 0 AND auth_revision >= 0)
)
""",
"""CREATE TABLE app.adminaudit (
	event_id VARCHAR(64) NOT NULL,
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
	actor_user_id VARCHAR,
	actor_kind VARCHAR(16) NOT NULL,
	action VARCHAR(64) NOT NULL,
	target_user_id VARCHAR,
	outcome VARCHAR(16) NOT NULL,
	reason VARCHAR(2000),
	request_id VARCHAR(64) NOT NULL,
	changes JSONB,
	CONSTRAINT pk_adminaudit PRIMARY KEY (event_id),
	CONSTRAINT ck_adminaudit_actor_kind CHECK (actor_kind IN ('admin','cli','system','anonymous')),
	CONSTRAINT ck_adminaudit_outcome CHECK (outcome IN ('succeeded','failed','denied'))
)
""",
"""CREATE INDEX ix_adminaudit_recorded ON app.adminaudit (recorded_at DESC, event_id)
""",
"""CREATE INDEX ix_adminaudit_actor ON app.adminaudit (actor_user_id)
""",
"""CREATE INDEX ix_adminaudit_target ON app.adminaudit (target_user_id)
""",
"""CREATE FUNCTION app.adminaudit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
	RAISE EXCEPTION 'adminaudit is append-only';
END
$$
""",
"""CREATE TRIGGER tr_adminaudit_immutable BEFORE UPDATE OR DELETE ON app.adminaudit
FOR EACH ROW EXECUTE FUNCTION app.adminaudit_immutable()
""",
"""CREATE TRIGGER tr_adminaudit_no_truncate BEFORE TRUNCATE ON app.adminaudit
FOR EACH STATEMENT EXECUTE FUNCTION app.adminaudit_immutable()
""",
"""CREATE FUNCTION app.adminaudit_clock() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
	NEW.recorded_at := now();
	RETURN NEW;
END
$$
""",
"""CREATE TRIGGER tr_adminaudit_clock BEFORE INSERT ON app.adminaudit
FOR EACH ROW EXECUTE FUNCTION app.adminaudit_clock()
""",
"""CREATE TABLE app.adminloginthrottle (
	key_hash VARCHAR(64) NOT NULL,
	window_start TIMESTAMP WITH TIME ZONE NOT NULL,
	failures INTEGER NOT NULL,
	CONSTRAINT pk_adminloginthrottle PRIMARY KEY (key_hash),
	CONSTRAINT ck_adminloginthrottle_key CHECK (key_hash ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_adminloginthrottle_failures CHECK (failures >= 0)
)
""",
)


def upgrade():
    roles=_runtime_roles()  # validate before any DDL
    for statement in UPGRADE_SQL:
        op.execute(sa.text(statement))
    for table in TABLES:
        op.execute(sa.text(f'REVOKE ALL ON TABLE app.{table} FROM PUBLIC'))
    for role in roles:
        quoted='"'+role+'"'  # ASCII identifier validated above; never a guessed role.
        for table,privileges in RUNTIME_PRIVILEGES.items():
            op.execute(sa.text(f'REVOKE ALL ON TABLE app.{table} FROM {quoted}'))
            op.execute(sa.text(f'GRANT {",".join(privileges)} ON TABLE app.{table} TO {quoted}'))


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError('Offline downgrade cannot verify that no admin data exists')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE '+', '.join('app.'+table for table in TABLES)+' IN ACCESS EXCLUSIVE MODE'))
    for table in TABLES:
        if connection.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM app.{table})')):
            raise RuntimeError('Refusing downgrade while admin data exists')
    for table in reversed(TABLES):
        op.execute(sa.text(f'DROP TABLE app.{table}'))
    op.execute(sa.text('DROP FUNCTION app.adminaudit_immutable()'))
    op.execute(sa.text('DROP FUNCTION app.adminaudit_clock()'))
