"""Support tickets: supportticket, supportpaymentcheck, membershipreissue (business tables).

One ticket = one question and one answer; at most one open "membership not credited" ticket per
checkout; membershipreissue (checkout_id primary key) makes a re-issue happen at most once per
checkout. Runtime roles may read/insert all three and update tickets only. Downgrade refuses while
any support row exists.
"""
import re
from alembic import context,op
import sqlalchemy as sa

revision='t1_0015'
down_revision='m1_0014'
branch_labels=None
depends_on=None

TABLES=('membershipreissue','supportpaymentcheck','supportticket')  # drop order
RUNTIME_PRIVILEGES={'supportticket':('SELECT','INSERT','UPDATE'),'supportpaymentcheck':('SELECT','INSERT'),
                    'membershipreissue':('SELECT','INSERT')}


def _runtime_roles():
    # Same validation contract as b3b_0004..m1_0014 (kept local: migrations stay self-contained).
    roles=context.config.attributes.get('b3b_runtime_roles')
    if not isinstance(roles,(list,tuple)) or not 1<=len(roles)<=16:
        raise RuntimeError('T1 migration requires explicit runtime roles')
    if any(type(role) is not str or not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',role) or role=='public' for role in roles):
        raise RuntimeError('T1 migration runtime role identifier rejected')
    if len(set(roles))!=len(roles):
        raise RuntimeError('T1 migration runtime role identifiers must be unique')
    if not context.is_offline_mode():
        connection=op.get_bind()
        for role in roles:
            row=connection.execute(sa.text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=:role"),{'role':role}).one_or_none()
            if row is None or any(row[1:]):
                raise RuntimeError('T1 runtime role has unsafe attributes')
    return tuple(roles)


UPGRADE_SQL=(
"""CREATE TABLE app.supportticket (
	id VARCHAR NOT NULL,
	user_id VARCHAR NOT NULL,
	category VARCHAR NOT NULL,
	user_note VARCHAR,
	checkout_id VARCHAR,
	priority VARCHAR NOT NULL,
	state VARCHAR NOT NULL,
	resolution VARCHAR,
	reply_template VARCHAR,
	reply_note VARCHAR,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	resolved_at TIMESTAMP WITH TIME ZONE,
	resolved_by VARCHAR,
	revision BIGINT NOT NULL,
	CONSTRAINT pk_supportticket PRIMARY KEY (id),
	CONSTRAINT fk_supportticket_user_id_user FOREIGN KEY(user_id) REFERENCES app."user" (id) ON DELETE RESTRICT,
	CONSTRAINT fk_supportticket_checkout_id_billingcheckout FOREIGN KEY(checkout_id) REFERENCES app.billingcheckout (id) ON DELETE RESTRICT,
	CONSTRAINT ck_supportticket_category CHECK (category IN ('membership_not_credited','download_failing','login_problem','other')),
	CONSTRAINT ck_supportticket_priority CHECK (priority IN ('priority','normal')),
	CONSTRAINT ck_supportticket_state CHECK (state IN ('open','resolved','rejected')),
	CONSTRAINT ck_supportticket_resolution CHECK (resolution IS NULL OR resolution IN ('reissued','replied','rejected')),
	CONSTRAINT ck_supportticket_checkout CHECK ((category = 'membership_not_credited') = (checkout_id IS NOT NULL)),
	CONSTRAINT ck_supportticket_resolved CHECK ((state = 'open') = (resolved_at IS NULL)),
	CONSTRAINT ck_supportticket_user_note CHECK (user_note IS NULL OR length(user_note) <= 2000),
	CONSTRAINT ck_supportticket_reply_note CHECK (reply_note IS NULL OR length(reply_note) <= 2000)
)
""",
"""CREATE UNIQUE INDEX uq_supportticket_open_checkout ON app.supportticket (checkout_id) WHERE state = 'open' AND category = 'membership_not_credited'
""",
"""CREATE INDEX ix_supportticket_queue ON app.supportticket (state, priority, created_at)
""",
"""CREATE INDEX ix_supportticket_user ON app.supportticket (user_id, created_at)
""",
"""CREATE TABLE app.supportpaymentcheck (
	id VARCHAR NOT NULL,
	ticket_id VARCHAR NOT NULL,
	checkout_id VARCHAR NOT NULL,
	payment_intent VARCHAR,
	result VARCHAR NOT NULL,
	checked_at TIMESTAMP WITH TIME ZONE NOT NULL,
	actor_user_id VARCHAR NOT NULL,
	CONSTRAINT pk_supportpaymentcheck PRIMARY KEY (id),
	CONSTRAINT fk_supportpaymentcheck_ticket_id_supportticket FOREIGN KEY(ticket_id) REFERENCES app.supportticket (id) ON DELETE RESTRICT,
	CONSTRAINT fk_supportpaymentcheck_checkout_id_billingcheckout FOREIGN KEY(checkout_id) REFERENCES app.billingcheckout (id) ON DELETE RESTRICT
)
""",
"""CREATE INDEX ix_supportpaymentcheck_checkout ON app.supportpaymentcheck (checkout_id, checked_at)
""",
"""CREATE TABLE app.membershipreissue (
	checkout_id VARCHAR NOT NULL,
	ticket_id VARCHAR NOT NULL,
	actor_user_id VARCHAR NOT NULL,
	payment_intent VARCHAR NOT NULL,
	granted_days INTEGER NOT NULL,
	expires_before FLOAT NOT NULL,
	expires_after FLOAT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	idempotency_key VARCHAR(128) NOT NULL,
	CONSTRAINT pk_membershipreissue PRIMARY KEY (checkout_id),
	CONSTRAINT fk_membershipreissue_checkout_id_billingcheckout FOREIGN KEY(checkout_id) REFERENCES app.billingcheckout (id) ON DELETE RESTRICT,
	CONSTRAINT fk_membershipreissue_ticket_id_supportticket FOREIGN KEY(ticket_id) REFERENCES app.supportticket (id) ON DELETE RESTRICT,
	CONSTRAINT ck_membershipreissue_granted_days CHECK (granted_days >= 1)
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
        raise RuntimeError('Offline downgrade cannot verify that no support data exists')
    connection=op.get_bind()
    connection.execute(sa.text('LOCK TABLE '+', '.join('app.'+table for table in TABLES)+' IN ACCESS EXCLUSIVE MODE'))
    for table in TABLES:
        if connection.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM app.{table})')):
            raise RuntimeError('Refusing downgrade while support data exists')
    for table in TABLES:
        op.execute(sa.text(f'DROP TABLE app.{table}'))
